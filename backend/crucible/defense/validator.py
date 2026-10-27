"""AST validator for model-written attack bodies, run before anything executes (PLAN §11.4)."""

from __future__ import annotations

import ast
import textwrap

from crucible.contracts.defense import AttackFunctions

MAX_BODY_CHARS = 4000
BANNED_NAMES = frozenset(
    {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
        "input",
        "exit",
        "quit",
        "memoryview",
        "os",
        "sys",
        "subprocess",
        "socket",
        "pathlib",
        "shutil",
        "importlib",
        "builtins",
        "ctypes",
        "signal",
        "threading",
        "multiprocessing",
    }
)
TEMPLATE_NAMES = frozenset({"BASE", "CONCURRENCY", "DURATION_S", "METRIC_INTERVAL_S"})


class AttackRejected(Exception):
    """The attack bodies broke a validator rule; the message is fed back to the model once."""


def validate_functions(fn: AttackFunctions) -> None:
    for label, body in (
        ("setup_body", fn.setup_body),
        ("request_body", fn.request_body),
        ("invariant_body", fn.invariant_body),
    ):
        _validate_body(label, body)


def _validate_body(label: str, body: str) -> None:
    if not body.strip():
        raise AttackRejected(f"{label} is empty")
    if len(body) > MAX_BODY_CHARS:
        raise AttackRejected(f"{label} is longer than {MAX_BODY_CHARS} characters")
    try:
        tree = ast.parse("async def _f():\n" + textwrap.indent(textwrap.dedent(body), "    "))
    except SyntaxError as exc:
        raise AttackRejected(f"{label} doesn't parse: {exc.msg} (line {exc.lineno})") from exc
    for node in ast.walk(tree):
        problem = _check(node)
        if problem:
            raise AttackRejected(f"{label}: {problem}")


def _check(node: ast.AST) -> str | None:
    if isinstance(node, ast.Import | ast.ImportFrom):
        return "imports aren't allowed; the template already imports what you need"
    if isinstance(node, ast.Global | ast.Nonlocal):
        return "global/nonlocal isn't allowed"
    if isinstance(node, ast.Name):
        if node.id in BANNED_NAMES:
            return f"`{node.id}` isn't allowed"
        if isinstance(node.ctx, ast.Store) and (node.id in TEMPLATE_NAMES or node.id.startswith("_")):
            return f"assigning to `{node.id}` isn't allowed"
    if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
        return f"dunder attribute `{node.attr}` isn't allowed"
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and "://" in node.value:
        return 'URLs must be built from BASE (e.g. f"{BASE}/path"), not written out'
    return None
