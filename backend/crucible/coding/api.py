"""Problem REST routes (PLAN §8.1, COD-1). The browser only ever gets `ProblemPublic`: no hidden tests,
rubric or reference solution."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from crucible.coding.problems import ProblemBank
from crucible.contracts.coding import ProblemPublic, ProblemSpec, ProblemSummary
from crucible.contracts.common import ApiError, ApiErrorBody, Difficulty

router = APIRouter(prefix="/api/problems", tags=["problems"])


@router.get("", response_model=list[ProblemSummary])
async def list_problems(
    request: Request, difficulty: Difficulty | None = None, topic: str | None = None
) -> list[ProblemSummary]:
    return [summary(p) for p in _bank(request).matching(difficulty, topic)]


@router.get("/{slug}", response_model=ProblemPublic, responses={404: {"model": ApiError}})
async def get_problem(slug: str, request: Request) -> ProblemPublic | JSONResponse:
    spec = _bank(request).get(slug)
    if spec is None:
        body = ApiError(error=ApiErrorBody(code="problem_not_found", message=f"No problem called {slug}."))
        return JSONResponse(status_code=404, content=body.model_dump())
    return public(spec)


def summary(spec: ProblemSpec) -> ProblemSummary:
    return ProblemSummary(slug=spec.slug, title=spec.title, difficulty=spec.difficulty, topics=spec.topics)


def public(spec: ProblemSpec) -> ProblemPublic:
    return ProblemPublic(
        slug=spec.slug,
        title=spec.title,
        difficulty=spec.difficulty,
        topics=spec.topics,
        statement_md=spec.statement_md,
        examples=spec.examples,
        constraints=spec.constraints,
        starter_code=spec.starter_code,
        tests_visible=spec.tests_visible,
        illustration_url=None,  # TODO(DATA-6): serve illustrations
        time_limit_min=spec.time_limit_min,
    )


def _bank(request: Request) -> ProblemBank:
    return request.app.state.problems
