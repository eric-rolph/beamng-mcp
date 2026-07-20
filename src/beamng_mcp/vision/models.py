"""Core data structures for the real-time vision and control subsystem.

The module intentionally depends only on the Python standard library and
NumPy.  It has no MCP, BeamNGpy, Pydantic, model-runtime, or network
dependencies, which keeps the control core straightforward to exercise in
unit tests and embed in different transports.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

import numpy as np
from numpy.typing import NDArray

ImageArray = NDArray[Any]
MaskArray = NDArray[np.bool_]


def _finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")


def _unit_interval(name: str, value: float) -> None:
    _finite(name, value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")


def _immutable_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Copy metadata so callers cannot mutate a result through their input."""

    return MappingProxyType(dict(metadata))


class ColorSpace(StrEnum):
    """Color ordering of a :class:`SensorFrame` image."""

    BGR = "bgr"
    RGB = "rgb"
    GRAY = "gray"


@dataclass(frozen=True, slots=True)
class VehicleState:
    """Small telemetry sample associated with a camera frame."""

    speed_mps: float = 0.0
    yaw_rate_rps: float = 0.0

    def __post_init__(self) -> None:
        _finite("speed_mps", self.speed_mps)
        _finite("yaw_rate_rps", self.yaw_rate_rps)
        if self.speed_mps < 0.0:
            raise ValueError("speed_mps cannot be negative")


@dataclass(frozen=True, slots=True)
class SensorFrame:
    """A timestamped image and the vehicle state observed with it.

    ``captured_at`` is expected to use the same monotonic clock as the
    supervisor.  Keeping it explicit lets the supervisor reject buffered or
    stale frames instead of treating them as fresh observations.
    """

    image: ImageArray
    captured_at: float
    sequence: int = 0
    color_space: ColorSpace = ColorSpace.BGR
    vehicle: VehicleState = field(default_factory=VehicleState)
    source: str = "camera"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            color_space = ColorSpace(self.color_space)
        except ValueError as exc:
            raise ValueError(f"unsupported color space: {self.color_space!r}") from exc
        object.__setattr__(self, "color_space", color_space)
        if not isinstance(self.image, np.ndarray):
            raise TypeError("image must be a numpy.ndarray")
        if self.image.size == 0:
            raise ValueError("image cannot be empty")
        if color_space is ColorSpace.GRAY:
            if self.image.ndim != 2:
                raise ValueError("GRAY frames must have shape (height, width)")
        elif self.image.ndim != 3 or self.image.shape[2] != 3:
            raise ValueError("BGR/RGB frames must have shape (height, width, 3)")
        if self.image.shape[0] < 2 or self.image.shape[1] < 2:
            raise ValueError("image height and width must both be at least 2")
        _finite("captured_at", self.captured_at)
        if self.sequence < 0:
            raise ValueError("sequence cannot be negative")
        if not self.source:
            raise ValueError("source cannot be empty")
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def width(self) -> int:
        return int(self.image.shape[1])


@dataclass(frozen=True, slots=True)
class LaneEstimate:
    """Lane position relative to the camera/vehicle center line.

    ``center_offset`` is normalized by half the image width.  Negative values
    mean the estimated lane center is left of the vehicle; positive values
    mean it is right.  ``heading_error_rad`` follows the same sign convention.
    """

    center_offset: float
    heading_error_rad: float
    curvature: float
    confidence: float
    center_x_px: float
    lookahead_x_px: float
    lane_width_px: float | None = None

    def __post_init__(self) -> None:
        _finite("center_offset", self.center_offset)
        _finite("heading_error_rad", self.heading_error_rad)
        _finite("curvature", self.curvature)
        _finite("center_x_px", self.center_x_px)
        _finite("lookahead_x_px", self.lookahead_x_px)
        _unit_interval("confidence", self.confidence)
        if not -1.0 <= self.center_offset <= 1.0:
            raise ValueError("center_offset must be in [-1, 1]")
        if not -math.pi / 2 <= self.heading_error_rad <= math.pi / 2:
            raise ValueError("heading_error_rad must be in [-pi/2, pi/2]")
        if self.lane_width_px is not None:
            _finite("lane_width_px", self.lane_width_px)
            if self.lane_width_px <= 0.0:
                raise ValueError("lane_width_px must be positive")


