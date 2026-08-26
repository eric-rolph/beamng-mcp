"""Physics gates for The Giant Fan's rotor, joints and controls.

The pack-wide suite proves a prop is well FORMED. These prove this one is
well AIMED: that the rotator drives a group the cage actually has, that the
blades are their own body hanging off it, that the three joints each leave
exactly the degree of freedom they are supposed to, and that the two authored
ladders are reproduced by the numbers the machine will really run at.

Every failure mode here is silent in game. A rotator whose ``node1:`` does not
resolve is DELETED by the engine and the fan simply never turns; a blade
triangle that spans the rotor and the fixed base is a physics bomb; a tip
speed that does not match its own dial detent is a machine that lies about
itself.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import math
import sys
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "giant_fan"


def load_spec():
    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    path = PACK_ROOT / MOD_KEY / "spec.py"
    loader = importlib.util.spec_from_file_location("giant_fan_spec", path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


S = load_spec()


def load_jbeam() -> dict:
    path = PACK_ROOT / MOD_KEY / "mod" / "vehicles" / S.MOD_ID / f"{S.MOD_ID}.jbeam"
    if not path.is_file():
        pytest.skip("giant_fan is not built; run build.py giant_fan prop")
    return json.loads(path.read_text(encoding="utf-8"))[S.MOD_ID]


def node_table(part) -> dict[str, dict]:
    out = {}
    for row in part["nodes"][1:]:
        identifier, x, y, z, options = row
        out[identifier] = {"pos": (x, y, z), **options}
    return out


# ---------------------------------------------------------------------------
# The ladders. Authored as tip speeds and strike heights; everything else is
# derived, so these gates prove the derivation round-trips.
# ---------------------------------------------------------------------------
def test_the_dial_ratios_reproduce_the_authored_tip_speeds() -> None:
    for setting, (ratio, want) in enumerate(zip(S.DIAL_RATIO, S.TIP_MPS, strict=False)):
        got = ratio * S.MOTOR_MAX_AV / S.GEAR_RATIO * S.TIP_R
        assert got == pytest.approx(want, abs=1e-9), setting


def test_no_dial_setting_asks_for_more_than_the_motor_has() -> None:
    # A ratio over 1.0 is a setting the machine can never reach, and the
    # console would then print a number the blade never does.
    for setting, ratio in enumerate(S.DIAL_RATIO):
        assert 0.0 <= ratio <= 1.0, (setting, ratio)
    assert max(S.DIAL_RATIO) > 0.90, "the top setting should use the motor"


def test_the_dial_keeps_the_reference_detent_order() -> None:
    """0 - 3 - 2 - 1: the first click from OFF is FULL POWER.

    This is the real Lasko layout and it is the best joke on the machine, so
    it is pinned rather than left to drift into a tidy 0-1-2-3.
    """

    assert tuple(S.DIAL_ORDER) == (0, 3, 2, 1)


def test_the_tilt_ladder_reproduces_the_authored_strike_heights() -> None:
    """Solved against the blade's own corner cloud, not against the tip.

    The closed form TIP_R*(1 - cos t) + DISC_OFFSET_Y*sin t treats a 12 m
    twisted paddle as a point at its tip. It overstates the rise by 7% at the
    top rung, because the lowest corner of the section MIGRATES inboard as the
    head pitches. The authored heights are what the console announces, so the
    number the blade really does has to be the number that was solved.
    """

    for rung, (angle, want) in enumerate(zip(S.TILT_RAD, S.TILT_CLEAR_M, strict=False)):
        assert S.blade_clearance_at_pitch(angle) == pytest.approx(want, abs=1e-9), rung
    # And the tip-only closed form must NOT be what produced them.
    tip_only = (
        S.TIP_R * (1.0 - math.cos(S.TILT_RAD[-1]))
        + S.DISC_OFFSET_Y * math.sin(S.TILT_RAD[-1])
        + S.BLADE_BOTTOM_CLEAR
    )
    assert abs(tip_only - S.TILT_CLEAR_M[-1]) > 0.05, tip_only


def test_the_tilt_ladder_only_ever_raises_the_blade() -> None:
    # Every rung must be strictly higher than the last, or "HEIGHT +" is a lie.
    assert list(S.TILT_CLEAR_M) == sorted(S.TILT_CLEAR_M)
    assert S.TILT_CLEAR_M[0] == S.BLADE_BOTTOM_CLEAR
    assert len(S.TILT_CLEAR_M) == len(S.TILT_RUNG_NAME)


def test_the_tilt_hydro_input_spans_exactly_the_authored_rungs() -> None:
    """Every command is on the hydro's OUT side, and the top rung is its limit.

    hydros.lua builds `center` = 1 from the jbeam defaults and maps a command
    onto `1 + cmd * (outLimit - 1)`, so the ladder has to be normalised about
    the beam's own rest length. The bottom rung is NOT zero: the rest pose only
    sweeps 0.245 m over the deck (the blade's corner nodes reach 15.4946 m,
    past TIP_R) and it has its own droop to make up, so it commands a little
    nose-up like every other rung.
    """

    assert S.TILT_INPUT[0] > 0.0, S.TILT_INPUT[0]
    assert S.TILT_INPUT[-1] == pytest.approx(1.0, abs=1e-12)
    assert list(S.TILT_INPUT) == sorted(S.TILT_INPUT)
    assert all(0.0 <= value <= 1.0 for value in S.TILT_INPUT), S.TILT_INPUT


# ---------------------------------------------------------------------------
# Tunnelling and stability.
# ---------------------------------------------------------------------------
def test_the_blade_cannot_tunnel_at_the_top_setting() -> None:
    """BeamNG solves at 2000 Hz. A blade must not cross a car node in one step.

    This is the whole reason the rotor is a jbeam rotator rather than a
    graphics-rate mechanism: at 60 fps the same blade would move 1.13 m per
    step against a 0.62 m shell.
    """

    per_step = S.TIP_MPS[-1] / 2000.0
    assert per_step < 0.25 * S.BLADE_THICK, per_step
    graphics_rate = S.TIP_MPS[-1] / 60.0
    assert graphics_rate > S.BLADE_THICK, "a graphics-rate rotor WOULD tunnel"


def test_the_rotor_is_not_stopped_by_eating_one_car() -> None:
    energy = 0.5 * S.ROTOR_INERTIA * S.OMEGA_3**2
    car = 0.5 * 1500.0 * 100.0**2
    assert energy > 3.0 * car, energy / car


# ---------------------------------------------------------------------------
# Geometry the machine cannot be built without.
# ---------------------------------------------------------------------------
def test_a_blade_is_a_city_bus() -> None:
    assert S.BLADE_SPAN == pytest.approx(S.BUS_L)
    # Bus-sized by area too: a bus's side elevation is 12.19 x 3.20.
    assert S.BLADE_PLANFORM_M2 == pytest.approx(S.BUS_L * S.BUS_H, rel=0.15)


def test_the_blade_clears_the_neck_at_bottom_dead_centre() -> None:
    assert S.BLADE_NECK_CLEARANCE > 0.60, S.BLADE_NECK_CLEARANCE
    assert S.DISC_OFFSET_Y > S.DISC_OFFSET_FLOOR


def test_the_head_sits_where_the_blade_can_reach_a_car() -> None:
    assert S.HUB_Z == pytest.approx(S.DECK_Z + S.TIP_R + S.BLADE_BOTTOM_CLEAR)
    # The gag only works if the strike height is bumper-to-roof, not overhead.
    assert 0.2 <= S.BLADE_BOTTOM_CLEAR <= 0.6


def test_the_axial_extent_is_not_the_shell_thickness() -> None:
    """A twisted paddle is far deeper along the axis than it is thick.

    Sizing a clearance off BLADE_THICK/2 is how a blade ends up passing
    through the neck.
    """

    for s in (0.0, 0.3, 0.62, 1.0):
        assert S.blade_axial_half(s) > 0.55 * S.BLADE_THICK


# ---------------------------------------------------------------------------
# The built JBeam: the rotator, its group, and the bodies.
# ---------------------------------------------------------------------------
def test_the_rotator_names_a_group_the_cage_really_has() -> None:
    part = load_jbeam()
    nodes = node_table(part)
    row = part["rotators"][-1]
    name, groups, node1, node2, node_arm, wheel_dir = row[:6]
    assert name == "fan_rotor"
    for identifier in (node1, node2, node_arm):
        assert identifier in nodes, identifier
    assert node1 != node2
    members = [i for i, n in nodes.items() if n["group"] in groups]
    assert len(members) >= 4, "the rotator group is empty; the engine deletes it"
    assert wheel_dir in (-1, 1)


def test_the_rotator_axis_nodes_are_free_and_colinear_with_the_disc() -> None:
    part = load_jbeam()
    nodes = node_table(part)
    row = part["rotators"][-1]
    node1, node2 = row[2], row[3]
    for identifier in (node1, node2):
        assert nodes[identifier]["fixed"] is False, (
            f"{identifier} is fixed; a rotator on a fixed axis cannot ride a "
            "head that yaws and tilts"
        )
    a, b = nodes[node1]["pos"], nodes[node2]["pos"]
    # The fan axis runs along the vehicle's Y; x and z must agree.
    assert a[0] == pytest.approx(b[0], abs=1e-6)
    assert a[2] == pytest.approx(b[2], abs=1e-6)
    assert abs(a[1] - b[1]) > 0.5


def test_the_rotor_and_blades_are_free_bodies_with_their_own_collision() -> None:
    part = load_jbeam()
    nodes = node_table(part)
    rotor = f"{S.MOD_ID}_rotor"
    blade = f"{S.MOD_ID}_blade"
    members = {i: n for i, n in nodes.items() if n["group"] in (rotor, blade)}
    assert members, "no rotor body at all"
    for identifier, node in members.items():
        assert node["fixed"] is False, identifier
        # Self-collision on a body that sweeps 0.35 m over its own base is a
        # solver fight the machine cannot win.
        assert node["selfCollision"] is False, identifier
    blades = [i for i, n in nodes.items() if n["group"] == blade]
    assert len(blades) >= 3 * 4, "the blades are not a body"
    assert any(nodes[i]["collision"] for i in blades), "the blades cannot hit anything"


def test_no_collision_triangle_spans_a_moving_body_and_a_fixed_one() -> None:
    """A triangle with one fixed corner and two free ones is a physics bomb."""

    part = load_jbeam()
    nodes = node_table(part)
    for row in part["triangles"][1:]:
        a, b, c = row[0], row[1], row[2]
        fixedness = {nodes[a]["fixed"], nodes[b]["fixed"], nodes[c]["fixed"]}
        assert len(fixedness) == 1, (a, b, c)


def test_no_node_triple_is_emitted_twice() -> None:
    """The TWIN-TILING law.

    Two coincident mirrored triangles spike the solver and pop tyres on flat
    ground; add_quad_both exists so a double-sided surface is four DISTINCT
    triples rather than two repeated ones.
    """

    part = load_jbeam()
    seen = set()
    for row in part["triangles"][1:]:
        triple = (row[0], row[1], row[2])
        assert triple not in seen, triple
        seen.add(triple)


def test_the_blades_declare_their_own_aerodynamic_drag() -> None:
    """A fan's load IS its blades.

    BeamNG defaults a triangle's ``dragCoef`` to 100, i.e. Cd 1.0. Left alone,
    the rotor's own aero torque eats a large fraction of the motor and the fan
    never reaches its top setting.
    """

    part = load_jbeam()
    nodes = node_table(part)
    blade = f"{S.MOD_ID}_blade"
    checked = 0
    for row in part["triangles"][1:]:
        if nodes[row[0]]["group"] != blade:
            continue
        checked += 1
        assert row[3].get("dragCoef") is not None, row[:3]
        assert row[3]["dragCoef"] < 100
    assert checked > 0, "no blade triangles at all"


def test_the_motor_pushes_back_against_the_head() -> None:
    part = load_jbeam()
    nodes = node_table(part)
    reaction = part["motor"]["torqueReactionNodes:"]
    assert len(reaction) >= 3
    for identifier in reaction:
        assert identifier in nodes, identifier
        assert nodes[identifier]["group"] == f"{S.MOD_ID}_head"


def powertrain_rows(part) -> list[dict]:
    """The powertrain table as powertrain.lua reads it: header-keyed rows."""

    header = part["powertrain"][0]
    rows = []
    for row in part["powertrain"][1:]:
        entry = {name: row[i] for i, name in enumerate(header) if i < len(row)}
        if len(row) > len(header) and isinstance(row[len(header)], dict):
            entry.update(row[len(header)])
        rows.append(entry)
    return rows


def test_the_powertrain_reaches_the_rotator() -> None:
    part = load_jbeam()
    shaft = next(r for r in powertrain_rows(part) if r["name"] == "shaft")
    assert shaft["type"] == "shaft"
    assert shaft["connectedWheel"] == part["rotators"][-1][0]
    assert shaft["gearRatio"] == S.GEAR_RATIO


def test_every_powertrain_input_names_a_device_that_exists() -> None:
    """powertrain.lua's own deviceLookup rule, reproduced.

    :544 only sets `device.parent` when `deviceLookup[device.inputName]`
    resolves. A row whose inputName names nothing becomes a ROOT with no
    torque source: shaft.lua's validate() forces mode "disconnected" and
    `wheelShaftDisconnectedUpdateTorque` writes propulsionTorque = 0 every
    physics step, forever. The fan shipped exactly that - a shaft driven by a
    `motor` no row declared - and the rotor never turned.
    """

    rows = powertrain_rows(load_jbeam())
    declared = {row["name"] for row in rows}
    for row in rows:
        assert row["name"] != row["inputName"], row["name"]
        assert row["inputName"] in ("", None) or row["inputName"] in declared, (
            row["name"],
            row["inputName"],
            sorted(declared),
        )
    roots = [r for r in rows if not r["inputName"]]
    assert len(roots) == 1, [r["name"] for r in roots]


def test_the_motor_block_configures_a_device_that_exists() -> None:
    """`tableMergeRecursive(jbeamData, v.data[jbeamData.name])`, powertrain.lua:485.

    A top-level parameter block is merged into the device NAMED after it. With
    no such device the whole authored torque curve, maxRPM, inertia,
    torqueReactionNodes and soundConfig are silently discarded.
    """

    part = load_jbeam()
    rows = powertrain_rows(part)
    declared = {row["name"] for row in rows}
    assert "motor" in declared, sorted(declared)
    assert part["motor"]["soundConfig"] in part, "the sound config is orphaned too"

    motor = next(r for r in rows if r["name"] == "motor")
    factories = Path("E:/SteamLibrary/steamapps/common/BeamNG.drive/lua/vehicle/powertrain")
    if factories.is_dir():
        available = {path.stem for path in factories.glob("*.lua")}
        assert motor["type"] in available, (motor["type"], sorted(available))
    else:
        assert motor["type"] == "electricMotor", motor["type"]


# ---------------------------------------------------------------------------
# The joints. Each is beam geometry and must leave exactly one DOF.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "pivot_a,pivot_b,moving_group",
    [
        ("yawpivot_lo", "yawpivot_hi", "yoke"),
        ("trunnion_l", "trunnion_r", "head"),
    ],
)
def test_each_pivot_pair_is_colinear_with_its_joint_axis(
    pivot_a: str, pivot_b: str, moving_group: str
) -> None:
    """A pin joint only works because the pivot nodes sit ON the axis.

    Distances to two points on a line constrain a node to a circle about that
    line - one degree of freedom. Move a pivot node off the axis and the joint
    silently becomes a rigid connection.
    """

    part = load_jbeam()
    nodes = node_table(part)
    a = nodes[f"{S.MOD_ID}_{pivot_a}"]["pos"]
    b = nodes[f"{S.MOD_ID}_{pivot_b}"]["pos"]
    shared = sum(1 for i in range(3) if a[i] == pytest.approx(b[i], abs=1e-6))
    assert shared == 2, (a, b)
    assert any(i in nodes for i in (f"{S.MOD_ID}_{pivot_a}",))


def test_the_hydro_endpoints_exist_and_are_not_coincident() -> None:
    part = load_jbeam()
    nodes = node_table(part)
    assert len(part["hydros"]) >= 3
    for row in part["hydros"][1:]:
        if not isinstance(row, list):
            continue
        a, b = row[0], row[1]
        assert a in nodes and b in nodes, (a, b)
        pa, pb = nodes[a]["pos"], nodes[b]["pos"]
        length = math.dist(pa, pb)
        assert length > 1.0, (a, b, length)
        options = row[2]
        assert options["inputSource"] in ("fanSweep", "fanTilt")
        # autoCenterRate ZERO freezes a hydro the instant its command reaches
        # the input centre - which would make the lowest tilt rung unreachable
        # for the rest of the session.
        assert options.get("autoCenterRate", 0) > 0, options["inputSource"]
        assert options["inLimit"] < options["outLimit"]


def hydro_row(part, source: str):
    for row in part["hydros"][1:]:
        if isinstance(row, list) and row[2].get("inputSource") == source:
            return row
    raise AssertionError(source)


def built_yaw_ratio(nodes, theta: float) -> float:
    """The sweep crank's length ratio, recomputed from the BUILT node cloud."""

    pin = nodes[f"{S.MOD_ID}_yaw_crank_pin"]["pos"]
    anchor = nodes[f"{S.MOD_ID}_yaw_anchor"]["pos"]
    rest = math.dist(pin, anchor)
    x = pin[0] * math.cos(theta) - pin[1] * math.sin(theta)
    y = pin[0] * math.sin(theta) + pin[1] * math.cos(theta)
    return math.dist((x, y, pin[2]), anchor) / rest


