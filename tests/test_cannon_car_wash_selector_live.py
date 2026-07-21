"""Isolated BeamNG gate for Cannon Car Wash vehicle-selector discovery and spawn."""

from __future__ import annotations

import contextlib
import json
import math
import threading
import uuid
import zipfile
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
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
from tests.test_cannon_car_wash_phase3_live import (
    _configured_runtime,
    _stage_full_mod,
    _structured,
    _wait_for_bridge,
)

MOD_ID = "ericrolph_cannon_car_wash"
MODEL_ID = MOD_ID
CONFIG_ID = "standard"
PROP_ID = f"{MOD_ID}_selector"
TRUCK_ID = f"{MOD_ID}_truck"
SELECTOR_VISUAL_NAME = f"{MOD_ID}_selector_visual"
PHYSICS_GROUP_NAME = f"{MOD_ID}_physics"
SCENARIO_FRAGMENT = f"{MOD_ID}/{MOD_ID}.json"
SPAWN_POSITION = [-110.0, -170.0, 100.12]
EXPECTED_SURFACE_Z = 100.0

EXPECTED_RUNTIME_FILES = {
    f"vehicles/{MOD_ID}/{MOD_ID}.dae",
    f"vehicles/{MOD_ID}/{MOD_ID}.jbeam",
    f"vehicles/{MOD_ID}/default.jpg",
    f"vehicles/{MOD_ID}/info.json",
    f"vehicles/{MOD_ID}/info_{CONFIG_ID}.json",
    f"vehicles/{MOD_ID}/main.materials.json",
    f"vehicles/{MOD_ID}/{CONFIG_ID}.jpg",
    f"vehicles/{MOD_ID}/{CONFIG_ID}.pc",
    f"levels/gridmap_v2/art/shapes/{MOD_ID}/{MOD_ID}.dae",
    f"levels/gridmap_v2/art/shapes/{MOD_ID}/{MOD_ID}.materials.json",
    f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.json",
    f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.lua",
    f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.prefab.json",
    f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.jpg",
}


