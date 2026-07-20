import asyncio
from pathlib import Path
from typing import Any

from .config import Settings
from .models import ControlInput, ScenarioSpec


class BeamNGController:
    """Async facade over BeamNGpy's synchronous API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bng: Any = None
        self.vehicles: dict[str, Any] = {}
        self.cameras: dict[str, Any] = {}
        self.scenario: Any = None

    @property
    def connected(self) -> bool:
        return self.bng is not None

    async def connect(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._connect)

    def _connect(self) -> dict[str, Any]:
        from beamngpy import BeamNGpy

        kwargs: dict[str, Any] = {}
        if self.settings.home:
            kwargs["home"] = str(self.settings.home)
        if self.settings.user_path:
            kwargs["user"] = str(self.settings.user_path)
        self.bng = BeamNGpy(self.settings.host, self.settings.port, **kwargs)
        self.bng.open(launch=self.settings.launch)
        return {"connected": True, "host": self.settings.host, "port": self.settings.port}

    async def disconnect(self) -> None:
        if self.bng:
            await asyncio.to_thread(self.bng.close)
            self.bng = None
            self.vehicles.clear()
            self.cameras.clear()

    def require_connection(self) -> None:
        if not self.bng:
            raise RuntimeError("Not connected to BeamNG; call connect first")

    async def create_scenario(self, spec: ScenarioSpec) -> dict[str, Any]:
        self.require_connection()
        return await asyncio.to_thread(self._create_scenario, spec)

    def _create_scenario(self, spec: ScenarioSpec) -> dict[str, Any]:
        from beamngpy import Road, Scenario, Vehicle

        scenario = Scenario(spec.level, spec.name, description=spec.description)
        for item in spec.vehicles:
            vehicle = Vehicle(item.vehicle_id, model=item.model, part_config=item.config)
            scenario.add_vehicle(vehicle, pos=item.pose.pos, rot_quat=item.pose.rot_quat)
            self.vehicles[item.vehicle_id] = vehicle
        for item in spec.roads:
            road = Road(item.material, rid=item.road_id, interpolate=item.interpolate)
            road.add_nodes(*item.nodes)
            scenario.add_road(road)
        scenario.make(self.bng)
        self.scenario = scenario
        return {"created": spec.name, "level": spec.level, "vehicles": list(self.vehicles)}

    async def load_scenario(self, start: bool = True) -> dict[str, Any]:
        self.require_connection()
        if not self.scenario:
            raise RuntimeError("No scenario has been created")
        await asyncio.to_thread(self.bng.scenario.load, self.scenario)
        if start:
            await asyncio.to_thread(self.bng.scenario.start)
        return {"loaded": True, "started": start}

    async def state(self, vehicle_id: str) -> dict[str, Any]:
        vehicle = self._vehicle(vehicle_id)
        await asyncio.to_thread(vehicle.sensors.poll)
        return dict(vehicle.state)

    async def control(self, command: ControlInput) -> dict[str, Any]:
        vehicle = self._vehicle(command.vehicle_id)
        values = command.model_dump(exclude={"vehicle_id"})
        await asyncio.to_thread(vehicle.control, **values)
        return {"applied": values, "vehicle_id": command.vehicle_id}

    async def stop(self, vehicle_id: str) -> None:
        vehicle = self._vehicle(vehicle_id)
        await asyncio.to_thread(vehicle.control, throttle=0, brake=1, steering=0, parkingbrake=1)

    async def ai_mode(self, vehicle_id: str, mode: str) -> dict[str, Any]:
        vehicle = self._vehicle(vehicle_id)
        await asyncio.to_thread(vehicle.ai.set_mode, mode)
        return {"vehicle_id": vehicle_id, "ai_mode": mode}

    async def map_data(self) -> dict[str, Any]:
        self.require_connection()
        roads, edges = await asyncio.gather(
            asyncio.to_thread(self.bng.scenario.get_roads),
            asyncio.to_thread(self.bng.scenario.get_road_edges),
        )
        return {"roads": roads, "edges": edges}

    async def camera_attach(
        self,
        vehicle_id: str,
        name: str,
        resolution: tuple[int, int] = (640, 384),
        update_seconds: float = 0.1,
    ) -> dict[str, Any]:
        self.require_connection()
        vehicle = self._vehicle(vehicle_id)
        return await asyncio.to_thread(
            self._camera_attach, vehicle, name, resolution, update_seconds
        )

    def _camera_attach(
        self,
        vehicle: Any,
        name: str,
        resolution: tuple[int, int],
        update_seconds: float,
    ) -> dict[str, Any]:
        from beamngpy.sensors import Camera

        if name in self.cameras:
            raise ValueError(f"Camera already exists: {name}")
        camera = Camera(
            name,
            self.bng,
            vehicle=vehicle,
            requested_update_time=update_seconds,
            pos=(0.0, -0.2, 1.4),
            dir=(0.0, -1.0, 0.0),
            resolution=resolution,
            is_using_shared_memory=True,
            is_render_colours=True,
            is_render_annotations=False,
            is_render_depth=True,
        )
        self.cameras[name] = camera
        return {"camera": name, "resolution": resolution, "shared_memory": True}

    async def camera_frame(self, name: str) -> Any:
        if name not in self.cameras:
            raise KeyError(f"Unknown camera: {name}")
        reading = await asyncio.to_thread(self.cameras[name].poll)
        if "colour" not in reading:
            raise RuntimeError(f"Camera {name} returned no colour frame")
        return reading["colour"]

    async def export_scenario(self, spec: ScenarioSpec, target: Path) -> dict[str, Any]:
        return await asyncio.to_thread(self._export_scenario, spec, target)

    def _export_scenario(self, spec: ScenarioSpec, target: Path) -> dict[str, Any]:
        target = target.resolve()
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{spec.name}.json"
        path.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
        return {"path": str(path), "bytes": path.stat().st_size}

    def _vehicle(self, vehicle_id: str) -> Any:
        self.require_connection()
        if vehicle_id not in self.vehicles:
            raise KeyError(f"Unknown vehicle: {vehicle_id}")
        return self.vehicles[vehicle_id]
