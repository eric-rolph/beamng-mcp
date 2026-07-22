"""Phase 2 live gate for the public Cannon Car Wash distribution artifact.

The package under test is the exact allowlisted Repository upload tree. Authoring
evidence and validation manifests are read from their source-only directories
and must never be copied into the disposable mod or resulting ZIP.
"""

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
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from beamng_mcp.config import Settings
from beamng_mcp.mcp_adapter import create_mcp_server
from examples.cannon_car_wash.build_distribution import EXPECTED_RUNTIME_FILES
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
    temporary_lua_bridge_config,
)

EXAMPLE_ROOT = Path(__file__).parents[1] / "examples" / "cannon_car_wash"
MOD_SOURCE = EXAMPLE_ROOT / "mod"
MOD_ID = "ericrolph_cannon_car_wash"
ASSET_RELATIVE_PATH = Path(f"art/shapes/{MOD_ID}/{MOD_ID}.dae")
GEOMETRY_MANIFEST_PATH = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}.geometry.json"
PHASE2_MANIFEST_PATH = EXAMPLE_ROOT / "validation" / "manifests" / "phase2.json"
VIRTUAL_ASSET_PATH = ASSET_RELATIVE_PATH.as_posix()
TRUCK_ID = f"{MOD_ID}_truck"
SCENARIO_VISUAL_ID = f"{MOD_ID}_scenario_visual"
LAUNCH_TRIGGER_ID = f"{MOD_ID}_launch_trigger"
WASH_TRIGGER_ID = f"{MOD_ID}_wash_activation_trigger"
REPAIR_TRIGGER_ID = f"{MOD_ID}_repair_trigger"
EXPECTED_EFFECT_COUNT = 16
EXPECTED_LIGHT_COUNT = 13
EXPECTED_EMITTER_COUNTS = {
    "BNGP_sprinkler": 6,
    "BNGP_waterfallsteam": 6,
    "BNGP_34": 2,
    "BNGP_2": 2,
}
PUBLIC_RUNTIME_FILES = frozenset(EXPECTED_RUNTIME_FILES)
PUBLIC_ROOTS = {"art", "levels", "lua", "vehicles"}


@dataclass(frozen=True, slots=True)
class FlatCorridor:
    road_id: str
    entrance_surface: tuple[float, float, float]
    downstream_surface: tuple[float, float, float]
    forward: tuple[float, float]
    length: float


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Cannon Car Wash Phase 2 gate"
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


