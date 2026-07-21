from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from beamngpy import Scenario
from PIL import Image

from beamng_mcp.adapters.beamngpy_adapter import (
    MAX_ATTACHED_SENSORS,
    BeamNGpyAdapter,
    SensorHandle,
)
from beamng_mcp.config import BeamNGSettings
from beamng_mcp.errors import ConflictError, SafetyInterlockError, SimulatorConnectionError
from beamng_mcp.models import (
    ScenarioRef,
    ScenarioSelector,
    ScenarioVehiclePlacement,
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


@pytest.mark.asyncio
async def test_connect_closes_a_launched_process_when_open_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FailingConnection:
        def __init__(self) -> None:
            self.process: object | None = object()
            self.quit_on_close = False
            self.close_calls = 0
            self.quit_on_close_when_closed: bool | None = None

        def open(self, **_kwargs: object) -> FailingConnection:
            raise RuntimeError("open failed after launch")

        def close(self) -> None:
            self.close_calls += 1
            self.quit_on_close_when_closed = self.quit_on_close
            self.process = None

    connection = FailingConnection()
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)

    try:
        with pytest.raises(SimulatorConnectionError, match="open failed after launch"):
            await adapter.connect(launch=True)

        assert connection.close_calls == 1
        assert connection.quit_on_close_when_closed is True
        status = await adapter.status()
        assert status.connected is False
        assert status.last_error == "RuntimeError: open failed after launch"
    finally:
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_connect_uses_the_raw_process_handle_when_beamngpy_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class RawProcess:
        def __init__(self) -> None:
            self.running = True
            self.kill_calls = 0
            self.wait_calls = 0

        def poll(self) -> int | None:
            return None if self.running else 1

        def kill(self) -> None:
            self.kill_calls += 1
            self.running = False

        def wait(self, timeout: float) -> int:
            assert timeout == 5.0
            self.wait_calls += 1
            return 1

    class FailingConnection:
        def __init__(self) -> None:
            self.process: RawProcess | None = RawProcess()
            self.quit_on_close = False

        def open(self, **_kwargs: object) -> FailingConnection:
            raise RuntimeError("open failed after launch")

        def close(self) -> None:
            raise RuntimeError("close failed")

        def _kill_beamng(self) -> None:
            raise RuntimeError("BeamNGpy kill failed")

    connection = FailingConnection()
    process = connection.process
    assert process is not None
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)

    try:
        with pytest.raises(SimulatorConnectionError, match="open failed after launch"):
            await adapter.connect(launch=True)

        assert process.kill_calls == 1
        assert process.wait_calls == 1
        assert process.running is False
        assert connection.process is None
        assert adapter._bng is None
    finally:
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_connect_recognizes_an_already_exited_provisional_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class ExitedProcess:
        def __init__(self) -> None:
            self.kill_calls = 0

        def poll(self) -> int:
            return 7

        def kill(self) -> None:
            self.kill_calls += 1
            raise RuntimeError("process already exited")

    class FailingConnection:
        def __init__(self) -> None:
            self.process: ExitedProcess | None = ExitedProcess()
            self.quit_on_close = False

        def open(self, **_kwargs: object) -> FailingConnection:
            raise RuntimeError("open failed after child exit")

        def close(self) -> None:
            raise RuntimeError("close failed")

        def _kill_beamng(self) -> None:
            raise RuntimeError("BeamNGpy kill failed")

    connection = FailingConnection()
    process = connection.process
    assert process is not None
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)

    try:
        with pytest.raises(SimulatorConnectionError) as raised:
            await adapter.connect(launch=True)

        assert "open failed after child exit" in str(raised.value)
        assert "provisional connection cleanup failed" not in str(raised.value)
        assert process.kill_calls == 0
        assert connection.process is None
        assert adapter._bng is None
    finally:
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_connect_retains_and_reports_an_unterminated_provisional_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class RawProcess:
        def __init__(self) -> None:
            self.allow_kill = False

        def poll(self) -> None:
            return None

        def kill(self) -> None:
            if not self.allow_kill:
                raise RuntimeError("raw kill failed")

        def wait(self, timeout: float) -> int:
            assert timeout == 5.0
            return 1

    class FailingConnection:
        def __init__(self) -> None:
            self.process: RawProcess | None = RawProcess()
            self.quit_on_close = False

        def open(self, **_kwargs: object) -> FailingConnection:
            raise RuntimeError("open failed after launch")

        def close(self) -> None:
            raise RuntimeError("close failed")

        def _kill_beamng(self) -> None:
            raise RuntimeError("BeamNGpy kill failed")

    connection = FailingConnection()
    process = connection.process
    assert process is not None
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)

    with pytest.raises(SimulatorConnectionError) as raised:
        await adapter.connect(launch=True)

    assert "open failed after launch" in str(raised.value)
    assert "provisional connection cleanup failed" in str(raised.value)
    assert "raw kill failed" in str(raised.value)
    assert adapter._bng is connection
    assert adapter._connected is False

    process.allow_kill = True
    await adapter.shutdown()
    assert adapter._bng is None
    assert adapter._closed is True


