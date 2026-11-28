"""Opt-in native MCP gauntlet: a fresh owned game, isolated profile, random port.

Set BEAMNG_MCP_TEST_NATIVE=1 plus the three BEAMNG_MCP_TEST_BEAMNG_* paths.
Never attaches to the user's running game or saves a level. See DEVELOPMENT.md.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from beamng_mcp.adapters.native_mcp import SUPPORTED_ACTIONS
from beamng_mcp.config import Settings
from beamng_mcp.mcp_adapter import create_mcp_server
from beamng_mcp.native_models import NativeSnapshot
from tests.live_support import (
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
)
from tests.test_beamng_live import _live_paths


@pytest.mark.beamng_live
async def test_native_owned_game_gauntlet(tmp_path: Path) -> None:
    if os.getenv("BEAMNG_MCP_TEST_NATIVE") != "1":
        pytest.skip("set BEAMNG_MCP_TEST_NATIVE=1 for the native owned-game gauntlet")
    home, user, binary = _live_paths()
    executable = binary if binary.is_absolute() else home / binary
    report_path = Path(
        os.getenv("BEAMNG_MCP_TEST_NATIVE_REPORT", str(tmp_path / "native-live.json"))
    )
    report: dict[str, Any] = {"checks": [], "passed": False, "profile": str(user)}
    with isolated_profile_lock(user), reserve_loopback_ports(1) as ports:
        port = ports.ports[0]
        # Engine upgrades can relocate current/. Keep the lock in the caller's root
        # and launch only a fresh child profile, never the root that owns the lock.
        profile = require_confined_profile_target(
            user, Path("native-runs") / uuid.uuid4().hex / "current"
        )
        profile.mkdir(parents=True)
        (profile / ".beamng-mcp-test-user").write_text("Owned native MCP test profile\n")
        report["profile"] = str(profile)
        settings_path = require_confined_profile_target(profile, Path("settings/settings.json"))
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        before = settings_path.read_bytes() if settings_path.exists() else None
        settings = json.loads(before) if before else {}
        settings.update(
            enableMcp=True,
            onlineFeatures="disable",
            GraphicDisplayModes="Window",
            GraphicResolution="800 600",
            GraphicQuality="Low",
            GraphicVSync=False,
        )
        settings_path.write_text(json.dumps(settings), encoding="utf-8")
        process = None
        watchdog = None
        runtime = None
        try:
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            ports.release()
            process = await asyncio.to_thread(
                subprocess.Popen,
                [
                    str(executable),
                    "-nosteam",
                    "-headless",
                    "-gfx",
                    "d3d12",
                    "-mcpport",
                    str(port),
                    "-userpath",
                    str(profile.parent),
                ],
                cwd=home,
                startupinfo=startup,
            )
            report["owned_pid"] = process.pid
            watchdog = threading.Timer(
                240, lambda: process.kill() if process.poll() is None else None
            )
            watchdog.daemon = True
            watchdog.start()
            url = f"http://127.0.0.1:{port}/mcp"
            report["url"] = url
            async with httpx.AsyncClient(trust_env=False, timeout=2) as http:
                for _ in range(90):
                    assert process.poll() is None, "owned game exited during startup"
                    try:
                        reply = await http.post(
                            url,
                            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                        )
                        if reply.status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(1)
                else:
                    pytest.fail("owned native MCP did not become ready")
                # Fixture-only, fixed read: match the engine's active user path to
                # the unique profile created above AND its startup log's user path.
                # The game listener is not visible to Windows TCP enumeration here.
                ownership = await http.post(
                    url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "run_lua",
                            "arguments": {"code": "return FS:getUserPath()"},
                        },
                    },
                )
                identity = ownership.json()["result"]
                assert identity["isError"] is False
                engine_profile = await asyncio.to_thread(
                    Path(identity["content"][0]["text"]).resolve
                )
                assert engine_profile == profile.resolve()
                startup_log = (profile / "beamng.log").read_text(errors="replace")
                assert (
                    str(profile) in startup_log
                    and "Command line argument (-userpath)" in startup_log
                )
                report["engine_log_header"] = startup_log.splitlines()[0]
                assert process.poll() is None
                report["profile_identity_verified"] = True
                # Fixture-only setup; unrestricted level loading is not a public tool.
                reply = await http.post(
                    url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "load_level", "arguments": {"name": "Utah"}},
                    },
                    timeout=60,
                )
                assert reply.json()["result"]["isError"] is False

            mcp, runtime = create_mcp_server(
                Settings(
                    native_mcp={"url": url, "timeout_seconds": 15},
                    workspace={"root": tmp_path / "workspace"},
                )
            )
            seen: set[str] = set()
            async with create_connected_server_and_client_session(mcp) as session:

                async def call(tool: str, payload: dict[str, Any]) -> Any:
                    started = time.monotonic()
                    result = await session.call_tool(tool, payload)
                    action = payload.get("request", {}).get("action", tool)
                    report["checks"].append(
                        {
                            "action": action,
                            "ok": not result.isError,
                            "seconds": round(time.monotonic() - started, 3),
                            "data": result.structuredContent,
                            "error": str(result.content)[:2000] if result.isError else None,
                        }
                    )
                    assert not result.isError, (action, result)
                    if action in SUPPORTED_ACTIONS:
                        seen.add(action)
                    if tool == "native_screenshot":
                        return result
                    return result.structuredContent

                async def inspect(action: str, **kwargs: Any) -> Any:
                    return (
                        await call("native_inspect", {"request": {"action": action, **kwargs}})
                    )["data"]

                report["tool_count"] = len((await session.list_tools()).tools)
                catalog = await call("native_status", {})
                assert not catalog["missing_upstream_actions"]
                for _ in range(90):
                    status = await inspect("get_status")
                    if status.get("level", "").endswith("utah/main.level.json") and status.get(
                        "vehicle"
                    ):
                        break
                    await asyncio.sleep(1)
                else:
                    pytest.fail("Utah did not load with a player vehicle")
                vid = status["vehicle"]["id"]
                report["initial_status"] = status
                await call(
                    "native_editor_control",
                    {"request": {"action": "set_editor_active", "active": True}},
                )
                for _ in range(30):
                    if (await inspect("editor_status")).get("active"):
                        break
                    await asyncio.sleep(0.2)
                else:
                    pytest.fail("editor did not initialize for inspection")
                for action in get_args(NativeSnapshot.model_fields["action"].annotation):
                    await inspect(action)
                for action in (
                    "get_vehicle",
                    "get_position",
                    "get_vehicle_damage",
                    "get_part_tree",
                    "get_vehicle_files",
                ):
                    await inspect(action, id=vid)
                for action in ("get_object", "serialize_object"):
                    await inspect(action, id=vid)
                await inspect("get_instability")
                await inspect("get_configs", model=status["vehicle"]["jbeam"])
                await inspect("get_logs", lines=50)
                await inspect("find_objects", **{"class": "BeamNGVehicle"})
                await inspect("list_editor_classes", pattern="Vehicle")
                await inspect("view_objects", **{"class": "vehicles", "maxDist": 100})
                pose = await inspect("get_position", id=vid)
                pos = pose["pos"]
                await inspect("get_ground_at_point", pos=pos)
                await inspect("get_navgraph", near=pos, radius=100, maxNodes=50)
                await inspect(
                    "raycast",
                    **{"from": {**pos, "z": pos["z"] + 10}, "to": {**pos, "z": pos["z"] - 10}},
                )
                await call(
                    "native_editor_control",
                    {"request": {"action": "set_editor_active", "active": False}},
                )

                for action, extras in [
                    ("pause_physics", {}),
                    ("step_physics", {"steps": 2}),
                    ("set_simulation_speed", {"scale": 0.5}),
                    ("resume_physics", {}),
                ]:
                    await call(
                        "native_simulation_control", {"request": {"action": action, **extras}}
                    )
                    state = await inspect("get_simulation_state")
                    if action == "pause_physics":
                        assert state["physicsRunning"] is False
                    elif action == "resume_physics":
                        assert state["physicsRunning"] is True
                    elif action == "set_simulation_speed":
                        assert abs(state["timeScale"] - 0.5) < 0.001

                for action, extras in [
                    ("set_camera", {"name": "free"}),
                    ("set_free_camera", {"pos": pos, "rot": pose["rot"]}),
                    ("orbit_camera", {"id": vid, "distance": 12, "yaw": 20, "pitch": 25}),
                ]:
                    await call("native_camera_control", {"request": {"action": action, **extras}})
                    camera = await inspect("get_camera_state")
                    assert camera["mode"] == ("orbit" if action == "orbit_camera" else "free")

                await call(
                    "native_editor_control",
                    {"request": {"action": "set_editor_active", "active": True}},
                )
                for _ in range(30):
                    if (await inspect("editor_status")).get("active"):
                        break
                    await asyncio.sleep(0.2)
                else:
                    pytest.fail("editor did not activate")
                for action, extras in [
                    ("select_editor_objects", {"ids": [vid]}),
                    ("fit_view_to_selection", {}),
                    ("clear_editor_selection", {}),
                    ("set_edit_mode", {"name": "objectSelect"}),
                    ("set_editor_active", {"active": False}),
                ]:
                    await call("native_editor_control", {"request": {"action": action, **extras}})
                    if action == "select_editor_objects":
                        assert (await inspect("get_editor_selection"))["count"] == 1

                await call(
                    "native_environment_control",
                    {
                        "request": {
                            "action": "set_time_of_day",
                            "time": 0.4,
                            "play": False,
                            "dayLength": 600,
                        }
                    },
                )
                lighting = await inspect("get_time_of_day")
                assert abs(lighting["time"] - 0.4) < 0.001
                await call(
                    "native_vehicle_control",
                    {
                        "request": {
                            "action": "set_position",
                            "id": vid,
                            "pos": pos,
                            "rot": pose["rot"],
                        }
                    },
                )
                await inspect("get_position", id=vid)
                await call(
                    "native_vehicle_control", {"request": {"action": "recover_vehicle", "id": vid}}
                )
                original_ids = {v["id"] for v in await inspect("get_vehicles")}
                await call(
                    "native_vehicle_control", {"request": {"action": "spawn", "model": "pickup"}}
                )
                for _ in range(30):
                    ids = {v["id"] for v in await inspect("get_vehicles")}
                    if original_ids < ids:
                        break
                    await asyncio.sleep(0.5)
                else:
                    pytest.fail("additive spawn did not retain existing vehicles and add one")

                for action, extras in [
                    ("toggle_ui", {"show": True}),
                    ("show_message", {"text": "BeamNG MCP isolated test", "ttl": 1}),
                    ("debug_draw", {"id": "beamng_mcp_debug_0", "pos": pos, "ttl": 2}),
                    ("debug_clear", {"id": "beamng_mcp_debug_0"}),
                ]:
                    await call("native_display_control", {"request": {"action": action, **extras}})
                for _ in range(12):
                    shot = await call("native_screenshot", {"scale": 0.2})
                    images = [item for item in shot.content if item.type == "image"]
                    if images:
                        report_path.with_suffix(".jpg").write_bytes(
                            base64.b64decode(images[0].data)
                        )
                        seen.add("screenshot_image")
                        break
                    await asyncio.sleep(0.5)
                else:
                    pytest.fail("screenshot did not complete")
                assert seen == SUPPORTED_ACTIONS, sorted(SUPPORTED_ACTIONS - seen)
                report["verified_actions"] = sorted(seen)
                report["passed"] = True
        finally:
            if runtime is not None:
                await runtime.shutdown()
            if watchdog is not None:
                watchdog.cancel()
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    await asyncio.to_thread(process.wait, timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait, timeout=5)
            report["owned_process_stopped"] = process is None or process.poll() is not None
            if before is None:
                settings_path.unlink(missing_ok=True)
            else:
                settings_path.write_bytes(before)
            await asyncio.to_thread(
                report_path.write_text, json.dumps(report, indent=2), encoding="utf-8"
            )
