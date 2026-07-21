"""Live Phase 3 gate for the packaged Cannon Car Wash Lua behavior."""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import shutil
import threading
import uuid
import zipfile
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from time import monotonic
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from beamng_mcp.config import Settings
from beamng_mcp.mcp_adapter import create_mcp_server
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    reserve_loopback_ports,
    temporary_lua_bridge_config,
)

MOD_SOURCE = Path(__file__).parents[1] / "examples" / "cannon_car_wash" / "mod"
PHASE2_MANIFEST = MOD_SOURCE / "mod_info" / "cannon_car_wash" / "phase2_manifest.json"
PHASE3_MANIFEST = MOD_SOURCE / "mod_info" / "cannon_car_wash" / "phase3_manifest.json"
PHASE4_MANIFEST = MOD_SOURCE / "mod_info" / "cannon_car_wash" / "phase4_manifest.json"
SCENARIO_FRAGMENT = "cannon_car_wash/cannon_car_wash.json"
TRUCK_ID = "cannon_car_wash_truck"
LOG_TAG = "CANNON_CAR_WASH"
LAUNCH_TRIGGER_NAME = "LaunchTrigger_Mesh"
WASH_TRIGGER_NAME = "WashActivationTrigger_Mesh"
EXPECTED_MISTER_COUNT = 12


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Cannon Car Wash Phase 3 gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Cannon Car Wash live gate requires a sentinel-isolated profile")
    return home, user, binary


def _structured(result: Any) -> Any:
    assert result.isError is False, result.content
    assert result.structuredContent is not None
    structured = result.structuredContent
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    return structured


def _stage_full_mod(workspace: Path, runtime_mod_name: str) -> Path:
    mod_root = workspace / "mods" / runtime_mod_name
    for source in MOD_SOURCE.rglob("*"):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(MOD_SOURCE)
        if relative.parts[0] == "mod_info":
            continue
        destination = mod_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    runtime_info = mod_root / "mod_info" / runtime_mod_name
    runtime_info.mkdir(parents=True, exist_ok=True)
    source_info = MOD_SOURCE / "mod_info" / "cannon_car_wash"
    for source in source_info.iterdir():
        if source.is_file() and not source.is_symlink():
            shutil.copy2(source, runtime_info / source.name)
    return mod_root


