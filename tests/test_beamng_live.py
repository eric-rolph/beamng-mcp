from __future__ import annotations

import asyncio
import os
import threading
import uuid
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from beamngpy import BeamNGpy, Scenario, Vehicle
from beamngpy.sensors import Electrics, State

from beamng_mcp.adapters.lua_bridge import LuaBridgeClient
from beamng_mcp.config import LuaSettings
from tests.live_support import (
    TemporaryLuaEndpoint,
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
    temporary_lua_bridge_config,
)


def _live_paths() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the isolated live simulator test"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not user.is_dir():
        pytest.fail(f"isolated BeamNG user directory does not exist: {user}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("live tests require an explicitly marked isolated BeamNG user folder")
    return home, user, binary


def _open_and_claim_with_lua_bridge(bng: Any, port_reservation: Any) -> Any:
    port_reservation.release()
    bng.open(
        launch=True,
        listen_ip="127.0.0.1",
    )
    process = claim_owned_beamng_process(bng)
    bng.control.queue_lua_command("extensions.load('beamng_mcp/bridge')")
    return process


async def _probe_real_lua_bridge(endpoint: TemporaryLuaEndpoint) -> None:
    client = LuaBridgeClient(
        LuaSettings(
            url=f"ws://127.0.0.1:{endpoint.port}",
            token=endpoint.token,
            request_timeout_seconds=5.0,
        )
    )
    try:
        status = await client.probe()
        assert status.connected is True
        assert status.authenticated is True
        assert status.bridge_version == "0.2.0"
        snapshot = await client.call("telemetry.snapshot")
        assert isinstance(snapshot, dict)
    finally:
        await client.close()


def test_lua_bridge_load_occurs_only_after_launched_process_is_claimed() -> None:
    events: list[str] = []
    process = SimpleNamespace(poll=lambda: None)
    bng = SimpleNamespace(process=process, quit_on_close=False)

    def open_beamng(**kwargs: object) -> None:
        assert "extensions" not in kwargs
        events.append("open")

    def load_extension(chunk: str) -> None:
        assert bng.quit_on_close is True
        assert chunk == "extensions.load('beamng_mcp/bridge')"
        events.append("load")

    bng.open = open_beamng
    bng.control = SimpleNamespace(queue_lua_command=load_extension)
    reservation = SimpleNamespace(release=lambda: events.append("release"))

    claimed = _open_and_claim_with_lua_bridge(bng, reservation)

    assert claimed is process
    assert events == ["release", "open", "load"]


def test_live_path_discovery_preserves_a_linked_profile_for_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    binary = home / "BeamNG.drive.x64.exe"
    binary.touch()
    real_user = tmp_path / "real-current"
    real_user.mkdir()
    (real_user / ".beamng-mcp-test-user").touch()
    linked_user = tmp_path / "current"
    try:
        linked_user.symlink_to(real_user, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory links are unavailable on this host: {exc}")
    monkeypatch.setenv("BEAMNG_MCP_TEST_BEAMNG_HOME", str(home))
    monkeypatch.setenv("BEAMNG_MCP_TEST_BEAMNG_USER", str(linked_user))
    monkeypatch.setenv("BEAMNG_MCP_TEST_BEAMNG_BINARY", str(binary))

    _, discovered_user, _ = _live_paths()

    assert discovered_user == Path(os.path.abspath(linked_user))
    assert discovered_user.is_symlink()


async def _exercise_real_lua_map_objects(endpoint: TemporaryLuaEndpoint) -> None:
    client = LuaBridgeClient(
        LuaSettings(
            url=f"ws://127.0.0.1:{endpoint.port}",
            token=endpoint.token,
            request_timeout_seconds=5.0,
        )
    )
    name = f"beamng_mcp_light_{uuid.uuid4().hex[:12]}"
    created = False
    try:
        result = await client.call(
            "world.create_object",
            {
                "name": name,
                "class": "PointLight",
                "position": [2.0, 3.0, 4.0],
                "rotation": [0.0, 0.0, 0.0, 1.0],
                "scale": [1.0, 1.0, 1.0],
                "fields": {
                    "color": [0.2, 0.4, 0.8, 1.0],
                    "brightness": 1.5,
                    "range": 12.0,
                    "castShadows": False,
                    "enabled": True,
                },
            },
        )
        created = True
        assert result["name"] == name
        assert result["class"] == "PointLight"
        assert result["managed"] is True

        fetched = await client.call("world.get_object", {"name": name})
        assert fetched["position"] == {"x": 2.0, "y": 3.0, "z": 4.0}
        updated = await client.call(
            "world.update_object",
            {
                "name": name,
                "position": [5.0, 6.0, 7.0],
                "fields": {"brightness": 2.0, "enabled": False},
            },
        )
        assert updated["position"] == {"x": 5.0, "y": 6.0, "z": 7.0}

        listing = await client.call(
            "world.list_objects", {"class": "PointLight", "name_prefix": name, "limit": 10}
        )
        assert any(item["name"] == name for item in listing["objects"])
    finally:
        if created:
            deleted = await client.call("world.delete_object", {"name": name, "confirm": True})
            assert deleted["deleted"] is True
        await client.close()


@pytest.mark.beamng_live
def test_isolated_live_beamng_scenario_bridge_and_vehicle_control() -> None:
    home, user, binary = _live_paths()
    launch_user = user.parent if user.name.casefold() == "current" else user
    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(2))
        tcom_port, lua_port = reservation.ports
        endpoint = safety.enter_context(temporary_lua_bridge_config(user, lua_port))
        bng = BeamNGpy(
            "127.0.0.1",
            tcom_port,
            home=str(home),
            binary=str(binary),
            user=str(launch_user),
            quit_on_close=False,
            headless=True,
            nogpu=True,
        )
        scenario: Scenario | None = None
        scenario_directory: Path | None = None
        owned_process: object | None = None

        def watchdog() -> None:
            process = bng.process
            if process is not None and process.poll() is None:
                process.terminate()

        timer = threading.Timer(180.0, watchdog)
        timer.daemon = True
        timer.start()
        try:
            owned_process = _open_and_claim_with_lua_bridge(bng, reservation)
            assert bng.connection.skt is not None
            assert bng.tech_enabled() is False
            assert bng.scenario.get_scenarios(None)
            asyncio.run(_probe_real_lua_bridge(endpoint))

            scenario = Scenario(
                "gridmap_v2",
                f"beamng_mcp_live_{uuid.uuid4().hex[:12]}",
                description="Disposable beamng-mcp live integration fixture",
            )
            scenario_directory = require_confined_profile_target(
                user,
                Path("levels") / "gridmap_v2" / "scenarios" / scenario.name,
            )
            vehicle = Vehicle("ego", "etk800", license="MCPTEST", color="White")
            scenario.add_vehicle(vehicle, pos=(0.0, 0.0, 0.5), cling=True)
            scenario.make(bng)

            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            assert vehicle.is_connected() is True

            vehicle.sensors.attach("state_extra", State())
            vehicle.sensors.attach("electrics", Electrics())
            vehicle.control(throttle=0.0, brake=1.0, parkingbrake=1.0, is_adas=True)
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)
            vehicle.sensors.poll()
            readings = vehicle.sensors.data
            assert "state_extra" in readings
            assert "electrics" in readings
            assert len(readings["state_extra"]["pos"]) == 3

            network = bng.scenario.get_road_network(include_edges=True, drivable_only=True)
            assert isinstance(network, dict)
            asyncio.run(_probe_real_lua_bridge(endpoint))
            asyncio.run(_exercise_real_lua_map_objects(endpoint))
        finally:
            try:
                cleanup_owned_beamng_session(
                    bng,
                    owned_process=owned_process,
                    scenario=scenario,
                )
            finally:
                timer.cancel()
                cleanup_exact_live_artifacts(
                    profile=user,
                    empty_directories=(scenario_directory,)
                    if scenario_directory is not None
                    else (),
                )
