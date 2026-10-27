"""Short random ids for sessions, events and interventions (PLAN §7)."""

from uuid import uuid4


def new_id() -> str:
    return uuid4().hex[:12]
