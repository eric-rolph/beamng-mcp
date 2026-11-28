"""Reviewed, bounded requests for the official in-game MCP (no code or file access)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NativeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, populate_by_name=True)


class NativeVector(NativeModel):
    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)
    z: float = Field(ge=-1_000_000, le=1_000_000)


class NativeQuaternion(NativeModel):
    x: float = Field(ge=-1, le=1)
    y: float = Field(ge=-1, le=1)
    z: float = Field(ge=-1, le=1)
    w: float = Field(ge=-1, le=1)

    @model_validator(mode="after")
    def unit_quaternion(self) -> NativeQuaternion:
        if abs(self.x**2 + self.y**2 + self.z**2 + self.w**2 - 1) > 0.01:
            raise ValueError("Rotation must be a unit quaternion")
        return self


class NativeSnapshot(NativeModel):
    action: Literal[
        "get_status",
        "get_camera_state",
        "get_performance_metrics",
        "get_fps_limit_reason",
        "get_vram_usage",
        "get_render_info",
        "get_simulation_state",
        "get_time_of_day",
        "get_ui_state",
        "get_vehicles",
        "get_player_vehicle_id",
        "list_levels",
        "editor_status",
        "get_editor_selection",
        "list_edit_modes",
        "dump_vue_state",
    ]


class NativeVehicleQuery(NativeModel):
    action: Literal[
        "get_vehicle", "get_position", "get_vehicle_damage", "get_part_tree", "get_vehicle_files"
    ]
    id: int = Field(gt=0)


class NativeInstability(NativeModel):
    action: Literal["get_instability"]
    clear: bool = False


class NativeConfigs(NativeModel):
    action: Literal["get_configs"]
    model: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )


class NativeLogs(NativeModel):
    action: Literal["get_logs"]
    lines: int = Field(default=200, ge=1, le=5000)


class NativeObjectQuery(NativeModel):
    action: Literal["get_object", "serialize_object"]
    id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def one_target(self) -> NativeObjectQuery:
        if (self.id is None) == (self.name is None):
            raise ValueError("Supply exactly one object id or name")
        return self


class NativeFindObjects(NativeModel):
    action: Literal["find_objects"]
    class_name: str = Field(alias="class", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_]+$")
    pattern: str | None = Field(default=None, max_length=256)


class NativeEditorClasses(NativeModel):
    action: Literal["list_editor_classes"]
    pattern: str | None = Field(default=None, max_length=128)


class NativeViewObjects(NativeModel):
    action: Literal["view_objects"]
    class_name: str = Field(
        default="vehicles", alias="class", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_]+$"
    )
    max_distance: float = Field(default=1000, alias="maxDist", gt=0, le=10000)


class NativeGroundQuery(NativeModel):
    action: Literal["get_ground_at_point"]
    pos: NativeVector
    radius: float = Field(default=2, gt=0, le=100)


class NativeRaycast(NativeModel):
    action: Literal["raycast"]
    start: NativeVector = Field(alias="from")
    end: NativeVector = Field(alias="to")
    render_geometry: bool = Field(default=False, alias="renderGeometry")
    include_terrain: bool = Field(default=True, alias="includeTerrain")

    @model_validator(mode="after")
    def bounded_ray(self) -> NativeRaycast:
        distance2 = sum(
            (getattr(self.end, a) - getattr(self.start, a)) ** 2 for a in ("x", "y", "z")
        )
        if not 0 < distance2 <= 10000**2:
            raise ValueError("Ray length must be greater than zero and at most 10000 metres")
        return self


class NativeNavgraph(NativeModel):
    action: Literal["get_navgraph"]
    near: NativeVector | None = None
    radius: float = Field(default=100, gt=0, le=10000)
    max_nodes: int = Field(default=300, alias="maxNodes", ge=1, le=2000)


NativeInspection = Annotated[
    NativeSnapshot
    | NativeInstability
    | NativeVehicleQuery
    | NativeConfigs
    | NativeLogs
    | NativeObjectQuery
    | NativeFindObjects
    | NativeEditorClasses
    | NativeViewObjects
    | NativeGroundQuery
    | NativeRaycast
    | NativeNavgraph,
    Field(discriminator="action"),
]


class NativeCameraMode(NativeModel):
    action: Literal["set_camera"]
    name: Literal["orbit", "driver", "chase", "external", "hood", "top", "dash", "free"]


class NativeOrbitCamera(NativeModel):
    action: Literal["orbit_camera"]
    id: int = Field(gt=0)
    yaw: float = Field(default=0, ge=-360, le=360)
    pitch: float = Field(default=20, ge=-85, le=85)
    distance: float = Field(default=10, ge=0.1, le=5000)
    spin: float = Field(default=0, ge=-180, le=180)


class NativeFreeCamera(NativeModel):
    action: Literal["set_free_camera"]
    pos: NativeVector
    rot: NativeQuaternion
    fov: float = Field(default=60, ge=10, le=150)


NativeCameraRequest = Annotated[
    NativeCameraMode | NativeOrbitCamera | NativeFreeCamera, Field(discriminator="action")
]


class NativeEditorActive(NativeModel):
    action: Literal["set_editor_active"]
    active: bool


class NativeEditorSelect(NativeModel):
    action: Literal["select_editor_objects"]
    ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=100)
    mode: Literal["new", "add", "remove", "toggle"] = "new"


class NativeEditorView(NativeModel):
    action: Literal["clear_editor_selection", "fit_view_to_selection"]


class NativeEditorMode(NativeModel):
    action: Literal["set_edit_mode"]
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_]+$")


NativeEditorRequest = Annotated[
    NativeEditorActive | NativeEditorSelect | NativeEditorView | NativeEditorMode,
    Field(discriminator="action"),
]


class NativeScreenshot(NativeModel):
    action: Literal["screenshot_image"] = "screenshot_image"
    scale: float = Field(default=0.4, ge=0.05, le=1)


class NativeUIVisibility(NativeModel):
    action: Literal["toggle_ui"]
    show: bool


class NativeMessage(NativeModel):
    action: Literal["show_message"]
    text: str = Field(min_length=1, max_length=500, pattern=r"^[^<>]*$")
    ttl: float = Field(default=5, gt=0, le=30)
    category: Literal["beamng_mcp"] = "beamng_mcp"
    icon: Literal["info"] = "info"


DebugShapeId = Annotated[str, Field(pattern=r"^beamng_mcp_debug_(?:[0-9]|[12][0-9]|3[01])$")]


class NativeDebugClear(NativeModel):
    action: Literal["debug_clear"]
    id: DebugShapeId


class NativeDebugDraw(NativeModel):
    action: Literal["debug_draw"]
    id: DebugShapeId
    kind: Literal["sphere", "line", "text"] = "sphere"
    pos: NativeVector | None = None
    start: NativeVector | None = Field(default=None, alias="from")
    end: NativeVector | None = Field(default=None, alias="to")
    radius: float = Field(default=0.5, gt=0, le=100)
    label: str | None = Field(default=None, min_length=1, max_length=256)
    ttl: float = Field(default=10, gt=0, le=60)

    @model_validator(mode="after")
    def require_shape_geometry(self) -> NativeDebugDraw:
        if self.kind == "line":
            if self.start is None or self.end is None or self.pos is not None:
                raise ValueError("Debug line needs from and to, without pos")
        elif self.pos is None or self.start is not None or self.end is not None:
            raise ValueError("Debug sphere/text needs pos, without from/to")
        if self.kind == "text" and self.label is None:
            raise ValueError("Debug text needs a label")
        return self


NativeDisplayRequest = Annotated[
    NativeUIVisibility | NativeMessage | NativeDebugDraw | NativeDebugClear,
    Field(discriminator="action"),
]


class NativePhysicsState(NativeModel):
    action: Literal["pause_physics", "resume_physics"]


class NativePhysicsStep(NativeModel):
    action: Literal["step_physics"]
    steps: int = Field(default=1, ge=1, le=1000)


class NativeSimulationSpeed(NativeModel):
    action: Literal["set_simulation_speed"]
    scale: float = Field(ge=0.01, le=4)


NativeSimulationRequest = Annotated[
    NativePhysicsState | NativePhysicsStep | NativeSimulationSpeed, Field(discriminator="action")
]


class NativeVehiclePose(NativeModel):
    action: Literal["set_position"]
    id: int = Field(gt=0)
    pos: NativeVector
    rot: NativeQuaternion | None = None


class NativeVehicleRecover(NativeModel):
    action: Literal["recover_vehicle"]
    id: int = Field(gt=0)


class NativeVehicleSpawn(NativeModel):
    action: Literal["spawn"]
    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    config: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"
    )
    add: Literal[True] = True


NativeVehicleRequest = Annotated[
    NativeVehiclePose | NativeVehicleRecover | NativeVehicleSpawn, Field(discriminator="action")
]


class NativeTimeOfDay(NativeModel):
    action: Literal["set_time_of_day"]
    time: float = Field(ge=0, le=1)
    play: bool = False
    day_length: float | None = Field(default=None, alias="dayLength", ge=1, le=86400)


NativeRequest = Annotated[
    NativeInspection
    | NativeCameraRequest
    | NativeEditorRequest
    | NativeScreenshot
    | NativeSimulationRequest
    | NativeDisplayRequest
    | NativeVehicleRequest
    | NativeTimeOfDay,
    Field(discriminator="action"),
]
