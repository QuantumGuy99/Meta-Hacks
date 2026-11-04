"""The session clock in the hub (PLAN §3.1, §11.2): it holds through the warm-up and the Defense audit and attack."""

from crucible.contracts.common import Phase
from crucible.engine.hub import SessionRuntime
from tests.engine.test_voice import Clock
from tests.factories import StubController, runtime


class AuditThenChaos(StubController):
    def allowed_transitions(self) -> dict[Phase, set[Phase]]:
        return {Phase.AUDIT: {Phase.CHAOS}, Phase.CHAOS: {Phase.GRILL}}


def audit_runtime(clock: Clock) -> SessionRuntime:
    rt = runtime(monotonic=clock)
    rt.controller = AuditThenChaos()
    rt.session.phase = Phase.AUDIT
    return rt


async def test_the_clock_holds_while_the_audit_and_attack_run() -> None:
    clock = Clock()
    rt = audit_runtime(clock)
    clock.now += 150  # a slow first audit
    assert rt.remaining_s() == rt.session.time_limit_s
    await rt.close()


async def test_the_clock_starts_with_the_full_time_at_the_grill() -> None:
    clock = Clock()
    rt = audit_runtime(clock)
    limit = rt.session.time_limit_s
    clock.now += 150
    await rt.set_phase(Phase.CHAOS, "audit done")
    clock.now += 40  # writing and running the attack
    assert rt.remaining_s() == limit
    await rt.set_phase(Phase.GRILL, "chaos broke")
    assert rt.remaining_s() == limit
    clock.now += 60
    assert rt.remaining_s() == limit - 60  # the grill is the candidate's time
    await rt.close()
