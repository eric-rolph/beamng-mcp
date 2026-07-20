from __future__ import annotations

import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from beamng_mcp.config import VisionSettings
from beamng_mcp.errors import SafetyInterlockError
from beamng_mcp.models import AutonomyStart, VehicleAIConfig, VehicleControl
from beamng_mcp.services.autonomy import (
    AutonomyService,
    BeamNGControlSink,
    BeamNGFrameSource,
)
from beamng_mcp.vision import (
    ControlCommand,
    FrameFreshnessError,
    LaneEstimate,
    PerceptionResult,
    SensorFrame,
    VisionSupervisor,
)


class StopAdapter:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def configure_ai(self, config: VehicleAIConfig) -> None:
        self.events.append(f"ai:{config.mode}")

    async def emergency_stop(self, vehicle_id: str | None = None) -> None:
        self.events.append(f"brake:{vehicle_id}")


class FailingDisableAdapter(StopAdapter):
    async def configure_ai(self, config: VehicleAIConfig) -> None:
        await super().configure_ai(config)
        if config.mode == "disabled":
            raise RuntimeError("AI socket failed")


class FailingBrakeAdapter(StopAdapter):
    async def emergency_stop(self, vehicle_id: str | None = None) -> None:
        await super().emergency_stop(vehicle_id)
        raise RuntimeError("control socket failed")


class FailingStartAdapter(StopAdapter):
    async def configure_ai(self, config: VehicleAIConfig) -> None:
        await super().configure_ai(config)
        if config.mode == "traffic":
            raise RuntimeError("AI start failed")


class ControlAdapter(StopAdapter):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.fail = fail
        self.controls: list[VehicleControl] = []

    async def control_vehicle(self, command: VehicleControl) -> None:
        self.controls.append(command)
        if self.fail:
            raise RuntimeError("control failed")


class FrozenCameraAdapter:
    def __init__(self) -> None:
        self.image = np.zeros((4, 6, 3), dtype=np.uint8)

    async def camera_frame(self, _sensor_name: str) -> np.ndarray:
        return self.image.copy()

    async def vehicle_state(self, _vehicle_id: str) -> SimpleNamespace:
        return SimpleNamespace(speed_mps=0.0)


class StatusBackend:
    name = "status"

    def __init__(self) -> None:
        self.inferences = 0

    def infer(self, frame: SensorFrame) -> PerceptionResult:
        self.inferences += 1
        return PerceptionResult(
            frame_sequence=frame.sequence,
            captured_at=frame.captured_at,
            image_shape=(frame.height, frame.width),
            backend=self.name,
            lane=LaneEstimate(
                center_offset=0.0,
                heading_error_rad=0.0,
                curvature=0.0,
                confidence=0.42,
                center_x_px=3.0,
                lookahead_x_px=3.0,
                lane_width_px=4.0,
            ),
            metadata={
                "device": "cuda:0",
                "providers": ("TensorrtExecutionProvider", "CUDAExecutionProvider"),
            },
        )


