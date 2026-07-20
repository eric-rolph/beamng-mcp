"""Real-time, SDK-independent perception and vehicle-control subsystem."""

from .backends import (
    BackendUnavailableError,
    HuggingFaceSegFormerBackend,
    ModelLoadError,
    ONNXRuntimeSegmentationBackend,
    ONNXRuntimeSegmentationConfig,
    OpenCVLaneBackend,
    OpenCVLaneConfig,
    SegFormerConfig,
)
from .control import (
    DrivingController,
    LaneCenterController,
    LaneCenterControllerConfig,
    SpeedDecision,
    SpeedGovernor,
    SpeedGovernorConfig,
)
from .geometry import (
    LaneGeometryConfig,
    SegmentationClassMap,
    estimate_lane_from_drivable_mask,
    hazards_from_labels,
    perception_from_segmentation,
)
from .interfaces import (
    AsyncControlSink,
    AsyncFrameSource,
    FrameFreshnessError,
    PerceptionBackend,
)
from .models import (
    ColorSpace,
    ControlCommand,
    HazardObservation,
    LaneEstimate,
    PerceptionResult,
    SensorFrame,
    SupervisorState,
    VehicleState,
)
from .supervisor import (
    MetricsSnapshot,
    SupervisorConfig,
    SupervisorStatus,
    VisionSupervisor,
)
from .watchdog import DeadmanWatchdog, WatchdogConfig, WatchdogSnapshot

__all__ = [
    "AsyncControlSink",
    "AsyncFrameSource",
    "BackendUnavailableError",
    "ColorSpace",
    "ControlCommand",
    "DeadmanWatchdog",
    "DrivingController",
    "FrameFreshnessError",
    "HazardObservation",
    "HuggingFaceSegFormerBackend",
    "LaneCenterController",
    "LaneCenterControllerConfig",
    "LaneEstimate",
    "LaneGeometryConfig",
    "MetricsSnapshot",
    "ModelLoadError",
    "ONNXRuntimeSegmentationBackend",
    "ONNXRuntimeSegmentationConfig",
    "OpenCVLaneBackend",
    "OpenCVLaneConfig",
    "PerceptionBackend",
    "PerceptionResult",
    "SegFormerConfig",
    "SegmentationClassMap",
    "SensorFrame",
    "SpeedDecision",
    "SpeedGovernor",
    "SpeedGovernorConfig",
    "SupervisorConfig",
    "SupervisorState",
    "SupervisorStatus",
    "VehicleState",
    "VisionSupervisor",
    "WatchdogConfig",
    "WatchdogSnapshot",
    "estimate_lane_from_drivable_mask",
    "hazards_from_labels",
    "perception_from_segmentation",
]
