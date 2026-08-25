"""Geometry and physics gates specific to COLOSSUS 10350/80R457.

The shared pack gates in ``test_giant_props_pack.py`` check that the jbeam
agrees with the handoff, that materials are covered and that the ZIP matches
its lock. None of that can tell you whether a 28 m tire will ROLL, and this
prop is the only one in the pack whose whole premise is that it does. These
gates check the things that premise actually rests on:

* the moulded size code and the modelled geometry are the same tire,
* the collision triangles face the right way (the crown outward, the inner
  liner inward) - a reversed panel here is an invisible one-way floor that a
  car falls straight through,
* nothing fixed is inside the volume the tire sweeps as it rolls,
* the beam families are integrable at BeamNG's 2000 Hz,
* the carcass has the inertia the spec's playability solve assumed, and
* the tie-down straps really are the only thing joining the tire to the dock.

Run:  .venv\\Scripts\\python.exe -m pytest -q tests\\test_colossus_tire_geometry.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = REPO_ROOT / "examples" / "giant_props"
EXAMPLE_ROOT = PACK_ROOT / "colossus_tire"

# BeamNG integrates the beam network at a fixed 2000 Hz.
PHYSICS_HZ = 2000.0
DT = 1.0 / PHYSICS_HZ


def load_spec():
    spec_path = EXAMPLE_ROOT / "spec.py"
    loader = importlib.util.spec_from_file_location("colossus_tire_spec", spec_path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def spec():
    return load_spec()


@pytest.fixture(scope="module")
def handoff(spec):
    path = EXAMPLE_ROOT / "authoring" / f"{spec.MOD_ID}.handoff.json"
    if not path.is_file():
        pytest.skip("no authored handoff; run the Blender generator")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def nodes(handoff):
    """Node id -> authored-frame world position (the measured coordinates)."""

    return {node["id"]: node["source_world_position"] for node in handoff["nodes"]}


@pytest.fixture(scope="module")
def by_id(handoff):
    return {node["id"]: node for node in handoff["nodes"]}


# ---------------------------------------------------------------------------
# The size code IS the geometry
# ---------------------------------------------------------------------------
def test_size_code_produces_the_modelled_tire(spec):
    """10350/80R457 must be the tire that was actually built.

    The sidewall moulding prints this code as real extruded geometry. If the
    code and the radii ever drift apart, the prop is a tire with someone
    else's size stamped on it - which is the one mistake a viewer who knows
    tires will catch instantly.
    """

    width_mm, rest = spec.SIZE_CODE.split("/")
    aspect, rim = rest.split("R")
    assert int(width_mm) == spec.SECTION_WIDTH_MM
    assert int(aspect) == spec.ASPECT_RATIO_PCT
    assert int(rim) == spec.RIM_DIAMETER_IN

    assert spec.SECTION_WIDTH == pytest.approx(int(width_mm) / 1000.0)
    assert spec.SECTION_HEIGHT == pytest.approx(spec.SECTION_WIDTH * int(aspect) / 100.0)
    assert spec.BEAD_RADIUS == pytest.approx(int(rim) * 0.0254 / 2.0)
    assert spec.OUTER_RADIUS == pytest.approx(spec.BEAD_RADIUS + spec.SECTION_HEIGHT)


def test_cage_matches_the_authored_radii(spec, nodes):
    """Every cage node sits on the radius its meridian station claims."""

    axle_z = spec.OUTER_RADIUS

    def radius_of(identifier):
        _, y, z = nodes[identifier]
        return math.hypot(y, axle_z - z)

    checks = {
        "bead_l": spec.BEAD_RADIUS,
        "bead_r": spec.BEAD_RADIUS,
        "crn_c": spec.OUTER_RADIUS,
        "lin_c": spec.CAVITY_RADIUS,
        "lin_l": spec.CAVITY_RADIUS,
        "lin_r": spec.CAVITY_RADIUS,
    }
    for station in (0, 7, 19, 31, 44):
        for key, expected in checks.items():
            identifier = f"{spec.MOD_ID}_{key}_j{station:02d}"
            assert radius_of(identifier) == pytest.approx(expected, abs=1e-4), identifier


def test_cavity_clears_a_car(spec):
    """The car has to fit, stand up, and get round the barrel.

    Three separate clearances, all of which have to hold at once, and all of
    which are derived rather than eyeballed.
    """

    # 1. The port opening.
    assert spec.PORT_HEIGHT > spec.CAR_HEIGHT + 1.5, "port too short to drive into"
    assert spec.PORT_ARC_WIDTH > spec.CAR_LENGTH + 1.0, "port too narrow"

    # 2. The floor, which is a cylinder: a rigid 4.5 m car bridges a chord and
    #    only its ends touch. The sagitta is how far its middle sits off the
    #    liner, and it has to stay under the car's ground clearance budget.
    half = spec.CAR_LENGTH / 2.0
    sagitta = spec.CAVITY_RADIUS - math.sqrt(spec.CAVITY_RADIUS**2 - half**2)
    assert sagitta < 0.25, f"cavity floor too tight for a {spec.CAR_LENGTH} m car: {sagitta:.3f} m"

    # 3. Width, for the 90 degree turn onto the barrel.
    assert 2 * spec.LINER_HALF > spec.CAR_LENGTH + 2.0, "no room to turn in the cavity"


def test_the_tire_is_not_a_pancake(spec):
    """A tire standing on its tread is a coin: past a lean angle it goes over.

    Not a failure - it is honest physics and the runtime detects it - but the
    angle must be big enough that flat ground does not tip it, and the spec's
    tipped-detection threshold must be consistent with the real geometry.
    """

    tip_angle = math.atan2(spec.SECTION_HALF, spec.OUTER_RADIUS)
    assert math.degrees(tip_angle) > 14.0, "too tippy to stand up on flat ground"
    # BEHAVIOR["tipped_dot"] is |axle . world_up| once it has fallen; the axle
    # is horizontal when upright, so the threshold must be well clear of zero.
    assert 0.5 < spec.BEHAVIOR["tipped_dot"] < 0.95


# ---------------------------------------------------------------------------
# Collision surfaces
# ---------------------------------------------------------------------------
def _triangle_normal(points):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def test_collision_triangles_face_the_right_way(spec, handoff, nodes):
    """The crown collides from OUTSIDE, the inner liner from INSIDE.

    A jbeam triangle only collides from its front face. Get the crown backwards
    and the tire sinks through the ground; get the liner backwards and the car
    drops through the floor of the cavity. Both are silent - nothing upstream
    of a live test notices - so the winding is measured here against the axle.
    """

    axle = (0.0, 0.0, spec.OUTER_RADIUS)
    crown_keys = ("crn_l", "crn_cl", "crn_c", "crn_cr", "crn_r")
    liner_keys = ("lin_l", "lin_cl", "lin_c", "lin_cr", "lin_r")

    def band_of(identifier):
        stem = identifier[len(spec.MOD_ID) + 1:].rsplit("_j", 1)[0]
        if stem in crown_keys:
            return "crown"
        if stem in liner_keys:
            return "liner"
        return None

    checked = {"crown": 0, "liner": 0}
    for triangle in handoff["triangles"]:
        bands = {band_of(identifier) for identifier in triangle["nodes"]}
        if len(bands) != 1:
            continue
        band = bands.pop()
        if band is None:
            continue
        points = [nodes[identifier] for identifier in triangle["nodes"]]
        normal = _triangle_normal(points)
        centre = [sum(axis) / 3.0 for axis in zip(*points)]
        outward = (centre[0] - axle[0], centre[1] - axle[1], centre[2] - axle[2])
        dot = sum(a * b for a, b in zip(normal, outward))
        if band == "crown":
            assert dot > 0, f"crown triangle faces inward: {triangle['nodes']}"
        else:
            assert dot < 0, f"liner triangle faces outward: {triangle['nodes']}"
        checked[band] += 1

    assert checked["crown"] >= 2 * 4 * spec.STATIONS * 0.9, checked
    assert checked["liner"] >= 2 * 4 * spec.STATIONS * 0.9, checked


def test_no_degenerate_or_duplicated_collision_triangles(handoff, nodes):
    """No slivers, and never the same node triple twice.

    Duplicated triples are the trap ``CageBuilder.add_quad_both`` documents:
    jbeam triangles carry contact state, so a coincident twin spikes the
    solver and pops tires on flat ground.
    """

    seen = set()
    for triangle in handoff["triangles"]:
        identifiers = tuple(triangle["nodes"])
        assert len(set(identifiers)) == 3, identifiers
        key = tuple(sorted(identifiers))
        assert key not in seen, f"duplicated collision triangle: {identifiers}"
        seen.add(key)
        normal = _triangle_normal([nodes[i] for i in identifiers])
        area = 0.5 * math.sqrt(sum(component * component for component in normal))
        assert area > 1e-3, f"degenerate collision triangle ({area:.2e} m2): {identifiers}"


# ---------------------------------------------------------------------------
# Nothing fixed inside the swept volume
# ---------------------------------------------------------------------------
def test_fixed_structure_is_outside_the_swept_volume(spec, handoff, nodes):
    """The dock must be unreachable by the tire, at every rotation.

    The tire translates along Y and spins about X, so the set of points it can
    ever occupy is |x| <= SECTION_HALF. Anything fixed inboard of that gets
    destroyed on the first revolution, and this is the one geometric mistake
    on this prop that no static gate elsewhere would catch. The tire's own
    boarding tongue is the single deliberate exception - it is part of the
    tire, and it lifts away on the first quarter turn.
    """

    margin = 0.20
    offenders = []
    for node in handoff["nodes"]:
        if not node["fixed"]:
            continue
        x = nodes[node["id"]][0]
        if x < spec.SECTION_HALF + margin:
            offenders.append((node["id"], round(x, 3)))
    assert not offenders, (
        "fixed structure inside the tire's swept volume "
        f"(needs x >= {spec.SECTION_HALF + margin:.2f}): {offenders[:8]}"
    )
    assert spec.DOCK_CLEAR_X >= spec.SECTION_HALF + margin


# ---------------------------------------------------------------------------
# Integrability and inertia
# ---------------------------------------------------------------------------
def test_the_cage_is_integrable_at_2000hz(spec, handoff, by_id):
    """omega_max * dt must stay under the explicit integrator's limit.

    THE BOUND IS PER NODE, NOT PER BEAM. A node does not feel one spring, it
    feels every spring meeting it, and for a mass-spring lattice the tight
    Gershgorin bound is omega_max = sqrt(2 * sum_k / m) over that node's
    beams. Testing families one at a time understates it badly: this cage's
    inner-liner nodes carry six belt beams plus three tread beams plus an
    inflation chord, and the per-beam figure said 0.39 while the true bound
    said 2.04 - past the symplectic-Euler limit of 2, i.e. divergent.

    Damping has its own limit: c * dt / m must also stay under 2, or the
    damping term alone flips the velocity sign every step.
    """

    specs = handoff["beam_specs"]
    stiffness: dict[str, float] = {}
    damping: dict[str, float] = {}
    for beam in handoff["beams"]:
        family = specs[beam["spec"]]
        for identifier in beam["nodes"]:
            if by_id[identifier]["fixed"]:
                continue
            stiffness[identifier] = stiffness.get(identifier, 0.0) + float(
                family["beamSpring"]
            )
            damping[identifier] = damping.get(identifier, 0.0) + float(family["beamDamp"])

    worst_node, worst, worst_damp = None, 0.0, 0.0
    for identifier, total in stiffness.items():
        mass = float(by_id[identifier]["weight"])
        omega = math.sqrt(2.0 * total / mass)
        if omega * DT > worst:
            worst, worst_node = omega * DT, identifier
        worst_damp = max(worst_damp, damping[identifier] * DT / mass)

    assert worst < 0.9, (
        f"node {worst_node} sits at omega*dt = {worst:.3f} at {PHYSICS_HZ:.0f} Hz; "
        "the cage will ring itself apart"
    )
    assert worst_damp < 0.9, f"damping alone is unstable: c*dt/m = {worst_damp:.3f}"


def test_rubber_families_are_damped_like_rubber(spec, handoff, by_id):
    """Rubber runs 10-30% of critical; steel cord runs under 10%.

    This is not decoration. Rubber's loss tangent really is that high - it is
    why tires get hot - and a tire carcass modelled with steel damping rings
    like a bell instead of settling.
    """

    specs = handoff["beam_specs"]
    heaviest: dict[str, float] = {}
    for beam in handoff["beams"]:
        family = beam["spec"]
        for identifier in beam["nodes"]:
            weight = float(by_id[identifier]["weight"])
            heaviest[family] = max(heaviest.get(family, weight), weight)

    rubber = {"sidewall", "tread"}
    steel = {"bead", "belt"}
    for family in rubber | steel:
        spring = float(specs[family]["beamSpring"])
        damp = float(specs[family]["beamDamp"])
        mass = heaviest[family]
        critical = 2.0 * math.sqrt(spring * mass)
        ratio = damp / critical
        if family in rubber:
            assert 0.08 < ratio < 0.35, f"{family} damping ratio {ratio:.3f} is not rubber"
        else:
            assert ratio < 0.12, f"{family} damping ratio {ratio:.3f} is not steel cord"


def carcass_nodes(handoff, nodes):
    """Free nodes that are the TIRE, i.e. not the bolted-on gangway."""

    for node in handoff["nodes"]:
        if node["fixed"] or "tongue" in node["id"]:
            continue
        yield node, nodes[node["id"]]


def test_carcass_inertia_supports_the_playability_solve(spec, handoff, nodes):
    """The spec sizes TIRE_MASS from a stated spin-up target. Check it holds.

    ONE TORQUE, NOT TWO. A car standing on the inner liner transmits a normal
    force (radial, zero moment about the axle) and a friction force
    (tangential). Only the friction is a torque. spec.py's first cut added
    "the occupant's weight moment" and "the driven-axle traction" as separate
    sources and so doubled the available torque; they are the same force, and
    the equilibrium condition f = m*g*sin(phi) and the traction bound
    f <= mu*m*g*cos(phi) are the same line, meeting at tan(phi) = mu.

    Everything here is computed from the MEASURED node positions, so the
    docstring's quoted radius of gyration cannot drift away from the layout.
    """

    axle_z = spec.OUTER_RADIUS
    inertia = mass = 0.0
    for node, (_, y, z) in carcass_nodes(handoff, nodes):
        radius = math.hypot(y, axle_z - z)
        inertia += float(node["weight"]) * radius * radius
        mass += float(node["weight"])

    assert mass == pytest.approx(spec.TIRE_MASS, abs=spec.MASS_TOTAL_TOLERANCE)
    gyration = math.sqrt(inertia / mass)
    assert gyration == pytest.approx(
        spec.RADIUS_OF_GYRATION, abs=spec.RADIUS_OF_GYRATION_TOLERANCE
    ), f"measured radius of gyration {gyration:.3f} m"

    climb = math.atan(spec.MU_EFFECTIVE)
    torque = spec.CAR_MASS * spec.GRAVITY * spec.CAVITY_RADIUS * math.sin(climb)
    # THE INERTIA IS THE ROLLING ONE. Nothing holds this axle - the tire rolls
    # on the ground, so the same mass has to be accelerated linearly as well
    # as spun, and the moment balance is about the CONTACT POINT:
    # I_eff = I_cm + M * R^2. Dividing by the axle figure alone is 2.24x
    # optimistic on this layout, which is exactly how the spec's first two
    # cuts promised a spin-up the tire could not deliver.
    effective = inertia + mass * spec.OUTER_RADIUS**2
    alpha = torque / effective
    seconds = (spec.SPINUP_TARGET_KPH / 3.6 / spec.OUTER_RADIUS) / alpha
    lo, hi = spec.SPINUP_SECONDS_BAND
    assert lo <= seconds <= hi, (
        f"a stock car takes {seconds:.1f} s to reach {spec.SPINUP_TARGET_KPH:.0f} km/h "
        f"(torque {torque / 1000:.1f} kNm, I_eff = {effective:.3e} kg m2)"
    )


def _relax(handoff, spec, residual=20.0, cap=250_000):
    """Settle the free cage under gravity on a rigid floor, TO CONVERGENCE.

    Damped dynamic relaxation: the standard way to find a static equilibrium
    of a mass-spring network without assembling a stiffness matrix. Ground
    contact is UNILATERAL - a node is pushed up only while it is below z = 0 -
    which is the whole point, because a bilateral solve would happily glue the
    tire to the floor and report a contact patch that does not exist.

    IT RUNS TO A RESIDUAL, not to a step count. A fixed 6,000 steps stopped
    while the ground was still carrying 37 kN of a 103 kN weight: the tire was
    a third of the way down and every measurement taken off it - the contact
    patch, the gangway's sag, the cone of the carcass - was of a transient.
    The gate that missed the gangway collapse missed it here.
    """

    import numpy as np

    order = [node["id"] for node in handoff["nodes"]]
    index = {identifier: position for position, identifier in enumerate(order)}
    points = np.array(
        [node["source_world_position"] for node in handoff["nodes"]], dtype=float
    )
    mass = np.array([float(node["weight"]) for node in handoff["nodes"]])
    free = np.array([not node["fixed"] for node in handoff["nodes"]])

    specs = handoff["beam_specs"]
    first = np.array([index[b["nodes"][0]] for b in handoff["beams"]])
    second = np.array([index[b["nodes"][1]] for b in handoff["beams"]])
    spring = np.array([float(specs[b["spec"]]["beamSpring"]) for b in handoff["beams"]])
    rest = np.linalg.norm(points[first] - points[second], axis=1)

    ground_k = 3.0e6
    node_k = np.zeros(len(order))
    np.add.at(node_k, first, spring)
    np.add.at(node_k, second, spring)
    omega = np.sqrt(2.0 * np.maximum(node_k, ground_k) / mass).max()
    step = 0.5 / omega
    velocity = np.zeros_like(points)

    taken = 0
    worst = float("inf")
    while taken < cap:
        delta = points[second] - points[first]
        length = np.linalg.norm(delta, axis=1)
        length = np.where(length < 1e-9, 1e-9, length)
        force = (spring * (length - rest) / length)[:, None] * delta
        total = np.zeros_like(points)
        np.add.at(total, first, force)
        np.add.at(total, second, -force)
        total[:, 2] -= mass * spec.GRAVITY
        below = points[:, 2] < 0.0
        total[below, 2] += -ground_k * points[below, 2]
        acceleration = total / mass[:, None]
        acceleration[~free] = 0.0
        velocity = (velocity + acceleration * step) * 0.98
        points = points + velocity * step
        taken += 1
        if taken % 250 == 0:
            worst = float(np.abs(total[free]).sum(axis=1).max())
            if worst < residual:
                break
    return order, points, free, {"steps": taken, "residual": worst}


def _settled(handoff, spec):
    """A converged settle, and PROOF that it converged.

    The ground has to be carrying the free weight before anything measured off
    the settled pose means anything. Checking that first is the difference
    between a static solution and a snapshot of a falling tire.
    """

    import numpy as np

    order, points, free, report = _relax(handoff, spec)
    index = {identifier: position for position, identifier in enumerate(order)}
    mass = np.array([float(node["weight"]) for node in handoff["nodes"]])
    weight = float(mass[free].sum()) * spec.GRAVITY
    ground = float((-3.0e6 * np.minimum(points[:, 2], 0.0)).sum())

    # AND WHAT THE QUAY CARRIES. The free set is not only the tire: the
    # gangway hangs off the port sill and stands on the dock through its
    # landing struts, and the tie-down webbing runs to the anchor posts. Those
    # beams take about 6 kN of the 111 kN, so demanding the GROUND carry all
    # of it would fail a perfectly converged solve. What has to balance is
    # every path to a fixed node, together.
    specs = handoff["beam_specs"]
    support = 0.0
    for beam in handoff["beams"]:
        first, second = (index[node] for node in beam["nodes"])
        if free[first] == free[second]:
            continue
        loose, anchor = (first, second) if free[first] else (second, first)
        delta = points[anchor] - points[loose]
        length = float(np.linalg.norm(delta))
        if length < 1e-9:
            continue
        rest = float(
            np.linalg.norm(
                np.array(handoff["nodes"][anchor]["source_world_position"])
                - np.array(handoff["nodes"][loose]["source_world_position"])
            )
        )
        spring = float(specs[beam["spec"]]["beamSpring"])
        support += spring * (length - rest) / length * float(delta[2])

    carried = ground + support
    assert abs(carried - weight) < 0.05 * weight, (
        f"the settle has not converged: the ground carries {ground / 1000:.1f} kN and "
        f"the dock {support / 1000:.1f} kN of a {weight / 1000:.1f} kN free weight "
        f"after {report['steps']} steps (residual {report['residual']:.1f} N)"
    )
    return order, points, free, index


def test_the_tire_settles_onto_a_real_contact_patch(spec, handoff):
    """It has to FLATTEN, and it has to stand up.

    TIRE_MASS is ~107x lighter than an honest carcass, so spring rates argued
    from real materials at full scale leave the cage orders of magnitude
    stiffer relative to its own weight than a real tire. The first cut of this
    prop converged on a contact set of TWO nodes over a 1.68 m strip under a
    body whose centre of mass is 14 m up: it would have fallen over on the
    first bump, and no check that looked only at spring rates could have said
    so - the tread's crown arc has to be closed by the settle, and whether it
    is depends on the whole structure at once.

    So the gate is the thing itself: settle the cage and demand a footprint
    wide enough that the Colossus is not balancing on a knife edge.
    """

    order, points, free, index = _settled(handoff, spec)

    contact = [
        identifier
        for identifier in order
        if free[index[identifier]] and points[index[identifier]][2] < 0.015
    ]
    assert contact, "the tire never reaches the ground"
    xs = [points[index[identifier]][0] for identifier in contact]
    ys = [points[index[identifier]][1] for identifier in contact]
    width = max(xs) - min(xs)
    length = max(ys) - min(ys)

    assert width > 0.55 * 2 * spec.TREAD_HALF, (
        f"contact patch is {width:.2f} m across a {2 * spec.TREAD_HALF:.2f} m tread "
        f"({len(contact)} nodes); the Colossus is balancing on its centre rib"
    )
    assert length > 1.5, f"contact patch is only {length:.2f} m long"


# ---------------------------------------------------------------------------
# The straps are the whole connection
# ---------------------------------------------------------------------------
def test_everything_joining_the_tire_to_the_dock_is_in_the_release_group(handoff, spec, by_id):
    """Every free-to-fixed beam must be cut by the release, and only those.

    The cage is one connected graph only because the tie-downs hold it, which
    is what makes it legal under the pack's one-cage rule. The invariant is
    not "exactly two beams" - the gangway's landing struts are a second,
    deliberate pair - it is that EVERY beam crossing between the tire and the
    dock carries the release break group. One that does not is a weld: the
    straps are cut, the runtime announces the Colossus is loose, and it stays
    bolted to the quay with nothing in the log.
    """

    bridges = []
    for beam in handoff["beams"]:
        first, second = beam["nodes"]
        if by_id[first]["fixed"] != by_id[second]["fixed"]:
            bridges.append(beam)

    assert bridges, "the cage is not connected at all"
    welds = [
        beam for beam in bridges
        if beam.get("extra", {}).get("breakGroup") != spec.STRAP_BREAK_GROUP
    ]
    assert not welds, (
        f"{len(welds)} beam(s) join the tire to the dock outside the release "
        f"group: {[b['nodes'] for b in welds][:4]}"
    )

    families = {beam["spec"] for beam in bridges}
    assert families <= {"strap", "landing"}, families
    for family in families:
        entry = handoff["beam_specs"][family]
        assert float(entry["beamStrength"]) < 1e6, f"{family} cannot break; it is a weld"
        assert float(entry["beamDeform"]) < float(entry["beamStrength"])


def test_runtime_never_drives_the_tire(spec):
    """The premise is that the physics does it. Prove the Lua does not.

    Every other rolling prop in this pack moves its subject with a per-frame
    velocity field. This one must not touch either body: a force field would
    be a lie the player can feel the moment they lift off.
    """

    behaviour = spec.LUA_BEHAVIOR
    forbidden = (
        "applyClusterVelocityScaleAdd",
        "setPosition",
        "setPositionRotation",
        "applyForce",
        "launchSubject",
        "addSubjectVelocity",
        "teleportSubject",
        "setPartPose",
    )
    used = [name for name in forbidden if name in behaviour]
    assert not used, f"the Colossus runtime moves things: {used}"
    # It is allowed exactly one command into the prop's own vehicle Lua: the
    # one that cuts the straps.
    assert behaviour.count("queueLuaCommand") == 1
    assert "beamstate.breakBreakGroup" in behaviour


def test_the_exported_collada_carries_no_wall_clock(spec):
    """The shipped DAE must not contain a timestamp from when it was built.

    Blender's Collada exporter stamps <created>/<modified> with the wall clock
    and writes "Blender User" as the author, so two runs of a deterministic
    generator produce different bytes. Nothing downstream notices - the
    handoff records the hash of the DAE from the same run - but it means the
    distribution ZIP lock churns on every Blender run with no content change,
    and "reproducible from a clean checkout" is not true.

    This is a PACK-WIDE property of the shared exporter; colossus_tire
    normalises its own output because fixing it centrally would invalidate
    twenty other mods' handoff hashes at once.
    """

    dae = (
        EXAMPLE_ROOT / "mod" / "vehicles" / spec.MOD_ID / f"{spec.MOD_ID}.dae"
    )
    if not dae.is_file():
        pytest.skip("no exported Collada")
    head = dae.read_text(encoding="utf-8", errors="ignore")[:4000]
    stamps = re.findall(r"<(?:created|modified)>([^<]*)<", head)
    assert stamps, "no <created>/<modified> found; the exporter changed shape"
    for stamp in stamps:
        assert stamp == "2026-08-01T00:00:00", (
            f"the shipped Collada carries a wall-clock stamp {stamp!r}; "
            "normalise_collada() did not run"
        )
    assert "Blender User" not in head

# ---------------------------------------------------------------------------
# The SHIPPED visual mesh.
#
# Every other gate in this file reads the handoff - the physics cage. The DAE
# is the other half of the mod and, until this, nothing read it: the pack gate
# only hashes it, and the generator's own orientation assert runs on Blender
# objects before export, matching by object NAME, so anything it had no rule
# for was waved through. Round 1 shipped 100% of its sidewalls inside out past
# every check in the repo. This parses the bytes that actually ship.
# ---------------------------------------------------------------------------
COLLADA_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}


def _collada_streams(path):
    """Yield (material_suffix, positions, uvs, triangle index array) per stream."""

    import numpy as np
    import xml.etree.ElementTree as ET

    root = ET.parse(path).getroot()
    for geometry in root.findall(".//c:library_geometries/c:geometry", COLLADA_NS):
        mesh = geometry.find("c:mesh", COLLADA_NS)
        sources = {}
        for source in mesh.findall("c:source", COLLADA_NS):
            array = source.find("c:float_array", COLLADA_NS)
            stride = int(
                source.find("c:technique_common/c:accessor", COLLADA_NS).get("stride")
            )
            values = np.array(array.text.split(), dtype=float)
            sources[source.get("id")] = values.reshape(-1, stride)
        vertices = mesh.find("c:vertices", COLLADA_NS)
        position_id = vertices.find("c:input", COLLADA_NS).get("source").lstrip("#")
        positions = sources[position_id]

        for primitive in mesh.findall("c:triangles", COLLADA_NS):
            inputs = primitive.findall("c:input", COLLADA_NS)
            stride = max(int(entry.get("offset")) for entry in inputs) + 1
            offsets = {
                entry.get("semantic"): int(entry.get("offset")) for entry in inputs
            }
            uv_input = next(
                (e for e in inputs if e.get("semantic") == "TEXCOORD"), None
            )
            uvs = (
                sources[uv_input.get("source").lstrip("#")]
                if uv_input is not None
                else None
            )
            data = np.array(primitive.find("c:p", COLLADA_NS).text.split(), dtype=int)
            data = data.reshape(-1, stride)
            faces = data[:, offsets["VERTEX"]].reshape(-1, 3)
            uv_faces = (
                data[:, offsets["TEXCOORD"]].reshape(-1, 3) if uvs is not None else None
            )
            # "<mod_id>_<suffix>-material" -> "<suffix>", which is the key
            # spec.MATERIAL_TILE and the palette are written in.
            material = (primitive.get("material") or "").replace("-material", "")
            suffix = material.split("ericrolph_colossus_tire_")[-1]
            yield suffix, positions, uvs, faces, uv_faces


@pytest.fixture(scope="module")
def collada(spec):
    path = (
        EXAMPLE_ROOT / "mod" / "vehicles" / spec.MOD_ID / f"{spec.MOD_ID}.dae"
    )
    if not path.is_file():
        pytest.skip("no exported Collada")
    pytest.importorskip("numpy")
    return list(_collada_streams(path))


def test_shipped_mesh_has_no_degenerate_or_duplicate_triangles(collada):
    """Zero-area and duplicated faces, measured on the shipped bytes.

    A zero-area triangle has a degenerate tangent basis, and BeamNG's
    normal-mapped shading on one is the classic source of black speckle. A
    duplicated triple is two coincident surfaces fighting for the same depth.
    """

    import numpy as np

    degenerate = 0
    duplicated = 0
    total = 0
    worst = None
    for suffix, positions, _uvs, faces, _uv_faces in collada:
        points = positions[faces]
        cross = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        area = 0.5 * np.linalg.norm(cross, axis=1)
        bad = int((area < 1e-9).sum())
        if bad and worst is None:
            worst = suffix
        degenerate += bad
        keys = np.sort(faces, axis=1)
        unique = np.unique(keys, axis=0)
        duplicated += len(keys) - len(unique)
        total += len(faces)

    assert total > 0
    assert degenerate == 0, f"{degenerate} zero-area triangles (first in {worst})"
    assert duplicated == 0, f"{duplicated} duplicated triangles in the shipped mesh"


def test_shipped_mesh_uv_density_is_metric_per_material(spec, collada):
    """Each material must appear at ONE grain size, its authored one.

    Measured as median (uv edge length / world edge length) x tile, where 1.0
    is exactly the authored metres-per-tile. Curved surfaces and box mapping
    spread this, so the band is generous - it is here to catch a material
    rendered at two densities in the same frame, or an unwrapped one left at
    a normalised 0..1, not to police a few percent.
    """

    import numpy as np

    report = {}
    for suffix, positions, uvs, faces, uv_faces in collada:
        if uvs is None or suffix not in spec.MATERIAL_TILE:
            continue
        tile = spec.MATERIAL_TILE[suffix]
        world = positions[faces]
        texel = uvs[uv_faces]
        ratios = []
        for first, second in ((0, 1), (1, 2), (2, 0)):
            world_edge = np.linalg.norm(world[:, second] - world[:, first], axis=1)
            uv_edge = np.linalg.norm(texel[:, second] - texel[:, first], axis=1)
            keep = (world_edge > 1e-4) & (uv_edge > 1e-9)
            ratios.append(uv_edge[keep] / world_edge[keep] * tile)
        if not any(len(chunk) for chunk in ratios):
            continue
        report[suffix] = float(np.median(np.concatenate(ratios)))

    assert report, "no textured streams found"
    # sidewall_print is a DECAL sheet, not a tiling material: v spans the band
    # 0..1 by design, which is how its four printed lines are laid out.
    decals = {"sidewall_print"}
    offenders = {
        suffix: round(value, 2)
        for suffix, value in report.items()
        if suffix not in decals and not 0.55 <= value <= 1.8
    }
    assert not offenders, (
        f"materials rendered off their authored grain size: {offenders} "
        f"(1.00 = metric; full report {dict(sorted((k, round(v, 2)) for k, v in report.items()))})"
    )


def test_shipped_mesh_faces_outward(spec, collada):
    """The carcass surfaces must face out of the rubber in the SHIPPED file.

    BeamNG backface-culls flexbodies. The generator asserts this before
    export on Blender objects, matched by object name; this asserts it after
    export on the geometry that actually ships, matched by MATERIAL - so a new
    object that slipped past the name rules cannot slip past both.

    Only faces whose normal is predominantly radial are judged: lug side walls
    and letter flanks are tangential by construction and carry no radial
    expectation.
    """

    import numpy as np

    axle = np.array([0.0, 0.0, spec.OUTER_RADIUS])
    # ONE RULE PER MATERIAL, the same way the generator does it, because a
    # single radial test is wrong for half of them: the sidewall lathe faces
    # AWAY FROM THE CENTRE PLANE and its normal tilts toward the axle below
    # maximum section width, the bead toe caps the shell and faces down the
    # bead hole, and the liner faces the cavity. sidewall_type is the extruded
    # lettering - closed solids whose flanks point every which way - and is
    # judged by the generator's own orientation pass instead.
    radial_out = {"tread"}
    radial_in = {"liner", "lane_mark", "bead"}
    axial_out = {"sidewall", "sidewall_print"}
    verdicts = {}
    for suffix, positions, _uvs, faces, _uv_faces in collada:
        if suffix not in radial_out | radial_in | axial_out:
            continue
        points = positions[faces]
        normals = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        keep = lengths > 1e-9
        normals = normals[keep] / lengths[keep][:, None]
        centres = points[keep].mean(axis=1)
        if suffix in axial_out:
            reference = np.zeros_like(centres)
            reference[:, 0] = np.sign(centres[:, 0])
            want_out = True
        else:
            reference = centres - axle
            reference[:, 0] = 0.0               # the radial direction is in y-z
            want_out = suffix in radial_out
        length = np.linalg.norm(reference, axis=1)
        good = length > 1e-6
        normals, reference = normals[good], reference[good] / length[good][:, None]
        alignment = (normals * reference).sum(axis=1)
        judged = np.abs(alignment) > 0.55
        if judged.sum() < 16:
            continue
        correct = (alignment[judged] > 0) if want_out else (alignment[judged] < 0)
        verdicts[suffix] = (int(correct.sum()), int(judged.sum()))

    assert verdicts, "no carcass materials judged"
    failures = {
        suffix: f"{good}/{total}"
        for suffix, (good, total) in verdicts.items()
        if good / total < 0.97
    }
    assert not failures, f"shipped faces pointing into the rubber: {failures}"


def test_the_shipped_type_is_wound_one_way(collada):
    """No edge in the moulded type may be traversed the same way twice.

    BeamNG backface-culls flexbodies, so a face wound the wrong way is not a
    dark face - it is a hole. Round 3 recalculated the type's normals and THEN
    attached a dissolve modifier that was applied downstream, so the merge and
    the re-triangulation both happened after the last thing that could orient
    them: 3,906 edges came out traversed the same way by both their faces and
    27% of the type - the surface the hero shot is composed around - faced
    into the rubber. This is measured on the bytes that ship.
    """

    import collections

    offenders = {}
    for suffix, _positions, _uvs, faces, _uv_faces in collada:
        if suffix not in {"sidewall_type", "sidewall_print", "sidewall", "liner", "tread"}:
            continue
        seen = collections.Counter()
        for first, second, third in faces:
            for edge in ((first, second), (second, third), (third, first)):
                seen[edge] += 1
        bad = sum(1 for count in seen.values() if count > 1)
        if bad:
            offenders[suffix] = bad
    assert not offenders, (
        f"faces disagree about which way is out: {offenders} edges traversed "
        f"identically by two faces"
    )


def test_no_shipped_triangle_has_a_degenerate_tangent_basis(collada):
    """A face with world area must have UV area.

    A triangle whose three UVs are collinear has no tangent basis, and a
    normal map sampled through one is the classic source of black speckle -
    a failure this file's sibling gate already warns about for zero-AREA
    faces, while 7,908 zero-UV ones shipped alongside them. The type's flank
    quads were unwrapped from (y, z) alone while the extrusion runs in x, so
    every single one of them collapsed.
    """

    import numpy as np

    offenders = {}
    for suffix, positions, uvs, faces, uv_faces in collada:
        if uvs is None or uv_faces is None:
            continue
        world = positions[faces]
        texel = uvs[uv_faces]
        world_area = 0.5 * np.linalg.norm(
            np.cross(world[:, 1] - world[:, 0], world[:, 2] - world[:, 0]), axis=1
        )
        first = texel[:, 1] - texel[:, 0]
        second = texel[:, 2] - texel[:, 0]
        uv_area = 0.5 * np.abs(first[:, 0] * second[:, 1] - first[:, 1] * second[:, 0])
        bad = int(((world_area > 1e-7) & (uv_area < 1e-12)).sum())
        if bad:
            offenders[suffix] = f"{bad}/{len(faces)}"
    assert not offenders, f"triangles with world area and no UV area: {offenders}"


def test_the_shipped_print_band_faces_out_of_the_sidewall(collada):
    """The small-print ring is an open band standing proud of the flank.

    The radial rule its sibling gate applies to the carcass says nothing about
    it: a band standing off the sidewall has an almost purely AXIAL normal, so
    every one of its faces falls below that gate's radial threshold and is
    skipped. This is the axial half of the same question.
    """

    import numpy as np

    verdicts = {}
    for suffix, positions, _uvs, faces, _uv_faces in collada:
        if suffix != "sidewall_print":
            continue
        points = positions[faces]
        normals = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        keep = lengths > 1e-9
        normals = normals[keep] / lengths[keep][:, None]
        centres = points[keep].mean(axis=1)
        judged = np.abs(normals[:, 0]) > 0.55
        if judged.sum() < 16:
            continue
        outboard = np.sign(centres[judged][:, 0])
        correct = np.sign(normals[judged][:, 0]) == outboard
        verdicts[suffix] = (int(correct.sum()), int(judged.sum()))

    assert verdicts, "no print band judged"
    failures = {
        suffix: f"{good}/{total}"
        for suffix, (good, total) in verdicts.items()
        if good / total < 0.97
    }
    assert not failures, f"print band facing into the sidewall: {failures}"


def test_every_moulded_glyph_is_a_solid_wound_outward(collada):
    """Each letter is a closed solid, and every one of them has volume.

    A face rule cannot judge the type. A glyph is a CLOSED extrusion: its
    crown faces outboard and its back cap faces inboard, flush on the flank,
    so exactly half of its axial faces point each way by construction and any
    "must face outboard" test scores it 50% whether it is right or wrong.
    What is unambiguous is the signed volume: positive for a solid wound
    outward, negative for one turned inside out, and it is computed per
    connected component so a single inverted glyph cannot hide inside the sum.
    """

    import numpy as np

    for suffix, positions, _uvs, faces, _uv_faces in collada:
        if suffix != "sidewall_type":
            continue
        parent = list(range(len(positions)))

        def root(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        for first, second, third in faces:
            for other in (second, third):
                a, b = root(int(first)), root(int(other))
                if a != b:
                    parent[a] = b

        volumes: dict[int, float] = {}
        points = positions[faces]
        signed = np.einsum(
            "ij,ij->i", points[:, 0], np.cross(points[:, 1], points[:, 2])
        ) / 6.0
        for face, value in zip(faces, signed, strict=True):
            key = root(int(face[0]))
            volumes[key] = volumes.get(key, 0.0) + float(value)

        assert len(volumes) >= 18, (
            f"expected at least one solid per moulded string, found {len(volumes)}"
        )
        inverted = [round(value, 4) for value in volumes.values() if value <= 0.0]
        assert not inverted, (
            f"{len(inverted)} of {len(volumes)} moulded glyph solids are wound "
            f"inside out (signed volumes {inverted[:6]}); BeamNG culls them to holes"
        )
        return
    pytest.skip("no moulded type in the shipped mesh")


def test_a_car_can_drive_from_the_cavity_floor_to_the_dock(spec, handoff):
    """The boarding path is continuous on the SETTLED geometry.

    Every gate in this file measured the tire as authored, standing at its
    spawn pose; the tire it ships settles 0.36 m onto its contact patch, and
    the gangway hangs off it. Round 3's gangway had its only two supports on
    its outer corners, running mostly sideways, so its mid-span - which is the
    boarding centreline - sagged onto the terrain and left a step no car can
    climb. Nothing static could see it, because nothing static settled first.

    So: walk the centreline out from the middle of the cavity floor to the
    foot of the ramp, take the highest up-facing collision surface under each
    step, and fail on a hole or a kerb.
    """

    import numpy as np

    order, points, free, index = _settled(handoff, spec)
    triangles = np.array(
        [[index[node] for node in tri["nodes"]] for tri in handoff["triangles"]]
    )
    corners = points[triangles]
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    up = normals[:, 2] > 0.0                       # a coltri collides one way

    def surface(x: float, y: float) -> float | None:
        best = None
        for tri in np.nonzero(up)[0]:
            a, b, c = corners[tri]
            v0, v1, v2 = b[:2] - a[:2], c[:2] - a[:2], np.array([x, y]) - a[:2]
            denominator = v0[0] * v1[1] - v1[0] * v0[1]
            if abs(denominator) < 1e-12:
                continue
            u = (v2[0] * v1[1] - v1[0] * v2[1]) / denominator
            v = (v0[0] * v2[1] - v2[0] * v0[1]) / denominator
            if u < -1e-6 or v < -1e-6 or u + v > 1.0 + 1e-6:
                continue
            z = a[2] + u * (b[2] - a[2]) + v * (c[2] - a[2])
            if z > 3.0:
                continue
            best = z if best is None else max(best, z)
        return best

    profile = []
    x = 2.0
    while x <= spec.DOCK_LANDING_X1:
        profile.append((x, surface(x, 0.0)))
        x += 0.10

    holes = [round(x, 2) for x, z in profile if z is None]
    assert not holes, (
        f"the boarding centreline has no collision surface at x = {holes}; "
        f"a car driving out drops through the floor"
    )
    heights = [z for _x, z in profile]
    steps = [
        (round(profile[i][0], 2), round(heights[i + 1] - heights[i], 3))
        for i in range(len(heights) - 1)
        if abs(heights[i + 1] - heights[i]) > 0.25
    ]
    assert not steps, f"the boarding centreline steps by more than 0.25 m at {steps}"


def test_the_verify_render_builds_everything_the_generator_ships():
    """The frames a round is judged from must contain the whole prop.

    verify_render.py assembles the scene by calling the generator's builders
    one at a time, and that list has now drifted from main()'s TWICE: the lane
    chevrons went a whole round unreviewed, and then the small-print ring went
    a whole round the same way - designed, textured, argued for in forty lines
    of spec prose, and absent from every image the critics looked at. A
    comment saying "keep these in sync" has failed twice, so this compares
    them.
    """

    import re

    generator = (
        EXAMPLE_ROOT / "blender" / "create_colossus_tire.py"
    ).read_text(encoding="utf-8")
    render = (EXAMPLE_ROOT / "authoring" / "verify_render.py").read_text(encoding="utf-8")

    def _builders(text: str, marker: str, prefix: str) -> set[str]:
        start = text.index(marker)
        body = text[start:]
        end = body.find("\ndef ", 1)
        if end < 0:
            end = len(body)
        return set(re.findall(rf"{prefix}(build_\w+)\(", body[:end]))

    # build_cage is the physics cage, not a surface; it has no appearance
    # to review and the renders are of the visual mesh.
    shipped = _builders(generator, "def main() -> None:", "") - {"build_cage"}
    rendered = _builders(render, "def scene() -> None:", "gen.")
    missing = sorted(shipped - rendered)
    assert not missing, (
        f"verify_render.py never builds {missing}, so no frame in "
        f"authoring/verify/ contains it and no review can see it"
    )
