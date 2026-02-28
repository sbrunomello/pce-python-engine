from pce_os.agents.base import AgentMessage
from pce_os.agents.bus import AgentBus


def test_agent_bus_dedupe_and_rate_limit() -> None:
    bus = AgentBus(max_turns=6, per_agent_limit=2)

    m1 = AgentMessage("engineering", "tests", "simulation.requested", {"reason": "cycle"})
    assert bus.enqueue(m1)
    assert not bus.enqueue(m1)

    assert bus.enqueue(AgentMessage("finance", "tests", "alert", {"n": 1}))
    assert bus.enqueue(AgentMessage("procurement", "tests", "alert", {"n": 2}))

    grouped = bus.dequeue_for_all()
    assert "tests" in grouped
    assert len(grouped["tests"]) == 2
