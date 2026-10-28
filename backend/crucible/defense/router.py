"""Defense REST API (PLAN §8.1) plus a dev-only API that runs the whole pipeline standalone."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from crucible.config import Settings
from crucible.contracts.defense import Project, ProjectSource
from crucible.defense.model_client import WrapperModelClient
from crucible.defense.pipeline import DefensePipeline, run_scripted
from crucible.defense.ports import MemorySink
from crucible.defense.projects import Sample, load_samples
from crucible.runner import make_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/defense", tags=["defense"])
dev_router = APIRouter(prefix="/api/defense/dev", tags=["defense-dev"])


@router.get("/samples", response_model=list[Project])
async def list_samples(request: Request) -> list[Project]:
    return [s.project for s in _samples(request).values()]


@router.get("/projects/{project_id}/files", response_model=ProjectSource)
async def project_files(project_id: str, request: Request) -> ProjectSource:
    """The project's source for the editor and the audit preview (PLAN §11.6, §14.4). Samples only: the
    candidate fixes these files, so they aren't secret. Uploads (P1) must check the session that owns them."""
    sample = _samples(request).get(project_id)
    if sample is None:
        raise HTTPException(404, f"unknown project {project_id!r}")
    return ProjectSource(project_id=project_id, files=dict(sample.files))


class DevRunRequest(BaseModel):
    project_id: str
    answer: str = Field(description="The candidate's grill answer, used for every broken finding")
    apply_reference_fix: bool = True
    duration_s: int | None = Field(default=None, ge=1, le=30)


class DevRunStatus(BaseModel):
    run_id: str
    status: Literal["running", "done", "failed"]
    error: str | None = None
    verdict: dict | None = None
    events: list[dict]


@dev_router.post("/runs", response_model=DevRunStatus, status_code=202)
async def start_dev_run(body: DevRunRequest, request: Request) -> DevRunStatus:
    sample = _samples(request).get(body.project_id)
    if sample is None:
        raise HTTPException(404, f"unknown project {body.project_id!r}")
    if body.apply_reference_fix and sample.fixed_files is None:
        raise HTTPException(422, f"{body.project_id} has no reference fix (fix.patch or fixed/)")
    run_id = uuid.uuid4().hex[:12]
    sink = MemorySink()
    runs = request.app.state.dev_runs
    runs[run_id] = {"status": "running", "error": None, "verdict": None, "sink": sink}
    task = asyncio.create_task(_run(runs[run_id], sample, body, sink, request.app.state.defense_settings))
    request.app.state.tasks.add(task)
    task.add_done_callback(request.app.state.tasks.discard)
    return _status(run_id, runs[run_id])


@dev_router.get("/runs/{run_id}", response_model=DevRunStatus)
async def get_dev_run(run_id: str, request: Request) -> DevRunStatus:
    run = request.app.state.dev_runs.get(run_id)
    if run is None:
        raise HTTPException(404, "unknown run")
    return _status(run_id, run)


async def _run(
    entry: dict, sample: Sample, body: DevRunRequest, sink: MemorySink, settings: Settings
) -> None:
    try:
        pipeline = DefensePipeline(
            sample,
            make_runner(settings),
            WrapperModelClient(),
            sink,
            duration_override_s=body.duration_s,
        )
        verdict = await run_scripted(
            pipeline, body.answer, sample.fixed_files if body.apply_reference_fix else None
        )
        entry.update(status="done", verdict=verdict.model_dump(mode="json"))
    except Exception as exc:  # task boundary: report, never crash the server
        logger.exception("dev run failed")
        entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")


def _status(run_id: str, entry: dict) -> DevRunStatus:
    return DevRunStatus(
        run_id=run_id,
        status=entry["status"],
        error=entry["error"],
        verdict=entry["verdict"],
        events=entry["sink"].public_events(),
    )


def _samples(request: Request) -> dict[str, Sample]:
    return request.app.state.samples


async def startup(app: FastAPI, settings: Settings) -> None:
    """Load the sample apps and set up dev-run bookkeeping (called from main.py's lifespan)."""
    app.state.defense_settings = settings
    app.state.samples = await asyncio.to_thread(
        load_samples, settings.DEFENSE_APPS_DIR, settings.DEFENSE_EXTRA_APPS_DIR
    )
    app.state.dev_runs = {}
    app.state.tasks = set()
    logger.info("loaded %d defense sample(s)", len(app.state.samples))


async def shutdown(app: FastAPI) -> None:
    for task in list(getattr(app.state, "tasks", ())):
        task.cancel()
