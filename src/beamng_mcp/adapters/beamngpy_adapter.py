"""Serialized asynchronous facade over BeamNGpy's synchronous socket API."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
from beamngpy import BeamNGpy, Scenario, Vehicle  # type: ignore[import-untyped]
from beamngpy.sensors import (  # type: ignore[import-untyped]
    GPS,
    AdvancedIMU,
    Camera,
    Damage,
    Electrics,
    Lidar,
    PowertrainSensor,
    Radar,
    RoadsSensor,
    State,
    Ultrasonic,
)
from PIL import Image

from ..config import BeamNGSettings
from ..errors import BeamNGMCPError, NotFoundError, SafetyInterlockError, SimulatorConnectionError
from ..models import (
    ConnectionStatus,
    ScenarioInfo,
    ScenarioRef,
    SensorReading,
    SensorSpec,
    VehicleAIConfig,
    VehicleControl,
    VehicleInfo,
    VehicleSpawn,
    VehicleTeleport,
)

T = TypeVar("T")
MAX_ATTACHED_SENSORS = 64


@dataclass(slots=True)
class SensorHandle:
    name: str
    kind: str
    sensor: Any
    vehicle_id: str | None
    legacy: bool = False


class BeamNGpyAdapter:
    """Own one BeamNGpy connection and serialize all socket access on one thread."""

    def __init__(
        self, settings: BeamNGSettings, artifacts: Path, extensions: list[str] | None = None
    ) -> None:
        self.settings = settings
        self.artifacts = artifacts
        self.extensions = list(extensions or [])
        self._bng: BeamNGpy | None = None
        self._vehicles: dict[str, Vehicle] = {}
        self._sensors: dict[str, SensorHandle] = {}
        self._pending_sensors: set[str] = set()
        self._pending_sensor_removals: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="beamngpy")
        self._connected = False
        self._last_error: str | None = None

    async def _call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        loop = asyncio.get_running_loop()
        call = partial(fn, *args, **kwargs)
        try:
            return await loop.run_in_executor(self._executor, call)
        except BeamNGMCPError:
            raise
        except Exception as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            raise SimulatorConnectionError(self._last_error) from exc

    def _require(self) -> BeamNGpy:
        if self._bng is None or not self._connected:
            raise SimulatorConnectionError(
                "BeamNGpy is not connected; call simulator_connect first"
            )
        return self._bng

    async def connect(self, *, launch: bool | None = None) -> ConnectionStatus:
        if self._connected:
            return await self.status()
        should_launch = self.settings.launch if launch is None else launch
        home = str(self.settings.home) if self.settings.home else None
        user = str(self.settings.user) if self.settings.user else None

        def open_connection() -> BeamNGpy:
            bng = BeamNGpy(
                self.settings.host,
                self.settings.port,
                home=home,
                user=user,
                quit_on_close=False,
            )
            return bng.open(
                extensions=self.extensions or None,
                launch=should_launch,
                listen_ip="127.0.0.1",
            )

        self._bng = await self._call(open_connection)
        self._connected = True
        self._last_error = None
        return await self.status()

    async def disconnect(self) -> None:
        if self._bng is None:
            return
        failures: list[str] = []
        for name in list(self._sensors):
            try:
                await self.remove_sensor(name)
            except Exception as exc:
                failures.append(f"sensor {name!r}: {type(exc).__name__}: {exc}")
        bng = self._bng
        disconnected = not self._connected
        if self._connected:
            try:
                await self._call(bng.disconnect)
                disconnected = True
            except Exception as exc:
                failures.append(f"connection: {type(exc).__name__}: {exc}")
        if disconnected:
            self._connected = False
            self._bng = None
            self._vehicles.clear()
            self._sensors.clear()
            self._pending_sensors.clear()
            self._pending_sensor_removals.clear()
        if failures:
            raise SimulatorConnectionError(
                "BeamNGpy disconnect completed with cleanup failures: " + "; ".join(failures)
            )

    async def shutdown(self) -> None:
        try:
            await self.disconnect()
        finally:
            self._executor.shutdown(wait=False, cancel_futures=True)

    async def status(self) -> ConnectionStatus:
        tech_enabled: bool | None = None
        version: str | None = None
        mode: str = "offline"
        if self._connected and self._bng is not None:
            bng = self._bng
            tech_enabled = bool(bng.tech_enabled)
            mode = "tech" if tech_enabled else "drive"
            try:
                info = await self._call(
                    bng.system.get_info, os=True, cpu=False, gpu=False, power=False
                )
                version = str(info.get("version") or info.get("build") or "unknown")
            except SimulatorConnectionError:
                version = None
        return ConnectionStatus(
            connected=self._connected,
            host=self.settings.host,
            port=self.settings.port,
            mode=mode,  # type: ignore[arg-type]
            home=str(self.settings.home) if self.settings.home else None,
            user=str(self.settings.user) if self.settings.user else None,
            version=version,
            tech_enabled=tech_enabled,
            last_error=self._last_error,
        )

    async def pause(self) -> None:
        await self._call(self._require().control.pause)

    async def resume(self) -> None:
        await self._call(self._require().control.resume)

    async def step(self, count: int, *, wait: bool = True) -> None:
        if not 1 <= count <= 100_000:
            raise ValueError("step count must be between 1 and 100000")
        await self._call(self._require().control.step, count, wait=wait)

    async def set_deterministic(self, *, steps_per_second: int = 60, speed_factor: int = 1) -> None:
        if not 20 <= steps_per_second <= 4000:
            raise ValueError("steps_per_second must be between 20 and 4000")
        if not 1 <= speed_factor <= 100:
            raise ValueError("speed_factor must be between 1 and 100")
        await self._call(
            self._require().settings.set_deterministic,
            steps_per_second=steps_per_second,
            speed_factor=speed_factor,
        )

    async def set_nondeterministic(self) -> None:
        await self._call(self._require().settings.set_nondeterministic)

    async def environment_state(self) -> dict[str, Any]:
        bng = self._require()
        gravity = await self._call(bng.env.get_gravity)
        time_of_day = await self._call(bng.env.get_tod)
        return {"gravity": gravity, "time_of_day": time_of_day}

    async def set_environment(
        self,
        *,
        gravity: float | None = None,
        time_of_day: float | str | None = None,
        play: bool | None = None,
        weather_preset: str | None = None,
        transition_seconds: float = 1.0,
    ) -> dict[str, Any]:
        bng = self._require()
        if gravity is not None:
            if not -100.0 <= gravity <= 100.0:
                raise ValueError("gravity must be between -100 and 100 m/s^2")
            await self._call(bng.env.set_gravity, gravity)
        if time_of_day is not None or play is not None:
            if isinstance(time_of_day, float) and not 0.0 <= time_of_day <= 1.0:
                raise ValueError("numeric time_of_day must be between 0 and 1")
            await self._call(bng.env.set_tod, tod=time_of_day, play=play)
        if weather_preset is not None:
            if not 0.0 <= transition_seconds <= 60.0:
                raise ValueError("transition_seconds must be between 0 and 60")
            await self._call(bng.env.set_weather_preset, weather_preset, transition_seconds)
        return await self.environment_state()

    async def traffic_control(
        self,
        action: str,
        *,
        max_amount: int | None = None,
        police_ratio: float = 0.0,
        parked_amount: int | None = None,
        stop_vehicles: bool = True,
    ) -> None:
        bng = self._require()
        if action == "spawn":
            if max_amount is not None and not 0 <= max_amount <= 100:
                raise ValueError("max_amount must be between 0 and 100")
            if parked_amount is not None and not 0 <= parked_amount <= 100:
                raise ValueError("parked_amount must be between 0 and 100")
            if not 0.0 <= police_ratio <= 1.0:
                raise ValueError("police_ratio must be between 0 and 1")
            await self._call(
                bng.traffic.spawn,
                max_amount=max_amount,
                police_ratio=police_ratio,
                parked_amount=parked_amount,
            )
        elif action == "stop":
            await self._call(bng.traffic.stop, stop_vehicles)
        elif action == "reset":
            await self._call(bng.traffic.reset)
        else:
            raise ValueError("traffic action must be spawn, stop, or reset")

    async def list_scenarios(self, level: str | None = None) -> list[ScenarioInfo]:
        bng = self._require()
        levels = [level] if level else None
        raw = await self._call(bng.scenario.get_scenarios, levels)
        result: list[ScenarioInfo] = []
        for level_name, scenarios in raw.items():
            for scenario in scenarios:
                result.append(
                    ScenarioInfo(
                        level=str(getattr(scenario, "level", level_name)),
                        name=str(getattr(scenario, "name", "unknown")),
                        description=getattr(scenario, "description", None),
                        source_file=getattr(scenario, "path", None),
                    )
                )
        return result

    async def _remove_all_sensors(self, *, reason: str) -> None:
        failures: list[str] = []
        for name in list(self._sensors):
            try:
                await self.remove_sensor(name)
            except Exception as exc:
                failures.append(f"{name!r}: {type(exc).__name__}: {exc}")
        if failures:
            raise SimulatorConnectionError(
                f"Cannot {reason} until attached sensors are released: " + "; ".join(failures)
            )

    async def load_scenario(self, ref: ScenarioRef) -> ScenarioInfo:
        bng = self._require()
        scenarios = await self._call(bng.scenario.get_level_scenarios, ref.level)
        match = next((item for item in scenarios if item.name == ref.name), None)
        if match is None:
            raise NotFoundError(f"Scenario {ref.level}/{ref.name} was not found")
        await self._remove_all_sensors(reason="load a scenario")
        try:
            await self._call(bng.scenario.load, match)
        finally:
            # Loading a scenario closes/replaces vehicle sockets. Never retain a
            # handle across that boundary, even when BeamNG reports a load error.
            self._vehicles.clear()
        return ScenarioInfo(
            level=ref.level,
            name=ref.name,
            description=getattr(match, "description", None),
            source_file=getattr(match, "path", None),
        )

    async def create_scenario(
        self,
        ref: ScenarioRef,
        vehicles: list[VehicleSpawn],
        *,
        description: str | None = None,
        load: bool = True,
        overwrite: bool = False,
    ) -> ScenarioInfo:
        bng = self._require()
        if len(vehicles) > 64:
            raise ValueError("A scenario may contain at most 64 requested vehicles")
        vehicle_ids = [spec.vehicle_id for spec in vehicles]
        if len(vehicle_ids) != len(set(vehicle_ids)):
            raise ValueError("Scenario vehicle IDs must be unique")
        if load:
            await self._remove_all_sensors(reason="load the created scenario")

        def make() -> Scenario:
            existing = bng.scenario.get_level_scenarios(ref.level)
            if any(candidate.name == ref.name for candidate in existing) and not overwrite:
                raise SafetyInterlockError(
                    f"Scenario {ref.level}/{ref.name} already exists; "
                    "an explicit confirmed overwrite is required"
                )
            scenario = Scenario(ref.level, ref.name, description=description)
            for spec in vehicles:
                vehicle = Vehicle(
                    spec.vehicle_id,
                    spec.model,
                    license=spec.license_plate,
                    color=spec.color,
                    part_config=spec.configuration,
                )
                scenario.add_vehicle(
                    vehicle,
                    pos=spec.position,
                    rot_quat=spec.rotation,
                    cling=spec.cling,
                )
            scenario.make(bng)
            if load:
                bng.scenario.load(scenario)
            return scenario

        try:
            scenario = await self._call(make)
        finally:
            if load:
                # Scenario.load() owns connecting its Vehicle instances. Resolve
                # those connected instances lazily rather than caching the
                # pre-load objects constructed above.
                self._vehicles.clear()
        return ScenarioInfo(
            level=ref.level,
            name=ref.name,
            description=description,
            source_file=getattr(scenario, "path", None),
        )

    async def scenario_start(self) -> None:
        await self._call(self._require().scenario.start)

    async def scenario_restart(self) -> None:
        await self._remove_all_sensors(reason="restart the scenario")
        try:
            await self._call(self._require().scenario.restart)
        finally:
            self._vehicles.clear()

    async def scenario_stop(self) -> None:
        await self._remove_all_sensors(reason="stop the scenario")
        try:
            await self._call(self._require().scenario.stop)
        finally:
            self._vehicles.clear()

    async def _vehicle(self, vehicle_id: str) -> Vehicle:
        bng = self._require()
        cached = self._vehicles.get(vehicle_id)
        if cached is not None:
            if await self._call(cached.is_connected):
                return cached
            self._vehicles.pop(vehicle_id, None)

        vehicle = await self._call(bng.scenario.get_vehicle, vehicle_id)
        if vehicle is None:
            current = await self._call(bng.vehicles.get_current)
            vehicle = current.get(vehicle_id)
        if vehicle is None:
            raise NotFoundError(f"Vehicle {vehicle_id!r} was not found in the current scenario")
        if not await self._call(vehicle.is_connected):
            await self._call(vehicle.connect, bng)
        self._vehicles[vehicle_id] = vehicle
        return vehicle

    async def list_vehicles(self) -> list[VehicleInfo]:
        bng = self._require()
        info = await self._call(bng.vehicles.get_current_info, True)
        states = await self._call(bng.vehicles.get_states, list(info)) if info else {}
        result: list[VehicleInfo] = []
        for vehicle_id, vehicle_data in info.items():
            state = states.get(vehicle_id, {})
            result.append(self._vehicle_info(vehicle_id, vehicle_data, state))
        return result

    @staticmethod
    def _vehicle_info(
        vehicle_id: str, vehicle_data: dict[str, Any], state: dict[str, Any]
    ) -> VehicleInfo:
        velocity = state.get("vel")
        speed = None
        if velocity is not None:
            speed = math.sqrt(sum(float(value) ** 2 for value in velocity))
        return VehicleInfo(
            vehicle_id=vehicle_id,
            model=vehicle_data.get("model") or vehicle_data.get("jbeam"),
            position=state.get("pos"),
            direction=state.get("dir"),
            velocity=velocity,
            speed_mps=speed,
            connected=vehicle_data.get("connected"),
            raw={
                key: value
                for key, value in vehicle_data.items()
                if isinstance(value, (str, int, float, bool))
            },
        )

    async def vehicle_state(self, vehicle_id: str) -> VehicleInfo:
        bng = self._require()
        vehicles = await self._call(bng.vehicles.get_current_info, True)
        if vehicle_id not in vehicles:
            raise NotFoundError(f"Vehicle {vehicle_id!r} was not found")
        states = await self._call(bng.vehicles.get_states, [vehicle_id])
        return self._vehicle_info(vehicle_id, vehicles[vehicle_id], states.get(vehicle_id, {}))

    async def spawn_vehicle(self, spec: VehicleSpawn) -> VehicleInfo:
        bng = self._require()
        vehicle = Vehicle(
            spec.vehicle_id,
            spec.model,
            license=spec.license_plate,
            color=spec.color,
            part_config=spec.configuration,
        )
        spawned = await self._call(
            bng.vehicles.spawn,
            vehicle,
            spec.position,
            spec.rotation,
            spec.cling,
            True,
        )
        if not spawned:
            raise SimulatorConnectionError(f"BeamNG rejected vehicle spawn for {spec.vehicle_id}")
        self._vehicles[spec.vehicle_id] = vehicle
        return await self.vehicle_state(spec.vehicle_id)

    async def remove_vehicle(self, vehicle_id: str) -> None:
        bng = self._require()
        failures: list[str] = []
        for name, handle in list(self._sensors.items()):
            if handle.vehicle_id != vehicle_id:
                continue
            try:
                await self.remove_sensor(name)
            except Exception as exc:
                failures.append(f"{name!r}: {type(exc).__name__}: {exc}")
        if failures:
            raise SimulatorConnectionError(
                f"Cannot remove vehicle {vehicle_id!r} until its sensors are released: "
                + "; ".join(failures)
            )
        vehicle = await self._vehicle(vehicle_id)
        await self._call(bng.vehicles.despawn, vehicle)
        self._vehicles.pop(vehicle_id, None)

    async def control_vehicle(self, command: VehicleControl) -> None:
        vehicle = await self._vehicle(command.vehicle_id)
        throttle = 0.0 if command.brake > 0.05 else command.throttle
        await self._call(
            vehicle.control,
            steering=command.steering,
            throttle=throttle,
            brake=command.brake,
            parkingbrake=command.parking_brake,
            clutch=command.clutch,
            gear=command.gear,
            is_adas=True,
        )

    async def teleport_vehicle(self, command: VehicleTeleport) -> bool:
        bng = self._require()
        vehicle = await self._vehicle(command.vehicle_id)
        return await self._call(
            bng.vehicles.teleport,
            vehicle,
            command.position,
            command.rotation,
            command.reset,
        )

    async def configure_ai(self, config: VehicleAIConfig) -> None:
        vehicle = await self._vehicle(config.vehicle_id)

        def apply() -> None:
            vehicle.ai.set_mode(config.mode)
            if config.speed_mps is not None:
                vehicle.ai.set_speed(config.speed_mps, mode=config.speed_mode)
            if config.aggression is not None:
                vehicle.ai.set_aggression(config.aggression)
            if config.lane is not None:
                vehicle.ai.drive_in_lane(config.lane)
            if config.target_vehicle_id is not None:
                vehicle.ai.set_target(config.target_vehicle_id, mode=config.mode)
            if config.target_waypoint is not None:
                vehicle.ai.set_waypoint(config.target_waypoint)

        await self._call(apply)

    async def attach_sensor(self, spec: SensorSpec) -> None:
        if spec.name in self._sensors or spec.name in self._pending_sensors:
            raise ValueError(f"Sensor {spec.name!r} is already attached")
        if len(self._sensors) + len(self._pending_sensors) >= MAX_ATTACHED_SENSORS:
            raise ValueError(f"At most {MAX_ATTACHED_SENSORS} sensors may be attached")

        self._pending_sensors.add(spec.name)
        try:
            bng = self._require()
            vehicle = await self._vehicle(spec.vehicle_id) if spec.vehicle_id else None

            def create() -> SensorHandle:
                common = {
                    "name": spec.name,
                    "bng": bng,
                    "vehicle": vehicle,
                    "requested_update_time": spec.update_time,
                    "pos": spec.position,
                    "dir": spec.direction,
                }
                sensor: Any
                legacy = False
                if spec.sensor_type == "camera":
                    sensor = Camera(
                        **common,
                        resolution=spec.resolution,
                        field_of_view_y=spec.field_of_view_y,
                        is_using_shared_memory=spec.shared_memory,
                        is_streaming=spec.streaming,
                        is_render_annotations=spec.render_annotations,
                        is_render_depth=spec.render_depth,
                        is_visualised=False,
                    )
                elif spec.sensor_type == "lidar":
                    sensor = Lidar(
                        **common,
                        is_using_shared_memory=spec.shared_memory,
                        is_streaming=spec.streaming,
                        is_visualised=False,
                    )
                elif spec.sensor_type == "radar":
                    sensor = Radar(**common, is_streaming=spec.streaming, is_visualised=False)
                elif spec.sensor_type == "ultrasonic":
                    sensor = Ultrasonic(**common, is_streaming=spec.streaming, is_visualised=False)
                elif spec.sensor_type in {"gps", "advanced_imu", "roads", "powertrain"}:
                    if vehicle is None:
                        raise ValueError(f"{spec.sensor_type} requires vehicle_id")
                    timed = {
                        "name": spec.name,
                        "bng": bng,
                        "vehicle": vehicle,
                        "gfx_update_time": spec.update_time,
                        "physics_update_time": min(spec.update_time, 0.01),
                        "is_visualised": False,
                    }
                    if spec.sensor_type == "gps":
                        sensor = GPS(**timed, pos=spec.position)
                    elif spec.sensor_type == "advanced_imu":
                        sensor = AdvancedIMU(**timed, pos=spec.position, dir=spec.direction)
                    elif spec.sensor_type == "roads":
                        sensor = RoadsSensor(**timed)
                    else:
                        timed.pop("is_visualised")
                        sensor = PowertrainSensor(**timed)
                else:
                    if vehicle is None:
                        raise ValueError(f"{spec.sensor_type} requires vehicle_id")
                    sensor = {"electrics": Electrics, "damage": Damage, "state": State}[
                        spec.sensor_type
                    ]()
                    vehicle.sensors.attach(spec.name, sensor)
                    legacy = True
                return SensorHandle(spec.name, spec.sensor_type, sensor, spec.vehicle_id, legacy)

            self._sensors[spec.name] = await self._call(create)
        finally:
            self._pending_sensors.discard(spec.name)

    async def poll_sensor(self, name: str) -> SensorReading:
        handle = self._sensors.get(name)
        if handle is None:
            raise NotFoundError(f"Sensor {name!r} is not attached")

        def poll() -> Any:
            if handle.legacy:
                assert handle.vehicle_id is not None
                vehicle = self._vehicles[handle.vehicle_id]
                vehicle.sensors.poll(name)
                return dict(vehicle.sensors.data[name])
            if handle.kind == "camera" and getattr(handle.sensor, "is_streaming", False):
                return handle.sensor.stream()
            return handle.sensor.poll()

        raw = await self._call(poll)
        data, artifacts = self._serialize_reading(name, raw)
        return SensorReading(
            name=name, sensor_type=handle.kind, data=data, artifact_paths=artifacts
        )

    async def camera_frame(self, name: str) -> np.ndarray:
        handle = self._sensors.get(name)
        if handle is None or handle.kind != "camera":
            raise NotFoundError(f"Camera sensor {name!r} is not attached")

        def read() -> Any:
            if getattr(handle.sensor, "is_streaming", False):
                return handle.sensor.stream()
            return handle.sensor.poll()

        reading = await self._call(read)
        colour = reading.get("colour")
        if colour is None:
            raise SimulatorConnectionError(f"Camera {name!r} returned no colour frame")
        return np.asarray(colour.convert("RGB"), dtype=np.uint8)

    def _serialize_reading(self, name: str, raw: Any) -> tuple[dict[str, Any], list[str]]:
        self.artifacts.mkdir(parents=True, exist_ok=True)
        artifacts: list[str] = []

        def convert(value: Any, key: str) -> Any:
            if isinstance(value, Image.Image):
                path = self.artifacts / f"{name}-{key}.png"
                value.save(path)
                artifacts.append(str(path))
                return {
                    "type": "image",
                    "path": str(path),
                    "size": list(value.size),
                    "mode": value.mode,
                }
            if isinstance(value, np.ndarray):
                if value.size <= 4096:
                    return value.tolist()
                path = self.artifacts / f"{name}-{key}.npy"
                np.save(path, value, allow_pickle=False)
                artifacts.append(str(path))
                return {
                    "type": "ndarray",
                    "path": str(path),
                    "shape": list(value.shape),
                    "dtype": str(value.dtype),
                }
            if isinstance(value, np.generic):
                return value.item()
            if isinstance(value, dict):
                return {str(k): convert(v, f"{key}-{k}") for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [convert(v, f"{key}-{index}") for index, v in enumerate(value)]
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            return str(value)

        converted = convert(raw, "reading")
        if isinstance(converted, dict):
            return converted, artifacts
        return {"result": converted}, artifacts

    async def remove_sensor(self, name: str) -> None:
        handle = self._sensors.get(name)
        if handle is None:
            return
        if name in self._pending_sensor_removals:
            raise ValueError(f"Sensor {name!r} removal is already in progress")
        self._pending_sensor_removals.add(name)

        def remove() -> None:
            if handle.legacy:
                if handle.vehicle_id and handle.vehicle_id in self._vehicles:
                    self._vehicles[handle.vehicle_id].sensors.detach(name)
            else:
                handle.sensor.remove()

        try:
            await self._call(remove)
        except Exception:
            # Keep ownership so an operator or shutdown can retry cleanup.
            raise
        else:
            if self._sensors.get(name) is handle:
                self._sensors.pop(name, None)
        finally:
            self._pending_sensor_removals.discard(name)

    async def road_network(
        self, *, include_edges: bool = True, drivable_only: bool = True
    ) -> dict[str, Any]:
        return await self._call(
            self._require().scenario.get_road_network,
            include_edges=include_edges,
            drivable_only=drivable_only,
        )

    async def road_edges(self, road_id: str) -> list[dict[str, Any]]:
        return await self._call(self._require().scenario.get_road_edges, road_id)

    async def find_objects(self, class_name: str) -> list[dict[str, Any]]:
        objects = await self._call(self._require().scenario.find_objects_class, class_name)
        result: list[dict[str, Any]] = []
        for obj in objects:
            result.append(
                {
                    "id": getattr(obj, "id", None),
                    "name": getattr(obj, "name", None),
                    "type": getattr(obj, "type", class_name),
                    "position": getattr(obj, "pos", None),
                    "rotation": getattr(obj, "rot_quat", None),
                    "scale": getattr(obj, "scale", None),
                }
            )
        return result

    async def emergency_stop(self, vehicle_id: str | None = None) -> None:
        bng = self._require()
        if vehicle_id:
            vehicle_ids = [vehicle_id]
        else:
            vehicle_ids = list((await self._call(bng.vehicles.get_current_info, False)).keys())
        for current_id in vehicle_ids:
            vehicle = await self._vehicle(current_id)
            await self._call(
                vehicle.control,
                throttle=0.0,
                brake=1.0,
                parkingbrake=1.0,
                steering=0.0,
                is_adas=True,
            )
