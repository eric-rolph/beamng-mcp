"""Lifecycle glue between BeamNGpy camera/control APIs and the vision supervisor."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, assert_never

import numpy as np

from ..adapters.beamngpy_adapter import BeamNGpyAdapter
from ..config import VisionSettings
from ..errors import ConfigurationError, SafetyInterlockError
from ..models import (
    AutonomyStart,
    AutonomyStatus,
    SensorSpec,
    VehicleAIConfig,
    VehicleControl,
)
from ..vision import (
    ColorSpace,
    ControlCommand,
    DrivingController,
    FrameFreshnessError,
    HuggingFaceSegFormerBackend,
    ONNXRuntimeSegmentationBackend,
    ONNXRuntimeSegmentationConfig,
    OpenCVLaneBackend,
    SegFormerConfig,
    SegmentationClassMap,
    SensorFrame,
    SpeedGovernor,
    SpeedGovernorConfig,
    SupervisorConfig,
    VehicleState,
    VisionSupervisor,
    WatchdogConfig,
)

CITYSCAPES_CLASSES = SegmentationClassMap(
    drivable_class_ids=(0,),
    hazard_class_ids=(11, 12, 13, 14, 15, 16, 17, 18),
    hazard_names={
        11: "person",
        12: "rider",
        13: "car",
        14: "truck",
        15: "bus",
        16: "train",
        17: "motorcycle",
        18: "bicycle",
    },
)


class BeamNGFrameSource:
    def __init__(
        self,
        adapter: BeamNGpyAdapter,
        sensor_name: str,
        vehicle_id: str,
        *,
        duplicate_frame_timeout_s: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(duplicate_frame_timeout_s) or duplicate_frame_timeout_s <= 0.0:
            raise ValueError("duplicate_frame_timeout_s must be positive and finite")
        self.adapter = adapter
        self.sensor_name = sensor_name
        self.vehicle_id = vehicle_id
        self.duplicate_frame_timeout_s = duplicate_frame_timeout_s
        self.clock = clock
        self.sequence = 0
        self._last_fingerprint: bytes | None = None
        self._duplicate_started_at: float | None = None

    @staticmethod
    def _fingerprint(image: Any) -> bytes:
        digest = hashlib.blake2b(digest_size=16)
        digest.update(str(image.shape).encode("ascii"))
        digest.update(str(image.dtype).encode("ascii"))
        digest.update(image.tobytes(order="C"))
        return digest.digest()

    async def next_frame(self) -> SensorFrame:
        image = await self.adapter.camera_frame(self.sensor_name)
        captured_at = self.clock()
        fingerprint = self._fingerprint(image)
        if fingerprint != self._last_fingerprint:
            self._last_fingerprint = fingerprint
            self._duplicate_started_at = captured_at
        else:
            duplicate_started_at = self._duplicate_started_at
            if (
                duplicate_started_at is not None
                and captured_at - duplicate_started_at >= self.duplicate_frame_timeout_s
            ):
                raise FrameFreshnessError(
                    "BeamNG camera content remained frozen beyond the duplicate-frame grace"
                )
        state = await self.adapter.vehicle_state(self.vehicle_id)
        self.sequence += 1
        return SensorFrame(
            image=image,
            captured_at=captured_at,
            sequence=self.sequence,
            color_space=ColorSpace.RGB,
            vehicle=VehicleState(speed_mps=state.speed_mps or 0.0),
            source=self.sensor_name,
        )


class BeamNGControlSink:
    def __init__(
        self,
        adapter: BeamNGpyAdapter,
        vehicle_id: str,
        *,
        on_successful_control: Callable[[float], None] | None = None,
        control_authorized: Callable[[], bool] | None = None,
    ) -> None:
        self.adapter = adapter
        self.vehicle_id = vehicle_id
        self.on_successful_control = on_successful_control
        self.control_authorized = control_authorized
        self.last_successful_control_monotonic: float | None = None

    async def send_control(self, command: ControlCommand) -> None:
        if self.control_authorized is not None and not self.control_authorized():
            raise SafetyInterlockError(
                "Engine safety lease is not active; refusing direct vehicle control"
            )
        await self.adapter.control_vehicle(
            VehicleControl(
                vehicle_id=self.vehicle_id,
                throttle=command.throttle,
                brake=command.brake,
                steering=command.steering,
                parking_brake=1.0 if command.emergency else 0.0,
            )
        )
        # Full-brake watchdog commands prove only that the fail-safe path worked;
        # they must not keep an autonomy lease alive without fresh perception.
        if not command.emergency:
            completed_at = time.monotonic()
            self.last_successful_control_monotonic = completed_at
            if self.on_successful_control is not None:
                self.on_successful_control(completed_at)


class AutonomyService:
    def __init__(
        self,
        adapter: BeamNGpyAdapter,
        settings: VisionSettings,
        *,
        control_authorized: Callable[[], bool] | None = None,
    ) -> None:
        self.adapter = adapter
        self.settings = settings
        self.control_authorized = control_authorized
        self._supervisor: VisionSupervisor | None = None
        self._task: asyncio.Task[None] | None = None
        self._spec: AutonomyStart | None = None
        self._started_at: datetime | None = None
        self._native_running = False
        self._last_successful_control_monotonic: float | None = None
        self._prepared_backend: Any | None = None
        self._owned_sensor_name: str | None = None

    async def prepare(self, spec: AutonomyStart) -> None:
        """Warm a vision backend before the short engine control lease is armed."""

        if self.running:
            raise SafetyInterlockError("Autonomy is already running")
        self._prepared_backend = None

        failures: list[str] = []
        try:
            await self.adapter.configure_ai(
                VehicleAIConfig(vehicle_id=spec.vehicle_id, mode="disabled")
            )
        except Exception as exc:
            failures.append(f"disable native AI: {type(exc).__name__}: {exc}")
        try:
            await self.adapter.emergency_stop(spec.vehicle_id)
        except Exception as exc:
            failures.append(f"emergency brake: {type(exc).__name__}: {exc}")
        if failures:
            raise SafetyInterlockError(
                "Autonomy preparation could not establish a safe vehicle state: "
                + "; ".join(failures)
            )
        if spec.mode == "native-ai":
            return

        backend = self._make_backend()
        warmup_frame = SensorFrame(
            image=np.zeros(
                (self.settings.input_height, self.settings.input_width, 3),
                dtype=np.uint8,
            ),
            captured_at=time.monotonic(),
            sequence=0,
            color_space=ColorSpace.RGB,
            vehicle=VehicleState(speed_mps=0.0),
            source="backend_warmup",
        )
        await asyncio.to_thread(backend.infer, warmup_frame)
        self._prepared_backend = backend

    def discard_prepared(self) -> None:
        self._prepared_backend = None

    async def start(self, spec: AutonomyStart) -> AutonomyStatus:
        if self.running:
            raise SafetyInterlockError("Autonomy is already running; stop it before reconfiguring")
        if self._owned_sensor_name is not None:
            raise SafetyInterlockError(
                f"Autonomy still owns sensor {self._owned_sensor_name!r} after failed cleanup"
            )
        self._spec = spec
        self._started_at = datetime.now(UTC)
        self._last_successful_control_monotonic = None
        try:
            if spec.mode == "native-ai":
                await self.adapter.configure_ai(
                    VehicleAIConfig(
                        vehicle_id=spec.vehicle_id,
                        mode=spec.ai_mode,
                        target_vehicle_id=spec.ai_target_vehicle_id,
                        target_waypoint=spec.ai_target_waypoint,
                        speed_mps=min(spec.target_speed_mps, spec.max_speed_mps),
                        speed_mode="limit",
                        aggression=spec.ai_aggression,
                        lane=spec.ai_drive_in_lane,
                    )
                )
                self._native_running = True
                return self.status()

            await self.adapter.configure_ai(
                VehicleAIConfig(vehicle_id=spec.vehicle_id, mode="disabled")
            )
            await self.adapter.attach_sensor(
                SensorSpec(
                    name=spec.sensor_name,
                    sensor_type="camera",
                    vehicle_id=spec.vehicle_id,
                    update_time=1.0 / self.settings.target_fps,
                    position=(0.0, -1.2, 1.35),
                    direction=(0.0, -1.0, -0.04),
                    resolution=(self.settings.input_width, self.settings.input_height),
                    field_of_view_y=70.0,
                    shared_memory=True,
                    streaming=True,
                    render_annotations=False,
                    render_depth=False,
                )
            )
            self._owned_sensor_name = spec.sensor_name
            backend = self._prepared_backend or self._make_backend()
            self._prepared_backend = None

            controller = DrivingController(
                speed_governor=SpeedGovernor(
                    SpeedGovernorConfig(
                        cruise_speed_mps=min(spec.target_speed_mps, spec.max_speed_mps)
                    )
                )
            )
            self._supervisor = VisionSupervisor(
                frame_source=BeamNGFrameSource(
                    self.adapter,
                    spec.sensor_name,
                    spec.vehicle_id,
                    duplicate_frame_timeout_s=self.settings.frame_timeout_seconds * 0.8,
                ),
                control_sink=BeamNGControlSink(
                    self.adapter,
                    spec.vehicle_id,
                    on_successful_control=self._record_successful_control,
                    control_authorized=self.control_authorized,
                ),
                backend=backend,
                controller=controller,
                watchdog_config=WatchdogConfig(
                    frame_timeout_s=max(self.settings.frame_timeout_seconds, 0.1),
                    command_timeout_s=max(self.settings.frame_timeout_seconds, 0.1),
                    maximum_frame_age_s=self.settings.frame_timeout_seconds,
                ),
                config=SupervisorConfig(target_loop_hz=self.settings.target_fps),
            )
            self._task = asyncio.create_task(
                self._supervisor.run(), name=f"beamng-autonomy-{spec.vehicle_id}"
            )
            return self.status()
        except Exception:
            self._native_running = False
            if self._supervisor is not None:
                self._supervisor.request_stop()
            if self._task is not None:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
            with contextlib.suppress(Exception):
                await self.adapter.configure_ai(
                    VehicleAIConfig(vehicle_id=spec.vehicle_id, mode="disabled")
                )
            with contextlib.suppress(Exception):
                await self.adapter.emergency_stop(spec.vehicle_id)
            if self._owned_sensor_name is not None:
                with contextlib.suppress(Exception):
                    await self.adapter.remove_sensor(self._owned_sensor_name)
                    self._owned_sensor_name = None
            self._task = None
            self._supervisor = None
            self._spec = None
            self._started_at = None
            self._last_successful_control_monotonic = None
            self._prepared_backend = None
            raise

    def _make_backend(self) -> Any:
        backend = self.settings.backend
        if backend == "classical":
            return OpenCVLaneBackend()
        if backend == "segformer":
            model = self.settings.model or "nvidia/segformer-b0-finetuned-cityscapes-512-1024"
            return HuggingFaceSegFormerBackend(
                SegFormerConfig(
                    model_id_or_path=model,
                    class_map=CITYSCAPES_CLASSES,
                    device="cuda",
                    dtype="float16",
                    allow_downloads=self.settings.allow_model_downloads,
                )
            )
        if backend == "onnx":
            path = self.settings.onnx_path
            if path is None:
                raise ConfigurationError("vision.onnx_path is required for the ONNX backend")
            if not Path(path).expanduser().is_file():
                raise ConfigurationError(f"ONNX model does not exist: {path}")
            return ONNXRuntimeSegmentationBackend(
                ONNXRuntimeSegmentationConfig(
                    model_path=path,
                    class_map=CITYSCAPES_CLASSES,
                    input_size=(self.settings.input_height, self.settings.input_width),
                    gpu_memory_limit_mb=self.settings.max_gpu_memory_mb,
                    tensorrt_workspace_mb=min(self.settings.max_gpu_memory_mb // 2, 4096),
                )
            )
        assert_never(backend)

    @property
    def running(self) -> bool:
        return self._native_running or (self._task is not None and not self._task.done())

    @property
    def last_successful_control_monotonic(self) -> float | None:
        return self._last_successful_control_monotonic

    def _record_successful_control(self, completed_at: float) -> None:
        self._last_successful_control_monotonic = completed_at

    def has_recent_successful_control(self, max_age_seconds: float) -> bool:
        completed_at = self._last_successful_control_monotonic
        return completed_at is not None and time.monotonic() - completed_at <= max_age_seconds

    async def stop(self, *, reason: str = "operator_stop") -> AutonomyStatus:
        spec = self._spec
        self._native_running = False
        supervisor = self._supervisor
        task = self._task
        failures: list[str] = []
        if supervisor is not None:
            supervisor.request_stop()
        if task is not None:
            try:
                if task.done():
                    task.result()
                else:
                    async with asyncio.timeout(3.0):
                        await task
            except TimeoutError:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                failures.append("vision supervisor: stop timed out")
            except asyncio.CancelledError:
                if task.cancelled():
                    failures.append("vision supervisor: task was cancelled")
                else:
                    raise
            except Exception as exc:
                failures.append(f"vision supervisor: {type(exc).__name__}: {exc}")
        self._task = None
        self._supervisor = None
        if spec is not None:
            try:
                await self.adapter.configure_ai(
                    VehicleAIConfig(vehicle_id=spec.vehicle_id, mode="disabled")
                )
            except Exception as exc:
                failures.append(f"disable native AI: {type(exc).__name__}: {exc}")
            try:
                await self.adapter.emergency_stop(spec.vehicle_id)
            except Exception as exc:
                failures.append(f"emergency brake: {type(exc).__name__}: {exc}")
        if self._owned_sensor_name is not None:
            try:
                await self.adapter.remove_sensor(self._owned_sensor_name)
                self._owned_sensor_name = None
            except Exception as exc:
                failures.append(f"remove sensor: {type(exc).__name__}: {exc}")
        stopped = self.status(reason_override=reason)
        self._spec = None
        self._started_at = None
        self._last_successful_control_monotonic = None
        self._prepared_backend = None
        if failures:
            raise SafetyInterlockError("Autonomy stop incomplete: " + "; ".join(failures))
        return stopped

    def status(self, *, reason_override: str | None = None) -> AutonomyStatus:
        if self._native_running and self._spec is not None:
            return AutonomyStatus(
                running=True,
                mode=self._spec.mode,
                vehicle_id=self._spec.vehicle_id,
                backend="beamng-native-ai",
                target_fps=None,
                started_at=self._started_at,
            )
        supervisor = self._supervisor
        spec = self._spec
        if supervisor is None:
            return AutonomyStatus(
                running=False,
                mode=spec.mode if spec else None,
                vehicle_id=spec.vehicle_id if spec else None,
                emergency_stopped=reason_override is not None,
                emergency_reason=reason_override,
                started_at=self._started_at,
            )
        status = supervisor.status()
        command = status.last_command
        watchdog = status.watchdog
        perception = status.last_perception
        confidence = perception.lane_confidence if perception is not None else None
        metadata = perception.metadata if perception is not None else {}
        raw_device = metadata.get("device")
        perception_device = str(raw_device) if raw_device is not None else None
        raw_providers = metadata.get("providers", ())
        perception_providers = (
            [str(provider) for provider in raw_providers]
            if isinstance(raw_providers, (list, tuple))
            else []
        )
        return AutonomyStatus(
            running=status.running and self.running,
            mode=spec.mode if spec else None,
            vehicle_id=spec.vehicle_id if spec else None,
            backend=status.backend,
            target_fps=self.settings.target_fps,
            measured_fps=(
                status.metrics.frames_processed
                / max((datetime.now(UTC) - self._started_at).total_seconds(), 0.001)
                if self._started_at
                else None
            ),
            frame_age_ms=(
                watchdog.last_frame_age_s * 1000.0
                if watchdog.last_frame_age_s is not None
                else None
            ),
            inference_ms=status.metrics.last_inference_ms,
            confidence=confidence,
            hazard_score=perception.hazard_score if perception is not None else None,
            perception_device=perception_device,
            perception_providers=perception_providers,
            last_control=(
                {
                    "steering": command.steering,
                    "throttle": command.throttle,
                    "brake": command.brake,
                    "target_speed_mps": command.target_speed_mps,
                }
                if command
                else {}
            ),
            emergency_stopped=bool(command and command.emergency),
            emergency_reason=(
                command.reason if command and command.emergency else status.last_error
            ),
            watchdog_armed=watchdog.armed,
            watchdog_latched=watchdog.latched,
            watchdog_reason=watchdog.reason,
            watchdog_trips=watchdog.trips,
            started_at=self._started_at,
        )

    async def emergency_stop(self, reason: str = "emergency_stop") -> AutonomyStatus:
        return await self.stop(reason=reason)

    async def shutdown(self) -> None:
        if self.running or self._spec is not None:
            await self.stop(reason="server_shutdown")