class VisionLifecycleAdapter(ControlAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.frame_number = 0

    async def attach_sensor(self, spec: object) -> None:
        self.events.append("sensor:attach")

    async def remove_sensor(self, _sensor_name: str) -> None:
        self.events.append("sensor:remove")

    async def camera_frame(self, _sensor_name: str) -> np.ndarray:
        self.frame_number += 1
        image = np.zeros((4, 6, 3), dtype=np.uint8)
        image[0, 0, 0] = self.frame_number % 255
        return image

    async def vehicle_state(self, _vehicle_id: str) -> SimpleNamespace:
        return SimpleNamespace(speed_mps=0.0)


class ConflictingSensorAdapter(VisionLifecycleAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.preexisting_sensor = True

    async def attach_sensor(self, spec: object) -> None:
        self.events.append("sensor:attach-conflict")
        raise ValueError("sensor already exists")

    async def remove_sensor(self, _sensor_name: str) -> None:
        self.preexisting_sensor = False
        self.events.append("sensor:remove-preexisting")


@pytest.mark.asyncio
async def test_frame_source_rejects_persistently_frozen_camera_content() -> None:
    now = [10.0]
    source = BeamNGFrameSource(
        FrozenCameraAdapter(),  # type: ignore[arg-type]
        "driver",
        "ego",
        duplicate_frame_timeout_s=0.2,
        clock=lambda: now[0],
    )

    first = await source.next_frame()
    now[0] += 0.19
    duplicate_within_grace = await source.next_frame()
    now[0] += 0.02

    assert first.sequence == 1
    assert duplicate_within_grace.sequence == 2
    with pytest.raises(FrameFreshnessError, match="frozen"):
        await source.next_frame()


@pytest.mark.asyncio
async def test_frozen_camera_content_trips_watchdog_and_applies_full_brake() -> None:
    now = [20.0]
    camera = FrozenCameraAdapter()
    source = BeamNGFrameSource(
        camera,  # type: ignore[arg-type]
        "driver",
        "ego",
        duplicate_frame_timeout_s=0.2,
        clock=lambda: now[0],
    )
    controls = ControlAdapter()
    supervisor = VisionSupervisor(
        frame_source=source,
        control_sink=BeamNGControlSink(controls, "ego"),  # type: ignore[arg-type]
        backend=StatusBackend(),
        clock=lambda: now[0],
    )
    supervisor.watchdog.arm(now[0])

    tracking = await supervisor.step()
    now[0] += 0.21
    command = await supervisor.step()

    assert tracking.emergency is False
    assert command.emergency is True
    assert command.reason == "frozen_frame"
    assert controls.controls[-1].brake == 1.0
    assert controls.controls[-1].parking_brake == 1.0
    watchdog = supervisor.status().watchdog
    assert watchdog.latched is True
    assert watchdog.reason == "frozen_frame"
    assert watchdog.trips == 1

    service = AutonomyService(camera, VisionSettings())  # type: ignore[arg-type]
    service._supervisor = supervisor
    service._spec = AutonomyStart(vehicle_id="ego", mode="vision-lane")
    service_status = service.status()
    assert service_status.confidence == pytest.approx(0.42)
    assert service_status.hazard_score == 0.0
    assert service_status.perception_device == "cuda:0"
    assert service_status.perception_providers == [
        "TensorrtExecutionProvider",
        "CUDAExecutionProvider",
    ]
    assert service_status.watchdog_armed is True
    assert service_status.watchdog_latched is True
    assert service_status.watchdog_reason == "frozen_frame"
    assert service_status.watchdog_trips == 1


@pytest.mark.asyncio
async def test_control_sink_records_only_successful_control_monotonic_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamps: list[float] = []
    adapter = ControlAdapter()
    sink = BeamNGControlSink(
        adapter,  # type: ignore[arg-type]
        "ego",
        on_successful_control=timestamps.append,
    )
    monkeypatch.setattr("beamng_mcp.services.autonomy.time.monotonic", lambda: 42.5)
    command = ControlCommand(
        steering=0.1,
        throttle=0.2,
        brake=0.0,
        target_speed_mps=3.0,
        issued_at=1.0,
    )

    await sink.send_control(command)

    assert sink.last_successful_control_monotonic == 42.5
    assert timestamps == [42.5]

    failed = BeamNGControlSink(
        ControlAdapter(fail=True),  # type: ignore[arg-type]
        "ego",
        on_successful_control=timestamps.append,
    )
    with pytest.raises(RuntimeError, match="control failed"):
        await failed.send_control(command)
    assert failed.last_successful_control_monotonic is None
    assert timestamps == [42.5]

    denied_adapter = ControlAdapter()
    denied = BeamNGControlSink(
        denied_adapter,  # type: ignore[arg-type]
        "ego",
        control_authorized=lambda: False,
    )
    with pytest.raises(SafetyInterlockError, match="Engine safety lease"):
        await denied.send_control(command)
    assert denied_adapter.controls == []


@pytest.mark.asyncio
async def test_emergency_brakes_do_not_count_as_lease_renewal_liveness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [30.0]
    timestamps: list[float] = []
    sink = BeamNGControlSink(
        ControlAdapter(),  # type: ignore[arg-type]
        "ego",
        on_successful_control=timestamps.append,
    )
    monkeypatch.setattr(
        "beamng_mcp.services.autonomy.time.monotonic",
        lambda: now[0],
    )
    await sink.send_control(
        ControlCommand(
            steering=0.0,
            throttle=0.2,
            brake=0.0,
            target_speed_mps=2.0,
            issued_at=now[0],
        )
    )
    now[0] += 1.0
    await sink.send_control(
        ControlCommand.emergency_stop(
            issued_at=now[0],
            reason="frozen_frame",
        )
    )

    assert sink.last_successful_control_monotonic == 30.0
    assert timestamps == [30.0]


@pytest.mark.asyncio
async def test_prepared_vision_backend_is_warmed_safe_and_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = VisionLifecycleAdapter()
    service = AutonomyService(adapter, VisionSettings())  # type: ignore[arg-type]
    backend = StatusBackend()
    factory_calls = 0

    def make_backend() -> StatusBackend:
        nonlocal factory_calls
        factory_calls += 1
        return backend

    monkeypatch.setattr(service, "_make_backend", make_backend)
    spec = AutonomyStart(vehicle_id="ego", mode="vision-lane")

    await service.prepare(spec)
    assert adapter.events[:2] == ["ai:disabled", "brake:ego"]
    assert backend.inferences == 1

    started = await service.start(spec)
    await asyncio.sleep(0)
    assert started.backend == "status"
    assert factory_calls == 1
    await service.stop(reason="test_cleanup")


@pytest.mark.asyncio
async def test_failed_camera_attach_does_not_remove_preexisting_sensor() -> None:
    adapter = ConflictingSensorAdapter()
    service = AutonomyService(adapter, VisionSettings())  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="already exists"):
        await service.start(AutonomyStart(vehicle_id="ego", mode="vision-lane"))

    assert adapter.preexisting_sensor is True
    assert "sensor:remove-preexisting" not in adapter.events


@pytest.mark.asyncio
async def test_native_preparation_disables_ai_and_brakes_before_lease_arm() -> None:
    adapter = StopAdapter()
    service = AutonomyService(adapter, VisionSettings())  # type: ignore[arg-type]

    await service.prepare(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    assert adapter.events == ["ai:disabled", "brake:ego"]


@pytest.mark.asyncio
async def test_native_ai_stop_disables_ai_before_holding_brakes() -> None:
    adapter = StopAdapter()
    service = AutonomyService(adapter, VisionSettings())  # type: ignore[arg-type]
    await service.start(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    status = await service.stop()

    assert adapter.events == ["ai:traffic", "ai:disabled", "brake:ego"]
    assert status.running is False
    assert status.emergency_stopped is True
    assert status.emergency_reason == "operator_stop"


@pytest.mark.asyncio
async def test_stop_reports_ai_disable_failure_after_attempting_emergency_brake() -> None:
    adapter = FailingDisableAdapter()
    service = AutonomyService(adapter, VisionSettings())  # type: ignore[arg-type]
    await service.start(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    with pytest.raises(SafetyInterlockError, match="disable native AI"):
        await service.stop()

    assert adapter.events == ["ai:traffic", "ai:disabled", "brake:ego"]
    assert service.status().running is False


@pytest.mark.asyncio
async def test_stop_reports_emergency_brake_failure_after_disabling_ai() -> None:
    adapter = FailingBrakeAdapter()
    service = AutonomyService(adapter, VisionSettings())  # type: ignore[arg-type]
    await service.start(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    with pytest.raises(SafetyInterlockError, match="emergency brake"):
        await service.stop()

    assert adapter.events == ["ai:traffic", "ai:disabled", "brake:ego"]
    assert service.status().running is False


@pytest.mark.asyncio
async def test_start_failure_clears_state_and_brakes_best_effort() -> None:
    adapter = FailingStartAdapter()
    service = AutonomyService(adapter, VisionSettings())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="AI start failed"):
        await service.start(AutonomyStart(vehicle_id="ego", mode="native-ai"))

    assert adapter.events == ["ai:traffic", "ai:disabled", "brake:ego"]
    status = service.status()
    assert status.running is False
    assert status.vehicle_id is None
