"""Uploaded projects: a zip from the candidate, read safely in memory and kept for their sessions (PLAN §11.1).

Limits from §11.1 (≤ 2 MB zipped, ≤ 60 files, ≤ 6,000 lines) plus an unzipped cap against zip bombs. Paths that
escape the project, symlinks and non-text files never get in. The entrypoint is crucible.json's `module:app`, or a
FastAPI `app` auto-detected in main.py / app.py / app/main.py. Uploads are private: unlisted, under a random id.
"""

from __future__ import annotations

import io
import json
import re
import stat
import uuid
import zipfile
from collections.abc import Awaitable, Callable, Mapping
from pathlib import PurePosixPath

from crucible.contracts.defense import Project
from crucible.defense.projects import (
    DEFAULT_PORT,
    META_FILES,
    SKIP_DIRS,
    TEXT_SUFFIXES,
    ProjectInvalid,
    Sample,
    build_project,
)

MAX_ZIP_BYTES = 2 * 1024 * 1024  # PLAN §11.1
MAX_UNZIPPED_BYTES = 8 * 1024 * 1024  # a 2 MB zip can't expand into more than this (zip bombs)
MAX_FILE_BYTES = 512 * 1024
MAX_NAME_CHARS = 40
MAX_CONTEXT_CHARS = 8_000  # the author's notes: a page or two of "what this project is"
# A root file with one of these names is the author's notes for the audit, not project source.
CONTEXT_FILES = frozenset({"context.txt", "crucible-context.txt", "project-context.txt"})
_CONTEXT_KEY = (
    ".crucible/context.txt"  # how the notes are kept with the files in the store: never a project path
)
# Where a FastAPI app is looked for when there's no crucible.json, as `module:app` targets (PLAN §11.1).
AUTO_ENTRYPOINTS = (("main.py", "main"), ("app.py", "app"), ("app/main.py", "app.main"))
_TARGET = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")
_FASTAPI_APP = re.compile(r"^(\w+)\s*(?::[^=]+)?=\s*FastAPI\(", re.MULTILINE)
_NAME_CHARS = re.compile(r"[^a-z0-9-]+")