@pytest.mark.asyncio
async def test_connect_closes_a_launched_process_when_initial_status_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FailingConnection:
        system = SimpleNamespace(get_info=lambda **_kwargs: {"version": "0.38.6"})

        def __init__(self) -> None:
            self.process: object | None = object()
            self.quit_on_close = False
            self.close_calls = 0
            self.quit_on_close_when_closed: bool | None = None
            self.tech_probe_calls = 0

        def open(self, **_kwargs: object) -> FailingConnection:
            return self

        def tech_enabled(self) -> bool:
            self.tech_probe_calls += 1
            if self.tech_probe_calls == 1:
                raise RuntimeError("status failed after launch")
            return False

        def close(self) -> None:
            self.close_calls += 1
            self.quit_on_close_when_closed = self.quit_on_close
            self.process = None

    connection = FailingConnection()
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)

    try:
        with pytest.raises(SimulatorConnectionError, match="status failed after launch"):
            await adapter.connect(launch=True)

        assert connection.close_calls == 1
        assert connection.quit_on_close_when_closed is True
        status = await adapter.status()
        assert status.connected is False
        assert status.last_error == "RuntimeError: status failed after launch"
    finally:
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_connect_records_a_direct_initial_status_validation_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class InvalidConnection:
        system = SimpleNamespace(get_info=lambda **_kwargs: {"version": "0.38.6"})

        def __init__(self) -> None:
            self.process: object | None = object()
            self.quit_on_close = False

        def open(self, **_kwargs: object) -> InvalidConnection:
            return self

        def tech_enabled(self) -> str:
            return "invalid"

        def close(self) -> None:
            self.process = None

    connection = InvalidConnection()
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)

    try:
        with pytest.raises(SimulatorConnectionError, match="invalid capability value"):
            await adapter.connect(launch=True)

        status = await adapter.status()
        assert status.connected is False
        assert status.last_error == (
            "SimulatorConnectionError: BeamNGpy tech_enabled() returned an invalid capability value"
        )
    finally:
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_connect_cancellation_waits_for_launch_and_closes_the_provisional_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launch_started = threading.Event()
    release_launch = threading.Event()

    class SlowConnection:
        def __init__(self) -> None:
            self.process: object | None = None
            self.quit_on_close = False
            self.close_calls = 0

        def open(self, **_kwargs: object) -> SlowConnection:
            self.process = object()
            launch_started.set()
            if not release_launch.wait(timeout=5.0):
                raise TimeoutError("test did not release the simulated launch")
            return self

        def close(self) -> None:
            self.close_calls += 1
            self.process = None

    connection = SlowConnection()
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    connecting = asyncio.create_task(adapter.connect(launch=True))

    try:
        assert await asyncio.to_thread(launch_started.wait, 2.0)
        connecting.cancel()
        await asyncio.sleep(0)
        connecting.cancel()
        release_launch.set()

        with pytest.raises(asyncio.CancelledError):
            await connecting

        assert connection.close_calls == 1
        assert connection.process is None
        assert adapter._bng is None
    finally:
        release_launch.set()
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_connect_cancellation_cleans_an_open_queued_behind_executor_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executor_busy = threading.Event()
    release_executor = threading.Event()
    open_queued = asyncio.Event()

    class FailingConnection:
        def __init__(self) -> None:
            self.process: object | None = None
            self.quit_on_close = False
            self.close_calls = 0

        def open(self, **_kwargs: object) -> FailingConnection:
            self.process = object()
            raise RuntimeError("queued open failed after launch")

        def close(self) -> None:
            self.close_calls += 1
            self.process = None

    connection = FailingConnection()
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    original_call = adapter._call

    async def observed_call(function: object, *args: object, **kwargs: object) -> object:
        if getattr(function, "__name__", None) == "open_connection":
            open_queued.set()
        return await original_call(function, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(adapter, "_call", observed_call)

    def occupy_executor() -> None:
        executor_busy.set()
        if not release_executor.wait(timeout=5.0):
            raise TimeoutError("test did not release the occupied executor")

    loop = asyncio.get_running_loop()
    occupying = loop.run_in_executor(adapter._executor, occupy_executor)
    assert await asyncio.to_thread(executor_busy.wait, 2.0)
    connecting = asyncio.create_task(adapter.connect(launch=True))

    try:
        await asyncio.wait_for(open_queued.wait(), timeout=2.0)
        connecting.cancel()
        release_executor.set()

        with pytest.raises(asyncio.CancelledError):
            await connecting
        await occupying

        assert connection.close_calls == 1
        assert connection.process is None
        assert adapter._bng is None
    finally:
        release_executor.set()
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_concurrent_connect_calls_share_one_serialized_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launch_started = threading.Event()
    release_launch = threading.Event()
    construction_count = 0

    class SlowConnection:
        system = SimpleNamespace(get_info=lambda **_kwargs: {"version": "0.38.6"})

        def open(self, **_kwargs: object) -> SlowConnection:
            launch_started.set()
            if not release_launch.wait(timeout=5.0):
                raise TimeoutError("test did not release the simulated launch")
            return self

        def tech_enabled(self) -> bool:
            return False

        def disconnect(self) -> None:
            return None

    connection = SlowConnection()

    def create_connection(*_args: object, **_kwargs: object) -> SlowConnection:
        nonlocal construction_count
        construction_count += 1
        return connection

    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        create_connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    first = asyncio.create_task(adapter.connect(launch=True))
    second = asyncio.create_task(adapter.connect(launch=True))

    try:
        assert await asyncio.to_thread(launch_started.wait, 2.0)
        release_launch.set()
        first_status, second_status = await asyncio.gather(first, second)

        assert first_status.connected is True
        assert second_status.connected is True
        assert construction_count == 1
        assert adapter._bng is connection
    finally:
        release_launch.set()
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_shutdown_waits_for_an_inflight_connect_before_disconnecting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launch_started = threading.Event()
    release_launch = threading.Event()

    class SlowConnection:
        system = SimpleNamespace(get_info=lambda **_kwargs: {"version": "0.38.6"})

        def __init__(self) -> None:
            self.disconnect_calls = 0

        def open(self, **_kwargs: object) -> SlowConnection:
            launch_started.set()
            if not release_launch.wait(timeout=5.0):
                raise TimeoutError("test did not release the simulated launch")
            return self

        def tech_enabled(self) -> bool:
            return False

        def disconnect(self) -> None:
            self.disconnect_calls += 1

    connection = SlowConnection()
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    connecting = asyncio.create_task(adapter.connect(launch=True))

    assert await asyncio.to_thread(launch_started.wait, 2.0)
    shutting_down = asyncio.create_task(adapter.shutdown())
    release_launch.set()
    status = await connecting
    await shutting_down

    assert status.connected is True
    assert connection.disconnect_calls == 1
    assert adapter._bng is None
    assert adapter._closed is True


@pytest.mark.asyncio
async def test_repeated_shutdown_cancellation_finishes_blocking_disconnect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    disconnect_started = threading.Event()
    release_disconnect = threading.Event()

    class SlowConnection:
        system = SimpleNamespace(get_info=lambda **_kwargs: {"version": "0.38.6"})

        def open(self, **_kwargs: object) -> SlowConnection:
            return self

        def tech_enabled(self) -> bool:
            return False

        def disconnect(self) -> None:
            disconnect_started.set()
            if not release_disconnect.wait(timeout=5.0):
                raise TimeoutError("test did not release the simulated disconnect")

    connection = SlowConnection()
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    await adapter.connect(launch=True)
    shutting_down = asyncio.create_task(adapter.shutdown())

    try:
        assert await asyncio.to_thread(disconnect_started.wait, 2.0)
        shutting_down.cancel()
        await asyncio.sleep(0)
        shutting_down.cancel()
        release_disconnect.set()

        with pytest.raises(asyncio.CancelledError):
            await shutting_down

        assert adapter._bng is None
        assert adapter._connected is False
        assert adapter._closed is True
    finally:
        release_disconnect.set()
        if not adapter._closed:
            await adapter.shutdown()


@pytest.mark.asyncio
async def test_failed_shutdown_remains_retryable_with_a_live_executor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FlakyConnection:
        system = SimpleNamespace(get_info=lambda **_kwargs: {"version": "0.38.6"})

        def __init__(self) -> None:
            self.disconnect_calls = 0

        def open(self, **_kwargs: object) -> FlakyConnection:
            return self

        def tech_enabled(self) -> bool:
            return False

        def disconnect(self) -> None:
            self.disconnect_calls += 1
            if self.disconnect_calls == 1:
                raise RuntimeError("disconnect failed")

    connection = FlakyConnection()
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    await adapter.connect(launch=True)

    with pytest.raises(SimulatorConnectionError, match="disconnect failed"):
        await adapter.shutdown()

    assert adapter._closed is False
    assert adapter._connected is True
    assert adapter._bng is connection
    assert (await adapter.status()).connected is True

    await adapter.shutdown()
    assert connection.disconnect_calls == 2
    assert adapter._closed is True
    assert adapter._connected is False
    assert adapter._bng is None


@pytest.mark.asyncio
async def test_status_waits_for_shutdown_and_returns_a_coherent_offline_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    disconnect_started = threading.Event()
    release_disconnect = threading.Event()

    class SlowConnection:
        system = SimpleNamespace(get_info=lambda **_kwargs: {"version": "0.38.6"})

        def __init__(self) -> None:
            self.probe_calls = 0

        def open(self, **_kwargs: object) -> SlowConnection:
            return self

        def tech_enabled(self) -> bool:
            self.probe_calls += 1
            return False

        def disconnect(self) -> None:
            disconnect_started.set()
            if not release_disconnect.wait(timeout=5.0):
                raise TimeoutError("test did not release the simulated disconnect")

    connection = SlowConnection()
    monkeypatch.setattr(
        "beamng_mcp.adapters.beamngpy_adapter.BeamNGpy",
        lambda *_args, **_kwargs: connection,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    await adapter.connect(launch=True)
    initial_probe_calls = connection.probe_calls
    shutting_down = asyncio.create_task(adapter.shutdown())

    try:
        assert await asyncio.to_thread(disconnect_started.wait, 2.0)
        checking_status = asyncio.create_task(adapter.status())
        await asyncio.sleep(0)
        release_disconnect.set()
        await shutting_down
        status = await checking_status

        assert status.connected is False
        assert status.mode == "offline"
        assert status.tech_enabled is None
        assert status.version is None
        assert connection.probe_calls == initial_probe_calls
    finally:
        release_disconnect.set()
        if not adapter._closed:
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
        self.shift_modes: list[str] = []
        self.lua_commands: list[str] = []
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

    def set_shift_mode(self, mode: str) -> None:
        self.shift_modes.append(mode)

    def queue_lua_command(self, command: str) -> None:
        self.lua_commands.append(command)


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


def test_installed_beamngpy_scenario_exposes_expected_vehicle_bookkeeping() -> None:
    scenario = Scenario("gridmap_v2", "bookkeeping_canary")

    assert isinstance(scenario.vehicles, dict)
    assert isinstance(scenario.transient_vehicles, dict)
    assert isinstance(scenario._vehicle_locations, dict)


@pytest.mark.asyncio
async def test_spawned_vehicle_is_registered_as_a_scenario_transient(
    tmp_path: Path,
) -> None:
    class SpawnVehiclesApi:
        def __init__(self) -> None:
            self.spawned: object | None = None

        def spawn(
            self,
            vehicle: object,
            _position: object,
            _rotation: object,
            _cling: bool,
            _connect: bool,
        ) -> bool:
            self.spawned = vehicle
            return True

        def get_current_info(self, _include_config: bool) -> dict[str, dict[str, str]]:
            if self.spawned is None:
                return {}
            return {"ego": {"model": "etk800"}}

        def get_states(self, _vehicle_ids: list[str]) -> dict[str, dict[str, object]]:
            return {"ego": {"pos": (1.0, 2.0, 3.0), "vel": (0.0, 0.0, 0.0)}}

    vehicles_api = SpawnVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={},
        transient_vehicles={},
        _vehicle_locations={},
    )
    bng = SimpleNamespace(vehicles=vehicles_api, _scenario=current_scenario)
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = bng  # type: ignore[assignment]

    try:
        spawned = await adapter.spawn_vehicle(
            VehicleSpawn(
                vehicle_id="ego",
                model="etk800",
                position=(1.0, 2.0, 3.0),
                cling=False,
            )
        )

        assert spawned.vehicle_id == "ego"
        assert current_scenario.vehicles == {"ego": vehicles_api.spawned}
        assert current_scenario.transient_vehicles == {"ego": vehicles_api.spawned}
        assert current_scenario._vehicle_locations == {
            "ego": ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0))
        }
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "existing_source",
    ["engine", "scenario", "transient", "cache"],
)
async def test_spawn_rejects_duplicate_id_without_spawn_or_rollback(
    tmp_path: Path,
    existing_source: str,
) -> None:
    existing_vehicle = FakeVehicle()

    class DuplicateVehiclesApi:
        def __init__(self) -> None:
            self.spawn_calls = 0
            self.despawn_calls = 0

        def get_current_info(self, _include_config: bool) -> dict[str, object]:
            if existing_source == "engine":
                return {"ego": {"model": "pickup"}}
            return {}

        def spawn(self, *_args: object) -> bool:
            self.spawn_calls += 1
            raise ValueError("invalid color before SpawnVehicle is sent")

        def despawn(self, _vehicle: object) -> None:
            self.despawn_calls += 1

    vehicles_api = DuplicateVehiclesApi()
    scenario_vehicles = {"ego": existing_vehicle} if existing_source == "scenario" else {}
    transient_vehicles = {"ego": existing_vehicle} if existing_source == "transient" else {}
    vehicle_locations: dict[str, object] = {}
    current_scenario = SimpleNamespace(
        vehicles=scenario_vehicles,
        transient_vehicles=transient_vehicles,
        _vehicle_locations=vehicle_locations,
    )
    expected_scenario_vehicles = dict(scenario_vehicles)
    expected_transient_vehicles = dict(transient_vehicles)
    expected_vehicle_locations = dict(vehicle_locations)
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )
    if existing_source == "cache":
        adapter._vehicles["ego"] = existing_vehicle

    try:
        with pytest.raises(ConflictError, match="already exists"):
            await adapter.spawn_vehicle(
                VehicleSpawn(
                    vehicle_id="ego",
                    model="etk800",
                    position=(1.0, 2.0, 100.0),
                    color="definitely-not-a-color",
                )
            )

        assert vehicles_api.spawn_calls == 0
        assert vehicles_api.despawn_calls == 0
        assert current_scenario.vehicles == expected_scenario_vehicles
        assert current_scenario.transient_vehicles == expected_transient_vehicles
        assert current_scenario._vehicle_locations == expected_vehicle_locations
        expected_cache = {"ego": existing_vehicle} if existing_source == "cache" else {}
        assert adapter._vehicles == expected_cache
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_spawn_fails_closed_when_vehicle_inventory_is_unavailable(tmp_path: Path) -> None:
    class UnavailableInventoryVehiclesApi:
        def __init__(self) -> None:
            self.spawn_calls = 0
            self.despawn_calls = 0

        def get_current_info(self, _include_config: bool) -> dict[str, object]:
            raise RuntimeError("inventory unavailable")

        def spawn(self, *_args: object) -> bool:
            self.spawn_calls += 1
            return True

        def despawn(self, _vehicle: object) -> None:
            self.despawn_calls += 1

    vehicles_api = UnavailableInventoryVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={},
        transient_vehicles={},
        _vehicle_locations={},
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )

    try:
        with pytest.raises(SimulatorConnectionError, match="inventory unavailable"):
            await adapter.spawn_vehicle(
                VehicleSpawn(
                    vehicle_id="ego",
                    model="etk800",
                    position=(1.0, 2.0, 100.0),
                )
            )

        assert vehicles_api.spawn_calls == 0
        assert vehicles_api.despawn_calls == 0
        assert current_scenario.vehicles == {}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {}
        assert adapter._vehicles == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_invalid_spawn_color_is_rejected_before_remote_mutation(tmp_path: Path) -> None:
    class InvalidColorVehiclesApi:
        def __init__(self) -> None:
            self.spawn_calls = 0
            self.despawn_calls = 0

        def get_current_info(self, _include_config: bool) -> dict[str, object]:
            return {}

        def spawn(self, *_args: object) -> bool:
            self.spawn_calls += 1
            return True

        def despawn(self, _vehicle: object) -> None:
            self.despawn_calls += 1

    vehicles_api = InvalidColorVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={},
        transient_vehicles={},
        _vehicle_locations={},
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )

    try:
        with pytest.raises(SimulatorConnectionError, match="Invalid RGBA argument"):
            await adapter.spawn_vehicle(
                VehicleSpawn(
                    vehicle_id="ego",
                    model="etk800",
                    position=(1.0, 2.0, 100.0),
                    color="definitely-not-a-color",
                )
            )

        assert vehicles_api.spawn_calls == 0
        assert vehicles_api.despawn_calls == 0
        assert current_scenario.vehicles == {}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {}
        assert adapter._vehicles == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_failed_post_spawn_verification_rolls_back_the_vehicle(tmp_path: Path) -> None:
    class FailingVerificationVehiclesApi:
        def __init__(self) -> None:
            self.spawned: object | None = None
            self.despawned: object | None = None

        def spawn(
            self,
            vehicle: object,
            _position: object,
            _rotation: object,
            _cling: bool,
            _connect: bool,
        ) -> bool:
            self.spawned = vehicle
            return True

        def despawn(self, vehicle: object) -> None:
            self.despawned = vehicle

        def get_current_info(self, _include_config: bool) -> dict[str, object]:
            if self.spawned is None:
                return {}
            raise RuntimeError("post-spawn state unavailable")

    vehicles_api = FailingVerificationVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={},
        transient_vehicles={},
        _vehicle_locations={},
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )

    try:
        with pytest.raises(SimulatorConnectionError, match="post-spawn state unavailable"):
            await adapter.spawn_vehicle(
                VehicleSpawn(
                    vehicle_id="ego",
                    model="etk800",
                    position=(0.0, 0.0, 0.0),
                    cling=False,
                )
            )

        assert vehicles_api.despawned is vehicles_api.spawned
        assert current_scenario.vehicles == {}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {}
        assert adapter._vehicles == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_failed_spawn_rollback_retains_ownership_for_retry(tmp_path: Path) -> None:
    class FailingRollbackVehiclesApi:
        def __init__(self) -> None:
            self.remote_created = False
            self.spawned: object | None = None

        def spawn(self, vehicle: object, *_args: object) -> bool:
            self.remote_created = True
            self.spawned = vehicle
            return True

        def despawn(self, vehicle: object) -> None:
            assert vehicle is self.spawned
            raise RuntimeError("despawn ack unavailable")

        def get_current_info(self, _include_config: bool) -> dict[str, object]:
            if self.spawned is None:
                return {}
            raise RuntimeError("post-spawn state unavailable")

    vehicles_api = FailingRollbackVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={},
        transient_vehicles={},
        _vehicle_locations={},
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )

    try:
        with pytest.raises(SimulatorConnectionError, match="rollback was incomplete"):
            await adapter.spawn_vehicle(
                VehicleSpawn(
                    vehicle_id="ego",
                    model="etk800",
                    position=(1.0, 2.0, 100.0),
                    cling=False,
                )
            )

        assert vehicles_api.remote_created is True
        assert current_scenario.vehicles == {"ego": vehicles_api.spawned}
        assert current_scenario.transient_vehicles == {"ego": vehicles_api.spawned}
        assert current_scenario._vehicle_locations == {
            "ego": ((1.0, 2.0, 100.0), (0.0, 0.0, 0.0, 1.0))
        }
        assert adapter._vehicles == {"ego": vehicles_api.spawned}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_spawn_connect_failure_after_engine_ack_is_rolled_back(tmp_path: Path) -> None:
    class AckThenFailVehiclesApi:
        def __init__(self) -> None:
            self.remote_created = False
            self.spawned: object | None = None

        def spawn(self, vehicle: object, *_args: object) -> bool:
            self.remote_created = True
            self.spawned = vehicle
            raise RuntimeError("vehicle connect failed after spawn ack")

        def despawn(self, vehicle: object) -> None:
            assert vehicle is self.spawned
            self.remote_created = False

        def get_current_info(self, _include_config: bool) -> dict[str, object]:
            return {}

    vehicles_api = AckThenFailVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={},
        transient_vehicles={},
        _vehicle_locations={},
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )

    try:
        with pytest.raises(SimulatorConnectionError, match="connect failed after spawn ack"):
            await adapter.spawn_vehicle(
                VehicleSpawn(
                    vehicle_id="ego",
                    model="etk800",
                    position=(1.0, 2.0, 100.0),
                )
            )

        assert vehicles_api.remote_created is False
        assert current_scenario.vehicles == {}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {}
        assert adapter._vehicles == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_cancelled_in_flight_spawn_is_settled_and_rolled_back(tmp_path: Path) -> None:
    spawn_started = threading.Event()
    release_spawn = threading.Event()

    class SlowSpawnVehiclesApi:
        def __init__(self) -> None:
            self.remote_created = False
            self.spawned: object | None = None

        def spawn(self, vehicle: object, *_args: object) -> bool:
            self.remote_created = True
            self.spawned = vehicle
            spawn_started.set()
            if not release_spawn.wait(timeout=5.0):
                raise TimeoutError("test did not release spawn")
            return True

        def despawn(self, vehicle: object) -> None:
            assert vehicle is self.spawned
            self.remote_created = False

        def get_current_info(self, _include_config: bool) -> dict[str, object]:
            return {}

    vehicles_api = SlowSpawnVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={},
        transient_vehicles={},
        _vehicle_locations={},
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )
    spawning = asyncio.create_task(
        adapter.spawn_vehicle(
            VehicleSpawn(
                vehicle_id="ego",
                model="etk800",
                position=(1.0, 2.0, 100.0),
            )
        )
    )

    try:
        assert await asyncio.to_thread(spawn_started.wait, 2.0)
        spawning.cancel()
        release_spawn.set()
        with pytest.raises(asyncio.CancelledError):
            await spawning

        assert vehicles_api.remote_created is False
        assert current_scenario.vehicles == {}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {}
        assert adapter._vehicles == {}
    finally:
        release_spawn.set()
        if not spawning.done():
            await spawning
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_spawn_refuses_missing_scenario_bookkeeping_before_engine_call(
    tmp_path: Path,
) -> None:
    class SpawnVehiclesApi:
        def __init__(self) -> None:
            self.spawn_calls = 0

        def spawn(self, *_args: object) -> bool:
            self.spawn_calls += 1
            return True

    vehicles_api = SpawnVehiclesApi()
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(vehicles=vehicles_api)  # type: ignore[assignment]

    try:
        with pytest.raises(
            SimulatorConnectionError,
            match="Loaded BeamNGpy scenario cannot track a transient vehicle",
        ):
            await adapter.spawn_vehicle(
                VehicleSpawn(
                    vehicle_id="ego",
                    model="etk800",
                    position=(0.0, 0.0, 0.0),
                )
            )

        assert vehicles_api.spawn_calls == 0
        assert adapter._vehicles == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_spawn_refuses_incompatible_scenario_bookkeeping_before_engine_call(
    tmp_path: Path,
) -> None:
    class SpawnVehiclesApi:
        def __init__(self) -> None:
            self.spawn_calls = 0

        def spawn(self, *_args: object) -> bool:
            self.spawn_calls += 1
            return True

    vehicles_api = SpawnVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={},
        transient_vehicles={},
        _vehicle_locations=[],
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )

    try:
        with pytest.raises(
            SimulatorConnectionError,
            match="Loaded BeamNGpy scenario cannot track a transient vehicle",
        ):
            await adapter.spawn_vehicle(
                VehicleSpawn(
                    vehicle_id="ego",
                    model="etk800",
                    position=(0.0, 0.0, 0.0),
                )
            )

        assert vehicles_api.spawn_calls == 0
        assert current_scenario.vehicles == {}
        assert current_scenario.transient_vehicles == {}
        assert adapter._vehicles == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_removed_vehicle_is_forgotten_by_the_current_scenario(tmp_path: Path) -> None:
    vehicle = FakeVehicle()

    class DespawnVehiclesApi:
        def __init__(self) -> None:
            self.despawned: object | None = None

        def despawn(self, removed: object) -> None:
            self.despawned = removed

    vehicles_api = DespawnVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={"ego": vehicle},
        transient_vehicles={"ego": vehicle},
        _vehicle_locations={"ego": ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0))},
    )
    bng = SimpleNamespace(vehicles=vehicles_api, _scenario=current_scenario)
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = bng  # type: ignore[assignment]
    adapter._vehicles["ego"] = vehicle  # type: ignore[assignment]

    try:
        await adapter.remove_vehicle("ego")

        assert vehicles_api.despawned is vehicle
        assert current_scenario.vehicles == {}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_cancelled_vehicle_remove_finishes_bookkeeping_before_propagating(
    tmp_path: Path,
) -> None:
    despawn_started = threading.Event()
    release_despawn = threading.Event()
    vehicle = FakeVehicle()

    class SlowDespawnVehiclesApi:
        def __init__(self) -> None:
            self.remote_present = True

        def despawn(self, removed: object) -> None:
            assert removed is vehicle
            despawn_started.set()
            if not release_despawn.wait(timeout=5.0):
                raise TimeoutError("test did not release despawn")
            self.remote_present = False

    vehicles_api = SlowDespawnVehiclesApi()
    current_scenario = SimpleNamespace(
        vehicles={"ego": vehicle},
        transient_vehicles={"ego": vehicle},
        _vehicle_locations={"ego": ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0))},
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )
    adapter._vehicles["ego"] = vehicle  # type: ignore[assignment]
    removing = asyncio.create_task(adapter.remove_vehicle("ego"))

    try:
        assert await asyncio.to_thread(despawn_started.wait, 2.0)
        removing.cancel()
        release_despawn.set()
        with pytest.raises(asyncio.CancelledError):
            await removing

        assert vehicles_api.remote_present is False
        assert current_scenario.vehicles == {}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {}
        assert adapter._vehicles == {}
    finally:
        release_despawn.set()
        if not removing.done():
            await removing
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_remove_preflights_scenario_bookkeeping_before_releasing_sensors(
    tmp_path: Path,
) -> None:
    vehicle = FakeVehicle()

    class DespawnVehiclesApi:
        def __init__(self) -> None:
            self.despawn_calls = 0

        def despawn(self, _removed: object) -> None:
            self.despawn_calls += 1

    class AttachedSensor:
        def __init__(self) -> None:
            self.remove_calls = 0

        def remove(self) -> None:
            self.remove_calls += 1

    vehicles_api = DespawnVehiclesApi()
    sensor = AttachedSensor()
    current_scenario = SimpleNamespace(
        vehicles={"ego": vehicle},
        transient_vehicles={"ego": vehicle},
        _vehicle_locations=None,
    )
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        vehicles=vehicles_api,
        _scenario=current_scenario,
    )
    adapter._vehicles["ego"] = vehicle  # type: ignore[assignment]
    adapter._sensors["state"] = SensorHandle(
        name="state",
        kind="state",
        sensor=sensor,
        vehicle_id="ego",
    )

    try:
        with pytest.raises(
            SimulatorConnectionError,
            match="Loaded BeamNGpy scenario cannot track a transient vehicle",
        ):
            await adapter.remove_vehicle("ego")

        assert sensor.remove_calls == 0
        assert vehicles_api.despawn_calls == 0
        assert adapter._vehicles == {"ego": vehicle}
        assert set(adapter._sensors) == {"state"}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scenario_restart_forgets_locations_of_transient_vehicles(
    tmp_path: Path,
) -> None:
    persistent = FakeVehicle()
    transient = FakeVehicle()
    current_scenario = SimpleNamespace(
        vehicles={"persistent": persistent, "ego": transient},
        transient_vehicles={"ego": transient},
        _vehicle_locations={
            "persistent": ((10.0, 20.0, 30.0), (0.0, 0.0, 0.0, 1.0)),
            "ego": ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0)),
        },
    )

    class RestartScenarioApi:
        def __init__(self) -> None:
            self.restart_calls = 0

        def restart(self) -> None:
            self.restart_calls += 1
            while current_scenario.transient_vehicles:
                vehicle_id, _vehicle = current_scenario.transient_vehicles.popitem()
                current_scenario.vehicles.pop(vehicle_id, None)

    scenario_api = RestartScenarioApi()
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        scenario=scenario_api,
        _scenario=current_scenario,
    )
    adapter._vehicles.update({"persistent": persistent, "ego": transient})  # type: ignore[arg-type]

    try:
        await adapter.scenario_restart()

        assert scenario_api.restart_calls == 1
        assert current_scenario.vehicles == {"persistent": persistent}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {
            "persistent": ((10.0, 20.0, 30.0), (0.0, 0.0, 0.0, 1.0))
        }
        assert adapter._vehicles == {}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scenario_restart_failure_before_mutation_preserves_locations(
    tmp_path: Path,
) -> None:
    transient = FakeVehicle()
    location = ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0))
    current_scenario = SimpleNamespace(
        vehicles={"ego": transient},
        transient_vehicles={"ego": transient},
        _vehicle_locations={"ego": location},
    )

    class FailingScenarioApi:
        def restart(self) -> None:
            raise RuntimeError("restart rejected before mutation")

    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        scenario=FailingScenarioApi(),
        _scenario=current_scenario,
    )

    try:
        with pytest.raises(SimulatorConnectionError, match="restart rejected before mutation"):
            await adapter.scenario_restart()

        assert current_scenario.vehicles == {"ego": transient}
        assert current_scenario.transient_vehicles == {"ego": transient}
        assert current_scenario._vehicle_locations == {"ego": location}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scenario_restart_partial_failure_preserves_still_tracked_location(
    tmp_path: Path,
) -> None:
    transient = FakeVehicle()
    location = ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0))
    current_scenario = SimpleNamespace(
        vehicles={"ego": transient},
        transient_vehicles={"ego": transient},
        _vehicle_locations={"ego": location},
    )

    class PartiallyFailingScenarioApi:
        def restart(self) -> None:
            current_scenario.transient_vehicles.pop("ego")
            raise RuntimeError("despawn failed during restart")

    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        scenario=PartiallyFailingScenarioApi(),
        _scenario=current_scenario,
    )

    try:
        with pytest.raises(SimulatorConnectionError, match="despawn failed during restart"):
            await adapter.scenario_restart()

        assert current_scenario.vehicles == {"ego": transient}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {"ego": location}
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_cancelled_scenario_restart_settles_before_reconciling_locations(
    tmp_path: Path,
) -> None:
    restart_started = threading.Event()
    release_restart = threading.Event()
    transient = FakeVehicle()
    current_scenario = SimpleNamespace(
        vehicles={"ego": transient},
        transient_vehicles={"ego": transient},
        _vehicle_locations={"ego": ((1.0, 2.0, 3.0), (0.0, 0.0, 0.0, 1.0))},
    )

    class SlowScenarioApi:
        def restart(self) -> None:
            restart_started.set()
            if not release_restart.wait(timeout=5.0):
                raise TimeoutError("test did not release restart")
            current_scenario.transient_vehicles.pop("ego")
            current_scenario.vehicles.pop("ego")

    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(  # type: ignore[assignment]
        scenario=SlowScenarioApi(),
        _scenario=current_scenario,
    )
    restarting = asyncio.create_task(adapter.scenario_restart())

    try:
        assert await asyncio.to_thread(restart_started.wait, 2.0)
        restarting.cancel()
        release_restart.set()
        with pytest.raises(asyncio.CancelledError):
            await restarting

        assert current_scenario.vehicles == {}
        assert current_scenario.transient_vehicles == {}
        assert current_scenario._vehicle_locations == {}
    finally:
        release_restart.set()
        if not restarting.done():
            await restarting
        adapter._executor.shutdown(wait=True)


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
async def test_status_reads_retail_game_version_from_engine_lua(tmp_path: Path) -> None:
    class FakeSystem:
        def get_info(self, **_kwargs: object) -> dict[str, str]:
            return {"os": "Windows", "version": "10.0.26100"}

    class FakeControl:
        def __init__(self) -> None:
            self.calls: list[tuple[str, bool]] = []

        def queue_lua_command(self, chunk: str, response: bool = False) -> str:
            self.calls.append((chunk, response))
            return "0.38.6.0.19963"

    class FakeDriveBng:
        system = FakeSystem()

        def __init__(self) -> None:
            self.control = FakeControl()

        def tech_enabled(self) -> bool:
            return False

    bng = FakeDriveBng()
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = bng  # type: ignore[assignment]

    try:
        status = await adapter.status()

        assert status.version == "0.38.6.0.19963"
        assert bng.control.calls == [
            (
                "return tostring(beamng_version or beamng_versionb or 'unknown')",
                True,
            )
        ]
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


