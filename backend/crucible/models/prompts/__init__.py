"""Prompts the model wrapper adds itself, loaded once at import (PLAN §22 rule 4)."""

from pathlib import Path

# Ares's identity and security rules, sent first to every candidate-facing role (PLAN §4.4 rule 9).
ARES_IDENTITY: str = (Path(__file__).parent / "ares_identity.md").read_text()
