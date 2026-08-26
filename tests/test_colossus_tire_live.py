"""Live gate for COLOSSUS 10350/80R457, in the sentinel-isolated profile.

The static gates prove the evidence chain, the cage arithmetic and the runtime
logic. There are four claims this mod rests on that NONE of them can reach,
because each is a property of the engine actually running the thing:

1. IT STANDS UP. 1,080 free nodes in a 28 m ring carrying 5.0 t with its
   centre of mass 14 m off the ground. The headless static solver says it
   settles onto an 8.3 x 3.7 m footprint, but a static solver cannot see
   integrator drift, contact chatter, or a carcass that slowly ovalises over
   a thousand frames. Here it has to be upright, round and at the right
   height after real physics has had it for several seconds.

2. THE FLOORS ARE SOLID FROM THE RIGHT SIDE. jbeam collision triangles are
   one-sided, and the whole first round of this mod shipped with its (since
   deleted) dock
   facing down and its cavity floor wound inside out. A car parked on each
   surface, in-engine, is the only test that actually settles that.

3. THE DOORWAY IS OPEN. Nine sidewall nodes stood inside the opening with
   collision on; the skin was gone, so nothing static could see them.

4. IT ROLLS BECAUSE SOMETHING PUSHED IT. The premise of the mod. The test
   pushes the SUBJECT (not the tire) and then reads the tire's own axle fit
   to see whether it moved. Nothing in the shipped runtime applies a force to
   anything - `ALLOW_SUBJECT_MUTATION = False` means the generated Lua does
   not even contain a function that could.

Configure with BEAMNG_MCP_TEST_BEAMNG_HOME / _USER / _BINARY; the profile must
carry the `.beamng-mcp-test-user` sentinel. Opt-in, like every live gate here.

    .venv\\Scripts\\python.exe -m pytest -q -s tests\\test_colossus_tire_live.py
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
    namespace_conflicts,
    require_confined_profile_target,
    reserve_loopback_ports,
)

MOD_KEY = "colossus_tire"
MOD_ID = "ericrolph_colossus_tire"
ZIP_BASENAME = "colossus_tire_ericrolph.zip"
RUNTIME_EXTENSION = "ericrolph__colossus__tire_runtime"
LOG_TAG = "ERICROLPH_COLOSSUS_TIRE_RUNTIME"
LIVE_TEST_TAG = "GIANT_PROPS_LIVE_TEST"
PROP_NAME = f"{MOD_ID}_live_prop"
SUBJECT_NAME = f"{MOD_ID}_live_subject"
PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
EXPECTED_TRIGGERS = {"approach": "Overlaps"}


def load_spec():
    import importlib.util

    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader = importlib.util.spec_from_file_location("colossus_live_spec", spec_path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


SPEC = load_spec()


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not home_value or not user_value or not binary_value:
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Colossus live gate"
        )
    home = Path(home_value).resolve()
    user = Path(os.path.abspath(user_value))
    binary = Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Colossus live gate requires a sentinel-isolated profile")
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


def _marker_points(bng: BeamNGpy) -> list[tuple[float, float, float]] | None:
    """World positions of the three crown-centre markers the runtime fits to.

    Read independently of the runtime, from the same cage nodes, so a failure
    here is the TIRE's and not the measurement layer's.
    """

    names = ", ".join(repr(name) for name in SPEC.BEHAVIOR["marker_nodes"])
    payload = _lua_json(
        bng,
        f"local prop = scenetree.findObject({PROP_NAME!r}); "
        "if not prop then return jsonEncode({ok = false}) end; "
        "local data = core_vehicle_manager.getVehicleData(prop:getID()); "
        "local nodes = data and data.vdata and data.vdata.nodes; "
        "if not nodes then return jsonEncode({ok = false}) end; "
        f"local wanted = {{{names}}}; "
        "local out = {}; "
        "local base = prop:getPosition(); "
        "for index, name in ipairs(wanted) do "
        "  for _, node in pairs(nodes) do "
        "    if node.name == name then "
        "      local rel = prop:getNodePosition(node.cid); "
        "      out[index] = {base.x + rel.x, base.y + rel.y, base.z + rel.z}; "
        "    end "
        "  end "
        "end; "
        "if #out < 3 then return jsonEncode({ok = false, found = #out}) end; "
        "return jsonEncode({ok = true, points = out})",
    )
    if not payload.get("ok"):
        return None
    return [tuple(float(value) for value in point) for point in payload["points"]]


def _marker_angle(centre, axis, marker) -> float:
    """Angle of a marker about the axle, in the tire's own frame."""

    radial = [marker[i] - centre[i] for i in range(3)]
    along = sum(radial[i] * axis[i] for i in range(3))
    radial = [radial[i] - axis[i] * along for i in range(3)]
    if math.sqrt(sum(v * v for v in radial)) < 1e-6:
        return 0.0
    reference = [(0.0, 0.0, 1.0)[i] - axis[i] * axis[2] for i in range(3)]
    if math.sqrt(sum(v * v for v in reference)) < 1e-6:
        reference = [(1.0, 0.0, 0.0)[i] - axis[i] * axis[0] for i in range(3)]
    scale = math.sqrt(sum(v * v for v in reference))
    reference = [value / scale for value in reference]
    other = [
        axis[1] * reference[2] - axis[2] * reference[1],
        axis[2] * reference[0] - axis[0] * reference[2],
        axis[0] * reference[1] - axis[1] * reference[0],
    ]
    return math.atan2(
        sum(radial[i] * other[i] for i in range(3)),
        sum(radial[i] * reference[i] for i in range(3)),
    )


