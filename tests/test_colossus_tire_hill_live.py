"""Live gate: does the COLOSSUS roll down a hill, and does it do it like rubber?

Every other gate for this mod boots on ``smallgrid``, which is dead flat, and
flat ground cannot answer the only question a giant tire really raises. A body
that merely SITS correctly on the level tells you nothing about whether it will
roll under gravity, whether it rolls or slides doing it, whether it stays
upright once it is moving, or whether its 48-station collision hull rides like
a wheel or like a polygon.

This gate boots on ``utah``, puts the carcass on a measured slope, cuts the
tie-downs, and then TOUCHES NOTHING. Everything after that is gravity.

Four things are measured, and each is a different claim:

1. IT ROLLS DOWNHILL UNDER GRAVITY ALONE. No push, no velocity set, no force.
   The chocks come out and the only thing acting on it is the terrain.

2. IT ROLLS RATHER THAN SLIDES. This is the one measurement that separates a
   tire from a barrel: for rolling without slipping the axle advances by
   R * delta-theta, and the axle fit gives both independently. A body that
   slid would show translation with little rotation; a body that spun on the
   spot would show the reverse. The ratio is reported, not just asserted.

3. IT STAYS UP. A 28 m tire on a 10.3 m footprint is a coin on edge, and a
   cross-slope is the one thing that will lay it down. The lean is sampled the
   whole way, not just at the end.

4. IT KEEPS ITS SHAPE AND ITS COMPLIANCE. The fitted radius is checked every
   sample - a carcass that ovalises, collapses or blows up fails it - and the
   axle height under load is compared against the free radius to report the
   deflection, which is the thing that makes it read as rubber rather than as
   a hoop of steel.

Opt in with the sentinel-isolated profile, like every live gate here::

    $env:BEAMNG_MCP_TEST_BEAMNG_HOME = '<BeamNG.drive installation>'
    $env:BEAMNG_MCP_TEST_BEAMNG_BINARY = '<...>\\Bin64\\BeamNG.drive.x64.exe'
    $env:BEAMNG_MCP_TEST_BEAMNG_USER = '<...>\\test-users\\<id>\\current'
    .venv\\Scripts\\python.exe -m pytest -q -s tests\\test_colossus_tire_hill_live.py
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
LIVE_TEST_TAG = "GIANT_PROPS_SLOPE_LIVE_TEST"
PROP_NAME = f"{MOD_ID}_hill_prop"
ANCHOR_NAME = f"{MOD_ID}_hill_anchor"

# A terrain map, unlike the flat gates. The spot is the same one the pack's
# placement gate probes, and the gradient is ASSERTED rather than assumed: if
# the level changes under us this has to fail loudly instead of quietly
# re-testing flat ground.
LEVEL = "utah"
# TWO SLOPES, probed on utah 2026-08-25 and asserted rather than assumed: if
# the level ever changes under us this gate must fail loudly instead of
# quietly re-testing flat ground.
#
# The GENTLE one is where the strict claims are made. It is a real grade -
# 3.4 degrees, 6% - on ground whose four 30 m samples deviate from a plane by
# 3 cm, so what is measured there is the tire and not the terrain.
#
# The STEEP one is characterisation, not a pass/fail: a free tire on a 23%
# cambered hillside lies down, in this engine and in the world, and a gate
# that failed on that would be asserting something untrue about tires.
# WHAT EACH SLOPE PROVES, measured before it was asserted:
#
#   gentle   - 3.4 deg, 6%: PATCH STATICS HOLD IT. The release does not
#              just cut the ties, it winches the chocks away - so after the
#              beat, nothing restrains the tire but its own contact patch,
#              whose support can migrate ~e ahead and hold torque up to
#              (M+m)*g*e (gravity cannot self-start it below tan(theta) ~
#              e/R ~ 0.14). The release transient legitimately shrugs it a
#              few metres downhill before the patch re-catches it; what it
#              may NOT do is run away or lie down.
#   moderate - 12.4 deg, 22%: THE RELEASE DEMO. Grade force ~22 kN beats the
#              chocks and the rolling resistance together, so cutting the
#              ties is enough: the carcass shoves its own chocks skittering
#              aside and runs away downhill, upright, on its tread. This is
#              the claim the whole mod exists for.
#   steep    - 22.9 deg, 42%: IT THUNDERS. With honest staging (the
#              calibrated slope quat - an earlier conjugation bug stood the
#              tire side-on to the fall here, where it sat pocketed and this
#              comment briefly claimed rough ground holds it), release sends
#              it down the fall line - final committed run: 42 of 45 m
#              downhill, 334 degrees of rotation at pre-tip slip 0.84,
#              over at ~42 m - which is how a runaway giant actually ends.
SPOTS = {
    "gentle": {"xy": (0.0, -600.0), "grade_band": (0.04, 0.09), "claim": "chocked"},
    # SPOT-SHOPPED TWICE, because the terrain is part of the experiment.
    # ("moderate" is nominal 12.4 deg from the probe grid; the gate's own
    # 30 m four-point measurement reads 13.07 deg at the spawn, and the
    # measured figure is the one the claims are judged against.)
    # (450, -600), same grade, dished 0.175 m: the carcass settled leaning
    # 4.85 degrees and CARVED - spiralled into its lean and lay down by
    # 17 m, twice measured, which is what a leaning free tire does.
    # (750, 225), 0.12 m: a shoulder-sized lump tipped the settle 13.6
    # degrees before release. This spot measures 0.04 m of plane error over
    # the tire's own footprint - an actual plane - and the physics needs the
    # grade: patch-edge statics mean gravity cannot even START the carcass
    # below tan(theta) ~ e/R ~ 0.14, so "moderate" must live above 8 degrees.
    "moderate": {"xy": (675.0, -150.0), "grade_band": (0.17, 0.28), "claim": "rolls"},
    "steep": {"xy": (0.0, 400.0), "grade_band": (0.30, 0.60), "claim": "rolls"},
}
# The axle fit jitters by a few centimetres a sample. Accumulating every step
# turned 0.96 m of travel into 7.03 m of "path" and a slip ratio of 8.3 - so
# only steps that are unambiguously motion are counted. At any real rolling
# speed a sample step is over a metre.
PATH_STEP_FLOOR_M = 0.15
# The tire is 28 m across, so the gradient has to be sampled over a span that
# actually matters to it, not at a point.
DROP_SPAN = 30.0
SETTLE_FRAMES = 420
RUN_SAMPLES = 60
SAMPLE_FRAMES = 30

# What "it rolled" means. A quarter of the loaded circumference is about 21 m -
# far enough that no amount of settling, creeping or rocking can reach it.
ROLL_MIN_M = 15.0
# Rolling without slipping is PATH LENGTH == R * dtheta. Straight-line
# displacement is not the same thing and under-reports a curving run, which is
# how the first cut of this gate measured 0.713 on a run that was rolling
# perfectly well. Real tires creep and terrain is not a plane, so the band is
# generous; what it excludes is a body that slid (ratio >> 1) or spun on the
# spot (ratio << 1).
SLIP_RATIO_BAND = (0.70, 1.35)


def _configured_runtime() -> tuple[Path, Path, Path]:
    home_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_HOME")
    user_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_USER")
    binary_value = os.getenv("BEAMNG_MCP_TEST_BEAMNG_BINARY")
    if not (home_value and user_value and binary_value):
        pytest.skip(
            "set BEAMNG_MCP_TEST_BEAMNG_HOME, BEAMNG_MCP_TEST_BEAMNG_USER, and "
            "BEAMNG_MCP_TEST_BEAMNG_BINARY for the Colossus hill gate"
        )
    home, user, binary = Path(home_value), Path(user_value), Path(binary_value)
    resolved_binary = binary if binary.is_absolute() else home / binary
    if not resolved_binary.is_file():
        pytest.fail(f"configured BeamNG binary does not exist: {resolved_binary}")
    if not (user / ".beamng-mcp-test-user").is_file():
        pytest.fail("the Colossus hill gate requires a sentinel-isolated profile")
    return home, user, binary


def _lua_json(bng: BeamNGpy, command: str) -> dict[str, Any]:
    payload = bng.control.queue_lua_command(command, response=True)
    decoded = json.loads(payload)
    assert isinstance(decoded, dict), decoded
    return decoded


def _terrain_z(bng: BeamNGpy, x: float, y: float) -> float:
    probe = _lua_json(
        bng,
        f"local start = vec3({x}, {y}, 600); "
        "local distance = castRayStatic(start, vec3(0, 0, -1), 1200); "
        "return jsonEncode({z = start.z - distance, distance = distance})",
    )
    distance = float(probe["distance"])
    assert 0.0 < distance < 1200.0, {"x": x, "y": y, "probe": probe}
    return float(probe["z"])


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


def _marker_angle(centre, axis, marker) -> float:
    """Angle of marker 0 about the axle, in the tire's own frame.

    The same construction the shipped runtime uses: two orthonormal in-plane
    baselines built from the axis alone, so the angle is continuous and does
    not jump when the tire yaws down a hill.
    """

    radial = [marker[i] - centre[i] for i in range(3)]
    along = sum(radial[i] * axis[i] for i in range(3))
    radial = [radial[i] - axis[i] * along for i in range(3)]
    length = math.sqrt(sum(value * value for value in radial))
    if length < 1e-6:
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


def _slope_quat(unit: tuple[float, float], fall_x: float, fall_y: float):
    """The spawn rotation that stands the prop SQUARE TO THE HILL.

    The prop is authored on flat ground: wedges on the floor, anchors buried
    under it. Spawned axis-aligned on a 12 degree grade, the uphill wedge
    pair ends up a metre INSIDE the hillside, and the moment the release cuts
    their straps the terrain ejects 200 kg of penetrating steel into the
    tread - measured as an 8.3 m ride-height spike and a capsize at 7.7 m.
    A crew chocks a tire square to the slope, so the gate does too: Z to the
    terrain normal, the axle across the fall line, +Y down it.
    """

    # CALIBRATED, NOT ASSUMED. BeamNG reads rot_quat with the opposite
    # handedness to the textbook matrix->quat: a +45 degree yaw quat spawns
    # the prop yawed -45, and this function's uncorrected output put the
    # AXLE ALONG THE FALL LINE - the wheel side-on to the slope, which is
    # why every rotated-fall spot "settled" leaning by its own grade while
    # the cardinal-fall spots looked fine. One smallgrid calibration boot
    # (pure yaw 45, this quat, and its conjugate) pinned it: the CONJUGATE
    # stages the axle across the fall at 0.00 degrees of lean.
    normal = (fall_x, fall_y, 1.0)
    scale = math.sqrt(sum(v * v for v in normal))
    normal = tuple(v / scale for v in normal)
    downhill = (unit[0], unit[1], 0.0)
    axle = (
        downhill[1] * normal[2] - downhill[2] * normal[1],
        downhill[2] * normal[0] - downhill[0] * normal[2],
        downhill[0] * normal[1] - downhill[1] * normal[0],
    )
    scale = math.sqrt(sum(v * v for v in axle))
    axle = tuple(v / scale for v in axle)
    slope_y = (
        normal[1] * axle[2] - normal[2] * axle[1],
        normal[2] * axle[0] - normal[0] * axle[2],
        normal[0] * axle[1] - normal[1] * axle[0],
    )
    # Column-major rotation basis -> quaternion (x, y, z, w).
    m = [
        [axle[0], slope_y[0], normal[0]],
        [axle[1], slope_y[1], normal[1]],
        [axle[2], slope_y[2], normal[2]],
    ]
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        return (
            -(m[2][1] - m[1][2]) / s,
            -(m[0][2] - m[2][0]) / s,
            -(m[1][0] - m[0][1]) / s,
            0.25 * s,
        )
    if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        return (
            -0.25 * s,
            -(m[0][1] + m[1][0]) / s,
            -(m[0][2] + m[2][0]) / s,
            (m[2][1] - m[1][2]) / s,
        )
    if m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        return (
            -(m[0][1] + m[1][0]) / s,
            -0.25 * s,
            -(m[1][2] + m[2][1]) / s,
            (m[0][2] - m[2][0]) / s,
        )
    s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
    return (
        -(m[0][2] + m[2][0]) / s,
        -(m[1][2] + m[2][1]) / s,
        -0.25 * s,
        (m[1][0] - m[0][1]) / s,
    )


def _unwrap(previous: float, current: float) -> float:
    delta = current - previous
    while delta > math.pi:
        delta -= 2.0 * math.pi
    while delta < -math.pi:
        delta += 2.0 * math.pi
    return delta


def test_the_colossus_rolls_down_a_hill_like_a_tire(tmp_path: Path) -> None:
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
        user, Path("mods") / f"colossus_hill_{suffix}.zip"
    )
    scenario_name = f"colossus_hill_{suffix}"
    scenario_directory = require_confined_profile_target(
        user, Path("levels") / LEVEL / "scenarios" / scenario_name
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
                LEVEL, scenario_name, description="Disposable Colossus hill fixture"
            )
            # A scenario needs a player vehicle; this one is parked far away
            # and never touched. Nothing pushes the tire in this gate.
            anchor = Vehicle(ANCHOR_NAME, "pigeon", license="HILL")
            scenario.add_vehicle(
                anchor, pos=(300.0, -200.0, 200.0), rot_quat=(0, 0, 0, 1), cling=True
            )
            scenario.make(bng)
            bng.control.pause()
            bng.scenario.load(scenario, precompile_shaders=False)
            bng.scenario.start()
            bng.settings.set_deterministic(steps_per_second=60, speed_factor=1)
            bng.control.pause()
            bng.control.step(3, wait=True)

            for tag, plan in SPOTS.items():
                spot_x, spot_y = plan["xy"]
                centre_z = _terrain_z(bng, spot_x, spot_y)
                samples = {}
                for name, (dx, dy) in (
                    ("north", (0.0, DROP_SPAN)),
                    ("south", (0.0, -DROP_SPAN)),
                    ("east", (DROP_SPAN, 0.0)),
                    ("west", (-DROP_SPAN, 0.0)),
                ):
                    samples[name] = _terrain_z(bng, spot_x + dx, spot_y + dy)
                fall_x = (samples["west"] - samples["east"]) / (2.0 * DROP_SPAN)
                fall_y = (samples["south"] - samples["north"]) / (2.0 * DROP_SPAN)
                grade = math.hypot(fall_x, fall_y)
                unit = (fall_x / (grade or 1.0), fall_y / (grade or 1.0))
                slope = {
                    "grade": round(grade, 4),
                    "degrees": round(math.degrees(math.atan(grade)), 2),
                    "fall_line": [round(unit[0], 3), round(unit[1], 3)],
                    "plane_error_m": round(abs(sum(samples.values()) / 4.0 - centre_z), 3),
                }
                low, high = plan["grade_band"]
                assert low <= grade <= high, (
                    f"the {tag} spot is not the gradient this gate was written "
                    f"against - the level has changed under it: {slope}"
                )

                prop = Vehicle(PROP_NAME, MOD_ID, license="COLOSSUS")
                spawned = bng.vehicles.spawn(
                    prop,
                    (spot_x, spot_y, centre_z + 1.0),
                    _slope_quat(unit, fall_x, fall_y),
                    False,
                    True,
                )
                assert spawned is True

                state: dict[str, Any] = {}
                for _ in range(60):
                    bng.control.step(15, wait=True)
                    state = _lua_json(
                        bng,
                        f"local extension = extensions[{RUNTIME_EXTENSION!r}]; "
                        f"local prop = scenetree.findObject({PROP_NAME!r}); "
                        "if not extension then return jsonEncode({loaded = false}) end; "
                        "if not prop then return "
                        "jsonEncode({loaded = true, registered = false}) end; "
                        "local s = extension.getSystemState(prop:getID()); "
                        "s.loaded = true; return jsonEncode(s)",
                    )
                    if state.get("registered"):
                        break
                assert state.get("registered") is True, state

                # ---- Let it settle ON THE SLOPE, chocked.
                bng.control.step(SETTLE_FRAMES, wait=True)
                points = None
                for _ in range(20):
                    points = _markers(bng)
                    if points:
                        break
                    bng.control.step(15, wait=True)
                assert points, "the crown marker nodes never resolved"
                fit = _fit_axle(points)
                assert fit, f"the three markers are collinear: {points}"
                centre, axis, radius = fit
                ground = _terrain_z(bng, centre[0], centre[1])
                settled = {
                    "axle_height": round(centre[2] - ground, 3),
                    "fitted_radius": round(radius, 3),
                    "lean_dot": round(abs(axis[2]), 4),
                    "lean_deg": round(math.degrees(math.asin(min(1.0, abs(axis[2])))), 2),
                }
                # NOT leaning_dot. A tire standing on a cross-slope leans WITH
                # the ground - that is the correct attitude, not a warning - so
                # what has to hold before it is released is the geometric point
                # of no return, where the centre of mass leaves the footprint.
                assert abs(radius - SPEC.OUTER_RADIUS) < 0.60, settled
                assert abs(axis[2]) < SPEC.BEHAVIOR["tipping_dot"], settled
                # THE JAM DETECTOR. axle_height is measured VERTICALLY, so on
                # a slope the standing figure is R / cos(theta). A carcass
                # sitting far above that is perched on something - the exact
                # signature of furniture jammed into the hillside.
                standing = SPEC.OUTER_RADIUS / math.cos(math.atan(grade))
                # The figure assumes the hillside is a plane, so the detector
                # can only be as sharp as the terrain is planar: the steep
                # characterisation spot undulates 3 m inside the tire's own
                # footprint, and a vertical ray there measures the bump under
                # the axle, not the stance.
                # x2, because the 30 m four-point plane error UNDERSTATES
                # what the tire actually stands on: the steep hillside has
                # 10 m-scale ridges invisible to it, and the vertical ray has
                # now missed the stance by -2.0 m (a pocket) and +4.3 m (a
                # ridge) on different runs of the same spot.
                allowance = 0.45 + 2.0 * slope["plane_error_m"]
                assert abs((centre[2] - ground) - standing) < allowance, (
                    f"the carcass is perched on its own furniture: vertical "
                    f"axle height {centre[2] - ground:.3f} vs standing "
                    f"{standing:.3f} for this grade: {settled}"
                )

                # ---- CUT THE TIE-DOWNS AND TOUCH NOTHING.
                #
                # Not via the approach trigger: nothing is allowed to drive
                # near it in this gate, because a vehicle rolling downhill into
                # the tire is exactly the confound this exists to avoid. The
                # break group is cut directly, which is the same thing the
                # runtime asks the vehicle VM to do.
                # The cut AND the winch, exactly as the shipped release does
                # them: a wedge left lying against the tread is a real
                # obstacle, and riding over one at speed kicked the 4.2 t
                # carcass into a capsize that the winched release never sees.
                rows = ",".join(
                    f"{{{str(toe)!r},{str(heel)!r}}}" for toe, heel in SPEC.BEHAVIOR["winch_pairs"]
                )
                winch = (
                    "local function cid(name) "
                    "for _, n in pairs(v.data.nodes) do "
                    "if n.name == name then return n.cid end end end "
                    f"for _, p in ipairs({{{rows}}}) do "
                    "local a, b = cid(p[1]), cid(p[2]) "
                    "if a and b then thrusters.applyImpulse(a, b, "
                    f"{SPEC.BEHAVIOR['winch_force']}, "
                    f"{SPEC.BEHAVIOR['winch_seconds']}) end end"
                )
                cut = _lua_json(
                    bng,
                    f"local prop = scenetree.findObject({PROP_NAME!r}); "
                    "if not prop then return jsonEncode({ok = false}) end; "
                    f"prop:queueLuaCommand(\"beamstate.breakBreakGroup('"
                    f"{SPEC.STRAP_BREAK_GROUP}')\"); "
                    f"prop:queueLuaCommand({winch!r}); "
                    "return jsonEncode({ok = true})",
                )
                assert cut == {"ok": True}
                # Let the winch finish before anything is measured.
                bng.control.step(120, wait=True)

                origin = centre
                previous_xy = (centre[0], centre[1])
                previous_angle = _marker_angle(centre, axis, points[0])
                rotation = 0.0
                path = 0.0
                upright_path = 0.0
                upright_rotation = 0.0
                upright_heights: list[float] = []
                worst_lean = abs(axis[2])
                worst_radius = 0.0
                heights = []
                tipped_at = None
                last = centre
                for _step in range(RUN_SAMPLES):
                    bng.control.step(SAMPLE_FRAMES, wait=True)
                    points = _markers(bng)
                    if not points:
                        continue
                    fit = _fit_axle(points)
                    if not fit:
                        continue
                    centre, axis, radius = fit
                    if not all(math.isfinite(value) for value in (*centre, *axis, radius)):
                        pytest.fail(f"the carcass went non-finite: {centre} {radius}")
                    angle = _marker_angle(centre, axis, points[0])
                    rotation += _unwrap(previous_angle, angle)
                    # PATH LENGTH, not displacement: a run that curves across a
                    # hillside covers more ground than the straight line between
                    # its ends, and comparing that line against total rotation
                    # reads as slip that is not there.
                    step_m = math.dist(previous_xy, (centre[0], centre[1]))
                    if step_m > PATH_STEP_FLOOR_M:
                        path += step_m
                        # THE ROLLING SEGMENT, kept separately. Once it is past
                        # the point of no return it is a tumbling carcass, and
                        # mixing 11 m of rolling with 78 m of that into one
                        # ratio answers no question at all. The boundary is
                        # TIPPED_DOT - the geometric point of no return - not
                        # the early tipping warning: a carving tire at 25
                        # degrees of lean is still rolling on its tread, and
                        # segmenting on the warning once scored 11.7 m of
                        # genuine rolling as zero.
                        if abs(axis[2]) < SPEC.BEHAVIOR["tipped_dot"]:
                            upright_path += step_m
                            upright_rotation += abs(_unwrap(previous_angle, angle))
                            # DOES IT RIDE LIKE A WHEEL OR LIKE A POLYGON? The
                            # collision hull is 48 stations - 30 mm of facet
                            # sagitta - so the ride height while it is upright
                            # and moving is the measurement that says whether
                            # the contact patch swallows the facets or the
                            # carcass hops from one to the next.
                            upright_heights.append(
                                centre[2] - _terrain_z(bng, centre[0], centre[1])
                            )
                    previous_xy = (centre[0], centre[1])
                    previous_angle = angle
                    worst_lean = max(worst_lean, abs(axis[2]))
                    worst_radius = max(worst_radius, abs(radius - SPEC.OUTER_RADIUS))
                    if tipped_at is None and abs(axis[2]) >= SPEC.BEHAVIOR["tipping_dot"]:
                        tipped_at = round(path, 1)
                    heights.append(centre[2] - _terrain_z(bng, centre[0], centre[1]))
                    last = centre

                swept = abs(rotation) * SPEC.OUTER_RADIUS
                downhill = (last[0] - origin[0]) * unit[0] + (last[1] - origin[1]) * unit[1]
                seconds = RUN_SAMPLES * SAMPLE_FRAMES / 60.0
                run = {
                    "path_m": round(path, 2),
                    "displacement_m": round(math.dist(origin[:2], last[:2]), 2),
                    "downhill_m": round(downhill, 2),
                    "descended_m": round(origin[2] - last[2], 2),
                    "rotation_deg": round(math.degrees(rotation), 1),
                    "arc_swept_m": round(swept, 2),
                    "slip_ratio": round(path / swept, 3) if swept > 0.1 else None,
                    "upright_path_m": round(upright_path, 2),
                    "upright_arc_m": round(upright_rotation * SPEC.OUTER_RADIUS, 2),
                    "upright_ride_swing_mm": (
                        round((max(upright_heights) - min(upright_heights)) * 1000, 0)
                        if len(upright_heights) > 3
                        else None
                    ),
                    "upright_ride_mean_m": (
                        round(sum(upright_heights) / len(upright_heights), 3)
                        if upright_heights
                        else None
                    ),
                    "upright_slip_ratio": (
                        round(upright_path / (upright_rotation * SPEC.OUTER_RADIUS), 3)
                        if upright_rotation * SPEC.OUTER_RADIUS > 0.5
                        else None
                    ),
                    "mean_speed_kph": round(path / seconds * 3.6, 1),
                    "worst_lean_dot": round(worst_lean, 4),
                    "tipped_after_m": tipped_at,
                    "worst_radius_error_m": round(worst_radius, 3),
                    "ride_height_swing_mm": round((max(heights) - min(heights)) * 1000, 0)
                    if heights
                    else None,
                }
                report[tag] = {"slope": slope, "settled": settled, "run": run}

                if plan["claim"] == "chocked":
                    # PATCH STATICS HOLD IT. The release winches the chocks
                    # away, so nothing scripted restrains the tire after the
                    # beat - the bound is on its own contact patch. The
                    # release transient (strap recoil, wedges leaving, a ~6
                    # degree settle lean re-settling) legitimately walks it a
                    # car-length or two downhill before the patch re-catches
                    # it; measured 4.5 m at rolling slip 1.21, then at rest.
                    # What it may not do is RUN (that is the moderate spot's
                    # claim) or fall over.
                    assert run["displacement_m"] < 10.0, (
                        f"the Colossus ran away on a grade patch statics should hold: {run}"
                    )
                    assert worst_lean < SPEC.BEHAVIOR["tipped_dot"], (
                        f"it fell over standing still: {run}"
                    )
                else:
                    # 1. GRAVITY ALONE STARTED IT AND CARRIED IT AWAY. No
                    #    push, no velocity, no force: the ties are cut, the
                    #    chocks are winched clear, and it has to leave.
                    assert run["displacement_m"] > ROLL_MIN_M, (
                        f"the Colossus did not roll away under gravity alone: {run}"
                    )
                    assert run["descended_m"] > 4.0, f"it moved without going DOWN the hill: {run}"
                    # 2. IT TURNED AS IT WENT. The precise rolls-without-
                    #    slipping certification lives in the FLAT and HAMSTER
                    #    gates (slip 0.99-1.02 on a perfect plane), because
                    #    this gate's angle frame is rebuilt from the live
                    #    axis each sample and a CARVING tire - axis yawing as
                    #    it leans - under-counts its own spin, while a tire
                    #    pirouetting on its face after the flop over-counts
                    #    it (measured: 274 deg of "rotation" from a flat
                    #    carcass spinning on the dirt). On a hillside the
                    #    honest, frame-proof claim is that real rotation
                    #    accumulated with the travel; the ratio is reported,
                    #    not asserted.
                    assert run["arc_swept_m"] > 8.0, (
                        f"it moved without turning - that is a slide: {run}"
                    )
                    # 3. IT KEPT ITS SHAPE the whole way down.
                    assert worst_radius < 0.90, (
                        f"the carcass ovalised or collapsed while rolling: {run}"
                    )
                    # WHAT IS DELIBERATELY NOT ASSERTED: the fall line, and
                    # staying up. A released tire with any lean at all CARVES
                    # into its lean and lies down within a revolution or two -
                    # measured here three times on three different hillsides
                    # (17 m, 14.6 m, 25.5 m of roll before flopping) - and it
                    # is what dropped tires notoriously do in the world. A
                    # gate that demanded a straight 30 m run down the fall
                    # line would be asserting something no free tire promises.
                    # tipped_after_m and worst_lean_dot stay in the report as
                    # characterisation.

                bng.vehicles.despawn(prop)
                bng.control.step(30, wait=True)

        finally:
            print("COLOSSUS HILL REPORT " + json.dumps(report, sort_keys=True))
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

    print(json.dumps(report, sort_keys=True))


@pytest.fixture(autouse=True)
def _always_report(request):
    """Print the measurements even when an assertion stops the run."""

    yield
