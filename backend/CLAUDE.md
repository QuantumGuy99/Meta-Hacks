# How backend code is written (Crucible, Python 3.12)

Loaded whenever you work under `backend/`. Architecture rules are in the root CLAUDE.md and PLAN.md;
this file is about the code itself. For file skeletons and templates, use the `crucible-code` skill.

## Stack and tooling
- Python 3.12, FastAPI, Pydantic v2, SQLModel, `openai` SDK (Meta base URL), `modal`, `httpx`, `websockets`.
- `uv` for everything: `uv add <pkg>` (say why in the PR), `uv run ...`. Never `pip install`.
- ruff is the formatter and linter (line length 110). Code must pass `uv run ruff check` and
  `uv run ruff format --check` before you finish.

## Types and data
- Type hints on every function signature and module-level constant. Built-in generics and unions:
  `list[str]`, `dict[str, int]`, `X | None`. No `typing.List`, `Optional` or `Dict`.
- Data that crosses a boundary (WebSocket, REST, timeline, LLM output, sandbox stdout) is a contract
  model from `crucible.contracts`. Never pass raw dicts between modules; validate at the edge with
  `Model.model_validate(...)` / `model_validate_json(...)`.
- Internal-only structs: `@dataclass(slots=True)` or a plain Pydantic model in the module, not a dict.
- Enums are `StrEnum`; closed string sets are `Literal[...]`.
- IDs: `uuid4().hex[:12]`. Times on the timeline: `int` milliseconds since session start. Durations in
  names carry the unit: `timeout_s`, `elapsed_ms`.

## Async and I/O (this product exists to catch the opposite, so get it right)
- Every I/O function is `async def`. Never call blocking I/O (`time.sleep`, `requests`, sync file or DB
  calls in hot paths) inside a coroutine. CPU-heavy or sync-only work goes through `asyncio.to_thread`.
- Every external call (model, ASR, SAM, Modal, HTTP) is wrapped in `async with asyncio.timeout(...)` using
  the timeouts in PLAN §21, and has a fallback path. No call can hang a WebSocket.
- Shared mutable state per session is guarded with `asyncio.Lock` or lives in a single task. No
  check-then-act across an `await` without a lock.
- Background tasks are created with a reference kept (`TaskGroup` or a stored task set), never
  fire-and-forget `asyncio.create_task(...)` that can be garbage-collected or swallow errors.

## Errors and fallbacks
- Catch specific exceptions only. No bare `except:`; `except Exception` only at a task/handler boundary,
  where it logs with `logger.exception` and turns into an `error` message or `system` timeline note.
- A fallback is explicit code, not a silent default: log it, append a `system` timeline note naming the
  fallback, and keep going. Never return fake or recorded data outside `MOCK=1`.
- Module-specific failures get a small exception class (`class AttackRejected(Exception)`), raised with
  a message a human can act on.

## Configuration, secrets and logging
- Read settings only through `crucible.config.settings`. No `os.getenv` / `os.environ` anywhere else.
- `logger = logging.getLogger(__name__)` per module. No `print` outside CLIs and the sandbox harness.
- Never log secrets, full prompts, full candidate code or audio. Log ids, sizes, latencies, model names.

## Design
- **LLM suggests, code decides:** model calls return contract models; the decision (score, verdict,
  phase change, what the user sees) is a pure function in plain Python that tests can drive directly.
- Pure functions for logic, thin async shells for I/O. Pass clocks (`now_ms`) and randomness in as
  arguments so tests are deterministic.
- Model calls only through `crucible.models` wrappers; model ids only in `models/registry.py`.
  Prompts only in `prompts/*.md`, loaded at startup; no prompt strings longer than one line in code.
- Functions do one thing and stay short (aim < 40 lines). Module names are nouns (`grill.py`), function
  names are verbs (`score_answer`). No `utils.py` / `helpers.py` dumping grounds.
- Public API at the top of a module (after constants), private helpers (`_name`) below.

## Comments and docs
- One-line module docstring saying what the module is for. Docstrings on public functions whose
  behaviour isn't obvious from the name and types.
- Comments explain *why* (a constraint, a gotcha, a PLAN section), never restate the code. Reference
  PLAN sections like `# PLAN §11.5`. No commented-out code, no TODOs without a WP id (`# TODO(DEF-8): ...`).
- No license headers.

## Tests
- pytest + pytest-asyncio; `backend/tests/` mirrors `crucible/` (`crucible/defense/grill.py` →
  `tests/defense/test_grill.py`).
- Unit tests never touch the network: fake the model wrapper with recorded contract objects, use
  LocalRunner or a fake Runner. Network/Modal tests are marked `@pytest.mark.integration`.
- Every decision rule gets a "fires" and a "doesn't fire" test. Every fallback gets a test that forces
  the failure (timeout, bad JSON, rejected script).
- Test names say the behaviour: `test_verdict_fails_when_root_cause_missed`.

## Before you say you're done
1. `uv run ruff format backend/ && uv run ruff check backend/`
2. `uv run pytest backend/tests/<area>/` then `MOCK=1 uv run pytest`
3. If contracts changed: `make contracts` and updated fixtures.
4. Update `docs/defense/MEMORY.md` (status, handoff, session log; release your claim).
