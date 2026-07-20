from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from beamng_mcp.adapters.beamngpy_adapter import (
    MAX_ATTACHED_SENSORS,
    BeamNGpyAdapter,
    SensorHandle,
)
from beamng_mcp.config import BeamNGSettings
from beamng_mcp.errors import SafetyInterlockError, SimulatorConnectionError
from beamng_mcp.models import (
    ScenarioRef,
    SensorSpec,
    VehicleAIConfig,
    VehicleControl,
    VehicleSpawn,
)


@pytest.mark.asyncio
async def test_connect_uses_the_configured_direct_simulator_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class FakeConnection:
        system = SimpleNamespace(get_info=lambda **_kwargs: {"version": "0.38.6"})

        def tech_enabled(self) -> bool:
            return False

        def open(self, **kwargs: object) -> FakeConnection:
            captured["open"] = kwargs
            return self

        def disconnect(self) -> None:
            return None

    def fake_beamngpy(host: str, port: int, **kwargs: object) -> FakeConnection:
        captured["host"] = host
        captured["port"] = port
        captured["constructor"] = kwargs
        return FakeConnection()

    monkeypatch.setattr("beamng_mcp.adapters.beamngpy_adapter.BeamNGpy", fake_beamngpy)
    settings = BeamNGSettings(
        home=tmp_path / "BeamNG.drive",
        binary=Path("Bin64/BeamNG.drive.x64.exe"),
        user=tmp_path / "BeamNG-user" / "current",
    )
    adapter = BeamNGpyAdapter(settings, tmp_path / "artifacts")

    try:
        status = await adapter.connect(launch=True)

        assert status.connected is True
        assert captured["constructor"] == {
            "home": str(settings.home),
            "binary": "Bin64\\BeamNG.drive.x64.exe",
            "user": str(settings.user.parent),
            "quit_on_close": False,
        }
        assert captured["open"] == {
            "extensions": None,
            "launch": True,
            "listen_ip": "127.0.0.1",
        }
    finally:
        await adapter.shutdown()


class FakeAI:
    def __init__(self) -> None:
        self.mode: str | None = None
        self.target: tuple[str, str] | None = None

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def set_target(self, target: str, mode: str = "chase") -> None:
        self.target = (target, mode)


class FakeVehicle:
    def __init__(self, *, connected: bool = True) -> None:
        self.kwargs: dict = {}
        self.connected = connected
        self.connected_with: object | None = None
        self.ai = FakeAI()

    def is_connected(self) -> bool:
        return self.connected

    def connect(self, bng: object) -> None:
        self.connected = True
        self.connected_with = bng

    def control(self, **kwargs) -> None:
        self.kwargs = kwargs


class FakeScenarioApi:
    def __init__(self, vehicle: FakeVehicle | None = None) -> None:
        self.vehicle = vehicle
        self.loaded: object | None = None

    def get_vehicle(self, _vehicle_id: str) -> FakeVehicle | None:
        return self.vehicle

    def get_level_scenarios(self, _level: str) -> list[object]:
        scenario = type("Scenario", (), {"name": "safe", "description": None, "path": None})()
        return [scenario]

    def load(self, scenario: object) -> None:
        self.loaded = scenario


class FakeVehiclesApi:
    def __init__(self, current: dict[str, FakeVehicle] | None = None) -> None:
        self.current = current or {}
        self.get_current_calls = 0

    def get_current(self) -> dict[str, FakeVehicle]:
        self.get_current_calls += 1
        return self.current

    def get_current_info(self, _include_config: bool) -> dict[str, dict]:
        return {"ego": {"model": "etk800"}}

    def get_states(self, _vehicle_ids: list[str]) -> dict[str, dict]:
        return {"ego": {"pos": (0.0, 0.0, 0.0), "vel": (0.0, 0.0, 0.0)}}


class FakeBng:
    def __init__(
        self,
        *,
        scenario: FakeScenarioApi | None = None,
        vehicles: FakeVehiclesApi | None = None,
    ) -> None:
        self.scenario = scenario or FakeScenarioApi()
        self.vehicles = vehicles or FakeVehiclesApi()