def test_the_sweep_limits_are_the_cranks_own_lengths() -> None:
    """A hydro commands a LENGTH, and this crank is not linear in yaw.

    hydros.lua:660-673 sets `center` to 1 and maps the electrics value
    linearly onto the beam's length ratio; the crank then turns length into
    angle. Two hand-picked symmetric literals therefore bought a sweep of
    -61.5 deg .. +90 deg, and the + end asked for 17.411 m from a linkage
    whose GEOMETRIC MAXIMUM is 16.931 m - 0.48 m of permanent overstretch
    against beamSpring 2.85e8, at a dead centre that is a stable equilibrium.
    """

    part = load_jbeam()
    nodes = node_table(part)
    options = hydro_row(part, "fanSweep")[2]

    # (a) the limits ARE the crank's ratios at the authored half-sweep
    assert options["inLimit"] == pytest.approx(built_yaw_ratio(nodes, -S.SWEEP_HALF_RAD), abs=1e-6)
    assert options["outLimit"] == pytest.approx(built_yaw_ratio(nodes, +S.SWEEP_HALF_RAD), abs=1e-6)

    # (b) neither limit may pass the crank's dead centre, at any yaw
    sweep = [built_yaw_ratio(nodes, math.radians(d)) for d in range(-180, 181)]
    assert options["outLimit"] < max(sweep), (options["outLimit"], max(sweep))
    assert options["inLimit"] > min(sweep), (options["inLimit"], min(sweep))

    # (c) and solving each limit forward lands on the authored half-sweep
    for limit, want in (
        (options["inLimit"], -S.SWEEP_HALF_RAD),
        (options["outLimit"], +S.SWEEP_HALF_RAD),
    ):
        lo, hi = math.radians(-90.0), math.radians(90.0)
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if built_yaw_ratio(nodes, mid) < limit:
                lo = mid
            else:
                hi = mid
        assert 0.5 * (lo + hi) == pytest.approx(want, abs=1e-4)


TILT_GROUPS = ("head", "rotor", "blade")
GRAVITY = 9.81