def _zip_members(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def _selector_error_lines(log_path: Path) -> list[str]:
    if not log_path.is_file():
        return []
    relevant_tokens = (
        MOD_ID,
        f"scenario_{MOD_ID}",
        f"{MOD_ID}_selector_visual",
        f"{MOD_ID}_selector_",
    )
    issues: list[str] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        folded = line.casefold()
        test_cleanup_notice = (
            "|w|" in folded
            and "core_modmanager.initdb| mod vanished:" in folded
            and f"/mods/repo/{MOD_ID}_" in folded
        )
        if (
            not test_cleanup_notice
            and ("|e|" in folded or "|w|" in folded)
            and any(token in folded for token in relevant_tokens)
        ):
            issues.append(line)
    return issues


async def _shell_snapshot(runtime: Any, vehicle: Any) -> dict[str, Any]:
    """Read every live shell node so transient flex cannot hide in the ref node."""

    payload = await runtime.simulator._call(
        vehicle.queue_lua_command,
        "local nodes = {}; local maxSpeed = 0; "
        "for nodeId = 0, obj:getNodeCount() - 1 do "
        "local position = obj:getNodePosition(nodeId); "
        "local velocity = obj:getNodeVelocityVector(nodeId); "
        "local speed = velocity:length(); "
        "if speed > maxSpeed then maxSpeed = speed end; "
        "nodes[#nodes + 1] = {"
        "id = nodeId, "
        "position = {position.x, position.y, position.z}, "
        "velocity = {velocity.x, velocity.y, velocity.z}, "
        "speed_mps = speed"
        "}; "
        "end; "
        "return jsonEncode({nodes = nodes, max_node_speed_mps = maxSpeed})",
        True,
    )
    snapshot = json.loads(payload)
    assert len(snapshot["nodes"]) == 77
    return snapshot


def _maximum_shell_displacement(
    baseline: dict[str, Any],
    observed: dict[str, Any],
) -> float:
    baseline_positions = {
        int(node["id"]): [float(value) for value in node["position"]] for node in baseline["nodes"]
    }
    observed_positions = {
        int(node["id"]): [float(value) for value in node["position"]] for node in observed["nodes"]
    }
    assert observed_positions.keys() == baseline_positions.keys()
    return max(
        math.dist(baseline_positions[node_id], observed_positions[node_id])
        for node_id in baseline_positions
    )


@pytest.mark.beamng_live
@pytest.mark.asyncio
async def test_cannon_car_wash_is_a_discoverable_stable_selector_prop(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    suffix = uuid.uuid4().hex[:10]
    runtime_mod_name = f"cannon_wash_selector_{suffix}"
    workspace = tmp_path / "workspace"
    _stage_full_mod(workspace, runtime_mod_name)
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
        prop_spawned = False
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
                archive_path = Path(artifact["path"])
                members = _zip_members(archive_path)
                assert members == EXPECTED_RUNTIME_FILES
                with zipfile.ZipFile(archive_path) as archive:
                    jbeam = json.loads(
                        archive.read(f"vehicles/{MOD_ID}/{MOD_ID}.jbeam").decode("utf-8")
                    )
                assert list(jbeam) == [MOD_ID]
                part = jbeam[MOD_ID]
                assert part["flexbodies"][1] == [SELECTOR_VISUAL_NAME, [PHYSICS_GROUP_NAME]]
                assert all(row[-1]["group"] == PHYSICS_GROUP_NAME for row in part["nodes"][1:])
                installed = _structured(
                    await session.call_tool(
                        "mod_install",
                        {"mod_name": runtime_mod_name, "confirm": True, "overwrite": False},
                    )
                )
                installed_path = Path(installed["path"])
                assert installed_path.is_file()

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
                await _wait_for_bridge(session)
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

                available = await runtime.simulator._call(bng.vehicles.get_available)
                catalog = available.get("vehicles", available)
                assert MODEL_ID in catalog, {
                    "reason": "Cannon Car Wash was absent from BeamNG's vehicle catalog",
                    "nearby": sorted(key for key in catalog if "cannon" in key.casefold()),
                }
                catalog_entry = catalog[MODEL_ID]
                assert catalog_entry["name"] == "Cannon Car Wash"
                assert catalog_entry["type"] == "Prop"
                assert catalog_entry["default_configuration"] == CONFIG_ID
                assert CONFIG_ID in catalog_entry["configurations"]
                assert catalog_entry["configurations"][CONFIG_ID]["name"].endswith(" Standard")

                spawned = _structured(
                    await session.call_tool(
                        "vehicle_spawn",
                        {
                            "spec": {
                                "vehicle_id": PROP_ID,
                                "model": MODEL_ID,
                                "position": SPAWN_POSITION,
                                "rotation": [0.0, 0.0, 0.0, 1.0],
                                "cling": False,
                            }
                        },
                    )
                )
                prop_spawned = True
                assert spawned["vehicle_id"] == PROP_ID
                assert spawned["model"] == MODEL_ID
                initial_position = [float(value) for value in spawned["position"]]
                assert math.dist(initial_position[:2], SPAWN_POSITION[:2]) <= 0.25
                assert 0.0 <= initial_position[2] - EXPECTED_SURFACE_Z <= 0.5

                prop_vehicle = runtime.simulator._vehicles[PROP_ID]
                topology = json.loads(
                    await runtime.simulator._call(
                        prop_vehicle.queue_lua_command,
                        "local mass = 0; local fixedNodes = 0; "
                        "for nodeId = 0, obj:getNodeCount() - 1 do "
                        "mass = mass + obj:getNodeMass(nodeId); "
                        "end; "
                        "for _, node in pairs(v.data.nodes or {}) do "
                        "if type(node) == 'table' and node.fixed == true then "
                        "fixedNodes = fixedNodes + 1; "
                        "end; "
                        "end; "
                        "return jsonEncode({"
                        "node_count = obj:getNodeCount(), "
                        "fixed_node_count = fixedNodes, "
                        "beam_count = obj:getBeamCount(), "
                        "triangle_count = tableSize(v.data.triangles or {}), "
                        "flexbody_count = tableSize(v.data.flexbodies or {}), "
                        "total_mass_kg = mass, "
                        "vehicle_directory = v.data.vehicleDirectory"
                        "})",
                        True,
                    )
                )
                assert topology["node_count"] == 77
                assert topology["fixed_node_count"] == 77
                assert topology["beam_count"] == 322
                assert topology["triangle_count"] == 144
                assert topology["flexbody_count"] == 1
                assert topology["total_mass_kg"] == pytest.approx(14875.0, rel=1e-5)
                assert topology["vehicle_directory"] == f"/vehicles/{MOD_ID}/"
                initial_shell = await _shell_snapshot(runtime, prop_vehicle)

                stepped = _structured(
                    await session.call_tool("simulation_control", {"action": "step", "steps": 120})
                )
                assert stepped["ok"] is True
                settled = _structured(
                    await session.call_tool("vehicle_state", {"vehicle_id": PROP_ID})
                )
                settled_position = [float(value) for value in settled["position"]]
                settled_velocity = [float(value) for value in settled["velocity"]]
                settled_shell = await _shell_snapshot(runtime, prop_vehicle)
                settling_shell_displacement = _maximum_shell_displacement(
                    initial_shell, settled_shell
                )
                assert settled["model"] == MODEL_ID
                assert math.dist(settled_position, initial_position) <= 0.005
                assert math.sqrt(sum(value * value for value in settled_velocity)) <= 0.01
                assert settling_shell_displacement <= 0.005
                assert float(settled_shell["max_node_speed_mps"]) <= 0.01
                assert 0.0 <= settled_position[2] - EXPECTED_SURFACE_Z <= 0.5

                ai_disabled = _structured(
                    await session.call_tool(
                        "vehicle_ai_configure",
                        {"config": {"vehicle_id": TRUCK_ID, "mode": "disabled"}},
                    )
                )
                assert ai_disabled["ok"] is True
                truck_target = [
                    settled_position[0],
                    settled_position[1],
                    EXPECTED_SURFACE_Z + 0.75,
                ]
                truck_teleported = _structured(
                    await session.call_tool(
                        "vehicle_teleport",
                        {
                            "command": {
                                "vehicle_id": TRUCK_ID,
                                "position": truck_target,
                                "rotation": [0.0, 0.0, 0.0, 1.0],
                                "reset": True,
                            }
                        },
                    )
                )
                assert truck_teleported["ok"] is True
                truck_released = _structured(
                    await session.call_tool(
                        "vehicle_control",
                        {
                            "command": {
                                "vehicle_id": TRUCK_ID,
                                "throttle": 0.0,
                                "brake": 0.0,
                                "parking_brake": 0.0,
                                "steering": 0.0,
                                "gear": 0,
                            }
                        },
                    )
                )
                assert truck_released["ok"] is True
                _structured(
                    await session.call_tool("simulation_control", {"action": "step", "steps": 30})
                )
                injected = json.loads(
                    await runtime.simulator._call(
                        bng.control.queue_lua_command,
                        f"local vehicle = scenetree.findObject('{TRUCK_ID}'); "
                        "if not vehicle then return jsonEncode({ok = false}) end; "
                        "vehicle:applyClusterVelocityScaleAdd("
                        "vehicle:getRefNodeId(), 0, 30, 0, 0); "
                        "return jsonEncode({ok = true, velocity_x_mps = 30})",
                        True,
                    )
                )
                assert injected == {"ok": True, "velocity_x_mps": 30}

                contact_samples: list[dict[str, Any]] = []
                prop_contact_samples: list[dict[str, Any]] = []
                step_schedule = ([1] * 30) + ([3] * 40)
                cumulative_steps = 0
                for sample_index, steps in enumerate(step_schedule):
                    _structured(
                        await session.call_tool(
                            "simulation_control", {"action": "step", "steps": steps}
                        )
                    )
                    cumulative_steps += steps
                    contact_samples.append(
                        _structured(
                            await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID})
                        )
                    )
                    if (
                        sample_index < 20
                        or sample_index % 5 == 0
                        or sample_index == len(step_schedule) - 1
                    ):
                        prop_state = _structured(
                            await session.call_tool("vehicle_state", {"vehicle_id": PROP_ID})
                        )
                        prop_contact_samples.append(
                            {
                                "physics_step": cumulative_steps,
                                "position": [float(value) for value in prop_state["position"]],
                                "velocity": [float(value) for value in prop_state["velocity"]],
                                "shell": await _shell_snapshot(runtime, prop_vehicle),
                            }
                        )

                truck_positions = [
                    [float(value) for value in sample["position"]] for sample in contact_samples
                ]
                truck_velocities = [
                    [float(value) for value in sample["velocity"]] for sample in contact_samples
                ]
                peak_positive_velocity = max(velocity[0] for velocity in truck_velocities)
                minimum_post_impact_velocity = min(velocity[0] for velocity in truck_velocities[8:])
                maximum_world_x = max(position[0] for position in truck_positions)
                final_truck_position = truck_positions[-1]
                final_truck_velocity = truck_velocities[-1]
                maximum_prop_ref_displacement = max(
                    math.dist(settled_position, sample["position"])
                    for sample in prop_contact_samples
                )
                maximum_prop_ref_speed = max(
                    math.sqrt(sum(value * value for value in sample["velocity"]))
                    for sample in prop_contact_samples
                )
                maximum_contact_shell_displacement = max(
                    _maximum_shell_displacement(settled_shell, sample["shell"])
                    for sample in prop_contact_samples
                )
                maximum_contact_shell_speed = max(
                    float(sample["shell"]["max_node_speed_mps"]) for sample in prop_contact_samples
                )
                collision_metrics = {
                    "peak_positive_velocity_x_mps": peak_positive_velocity,
                    "minimum_post_impact_velocity_x_mps": minimum_post_impact_velocity,
                    "maximum_world_x": maximum_world_x,
                    "wall_world_x": settled_position[0] + 3.1,
                    "final_truck_position": final_truck_position,
                    "final_truck_velocity_mps": final_truck_velocity,
                    "sample_count": len(contact_samples),
                    "prop_rigidity": {
                        "sample_count": len(prop_contact_samples),
                        "maximum_ref_displacement_m": maximum_prop_ref_displacement,
                        "maximum_ref_speed_mps": maximum_prop_ref_speed,
                        "maximum_shell_node_displacement_m": (maximum_contact_shell_displacement),
                        "maximum_shell_node_speed_mps": maximum_contact_shell_speed,
                    },
                }
                assert peak_positive_velocity >= 20.0, collision_metrics
                assert maximum_world_x <= settled_position[0] + 4.5, collision_metrics
                assert minimum_post_impact_velocity <= 5.0, collision_metrics
                assert final_truck_position[0] <= settled_position[0] + 4.5, collision_metrics
                assert maximum_prop_ref_displacement <= 0.005, collision_metrics
                assert maximum_prop_ref_speed <= 0.01, collision_metrics
                assert maximum_contact_shell_displacement <= 0.005, collision_metrics
                assert maximum_contact_shell_speed <= 0.01, collision_metrics
                post_contact_prop = _structured(
                    await session.call_tool("vehicle_state", {"vehicle_id": PROP_ID})
                )
                assert post_contact_prop["position"] == pytest.approx(settled_position, abs=0.005)

                vehicles = _structured(await session.call_tool("vehicle_list", {}))
                assert any(
                    vehicle["vehicle_id"] == PROP_ID and vehicle["model"] == MODEL_ID
                    for vehicle in vehicles
                )
                removed = _structured(
                    await session.call_tool(
                        "vehicle_remove", {"vehicle_id": PROP_ID, "confirm": True}
                    )
                )
                assert "removed" in removed["message"]
                prop_spawned = False

                stopped = _structured(
                    await session.call_tool("scenario_control", {"action": "stop"})
                )
                assert stopped["ok"] is True
                disconnected = _structured(await session.call_tool("simulator_disconnect", {}))
                assert disconnected["ok"] is True
                normal_disconnect = True
                cleanup_owned_beamng_session(bng, owned_process=owned_process)
                owned_process_cleaned = True

                errors = _selector_error_lines(log_path)
                assert errors == []
                print(
                    "CANNON_SELECTOR_TELEMETRY "
                    + json.dumps(
                        {
                            "catalog_name": catalog_entry["name"],
                            "catalog_type": catalog_entry["type"],
                            "configuration": CONFIG_ID,
                            "topology": topology,
                            "initial_position": initial_position,
                            "settled_position": settled_position,
                            "settled_velocity_mps": settled_velocity,
                            "settling_rigidity": {
                                "maximum_shell_node_displacement_m": (settling_shell_displacement),
                                "maximum_shell_node_speed_mps": settled_shell["max_node_speed_mps"],
                            },
                            "collision_contact": {
                                "injected_velocity_x_mps": injected["velocity_x_mps"],
                                **collision_metrics,
                                "prop_position_after_contact": post_contact_prop["position"],
                            },
                            "errors": errors,
                        },
                        sort_keys=True,
                    )
                )
        finally:
            try:
                if bng is not None and not normal_disconnect:
                    if prop_spawned:
                        with contextlib.suppress(Exception):
                            await runtime.simulator.remove_vehicle(PROP_ID)
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
