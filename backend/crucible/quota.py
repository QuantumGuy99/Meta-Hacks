"""Per-client daily session quota (PLAN §19: MAX_SESSIONS_PER_IP_PER_DAY), so nobody can run up the model
and sandbox bill. In memory: one backend instance (PLAN §19), and a restart only resets today's counts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

from starlette.requests import Request


class DailyQuota:
    """`take` reserves one session for a client today; `give_back` returns it when creation fails."""

    def __init__(self, limit: int, *, today: Callable[[], date] = lambda: datetime.now(UTC).date()) -> None:
        self.limit = limit
        self._today = today
        self._day = today()
        self._used: dict[str, int] = {}

    def take(self, client: str) -> bool:
        self._roll()
        if self._used.get(client, 0) >= self.limit:
            return False
        self._used[client] = self._used.get(client, 0) + 1
        return True

    def give_back(self, client: str) -> None:
        if self._used.get(client, 0) > 0:
            self._used[client] -= 1

    def _roll(self) -> None:
        day = self._today()
        if day != self._day:
            self._day, self._used = day, {}


def client_ip(request: Request, *, behind_proxy: bool) -> str:
    """The caller's IP. Behind a proxy, the right-most X-Forwarded-For entry is the one the proxy added;
    entries to its left come from the client and can be forged."""
    if behind_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"
