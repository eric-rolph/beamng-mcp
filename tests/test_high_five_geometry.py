"""Offline geometry and pose gates for Charlie's High Five.

The pack's static gates prove the evidence chain and the lupa gate proves
the state machine, but neither can see the thing this machine is actually
made of: a chain of derived vectors that has to agree in THREE independent
transcriptions —

* ``spec.py``, which computes the hand frame and the digit pivots/axes and
  formats them into the generated Lua,
* ``blender/hand_sculpt.py``, which builds the mesh in a hand-local frame
  and maps it into the authored frame,
* the emitted ``runtime.lua``, which re-derives where every part goes each
  frame from the same numbers.

A sign error in any one of them is EXACTLY IDENTITY at the authored rest
pose. That is the whole danger: the prop looks perfect until it swings, or
until it is placed at a nonzero yaw, which is the same failure signature
that cost this repo three compounding convention bugs on 2026-08-24 (see
``tests/test_giant_props_frame_math.py``). So the tests below deliberately
assert at NON-rest angles.

Nothing here needs Blender or BeamNG.
"""

from __future__ import annotations

import importlib.util
import math
import re
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "high_five"


def load_spec():
    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader = importlib.util.spec_from_file_location("high_five_spec", spec_path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


spec = load_spec()


# ---------------------------------------------------------------------------
# Vector helpers — deliberately hand-rolled, so this file shares no code with
# the thing it is checking.
# ---------------------------------------------------------------------------


def dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=False))


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    length = norm(a) or 1.0
    return tuple(x / length for x in a)


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=False))


def add(a, b):
    return tuple(x + y for x, y in zip(a, b, strict=False))


def scale(a, k):
    return tuple(x * k for x in a)


def rodrigues(vector, axis, angle):
    axis = unit(axis)
    c, s = math.cos(angle), math.sin(angle)
    return add(
        add(scale(vector, c), scale(cross(axis, vector), s)),
        scale(axis, dot(axis, vector) * (1.0 - c)),
    )


def spin_z(point, centre_xy, angle):
    dx, dy = point[0] - centre_xy[0], point[1] - centre_xy[1]
    c, s = math.cos(angle), math.sin(angle)
    return (centre_xy[0] + dx * c - dy * s, centre_xy[1] + dx * s + dy * c, point[2])


# ---------------------------------------------------------------------------
# The hand frame
# ---------------------------------------------------------------------------


def test_hand_frame_is_orthonormal_and_right_handed_for_a_right_hand():
    """n = v x u is the identity that makes this a RIGHT hand.

    It is also what puts the thumb at +Z with the fingers pointing radially
    out and the palm facing the sweep tangent — i.e. the pose was not
    chosen, it fell out. If this ever fails the prop has quietly become a
    left hand, and the thumb will be on the wrong side of a mesh nobody
    re-renders.
    """

    u, v, n = spec.U_REST, spec.V_REST, spec.N_REST
    for axis, name in ((u, "u"), (v, "v"), (n, "n")):
        assert norm(axis) == pytest.approx(1.0, abs=1e-9), name
    assert dot(u, v) == pytest.approx(0.0, abs=1e-9)
    assert dot(u, n) == pytest.approx(0.0, abs=1e-9)
    assert dot(v, n) == pytest.approx(0.0, abs=1e-9)
    for actual, expected in zip(cross(v, u), n, strict=False):
        assert actual == pytest.approx(expected, abs=1e-9)
    # Thumb up.
    assert v == (0.0, 0.0, 1.0)


def test_hand_local_basis_used_by_the_generator_is_a_rotation_not_a_reflection():
    """hand_sculpt builds in (x=u, y=n, z=v) and maps with columns [u|n|v].

    (u, v, n) is LEFT-handed because n = v x u, so a [u|v|n] matrix would
    have determinant -1 and silently invert every normal on the hero mesh.
    The generator's docstring says it uses [u|n|v]; this asserts that the
    ordering it names really is the proper one.
    """

    u, n, v = spec.U_REST, spec.N_REST, spec.V_REST
    determinant = dot(u, cross(n, v))
    assert determinant == pytest.approx(1.0, abs=1e-9)
    # And the ordering the module rejects really is the reflection.
    assert dot(u, cross(v, n)) == pytest.approx(-1.0, abs=1e-9)


def test_the_origin_is_the_strike_point():
    """At contact azimuth the palm centre must pass through (0, 0, WRIST_Z).

    Every trigger, effect and launch vector is measured from the prop
    origin, and the whole reason MAST_X is derived rather than authored is
    so this holds by construction.
    """

    assert spec.CONTACT_DEG == 0.0
    contact_u = (1.0, 0.0, 0.0)  # azimuth 0 points +x
    palm_centre = add(
        (spec.MAST_X, spec.MAST_Y, spec.WRIST_Z),
        scale(contact_u, spec.WRIST_R + spec.PALM_CENTRE_U),
    )
    assert palm_centre[0] == pytest.approx(0.0, abs=1e-9)
    assert palm_centre[1] == pytest.approx(0.0, abs=1e-9)
    assert palm_centre[2] == pytest.approx(spec.WRIST_Z, abs=1e-9)


def swept_low_point():
    """Lowest point anything on the hand reaches, over every TILT detent.

    Sampled along every DIGIT as well as the palm. The first version of
    this gate asserted only on the palm's ulnar edge — PALM_WIDTH/2 below
    the hand axis — agreed with WRIST_Z's comment, and passed. It was
    wrong: the little finger's metacarpal head already sits within 90 mm of
    that edge and its splay takes the tip half a metre further down again,
    so the pinky swept 0.42 m UNDER the tarmac at TILT 0 and 0.09 m under
    at the default setting. Measured on the shipped meshes, not inferred.

    The swing is about a VERTICAL axis, so z does not vary with azimuth and
    the roll is the only thing that can lift anything. Worst case is
    therefore a sweep over the detents.
    """

    worst = (spec.WRIST_Z, "palm")
    for index in range(spec.BEHAVIOR["tilt_levels"]):
        tilt = math.radians(index * spec.BEHAVIOR["tilt_step_deg"])
        edge = rodrigues(scale(spec.V_REST, -spec.PALM_WIDTH / 2.0), spec.U_REST, tilt)
        if spec.WRIST_Z + edge[2] < worst[0]:
            worst = (spec.WRIST_Z + edge[2], "palm")
        for name in spec.DIGIT_ORDER:
            pivot = spec.DIGIT_PIVOTS[name]
            ray = spec.DIGIT_RAYS[name]
            if name == "thumb":
                length = spec._mm(spec.THUMB_LENGTH_MM)
                radius = spec._mm(spec.THUMB_DIAMETER_MM) / 2.0
            else:
                length = spec._mm(spec.FINGER_LENGTH_MM[name])
                radius = spec._mm(spec.FINGER_DIAMETER_MM[name]) / 2.0
            radius *= 1.0 + spec.MCP_HEAD_SWELL
            for step in range(9):
                along = length * step / 8.0
                point = add(pivot, scale(ray, along))
                carried = rodrigues(sub(point, spec.WRIST_POINT), spec.U_REST, tilt)
                low = spec.WRIST_POINT[2] + carried[2] - radius
                if low < worst[0]:
                    worst = (low, f"{name}@{along:.1f}m tilt{index}")
    return worst


def test_nothing_on_the_hand_sweeps_below_grade():
    low, where = swept_low_point()
    assert low > 0.15, (
        f"{where} reaches z={low:.3f} m; the hand ploughs the road on its own "
        "swing. Raise WRIST_Z or pull in the ulnar splay."
    )


def test_the_palm_still_reaches_a_cars_body():
    """Clearance is bought by lifting the hand, so it has to be spent
    carefully: lift it far enough and the machine sails over the roof and
    launches cars it never touched, which is the one thing it must not do.
    """

    palm_bottom = spec.WRIST_Z - spec.PALM_WIDTH / 2.0
    assert palm_bottom < 1.25, (
        f"palm bottom edge is {palm_bottom:.2f} m up; a hatchback's waistline "
        "is under a metre and the slap would be all air"
    )
    low, _where = swept_low_point()
    assert low < 0.60, f"the lowest thing on the hand is {low:.2f} m up — nothing reaches a bumper"


