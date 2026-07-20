"""Runtime interfaces used to inject game and transport integrations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import ControlCommand, PerceptionResult, SensorFrame


class FrameFreshnessError(RuntimeError):
    """A frame source detected data that is not advancing at the producer."""

    def __init__(self, message: str, *, reason: str = "frozen_frame") -> None:
        super().__init__(message)
        self.reason = reason


@runtime_checkable
class PerceptionBackend(Protocol):
    """Synchronous frame-to-perception implementation.

    Backends remain synchronous because OpenCV, PyTorch, and ONNX Runtime all
    expose synchronous inference calls.  The supervisor can move these calls
    to a worker thread without forcing a runtime choice on backend code.
    """

    @property
    def name(self) -> str:
        """Stable backend identifier included in status and metrics."""

    def infer(self, frame: SensorFrame) -> PerceptionResult:
        """Infer lane geometry and hazards for one frame."""


@runtime_checkable
class AsyncFrameSource(Protocol):
    """Injected source of camera frames and synchronized telemetry."""

    async def next_frame(self) -> SensorFrame:
        """Wait for and return the next frame."""


@runtime_checkable
class AsyncControlSink(Protocol):
    """Injected sink for normalized vehicle commands."""

    async def send_control(self, command: ControlCommand) -> None:
        """Apply a command to the vehicle/bridge."""
