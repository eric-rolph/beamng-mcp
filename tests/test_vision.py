from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from beamng_mcp.vision import (
    ColorSpace,
    ControlCommand,
    DeadmanWatchdog,
    HazardObservation,
    HuggingFaceSegFormerBackend,
    LaneCenterController,
    LaneCenterControllerConfig,
    LaneEstimate,
    ONNXRuntimeSegmentationBackend,
    ONNXRuntimeSegmentationConfig,
    OpenCVLaneBackend,
    PerceptionResult,
    SegFormerConfig,
    SegmentationClassMap,
    SensorFrame,
    SpeedGovernor,
    SpeedGovernorConfig,
    SupervisorConfig,
    SupervisorState,
    VehicleState,
    VisionSupervisor,
    WatchdogConfig,
    estimate_lane_from_drivable_mask,
    perception_from_segmentation,
)


def _frame(
    *,
    sequence: int = 1,
    captured_at: float | None = None,
    speed_mps: float = 0.0,
    width: int = 200,
    height: int = 120,
) -> SensorFrame:
    return SensorFrame(
        image=np.zeros((height, width, 3), dtype=np.uint8),
        captured_at=time.monotonic() if captured_at is None else captured_at,
        sequence=sequence,
        color_space=ColorSpace.BGR,
        vehicle=VehicleState(speed_mps=speed_mps),
    )


def _road_mask(
    *,
    height: int = 120,
    width: int = 200,
    bottom_shift_px: float = 0.0,
    top_shift_px: float = 0.0,
) -> np.ndarray:
    mask = np.zeros((height, width), dtype=bool)
    top = int(height * 0.42)
    for y in range(top, height):
        progress = (y - top) / max(height - 1 - top, 1)
        center = width / 2 + top_shift_px * (1 - progress) + bottom_shift_px * progress
        half_width = width * (0.13 + 0.29 * progress)
        left = max(0, round(center - half_width))
        right = min(width, round(center + half_width))
        mask[y, left:right] = True
    return mask


def _perception(
    *,
    confidence: float = 0.9,
    offset: float = 0.0,
    heading: float = 0.0,
    curvature: float = 0.0,
    hazard: float = 0.0,
    sequence: int = 1,
    captured_at: float = 1.0,
) -> PerceptionResult:
    lane = LaneEstimate(
        center_offset=offset,
        heading_error_rad=heading,
        curvature=curvature,
        confidence=confidence,
        center_x_px=100.0 + 100.0 * offset,
        lookahead_x_px=100.0 + 100.0 * offset,
        lane_width_px=100.0,
    )
    hazards = () if hazard == 0 else (HazardObservation("obstacle", hazard),)
    return PerceptionResult(
        frame_sequence=sequence,
        captured_at=captured_at,
        image_shape=(120, 200),
        backend="synthetic",
        lane=lane,
        hazards=hazards,
    )


def test_frame_validates_shape_and_copies_metadata() -> None:
    metadata: dict[str, Any] = {"camera": "front"}
    frame = SensorFrame(
        np.zeros((16, 24, 3), dtype=np.uint8),
        captured_at=1.0,
        metadata=metadata,
    )
    metadata["camera"] = "rear"
    assert frame.width == 24
    assert frame.height == 16
    assert frame.metadata["camera"] == "front"

    with pytest.raises(ValueError, match="shape"):
        SensorFrame(np.zeros((16, 24), dtype=np.uint8), captured_at=1.0)


def test_import_does_not_load_optional_model_frameworks() -> None:
    script = (
        "import sys; import beamng_mcp.vision; "
        "assert 'onnxruntime' not in sys.modules; "
        "assert 'transformers' not in sys.modules; "
        "assert 'torch' not in sys.modules; "
        "assert 'cv2' not in sys.modules"
    )
    environment = dict(os.environ)
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (source_root, environment.get("PYTHONPATH", "")))
    )
    subprocess.run(  # noqa: S603 - fixed interpreter and static child script
        [sys.executable, "-c", script],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )


