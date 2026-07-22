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
from PIL import Image, ImageChops, ImageStat

from beamng_mcp.config import Settings
from beamng_mcp.mcp_adapter import create_mcp_server
from examples.cannon_car_wash.build_distribution import EXPECTED_RUNTIME_FILES
from tests.live_support import (
    BeamNGLogCursor,
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
VALIDATION_MANIFESTS = EXAMPLE_ROOT / "validation" / "manifests"
PHASE2_MANIFEST = VALIDATION_MANIFESTS / "phase2.json"
PHASE3_MANIFEST = VALIDATION_MANIFESTS / "phase3.json"
PHASE4_MANIFEST = VALIDATION_MANIFESTS / "phase4.json"
SCENARIO_FRAGMENT = f"{MOD_ID}/{MOD_ID}.json"
TRUCK_ID = f"{MOD_ID}_truck"
LOG_TAG = "ERICROLPH_CANNON_CAR_WASH"
LAUNCH_TRIGGER_NAME = f"{MOD_ID}_launch_trigger"
WASH_TRIGGER_NAME = f"{MOD_ID}_wash_activation_trigger"
REPAIR_TRIGGER_NAME = f"{MOD_ID}_repair_trigger"
SCENARIO_VISUAL_NAME = f"{MOD_ID}_scenario_visual"
CRASH_WALL_NAME = f"{MOD_ID}_crash_wall"
EXTENSION_REGISTRY_NAME = f"scenario_{MOD_ID}"
EXPECTED_EFFECT_COUNT = 16
EXPECTED_EMITTER_COUNTS = {
    "BNGP_sprinkler": 6,
    "BNGP_waterfallsteam": 6,
    "BNGP_34": 2,
    "BNGP_2": 2,
}
GALLERY_DIRECTORY_ENV = "BEAMNG_MCP_CANNON_GALLERY_DIR"
GALLERY_RESOLUTION = (1280, 720)
PUBLIC_RUNTIME_FILES = frozenset(EXPECTED_RUNTIME_FILES)
PUBLIC_ROOTS = {"art", "levels", "lua", "vehicles"}
_LOG_CURSORS: dict[Path, BeamNGLogCursor] = {}
_LOG_RECORDS: dict[Path, list[dict[str, Any]]] = {}
_LOG_LINES: dict[Path, list[str]] = {}


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


def _configured_gallery_directory() -> Path | None:
    value = os.getenv(GALLERY_DIRECTORY_ENV)
    if value is None or not value.strip():
        return None
    return Path(value).expanduser().resolve(strict=False)


def _structured(result: Any) -> Any:
    assert result.isError is False, result.content
    assert result.structuredContent is not None
    structured = result.structuredContent
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    return structured


def _stage_full_mod(workspace: Path, runtime_mod_name: str) -> Path:
    source_files = {
        source.relative_to(MOD_SOURCE).as_posix(): source
        for source in MOD_SOURCE.rglob("*")
        if source.is_file() and not source.is_symlink()
    }
    assert len(PUBLIC_RUNTIME_FILES) == 40
    assert set(source_files) == PUBLIC_RUNTIME_FILES

    mod_root = workspace / "mods" / runtime_mod_name
    for relative in sorted(PUBLIC_RUNTIME_FILES):
        source = source_files[relative]
        destination = mod_root / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    staged_files = {
        path.relative_to(mod_root).as_posix() for path in mod_root.rglob("*") if path.is_file()
    }
    assert staged_files == PUBLIC_RUNTIME_FILES
    return mod_root


def _zip_members(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def _reset_log_cursor(log_path: Path) -> None:
    _LOG_CURSORS[log_path] = BeamNGLogCursor(
        log_path,
        namespaces=(LOG_TAG, MOD_ID, EXTENSION_REGISTRY_NAME),
        json_tag=LOG_TAG,
        schema_version=1,
        start_at_end=True,
    )
    _LOG_RECORDS[log_path] = []
    _LOG_LINES[log_path] = []


def _read_log_delta(log_path: Path) -> None:
    if log_path not in _LOG_CURSORS:
        _LOG_CURSORS[log_path] = BeamNGLogCursor(
            log_path,
            namespaces=(LOG_TAG, MOD_ID, EXTENSION_REGISTRY_NAME),
            json_tag=LOG_TAG,
            schema_version=1,
        )
        _LOG_RECORDS[log_path] = []
        _LOG_LINES[log_path] = []
    delta = _LOG_CURSORS[log_path].read()
    if delta.restarted:
        _LOG_RECORDS[log_path].clear()
        _LOG_LINES[log_path].clear()
    _LOG_RECORDS[log_path].extend(delta.records)
    _LOG_LINES[log_path].extend(delta.lines)


def _tagged_records(log_path: Path) -> list[dict[str, Any]]:
    _read_log_delta(log_path)
    return list(_LOG_RECORDS[log_path])


def _cannon_log_issues(log_path: Path, *, start_offset: int) -> list[str]:
    del start_offset  # Cursor initialization already marks the current run boundary.
    _read_log_delta(log_path)
    tokens = (LOG_TAG.casefold(), MOD_ID, EXTENSION_REGISTRY_NAME)
    return [
        line
        for line in _LOG_LINES[log_path]
        if ("|E|" in line or "|W|" in line) and any(token in line.casefold() for token in tokens)
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


async def _request_gallery_capture(
    runtime: Any,
    bng: Any,
    *,
    relative_path: Path,
    render_view_name: str,
    camera_position: tuple[float, float, float],
    camera_target: tuple[float, float, float],
) -> None:
    filename = relative_path.as_posix()
    directory = relative_path.parent.as_posix()
    payload = await runtime.simulator._call(
        bng.control.queue_lua_command,
        f"local directory = '{directory}'; "
        f"local filename = '{filename}'; "
        f"local capturePos = vec3({camera_position[0]}, {camera_position[1]}, "
        f"{camera_position[2]}); "
        f"local captureTarget = vec3({camera_target[0]}, {camera_target[1]}, "
        f"{camera_target[2]}); "
        "local captureRot = quatFromDir((captureTarget - capturePos):normalized(), "
        "vec3(0, 0, 1)); "
        "if not FS:directoryExists(directory) then FS:directoryCreate(directory, true) end; "
        "if not render_renderViews then extensions.load('render/renderViews') end; "
        "if not render_renderViews or not render_renderViews.takeScreenshot then "
        "return jsonEncode({ok = false, error = 'render_renderViews unavailable'}); "
        "end; "
        "if not core_camera then "
        "return jsonEncode({ok = false, error = 'player camera unavailable'}); "
        "end; "
        "local ok, captureError = pcall(function() "
        "render_renderViews.takeScreenshot({"
        f"renderViewName = '{render_view_name}', "
        "filename = filename, "
        "resolution = vec3(1280, 720, 0), "
        "pos = capturePos, "
        "rot = captureRot, "
        "fov = core_camera.getFovDeg(), "
        "nearPlane = 0.1, "
        "screenshotDelay = 0.1"
        "}); "
        "end); "
        "return jsonEncode({ok = ok, error = ok and nil or tostring(captureError)})",
        True,
    )
    status = json.loads(payload)
    assert status.get("ok") is True, status


def _read_gallery_capture(path: Path) -> tuple[Image.Image | None, OSError | None]:
    if not path.is_file():
        return None, None
    try:
        with Image.open(path) as captured:
            image = captured.convert("RGB")
            image.load()
        if image.size == GALLERY_RESOLUTION and max(ImageStat.Stat(image).stddev) > 1.0:
            return image, None
    except OSError as exc:
        return None, exc
    return None, None


async def _wait_for_gallery_capture(session: Any, path: Path) -> Image.Image:
    deadline = monotonic() + 30.0
    last_error: OSError | None = None
    while monotonic() < deadline:
        await _step(session, 3)
        image, image_error = await asyncio.to_thread(_read_gallery_capture, path)
        if image is not None:
            return image
        last_error = image_error or last_error
        await asyncio.sleep(0.05)
    pytest.fail(
        "BeamNG retail RenderView did not produce a non-blank 1280x720 gallery frame "
        f"within 30 seconds; capture={path}, last image error={last_error!r}"
    )


def _publish_gallery_captures(
    output_directory: Path,
    *,
    exterior_source: Path,
    exterior_image: Image.Image,
    wash_source: Path,
    wash_image: Image.Image,
) -> None:
    difference = ImageChops.difference(exterior_image, wash_image)
    assert max(ImageStat.Stat(difference).mean) > 1.0, (
        "Cannon Car Wash gallery frames are not materially distinct"
    )
    if output_directory.exists() and not output_directory.is_dir():
        pytest.fail(f"configured gallery destination is not a directory: {output_directory}")
    output_directory.mkdir(parents=True, exist_ok=True)
    destinations = (
        (exterior_source, output_directory / "01_exterior.png"),
        (wash_source, output_directory / "02_wash_active.png"),
    )
    for source, destination in destinations:
        shutil.copy2(source, destination)
        if not destination.is_file() or destination.stat().st_size == 0:
            pytest.fail(f"gallery capture was not published: {destination}")


async def _wait_for_tagged_event(
    log_path: Path,
    event: str,
    *,
    after_count: int = 0,
    attempts: int = 80,
) -> dict[str, Any]:
    for _ in range(attempts):
        matching = [record for record in _tagged_records(log_path) if record.get("event") == event]
        if len(matching) > after_count:
            return matching[-1]
        await asyncio.sleep(0.1)
    pytest.fail(f"timed out waiting for {LOG_TAG} event {event!r}")


async def _extension_loaded(runtime: Any, bng: Any) -> bool:
    payload = await runtime.simulator._call(
        bng.control.queue_lua_command,
        "return jsonEncode({loaded = extensions.isExtensionLoaded("
        f"'{EXTENSION_REGISTRY_NAME}')"
        "})",
        True,
    )
    return bool(json.loads(payload)["loaded"])


async def _wait_for_extension_loaded(runtime: Any, bng: Any, *, expected: bool) -> None:
    for _ in range(80):
        if await _extension_loaded(runtime, bng) is expected:
            return
        await asyncio.sleep(0.1)
    pytest.fail(
        f"scenario-owned extension {EXTENSION_REGISTRY_NAME!r} did not become loaded={expected}"
    )


async def _wash_system_state(runtime: Any, bng: Any) -> dict[str, Any]:
    payload = await runtime.simulator._call(
        bng.control.queue_lua_command,
        f"local extension = extensions['{EXTENSION_REGISTRY_NAME}']; "
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
    expected_active_effects = EXPECTED_EFFECT_COUNT if active else 0
    expected_active_emitters = EXPECTED_EMITTER_COUNTS if active else {}
    last_state: dict[str, Any] | None = None
    for _ in range(attempts):
        last_state = await _wash_system_state(runtime, bng)
        if (
            last_state.get("active") is active
            and int(last_state.get("effect_present_count", -1)) == EXPECTED_EFFECT_COUNT
            and int(last_state.get("effect_expected_count", -1)) == EXPECTED_EFFECT_COUNT
            and int(last_state.get("effect_active_count", -1)) == expected_active_effects
            and last_state.get("emitter_present_counts") == EXPECTED_EMITTER_COUNTS
            and last_state.get("emitter_active_counts") == expected_active_emitters
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
        f"local repair = scenetree.findObject('{REPAIR_TRIGGER_NAME}'); "
        "local function describe(trigger) "
        "if not trigger then return nil end; "
        "return {"
        "name = trigger:getName(), "
        "class = trigger:getClassName(), "
        "mode = trigger:getField('triggerMode', 0), "
        "test_type = trigger:getField('triggerTestType', 0)"
        "}; "
        "end; "
        "return jsonEncode({"
        "launch = describe(launch), wash = describe(wash), repair = describe(repair)})",
        True,
    )
    return json.loads(payload)


async def _vehicle_integrity_state(runtime: Any, vehicle: Any) -> dict[str, Any]:
    payload = await runtime.simulator._call(
        vehicle.queue_lua_command,
        "local partDamage = beamstate and type(beamstate.getPartDamageData) == 'function' "
        "and beamstate.getPartDamageData() or {}; "
        "local partDamageCount = 0; "
        "for _ in pairs(partDamage) do partDamageCount = partDamageCount + 1 end; "
        "local brokenBeamCount = 0; "
        "if v and v.data and v.data.beams then "
        "for _, beam in pairs(v.data.beams) do "
        "if type(beam) == 'table' and beam.cid ~= nil "
        "and obj:beamIsBroken(beam.cid) then brokenBeamCount = brokenBeamCount + 1 end; "
        "end; end; "
        "local deflatedTireCount = 0; "
        "if wheels and wheels.wheels then "
        "for _, wheel in pairs(wheels.wheels) do "
        "if type(wheel) == 'table' and wheel.isTireDeflated == true then "
        "deflatedTireCount = deflatedTireCount + 1 end; "
        "end; end; "
        "return jsonEncode({"
        "damage = beamstate and tonumber(beamstate.damage) or 0, "
        "part_damage_count = partDamageCount, broken_beam_count = brokenBeamCount, "
        "deflated_tire_count = deflatedTireCount})",
        True,
    )
    state = json.loads(payload)
    return {
        "damage": float(state["damage"]),
        "part_damage_count": int(state["part_damage_count"]),
        "broken_beam_count": int(state["broken_beam_count"]),
        "deflated_tire_count": int(state["deflated_tire_count"]),
    }


async def _damage_vehicle_for_repair(runtime: Any, vehicle: Any) -> dict[str, Any]:
    """Break one stable, deterministic beam and deflate one tire before entry."""

    payload = await runtime.simulator._call(
        vehicle.queue_lua_command,
        "local candidates = {}; "
        "for _, beam in pairs(v.data.beams or {}) do "
        "if type(beam) == 'table' and type(beam.cid) == 'number' "
        "and not obj:beamIsBroken(beam.cid) then "
        "local part = tostring(beam.partOrigin or beam.partName or beam.partPath or ''); "
        "local folded = string.lower(part); "
        "local priority = string.find(folded, 'bumper', 1, true) and 0 "
        "or (string.find(folded, 'body', 1, true) and 1 or 2); "
        "candidates[#candidates + 1] = {cid = beam.cid, part = part, priority = priority}; "
        "end; end; "
        "table.sort(candidates, function(left, right) "
        "if left.priority ~= right.priority then return left.priority < right.priority end; "
        "return left.cid < right.cid end); "
        "local selected = candidates[1]; "
        "if not selected then return jsonEncode({ok = false, error = 'no intact beam'}) end; "
        "obj:breakBeam(selected.cid); "
        "local wheelIds = {}; "
        "for wheelId, wheel in pairs((wheels and wheels.wheels) or {}) do "
        "if type(wheel) == 'table' and wheel.isTireDeflated ~= true then "
        "wheelIds[#wheelIds + 1] = wheelId end; end; "
        "table.sort(wheelIds, function(left, right) return left < right end); "
        "local wheelId = wheelIds[1]; "
        "if wheelId == nil or not beamstate or type(beamstate.deflateTire) ~= 'function' then "
        "return jsonEncode({ok = false, error = 'no inflatable tire'}); end; "
        "beamstate.deflateTire(wheelId); "
        "return jsonEncode({ok = true, beam_cid = selected.cid, "
        "beam_part = selected.part, wheel_id = wheelId})",
        True,
    )
    result = json.loads(payload)
    assert result.get("ok") is True, result
    return result


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
    # Phase 4 executes the complete Phase 3 wash path before impact telemetry,
    # so it can publish the same canonical gallery without a redundant cold
    # Phase 3 launch.
    gallery_output_directory = _configured_gallery_directory()
    gallery_relative_directory = (
        Path("screenshots") / "beamng-mcp" / f"cannon-gallery-{suffix}"
        if gallery_output_directory is not None
        else None
    )
    gallery_temp_directory = (
        require_confined_profile_target(user, gallery_relative_directory)
        if gallery_relative_directory is not None
        else None
    )
    gallery_exterior_path = (
        gallery_temp_directory / "01_exterior.png" if gallery_temp_directory is not None else None
    )
    gallery_wash_path = (
        gallery_temp_directory / "02_wash_active.png"
        if gallery_temp_directory is not None
        else None
    )
    gallery_exterior_image: Image.Image | None = None
    gallery_temp_owned = False
    runtime_mod_name = f"{MOD_ID}_phase{phase}_{suffix}"
    workspace = tmp_path / "workspace"
    _stage_full_mod(workspace, runtime_mod_name)
    phase2 = json.loads(PHASE2_MANIFEST.read_text(encoding="utf-8"))
    phase3 = json.loads(PHASE3_MANIFEST.read_text(encoding="utf-8"))
    phase4 = json.loads(PHASE4_MANIFEST.read_text(encoding="utf-8")) if phase == 4 else None
    assert phase2["vehicle"]["name"] == TRUCK_ID
    assert phase2["trigger"]["name"] == LAUNCH_TRIGGER_NAME
    assert phase2["wash_activation_trigger"]["name"] == WASH_TRIGGER_NAME
    assert phase2["repair_trigger"]["name"] == REPAIR_TRIGGER_NAME
    assert phase2["wash_effects"]["visual_name"] == SCENARIO_VISUAL_NAME
    assert len(phase2["wash_effects"]["effects"]) == EXPECTED_EFFECT_COUNT
    assert phase2["wash_effects"]["emitter_counts"] == EXPECTED_EMITTER_COUNTS
    assert phase3["extension"] == {
        "registry_name": EXTENSION_REGISTRY_NAME,
        "file": f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.lua",
        "scenario_entry": {"name": MOD_ID},
        "lifecycle": "scenario_owned",
    }
    assert phase3["telemetry"]["log_tag"] == LOG_TAG
    if phase4 is not None:
        assert phase4["crash_target"]["name"] == CRASH_WALL_NAME
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
        cannon_log_offset = 0

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
                assert len(members) == len(PUBLIC_RUNTIME_FILES)
                assert members == PUBLIC_RUNTIME_FILES
                assert {member.partition("/")[0] for member in members} == PUBLIC_ROOTS
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
                cannon_log_offset = log_path.stat().st_size if log_path.is_file() else 0
                _reset_log_cursor(log_path)
                assert await _extension_loaded(runtime, bng) is False

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
                await _wait_for_extension_loaded(runtime, bng, expected=True)

                loaded_before_reload = sum(
                    record.get("event") == "extension_loaded"
                    for record in _tagged_records(log_path)
                )
                unloaded_before_reload = sum(
                    record.get("event") == "extension_unloaded"
                    for record in _tagged_records(log_path)
                )
                sessions_before_reload = sum(
                    record.get("event") == "session_start" for record in _tagged_records(log_path)
                )
                stopped_for_reload = _structured(
                    await session.call_tool("scenario_control", {"action": "stop"})
                )
                assert stopped_for_reload["ok"] is True
                await _wait_for_tagged_event(
                    log_path,
                    "extension_unloaded",
                    after_count=unloaded_before_reload,
                )
                await _wait_for_extension_loaded(runtime, bng, expected=False)

                _structured(
                    await session.call_tool(
                        "scenario_load",
                        {"ref": {"level": "gridmap_v2", "name": packaged["name"]}},
                    )
                )
                reloaded = _structured(
                    await session.call_tool("scenario_control", {"action": "start"})
                )
                assert reloaded["ok"] is True
                await _wait_for_tagged_event(
                    log_path,
                    "extension_loaded",
                    after_count=loaded_before_reload,
                )
                await _wait_for_tagged_event(
                    log_path,
                    "session_start",
                    after_count=sessions_before_reload,
                )
                await _wait_for_extension_loaded(runtime, bng, expected=True)
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
                assert trigger_scene_state["repair"]["name"] == REPAIR_TRIGGER_NAME
                assert trigger_scene_state["repair"]["class"] == "BeamNGTrigger"
                assert trigger_scene_state["repair"]["mode"] == "Overlaps"
                assert trigger_scene_state["repair"]["test_type"] == "Bounding box"
                initial_wash_state = await _wait_for_wash_system_state(runtime, bng, active=False)
                assert int(initial_wash_state["subject_count"]) == 0
                assert initial_wash_state["repair_trigger"] == {
                    "name": REPAIR_TRIGGER_NAME,
                    "id": initial_wash_state["repair_trigger"]["id"],
                    "mode": "Overlaps",
                    "test_type": "Bounding box",
                }
                if phase == 4:
                    assert phase4 is not None
                    crash_wall = _structured(
                        await session.call_tool("map_object_get", {"object_id": CRASH_WALL_NAME})
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
                if gallery_output_directory is not None:
                    assert gallery_relative_directory is not None
                    assert gallery_temp_directory is not None
                    assert gallery_exterior_path is not None
                    if gallery_temp_directory.exists():
                        pytest.fail(
                            "refusing to overwrite an existing isolated-profile gallery "
                            f"directory: {gallery_temp_directory}"
                        )
                    gallery_temp_owned = True
                    asset_position = tuple(float(value) for value in phase2["asset"]["position"])
                    await _request_gallery_capture(
                        runtime,
                        bng,
                        relative_path=gallery_relative_directory / "01_exterior.png",
                        render_view_name=f"beamngMcpCannonExterior{suffix}",
                        camera_position=(
                            asset_position[0],
                            asset_position[1] - 16.0,
                            asset_position[2] + 3.0,
                        ),
                        camera_target=(
                            asset_position[0],
                            asset_position[1],
                            asset_position[2] + 2.35,
                        ),
                    )
                    gallery_exterior_image = await _wait_for_gallery_capture(
                        session, gallery_exterior_path
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
                damage_sensor_name = f"cannon_phase{phase}_damage"
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
                clean_damage_reading = _structured(
                    await session.call_tool("sensor_poll", {"name": damage_sensor_name})
                )
                live_vehicle = await runtime.simulator._vehicle(TRUCK_ID)
                clean_integrity = await _vehicle_integrity_state(runtime, live_vehicle)
                assert clean_integrity == {
                    "damage": pytest.approx(0.0, abs=0.01),
                    "part_damage_count": 0,
                    "broken_beam_count": 0,
                    "deflated_tire_count": 0,
                }
                assert float(clean_damage_reading["data"]["damage"]) <= 0.01
                damage_injection = await _damage_vehicle_for_repair(runtime, live_vehicle)
                damaged_integrity: dict[str, Any] | None = None
                for _ in range(60):
                    await _step(session, 1)
                    candidate_integrity = await _vehicle_integrity_state(runtime, live_vehicle)
                    if (
                        candidate_integrity["broken_beam_count"] >= 1
                        and candidate_integrity["deflated_tire_count"] >= 1
                        and (
                            candidate_integrity["damage"] > clean_integrity["damage"]
                            or candidate_integrity["part_damage_count"] > 0
                        )
                    ):
                        damaged_integrity = candidate_integrity
                        break
                assert damaged_integrity is not None, damage_injection
                assert damaged_integrity["damage"] > clean_integrity["damage"] or (
                    damaged_integrity["part_damage_count"] > 0
                )
                assert damaged_integrity["broken_beam_count"] >= 1
                assert damaged_integrity["deflated_tire_count"] >= 1
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
                    "lua_errors": _cannon_log_issues(
                        log_path,
                        start_offset=cannon_log_offset,
                    ),
                }
                assert trigger_record is not None, drive_diagnostics
                repair_records = [
                    record
                    for record in _tagged_records(log_path)
                    if int(record.get("session", 0)) == session_number
                    and record.get("event")
                    in {
                        "repair_snapshot",
                        "repair_requested",
                        "repair_reset_ack",
                        "repair_complete",
                    }
                ]
                repair_snapshots = [
                    record for record in repair_records if record.get("event") == "repair_snapshot"
                ]
                repair_reset_acks = [
                    record for record in repair_records if record.get("event") == "repair_reset_ack"
                ]
                repair_completions = [
                    record for record in repair_records if record.get("event") == "repair_complete"
                ]
                assert len(repair_snapshots) == 1, repair_records
                assert len(repair_reset_acks) == 1, repair_records
                assert len(repair_completions) == 1, repair_records
                repair_snapshot = repair_snapshots[0]
                repair_complete = repair_completions[0]
                repair_token = int(repair_snapshot["repair_token"])
                assert int(repair_reset_acks[0]["repair_token"]) == repair_token
                assert int(repair_complete["repair_token"]) == repair_token
                assert int(repair_snapshot["broken_beams_before"]) >= 1
                assert int(repair_snapshot["deflated_tires_before"]) >= 1
                assert (
                    float(repair_snapshot["damage_before"]) > 0.01
                    or int(repair_snapshot["part_damage_before"]) > 0
                )
                assert float(repair_complete["damage_after"]) <= 0.01
                assert int(repair_complete["part_damage_after"]) == 0
                assert int(repair_complete["broken_beams_after"]) == 0
                assert int(repair_complete["deflated_tires_after"]) == 0
                assert repair_complete["pose_policy"] == "restore_exact_pre_repair_pose"
                assert float(repair_complete["position_drift_m"]) <= 0.15
                assert float(repair_complete["heading_dot"]) >= 0.995
                assert float(repair_complete["upright_dot"]) >= 0.98
                assert repair_complete["travel_sign_preserved"] is True
                restored_integrity = await _vehicle_integrity_state(runtime, live_vehicle)
                assert restored_integrity["damage"] <= 0.01
                assert restored_integrity["part_damage_count"] == 0
                assert restored_integrity["broken_beam_count"] == 0
                assert restored_integrity["deflated_tire_count"] == 0
                records_after_repair = _tagged_records(log_path)
                assert not any(
                    record.get("event") == "abort"
                    and record.get("reason") == "vehicle_reset"
                    and int(record.get("session", 0)) == session_number
                    for record in records_after_repair
                )
                assert not any(
                    record.get("event") == "wash_subject_removed"
                    and record.get("reason") == "vehicle_reset"
                    and int(record.get("session", 0)) == session_number
                    for record in records_after_repair
                )
                restored_damage_reading = _structured(
                    await session.call_tool("sensor_poll", {"name": damage_sensor_name})
                )
                initial_damage = float(restored_damage_reading["data"]["damage"])
                initial_part_damage = restored_damage_reading["data"].get("part_damage") or {}
                assert initial_damage <= 0.01
                assert initial_part_damage == {}
                pre_go_damage_samples = [initial_damage]
                pre_go_part_damage_samples = [initial_part_damage]
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
                if gallery_output_directory is not None:
                    assert gallery_relative_directory is not None
                    assert gallery_exterior_path is not None
                    assert gallery_wash_path is not None
                    assert gallery_exterior_image is not None
                    repaused = _structured(
                        await session.call_tool("simulation_control", {"action": "pause"})
                    )
                    assert repaused["ok"] is True
                    await _request_gallery_capture(
                        runtime,
                        bng,
                        relative_path=gallery_relative_directory / "02_wash_active.png",
                        render_view_name=f"beamngMcpCannonWashActive{suffix}",
                        camera_position=(
                            asset_position[0],
                            asset_position[1] - 7.8,
                            asset_position[2] + 2.65,
                        ),
                        camera_target=(
                            asset_position[0],
                            asset_position[1] + 4.5,
                            asset_position[2] + 2.1,
                        ),
                    )
                    gallery_wash_image = await _wait_for_gallery_capture(session, gallery_wash_path)
                    launch_already_occurred = any(
                        record.get("event") == "launch"
                        and record.get("run") == trigger_record["run"]
                        for record in _tagged_records(log_path)
                    )
                    assert launch_already_occurred is False, (
                        "active-wash gallery capture completed after launch"
                    )
                    _publish_gallery_captures(
                        gallery_output_directory,
                        exterior_source=gallery_exterior_path,
                        exterior_image=gallery_exterior_image,
                        wash_source=gallery_wash_path,
                        wash_image=gallery_wash_image,
                    )
                    gallery_exterior_image.close()
                    gallery_wash_image.close()
                    resumed = _structured(
                        await session.call_tool("simulation_control", {"action": "resume"})
                    )
                    assert resumed["ok"] is True
                    realtime = _structured(
                        await session.call_tool("simulation_control", {"action": "realtime"})
                    )
                    assert realtime["ok"] is True

                hold_anchor = _structured(
                    await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID})
                )
                prelaunch_damage_reading = _structured(
                    await session.call_tool("sensor_poll", {"name": damage_sensor_name})
                )
                pre_go_damage_samples.append(float(prelaunch_damage_reading["data"]["damage"]))
                pre_go_part_damage_samples.append(
                    prelaunch_damage_reading["data"].get("part_damage") or {}
                )
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
                    run_events_before_damage = {
                        str(record.get("event"))
                        for record in records
                        if record.get("run") == trigger_record["run"]
                    }
                    if "go" not in run_events_before_damage:
                        hold_damage = _structured(
                            await session.call_tool("sensor_poll", {"name": damage_sensor_name})
                        )
                        records_after_damage = _tagged_records(log_path)
                        run_events_after_damage = {
                            str(record.get("event"))
                            for record in records_after_damage
                            if record.get("run") == trigger_record["run"]
                        }
                        if "go" not in run_events_after_damage:
                            pre_go_damage_samples.append(float(hold_damage["data"]["damage"]))
                            pre_go_part_damage_samples.append(
                                hold_damage["data"].get("part_damage") or {}
                            )
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
                assert launch_state is not None, _cannon_log_issues(
                    log_path,
                    start_offset=cannon_log_offset,
                )
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
                prelaunch_damage = max(pre_go_damage_samples)
                prelaunch_damage_delta = prelaunch_damage - initial_damage
                assert prelaunch_damage_delta == pytest.approx(0.0, abs=1e-3), {
                    "reason": "vehicle accumulated damage before the GO event",
                    "initial_damage": initial_damage,
                    "peak_pre_go_damage": prelaunch_damage,
                    "pre_go_damage_delta": prelaunch_damage_delta,
                    "sample_count": len(pre_go_damage_samples),
                }
                assert all(
                    sample == initial_part_damage for sample in pre_go_part_damage_samples
                ), {
                    "reason": "part-damage map changed before the GO event",
                    "initial_part_damage": initial_part_damage,
                    "pre_go_part_damage_samples": pre_go_part_damage_samples,
                }

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
                            "initial_damage": initial_damage,
                            "peak_pre_go_damage": prelaunch_damage,
                            "pre_go_damage_delta": prelaunch_damage_delta,
                            "pre_go_part_damage_count": len(initial_part_damage),
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
                unloaded_before_stop = sum(
                    record.get("event") == "extension_unloaded"
                    for record in _tagged_records(log_path)
                )
                stopped = _structured(
                    await session.call_tool("scenario_control", {"action": "stop"})
                )
                assert stopped["ok"] is True
                await _wait_for_tagged_event(
                    log_path,
                    "extension_unloaded",
                    after_count=unloaded_before_stop,
                )
                await _wait_for_extension_loaded(runtime, bng, expected=False)
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
                    "repair_trigger_enter",
                    "repair_snapshot",
                    "repair_requested",
                    "repair_reset_ack",
                    "repair_complete",
                    "containment_verified",
                    "trigger_enter",
                    "hold_requested",
                    "hold_ack",
                    "hold_start",
                    "countdown_3",
                    "countdown_timer_start",
                    "countdown_2",
                    "countdown_1",
                    "release_requested",
                    "release_ack",
                    "release",
                    "go",
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
                assert int(wash_start_record["effect_count"]) == EXPECTED_EFFECT_COUNT
                assert wash_start_record["emitter_counts"] == EXPECTED_EMITTER_COUNTS
                assert sum(event == "repair_requested" for event in event_names) == 1
                assert sum(event == "repair_reset_ack" for event in event_names) == 1
                assert sum(event == "repair_complete" for event in event_names) == 1
                assert not any(
                    record.get("event") == "abort" and record.get("reason") == "vehicle_reset"
                    for record in session_records
                )
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
                assert (
                    _cannon_log_issues(
                        log_path,
                        start_offset=cannon_log_offset,
                    )
                    == []
                )
                wash_telemetry = {
                    "launch_trigger": trigger_scene_state["launch"],
                    "activation_trigger": trigger_scene_state["wash"],
                    "repair_trigger": trigger_scene_state["repair"],
                    "contained_vehicle_oobb": contained_oobb,
                    "initial": initial_wash_state,
                    "active_on_entry": active_wash_state,
                    "final": final_wash_state,
                }
                repair_telemetry = {
                    "injection": damage_injection,
                    "clean_integrity": clean_integrity,
                    "damaged_integrity": damaged_integrity,
                    "restored_integrity": restored_integrity,
                    "snapshot": repair_snapshot,
                    "complete": repair_complete,
                }
                if phase4_telemetry is not None:
                    phase4_telemetry["countdown_elapsed_seconds"] = countdown
                    phase4_telemetry["ordered_lua_events"] = event_names
                    phase4_telemetry["wash_systems"] = wash_telemetry
                    phase4_telemetry["repair"] = repair_telemetry
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
                                "repair": repair_telemetry,
                                "countdown_elapsed_seconds": countdown,
                                "pre_go_damage": {
                                    "initial": initial_damage,
                                    "peak": prelaunch_damage,
                                    "delta": prelaunch_damage_delta,
                                    "part_damage_count": len(initial_part_damage),
                                    "sample_count": len(pre_go_damage_samples),
                                },
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
                    files=tuple(
                        path
                        for path in (
                            installed_path,
                            gallery_exterior_path if gallery_temp_owned else None,
                            gallery_wash_path if gallery_temp_owned else None,
                        )
                        if path is not None
                    ),
                    empty_directories=(
                        (gallery_temp_directory,)
                        if gallery_temp_owned and gallery_temp_directory is not None
                        else ()
                    ),
                )


@pytest.mark.beamng_live
@pytest.mark.asyncio
async def test_cannon_car_wash_phase3_countdown_hold_and_launch(tmp_path: Path) -> None:
    await _run_cannon_car_wash_live_gate(tmp_path, phase=3)