def tilt_rig():
    """Everything the head's pitch depends on, read out of the BUILT jbeam.

    The built cage is the vehicle frame: x and y are both flipped against the
    authored frame, so nose-up is a NEGATIVE rotation about +X here.
    """

    part = load_jbeam()
    nodes = node_table(part)
    options = hydro_row(part, "fanTilt")[2]
    trunnion_z = nodes[f"{S.MOD_ID}_trunnion_l"]["pos"][2]
    assert nodes[f"{S.MOD_ID}_trunnion_r"]["pos"][2] == pytest.approx(trunnion_z)
    pin = nodes[f"{S.MOD_ID}_tilt_pin"]["pos"]
    anchor = nodes[f"{S.MOD_ID}_tilt_anchor"]["pos"]
    rest = math.dist(pin, anchor)

    groups = {f"{S.MOD_ID}_{name}" for name in TILT_GROUPS}
    body = [n for n in nodes.values() if n.get("group") in groups]
    assert len(body) >= 100, len(body)
    mass = sum(n.get("nodeWeight", 125.0) for n in body)
    cg_y = sum(n.get("nodeWeight", 125.0) * n["pos"][1] for n in body) / mass
    cg_z = sum(n.get("nodeWeight", 125.0) * n["pos"][2] for n in body) / mass

    blades = [n["pos"] for n in nodes.values() if n.get("group") == f"{S.MOD_ID}_blade"]
    assert len(blades) >= 60, len(blades)
    # Axial station and radius about the hub axis, which runs along Y through
    # the trunnion height. The rotor TURNS, so the radius is what reaches the
    # deck, not the node's own static z.
    swept = [(pos[1], math.hypot(pos[0], pos[2] - trunnion_z)) for pos in blades]

    def ratio(theta: float) -> float:
        y, z = pin[1], pin[2] - trunnion_z
        ry = y * math.cos(theta) + z * math.sin(theta)
        rz = -y * math.sin(theta) + z * math.cos(theta)
        return math.hypot(ry - anchor[1], rz - (anchor[2] - trunnion_z)) / rest

    def swept_floor(theta: float) -> float:
        return trunnion_z + min(
            -station * math.sin(theta) - radius * math.cos(theta) for station, radius in swept
        )

    def potential(theta: float, commanded: float) -> float:
        height = trunnion_z - cg_y * math.sin(theta) + (cg_z - trunnion_z) * math.cos(theta)
        stretch = (ratio(theta) - commanded) * rest
        return mass * GRAVITY * height + 0.5 * options["beamSpring"] * stretch**2

    return {
        "options": options,
        "mass": mass,
        "cg_y": cg_y,
        "cg_z": cg_z,
        "rest": rest,
        "trunnion_z": trunnion_z,
        "ratio": ratio,
        "swept_floor": swept_floor,
        "potential": potential,
    }


def settled_pitch(rig, commanded: float) -> float:
    """The pitch the head really comes to rest at, by minimising its energy.

    Not the pitch the crank length names: the tilt hydro is the ONLY member
    that resists pitch - every head-to-yoke beam lands ON the trunnion pair and
    so carries no pitch moment at all - so 122 t of head, rotor and blade with
    its mass centre 2.46 m in front of the axis droops the joint by its own
    weight over the crank's lever.
    """

    samples = [math.radians(-40.0 + 0.01 * i) for i in range(9001)]
    energies = [rig["potential"](theta, commanded) for theta in samples]
    # The well the machine actually lives in is the one nearest the pose the
    # crank was commanded to, not the global minimum.
    lo, hi = math.radians(-5.0), math.radians(40.0)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if rig["ratio"](mid) < commanded:
            lo = mid
        else:
            hi = mid
    rigid = 0.5 * (lo + hi)
    index = min(range(len(samples)), key=lambda i: abs(samples[i] - rigid))
    while 0 < index < len(samples) - 1:
        if energies[index - 1] < energies[index]:
            index -= 1
        elif energies[index + 1] < energies[index]:
            index += 1
        else:
            break
    # Polish with a bisection on the gradient inside that well.
    step = math.radians(0.01)
    lo, hi = samples[index] - step, samples[index] + step
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        slope = rig["potential"](mid + 1e-7, commanded) - rig["potential"](mid - 1e-7, commanded)
        if slope < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def test_the_tilt_body_ledger_matches_the_built_cage() -> None:
    """spec.py carries the tilting body's mass and mass centre as MEASURED
    constants, because the generator distributes them node by node and a second
    mass model in the spec would be a second machine. This is what keeps them
    from drifting apart.
    """

    rig = tilt_rig()
    assert rig["mass"] == pytest.approx(S.TILT_BODY_KG, rel=1e-6), rig["mass"]
    # Authored +Y is forward; the built cage flips it.
    assert -rig["cg_y"] == pytest.approx(S.TILT_BODY_CG_Y, abs=1e-4), rig["cg_y"]
    assert rig["cg_z"] - rig["trunnion_z"] == pytest.approx(S.TILT_BODY_CG_DZ, abs=1e-4), rig[
        "cg_z"
    ]


def test_the_tilt_rungs_strike_the_heights_the_console_announces() -> None:
    """End to end through the BUILT artifact, LOADED, with the rotor turning.

    Built blade nodes, built trunnion axis, built tilt crank, built hydro
    spring and limits, built node weights, and the shipped TILT_INPUT table.
    Two things the gate this replaces could not see, both in the same
    direction:

      * it took the lowest STATIC blade node. The rotor turns, and the
        outermost blade node is 15.4946 m from the hub axis - 0.105 m past
        TIP_R, because the tip station's chord corners sit off the radial line
        - so every rung swept 0.105 m lower than it measured;
      * it solved a WEIGHTLESS head. The real one droops on its own hydro.

    Together they put the bottom rung - the one the console boots into and
    prints by name - at 0.151 m against an announced 0.350 m.
    """

    rig = tilt_rig()
    out_limit = rig["options"]["outLimit"]
    for rung, (command, want) in enumerate(zip(S.TILT_INPUT, S.TILT_CLEAR_M, strict=False)):
        # hydros.lua: center is 1, inputCenter 0, inputOutLimit 1.
        commanded = 1.0 + command * (out_limit - 1.0)
        theta = settled_pitch(rig, commanded)
        clearance = rig["swept_floor"](theta) - S.DECK_Z
        assert clearance == pytest.approx(want, abs=0.01), (rung, clearance)
        assert clearance > 0.0, rung


def test_no_tilt_rung_parks_the_crank_on_its_dead_centre() -> None:
    """L(theta) is NOT monotone: it has a minimum 10 degrees nose-DOWN.

    So a commanded length has a SECOND solution on the far side of that dead
    centre, near 19 degrees nose-down, where the blade disc is 1.3 m through the
    deck and the spring is back at its rest length - and because the head's own
    weight is lower there, that far well is the GLOBAL minimum. Shipped, the
    bottom rung commanded exactly the rest length and sat 88 kJ from it: an
    eighth of the kinetic energy of a 1500 kg car at 30 m/s. One lower-blade
    strike and the machine face-planted into a pose the tilt control cannot
    climb out of, because past the dead centre dL/dtheta changes sign and
    "raise the head" lowers it. Nothing exploded on the way, either: every node
    ships selfCollision false, so the blades slice through the deck.

    1.2e6 J is a 1500 kg car at 40 m/s.
    """

    rig = tilt_rig()
    out_limit = rig["options"]["outLimit"]
    samples = [math.radians(-40.0 + 0.01 * i) for i in range(9001)]
    for rung, command in enumerate(S.TILT_INPUT):
        commanded = 1.0 + command * (out_limit - 1.0)
        theta = settled_pitch(rig, commanded)
        here = rig["potential"](theta, commanded)
        energies = [rig["potential"](value, commanded) for value in samples]
        index = min(range(len(samples)), key=lambda i: abs(samples[i] - theta))
        for direction in (-1, 1):
            peak = here
            walk = index
            while 0 <= walk + direction < len(samples):
                walk += direction
                peak = max(peak, energies[walk])
                if energies[walk] < here - 1.0:
                    assert peak - here > 1.2e6, (rung, direction, peak - here)
                    break


def test_no_hydro_limit_is_a_hand_typed_literal() -> None:
    """Both blocking geometry bugs were bare floats in JBEAM_SECTIONS.

    Every ratio in the table must be one a crank function produced.
    """

    part = load_jbeam()
    traceable = {
        round(S.YAW_IN_LIMIT, 9),
        round(S.YAW_OUT_LIMIT, 9),
        round(S.TILT_OUT_LIMIT, 9),
        1.0,
    }
    for row in part["hydros"][1:]:
        if not isinstance(row, list):
            continue
        options = row[2]
        for key in ("inLimit", "outLimit"):
            assert round(options[key], 9) in traceable, (
                options["inputSource"],
                key,
                options[key],
            )


# ---------------------------------------------------------------------------
# The controls.
# ---------------------------------------------------------------------------
def test_every_console_cap_has_its_own_frame_pair() -> None:
    """The triggers2 box basis is (idX - idRef, idY - idRef).

    One shared frame pair skews AND translates the hitbox of every cap not
    co-located with it, so the hover ghost floats away from the button.
    """

    part = load_jbeam()
    rows = part["triggers2"][1:]
    frames = [(row[2], row[3]) for row in rows]
    assert len(frames) == len(set(frames)), "two caps share a frame pair"


def test_panel_titles_are_ascii() -> None:
    # BeamNG's tooltip renderer prints unicode escapes literally.
    for button in S.PANEL_BUTTONS:
        assert all(ord(ch) < 127 for ch in button["title"]), button["id"]


def test_the_oscillation_verb_is_on_the_plunger() -> None:
    """The user asked for the sweep to live where a real fan's control does."""

    ids = {b["id"] for b in S.PANEL_BUTTONS}
    assert "plunger" in ids
    plunger = next(b for b in S.PANEL_BUTTONS if b["id"] == "plunger")
    # On the crown of the motor housing, above the hub.
    assert plunger["position"][2] > S.HUB_Z
    assert "osc" in ids, "and a reachable duplicate at ground level"


def test_the_stop_pad_can_actually_contain_a_car() -> None:
    dims = S.TRIGGERS["stop_pad"]["dimensions"]
    for got, want in zip(dims, (2.9, 4.5, 3.0), strict=False):
        assert got >= want, dims


def test_the_rotor_speed_is_signed_exactly_once() -> None:
    """powertrain/shaft.lua has already applied wheelDirection.

    ``wheelShaftUpdateVelocity`` does ``device.outputAV1 =
    device.wheel.angularVelocity * device.wheelDirection`` and then pushes
    ``outputAV1 * gearRatio`` into the motor, so ``motor.outputAV1`` is
    rawAV x wheelDir x gearRatio. A controller that multiplies by wheelDir
    again squares it back to the RAW value - and with wheelDir -1 that is
    negative for a rotor turning forwards.

    This is the static half; test_the_dial_settles_on_the_tip_speed_it_prints
    is the half that would have caught it.
    """

    lua = S.VEHICLE_CONTROLLERS["giantFan"]
    body = lua[lua.index("local function rotorAV") :]
    body = body[: body.index("\nend")]
    assert "wheelDir" not in body, body
    assert "/ GEAR_RATIO" in body, body


