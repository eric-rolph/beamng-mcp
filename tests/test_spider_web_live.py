"""Live catch gate for the 200MPH Spider Web Catcher.

Boots BeamNG.drive in the sentinel-isolated profile with the packaged web
installed, spawns the prop plus a normal-sized ETK800 subject on the
run-up, injects a 62 m/s (139 mph) approach, and proves the catch chain:

- the elastic web arrests the car (deep stretch, no punch-through),
- the spider descends to inspect the catch and retreats,
- the web re-spins itself once the fly is removed,
- the telemetry log carries the ordered event chain with no namespaced
  errors.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import pytest
from beamngpy import BeamNGpy, Scenario, Vehicle

from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
)

MOD_KEY = "spider_web_catcher"
MOD_ID = "ericrolph_spider_web_catcher"
ZIP_BASENAME = "spider_web_catcher_ericrolph.zip"
RUNTIME_EXTENSION = "ericrolph__spider__web__catcher_runtime"
LOG_TAG = "ERICROLPH_SPIDER_WEB_CATCHER_RUNTIME"
LIVE_TEST_TAG = "SPIDER_WEB_CATCHER_LIVE_TEST"
PROP_NAME = f"{MOD_ID}_live_prop"
SUBJECT_NAME = f"{MOD_ID}_live_subject"
PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
EXPECTED_TRIGGERS = {"approach_zone": "Overlaps", "web_zone": "Overlaps"}
# The run-up is authored at -Y; identity spawn = 180-degree Z flip, so
# the approach is at world +Y and the hit travels toward world -Y.
START_WORLD_OFFSET_Y = 45.0
IMPACT_SPEED_MPS = 62.0
MIN_CATCH_DEPTH_M = 3.0
MAX_CATCH_DEPTH_M = 22.0
CAUGHT_SPEED_MPS = 10.0


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Spider Web live gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Spider Web live gate requires a sentinel-isolated profile")
    return home, user, binary


def _lua_json(bng: BeamNGpy, command: str) -> dict[str, Any]:
    payload = bng.control.queue_lua_command(command, response=True)
    decoded = json.loads(payload)
    assert isinstance(decoded, dict), decoded
    return decoded


def _runtime_state(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
        f"local prop = scenetree.findObject({PROP_NAME!r}); "
        "if not extension then return jsonEncode({loaded = false}) end; "
        "if not prop then return jsonEncode({loaded = true, registered = false}) end; "
        "local state = extension.getSystemState(prop:getID()); "
        "state.loaded = true; "
        "return jsonEncode(state)",
    )


def _subject_probe(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local subject = scenetree.findObject({SUBJECT_NAME!r}); "
        "if not subject then return jsonEncode({ok = false}) end; "
        "local position = subject:getPosition(); "
        "local velocity = subject:getVelocity(); "
        "return jsonEncode({ok = true, x = position.x, y = position.y, z = position.z, "
        "speed = velocity:length()})",
    )


def _runtime_log_records(log_path: Path, start_marker: str) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    issues: list[str] = []
    started = False
    payload = log_path.read_text(encoding="utf-8", errors="replace")
    for line in payload.splitlines():
        if start_marker in line:
            started = True
            continue
        if not started or LOG_TAG not in line:
            continue
        if "|E|" in line:
            issues.append(line)
        json_start = line.find("{")
        if json_start < 0:
            continue
        try:
            record = json.loads(line[json_start:])
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("event"), str):
            records.append(record)
    return records, issues


@pytest.mark.beamng_live
def test_spider_web_catches_normal_car(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    dist_root = PACK_ROOT / MOD_KEY / "dist"
    archive = dist_root / ZIP_BASENAME
    lock = json.loads((dist_root / f"{MOD_ID}.lock.json").read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"]

    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(user, Path("mods") / f"web_live_{suffix}.zip")
    scenario_name = f"web_live_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    log_path = user / "beamng.log"
    log_start = f"web_live_start_{suffix}"

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        existing_conflicts = (
            [
                str(path)
                for path in (user / "mods").glob("*.zip")
                if MOD_ID in path.name and path != installed_zip
            ]
            if (user / "mods").is_dir()
            else []
        )
        if existing_conflicts:
            pytest.fail(
                f"competing {MOD_ID} archives in the isolated profile: {existing_conflicts}"
            )
        if installed_zip.exists():
            pytest.fail(f"refusing to overwrite isolated-profile artifact: {installed_zip}")
        installed_zip.parent.mkdir(parents=True, exist_ok=True)
        with installed_zip.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        launch_user = user.parent if user.name.casefold() == "current" else user
        bng = BeamNGpy(
            "127.0.0.1",
            tcom_port,
            home=str(home),
            binary=str(binary),
            user=str(launch_user),
            quit_on_close=False,
            headless=True,
            nogpu=False,
        )
        scenario: Scenario | None = None
        owned_process: Any | None = None
        timer: threading.Timer | None = None
        try:

            def watchdog() -> None:
                process = bng.process
                if process is not None and process.poll() is None:
                    process.terminate()

            timer = threading.Timer(600.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid",
                scenario_name,
                description="Disposable Spider Web live catch fixture",
            )
            subject = Vehicle(SUBJECT_NAME, "etk800", license="THE FLY")
            scenario.add_vehicle(
                subject, pos=(-60.0, -60.0, 20.0), rot_quat=(0, 0, 0, 1), cling=False
            )
            scenario.make(bng)
            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)
            marker = _lua_json(
                bng,
                f"log('I', {LIVE_TEST_TAG!r}, {log_start!r}); return jsonEncode({{ok = true}})",
            )
            assert marker == {"ok": True}

            surface = _lua_json(
                bng,
                "local rayStart = vec3(0, 0, 200); "
                "local rayDistance = castRayStatic(rayStart, vec3(0, 0, -1), 300); "
                "return jsonEncode({distance = rayDistance, "
                "surface_z = rayStart.z - rayDistance})",
            )
            assert 0.0 < float(surface["distance"]) < 300.0, surface
            surface_z = float(surface["surface_z"])

            prop = Vehicle(PROP_NAME, MOD_ID, license="WEB")
            spawned = bng.vehicles.spawn(prop, (0.0, 0.0, surface_z), (0, 0, 0, 1), False, True)
            assert spawned is True

            state: dict[str, Any] = {}
            for _ in range(24):
                bng.control.step(15, wait=True)
                state = _runtime_state(bng)
                if state.get("registered"):
                    break
            assert state.get("loaded") is True, state
            assert state.get("registered") is True, state
            assert state["trigger_count"] == len(EXPECTED_TRIGGERS), state
            for zone, mode in EXPECTED_TRIGGERS.items():
                trigger = state["triggers"][zone]
                assert trigger["mode"] == mode, (zone, trigger)
            origin = state["origin"]
            origin_x, origin_y, _origin_z = (float(v) for v in origin)

            # Line the fly up on the run-up and slam it into the web.
            subject.teleport(
                pos=(origin_x, origin_y + START_WORLD_OFFSET_Y, surface_z + 0.5),
                rot_quat=(0, 0, 0, 1),
                reset=True,
            )
            bng.control.step(30, wait=True)
            launched = _lua_json(
                bng,
                f"local subject = scenetree.findObject({SUBJECT_NAME!r}); "
                "if not subject then return jsonEncode({ok = false}) end; "
                "subject:applyClusterVelocityScaleAdd("
                f"subject:getRefNodeId(), 0, 0, -{IMPACT_SPEED_MPS}, 0); "
                "return jsonEncode({ok = true})",
            )
            assert launched == {"ok": True}

            # Ride the catch: track depth (authored +Y = world -Y) and wait
            # for the web to bleed the speed off without punch-through.
            caught = False
            peak_depth = 0.0
            final_probe: dict[str, Any] = {}
            for _ in range(200):
                bng.control.step(15, wait=True)
                probe = _subject_probe(bng)
                if not probe.get("ok"):
                    continue
                depth = -(float(probe["y"]) - origin_y)
                peak_depth = max(peak_depth, depth)
                assert depth < MAX_CATCH_DEPTH_M, {
                    "detail": "subject punched through the web",
                    "depth": depth,
                    "probe": probe,
                }
                if depth > 0.5 and float(probe["speed"]) < CAUGHT_SPEED_MPS:
                    caught = True
                    final_probe = probe
                    break
            assert caught, {
                "detail": "web never arrested the subject",
                "peak_depth": peak_depth,
                "state": _runtime_state(bng),
                "probe": _subject_probe(bng),
            }
            assert peak_depth >= MIN_CATCH_DEPTH_M, {
                "detail": "web barely stretched - not an elastic catch",
                "peak_depth": peak_depth,
                "probe": final_probe,
            }

            # The spider comes down to look, then retreats.
            inspected = False
            for _ in range(120):
                bng.control.step(15, wait=True)
                state = _runtime_state(bng)
                if state.get("behavior_phase") in ("inspect", "retreat", "waiting_clear"):
                    inspected = True
                    break
            assert inspected, {"detail": "spider never inspected", "state": state}

            stats = state.get("behavior_stats") or {}
            assert int(stats.get("catches", 0)) >= 1, stats
            assert float(stats.get("peak_entry_mps", 0.0)) >= IMPACT_SPEED_MPS * 0.7, stats

            # Remove the fly; the web re-spins itself.
            subject.teleport(
                pos=(origin_x + 60.0, origin_y + 60.0, surface_z + 0.5),
                rot_quat=(0, 0, 0, 1),
                reset=True,
            )
            rearmed = False
            for _ in range(80):
                bng.control.step(30, wait=True)
                state = _runtime_state(bng)
                if state.get("behavior_phase") == "idle":
                    rearmed = True
                    break
            assert rearmed, {"detail": "web never re-armed", "state": state}
        finally:
            try:
                cleanup_owned_beamng_session(
                    bng,
                    owned_process=owned_process,
                    scenario=scenario,
                )
            finally:
                if timer is not None:
                    timer.cancel()
                cleanup_exact_live_artifacts(
                    profile=user,
                    files=(installed_zip,),
                    empty_directories=(scenario_directory,),
                )

    records, issues = _runtime_log_records(log_path, log_start)
    events = [str(record["event"]) for record in records]
    for required in (
        "prop_registered",
        "web_impact",
        "web_catch",
        "spider_inspected",
        "web_rearmed",
    ):
        assert required in events, {"events": events, "issues": issues}
    assert events.index("web_impact") < events.index("web_catch")
    assert events.index("web_catch") < events.index("spider_inspected")
    assert not issues, issues
    print(json.dumps({"mod": MOD_ID, "events": events}, sort_keys=True))
