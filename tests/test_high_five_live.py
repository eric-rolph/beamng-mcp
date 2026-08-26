"""Live gate for Charlie's High Five: does it actually lead a moving car?

Everything about this mod is verified headless except the one thing that
matters, and the headless harness cannot reach it. `test_high_five_sequence`
drives the real generated `runtime.lua` under stubbed engine globals, so it
proves the state machine's arithmetic — but it feeds that machine synthetic
positions. It has never been told the truth by a physics engine.

So this boots BeamNG in the sentinel-isolated profile, spawns the prop on
smallgrid, puts a car 85 m up the approach corridor, and drives it at the
machine under its own power. The assertions are the two claims the mod is
sold on and the four that hold them up:

- the prop registers with its 26 posable parts and both authored triggers,
- entering the corridor ARMS it (a `zone_enter` on `approach`),
- it alerts, winds up, and swings,
- the swing CONNECTS with a car that never stopped moving — `high_five_
  slapped` rather than `high_five_whiffed`,
- the subject is launched, and the engine agrees: a real speed jump and a
  real change of heading, measured off the vehicle, not off the runtime's
  own telemetry,
- and the runtime logs no errors doing any of it.

The lead is what is on trial. A prop that waits for contact and then reacts
would also produce most of this chain against a PARKED car; it would not
produce it against one arriving at 22 m/s, because by the time a reactive
machine had finished a 0.85 s wind-up the car would be 19 m past it.
"""

from __future__ import annotations

import hashlib
import json
import math
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

MOD_KEY = "high_five"
MOD_ID = "ericrolph_high_five"
ZIP_BASENAME = "high_five_ericrolph.zip"
RUNTIME_EXTENSION = "ericrolph__high__five_runtime"
LOG_TAG = "ERICROLPH_HIGH_FIVE_RUNTIME"
LIVE_TEST_TAG = "GIANT_PROPS_LIVE_TEST"
PROP_NAME = f"{MOD_ID}_live_prop"
SUBJECT_NAME = f"{MOD_ID}_live_subject"
PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"

EXPECTED_TRIGGERS = {"approach": "Overlaps", "slap_zone": "Overlaps"}
EXPECTED_PART_COUNT = 26

#: Authored y where the run starts. The corridor is 108 m long centred on
#: y = -70, i.e. -124 .. -16, so this is inside it with 69 m of run-up left
#: to the strike point and 39 m of corridor behind for the arming trigger.
START_AUTHORED_Y = -85.0
#: Comfortably above BEHAVIOR.min_closing_mps (2.5) and inside the 30 m/s
#: band beamngpy's set_velocity is documented to handle at dt = 1.0.
APPROACH_MPS = 22.0
#: Physics steps per control.step() call. How much SIM TIME that buys is
#: deliberately not assumed: the first version of this file wrote
#: `STEPS_PER_CALL / 60` and produced a trace whose samples were 18 m apart
#: at 25 m/s, i.e. three times the labelled interval. The engine's step
#: accounting is its own business, so the test measures the interval from
#: the subject's own motion during the approach and reports it.
STEPS_PER_CALL = 15


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the High Five live gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the High Five live gate requires a sentinel-isolated profile")
    return home, user, resolved_binary


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
    """Position, velocity and facing, straight off the vehicle object."""

    return _lua_json(
        bng,
        f"local subject = scenetree.findObject({SUBJECT_NAME!r}); "
        "if not subject then return jsonEncode({ok = false}) end; "
        "local position = subject:getPosition(); "
        "local velocity = subject:getVelocity(); "
        "local facing = subject:getDirectionVector(); "
        "return jsonEncode({ok = true, x = position.x, y = position.y, z = position.z, "
        "vx = velocity.x, vy = velocity.y, vz = velocity.z, speed = velocity:length(), "
        "fx = facing.x, fy = facing.y, fz = facing.z})",
    )


def _authored(
    origin: tuple[float, float, float], probe: dict[str, Any]
) -> tuple[float, float, float]:
    """World probe -> authored prop frame (identity spawn is a 180 deg Z flip)."""

    return (
        -(float(probe["x"]) - origin[0]),
        -(float(probe["y"]) - origin[1]),
        float(probe["z"]) - origin[2],
    )


