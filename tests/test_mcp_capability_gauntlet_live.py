from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import subprocess
import threading
import uuid
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import AnyUrl

from beamng_mcp.config import Settings
from beamng_mcp.mcp_adapter import create_mcp_server
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
    temporary_lua_bridge_config,
)


def _configured_runtime() -> tuple[Path, Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    blender_value = os.getenv("BEAMNG_MCP_TEST_BLENDER")
    if not home_value or not user_value or not binary_value or not blender_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY plus BEAMNG_MCP_TEST_BLENDER for the MCP "
            "capability gauntlet"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    blender = Path(blender_value).resolve()
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the MCP capability gauntlet requires a sentinel-isolated BeamNG profile")
    if not blender.is_file():
        pytest.fail(f"configured Blender executable does not exist: {blender}")
    return home, user, binary, blender


def _structured(result: Any) -> Any:
    assert result.isError is False, result.content
    assert result.structuredContent is not None
    structured = result.structuredContent
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    return structured


class _TrackedSession:
    def __init__(self, session: Any, called_tools: set[str]) -> None:
        self._session = session
        self._called_tools = called_tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._called_tools.add(name)
        return await self._session.call_tool(name, arguments)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


async def _wait_for_job(session: Any, job_id: str) -> dict[str, Any]:
    for _ in range(200):
        job = _structured(await session.call_tool("job_get", {"job_id": job_id}))
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        await asyncio.sleep(0.05)
    pytest.fail(f"timed out waiting for MCP job {job_id}")


async def _wait_for_trigger_events(
    session: Any,
    handle: str,
    expected: list[str],
) -> dict[str, Any]:
    for _ in range(60):
        stepped = _structured(
            await session.call_tool("simulation_control", {"action": "step", "steps": 1})
        )
        assert stepped["ok"] is True
        await asyncio.sleep(0.05)
        page = _structured(
            await session.call_tool(
                "map_trigger_events",
                {"handle": handle, "after_sequence": 0, "limit": 10},
            )
        )
        observed = [event["event"] for event in page["events"]]
        assert observed == expected[: len(observed)]
        if observed == expected:
            return page
    pytest.fail(f"timed out waiting for trigger events {expected!r}")


async def _wait_for_bridge(session: Any) -> dict[str, Any]:
    last_result: Any = None
    for _ in range(50):
        last_result = await session.call_tool("lua_bridge_status", {"probe": True})
        if last_result.isError is False and last_result.structuredContent is not None:
            status = _structured(last_result)
            if status["connected"] is True and status["authenticated"] is True:
                return status
        await asyncio.sleep(0.1)
    pytest.fail(f"authenticated Lua bridge did not return after mission reset: {last_result}")


async def _measured_road_surface_points(
    session: Any,
    road_ids: list[str],
    *,
    count: int,
    minimum_planar_separation: float,
) -> list[list[float]]:
    """Return separated, locally flat interior XYZ samples from distinct roads."""

    def middle_point(edge: object) -> list[float] | None:
        if not isinstance(edge, dict):
            return None
        raw_middle = edge.get("middle")
        if isinstance(raw_middle, dict):
            raw_components = [raw_middle.get(axis) for axis in ("x", "y", "z")]
        elif isinstance(raw_middle, (list, tuple)):
            raw_components = list(raw_middle)
        else:
            return None
        if len(raw_components) != 3:
            return None
        try:
            point = [float(component) for component in raw_components]
        except (TypeError, ValueError):
            return None
        return point if all(math.isfinite(component) for component in point) else None

    points: list[list[float]] = []
    rejected_roads: list[str] = []
    for road_id in road_ids:
        result = await session.call_tool("map_road_edges", {"road_id": road_id})
        if result.isError or result.structuredContent is None:
            rejected_roads.append(road_id)
            continue
        edges = _structured(result)
        if not isinstance(edges, list):
            rejected_roads.append(road_id)
            continue
        center = (len(edges) - 1) / 2.0
        candidate_indices = sorted(range(len(edges)), key=lambda index: abs(index - center))
        for index in candidate_indices:
            point = middle_point(edges[index])
            if point is None:
                continue
            neighbors = [
                neighbor
                for neighbor in (
                    middle_point(edges[index - 1]) if index > 0 else None,
                    middle_point(edges[index + 1]) if index + 1 < len(edges) else None,
                )
                if neighbor is not None
            ]
            if not neighbors:
                continue
            locally_flat = True
            for neighbor in neighbors:
                planar_distance = math.dist(point[:2], neighbor[:2])
                if planar_distance < 0.25 or abs(point[2] - neighbor[2]) / planar_distance > 0.08:
                    locally_flat = False
                    break
            if not locally_flat:
                continue
            if any(
                math.dist(point[:2], existing[:2]) < minimum_planar_separation
                for existing in points
            ):
                continue
            points.append(point)
            if len(points) == count:
                return points
            break
    pytest.fail(
        f"found only {len(points)} of {count} measured road points separated by "
        f"{minimum_planar_separation:g} m; rejected road edge queries: {rejected_roads[:10]}"
    )


async def _stabilized_vehicle_state(
    session: Any,
    vehicle_id: str,
    *,
    maximum_final_vertical_drift: float,
    maximum_final_vertical_speed: float,
    maximum_final_planar_speed: float,
) -> dict[str, Any]:
    """Advance deterministic physics until three consecutive polls settle."""

    states: list[dict[str, Any]] = []
    for _ in range(12):
        stepped = _structured(
            await session.call_tool("simulation_control", {"action": "step", "steps": 30})
        )
        assert stepped["ok"] is True
        states.append(
            _structured(await session.call_tool("vehicle_state", {"vehicle_id": vehicle_id}))
        )
        if len(states) < 3:
            continue
        recent_z = [float(state["position"][2]) for state in states[-3:]]
        velocity = states[-1].get("velocity")
        vertical_speed = (
            abs(float(velocity[2]))
            if isinstance(velocity, (list, tuple)) and len(velocity) == 3
            else math.inf
        )
        planar_speed = (
            math.hypot(float(velocity[0]), float(velocity[1]))
            if isinstance(velocity, (list, tuple)) and len(velocity) == 3
            else math.inf
        )
        if (
            max(recent_z) - min(recent_z) <= maximum_final_vertical_drift
            and vertical_speed <= maximum_final_vertical_speed
            and planar_speed <= maximum_final_planar_speed
        ):
            return states[-1]
    pytest.fail(
        {
            "vehicle_id": vehicle_id,
            "recent_z": [float(state["position"][2]) for state in states[-3:]],
            "final_velocity": states[-1].get("velocity"),
            "maximum_final_vertical_drift": maximum_final_vertical_drift,
            "maximum_final_vertical_speed": maximum_final_vertical_speed,
            "maximum_final_planar_speed": maximum_final_planar_speed,
        }
    )


def _assert_grounded(
    state: dict[str, Any],
    surface: list[float],
    *,
    minimum_clearance: float,
    maximum_clearance: float,
    maximum_planar_drift: float,
) -> None:
    position = [float(component) for component in state["position"]]
    clearance = position[2] - surface[2]
    assert minimum_clearance <= clearance <= maximum_clearance, {
        "vehicle_id": state["vehicle_id"],
        "position": position,
        "measured_surface": surface,
        "clearance": clearance,
        "expected_clearance": [minimum_clearance, maximum_clearance],
    }
    planar_drift = math.dist(position[:2], surface[:2])
    assert planar_drift <= maximum_planar_drift, {
        "vehicle_id": state["vehicle_id"],
        "position": position,
        "measured_surface": surface,
        "planar_drift": planar_drift,
        "maximum_planar_drift": maximum_planar_drift,
    }


@pytest.mark.beamng_live
@pytest.mark.blender
@pytest.mark.asyncio
async def test_mcp_capability_gauntlet_tracer_scenario(tmp_path: Path) -> None:
    home, user, binary, blender = _configured_runtime()
    scenario_name = f"mcp_gauntlet_{uuid.uuid4().hex[:12]}"
    scenario_directory = require_confined_profile_target(
        user,
        Path("levels") / "gridmap_v2" / "scenarios" / scenario_name,
    )
    scenario_info = require_confined_profile_target(
        user,
        Path("levels") / "gridmap_v2" / "scenarios" / scenario_name / f"{scenario_name}.json",
    )
    scenario_prefab = require_confined_profile_target(
        user,
        Path("levels")
        / "gridmap_v2"
        / "scenarios"
        / scenario_name
        / f"{scenario_name}.prefab.json",
    )
    suffix = uuid.uuid4().hex[:10]
    support_mod = f"gauntlet_support_{suffix}"
    ramp_mod = f"gauntlet_ramp_{suffix}"
    ramp_asset = ramp_mod

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
                "root": tmp_path / "workspace",
                "allow_mod_install": True,
                "max_file_bytes": 16 * 1024 * 1024,
            },
            blender={"executable": blender},
        )
        mcp, runtime = create_mcp_server(settings)
        bng: Any | None = None
        scenario: Any | None = None
        owned_process: Any | None = None
        installed_files: list[Path] = []
        map_object_name: str | None = None
        trigger_handle: str | None = None
        normal_disconnect = False
        called_tools: set[str] = set()
        declared_tools: set[str] = set()

        def watchdog() -> None:
            active_bng = runtime.simulator._bng
            process = owned_process or (
                getattr(active_bng, "process", None) if active_bng is not None else None
            )
            if process is not None and process.poll() is None:
                process.terminate()

        timer = threading.Timer(180.0, watchdog)
        timer.daemon = True
        timer.start()
        try:
            async with create_connected_server_and_client_session(
                mcp,
                read_timeout_seconds=timedelta(seconds=120),
            ) as raw_session:
                session = _TrackedSession(raw_session, called_tools)
                try:
                    registered = await session.list_tools()
                    registered_tool_names = [tool.name for tool in registered.tools]
                    assert len(registered_tool_names) == len(set(registered_tool_names)) == 57
                    capabilities = _structured(await session.call_tool("capabilities_get", {}))
                    assert capabilities["mode"] == "offline"
                    assert len(capabilities["tools"]) == len(set(capabilities["tools"])) == 57
                    assert set(capabilities["tools"]) == set(registered_tool_names)
                    declared_tools = set(registered_tool_names)

                    resources = await session.list_resources()
                    assert {str(resource.uri) for resource in resources.resources} == {
                        "beamng://status",
                        "beamng://vehicles",
                        "beamng://autonomy",
                        "beamng://authoring/softbody/v1",
                    }
                    templates = await session.list_resource_templates()
                    assert {
                        str(template.uriTemplate) for template in templates.resourceTemplates
                    } == {"beamng://jobs/{job_id}"}
                    status_resource = await session.read_resource(AnyUrl("beamng://status"))
                    status_payload = json.loads(status_resource.contents[0].text)  # type: ignore[union-attr]
                    assert status_payload["mode"] == "offline"
                    autonomy_resource = await session.read_resource(AnyUrl("beamng://autonomy"))
                    autonomy_payload = json.loads(autonomy_resource.contents[0].text)  # type: ignore[union-attr]
                    assert autonomy_payload["running"] is False
                    contract_resource = await session.read_resource(
                        AnyUrl("beamng://authoring/softbody/v1")
                    )
                    contract_payload = json.loads(contract_resource.contents[0].text)  # type: ignore[union-attr]
                    assert contract_payload["schema"] == "beamng-softbody-authoring-resource-v1"

                    prompts = await session.list_prompts()
                    assert {prompt.name for prompt in prompts.prompts} == {
                        "inspect_current_scene",
                        "build_and_test_mod",
                        "build_softbody_mod",
                        "cautious_autonomous_run",
                    }
                    prompt_arguments = {
                        "inspect_current_scene": None,
                        "build_and_test_mod": {
                            "mod_name": support_mod,
                            "goal": "exercise the full MCP authoring surface",
                        },
                        "build_softbody_mod": {
                            "mod_name": ramp_mod,
                            "asset_name": ramp_asset,
                            "goal": "build a coordinate-aligned concrete ramp",
                        },
                        "cautious_autonomous_run": {"vehicle_id": "ego"},
                    }
                    for prompt_name, arguments in prompt_arguments.items():
                        prompt = await session.get_prompt(prompt_name, arguments)
                        assert prompt.messages
                        assert prompt.messages[0].role == "user"

                    scaffold = _structured(
                        await session.call_tool(
                            "mod_scaffold",
                            {
                                "mod_name": support_mod,
                                "title": "MCP Capability Gauntlet Support",
                                "author": "beamng-mcp integration test",
                                "kind": "mixed",
                            },
                        )
                    )
                    assert {item["path"] for item in scaffold} == {
                        "README.md",
                        f"mod_info/{support_mod}/info.json",
                    }
                    listed = _structured(
                        await session.call_tool("mod_file_list", {"mod_name": support_mod})
                    )
                    assert listed == scaffold
                    info = _structured(
                        await session.call_tool(
                            "mod_file_read",
                            {
                                "mod_name": support_mod,
                                "path": f"mod_info/{support_mod}/info.json",
                            },
                        )
                    )
                    assert "MCP Capability Gauntlet Support" in info["data"]["content"]

                    extension_path = f"lua/ge/extensions/{support_mod}.lua"
                    first_lua = (
                        "local M = {}\n"
                        "function M.onExtensionLoaded()\n"
                        f"  log('I', '{support_mod}', 'loaded')\n"
                        "end\n"
                        "return M\n"
                    )
                    first_write = _structured(
                        await session.call_tool(
                            "mod_file_write",
                            {
                                "request": {
                                    "mod_name": support_mod,
                                    "path": extension_path,
                                    "content": first_lua,
                                }
                            },
                        )
                    )
                    second_lua = first_lua.replace("'loaded'", "'gauntlet ready'")
                    second_write = _structured(
                        await session.call_tool(
                            "mod_file_write",
                            {
                                "request": {
                                    "mod_name": support_mod,
                                    "path": extension_path,
                                    "content": second_lua,
                                    "expected_sha256": first_write["sha256"],
                                }
                            },
                        )
                    )
                    assert second_write["sha256"] != first_write["sha256"]
                    read_lua = _structured(
                        await session.call_tool(
                            "mod_file_read",
                            {"mod_name": support_mod, "path": extension_path},
                        )
                    )
                    assert read_lua["data"]["content"] == second_lua
                    support_validation = _structured(
                        await session.call_tool("mod_validate", {"mod_name": support_mod})
                    )
                    assert support_validation["valid"] is True
                    support_pack = _structured(
                        await session.call_tool("mod_pack", {"mod_name": support_mod})
                    )
                    assert await asyncio.to_thread(Path(support_pack["path"]).is_file)
                    support_job = _structured(
                        await session.call_tool(
                            "mod_test_start",
                            {"mod_name": support_mod, "pack": True, "install": False},
                        )
                    )
                    completed_job = await _wait_for_job(session, support_job["job_id"])
                    assert completed_job["status"] == "succeeded"
                    jobs = _structured(await session.call_tool("job_list", {"limit": 10}))
                    assert any(item["job_id"] == support_job["job_id"] for item in jobs)
                    terminal_cancel = _structured(
                        await session.call_tool("job_cancel", {"job_id": support_job["job_id"]})
                    )
                    assert terminal_cancel["status"] == "succeeded"
                    job_resource = await session.read_resource(
                        AnyUrl(f"beamng://jobs/{support_job['job_id']}")
                    )
                    job_payload = json.loads(job_resource.contents[0].text)  # type: ignore[union-attr]
                    assert job_payload["status"] == "succeeded"
                    support_install = _structured(
                        await session.call_tool(
                            "mod_install",
                            {"mod_name": support_mod, "confirm": True, "overwrite": False},
                        )
                    )
                    installed_files.append(Path(support_install["path"]))

                    handoff = _structured(
                        await session.call_tool(
                            "softbody_handoff_create",
                            {
                                "request": {
                                    "mod_name": ramp_mod,
                                    "asset_name": ramp_asset,
                                    "visual_object": f"{ramp_asset}_visual",
                                    "cage_object": f"{ramp_asset}_physics",
                                    "coordinates": {
                                        "source_origin_world": [0.0, 0.0, 0.0],
                                        "source_world_to_beamng_vehicle": [
                                            [1.0, 0.0, 0.0, 0.0],
                                            [0.0, 1.0, 0.0, 0.0],
                                            [0.0, 0.0, 1.0, 0.0],
                                            [0.0, 0.0, 0.0, 1.0],
                                        ],
                                    },
                                }
                            },
                        )
                    )
                    fixture = Path(__file__).with_name("fixtures") / "blender_structural_ramp.py"
                    blender_run = await asyncio.to_thread(
                        subprocess.run,
                        [
                            str(blender),
                            "--background",
                            "--factory-startup",
                            "--python-exit-code",
                            "1",
                            "--python",
                            str(fixture),
                            "--",
                            handoff["blender_runner_path"],
                            ramp_asset,
                        ],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    assert blender_run.returncode == 0, blender_run.stdout + blender_run.stderr
                    staged = _structured(
                        await session.call_tool(
                            "softbody_handoff_validate",
                            {"slot_id": handoff["slot_id"]},
                        )
                    )
                    assert staged["valid"] is True, staged["issues"]
                    assert staged["manifest"]["measured_volume_m3"] == pytest.approx(6.0)
                    ramp_build = _structured(
                        await session.call_tool(
                            "softbody_mod_build",
                            {
                                "request": {
                                    "slot_id": handoff["slot_id"],
                                    "mod_name": ramp_mod,
                                    "asset_name": ramp_asset,
                                    "title": "MCP Capability Gauntlet Concrete Ramp",
                                    "author": "beamng-mcp integration test",
                                    "material": {
                                        "preset": "concrete",
                                        "material_id": f"{ramp_asset}_material",
                                        "base_color": [0.45, 0.47, 0.5, 1.0],
                                        "roughness": 0.9,
                                    },
                                    "mass": {"closed_volume_m3": 6.0},
                                    "grounded": True,
                                    "fixed": True,
                                }
                            },
                        )
                    )
                    assert ramp_build["total_mass_kg"] == pytest.approx(14_400.0)
                    ramp_validation = _structured(
                        await session.call_tool(
                            "softbody_mod_validate",
                            {"mod_name": ramp_mod, "asset_name": ramp_asset},
                        )
                    )
                    assert ramp_validation["valid"] is True, ramp_validation["issues"]
                    generic_ramp_validation = _structured(
                        await session.call_tool("mod_validate", {"mod_name": ramp_mod})
                    )
                    assert generic_ramp_validation["valid"] is True
                    ramp_pack = _structured(
                        await session.call_tool("mod_pack", {"mod_name": ramp_mod})
                    )
                    assert await asyncio.to_thread(Path(ramp_pack["path"]).is_file)
                    ramp_install = _structured(
                        await session.call_tool(
                            "mod_install",
                            {"mod_name": ramp_mod, "confirm": True, "overwrite": False},
                        )
                    )
                    installed_files.append(Path(ramp_install["path"]))

                    offline = _structured(await session.call_tool("simulator_status", {}))
                    assert offline["connected"] is False

                    reservation.release()
                    connected = _structured(
                        await session.call_tool("simulator_connect", {"launch": True})
                    )
                    assert connected["connected"] is True
                    assert connected["mode"] == "drive"
                    assert connected["tech_enabled"] is False

                    bng = runtime.simulator._bng
                    assert bng is not None
                    owned_process = claim_owned_beamng_process(bng)

                    created = _structured(
                        await session.call_tool(
                            "scenario_create",
                            {
                                "ref": {"level": "gridmap_v2", "name": scenario_name},
                                "vehicles": [],
                                "description": "Disposable full-surface MCP capability gauntlet",
                                "load": False,
                            },
                        )
                    )
                    assert created["level"] == "gridmap_v2"
                    assert created["name"] == scenario_name
                    available = _structured(
                        await session.call_tool(
                            "scenario_list",
                            {"level": "gridmap_v2"},
                        )
                    )
                    assert any(item["name"] == scenario_name for item in available)
                    loaded = _structured(
                        await session.call_tool(
                            "scenario_load",
                            {"ref": {"level": "gridmap_v2", "name": scenario_name}},
                        )
                    )
                    assert loaded["name"] == scenario_name

                    started = _structured(
                        await session.call_tool("scenario_control", {"action": "start"})
                    )
                    assert started["ok"] is True

                    scenario = await runtime.simulator._call(bng.scenario.get_current)
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
                    assert (
                        _structured(
                            await session.call_tool("simulation_control", {"action": "pause"})
                        )["ok"]
                        is True
                    )
                    assert (
                        _structured(
                            await session.call_tool(
                                "simulation_control",
                                {"action": "step", "steps": 3},
                            )
                        )["ok"]
                        is True
                    )

                    bridge = _structured(
                        await session.call_tool("lua_bridge_status", {"probe": True})
                    )
                    assert bridge["connected"] is True
                    assert bridge["authenticated"] is True
                    assert bridge["bridge_version"] == "0.3.0"

                    environment = _structured(await session.call_tool("environment_get", {}))
                    restored_environment = _structured(
                        await session.call_tool(
                            "environment_set",
                            {"gravity": environment["gravity"]},
                        )
                    )
                    assert restored_environment["gravity"] == pytest.approx(environment["gravity"])

                    roads = _structured(
                        await session.call_tool(
                            "map_road_network",
                            {"include_edges": True, "drivable_only": True, "limit": 500},
                        )
                    )
                    road_ids = [road_id for road_id in roads if road_id != "_meta"]
                    assert road_ids
                    (
                        ramp_surface,
                        ego_surface,
                        probe_surface,
                        trigger_surface,
                    ) = await _measured_road_surface_points(
                        session,
                        road_ids,
                        count=4,
                        minimum_planar_separation=50.0,
                    )

                    stopped_empty = _structured(
                        await session.call_tool("scenario_control", {"action": "stop"})
                    )
                    assert stopped_empty["ok"] is True
                    persistent_scenario = _structured(
                        await session.call_tool(
                            "scenario_create",
                            {
                                "ref": {"level": "gridmap_v2", "name": scenario_name},
                                "vehicles": [
                                    {
                                        "vehicle_id": "ramp",
                                        "model": ramp_mod,
                                        "position": ramp_surface,
                                        "license_plate": "MCPRAMP",
                                        "cling": False,
                                    }
                                ],
                                "description": (
                                    "Disposable full-surface MCP capability gauntlet with "
                                    "measured persistent placement"
                                ),
                                "load": True,
                                "overwrite": True,
                                "confirm_overwrite": True,
                            },
                        )
                    )
                    assert persistent_scenario["name"] == scenario_name
                    assert (
                        _structured(
                            await session.call_tool("scenario_control", {"action": "start"})
                        )["ok"]
                        is True
                    )
                    scenario = await runtime.simulator._call(bng.scenario.get_current)
                    rebuilt_bridge = await _wait_for_bridge(session)
                    assert rebuilt_bridge["bridge_version"] == "0.3.0"
                    assert (
                        _structured(
                            await session.call_tool(
                                "simulation_control",
                                {
                                    "action": "deterministic",
                                    "steps_per_second": 60,
                                    "speed_factor": 1,
                                },
                            )
                        )["ok"]
                        is True
                    )
                    assert (
                        _structured(
                            await session.call_tool("simulation_control", {"action": "pause"})
                        )["ok"]
                        is True
                    )
                    ramp_state = await _stabilized_vehicle_state(
                        session,
                        "ramp",
                        maximum_final_vertical_drift=0.05,
                        maximum_final_vertical_speed=0.1,
                        maximum_final_planar_speed=0.1,
                    )
                    assert ramp_state["model"] == ramp_mod
                    _assert_grounded(
                        ramp_state,
                        ramp_surface,
                        minimum_clearance=-0.15,
                        maximum_clearance=0.5,
                        maximum_planar_drift=0.5,
                    )

                    ego_spawn_position = [
                        ego_surface[0],
                        ego_surface[1],
                        ego_surface[2] + 0.75,
                    ]
                    spawned_ego = _structured(
                        await session.call_tool(
                            "vehicle_spawn",
                            {
                                "spec": {
                                    "vehicle_id": "ego",
                                    "model": "etk800",
                                    "position": ego_spawn_position,
                                    "license_plate": "MCPTEST",
                                    "color": "White",
                                    "cling": False,
                                }
                            },
                        )
                    )
                    assert spawned_ego["vehicle_id"] == "ego"
                    assert math.dist(spawned_ego["position"][:2], ego_surface[:2]) <= 0.5
                    assert -0.2 <= spawned_ego["position"][2] - ego_surface[2] <= 1.5
                    reset_spawn = _structured(
                        await session.call_tool(
                            "vehicle_teleport",
                            {
                                "command": {
                                    "vehicle_id": "ego",
                                    "position": ego_spawn_position,
                                    "reset": True,
                                }
                            },
                        )
                    )
                    assert reset_spawn["ok"] is True
                    spawn_ai_disabled = _structured(
                        await session.call_tool(
                            "vehicle_ai_configure",
                            {"config": {"vehicle_id": "ego", "mode": "disabled"}},
                        )
                    )
                    assert spawn_ai_disabled["ok"] is True
                    controlled = _structured(
                        await session.call_tool(
                            "vehicle_control",
                            {
                                "command": {
                                    "vehicle_id": "ego",
                                    "throttle": 0.0,
                                    "brake": 1.0,
                                    "parking_brake": 1.0,
                                    "steering": 0.0,
                                    "gear": 0,
                                }
                            },
                        )
                    )
                    assert controlled["ok"] is True
                    state = await _stabilized_vehicle_state(
                        session,
                        "ego",
                        maximum_final_vertical_drift=0.1,
                        maximum_final_vertical_speed=0.35,
                        maximum_final_planar_speed=0.5,
                    )
                    _assert_grounded(
                        state,
                        ego_surface,
                        minimum_clearance=-0.2,
                        maximum_clearance=1.5,
                        maximum_planar_drift=1.5,
                    )

                    vehicles = _structured(await session.call_tool("vehicle_list", {}))
                    assert {vehicle["vehicle_id"] for vehicle in vehicles} == {"ego", "ramp"}
                    vehicles_resource = await session.read_resource(AnyUrl("beamng://vehicles"))
                    vehicles_payload = json.loads(vehicles_resource.contents[0].text)  # type: ignore[union-attr]
                    assert {vehicle["vehicle_id"] for vehicle in vehicles_payload} == {
                        "ego",
                        "ramp",
                    }
                    state = _structured(
                        await session.call_tool("vehicle_state", {"vehicle_id": "ego"})
                    )
                    assert state["vehicle_id"] == "ego"
                    assert len(state["position"]) == 3
                    ramp_state = _structured(
                        await session.call_tool("vehicle_state", {"vehicle_id": "ramp"})
                    )
                    assert ramp_state["model"] == ramp_mod

                    for sensor_type in ("state", "electrics", "damage"):
                        sensor_name = f"gauntlet_{sensor_type}"
                        attached = _structured(
                            await session.call_tool(
                                "sensor_attach",
                                {
                                    "spec": {
                                        "name": sensor_name,
                                        "sensor_type": sensor_type,
                                        "vehicle_id": "ego",
                                    }
                                },
                            )
                        )
                        assert attached["ok"] is True
                        reading = _structured(
                            await session.call_tool("sensor_poll", {"name": sensor_name})
                        )
                        assert reading["name"] == sensor_name
                        assert reading["sensor_type"] == sensor_type
                        assert isinstance(reading["data"], dict)
                        removed = _structured(
                            await session.call_tool("sensor_remove", {"name": sensor_name})
                        )
                        assert removed["ok"] is True

                    controlled = _structured(
                        await session.call_tool(
                            "vehicle_control",
                            {
                                "command": {
                                    "vehicle_id": "ego",
                                    "throttle": 0.0,
                                    "brake": 1.0,
                                    "parking_brake": 1.0,
                                    "steering": 0.0,
                                }
                            },
                        )
                    )
                    assert controlled["ok"] is True
                    disabled_ai = _structured(
                        await session.call_tool(
                            "vehicle_ai_configure",
                            {"config": {"vehicle_id": "ego", "mode": "disabled"}},
                        )
                    )
                    assert disabled_ai["ok"] is True
                    teleported = _structured(
                        await session.call_tool(
                            "vehicle_teleport",
                            {
                                "command": {
                                    "vehicle_id": "ego",
                                    "position": state["position"],
                                    "reset": True,
                                }
                            },
                        )
                    )
                    assert teleported["ok"] is True

                    probe_spawn_position = [
                        probe_surface[0],
                        probe_surface[1],
                        probe_surface[2] + 1.0,
                    ]
                    spawned = _structured(
                        await session.call_tool(
                            "vehicle_spawn",
                            {
                                "spec": {
                                    "vehicle_id": "probe",
                                    "model": "pickup",
                                    "position": probe_spawn_position,
                                    "license_plate": "MCPPROBE",
                                    "cling": False,
                                }
                            },
                        )
                    )
                    assert spawned["vehicle_id"] == "probe"
                    assert math.dist(spawned["position"][:2], probe_surface[:2]) <= 0.5
                    assert -0.2 <= spawned["position"][2] - probe_surface[2] <= 1.75
                    reset_probe = _structured(
                        await session.call_tool(
                            "vehicle_teleport",
                            {
                                "command": {
                                    "vehicle_id": "probe",
                                    "position": probe_spawn_position,
                                    "reset": True,
                                }
                            },
                        )
                    )
                    assert reset_probe["ok"] is True
                    probe_ai_disabled = _structured(
                        await session.call_tool(
                            "vehicle_ai_configure",
                            {"config": {"vehicle_id": "probe", "mode": "disabled"}},
                        )
                    )
                    assert probe_ai_disabled["ok"] is True
                    probe_braked = _structured(
                        await session.call_tool(
                            "vehicle_control",
                            {
                                "command": {
                                    "vehicle_id": "probe",
                                    "throttle": 0.0,
                                    "brake": 1.0,
                                    "parking_brake": 1.0,
                                    "steering": 0.0,
                                    "gear": 0,
                                }
                            },
                        )
                    )
                    assert probe_braked["ok"] is True
                    probe_state = await _stabilized_vehicle_state(
                        session,
                        "probe",
                        maximum_final_vertical_drift=0.15,
                        maximum_final_vertical_speed=0.5,
                        maximum_final_planar_speed=0.5,
                    )
                    assert probe_state["model"] == "pickup"
                    _assert_grounded(
                        probe_state,
                        probe_surface,
                        minimum_clearance=-0.2,
                        maximum_clearance=1.75,
                        maximum_planar_drift=1.5,
                    )
                    removed_vehicle = _structured(
                        await session.call_tool(
                            "vehicle_remove",
                            {"vehicle_id": "probe", "confirm": True},
                        )
                    )
                    assert removed_vehicle["ok"] is True

                    map_object_name = f"beamng_mcp_light_{suffix}"
                    light_initial = [
                        ego_surface[0] + 2.0,
                        ego_surface[1] + 3.0,
                        ego_surface[2] + 4.0,
                    ]
                    light_updated = [
                        ego_surface[0] + 5.0,
                        ego_surface[1] + 6.0,
                        ego_surface[2] + 7.0,
                    ]
                    light = _structured(
                        await session.call_tool(
                            "map_object_create",
                            {
                                "mutation": {
                                    "name": map_object_name,
                                    "class_name": "PointLight",
                                    "position": light_initial,
                                    "rotation": [0.0, 0.0, 0.0, 1.0],
                                    "scale": [1.0, 1.0, 1.0],
                                    "fields": {
                                        "color": [0.2, 0.4, 0.8, 1.0],
                                        "brightness": 1.5,
                                        "range": 12.0,
                                        "castShadows": False,
                                        "enabled": True,
                                    },
                                }
                            },
                        )
                    )
                    assert light["name"] == map_object_name
                    assert light["class"] == "PointLight"
                    assert isinstance(light["id"], int) and light["id"] > 0
                    assert light["managed"] is True

                    blocked_reload = await session.call_tool("lua_extension_reload", {})
                    blocked_reload_text = str(blocked_reload.content).lower()
                    assert blocked_reload.isError is True
                    assert "managed" in blocked_reload_text and "object" in blocked_reload_text

                    fetched_light = _structured(
                        await session.call_tool(
                            "map_object_get",
                            {"object_id": map_object_name},
                        )
                    )
                    assert fetched_light["id"] == light["id"]
                    assert tuple(
                        fetched_light["position"][axis] for axis in ("x", "y", "z")
                    ) == pytest.approx(light_initial)
                    updated_light = _structured(
                        await session.call_tool(
                            "map_object_update",
                            {
                                "patch": {
                                    "object_id": map_object_name,
                                    "position": light_updated,
                                    "fields": {"brightness": 2.0, "enabled": False},
                                }
                            },
                        )
                    )
                    assert updated_light["id"] == light["id"]
                    assert tuple(
                        updated_light["position"][axis] for axis in ("x", "y", "z")
                    ) == pytest.approx(light_updated)
                    light_listing = _structured(
                        await session.call_tool(
                            "map_object_list",
                            {
                                "class_name": "PointLight",
                                "name_prefix": map_object_name,
                                "limit": 10,
                            },
                        )
                    )
                    assert any(
                        item["name"] == map_object_name and item["id"] == light["id"]
                        for item in light_listing["objects"]
                    )
                    deleted_light = _structured(
                        await session.call_tool(
                            "map_object_delete",
                            {"object_id": map_object_name, "confirm": True},
                        )
                    )
                    assert deleted_light["deleted"] is True
                    map_object_name = None

                    origin = [float(component) for component in state["position"]]
                    ego_reference_height = origin[2] - ego_surface[2]
                    trigger_center = {
                        "x": trigger_surface[0],
                        "y": trigger_surface[1],
                        "z": trigger_surface[2] + ego_reference_height,
                    }
                    trigger = _structured(
                        await session.call_tool(
                            "map_trigger_create",
                            {
                                "request": {
                                    "position": trigger_center,
                                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                                    "scale": {"x": 6.0, "y": 6.0, "z": 6.0},
                                    "mode": "center",
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
                    assert trigger["enabled"] is False
                    assert trigger["object_id"] is None
                    assert trigger["persistent"] is False
                    assert trigger["count"] == trigger["sequence"] == 0
                    fetched_trigger = _structured(
                        await session.call_tool(
                            "map_trigger_get",
                            {"handle": trigger_handle},
                        )
                    )
                    assert fetched_trigger["handle"] == trigger_handle
                    trigger_listing = _structured(
                        await session.call_tool("map_trigger_list", {"limit": 10})
                    )
                    assert any(
                        item["handle"] == trigger_handle for item in trigger_listing["triggers"]
                    )
                    empty_events = _structured(
                        await session.call_tool(
                            "map_trigger_events",
                            {"handle": trigger_handle, "after_sequence": 0, "limit": 10},
                        )
                    )
                    assert empty_events["events"] == []
                    assert empty_events["next_sequence"] == empty_events["latest_sequence"] == 0

                    assert (
                        _structured(
                            await session.call_tool(
                                "vehicle_teleport",
                                {
                                    "command": {
                                        "vehicle_id": "ego",
                                        "position": origin,
                                        "reset": True,
                                    }
                                },
                            )
                        )["ok"]
                        is True
                    )
                    assert (
                        _structured(
                            await session.call_tool(
                                "simulation_control", {"action": "step", "steps": 3}
                            )
                        )["ok"]
                        is True
                    )
                    enabled_trigger = _structured(
                        await session.call_tool(
                            "map_trigger_update",
                            {"patch": {"handle": trigger_handle, "enabled": True}},
                        )
                    )
                    assert enabled_trigger["enabled"] is True
                    assert isinstance(enabled_trigger["object_id"], int)
                    assert (
                        _structured(
                            await session.call_tool(
                                "simulation_control", {"action": "step", "steps": 3}
                            )
                        )["ok"]
                        is True
                    )
                    assert (
                        _structured(
                            await session.call_tool(
                                "map_trigger_events",
                                {"handle": trigger_handle, "after_sequence": 0, "limit": 10},
                            )
                        )["events"]
                        == []
                    )

                    assert (
                        _structured(
                            await session.call_tool(
                                "vehicle_teleport",
                                {
                                    "command": {
                                        "vehicle_id": "ego",
                                        "position": [
                                            trigger_center["x"],
                                            trigger_center["y"],
                                            trigger_center["z"],
                                        ],
                                        "reset": True,
                                    }
                                },
                            )
                        )["ok"]
                        is True
                    )
                    entered = await _wait_for_trigger_events(session, trigger_handle, ["enter"])
                    assert entered["events"][0]["subject_name"] == "ego"
                    assert entered["events"][0]["trigger_id"] == enabled_trigger["object_id"]
                    assert (
                        _structured(
                            await session.call_tool(
                                "vehicle_teleport",
                                {
                                    "command": {
                                        "vehicle_id": "ego",
                                        "position": origin,
                                        "reset": True,
                                    }
                                },
                            )
                        )["ok"]
                        is True
                    )
                    exited = await _wait_for_trigger_events(
                        session, trigger_handle, ["enter", "exit"]
                    )
                    assert [event["sequence"] for event in exited["events"]] == [1, 2]
                    assert [event["count"] for event in exited["events"]] == [1, 2]
                    assert exited["next_sequence"] == exited["latest_sequence"] == 2
                    exit_only = _structured(
                        await session.call_tool(
                            "map_trigger_events",
                            {"handle": trigger_handle, "after_sequence": 1, "limit": 10},
                        )
                    )
                    assert [event["event"] for event in exit_only["events"]] == ["exit"]
                    observed_trigger = _structured(
                        await session.call_tool(
                            "map_trigger_get",
                            {"handle": trigger_handle},
                        )
                    )
                    assert observed_trigger["last_event"]["event"] == "exit"
                    assert observed_trigger["last_event"]["subject_name"] == "ego"
                    disabled_trigger = _structured(
                        await session.call_tool(
                            "map_trigger_update",
                            {"patch": {"handle": trigger_handle, "enabled": False}},
                        )
                    )
                    assert disabled_trigger["enabled"] is False
                    assert disabled_trigger["object_id"] is None
                    deleted_trigger = _structured(
                        await session.call_tool(
                            "map_trigger_delete",
                            {"handle": trigger_handle, "confirm": True},
                        )
                    )
                    assert deleted_trigger == {"deleted": True, "handle": trigger_handle}
                    trigger_handle = None

                    blocked_save = await session.call_tool(
                        "map_save", {"level": "gridmap_v2", "confirm": True}
                    )
                    assert blocked_save.isError is True
                    assert "persistent map edits are disabled" in str(blocked_save.content).lower()

                    for action, arguments in (
                        (
                            "spawn",
                            {
                                "action": "spawn",
                                "max_amount": 1,
                                "police_ratio": 0.0,
                                "parked_amount": 0,
                            },
                        ),
                        ("stop", {"action": "stop", "stop_vehicles": True}),
                        ("reset", {"action": "reset"}),
                    ):
                        traffic = _structured(await session.call_tool("traffic_control", arguments))
                        assert traffic["ok"] is True, action

                    assert (
                        _structured(
                            await session.call_tool("simulation_control", {"action": "resume"})
                        )["ok"]
                        is True
                    )
                    assert (
                        _structured(
                            await session.call_tool("simulation_control", {"action": "realtime"})
                        )["ok"]
                        is True
                    )
                    reloaded = _structured(await session.call_tool("lua_extension_reload", {}))
                    assert reloaded["scheduled"] is True
                    assert reloaded["bridge_ready"] is True
                    bridge_after_reload = _structured(
                        await session.call_tool("lua_bridge_status", {"probe": True})
                    )
                    assert bridge_after_reload["connected"] is True
                    assert bridge_after_reload["authenticated"] is True

                    idle_autonomy = _structured(await session.call_tool("autonomy_status", {}))
                    assert idle_autonomy["running"] is False
                    native_ai_spec = {
                        "vehicle_id": "ego",
                        "mode": "native-ai",
                        "target_speed_mps": 3.0,
                        "max_speed_mps": 4.0,
                        "ai_mode": "span",
                        "ai_aggression": 0.1,
                        "ai_drive_in_lane": True,
                    }
                    started_autonomy = _structured(
                        await session.call_tool("autonomy_start", {"spec": native_ai_spec})
                    )
                    assert started_autonomy["running"] is True
                    assert started_autonomy["mode"] == "native-ai"
                    assert started_autonomy["backend"] == "beamng-native-ai"
                    assert started_autonomy["engine_deadman_armed"] is True
                    assert started_autonomy["engine_deadman_control_authorized"] is True
                    assert started_autonomy["engine_deadman_expires_in_ms"] > 0
                    await asyncio.sleep(settings.lua.safety_lease_seconds * 0.6)
                    live_autonomy = _structured(await session.call_tool("autonomy_status", {}))
                    assert live_autonomy["running"] is True
                    assert live_autonomy["engine_deadman_armed"] is True
                    assert live_autonomy["engine_deadman_control_authorized"] is True
                    assert live_autonomy["engine_deadman_last_renewal_age_ms"] is not None
                    assert live_autonomy["engine_deadman_last_error"] is None
                    autonomy_resource_live = await session.read_resource(
                        AnyUrl("beamng://autonomy")
                    )
                    autonomy_payload_live = json.loads(
                        autonomy_resource_live.contents[0].text  # type: ignore[union-attr]
                    )
                    assert autonomy_payload_live["running"] is True

                    stopped_autonomy = _structured(
                        await session.call_tool(
                            "autonomy_stop",
                            {"reason": "gauntlet_native_ai_complete"},
                        )
                    )
                    assert stopped_autonomy["running"] is False
                    assert stopped_autonomy["emergency_stopped"] is True
                    assert stopped_autonomy["emergency_reason"] == "gauntlet_native_ai_complete"
                    assert stopped_autonomy["engine_deadman_armed"] is False
                    assert stopped_autonomy["engine_deadman_control_authorized"] is False

                    restarted_autonomy = _structured(
                        await session.call_tool("autonomy_start", {"spec": native_ai_spec})
                    )
                    assert restarted_autonomy["engine_deadman_armed"] is True
                    first_stop = _structured(
                        await session.call_tool("emergency_stop", {"vehicle_id": "ego"})
                    )
                    assert first_stop["ok"] is True
                    first_outcomes = first_stop["data"]["outcomes"]
                    assert first_outcomes["autonomy"]["status"] == "applied"
                    assert first_outcomes["beamngpy"]["status"] == "applied"
                    assert first_outcomes["lua"]["status"] == "applied"
                    assert first_outcomes["engine_deadman"]["status"] == "disarmed"
                    post_stop = _structured(await session.call_tool("autonomy_status", {}))
                    assert post_stop["running"] is False
                    assert post_stop["engine_deadman_armed"] is False
                    assert post_stop["engine_deadman_control_authorized"] is False

                    second_stop = _structured(
                        await session.call_tool("emergency_stop", {"vehicle_id": "ego"})
                    )
                    assert second_stop["ok"] is True
                    second_outcomes = second_stop["data"]["outcomes"]
                    assert second_outcomes["autonomy"]["status"] == "not_running"
                    assert second_outcomes["beamngpy"]["status"] == "applied"
                    assert second_outcomes["lua"]["status"] == "applied"
                    assert second_outcomes["engine_deadman"]["status"] == "not_armed"

                    vision_refusal = await session.call_tool(
                        "autonomy_start",
                        {
                            "spec": {
                                "vehicle_id": "ego",
                                "mode": "vision-lane",
                                "sensor_name": f"gauntlet_camera_{suffix}",
                                "target_speed_mps": 3.0,
                                "max_speed_mps": 4.0,
                            }
                        },
                    )
                    assert vision_refusal.isError is True
                    assert "requires a BeamNG.tech license" in str(vision_refusal.content)
                    failed_vision = _structured(await session.call_tool("autonomy_status", {}))
                    assert failed_vision["running"] is False
                    assert failed_vision["engine_deadman_armed"] is False
                    assert failed_vision["engine_deadman_control_authorized"] is False
                    assert "BeamNG.tech license" in (
                        failed_vision["engine_deadman_last_error"] or ""
                    )

                    restarted_scenario = _structured(
                        await session.call_tool("scenario_control", {"action": "restart"})
                    )
                    assert restarted_scenario["ok"] is True
                    reset_bridge = await _wait_for_bridge(session)
                    assert reset_bridge["bridge_version"] == "0.3.0"
                    reset_vehicle_ids = {
                        vehicle["vehicle_id"]
                        for vehicle in _structured(await session.call_tool("vehicle_list", {}))
                    }
                    assert "ramp" in reset_vehicle_ids
                    assert "ego" not in reset_vehicle_ids
                    assert (
                        _structured(
                            await session.call_tool(
                                "simulation_control",
                                {
                                    "action": "deterministic",
                                    "steps_per_second": 60,
                                    "speed_factor": 1,
                                },
                            )
                        )["ok"]
                        is True
                    )
                    assert (
                        _structured(
                            await session.call_tool("simulation_control", {"action": "pause"})
                        )["ok"]
                        is True
                    )
                    reset_ramp_state = await _stabilized_vehicle_state(
                        session,
                        "ramp",
                        maximum_final_vertical_drift=0.05,
                        maximum_final_vertical_speed=0.1,
                        maximum_final_planar_speed=0.1,
                    )
                    _assert_grounded(
                        reset_ramp_state,
                        ramp_surface,
                        minimum_clearance=-0.15,
                        maximum_clearance=0.5,
                        maximum_planar_drift=0.5,
                    )
                    respawned_ego = _structured(
                        await session.call_tool(
                            "vehicle_spawn",
                            {
                                "spec": {
                                    "vehicle_id": "ego",
                                    "model": "etk800",
                                    "position": ego_spawn_position,
                                    "license_plate": "MCPTEST",
                                    "color": "White",
                                    "cling": False,
                                }
                            },
                        )
                    )
                    assert respawned_ego["vehicle_id"] == "ego"
                    assert math.dist(respawned_ego["position"][:2], ego_surface[:2]) <= 0.5
                    assert -0.2 <= respawned_ego["position"][2] - ego_surface[2] <= 1.5
                    reset_respawn = _structured(
                        await session.call_tool(
                            "vehicle_teleport",
                            {
                                "command": {
                                    "vehicle_id": "ego",
                                    "position": ego_spawn_position,
                                    "reset": True,
                                }
                            },
                        )
                    )
                    assert reset_respawn["ok"] is True
                    respawn_ai_disabled = _structured(
                        await session.call_tool(
                            "vehicle_ai_configure",
                            {"config": {"vehicle_id": "ego", "mode": "disabled"}},
                        )
                    )
                    assert respawn_ai_disabled["ok"] is True
                    reset_ego_braked = _structured(
                        await session.call_tool(
                            "vehicle_control",
                            {
                                "command": {
                                    "vehicle_id": "ego",
                                    "throttle": 0.0,
                                    "brake": 1.0,
                                    "parking_brake": 1.0,
                                    "steering": 0.0,
                                    "gear": 0,
                                }
                            },
                        )
                    )
                    assert reset_ego_braked["ok"] is True
                    reset_ego_state = await _stabilized_vehicle_state(
                        session,
                        "ego",
                        maximum_final_vertical_drift=0.1,
                        maximum_final_vertical_speed=0.35,
                        maximum_final_planar_speed=0.5,
                    )
                    _assert_grounded(
                        reset_ego_state,
                        ego_surface,
                        minimum_clearance=-0.2,
                        maximum_clearance=1.5,
                        maximum_planar_drift=1.5,
                    )
                    assert (
                        _structured(
                            await session.call_tool("vehicle_state", {"vehicle_id": "ego"})
                        )["vehicle_id"]
                        == "ego"
                    )
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
                    if bng is not None and not normal_disconnect:
                        with contextlib.suppress(Exception):
                            await session.call_tool("emergency_stop", {"vehicle_id": "ego"})
                        if trigger_handle is not None:
                            with contextlib.suppress(Exception):
                                await session.call_tool(
                                    "map_trigger_delete",
                                    {"handle": trigger_handle, "confirm": True},
                                )
                            trigger_handle = None
                        if map_object_name is not None:
                            with contextlib.suppress(Exception):
                                await session.call_tool(
                                    "map_object_delete",
                                    {"object_id": map_object_name, "confirm": True},
                                )
                            map_object_name = None
                        if scenario is None:
                            with contextlib.suppress(Exception):
                                candidate = await runtime.simulator._call(bng.scenario.get_current)
                                if getattr(candidate, "name", None) == scenario_name:
                                    scenario = candidate
                        with contextlib.suppress(Exception):
                            await session.call_tool("scenario_control", {"action": "stop"})
                        if scenario is not None:
                            with contextlib.suppress(Exception):
                                await runtime.simulator._call(scenario.delete, bng)
                            scenario = None
                        with contextlib.suppress(Exception):
                            await session.call_tool("simulator_disconnect", {})
            assert called_tools == declared_tools, {
                "missing": sorted(declared_tools - called_tools),
                "unexpected": sorted(called_tools - declared_tools),
            }
        finally:
            try:
                if bng is not None:
                    if not normal_disconnect:
                        with contextlib.suppress(Exception):
                            await runtime.emergency_stop("ego")
                        with contextlib.suppress(Exception):
                            if scenario is not None:
                                await runtime.simulator._call(bng.scenario.stop)
                                await runtime.simulator._call(scenario.delete, bng)
                    cleanup_owned_beamng_session(
                        bng,
                        owned_process=owned_process,
                    )
            finally:
                timer.cancel()
                cleanup_exact_live_artifacts(
                    profile=user,
                    files=(*installed_files, scenario_info, scenario_prefab),
                    empty_directories=(scenario_directory,),
                )
