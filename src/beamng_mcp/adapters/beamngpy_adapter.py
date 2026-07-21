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
from beamngpy.misc.colors import coerce_color  # type: ignore[import-untyped]
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
from ..errors import (
    BeamNGMCPError,
    ConflictError,
    NotFoundError,
    SafetyInterlockError,
    SimulatorConnectionError,
)
from ..models import (
    ConnectionStatus,
    ScenarioInfo,
    ScenarioRef,
    ScenarioSelector,
    ScenarioVehiclePlacement,
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
        self._lifecycle_lock = asyncio.Lock()
        self._closed = False
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

    @staticmethod
    async def _join_task_resiliently(task: asyncio.Task[T]) -> tuple[T, bool]:
        """Join a lifecycle task without allowing caller cancellation to detach it."""

        cancellation_requested = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancellation_requested = True
        return task.result(), cancellation_requested

    @staticmethod
    async def _settle_task_resiliently(
        task: asyncio.Task[T],
    ) -> tuple[T | None, BaseException | None, bool]:
        """Join a task and capture its outcome without detaching it on cancellation."""

        cancellation_requested = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancellation_requested = True
            except BaseException:
                # Read the completed task's exception below so callers can
                # perform compensation before deciding which error to raise.
                break
        try:
            return task.result(), None, cancellation_requested
        except BaseException as exc:
            return None, exc, cancellation_requested

    def _require(self) -> BeamNGpy:
        if self._bng is None or not self._connected:
            raise SimulatorConnectionError(
                "BeamNGpy is not connected; call simulator_connect first"
            )
        return self._bng

    @staticmethod
    def _close_failed_connection(bng: BeamNGpy) -> None:
        """Dispose of a connection that never became usable, or report why not."""

        owns_process = getattr(bng, "process", None) is not None
        if not owns_process:
            try:
                bng.disconnect()
            except Exception as exc:
                raise RuntimeError(
                    f"failed to disconnect provisional BeamNGpy session: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            return

        # Normal adapter disconnects deliberately leave BeamNG running. A
        # process launched by this failed attempt has no owner, however, so
        # exhaust BeamNGpy and raw-process termination paths before returning.
        failures: list[str] = []

        def clear_exited_process() -> bool:
            process = getattr(bng, "process", None)
            if process is None:
                return True
            poll = getattr(process, "poll", None)
            if not callable(poll):
                return False
            try:
                return_code = poll()
            except Exception as exc:
                failures.append(f"raw process poll: {type(exc).__name__}: {exc}")
                return False
            if return_code is None:
                return False
            bng.process = None
            return True

        bng.quit_on_close = True
        try:
            bng.close()
        except Exception as exc:
            failures.append(f"close: {type(exc).__name__}: {exc}")

        clear_exited_process()
        if getattr(bng, "process", None) is not None:
            kill_process = getattr(bng, "_kill_beamng", None)
            if callable(kill_process):
                try:
                    kill_process()
                except Exception as exc:
                    failures.append(f"BeamNGpy kill: {type(exc).__name__}: {exc}")

        clear_exited_process()
        process = getattr(bng, "process", None)
        if process is not None:
            raw_kill = getattr(process, "kill", None)
            if not callable(raw_kill):
                failures.append("raw process handle exposes no kill() method")
            else:
                try:
                    raw_kill()
                    wait = getattr(process, "wait", None)
                    if callable(wait):
                        wait(timeout=5.0)
                    bng.process = None
                except Exception as exc:
                    failures.append(f"raw process kill: {type(exc).__name__}: {exc}")
                    clear_exited_process()

        if getattr(bng, "process", None) is not None:
            detail = "; ".join(failures) or "process remained live after cleanup"
            raise RuntimeError(detail)

    def _retain_provisional_connection(self, bng: BeamNGpy) -> None:
        """Keep an unclosed provisional handle available for a shutdown retry."""

        self._connected = False
        self._bng = bng
        self._vehicles.clear()
        self._sensors.clear()
        self._pending_sensors.clear()
        self._pending_sensor_removals.clear()

    def _forget_connection(self) -> None:
        self._connected = False
        self._bng = None
        self._vehicles.clear()
        self._sensors.clear()
        self._pending_sensors.clear()
        self._pending_sensor_removals.clear()

    async def connect(self, *, launch: bool | None = None) -> ConnectionStatus:
        async with self._lifecycle_lock:
            if self._closed:
                raise SimulatorConnectionError("BeamNGpy adapter has been shut down")
            return await self._connect_unlocked(launch=launch)

    async def _connect_unlocked(self, *, launch: bool | None = None) -> ConnectionStatus:
        if self._connected:
            return await self._status_unlocked()
        if self._bng is not None:
            raise SimulatorConnectionError(
                "A failed provisional BeamNGpy session is still owned by the adapter; "
                "call simulator_disconnect or shut down the server to retry cleanup"
            )
        should_launch = self.settings.launch if launch is None else launch
        home = str(self.settings.home) if self.settings.home else None
        binary = str(self.settings.binary) if self.settings.binary else None
        user_path = self.settings.user
        # BeamNG's ``-userpath`` expects the root and appends ``current`` for
        # modern releases, while the rest of this project stores the resolved
        # active folder so mod installation and token discovery are exact.
        if should_launch and user_path is not None and user_path.name.casefold() == "current":
            user_path = user_path.parent
        user = str(user_path) if user_path else None

        provisional: BeamNGpy | None = None

        def open_connection() -> BeamNGpy:
            nonlocal provisional
            provisional = BeamNGpy(
                self.settings.host,
                self.settings.port,
                home=home,
                binary=binary,
                user=user,
                quit_on_close=False,
            )
            return provisional.open(
                extensions=self.extensions or None,
                launch=should_launch,
                listen_ip="127.0.0.1",
            )

        opening = asyncio.create_task(self._call(open_connection))
        try:
            self._bng = await asyncio.shield(opening)
        except asyncio.CancelledError:
            # Cancelling run_in_executor does not stop its worker. Wait for the
            # bounded BeamNGpy open attempt to return, then dispose of any
            # process it launched before propagating cancellation.
            candidate = provisional
            try:
                opened, _ = await self._join_task_resiliently(opening)
            except Exception as exc:
                self._last_error = self._last_error or f"{type(exc).__name__}: {exc}"
                candidate = provisional
            else:
                candidate = opened
            if candidate is not None:
                cleanup = asyncio.create_task(self._call(self._close_failed_connection, candidate))
                try:
                    await self._join_task_resiliently(cleanup)
                except Exception as exc:
                    self._last_error = self._last_error or (
                        f"provisional connection cleanup failed: {type(exc).__name__}: {exc}"
                    )
                    self._retain_provisional_connection(candidate)
                else:
                    self._forget_connection()
            else:
                self._forget_connection()
            raise
        except Exception as exc:
            original_error = self._last_error or f"{type(exc).__name__}: {exc}"
            cleanup_error: str | None = None
            cleanup_cancelled = False
            if provisional is not None:
                cleanup = asyncio.create_task(
                    self._call(self._close_failed_connection, provisional)
                )
                try:
                    _, cleanup_cancelled = await self._join_task_resiliently(cleanup)
                except Exception as cleanup_exc:
                    cleanup_error = f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                    self._retain_provisional_connection(provisional)
                else:
                    self._forget_connection()
            if cleanup_error is not None:
                original_error += f"; provisional connection cleanup failed: {cleanup_error}"
            self._last_error = original_error
            if cleanup_cancelled:
                raise asyncio.CancelledError from exc
            if cleanup_error is not None:
                raise SimulatorConnectionError(original_error) from exc
            raise
        self._connected = True
        self._last_error = None
        try:
            return await self._status_unlocked()
        except BaseException as exc:
            last_error = self._last_error or f"{type(exc).__name__}: {exc}"
            bng = self._bng
            cleanup_cancelled = False
            if bng is not None:
                cleanup = asyncio.create_task(self._call(self._close_failed_connection, bng))
                try:
                    _, cleanup_cancelled = await self._join_task_resiliently(cleanup)
                except Exception as cleanup_exc:
                    last_error += (
                        "; provisional connection cleanup failed: "
                        f"{type(cleanup_exc).__name__}: {cleanup_exc}"
                    )
                    self._retain_provisional_connection(bng)
                else:
                    self._forget_connection()
            else:
                self._forget_connection()
            self._last_error = last_error
            if cleanup_cancelled and not isinstance(exc, asyncio.CancelledError):
                raise asyncio.CancelledError from exc
            if "provisional connection cleanup failed:" in last_error:
                raise SimulatorConnectionError(last_error) from exc
            raise

    async def disconnect(self) -> None:
        async with self._lifecycle_lock:
            if self._closed:
                return
            operation = asyncio.create_task(self._disconnect_unlocked())
            _, cancellation_requested = await self._join_task_resiliently(operation)
            if cancellation_requested:
                raise asyncio.CancelledError

    async def _disconnect_unlocked(self) -> None:
        if self._bng is None:
            return
        if not self._connected:
            bng = self._bng
            try:
                await self._call(self._close_failed_connection, bng)
            except Exception as exc:
                raise SimulatorConnectionError(
                    "Failed to dispose retained provisional BeamNGpy session: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            self._forget_connection()
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
            self._forget_connection()
        if failures:
            raise SimulatorConnectionError(
                "BeamNGpy disconnect completed with cleanup failures: " + "; ".join(failures)
            )

    async def shutdown(self) -> None:
        async def finish_shutdown() -> None:
            async with self._lifecycle_lock:
                if self._closed:
                    return
                try:
                    await self._disconnect_unlocked()
                except Exception:
                    if self._bng is None:
                        self._closed = True
                        self._executor.shutdown(wait=False, cancel_futures=True)
                    raise
                else:
                    self._closed = True
                    self._executor.shutdown(wait=False, cancel_futures=True)

        operation = asyncio.create_task(finish_shutdown())
        _, cancellation_requested = await self._join_task_resiliently(operation)
        if cancellation_requested:
            raise asyncio.CancelledError

    async def status(self) -> ConnectionStatus:
        async with self._lifecycle_lock:
            return await self._status_unlocked()

    async def _status_unlocked(self) -> ConnectionStatus:
        tech_enabled: bool | None = None
        version: str | None = None
        mode: str = "offline"
        if self._connected and self._bng is not None:
            bng = self._bng
            capability = await self._call(bng.tech_enabled)
            if capability is None:
                tech_enabled = None
                mode = "unknown"
            elif isinstance(capability, bool):
                tech_enabled = capability
                mode = "tech" if capability else "drive"
            else:
                raise SimulatorConnectionError(
                    "BeamNGpy tech_enabled() returned an invalid capability value"
                )
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
                description = getattr(scenario, "description", None)
                source_file = getattr(scenario, "path", None)
                result.append(
                    ScenarioInfo(
                        level=str(getattr(scenario, "level", level_name)),
                        name=str(getattr(scenario, "name", "unknown")),
                        description=None if description is None else str(description),
                        source_file=None if source_file is None else str(source_file),
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

    async def load_scenario(self, ref: ScenarioSelector) -> ScenarioInfo:
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
        vehicles: list[ScenarioVehiclePlacement],
        *,
        description: str | None = None,
        load: bool = True,
        overwrite: bool = False,
    ) -> ScenarioInfo:
        bng = self._require()
        if len(vehicles) > 64:
            raise ValueError("A scenario may contain at most 64 requested vehicles")
        if any(not isinstance(spec, ScenarioVehiclePlacement) for spec in vehicles):
            raise ValueError(
                "Scenario vehicles require ScenarioVehiclePlacement with an explicit "
                "surface position and cling=false"
            )
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

    @staticmethod
    def _scenario_vehicle_bookkeeping(
        bng: Any,
    ) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
        scenario = getattr(bng, "_scenario", None)
        if scenario is None:
            raise SimulatorConnectionError(
                "Loaded BeamNGpy scenario cannot track a transient vehicle"
            )
        records: list[dict[str, Any]] = []
        for attribute in ("vehicles", "transient_vehicles", "_vehicle_locations"):
            value = getattr(scenario, attribute, None)
            if not isinstance(value, dict):
                raise SimulatorConnectionError(
                    "Loaded BeamNGpy scenario cannot track a transient vehicle"
                )
            records.append(value)
        return scenario, records[0], records[1], records[2]

    async def scenario_start(self) -> None:
        await self._call(self._require().scenario.start)

    async def scenario_restart(self) -> None:
        bng = self._require()
        _, scenario_vehicles, transient_vehicles, vehicle_locations = await self._call(
            self._scenario_vehicle_bookkeeping, bng
        )
        original_transient_vehicles = dict(transient_vehicles)

        def reconcile_transient_locations() -> None:
            for vehicle_id in original_transient_vehicles:
                if vehicle_id not in scenario_vehicles and vehicle_id not in transient_vehicles:
                    vehicle_locations.pop(vehicle_id, None)

        await self._remove_all_sensors(reason="restart the scenario")
        restarting = asyncio.create_task(self._call(bng.scenario.restart))
        _, restart_error, restart_cancelled = await self._settle_task_resiliently(restarting)
        reconciling = asyncio.create_task(self._call(reconcile_transient_locations))
        _, reconciliation_error, reconciliation_cancelled = await self._settle_task_resiliently(
            reconciling
        )
        self._vehicles.clear()
        if restart_cancelled or reconciliation_cancelled:
            raise asyncio.CancelledError from restart_error
        if reconciliation_error is not None:
            raise reconciliation_error
        if restart_error is not None:
            raise restart_error

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
        states = await self._vehicle_states(list(info))
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

    async def _vehicle_states(self, vehicle_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Use the batch Tech API, falling back to each vehicle's built-in State sensor."""

        if not vehicle_ids:
            return {}
        bng = self._require()
        try:
            return await self._call(bng.vehicles.get_states, vehicle_ids)
        except SimulatorConnectionError as batch_error:
            states: dict[str, dict[str, Any]] = {}
            try:
                for vehicle_id in vehicle_ids:
                    vehicle = await self._vehicle(vehicle_id)
                    await self._call(vehicle.sensors.poll, "state")
                    state = vehicle.sensors.data.get("state", {})
                    states[vehicle_id] = dict(state) if isinstance(state, dict) else {}
            except Exception as fallback_error:
                raise batch_error from fallback_error
            self._last_error = None
            return states

    async def vehicle_state(self, vehicle_id: str) -> VehicleInfo:
        bng = self._require()
        vehicles = await self._call(bng.vehicles.get_current_info, True)
        if vehicle_id not in vehicles:
            raise NotFoundError(f"Vehicle {vehicle_id!r} was not found")
        states = await self._vehicle_states([vehicle_id])
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
        bookkeeping: tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]] | None = None
        spawn_attempted = False

        def spawn_and_register() -> bool:
            nonlocal bookkeeping, spawn_attempted
            bookkeeping = self._scenario_vehicle_bookkeeping(bng)
            _, scenario_vehicles, transient_vehicles, vehicle_locations = bookkeeping
            if (
                spec.vehicle_id in self._vehicles
                or spec.vehicle_id in scenario_vehicles
                or spec.vehicle_id in transient_vehicles
            ):
                raise ConflictError(
                    f"Vehicle {spec.vehicle_id!r} already exists; remove it explicitly "
                    "or choose another vehicle_id"
                )
            current_vehicles = bng.vehicles.get_current_info(False)
            if spec.vehicle_id in current_vehicles:
                raise ConflictError(
                    f"Vehicle {spec.vehicle_id!r} already exists; remove it explicitly "
                    "or choose another vehicle_id"
                )
            if spec.color is not None:
                # BeamNGpy otherwise validates colors inside spawn(), before it
                # sends SpawnVehicle. Keep local validation outside the range
                # that requires compensating for an uncertain remote mutation.
                coerce_color(spec.color)
            spawn_attempted = True
            spawned = bng.vehicles.spawn(
                vehicle,
                spec.position,
                spec.rotation,
                spec.cling,
                True,
            )
            if spawned:
                scenario_vehicles[spec.vehicle_id] = vehicle
                transient_vehicles[spec.vehicle_id] = vehicle
                vehicle_locations[spec.vehicle_id] = (
                    spec.position,
                    spec.rotation,
                )
            return bool(spawned)

        def rollback_spawn() -> tuple[bool, list[str]]:
            failures: list[str] = []
            if bookkeeping is None:
                return False, ["scenario bookkeeping was not captured before spawning"]
            _, scenario_vehicles, transient_vehicles, vehicle_locations = bookkeeping
            try:
                bng.vehicles.despawn(vehicle)
            except Exception as exc:
                despawned = False
                failures.append(f"despawn: {type(exc).__name__}: {exc}")
            else:
                despawned = True

            tracked_vehicle_maps = (
                ("vehicles", scenario_vehicles),
                ("transient_vehicles", transient_vehicles),
            )
            replacement_present = False
            if despawned:
                for label, records in tracked_vehicle_maps:
                    tracked = records.get(spec.vehicle_id)
                    if tracked is vehicle:
                        records.pop(spec.vehicle_id, None)
                    elif tracked is not None:
                        replacement_present = True
                        failures.append(f"scenario.{label} contains a replacement vehicle")
                if not replacement_present:
                    expected_location = (spec.position, spec.rotation)
                    location = vehicle_locations.get(spec.vehicle_id)
                    if location == expected_location:
                        vehicle_locations.pop(spec.vehicle_id, None)
                    elif location is not None:
                        failures.append("scenario._vehicle_locations contains a replacement entry")
            else:
                for label, records in tracked_vehicle_maps:
                    tracked = records.get(spec.vehicle_id)
                    if tracked is None:
                        records[spec.vehicle_id] = vehicle
                    elif tracked is not vehicle:
                        replacement_present = True
                        failures.append(f"scenario.{label} contains a replacement vehicle")
                if not replacement_present:
                    expected_location = (spec.position, spec.rotation)
                    location = vehicle_locations.get(spec.vehicle_id)
                    if location is None:
                        vehicle_locations[spec.vehicle_id] = expected_location
                    elif location != expected_location:
                        failures.append("scenario._vehicle_locations contains a replacement entry")
            return despawned, failures

        async def rollback_spawn_resiliently() -> tuple[list[str], bool]:
            rollback = asyncio.create_task(self._call(rollback_spawn))
            result, rollback_error, rollback_cancelled = await self._settle_task_resiliently(
                rollback
            )
            if rollback_error is not None:
                despawned = False
                failures = [f"cleanup: {type(rollback_error).__name__}: {rollback_error}"]
            else:
                assert result is not None
                despawned, failures = result
            cached = self._vehicles.get(spec.vehicle_id)
            if despawned:
                if cached is vehicle:
                    self._vehicles.pop(spec.vehicle_id, None)
                elif cached is not None:
                    failures.append("adapter cache contains a replacement vehicle")
            elif cached is None:
                self._vehicles[spec.vehicle_id] = vehicle
            elif cached is not vehicle:
                failures.append("adapter cache contains a replacement vehicle")
            return failures, rollback_cancelled

        spawning = asyncio.create_task(self._call(spawn_and_register))
        spawned, spawn_error, spawn_cancelled = await self._settle_task_resiliently(spawning)
        rollback_failures: list[str] = []
        rollback_cancelled = False
        if spawn_attempted and (spawn_error is not None or (spawn_cancelled and bool(spawned))):
            rollback_failures, rollback_cancelled = await rollback_spawn_resiliently()

        if spawn_cancelled or rollback_cancelled:
            if rollback_failures:
                self._last_error = (
                    f"Vehicle {spec.vehicle_id!r} spawn was cancelled; rollback was incomplete: "
                    + "; ".join(rollback_failures)
                )
            raise asyncio.CancelledError from spawn_error
        if spawn_error is not None:
            if rollback_failures:
                message = (
                    f"Vehicle {spec.vehicle_id!r} spawn failed ({spawn_error}); "
                    "rollback was incomplete: " + "; ".join(rollback_failures)
                )
                self._last_error = message
                raise SimulatorConnectionError(message) from spawn_error
            raise spawn_error
        assert spawned is not None
        if not spawned:
            raise SimulatorConnectionError(f"BeamNG rejected vehicle spawn for {spec.vehicle_id}")
        self._vehicles[spec.vehicle_id] = vehicle
        try:
            return await self.vehicle_state(spec.vehicle_id)
        except BaseException as verification_error:
            rollback_failures, rollback_cancelled = await rollback_spawn_resiliently()
            if rollback_failures:
                message = (
                    f"Vehicle {spec.vehicle_id!r} post-spawn verification failed "
                    f"({verification_error}); "
                    "rollback was incomplete: " + "; ".join(rollback_failures)
                )
                self._last_error = message
                if isinstance(verification_error, asyncio.CancelledError) or rollback_cancelled:
                    raise asyncio.CancelledError from verification_error
                raise SimulatorConnectionError(message) from verification_error
            if rollback_cancelled and not isinstance(verification_error, asyncio.CancelledError):
                raise asyncio.CancelledError from verification_error
            raise

    async def remove_vehicle(self, vehicle_id: str) -> None:
        bng = self._require()
        await self._call(self._scenario_vehicle_bookkeeping, bng)
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

        def despawn_and_unregister() -> None:
            _, scenario_vehicles, transient_vehicles, vehicle_locations = (
                self._scenario_vehicle_bookkeeping(bng)
            )
            bng.vehicles.despawn(vehicle)
            scenario_vehicles.pop(vehicle_id, None)
            transient_vehicles.pop(vehicle_id, None)
            vehicle_locations.pop(vehicle_id, None)

        removing = asyncio.create_task(self._call(despawn_and_unregister))
        _, removal_error, removal_cancelled = await self._settle_task_resiliently(removing)
        if removal_error is None and self._vehicles.get(vehicle_id) is vehicle:
            self._vehicles.pop(vehicle_id, None)
        if removal_cancelled:
            raise asyncio.CancelledError from removal_error
        if removal_error is not None:
            raise removal_error

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
            is_adas=command.is_adas,
        )
        if command.shift_mode is not None:
            await self._call(vehicle.set_shift_mode, command.shift_mode)
            gearbox_behavior = "arcade" if command.shift_mode == "arcade" else "realistic"
            modern_controller_command = (
                "local c=controller.getController('vehicleController');"
                f"if c and c.setGearboxMode then c.setGearboxMode('{gearbox_behavior}') end"
            )
            await self._call(vehicle.queue_lua_command, modern_controller_command)

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
