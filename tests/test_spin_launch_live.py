"""Live gate for the Spin Launch Kinetic Accelerator.

Boots BeamNG.drive in the sentinel-isolated profile with the packaged mod
installed and proves the machine end to end, the way a player meets it:

- an ordinary car DRIVES up the approach ramp and through the airlock under
  its own throttle, which is the only real proof that the tunnel admits a
  vehicle and the deck is a drivable surface,
- parking on the cradle auto-arms the sequence with no button press,
- the sequence walks seal -> evacuate -> retract deck -> spin up -> hold ->
  release without wedging,
- the payload leaves at the speed the POWER ladder selects, on the elevation
  the TILT ladder selects, MEASURED off the car's own world velocity rather
  than read back out of the runtime that chose it,
- the machine repressurises, reopens and returns to idle,
- and the telemetry log carries the ordered event chain with no namespaced
  errors.

The headless gate in ``test_spin_launch_sequence.py`` proves the state
machine against stubs. This is the half that stubs cannot reach: real
collision on the retracting deck and the blast door, a real soft body under
a real velocity constraint, and a real car actually fitting through the hole.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import uuid
import zipfile
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
    purge_cached_prop_meshes,
    require_confined_profile_target,
    reserve_loopback_ports,
)

MOD_KEY = "spin_launch"
MOD_ID = "ericrolph_spin_launch"
ZIP_BASENAME = "spin_launch_ericrolph.zip"
# BeamNG doubles literal underscores before replacing the path separator.
RUNTIME_EXTENSION = "ericrolph__spin__launch_runtime"
LOG_TAG = "ERICROLPH_SPIN_LAUNCH_RUNTIME"
LIVE_TEST_TAG = "SPIN_LAUNCH_LIVE_TEST"
PROP_NAME = f"{MOD_ID}_live_prop"
SUBJECT_NAME = f"{MOD_ID}_live_subject"
PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"

EXPECTED_TRIGGERS = {
    "approach_zone": "Overlaps",
    "chamber_zone": "Overlaps",
    "cradle_zone": "Contains",
}

# Where the car is put down to begin its own drive in: on the flat apron,
# short of the airlock, in the middle of the lane, 0.20 m above the deck.
#
# The HEIGHT is read off spec.DECK_Z at the call site, never written flat.
# This used to be a literal 3.20 that only landed on the apron BECAUSE the
# prop was spawning 3 m in the air: _authored_to_world adds origin.z, and
# 3.0 + 3.20 came to world 6.20, which is the apron top. With the machine
# re-datumed the two terms swap - origin.z 0.0 plus an authored 6.20 - and
# a flat literal would have dropped the car 2.8 m inside the ramp slab.
DRIVE_START_AUTHORED_Y = -26.0
DRIVE_START_ABOVE_DECK = 0.20
# How far the measured launch may sit from the commanded shot before the
# aiming claim is not a claim any more. The payload is a soft body leaving a
# clamp, so this is deliberately loose in absolute terms and still far
# tighter than the 38-degree span of the elevation ladder.
LAUNCH_SPEED_TOLERANCE = 0.22  # fraction of commanded exit speed
LAUNCH_ELEVATION_TOLERANCE = 9.0  # degrees

# Shot two reseats the payload straight onto the cradle rather than driving it
# in again: the drive-in claim is fully proved by shot one and re-proving it
# buys nothing but wall clock. Authored (0, 0) is the cradle centre and the car
# stands on the DECK, whose top is at DECK_Z; 0.30 m is a settle drop, the same
# order as the 0.20 m the drive-in start already uses on the apron. Read off
# spec.DECK_Z at the call site for the same reason DRIVE_START_ABOVE_DECK is:
# a flat literal is a datum bug waiting to happen. The landing point is inside
# cradle_zone, which is Contains and spans authored z DECK_Z - 0.8 .. + 4.6.
CRADLE_RESEAT_ABOVE_DECK = 0.30
# How far off the cradle the payload may be found after the deck comes home
# before "returned to idle" stops meaning the floor is back. The deck drops
# DECK_DROP = 3.6 m, so 0.5 m separates "resting on the deck" from "fell into
# the sump" with 7x of margin.
DECK_RETURN_TOLERANCE = 0.5

# HOW FAST THE RIDE MAY BE STEPPED.
#
# One simulation step is 0.05 s and the prop's behaviour runs ONCE per
# bng.control.step(n) call, with dtSim = n * 0.05. Measured three ways on
# 2026-08-25: `engaging` (deck_seconds 2.4 + clamp_seconds 1.6 = 4.0 s)
# took 8 iterations of step(10); omega climbed 0.200 rad/s per iteration of
# step(10) against spin_ramp_rad_s2 = 0.40; and theta advanced 29.5 deg per
# iteration of step(2) at omega 5.157 rad/s.
#
# So step(10) ran this machine's tether field at 2 Hz - 74 degrees of arc in
# one update. applyTetherField's own docstring says its residual grows
# quadratically with frame time, and it does: on the identical ZIP, step(10)
# walked the payload 15.9 -> 24.8 -> 93.9 m and lost it, while step(2) held
# it between 15.83 and 15.91 m for the entire ride and fired.
#
# What the chord approximation and the centrifugal feed-forward both care
# about is the ARC SWEPT PER UPDATE, omega * dtSim. Cap that and the top of
# the power ladder is stepped as finely as the bottom - which it has to be,
# because shot two runs omega = 182/15.9 = 11.447 rad/s.
SIM_STEP_SECONDS = 0.05
RIDE_ARC_PER_UPDATE_RAD = 0.6


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Spin Launch live gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Spin Launch live gate requires a sentinel-isolated profile")
    return home, user, binary


def _load_spec():
    import importlib.util

    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader = importlib.util.spec_from_file_location("spin_launch_live_spec", spec_path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


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


def _press(bng: BeamNGpy, button: str) -> None:
    """Drive one console button through the same GE entry point the panel uses.

    The triggers2 click boxes forward a press to
    ``pressPanelButtonByVehicle`` via the interaction json's onDown, and a
    mouse ray is not scriptable; the static gates prove the jbeam rows and
    the action map exist, and this proves what they call.
    """

    result = _lua_json(
        bng,
        f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
        f"local prop = scenetree.findObject({PROP_NAME!r}); "
        "if not extension or not prop then return jsonEncode({ok = false}) end; "
        f"local ok = extension.pressPanelButtonByVehicle(prop:getID(), {button!r}); "
        "return jsonEncode({ok = ok and true or false})",
    )
    assert result.get("ok") is True, (button, result)


def _subject_probe(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local subject = scenetree.findObject({SUBJECT_NAME!r}); "
        "if not subject then return jsonEncode({ok = false}) end; "
        "local position = subject:getPosition(); "
        "local velocity = subject:getVelocity(); "
        "return jsonEncode({ok = true, x = position.x, y = position.y, z = position.z, "
        "vx = velocity.x, vy = velocity.y, vz = velocity.z, "
        "speed = velocity:length()})",
    )


def _ride_steps(commanded_speed: float, payload_r: float) -> int:
    """Simulation steps per poll that keep the field inside its own envelope."""

    omega = commanded_speed / payload_r
    if omega <= 0.0:
        return 10
    budget = RIDE_ARC_PER_UPDATE_RAD / (omega * SIM_STEP_SECONDS)
    return max(1, int(budget))


def _ride_digest(
    trace: list[dict[str, Any]], *, budget: int = 56, window: int = 4
) -> list[dict[str, Any]]:
    """A bounded slice of the WHOLE ride that always contains the excursion.

    THE INSTRUMENT THIS REPLACES COULD NOT SEE THE EVENT IT WAS BUILT FOR.
    ``shot_one.engage_trace`` was the first 24 samples of ``engaging``, added
    to attribute the residual in ``orbit_max_m``. Measured on a full trace
    2026-08-25: over 47 ``engaging`` samples the peak radius is 16.44 m,
    which IS the seated radius - no excursion at all - and the 17.82 m peak
    lands 110 samples in, during ``spinup``, at omega 2.52. The 24-sample cut
    also stopped before the load deck reached its endpoint (the castRayStatic
    flip lands at sample 31 of 47), so the one mechanism it was meant to rule
    in or out was off the end of it too. It came out byte-identical between a
    failing and a passing build, which is the definition of an instrument
    that is worse than none.

    So: the whole ride, decimated to a fixed budget, with three things always
    kept whatever the decimation does -

      * the PEAK radius sample and `window` samples either side of it, so the
        SHAPE of the excursion survives. That is the difference between a
        slow spring, a stale collision and a soft-body ring: they produce the
        same single number and completely different neighbourhoods.
      * the FIRST sample of every phase, so the reader can see which phase
        the peak is in without counting.
      * the first and last samples of the ride.

    Bounded because this goes in an assertion payload: 56 samples of eight
    small fields is a few kB, and a 400-sample ride is not.
    """

    if not trace:
        return []
    keep = {0, len(trace) - 1}
    peak = max(range(len(trace)), key=lambda index: trace[index]["r"])
    keep.update(range(max(0, peak - window), min(len(trace), peak + window + 1)))
    previous = None
    for index, sample in enumerate(trace):
        if sample["phase"] != previous:
            keep.add(index)
            previous = sample["phase"]
    # THE BUDGET IS SPENT ON THE STRIDE, NEVER ON THE MANDATORY SAMPLES. The
    # first cut of this took the stride unconditionally and then truncated
    # `sorted(keep)[:budget]`, which trims from the END - so on a long ride
    # it silently dropped the release phase and the last sample, i.e. it
    # reintroduced the exact failure mode it was written to remove, in the
    # other direction. The mandatory set is bounded anyway (two ends, nine
    # around the peak, one per phase), so it can never crowd the budget out.
    remaining = budget - len(keep)
    if remaining > 0:
        stride = max(1, len(trace) // remaining)
        for index in range(0, len(trace), stride):
            if len(keep) >= budget:
                break
            keep.add(index)
    return [trace[index] for index in sorted(keep)]


def test_ride_digest_keeps_the_peak_and_every_phase_edge() -> None:
    """The instrument has to be able to see the event it was built for.

    Not marked beamng_live: this is arithmetic on a list, and it is the half
    of the ride trace that a live run cannot check for itself. Built from the
    2026-08-25 measurement it exists because of - a 250-sample ride whose
    radius peaks at 17.82 m in `spinup`, 110 samples in, with the phase edges
    where that run put them.
    """

    phases = (
        [("engaging", 15.9)] * 47
        + [("spinup", 15.9)] * 120
        + [("hold", 15.9)] * 60
        + [("release", 15.9)] * 23
    )
    trace = [{"phase": phase, "r": radius, "omega": 2.5} for phase, radius in phases]
    for index, radius in ((108, 16.34), (109, 17.07), (110, 17.82), (111, 13.90), (112, 17.45)):
        trace[index]["r"] = radius
    digest = _ride_digest(trace)

    assert len(digest) <= 56, len(digest)
    # THE PEAK, and its neighbourhood: one number cannot tell a slow spring
    # from a soft-body ring, and the samples either side of it can.
    assert max(sample["r"] for sample in digest) == 17.82
    for radius in (16.34, 17.07, 17.82, 13.90, 17.45):
        assert any(sample["r"] == radius for sample in digest), radius
    # EVERY PHASE, so the reader can see which one the peak is in. This is
    # exactly what the phase-filtered slice could not do: it only ever
    # contained `engaging`, and the peak has never once been in `engaging`.
    assert {sample["phase"] for sample in digest} == {"engaging", "spinup", "hold", "release"}
    # The whole ride, not one end of it.
    assert digest[0] is trace[0] and digest[-1] is trace[-1]
    # Order preserved, so the digest reads as a ride and not as a bag. By
    # IDENTITY: most samples on a steady ride are equal dicts, so `.index`
    # would answer for the first one every time and prove nothing.
    positions = [
        next(index for index, sample in enumerate(trace) if sample is entry) for entry in digest
    ]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)
    # Degenerate inputs are not a crash in an assertion payload.
    assert _ride_digest([]) == []
    assert _ride_digest(trace[:1]) == trace[:1]


def _authored_to_world(
    origin: tuple[float, float, float], authored: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Identity spawn puts the model rotation at a 180-degree Z flip."""

    return (origin[0] - authored[0], origin[1] - authored[1], origin[2] + authored[2])


