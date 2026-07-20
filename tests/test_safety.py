import asyncio

from beamng_mcp.models import ControlInput
from beamng_mcp.safety import ControlSafetyGate


def test_overspeed_cuts_throttle_and_brakes() -> None:
    async def stop(_: str) -> None:
        pass

    gate = ControlSafetyGate(0.1, stop)
    result = gate.validate(ControlInput(vehicle_id="ego", throttle=1), 131, 130)
    assert result.throttle == 0
    assert result.brake == 0.25


async def test_deadman_stops_vehicle() -> None:
    stopped = asyncio.Event()

    async def stop(vehicle_id: str) -> None:
        assert vehicle_id == "ego"
        stopped.set()

    gate = ControlSafetyGate(0.05, stop)
    await gate.start()
    gate.heartbeat("ego")
    await asyncio.wait_for(stopped.wait(), 0.3)
    await gate.close()