@pytest.mark.asyncio
async def test_status_calls_the_sdk_tech_capability_probe(tmp_path: Path) -> None:
    class FakeSystem:
        def get_info(self, **_kwargs: object) -> dict[str, str]:
            return {"version": "0.38.6"}

    class FakeDriveBng:
        system = FakeSystem()

        def __init__(self) -> None:
            self.probe_calls = 0

        def tech_enabled(self) -> bool:
            self.probe_calls += 1
            return False

    bng = FakeDriveBng()
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = bng  # type: ignore[assignment]

    try:
        status = await adapter.status()

        assert status.mode == "drive"
        assert status.tech_enabled is False
        assert status.version == "0.38.6"
        assert bng.probe_calls == 1
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_status_preserves_an_unknown_sdk_tech_capability(tmp_path: Path) -> None:
    class FakeSystem:
        def get_info(self, **_kwargs: object) -> dict[str, str]:
            return {"version": "0.38.6"}

    class FakeUnknownBng:
        system = FakeSystem()

        def tech_enabled(self) -> None:
            return None

    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = FakeUnknownBng()  # type: ignore[assignment]

    try:
        status = await adapter.status()

        assert status.mode == "unknown"
        assert status.tech_enabled is None
    finally:
        adapter._executor.shutdown(wait=True)


class FakeSensor:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.remove_calls = 0

    def remove(self) -> None:
        self.remove_calls += 1
        if self.fail:
            raise RuntimeError("sensor remove failed")