def _runtime_log_records(
    log_path: Path, start_marker: str
) -> tuple[list[dict], list[str], list[str]]:
    records: list[dict] = []
    issues: list[str] = []
    warnings: list[str] = []
    started = False
    payload = log_path.read_text(encoding="utf-8", errors="replace")
    for line in payload.splitlines():
        if start_marker in line:
            started = True
            continue
        if not started or LOG_TAG not in line:
            continue
        # live_support's own cursor treats |w| as an issue alongside |e|; this
        # local reader silently dropped warnings, so a namespaced warning could
        # not reach any human. Keep them, tagged, and let the reader decide.
        if "|E|" in line:
            issues.append(line)
        elif "|W|" in line:
            warnings.append(line)
        json_start = line.find("{")
        if json_start < 0:
            continue
        try:
            record = json.loads(line[json_start:])
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("event"), str):
            records.append(record)
    return records, issues, warnings


@pytest.mark.beamng_live
def test_spin_launch_drives_in_and_throws_the_car(tmp_path: Path) -> None:
    spec = _load_spec()
    home, user, binary = _configured_runtime()
    dist_root = PACK_ROOT / MOD_KEY / "dist"
    archive = dist_root / ZIP_BASENAME
    lock = json.loads((dist_root / f"{MOD_ID}.lock.json").read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"]
    report: dict[str, Any] = {"mod": MOD_ID}

    # Hashing the archive proves what we BUILT. It does not prove what the game
    # will LOAD: BeamNG caches compiled meshes per model path and never
    # invalidates them when the ZIP behind that path changes. Three rebuilds on
    # 2026-08-24 silently did nothing while this very assertion stayed green.
    # Purge first, then assert below that the game recompiled every mesh.
    purged = purge_cached_prop_meshes(user, MOD_ID)
    report["mesh_cache"] = {"purged_entries": len(purged)}
    mesh_cache = require_confined_profile_target(user, Path("temp") / "vehicles" / MOD_ID)
    # GEOMETRY only. Cooked textures are deliberately spared - purging them
    # buys no freshness (the engine re-cooks from the source PNG) and races the
    # material loader into refusing half-written uploads - so the directory
    # itself can legitimately survive the purge. The .cdae must not.
    assert not list(mesh_cache.glob("*.cdae")), mesh_cache
    shipped_meshes = {
        Path(name).stem
        for name in zipfile.ZipFile(archive).namelist()
        if name.casefold().endswith(".dae")
    }
    assert len(shipped_meshes) == 29, sorted(shipped_meshes)

    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(
        user, Path("mods") / f"spin_launch_live_{suffix}.zip"
    )
    scenario_name = f"spin_launch_live_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    log_path = user / "beamng.log"
    log_start = f"spin_launch_live_start_{suffix}"

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

            timer = threading.Timer(1500.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid",
                scenario_name,
                description="Disposable Spin Launch live fixture",
            )
            subject = Vehicle(SUBJECT_NAME, "etk800", license="PAYLOAD")
            scenario.add_vehicle(
                subject, pos=(-90.0, -90.0, 10.0), rot_quat=(0, 0, 0, 1), cling=False
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
            # Printed, not just asserted against. "the prop stands on the
            # terrain" is the headline claim of the whole re-datum and the
            # report should carry both numbers, not one of them.
            report["surface_z"] = surface_z

            prop = Vehicle(PROP_NAME, MOD_ID, license="KLS A-1")
            spawned = bng.vehicles.spawn(prop, (0.0, 0.0, surface_z), (0, 0, 0, 1), False, True)
            assert spawned is True

            state: dict[str, Any] = {}
            for _ in range(30):
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
            for zone in EXPECTED_TRIGGERS:
                assert state["triggers"][zone]["test_type"] == "Bounding box", zone
            assert state["part_count"] == 28, state

            # THE GEOMETRY IS THE SHIPPED GEOMETRY. Every .dae in the archive
            # this test hashed had to be compiled into a .cdae during THIS
            # session, because the cache was purged before launch. Without this
            # the gate can only say the ZIP on disk is correct - it said
            # exactly that through three rebuilds that the game ignored.
            cached = {path.stem for path in mesh_cache.glob("*.cdae")}
            assert cached == shipped_meshes, {
                "missing": sorted(shipped_meshes - cached),
                "unexpected": sorted(cached - shipped_meshes),
            }
            zip_mtime = installed_zip.stat().st_mtime
            stale = sorted(
                path.name for path in mesh_cache.glob("*.cdae") if path.stat().st_mtime < zip_mtime
            )
            assert not stale, {"detail": "served from a cache older than the ZIP", "stale": stale}
            report["mesh_cache"]["recompiled"] = len(cached)

            origin = tuple(float(value) for value in state["origin"])
            report["origin"] = list(origin)
            # HOLE 5, LIVE. lua_kit's origin IS the authored origin in world
            # space, and BeamNG rests the cage's lowest node on the terrain - so
            # origin.z above the surface means the whole machine was lifted and
            # every authored z has stopped meaning height above ground.
            # Measured 3.0 on 2026-08-24 and printed, never asserted; the ramp
            # foot, which spec.py calls "at authored ground level", was 3 m in
            # the air. This costs one line and one comparison.
            assert abs(origin[2] - surface_z) <= 0.05, {
                "detail": "the prop was lifted off the terrain it spawned on",
                "origin_z": origin[2],
                "surface_z": surface_z,
            }

            status = state["behavior_status"]
            assert status["phase"] == "idle", status
            commanded_speed = float(status["exit_speed_mps"])
            commanded_elevation = float(status["elevation_deg"])
            # Anchor the command to the LADDER, not to itself. Everything below
            # compares the car against these two numbers, so if they come out
            # of a runtime that has quietly stopped reading POWER_STEPS_MPS the
            # aiming claim degenerates into "the car moved".
            assert commanded_speed == pytest.approx(
                spec.POWER_STEPS_MPS[spec.POWER_NOM_INDEX - 1], abs=1e-6
            ), status
            assert commanded_elevation == pytest.approx(
                spec.TILT_STEPS_DEG[spec.TILT_NOM_INDEX - 1], abs=1e-6
            ), status
            report["commanded"] = {
                "speed_mps": commanded_speed,
                "elevation_deg": commanded_elevation,
            }

            # ---------------------------------------------------------------
            # 1. Drive in. This is the part no stub can fake: the airlock has
            #    to be wide and tall enough, the tunnel floor and the deck
            #    have to carry a car, and the approach zone has to open the
            #    door before the car reaches it.
            # ---------------------------------------------------------------
            start = _authored_to_world(
                origin, (0.0, DRIVE_START_AUTHORED_Y, spec.DECK_Z + DRIVE_START_ABOVE_DECK)
            )
            subject.teleport(pos=start, rot_quat=(0, 0, 0, 1), reset=True)
            bng.control.step(30, wait=True)
            subject.control(parkingbrake=0.0, brake=0.0, throttle=0.32)

            aboard = False
            drive_trace: list[dict[str, Any]] = []
            for _ in range(200):
                bng.control.step(10, wait=True)
                probe = _subject_probe(bng)
                live = _runtime_state(bng)
                counts = live.get("zone_counts") or {}
                drive_trace.append(
                    {
                        "authored_y": round(origin[1] - float(probe["y"]), 2),
                        "authored_z": round(float(probe["z"]) - origin[2], 2),
                        "z": round(float(probe["z"]), 2),
                        "speed": round(float(probe["speed"]), 2),
                        "cradle": int(counts.get("cradle_zone", 0)),
                    }
                )
                if int(counts.get("cradle_zone", 0)) >= 1:
                    aboard = True
                    break
            report["drive_in"] = {"reached_cradle": aboard, "trace": drive_trace[-6:]}
            assert aboard, {
                "detail": "the car never drove itself onto the cradle",
                "trace": drive_trace[-12:],
                "state": _runtime_state(bng),
            }

            # IT WENT THROUGH THE HOLE. Occupancy of a Contains box says a car
            # is on the cradle, not how it got there - a car dropped in, pushed
            # over the rim, or clipped through the shell satisfies it just as
            # well, and the trace that distinguishes them was already being
            # collected and thrown away.
            #
            # The band test is sampled, so it must not require a sample INSIDE
            # the 1.94 m tunnel chord: at ~9 m/s and 10 steps a sample is 1.5 m
            # apart and would be missed about a quarter of the time. Crossing
            # from beyond TUNNEL_Y_OUT to past TUNNEL_Y_IN cannot be missed.
            outside = [row for row in drive_trace if row["authored_y"] <= spec.TUNNEL_Y_OUT]
            inside = [row for row in drive_trace if row["authored_y"] >= spec.TUNNEL_Y_IN]
            assert outside and inside, {
                "detail": "the car never crossed the shell wall",
                "tunnel_y": [spec.TUNNEL_Y_OUT, spec.TUNNEL_Y_IN],
                "trace": drive_trace[-12:],
            }
            assert drive_trace.index(outside[0]) < drive_trace.index(inside[-1]), {
                "detail": "the car was inside before it was outside",
                "trace": drive_trace[-12:],
            }
            # And it stayed in the lane: the apron, the tunnel floor and the
            # deck are all at DECK_Z, and the portal's clear height is
            # TUNNEL_CLEAR_Z. Below DECK_Z - 0.5 is the sump; above
            # DECK_Z + TUNNEL_CLEAR_Z is over the top of the doorway.
            heights = [row["authored_z"] for row in drive_trace]
            assert min(heights) >= spec.DECK_Z - 0.5, {
                "detail": "the car dropped below the drivable surface",
                "min_authored_z": min(heights),
                "trace": drive_trace[-12:],
            }
            assert max(heights) <= spec.DECK_Z + spec.TUNNEL_CLEAR_Z, {
                "detail": "the car left through the roof, not the airlock",
                "max_authored_z": max(heights),
                "trace": drive_trace[-12:],
            }

            # Stop on the pad and let go of everything.
            #
            # The brake comes off the FRAME the car is stopped, and that is
            # not tidiness. A stock automatic on a fresh profile runs the
            # ARCADE gearbox, where holding the brake at a standstill IS
            # reverse - so a fixed 90-step brake hold spends its last half
            # second flooring the payload backwards. Measured live
            # 2026-08-24: 11.5 m/s back down the tunnel, out through the
            # airlock and onto the apron, 1.4 s after the machine first saw
            # the car and well inside its 3 s arm delay. Three runs died on
            # that with nothing wrong with the machine - the harness was
            # driving. Every assertion below is unchanged; this only makes
            # the stop do what the line above always claimed it did.
            subject.control(throttle=0.0, brake=1.0)
            stopped = False
            for _ in range(24):
                bng.control.step(5, wait=True)
                if float(_subject_probe(bng)["speed"]) < 0.4:
                    stopped = True
                    break
            # 24 x 5 steps is 2.00 s at 60 Hz; braking from the 9.2 m/s this
            # gate measured crossing the cradle takes about 1.0 s. Falling
            # through without stopping parks a ROLLING car, the 1.6 m/s arm
            # gate then refuses forever, and the failure surfaces 1600
            # iterations later as "the machine never reached the release" -
            # which blames the machine for the harness.
            assert stopped, {
                "detail": "the payload never came to rest on the cradle",
                "probe": _subject_probe(bng),
            }
            subject.control(throttle=0.0, brake=0.0, parkingbrake=1.0)
            bng.control.step(20, wait=True)

            # ---------------------------------------------------------------
            # 2. Auto-detect and the sequence. No button is pressed here.
            # ---------------------------------------------------------------
            phases: list[str] = []
            launched_probe: dict[str, Any] | None = None
            best_speed = 0.0
            # THE RADIUS, ON THE SHOT THAT MATTERS TOO.
            #
            # The tether circle lies in the authored y-z plane about the hub,
            # and an identity spawn is a 180-degree Z flip, so it is still the
            # world y-z plane about the same point. The payload is supposed to
            # ride PAYLOAD_R = 15.9 m from it; past CHAMBER_R = 20.4 m
            # insideChamber stops counting it, the field lets go, and every
            # downstream symptom is the same useless sentence - the machine
            # "never reached the release". Shot two measured this from the
            # start; shot one did not, and shot one is the one that failed.
            hub_y_one = origin[1]
            hub_z_one = origin[2] + spec.HUB_Z
            orbit_one = 0.0
            spin_trace: list[dict[str, Any]] = []
            ride_steps = _ride_steps(commanded_speed, spec.PAYLOAD_R)
            report["ride_steps"] = {"shot_one": ride_steps}
            for _ in range(8000):
                bng.control.step(ride_steps, wait=True)
                live = _runtime_state(bng)
                status_live = live.get("behavior_status") or {}
                current = status_live.get("phase")
                if current and (not phases or phases[-1] != current):
                    phases.append(str(current))
                if current in ("engaging", "spinup", "hold", "release"):
                    probe = _subject_probe(bng)
                    if probe.get("ok"):
                        radius = math.hypot(
                            float(probe["y"]) - hub_y_one, float(probe["z"]) - hub_z_one
                        )
                        orbit_one = max(orbit_one, radius)
                        spin_trace.append(
                            {
                                "phase": str(current),
                                "r": round(radius, 2),
                                "x_off": round(float(probe["x"]) - origin[0], 2),
                                "omega": round(float(status_live.get("omega", 0.0)), 3),
                                "theta": round(float(status_live.get("theta_deg", 0.0)), 1),
                                "aboard": int(status_live.get("aboard", 0)),
                                "lost": round(float(status_live.get("lost_clock", 0.0)), 2),
                                "v": round(float(probe["speed"]), 1),
                            }
                        )
                if current == "recover":
                    # Sample the free flight for a few ticks and keep the
                    # fastest reading: the launch replaces the cluster
                    # velocity in one frame, and the soft body settles around
                    # it over the next few.
                    for _ in range(8):
                        bng.control.step(2, wait=True)
                        probe = _subject_probe(bng)
                        if probe.get("ok") and float(probe["speed"]) > best_speed:
                            best_speed = float(probe["speed"])
                            launched_probe = probe
                    break
            report["phases"] = phases
            report["shot_one"] = {
                "orbit_max_m": round(orbit_one, 2),
                "payload_r": spec.PAYLOAD_R,
                "bore_r": spec.CHAMBER_R,
                "spin_trace": spin_trace[-40:],
                # `spin_trace[-40:]` is forty samples of `release`, which is
                # where the ride ENDS and not where orbit_max_m is set. The
                # digest is the whole ride, peak-centred - see _ride_digest
                # for why the phase-filtered slice it replaces could not see
                # its own event.
                "ride_trace": _ride_digest(spin_trace),
                "ride_samples": len(spin_trace),
                "orbit_peak_phase": (
                    max(spin_trace, key=lambda sample: sample["r"])["phase"] if spin_trace else None
                ),
            }
            # Name the cause before the symptom. A payload that drifted out of
            # the bore takes the field with it, and everything after that reads
            # as "the machine never reached the release".
            assert orbit_one <= spec.CHAMBER_R, {
                "detail": "the field lost the payload out of the bore",
                "orbit_max_m": round(orbit_one, 2),
                "bore_r": spec.CHAMBER_R,
                "payload_r": spec.PAYLOAD_R,
                "phases": phases,
                "spin_trace": spin_trace[-24:],
            }
            assert launched_probe is not None, {
                "detail": "the machine never reached the release",
                "phases": phases,
                "orbit_max_m": round(orbit_one, 2),
                "spin_trace": spin_trace[-24:],
                "state": _runtime_state(bng),
            }
            for required in ("sealing", "evacuating", "engaging", "spinup", "hold", "release"):
                assert required in phases, {"phases": phases, "spin_trace": spin_trace[-24:]}

            # ---------------------------------------------------------------
            # 3. THE AIMING CLAIM, measured off the car and not off the
            #    runtime that aimed it.
            # ---------------------------------------------------------------
            vx = float(launched_probe["vx"])
            vy = float(launched_probe["vy"])
            vz = float(launched_probe["vz"])
            speed = math.sqrt(vx * vx + vy * vy + vz * vz)
            horizontal = math.hypot(vx, vy)
            elevation = math.degrees(math.atan2(vz, horizontal)) if horizontal else 90.0
            report["measured"] = {
                "speed_mps": round(speed, 2),
                "elevation_deg": round(elevation, 2),
            }
            # TWO-SIDED. A one-sided floor is passed by a runaway field just as
            # happily as by a correct one - field_speed_cap_mps is 240, nearly
            # three times the commanded 82 - and "at least 64 m/s" is not the
            # claim this test's name makes.
            assert abs(speed - commanded_speed) <= (LAUNCH_SPEED_TOLERANCE * commanded_speed), (
                report
            )
            assert abs(elevation - commanded_elevation) <= LAUNCH_ELEVATION_TOLERANCE, report

            # ---------------------------------------------------------------
            # 4. Reset: the machine has to come all the way home by itself.
            # ---------------------------------------------------------------
            idled = False
            idle_state: dict[str, Any] = {}
            for _ in range(600):
                bng.control.step(20, wait=True)
                idle_state = _runtime_state(bng)
                if (idle_state.get("behavior_status") or {}).get("phase") == "idle":
                    idled = True
                    break
            assert idled, {"detail": "never returned to idle", "state": idle_state}
            reset_status = idle_state["behavior_status"]
            assert float(reset_status["door_close"]) == pytest.approx(0.0, abs=1e-6)
            assert float(reset_status["deck_drop"]) == pytest.approx(0.0, abs=1e-6)
            assert float(reset_status["vac"]) == pytest.approx(1.0, abs=1e-6)
            assert float(reset_status["theta_deg"]) == pytest.approx(spec.LOAD_THETA_DEG, abs=0.5)

            # ---------------------------------------------------------------
            # 5. The console actually moves the machine.
            # ---------------------------------------------------------------
            _press(bng, "btn_pwr_up")
            _press(bng, "btn_tilt_down")
            bng.control.step(6, wait=True)
            panel_status = _runtime_state(bng)["behavior_status"]
            assert int(panel_status["power_index"]) == spec.POWER_NOM_INDEX + 1, panel_status
            assert int(panel_status["tilt_index"]) == spec.TILT_NOM_INDEX - 1, panel_status
            # The index moving is not the claim; the index SELECTING is. Both
            # numbers were being printed into the report and never compared.
            assert float(panel_status["exit_speed_mps"]) == pytest.approx(
                spec.POWER_STEPS_MPS[spec.POWER_NOM_INDEX], abs=1e-6
            ), panel_status
            assert float(panel_status["elevation_deg"]) == pytest.approx(
                spec.TILT_STEPS_DEG[spec.TILT_NOM_INDEX - 2], abs=1e-6
            ), panel_status
            report["panel"] = {
                "power_index": int(panel_status["power_index"]),
                "exit_speed_mps": float(panel_status["exit_speed_mps"]),
                "tilt_index": int(panel_status["tilt_index"]),
                "elevation_deg": float(panel_status["elevation_deg"]),
            }

            # ---------------------------------------------------------------
            # 6. SHOT TWO: the BOTTOM of the elevation ladder and the TOP of
            #    the power ladder, in the same session.
            #
            # Both are untested live and both are untestable anywhere else.
            # Tilt 1 (34 degrees) is a GEOMETRY question - every render, the
            # selector thumbnail, the headless default and shot one sit at 50,
            # and the stubs the lupa gate runs against have no geometry at all.
            # It is also where the warning beacon used to stand 0.115 m off the
            # bore axis, inside a barrel a car leaves down at up to 182 m/s.
            # Power 8 (182 m/s) is a SOLVER question - omega goes to 11.45
            # rad/s and the residual radius error grows with frame time; past
            # the 20.4 m bore insideChamber stops counting the payload and the
            # machine fires an empty tether.
            #
            # One shot, not two: the aiming identity is speed-independent (the
            # lupa gate proves that over the tilt ladder) and the field is
            # elevation-independent, so a single shot at both extremes is the
            # worst case for each and the failing assertion names which.
            #
            # Inside this session, not a second test function and not a
            # parametrisation: isolated_profile_lock is a hard exclusive lock,
            # so parametrised cases cannot overlap - each would serially re-pay
            # a BeamNG boot, a level load and a 4.6 MB mesh compile. Measured
            # on the lupa rig, shot two costs 69.5 s of sim from idle to idle
            # (1.0 s to re-arm, 51.0 s to the release, 17.5 s to spin down and
            # come home) against 47.9 s for shot one. The watchdog is 1500 s.
            # ---------------------------------------------------------------
            for _ in range(len(spec.POWER_STEPS_MPS) - (spec.POWER_NOM_INDEX + 1)):
                _press(bng, "btn_pwr_up")
            for _ in range(spec.TILT_NOM_INDEX - 2):
                _press(bng, "btn_tilt_down")
            bng.control.step(6, wait=True)
            armed = _runtime_state(bng)["behavior_status"]
            assert int(armed["power_index"]) == len(spec.POWER_STEPS_MPS), armed
            assert int(armed["tilt_index"]) == 1, armed
            assert float(armed["exit_speed_mps"]) == pytest.approx(
                spec.POWER_STEPS_MPS[-1], abs=1e-6
            ), armed
            assert float(armed["elevation_deg"]) == pytest.approx(
                spec.TILT_STEPS_DEG[0], abs=1e-6
            ), armed

            # Reseating the payload is also the ONLY live proof that the deck
            # came back. Step 4 asserts deck_drop == 0, but that is the runtime
            # reporting its own pose; the deck is a collision part and the
            # question is whether its bake re-ran. A car put on it either rests
            # or falls 3.6 m into the sump, and nothing else distinguishes the
            # two. The lupa gate checks collisionReloads; this checks gravity.
            reseat = _authored_to_world(origin, (0.0, 0.0, spec.DECK_Z + CRADLE_RESEAT_ABOVE_DECK))
            subject.teleport(pos=reseat, rot_quat=(0, 0, 0, 1), reset=True)
            subject.control(throttle=0.0, brake=0.0, parkingbrake=1.0)
            bng.control.step(60, wait=True)
            seated = _subject_probe(bng)
            assert seated.get("ok") is True, seated
            seated_z = float(seated["z"]) - origin[2]
            report["reseat"] = {
                "authored_z": round(seated_z, 2),
                "speed": round(float(seated["speed"]), 2),
            }
            assert seated_z >= spec.DECK_Z - DECK_RETURN_TOLERANCE, {
                "detail": "the payload fell through the returned deck",
                "authored_z": seated_z,
                "deck_z": spec.DECK_Z,
            }
            assert float(seated["speed"]) < 0.5, seated

            # The tether circle lies in the authored y-z plane about the hub,
            # and an identity spawn is a 180-degree Z flip, so it is still the
            # world y-z plane about the same point.
            hub_y = origin[1]
            hub_z = origin[2] + spec.HUB_Z
            phases_two: list[str] = []
            orbit_max = 0.0
            launched_two: dict[str, Any] | None = None
            best_two = 0.0
            ride_steps_two = _ride_steps(spec.POWER_STEPS_MPS[-1], spec.PAYLOAD_R)
            report["ride_steps"]["shot_two"] = ride_steps_two
            for _ in range(12000):
                bng.control.step(ride_steps_two, wait=True)
                live = _runtime_state(bng)
                current = (live.get("behavior_status") or {}).get("phase")
                if current and (not phases_two or phases_two[-1] != current):
                    phases_two.append(str(current))
                if current in ("spinup", "hold"):
                    probe = _subject_probe(bng)
                    if probe.get("ok"):
                        orbit_max = max(
                            orbit_max,
                            math.hypot(float(probe["y"]) - hub_y, float(probe["z"]) - hub_z),
                        )
                if current == "recover":
                    for _ in range(8):
                        bng.control.step(2, wait=True)
                        probe = _subject_probe(bng)
                        if probe.get("ok") and float(probe["speed"]) > best_two:
                            best_two = float(probe["speed"])
                            launched_two = probe
                    break
            report["shot_two"] = {
                "phases": phases_two,
                "orbit_max_m": round(orbit_max, 2),
                "payload_r": spec.PAYLOAD_R,
                "bore_r": spec.CHAMBER_R,
            }
            assert launched_two is not None, {
                "detail": "the machine never reached the release at full power",
                "phases": phases_two,
                "orbit_max_m": round(orbit_max, 2),
                "state": _runtime_state(bng),
            }
            # THE ACTUAL FAILURE MODE, MEASURED. At 182 m/s omega is 11.45
            # rad/s and the field's residual radius error grows with frame
            # time; the payload only has CHAMBER_R - PAYLOAD_R = 4.5 m of room
            # before insideChamber stops counting it, at which point the field
            # lets go and the machine throws an empty tether. Without this the
            # symptom is "never reached the release" and the cause is invisible.
            assert orbit_max <= spec.CHAMBER_R, {
                "detail": "the field lost the payload out of the bore",
                "orbit_max_m": round(orbit_max, 2),
                "bore_r": spec.CHAMBER_R,
                "payload_r": spec.PAYLOAD_R,
            }
            for required in ("sealing", "evacuating", "engaging", "spinup", "hold", "release"):
                assert required in phases_two, {"phases": phases_two}

            vx2 = float(launched_two["vx"])
            vy2 = float(launched_two["vy"])
            vz2 = float(launched_two["vz"])
            speed_two = math.sqrt(vx2 * vx2 + vy2 * vy2 + vz2 * vz2)
            horizontal_two = math.hypot(vx2, vy2)
            elevation_two = (
                math.degrees(math.atan2(vz2, horizontal_two)) if horizontal_two else 90.0
            )
            report["shot_two"]["measured"] = {
                "speed_mps": round(speed_two, 2),
                "elevation_deg": round(elevation_two, 2),
            }
            assert abs(speed_two - spec.POWER_STEPS_MPS[-1]) <= (
                LAUNCH_SPEED_TOLERANCE * spec.POWER_STEPS_MPS[-1]
            ), report
            assert abs(elevation_two - spec.TILT_STEPS_DEG[0]) <= (LAUNCH_ELEVATION_TOLERANCE), (
                report
            )
        finally:
            # ALWAYS print the report, pass or fail. A live run that dies
            # mid-sequence used to print nothing at all - every number this
            # gate collected was thrown away at exactly the moment somebody
            # needed it, and pytest's assertion repr elides long payloads.
            print("SPIN_LAUNCH_REPORT " + json.dumps(report, sort_keys=True))
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

    records, issues, log_warnings = _runtime_log_records(log_path, log_start)
    report["log_warnings"] = log_warnings
    events = [str(record["event"]) for record in records]
    for required in (
        "prop_registered",
        "sequence_armed",
        "payload_launched",
        "sequence_recover",
    ):
        assert required in events, {"events": events, "issues": issues}
    assert events.index("sequence_armed") < events.index("payload_launched")
    launches = [record for record in records if record["event"] == "payload_launched"]
    # Two shots, and the runtime emits count = fired - the number of payloads
    # it actually threw. There was one car aboard each time, so >= 1 is not the
    # claim; == 1 is. An empty tether reports 0 and a runaway zone reports more.
    assert len(launches) == 2, launches
    assert [int(record.get("count", 0)) for record in launches] == [1, 1], launches
    # The telemetry carries the shot it thinks it took. Comparing that to the
    # ladder is a third independent witness alongside the console readback and
    # the car's own velocity.
    assert float(launches[0]["speed_mps"]) == pytest.approx(
        spec.POWER_STEPS_MPS[spec.POWER_NOM_INDEX - 1], abs=1e-6
    ), launches[0]
    assert float(launches[1]["speed_mps"]) == pytest.approx(spec.POWER_STEPS_MPS[-1], abs=1e-6), (
        launches[1]
    )
    assert float(launches[1]["elevation_deg"]) == pytest.approx(spec.TILT_STEPS_DEG[0], abs=1e-6), (
        launches[1]
    )
    assert not issues, issues
    report["events"] = events
    report["telemetry_launches"] = launches
    print(json.dumps(report, sort_keys=True))
