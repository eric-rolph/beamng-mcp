"""Opt-in smoke test for the exact prebuilt Cannon Car Wash release archive."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import threading
import zipfile
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from beamng_mcp.config import Settings
from beamng_mcp.installer import MOD_DIRECTORY
from beamng_mcp.mcp_adapter import create_mcp_server
from examples.cannon_car_wash.build_distribution import (
    ZIP_NAME,
    build_distribution,
    verify_archive,
)
from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
    temporary_lua_bridge_config,
)
from tests.test_cannon_car_wash_phase3_live import (
    _configured_runtime,
    _extension_loaded,
    _structured,
    _wait_for_bridge,
)

EXAMPLE_ROOT = Path(__file__).parents[1] / "examples" / "cannon_car_wash"
DISTRIBUTION_ARCHIVE = EXAMPLE_ROOT / "dist" / ZIP_NAME
EXPECTED_SHA256 = "1168cbd637959c238714ecd3813597b53049a9c6690416fc7858f4c8c273f2b0"
EXPECTED_GAME_VERSION = "0.38.6"
MOD_ID = "ericrolph_cannon_car_wash"
SCENARIO_FRAGMENT = f"{MOD_ID}/{MOD_ID}.json"
TRUCK_ID = f"{MOD_ID}_truck"
LAUNCH_TRIGGER_NAME = f"{MOD_ID}_launch_trigger"
WASH_TRIGGER_NAME = f"{MOD_ID}_wash_activation_trigger"
SCENARIO_VISUAL_NAME = f"{MOD_ID}_scenario_visual"
EXTENSION_REGISTRY_NAME = f"scenario_{MOD_ID}"
LOG_TAG = "ERICROLPH_CANNON_CAR_WASH"
EXPECTED_TRUCK_POSITION = (-122.011475, -182.5, 100.747742)
EXPECTED_SURFACE_Z = 100.0
NAMESPACE_NEEDLE = b"cannon_car_wash"
NAMESPACE_TEXT_SUFFIXES = (
    ".cs",
    ".dae",
    ".html",
    ".jbeam",
    ".js",
    ".json",
    ".lua",
    ".mis",
    ".pc",
    ".txt",
    ".xml",
)
MAX_NAMESPACE_SCAN_BYTES = 128 * 1024 * 1024


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _support_mod_snapshot(root: Path) -> dict[str, str]:
    if root.is_symlink() or not root.is_dir():
        pytest.fail(f"BeamNG MCP unpacked support mod is unavailable: {root}")
    snapshot: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            pytest.fail(f"support mod contains a symlink: {path}")
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = _sha256(path.read_bytes())
    assert snapshot, f"BeamNG MCP unpacked support mod is empty: {root}"
    return snapshot


def _safe_files(user: Path, root: Path) -> list[Path]:
    pending = [require_confined_profile_target(user, root)]
    files: list[Path] = []
    while pending:
        directory = pending.pop()
        if not directory.is_dir():
            continue
        for child in directory.iterdir():
            child = require_confined_profile_target(user, child)
            if child.is_dir():
                pending.append(child)
            elif child.is_file():
                files.append(child)
    return files


def _stream_carries_namespace(handle: Any, *, byte_limit: int) -> tuple[bool, int]:
    scanned = 0
    overlap = b""
    while block := handle.read(1024 * 1024):
        scanned += len(block)
        if scanned > byte_limit:
            pytest.fail("active mod namespace inventory exceeded its bounded scan budget")
        searchable = overlap + block.lower()
        if NAMESPACE_NEEDLE in searchable:
            return True, scanned
        overlap = searchable[-(len(NAMESPACE_NEEDLE) - 1) :]
    return False, scanned


def _zip_carries_namespace(path: Path) -> bool:
    remaining = MAX_NAMESPACE_SCAN_BYTES
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            if any(NAMESPACE_NEEDLE.decode() in member.filename.casefold() for member in members):
                return True
            for member in members:
                lowered = member.filename.casefold()
                if member.is_dir() or not lowered.endswith(NAMESPACE_TEXT_SUFFIXES):
                    continue
                if member.flag_bits & 0x1:
                    pytest.fail(
                        f"cannot inventory encrypted active mod member: {path}!{member.filename}"
                    )
                with archive.open(member) as handle:
                    carries_namespace, scanned = _stream_carries_namespace(
                        handle, byte_limit=remaining
                    )
                if carries_namespace:
                    return True
                remaining -= scanned
    except (OSError, zipfile.BadZipFile) as exc:
        pytest.fail(f"cannot inventory active mod archive {path}: {exc}")
    return False


def _unpacked_mod_carries_namespace(user: Path, root: Path) -> bool:
    if NAMESPACE_NEEDLE.decode() in root.name.casefold():
        return True
    remaining = MAX_NAMESPACE_SCAN_BYTES
    for path in _safe_files(user, root):
        relative = path.relative_to(root).as_posix().casefold()
        if NAMESPACE_NEEDLE.decode() in relative:
            return True
        if not path.name.casefold().endswith(NAMESPACE_TEXT_SUFFIXES):
            continue
        with path.open("rb") as handle:
            carries_namespace, scanned = _stream_carries_namespace(handle, byte_limit=remaining)
        if carries_namespace:
            return True
        remaining -= scanned
    return False


def _competing_namespace_mods(
    user: Path,
    *,
    installed_zip: Path,
    support_root: Path,
) -> list[str]:
    mods_root = require_confined_profile_target(user, Path("mods"))
    conflicts: list[str] = []
    for path in _safe_files(user, mods_root):
        if path == installed_zip or path.is_relative_to(support_root):
            continue
        if path.suffix.casefold() == ".zip" and _zip_carries_namespace(path):
            conflicts.append(path.relative_to(mods_root).as_posix())

    unpacked_root = require_confined_profile_target(user, Path("mods") / "unpacked")
    if unpacked_root.is_dir():
        for child in unpacked_root.iterdir():
            child = require_confined_profile_target(user, child)
            if child == support_root or not child.is_dir():
                continue
            if _unpacked_mod_carries_namespace(user, child):
                conflicts.append(child.relative_to(mods_root).as_posix() + "/")
    return sorted(set(conflicts))


def _new_namespace_violations(log_path: Path, previous: bytes) -> list[str]:
    if not log_path.is_file():
        return []
    current = log_path.read_bytes()
    new_output = current[len(previous) :] if current.startswith(previous) else current
    tokens = (MOD_ID, EXTENSION_REGISTRY_NAME, LOG_TAG.casefold())
    violations: list[str] = []
    for line in new_output.decode("utf-8", errors="replace").splitlines():
        folded = line.casefold()
        test_cleanup_notice = (
            "|w|" in folded
            and "core_modmanager.initdb| mod vanished:" in folded
            and f"/mods/repo/{MOD_ID}_" in folded
        )
        if (
            not test_cleanup_notice
            and ("|e|" in folded or "|w|" in folded)
            and any(token in folded for token in tokens)
        ):
            violations.append(line)
    return violations


def _verified_release_payload(output_dir: Path) -> bytes:
    source_payload = DISTRIBUTION_ARCHIVE.read_bytes()
    assert _sha256(source_payload) == EXPECTED_SHA256
    verify_archive(DISTRIBUTION_ARCHIVE)
    fresh_result = build_distribution(output_dir)
    fresh_archive = Path(str(fresh_result["archive"]))
    fresh_payload = fresh_archive.read_bytes()
    verify_archive(fresh_archive)
    assert fresh_result["sha256"] == EXPECTED_SHA256
    assert fresh_payload == source_payload, (
        "the ignored release ZIP is not the deterministic build of the current mod tree"
    )
    return source_payload


async def _scene_contract(runtime: Any, bng: Any) -> dict[str, Any]:
    payload = await runtime.simulator._call(
        bng.control.queue_lua_command,
        "local function describe(name) "
        "local object = scenetree.findObject(name); "
        "if not object then return {name = name, exists = false} end; "
        "return {"
        "name = object:getName(), exists = true, class = object:getClassName(), "
        "mode = object:getField('triggerMode', 0), "
        "test_type = object:getField('triggerTestType', 0)"
        "}; end; "
        "return jsonEncode({"
        f"extension = {{name = '{EXTENSION_REGISTRY_NAME}', "
        f"loaded = extensions['{EXTENSION_REGISTRY_NAME}'] ~= nil}}, "
        f"truck = describe('{TRUCK_ID}'), "
        f"launch = describe('{LAUNCH_TRIGGER_NAME}'), "
        f"wash = describe('{WASH_TRIGGER_NAME}'), "
        f"visual = describe('{SCENARIO_VISUAL_NAME}')"
        "})",
        True,
    )
    return json.loads(payload)


async def _settle_truck(session: Any) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for _ in range(16):
        stepped = _structured(
            await session.call_tool("simulation_control", {"action": "step", "steps": 30})
        )
        assert stepped["ok"] is True
        state = _structured(await session.call_tool("vehicle_state", {"vehicle_id": TRUCK_ID}))
        samples.append(state)
        if len(samples) < 3:
            continue
        positions = [[float(value) for value in item["position"]] for item in samples[-3:]]
        velocity = [float(value) for value in state["velocity"]]
        horizontal_speed = math.hypot(velocity[0], velocity[1])
        if (
            max(position[2] for position in positions) - min(position[2] for position in positions)
            <= 0.06
            and abs(velocity[2]) <= 0.2
            and horizontal_speed <= 0.35
        ):
            return state
    pytest.fail(f"scenario truck did not settle on Gridmap V2: {samples[-3:]}")


@pytest.mark.beamng_live
@pytest.mark.asyncio
async def test_exact_cannon_car_wash_distribution_archive_loads_in_beamng(
    tmp_path: Path,
) -> None:
    home, user, binary = _configured_runtime()
    source_payload = _verified_release_payload(tmp_path / "fresh-distribution")

    installed_zip = require_confined_profile_target(user, Path("mods") / ZIP_NAME)
    repo_target = require_confined_profile_target(user, Path("mods") / "repo" / ZIP_NAME)
    profile_mods = require_confined_profile_target(user, Path("mods"))
    assert installed_zip.parent == profile_mods
    assert installed_zip != repo_target
    bridge_root = require_confined_profile_target(user, Path("mods") / "unpacked" / MOD_DIRECTORY)
    log_path = user / "beamng.log"
    installed_owned = False

    with isolated_profile_lock(user):
        destination_existed = installed_zip.exists()
        repo_target_existed = repo_target.exists()
        bridge_before = _support_mod_snapshot(bridge_root)
        log_before = log_path.read_bytes() if log_path.is_file() else b""
        try:
            if destination_existed:
                pytest.fail(f"refusing to overwrite existing distribution archive: {installed_zip}")
            if repo_target_existed:
                pytest.fail(f"duplicate distribution archive exists under mods/repo: {repo_target}")
            assert (
                _competing_namespace_mods(
                    user,
                    installed_zip=installed_zip,
                    support_root=bridge_root,
                )
                == []
            )
            handle = installed_zip.open("xb")
            installed_owned = True
            with handle:
                handle.write(source_payload)
                handle.flush()
                os.fsync(handle.fileno())
            installed_payload = installed_zip.read_bytes()
            assert installed_payload == source_payload
            assert _sha256(installed_payload) == EXPECTED_SHA256
            verify_archive(installed_zip)
            assert (
                _competing_namespace_mods(
                    user,
                    installed_zip=installed_zip,
                    support_root=bridge_root,
                )
                == []
            )

            with ExitStack() as runtime_safety:
                reservation = runtime_safety.enter_context(reserve_loopback_ports(2))
                tcom_port, lua_port = reservation.ports
                endpoint = runtime_safety.enter_context(
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
                        "allow_mod_install": False,
                        "max_file_bytes": 16 * 1024 * 1024,
                    },
                )
                mcp, runtime = create_mcp_server(settings)
                bng: Any | None = None
                owned_process: Any | None = None
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
                        reservation.release()
                        connected = _structured(
                            await session.call_tool("simulator_connect", {"launch": True})
                        )
                        assert connected["connected"] is True
                        bng = runtime.simulator._bng
                        assert bng is not None
                        owned_process = claim_owned_beamng_process(bng)

                        status = _structured(await session.call_tool("simulator_status", {}))
                        assert str(status["version"]).startswith(EXPECTED_GAME_VERSION), status

                        scenarios = _structured(
                            await session.call_tool("scenario_list", {"level": "gridmap_v2"})
                        )
                        packaged = next(
                            (
                                item
                                for item in scenarios
                                if SCENARIO_FRAGMENT
                                in str(item.get("source_file", "")).replace("\\", "/")
                            ),
                            None,
                        )
                        assert packaged is not None, scenarios

                        available = await runtime.simulator._call(bng.vehicles.get_available)
                        catalog = available.get("vehicles", available)
                        assert MOD_ID in catalog, sorted(
                            key for key in catalog if "cannon" in key.casefold()
                        )
                        catalog_entry = catalog[MOD_ID]
                        assert catalog_entry["name"] == "Cannon Car Wash"
                        assert catalog_entry["type"] == "Prop"

                        loaded = _structured(
                            await session.call_tool(
                                "scenario_load",
                                {
                                    "ref": {
                                        "level": "gridmap_v2",
                                        "name": packaged["name"],
                                    }
                                },
                            )
                        )
                        assert loaded["level"] == "gridmap_v2"
                        assert loaded["name"] == packaged["name"]
                        assert SCENARIO_FRAGMENT in str(loaded["source_file"]).replace("\\", "/")
                        started = _structured(
                            await session.call_tool("scenario_control", {"action": "start"})
                        )
                        assert started["ok"] is True
                        bridge = await _wait_for_bridge(session)
                        assert str(bridge["game_version"]).startswith(EXPECTED_GAME_VERSION), bridge

                        scene = await _scene_contract(runtime, bng)
                        assert scene["extension"] == {
                            "name": EXTENSION_REGISTRY_NAME,
                            "loaded": True,
                        }
                        assert scene["truck"]["exists"] is True
                        assert scene["truck"]["name"] == TRUCK_ID
                        assert scene["truck"]["class"] == "BeamNGVehicle"
                        assert scene["visual"]["exists"] is True
                        assert scene["visual"]["name"] == SCENARIO_VISUAL_NAME
                        assert scene["visual"]["class"] == "TSStatic"
                        assert scene["launch"] == {
                            "name": LAUNCH_TRIGGER_NAME,
                            "exists": True,
                            "class": "BeamNGTrigger",
                            "mode": "Contains",
                            "test_type": "Bounding box",
                        }
                        assert scene["wash"] == {
                            "name": WASH_TRIGGER_NAME,
                            "exists": True,
                            "class": "BeamNGTrigger",
                            "mode": "Overlaps",
                            "test_type": "Bounding box",
                        }

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
                        settled = await _settle_truck(session)
                        position = [float(value) for value in settled["position"]]
                        velocity = [float(value) for value in settled["velocity"]]
                        assert math.dist(position[:2], EXPECTED_TRUCK_POSITION[:2]) <= 1.0
                        assert 0.05 <= position[2] - EXPECTED_SURFACE_Z <= 1.4
                        assert math.hypot(velocity[0], velocity[1]) <= 0.35
                        assert abs(velocity[2]) <= 0.2

                        stopped = _structured(
                            await session.call_tool("scenario_control", {"action": "stop"})
                        )
                        assert stopped["ok"] is True
                        assert await _extension_loaded(runtime, bng) is False
                        disconnected = _structured(
                            await session.call_tool("simulator_disconnect", {})
                        )
                        assert disconnected["ok"] is True
                        normal_disconnect = True
                        cleanup_owned_beamng_session(bng, owned_process=owned_process)
                        owned_process_cleaned = True
                finally:
                    try:
                        if bng is not None and not normal_disconnect:
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

            violations = _new_namespace_violations(log_path, log_before)
            assert violations == []
        finally:
            if installed_owned:
                cleanup_exact_live_artifacts(profile=user, files=(installed_zip,))
            assert installed_zip.exists() is destination_existed
            assert repo_target.exists() is repo_target_existed
            assert _support_mod_snapshot(bridge_root) == bridge_before
