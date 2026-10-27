"""The problem bank: original problems loaded from data/problems (PLAN §10.2, §13.1).

ENG-4 needs the loader to attach a rubric. COD-1 adds the problem API and skips problems an IP saw recently.
"""

import json
import logging
import random
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from crucible.contracts.coding import ProblemSpec
from crucible.contracts.common import Difficulty

logger = logging.getLogger(__name__)

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "problems"


class ProblemError(Exception):
    """A problem folder that doesn't load or doesn't match `ProblemSpec`."""


class ProblemBank:
    def __init__(self, problems: Iterable[ProblemSpec]) -> None:
        self._by_slug = {p.slug: p for p in problems}

    @classmethod
    def load(cls, root: Path = DEFAULT_ROOT, *, strict: bool = True) -> "ProblemBank":
        """Load every `<slug>/` folder (folders starting with `_` are drafts). `strict` fails on a bad one."""
        problems: list[ProblemSpec] = []
        folders = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
        for folder in folders:
            if folder.name.startswith(("_", ".")):
                continue
            try:
                problems.append(load_problem(folder))
            except (OSError, ValueError) as exc:
                if strict:
                    raise ProblemError(f"{folder.name}: {exc}") from exc
                logger.warning("skipping problem %s: %s", folder.name, exc)
        return cls(problems)

    def get(self, slug: str | None) -> ProblemSpec | None:
        return self._by_slug.get(slug) if slug else None

    def matching(self, difficulty: Difficulty | None, topic: str | None) -> list[ProblemSpec]:
        """Problems at `difficulty` whose topics mention `topic` (case-insensitive), sorted by slug."""
        wanted = topic.strip().lower() if topic else None
        return sorted(
            (
                p
                for p in self._by_slug.values()
                if (difficulty is None or p.difficulty == difficulty)
                and (wanted is None or any(wanted in t.lower() for t in p.topics))
            ),
            key=lambda p: p.slug,
        )

    def pick(
        self, difficulty: Difficulty | None, topic: str | None, rng: random.Random | None = None
    ) -> ProblemSpec | None:
        """A random problem at `difficulty` whose topics mention `topic`; None if nothing matches."""
        matches = self.matching(difficulty, topic)
        return (rng or random).choice(matches) if matches else None

    def __len__(self) -> int:
        return len(self._by_slug)


def load_problem(folder: Path) -> ProblemSpec:
    """`problem.json` plus its sibling files (statement, reference, optional brute force)."""
    raw = json.loads((folder / "problem.json").read_text())
    raw["statement_md"] = (folder / "statement.md").read_text()
    raw["reference_solution"] = (folder / "reference.py").read_text()
    brute = folder / "brute.py"
    if brute.exists():
        raw["brute_force_solution"] = brute.read_text()
    try:
        spec = ProblemSpec.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    if spec.slug != folder.name:
        raise ValueError(f"slug {spec.slug!r} doesn't match its folder")
    return spec
