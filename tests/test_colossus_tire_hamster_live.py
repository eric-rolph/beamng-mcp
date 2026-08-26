"""Live gate: a car driving around INSIDE the COLOSSUS makes the tire move.

The cavity is the point of this prop: the ramp, the dock and the access port
are gone, but the interior liner is still a drivable surface, and the brief is
that a car rolling around inside the tire MOVES the tire - a 28 m hamster
wheel. Nothing scripts that. The liner's collision triangles face the cavity,
the car's wheels push on them, and the reaction torque is the only thing that
turns the carcass.

This gate proves the whole chain live on ``smallgrid``:

1. THE FLOOR IS REAL. A car spawned inside the cavity lands on the liner and
   stays there - it does not clip through a one-sided triangle into the
   ground. That is a claim about winding, and only the engine can make it.

2. DRIVING INSIDE TURNS THE WHEEL. With the tie-downs cut and no external
   contact at all, the car throttles up and the tire must translate - in the
   direction the car drives, because that is which way a hamster wheel goes.

3. IT MOVES BY ROLLING. The axle's path length must agree with R * dtheta;
   an interior force that slid the carcass across the ground instead of
   rolling it would be a physics bug, not a hamster wheel.

4. THE CAR STAYS INSIDE while all of it happens - riding up the wall in the
   drive direction is expected (that is the equilibrium of the machine), but
   it must stay within the cavity.

THE DRIVER'S MASS FRACTION IS THE WHOLE GAME. A car holding station at
angle phi applies torque m*g*R_liner*sin(phi); the tire can statically
resist up to (M+m)*g*e, where e is how far the ground reaction can migrate
ahead - measured live at >= 2.0 m, because the 48-station collision hull's
SECOND facet picks up load 2.8 m out. Breakaway therefore needs
m/(M+m) > e/(R*sin(phi)) ~ 0.29: an etk800 against 4.2 t sits exactly on
that line (measured: 115 kNm applied, 0.2 m of lean, no roll), which is why
the subject here is a ROAMER - 2.4 t clears the inequality with real margin
at an honest 35-45 degree climb.

Opt in with the sentinel-isolated profile, like every live gate here::

    $env:BEAMNG_MCP_TEST_BEAMNG_HOME = '<BeamNG.drive installation>'
    $env:BEAMNG_MCP_TEST_BEAMNG_BINARY = '<...>\\Bin64\\BeamNG.drive.x64.exe'
    $env:BEAMNG_MCP_TEST_BEAMNG_USER = '<...>\\test-users\\<id>\\current'
    .venv\\Scripts\\python.exe -m pytest -q -s tests\\test_colossus_tire_hamster_live.py
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
from tests.test_colossus_tire_live import (
    MOD_ID,
    MOD_KEY,
    PACK_ROOT,
    RUNTIME_EXTENSION,
    ZIP_BASENAME,
    _fit_axle,
    load_spec,
)

SPEC = load_spec()
PROP_NAME = f"{MOD_ID}_hamster_prop"
SUBJECT_NAME = f"{MOD_ID}_hamster_car"

SETTLE_FRAMES = 420
DRIVE_SAMPLES = 120
SAMPLE_FRAMES = 15  # 120 x 15 / 60 Hz = 30 s of driving
# What "the car moved the tire" means: far enough that no settle wobble,
# release twitch or wedge shove can fake it. A quarter revolution is ~22 m,
# so 3 m is modest and still an order of magnitude over the noise.
HAMSTER_MIN_M = 3.0
SLIP_RATIO_BAND = (0.75, 1.25)


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not (home_value and user_value and binary_value):
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Colossus hamster gate"
        )
    home, user, binary = Path(home_value), Path(user_value), Path(binary_value)
    resolved = binary if binary.is_absolute() else home / binary
    if not resolved.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Colossus hamster gate requires a sentinel-isolated profile")
    return home, user, binary


def _lua_json(bng: BeamNGpy, command: str) -> dict[str, Any]:
    payload = bng.control.queue_lua_command(command, response=True)
    decoded = json.loads(payload)
    assert isinstance(decoded, dict), decoded
    return decoded


def _markers(bng: BeamNGpy) -> list[tuple[float, float, float]] | None:
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


def _car_state(bng: BeamNGpy) -> dict[str, Any] | None:
    payload = _lua_json(
        bng,
        f"local car = scenetree.findObject({SUBJECT_NAME!r}); "
        "if not car then return jsonEncode({ok = false}) end; "
        "local p = car:getPosition(); local d = car:getDirectionVector(); "
        "local v = car:getVelocity(); "
        "return jsonEncode({ok = true, x = p.x, y = p.y, z = p.z, "
        "dx = d.x, dy = d.y, dz = d.z, vx = v.x, vy = v.y, "
        "speed = math.sqrt(v.x^2 + v.y^2 + v.z^2)})",
    )
    return payload if payload.get("ok") else None


def _unwrap(previous: float, current: float) -> float:
    delta = current - previous
    while delta > math.pi:
        delta -= 2.0 * math.pi
    while delta < -math.pi:
        delta += 2.0 * math.pi
    return delta


def _marker_angle(centre, axis, marker) -> float:
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


def test_a_car_inside_the_colossus_drives_it_like_a_hamster_wheel(tmp_path: Path) -> None:
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
        user, Path("mods") / f"colossus_hamster_{suffix}.zip"
    )
    scenario_name = f"colossus_hamster_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / "smallgrid" / "scenarios" / scenario_name
    )
    report: dict[str, Any] = {}

    with ExitStack() as safety:
        safety.enter_context(isolated_profile_lock(user))
        reservation = safety.enter_context(reserve_loopback_ports(1))
        (tcom_port,) = reservation.ports
        # CONTENT-based shadow scan, not filename: colossus' own dist zip is
        # colossus_tire_ericrolph.zip, which no substring check on the mod id
        # ever sees, and BeamNG mounts every zip under mods/ recursively.
        conflicts = namespace_conflicts(user, MOD_ID, installed_zip)
        if conflicts:
            pytest.fail(f"competing {MOD_ID} archives in the isolated profile: {conflicts}")
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

            timer = threading.Timer(900.0, watchdog)
            timer.daemon = True
            timer.start()
            reservation.release()
            bng.open(launch=True, listen_ip="127.0.0.1")
            owned_process = claim_owned_beamng_process(bng)

            scenario = Scenario(
                "smallgrid", scenario_name, description="Disposable Colossus hamster fixture"
            )
            anchor = Vehicle(f"{MOD_ID}_hamster_anchor", "pigeon", license="WHEEL")
            scenario.add_vehicle(anchor, pos=(120.0, 120.0, 0.2), rot_quat=(0, 0, 0, 1), cling=True)
            scenario.make(bng)
            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)

            surface = _lua_json(
                bng,
                "local rayStart = vec3(0, 0, 60); "
                "local rayDistance = castRayStatic(rayStart, vec3(0, 0, -1), 120); "
                "return jsonEncode({surface_z = rayStart.z - rayDistance})",
            )
            surface_z = float(surface["surface_z"])

            prop = Vehicle(PROP_NAME, MOD_ID, license="HAMSTER")
            spawned = bng.vehicles.spawn(prop, (0.0, 0.0, surface_z), (0, 0, 0, 1), False, True)
            assert spawned is True

            state: dict[str, Any] = {}
            for _ in range(60):
                bng.control.step(15, wait=True)
                state = _lua_json(
                    bng,
                    f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
                    f"local prop = scenetree.findObject({PROP_NAME!r}); "
                    "if not extension then return jsonEncode({loaded = false}) end; "
                    "if not prop then return jsonEncode({loaded = true, registered = false}) end; "
                    "local s = extension.getSystemState(prop:getID()); "
                    "s.loaded = true; return jsonEncode(s)",
                )
                if state.get("registered"):
                    break
            assert state.get("registered") is True, state

            bng.control.step(SETTLE_FRAMES, wait=True)
            points = _markers(bng)
            assert points, "the crown marker nodes never resolved"
            fit = _fit_axle(points)
            assert fit, f"the three markers are collinear: {points}"
            centre, axis, _radius = fit
            axle_height = centre[2] - surface_z
            report["settled_axle_m"] = round(axle_height, 3)

            # ---- THE CAR GOES IN. Straight down onto the liner at the bottom
            # of the cavity: the floor sits CAVITY_RADIUS under the axle, and
            # the drop is a few tens of centimetres so the landing is a step
            # off a kerb, not a crash test.
            floor_z = centre[2] - SPEC.CAVITY_RADIUS
            report["cavity_floor_m"] = round(floor_z - surface_z, 3)
            # The wedge baseline is taken NOW, while the car is still
            # parked far outside the approach zone: the moment it
            # teleports into the cavity it is a vehicle in the zone, and
            # the shipped sequence - arm, countdown, cut, winch - runs
            # during the landing frames.
            # The wedge CENTROID, not one corner: the diagonal winch lands
            # both impulses at the heel, so the wedge pivots about its toe
            # and a toe-corner tracker under-reads the escape (measured
            # 0.72 m of corner motion on a wedge that had swung well clear).
            wedge_probe = (
                f"local prop = scenetree.findObject({PROP_NAME!r}); "
                "if not prop then return jsonEncode({ok = false}) end; "
                "local data = core_vehicle_manager.getVehicleData(prop:getID()); "
                "local nodes = data and data.vdata and data.vdata.nodes; "
                "if not nodes then return jsonEncode({ok = false}) end; "
                "local sx, sy, sz, count = 0, 0, 0, 0 "
                "for _, node in pairs(nodes) do "
                f"  if node.name and node.name:find('{MOD_ID}_chock_0_', 1, true) == 1 "
                "      and not node.name:find('anchor', 1, true) then "
                "    local rel = prop:getNodePosition(node.cid); "
                "    sx = sx + rel.x; sy = sy + rel.y; sz = sz + rel.z; "
                "    count = count + 1 "
                "  end "
                "end; "
                "if count == 0 then return jsonEncode({ok = false}) end; "
                "local base = prop:getPosition(); "
                "return jsonEncode({ok = true, x = base.x + sx / count, "
                "                   y = base.y + sy / count, z = base.z + sz / count})"
            )
            wedge_before = _lua_json(bng, wedge_probe)
            assert wedge_before.get("ok"), wedge_before

            # SPAWN OUTSIDE, TELEPORT IN. Spawning a vehicle inside another
            # vehicle's volume trips BeamNG's placement safety, which quietly
            # relocates the newcomer to open ground BESIDE the tire - measured
            # twice at identical coordinates before this gate believed it.
            # Teleports skip that sanitising, so the car goes in the honest
            # way: materialise on open ground, then step through the sidewall.
            subject = Vehicle(SUBJECT_NAME, "roamer", license="HAMSTER")
            spawned = bng.vehicles.spawn(subject, (60.0, 60.0, 0.2), (0, 0, 0, 1), False, True)
            assert spawned is True
            bng.control.step(60, wait=True)
            # +0.45: enough that the roamer's wheels cannot materialise
            # INSIDE the one-sided liner surface - at +0.15 they spawned
            # embedded and were clamped solid (engine in D at 2218 rpm,
            # wheelspeed 0.001) - while still small enough that the landing
            # thump stays a kerb-hop.
            moved = subject.teleport(
                (centre[0], centre[1], floor_z + 0.45), (0, 0, 0, 1), reset=True
            )
            assert moved is True
            bng.control.step(5, wait=True)
            probe = _car_state(bng)
            report["car_spawn_probe_z_m"] = round(probe["z"] - surface_z, 3) if probe else None
            assert probe and probe["z"] > surface_z + 0.3, (
                "the teleport into the cavity was rejected too - the car is "
                f"not inside the tire: {probe}"
            )
            bng.control.step(240, wait=True)

            landed = _car_state(bng)
            assert landed, "the car vanished on spawn"
            assert landed["z"] > surface_z + 0.25, (
                "the car fell THROUGH the liner floor - the interior "
                f"triangles are not holding it: {landed}"
            )
            drive_sign = -1.0 if landed["dy"] < 0 else 1.0
            report["car_landed_z_m"] = round(landed["z"] - surface_z, 3)

            # ---- RELEASE VIA THE MACHINE ITSELF. The car materialising
            # inside the cavity is also a vehicle entering the approach zone,
            # so the SHIPPED sequence runs: arm, countdown, cut - and the
            # same beat WINCHES the chocks clear along their own axes,
            # because a wedge lying against the tread props the carcass
            # through the ramp geometry even with every strap broken
            # (measured: ~115 kNm from inside, 0.09 m of lean, wedge parked).
            # The gate audits the beams and the wedge rather than trusting
            # the ceremony.
            def strap_audit(tag: str) -> str | None:
                prop.queue_lua_command(
                    "local total, broken = 0, 0 "
                    "for _, b in pairs(v.data.beams) do "
                    "  if b.breakGroup == '" + SPEC.STRAP_BREAK_GROUP + "' then "
                    "    total = total + 1 "
                    "    if obj:beamIsBroken(b.cid) then broken = broken + 1 end "
                    "  end "
                    "end "
                    "obj:queueGameEngineLua("
                    "'COLOSSUS_STRAPS_" + tag + " = \"' .. total .. '/' .. broken .. '\"')"
                )
                for _ in range(10):
                    bng.control.step(15, wait=True)
                    payload = _lua_json(
                        bng,
                        "return jsonEncode({value = COLOSSUS_STRAPS_" + tag + "})",
                    )
                    if payload.get("value"):
                        return str(payload["value"])
                return None

            released = None
            for attempt in range(12):
                released = strap_audit(f"A{attempt}")
                if released:
                    total_s, broken_s = released.split("/")
                    if int(total_s) > 0 and total_s == broken_s:
                        break
            report["straps_total_broken"] = released
            assert released, "the strap audit never came back"
            total_s, broken_s = released.split("/")
            assert int(total_s) > 0 and total_s == broken_s, (
                "the shipped release sequence never freed the tire: strap "
                f"audit reads {released} (total/broken)"
            )

            # The winch receipt, twice over: the shipped command echoes how
            # many pairs it resolved and pulled, and the front wedge must be
            # metres away, not merely unstrapped.
            winched = _lua_json(bng, "return jsonEncode({value = COLOSSUS_WINCHED})")
            report["winch_pairs_pulled"] = winched.get("value")
            assert winched.get("value") == 8, (
                f"the shipped winch resolved {winched.get('value')} of 8 chock pairs"
            )
            bng.control.step(180, wait=True)
            wedge_mid = _lua_json(bng, wedge_probe)
            assert wedge_mid.get("ok"), wedge_mid
            report["wedge_winched_m"] = round(
                math.dist(
                    (wedge_before["x"], wedge_before["y"], wedge_before["z"]),
                    (wedge_mid["x"], wedge_mid["y"], wedge_mid["z"]),
                ),
                2,
            )
            assert report["wedge_winched_m"] > 1.0, (
                f"the winch did not pull the chocks clear: {report['wedge_winched_m']} m"
            )

            # ---- DRIVE, STATION-KEPT. A hamster wheel is a station-keeping
            # problem: the interior surface at the bottom moves at only
            # (1 - r_liner/R) ~ 7% of the axle speed, so the car has to HOLD a
            # climb angle and let its weight component torque the ring.
            # Flat throttle wall-of-deaths around the inside (measured: 7.4
            # m/s, 71 degrees up, tire still); a speed governor turns the car
            # into a PENDULUM in the bowl, alternating torque that averages
            # to nothing (measured: -9.3 m swings, tire wiggling 0.17 m).
            # What works is the thing a human does: throttle by POSITION on
            # the wall, and brake the backswing so the pendulum never builds.
            # First-class beamngpy APIs, not raw controller Lua: the roamer
            # sat dead through two runs of the queued-command version with
            # its parking brake never released.
            subject.set_shift_mode("arcade")
            bng.control.step(30, wait=True)
            subject.control(parkingbrake=0.0)
            bng.control.step(30, wait=True)
            subject.control(throttle=0.4, steering=0.0)
            bng.control.step(90, wait=True)
            subject.queue_lua_command(
                "local e = electrics.values "
                "obj:queueGameEngineLua('COLOSSUS_CAR_DIAG = ' .. string.format('%q', "
                "jsonEncode({throttle = e.throttle, brake = e.brake, "
                "parkingbrake = e.parkingbrake, gear = tostring(e.gear), "
                "gearIndex = e.gearIndex, rpm = e.rpm, engineRunning = e.engineRunning, "
                "wheelspeed = e.wheelspeed, ignitionLevel = e.ignitionLevel})))"
            )
            for _ in range(10):
                bng.control.step(15, wait=True)
                diag = _lua_json(bng, "return jsonEncode({value = COLOSSUS_CAR_DIAG})")
                if diag.get("value"):
                    report["car_electrics"] = json.loads(diag["value"])
                    break

            fit = _fit_axle(_markers(bng) or points)
            assert fit
            centre, axis, _radius = fit
            origin = centre
            previous_xy = (centre[0], centre[1])
            previous_angle = _marker_angle(centre, axis, (_markers(bng) or points)[0])
            path = 0.0
            rotation = 0.0
            car_speed_peak = 0.0
            car_off_axis_worst = 0.0
            car_z_lowest = float("inf")
            car_climb = (0.0, 0.0)  # min/max of car y relative to the axle
            for sample in range(DRIVE_SAMPLES):
                bng.control.step(SAMPLE_FRAMES, wait=True)
                points_now = _markers(bng)
                car = _car_state(bng)
                if not points_now or not car:
                    continue
                # Station-keeping: throttle by how far up the front wall
                # the car sits, brake any backswing dead - and STEER back to
                # the mid-plane. Axial drift was the one unhandled degree of
                # freedom: nothing centres the car across the cavity, and a
                # run that lost axial station wandered 12.5 m along the axle
                # into the sidewall region while the fore-aft law fought a
                # fight it could no longer win.
                fit_now = _fit_axle(points_now)
                axle_y = fit_now[0][1] if fit_now else previous_xy[1]
                axle_x = fit_now[0][0] if fit_now else 0.0
                ahead = (float(car["y"]) - axle_y) * drive_sign
                off_axis = float(car["x"]) - axle_x
                drift = float(car["vx"])
                forward = float(car["vy"]) * drive_sign > 0.0
                # Positive steering turns left (-x for a nose-minus-y car);
                # the correction flips with travel direction.
                steer = max(-0.3, min(0.3, 0.10 * (off_axis + 1.2 * drift)))
                if not forward:
                    steer = -steer
                backswing = float(car["vy"]) * drive_sign < -0.4
                if backswing:
                    subject.control(throttle=0.0, brake=0.6, steering=steer)
                elif ahead > 9.5:
                    subject.control(throttle=0.05, brake=0.0, steering=steer)
                elif ahead > 6.5:
                    subject.control(throttle=0.15, brake=0.0, steering=steer)
                else:
                    subject.control(throttle=0.3, brake=0.0, steering=steer)
                fit = _fit_axle(points_now)
                if not fit:
                    continue
                centre, axis, radius = fit
                assert abs(radius - SPEC.OUTER_RADIUS) < 0.9, (
                    f"the carcass ovalised under the car: {radius}"
                )
                angle = _marker_angle(centre, axis, points_now[0])
                rotation += _unwrap(previous_angle, angle)
                step_m = math.dist(previous_xy, (centre[0], centre[1]))
                # The axle fit wobbles a couple of centimetres a sample, and
                # 40 samples of that reads as metres of path on a tire that
                # never moved. Only count unambiguous motion.
                if step_m > 0.10:
                    path += step_m
                previous_xy = (centre[0], centre[1])
                previous_angle = angle
                car_speed_peak = max(car_speed_peak, float(car["speed"]))
                car_z_lowest = min(car_z_lowest, float(car["z"]))
                offset_y = float(car["y"]) - centre[1]
                car_climb = (min(car_climb[0], offset_y), max(car_climb[1], offset_y))
                car_off_axis_worst = max(car_off_axis_worst, abs(float(car["x"]) - centre[0]))
                # Riding up the wall in the drive direction is the machine's
                # equilibrium; leaving the cavity is not.
                assert (
                    math.hypot(float(car["y"]) - centre[1], float(car["z"]) - centre[2])
                    < SPEC.CAVITY_RADIUS + 1.0
                ), f"the car left the cavity: {car} vs axle {centre}"

                # The drivetrain sanity check, early and loud: a gate that
                # spent 20 s measuring a parked car would report a hamster
                # failure that is actually a harness failure.
                if sample == 24:
                    assert car_speed_peak > 0.4, (
                        "the car never started driving inside the tire - "
                        f"drivetrain harness problem, not physics: {car}"
                    )

            wedge_after = _lua_json(bng, wedge_probe)
            if wedge_after.get("ok") and wedge_before.get("ok"):
                report["wedge_final_from_start_m"] = round(
                    math.dist(
                        (wedge_before["x"], wedge_before["y"], wedge_before["z"]),
                        (wedge_after["x"], wedge_after["y"], wedge_after["z"]),
                    ),
                    2,
                )
            swept = abs(rotation) * SPEC.OUTER_RADIUS
            moved = math.dist(origin[:2], previous_xy)
            along = (previous_xy[1] - origin[1]) * drive_sign
            report["drive"] = {
                "car_speed_peak_ms": round(car_speed_peak, 2),
                "car_lowest_z_m": round(car_z_lowest - surface_z, 3),
                "car_off_axis_worst_m": round(car_off_axis_worst, 2),
                "car_climb_rel_axle_m": [round(v, 2) for v in car_climb],
                "tire_path_m": round(path, 2),
                "tire_displacement_m": round(moved, 2),
                "tire_along_drive_m": round(along, 2),
                "tire_rotation_deg": round(math.degrees(rotation), 1),
                "tire_arc_m": round(swept, 2),
                # FLOORED PATH against net rotation. The metric has now been
                # wrong twice in two directions: raw path inflated 8.6 m of
                # travel to 41.9 m of fit jitter at creep speeds, and
                # displacement-vs-arc read an honestly-rolling CURVED lap as
                # 0.54 because a chord under-counts a curve. With the 0.10 m
                # step floor, jitter is gone at any real speed, and path
                # follows the curve the tire actually rolled (measured: path
                # 32.1 m, arc 39.3 m, ratio 0.82 on a lap the car steered
                # all over the cavity).
                "hamster_slip_ratio": (round(path / swept, 3) if swept > 0.5 else None),
            }

            # 1. The floor held the whole time.
            assert car_z_lowest > surface_z + 0.25, report["drive"]
            # 1b. The wheel TALKED while it moved: the distance-milestone
            # chatter is the only feedback a hamster driver gets inside the
            # first 88.5 m revolution, and this is what keeps that channel
            # from silently dying in a refactor.
            stats = _lua_json(
                bng,
                f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
                f"local prop = scenetree.findObject({PROP_NAME!r}); "
                "if not (extension and prop) then return jsonEncode({}) end; "
                "local s = extension.getSystemState(prop:getID()); "
                "return jsonEncode({stats = s.behavior_stats})",
            )
            report["behavior_stats"] = stats.get("stats")
            milestones = (stats.get("stats") or {}).get("milestones", 0)
            assert milestones >= 1, (
                "the tire moved but never told the driver: "
                f"{report['behavior_stats']} after {report['drive']}"
            )
            # 2. The car moved the tire, in the direction it drove.
            assert along > HAMSTER_MIN_M, (
                f"a car driving inside the cavity did not move the tire: {report}"
            )
            # 3. And the tire MOVED BY ROLLING, not by being scraped along.
            ratio = report["drive"]["hamster_slip_ratio"]
            assert ratio is not None, report
            assert SLIP_RATIO_BAND[0] <= ratio <= SLIP_RATIO_BAND[1], (
                f"the tire moved without rolling - path and R*dtheta disagree: {report}"
            )

        finally:
            print("COLOSSUS HAMSTER REPORT " + json.dumps(report, sort_keys=True))
            try:
                cleanup_owned_beamng_session(bng, owned_process=owned_process, scenario=scenario)
            finally:
                if timer is not None:
                    timer.cancel()
                cleanup_exact_live_artifacts(
                    profile=user,
                    files=(installed_zip,),
                    empty_directories=(scenario_directory,),
                )
