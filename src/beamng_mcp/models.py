from typing import Any, Literal

from pydantic import BaseModel, Field


class Pose(BaseModel):
    pos: tuple[float, float, float]
    rot_quat: tuple[float, float, float, float] = (0, 0, 0, 1)


class VehicleSpec(BaseModel):
    vehicle_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    model: str = "etk800"
    pose: Pose
    config: str | None = None


class RoadSpec(BaseModel):
    material: str
    nodes: list[tuple[float, float, float, float]] = Field(min_length=2)
    road_id: str | None = None
    interpolate: bool = True


class ScenarioSpec(BaseModel):
    level: str
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    description: str = "Created by BeamNG MCP"
    vehicles: list[VehicleSpec] = Field(default_factory=list)
    roads: list[RoadSpec] = Field(default_factory=list)


class ControlInput(BaseModel):
    vehicle_id: str
    throttle: float = Field(default=0, ge=0, le=1)
    brake: float = Field(default=0, ge=0, le=1)
    steering: float = Field(default=0, ge=-1, le=1)
    parkingbrake: float = Field(default=0, ge=0, le=1)
    clutch: float = Field(default=0, ge=0, le=1)


class LuaRequest(BaseModel):
    operation: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    arguments: dict[str, Any] = Field(default_factory=dict)


class VisionConfig(BaseModel):
    vehicle_id: str
    model: str | None = None
    device: str | None = None
    mode: Literal["observe", "assist"] = "observe"
    target_speed_kph: float = Field(default=30, ge=0, le=130)