@dataclass(frozen=True, slots=True)
class HazardObservation:
    """A normalized hazard estimate produced by perception."""

    kind: str
    score: float
    bbox: tuple[float, float, float, float] | None = None
    distance_m: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("hazard kind cannot be empty")
        _unit_interval("score", self.score)
        if self.bbox is not None:
            if len(self.bbox) != 4:
                raise ValueError("bbox must contain (x_min, y_min, x_max, y_max)")
            for coordinate in self.bbox:
                _unit_interval("bbox coordinate", coordinate)
            x_min, y_min, x_max, y_max = self.bbox
            if x_min > x_max or y_min > y_max:
                raise ValueError("bbox minimums cannot exceed maximums")
        if self.distance_m is not None:
            _finite("distance_m", self.distance_m)
            if self.distance_m < 0.0:
                raise ValueError("distance_m cannot be negative")
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class PerceptionResult:
    """Perception output for one frame."""

    frame_sequence: int
    captured_at: float
    image_shape: tuple[int, int]
    backend: str
    lane: LaneEstimate | None
    hazards: tuple[HazardObservation, ...] = ()
    drivable_mask: MaskArray | None = None
    lane_mask: MaskArray | None = None
    inference_ms: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.frame_sequence < 0:
            raise ValueError("frame_sequence cannot be negative")
        _finite("captured_at", self.captured_at)
        if len(self.image_shape) != 2 or min(self.image_shape) < 2:
            raise ValueError("image_shape must contain positive (height, width)")
        if not self.backend:
            raise ValueError("backend cannot be empty")
        _finite("inference_ms", self.inference_ms)
        if self.inference_ms < 0.0:
            raise ValueError("inference_ms cannot be negative")
        for name, mask in (
            ("drivable_mask", self.drivable_mask),
            ("lane_mask", self.lane_mask),
        ):
            if mask is not None:
                if not isinstance(mask, np.ndarray) or mask.ndim != 2:
                    raise ValueError(f"{name} must be a two-dimensional ndarray")
                if tuple(mask.shape) != tuple(self.image_shape):
                    raise ValueError(
                        f"{name} shape {mask.shape!r} does not match image_shape "
                        f"{self.image_shape!r}"
                    )
        object.__setattr__(self, "hazards", tuple(self.hazards))
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))

    @property
    def lane_confidence(self) -> float:
        return self.lane.confidence if self.lane is not None else 0.0

    @property
    def hazard_score(self) -> float:
        return max((hazard.score for hazard in self.hazards), default=0.0)


@dataclass(frozen=True, slots=True)
class ControlCommand:
    """Normalized actuation request emitted by the controller."""

    steering: float
    throttle: float
    brake: float
    target_speed_mps: float
    issued_at: float
    frame_sequence: int | None = None
    emergency: bool = False
    reason: str = "tracking"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _finite("steering", self.steering)
        if not -1.0 <= self.steering <= 1.0:
            raise ValueError("steering must be in [-1, 1]")
        _unit_interval("throttle", self.throttle)
        _unit_interval("brake", self.brake)
        _finite("target_speed_mps", self.target_speed_mps)
        if self.target_speed_mps < 0.0:
            raise ValueError("target_speed_mps cannot be negative")
        _finite("issued_at", self.issued_at)
        if self.frame_sequence is not None and self.frame_sequence < 0:
            raise ValueError("frame_sequence cannot be negative")
        if self.emergency and (self.throttle != 0.0 or self.brake <= 0.0):
            raise ValueError("emergency commands require zero throttle and positive brake")
        if not self.reason:
            raise ValueError("reason cannot be empty")
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))

    @classmethod
    def emergency_stop(
        cls,
        *,
        issued_at: float,
        reason: str,
        brake: float = 1.0,
        frame_sequence: int | None = None,
    ) -> ControlCommand:
        return cls(
            steering=0.0,
            throttle=0.0,
            brake=brake,
            target_speed_mps=0.0,
            issued_at=issued_at,
            frame_sequence=frame_sequence,
            emergency=True,
            reason=reason,
        )


class SupervisorState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    EMERGENCY = "emergency"
    STOPPING = "stopping"
    FAILED = "failed"
