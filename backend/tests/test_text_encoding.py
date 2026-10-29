"""Every text read and write names its encoding. Without one, Python uses the platform's default: UTF-8 on
Linux and Mac, but cp1252 on Windows, where "→" in a problem statement is served as "â†’" and a "”" in a
prompt fails to load at all."""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
# As ruff's extend-exclude: the chaos template has placeholders until it's rendered, and the fixture apps
# imitate a candidate's code.
SKIP = ("crucible/runner/harness/chaos_template.py", "tests/fixtures/apps/")
SOURCES = [
    p
    for p in sorted((BACKEND / "crucible").rglob("*.py")) + sorted((BACKEND / "tests").rglob("*.py"))
    if not p.relative_to(BACKEND).as_posix().startswith(SKIP)
]
TEXT_METHODS = {"read_text", "write_text"}


def _has_encoding(call: ast.Call) -> bool:
    return any(k.arg == "encoding" for k in call.keywords)


def _text_mode_open(call: ast.Call) -> bool:
    """open(path) or open(path, "r"/"w"/...): text mode unless the mode has a "b"."""
    mode = (
        call.args[1]
        if len(call.args) > 1
        else next((k.value for k in call.keywords if k.arg == "mode"), None)
    )
    return not (isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" in mode.value)


def _unnamed_encodings(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call) or _has_encoding(node):
            continue
        func = node.func
        name = (
            func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        )
        text_subprocess = name in ("run", "check_output", "Popen") and any(
            k.arg in ("text", "universal_newlines") for k in node.keywords
        )
        if name in TEXT_METHODS or (name == "open" and isinstance(func, ast.Name) and _text_mode_open(node)):
            found.append(f"{path.relative_to(BACKEND)}:{node.lineno} {name}()")
        elif text_subprocess:
            found.append(f"{path.relative_to(BACKEND)}:{node.lineno} {name}(text=True)")
    return found


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: str(p.relative_to(BACKEND)))
def test_text_io_names_its_encoding(path: Path) -> None:
    assert _unnamed_encodings(path) == [], "add encoding='utf-8'"
