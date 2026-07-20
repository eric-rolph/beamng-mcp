"""A transport-independent dead-man watchdog for vehicle control."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import SensorFrame


@dataclass(frozen=True, slots=True)
class WatchdogConfig:
    frame_timeout_s: float = 0.45
    command_timeout_s: float = 0.35
    maximum_frame_age_s: float = 0.30
    check_interval_s: float = 0.05
    emergency_repeat_s: float = 0.40
    emergency_brake: float = 1.0

    def __post_init__(self) -> None:
        if (
            min(
                self.frame_timeout_s,
                self.command_timeout_s,
                self.maximum_frame_age_s,
                self.check_interval_s,
                self.emergency_repeat_s,
            )
            <= 0.0
        ):
            raise ValueError("watchdog timeouts and intervals must be positive")
        if self.check_interval_s > min(self.frame_timeout_s, self.command_timeout_s):
            raise ValueError("check_interval_s must not exceed the shortest timeout")
        if not 0.0 < self.emergency_brake <= 1.0:
            raise ValueError("emergency_brake must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class WatchdogSnapshot:
    armed: bool
    latched: bool
    reason: str | None
    trips: int
    last_frame_age_s: float | None
    last_command_age_s: float | None


class DeadmanWatchdog:
    """Detect stale input or output even while the main loop is blocked."""

    def __init__(self, config: WatchdogConfig | None = None) -> None:
        self.config = config or WatchdogConfig()
        self._armed = False
        self._armed_at: float | None = None
        self._last_frame_received_at: float | None = None
        self._last_frame_captured_at: float | None = None
        self._last_command_at: float | None = None
        self._last_emergency_at: float | None = None
        self._latched_reason: str | None = None
        self._source_failure_reason: str | None = None
        self._trips = 0

    @property
    def armed(self) -> bool:
        return self._armed

    @property
    def latched_reason(self) -> str | None:
        return self._latched_reason

    @property
    def trips(self) -> int:
        return self._trips

    def arm(self, now: float) -> None:
        if not math.isfinite(now):
            raise ValueError("watchdog time must be finite")
        self._armed = True
        self._armed_at = now
        self._last_frame_received_at = now
        self._last_frame_captured_at = None
        self._last_command_at = now
        self._last_emergency_at = None
        self._latched_reason = None
        self._source_failure_reason = None

    def disarm(self) -> None:
        self._armed = False
        self._latched_reason = None
        self._source_failure_reason = None

    def observe_frame(self, frame: SensorFrame, received_at: float) -> str | None:
        if not math.isfinite(received_at):
            raise ValueError("received_at must be finite")
        self._last_frame_received_at = received_at
        self._last_frame_captured_at = frame.captured_at
        if received_at - frame.captured_at > self.config.maximum_frame_age_s:
            return self._latch("stale_frame")
        self._source_failure_reason = None
        return None

    def observe_command(self, sent_at: float) -> None:
        if not math.isfinite(sent_at):
            raise ValueError("sent_at must be finite")
        self._last_command_at = sent_at

    def observe_source_failure(self, reason: str) -> str:
        """Latch an explicit producer-side freshness failure."""

        if not reason:
            raise ValueError("source failure reason cannot be empty")
        self._source_failure_reason = reason
        return self._latch(reason)

    def _latch(self, reason: str) -> str:
        if self._latched_reason is None:
            self._trips += 1
        self._latched_reason = reason
        return reason

    def check(self, now: float) -> str | None:
        if not self._armed:
            return None
        if not math.isfinite(now):
            raise ValueError("watchdog time must be finite")
        assert self._armed_at is not None
        frame_reference = self._last_frame_received_at or self._armed_at
        command_reference = self._last_command_at or self._armed_at
        reason: str | None = None
        if self._source_failure_reason is not None:
            reason = self._source_failure_reason
        elif now - frame_reference > self.config.frame_timeout_s:
            reason = "frame_timeout"
        elif (
            self._last_frame_captured_at is not None
            and now - self._last_frame_captured_at > self.config.maximum_frame_age_s
        ):
            reason = "stale_frame"
        elif now - command_reference > self.config.command_timeout_s:
            reason = "command_timeout"

        if reason is not None:
            return self._latch(reason)
        self._latched_reason = None
        self._last_emergency_at = None
        return None

    def emergency_due(self, now: float) -> str | None:
        reason = self.check(now)
        if reason is None:
            return None
        if (
            self._last_emergency_at is None
            or now - self._last_emergency_at >= self.config.emergency_repeat_s
        ):
            return reason
        return None

    def record_emergency(self, sent_at: float) -> None:
        self._last_emergency_at = sent_at

    def snapshot(self, now: float) -> WatchdogSnapshot:
        frame_age = (
            None
            if self._last_frame_received_at is None
            else max(0.0, now - self._last_frame_received_at)
        )
        command_age = (
            None if self._last_command_at is None else max(0.0, now - self._last_command_at)
        )
        return WatchdogSnapshot(
            armed=self._armed,
            latched=self._latched_reason is not None,
            reason=self._latched_reason,
            trips=self._trips,
            last_frame_age_s=frame_age,
            last_command_age_s=command_age,
        )
