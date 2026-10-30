"""Project store for sample apps: load, enforce limits, hash (PLAN §11.1, §13.2). Zip upload is P1."""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from crucible.contracts.defense import AttackFunctions, Project, ProjectFile

logger = logging.getLogger(__name__)

MAX_FILES = 60
MAX_LINES = 6000
DEFAULT_ENTRYPOINT = "uvicorn app.main:app --host 127.0.0.1 --port 8080"
DEFAULT_PORT = 8080
META_FILES = {"crucible.json", "flaws.json", "reference_attack.json", "fix.patch", "README.md"}
SKIP_DIRS = {".git", "venv", ".venv", "node_modules", "__pycache__", "fixed"}
TEXT_SUFFIXES = {".py", ".txt", ".toml", ".cfg", ".ini", ".json", ".sql", ".html", ".md", ".yaml", ".yml"}


class ProjectInvalid(Exception):
    """The project breaks the limits in PLAN §11.1 or can't be read."""


@dataclass(slots=True)
class ReferenceAttack:
    concurrency: int
    duration_s: int
    functions: AttackFunctions
    flaw_id: str | None = None  # None: applies to the app's first finding with a chaos plan


@dataclass(slots=True)
class Sample:
    project: Project
    files: dict[str, str]
    flaws: list[dict] = field(default_factory=list)
    # reference_attack.json holds one attack or a list (one per flaw, e.g. ticket-drop's race and its O(n²) loop)
    reference_attacks: list[ReferenceAttack] = field(default_factory=list)
    fixed_files: dict[str, str] | None = None  # the reference fix applied (fix.patch or fixed/)

    @property
    def reference_attack(self) -> ReferenceAttack | None:
        """The first reference attack (the one for the app's headline flaw)."""
        return self.reference_attacks[0] if self.reference_attacks else None

    def reference_for(self, flaw_id: str, first_chaos_id: str | None) -> ReferenceAttack | None:
        """The reference attack for `flaw_id`. One without a flaw_id belongs to the first finding with a chaos
        plan (`first_chaos_id`)."""
        for ref in self.reference_attacks:
            if ref.flaw_id == flaw_id or (ref.flaw_id is None and first_chaos_id == flaw_id):
                return ref
        return None


def load_samples(*dirs: Path | None) -> dict[str, Sample]:
    """Every sub-directory with an `app/` folder becomes a sample. Bad samples are skipped with a log.
    Cached per set of directories: main.py's defense mode and the defense router share one load."""
    return _load_samples(tuple(d.resolve() if d is not None else None for d in dirs))


@lru_cache(maxsize=8)
def _load_samples(dirs: tuple[Path | None, ...]) -> dict[str, Sample]:
    out: dict[str, Sample] = {}
    for root in dirs:
        if root is None or not root.is_dir():
            continue
        for d in sorted(p for p in root.iterdir() if (p / "app").is_dir()):
            try:
                s = load_project_dir(d)
            except (ProjectInvalid, OSError, UnicodeDecodeError) as exc:  # one bad sample never stops startup
                logger.error("skipping sample %s: %s", d.name, exc)
                continue
            out[s.project.id] = s
    return out


def load_project_dir(d: Path, *, source: str = "sample") -> Sample:
    files = _read_files(d)
    meta = _read_json(d / "crucible.json") or {}
    project = build_project(
        d.name,
        files,
        source=source,
        entrypoint=meta.get("entrypoint", DEFAULT_ENTRYPOINT),
        port=int(meta.get("port", DEFAULT_PORT)),
    )
    flaws = _read_json(d / "flaws.json") or []
    return Sample(
        project=project,
        files=files,
        flaws=flaws,
        reference_attacks=_reference_attacks(_read_json(d / "reference_attack.json")),
        fixed_files=_reference_fix(d, files),
    )