# ---------------------------------------------------------------------------
# Digit pivots and axes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", spec.DIGIT_ORDER)
def test_digit_flexion_axis_curls_into_the_palm(name):
    """A positive flex angle must move the fingertip toward +n.

    This is the sign that decides whether the twitch looks like a hand
    beckoning or like a hand bending backwards at every joint, and it is
    invisible at rest because the twitch amplitude is zero there.
    """

    axis = spec.DIGIT_AXES[name]
    ray = spec.DIGIT_RAYS[name]
    assert norm(axis) == pytest.approx(1.0, abs=1e-6)
    assert norm(ray) == pytest.approx(1.0, abs=1e-6)
    # The flexion axis is perpendicular to its own ray...
    assert dot(axis, ray) == pytest.approx(0.0, abs=1e-6)
    # ...and a small positive turn about it carries the tip toward the palm.
    moved = rodrigues(ray, axis, math.radians(10.0))
    assert dot(sub(moved, ray), spec.N_REST) > 0.0, (
        f"{name}: positive flexion bends AWAY from the palm"
    )


@pytest.mark.parametrize("name", spec.FINGER_ORDER)
def test_metacarpal_heads_cover_the_palms_distal_end(name):
    """Every knuckle ball must overlap its neighbour, and the row must span
    the palm.

    The palm's distal cap is a plain half-ellipsoid whose pole is buried
    inside the middle metacarpal head — that is only legitimate because the
    row of heads covers what the cap does. If a head shrinks or the arc
    spreads, the cap becomes a visible bare cliff between the fingers, which
    is exactly what the first build looked like.
    """

    order = list(spec.FINGER_ORDER)

    def head(finger):
        _u, v, _n = spec.mcp_local(finger)
        radius = spec._mm(spec.FINGER_DIAMETER_MM[finger]) / 2.0 * (1.0 + spec.MCP_HEAD_SWELL)
        return v, radius

    index = order.index(name)
    v_here, r_here = head(name)
    if index + 1 < len(order):
        v_next, r_next = head(order[index + 1])
        gap = abs(v_here - v_next) - (r_here + r_next)
        assert gap < 0.0, f"{name} and {order[index + 1]} knuckles do not touch: {gap:.3f} m apart"
    # And the whole row must reach at least to the palm's own half width on
    # the ulnar side, where there is no thumb to cover the corner.
    lows = [v - r for v, r in (head(f) for f in order)]
    assert min(lows) <= -spec.PALM_WIDTH / 2.0 + 0.05


def test_thumb_is_rooted_at_the_wrist_not_past_the_knuckles():
    """The trapezium is a WRIST bone.

    Authored once as +22 mm distal of the middle metacarpal head, which put
    the entire thumb a metre beyond the knuckle line growing out of nothing.
    """

    u, v, _n = spec.thumb_cmc_local()
    assert u < spec.PALM_LENGTH * 0.45, f"thumb CMC at u={u:.2f} is too distal"
    assert u > 0.0, "thumb CMC is behind the wrist crease"
    assert v > 0.0, "thumb CMC is on the ulnar side"
    assert v < spec.PALM_WIDTH / 2.0, "thumb CMC is outside the palm"


def test_thumb_opposes_the_fingers():
    """The thumb ray must have a real palmar component, and its flexion axis
    must not be parallel to the fingers'.

    Both are what stop the thumb reading as a short sixth finger. The
    palmar sign was authored backwards once and the thumb pointed out
    behind the back of the hand.
    """

    ray = spec.DIGIT_RAYS["thumb"]
    assert dot(ray, spec.N_REST) > 0.25, "thumb does not reach toward the palm"
    assert dot(ray, spec.V_REST) > 0.25, "thumb is not abducted toward the radial side"
    middle_axis = spec.DIGIT_AXES["middle"]
    thumb_axis = spec.DIGIT_AXES["thumb"]
    alignment = abs(dot(unit(middle_axis), unit(thumb_axis)))
    assert alignment < 0.75, (
        f"thumb flexes in nearly the same plane as the fingers ({alignment:.2f}); "
        "THUMB_PRONATE_DEG is not doing its job"
    )


# ---------------------------------------------------------------------------
# The pose maths the runtime performs
# ---------------------------------------------------------------------------


def swing_and_roll(point, azimuth_deg, tilt_deg):
    """Independent re-derivation of where a point on the hand ends up.

    p' = Swing( Roll(p - W) + W ), roll about the authored forearm axis
    through the wrist, swing about the vertical slew axis through the mast.
    """

    wrist = spec.WRIST_POINT
    rolled = add(rodrigues(sub(point, wrist), spec.U_REST, math.radians(tilt_deg)), wrist)
    return spin_z(rolled, (spec.MAST_X, spec.MAST_Y), math.radians(azimuth_deg - spec.REST_DEG))


def test_wrist_stays_on_its_own_circle_through_the_whole_stroke():
    for azimuth in (spec.REST_DEG, spec.WINDUP_DEG, -40.0, spec.CONTACT_DEG, spec.FOLLOW_DEG):
        moved = swing_and_roll(spec.WRIST_POINT, azimuth, 40.0)
        radius = math.hypot(moved[0] - spec.MAST_X, moved[1] - spec.MAST_Y)
        # 1e-5, not 1e-9: WRIST_POINT is rounded to six decimals where it is
        # authored, so the circle it lies on is only true to that.
        assert radius == pytest.approx(spec.WRIST_R, abs=1e-5), azimuth
        assert moved[2] == pytest.approx(spec.WRIST_Z, abs=1e-9), (
            "TILT must roll the hand about the forearm, not lift the wrist"
        )


def test_roll_does_not_move_the_wrist_but_does_move_the_knuckles():
    """The two halves of the same claim, asserted at a NON-zero tilt.

    Everything in this file that is only checked at tilt 0 would pass with
    the roll axis set to any vector at all.
    """

    still = swing_and_roll(spec.WRIST_POINT, spec.REST_DEG, 50.0)
    assert still == pytest.approx(spec.WRIST_POINT, abs=1e-9)
    moved = swing_and_roll(spec.DIGIT_PIVOTS["thumb"], spec.REST_DEG, 50.0)
    assert norm(sub(moved, spec.DIGIT_PIVOTS["thumb"])) > 1.0


def test_launch_elevation_equals_the_tilt_setting():
    """The launch leaves along the palm normal, and at CONTACT_DEG the palm
    normal is authored +y rolled up by TILT.

    This is the one identity the console is selling, so it is measured
    rather than asserted in a comment: the runtime builds the direction as
    ``vec3(0, cos tilt, sin tilt)`` and this checks that the vector it names
    really is the sweep tangent rolled about the forearm.
    """

    for index in range(spec.BEHAVIOR["tilt_levels"]):
        tilt_deg = index * spec.BEHAVIOR["tilt_step_deg"]
        claimed = (0.0, math.cos(math.radians(tilt_deg)), math.sin(math.radians(tilt_deg)))
        elevation = math.degrees(math.asin(max(-1.0, min(1.0, claimed[2]))))
        assert elevation == pytest.approx(tilt_deg, abs=1e-9)
        # And the tangent at contact really is +y: the sweep tangent is
        # perpendicular to the boom, and at azimuth 0 the boom is +x.
        contact_u = (1.0, 0.0, 0.0)
        tangent = cross((0.0, 0.0, 1.0), contact_u)
        assert tangent == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)