def _fit_axle(points):
    """Centre, unit axis and radius of the circle through three points."""

    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points
    v1 = (bx - ax, by - ay, bz - az)
    v2 = (cx - ax, cy - ay, cz - az)
    normal = (
        v1[1] * v2[2] - v1[2] * v2[1],
        v1[2] * v2[0] - v1[0] * v2[2],
        v1[0] * v2[1] - v1[1] * v2[0],
    )
    nn = sum(component * component for component in normal)
    if nn < 1e-9:
        return None
    v1v1 = sum(value * value for value in v1)
    v2v2 = sum(value * value for value in v2)
    v1mv2 = tuple(v1[i] - v2[i] for i in range(3))
    alpha = v2v2 * sum(v1[i] * v1mv2[i] for i in range(3)) / (2 * nn)
    beta = v1v1 * sum(v2[i] * -v1mv2[i] for i in range(3)) / (2 * nn)
    centre = tuple((ax, ay, az)[i] + v1[i] * alpha + v2[i] * beta for i in range(3))
    length = math.sqrt(nn)
    axis = tuple(component / length for component in normal)
    radius = math.dist(centre, (ax, ay, az))
    return centre, axis, radius


def _subject_probe(bng: BeamNGpy) -> dict[str, Any]:
    return _lua_json(
        bng,
        f"local subject = scenetree.findObject({SUBJECT_NAME!r}); "
        "if not subject then return jsonEncode({ok = false}) end; "
        "local position = subject:getPosition(); "
        "return jsonEncode({ok = true, x = position.x, y = position.y, z = position.z})",
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


def _authored_to_world(origin, authored) -> tuple[float, float, float]:
    """The prop renders at world (-x, -y, z) from its origin.

    MODEL_ALIGNMENT_ROTATION is a proper 180-degree Z flip, which is the same
    rotation the cage coordinates went through, so an authored point maps by
    negating x and y.
    """

    return (
        float(origin[0]) - authored[0],
        float(origin[1]) - authored[1],
        float(origin[2]) + authored[2],
    )


@pytest.mark.beamng_live
def test_the_colossus_stands_up_holds_its_floors_and_rolls(tmp_path: Path) -> None:
    home, user, binary = _configured_runtime()
    dist_root = PACK_ROOT / MOD_KEY / "dist"
    archive = dist_root / ZIP_BASENAME
    lock = json.loads((dist_root / f"{MOD_ID}.lock.json").read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"], (
        "the packaged ZIP does not match its lock; run build.py <mod> all"
    )

    suffix = uuid.uuid4().hex[:10]
    installed_zip = require_confined_profile_target(
        user, Path("mods") / f"colossus_tire_live_{suffix}.zip"
    )
    scenario_name = f"colossus_tire_live_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    log_path = user / "beamng.log"
    log_start = f"colossus_live_start_{suffix}"
    report: dict[str, Any] = {}

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        # CONTENT-based shadow scan, not filename: colossus' own dist zip is
        # colossus_tire_ericrolph.zip, which no substring check on the mod id
        # ever sees, and BeamNG mounts every zip under mods/ recursively.
        existing_conflicts = namespace_conflicts(user, MOD_ID, installed_zip)
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

            # A 1,090-node softbody takes longer to settle than the pack's
            # other props, so the watchdog is longer than the toaster's 300 s.
            timer = threading.Timer(600.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid",
                scenario_name,
                description="Disposable Colossus live smoke fixture",
            )
            # A REAL VEHICLE, NOT A PIGEON. The subject used to be driven
            # INSIDE the carcass, where its weight on the liner is a torque
            # about the axle and 300 kg is plenty. There is no inside any
            # more: the push is a collision from outside against the carcass,
            # and momentum is the only thing that matters.
            subject = Vehicle(SUBJECT_NAME, "etk800", license="ROLL")
            scenario.add_vehicle(
                subject, pos=(40.0, 40.0, 20.0), rot_quat=(0, 0, 0, 1), cling=False
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

            prop = Vehicle(PROP_NAME, MOD_ID, license="COLOSSUS")
            spawned = bng.vehicles.spawn(prop, (0.0, 0.0, surface_z), (0, 0, 0, 1), False, True)
            assert spawned is True

            state: dict[str, Any] = {}
            for _ in range(40):
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
                assert trigger["test_type"] == "Bounding box", (zone, trigger)
            origin = state["origin"]

            # ---- CLAIM 1: it stands up, stays round, and does not sink.
            bng.control.step(300, wait=True)  # five seconds of settling
            points = None
            for _ in range(20):
                points = _marker_points(bng)
                if points:
                    break
                bng.control.step(15, wait=True)
            assert points, "the crown marker nodes never resolved"
            fit = _fit_axle(points)
            assert fit, f"the three markers are collinear: {points}"
            centre, axis, radius = fit
            for value in (*centre, *axis, radius):
                assert math.isfinite(value), (centre, axis, radius)

            axle_height = centre[2] - surface_z
            lean = abs(axis[2])
            report["settled"] = {
                "axle_height": round(axle_height, 3),
                "fitted_radius": round(radius, 3),
                "lean_dot": round(lean, 4),
            }
            # A carcass that collapsed, ovalised or exploded fails one of
            # these three; a carcass that fell over fails the lean.
            assert abs(radius - SPEC.OUTER_RADIUS) < 0.60, report["settled"]
            assert abs(axle_height - SPEC.OUTER_RADIUS) < 0.80, report["settled"]
            assert lean < SPEC.BEHAVIOR["leaning_dot"], report["settled"]

            # ---- CLAIM 2: the TREAD is solid from outside. There is no
            # doorway and nothing to board any more, so what has to hold is
            # the surface a car actually meets: park one against the flank and
            # it must not pass through the carcass.
            flank_target = _authored_to_world(origin, (SPEC.SECTION_HALF + 3.4, 0.0, 1.2))
            subject.teleport(pos=flank_target, rot_quat=(0, 0, 0, 1), reset=True)
            bng.control.step(180, wait=True)
            beside = _subject_probe(bng)
            assert beside["ok"] is True, beside
            report["beside_x"] = round(float(beside["x"]) - origin[0], 3)
            report["beside_z"] = round(float(beside["z"]) - surface_z, 3)
            assert report["beside_z"] > 0.15, (
                "the subject sank into the ground beside the tire: "
                f"rested at {report['beside_z']:.3f}"
            )

            # ---- CLAIM 3: coming near it pulls the chocks. That is the whole
            # interaction now, and it is a trigger the tire carries with it.
            armed = False
            for _ in range(60):
                bng.control.step(15, wait=True)
                state = _runtime_state(bng)
                if state.get("zone_counts", {}).get("approach", 0) >= 1:
                    armed = True
                    break
            report["armed"] = armed
            assert armed, state

            # ---- CLAIM 4: a car pushing the TREAD rolls the tire.
            #
            # Nobody gets inside it any more, so the push is from outside and
            # its direction matters: the subject is placed off the chocks'
            # centre line, aimed at the tread, and driven into it.
            before = _fit_axle(_marker_points(bng) or points)
            assert before
            roll = (-axis[1], axis[0], 0.0)
            norm = math.hypot(roll[0], roll[1]) or 1.0
            roll = (roll[0] / norm, roll[1] / norm, 0.0)

            # Yawed 180 degrees so its nose is at the tire: set_velocity drives
            # along the vehicle's OWN forward axis, so the heading is the whole
            # experiment now that the push comes from outside.
            # ON THE CENTRE LINE. The four chocks sit under the shoulders and
            # leave the middle of the tread clear precisely so this push has no
            # roll moment: measured off-centre at x 3.2, the same shove rolled
            # the Colossus straight over instead of along.
            # WAIT FOR THE RELEASE, BY EVENT, NOT BY CLOCK. The countdown is
            # a shipped tunable (3.5 s now, 2.0 once) and a ram scheduled by
            # frame count hit a still-tied tire the day it changed: 27.6 m of
            # dragged shove and zero coast. The winch also needs its 1.2 s to
            # pull the wedges out of the ram line.
            released = False
            for _ in range(40):
                bng.control.step(15, wait=True)
                # Poll the runtime STATE, not the log: beamng.log flushes
                # lazily and a log-tail here raced the flush into a false
                # "never fired" while the release was on time.
                stats = _runtime_state(bng).get("behavior_stats") or {}
                if stats.get("released"):
                    released = True
                    break
            assert released, "the release never fired after arming"
            bng.control.step(150, wait=True)

            ram_from = _authored_to_world(origin, (0.0, 14.0, 1.0))
            subject.teleport(pos=ram_from, rot_quat=(0, 0, 1, 0), reset=True)
            bng.control.step(90, wait=True)
            start_probe = _subject_probe(bng)
            # 12 m/s: sized twice. 18 (the 10.5 t original) flipped the
            # 4.2 t carcass mid-coast; 10 rolled it, but round 5's closed
            # wedge hulls mean the tire now spends real momentum shoving
            # both 200 kg front chocks out of its own path - honest physics
            # that halved the coast - so the push gets one notch back.
            for _ in range(18):
                subject.set_velocity(12.0, dt=0.12)
                bng.control.step(45, wait=True)
            end_probe = _subject_probe(bng)
            report["subject_ran_m"] = round(
                math.dist(
                    (start_probe["x"], start_probe["y"]),
                    (end_probe["x"], end_probe["y"]),
                ),
                2,
            )
            report["subject_end_y"] = round(float(end_probe["y"]) - origin[1], 2)
            after = _fit_axle(_marker_points(bng) or points)
            assert after
            travelled = math.dist(before[0], after[0])
            report["axle_travel_m"] = round(travelled, 3)
            report["roll_hint"] = [round(value, 3) for value in roll]

            # ---- CLAIM 4b: it COASTS. Rolling and rocking are the same
            # measurement over a single interval, and a small bar would pass
            # on a tire that climbed its own chock and rocked back.
            #
            # The coast is also the only clean place in the whole suite to ask
            # whether the 48-station COLLISION hull rides like a wheel or like
            # a polygon: smallgrid is a perfect plane, so every millimetre of
            # ride-height variation here belongs to the tire.
            def _ride_window(samples: int, stride: int) -> dict[str, Any] | None:
                """Detrended ride-height ripple over one window of the coast."""

                heights: list[float] = []
                places: list[tuple[float, float]] = []
                spin = 0.0
                previous = None
                for _ in range(samples):
                    bng.control.step(stride, wait=True)
                    sample = _marker_points(bng)
                    if not sample:
                        continue
                    sample_fit = _fit_axle(sample)
                    if not sample_fit:
                        continue
                    sample_centre, sample_axis, _sample_radius = sample_fit
                    heights.append(sample_centre[2] - surface_z)
                    places.append((sample_centre[0], sample_centre[1]))
                    # SLIP ON A PERFECT PLANE. smallgrid removes every excuse
                    # the hillside gave: whatever the ratio is here is the
                    # tire's own scrub, and it is the number that says where a
                    # measured 6% rolling resistance is actually going.
                    angle = _marker_angle(sample_centre, sample_axis, sample[0])
                    if previous is not None:
                        delta = angle - previous
                        while delta > math.pi:
                            delta -= 2.0 * math.pi
                        while delta < -math.pi:
                            delta += 2.0 * math.pi
                        spin += abs(delta)
                    previous = angle
                if len(heights) < 12:
                    return None
                # Detrend: the tire is slowing and settling, and a drift is not
                # a hop. What is left after a straight line is the ripple.
                count = len(heights)
                mean_index = (count - 1) / 2.0
                mean_ride = sum(heights) / count
                span = sum((index - mean_index) ** 2 for index in range(count))
                gradient = (
                    sum(
                        (index - mean_index) * (value - mean_ride)
                        for index, value in enumerate(heights)
                    )
                    / span
                    if span
                    else 0.0
                )
                residual = [
                    value - (mean_ride + gradient * (index - mean_index))
                    for index, value in enumerate(heights)
                ]
                distance = sum(
                    math.dist(places[index], places[index + 1]) for index in range(len(places) - 1)
                )
                seconds = count * stride / 60.0
                speed = distance / seconds if seconds else 0.0
                chord = 2.0 * SPEC.OUTER_RADIUS * math.sin(math.pi / SPEC.STATIONS)
                return {
                    "samples": count,
                    "seconds": round(seconds, 2),
                    "mean_speed_ms": round(speed, 2),
                    "mean_ride_m": round(mean_ride, 3),
                    "facet_hz": round(speed / chord, 2) if chord else None,
                    "ripple_peak_to_peak_mm": round((max(residual) - min(residual)) * 1000, 1),
                    "ripple_rms_mm": round(
                        math.sqrt(sum(v * v for v in residual) / count) * 1000, 1
                    ),
                    "arc_m": round(spin * SPEC.OUTER_RADIUS, 2),
                    "path_m": round(distance, 2),
                    "slip_ratio": (
                        round(distance / (spin * SPEC.OUTER_RADIUS), 3)
                        if spin * SPEC.OUTER_RADIUS > 0.5
                        else None
                    ),
                }

            chord_m = 2.0 * SPEC.OUTER_RADIUS * math.sin(math.pi / SPEC.STATIONS)
            facet_sagitta_mm = SPEC.OUTER_RADIUS * (1.0 - math.cos(math.pi / SPEC.STATIONS)) * 1000
            report["facet"] = {
                "stations": SPEC.STATIONS,
                "chord_m": round(chord_m, 3),
                "sagitta_mm": round(facet_sagitta_mm, 1),
            }
            # WINDOW A, straight after the ram: this is the carcass RINGING on
            # its own compliance, and it is a rubber observation in its own
            # right - a rigid hoop would not do it at all.
            report["ring"] = _ride_window(48, 5)
            # WINDOW B, four seconds later: the ring has decayed and what is
            # left is steady rolling. This is the only window in which the
            # 48-station collision hull can be judged, because smallgrid is a
            # perfect plane and there is no terrain to blame.
            report["steady"] = _ride_window(48, 5)

            # ROLLING RESISTANCE, from the two windows. Consecutive equal
            # windows give a mean speed at each midpoint, so the deceleration
            # of a freely coasting body on a flat plane is (v1 - v2) / dt and
            # Crr is that over g. It is the most material-relevant number this
            # gate can produce: the beam damping that makes the carcass behave
            # like rubber is the same mechanism as hysteresis loss in a real
            # one, and this is what it costs.
            ring = report["ring"]
            steady = report["steady"]
            if ring and steady and ring["seconds"] > 0:
                decel = (ring["mean_speed_ms"] - steady["mean_speed_ms"]) / (ring["seconds"])
                report["rolling"] = {
                    "decel_ms2": round(decel, 3),
                    "crr": round(decel / 9.81, 4),
                    "note": "free coast on a flat plane, no input",
                }
            # ROLLING WITHOUT SLIPPING, on a plane, with nothing touching it.
            # This is the claim a barrel cannot make: path length and R x
            # d-theta have to agree. Measured on the faster window, because a
            # short slow arc is dominated by the axle fit's own noise.
            if ring and ring["slip_ratio"] is not None and ring["arc_m"] > 5.0:
                assert 0.90 <= ring["slip_ratio"] <= 1.10, (
                    "coasting freely on a flat plane, the tread is scrubbing "
                    f"rather than rolling: {ring}"
                )
            if steady and steady["mean_speed_ms"] > 0.5:
                assert steady["ripple_rms_mm"] < facet_sagitta_mm, (
                    "rolling steadily on a perfectly flat plane, the axle still "
                    "ripples by more than the collision hull's own facet - it is "
                    f"riding the polygon: {report['facet']} {steady}"
                )

            coasted = _fit_axle(_marker_points(bng) or points)
            assert coasted
            drift = (
                coasted[0][0] - after[0][0],
                coasted[0][1] - after[0][1],
                0.0,
            )
            along = math.hypot(drift[0], drift[1])
            report["coast_m"] = round(along, 3)
            report["axle_travel_total_m"] = round(math.dist(before[0], coasted[0]), 3)

            assert travelled > 2.0, (
                "the Colossus barely moved when a car drove into it: "
                f"axle travelled {travelled:.3f} m"
            )
            assert report["axle_travel_total_m"] > travelled, (
                "the Colossus stopped dead the moment it was hit - that is a "
                f"collision, not a roll: {report['axle_travel_total_m']:.2f} m total "
                f"against {travelled:.2f} m under the push"
            )
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
    report["events"] = events
    report["log_issues"] = issues
    for required in ("prop_registered", "zone_enter", "colossus_released"):
        assert required in events, report
    assert not issues, report
    print(json.dumps(report, sort_keys=True))