def controller_under_lupa():
    """The SHIPPED controller, against the engine's own sign chain."""

    lupa = pytest.importorskip("lupa")
    path = (
        PACK_ROOT / MOD_KEY / "mod" / "vehicles" / S.MOD_ID / "lua" / "controller" / "giantFan.lua"
    )
    if not path.is_file():
        pytest.skip("giant_fan is not built; run build.py giant_fan prop")
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        f"""
        nop = function() end
        electrics = {{values = {{}}}}
        MOTOR = {{maxAV = {float(S.MOTOR_MAX_AV)!r}, outputAV1 = 0.0,
                 setIgnition = function() end, sendTorqueData = function() end}}
        ROT = {{name = "fan_rotor", wheelDir = -1,
               brakeTorque = {float(S.BRAKE_TORQUE)!r}, desiredBrakingTorque = 0}}
        powertrain = {{getDevice = function() return MOTOR end}}
        wheels = {{wheelRotatorCount = 1, wheelRotators = {{[0] = ROT}}}}
        playerInfo = {{firstPlayerSeated = true}}
        function _throttle() return electrics.values.throttle or 0.0 end
        function _brake() return ROT.desiredBrakingTorque or 0.0 end
        function _setav(v) MOTOR.outputAV1 = v end
        function _tipspeed() return electrics.values.fanTipSpeed or 0.0 end
        """
    )
    module = lua.eval("function(src) return load(src, 'giantFan') end")(
        path.read_text(encoding="utf-8")
    )
    assert module, "the shipped controller does not compile"
    controller = module()
    controller.init(lua.table())
    return lua, controller


def motor_output_av(omega: float) -> float:
    """What `motor.outputAV1` really is for a rotor turning forwards.

    wheelDir is -1, so the wheel's RAW angular velocity is -omega and shaft.lua
    reports -omega * -1 * gearRatio. Signed once, by the engine.
    """

    return (-omega) * -1.0 * S.GEAR_RATIO


def motor_curve():
    curve = S.JBEAM_SECTIONS["motor"]["torque"][1:]

    def torque(rpm: float) -> float:
        rpm = min(max(rpm, curve[0][0]), curve[-1][0])
        for (r0, t0), (r1, t1) in itertools.pairwise(curve):
            if r0 <= rpm <= r1:
                span = (rpm - r0) / (r1 - r0) if r1 != r0 else 0.0
                return t0 + span * (t1 - t0)
        return curve[-1][1]

    return torque


def aero_torque(omega: float, segments: int = 48) -> float:
    """The blades' own drag at the dragCoef the jbeam really ships."""

    rho, drag = 1.225, 0.07
    total = 0.0
    for i in range(segments):
        station = (i + 0.5) / segments
        radius = S.HUB_R + station * S.BLADE_SPAN
        chord = S.blade_chord(station) * math.sin(S.blade_pitch(station))
        total += (
            0.5 * rho * drag * (omega * radius) ** 2 * chord * (S.BLADE_SPAN / segments) * radius
        )
    return S.BLADE_COUNT * total


@pytest.mark.parametrize("clicks,setting", [(1, 3), (2, 2), (3, 1)])
def test_the_dial_settles_on_the_tip_speed_it_prints(clicks: int, setting: int) -> None:
    """Drive the BUILT controller through the ENGINE's own sign chain.

    The controller shipped applying wheelDir a second time on top of the one
    shaft.lua had already applied, which made `ratio` negative at every speed:
    `ratioError` could never fall below its setpoint, so the throttle pinned at
    1.000 and all three dial settings ran flat out to the redline at 70.91 m/s;
    the down-step brake branch was unreachable; and `fanTipSpeed` reached the GE
    runtime negative, where applyWind's `if speed < 1.0 then return end`
    switched the wind jet off permanently. Every static gate passed - the one
    that guarded this asserted the bug's own text was present.
    """

    lua, controller = controller_under_lupa()
    for _ in range(clicks):
        controller.stepDial()
    globals_ = lua.globals()
    torque = motor_curve()
    omega, dt = 0.0, 1 / 60.0
    for _ in range(int(90.0 / dt)):
        globals_._setav(motor_output_av(omega))
        controller.updateGFX(dt)
        controller.updateWheelsIntermediate(dt)
        drive = torque(omega * S.GEAR_RATIO * S.AV_TO_RPM) * globals_._throttle()
        net = (
            drive * S.GEAR_RATIO
            - aero_torque(omega)
            - S.SHAFT_FRICTION
            - (globals_._brake() if omega > 1e-6 else 0.0)
        )
        omega = max(0.0, omega + net / S.ROTOR_INERTIA * dt)
    assert omega * S.TIP_R == pytest.approx(S.TIP_MPS[setting], abs=0.5), (
        setting,
        omega * S.TIP_R,
    )
    status = controller.status()
    assert status.tip_mps > 0.0, status.tip_mps
    assert status.tip_mps == pytest.approx(S.TIP_MPS[setting], abs=0.5)


def test_the_reported_tip_speed_is_never_negative() -> None:
    """runtime.lua's applyWind opens with `if speed < 1.0 then return end`.

    A negative tip speed is not a cosmetic sign error: it switches the wind
    field off for the whole session, silently.
    """

    lua, controller = controller_under_lupa()
    controller.stepDial()
    globals_ = lua.globals()
    for omega in (0.5, 1.0, S.OMEGA_3 * 0.5, S.OMEGA_3):
        globals_._setav(motor_output_av(omega))
        controller.updateGFX(1 / 60.0)
        assert controller.status().tip_mps == pytest.approx(omega * S.TIP_R, abs=1e-6)
        assert globals_._tipspeed() > 0.0


def test_the_controller_is_addressed_per_vehicle() -> None:
    """Stock's onGameplayEvent is a BROADCAST with no vehicle filter.

    Two of the same prop on one map would move together. The GE runtime must
    reach this controller through queueLuaCommand, which targets one vehicle.
    """

    assert "queueLuaCommand" in S.LUA_BEHAVIOR
    assert "onGameplayEvent" not in S.LUA_BEHAVIOR


# ---------------------------------------------------------------------------
# The BUILT visual mesh.
#
# Every gate above this line reads spec constants, the jbeam cage or the
# controller Lua. None of them could see that six authored details had been
# placed as flat or axis-aligned primitives with no regard for the curved
# shells they sit on - four guard stubs hanging 1.33 m off the flange, ten
# ladder rungs levitating up the back of the neck, a 12 m plank spearing out
# of the head, a decal cutting 1.09 m through a spinning blade, a buried hub
# badge, and the fallen guard's sticker welded to the tilting head.
#
# So these parse the exported DAE. The mesh is written in the VEHICLE frame,
# which is the authored frame rotated 180 degrees about Z, so x and y both
# flip on the way back.
# ---------------------------------------------------------------------------
DAE_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}


