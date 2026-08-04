"""Live smoke gate for the Giant Props pack framework.

Boots BeamNG.drive in the sentinel-isolated profile with the packaged Giant
Toaster installed, spawns the prop plus a subject vehicle in a disposable
smallgrid free-roam, and proves the shared contraption runtime end to end:

- the vehicle bootstrap loads the on-demand GE extension and registers,
- the runtime creates its parts, effects, and validated triggers,
- a subject teleported into a slot produces zone occupancy,
- the anticipation state machine runs to POP and injects launch velocity,
- the structured telemetry log carries the full ordered event chain with no
  namespaced errors.

The other nine contraptions share the same generated runtime core, so this
gate is the framework's live proof; per-mod behaviour still deserves its own
play-testing.
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

MOD_KEY = "giant_toaster"
MOD_ID = "ericrolph_giant_toaster"
ZIP_BASENAME = "giant_toaster_ericrolph.zip"
RUNTIME_EXTENSION = "ericrolph__giant__toaster_runtime"
LOG_TAG = "ERICROLPH_GIANT_TOASTER_RUNTIME"
LIVE_TEST_TAG = "GIANT_PROPS_LIVE_TEST"
PROP_NAME = f"{MOD_ID}_live_prop"
SUBJECT_NAME = f"{MOD_ID}_live_subject"
PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
EXPECTED_TRIGGERS = {
    "slot_l": "Contains",
    "slot_r": "Contains",
    "dial_zone": "Overlaps",
}
EXPECTED_PART_COUNT = 4
# Authored slot_l centre is (-1.55, -0.8) in the 2026-07-23 upright
# redesign; the model rotation is a proper 180-degree Z flip, so with an
# identity spawn quaternion the slot sits at world (+1.55, +0.8) from the
# prop origin, with its floor at authored z 4.15.
SLOT_WORLD_OFFSET_X = 1.55
SLOT_WORLD_OFFSET_Y = 0.8
SLOT_FLOOR_Z = 4.35
TICK_DURATION_SECONDS = 2.8


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Giant Props live gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Giant Props live gate requires a sentinel-isolated profile")
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
        "return jsonEncode({ok = true, z = position.z})",
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
def test_giant_toaster_prop_registers_ticks_and_pops(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    dist_root = PACK_ROOT / MOD_KEY / "dist"
    archive = dist_root / ZIP_BASENAME
    lock = json.loads((dist_root / f"{MOD_ID}.lock.json").read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"]

    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(
        user, Path("mods") / f"giant_toaster_live_{suffix}.zip"
    )
    scenario_name = f"giant_toaster_live_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    log_path = user / "beamng.log"
    log_start = f"giant_props_live_start_{suffix}"

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

            timer = threading.Timer(300.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid",
                scenario_name,
                description="Disposable Giant Toaster live smoke fixture",
            )
            subject = Vehicle(SUBJECT_NAME, "pigeon", license="TOAST")
            scenario.add_vehicle(
                subject, pos=(18.0, 18.0, 20.0), rot_quat=(0, 0, 0, 1), cling=False
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

            prop = Vehicle(PROP_NAME, MOD_ID, license="TOASTY")
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
            assert state["part_count"] == EXPECTED_PART_COUNT, state
            assert state["trigger_count"] == len(EXPECTED_TRIGGERS), state
            for zone, mode in EXPECTED_TRIGGERS.items():
                trigger = state["triggers"][zone]
                assert trigger["mode"] == mode, (zone, trigger)
                assert trigger["test_type"] == "Bounding box", (zone, trigger)
            origin = state["origin"]

            # Drop the subject into the left slot and let Contains fire.
            slot_position = (
                float(origin[0]) + SLOT_WORLD_OFFSET_X,
                float(origin[1]) + SLOT_WORLD_OFFSET_Y,
                surface_z + SLOT_FLOOR_Z + 0.6,
            )
            subject.teleport(pos=slot_position, rot_quat=(0, 0, 0, 1), reset=True)
            bng.control.step(30, wait=True)

            occupied = False
            for _ in range(20):
                bng.control.step(15, wait=True)
                state = _runtime_state(bng)
                counts = state.get("zone_counts", {})
                if counts.get("slot_l", 0) >= 1 or counts.get("slot_r", 0) >= 1:
                    occupied = True
                    break
            assert occupied, state

            baseline = _subject_probe(bng)
            assert baseline["ok"] is True, baseline
            baseline_z = float(baseline["z"])

            # Step through the tick anticipation plus flight time and track
            # the subject's peak altitude.
            peak_z = baseline_z
            total_steps = int((TICK_DURATION_SECONDS + 3.5) * 60)
            for _ in range(total_steps // 15):
                bng.control.step(15, wait=True)
                probe = _subject_probe(bng)
                if probe.get("ok"):
                    peak_z = max(peak_z, float(probe["z"]))
            height_gain = peak_z - baseline_z
            assert height_gain > 3.0, {
                "baseline_z": baseline_z,
                "peak_z": peak_z,
                "state": _runtime_state(bng),
            }
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

    # BeamNG buffers its file logger; parse only after the owned process has
    # closed so the marker and events are flushed.
    records, issues = _runtime_log_records(log_path, log_start)
    events = [str(record["event"]) for record in records]
    for required in (
        "prop_registered",
        "zone_enter",
        "toasting_started",
        "toast_popped",
        "subject_launched",
    ):
        assert required in events, {"events": events, "issues": issues}
    assert events.index("toasting_started") < events.index("toast_popped")
    assert not issues, issues
    print(
        json.dumps(
            {
                "mod": MOD_ID,
                "events": events,
                "log_issues": issues,
            },
            sort_keys=True,
        )
    )
