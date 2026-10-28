"""FastAPI app factory: settings, CORS, error envelope, store, model wrapper and the session hub (PLAN §6).

Run: `uvicorn crucible.main:app --reload` from backend/ (or `make dev` from the repo root).

The engine (ENG-1, PR #8), contracts (S-1, #5) and model wrapper (ENG-3, #6) are wired here but may not be
merged yet. `_engine()` imports them if they're present, so this scaffold merges in any order and the app
still boots with just /api/health. TODO(S-0): drop the import guard once #5, #6 and #8 are on main.
"""

from __future__ import annotations

import importlib
import inspect
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from crucible import model_setup
from crucible.config import Settings, get_settings
from crucible.defense import router as defense
from crucible.quota import DailyQuota, client_ip
from crucible.runner import make_runner

logger = logging.getLogger(__name__)

SESSIONS_PATH = "/api/sessions"  # POST creates a session: the call the daily quota counts
ROLE_ENV = model_setup.ROLE_ENV  # re-exported: older scripts import it from here


@dataclass(slots=True)
class _EngineParts:
    router: Any
    hub_cls: Any
    controllers: dict[Any, Any]
    store_cls: Any
    problems: Any = None  # the coding ProblemBank, shared by the hub and the problem API


def _app_version() -> str:
    try:
        return version("crucible")
    except PackageNotFoundError:
        return "0.0.0"


def _import(name: str):
    """Import a crucible module that may not be merged yet. Only a missing crucible.* module counts as
    "not there yet"; any other ImportError (a broken dependency) still raises."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("crucible"):
            return None
        raise


def _engine(s: Settings) -> _EngineParts | None:
    api, hub, coding, common, repo = (
        _import(m)
        for m in (
            "crucible.engine.api",
            "crucible.engine.hub",
            "crucible.coding.session",
            "crucible.contracts.common",
            "crucible.store.repo",
        )
    )
    if not all((api, hub, coding, common, repo)):
        return None
    if hasattr(coding, "CodingMode"):  # ENG-4 (#9): the hub takes mode factories
        bank = _import("crucible.coding.problems").ProblemBank.load(strict=False)
        controllers = {common.Mode.CODING: coding.CodingMode(bank, runner=lambda: make_runner(s))}
    else:  # ENG-1 (#8): the hub takes controller classes
        bank, controllers = None, {common.Mode.CODING: coding.CodingController}
    defense = _import("crucible.defense.controller")  # DEF-6; until then defense sessions get 400
    if defense is not None:
        controllers[common.Mode.DEFENSE] = defense.make_mode(s)
    return _EngineParts(
        router=api.router,
        hub_cls=hub.SessionHub,
        controllers=controllers,
        store_cls=repo.SqliteStore,
        problems=bank,
    )


def _configure_models(s: Settings) -> Any | None:
    """Configure the model wrapper; returns the LLM, or None without a key."""
    return model_setup.configure_models(s)


def _configure_asr(s: Settings) -> Any | None:
    """Muse Voice Transcribe for the voice bridge; None without a key (the audio socket then says so)."""
    asr = _import("crucible.models.asr")
    if asr is None or not s.has_meta_key:
        return None
    return asr.MuseASR(asr.ASRSettings(api_key=s.MODEL_API_KEY, realtime_url=s.ASR_URL, model=s.ASR_MODEL))


def _error(status: int, code: str, message: str) -> JSONResponse:
    """PLAN §8.1 error envelope (`ApiError` in contracts/common.py)."""
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    if s.is_production and (problems := s.production_problems()):
        raise RuntimeError(f"refusing to start in production: {'; '.join(problems)}")
    engine = _engine(s)
    if engine is None:
        logger.warning("engine not merged yet (#5/#8): serving /api/health only")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = s
        app.state.problems = engine.problems if engine is not None else None
        await defense.startup(app, s)
        store = hub = None
        if engine is not None and not s.MOCK:
            model = _configure_models(s)
            store = await engine.store_cls.open(s.database_path)
            params = inspect.signature(engine.hub_cls).parameters
            extras = {"model": model, "asr": _configure_asr(s)}
            hub = engine.hub_cls(
                store, engine.controllers, **{k: v for k, v in extras.items() if k in params}
            )
            app.state.store, app.state.hub = store, hub
        try:
            yield
        finally:
            if hub is not None:
                await hub.close()
            if store is not None:
                await store.close()
            await defense.shutdown(app)

    app = FastAPI(title="Crucible", version=_app_version(), lifespan=lifespan)
    if not s.MOCK:
        quota = DailyQuota(s.MAX_SESSIONS_PER_IP_PER_DAY)

        @app.middleware("http")
        async def _session_quota(request: Request, call_next):
            """Caps new sessions per client per day; a failed creation gives its slot back."""
            if request.method != "POST" or request.url.path != SESSIONS_PATH:
                return await call_next(request)
            client = client_ip(request, behind_proxy=s.BEHIND_PROXY)
            if not quota.take(client):
                logger.warning("session quota reached for a client (%d/day)", quota.limit)
                return _error(429, "rate_limited", "Daily session limit reached. Try again tomorrow.")
            response = await call_next(request)
            if response.status_code != 201:
                quota.give_back(client)
            return response

    # Added last so it wraps everything: the quota's 429 still carries CORS headers the browser can read.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()))
        return _error(422, "invalid_request", f"{where}: {first.get('msg', 'invalid request')}")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else f"http_{exc.status_code}"
        return _error(exc.status_code, code, str(exc.detail))

    @app.get("/api/health")
    async def health() -> dict:
        """`Health` in contracts/common.py: {ok, version, mock}."""
        return {"ok": True, "version": app.version, "mock": s.MOCK}

    if s.MOCK:
        # Recorded sessions instead of the live hub (PLAN §14.6). Only ever on when MOCK=1 is set.
        from crucible.mock.replay import router as mock_router

        app.include_router(mock_router)
    elif engine is not None:
        app.include_router(engine.router)
    if engine is not None and engine.problems is not None:
        from crucible.coding.api import router as problems_router

        app.include_router(problems_router)
    app.include_router(defense.router)
    if s.DEFENSE_DEV_API:
        app.include_router(defense.dev_router)
    return app


app = create_app()
