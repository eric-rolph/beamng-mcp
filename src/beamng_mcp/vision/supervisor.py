"""Asynchronous perception/control supervisor with independent dead-man task."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from .control import DrivingController
from .interfaces import (
    AsyncControlSink,
    AsyncFrameSource,
    FrameFreshnessError,
    PerceptionBackend,
)
from .models import ControlCommand, PerceptionResult, SensorFrame, SupervisorState
from .watchdog import DeadmanWatchdog, WatchdogConfig, WatchdogSnapshot


@dataclass(frozen=True, slots=True)
class SupervisorConfig:
    """Runtime behavior for :class:`VisionSupervisor`."""

    target_loop_hz: float = 20.0
    inference_in_worker_thread: bool = True
    maximum_consecutive_errors: int = 3
    send_emergency_on_shutdown: bool = True

    def __post_init__(self) -> None:
        if not 0.5 <= self.target_loop_hz <= 240.0:
            raise ValueError("target_loop_hz must be in [0.5, 240]")
        if self.maximum_consecutive_errors < 1:
            raise ValueError("maximum_consecutive_errors must be positive")


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    frames_received: int
    frames_processed: int
    frames_dropped: int
    stale_frames: int
    perception_errors: int
    sink_errors: int
    commands_sent: int
    emergency_commands: int
    watchdog_emergency_commands: int
    last_inference_ms: float
    average_inference_ms: float
    maximum_inference_ms: float
    last_loop_ms: float


@dataclass(slots=True)
class _MutableMetrics:
    frames_received: int = 0
    frames_processed: int = 0
    frames_dropped: int = 0
    stale_frames: int = 0
    perception_errors: int = 0
    sink_errors: int = 0
    commands_sent: int = 0
    emergency_commands: int = 0
    watchdog_emergency_commands: int = 0
    last_inference_ms: float = 0.0
    total_inference_ms: float = 0.0
    maximum_inference_ms: float = 0.0
    last_loop_ms: float = 0.0

    def record_inference(self, milliseconds: float) -> None:
        self.last_inference_ms = milliseconds
        self.total_inference_ms += milliseconds
        self.maximum_inference_ms = max(self.maximum_inference_ms, milliseconds)

    def snapshot(self) -> MetricsSnapshot:
        average = self.total_inference_ms / self.frames_processed if self.frames_processed else 0.0
        return MetricsSnapshot(
            frames_received=self.frames_received,
            frames_processed=self.frames_processed,
            frames_dropped=self.frames_dropped,
            stale_frames=self.stale_frames,
            perception_errors=self.perception_errors,
            sink_errors=self.sink_errors,
            commands_sent=self.commands_sent,
            emergency_commands=self.emergency_commands,
            watchdog_emergency_commands=self.watchdog_emergency_commands,
            last_inference_ms=self.last_inference_ms,
            average_inference_ms=average,
            maximum_inference_ms=self.maximum_inference_ms,
            last_loop_ms=self.last_loop_ms,
        )


@dataclass(frozen=True, slots=True)
class SupervisorStatus:
    state: SupervisorState
    backend: str
    running: bool
    last_error: str | None
    last_frame_sequence: int | None
    last_perception: PerceptionResult | None
    last_command: ControlCommand | None
    metrics: MetricsSnapshot
    watchdog: WatchdogSnapshot


class VisionSupervisor:
    """Drive a perception/control loop over injected async I/O boundaries.

    The watchdog runs in its own asyncio task, so a blocked frame source or a
    slow inference call cannot silently leave the last throttle command active.
    For stronger process-crash guarantees, the Lua bridge should enforce its
    own independent command lease as well.
    """

    def __init__(
        self,
        *,
        frame_source: AsyncFrameSource,
        control_sink: AsyncControlSink,
        backend: PerceptionBackend,
        controller: DrivingController | None = None,
        watchdog: DeadmanWatchdog | None = None,
        watchdog_config: WatchdogConfig | None = None,
        config: SupervisorConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if watchdog is not None and watchdog_config is not None:
            raise ValueError("pass watchdog or watchdog_config, not both")
        self.frame_source = frame_source
        self.control_sink = control_sink
        self.backend = backend
        self.controller = controller or DrivingController()
        self.watchdog = watchdog or DeadmanWatchdog(watchdog_config)
        self.config = config or SupervisorConfig()
        self._clock = clock
        self._state = SupervisorState.STOPPED
        self._metrics = _MutableMetrics()
        self._last_error: str | None = None
        self._last_frame_sequence: int | None = None
        self._last_perception: PerceptionResult | None = None
        self._last_command: ControlCommand | None = None
        self._send_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._watchdog_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> SupervisorState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state in {
            SupervisorState.STARTING,
            SupervisorState.RUNNING,
            SupervisorState.DEGRADED,
            SupervisorState.EMERGENCY,
        }

    def request_stop(self) -> None:
        self._stop_event.set()

    def status(self, *, now: float | None = None) -> SupervisorStatus:
        timestamp = self._clock() if now is None else now
        return SupervisorStatus(
            state=self._state,
            backend=self.backend.name,
            running=self.running,
            last_error=self._last_error,
            last_frame_sequence=self._last_frame_sequence,
            last_perception=self._last_perception,
            last_command=self._last_command,
            metrics=self._metrics.snapshot(),
            watchdog=self.watchdog.snapshot(timestamp),
        )

    async def _send_command(
        self,
        command: ControlCommand,
        *,
        watchdog_emergency: bool = False,
    ) -> None:
        async with self._send_lock:
            try:
                await self.control_sink.send_control(command)
            except Exception as exc:
                self._metrics.sink_errors += 1
                self._last_error = f"control sink failed: {exc}"
                self._state = SupervisorState.FAILED
                raise
            sent_at = self._clock()
            self.watchdog.observe_command(sent_at)
            if watchdog_emergency:
                self.watchdog.record_emergency(sent_at)
                self._metrics.watchdog_emergency_commands += 1
            self._metrics.commands_sent += 1
            if command.emergency:
                self._metrics.emergency_commands += 1
                self._state = SupervisorState.EMERGENCY
            else:
                self._state = SupervisorState.RUNNING
            self._last_command = command

    async def _send_emergency(
        self,
        reason: str,
        *,
        frame_sequence: int | None = None,
        watchdog_emergency: bool = False,
    ) -> ControlCommand:
        command = ControlCommand.emergency_stop(
            issued_at=self._clock(),
            reason=reason,
            brake=self.watchdog.config.emergency_brake,
            frame_sequence=frame_sequence,
        )
        await self._send_command(command, watchdog_emergency=watchdog_emergency)
        return command

    async def _infer(self, frame: SensorFrame) -> PerceptionResult:
        if self.config.inference_in_worker_thread:
            return await asyncio.to_thread(self.backend.infer, frame)
        return self.backend.infer(frame)

    async def step(self) -> ControlCommand:
        """Read, process, and actuate one frame.

        This method is useful for deterministic integration tests and manual
        stepping.  :meth:`run` adds loop pacing and the concurrent watchdog.
        """

        loop_started = self._clock()
        try:
            frame = await asyncio.wait_for(
                self.frame_source.next_frame(),
                timeout=self.watchdog.config.frame_timeout_s,
            )
        except FrameFreshnessError as exc:
            self._metrics.frames_dropped += 1
            self._metrics.stale_frames += 1
            reason = self.watchdog.observe_source_failure(exc.reason)
            command = await self._send_emergency(
                reason,
                frame_sequence=self._last_frame_sequence,
                watchdog_emergency=True,
            )
            self._metrics.last_loop_ms = (self._clock() - loop_started) * 1000.0
            return command
        except TimeoutError:
            self._metrics.frames_dropped += 1
            command = await self._send_emergency(
                "frame_timeout",
                watchdog_emergency=True,
            )
            self._metrics.last_loop_ms = (self._clock() - loop_started) * 1000.0
            return command

        received_at = self._clock()
        self._metrics.frames_received += 1
        stale_reason = self.watchdog.observe_frame(frame, received_at)
        if stale_reason is not None:
            self._metrics.frames_dropped += 1
            self._metrics.stale_frames += 1
            command = await self._send_emergency(
                stale_reason,
                frame_sequence=frame.sequence,
                watchdog_emergency=True,
            )
            self._metrics.last_loop_ms = (self._clock() - loop_started) * 1000.0
            return command

        if self._last_frame_sequence is not None and frame.sequence <= self._last_frame_sequence:
            self._metrics.frames_dropped += 1
            command = await self._send_emergency(
                "non_monotonic_frame",
                frame_sequence=frame.sequence,
                watchdog_emergency=True,
            )
            self._metrics.last_loop_ms = (self._clock() - loop_started) * 1000.0
            return command

        inference_started = self._clock()
        try:
            perception = await self._infer(frame)
        except Exception:
            self._metrics.perception_errors += 1
            raise
        self._last_perception = perception
        measured_inference_ms = (self._clock() - inference_started) * 1000.0
        inference_ms = max(measured_inference_ms, perception.inference_ms)
        self._metrics.record_inference(inference_ms)

        now = self._clock()
        if now - frame.captured_at > self.watchdog.config.maximum_frame_age_s:
            self._metrics.frames_dropped += 1
            self._metrics.stale_frames += 1
            command = await self._send_emergency(
                "perception_latency",
                frame_sequence=frame.sequence,
                watchdog_emergency=True,
            )
            self._metrics.last_loop_ms = (self._clock() - loop_started) * 1000.0
            return command

        command = self.controller.compute(
            perception,
            current_speed_mps=frame.vehicle.speed_mps,
            now=now,
        )
        await self._send_command(command)
        self._last_frame_sequence = frame.sequence
        self._metrics.frames_processed += 1
        self._metrics.last_loop_ms = (self._clock() - loop_started) * 1000.0
        return command

    async def _watchdog_loop(self) -> None:
        while True:
            await asyncio.sleep(self.watchdog.config.check_interval_s)
            now = self._clock()
            reason = self.watchdog.emergency_due(now)
            if reason is not None:
                try:
                    await self._send_emergency(
                        reason,
                        frame_sequence=self._last_frame_sequence,
                        watchdog_emergency=True,
                    )
                except Exception:
                    # Sink failure is already recorded.  The main run loop will
                    # observe FAILED state and terminate rather than spinning.
                    return

    async def run(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Run until stopped, the source ends, or repeated failures occur."""

        if self._watchdog_task is not None:
            raise RuntimeError("vision supervisor is already running")
        self._stop_event = asyncio.Event()
        self._state = SupervisorState.STARTING
        self._last_error = None
        self._last_perception = None
        self.controller.reset()
        self.watchdog.arm(self._clock())
        self._watchdog_task = asyncio.create_task(
            self._watchdog_loop(),
            name="beamng-vision-deadman",
        )
        self._state = SupervisorState.RUNNING
        consecutive_errors = 0
        period_s = 1.0 / self.config.target_loop_hz

        try:
            while not self._stop_event.is_set() and not (
                stop_event is not None and stop_event.is_set()
            ):
                iteration_started = self._clock()
                try:
                    await self.step()
                    consecutive_errors = 0
                except StopAsyncIteration:
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    consecutive_errors += 1
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    self._state = SupervisorState.DEGRADED
                    with suppress(Exception):
                        await self._send_emergency("supervisor_error")
                    if consecutive_errors >= self.config.maximum_consecutive_errors:
                        self._state = SupervisorState.FAILED
                        break

                if self._state is SupervisorState.FAILED:
                    break
                remaining = period_s - (self._clock() - iteration_started)
                if remaining > 0.0:
                    await asyncio.sleep(remaining)
        finally:
            failed = self._state is SupervisorState.FAILED
            if not failed:
                self._state = SupervisorState.STOPPING
            if self._watchdog_task is not None:
                self._watchdog_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._watchdog_task
                self._watchdog_task = None
            if self.config.send_emergency_on_shutdown:
                with suppress(Exception):
                    await self._send_emergency("supervisor_shutdown")
            self.watchdog.disarm()
            self.controller.reset()
            if not failed:
                self._state = SupervisorState.STOPPED
