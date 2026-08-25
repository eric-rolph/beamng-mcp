"""Swept-volume gate for the Spin Launch launch tube.

The tube is the only thing on this machine that moves THROUGH the machine:
33 m of barrel pivoted about the chamber axis, sweeping the whole x ~ 0 plane
above a 43 m disc. Nothing else in the evidence chain can see a fixture
standing in its path. The static pack gates check hashes, cages and
materials; the headless gate checks the state machine; the live gate drives a
car - and all three of them, plus every render and the selector thumbnail,
sit at ELEVATION 50, which is the FIRST of eight rungs that clears the
crown. The warning beacon spent its whole life 0.115 m off the bore axis at
rung 1 and nothing noticed.

The containment argument this file leans on: phi = tilt - TILT_REF_DEG is
monotonic in the setting, so the union of the eight poses is bounded by the
two END rungs. Everything is still checked at all eight, cheaply, but the
first test asserts the monotonicity itself - if the tube ever stops being a
single rigid rotation, this file's reasoning is void and it should say so
rather than pass.

THE ORBIT IS GATED HERE TOO NOW, and it never was. Everything above is about
the swept TUBE; nothing in this suite ever measured a distance against the
15.9 m circle the payload actually rides, which is a different surface with a
different set of neighbours. See test_nothing_solid_stands_in_the_payload_s
_orbit below, and the tunnel-mouth finding in its docstring.

ONE DELIBERATE EXEMPTION, stated so nobody has to rediscover it: the shingle
leaves are NOT in SWEPT_KEEPOUT. build_slot models them CLOSED across the
whole arc by design ("letting the apron sit proud gets the look with no
animation and no moving seal to bake"), so a steel leaf crosses the bore
centreline at station ~14.6 at every rung (-2.550 m from the bore surface).
That is the declared cheat, not a regression. If someone later gives the
leaves a real aperture, add them to the table and this gate will hold them
to it. The bore LINER carries the same convention for the same reason: its
slot omission was closed rather than widened, so there is no BORE_SLOT_DEG
here to test.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
from xml.etree import ElementTree

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "spin_launch"


def load_spec():
    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader_spec = importlib.util.spec_from_file_location(
        "spin_launch_clearance_spec", spec_path)
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)
    return module


SPEC = load_spec()


def _span(half, steps):
    return [-half + 2.0 * half * k / (steps - 1) for k in range(steps)]


def _sample_box(centre, axes, halves, steps=7):
    """Corner-and-face sampling of an oriented box, in world coordinates."""

    for a in _span(halves[0], steps):
        for b in _span(halves[1], steps):
            for c in _span(halves[2], steps):
                yield tuple(
                    centre[k] + axes[0][k] * a + axes[1][k] * b
                    + axes[2][k] * c
                    for k in range(3)
                )


def _ring(theta_deg, radius, x=0.0):
    angle = math.radians(theta_deg)
    return (x, radius * math.cos(angle),
            SPEC.HUB_Z + radius * math.sin(angle))


def _jamb_points(theta_deg):
    angle = math.radians(theta_deg)
    radial = (0.0, math.cos(angle), math.sin(angle))
    tangent = (0.0, -math.sin(angle), math.cos(angle))
    return _sample_box(
        _ring(theta_deg, SPEC.SLOT_JAMB_R),
        ((1.0, 0.0, 0.0), tangent, radial),
        (SPEC.OUTER_HALF_X + 0.35, SPEC.SLOT_JAMB_HALF_T,
         SPEC.SLOT_JAMB_HALF_R),
    )


def test_the_sweep_is_bounded_by_the_two_end_rungs():
    """The containment argument the rest of this module rests on.

    Probed at the beacon's ORIGINAL home, which is the point that proves it:
    clearance there has to rise monotonically with elevation, worst at rung 1.
    """

    probe = (0.0, 4.2, SPEC.CHAMBER_TOP_Z + 0.55)
    clearances = [SPEC.tube_clearance(t, probe) for t in SPEC.TILT_STEPS_DEG]
    assert clearances == sorted(clearances)
    assert clearances[0] == pytest.approx(min(clearances))


def test_no_authored_fixture_enters_the_swept_bore():
    """The hard one: nothing may be in the tube a car flies down at 182 m/s."""

    for name, point, radius in SPEC.SWEPT_KEEPOUT:
        for tilt in SPEC.TILT_STEPS_DEG:
            gap = SPEC.bore_clearance(tilt, point) - radius
            assert gap >= SPEC.SWEPT_CLEARANCE_MIN, (
                f"{name} is {gap:.3f} m from the bore at elevation {tilt:g}")


def test_no_authored_fixture_touches_the_tube():
    for name, point, radius in SPEC.SWEPT_KEEPOUT:
        for tilt in SPEC.TILT_STEPS_DEG:
            gap = SPEC.tube_clearance(tilt, point) - radius
            assert gap >= SPEC.SWEPT_CLEARANCE_MIN, (
                f"{name} is {gap:.3f} m from the tube at elevation {tilt:g}")


def test_the_beacon_clears_the_tube_at_the_lowest_rung():
    """The regression this module was written for.

    BEACON_PIVOT = (0, 4.2, CHAMBER_TOP_Z + 0.55) put the rotating head, the
    pedestal and a 2.2 x 2.2 m base plate INSIDE the barrel at elevations 34
    and 39, and inside the rib flanges at 45.
    """

    lowest = SPEC.TILT_STEPS_DEG[0]
    for point in (
        SPEC.BEACON_PIVOT,
        (0.0, SPEC.BEACON_PIVOT[1], SPEC.BEACON_PIVOT[2] - 1.50),
        (0.0, SPEC.BEACON_PIVOT[1], SPEC.BEACON_PIVOT[2] + 0.56),
    ):
        assert SPEC.tube_clearance(lowest, point) > 0.0
    # And it must be clockwise of the slot, not just clear of the barrel.
    assert SPEC.BEACON_THETA_DEG < SPEC.SLOT_DEG[0]


def test_the_slot_is_wide_enough_at_both_end_rungs():
    """The jambs are the declared edges of the opening; the tube may not
    reach them. Authored at 70/134 the barrel was 1.482 m inside the lower
    jamb at 34 and 0.893 m inside the upper one at 72."""

    for theta in SPEC.SLOT_DEG:
        for point in _jamb_points(theta):
            for tilt in SPEC.TILT_STEPS_DEG:
                assert SPEC.tube_clearance(tilt, point) >= (
                    SPEC.SWEPT_CLEARANCE_MIN - 1e-6), (
                    f"jamb at {theta:.3f} deg fouls the tube at {tilt:g}")


def test_the_apron_sits_proud_of_every_shingle():
    for index in range(SPEC.SLOT_LEAVES):
        leaf = SPEC.SLOT_LEAF_R0 + SPEC.SLOT_LEAF_STEP * index
        assert SPEC.APRON_R > leaf + 0.04


def test_the_baffle_case_begins_outboard_of_the_shell_furniture():
    inner = (SPEC.PAYLOAD_R + SPEC.BAFFLE_RADIAL
             - SPEC.BAFFLE_RIB_HALF_RADIAL)
    reach = math.hypot(inner, SPEC.BAFFLE_S0 - SPEC.BAFFLE_RIB_HALF_AXIAL)
    assert reach >= SPEC.SLOT_RAIL_R1 + SPEC.SWEPT_CLEARANCE_MIN - 1e-6
    # Outboard, where tube_radial's docstring says the case hangs.
    assert SPEC.BAFFLE_RADIAL > 0.0


# --- the payload's orbit ---------------------------------------------------
# THE RADIAL RING, AND WHY THIS GATE EXISTS.
#
# A period-2 radial oscillation was measured live on the drive-in shot,
# bit-identical over four runs: the sign of the deviation alternates on every
# single sample of the tether field's own update, which at dtSim 0.10 s is
# 5 Hz - the Nyquist frequency of that loop, which a loop cannot resolve about
# itself. Velocity collapses first (36.2 -> 19.5 -> 10.2 m/s) and the radius
# flies afterwards. Onset is the sample after theta ~= 234, and
# TUNNEL_FLOOR_DEG is 233.981: the airlock mouth. The same passage one
# revolution earlier at 10.8 m/s is uneventful; it fires at 37 m/s. It decays
# inside 1 s, `hold` and `release` sit in a 0.07 m band, and a sweep of the
# field update period across 4x on a RESEATED payload shows no ring at any
# clock - so it belongs to the drive-in shot specifically and the shot itself
# is untouched.
#
# The angular coincidence made a physical interaction at the tunnel mouth the
# obvious suspect, and the suite could not answer it, because nothing here
# had ever measured anything against the ORBIT. So it does now, and the
# answer is NO. Measured 2026-08-25 on the shipped cage and the shipped
# collision parts:
#
#   nearest cage node to the orbit, theta 200-270   3.429 m  (tunnel_top,
#                                                    at |x| = 3.40)
#   nearest anything at TUNNEL_FLOOR_DEG itself      4.450 m  (the bore ring
#                                                    at r = 20.35)
#   deck, dropped                                    4.486 m
#   door, hooded / filling the portal        3.123 / 3.483 m
#
# and the cage's bore ring is OMITTED across CAGE_TUNNEL_DEG =
# (212.964, 238.764) anyway, so at the mouth there is nothing there to hit
# even in principle. Nothing is clipping. The ring is not a collision event,
# and a derivative damping term is not the answer either: for a period-2 mode
# the first difference is IN PHASE with the deviation, so a damping term is
# proportional gain of 2*damp/dt and the textbook critical value sits an
# order of magnitude past a gain*dt already measured to eject the payload.
# The field is left alone. This gate is what the investigation bought.
#
# ONE DECLARED EXEMPTION: the deck in its PARKED pose is 0.947 m from the
# orbit, because it is the cradle bed - that is where the car was sitting.
# The sequence guarantees it has dropped before the tether turns
# (test_the_chamber_actually_seals_and_evacuates asserts deck_drop is at
# BEHAVIOR["deck_drop"] by `spinup`), so the pose measured here is the
# dropped one.

# A BeamNG road car presents hypot(half_width, half_height) =
# hypot(0.95, 0.75) = 1.21 m PERPENDICULAR to its direction of travel, which
# is the only direction that matters against a circle it is sweeping. Plus
# the pack's own SWEPT_CLEARANCE_MIN of 0.60 that is 1.81 m, rounded up.
ORBIT_KEEPOUT_MIN = 2.00


def _orbit_distance(point):
    """Distance from an authored point to the payload's orbit CIRCLE.

    The payload sweeps the whole circle, so the tangential coordinate is not
    a clearance at all: what matters is how far the point is from the circle
    in the (radial, axial) plane.
    """

    radius = math.hypot(point[1], point[2] - SPEC.HUB_Z)
    return math.hypot(radius - SPEC.PAYLOAD_R, point[0])


def _cage_nodes():
    """Every jbeam node, converted to the authored frame.

    The jbeam is in the VEHICLE frame - authored with x and y negated - which
    the shipped PROP_REF_OFFSET pins: the ref node is the ramp foot at
    authored (0, RAMP_Y0, 0) with RAMP_Y0 = -76, and the constant reads
    (~0, +76, 0).
    """

    jbeam = json.loads(
        (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / SPEC.MOD_ID
         / f"{SPEC.MOD_ID}.jbeam").read_text(encoding="utf-8"))
    section = jbeam[SPEC.MOD_ID]
    nodes = {
        row[0]: (-float(row[1]), -float(row[2]), float(row[3]))
        for row in section["nodes"]
        if isinstance(row, list) and row[0] != "id"
    }
    assert nodes, "the shipped jbeam has no nodes"
    # Only nodes that carry a collision triangle can be hit at all.
    collides = set()
    for row in section.get("triangles", []):
        if isinstance(row, list) and row[0] != "id1":
            collides.update(row[:3])
    return {name: position for name, position in nodes.items()
            if name in collides}


def _part_points(name, pivot, drop):
    """A collision part's vertices in the authored frame, at a given pose.

    Both this machine's collision parts move by pure vertical translation,
    so a pose is one number.
    """

    path = (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / SPEC.MOD_ID
            / f"{SPEC.MOD_ID}_{name}.dae")
    points = []
    for element in ElementTree.parse(path).iter():
        if element.tag.split("}")[-1] != "float_array":
            continue
        if not (element.get("id") or "").endswith("positions-array"):
            continue
        values = [float(token) for token in element.text.split()]
        points.extend(
            (x + pivot[0], y + pivot[1], z + pivot[2] - drop)
            for x, y, z
            in zip(values[0::3], values[1::3], values[2::3], strict=True))
    assert points, f"no vertex positions in {path.name}"
    return points


def test_nothing_solid_stands_in_the_payload_s_orbit():
    """THE GATE THIS SUITE NEVER HAD.

    bore_clearance and tube_clearance are both TUBE-frame: they answer "is
    the barrel clear", which is a different question from "is the circle the
    car rides clear". The airlock mouth is 4.5 m outboard of that circle and
    the cage omits its bore ring across the whole tunnel arc, so nothing at
    TUNNEL_FLOOR_DEG can be touched - but until this test ran, nothing in the
    evidence chain could say so.
    """

    worst = min(
        (_orbit_distance(position), name)
        for name, position in _cage_nodes().items())
    assert worst[0] >= ORBIT_KEEPOUT_MIN, (
        f"cage node {worst[1]} is {worst[0]:.3f} m from the orbit")

    # ...and the two collision PARTS, in the poses a stale bake can leave
    # them at while the tether is turning. The deck's parked pose is the
    # cradle bed and is exempt by construction - see the block above.
    poses = (
        ("deck", (0.0, 0.0, SPEC.DECK_Z), (SPEC.BEHAVIOR["deck_drop"],)),
        ("door", (0.0, SPEC.TUNNEL_Y_OUT - 0.35, SPEC.DECK_Z),
         (0.0, SPEC.BEHAVIOR["door_travel"])),
    )
    for name, pivot, drops in poses:
        for drop in drops:
            points = _part_points(name, pivot, drop)
            gap = min(_orbit_distance(point) for point in points)
            assert gap >= ORBIT_KEEPOUT_MIN, (
                f"{name} at drop {drop:g} is {gap:.3f} m from the orbit")


def test_the_airlock_mouth_is_nowhere_near_the_orbit():
    """The angular coincidence the radial ring investigation turned on.

    TUNNEL_FLOOR_DEG is the angle at which the DECK PLANE meets the chamber
    at r = CHAMBER_R. It is not a radius near PAYLOAD_R and never was: the
    two differ by CHAMBER_R - PAYLOAD_R = 4.500 m by construction, and the
    cage omits its bore ring across the whole tunnel arc on top of that.
    """

    assert SPEC.CHAMBER_R - SPEC.PAYLOAD_R == pytest.approx(4.5, abs=1e-9)
    # The constant really is the deck plane's intersection, not something
    # that happens to be near the orbit.
    assert _ring(SPEC.TUNNEL_FLOOR_DEG, SPEC.CHAMBER_R)[2] == pytest.approx(
        SPEC.DECK_Z, abs=1e-9)
    # Nothing in the cage lives inside the omitted arc at bore radius.
    low, high = SPEC.CAGE_TUNNEL_DEG
    for name, position in _cage_nodes().items():
        theta = math.degrees(math.atan2(
            position[2] - SPEC.HUB_Z, position[1])) % 360.0
        radius = math.hypot(position[1], position[2] - SPEC.HUB_Z)
        if low + 1e-6 < theta < high - 1e-6:
            assert abs(radius - SPEC.CAGE_BORE_R) > 1e-6, (
                f"{name} is a bore-ring node inside the omitted tunnel arc")


def _tube_mesh_points():
    """Vertices of the SHIPPED launch-tube mesh, in its own authored frame.

    Part meshes are authored about their own pivot, and the tube's pivot IS
    the hub, so (y, z) here are already hub-relative and hypot(y, z) is the
    chamber radius of a point on the barrel.
    """

    path = (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / SPEC.MOD_ID
            / f"{SPEC.MOD_ID}_tube.dae")
    points = []
    for element in ElementTree.parse(path).iter():
        if element.tag.split("}")[-1] != "float_array":
            continue
        if not (element.get("id") or "").endswith("positions-array"):
            continue
        values = [float(token) for token in element.text.split()]
        points.extend(zip(values[0::3], values[1::3], values[2::3], strict=True))
    assert points, f"no vertex positions in {path.name}"
    return points


def test_the_roller_trucks_are_built_on_the_rail_the_slot_carries():
    """THE ROLLERS, MEASURED OFF THE SHIPPED BARREL.

    What this test used to do could not fail. ``roller_radial`` SOLVES the
    radial offset as ``sqrt(ROLLER_RUN_R^2 - station^2) - PAYLOAD_R``, and the
    assertion re-substituted it:
    ``hypot(PAYLOAD_R + radial, station) == ROLLER_RUN_R`` reduces to
    ``hypot(sqrt(R^2 - s^2), s) == R``, which is true for every R. Setting
    ROLLER_RUN_R to 999.0 still passed it, and so did the two lines under it:
    SLOT_RAIL_R0 is DEFINED as ROLLER_RUN_R + ROLLER_R and LID_RIB_R1 as
    ROLLER_RUN_R - ROLLER_R - SWEPT_CLEARANCE_MIN, so both reduced to
    ``x == x`` and ``MIN >= MIN``.

    The regression it was written for is real - the three trucks were once
    authored ON the bore axis, which on a straight beam riding a curved rail
    put them at 20.4, 21.6 and 21.9, so one missed the rail by 1.5 m, one cut
    0.09 m into it and all three ploughed the rib fan - and the way to catch
    that is to measure the barrel that ships. Each truck's wheel has to be a
    disc of radius ROLLER_R centred on the rail's running locus, on both
    flanks, at the station the collar puts it.
    """

    assert len(SPEC.ROLLER_OFFSETS) == len(SPEC.ROLLER_RADIAL), (
        "a truck grew without a radial offset to place it")

    points = _tube_mesh_points()
    theta = math.radians(SPEC.release_theta_deg(SPEC.TILT_REF_DEG))
    axial = (math.sin(theta), -math.cos(theta))       # along the bore
    # Everything outboard of the lid plates that sits in the rail's own
    # radial band. The wheels are the only barrel geometry out there.
    band = [
        point for point in points
        if abs(point[0]) > SPEC.OUTER_HALF_X + 0.05
        and SPEC.ROLLER_RUN_R - SPEC.ROLLER_R - 0.02
        <= math.hypot(point[1], point[2])
        <= SPEC.ROLLER_RUN_R + SPEC.ROLLER_R + 0.02
    ]
    assert band, "the shipped tube has no geometry on the rail at all"

    seen = 0
    for offset in SPEC.ROLLER_OFFSETS:
        station = SPEC.TUBE_PIERCE_S + offset
        for flank in (-1.0, 1.0):
            wheel = [
                point for point in band
                if point[0] * flank > 0.0
                and abs(point[1] * axial[0] + point[2] * axial[1] - station)
                <= 0.35
            ]
            assert wheel, f"no roller at station {station:.3f} on flank {flank:+.0f}"
            seen += 1
            radii = [math.hypot(point[1], point[2]) for point in wheel]
            centre = 0.5 * (min(radii) + max(radii))
            half = 0.5 * (max(radii) - min(radii))
            # The wheel is centred ON the running locus. Measured to 0.1 mm
            # on the shipped barrel: 21.8500 / 21.8500 / 21.8501 m.
            assert centre == pytest.approx(SPEC.ROLLER_RUN_R, abs=1e-3), (
                station, centre)
            # ...and it is ROLLER_R across. The tolerance is 10 mm because a
            # faceted cylinder's VERTICES sample its circle, so the measured
            # radial extremes depend on where the facets fall: 0.2999,
            # 0.2989 and 0.2935 m for the three trucks.
            assert half == pytest.approx(SPEC.ROLLER_R, abs=0.01), (station, half)
            # ...which puts its running face on the rail's, and never through
            # it: this one is one-sided on purpose, because a wheel that
            # reaches PAST SLOT_RAIL_R0 is cutting into the rail.
            assert max(radii) <= SPEC.SLOT_RAIL_R0 + 1e-3, (station, max(radii))
            assert max(radii) >= SPEC.SLOT_RAIL_R0 - 0.01, (station, max(radii))
            # ...and it straddles the rail in x rather than hanging beside it.
            assert min(abs(point[0]) for point in wheel) < SPEC.SLOT_RAIL_X
            assert max(abs(point[0]) for point in wheel) > SPEC.SLOT_RAIL_X
            # ...and its underside still clears the rib fan.
            assert min(radii) - SPEC.LID_RIB_R1 >= (
                SPEC.SWEPT_CLEARANCE_MIN - 0.01), (station, min(radii))
    assert seen == 2 * len(SPEC.ROLLER_OFFSETS)
    # Nothing ELSE of the barrel is allowed into the rail's band out there:
    # a fourth truck nobody declared would be measured by nothing.
    stations = sorted({
        round(point[1] * axial[0] + point[2] * axial[1], 3) for point in band})
    clusters = 1
    for previous, following in zip(stations, stations[1:]):
        if following - previous > 0.5:
            clusters += 1
    assert clusters == len(SPEC.ROLLER_OFFSETS), (clusters, stations)
