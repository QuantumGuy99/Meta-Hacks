"""Defense REST API (PLAN §8.1) plus a dev-only API that runs the whole pipeline standalone."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from crucible.config import Settings
from crucible.contracts.defense import Project, ProjectSource
from crucible.defense.model_client import WrapperModelClient
from crucible.defense.pipeline import DefensePipeline, run_scripted
from crucible.defense.ports import MemorySink
from crucible.defense.projects import ProjectInvalid, Sample, load_samples
from crucible.defense.uploads import MAX_CONTEXT_CHARS, MAX_ZIP_BYTES, ProjectLibrary, make_upload
from crucible.quota import DailyQuota, client_ip
from crucible.runner import make_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/defense", tags=["defense"])
dev_router = APIRouter(prefix="/api/defense/dev", tags=["defense-dev"])


@router.get("/samples", response_model=list[Project])
async def list_samples(request: Request) -> list[Project]:
    return [s.project for s in _samples(request).values()]


@router.post("/projects", response_model=Project, status_code=201)
async def upload_project(request: Request, name: str = "project.zip") -> Project | JSONResponse:
    """A candidate's own project as a zip (PLAN §8.1, limits §11.1), sent as the raw body (`application/zip`),
    so no multipart parser is needed. Returns its Project; start a session with its id."""
    s = request.app.state.settings
    quota: DailyQuota = request.app.state.upload_quota
    if not quota.take(client_ip(request, behind_proxy=s.BEHIND_PROXY)):
        raise HTTPException(429, "You've uploaded a lot of projects today. Try again tomorrow.")
    data = await _read_capped(request, MAX_ZIP_BYTES)
    if data is None:
        return _invalid(413, f"the zip is over the {MAX_ZIP_BYTES // (1024 * 1024)} MB limit")
    try:
        sample = await asyncio.to_thread(make_upload, name, data)
    except ProjectInvalid as exc:
        return _invalid(400, f"Couldn't use that project: {exc}")
    await _library(request).add(sample)
    logger.info(
        "uploaded project %s: %d files, %d lines", sample.project.id, len(sample.files), sample.project.loc
    )
    return sample.project


@router.put("/projects/{project_id}/context", status_code=204)
async def project_context(project_id: str, request: Request) -> None:
    """Notes about an uploaded project for the audit (a .txt the candidate attaches), as the raw text body."""
    body = await _read_capped(request, MAX_CONTEXT_CHARS * 4)  # utf-8 is at most 4 bytes a character
    if body is None:
        raise HTTPException(413, f"the context file is over {MAX_CONTEXT_CHARS:,} characters")
    try:
        await _library(request).set_context(project_id, body.decode("utf-8", errors="replace"))
    except LookupError as exc:
        raise HTTPException(404, f"no uploaded project {project_id!r}") from exc
    except ProjectInvalid as exc:
        raise HTTPException(400, f"Couldn't use that context file: {exc}") from exc


@router.get("/projects/{project_id}/files", response_model=ProjectSource)
async def project_files(project_id: str, request: Request) -> ProjectSource:
    """The project's source for the editor and the audit preview (PLAN §11.6, §14.4). Samples aren't secret;
    an upload is private to whoever has its random id (nothing lists uploads)."""
    sample = await _library(request).load(project_id)
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


def _library(request: Request) -> ProjectLibrary:
    """The Defense mode's library (main.py shares it, with the store), or one over the samples alone."""
    state = request.app.state
    if getattr(state, "projects", None) is None:
        state.projects = ProjectLibrary(state.samples)
    return state.projects


async def _read_capped(request: Request, limit: int) -> bytes | None:
    """The request body, or None once it passes `limit`: reading stops there, so a huge body is never held."""
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > limit:
            return None
    return bytes(data)


def _invalid(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": "project_invalid", "message": message}}
    )


async def startup(app: FastAPI, settings: Settings) -> None:
    """Load the sample apps and set up dev-run bookkeeping (called from main.py's lifespan)."""
    app.state.defense_settings = settings
    app.state.samples = await asyncio.to_thread(
        load_samples, settings.DEFENSE_APPS_DIR, settings.DEFENSE_EXTRA_APPS_DIR
    )
    app.state.dev_runs = {}
    app.state.tasks = set()
    logger.info("loaded %d defense sample(s)", len(app.state.samples))
    if settings.RUNNER == "modal" and settings.has_modal and not settings.MOCK:
        task = asyncio.create_task(_prebuild_images(settings, list(app.state.samples.values())))
        app.state.tasks.add(task)
        task.add_done_callback(app.state.tasks.discard)


async def _prebuild_images(settings: Settings, samples: list[Sample]) -> None:
    """Build the Modal images in the background at startup, so the first session doesn't wait minutes for
    one (#22 item 8). A failure only means the first session builds it instead."""
    from crucible.runner.modal_runner import ModalRunner

    try:
        await ModalRunner(settings).prebuild(s.files for s in samples)
    except Exception:  # background task boundary: log and let sessions build on demand
        logger.exception("modal: prebuilding images failed; sessions will build them on demand")


async def shutdown(app: FastAPI) -> None:
    for task in list(getattr(app.state, "tasks", ())):
        task.cancel()