def _zip_members(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def _tagged_records(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.is_file():
        return []
    decoder = json.JSONDecoder()
    records: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if LOG_TAG not in line:
            continue
        start = line.find("{")
        if start < 0:
            continue
        with contextlib.suppress(json.JSONDecodeError):
            value, _ = decoder.raw_decode(line[start:])
            if isinstance(value, dict) and value.get("schema_version") == 1:
                records.append(value)
    return records


def _cannon_error_lines(log_path: Path) -> list[str]:
    if not log_path.is_file():
        return []
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [
        line
        for line in lines
        if "|E|" in line
        and (
            LOG_TAG in line
            or "cannon_car_wash" in line.casefold()
            or "cannon__car__wash" in line.casefold()
        )
    ]


async def _wait_for_bridge(session: Any) -> dict[str, Any]:
    for _ in range(80):
        result = await session.call_tool("lua_bridge_status", {"probe": True})
        if result.isError is False and result.structuredContent is not None:
            status = _structured(result)
            if status["connected"] is True and status["authenticated"] is True:
                return status
        await asyncio.sleep(0.1)
    pytest.fail("BeamNG MCP Lua bridge did not reconnect after scenario load")


async def _step(session: Any, steps: int) -> None:
    result = _structured(
        await session.call_tool("simulation_control", {"action": "step", "steps": steps})
    )
    assert result["ok"] is True


async def _wait_for_tagged_event(
    log_path: Path,
    event: str,
    *,
    attempts: int = 80,
) -> dict[str, Any]:
    for _ in range(attempts):
        matching = [record for record in _tagged_records(log_path) if record.get("event") == event]
        if matching:
            return matching[-1]
        await asyncio.sleep(0.1)
    pytest.fail(f"timed out waiting for {LOG_TAG} event {event!r}")


async def _wash_system_state(runtime: Any, bng: Any) -> dict[str, Any]:
    payload = await runtime.simulator._call(
        bng.control.queue_lua_command,
        "local extension = extensions['cannon__car__wash_main']; "
        "if not extension or not extension.getSystemState then "
        "return jsonEncode({error = 'cannon wash extension state unavailable'}); "
        "end; "
        "return jsonEncode(extension.getSystemState())",
        True,
    )
    state = json.loads(payload)
    assert "error" not in state, state
    return state


async def _wait_for_wash_system_state(
    runtime: Any,
    bng: Any,
    *,
    active: bool,
    attempts: int = 80,
) -> dict[str, Any]:
    expected_ambient = "1" if active else "0"
    expected_active_misters = EXPECTED_MISTER_COUNT if active else 0
    last_state: dict[str, Any] | None = None
    for _ in range(attempts):
        last_state = await _wash_system_state(runtime, bng)
        if (
            last_state.get("active") is active
            and int(last_state.get("mister_present_count", -1)) == EXPECTED_MISTER_COUNT
            and int(last_state.get("mister_expected_count", -1)) == EXPECTED_MISTER_COUNT
            and int(last_state.get("mister_active_count", -1)) == expected_active_misters
            and str(last_state.get("roller_play_ambient")) == expected_ambient
        ):
            return last_state
        await asyncio.sleep(0.1)
    pytest.fail(f"Cannon Car Wash systems did not become active={active}: {last_state}")


async def _trigger_scene_state(runtime: Any, bng: Any) -> dict[str, Any]:
    payload = await runtime.simulator._call(
        bng.control.queue_lua_command,
        f"local launch = scenetree.findObject('{LAUNCH_TRIGGER_NAME}'); "
        f"local wash = scenetree.findObject('{WASH_TRIGGER_NAME}'); "
        "local function describe(trigger) "
        "if not trigger then return nil end; "
        "return {"
        "name = trigger:getName(), "
        "class = trigger:getClassName(), "
        "mode = trigger:getField('triggerMode', 0), "
        "test_type = trigger:getField('triggerTestType', 0)"
        "}; "
        "end; "
        "return jsonEncode({launch = describe(launch), wash = describe(wash)})",
        True,
    )
    return json.loads(payload)


async def _vehicle_oobb_state(runtime: Any, bng: Any) -> dict[str, Any]:
    payload = await runtime.simulator._call(
        bng.control.queue_lua_command,
        f"local vehicle = scenetree.findObject('{TRUCK_ID}'); "
        "if not vehicle then return jsonEncode({error = 'vehicle missing'}) end; "
        "local id = vehicle:getId(); "
        "if not be:getObjectOOBBIsInitialized(id) then "
        "return jsonEncode({error = 'oobb not initialized'}) end; "
        "local center = vec3(be:getObjectOOBBCenterXYZ(id)); "
        "local a0 = vec3(be:getObjectOOBBHalfAxisXYZ(id, 0)); "
        "local a1 = vec3(be:getObjectOOBBHalfAxisXYZ(id, 1)); "
        "local a2 = vec3(be:getObjectOOBBHalfAxisXYZ(id, 2)); "
        "local extent = vec3("
        "math.abs(a0.x) + math.abs(a1.x) + math.abs(a2.x), "
        "math.abs(a0.y) + math.abs(a1.y) + math.abs(a2.y), "
        "math.abs(a0.z) + math.abs(a1.z) + math.abs(a2.z)); "
        "return jsonEncode({"
        "center = {center.x, center.y, center.z}, "
        "minimum = {center.x - extent.x, center.y - extent.y, center.z - extent.z}, "
        "maximum = {center.x + extent.x, center.y + extent.y, center.z + extent.z}, "
        "dimensions = {extent.x * 2, extent.y * 2, extent.z * 2}"
        "})",
        True,
    )
    return json.loads(payload)


async def _run_cannon_car_wash_live_gate(tmp_path: Path, *, phase: int) -> None:
    assert phase in {3, 4}
    home, user, binary = _configured_runtime()
    suffix = uuid.uuid4().hex[:10]
    runtime_mod_name = f"cannon_wash_phase{phase}_{suffix}"
    workspace = tmp_path / "workspace"
    _stage_full_mod(workspace, runtime_mod_name)
    phase2 = json.loads(PHASE2_MANIFEST.read_text(encoding="utf-8"))
    phase3 = json.loads(PHASE3_MANIFEST.read_text(encoding="utf-8"))
    phase4 = json.loads(PHASE4_MANIFEST.read_text(encoding="utf-8")) if phase == 4 else None
    log_path = user / "beamng.log"

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
        settings = Settings(
            beamng={
                "home": home,
                "binary": binary,
                "user": user,
                "port": tcom_port,
                "launch": True,
            },
            lua={
                "url": f"ws://127.0.0.1:{endpoint.port}",
                "token": endpoint.token,
                "request_timeout_seconds": 5.0,
            },
            workspace={
                "root": workspace,
                "allow_mod_install": True,
                "max_file_bytes": 16 * 1024 * 1024,
            },
        )
        mcp, runtime = create_mcp_server(settings)
        bng: Any | None = None
        owned_process: Any | None = None
        installed_path: Path | None = None
        normal_disconnect = False
        owned_process_cleaned = False

        def watchdog() -> None:
            active_bng = runtime.simulator._bng
            process = owned_process or (
                getattr(active_bng, "process", None) if active_bng is not None else None
            )
            if process is not None and process.poll() is None:
                process.terminate()

        timer = threading.Timer(240.0, watchdog)
        timer.daemon = True
        timer.start()
        try:
            async with create_connected_server_and_client_session(
                mcp,
                read_timeout_seconds=timedelta(seconds=120),
            ) as session:
                validation = _structured(
                    await session.call_tool("mod_validate", {"mod_name": runtime_mod_name})
                )
                assert validation["valid"] is True, validation["issues"]
                assert validation["issues"] == []
                artifact = _structured(
                    await session.call_tool("mod_pack", {"mod_name": runtime_mod_name})
                )
                artifact_path = Path(artifact["path"])
                members = _zip_members(artifact_path)
                assert "lua/ge/extensions/cannon_car_wash/main.lua" in members
                assert "scripts/cannon_car_wash/modScript.lua" in members
                installed = _structured(
                    await session.call_tool(
                        "mod_install",
                        {"mod_name": runtime_mod_name, "confirm": True, "overwrite": False},
                    )
                )
                installed_path = Path(installed["path"])

                reservation.release()
                connected = _structured(
                    await session.call_tool("simulator_connect", {"launch": True})
                )
                assert connected["connected"] is True
                bng = runtime.simulator._bng
                assert bng is not None
                owned_process = claim_owned_beamng_process(bng)

                scenarios = _structured(
                    await session.call_tool("scenario_list", {"level": "gridmap_v2"})
                )
                packaged = next(
                    (
                        item
                        for item in scenarios
                        if SCENARIO_FRAGMENT in str(item.get("source_file", "")).replace("\\", "/")
                    ),
                    None,
                )
                assert packaged is not None
                _structured(
                    await session.call_tool(
                        "scenario_load",
                        {"ref": {"level": "gridmap_v2", "name": packaged["name"]}},
                    )
                )
                started = _structured(
                    await session.call_tool("scenario_control", {"action": "start"})
                )
                assert started["ok"] is True
                bridge = await _wait_for_bridge(session)
                assert bridge["bridge_version"] == "0.3.0"
                deterministic = _structured(
                    await session.call_tool(
                        "simulation_control",
                        {
                            "action": "deterministic",
                            "steps_per_second": 60,
                            "speed_factor": 1,
                        },
                    )
                )
                assert deterministic["ok"] is True
                paused = _structured(
                    await session.call_tool("simulation_control", {"action": "pause"})
                )
                assert paused["ok"] is True
                session_record = await _wait_for_tagged_event(log_path, "session_start")
                session_number = int(session_record["session"])
                trigger_scene_state = await _trigger_scene_state(runtime, bng)
                assert trigger_scene_state["launch"]["name"] == LAUNCH_TRIGGER_NAME
                assert trigger_scene_state["launch"]["class"] == "BeamNGTrigger"
                assert trigger_scene_state["launch"]["mode"] == "Contains"
                assert trigger_scene_state["launch"]["test_type"] == "Bounding box"
                assert trigger_scene_state["wash"]["name"] == WASH_TRIGGER_NAME
                assert trigger_scene_state["wash"]["class"] == "BeamNGTrigger"
                assert trigger_scene_state["wash"]["mode"] == "Overlaps"
                assert trigger_scene_state["wash"]["test_type"] == "Bounding box"
                initial_wash_state = await _wait_for_wash_system_state(runtime, bng, active=False)
                assert int(initial_wash_state["subject_count"]) == 0
                if phase == 4:
                    assert phase4 is not None
                    crash_wall = _structured(
                        await session.call_tool("map_object_get", {"object_id": "CannonCrashWall"})
                    )
                    assert crash_wall["class"] == "TSStatic"
                    assert crash_wall["managed"] is False
                    assert crash_wall["fields"]["shapeName"] == phase4["crash_target"]["asset"]
                    assert tuple(
                        crash_wall["position"][axis] for axis in ("x", "y", "z")
                    ) == pytest.approx(phase4["crash_target"]["position"])

                disabled_ai = _structured(
                    await session.call_tool(
                        "vehicle_ai_configure",
                        {"config": {"vehicle_id": TRUCK_ID, "mode": "disabled"}},
                    )
                )
                assert disabled_ai["ok"] is True
                braked = _structured(
                    await session.call_tool(
                        "vehicle_control",
                        {
                            "command": {
                                "vehicle_id": TRUCK_ID,
                                "throttle": 0.0,
                                "brake": 1.0,
                                "parking_brake": 1.0,
                                "steering": 0.0,
                                "gear": 2,
                                "shift_mode": "realistic_automatic",
                                "is_adas": False,
                            }
                        },
                    )
                )
                assert braked["ok"] is True
                await _step(session, 60)
                initial_state = _structured(
                    await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID})
                )
                electrics_sensor_name = f"cannon_phase{phase}_electrics"
                attached_electrics = _structured(
                    await session.call_tool(
                        "sensor_attach",
                        {
                            "spec": {
                                "name": electrics_sensor_name,
                                "sensor_type": "electrics",
                                "vehicle_id": TRUCK_ID,
                            }
                        },
                    )
                )
                assert attached_electrics["ok"] is True
                damage_sensor_name: str | None = None
                initial_damage = 0.0
                if phase == 4:
                    damage_sensor_name = "cannon_phase4_damage"
                    attached_damage = _structured(
                        await session.call_tool(
                            "sensor_attach",
                            {
                                "spec": {
                                    "name": damage_sensor_name,
                                    "sensor_type": "damage",
                                    "vehicle_id": TRUCK_ID,
                                }
                            },
                        )
                    )
                    assert attached_damage["ok"] is True
                    initial_damage_reading = _structured(
                        await session.call_tool("sensor_poll", {"name": damage_sensor_name})
                    )
                    initial_damage = float(initial_damage_reading["data"]["damage"])
                forward = [float(value) for value in phase2["vehicle"]["forward_axis_world"]]
                rotation = phase2["vehicle"]["rotation_xyzw"]

                expected_spawn_z = float(phase2["vehicle"]["position"][2])
                assert abs(float(initial_state["position"][2]) - expected_spawn_z) <= 1.0

                resumed = _structured(
                    await session.call_tool("simulation_control", {"action": "resume"})
                )
                assert resumed["ok"] is True
                realtime = _structured(
                    await session.call_tool("simulation_control", {"action": "realtime"})
                )
                assert realtime["ok"] is True

                trigger_record: dict[str, Any] | None = None
                drive_states: list[dict[str, Any]] = []
                last_oobb: dict[str, Any] | None = None
                drive_deadline = monotonic() + 18.0
                while monotonic() < drive_deadline:
                    state = _structured(
                        await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID})
                    )
                    drive_states.append(state)
                    records = _tagged_records(log_path)
                    trigger_record = next(
                        (
                            record
                            for record in reversed(records)
                            if record.get("event") == "trigger_enter"
                            and int(record.get("session", 0)) == session_number
                            and int(record.get("run", 0)) > 0
                        ),
                        None,
                    )
                    if trigger_record is not None:
                        break

                    speed_mps = float(state["speed_mps"])
                    current_position = [float(value) for value in state["position"]]
                    current_progress = sum(
                        (current_position[axis] - float(initial_state["position"][axis]))
                        * forward[axis]
                        for axis in range(3)
                    )
                    if current_progress >= 10.0:
                        last_oobb = await _vehicle_oobb_state(runtime, bng)
                    if current_progress < -3.0 or current_progress > 24.0:
                        await session.call_tool(
                            "vehicle_control",
                            {
                                "command": {
                                    "vehicle_id": TRUCK_ID,
                                    "throttle": 0.0,
                                    "brake": 1.0,
                                    "parking_brake": 1.0,
                                    "steering": 0.0,
                                    "is_adas": False,
                                }
                            },
                        )
                        pytest.fail(
                            "truck left the guarded approach corridor before trigger entry: "
                            f"progress={current_progress:.3f} m, state={state}, "
                            f"oobb={last_oobb}, triggers={trigger_scene_state}"
                        )
                    if speed_mps < 3.0:
                        throttle, brake = 0.35, 0.0
                    elif speed_mps > 5.0:
                        throttle, brake = 0.0, 0.15
                    else:
                        throttle, brake = 0.12, 0.0
                    driven = _structured(
                        await session.call_tool(
                            "vehicle_control",
                            {
                                "command": {
                                    "vehicle_id": TRUCK_ID,
                                    "throttle": throttle,
                                    "brake": brake,
                                    "parking_brake": 0.0,
                                    "steering": 0.0,
                                    "gear": 2,
                                    "shift_mode": "realistic_automatic",
                                    "is_adas": False,
                                }
                            },
                        )
                    )
                    assert driven["ok"] is True
                    await asyncio.sleep(0.08)

                initial_position = [float(value) for value in initial_state["position"]]
                drive_progress = [
                    sum(
                        (float(state["position"][axis]) - initial_position[axis]) * forward[axis]
                        for axis in range(3)
                    )
                    for state in drive_states
                ]
                drive_diagnostics = {
                    "first": drive_states[0],
                    "last": drive_states[-1],
                    "maximum_progress_m": max(drive_progress),
                    "maximum_speed_mps": max(float(state["speed_mps"]) for state in drive_states),
                    "minimum_z": min(float(state["position"][2]) for state in drive_states),
                    "maximum_z": max(float(state["position"][2]) for state in drive_states),
                    "electrics": _structured(
                        await session.call_tool("sensor_poll", {"name": electrics_sensor_name})
                    )["data"],
                    "lua_errors": _cannon_error_lines(log_path),
                }
                assert trigger_record is not None, drive_diagnostics
                assert max(drive_progress) >= 10.0
                assert max(float(state["speed_mps"]) for state in drive_states) <= 8.0
                assert max(float(state["speed_mps"]) for state in drive_states) >= 1.0
                contained_oobb = await _vehicle_oobb_state(runtime, bng)
                assert "error" not in contained_oobb, contained_oobb
                trigger_center = [float(value) for value in phase2["trigger"]["world_center"]]
                trigger_dimensions = [float(value) for value in phase2["trigger"]["dimensions"]]
                trigger_minimum = [
                    trigger_center[axis] - trigger_dimensions[axis] / 2.0 for axis in range(3)
                ]
                trigger_maximum = [
                    trigger_center[axis] + trigger_dimensions[axis] / 2.0 for axis in range(3)
                ]
                assert all(
                    float(contained_oobb["minimum"][axis]) >= trigger_minimum[axis] - 1e-3
                    and float(contained_oobb["maximum"][axis]) <= trigger_maximum[axis] + 1e-3
                    for axis in range(3)
                ), {
                    "reason": "Contains event fired before the live D-Series OOBB was inside",
                    "oobb": contained_oobb,
                    "trigger_minimum": trigger_minimum,
                    "trigger_maximum": trigger_maximum,
                }
                active_wash_state = await _wait_for_wash_system_state(runtime, bng, active=True)
                assert int(active_wash_state["subject_count"]) >= 1

                hold_anchor = _structured(
                    await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID})
                )
                prelaunch_damage = initial_damage
                if damage_sensor_name is not None:
                    prelaunch_damage_reading = _structured(
                        await session.call_tool("sensor_poll", {"name": damage_sensor_name})
                    )
                    prelaunch_damage = float(prelaunch_damage_reading["data"]["damage"])
                hold_states: list[dict[str, Any]] = []
                launch_state: dict[str, Any] | None = None
                launch_samples: list[dict[str, Any]] = []
                deadline = monotonic() + 7.0
                while monotonic() < deadline:
                    await asyncio.sleep(0.08)
                    state = _structured(
                        await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID})
                    )
                    records = _tagged_records(log_path)
                    launched = any(
                        record.get("event") == "launch"
                        and record.get("run") == trigger_record["run"]
                        for record in records
                    )
                    if launched or float(state["speed_mps"]) >= 80.0:
                        launch_samples.append(state)
                        if phase == 3:
                            repaused = _structured(
                                await session.call_tool("simulation_control", {"action": "pause"})
                            )
                            assert repaused["ok"] is True
                            launch_samples.append(
                                _structured(
                                    await session.call_tool(
                                        "vehicle_state", {"vehicle_id": TRUCK_ID}
                                    )
                                )
                            )
                        launch_state = max(
                            launch_samples,
                            key=lambda sample: float(sample["speed_mps"]),
                        )
                        break
                    hold_states.append(state)
                if launch_state is None:
                    repaused = _structured(
                        await session.call_tool("simulation_control", {"action": "pause"})
                    )
                    assert repaused["ok"] is True
                assert launch_state is not None, _cannon_error_lines(log_path)
                assert hold_states

                anchor_position = [float(value) for value in hold_anchor["position"]]
                maximum_hold_drift = max(
                    math.dist(
                        anchor_position,
                        [float(value) for value in state["position"]],
                    )
                    for state in hold_states
                )
                maximum_hold_speed = max(float(state["speed_mps"]) for state in hold_states)
                assert maximum_hold_drift <= 0.30
                assert maximum_hold_speed <= 0.50

                peak_speed = float(launch_state["speed_mps"])
                assert peak_speed >= 83.333
                velocity = [float(value) for value in launch_state["velocity"]]
                direction = [float(value) for value in launch_state["direction"]]
                velocity_length = math.sqrt(sum(value * value for value in velocity))
                direction_length = math.sqrt(sum(value * value for value in direction))
                alignment = sum(velocity[axis] * direction[axis] for axis in range(3)) / (
                    velocity_length * direction_length
                )
                assert alignment >= 0.98

                phase4_telemetry: dict[str, Any] | None = None
                if phase == 4:
                    assert phase4 is not None
                    assert damage_sensor_name is not None
                    crash_started = monotonic()
                    crash_states = [launch_state]
                    damage_samples = [prelaunch_damage]
                    crash_deadline = crash_started + 5.0
                    speed_fraction = float(
                        phase4["acceptance"]["maximum_post_crash_speed_fraction"]
                    )
                    minimum_damage_delta = float(phase4["acceptance"]["minimum_damage_delta"])
                    while monotonic() < crash_deadline:
                        await asyncio.sleep(0.02)
                        crash_state = _structured(
                            await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID})
                        )
                        crash_damage = _structured(
                            await session.call_tool("sensor_poll", {"name": damage_sensor_name})
                        )
                        crash_states.append(crash_state)
                        damage_samples.append(float(crash_damage["data"]["damage"]))
                        observed_peak_speed = max(
                            float(sample["speed_mps"]) for sample in crash_states
                        )
                        if (
                            max(damage_samples) - prelaunch_damage >= minimum_damage_delta
                            and float(crash_state["speed_mps"])
                            <= observed_peak_speed * speed_fraction
                        ):
                            break

                    repaused = _structured(
                        await session.call_tool("simulation_control", {"action": "pause"})
                    )
                    assert repaused["ok"] is True
                    final_crash_state = _structured(
                        await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID})
                    )
                    final_damage = _structured(
                        await session.call_tool("sensor_poll", {"name": damage_sensor_name})
                    )
                    crash_states.append(final_crash_state)
                    damage_samples.append(float(final_damage["data"]["damage"]))

                    peak_speed = max(float(sample["speed_mps"]) for sample in crash_states)
                    peak_damage = max(damage_samples)
                    peak_damage_index = max(
                        range(len(damage_samples)), key=damage_samples.__getitem__
                    )
                    impact_state = crash_states[peak_damage_index]
                    impact_position = [float(value) for value in impact_state["position"]]
                    damage_delta = peak_damage - prelaunch_damage
                    minimum_post_crash_speed = min(
                        float(sample["speed_mps"]) for sample in crash_states[1:]
                    )
                    maximum_world_y = max(float(sample["position"][1]) for sample in crash_states)
                    assert peak_speed >= float(phase4["acceptance"]["minimum_launch_speed_mps"])
                    assert damage_delta >= minimum_damage_delta
                    assert minimum_post_crash_speed <= peak_speed * speed_fraction
                    assert maximum_world_y >= float(phase4["crash_target"]["impact_face_y"]) - 10.0
                    wall_minimum = phase4["crash_target"]["world_bounds"]["minimum"]
                    wall_maximum = phase4["crash_target"]["world_bounds"]["maximum"]
                    assert float(wall_minimum[0]) - 3.0 <= impact_position[0]
                    assert impact_position[0] <= float(wall_maximum[0]) + 3.0
                    assert float(wall_minimum[1]) - 6.0 <= impact_position[1]
                    assert impact_position[1] <= float(wall_maximum[1]) + 6.0
                    part_damage = final_damage["data"].get("part_damage") or {}
                    phase4_telemetry = {
                        "schema_version": 1,
                        "phase": 4,
                        "scenario": "Cannon Car Wash",
                        "vehicle": TRUCK_ID,
                        "approach": {
                            "forward_progress_m": max(drive_progress),
                            "peak_speed_mps": max(
                                float(sample["speed_mps"]) for sample in drive_states
                            ),
                            "minimum_z": min(
                                float(sample["position"][2]) for sample in drive_states
                            ),
                            "maximum_z": max(
                                float(sample["position"][2]) for sample in drive_states
                            ),
                        },
                        "hold": {
                            "maximum_drift_m": maximum_hold_drift,
                            "maximum_speed_mps": maximum_hold_speed,
                        },
                        "launch": {
                            "peak_speed_mps": peak_speed,
                            "peak_speed_kph": peak_speed * 3.6,
                            "forward_alignment": alignment,
                        },
                        "impact": {
                            "wall": phase4["crash_target"]["name"],
                            "initial_damage": initial_damage,
                            "prelaunch_damage": prelaunch_damage,
                            "peak_damage": peak_damage,
                            "damage_delta": damage_delta,
                            "position": impact_position,
                            "part_damage_count": len(part_damage),
                            "minimum_post_crash_speed_mps": minimum_post_crash_speed,
                            "maximum_world_y": maximum_world_y,
                            "sample_count": len(crash_states),
                            "observation_seconds": monotonic() - crash_started,
                        },
                    }

                removed_electrics = _structured(
                    await session.call_tool("sensor_remove", {"name": electrics_sensor_name})
                )
                assert removed_electrics["ok"] is True
                if damage_sensor_name is not None:
                    removed_damage = _structured(
                        await session.call_tool("sensor_remove", {"name": damage_sensor_name})
                    )
                    assert removed_damage["ok"] is True

                reset = _structured(
                    await session.call_tool(
                        "vehicle_teleport",
                        {
                            "command": {
                                "vehicle_id": TRUCK_ID,
                                "position": initial_state["position"],
                                "rotation": rotation,
                                "reset": True,
                            }
                        },
                    )
                )
                assert reset["ok"] is True
                await _step(session, 3)
                final_wash_state = await _wait_for_wash_system_state(runtime, bng, active=False)
                assert int(final_wash_state["subject_count"]) == 0
                stopped = _structured(
                    await session.call_tool("scenario_control", {"action": "stop"})
                )
                assert stopped["ok"] is True
                disconnected = _structured(await session.call_tool("simulator_disconnect", {}))
                assert disconnected["ok"] is True
                normal_disconnect = True
                cleanup_owned_beamng_session(bng, owned_process=owned_process)
                owned_process_cleaned = True

                session_records = [
                    record
                    for record in _tagged_records(log_path)
                    if int(record.get("session", 0)) == session_number
                ]
                run_records = [
                    record
                    for record in session_records
                    if record.get("run") == trigger_record["run"]
                ]
                event_names = [str(record.get("event")) for record in session_records]
                required_order = [
                    "wash_trigger_enter",
                    "wash_systems_start",
                    "containment_verified",
                    "trigger_enter",
                    "hold_start",
                    "countdown_3",
                    "countdown_timer_start",
                    "countdown_2",
                    "countdown_1",
                    "go",
                    "release",
                    "launch",
                ]
                cursor = -1
                for event in required_order:
                    cursor = event_names.index(event, cursor + 1)
                containment_record = next(
                    record
                    for record in run_records
                    if record.get("event") == "containment_verified"
                )
                assert containment_record["trigger_mode"] == "Contains"
                wash_start_record = next(
                    record
                    for record in session_records
                    if record.get("event") == "wash_systems_start"
                )
                assert int(wash_start_record["mister_count"]) == EXPECTED_MISTER_COUNT
                assert wash_start_record["mister_emitter"] == "BNGP_sprinkler"
                countdown = {
                    str(record["event"]): float(record["elapsed_time_seconds"])
                    for record in run_records
                    if record.get("event") in {"countdown_3", "countdown_2", "countdown_1", "go"}
                }
                assert countdown["countdown_2"] - countdown["countdown_3"] == pytest.approx(
                    phase3["countdown"]["interval_seconds"], abs=0.12
                )
                assert countdown["countdown_1"] - countdown["countdown_2"] == pytest.approx(
                    phase3["countdown"]["interval_seconds"], abs=0.12
                )
                assert countdown["go"] - countdown["countdown_1"] == pytest.approx(
                    phase3["countdown"]["interval_seconds"], abs=0.12
                )
                assert sum(event == "launch" for event in event_names) == 1
                assert _cannon_error_lines(log_path) == []
                wash_telemetry = {
                    "launch_trigger": trigger_scene_state["launch"],
                    "activation_trigger": trigger_scene_state["wash"],
                    "contained_vehicle_oobb": contained_oobb,
                    "initial": initial_wash_state,
                    "active_on_entry": active_wash_state,
                    "final": final_wash_state,
                }
                if phase4_telemetry is not None:
                    phase4_telemetry["countdown_elapsed_seconds"] = countdown
                    phase4_telemetry["ordered_lua_events"] = event_names
                    phase4_telemetry["wash_systems"] = wash_telemetry
                    phase4_telemetry["lua_errors"] = []
                    telemetry_path = tmp_path / "cannon_car_wash_phase4_telemetry.json"
                    telemetry_path.write_text(
                        json.dumps(phase4_telemetry, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    print("CANNON_PHASE4_TELEMETRY " + json.dumps(phase4_telemetry, sort_keys=True))
                else:
                    print(
                        "CANNON_PHASE3_TELEMETRY "
                        + json.dumps(
                            {
                                "ordered_lua_events": event_names,
                                "wash_systems": wash_telemetry,
                                "countdown_elapsed_seconds": countdown,
                                "lua_errors": [],
                            },
                            sort_keys=True,
                        )
                    )
        finally:
            try:
                if bng is not None and not normal_disconnect:
                    with contextlib.suppress(Exception):
                        await runtime.emergency_stop(TRUCK_ID)
                    with contextlib.suppress(Exception):
                        await runtime.simulator.scenario_stop()
                    with contextlib.suppress(Exception):
                        await runtime.simulator.disconnect()
                if bng is not None and not owned_process_cleaned:
                    cleanup_owned_beamng_session(bng, owned_process=owned_process)
            finally:
                timer.cancel()
                with contextlib.suppress(Exception):
                    await runtime.shutdown()
                cleanup_exact_live_artifacts(
                    profile=user,
                    files=(installed_path,) if installed_path is not None else (),
                )


@pytest.mark.beamng_live
@pytest.mark.asyncio
async def test_cannon_car_wash_phase3_countdown_hold_and_launch(tmp_path: Path) -> None:
    await _run_cannon_car_wash_live_gate(tmp_path, phase=3)
