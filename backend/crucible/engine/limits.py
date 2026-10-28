"""Per-connection message limits for the session sockets (PLAN §8.2, §8.3).

A token bucket per socket: messages within the rate (plus a burst) pass, the rest are dropped, and a socket that
keeps flooding is closed. Pure and clock-injected, so tests drive it directly.
"""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

Verdict = Literal["ok", "drop", "close"]

# The session socket: real use is an editor batch every 500 ms, the odd snapshot, chat and run.
SESSION_RATE_PER_S = 20.0
SESSION_BURST = 60
# The audio socket: 12.5 frames a second at real-time pace; twice that absorbs network jitter.
AUDIO_RATE_PER_S = 25.0
AUDIO_BURST = 50
FLOOD_WINDOW_S = 10.0
FLOOD_DROPS = 200  # dropped messages within the window before the socket is closed


@dataclass(slots=True)
class TokenBucket:
    rate_per_s: float
    burst: float
    clock: Callable[[], float] = time.monotonic
    tokens: float = field(init=False)
    updated: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.burst
        self.updated = self.clock()

    def take(self) -> bool:
        now = self.clock()
        self.tokens = min(self.burst, self.tokens + (now - self.updated) * self.rate_per_s)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


@dataclass(slots=True)
class MessageGate:
    """`check()` per incoming message: "ok", "drop" (over the rate) or "close" (flooding for too long)."""

    bucket: TokenBucket
    clock: Callable[[], float] = time.monotonic
    window_s: float = FLOOD_WINDOW_S
    max_drops: int = FLOOD_DROPS
    _drops: deque[float] = field(default_factory=deque)

    def check(self) -> Verdict:
        if self.bucket.take():
            return "ok"
        now = self.clock()
        self._drops.append(now)
        while self._drops and now - self._drops[0] > self.window_s:
            self._drops.popleft()
        return "close" if len(self._drops) >= self.max_drops else "drop"


def session_gate(clock: Callable[[], float] = time.monotonic) -> MessageGate:
    return MessageGate(TokenBucket(SESSION_RATE_PER_S, SESSION_BURST, clock), clock)


def audio_gate(clock: Callable[[], float] = time.monotonic) -> MessageGate:
    return MessageGate(TokenBucket(AUDIO_RATE_PER_S, AUDIO_BURST, clock), clock)
