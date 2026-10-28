"""Tests for the contracts (PLAN §7): fixtures validate, LLM schemas are strict-mode safe, unions round-trip."""

import json
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from crucible.contracts import coding, common, defense, events, export, report, ws

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

MODEL_FIXTURES: dict[str, type[BaseModel]] = {
    "session_config.json": common.SessionConfig,
    "session.json": common.Session,
    "problem_spec.json": coding.ProblemSpec,
    "problem_public.json": coding.ProblemPublic,
    "analysis.json": coding.Analysis,
    "intervention_text.json": events.InterventionText,
    "project.json": defense.Project,
    "audit_result.json": defense.AuditResult,
    "attack_functions.json": defense.AttackFunctions,
    "grill_eval.json": defense.GrillEval,
    "report_draft.json": report.ReportDraft,
    "report_coding.json": report.Report,
    "report_defense.json": report.Report,
}

REST_FIXTURES: dict[str, type[BaseModel]] = {
    "health": common.Health,
    "api_error": common.ApiError,
    "report_pending": common.ReportPending,
}

# Used as structured-output schemas (PLAN §7: no defaults, every field required, depth ≤ 10).
LLM_OUTPUT_MODELS: list[type[BaseModel]] = [
    coding.Analysis,
    events.InterventionText,
    defense.AuditResult,
    defense.AttackFunctions,
    defense.GrillEval,
    report.ReportDraft,
    events.TurnLabel,
    coding.ComplexityClaim,
]

# TODO(ENG-1): replace with engine.timeline.PAYLOAD_MODELS once it exists.
PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "phase": events.PhaseChange,
    "editor": events.EditorEvent,
    "snapshot": events.CodeSnapshot,
    "transcript": events.TranscriptTurn,
    "run": events.RunResult,
    "intervention": events.Intervention,
    "integrity": events.IntegrityFlag,
    "system": events.SystemNote,
    "model_activity": events.ModelActivity,
}

CLIENT = TypeAdapter(ws.ClientMessage)
SERVER = TypeAdapter(ws.ServerMessage)


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def _message_types(union: Any) -> set[str]:
    members = get_args(get_args(union)[0])
    return {get_args(m.model_fields["type"].annotation)[0] for m in members}


@pytest.mark.parametrize(("filename", "model"), MODEL_FIXTURES.items())
def test_fixture_validates(filename: str, model: type[BaseModel]) -> None:
    model.model_validate(_load(filename))


@pytest.mark.parametrize(("key", "model"), REST_FIXTURES.items())
def test_rest_fixture_validates(key: str, model: type[BaseModel]) -> None:
    model.model_validate(_load("rest.json")[key])


def test_timeline_fixture_payloads_match_their_kind() -> None:
    for raw in _load("timeline_events.json"):
        event = events.TimelineEvent.model_validate(raw)
        PAYLOAD_MODELS[event.kind].model_validate(event.payload)


@pytest.mark.parametrize(
    ("adapter", "union", "filename"),
    [(CLIENT, ws.ClientMessage, "client_messages.json"), (SERVER, ws.ServerMessage, "server_messages.json")],
    ids=["client", "server"],
)
def test_every_message_type_round_trips(adapter: TypeAdapter, union: Any, filename: str) -> None:
    messages = _load(filename)
    assert {m["type"] for m in messages} == _message_types(union)
    for raw in messages:
        parsed = adapter.validate_python(raw)
        assert parsed.model_dump(mode="json", exclude_unset=True) == raw


@pytest.mark.parametrize("model", LLM_OUTPUT_MODELS, ids=lambda m: m.__name__)
def test_llm_output_schema_is_strict_mode_safe(model: type[BaseModel]) -> None:
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    for obj in [schema, *defs.values()]:
        if "properties" not in obj:
            continue  # enums
        assert obj.get("additionalProperties") is False, obj.get("title")
        assert set(obj.get("required", [])) == set(obj["properties"]), obj.get("title")
    assert '"default"' not in json.dumps(schema)
    assert _depth(schema, defs) <= 10


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        CLIENT.validate_python({"type": "hello", "client_now_ms": 1, "api_key": "x"})


def test_public_models_have_no_room_for_answers() -> None:
    assert not {"tests_hidden", "rubric", "reference_solution", "brute_force_solution"} & set(
        coding.ProblemPublic.model_fields
    )
    assert not {"explanation", "grill", "fix_steps", "chaos"} & set(defense.FindingPublic.model_fields)


def test_audit_message_rejects_a_full_finding() -> None:
    full = _load("audit_result.json")
    with pytest.raises(ValidationError):
        SERVER.validate_python({"type": "defense.audit", "audit": full})


def test_circle_image_size_is_capped() -> None:
    too_big = "A" * (ws.MAX_CIRCLE_IMAGE_B64 + 1)
    with pytest.raises(ValidationError):
        CLIENT.validate_python(
            {"type": "defense.circle", "finding_id": "f1", "source": "webcam", "image_b64": too_big}
        )


def test_export_schema_names_every_top_level_type() -> None:
    definitions = export.build_schema()["definitions"]
    assert set(export.TOP_LEVEL) <= set(definitions)
    assert all(schema["title"] == name for name, schema in definitions.items())


def _depth(node: Any, defs: dict[str, Any], level: int = 0) -> int:
    # Object nesting depth, following $refs (the contracts have no recursive types).
    if isinstance(node, list):
        return max([level, *(_depth(item, defs, level) for item in node)])
    if not isinstance(node, dict):
        return level
    if "$ref" in node:
        return _depth(defs[node["$ref"].rsplit("/", 1)[-1]], defs, level)
    here = level + 1 if node.get("type") == "object" else level
    children = [v for k, v in node.items() if k != "$defs"]
    return max([here, *(_depth(child, defs, here) for child in children)])