def test_lane_geometry_tracks_center_offset_and_heading() -> None:
    centered = estimate_lane_from_drivable_mask(_road_mask())
    assert centered is not None
    assert centered.center_offset == pytest.approx(0.0, abs=0.04)
    assert centered.confidence > 0.65

    right_curve = estimate_lane_from_drivable_mask(
        _road_mask(bottom_shift_px=28.0, top_shift_px=5.0)
    )
    assert right_curve is not None
    assert right_curve.center_offset > 0.20
    assert right_curve.heading_error_rad < 0.0


def test_segmentation_extracts_lane_and_near_center_hazard() -> None:
    frame = _frame()
    labels = np.zeros((frame.height, frame.width), dtype=np.int64)
    labels[_road_mask()] = 1
    labels[86:119, 84:116] = 2
    confidence = np.full(labels.shape, 0.95, dtype=np.float32)
    class_map = SegmentationClassMap(
        drivable_class_ids=(1,),
        hazard_class_ids=(2,),
        hazard_names={2: "vehicle"},
    )
    result = perception_from_segmentation(
        frame,
        labels,
        class_map=class_map,
        backend="test_segmentation",
        inference_ms=2.5,
        confidence_map=confidence,
    )
    assert result.lane is not None
    assert result.lane.confidence > 0.5
    assert result.hazards[0].kind == "vehicle"
    assert result.hazard_score > 0.75
    assert result.drivable_mask is not None
    assert result.drivable_mask.dtype == np.bool_


def test_opencv_classical_backend_detects_centered_and_shifted_lanes() -> None:
    cv2 = pytest.importorskip("cv2")
    height, width = 240, 320

    def lane_frame(shift: int, sequence: int) -> SensorFrame:
        image = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.line(image, (82 + shift, 238), (135 + shift, 120), (255, 255, 255), 7)
        cv2.line(image, (238 + shift, 238), (185 + shift, 120), (255, 255, 255), 7)
        return SensorFrame(image, captured_at=1.0, sequence=sequence)

    backend = OpenCVLaneBackend()
    centered = backend.infer(lane_frame(0, 1))
    shifted = backend.infer(lane_frame(24, 2))
    assert centered.lane is not None
    assert centered.lane.center_offset == pytest.approx(0.0, abs=0.08)
    assert centered.lane.confidence > 0.55
    assert shifted.lane is not None
    assert shifted.lane.center_offset > 0.08
    assert shifted.metadata["left_segment_count"] > 0
    assert shifted.metadata["right_segment_count"] > 0


def test_segformer_is_lazy_and_disables_downloads_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    calls: list[dict[str, Any]] = []

    class DummyProcessor:
        @classmethod
        def from_pretrained(cls, _name: str, **kwargs: Any) -> object:
            calls.append(kwargs)
            return object()

    class DummyModel:
        @classmethod
        def from_pretrained(cls, _name: str, **kwargs: Any) -> DummyModel:
            calls.append(kwargs)
            return cls()

        def to(self, **_kwargs: Any) -> DummyModel:
            return self

        def eval(self) -> None:
            return None

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    fake_transformers = ModuleType("transformers")
    fake_transformers.AutoImageProcessor = DummyProcessor  # type: ignore[attr-defined]
    fake_transformers.SegformerForSemanticSegmentation = DummyModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    backend = HuggingFaceSegFormerBackend(
        SegFormerConfig(
            model_id_or_path="local-model",
            class_map=SegmentationClassMap(drivable_class_ids=(1,)),
        )
    )
    assert not backend.loaded
    assert calls == []
    backend._ensure_loaded()
    assert backend.loaded
    assert backend.device == "cpu"
    assert len(calls) == 2
    assert all(call["local_files_only"] is True for call in calls)
    assert calls[0]["use_fast"] is False


def test_segformer_moves_floating_inputs_at_model_precision() -> None:
    calls: list[dict[str, Any]] = []

    class FakeTensor:
        def __init__(self, floating: bool) -> None:
            self.floating = floating

        def is_floating_point(self) -> bool:
            return self.floating

        def to(self, **kwargs: Any) -> FakeTensor:
            calls.append(kwargs)
            return self

    floating = FakeTensor(True)
    integer = FakeTensor(False)
    untouched = object()
    moved = HuggingFaceSegFormerBackend._move_inputs(
        {"pixel_values": floating, "labels": integer, "metadata": untouched},
        device="cuda:0",
        floating_dtype="float16",
    )

    assert moved == {"pixel_values": floating, "labels": integer, "metadata": untouched}
    assert calls == [
        {"device": "cuda:0", "dtype": "float16"},
        {"device": "cuda:0"},
    ]


