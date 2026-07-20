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
from beamng_mcp.errors import LuaBridgeError
from beamng_mcp.runtime import Runtime
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
        assert status.bridge_version == "0.3.0"
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

        with pytest.raises(LuaBridgeError, match="bridge-managed map object"):
            await client.call("extension.reload", {"name": "beamng_mcp/bridge"})

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


def _trigger_create_params(
    handle: str,
    position: tuple[float, float, float],
) -> dict[str, Any]:
    return {
        "handle": handle,
        "shape": "box",
        "position": {"x": position[0], "y": position[1], "z": position[2]},
        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "scale": {"x": 6.0, "y": 6.0, "z": 6.0},
        "mode": "center",
        "test_type": "bounding_box",
        "debug": False,
        "action": {"type": "emit_bridge_event", "events": ["enter", "exit"]},
    }


def _trigger_events(client: LuaBridgeClient, handle: str) -> list[dict[str, Any]]:
    return [
        event["params"]
        for event in client.recent_events(limit=256)
        if event.get("method") == "trigger.event"
        and isinstance(event.get("params"), dict)
        and event["params"].get("handle") == handle
    ]


async def _wait_for_trigger_event_sequence(
    client: LuaBridgeClient,
    bng: BeamNGpy,
    handle: str,
    expected: list[str],
) -> list[dict[str, Any]]:
    for _ in range(60):
        bng.control.step(1, wait=True)
        await asyncio.sleep(0.05)
        events = _trigger_events(client, handle)
        if [event["event"] for event in events] == expected:
            return events
    events = _trigger_events(client, handle)
    pytest.fail(
        "timed out waiting for trigger events "
        f"{expected!r}; observed {[event['event'] for event in events]!r}"
    )


