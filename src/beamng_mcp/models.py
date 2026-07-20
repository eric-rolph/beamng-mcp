"""MCP-facing schemas and SDK-independent domain records."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_ABSOLUTE_COORDINATE = 1_000_000.0
MAX_SENSOR_PIXELS = 16_777_216
MIN_SENSOR_UPDATE_SECONDS = 1.0 / 240.0

CoordinateComponent = Annotated[
    float, Field(ge=-MAX_ABSOLUTE_COORDINATE, le=MAX_ABSOLUTE_COORDINATE)
]
Vector3 = tuple[CoordinateComponent, CoordinateComponent, CoordinateComponent]
DirectionComponent = Annotated[float, Field(ge=-1.0, le=1.0)]
QuaternionComponent = Annotated[float, Field(ge=-1.0, le=1.0)]
ScaleComponent = Annotated[float, Field(ge=0.0001, le=10_000.0)]
SensorDimension = Annotated[int, Field(ge=16, le=8192)]


def _valid_direction(value: tuple[float, float, float]) -> tuple[float, float, float]:
    if math.fsum(component * component for component in value) < 1e-12:
        raise ValueError("direction vector must be nonzero")
    return value


def _valid_quaternion(
    value: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if math.fsum(component * component for component in value) < 1e-12:
        raise ValueError("rotation quaternion must be nonzero")
    return value


Direction3 = Annotated[
    tuple[DirectionComponent, DirectionComponent, DirectionComponent],
    AfterValidator(_valid_direction),
]
Quaternion = Annotated[
    tuple[
        QuaternionComponent,
        QuaternionComponent,
        QuaternionComponent,
        QuaternionComponent,
    ],
    AfterValidator(_valid_quaternion),
]
Scale3 = tuple[ScaleComponent, ScaleComponent, ScaleComponent]
SensorResolution = tuple[SensorDimension, SensorDimension]
UnitControl = Annotated[float, Field(ge=0.0, le=1.0)]
SteeringControl = Annotated[float, Field(ge=-1.0, le=1.0)]
SafeMapIdentifier = Annotated[
    str, Field(min_length=1, max_length=96, pattern=r"^[A-Za-z_][A-Za-z0-9_.-]*$")
]
PositiveObjectId = Annotated[int, Field(ge=1)]
ColorComponent = Annotated[float, Field(ge=0.0, le=1.0)]
RGBColor = tuple[ColorComponent, ColorComponent, ColorComponent]
RGBAColor = tuple[ColorComponent, ColorComponent, ColorComponent, ColorComponent]
MapFieldValue = str | float | bool | RGBColor | RGBAColor


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, allow_inf_nan=False)


class OperationResult(StrictModel):
    ok: bool = True
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class CapabilitySnapshot(StrictModel):
    server_version: str
    mode: Literal["offline", "drive", "tech", "unknown"]
    beamngpy_connected: bool
    lua_connected: bool
    beamngpy_officially_supported: bool
    tools: list[str]
    limitations: list[str] = Field(default_factory=list)


class ConnectionStatus(StrictModel):
    connected: bool
    host: str
    port: int
    mode: Literal["offline", "drive", "tech", "unknown"] = "offline"
    home: str | None = None
    user: str | None = None
    version: str | None = None
    tech_enabled: bool | None = None
    last_error: str | None = None


class ScenarioRef(StrictModel):
    level: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")

    @field_validator("level", "name")
    @classmethod
    def reject_dot_segments(cls, value: str) -> str:
        if ".." in value:
            raise ValueError("scenario identifiers must not contain dot segments")
        return value


class ScenarioInfo(ScenarioRef):
    description: str | None = None
    source_file: str | None = None


class VehicleSpawn(StrictModel):
    vehicle_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    position: Vector3 = (0.0, 0.0, 0.0)
    rotation: Quaternion = (0.0, 0.0, 0.0, 1.0)
    configuration: str | None = Field(default=None, max_length=128)
    license_plate: str = Field(default="MCP", max_length=16)
    color: str | None = Field(default=None, max_length=64)
    cling: bool = True


class VehicleControl(StrictModel):
    vehicle_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    throttle: UnitControl = 0.0
    brake: UnitControl = 0.0
    steering: SteeringControl = 0.0
    parking_brake: UnitControl = 0.0
    clutch: UnitControl = 0.0
    gear: int | None = Field(default=None, ge=-1, le=32)

    @field_validator("brake")
    @classmethod
    def brake_wins_over_throttle(cls, value: float) -> float:
        return value


class VehicleTeleport(StrictModel):
    vehicle_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    position: Vector3
    rotation: Quaternion | None = None
    reset: bool = True


class VehicleAIConfig(StrictModel):
    vehicle_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    mode: Literal["disabled", "random", "traffic", "span", "manual", "chase", "flee", "stopping"]
    target_vehicle_id: str | None = Field(default=None, max_length=64)
    target_waypoint: str | None = Field(default=None, max_length=128)
    speed_mps: float | None = Field(default=None, ge=0.0, le=100.0)
    speed_mode: Literal["limit", "set"] = "limit"
    aggression: float | None = Field(default=None, ge=0.0, le=2.0)
    lane: bool | None = None

    @model_validator(mode="after")
    def validate_target_for_mode(self) -> VehicleAIConfig:
        if self.target_vehicle_id is not None and self.target_waypoint is not None:
            raise ValueError("configure either a target vehicle or a waypoint, not both")
        if self.target_vehicle_id is not None and self.mode not in {"chase", "flee"}:
            raise ValueError("target_vehicle_id requires AI mode chase or flee")
        if self.target_waypoint is not None and self.mode != "manual":
            raise ValueError("target_waypoint requires AI mode manual")
        return self


class VehicleInfo(StrictModel):
    vehicle_id: str
    model: str | None = None
    position: Vector3 | None = None
    direction: Vector3 | None = None
    velocity: Vector3 | None = None
    speed_mps: float | None = None
    connected: bool | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class SensorSpec(StrictModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    sensor_type: Literal[
        "camera",
        "lidar",
        "radar",
        "ultrasonic",
        "gps",
        "advanced_imu",
        "electrics",
        "damage",
        "state",
        "roads",
        "powertrain",
    ]
    vehicle_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    update_time: float = Field(default=0.1, ge=MIN_SENSOR_UPDATE_SECONDS, le=60.0)
    position: Vector3 = (0.0, 0.0, 1.5)
    direction: Direction3 = (0.0, -1.0, 0.0)
    resolution: SensorResolution = (640, 360)
    field_of_view_y: float = Field(default=70.0, gt=1.0, lt=179.0)
    shared_memory: bool = False
    streaming: bool = False
    render_annotations: bool = True
    render_depth: bool = True

    @model_validator(mode="after")
    def cap_render_pixels(self) -> SensorSpec:
        width, height = self.resolution
        if width * height > MAX_SENSOR_PIXELS:
            raise ValueError(f"sensor resolution must not exceed {MAX_SENSOR_PIXELS} pixels")
        return self


class SensorReading(StrictModel):
    name: str
    sensor_type: str
    timestamp: datetime = Field(default_factory=utc_now)
    data: dict[str, Any] = Field(default_factory=dict)
    artifact_paths: list[str] = Field(default_factory=list)


class RoadEdgesRequest(StrictModel):
    road_id: str = Field(min_length=1, max_length=256)


class MapObjectMutation(StrictModel):
    name: SafeMapIdentifier
    class_name: Literal["TSStatic", "PointLight", "SpotLight", "BeamNGWaypoint"]
    position: Vector3 = (0.0, 0.0, 0.0)
    rotation: Quaternion = (0.0, 0.0, 0.0, 1.0)
    scale: Scale3 = (1.0, 1.0, 1.0)
    fields: dict[str, MapFieldValue] = Field(default_factory=dict)


class MapObjectPatch(StrictModel):
    object_id: SafeMapIdentifier | PositiveObjectId
    new_name: SafeMapIdentifier | None = None
    position: Vector3 | None = None
    rotation: Quaternion | None = None
    scale: Scale3 | None = None
    fields: dict[str, MapFieldValue] = Field(default_factory=dict)


class MapObjectInfo(StrictModel):
    object_id: str | int
    name: str
    class_name: str
    position: Vector3 | None = None
    rotation: Quaternion | None = None
    scale: Vector3 | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class BridgeStatus(StrictModel):
    connected: bool
    authenticated: bool
    url: str
    bridge_version: str | None = None
    game_version: str | None = None
    latency_ms: float | None = None
    last_message_at: datetime | None = None
    last_error: str | None = None


class ModFileWrite(StrictModel):
    mod_name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    path: str = Field(min_length=1, max_length=512)
    content: str
    expected_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ModFileInfo(StrictModel):
    path: str
    size: int
    sha256: str


class ValidationIssue(StrictModel):
    severity: Literal["error", "warning"]
    path: str | None = None
    message: str


class ModValidation(StrictModel):
    valid: bool
    mod_name: str
    files_checked: int
    issues: list[ValidationIssue] = Field(default_factory=list)


class ModArtifact(StrictModel):
    mod_name: str
    path: str
    sha256: str
    size: int


class JobInfo(StrictModel):
    job_id: str
    kind: str
    status: Literal["pending", "running", "succeeded", "failed", "cancelled"]
    stage: str = Field(
        default="queued",
        min_length=1,
        max_length=128,
        description="Current work stage, or the terminal outcome stage",
    )
    cancellable: bool = Field(
        default=True,
        description="Whether job_cancel can safely interrupt the current stage",
    )
    created_at: datetime
    updated_at: datetime
    progress: float = Field(ge=0.0, le=1.0)
    result: dict[str, Any] | None = None
    error: str | None = None


class AutonomyStart(StrictModel):
    vehicle_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    mode: Literal["native-ai", "vision-lane", "hybrid"] = "hybrid"
    sensor_name: str = Field(default="mcp_driver_camera", max_length=64)
    target_speed_mps: float = Field(default=12.0, ge=0.5, le=45.0)
    max_speed_mps: float = Field(default=18.0, ge=0.5, le=55.0)
    ai_mode: Literal["random", "traffic", "span", "manual", "chase", "flee"] = "traffic"
    ai_target_vehicle_id: str | None = Field(default=None, max_length=64)
    ai_target_waypoint: str | None = Field(default=None, max_length=128)
    ai_aggression: float | None = Field(default=None, ge=0.0, le=2.0)
    ai_drive_in_lane: bool = True

    @model_validator(mode="after")
    def validate_native_ai_target(self) -> AutonomyStart:
        if self.ai_target_vehicle_id is not None and self.ai_target_waypoint is not None:
            raise ValueError("configure either an AI target vehicle or waypoint, not both")
        if self.ai_mode in {"chase", "flee"} and self.ai_target_vehicle_id is None:
            raise ValueError(f"ai_mode {self.ai_mode!r} requires ai_target_vehicle_id")
        if self.ai_target_vehicle_id is not None and self.ai_mode not in {"chase", "flee"}:
            raise ValueError("ai_target_vehicle_id requires ai_mode chase or flee")
        if self.ai_mode == "manual" and self.ai_target_waypoint is None:
            raise ValueError("ai_mode 'manual' requires ai_target_waypoint")
        if self.ai_target_waypoint is not None and self.ai_mode != "manual":
            raise ValueError("ai_target_waypoint requires ai_mode manual")
        return self


class AutonomyStatus(StrictModel):
    running: bool
    mode: str | None = None
    vehicle_id: str | None = None
    backend: str | None = None
    target_fps: float | None = None
    measured_fps: float | None = None
    frame_age_ms: float | None = None
    inference_ms: float | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    hazard_score: float | None = Field(default=None, ge=0.0, le=1.0)
    perception_device: str | None = None
    perception_providers: list[str] = Field(default_factory=list)
    last_control: dict[str, float] = Field(default_factory=dict)
    emergency_stopped: bool = False
    emergency_reason: str | None = None
    watchdog_armed: bool = False
    watchdog_latched: bool = False
    watchdog_reason: str | None = None
    watchdog_trips: int = Field(default=0, ge=0)
    engine_deadman_armed: bool = False
    engine_deadman_control_authorized: bool = False
    engine_deadman_lease_seconds: float | None = None
    engine_deadman_expires_in_ms: float | None = None
    engine_deadman_last_renewal_age_ms: float | None = None
    engine_deadman_last_error: str | None = None
    started_at: datetime | None = None
