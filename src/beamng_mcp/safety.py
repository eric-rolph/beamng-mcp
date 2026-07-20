import asyncio
import time
from collections.abc import Awaitable, Callable

from .models import ControlInput


class ControlSafetyGate:
    """Bounds controls and brakes after a missed heartbeat."""

    def __init__(self, ttl: float, stop: Callable[[str], Awaitable[None]]) -> None:
        self.ttl = ttl
        self._stop = stop
        self._deadlines: dict[str, float] = {}
        self._task: asyncio.Task[None] | None = None

    def validate(
        self, command: ControlInput, speed_kph: float, max_speed_kph: float
    ) -> ControlInput:
        if speed_kph >= max_speed_kph and command.throttle > 0:
            return command.model_copy(update={"throttle": 0.0, "brake": max(command.brake, 0.25)})
        return command

    def heartbeat(self, vehicle_id: str) -> None:
        self._deadlines[vehicle_id] = time.monotonic() + self.ttl

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._watchdog())

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _watchdog(self) -> None:
        while True:
            now = time.monotonic()
            expired = [
                vehicle_id
                for vehicle_id, deadline in self._deadlines.items()
                if now >= deadline
            ]
            for vehicle_id in expired:
                self._deadlines.pop(vehicle_id, None)
                await self._stop(vehicle_id)
            await asyncio.sleep(min(self.ttl / 4, 0.1))