@pytest.mark.asyncio
async def test_vehicle_state_falls_back_to_the_builtin_state_sensor(
    tmp_path: Path,
) -> None:
    class FailingStateApi(FakeVehiclesApi):
        def get_states(self, _vehicle_ids: list[str]) -> dict[str, dict]:
            raise RuntimeError("ScenarioUpdate is unavailable in retail Drive")

    class BuiltinSensors:
        def __init__(self) -> None:
            self.data = {
                "state": {
                    "pos": (1.0, 2.0, 3.0),
                    "dir": (0.0, 1.0, 0.0),
                    "vel": (3.0, 4.0, 0.0),
                }
            }
            self.poll_calls: list[str] = []

        def poll(self, name: str) -> None:
            self.poll_calls.append(name)

    vehicle = FakeVehicle()
    vehicle.sensors = BuiltinSensors()  # type: ignore[attr-defined]
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = FakeBng(  # type: ignore[assignment]
        scenario=FakeScenarioApi(vehicle),
        vehicles=FailingStateApi(),
    )

    try:
        state = await adapter.vehicle_state("ego")

        assert state.position == (1.0, 2.0, 3.0)
        assert state.velocity == (3.0, 4.0, 0.0)
        assert state.speed_mps == 5.0
        assert vehicle.sensors.poll_calls == ["state"]  # type: ignore[attr-defined]
        assert adapter._last_error is None
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_service_brake_wins_over_throttle(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    fake = FakeVehicle()
    adapter._connected = True
    adapter._bng = object()  # type: ignore[assignment]
    adapter._vehicles["ego"] = fake  # type: ignore[assignment]
    await adapter.control_vehicle(
        VehicleControl(vehicle_id="ego", throttle=1.0, brake=0.2, steering=0.1)
    )
    assert fake.kwargs["throttle"] == 0.0
    assert fake.kwargs["brake"] == 0.2
    assert fake.kwargs["is_adas"] is True
    adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_vehicle_resolution_connects_sdk_vehicle_before_caching(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    vehicle = FakeVehicle(connected=False)
    bng = FakeBng(scenario=FakeScenarioApi(vehicle))
    adapter._connected = True
    adapter._bng = bng  # type: ignore[assignment]

    try:
        resolved = await adapter._vehicle("ego")

        assert resolved is vehicle
        assert vehicle.connected_with is bng
        assert adapter._vehicles == {"ego": vehicle}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_vehicle_resolution_connects_get_current_fallback(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    vehicle = FakeVehicle(connected=False)
    bng = FakeBng(vehicles=FakeVehiclesApi({"ego": vehicle}))
    adapter._connected = True
    adapter._bng = bng  # type: ignore[assignment]

    try:
        resolved = await adapter._vehicle("ego")

        assert resolved is vehicle
        assert vehicle.connected_with is bng
        assert bng.vehicles.get_current_calls == 1
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_vehicle_list_does_not_cache_unconnected_sdk_snapshots(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    vehicles = FakeVehiclesApi({"ego": FakeVehicle(connected=False)})
    adapter._connected = True
    adapter._bng = FakeBng(vehicles=vehicles)  # type: ignore[assignment]

    try:
        listed = await adapter.list_vehicles()

        assert [vehicle.vehicle_id for vehicle in listed] == ["ego"]
        assert vehicles.get_current_calls == 0
        assert adapter._vehicles == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scenario_load_invalidates_cached_vehicle_handles(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    cached = FakeVehicle()
    scenario = FakeScenarioApi()
    sensor = FakeSensor()
    adapter._connected = True
    adapter._bng = FakeBng(scenario=scenario)  # type: ignore[assignment]
    adapter._vehicles["ego"] = cached  # type: ignore[assignment]
    adapter._sensors["camera"] = SensorHandle(
        name="camera",
        kind="camera",
        sensor=sensor,
        vehicle_id="ego",
    )

    try:
        await adapter.load_scenario(ScenarioRef(level="gridmap_v2", name="safe"))

        assert scenario.loaded is not None
        assert adapter._vehicles == {}
        assert sensor.remove_calls == 1
        assert adapter._sensors == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_failed_sensor_remove_keeps_handle_for_retry(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    sensor = FakeSensor(fail=True)
    handle = SensorHandle(
        name="camera",
        kind="camera",
        sensor=sensor,
        vehicle_id="ego",
    )
    adapter._sensors["camera"] = handle

    try:
        with pytest.raises(SimulatorConnectionError, match="sensor remove failed"):
            await adapter.remove_sensor("camera")

        assert adapter._sensors["camera"] is handle
        assert sensor.remove_calls == 1
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_flee_target_does_not_fall_back_to_chase(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    vehicle = FakeVehicle()
    adapter._connected = True
    adapter._bng = FakeBng()  # type: ignore[assignment]
    adapter._vehicles["ego"] = vehicle  # type: ignore[assignment]

    try:
        await adapter.configure_ai(
            VehicleAIConfig(vehicle_id="ego", mode="flee", target_vehicle_id="pursuer")
        )

        assert vehicle.ai.target == ("pursuer", "flee")
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scenario_create_refuses_unconfirmed_overwrite(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = FakeBng(scenario=FakeScenarioApi())  # type: ignore[assignment]

    try:
        with pytest.raises(SafetyInterlockError, match="already exists"):
            await adapter.create_scenario(
                ScenarioRef(level="gridmap_v2", name="safe"),
                [VehicleSpawn(vehicle_id="ego", model="etk800")],
            )
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scenario_create_caps_vehicle_count_before_engine_calls(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = FakeBng()  # type: ignore[assignment]
    vehicles = [VehicleSpawn(vehicle_id=f"car_{index}", model="etk800") for index in range(65)]

    try:
        with pytest.raises(ValueError, match="at most 64"):
            await adapter.create_scenario(ScenarioRef(level="gridmap_v2", name="large"), vehicles)
    finally:
        adapter._executor.shutdown(wait=True)


def test_large_sensor_payloads_become_local_artifacts(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    raw = {
        "colour": Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)),
        "points": np.zeros((5000, 3), dtype=np.float32),
    }
    data, artifacts = adapter._serialize_reading("camera", raw)
    assert data["colour"]["type"] == "image"
    assert data["points"]["type"] == "ndarray"
    assert len(artifacts) == 2
    assert all(Path(path).is_file() for path in artifacts)
    adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_sensor_quota_is_checked_before_engine_allocation(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._sensors.update(
        {
            f"sensor-{index}": SensorHandle(
                name=f"sensor-{index}",
                kind="camera",
                sensor=object(),
                vehicle_id=None,
            )
            for index in range(MAX_ATTACHED_SENSORS)
        }
    )

    try:
        with pytest.raises(ValueError, match=f"At most {MAX_ATTACHED_SENSORS}"):
            await adapter.attach_sensor(SensorSpec(name="overflow", sensor_type="camera"))
    finally:
        adapter._executor.shutdown(wait=True)