@pytest.mark.asyncio
async def test_scenario_list_preserves_built_in_display_names(
    tmp_path: Path,
) -> None:
    class ScenarioApi:
        def get_scenarios(self, _levels: list[str] | None) -> dict[str, list[object]]:
            return {
                "gridmap_v2": [
                    SimpleNamespace(
                        level="gridmap_v2",
                        name="mcp_addressable",
                        description="valid",
                        path="levels/gridmap_v2/scenarios/mcp_addressable.json",
                    ),
                    SimpleNamespace(
                        level="gridmap_v2",
                        name="A built-in scenario with spaces",
                        description="loadable built-in display name",
                        path="levels/gridmap_v2/scenarios/external.json",
                    ),
                ]
            }

    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(scenario=ScenarioApi())  # type: ignore[assignment]

    try:
        scenarios = await adapter.list_scenarios("gridmap_v2")

        assert [scenario.name for scenario in scenarios] == [
            "mcp_addressable",
            "A built-in scenario with spaces",
        ]
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scenario_load_accepts_an_enumerated_built_in_display_name(tmp_path: Path) -> None:
    display_name = "A built-in scenario with spaces"

    class ScenarioApi:
        def __init__(self) -> None:
            self.loaded: object | None = None

        def get_level_scenarios(self, _level: str) -> list[object]:
            return [
                SimpleNamespace(
                    name=display_name,
                    description="built in",
                    path="levels/gridmap_v2/scenarios/external.json",
                )
            ]

        def load(self, scenario: object) -> None:
            self.loaded = scenario

    scenario_api = ScenarioApi()
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = SimpleNamespace(scenario=scenario_api)  # type: ignore[assignment]

    try:
        info = await adapter.load_scenario(ScenarioSelector(level="gridmap_v2", name=display_name))

        assert info.name == display_name
        assert scenario_api.loaded is not None
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
async def test_direct_vehicle_control_can_override_local_inputs(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    fake = FakeVehicle()
    adapter._connected = True
    adapter._bng = object()  # type: ignore[assignment]
    adapter._vehicles["ego"] = fake  # type: ignore[assignment]
    await adapter.control_vehicle(
        VehicleControl(
            vehicle_id="ego",
            brake=0.0,
            parking_brake=0.0,
            shift_mode="arcade",
            is_adas=False,
        )
    )
    assert fake.shift_modes == ["arcade"]
    assert fake.lua_commands == [
        "local c=controller.getController('vehicleController');"
        "if c and c.setGearboxMode then c.setGearboxMode('arcade') end"
    ]
    assert fake.kwargs["brake"] == 0.0
    assert fake.kwargs["parkingbrake"] == 0.0
    assert fake.kwargs["is_adas"] is False
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
                [
                    ScenarioVehiclePlacement(
                        vehicle_id="ego",
                        model="etk800",
                        position=(1.0, 2.0, 100.0),
                        cling=False,
                    )
                ],
            )
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scenario_create_rejects_runtime_vehicle_spawn_models(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = FakeBng()  # type: ignore[assignment]

    try:
        with pytest.raises(ValueError, match="ScenarioVehiclePlacement"):
            await adapter.create_scenario(
                ScenarioRef(level="gridmap_v2", name="strict_placement"),
                [
                    VehicleSpawn(
                        vehicle_id="ego",
                        model="etk800",
                        position=(1.0, 2.0, 100.0),
                        cling=False,
                    )
                ],  # type: ignore[list-item]
                load=False,
            )
    finally:
        adapter._executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_scenario_create_caps_vehicle_count_before_engine_calls(tmp_path: Path) -> None:
    adapter = BeamNGpyAdapter(BeamNGSettings(), tmp_path)
    adapter._connected = True
    adapter._bng = FakeBng()  # type: ignore[assignment]
    vehicles = [
        ScenarioVehiclePlacement(
            vehicle_id=f"car_{index}",
            model="etk800",
            position=(float(index), 0.0, 100.0),
            cling=False,
        )
        for index in range(65)
    ]

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