def load_dae() -> dict:
    """{geometry name: {material key: [authored-frame positions]}}."""

    import xml.etree.ElementTree as ElementTree

    path = PACK_ROOT / MOD_KEY / "mod" / "vehicles" / S.MOD_ID / f"{S.MOD_ID}.dae"
    if not path.is_file():
        pytest.skip("giant_fan is not built; run build.py giant_fan prop")
    root = ElementTree.parse(path).getroot()
    out = {}
    for geometry in root.find("c:library_geometries", DAE_NS):
        mesh = geometry.find("c:mesh", DAE_NS)
        raw = [
            float(value)
            for value in mesh.find("c:source", DAE_NS).find("c:float_array", DAE_NS).text.split()
        ]
        points = [(-raw[i], -raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
        by_material = {}
        for triangles in mesh.findall("c:triangles", DAE_NS):
            material = triangles.get("material", "").replace("-material", "")
            inputs = triangles.findall("c:input", DAE_NS)
            stride = max(int(i.get("offset")) for i in inputs) + 1
            offset = next(int(i.get("offset")) for i in inputs if i.get("semantic") == "VERTEX")
            indices = [int(value) for value in triangles.find("c:p", DAE_NS).text.split()][
                offset::stride
            ]
            bucket = by_material.setdefault(material, [])
            bucket.extend(points[i] for i in set(indices))
        out[geometry.get("name")] = by_material
    return out


def load_dae_faces() -> list[tuple[str, str, tuple, tuple]]:
    """[(geometry, material, three authored-frame points, three UVs)].

    load_dae() above only needs positions. These gates need the triangle AND
    its texture coordinates, because the defect they exist for is a mesh whose
    geometry is perfect and whose UV window is 25% of the map, rotated 90
    degrees.
    """

    import xml.etree.ElementTree as ElementTree

    path = PACK_ROOT / MOD_KEY / "mod" / "vehicles" / S.MOD_ID / f"{S.MOD_ID}.dae"
    if not path.is_file():
        pytest.skip("giant_fan is not built; run build.py giant_fan prop")
    root = ElementTree.parse(path).getroot()
    faces = []
    for geometry in root.find("c:library_geometries", DAE_NS):
        mesh = geometry.find("c:mesh", DAE_NS)
        sources = {}
        for source in mesh.findall("c:source", DAE_NS):
            stride = int(
                source.find("c:technique_common", DAE_NS).find("c:accessor", DAE_NS).get("stride")
            )
            values = [float(value) for value in source.find("c:float_array", DAE_NS).text.split()]
            sources[source.get("id")] = [
                tuple(values[i : i + stride]) for i in range(0, len(values), stride)
            ]
        alias = {}
        for vertices in mesh.findall("c:vertices", DAE_NS):
            alias[vertices.get("id")] = vertices.find("c:input", DAE_NS).get("source")[1:]
        for triangles in mesh.findall("c:triangles", DAE_NS):
            material = triangles.get("material", "").replace("-material", "")
            inputs = triangles.findall("c:input", DAE_NS)
            stride = max(int(i.get("offset")) for i in inputs) + 1
            semantics = {}
            for entry in inputs:
                source = entry.get("source")[1:]
                semantics[entry.get("semantic")] = (
                    alias.get(source, source),
                    int(entry.get("offset")),
                )
            indices = [int(value) for value in triangles.find("c:p", DAE_NS).text.split()]
            for face in range(len(indices) // stride // 3):
                points, uvs = [], []
                for corner in range(3):
                    base = (face * 3 + corner) * stride
                    key, offset = semantics["VERTEX"]
                    raw = sources[key][indices[base + offset]]
                    points.append((-raw[0], -raw[1], raw[2]))
                    if "TEXCOORD" in semantics:
                        key, offset = semantics["TEXCOORD"]
                        uvs.append(sources[key][indices[base + offset]])
                    else:
                        uvs.append((0.0, 0.0))
                faces.append((geometry.get("name"), material, tuple(points), tuple(uvs)))
    return faces


def face_normal(points) -> tuple[float, float, float]:
    a, b, c = points
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = [
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    ]
    length = math.sqrt(sum(value * value for value in n)) or 1.0
    return tuple(value / length for value in n)


def uv_tangents(points, uvs):
    """(dP/du, dP/dv) for one triangle, or None if its UV is degenerate."""

    a, b, c = points
    e1 = [b[i] - a[i] for i in range(3)]
    e2 = [c[i] - a[i] for i in range(3)]
    d1 = (uvs[1][0] - uvs[0][0], uvs[1][1] - uvs[0][1])
    d2 = (uvs[2][0] - uvs[0][0], uvs[2][1] - uvs[0][1])
    determinant = d1[0] * d2[1] - d2[0] * d1[1]
    if abs(determinant) < 1e-12:
        return None
    scale = 1.0 / determinant
    tangent = [(e1[i] * d2[1] - e2[i] * d1[1]) * scale for i in range(3)]
    bitangent = [(e2[i] * d1[0] - e1[i] * d2[0]) * scale for i in range(3)]

    def unit(vector):
        length = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / length for value in vector]

    return unit(tangent), unit(bitangent)


def ray_hits_triangle(origin, direction, triangle) -> float | None:
    """Moller-Trumbore, both windings. Returns the forward distance or None."""

    a, b, c = triangle
    e1 = [b[i] - a[i] for i in range(3)]
    e2 = [c[i] - a[i] for i in range(3)]
    h = [
        direction[1] * e2[2] - direction[2] * e2[1],
        direction[2] * e2[0] - direction[0] * e2[2],
        direction[0] * e2[1] - direction[1] * e2[0],
    ]
    determinant = sum(e1[i] * h[i] for i in range(3))
    if abs(determinant) < 1e-12:
        return None
    inverse = 1.0 / determinant
    sv = [origin[i] - a[i] for i in range(3)]
    u = inverse * sum(sv[i] * h[i] for i in range(3))
    if u < 0.0 or u > 1.0:
        return None
    q = [
        sv[1] * e1[2] - sv[2] * e1[1],
        sv[2] * e1[0] - sv[0] * e1[2],
        sv[0] * e1[1] - sv[1] * e1[0],
    ]
    v = inverse * sum(direction[i] * q[i] for i in range(3))
    if v < 0.0 or u + v > 1.0:
        return None
    distance = inverse * sum(e2[i] * q[i] for i in range(3))
    return distance if distance > 1e-6 else None


ESC_TILT = math.radians(-S.ESC_TILT_DEG)
ESC_NORMAL = (0.0, math.cos(ESC_TILT), math.sin(ESC_TILT))
ESC_UP = (0.0, -math.sin(ESC_TILT), math.cos(ESC_TILT))
ESC_CENTRE = (0.0, 12.45 - S.ESC_RECESS, S.ESC_C_Z)


@pytest.mark.parametrize(
    "material,view,width_axis,height_axis",
    [
        ("dial_face", ESC_NORMAL, (-1.0, 0.0, 0.0), ESC_UP),
        ("panel_legend", (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        ("hub_badge", (0.0, 1.0, 0.0), None, None),
    ],
)
def test_every_printed_legend_covers_its_whole_map(material, view, width_axis, height_axis) -> None:
    """ONE_TILE_MATERIALS is necessary and nowhere near sufficient.

    One tile only helps if the primitive's default UV puts the artwork on the
    face you can see, and for boxes and cylinder caps it does not. Measured off
    the shipped DAE: the escutcheon's outward face carried u [0.378, 0.622] x
    v [0.251, 0.499] - a 24% x 25% crop - with the texture's U axis running
    along the plate's HEIGHT, so only "3" and "1" survived and they lay on their
    sides; the console legend's window did not contain the GALEFORCE title at
    all, so a 3.6 x 1.5 m plate with five buttons on it rendered blank; and the
    hub badge's cap carried Blender's stock quadrant, u [0.51, 0.99] x
    v [0.01, 0.49], so the roundel was one ring arc and a stub of a letter.
    """

    key = f"{S.MOD_ID}_{material}"
    outward = [
        (points, uvs)
        for _geometry, name, points, uvs in load_dae_faces()
        if name == key and sum(face_normal(points)[i] * view[i] for i in range(3)) > 0.5
    ]
    assert outward, key

    us = [uv[0] for _points, uvs in outward for uv in uvs]
    vs = [uv[1] for _points, uvs in outward for uv in uvs]
    assert min(us) < 0.05 and max(us) > 0.95, (key, min(us), max(us))
    assert min(vs) < 0.05 and max(vs) > 0.95, (key, min(vs), max(vs))

    # ...and the artwork must not be in a MIRROR. u x v has to point the way
    # the surface faces, or every glyph on it reads backwards - which is the
    # other half of "the print is on the plate", and the half that survives a
    # UV window fix.
    for points, uvs in outward:
        axes = uv_tangents(points, uvs)
        assert axes, (key, points)
        tangent, bitangent = axes
        handedness = (
            (tangent[1] * bitangent[2] - tangent[2] * bitangent[1]) * view[0]
            + (tangent[2] * bitangent[0] - tangent[0] * bitangent[2]) * view[1]
            + (tangent[0] * bitangent[1] - tangent[1] * bitangent[0]) * view[2]
        )
        assert handedness > 0.9, (key, handedness)

    if width_axis is None:
        return
    limit = math.cos(math.radians(5.0))
    for points, uvs in outward:
        tangent, bitangent = uv_tangents(points, uvs)
        along = sum(tangent[i] * width_axis[i] for i in range(3))
        up = sum(bitangent[i] * height_axis[i] for i in range(3))
        assert along > limit, (key, along)
        assert up > limit, (key, up)


def test_the_dial_face_is_not_sealed_inside_its_own_bezel() -> None:
    """What shipped was a lid, not a bezel.

    `esc_bezel` was one SOLID bevelled box, 0.06 m in front of the dial plate
    and larger than it in both in-plane directions, and the chrome knob sat
    0.10 m BEHIND the plate. Rasterised from the front the escutcheon was a
    blank cream slab: no dial, no numerals, no knob. "The dial adjusts power"
    is the headline verb and there was no dial on the machine.
    """

    shell = [
        points
        for _geometry, name, points, _uvs in load_dae_faces()
        if name == f"{S.MOD_ID}_shell_yellowed"
    ]
    dial = [
        points
        for _geometry, name, points, _uvs in load_dae_faces()
        if name == f"{S.MOD_ID}_dial_face"
    ]
    assert dial, "no dial face at all"

    def world(across, up, out):
        return tuple(
            ESC_CENTRE[i] + across * (1.0, 0.0, 0.0)[i] + up * ESC_UP[i] + out * ESC_NORMAL[i]
            for i in range(3)
        )

    for i in range(1, 8):
        for j in range(1, 5):
            origin = world((i / 8.0 - 0.5) * S.ESC_W, (j / 5.0 - 0.5) * S.ESC_H, 0.10)
            blocked = [
                triangle
                for triangle in shell
                if ray_hits_triangle(origin, ESC_NORMAL, triangle) is not None
            ]
            assert not blocked, (i, j, blocked[0])


def test_no_cap_detail_is_buried_inside_the_hub_cap() -> None:
    """The cap is an ELLIPSOID, so "a bit past its centre" is inside it.

    Round 1 caught the badge and it was fixed with an explicit sqrt; the eight
    nibs thirty lines below kept the `CAP_DOME_RISE * 0.42` fudge factor and sat
    0.337 m INSIDE the shell - 864 triangles nobody could ever see, on a cap
    that then had nothing on it at all. This is the general rule instead of the
    two special cases: every detail seated on the cap has to break its surface
    and stand proud of it, and none may be sunk more than its own seat depth.
    """

    dae = load_dae()
    head = dae[f"{S.MOD_ID}_head_mesh"]
    centre_y = S.DISC_OFFSET_Y + S.CAP_PROUD * 0.35

    def proud(point) -> float:
        radius = math.hypot(point[0], point[2] - S.HUB_Z)
        drop = max(0.0, 1.0 - (radius / S.CAP_R) ** 2)
        return point[1] - (centre_y + S.CAP_DOME_RISE * math.sqrt(drop))

    details = {"hub_badge": list(head[f"{S.MOD_ID}_hub_badge"])}
    # The nibs are shell_yellowed like the dome itself, so pick them out by
    # standing on the nib circle rather than by material.
    details["nibs"] = [
        point
        for point in head[f"{S.MOD_ID}_shell_yellowed"]
        if abs(math.hypot(point[0], point[2] - S.HUB_Z) - S.NIB_R) < 0.30
        and centre_y + 0.5 * S.CAP_DOME_RISE < point[1] < centre_y + S.CAP_DOME_RISE + 0.30
    ]
    assert details["hub_badge"], "no badge"
    # A nib sunk back to where it shipped would fall out of this window
    # entirely, so the COUNT is half the gate: eight nibs have to be up here.
    assert len(details["nibs"]) >= S.NIB_N * 4, len(details["nibs"])
    for name, points in details.items():
        heights = [proud(point) for point in points]
        assert max(heights) > 0.05, (name, max(heights))
        assert min(heights) > -0.06, (name, min(heights))


def test_the_yoke_is_one_body_and_not_a_pair_of_islands() -> None:
    """The arms floated 2.245 m clear of the collar.

    build_yoke() put the collar at r 3.55, z 9.20..10.90 and then the arms at
    |x| 5.795..7.305, z 11.30..18.14, with nothing between them: a 2.245 m
    horizontal and 0.40 m vertical gap, so the whole upper yoke - arms,
    trunnions, tie rails, cross tie - was a mesh island whose nearest surface
    inside its own body was 2.304 m away. Two 6.84 m slabs standing on daylight,
    plainly visible from the front or the back.

    Measured as a bounding-box gap between welded components, which is the
    right coarseness for a machine assembled out of boxes and cylinders: two
    parts that share volume are bolted together, two whose boxes are 2.3 m apart
    are not.
    """

    faces = [
        points
        for geometry, _name, points, _uvs in load_dae_faces()
        if geometry == f"{S.MOD_ID}_yoke_mesh"
    ]
    assert faces

    def key(point):
        return tuple(round(value, 4) for value in point)

    parent: dict = {}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for points in faces:
        keys = [key(point) for point in points]
        for entry in keys:
            parent.setdefault(entry, entry)
        union(keys[0], keys[1])
        union(keys[1], keys[2])

    boxes: dict = {}
    for entry in parent:
        root = find(entry)
        box = boxes.get(root)
        if box is None:
            boxes[root] = [list(entry), list(entry)]
            continue
        for axis in range(3):
            box[0][axis] = min(box[0][axis], entry[axis])
            box[1][axis] = max(box[1][axis], entry[axis])
    assert len(boxes) > 1, "nothing to compare"

    def gap(a, b) -> float:
        return math.sqrt(
            sum(
                max(0.0, max(a[0][axis] - b[1][axis], b[0][axis] - a[1][axis])) ** 2
                for axis in range(3)
            )
        )

    for root, box in boxes.items():
        nearest = min(gap(box, other) for key_, other in boxes.items() if key_ != root)
        assert nearest < 0.10, (box, nearest)


def neck_radius(z: float) -> float:
    return S.NECK_R_BOT + (S.NECK_R_TOP - S.NECK_R_BOT) * (z - S.DECK_Z) / S.NECK_H


def housing_radius(y: float) -> float:
    return S.HSG_R_REAR + (S.HSG_R_FRONT - S.HSG_R_REAR) * ((y - S.HSG_REAR_Y) / S.HSG_L)


def test_the_moulded_warning_bands_hug_the_shells_they_are_moulded_into() -> None:
    """A flat box chorded across a cone is buried in the middle and floating
    at the ends - and here it was both. The neck band's text sat 0.29 m INSIDE
    the neck while its ends floated 1.88 m clear; the housing band was a 12 m
    plank spearing 4.6 m out of a shell only 2.8 m wide at that height.
    """

    dae = load_dae()
    key = f"{S.MOD_ID}_moulded_warning"

    neck = dae[f"{S.MOD_ID}_visual"][key]
    assert len(neck) >= 32
    for x, y, z in neck:
        assert S.NECK_WARN_Z[0] - 1e-3 <= z <= S.NECK_WARN_Z[1] + 1e-3
        proud = math.hypot(x, y) - neck_radius(z)
        assert 0.0 < proud <= 0.20, (x, y, z, proud)

    housing = dae[f"{S.MOD_ID}_head_mesh"][key]
    assert len(housing) >= 32
    for x, y, z in housing:
        proud = math.hypot(x, z - S.HUB_Z) - housing_radius(y)
        assert 0.0 < proud <= 0.20, (x, y, z, proud)


def test_the_guard_stubs_leave_the_flange_radially() -> None:
    """add_cylinder can only point along X, Y or Z. Built with axis="Y" the
    stubs ran along the FAN axis at a single radius, so all four floated
    1.33 m off the flange bead with their torn ends a further 1.37 m out.
    """

    dae = load_dae()
    torn = dae[f"{S.MOD_ID}_head_mesh"][f"{S.MOD_ID}_blade_smoke_dark"]
    bead = S.FLANGE_OD / 2.0 + S.RIM_BEAD_R
    assert len(torn) >= 4 * 10

    def radius(point) -> float:
        return math.hypot(point[0], point[2] - S.HUB_Z)

    # The torn ends are the far end of a stub that STARTS on the bead, so they
    # must sit about one stub-length out - not a stub-length plus a gap.
    for point in torn:
        reach = radius(point) - bead
        assert 0.0 < reach <= S.STUB_ROOT_L + 0.35, (point, reach)

    # And a radial rod sweeps a RANGE of radii; a fan-axis rod does not.
    white = dae[f"{S.MOD_ID}_head_mesh"][f"{S.MOD_ID}_shell_white"]
    outboard = [radius(point) for point in white if radius(point) > bead + 0.05]
    assert outboard, "no shell_white geometry outboard of the bead at all"
    assert max(outboard) - min(outboard) > 0.7 * S.STUB_ROOT_L, (
        min(outboard),
        max(outboard),
    )


def test_the_gantry_is_carried_by_the_neck_it_climbs() -> None:
    """The rungs sat at a constant y against a cone that loses 1.85 m of
    radius over its rise, so the top rung floated 2.60 m clear and every rung
    was its own island. They must overlap the shell at EVERY height, and the
    ladder must honour the authored 0.28 m rise rather than NECK_H/10.
    """

    dae = load_dae()
    rungs = dae[f"{S.MOD_ID}_visual"][f"{S.MOD_ID}_gantry_steel"]
    count = int(S.NECK_H / S.GANTRY_STAIR_RISE)
    assert count >= 20, count

    # Nothing anywhere on the ladder may hang more than a rung's own depth
    # clear of the shell it climbs. The shipped top rung was 2.60 m out.
    for x, y, z in rungs:
        assert abs(y) - neck_radius(z) <= 0.70, (x, y, z)

    # And every authored rung must actually bite into the shell. The rung's
    # inboard face is a constant-y plane, so its own |y| is the reach; the
    # corners sit further out simply because the rung is 2.60 m wide.
    for i in range(count):
        z = S.DECK_Z + (i + 1) * S.GANTRY_STAIR_RISE
        reach = [
            abs(y) - neck_radius(point_z) for _x, y, point_z in rungs if abs(point_z - z) < 0.09
        ]
        assert reach, i
        assert min(reach) < 0.0, (i, z, min(reach))


def test_the_hub_badge_stands_proud_of_the_cap() -> None:
    """The cap is an ellipsoid, so a badge placed "past its centre" is inside
    it. The GF roundel shipped 0.29 m under the shell and no player could ever
    have seen it.
    """

    dae = load_dae()
    badge = dae[f"{S.MOD_ID}_head_mesh"][f"{S.MOD_ID}_hub_badge"]
    assert badge
    centre_y = S.DISC_OFFSET_Y + S.CAP_PROUD * 0.35
    rim_y = centre_y + S.CAP_DOME_RISE * math.sqrt(1.0 - (S.BADGE_A / (2.0 * S.CAP_R)) ** 2)
    apex_y = centre_y + S.CAP_DOME_RISE
    front = max(point[1] for point in badge)
    back = min(point[1] for point in badge)
    assert front > apex_y, (front, apex_y)  # visible over the whole dome
    assert back >= rim_y - 0.10, (back, rim_y)  # and seated, not floating


def test_the_blade_transfer_lies_on_the_blade_it_is_painted_on() -> None:
    """The station is pitched 22 degrees. A box rotated by the AZIMUTH only
    stays flat in the disc plane and cuts through the shell - 0.22 m buried at
    one edge and 1.09 m clear of it at the other, on a blade that spins.
    """

    dae = load_dae()
    decal = dae[f"{S.MOD_ID}_rotor_mesh"][f"{S.MOD_ID}_blade_transfer"]
    assert decal
    skin = [
        S.blade_point(S.BLADE_AZIMUTHS[0], i / 80.0, -0.5 + j / 60.0, -0.5)
        for i in range(81)
        for j in range(61)
    ]
    for point in decal:
        assert min(math.dist(point, sample) for sample in skin) < 0.15, point


def test_the_head_mesh_carries_only_the_head() -> None:
    """Anything built inside build_head() is bound to the group that yaws for
    the sweep AND tilts for the strike ladder. The fallen guard's sticker went
    in there, 25 m from the yaw axis: it skated 19 m across the ground at full
    sweep and lifted 6.8 m into the air at the top tilt rung.
    """

    dae = load_dae()
    hub = (0.0, S.DISC_OFFSET_Y, S.HUB_Z)
    for material, points in dae[f"{S.MOD_ID}_head_mesh"].items():
        for point in points:
            assert math.dist(point, hub) <= 12.0, (material, point)


# ---------------------------------------------------------------------------
# The palette, and the two GE-runtime mechanisms the panel caught.
# ---------------------------------------------------------------------------
def test_every_palette_entry_becomes_a_shipped_material() -> None:
    """A palette entry with no geometry is a texture bake nobody sees, and -
    worse - an invitation to "restore" a subsystem that was deliberately
    trimmed. Nine dead lamp/deck entries baked 29 PNGs on every build and
    shipped none of them.
    """

    path = PACK_ROOT / MOD_KEY / "mod" / "vehicles" / S.MOD_ID / "main.materials.json"
    if not path.is_file():
        pytest.skip("giant_fan is not built; run build.py giant_fan prop")
    shipped = set(json.loads(path.read_text(encoding="utf-8")))
    assert shipped == set(S.PALETTE), shipped.symmetric_difference(S.PALETTE)
    # And every material is UV-mapped exactly once: metric, or deliberately
    # one tile, never both and never neither.
    for key in S.PALETTE:
        assert (key in S.UV_METERS) != (key in S.ONE_TILE_MATERIALS), key


def runtime_source() -> str:
    path = PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / S.MOD_ID / "runtime.lua"
    if not path.is_file():
        pytest.skip("giant_fan is not built; run build.py giant_fan prop")
    return path.read_text(encoding="utf-8")


def test_the_wind_takes_an_id_off_each_vehicle_object() -> None:
    """ge_utils.lua:508 - getAllVehicles() returns BeamNGVehicle OBJECTS.

    The ids live in a cache it does not hand out. Passing an object straight
    to eligibleSubject makes its integer() guard reject every vehicle, with no
    log line, so the wind field touched nobody. Every sibling in this pack
    calls :getId() first; the fan was the one that skipped it.
    """

    source = runtime_source()
    start = source.index("local function applyWind")
    body = source[start : source.index("\nfunction behavior.", start)]
    assert "getAllVehicles" in body, body

    # The roster is a table of objects, so the id has to be taken off one
    # before anything that expects an id ever sees it.
    fetch = body.index(":getId()")
    use = body.index("eligibleSubject(")
    assert fetch < use, body
    # ...and the loop variable itself must never be handed over as an id.
    loop = body[body.index("for _, ") : body.index("for _, ") + 40]
    variable = loop.split("for _, ")[1].split(" ")[0]
    assert f"eligibleSubject({variable})" not in body, variable


def test_the_stop_pad_banks_no_dwell_while_the_fan_is_off() -> None:
    """The pad and the console share the rear bay floor.

    A player who drives up the service ramp and parks at the console banks
    dwell with the dial at 0; the firing test then sees a non-zero dial on the
    very next frame and switches the fan straight back off. The first thing a
    player does in the first ninety seconds could not be done at all.
    """

    source = runtime_source()
    start = source.index("function behavior.update")
    body = source[start : source.index("function behavior.onPanelButton", start)]
    accumulate = body.index("padDwell = (b.padDwell or 0.0) + dtSim")
    guard = body.rindex("if ", 0, accumulate)
    assert "(b.dial or 0) ~= 0" in body[guard:accumulate], body[guard:accumulate]

    press = source.index("function behavior.onPanelButton")
    head = source[press : source.index("if buttonId ==", press)]
    assert "padDwell = 0.0" in head, head


# ---------------------------------------------------------------------------
# The shipped material book.
# ---------------------------------------------------------------------------
def test_no_material_on_this_machine_is_translucent() -> None:
    """There is no glass on a giant fan, so the rule is absolute.

    prop_builder turns any palette alpha below 1.0 into `translucent: true,
    alphaRef: 0`, and the two blade materials shipped at 0.62 - which is
    BLADE_THICK, a thickness constant that landed in the RGBA alpha slot. That
    put all three 12.19 m paddles, the hub disc and the four torn guard stubs
    into the blended pass at 62% opacity, and doubleSided meant it happened
    twice per blade: you could read the flange's bolt bosses through the thing
    that is about to eat your car. In stock BeamNG that exact combination
    appears on five materials across forty vehicle zips and four of them are
    police light glass.
    """

    path = PACK_ROOT / MOD_KEY / "mod" / "vehicles" / S.MOD_ID / "main.materials.json"
    if not path.is_file():
        pytest.skip("giant_fan is not built; run build.py giant_fan prop")
    book = json.loads(path.read_text(encoding="utf-8"))
    assert book
    for name, definition in book.items():
        stage = definition["Stages"][0]
        alpha = stage.get("baseColorFactor", [1.0, 1.0, 1.0, 1.0])[3]
        assert alpha == pytest.approx(1.0), (name, alpha)
        assert not definition.get("translucent"), name


def test_no_hydro_authors_a_bound_the_engine_never_reads() -> None:
    """beamLimitSpring / beamLimitDamp are BEAM_BOUNDED keys.

    jbeam/stage2.lua's addBeamByData reads them only inside its
    `elseif beam.beamType == BEAM_BOUNDED` branch, and a hydro is BEAM_HYDRO
    (6), which falls through to the plain linear path. Both rows authored them
    equal to their own beamSpring, which read as a stated bound and was nothing
    at all.
    """

    part = load_jbeam()
    for row in part["hydros"][1:]:
        if not isinstance(row, list):
            continue
        options = row[2]
        assert "beamLimitSpring" not in options, options["inputSource"]
        assert "beamLimitDamp" not in options, options["inputSource"]


# ---------------------------------------------------------------------------
# The machine you drive on versus the machine you can see.
# ---------------------------------------------------------------------------
def collision_faces_authored(ground_model: str | None = None):
    """Every collision triangle as three authored-frame points."""

    part = load_jbeam()
    nodes = node_table(part)
    faces = []
    for row in part["triangles"][1:]:
        if not isinstance(row, list):
            continue
        if ground_model is not None:
            options = row[3] if len(row) > 3 and isinstance(row[3], dict) else {}
            if options.get("groundModel") != ground_model:
                continue
        points = []
        for identifier in row[:3]:
            x, y, z = nodes[identifier]["pos"]
            points.append((-x, -y, z))
        faces.append(points)
    assert faces
    return faces


def surface_gap(point, triangle) -> float:
    """How far a point is from a collision triangle's drivable surface.

    In plan while it is outside the triangle, in HEIGHT once it is over it.
    """

    plan = plan_distance(point, triangle)
    if plan > 0.0:
        return plan
    (x1, y1), (x2, y2), (x3, y3) = [(q[0], q[1]) for q in triangle]
    determinant = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    a = ((y2 - y3) * (point[0] - x3) + (x3 - x2) * (point[1] - y3)) / determinant
    b = ((y3 - y1) * (point[0] - x3) + (x1 - x3) * (point[1] - y3)) / determinant
    height = a * triangle[0][2] + b * triangle[1][2] + (1.0 - a - b) * triangle[2][2]
    return abs(height - point[2])


def plan_height(point, faces):
    """Interpolated surface height under a plan position, or None."""

    best = None
    for triangle in faces:
        (x1, y1), (x2, y2), (x3, y3) = [(q[0], q[1]) for q in triangle]
        determinant = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
        if abs(determinant) < 1e-12:
            continue
        a = ((y2 - y3) * (point[0] - x3) + (x3 - x2) * (point[1] - y3)) / determinant
        b = ((y3 - y1) * (point[0] - x3) + (x1 - x3) * (point[1] - y3)) / determinant
        c = 1.0 - a - b
        if a < -1e-9 or b < -1e-9 or c < -1e-9:
            continue
        height = a * triangle[0][2] + b * triangle[1][2] + c * triangle[2][2]
        if best is None or abs(height - point[2]) < abs(best - point[2]):
            best = height
    return best


def plan_distance(point, triangle) -> float:
    (x1, y1), (x2, y2), (x3, y3) = [(q[0], q[1]) for q in triangle]
    determinant = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if abs(determinant) > 1e-12:
        a = ((y2 - y3) * (point[0] - x3) + (x3 - x2) * (point[1] - y3)) / determinant
        b = ((y3 - y1) * (point[0] - x3) + (x1 - x3) * (point[1] - y3)) / determinant
        if a >= -1e-9 and b >= -1e-9 and 1.0 - a - b >= -1e-9:
            return 0.0
    best = math.inf
    for i in range(3):
        a, b = triangle[i], triangle[(i + 1) % 3]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = dx * dx + dy * dy
        t = 0.0
        if length > 0.0:
            t = max(
                0.0,
                min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length),
            )
        best = min(best, math.hypot(point[0] - (a[0] + t * dx), point[1] - (a[1] + t * dy)))
    return best


def test_the_drivable_deck_reaches_the_deck_you_can_see() -> None:
    """The cage stopped 0.7 to 2.8 m inside the machine you can see.

    build_cage() laid the whole fixed body on `BASE_X / 2 - 2.20`, a 21.6 m
    square, while the visible base is a 26 m four-lobed superellipse reaching
    |x| 13.565 and a radius of 17.511. 185 m2 of the 652 m2 deck top - 28 % of
    it - had no floor: a car flung by the blade landed there and dropped
    through the slab onto the terrain inside the plinth. The lattice also
    shipped `collision_faces=("top",)` only, so the 1.88 m plinth had no flanks
    either and its edge nodes are 5.4 m apart - wider than a car.

    What is left is the chord error of the skirt's own sampling at the diagonal
    lobes, 0.042 m, and it is outboard of the kerb the deck already carries.
    """

    faces = collision_faces_authored()
    drivable = collision_faces_authored(ground_model="asphalt")
    deck = [
        triangle
        for triangle in drivable
        if all(abs(point[2] - S.DECK_Z) < 0.05 for point in triangle)
    ]
    assert len(deck) >= 32, len(deck)
    visible = [
        point
        for materials in load_dae().values()
        for points in materials.values()
        for point in points
        if abs(point[2] - S.DECK_Z) < 0.005
    ]
    assert len(visible) >= 100, len(visible)
    worst = max(min(surface_gap(point, triangle) for triangle in drivable) for point in visible)
    assert worst < 0.10, worst

    # ...and the plinth is solid from outside, not an open-sided lattice.
    flanks = [
        triangle
        for triangle in faces
        if all(S.BASE_UNDERSIDE_Z - 0.01 <= point[2] <= S.DECK_Z + 0.01 for point in triangle)
        and len({round(point[2], 3) for point in triangle}) > 1
    ]
    assert len(flanks) >= 16, len(flanks)


def test_each_ramp_drives_where_it_looks() -> None:
    """The cage's ramps ran 0.41 m below the ramps you can see.

    `ramp_wedge` crested at y 12.282 and toed out at 21.282; build_cage()
    crested at `BASE_X / 2 - 2.30` = 10.70 and toed at 19.80 with its last
    row clamped to z 0.04. So the drivable surface sat 0.410 m under the
    visible ramp at the crest, 0.390 m at mid-span, and the outer 1.48 m of
    every ramp had no collision at all. Driving up the kick ramp at the fan is
    the first thing anyone does with this mod, and it was done with the wheels
    buried to the axle. Both now read S.RAMP_CREST_Y.
    """

    faces = collision_faces_authored()
    for name, cx, sy in (
        ("kick_l", -S.KICK_RAMP_X, 1.0),
        ("kick_r", S.KICK_RAMP_X, 1.0),
        ("rear", S.REAR_RAMP_X, -1.0),
    ):
        station = S.RAMP_CREST_Y
        while station <= S.RAMP_CREST_Y + S.RAMP_RUN + 1e-9:
            fraction = (station - S.RAMP_CREST_Y) / S.RAMP_RUN
            visible = S.DECK_Z * (1.0 - fraction)
            height = plan_height((cx, sy * station, visible), faces)
            assert height is not None, (name, station)
            assert abs(height - visible) < 0.05, (name, station, height, visible)
            station += 0.5


# ---------------------------------------------------------------------------
# The stop pad.
# ---------------------------------------------------------------------------
def test_the_stop_pad_is_not_the_floor_you_have_to_park_on() -> None:
    """Centred on the console bay, the pad WAS the console.

    x 4.20..7.60 over the rear service ramp's own 3.00..10.20 centre lane and
    y 5.60..11.20 bracketing the console's own station, in Contains mode: a
    1.9 m car tracking the ramp centreline is entirely inside its x-window and
    a 4.5 m car is inside its y-window for any centre in a 1.1 m band. So the
    only floor you could reach the controls from was the floor that switched
    the fan off, and no amount of resetting the dwell on a press could fix
    that - the car is still parked, still slow, still contained on the next
    frame.
    """

    pad = S.TRIGGERS["stop_pad"]
    cx, cy, _cz = pad["center"]
    width, depth, _height = pad["dimensions"]
    pad_x = (cx - width / 2.0, cx + width / 2.0)
    ramp_x = (S.REAR_RAMP_X - S.RAMP_W / 2.0, S.REAR_RAMP_X + S.RAMP_W / 2.0)
    assert pad_x[0] > ramp_x[1] or pad_x[1] < ramp_x[0], (pad_x, ramp_x)
    for button in S.PANEL_BUTTONS:
        bx, by, _bz = button["position"]
        near_x = min(max(bx, pad_x[0]), pad_x[1])
        near_y = min(max(by, cy - depth / 2.0), cy + depth / 2.0)
        assert math.hypot(bx - near_x, by - near_y) > 6.0, button["id"]

    # And it has to be over real deck, or parking on it is impossible.
    faces = collision_faces_authored()
    for sx in (-0.45, 0.0, 0.45):
        for sy in (-0.45, 0.0, 0.45):
            corner = (cx + sx * width, cy + sy * depth, S.DECK_Z)
            height = plan_height(corner, faces)
            assert height is not None and abs(height - S.DECK_Z) < 0.05, corner


def behavior_chunk():
    """The SHIPPED behaviour, loaded standalone with the engine stubbed out."""

    lupa = pytest.importorskip("lupa")
    path = PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / S.MOD_ID / "runtime.lua"
    if not path.is_file():
        pytest.skip("giant_fan is not built")
    source = path.read_text(encoding="utf-8")
    tunables = source[source.index("local B = {") :]
    tunables = tunables[: tunables.index("\n}") + 2].replace("local B = {", "B = {", 1)
    chunk = source[
        source.index("local behavior = {}") : source.index("local function synchronizeInstallation")
    ].replace("local behavior = {}", "behavior = {}", 1)

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(tunables)
    lua.execute(
        """
        MESSAGES = {}
        SPEED = 0.0
        OCCUPANT = {getVelocity = function() return {length = function() return SPEED end} end}
        CONTAINED = false
        function showMessage(message) MESSAGES[#MESSAGES + 1] = message end
        function firstOccupant(state, zone)
          if zone == "stop_pad" and CONTAINED then return OCCUPANT end
          return nil
        end
        function exactVehicle() return nil end
        function eligibleSubject() return false end
        function addSubjectVelocity() return false end
        function finiteVector3() return true end
        function nodeWorldPosition() return nil end
        function emitEvent() end
        function emitError() end
        function zoneOccupants() return {} end
        FAN_AXIS_FRONT, FAN_AXIS_REAR = "front", "rear"
        STATE = {propId = 1, behavior = {}}
        function _dial() return STATE.behavior.dial end
        function _contain(value) CONTAINED = value end
        function _run(seconds)
          for _ = 1, math.floor(seconds * 60) do behavior.update(STATE, 1/60, 1/60) end
        end
        """
    )
    loader = lua.eval("function(src) return load(src, 'behavior') end")(chunk)
    assert loader, "the shipped behaviour chunk does not compile"
    loader()
    return lua


def test_the_stop_pad_cannot_cancel_the_press_that_started_the_fan() -> None:
    """Park at the controls, press SPEED, and the pad used to switch it off.

    The shipped guard only stopped dwell banking while the dial was 0. The
    instant a press set the dial to 3 the accumulator started again under a car
    that had not moved, and 0.417 s later the pad called dialOff() and printed
    "STOP PAD - the fan is winding down." - a message that reads like a fault.
    The pad now ARMS ON ENTRY and only if the fan was already running, so a car
    that was standing there when the fan started can never trip it.
    """

    lua = behavior_chunk()
    globals_ = lua.globals()
    globals_.behavior.init(globals_.STATE)
    globals_._contain(True)
    globals_.behavior.onEnter(globals_.STATE, "stop_pad", globals_.OCCUPANT)
    globals_._run(1.0)
    assert globals_._dial() == 0
    globals_.behavior.onPanelButton(globals_.STATE, "dial_cw")
    assert globals_._dial() == 3
    globals_._run(5.0)
    assert globals_._dial() == 3, list(globals_.MESSAGES.values())


def test_the_stop_pad_still_stops_a_running_fan_you_drive_onto() -> None:
    """Which is the only thing the pad is for."""

    lua = behavior_chunk()
    globals_ = lua.globals()
    globals_.behavior.init(globals_.STATE)
    globals_.behavior.onPanelButton(globals_.STATE, "dial_cw")
    assert globals_._dial() == 3
    globals_._contain(True)
    globals_.behavior.onEnter(globals_.STATE, "stop_pad", globals_.OCCUPANT)
    globals_._run(0.45)
    assert globals_._dial() == 0, list(globals_.MESSAGES.values())


def test_the_tilt_pin_carries_its_worst_load_inside_the_force_ceiling() -> None:
    """NODE_FORCE_CEIL was a comment, not a limit - and the tilt pin broke it.

    The worst case is the machine's own headline combination: dial 3 with the
    sweep on. Yawing a spinning rotor puts Omega x H about the axis
    perpendicular to both, which here is the TRUNNION axis, so the tilt hydro
    carries it on top of the head's weight - and it is the bigger of the two.
    Every term is recomputed from the BUILT cage: the spin inertia by summing
    m*r^2 over the rotor and blade groups about the hub-axis pair, the peak yaw
    rate by driving the shipped sweep waveform through the BUILT crank, the
    weight moment off the built node table.

    Raising the hydro's spring does nothing for this: the force is fixed by
    moment equilibrium. The node has to be heavy enough to carry it.
    """

    part = load_jbeam()
    nodes = node_table(part)
    rig = tilt_rig()
    trunnion_z = rig["trunnion_z"]

    spin_inertia = sum(
        entry.get("nodeWeight", 125.0)
        * (entry["pos"][0] ** 2 + (entry["pos"][2] - trunnion_z) ** 2)
        for entry in nodes.values()
        if entry.get("group") in (f"{S.MOD_ID}_rotor", f"{S.MOD_ID}_blade")
    )
    assert spin_inertia > 2.0e6, spin_inertia

    sweep = hydro_row(part, "fanSweep")[2]

    def yaw_for(command: float) -> float:
        target = (
            1.0 + command * (sweep["outLimit"] - 1.0)
            if command >= 0.0
            else 1.0 + command * (1.0 - sweep["inLimit"])
        )
        lo, hi = math.radians(-90.0), math.radians(90.0)
        for _ in range(120):
            mid = 0.5 * (lo + hi)
            if built_yaw_ratio(nodes, mid) < target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    steps = 720
    step = S.SWEEP_PERIOD_S / steps
    angles = [yaw_for(math.sin(2.0 * math.pi * i / steps)) for i in range(steps)]
    peak_rate = max(abs(angles[(i + 1) % steps] - angles[i]) / step for i in range(steps))

    gyroscopic = peak_rate * spin_inertia * S.OMEGA_3
    weight = rig["mass"] * GRAVITY * abs(rig["cg_y"])
    lever = (S.tilt_length_ratio(1e-7) - S.tilt_length_ratio(-1e-7)) * S.TILT_REST_LEN / 2e-7
    force = (weight + gyroscopic) / lever

    pin = nodes[f"{S.MOD_ID}_tilt_pin"]["nodeWeight"]
    anchor = nodes[f"{S.MOD_ID}_tilt_anchor"]["nodeWeight"]
    for weight_kg in (pin, anchor):
        assert force / weight_kg <= S.NODE_FORCE_CEIL, (force, weight_kg, force / weight_kg)


# ---------------------------------------------------------------------------
# Every visible body must be able to hit a car.
#
# Found by the artifact critic panel, 2026-08-25, after the whole suite was
# green: the head, the yoke and the rotor collar carried collision NODES and
# no collision TRIANGLES. BeamNG collides node against triangle, so a body
# with no triangles can only push a car when one of its own nodes happens to
# land inside the car shell - and the housing rings are 5.70 m apart and the
# yoke arms were two nodes 6.84 m apart. A car-sized box fitted between them
# touching nothing. 153 tonnes of the machine you can see was a ghost.
#
# That is not a quality issue, it is the user's actual requirement: "a
# collision mesh so vehicles running into it could get wrecked".
# ---------------------------------------------------------------------------
def test_every_collidable_body_owns_collision_triangles() -> None:
    part = load_jbeam()
    nodes = node_table(part)
    collidable: dict[str, int] = {}
    for node in nodes.values():
        if node["collision"]:
            collidable[node["group"]] = collidable.get(node["group"], 0) + 1
    owns: dict[str, int] = {}
    for row in part["triangles"][1:]:
        group = nodes[row[0]]["group"]
        owns[group] = owns.get(group, 0) + 1
    for group, count in sorted(collidable.items()):
        if count <= 4:
            continue  # too few nodes to be a surface anyway
        assert owns.get(group, 0) > 0, (
            f"{group} has {count} collision nodes and NO collision triangles: "
            "a car passes straight through it"
        )


def test_no_car_sized_gap_exists_inside_the_motor_housing() -> None:
    """The check that actually reproduces the bug.

    Counting triangles would pass the moment ONE existed. What mattered was
    that the housing's three node rings are 5.70 m apart and the yoke arms
    were two nodes 6.84 m apart, so a car-sized box fitted BETWEEN them and
    touched nothing. This probes the real hull - the housing's own cone and
    each yoke arm's own box, both taken from the authored dimensions - rather
    than an axis-aligned bounding box, which would also sweep the empty air
    around the plunger and report false gaps.
    """

    part = load_jbeam()
    nodes = node_table(part)
    car = (4.5, 1.9, 1.5)

    def group_geometry(group: str):
        pts = [n["pos"] for n in nodes.values() if n["group"] == group]
        tris = [
            tuple(nodes[row[i]]["pos"] for i in range(3))
            for row in part["triangles"][1:]
            if nodes[row[0]]["group"] == group
        ]
        return pts, tris

    def covered(centre, pts, tris) -> bool:
        lo = [centre[i] - car[i] / 2 for i in range(3)]
        hi = [centre[i] + car[i] / 2 for i in range(3)]
        for p in pts:
            if all(lo[i] <= p[i] <= hi[i] for i in range(3)):
                return True
        for tri in tris:
            tlo = [min(v[i] for v in tri) for i in range(3)]
            thi = [max(v[i] for v in tri) for i in range(3)]
            if all(tlo[i] <= hi[i] and thi[i] >= lo[i] for i in range(3)):
                return True
        return False

    # The vehicle frame is the authored frame yawed 180 degrees about Z, so an
    # authored +Y lands at vehicle -Y. Probe in vehicle space, which is what
    # the jbeam holds.
    head_pts, head_tris = group_geometry(f"{S.MOD_ID}_head")
    misses = []
    for iy in range(9):
        y_auth = S.HSG_REAR_Y + (S.HSG_FRONT_Y - S.HSG_REAR_Y) * iy / 8.0
        radius = S.HSG_R_REAR + (S.HSG_R_FRONT - S.HSG_R_REAR) * ((y_auth - S.HSG_REAR_Y) / S.HSG_L)
        for ix in range(-2, 3):
            for iz in range(-2, 3):
                x = radius * ix / 3.0
                z = S.HUB_Z + radius * iz / 3.0
                if math.hypot(x, z - S.HUB_Z) > radius * 0.92:
                    continue
                centre = (-x, -y_auth, z)  # authored -> vehicle
                if not covered(centre, head_pts, head_tris):
                    misses.append(tuple(round(v, 2) for v in centre))
    assert not misses, (
        "motor housing: a car-sized box fits inside it without touching any "
        f"node or triangle at {misses[:4]}"
    )

    yoke_pts, yoke_tris = group_geometry(f"{S.MOD_ID}_yoke")
    misses = []
    for sx in (-1.0, 1.0):
        for iz in range(7):
            z = S.YAWPIVOT_HI_Z + (S.HUB_Z - S.YAWPIVOT_HI_Z) * iz / 6.0
            centre = (-sx * S.YOKE_HALF_SPAN, 0.0, z)
            if not covered(centre, yoke_pts, yoke_tris):
                misses.append(tuple(round(v, 2) for v in centre))
    assert not misses, (
        "yoke arm: a car-sized box fits inside it without touching any node "
        f"or triangle at {misses[:4]}"
    )
