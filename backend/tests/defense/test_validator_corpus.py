"""Sharvil's validator corpus (PLAN §16 DEF-3): every bad_*.json is rejected, every good_*.json passes and renders."""

import json
from pathlib import Path

import pytest

from crucible.contracts.defense import AttackFunctions
from crucible.defense.attack_writer import render_attack
from crucible.defense.validator import AttackRejected, validate_functions

CORPUS = Path(__file__).parent / "validator_corpus"
BAD = sorted(CORPUS.glob("bad_*.json"))
GOOD = sorted(CORPUS.glob("good_*.json"))


def _load(path: Path) -> AttackFunctions:
    return AttackFunctions.model_validate(json.loads(path.read_text()))


def test_the_corpus_has_the_planned_size():
    assert 15 <= len(BAD) <= 20 and len(GOOD) >= 5


@pytest.mark.parametrize("path", BAD, ids=lambda p: p.stem)
def test_every_bad_attack_is_rejected(path):
    with pytest.raises(AttackRejected):
        validate_functions(_load(path))


@pytest.mark.parametrize("path", GOOD, ids=lambda p: p.stem)
def test_every_good_attack_passes_and_compiles(path):
    fn = _load(path)
    validate_functions(fn)
    compile(render_attack(fn, port=8123, concurrency=10, duration_s=2), path.name, "exec")