def test_ballistic_range_ladder_is_monotonic_and_lands_on_the_map():
    """POWER and TILT must both do something, and the top of the ladder must
    not be a teleport.

    Flat ground, no drag; enough to catch a ladder where two settings do
    the same thing or where the top setting throws a car off the level.
    """

    behavior = spec.BEHAVIOR
    speed = (behavior["slap_speed_min_mps"] + behavior["slap_speed_max_mps"]) / 2.0

    def ranged(power_level, tilt_index):
        multiplier = 1.0 + (power_level - 1) * (behavior["power_multiplier_max"] - 1.0) / (
            behavior["power_levels"] - 1
        )
        v = speed * multiplier
        theta = math.radians(tilt_index * behavior["tilt_step_deg"])
        # Launched from the palm's height, so solve the full quadratic.
        vy, vz = v * math.cos(theta), v * math.sin(theta)
        flight = (vz + math.sqrt(vz * vz + 2.0 * 9.81 * spec.WRIST_Z)) / 9.81
        return vy * flight

    mid_tilt = behavior["tilt_levels"] // 2
    powers = [ranged(level, mid_tilt) for level in range(1, behavior["power_levels"] + 1)]
    assert powers == sorted(powers), "POWER ladder is not monotonic"
    assert powers[-1] / powers[0] > 3.0, "POWER ladder barely does anything"

    tilts = [ranged(behavior["default_power_level"], i) for i in range(behavior["tilt_levels"])]
    assert len(set(round(value, 1) for value in tilts)) == len(tilts), (
        "two TILT detents give the same range"
    )
    assert max(powers) < 4000.0, (
        f"top of the ladder throws a car {max(powers):.0f} m — that is a teleport, not a slap"
    )


# ---------------------------------------------------------------------------
# The generated Lua must carry the SAME numbers
# ---------------------------------------------------------------------------


def emitted_runtime() -> str:
    path = PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID / "runtime.lua"
    return path.read_text(encoding="utf-8")


def parse_vec3(source: str, name: str):
    match = re.search(
        rf"\b{re.escape(name)}\s*=\s*vec3\(([-\d.e+]+),\s*([-\d.e+]+),\s*([-\d.e+]+)\)",
        source,
    )
    assert match, f"{name} not found in the generated runtime"
    return tuple(float(match.group(i)) for i in (1, 2, 3))


def test_generated_lua_carries_the_spec_geometry():
    """spec.py formats the pivots and axes straight into the Lua, so this is
    a transcription check on the SHIPPED artifact rather than on the
    generator's intent.
    """

    source = emitted_runtime()
    assert parse_vec3(source, "WRIST_POINT") == pytest.approx(spec.WRIST_POINT, abs=1e-5)
    assert parse_vec3(source, "FOREARM_AXIS") == pytest.approx(spec.U_REST, abs=1e-5)
    for name in spec.DIGIT_ORDER:
        # Each digit appears once in DIGIT_AXES and once in DIGIT_PIVOTS; the
        # tables are emitted in that order, so search the blocks separately.
        axes_block = source[source.index("local DIGIT_AXES") : source.index("local DIGIT_PIVOTS")]
        pivots_block = source[
            source.index("local DIGIT_PIVOTS") : source.index("local TWITCH_PHASE")
        ]
        assert parse_vec3(axes_block, name) == pytest.approx(spec.DIGIT_AXES[name], abs=1e-5)
        assert parse_vec3(pivots_block, name) == pytest.approx(spec.DIGIT_PIVOTS[name], abs=1e-5)


def test_generated_lua_azimuths_match_the_spec():
    source = emitted_runtime()
    for name, value in (
        ("REST_DEG", spec.REST_DEG),
        ("WINDUP_DEG", spec.WINDUP_DEG),
        ("CONTACT_DEG", spec.CONTACT_DEG),
        ("FOLLOW_DEG", spec.FOLLOW_DEG),
        # WRIST_Z is deliberately NOT here: it was emitted into the runtime
        # and read by nothing, so it was removed from the constants block.
    ):
        match = re.search(rf"^local {name} = ([-\d.]+)$", source, re.M)
        assert match, name
        assert float(match.group(1)) == pytest.approx(value, abs=1e-4), name


def test_swing_sweeps_away_from_the_mast_furniture():
    """Ladder, guy anchors and their chains live in the sector the arm never
    reaches, and the bollards live outside the swept circle entirely.

    Both are safety claims made in spec.py comments; this is the assertion
    behind them.
    """

    swept = (min(spec.REST_DEG, spec.WINDUP_DEG), max(spec.FOLLOW_DEG, spec.REST_DEG))
    for azimuth in (180.0, 180.0 - 38.0, 180.0 + 38.0):
        folded = (azimuth + 180.0) % 360.0 - 180.0
        assert not (swept[0] <= folded <= swept[1]), (
            f"fixed furniture at azimuth {azimuth} sits inside the swept sector {swept}"
        )
    tip_radius = spec.WRIST_R + spec.HAND_LENGTH
    for y in spec.BOLLARD_Y:
        radius = math.hypot(spec.BOLLARD_X - spec.MAST_X, y - spec.MAST_Y)
        assert radius > tip_radius, (
            f"bollard at y={y} sits {radius:.1f} m out, inside the {tip_radius:.1f} m "
            "fingertip circle"
        )


def test_console_is_clear_of_everything_that_moves():
    """The cabinet must be inside the wrist collar's sweep circle (so the
    HAND never passes over the player) and under the forearm (which does).
    """

    radius = math.hypot(spec.CONSOLE_CX - spec.MAST_X, spec.CONSOLE_CY - spec.MAST_Y)
    # Half the cabinet's diagonal, so a corner counts.
    corner = math.hypot(spec.CASE_W / 2.0, spec.CASE_D / 2.0)
    collar_inner = spec.WRIST_R - (1.35 + spec.COLLAR_LENGTH / 2.0)
    assert radius + corner < collar_inner, (
        f"console reaches {radius + corner:.2f} m from the mast; the collar sweeps "
        f"inward to {collar_inner:.2f} m"
    )
    # Forearm height directly above the cabinet.
    along = (radius - spec.ELBOW_R) / (spec.WRIST_R - spec.ELBOW_R)
    boom_z = spec.ELBOW_Z + (spec.WRIST_Z - spec.ELBOW_Z) * along
    clearance = boom_z - spec.BOOM_TIP_DEPTH / 2.0 - (spec.CASE_Z1 + spec.CAP_T)
    assert clearance > 0.5, f"forearm clears the console cap by only {clearance:.2f} m"


def test_the_lead_and_the_swing_are_the_same_number():
    """The release fires when the subject is ``swing_lead_seconds`` from the
    strike plane, and the palm arrives ``slap_seconds`` after the release.
    They are one quantity wearing two names.

    Tuning either alone mis-aims the machine by the difference times the
    closing speed — 0.10 s at 40 m/s is 4 m, more than half the strike
    zone — and nothing else in the build would notice.
    """

    behavior = spec.BEHAVIOR
    assert behavior["swing_lead_seconds"] == pytest.approx(behavior["slap_seconds"])


def test_the_tilt_ladder_is_centred_and_its_scale_is_honest():
    """Seven segments at a fixed pitch, and a printed maximum that matches
    what the machine can actually do."""

    behavior = spec.BEHAVIOR
    span = (behavior["tilt_levels"] - 1) * spec.TILT_SEG_PITCH
    centre = spec.TILT_SEG_DX0 + span / 2.0
    assert centre == pytest.approx(0.0, abs=1e-6), (
        f"tilt ladder centre is {centre:+.3f} m off the panel axis"
    )
    power_span = (behavior["power_levels"] - 1) * spec.POWER_SEG_PITCH
    assert spec.POWER_SEG_DX0 + power_span / 2.0 == pytest.approx(0.0, abs=1e-6)

    top = (behavior["tilt_levels"] - 1) * behavior["tilt_step_deg"]
    printed = {label[2] for label in spec.PANEL_LEGEND_LABELS}
    assert f"{top:g}" in printed, (
        f"the panel prints {sorted(printed)} but the top detent is {top:g} deg"
    )
    # And every legend label must sit within the plate it is printed on.
    for u, v, text, _scale in spec.PANEL_LEGEND_LABELS:
        assert 0.0 <= u <= 1.0, (text, u)
        assert 0.0 <= v <= 1.0, (text, v)