async def _exercise_real_lua_triggers(
    endpoint: TemporaryLuaEndpoint,
    bng: BeamNGpy,
    vehicle: Vehicle,
    origin: tuple[float, float, float],
) -> None:
    settings = LuaSettings(
        url=f"ws://127.0.0.1:{endpoint.port}",
        token=endpoint.token,
        request_timeout_seconds=5.0,
    )
    owner = LuaBridgeClient(settings)
    intruder = LuaBridgeClient(settings)
    replacement = LuaBridgeClient(settings)
    owner_open = False
    intruder_open = False
    replacement_open = False
    handle = "trg_" + uuid.uuid4().hex
    center = (origin[0] + 12.0, origin[1], origin[2] + 0.5)
    spec = _trigger_create_params(handle, center)
    try:
        await owner.connect()
        owner_open = True
        await intruder.connect()
        intruder_open = True

        draft = await owner.call("trigger.create", spec)
        assert draft["handle"] == handle
        assert draft["enabled"] is False
        assert draft.get("object_id") is None
        assert draft["persistent"] is False
        assert _trigger_events(owner, handle) == []

        with pytest.raises(LuaBridgeError, match="managed trigger"):
            await owner.call("extension.reload", {"name": "beamng_mcp/bridge"})

        fetched = await owner.call("trigger.get", {"handle": handle})
        assert fetched == draft
        with pytest.raises(LuaBridgeError, match="trigger was not found"):
            await intruder.call("trigger.get", {"handle": handle})

        with pytest.raises(LuaBridgeError, match="class is not in the creation allowlist"):
            await owner.call(
                "world.create_object",
                {
                    "name": "beamng_mcp_injected_trigger",
                    "class": "BeamNGTrigger",
                    "position": [0.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0, 1.0],
                    "scale": [1.0, 1.0, 1.0],
                    "fields": {},
                },
            )
        with pytest.raises(LuaBridgeError, match="unknown field"):
            await owner.call(
                "trigger.create",
                {
                    **_trigger_create_params("trg_" + uuid.uuid4().hex, center),
                    "luaFunction": "onInjectedCallback",
                },
            )
        with pytest.raises(LuaBridgeError, match="unknown field"):
            await owner.call(
                "trigger.update",
                {"handle": handle, "name": "spoofed_mission_trigger", "enabled": True},
            )
        assert (await owner.call("trigger.get", {"handle": handle}))["enabled"] is False

        vehicle.teleport(origin, reset=True)
        bng.control.step(3, wait=True)
        enabled = await owner.call("trigger.update", {"handle": handle, "enabled": True})
        assert enabled["enabled"] is True
        assert isinstance(enabled["object_id"], int)
        assert enabled["engine_name"] == "beamng_mcp_trigger_" + handle.removeprefix("trg_")
        bng.control.step(3, wait=True)
        await asyncio.sleep(0.1)
        assert _trigger_events(owner, handle) == []

        with pytest.raises(LuaBridgeError, match="enabled triggers are immutable"):
            await owner.call(
                "trigger.update",
                {"handle": handle, "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
            )

        vehicle.teleport(center, reset=True)
        events = await _wait_for_trigger_event_sequence(owner, bng, handle, ["enter"])
        assert events[0]["subject_name"] == "ego"
        assert events[0]["trigger_id"] == enabled["object_id"]

        vehicle.teleport(origin, reset=True)
        events = await _wait_for_trigger_event_sequence(owner, bng, handle, ["enter", "exit"])
        assert [event["sequence"] for event in events] == [1, 2]
        assert [event["count"] for event in events] == [1, 2]

        observed = await owner.call("trigger.get", {"handle": handle})
        assert observed["count"] == 2
        assert observed["last_event"]["event"] == "exit"
        assert observed["last_event"]["subject_name"] == "ego"

        # Exercise the same typed, ownership-checked cursor path exposed by the
        # MCP tool, not only the bridge client's private receive queue.
        runtime = object.__new__(Runtime)
        runtime.lua = owner
        page = await runtime.map_trigger_events(handle, after_sequence=0, limit=10)
        assert [event.event for event in page.events] == ["enter", "exit"]
        assert page.next_sequence == 2
        assert page.latest_sequence == 2
        assert page.truncated is False
        assert page.has_more is False

        disabled = await owner.call("trigger.update", {"handle": handle, "enabled": False})
        assert disabled["enabled"] is False
        assert disabled.get("object_id") is None
        bng.control.step(2, wait=True)
        reenabled = await owner.call("trigger.update", {"handle": handle, "enabled": True})
        assert reenabled["enabled"] is True
        assert isinstance(reenabled["object_id"], int)
        await owner.call("trigger.update", {"handle": handle, "enabled": False})
        bng.control.step(2, wait=True)
        with pytest.raises(LuaBridgeError, match="confirm"):
            await owner.call("trigger.delete", {"handle": handle, "confirm": False})
        deleted = await owner.call("trigger.delete", {"handle": handle, "confirm": True})
        assert deleted == {"deleted": True, "handle": handle}
        assert (await owner.call("trigger.list", {"limit": 10}))["count"] == 0

        rotated_handle = "trg_" + uuid.uuid4().hex
        rotated_spec = _trigger_create_params(rotated_handle, center)
        rotated_spec["rotation"] = {
            "x": 0.0,
            "y": 0.0,
            "z": 0.3826834323650898,
            "w": 0.9238795325112867,
        }
        # Keep every dimension non-degenerate for deterministic teleport-based
        # crossing; very thin BeamNG volumes are test-type/motion dependent.
        rotated_spec["scale"] = {"x": 8.0, "y": 6.0, "z": 3.0}
        rotated_spec["mode"] = "overlaps"
        rotated_spec["action"] = {
            "type": "emit_bridge_event",
            "events": ["exit"],
        }
        await owner.call("trigger.create", rotated_spec)
        rotated_live = await owner.call(
            "trigger.update", {"handle": rotated_handle, "enabled": True}
        )
        assert rotated_live["enabled"] is True

        # Enter is intentionally filtered, but it must still update occupancy
        # so each following exit is emitted and the next cycle can re-arm.
        for expected_exits in (["exit"], ["exit", "exit"]):
            vehicle.teleport(center, reset=True)
            bng.control.step(3, wait=True)
            await asyncio.sleep(0.1)
            assert [event["event"] for event in _trigger_events(owner, rotated_handle)] == ["exit"][
                : len(expected_exits) - 1
            ]
            vehicle.teleport(origin, reset=True)
            rotated_events = await _wait_for_trigger_event_sequence(
                owner,
                bng,
                rotated_handle,
                expected_exits,
            )
        assert [event["sequence"] for event in rotated_events] == [1, 2]
        await owner.call("trigger.update", {"handle": rotated_handle, "enabled": False})
        await owner.call("trigger.delete", {"handle": rotated_handle, "confirm": True})

        cleanup_handle = "trg_" + uuid.uuid4().hex
        cleanup_spec = _trigger_create_params(cleanup_handle, center)
        await owner.call("trigger.create", cleanup_spec)
        cleanup_live = await owner.call(
            "trigger.update", {"handle": cleanup_handle, "enabled": True}
        )
        assert cleanup_live["enabled"] is True
        await owner.close()
        owner_open = False
        bng.control.step(3, wait=True)
        await asyncio.sleep(0.1)

        await replacement.connect()
        replacement_open = True
        replacement_draft: dict[str, Any] | None = None
        last_cleanup_error: LuaBridgeError | None = None
        # BeamNG's WebSocket wrapper may surface a clean close only through the
        # stale-peer path. Allow longer than the 12-second test timeout while
        # continuing to drive engine updates; a healthy client still pings at 5s.
        for _ in range(64):
            try:
                replacement_draft = await replacement.call("trigger.create", cleanup_spec)
                break
            except LuaBridgeError as exc:
                if not any(
                    text in str(exc)
                    for text in (
                        "trigger handle already exists",
                        "reserved trigger name is unavailable",
                    )
                ):
                    raise
                last_cleanup_error = exc
                bng.control.step(1, wait=True)
                await asyncio.sleep(0.25)
        if replacement_draft is None:
            pytest.fail(f"disconnected trigger owner was not reclaimed: {last_cleanup_error}")
        assert replacement_draft["enabled"] is False
        replacement_live = await replacement.call(
            "trigger.update", {"handle": cleanup_handle, "enabled": True}
        )
        assert replacement_live["enabled"] is True
        await replacement.call("trigger.update", {"handle": cleanup_handle, "enabled": False})
        await replacement.call("trigger.delete", {"handle": cleanup_handle, "confirm": True})
    finally:
        if owner_open:
            await owner.close()
        if intruder_open:
            await intruder.close()
        if replacement_open:
            await replacement.close()


@pytest.mark.beamng_live
def test_isolated_live_beamng_scenario_bridge_and_vehicle_control() -> None:
    home, user, binary = _live_paths()
    launch_user = user.parent if user.name.casefold() == "current" else user
    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(2))
        tcom_port, lua_port = reservation.ports
        endpoint = safety.enter_context(
            temporary_lua_bridge_config(
                user,
                lua_port,
                heartbeat_interval_seconds=1.0,
                heartbeat_timeout_seconds=12.0,
            )
        )
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
            origin = tuple(float(component) for component in readings["state_extra"]["pos"])
            asyncio.run(_exercise_real_lua_triggers(endpoint, bng, vehicle, origin))
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