def _world_point(
    origin: tuple[float, float, float], authored_x: float, authored_y: float, authored_z: float
) -> tuple[float, float, float]:
    return (origin[0] - authored_x, origin[1] - authored_y, origin[2] + authored_z)


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
def test_high_five_leads_a_moving_car_and_slaps_it(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    dist_root = PACK_ROOT / MOD_KEY / "dist"
    archive = dist_root / ZIP_BASENAME
    lock = json.loads((dist_root / f"{MOD_ID}.lock.json").read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"], (
        "the packaged zip does not match its lock; rebuild before testing it"
    )

    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(
        user, Path("mods") / f"high_five_live_{suffix}.zip"
    )
    scenario_name = f"high_five_live_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    log_path = user / "beamng.log"
    log_start = f"high_five_live_start_{suffix}"
    trace: list[dict[str, Any]] = []
    facing_note = "unset"

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

            timer = threading.Timer(420.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid",
                scenario_name,
                description="Disposable High Five live approach fixture",
            )
            subject = Vehicle(SUBJECT_NAME, "etk800", license="SLAPPED")
            scenario.add_vehicle(
                subject, pos=(120.0, 120.0, 20.0), rot_quat=(0, 0, 0, 1), cling=False
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

            prop = Vehicle(PROP_NAME, MOD_ID, license="HIGH5")
            spawned = bng.vehicles.spawn(prop, (0.0, 0.0, surface_z), (0, 0, 0, 1), False, True)
            assert spawned is True

            state: dict[str, Any] = {}
            for _ in range(24):
                bng.control.step(STEPS_PER_CALL, wait=True)
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
            origin_raw = state["origin"]
            origin = (float(origin_raw[0]), float(origin_raw[1]), float(origin_raw[2]))

            # --- put the car up the corridor, pointed at the machine -------
            #
            # Authored +y is world -y (identity spawn is a 180 degree Z
            # flip), so "toward the hand" is world -y. Which quaternion faces
            # a vehicle that way is an engine convention rather than a
            # property of this mod, so it is MEASURED: place with identity,
            # read the direction vector, and flip 180 degrees about Z if it
            # points the wrong way. The chosen orientation is asserted below
            # and reported, so a convention change shows up as a fact rather
            # than a mystery failure.
            start_world = _world_point(origin, 0.0, START_AUTHORED_Y, 0.8)
            subject.teleport(pos=start_world, rot_quat=(0, 0, 0, 1), reset=True)
            bng.control.step(STEPS_PER_CALL, wait=True)
            probe = _subject_probe(bng)
            assert probe.get("ok") is True, probe
            if float(probe["fy"]) > 0.0:
                subject.teleport(pos=start_world, rot_quat=(0, 0, 1, 0), reset=True)
                bng.control.step(STEPS_PER_CALL, wait=True)
                probe = _subject_probe(bng)
                facing_note = "yaw180"
            else:
                facing_note = "identity"
            assert float(probe["fy"]) < -0.7, {
                "detail": "subject is not pointed down the corridor at the hand",
                "facing": [probe["fx"], probe["fy"], probe["fz"]],
                "tried": facing_note,
            }

            subject.control(parkingbrake=0.0, brake=0.0, throttle=1.0)
            subject.set_velocity(APPROACH_MPS, 1.0)
            bng.control.step(STEPS_PER_CALL, wait=True)

            # --- run it in and watch --------------------------------------
            approach_speed = 0.0
            approach_samples: list[tuple[float, float]] = []
            peak_speed = 0.0
            peak_z = float(probe["z"])
            baseline_z = float(probe["z"])
            slapped_at: tuple[float, float, float] | None = None
            arrival_offset = None
            ground_z = None
            for index in range(60):
                # Fine steps through the strike window so the arrival
                # offset can be back-solved from the car's climb; coarse
                # everywhere else. The offset is the one number the
                # headless stub structurally cannot measure -- its 60 Hz
                # loop has none of the live cadence that made the palm
                # land 2.9 m late before release_bias_seconds (a reviewer
                # back-solved it from the frames3 track, 2026-08-26).
                near_strike = trace and -30.0 < trace[-1]["authored_y"] < 12.0
                bng.control.step(3 if near_strike else STEPS_PER_CALL, wait=True)
                sample = _subject_probe(bng)
                if not sample.get("ok"):
                    continue
                rel = _authored(origin, sample)
                speed = float(sample["speed"])
                trace.append(
                    {
                        "step": index,
                        "authored_y": round(rel[1], 2),
                        "authored_x": round(rel[0], 2),
                        "z": round(rel[2], 2),
                        "speed": round(speed, 2),
                    }
                )
                peak_z = max(peak_z, float(sample["z"]))
                if ground_z is None:
                    ground_z = float(sample["z"])
                if (arrival_offset is None
                        and float(sample["z"]) > ground_z + 0.40
                        and rel[1] > -20.0):
                    # Back-solve the contact point from the climb, gravity
                    # included: z = vz t - 4.9 t^2, take the small root.
                    vz = max(speed * math.sin(math.radians(14.0)), 1.0)
                    climb = float(sample["z"]) - ground_z
                    disc = vz * vz - 4.0 * 4.9 * climb
                    climb_t = (
                        (vz - math.sqrt(disc)) / 9.8 if disc > 0 else climb / vz
                    )
                    arrival_offset = rel[1] - climb_t * speed * math.cos(
                        math.radians(14.0))
                # Approach speed is what it was doing while still short of
                # the strike zone; peak is whatever the slap did to it.
                if rel[1] < -12.0:
                    approach_speed = max(approach_speed, speed)
                    approach_samples.append((rel[1], speed))
                else:
                    peak_speed = max(peak_speed, speed)
                    if slapped_at is None and speed > approach_speed + 6.0:
                        slapped_at = rel
                if rel[1] > 40.0 or abs(rel[0]) > 60.0:
                    break

            assert approach_speed > 12.0, {
                "detail": "the car never got up the corridor under power; "
                "nothing about the lead can be concluded from this run",
                "approach_speed": approach_speed,
                "trace": trace[:20],
            }

            # --- PHASE 2: the painted pad, which is a different trigger ---
            #
            # Found in play, and invisible to phase 1 by construction. The
            # corridor runs authored y = -124 .. -16 and the pad is
            # -4.3 .. +4.3, so a car put straight onto the pad has never
            # been inside the only zone that used to arm anything. Phase 1
            # drives the MECHANISM; this drives the AFFORDANCE -- the hand
            # stencilled on the road that says "drive here".
            #
            # It also exercises re-arming: the machine has to finish its
            # follow-through, return and cooldown from the first slap
            # before this can possibly fire.
            for _ in range(12):
                bng.control.step(STEPS_PER_CALL, wait=True)
            pad_world = _world_point(origin, 0.0, 0.0, 0.8)
            subject.teleport(pos=pad_world, rot_quat=(0, 0, 0, 1), reset=True)
            subject.control(parkingbrake=1.0, throttle=0.0, brake=0.0)
            pad_baseline = _subject_probe(bng)
            pad_peak_speed = 0.0
            for _ in range(12):
                bng.control.step(STEPS_PER_CALL, wait=True)
                sample = _subject_probe(bng)
                if sample.get("ok"):
                    pad_peak_speed = max(pad_peak_speed, float(sample["speed"]))
            pad_start_authored = _authored(origin, pad_baseline)
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
    by_event = {str(record["event"]): record for record in records}

    # What one control.step(STEPS_PER_CALL) actually bought, measured off
    # the car rather than assumed from the requested step count.
    seconds_per_call = None
    if len(approach_samples) >= 2:
        (y0, s0), (y1, s1) = approach_samples[0], approach_samples[-1]
        mean_speed = (s0 + s1) / 2.0
        if mean_speed > 1.0:
            seconds_per_call = abs(y1 - y0) / mean_speed / (len(approach_samples) - 1)

    summary = {
        "arrival_offset_m": (
            round(arrival_offset, 2) if arrival_offset is not None else None
        ),
        "pad_start_authored": [round(c, 2) for c in pad_start_authored],
        "pad_peak_speed_mps": round(pad_peak_speed, 2),
        "seconds_per_step_call": (round(seconds_per_call, 4) if seconds_per_call else None),
        "mod": MOD_ID,
        "facing": facing_note,
        "approach_speed_mps": round(approach_speed, 2),
        "peak_speed_mps": round(peak_speed, 2),
        "height_gain_m": round(peak_z - baseline_z, 2),
        "slapped_at_authored": slapped_at,
        "events": events,
        "log_issues": issues,
        "trace": trace,
    }

    for required in (
        "prop_registered",
        "zone_enter",
        "high_five_alerted",
        "high_five_winding",
        "high_five_swinging",
    ):
        assert required in events, {"missing": required, **summary}

    # THE CLAIM. A reactive machine gets all of the above against a moving
    # car and then misses it, because a 0.85 s wind-up is 19 m at this
    # speed. Connecting is the whole difference.
    assert "high_five_slapped" in events, {
        "detail": "the hand ran its whole sequence and did not connect — "
        "it is reacting, not leading",
        "whiffed": events.count("high_five_whiffed"),
        **summary,
    }
    assert "subject_launched" in events, {"detail": "no launch recorded", **summary}
    assert events.index("high_five_winding") < events.index("high_five_swinging")
    assert events.index("high_five_swinging") <= events.index("high_five_slapped")

    # THE PALM MUST MEET THE CAR, not its wake. Measured across 22-55 m/s
    # with the bias in place: -0.97 to -2.63 m (early, the car driving
    # into the palm), against +2.9 m late and diverging without it.
    assert arrival_offset is not None, {
        "detail": "the strike was never localized; the offset gate did not "
        "engage",
        **summary,
    }
    assert abs(arrival_offset) < 3.0, {
        "detail": "the palm arrived off the car: the release timing has "
        "drifted (see release_bias_seconds)",
        **summary,
    }

    # ...and the engine has to agree with the telemetry. The runtime saying
    # it launched something is not evidence that anything moved.
    assert peak_speed > approach_speed + 6.0, {
        "detail": "the runtime logged a launch the physics did not produce",
        **summary,
    }
    # THE LAUNCH LEAVES ALONG THE PALM NORMAL. This is the console's whole
    # premise — WRIST TILT is a ballistic control, not a cosmetic one — and
    # it has never been checkable outside the arithmetic that produces it.
    # The engine now says so: elevation of the launch velocity against the
    # tilt the runtime reported using.
    launch = by_event.get("subject_launched") or {}
    swing = by_event.get("high_five_swinging") or {}
    horizontal = math.hypot(
        float(launch.get("velocity_x", 0.0)), float(launch.get("velocity_y", 0.0))
    )
    elevation = math.degrees(math.atan2(float(launch.get("velocity_z", 0.0)), horizontal))
    tilt_deg = float(swing.get("tilt_deg", -1.0))
    summary["launch_elevation_deg"] = round(elevation, 2)
    summary["tilt_deg"] = tilt_deg
    assert abs(elevation - tilt_deg) < 1.0, {
        "detail": "the launch did not leave along the palm normal",
        **summary,
    }

    # ...and the speed the runtime rolled has to be the speed it announced,
    # and the speed the car actually reached.
    slapped = by_event.get("high_five_slapped") or {}
    logged_speed = float(slapped.get("slap_speed_mps", 0.0))
    launch_speed = math.hypot(horizontal, float(launch.get("velocity_z", 0.0)))
    summary["logged_slap_mps"] = round(logged_speed, 2)
    assert abs(launch_speed - logged_speed) < 0.5, {
        "detail": "the launch vector does not match the announced slap speed",
        **summary,
    }
    # Not an identity any more: with the tumble injected, a forward-rolling
    # car can plant its nose within the first second and scrub hard (one
    # run measured 27.4 against a logged 40.1 -- and still flew, climbed,
    # and scored). What this actually guards is a NO-OP launch: the
    # runtime logging a speed the physics never saw at all.
    assert peak_speed > logged_speed * 0.6, {
        "detail": "the car never reached even a scrubbed fraction of the "
        "speed the runtime says it left at -- the launch is a no-op",
        **summary,
    }

    # THE PAD. A car placed on the painted hand, having never been in the
    # corridor, has to be swung at -- and swung at AT ONCE, because it is
    # already standing on the contact point.
    assert "high_five_pad_swing" in events, {
        "detail": "a car parked on the painted pad was never swung at; the "
        "thing the player can see and the thing that arms the machine are "
        "still different objects",
        **summary,
    }
    assert events.count("high_five_slapped") >= 2, {
        "detail": "the pad swing did not connect, or the machine never "
        "re-armed after the corridor slap",
        **summary,
    }
    assert pad_peak_speed > 8.0, {
        "detail": "the runtime logged a pad slap the physics did not produce",
        **summary,
    }
    assert abs(pad_start_authored[1]) < 6.0, {
        "detail": "the pad phase did not start on the pad",
        **summary,
    }

    assert not issues, {"detail": "runtime logged errors", **summary}
    print(json.dumps(summary, sort_keys=True, default=str))