def test_the_strike_zone_matches_where_the_hand_actually_is():
    """At contact the hand spans from the wrist to the fingertips in +x, and
    the box must be that, not a box centred on the origin.

    Centred on the origin it launched cars 4.5 m to the MAST side with
    nothing over them but the forearm passing 3.4 m up, and failed to
    launch a car at +6.2 m that the fingertips demonstrably swept.
    """

    zone = spec.TRIGGERS["slap_zone"]
    low = zone["center"][0] - zone["dimensions"][0] / 2.0
    high = zone["center"][0] + zone["dimensions"][0] / 2.0
    wrist_x = spec.MAST_X + spec.WRIST_R
    tip_x = spec.MAST_X + spec.WRIST_R + spec.HAND_LENGTH
    assert low >= wrist_x - 0.6, (
        f"the box reaches x={low:.1f} but the hand starts at the wrist, x={wrist_x:.1f}"
    )
    assert high >= tip_x - 1.0, (
        f"the box stops at x={high:.1f} while the fingertips sweep to x={tip_x:.1f}"
    )


def test_the_approach_corridor_does_not_arm_the_console_apron():
    """A player parked where they can read the panel must not be inside the
    trap. Measured before the fix: five launches in forty seconds, forever.
    """

    corridor = spec.TRIGGERS["approach"]
    near_edge = corridor["center"][1] + corridor["dimensions"][1] / 2.0
    assert near_edge < spec.CONSOLE_CY - 6.0, (
        f"the corridor reaches y={near_edge:.1f} and the console is at "
        f"y={spec.CONSOLE_CY:.1f}; anyone reading the panel is in the trap"
    )
    # And it still has to be long enough for the machine to wind up.
    behavior = spec.BEHAVIOR
    needed = behavior["alert_seconds"] + behavior["windup_seconds"] + behavior["swing_lead_seconds"]
    fastest = 60.0
    assert corridor["dimensions"][1] >= needed * fastest, (
        f"{corridor['dimensions'][1]:.0f} m of corridor is under the "
        f"{needed * fastest:.0f} m a {fastest:.0f} m/s car needs to be seen in"
    )


def test_the_hero_colour_survives_the_srgb_round_trip():
    """The foam's authored linear base must ENCODE back to the swatch it was
    sampled from.

    ``"srgb": True`` means the palette holds LINEAR values and build_set
    encodes them on the way out. The sRGB migration ran a blanket decode
    over the whole palette and caught this entry, which had already been
    authored linear — and decoding a linear value a second time is not a
    no-op. It took the rendered albedo from a dusty khaki to caramel: 2.86x
    too dark, 2.7x too saturated, and invisible in a diff because all six
    components moved together and every render still looked like a hand.

    "Sampled off the reference frames" is a checkable claim, so it is
    checked.
    """

    def encode(value):
        if value <= 0.0031308:
            return value * 12.92
        return 1.055 * value ** (1.0 / 2.4) - 0.055

    entry = spec.PALETTE[f"{spec.MOD_ID}_foam_latex"]["texture"]
    assert entry.get("srgb") is True, "the hero material must be sRGB-encoded"
    # THE ALBEDO, not the highlight. (190, 168, 118) was sampled off the lit
    # side of the reference hand and sits at the 99.5th percentile of that
    # hand's own pixels; normalising against the white fridge in the same
    # frame puts the palm's true albedo here. Saturation is
    # exposure-invariant, and the rendered palm was measuring 0.22 against
    # the reference's 0.48-0.55 while this gate happily passed.
    sampled = (146, 120, 66)
    for component, expected, channel in zip(entry["params"]["base"], sampled, "RGB", strict=False):
        byte = encode(component) * 255.0
        assert byte == pytest.approx(expected, abs=4.0), (
            f"foam_latex base {channel} encodes to {byte:.0f}, not the sampled {expected}"
        )
    # And the material's own colour field must agree with the map it wears.
    assert spec.PALETTE[f"{spec.MOD_ID}_foam_latex"]["color"][:3] == pytest.approx(
        entry["params"]["base"], abs=1e-6
    )


def test_the_generated_map_keeps_the_colour_the_base_promises():
    """ASSERT ON THE TEXTURE, NOT ON THE CONSTANT THAT SEEDS IT.

    The gate above passed while the rendered hand carried HALF the authored
    chroma: the base encoded to (190, 168, 118) with R-B = 72, and the
    surface came out at R-B = 36, because mottle and dust are both
    near-neutral lifters and between them they washed the tile. A gate
    pointed at an input cannot see what the function does to it — the same
    lesson as the clearance sweep, which only found the pinky in the road
    once it stopped asserting on WRIST_Z's own derivation and started
    sampling the parts.

    So this generates the actual map and measures it. 512 rather than the
    shipped 2048 purely for speed; the statistics this asserts on are
    resolution-independent.
    """

    import sys

    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    import numpy
    from proplib import texture_kit

    entry = spec.PALETTE[f"{spec.MOD_ID}_foam_latex"]["texture"]
    colour, _height, _rough, _opacity = texture_kit.FAMILIES["foam_latex"](
        512, texture_kit._rng("gate"), **entry["params"]
    )
    encoded = texture_kit._srgb_encode(numpy.clip(colour, 0.0, 1.0)) * 255.0
    mean = encoded.reshape(-1, 3).mean(axis=0)
    warmth = float(mean[0] - mean[2])
    assert warmth >= 60.0, (
        f"the generated map is R-B {warmth:.0f}; the authored albedo is 80. "
        "Something in the tile is washing it — mottle and dust are both "
        "near-neutral, so they are the usual culprits"
    )
    # And it must not drift far from the swatch in overall level either.
    for value, expected, channel in zip(mean, (146, 120, 66), "RGB", strict=False):
        assert value == pytest.approx(expected, abs=34.0), (
            f"generated map mean {channel} is {value:.0f} against a sampled {expected}"
        )


def test_every_generated_palette_entry_is_srgb_encoded():
    """Mixed encoding across one prop is worse than either convention.

    Every generated family in this palette writes a colour map, the engine
    reads all of them as sRGB, and colossus_tire — the pack's other new mod
    — opts in on all of its entries. An entry that opts out silently ships
    up to 9x too dark.
    """

    for name, entry in spec.PALETTE.items():
        texture = entry.get("texture")
        if not texture or texture.get("family") == "external":
            continue
        assert texture.get("srgb") is True, f"{name} is not sRGB-encoded"