def read_zip(data: bytes) -> dict[str, str]:
    """{relative path: text} for the project's text files. Raises ProjectInvalid with a reason a person can act on."""
    if len(data) > MAX_ZIP_BYTES:
        raise ProjectInvalid(
            f"the zip is {len(data) / 1e6:.1f} MB (limit {MAX_ZIP_BYTES // (1024 * 1024)} MB)"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ProjectInvalid("that isn't a zip file") from exc
    entries = [i for i in archive.infolist() if not i.is_dir()]
    if sum(i.file_size for i in entries) > MAX_UNZIPPED_BYTES:
        raise ProjectInvalid(f"the project unzips to more than {MAX_UNZIPPED_BYTES // (1024 * 1024)} MB")
    prefix = _common_folder([i.filename for i in entries])
    files: dict[str, str] = {}
    for info in entries:
        rel = _safe_path(info.filename, prefix)
        if rel is None or stat.S_ISLNK(info.external_attr >> 16):
            continue  # skipped: a dependency/cache folder, a non-text file or a symlink
        if info.file_size > MAX_FILE_BYTES:
            raise ProjectInvalid(f"{rel} is larger than {MAX_FILE_BYTES // 1024} KB")
        try:
            files[rel] = archive.read(info).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectInvalid(f"{rel} isn't UTF-8 text") from exc
    return files


def entrypoint(files: Mapping[str, str]) -> str:
    """The uvicorn command for the project: crucible.json's `module:app` target, or an auto-detected FastAPI app.
    Only the target is taken from the upload; the command around it is ours (no uvicorn flags from a stranger)."""
    meta = files.get("crucible.json")
    if meta is not None:
        try:
            target = str(json.loads(meta).get("entrypoint", "")).split()
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ProjectInvalid("crucible.json isn't valid JSON") from exc
        found = next((t for t in target if _TARGET.match(t)), None)
        if target[:1] != ["uvicorn"] or found is None:
            raise ProjectInvalid('crucible.json\'s "entrypoint" must be "uvicorn module:app"')
        return _command(found)
    for path, module in AUTO_ENTRYPOINTS:
        match = _FASTAPI_APP.search(files.get(path, ""))
        if match:
            return _command(f"{module}:{match.group(1)}")
    if any("Flask(" in text for p, text in files.items() if p.endswith(".py")):
        raise ProjectInvalid(
            "Flask apps aren't supported yet: Project Defense runs FastAPI apps with uvicorn"
        )
    raise ProjectInvalid(
        "no FastAPI app found: put `app = FastAPI()` in main.py, app.py or app/main.py, or add a crucible.json "
        'with {"entrypoint": "uvicorn module:app"}'
    )


def make_upload(filename: str, data: bytes) -> Sample:
    """A Sample for an uploaded zip: no flaws.json, reference attack or fix, so the audit and attacks come from
    the models. A random id keeps it private: nothing lists uploads, so the id is the link to it."""
    files = read_zip(data)
    command = entrypoint(files)
    notes = next((files[k] for k in files if k.lower() in CONTEXT_FILES), None)
    source = {k: v for k, v in files.items() if k not in META_FILES and k.lower() not in CONTEXT_FILES}
    project = build_project(
        uuid.uuid4().hex, source, source="upload", entrypoint=command, port=DEFAULT_PORT
    ).model_copy(update={"name": display_name(filename)})
    return Sample(project=project, files=source, context=clean_context(notes) if notes else None)


def clean_context(text: str) -> str:
    """The author's notes as the audit sees them: plain text, capped. Raises ProjectInvalid if there's nothing."""
    cleaned = "".join(c for c in text if c.isprintable() or c in "\n\t").strip()
    if not cleaned:
        raise ProjectInvalid("the context file is empty")
    return cleaned[:MAX_CONTEXT_CHARS]


def display_name(filename: str) -> str:
    stem = PurePosixPath(filename.replace("\\", "/")).name.removesuffix(".zip").lower()
    return _NAME_CHARS.sub("-", stem).strip("-")[:MAX_NAME_CHARS] or "my-project"


class ProjectLibrary:
    """The sample apps plus uploaded projects. Uploads are cached here and kept in the store, so a session on
    one still works after a restart (`load` brings it back before the session's pipeline needs it)."""

    def __init__(self, samples: Mapping[str, Sample]) -> None:
        self.samples = samples
        self._uploads: dict[str, Sample] = {}
        self._save: Callable[[Project, dict[str, str]], Awaitable[None]] | None = None
        self._fetch: Callable[[str], Awaitable[tuple[Project, dict[str, str]] | None]] | None = None

    def attach(self, store: object) -> None:
        """The SQLite store (store/repo.py): uploads outlive the process."""
        self._save = getattr(store, "save_project", None)
        self._fetch = getattr(store, "get_project", None)

    def get(self, project_id: str) -> Sample | None:
        return self.samples.get(project_id) or self._uploads.get(project_id)

    async def load(self, project_id: str) -> Sample | None:
        found = self.get(project_id)
        if found is None and self._fetch is not None:
            row = await self._fetch(project_id)
            if row is not None and row[0].source == "upload":
                files = dict(row[1])
                notes = files.pop(_CONTEXT_KEY, None)
                found = self._uploads[project_id] = Sample(project=row[0], files=files, context=notes)
        return found

    async def add(self, sample: Sample) -> None:
        self._uploads[sample.project.id] = sample
        if self._save is not None:
            notes = {_CONTEXT_KEY: sample.context} if sample.context else {}
            await self._save(sample.project, {**sample.files, **notes})

    async def set_context(self, project_id: str, text: str) -> Sample:
        """Attach (or replace) an upload's notes. Raises LookupError for a sample or an unknown id."""
        sample = await self.load(project_id)
        if sample is None or sample.project.source != "upload":
            raise LookupError(project_id)
        sample.context = clean_context(text)
        await self.add(sample)
        return sample


# --- private helpers ------------------------------------------------------------------------------------------


def _command(target: str) -> str:
    return f"uvicorn {target} --host 127.0.0.1 --port {DEFAULT_PORT}"


def _common_folder(names: list[str]) -> str:
    """ "myproject/" when every file sits under one top folder (how most zips of a folder come out)."""
    tops = {n.replace("\\", "/").split("/", 1)[0] for n in names}
    nested = all("/" in n.replace("\\", "/") for n in names)
    return f"{tops.pop()}/" if nested and len(tops) == 1 else ""


def _safe_path(name: str, prefix: str) -> str | None:
    """The file's path inside the project, or None to skip it. Paths that escape the project are an error."""
    path = name.replace("\\", "/")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path) or ".." in path.split("/"):
        raise ProjectInvalid(f"{name} points outside the project")
    path = path.removeprefix(prefix)
    parts = PurePosixPath(path).parts
    if not parts or set(parts) & SKIP_DIRS or any(p.startswith(".") for p in parts):
        return None
    if PurePosixPath(path).suffix not in TEXT_SUFFIXES:
        return None
    return path