def test_onnx_decodes_logits_without_loading_a_session() -> None:
    backend = ONNXRuntimeSegmentationBackend(
        ONNXRuntimeSegmentationConfig(
            model_path="unused.onnx",
            class_map=SegmentationClassMap(drivable_class_ids=(1,)),
            input_size=(8, 10),
        )
    )
    logits = np.zeros((1, 2, 4, 5), dtype=np.float32)
    logits[:, 1, :, 2:] = 4.0
    labels, confidence = backend._decode_output(logits, 8, 10)
    assert labels.shape == (8, 10)
    assert confidence.shape == (8, 10)
    assert np.all(labels[:, -3:] == 1)
    assert float(np.min(confidence)) >= 0.5
    assert not backend.loaded


def test_onnx_gpu_provider_options_bound_memory() -> None:
    pytest.importorskip("onnxruntime")
    backend = ONNXRuntimeSegmentationBackend(
        ONNXRuntimeSegmentationConfig(
            model_path="unused.onnx",
            class_map=SegmentationClassMap(drivable_class_ids=(1,)),
            gpu_memory_limit_mb=1024,
            tensorrt_workspace_mb=512,
        )
    )
    specs = backend._build_provider_specs(
        [
            "TensorrtExecutionProvider",
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]
    )
    tensorrt_options = specs[0][1]
    cuda_options = specs[1][1]
    assert tensorrt_options["trt_max_workspace_size"] == 512 * 1024 * 1024
    assert cuda_options["gpu_mem_limit"] == 1024 * 1024 * 1024
    assert specs[-1] == "CPUExecutionProvider"


def test_lane_controller_steers_toward_lane_and_rate_limits() -> None:
    controller = LaneCenterController(
        LaneCenterControllerConfig(
            proportional_offset=1.0,
            proportional_heading=0.0,
            derivative_offset=0.0,
            steering_rate_limit_per_s=1.0,
            default_dt_s=0.1,
        )
    )
    right_lane = _perception(offset=0.7).lane
    assert right_lane is not None
    first = controller.compute(right_lane, now=1.0)
    second = controller.compute(right_lane, now=1.1)
    assert first == pytest.approx(0.1)
    assert second == pytest.approx(0.2)


def test_speed_governor_reduces_speed_and_emergency_brakes() -> None:
    governor = SpeedGovernor(SpeedGovernorConfig(cruise_speed_mps=14.0))
    clear = governor.decide(_perception(confidence=0.95), current_speed_mps=5.0)
    uncertain = governor.decide(_perception(confidence=0.35), current_speed_mps=5.0)
    hazard = governor.decide(
        _perception(confidence=0.95, hazard=0.97),
        current_speed_mps=5.0,
    )
    assert clear.target_speed_mps == pytest.approx(14.0)
    assert clear.throttle > 0.0
    assert uncertain.target_speed_mps < clear.target_speed_mps
    assert hazard.emergency
    assert hazard.throttle == 0.0
    assert hazard.brake == 1.0


def test_deadman_watchdog_latches_and_rate_limits_emergency() -> None:
    watchdog = DeadmanWatchdog(
        WatchdogConfig(
            frame_timeout_s=0.20,
            command_timeout_s=0.15,
            maximum_frame_age_s=0.10,
            check_interval_s=0.01,
            emergency_repeat_s=0.10,
        )
    )
    watchdog.arm(0.0)
    watchdog.observe_frame(_frame(captured_at=0.01), 0.01)
    watchdog.observe_command(0.01)
    assert watchdog.check(0.05) is None
    assert watchdog.emergency_due(0.18) == "stale_frame"
    watchdog.record_emergency(0.18)
    assert watchdog.emergency_due(0.20) is None
    assert watchdog.emergency_due(0.29) == "frame_timeout"
    assert watchdog.trips == 1