def _copy_regular_file(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        pytest.fail(f"required regular Cannon Car Wash source file is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _stage_public_mod(
    workspace: Path, runtime_mod_name: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copy exactly the reviewed public-upload tree into a disposable workspace."""

    try:
        manifest = json.loads(GEOMETRY_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        pytest.fail(f"cannot read Cannon Car Wash geometry contract: {exc}")
    assert manifest["coordinate_system"] == "right-handed, meters, Z-up"
    assert manifest["drive_axis"] == [0.0, 1.0, 0.0]
    assert manifest["clear_opening"] == {
        "width": 6.2,
        "height": 4.48,
        "length": 18.0,
    }
    try:
        phase2_manifest = json.loads(PHASE2_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        pytest.fail(f"cannot read Cannon Car Wash Phase 2 contract: {exc}")
    assert phase2_manifest["schema_version"] == 1
    assert phase2_manifest["phase"] == 2
    assert phase2_manifest["phase3_launch_behavior_present"] is False
    assert phase2_manifest["asset"]["path"] == f"/{VIRTUAL_ASSET_PATH}"
    assert phase2_manifest["vehicle"]["name"] == TRUCK_ID
    assert phase2_manifest["wash_effects"]["visual_name"] == SCENARIO_VISUAL_ID
    assert phase2_manifest["trigger"]["name"] == LAUNCH_TRIGGER_ID
    assert phase2_manifest["wash_activation_trigger"]["name"] == WASH_TRIGGER_ID
    assert phase2_manifest["repair_trigger"]["name"] == REPAIR_TRIGGER_ID
    assert phase2_manifest["trigger"]["local_center"] == manifest["trigger"]["center"]
    assert phase2_manifest["trigger"]["dimensions"] == manifest["trigger"]["dimensions"]
    effects = phase2_manifest["wash_effects"]["effects"]
    assert len(effects) == EXPECTED_EFFECT_COUNT
    assert phase2_manifest["wash_effects"]["emitter_counts"] == EXPECTED_EMITTER_COUNTS
    assert {
        emitter: sum(effect["emitter"] == emitter for effect in effects)
        for emitter in EXPECTED_EMITTER_COUNTS
    } == EXPECTED_EMITTER_COUNTS

    source_files = {
        path.relative_to(MOD_SOURCE).as_posix(): path
        for path in MOD_SOURCE.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    assert len(PUBLIC_RUNTIME_FILES) == 40
    assert set(source_files) == PUBLIC_RUNTIME_FILES

    mod_root = workspace / "mods" / runtime_mod_name
    for relative in sorted(PUBLIC_RUNTIME_FILES):
        _copy_regular_file(source_files[relative], mod_root / Path(relative))

    staged_files = {
        path.relative_to(mod_root).as_posix() for path in mod_root.rglob("*") if path.is_file()
    }
    assert staged_files == PUBLIC_RUNTIME_FILES
    return manifest, phase2_manifest


def _zip_members(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def _middle_point(edge: object) -> tuple[float, float, float] | None:
    if not isinstance(edge, dict):
        return None
    value = edge.get("middle")
    if isinstance(value, dict):
        components = [value.get(axis) for axis in ("x", "y", "z")]
    elif isinstance(value, (list, tuple)):
        components = list(value)
    else:
        return None
    if len(components) != 3:
        return None
    try:
        point = (float(components[0]), float(components[1]), float(components[2]))
    except (TypeError, ValueError):
        return None
    return point if all(math.isfinite(component) for component in point) else None


def _corridor_candidate(
    road_id: str,
    points: list[tuple[float, float, float]],
    start_index: int,
    end_index: int,
) -> FlatCorridor | None:
    start = points[start_index]
    end = points[end_index]
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    planar_length = math.hypot(delta_x, delta_y)
    if not 28.0 <= planar_length <= 90.0:
        return None
    if abs(end[2] - start[2]) / planar_length > 0.015:
        return None
    forward = (delta_x / planar_length, delta_y / planar_length)
    right = (forward[1], -forward[0])
    previous_progress = -math.inf
    for point in points[start_index : end_index + 1]:
        relative = (point[0] - start[0], point[1] - start[1])
        progress = relative[0] * forward[0] + relative[1] * forward[1]
        lateral = abs(relative[0] * right[0] + relative[1] * right[1])
        expected_z = start[2] + (end[2] - start[2]) * progress / planar_length
        if progress + 0.1 < previous_progress or lateral > 1.0:
            return None
        if abs(point[2] - expected_z) > 0.18:
            return None
        previous_progress = progress
    return FlatCorridor(
        road_id=road_id,
        entrance_surface=start,
        downstream_surface=end,
        forward=forward,
        length=planar_length,
    )


async def _find_flat_corridor(session: Any) -> FlatCorridor:
    roads = _structured(
        await session.call_tool(
            "map_road_network",
            {"include_edges": True, "drivable_only": True, "limit": 1000},
        )
    )
    candidates: list[FlatCorridor] = []
    for road_id in (identifier for identifier in roads if identifier != "_meta"):
        result = await session.call_tool("map_road_edges", {"road_id": road_id})
        if result.isError or result.structuredContent is None:
            continue
        raw_edges = _structured(result)
        if not isinstance(raw_edges, list):
            continue
        points = [point for edge in raw_edges if (point := _middle_point(edge)) is not None]
        for start_index in range(len(points) - 1):
            for end_index in range(start_index + 1, len(points)):
                candidate = _corridor_candidate(road_id, points, start_index, end_index)
                if candidate is not None:
                    candidates.append(candidate)
    if not candidates:
        pytest.fail("Gridmap V2 exposed no straight, locally flat 28 m road corridor")
    return min(
        candidates,
        key=lambda item: (
            abs(item.downstream_surface[2] - item.entrance_surface[2]),
            abs(item.length - 40.0),
        ),
    )


def _asset_transform(
    corridor: FlatCorridor,
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    # Put the truck on the measured road point, three metres before the visual entrance.
    forward_x, forward_y = corridor.forward
    origin = (
        corridor.entrance_surface[0] + 12.0 * forward_x,
        corridor.entrance_surface[1] + 12.0 * forward_y,
        corridor.entrance_surface[2],
    )
    yaw = math.atan2(-forward_x, forward_y)  # local +Y -> road-forward
    rotation = (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))
    return origin, rotation


def _vehicle_rotation(corridor: FlatCorridor) -> tuple[float, float, float, float]:
    # BeamNG vehicles use local -Y as forward, unlike this Blender asset's +Y drive axis.
    forward_x, forward_y = corridor.forward
    yaw = math.atan2(forward_x, -forward_y)
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def _transform_local_point(
    origin: tuple[float, float, float],
    corridor: FlatCorridor,
    local: list[float],
) -> tuple[float, float, float]:
    forward_x, forward_y = corridor.forward
    right_x, right_y = forward_y, -forward_x
    return (
        origin[0] + local[0] * right_x + local[1] * forward_x,
        origin[1] + local[0] * right_y + local[1] * forward_y,
        origin[2] + local[2],
    )


async def _wait_for_bridge(session: Any) -> dict[str, Any]:
    last_result: Any = None
    for _ in range(80):
        last_result = await session.call_tool("lua_bridge_status", {"probe": True})
        if last_result.isError is False and last_result.structuredContent is not None:
            status = _structured(last_result)
            if (
                isinstance(status, dict)
                and status["connected"] is True
                and status["authenticated"] is True
            ):
                return status
        await asyncio.sleep(0.1)
    pytest.fail(f"authenticated Lua bridge did not become ready: {last_result}")


async def _settle_grounded_truck(
    session: Any,
    surface: tuple[float, float, float],
) -> dict[str, Any]:
    states: list[dict[str, Any]] = []
    for _ in range(16):
        stepped = _structured(
            await session.call_tool("simulation_control", {"action": "step", "steps": 30})
        )
        assert stepped["ok"] is True
        state = _structured(await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID}))
        states.append(state)
        if len(states) < 3:
            continue
        recent_z = [float(item["position"][2]) for item in states[-3:]]
        velocity = [float(component) for component in state["velocity"]]
        if (
            max(recent_z) - min(recent_z) <= 0.06
            and abs(velocity[2]) <= 0.2
            and math.hypot(velocity[0], velocity[1]) <= 0.35
        ):
            break
    else:
        pytest.fail(json.dumps({"reason": "truck did not settle", "states": states[-3:]}))

    final = states[-1]
    position = [float(component) for component in final["position"]]
    clearance = position[2] - surface[2]
    planar_drift = math.dist(position[:2], surface[:2])
    assert 0.05 <= clearance <= 1.40, {
        "reason": "truck spawned below the map or implausibly above the measured surface",
        "position": position,
        "surface": surface,
        "clearance": clearance,
    }
    assert planar_drift <= 1.0, {
        "reason": "truck drifted away while settling",
        "position": position,
        "surface": surface,
        "planar_drift": planar_drift,
    }
    return final


async def _wait_for_enter_event(session: Any, trigger_handle: str) -> dict[str, Any]:
    for _ in range(80):
        stepped = _structured(
            await session.call_tool("simulation_control", {"action": "step", "steps": 1})
        )
        assert stepped["ok"] is True
        await asyncio.sleep(0.05)
        events = _structured(
            await session.call_tool(
                "map_trigger_events",
                {"handle": trigger_handle, "after_sequence": 0, "limit": 10},
            )
        )
        enter = next((event for event in events["events"] if event["event"] == "enter"), None)
        if enter is not None:
            assert enter["subject_name"] == TRUCK_ID
            return enter
    trigger = _structured(await session.call_tool("map_trigger_get", {"handle": trigger_handle}))
    state = _structured(await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID}))
    pytest.fail(
        json.dumps(
            {
                "reason": "truck did not enter the exact Blender-derived trigger",
                "trigger": trigger,
                "vehicle": state,
            }
        )
    )


@pytest.mark.beamng_live
@pytest.mark.asyncio
async def test_cannon_car_wash_phase2_visual_placement_and_trigger(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    suffix = uuid.uuid4().hex[:10]
    runtime_mod_name = f"{MOD_ID}_phase2_{suffix}"
    scenario_name = f"cannon_wash_phase2_{suffix}"
    map_object_name = f"cannon_wash_asset_{suffix}"
    workspace = tmp_path / "workspace"
    manifest, phase2_manifest = _stage_public_mod(workspace, runtime_mod_name)

    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "gridmap_v2" / "scenarios" / scenario_name
    )
    scenario_info = scenario_directory / f"{scenario_name}.json"
    scenario_prefab = scenario_directory / f"{scenario_name}.prefab.json"

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
        scenario: Any | None = None
        owned_process: Any | None = None
        installed_path: Path | None = None
        trigger_handle: str | None = None
        probe_trigger_handle: str | None = None
        object_created = False
        normal_disconnect = False

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
                artifact = _structured(
                    await session.call_tool("mod_pack", {"mod_name": runtime_mod_name})
                )
                artifact_path = Path(artifact["path"])
                assert await asyncio.to_thread(artifact_path.is_file)
                names = await asyncio.to_thread(_zip_members, artifact_path)
                assert len(names) == len(PUBLIC_RUNTIME_FILES)
                assert names == PUBLIC_RUNTIME_FILES
                assert {name.partition("/")[0] for name in names} == PUBLIC_ROOTS
                installed = _structured(
                    await session.call_tool(
                        "mod_install",
                        {"mod_name": runtime_mod_name, "confirm": True, "overwrite": False},
                    )
                )
                installed_path = Path(installed["path"])
                assert await asyncio.to_thread(installed_path.is_file)

                reservation.release()
                connected = _structured(
                    await session.call_tool("simulator_connect", {"launch": True})
                )
                assert connected["connected"] is True
                bng = runtime.simulator._bng
                assert bng is not None
                owned_process = claim_owned_beamng_process(bng)

                available_scenarios = _structured(
                    await session.call_tool("scenario_list", {"level": "gridmap_v2"})
                )
                packaged_scenario = next(
                    (
                        item
                        for item in available_scenarios
                        if f"{MOD_ID}/{MOD_ID}.json"
                        in str(item.get("source_file", "")).replace("\\", "/")
                    ),
                    None,
                )
                assert packaged_scenario is not None, {
                    "reason": "installed Cannon Car Wash scenario was not discovered",
                    "scenarios": available_scenarios,
                }
                packaged_loaded = _structured(
                    await session.call_tool(
                        "scenario_load",
                        {
                            "ref": {
                                "level": "gridmap_v2",
                                "name": packaged_scenario["name"],
                            }
                        },
                    )
                )
                assert packaged_loaded["source_file"] == packaged_scenario["source_file"]
                packaged_started = _structured(
                    await session.call_tool("scenario_control", {"action": "start"})
                )
                assert packaged_started["ok"] is True
                packaged_bridge = await _wait_for_bridge(session)
                assert packaged_bridge["bridge_version"] == "0.3.0"
                packaged_deterministic = _structured(
                    await session.call_tool(
                        "simulation_control",
                        {
                            "action": "deterministic",
                            "steps_per_second": 60,
                            "speed_factor": 1,
                        },
                    )
                )
                assert packaged_deterministic["ok"] is True
                packaged_paused = _structured(
                    await session.call_tool("simulation_control", {"action": "pause"})
                )
                assert packaged_paused["ok"] is True
                packaged_asset = _structured(
                    await session.call_tool("map_object_get", {"object_id": SCENARIO_VISUAL_ID})
                )
                assert packaged_asset["class"] == "TSStatic"
                assert packaged_asset["managed"] is False
                assert packaged_asset["fields"]["shapeName"] == phase2_manifest["asset"]["path"]
                assert tuple(
                    packaged_asset["position"][axis] for axis in ("x", "y", "z")
                ) == pytest.approx(phase2_manifest["asset"]["position"])

                packaged_triggers = {
                    "launch": (LAUNCH_TRIGGER_ID, phase2_manifest["trigger"]),
                    "wash": (WASH_TRIGGER_ID, phase2_manifest["wash_activation_trigger"]),
                    "repair": (REPAIR_TRIGGER_ID, phase2_manifest["repair_trigger"]),
                }
                for trigger_name, trigger_contract in packaged_triggers.values():
                    packaged_trigger = _structured(
                        await session.call_tool("map_object_get", {"object_id": trigger_name})
                    )
                    assert packaged_trigger["class"] == "BeamNGTrigger"
                    assert packaged_trigger["managed"] is False
                    assert packaged_trigger["fields"]["triggerMode"] == trigger_contract["mode"]
                    assert (
                        packaged_trigger["fields"]["triggerTestType"]
                        == trigger_contract["test_type"]
                    )
                    assert tuple(
                        packaged_trigger["position"][axis] for axis in ("x", "y", "z")
                    ) == pytest.approx(trigger_contract["world_center"])
                    assert tuple(
                        packaged_trigger["scale"][axis] for axis in ("x", "y", "z")
                    ) == pytest.approx(trigger_contract["dimensions"])

                live_emitter_counts = {emitter: 0 for emitter in EXPECTED_EMITTER_COUNTS}
                for effect in phase2_manifest["wash_effects"]["effects"]:
                    packaged_effect = _structured(
                        await session.call_tool("map_object_get", {"object_id": effect["name"]})
                    )
                    assert packaged_effect["class"] == "ParticleEmitterNode"
                    assert packaged_effect["managed"] is False
                    assert packaged_effect["fields"]["dataBlock"] == "lightExampleEmitterNodeData1"
                    assert packaged_effect["fields"]["emitter"] == effect["emitter"]
                    live_emitter_counts[effect["emitter"]] += 1
                assert live_emitter_counts == EXPECTED_EMITTER_COUNTS

                assert phase2_manifest["lighting"]["light_count"] == EXPECTED_LIGHT_COUNT
                for light in phase2_manifest["lighting"]["lights"]:
                    packaged_light = _structured(
                        await session.call_tool("map_object_get", {"object_id": light["name"]})
                    )
                    assert packaged_light["class"] == light["class"]
                    assert packaged_light["managed"] is False
                    assert tuple(
                        packaged_light["position"][axis] for axis in ("x", "y", "z")
                    ) == pytest.approx(light["world_position"])
                    assert float(packaged_light["fields"]["brightness"]) == pytest.approx(
                        light["brightness"]
                    )
                    # The bridge's safe PointLight/SpotLight schema exposes the
                    # engine field as ``enabled``. Persistent prefab JSON uses
                    # Torque's serialized ``isEnabled`` spelling.
                    assert str(packaged_light["fields"]["enabled"]).lower() in {"1", "true"}

                packaged_ai_disabled = _structured(
                    await session.call_tool(
                        "vehicle_ai_configure",
                        {"config": {"vehicle_id": TRUCK_ID, "mode": "disabled"}},
                    )
                )
                assert packaged_ai_disabled["ok"] is True
                packaged_braked = _structured(
                    await session.call_tool(
                        "vehicle_control",
                        {
                            "command": {
                                "vehicle_id": TRUCK_ID,
                                "throttle": 0.0,
                                "brake": 1.0,
                                "parking_brake": 1.0,
                                "steering": 0.0,
                                "gear": 1,
                            }
                        },
                    )
                )
                assert packaged_braked["ok"] is True
                expected_truck_position = phase2_manifest["vehicle"]["position"]
                packaged_truck = await _settle_grounded_truck(
                    session,
                    (
                        float(expected_truck_position[0]),
                        float(expected_truck_position[1]),
                        float(phase2_manifest["asset"]["position"][2]),
                    ),
                )
                assert packaged_truck["model"] == "pickup"
                packaged_direction = [float(component) for component in packaged_truck["direction"]]
                expected_forward = phase2_manifest["vehicle"]["forward_axis_world"]
                packaged_alignment = (
                    packaged_direction[0] * expected_forward[0]
                    + packaged_direction[1] * expected_forward[1]
                ) / math.hypot(packaged_direction[0], packaged_direction[1])
                assert packaged_alignment >= 0.97, {
                    "reason": "packaged default D-Series is not facing the exit",
                    "direction": packaged_direction,
                    "expected_forward": expected_forward,
                }
                assert float(packaged_truck["speed_mps"]) <= 0.35
                packaged_stopped = _structured(
                    await session.call_tool("scenario_control", {"action": "stop"})
                )
                assert packaged_stopped["ok"] is True

                created = _structured(
                    await session.call_tool(
                        "scenario_create",
                        {
                            "ref": {"level": "gridmap_v2", "name": scenario_name},
                            "vehicles": [],
                            "description": "Disposable Cannon Car Wash Phase 2 live gate",
                            "load": True,
                        },
                    )
                )
                assert created["level"] == "gridmap_v2"
                assert created["name"] == scenario_name
                started = _structured(
                    await session.call_tool("scenario_control", {"action": "start"})
                )
                assert started["ok"] is True
                scenario = await runtime.simulator._call(bng.scenario.get_current)
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

                corridor = await _find_flat_corridor(session)
                spawn_position = [
                    corridor.entrance_surface[0],
                    corridor.entrance_surface[1],
                    corridor.entrance_surface[2] + 0.9,
                ]

                # BeamNGTrigger needs a valid player vehicle when the mission is
                # initialized.  A vehicle spawned into an otherwise empty scenario is
                # driveable through BeamNGpy, but BeamNG's trigger subsystem remains
                # uninitialized (the engine logs "Player vehicle not found") and no
                # onBeamNGTrigger callbacks are produced.  Rebuild the disposable
                # scenario with the D-Series as a persistent placement before creating
                # either the exact trigger or the independent control probe.
                stopped_empty = _structured(
                    await session.call_tool("scenario_control", {"action": "stop"})
                )
                assert stopped_empty["ok"] is True
                persistent = _structured(
                    await session.call_tool(
                        "scenario_create",
                        {
                            "ref": {"level": "gridmap_v2", "name": scenario_name},
                            "vehicles": [
                                {
                                    "vehicle_id": TRUCK_ID,
                                    "model": "pickup",
                                    "position": spawn_position,
                                    "rotation": _vehicle_rotation(corridor),
                                    "license_plate": "CANNON",
                                    "color": "White",
                                    "cling": False,
                                }
                            ],
                            "description": (
                                "Disposable Cannon Car Wash Phase 2 live gate with "
                                "persistent player truck"
                            ),
                            "load": True,
                            "overwrite": True,
                            "confirm_overwrite": True,
                        },
                    )
                )
                assert persistent["name"] == scenario_name
                started_persistent = _structured(
                    await session.call_tool("scenario_control", {"action": "start"})
                )
                assert started_persistent["ok"] is True
                scenario = await runtime.simulator._call(bng.scenario.get_current)
                rebuilt_bridge = await _wait_for_bridge(session)
                assert rebuilt_bridge["bridge_version"] == "0.3.0"
                persistent_deterministic = _structured(
                    await session.call_tool(
                        "simulation_control",
                        {
                            "action": "deterministic",
                            "steps_per_second": 60,
                            "speed_factor": 1,
                        },
                    )
                )
                assert persistent_deterministic["ok"] is True
                persistent_paused = _structured(
                    await session.call_tool("simulation_control", {"action": "pause"})
                )
                assert persistent_paused["ok"] is True

                asset_origin, asset_rotation = _asset_transform(corridor)
                asset = _structured(
                    await session.call_tool(
                        "map_object_create",
                        {
                            "mutation": {
                                "name": map_object_name,
                                "class_name": "TSStatic",
                                "position": asset_origin,
                                "rotation": asset_rotation,
                                "scale": [1.0, 1.0, 1.0],
                                "fields": {
                                    "shapeName": VIRTUAL_ASSET_PATH,
                                    "collisionType": "Collision Mesh",
                                    "decalType": "Collision Mesh",
                                },
                            }
                        },
                    )
                )
                object_created = True
                assert asset["class"] == "TSStatic"
                assert asset["managed"] is True
                fetched_asset = _structured(
                    await session.call_tool("map_object_get", {"object_id": map_object_name})
                )
                assert fetched_asset["fields"]["shapeName"] == VIRTUAL_ASSET_PATH
                assert tuple(fetched_asset["position"][axis] for axis in ("x", "y", "z")) == (
                    pytest.approx(asset_origin)
                )

                trigger_local = manifest["trigger"]["center"]
                trigger_dimensions = manifest["trigger"]["dimensions"]
                trigger_center_world = _transform_local_point(asset_origin, corridor, trigger_local)
                trigger_world = trigger_center_world
                trigger = _structured(
                    await session.call_tool(
                        "map_trigger_create",
                        {
                            "request": {
                                "position": {
                                    "x": trigger_world[0],
                                    "y": trigger_world[1],
                                    "z": trigger_world[2],
                                },
                                "rotation": {
                                    "x": asset_rotation[0],
                                    "y": asset_rotation[1],
                                    "z": asset_rotation[2],
                                    "w": asset_rotation[3],
                                },
                                "scale": {
                                    "x": trigger_dimensions[0],
                                    "y": trigger_dimensions[1],
                                    "z": trigger_dimensions[2],
                                },
                                "mode": str(phase2_manifest["trigger"]["mode"]).lower(),
                                "test_type": "bounding_box",
                                "debug": False,
                                "action": {
                                    "type": "emit_bridge_event",
                                    "events": ["enter", "exit"],
                                },
                            }
                        },
                    )
                )
                trigger_handle = trigger["handle"]
                enabled = _structured(
                    await session.call_tool(
                        "map_trigger_update",
                        {"patch": {"handle": trigger_handle, "enabled": True}},
                    )
                )
                assert enabled["enabled"] is True
                assert isinstance(enabled["object_id"], int)
                assert enabled["position"] == {
                    "x": pytest.approx(trigger_world[0]),
                    "y": pytest.approx(trigger_world[1]),
                    "z": pytest.approx(trigger_world[2]),
                }
                assert enabled["scale"] == {
                    "x": pytest.approx(trigger_dimensions[0]),
                    "y": pytest.approx(trigger_dimensions[1]),
                    "z": pytest.approx(trigger_dimensions[2]),
                }
                assert enabled["mode"] == "contains"
                actual_rotation = enabled["rotation"]
                rotation_dot = abs(
                    actual_rotation["x"] * asset_rotation[0]
                    + actual_rotation["y"] * asset_rotation[1]
                    + actual_rotation["z"] * asset_rotation[2]
                    + actual_rotation["w"] * asset_rotation[3]
                )
                assert rotation_dot == pytest.approx(1.0, abs=1e-6)

                # Validate each managed trigger in isolation. BeamNG's trigger event
                # routing is global, so a broad control volume must not remain live at
                # the same time as the exact asset-derived volume under test.
                disabled_exact = _structured(
                    await session.call_tool(
                        "map_trigger_update",
                        {"patch": {"handle": trigger_handle, "enabled": False}},
                    )
                )
                assert disabled_exact["enabled"] is False

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
                                "gear": 1,
                            }
                        },
                    )
                )
                assert braked["ok"] is True
                settled = await _settle_grounded_truck(session, corridor.entrance_surface)
                direction = [float(component) for component in settled["direction"]]
                planar_direction_length = math.hypot(direction[0], direction[1])
                alignment = (
                    direction[0] * corridor.forward[0] + direction[1] * corridor.forward[1]
                ) / planar_direction_length
                assert alignment >= 0.97, {
                    "reason": "default D-Series is not facing the car-wash exit",
                    "direction": direction,
                    "corridor_forward": corridor.forward,
                    "alignment": alignment,
                }

                # Prove the bridge event path independently before testing the exact,
                # Blender-sized marker. This mirrors the established trigger gauntlet.
                settled_position = [float(component) for component in settled["position"]]
                outside_probe = [
                    settled_position[0] - 12.0 * corridor.forward[0],
                    settled_position[1] - 12.0 * corridor.forward[1],
                    settled_position[2],
                ]
                moved_outside = _structured(
                    await session.call_tool(
                        "vehicle_teleport",
                        {
                            "command": {
                                "vehicle_id": TRUCK_ID,
                                "position": outside_probe,
                                "rotation": _vehicle_rotation(corridor),
                                "reset": True,
                            }
                        },
                    )
                )
                assert moved_outside["ok"] is True
                probe = _structured(
                    await session.call_tool(
                        "map_trigger_create",
                        {
                            "request": {
                                "position": {
                                    "x": settled_position[0],
                                    "y": settled_position[1],
                                    "z": settled_position[2],
                                },
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                                "scale": {"x": 6.0, "y": 6.0, "z": 6.0},
                                "mode": "overlaps",
                                "test_type": "bounding_box",
                                "debug": False,
                                "action": {
                                    "type": "emit_bridge_event",
                                    "events": ["enter", "exit"],
                                },
                            }
                        },
                    )
                )
                probe_trigger_handle = probe["handle"]
                probe_enabled = _structured(
                    await session.call_tool(
                        "map_trigger_update",
                        {"patch": {"handle": probe_trigger_handle, "enabled": True}},
                    )
                )
                assert probe_enabled["enabled"] is True
                for _ in range(3):
                    _structured(
                        await session.call_tool(
                            "simulation_control", {"action": "step", "steps": 1}
                        )
                    )
                moved_to_probe = _structured(
                    await session.call_tool(
                        "vehicle_teleport",
                        {
                            "command": {
                                "vehicle_id": TRUCK_ID,
                                "position": settled_position,
                                "rotation": _vehicle_rotation(corridor),
                                "reset": True,
                            }
                        },
                    )
                )
                assert moved_to_probe["ok"] is True
                probe_event = await _wait_for_enter_event(session, probe_trigger_handle)
                assert probe_event["trigger_id"] == probe_enabled["object_id"]
                deleted_probe = _structured(
                    await session.call_tool(
                        "map_trigger_delete",
                        {"handle": probe_trigger_handle, "confirm": True},
                    )
                )
                assert deleted_probe["deleted"] is True
                probe_trigger_handle = None

                enabled = _structured(
                    await session.call_tool(
                        "map_trigger_update",
                        {"patch": {"handle": trigger_handle, "enabled": True}},
                    )
                )
                assert enabled["enabled"] is True

                initial_events = _structured(
                    await session.call_tool(
                        "map_trigger_events",
                        {"handle": trigger_handle, "after_sequence": 0, "limit": 10},
                    )
                )
                assert initial_events["events"] == []
                # A thin drive-through slab can lie between the D-Series' sampled
                # front and rear bounding-box corners when its reference node is
                # teleported directly to the trigger center. Sweep the truck through
                # the exact volume so BeamNG observes the same boundary crossing as a
                # real low-speed approach.
                enter_event: dict[str, Any] | None = None
                entered_position: list[float] | None = None
                for step_index in range(49):
                    longitudinal_offset = -6.0 + step_index * 0.25
                    candidate_position = [
                        trigger_center_world[0] + longitudinal_offset * corridor.forward[0],
                        trigger_center_world[1] + longitudinal_offset * corridor.forward[1],
                        settled_position[2],
                    ]
                    teleported = _structured(
                        await session.call_tool(
                            "vehicle_teleport",
                            {
                                "command": {
                                    "vehicle_id": TRUCK_ID,
                                    "position": candidate_position,
                                    "rotation": _vehicle_rotation(corridor),
                                    "reset": True,
                                }
                            },
                        )
                    )
                    assert teleported["ok"] is True
                    stepped = _structured(
                        await session.call_tool(
                            "simulation_control", {"action": "step", "steps": 2}
                        )
                    )
                    assert stepped["ok"] is True
                    await asyncio.sleep(0.05)
                    page = _structured(
                        await session.call_tool(
                            "map_trigger_events",
                            {
                                "handle": trigger_handle,
                                "after_sequence": 0,
                                "limit": 10,
                            },
                        )
                    )
                    enter_event = next(
                        (event for event in page["events"] if event["event"] == "enter"),
                        None,
                    )
                    if enter_event is not None:
                        entered_position = candidate_position
                        break
                if enter_event is None or entered_position is None:
                    await _wait_for_enter_event(session, trigger_handle)
                    pytest.fail("unreachable trigger sweep fallback")
                assert enter_event["subject_name"] == TRUCK_ID
                assert enter_event["trigger_id"] == enabled["object_id"]
                entry_state = _structured(
                    await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID})
                )
                assert tuple(entry_state["position"][:2]) == pytest.approx(
                    entered_position[:2], abs=0.75
                )

                deleted_trigger = _structured(
                    await session.call_tool(
                        "map_trigger_delete", {"handle": trigger_handle, "confirm": True}
                    )
                )
                assert deleted_trigger["deleted"] is True
                trigger_handle = None
                deleted_object = _structured(
                    await session.call_tool(
                        "map_object_delete", {"object_id": map_object_name, "confirm": True}
                    )
                )
                assert deleted_object["deleted"] is True
                object_created = False
                stopped = _structured(
                    await session.call_tool("scenario_control", {"action": "stop"})
                )
                assert stopped["ok"] is True
                assert scenario is not None
                await runtime.simulator._call(scenario.delete, bng)
                scenario = None
                disconnected = _structured(await session.call_tool("simulator_disconnect", {}))
                assert disconnected["ok"] is True
                normal_disconnect = True
        finally:
            try:
                if bng is not None and not normal_disconnect:
                    with contextlib.suppress(Exception):
                        await runtime.emergency_stop(TRUCK_ID)
                    if trigger_handle is not None:
                        with contextlib.suppress(Exception):
                            await runtime.map_trigger_delete(trigger_handle, confirm=True)
                    if probe_trigger_handle is not None:
                        with contextlib.suppress(Exception):
                            await runtime.map_trigger_delete(probe_trigger_handle, confirm=True)
                    if object_created:
                        with contextlib.suppress(Exception):
                            await runtime.map_delete_object(map_object_name, confirm=True)
                    if scenario is None:
                        with contextlib.suppress(Exception):
                            candidate = await runtime.simulator._call(bng.scenario.get_current)
                            if getattr(candidate, "name", None) == scenario_name:
                                scenario = candidate
                    with contextlib.suppress(Exception):
                        await runtime.simulator.scenario_stop()
                    if scenario is not None:
                        with contextlib.suppress(Exception):
                            await runtime.simulator._call(scenario.delete, bng)
                    with contextlib.suppress(Exception):
                        await runtime.simulator.disconnect()
                if bng is not None:
                    cleanup_owned_beamng_session(bng, owned_process=owned_process)
            finally:
                timer.cancel()
                with contextlib.suppress(Exception):
                    await runtime.shutdown()
                cleanup_exact_live_artifacts(
                    profile=user,
                    files=tuple(
                        path
                        for path in (installed_path, scenario_info, scenario_prefab)
                        if path is not None
                    ),
                    empty_directories=(scenario_directory,),
                )