def build_project(name: str, files: dict[str, str], *, source: str, entrypoint: str, port: int) -> Project:
    if not files:
        raise ProjectInvalid("no source files")
    if len(files) > MAX_FILES:
        raise ProjectInvalid(f"{len(files)} files (limit {MAX_FILES})")
    loc = sum(c.count("\n") + 1 for c in files.values())
    if loc > MAX_LINES:
        raise ProjectInvalid(f"{loc} lines (limit {MAX_LINES})")
    return Project(
        id=name,
        name=name,
        source=source,
        entrypoint=entrypoint,
        port=port,
        files=[ProjectFile(path=p, size=len(c.encode())) for p, c in sorted(files.items())],
        loc=loc,
        content_hash=content_hash(files),
    )


def content_hash(files: dict[str, str]) -> str:
    h = hashlib.sha256()
    for path, content in sorted(files.items()):
        h.update(path.encode() + b"\0" + content.encode() + b"\0")
    return h.hexdigest()


def numbered_source(files: dict[str, str]) -> str:
    """File tree + every file with line numbers: the audit prompt's project block."""
    parts = ["# File tree", *sorted(files), ""]
    for path, content in sorted(files.items()):
        parts.append(f"# {path}")
        parts += [f"{i:4d} | {line}" for i, line in enumerate(content.splitlines(), 1)]
        parts.append("")
    return "\n".join(parts)


def _read_files(d: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for p in sorted(d.rglob("*")):
        rel = p.relative_to(d)
        if not p.is_file() or set(rel.parts) & SKIP_DIRS:
            continue
        if len(rel.parts) == 1 and rel.name in META_FILES:
            continue
        if p.suffix not in TEXT_SUFFIXES:
            continue
        try:
            files[rel.as_posix()] = p.read_text()
        except UnicodeDecodeError as exc:
            raise ProjectInvalid(f"{rel} isn't UTF-8 text") from exc
    return files


def _read_json(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise ProjectInvalid(f"{p.name} isn't valid JSON: {exc}") from exc


def _reference_attacks(raw: dict | list | None) -> list[ReferenceAttack]:
    items = raw if isinstance(raw, list) else [raw] if raw else []
    try:
        refs = [
            ReferenceAttack(
                concurrency=int(ref["concurrency"]),
                duration_s=int(ref["duration_s"]),
                functions=AttackFunctions.model_validate(ref["functions"]),
                flaw_id=ref.get("flaw_id"),
            )
            for ref in items
        ]
    except (KeyError, TypeError, ValueError) as exc:  # ValidationError is a ValueError
        raise ProjectInvalid(f"reference_attack.json is invalid: {exc}") from exc
    ids = [r.flaw_id for r in refs]
    if len(ids) != len(set(ids)):
        raise ProjectInvalid("reference_attack.json has two attacks for the same flaw")
    return refs


def _reference_fix(d: Path, files: dict[str, str]) -> dict[str, str] | None:
    fixed_dir = d / "fixed"
    if fixed_dir.is_dir():
        return {
            **files,
            **{
                p.relative_to(fixed_dir).as_posix(): p.read_text()
                for p in fixed_dir.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts
            },
        }
    patch = d / "fix.patch"
    if patch.exists():
        return apply_patch(files, patch.read_text())
    return None


def apply_patch(files: dict[str, str], patch_text: str) -> dict[str, str]:
    """Apply a unified diff (-p1) to an in-memory file set; used at startup for sample apps' fix.patch."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, content in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(content)
        try:
            result = subprocess.run(
                ["patch", "-p1", "--quiet", "--forward"],
                input=patch_text,
                text=True,
                cwd=root,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:  # the backend image installs GNU patch (Dockerfile)
            raise ProjectInvalid("fix.patch needs the `patch` program, which isn't installed") from exc
        if result.returncode:
            raise ProjectInvalid(f"fix.patch doesn't apply: {result.stdout or result.stderr}")
        # Read back every file, so files the patch creates are included too.
        return {
            p.relative_to(root).as_posix(): p.read_text()
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.suffix not in (".orig", ".rej")
        }