def test_producer_freshness_latch_persists_until_a_fresh_frame_arrives() -> None:
    watchdog = DeadmanWatchdog(
        WatchdogConfig(
            frame_timeout_s=0.2,
            command_timeout_s=0.2,
            maximum_frame_age_s=0.1,
            check_interval_s=0.01,
        )
    )
    watchdog.arm(0.0)

    watchdog.observe_source_failure("frozen_frame")

    assert watchdog.check(0.05) == "frozen_frame"
    assert watchdog.trips == 1
    watchdog.observe_frame(_frame(captured_at=0.06), 0.06)
    assert watchdog.check(0.07) is None


class _FrameSource:
    def __init__(self, frames: list[SensorFrame]) -> None:
        self.frames = frames

    async def next_frame(self) -> SensorFrame:
        if not self.frames:
            raise StopAsyncIteration
        return self.frames.pop(0)


class _BlockingFrameSource:
    async def next_frame(self) -> SensorFrame:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class _RecordingSink:
    def __init__(self) -> None:
        self.commands: list[ControlCommand] = []

    async def send_control(self, command: ControlCommand) -> None:
        self.commands.append(command)


class _SyntheticBackend:
    name = "synthetic_backend"

    def infer(self, frame: SensorFrame) -> PerceptionResult:
        return replace(
            _perception(
                confidence=0.9,
                offset=0.2,
                sequence=frame.sequence,
                captured_at=frame.captured_at,
            ),
            inference_ms=1.0,
        )


def test_supervisor_step_emits_control_and_metrics() -> None:
    async def scenario() -> None:
        now = time.monotonic()
        sink = _RecordingSink()
        supervisor = VisionSupervisor(
            frame_source=_FrameSource([_frame(sequence=7, captured_at=now, speed_mps=2.0)]),
            control_sink=sink,
            backend=_SyntheticBackend(),
            config=SupervisorConfig(inference_in_worker_thread=False),
        )
        command = await supervisor.step()
        status = supervisor.status()
        assert command.frame_sequence == 7
        assert command.steering > 0.0
        assert not command.emergency
        assert sink.commands == [command]
        assert status.state is SupervisorState.RUNNING
        assert status.metrics.frames_received == 1
        assert status.metrics.frames_processed == 1
        assert status.metrics.commands_sent == 1
        assert status.last_perception is not None
        assert status.last_perception.lane_confidence == pytest.approx(0.9)

    asyncio.run(scenario())


def test_supervisor_rejects_stale_frame_with_emergency_brake() -> None:
    async def scenario() -> None:
        now = time.monotonic()
        sink = _RecordingSink()
        supervisor = VisionSupervisor(
            frame_source=_FrameSource([_frame(sequence=1, captured_at=now - 1.0)]),
            control_sink=sink,
            backend=_SyntheticBackend(),
            watchdog_config=WatchdogConfig(
                frame_timeout_s=0.1,
                command_timeout_s=0.1,
                maximum_frame_age_s=0.05,
                check_interval_s=0.01,
                emergency_repeat_s=0.05,
            ),
            config=SupervisorConfig(inference_in_worker_thread=False),
        )
        command = await supervisor.step()
        assert command.emergency
        assert command.reason == "stale_frame"
        assert command.brake == 1.0
        assert supervisor.status().metrics.stale_frames == 1

    asyncio.run(scenario())


def test_concurrent_watchdog_brakes_when_frame_source_stalls() -> None:
    async def scenario() -> None:
        sink = _RecordingSink()
        supervisor = VisionSupervisor(
            frame_source=_BlockingFrameSource(),
            control_sink=sink,
            backend=_SyntheticBackend(),
            watchdog_config=WatchdogConfig(
                frame_timeout_s=0.05,
                command_timeout_s=0.04,
                maximum_frame_age_s=0.04,
                check_interval_s=0.01,
                emergency_repeat_s=0.03,
            ),
            config=SupervisorConfig(
                target_loop_hz=100.0,
                inference_in_worker_thread=False,
            ),
        )
        task = asyncio.create_task(supervisor.run())
        await asyncio.sleep(0.085)
        supervisor.request_stop()
        await asyncio.wait_for(task, timeout=0.5)
        assert any(command.emergency for command in sink.commands)
        assert any(
            command.reason in {"command_timeout", "frame_timeout"} for command in sink.commands
        )
        assert supervisor.status().state is SupervisorState.STOPPED
        assert supervisor.status().metrics.watchdog_emergency_commands >= 1

    asyncio.run(scenario())