def test_the_palm_never_emerges_between_the_knuckles():
    """The web is a raw intersection between independent shells, so the
    palm must stay INSIDE the knuckle envelope by construction.

    The palm, five digits and five nails are eleven separate closed shells
    that interpenetrate — deliberately, because the concentric-ball joint
    is what lets the digits animate. That is correct at the joint, where
    the ball is static under rotation. It is NOT automatically correct at
    the WEB, where the visible edge is an uncontrolled intersection curve;
    and two rounds of tuning the web amplitude to hide it made it worse,
    because pushing the palm forward to fill the gap exposes the palm.

    `PalmSurface.point` now clamps the web bulge to the distal reach of
    whichever metacarpal head covers the point. This asserts the property
    that clamp exists to guarantee, sampled on the surface rather than
    inferred from the constants.
    """

    import sys

    if str(PACK_ROOT / MOD_KEY / "blender") not in sys.path:
        sys.path.insert(0, str(PACK_ROOT / MOD_KEY / "blender"))
    import hand_sculpt

    surface = hand_sculpt.PalmSurface(spec)

    # EVERY digit root must have a covering ball, or the clamp silently has
    # no ceiling there and this whole gate degrades to checking the dome
    # against itself. The thumb was missing from both the envelope and the
    # web list for a full round precisely because both were built from
    # FINGER_ORDER, and the earlier version of this test could not see it:
    # where ball_limit is -inf the ceiling fell back to the dome's own
    # reach, so the assertion was vacuous across the entire radial side.
    # EVERY BALL USED AS A CAP CONSTRAINT MUST BE ABLE TO REACH THE CAP.
    #
    # This is the assertion that would have caught the round-5 mistake in
    # one line. The thumb's metacarpal head was added to this list on the
    # reasoning that the first web space needed a covering ball like the
    # other three — but it tops out at u = 2.99 against a cap starting at
    # 3.84, so it could never certify a cap point: `ball_limit` stayed -inf
    # across the whole radial side, the clamp forced the fold to zero, and
    # the list-length check that was here passed happily on an inert fifth
    # entry. A membership test cannot see a geometric no-op.
    for du, _dv, _dn, radius in surface.balls:
        assert du + radius >= surface.u_knuckle, (
            f"a cap ball reaching only u={du + radius:.2f} is inert against a "
            f"cap starting at {surface.u_knuckle:.2f}"
        )
    assert len(surface.balls) == len(spec.FINGER_ORDER), (
        "the cap envelope is the FINGERS; the thumb cannot reach it"
    )
    assert len(surface.web_mid) == len(spec.FINGER_ORDER) - 1
    # And the thumb head must indeed be the one that cannot, so that if the
    # anatomy ever changes enough for it to reach, this stops being true and
    # somebody re-reads the argument above.
    thumb_u, _tv, _tn, thumb_r = surface.thumb_head
    assert thumb_u + thumb_r < surface.u_knuckle

    worst = None
    uncovered = None
    dome = surface.u_knuckle + surface.cap_length
    for station in range(60):
        s = 0.75 + 0.25 * station / 59.0  # the cap region only
        for column in range(96):
            theta = 2.0 * math.pi * column / 96.0
            point = surface.point(s, theta)
            u, n, v = point[0], point[1], point[2]
            if u <= surface.u_knuckle + 1e-6:
                continue
            limit = surface.ball_limit(v, n)
            if limit <= -1e8:
                # Nothing covers this point, so the palm may not push past
                # the plain dome at all — the fallback the old version got
                # wrong by allowing exactly that.
                excess = u - dome
                if uncovered is None or excess > uncovered[0]:
                    uncovered = (excess, round(s, 3), round(math.degrees(theta)))
                continue
            excess = u - max(limit, dome)
            if worst is None or excess > worst[0]:
                worst = (excess, round(s, 3), round(math.degrees(theta)))
    assert worst is not None
    assert worst[0] <= 0.02, (
        f"the palm reaches {worst[0]:.3f} m past the knuckle envelope at "
        f"s={worst[1]}, theta={worst[2]} deg — it is showing between the "
        "fingers"
    )
    if uncovered is not None:
        assert uncovered[0] <= 0.02, (
            f"where no knuckle covers it the palm still bulges "
            f"{uncovered[0]:.3f} m past the dome at s={uncovered[1]}, "
            f"theta={uncovered[2]} deg"
        )


def test_the_cuff_moves_with_the_hand_it_holds():
    """The roll compensation drops the hand; the collar must go with it.

    ``poseArm`` lowers the hand and every digit by
    ``ROLL_DROP * (1 - cos tilt)`` — up to 0.374 m at the top detent — so
    the palm stays on a car's flank. The collar that swallows the foam
    stump used to be part of the ARM, which does not move: that is a rigid
    0.374 m displacement across a joint with COLLAR_CLEARANCE = 0.17 m of
    bore, i.e. the stump comes out through the cuff wall. spec.py already
    records that a ~0.35 m error at this exact joint was visible once
    before, which is why COLLAR_R went 1.02 -> 1.62.

    So the cuff is its own part on the same pivot, taking the same drop and
    the same swing but NOT the roll. This asserts the shipped runtime
    actually does that, because the failure is invisible at tilt 0 — which
    is every render anyone looks at.
    """

    source = emitted_runtime()
    assert 'setPartPose(\n    state, "wrist",' in source or '"wrist",' in source, (
        "the cuff is not posed at all"
    )
    # The drop must be the SAME expression for the hand, the digits and the
    # cuff. Three copies of a number is how they drift apart.
    assert source.count("ROLL_DROP * (1 - math.cos(roll))") >= 3, (
        "hand, digits and cuff do not all take ROLL_DROP"
    )
    # And the cuff must not take the roll itself, or it would counter-rotate
    # against the hand turning inside it.
    wrist_call = source[source.index('state, "wrist"') :]
    wrist_call = wrist_call[: wrist_call.index(")\n") + 1]
    assert "rollQ" not in wrist_call, (
        "the cuff is being rolled; it is the housing the hand turns INSIDE"
    )
    assert "swingQ" in wrist_call, "the cuff does not follow the arm's swing"


def test_digit_tips_converge_on_a_point():
    """Every column of a digit's tip dome must land on ONE point.

    The dome's reach is deliberately asymmetric — it goes further on the
    volar (pulp) side than over the nail — and the first version applied
    that asymmetry as ``direction * sin(angle) * reach(theta)``. At the
    pole the ring collapses, so every column landed on
    ``position + direction * reach(theta)``, and reach depended on theta:
    the pole was not a point, it was a SEGMENT 0.30 * radius0 long. 159 mm
    on the index, 192 mm on the thumb, and every digit ended in a flat
    triangular beak on its volar side.

    Multiplying the asymmetry by sin*cos makes it vanish at both ends. This
    is the same trick the palm's distal cap documents at length, and the
    same failure it had first — which is exactly why it is worth a gate on
    both rather than a comment on one.
    """

    import sys

    for path in (PACK_ROOT / MOD_KEY / "blender", PACK_ROOT / MOD_KEY):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import hand_sculpt

    for name, surface in hand_sculpt.digit_surfaces(spec).items():
        pole = [surface.point(1.0, 2.0 * math.pi * k / 24.0) for k in range(24)]
        spread = max(math.dist(tuple(a), tuple(b)) for a in pole for b in pole)
        assert spread < 0.001, (
            f"{name}'s tip pole spans {spread * 1000:.0f} mm instead of "
            "converging — the dome's asymmetry is not vanishing at the pole"
        )


def test_the_hand_maths_imports_without_blender():
    """A guard on the guard.

    Every one of this module's shipped defects — the folded cross-sections,
    the segment poles, the palm emerging between the knuckles — was a
    property of the analytic functions and not of the mesh assembly, and
    every one was found by eye on a render because nothing could import the
    code to check it. The bpy/mathutils imports are now optional. If that
    ever regresses, three gates in this file go quiet at once, so it is
    asserted directly rather than left to a skip.
    """

    import sys

    for path in (PACK_ROOT / MOD_KEY / "blender", PACK_ROOT / MOD_KEY):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import hand_sculpt

    assert hand_sculpt.PalmSurface(spec).cap_length > 0.0
    assert len(hand_sculpt.digit_surfaces(spec)) == len(spec.DIGIT_ORDER)


def test_the_thumb_web_is_a_fold_and_not_a_gap():
    """A LOWER bound, which is the shape of assertion this file was missing.

    Every check written before this one is an upper bound — the palm must
    not exceed the envelope, must not exceed the dome, the list must have
    the right length. The first web space failed a lower bound: there was
    no fold where there should have been one, for three rounds, and an
    upper-bound assertion structurally cannot see a missing feature.

    The thumb-index web lives on the palm's radial FLANK, around u 2.2-3.4,
    not in the distal cap — the thumb metacarpal sits 0.85 m proximal of
    where the cap begins. So the test is: does the palm's flank actually
    reach out and overlap the thumb's own metacarpal ball? If the two shells
    merely graze, the intersection is near-tangent and renders as a thin
    hard-edged sliver, which is exactly what it did.
    """

    import sys

    for path in (PACK_ROOT / MOD_KEY / "blender", PACK_ROOT / MOD_KEY):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import hand_sculpt

    surface = hand_sculpt.PalmSurface(spec)
    thumb_u, thumb_v, thumb_n, thumb_r = surface.thumb_head
    closest = None
    for step in range(61):
        theta = math.radians(-30.0 + step * 2.0)
        for offset in range(31):
            u = thumb_u - 1.5 + offset * 0.1
            a, b = surface.radius(u, theta)
            gap = math.sqrt((thumb_v - a) ** 2 + (thumb_n - b) ** 2 + (thumb_u - u) ** 2) - thumb_r
            if closest is None or gap < closest:
                closest = gap
    # -0.15, not -0.05. A bound that merely forbids a GAP is satisfied by
    # two shells that touch, and two shells that touch cross at a shallow
    # angle and leave a hard-edged tab — which is the same defect the gap
    # produced, in a different disguise. The fold has to be BURIED. At
    # -0.15 the crossing is 35 degrees; the shipped 0.75 amplitude lands
    # at -0.247 and 46 degrees, so this holds a real margin rather than
    # being drawn tight around the current value.
    assert closest < -0.15, (
        f"the palm's flank comes within {closest:+.3f} m of the thumb's "
        "metacarpal ball — the two shells graze rather than merge, and a "
        "near-tangent intersection is a hard-edged sliver"
    )
    # But not so far that the palm swallows the thumb whole.
    assert closest > -0.60, (
        f"the flank penetrates the thumb ball by {-closest:.2f} m; the thenar "
        "belongs to the THUMB part, and the palm is eating it"
    )


def test_the_parting_seam_is_a_fin_and_not_a_hill():
    """THE WHOLE LENGTH, in true 3-D, on every part and both meridians.

    The seam existed in the vertices for four rounds and no reviewer could
    find it, because two things each cancelled it: `_bump`'s `width` is a
    Gaussian SIGMA, so the authored 8 degrees was really +/-24 (50 of the
    palm's 192 columns, a 1.75 m arc under a 0.067 m rise — a hill), and
    `_grid_to_object` smooth-shaded across it anyway.

    The FIRST version of this gate then sampled exactly one station, u =
    1.30, which reads 41.8 degrees. A reviewer measuring the full meridian
    found the palm's radial crest dipping to 29.4 over 34 contiguous
    stations, and a one-sample gate cannot see a stretch. Same shape of
    mistake as the fold gate that covered only the palm, three tests down.
    It also reconstructed the section as `hypot(a, b)` at polar angle
    theta, which is not the surface the generator builds; this takes the
    dihedral off `point()` itself.

    THE BOUND IS 25, AND IT IS NOT 38 WIDENED. 38 was the auto-smooth
    angle, and it was the right threshold while shading depended on an
    angle test. It does not any more: the crest is marked sharp
    explicitly, so it shades crisply at any dihedral. What the number has
    to do now is only prove a RIDGE exists under the mark — mark a swell
    and you draw a crease across smooth skin with nothing beneath it.

    Measured today the minimum is 29.4 degrees, on the palm's radial
    meridian over stations 104-137, where the thumb-web term inflates the
    flank by about 55%%. That is honest geometry rather than a defect: a
    fin of constant height sitting on a locally flatter section IS a
    shallower crease, on a real casting too. The median across all 1,820
    samples is 47.9-80.9 by part, which the second assertion holds, so a
    global collapse cannot hide behind one soft stretch.
    """

    import sys

    for path in (PACK_ROOT / MOD_KEY / "blender", PACK_ROOT / MOD_KEY):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import hand_sculpt

    palm = hand_sculpt.PalmSurface(spec)
    # `section` gives the part's own half-extents on the crest meridian.
    # It cannot be read off point(), because a digit's point() carries the
    # digit's offset in the hand and hypot() of that is not a radius.
    parts = [
        ("palm", palm.point, palm.seam_divisions, 224, 20, 190, lambda: palm.radius(1.30, 0.0))
    ]
    for name, digit in hand_sculpt.digit_surfaces(spec).items():
        parts.append(
            (
                name,
                digit.point,
                digit.seam_divisions,
                176,
                14,
                162,
                (lambda d: lambda: d.profile(0.5, 0.0))(digit),
            )
        )

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    def unit(a):
        size = math.sqrt(sum(c * c for c in a))
        return None if size < 1e-12 else tuple(c / size for c in a)

    FIN_DEG = 25.0
    height = spec._mm(spec.FLASH_PROUD_MM)
    assert 0.04 <= height <= 0.14, (
        f"the flash stands {height:.3f} m proud; a dressed parting line on "
        "a 44x casting is a few centimetres, not a moulding strip"
    )

    for name, sampler, divisions, stations, low, high, section in parts:

        def at(station, column, _s=sampler, _d=divisions, _n=stations):
            p = _s(station / _n, 2.0 * math.pi * (column % _d) / _d)
            return (p[0], p[1], p[2])

        for crest, meridian in ((0, "radial"), (divisions // 2, "ulnar")):
            angles = []
            for station in range(low, high):
                here = at(station, crest)
                before = at(station, crest - 1)
                after = at(station, crest + 1)
                first = unit(cross(sub(here, before), sub(at(station + 1, crest - 1), before)))
                second = unit(cross(sub(after, here), sub(at(station + 1, crest), here)))
                if not first or not second:
                    continue
                dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(first, second, strict=False))))
                angles.append(math.degrees(math.acos(dot)))

            assert angles, f"{name}/{meridian}: no crest samples"
            weakest = min(angles)
            strongest = max(angles)
            middle = sorted(angles)[len(angles) // 2]
            assert weakest > FIN_DEG, (
                f"{name}/{meridian}: the parting seam falls to {weakest:.1f} "
                f"deg somewhere along its length, under {FIN_DEG:.0f} — that "
                "is a swell, and the sharp edge marked along its crest would "
                "be a crease drawn across smooth skin with no ridge under it"
            )
            assert strongest < 150.0, (
                f"{name}/{meridian}: the seam breaks {strongest:.1f} deg "
                "somewhere along its length — that is a spike, not a "
                "dressed flash line, and the fold gate steps aside for "
                "these columns on the understanding that this one bounds "
                "them. The previous version measured a max at ONE station "
                "and never reached the cap, which is how a 164.5 degree "
                "break shipped: a bead held at full height into a "
                "collapsing ring leaves a segment where the pole should be"
            )
            assert middle > 40.0, (
                f"{name}/{meridian}: the seam's MEDIAN crest is only "
                f"{middle:.1f} deg. The minimum can dip where the form "
                "bulges, but a low median means the bead is weak "
                "everywhere, which is the hill this gate is named for"
            )

        # THE BEAD MUST NOT THIN INTO THE CAP. It was folded into the
        # section's half-extents and then scaled by the dome's `shrink`,
        # so it faded toward the pole — the crest fell to 26.8 degrees over
        # stations 178-189 while the rest of the meridian held 48. A mould
        # gap is a constant and the fin it leaves is one height wherever
        # the parting plane cuts, and the one place it must not thin is
        # where the form rolls away and the line is all you can see of the
        # edge. Asserted as its own property because the dihedral bound
        # above cannot catch it without being drawn tight around today's
        # numbers: the defect measured 26.8 against a shipped 29.4.
        if name == "palm":
            # THE CAP BODY, deliberately stopping short of the pole. The
            # bead is held at the mould gap's height through the cap and
            # then tapered over the last 8% of it, because a bead that does
            # NOT collapse when the ring does leaves a segment instead of a
            # point. So this window must not include the taper, or it would
            # forbid the very thing that keeps the pole a pole.
            beads = []
            for station in range(int(0.78 * stations), int(0.94 * stations)):
                lit = sampler(station / stations, 0.0)
                bare = sampler(station / stations, 0.0, with_flash=False)
                beads.append(
                    math.sqrt(
                        sum(
                            (x - y) ** 2
                            for x, y in zip(
                                (lit[0], lit[1], lit[2]), (bare[0], bare[1], bare[2]), strict=False
                            )
                        )
                    )
                )
            spread = (max(beads) - min(beads)) / max(beads)
            assert spread < 0.02, (
                f"the seam's bead varies {100 * spread:.1f}% across the "
                "distal cap — it is being scaled by the dome instead of "
                "held at the height the mould gap sets"
            )
            assert min(beads) > 0.5 * height, (
                f"the bead is down to {min(beads):.3f} m in the cap against a full {height:.3f} m"
            )
            # AND THE POLE IS STILL A POINT. `test_digit_tips_converge_on_
            # a_point` asserts this for the five digits and nothing
            # asserted it for the palm — so holding the bead at full height
            # to fix the cap's dihedral quietly opened the palm's pole to a
            # 0.126 m segment, with seam facets at 155-165 degrees over the
            # last six stations, and all 74 gates still passed. The defect
            # DigitSurface.point describes at length, reproduced on the one
            # part its own test does not cover.
            pole = [sampler(1.0, 2.0 * math.pi * column / divisions) for column in range(divisions)]
            for axis in (1, 2):
                spread = max(p[axis] for p in pole) - min(p[axis] for p in pole)
                assert spread < 1e-6, (
                    f"the palm's cap ends on a segment {spread:.4f} m long "
                    "rather than a point — a closed cap converges, and a "
                    "bead that keeps its height while the ring collapses "
                    "is what stops it"
                )

        # ...and the WIDTH, in metres of prop.
        sigma = math.radians(spec.FLASH_WIDTH_COLUMNS * 360.0 / divisions)
        fwhm = 2.0 * sigma * math.sqrt(math.log(2.0)) * math.hypot(*section())
        assert 0.03 <= fwhm <= 0.25, (
            f"{name}: the seam measures {fwhm:.3f} m across on the prop — "
            "outside the range a dressed flash line occupies, so it reads "
            "as either a scratch or a moulding strip"
        )


def test_the_parting_seam_is_creased_by_marking_and_not_by_angle():
    """The seam is a KNOWN column, so it is marked, not discovered.

    Both halves of this matter, and the first one is why the second is
    written the way it is.

    hand_sculpt originally called a bare `shade_smooth()`, which was
    wrong — but the obvious repair, `shade_auto_smooth(38 degrees)` like
    `add_loft`, was wrong in a more expensive way. An angle test has to
    DISCOVER which edges are sharp, and on this mesh the input to that
    test is undefined: the cap is a single-pole dome over a 3.2:1 section,
    and in one patch of the radial-volar quadrant the two parameter
    directions run within 1.6 degrees of each other. Those quads are
    slivers, their face normals are numerical noise, and the angle test
    duly split them into a blocky staircase across the thenar.

    So the parting line is marked explicitly along its own column and
    everything else is smooth. This asserts that the marking happens and
    is not silently skipped — `bm.edges.get` returning None for every
    edge would leave the hand smooth with no seam and no error.
    """

    sculpt = (PACK_ROOT / MOD_KEY / "blender" / "hand_sculpt.py").read_text(encoding="utf-8")
    # Scoped to _grid_to_object, which builds the palm and the digits.
    # build_nail may use the angle test and does: a nail plate is a small
    # well-conditioned grid whose rim is a real geometric edge.
    body = sculpt[sculpt.index("def _grid_to_object(") :]
    body = body[: body.index(chr(10) + "def ", 1)]
    assert "bpy.ops.object.shade_auto_smooth(" not in body, (
        "the palm and digits must not use an angle test — their cap carries "
        "sliver quads whose face normals are undefined, and an angle test "
        "fed undefined normals invents edges"
    )
    assert "bpy.ops.object.shade_smooth()" in body
    assert sculpt.count("sharp_columns=(0, divisions // 2, divisions)") == 2, (
        "both the palm and the digits must mark their two mould meridians"
    )
    assert "edge.smooth = False" in sculpt


def test_no_part_of_the_hand_carries_folded_quads():
    """THE PALM AND THE DIGITS. The first version sampled only the palm.

    That is how the worst fold in the mod survived this file: every digit
    stepped 65-123 mm BACKWARD at both interphalangeal joints, against a
    station pitch of 21-33 mm, with facet normals 179.9 degrees apart —
    the strip passing through itself, on five parts, at ten joints — and
    the gate written specifically to catch folds could not see it, because
    it only ever constructed a PalmSurface. A reviewer found it in a
    render.

    The mechanism was worth the lesson too. `DigitSurface` emitted the last
    spine sample of one phalanx and the first of the next at the SAME arc
    length, so `frame()`'s span was zero and its lerp returned the upstream
    direction unchanged: the section frame rotated by the whole flexion
    angle between two adjacent stations.

    Four constructs were each folding this hand and every one was hidden by
    the same `shade_smooth()` call:

      * the digit spine, above;
      * `ball_limit` returning -inf where no metacarpal head covered the
        point, so the palm's web bulge switched off for a single station
        and back on — a one-row crater 0.26 m deep;
      * the clamp that used it, which made the SURFACE track a level set of
        that function; the level set does not follow the grid, so the volar
        cap came out a ragged staircase with facets 177 degrees apart;
      * the palmar creases, narrowed to 0.115 m wide against 0.221 m deep
        to make them "cast a shadow line", which inverted outright.

    None is visible to an assertion on the constants that produce them.
    """

    import sys

    for path in (PACK_ROOT / MOD_KEY / "blender", PACK_ROOT / MOD_KEY):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import hand_sculpt

    palm = hand_sculpt.PalmSurface(spec)
    parts = [("palm", palm.point, palm.seam_divisions, 224, 215)]
    for name, digit in hand_sculpt.digit_surfaces(spec).items():
        parts.append((name, digit.point, digit.seam_divisions, 176, 170))

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    def length(a):
        return math.sqrt(sum(c * c for c in a))

    def apart(first, second):
        if not first or not second:
            return 0.0
        dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(first, second, strict=False))))
        return math.degrees(math.acos(dot))

    # A quad whose two parameter directions are nearly collinear has no
    # meaningful normal: the cross product is a difference of two nearly
    # equal products, so its SIGN is noise. Comparing those measures the
    # arithmetic, not the surface. A reviewer reported a 179.6 degree
    # "fold" on the palm cap at station 207 which is a 4.1 degree dihedral
    # once measured on a well-formed quad — the flip was the sign of a
    # cross product 15 degrees from degenerate. So slivers are counted
    # separately and bounded, rather than folded into the same threshold
    # until it is too wide to catch anything real.
    DEGENERATE_DEG = 20.0

    failures = []
    sliver_counts = {}
    for name, sampler, divisions, stations, ceiling in parts:

        def point(station, column, _s=sampler, _d=divisions, _n=stations):
            p = _s(station / _n, 2.0 * math.pi * (column % _d) / _d)
            return (p[0], p[1], p[2])

        def tangents(station, column):
            here = point(station, column)
            return (sub(point(station, column + 1), here), sub(point(station + 1, column), here))

        def separation(station, column):
            across, along = tangents(station, column)
            if length(across) < 1e-12 or length(along) < 1e-12:
                return 0.0
            dot = sum(x * y for x, y in zip(across, along, strict=False)) / (
                length(across) * length(along)
            )
            return math.degrees(math.acos(max(-1.0, min(1.0, dot))))

        def face(station, column):
            across, along = tangents(station, column)
            normal = cross(across, along)
            size = length(normal)
            return None if size < 1e-12 else tuple(c / size for c in normal)

        def authored(column, divisions=divisions):
            """The two mould meridians are deliberate discontinuities.

            ``divisions`` is bound as a default (B023) so the closure holds
            this iteration's value structurally.
            """

            for crest in (0, divisions // 2):
                if min((column - crest) % divisions, (crest - column) % divisions) <= 1:
                    return True
            return False

        slivers = 0
        # BOTH directions. An earlier version compared only quads down a
        # column, and the crease inversions it exists to catch run ACROSS
        # them — so it passed on the exact defect it was written for.
        for column in range(divisions):
            if authored(column):
                # The seam crest reaches 120 degrees on the little finger,
                # which is a fin doing its job and not a fold. It has its
                # own gate, with its own bounds on both sides, so this one
                # stays narrow enough to keep 120 meaningful everywhere
                # else rather than being widened until it catches nothing.
                continue
            for station in range(1, ceiling):
                if separation(station, column) < DEGENERATE_DEG:
                    slivers += 1
                    continue
                here = face(station, column)
                for other in ((station - 1, column), (station, (column - 1) % divisions)):
                    if separation(*other) < DEGENERATE_DEG:
                        continue
                    if apart(face(*other), here) > 120.0:
                        failures.append((name, station, column))
        sliver_counts[name] = slivers

    assert not failures, (
        f"{len(failures)} pairs of adjacent well-formed quads have normals "
        f"more than 120 degrees apart — first on the {failures[0][0]} at "
        f"station {failures[0][1]}, column {failures[0][2]}. The surface is "
        "folded back on itself there."
    )
    # And the degeneracy is bounded, so the cap cannot quietly get worse.
    # The palm's sit in one patch of the radial-volar cap, where a
    # single-pole dome over a 3.2:1 section runs its two parameter
    # directions together; that patch is exactly why the hand is smooth
    # shaded with the seam marked by hand rather than discovered by angle.
    for name, count in sliver_counts.items():
        assert count <= 400, (
            f"{name}: {count} quads have parameter directions within "
            f"{DEGENERATE_DEG:.0f} degrees of collinear — their normals are "
            "noise, and any shading that reads face normals will show it"
        )


def test_the_nail_holds_its_ratio_to_the_foam():
    """THE SHIPPED MAPS, not the palette constants that produce them.

    The nail is authored relative to the skin, and the relation has been
    got wrong three times now. Twice the constant drifted because the foam
    moved and the nail did not follow. The third time was worse and is why
    this test reads PNGs: a reviewer measured the authored base at 0.90x
    the foam, against a comment claiming 1.21x and a reference measuring
    1.09, and the obvious repair was to re-author the base to 1.09x.

    That repair is wrong, and the first version of this test asserted it.
    `nail_keratin` LIFTS its base — plate sheen, lunula, striation — so a
    base at 0.90x lands the map at 1.18x and the rendered plate at 1.07x,
    which is exactly the reference. Moving the base to 1.09x took the map
    to 1.41x. Correcting an input to equal a figure that describes an
    output, and a gate pointed at the same input could not see it: it
    passed, on a 20% overshoot.

    So this measures the maps that actually ship.
    """

    import numpy as np
    from PIL import Image

    textures = PACK_ROOT / MOD_KEY / "textures"

    def linear_luminance(name):
        pixels = (
            np.asarray(Image.open(textures / f"{name}.color.png").convert("RGB"), dtype=float)
            / 255.0
        )
        linear = np.where(pixels <= 0.04045, pixels / 12.92, ((pixels + 0.055) / 1.055) ** 2.4)
        return float(
            (0.2126 * linear[..., 0] + 0.7152 * linear[..., 1] + 0.0722 * linear[..., 2]).mean()
        )

    foam = linear_luminance(f"{spec.MOD_ID}_foam_latex")
    nail = linear_luminance(f"{spec.MOD_ID}_nail")
    ratio = nail / foam
    assert 1.05 <= ratio <= 1.30, (
        f"the shipped nail map is {ratio:.3f}x the foam map's linear "
        "luminance; the reference hand renders at 1.09 and this band is "
        "what puts it there. Below it the nails vanish into the skin; "
        "above it they become the only thing legible on the prop at 100 m"
    )
    # The hue is authored, so it is checked where it is authored: a
    # fingernail is a desaturated PINK, and the drift that produced 3.2x
    # also produced B/G = 0.68.
    nail_base = spec.PALETTE[f"{spec.MOD_ID}_nail"]["texture"]["params"]["base"]
    assert nail_base[2] / nail_base[1] > 0.80, (
        f"the nail's B/G is {nail_base[2] / nail_base[1]:.2f} — that is a tan"
    )
    # The bed is the skin seen THROUGH the plate, so it tracks the foam
    # exactly rather than being a third constant that can drift apart.
    bed = spec.PALETTE[f"{spec.MOD_ID}_nail"]["texture"]["params"]["bed"]
    foam_base = spec.PALETTE[f"{spec.MOD_ID}_foam_latex"]["texture"]["params"]["base"]
    assert list(bed) == list(foam_base), (
        "the nail bed is the skin seen through keratin; it must be the "
        "foam's own base, or it becomes a third constant to keep in step"
    )


def test_the_castings_are_lighter_than_the_paint_bolted_to_them():
    """An ORDERING, which is why srgb could not fix it.

    The cast iron rendered 5.9x darker than the matte black enamel beside
    it. A note in spec.py spotted the inversion and prescribed `srgb:
    True` — but srgb scales both entries, and scaling both sides of a
    ratio leaves the ratio alone. It shipped inverted for two more rounds.

    Effective diffuse, not base colour: the iron carried metallic 0.7, so
    70% of its albedo was never diffuse at all, and no change to the base
    alone would have been legible against a dielectric.
    """

    def effective(entry):
        colour = entry["color"]
        luminance = 0.2126 * colour[0] + 0.7152 * colour[1] + 0.0722 * colour[2]
        return luminance * (1.0 - (entry.get("metallic") or 0.0))

    iron = effective(spec.PALETTE[f"{spec.MOD_ID}_cast_iron"])
    paint = effective(spec.PALETTE[f"{spec.MOD_ID}_rig_black"])
    assert 2.0 <= iron / paint <= 4.0, (
        f"the castings sit at {iron / paint:.2f}x the enamel's effective "
        "diffuse; foundry-skinned cast iron runs 2-4x above matte black, "
        "and below 1.0 the machine reads as painted castings on an iron "
        "frame, which is backwards"
    )


def test_the_rust_stays_legible_against_the_iron_it_stains():
    """Two more ratios in a shipped map, both of which broke silently.

    Lightening the castings 5.71x to get them above the enamel took the
    oxide with it — but only 2.49x, because it was scaled by eye. The
    stain landed at 0.985x the body's luminance: ISO-LUMINANT, the one
    value at which a stain cannot be seen, leaving it nothing but 19
    counts of chroma. Nothing failed. The rust was still there, still the
    right hue, still in the right places, and invisible.

    And the sand-cast grain went the same way for a different reason.
    `_colorize` is multiplicative, so the LINEAR contrast is identical at
    any base — but sRGB encoding is steep in the shadows and flat higher
    up, so the same grain that spanned a usable range on a near-black
    casting collapsed to 0.95% relative, under one code value of standard
    deviation. That is a banding map, and it is invisible to any
    assertion on the palette constants because none of them changed.

    Both are read off the PNG that ships, for the reason the nail gate
    above spells out.
    """

    import numpy as np
    from PIL import Image

    pixels = np.asarray(
        Image.open(PACK_ROOT / MOD_KEY / "textures" / f"{spec.MOD_ID}_cast_iron.color.png").convert(
            "RGB"
        ),
        dtype=float,
    )
    luma = 0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1] + 0.0722 * pixels[..., 2]

    # The oxide bloom is the reddest 1% of the map.
    chroma = pixels[..., 0] - pixels[..., 2]
    bloom = chroma >= np.percentile(chroma, 99)
    ratio = float(luma[bloom].mean() / luma.mean())
    assert 1.04 <= ratio <= 1.20, (
        f"the oxide sits at {ratio:.3f}x the casting's luminance; a rust "
        "bloom reads by being LIGHTER as well as redder, and at 1.0 it is "
        "iso-luminant with the iron and carries chroma alone"
    )
    assert float(chroma[bloom].mean()) > 25.0, (
        f"the oxide carries only {chroma[bloom].mean():.1f} counts of R-B"
    )

    relative = float(100.0 * luma.std() / luma.mean())
    assert relative > 1.4, (
        f"the casting's grain spans {relative:.2f}% relative contrast — "
        "under about one code value of standard deviation, which BC1 will "
        "flatten to a smooth grey. Lightening the base without raising "
        "`contrast` does exactly this, and changes no constant that any "
        "other assertion reads"
    )


def test_the_storefront_is_lit_like_the_evidence():
    """The one frame a player sees before downloading was the odd one out.

    Its foam measured saturation 0.329 against 0.407 on the reference and
    0.431-0.471 across all sixteen review frames — on the SAME scene, with
    the same materials. The studio stage adds fills on top of REVIEW_LIGHT,
    and fills are a neutral pedestal: two points fit `foam mean R = 136.6 +
    73.9 * fill` with the chroma invariant, which is the signature of a
    pedestal rather than a light. Saturation was falling purely because the
    denominator rose.

    This asserts the multiplier at the source, because the alternative is
    re-measuring a JPEG in a test, and the failure mode here is somebody
    adding a fill back rather than the number drifting.
    """

    generator = (PACK_ROOT / MOD_KEY / "blender" / f"create_{MOD_KEY}.py").read_text(
        encoding="utf-8"
    )
    assert "light.data.energy *= 0.05" in generator, (
        "the storefront's studio fills must stay at 0.05 or lower; at 0.22 "
        "the frame sat 9.5% below the saturation band every other render "
        "of the same scene is inside"
    )
