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

    # The liner ring is CIRCUMSCRIBED, not inscribed: its 48 nodes sit on a
    # radius whose chord midpoints land on CAVITY_RADIUS, because the surface
    # a car actually rides is the chord and not the node. Putting the nodes on
    # the cavity radius put the whole drivable floor 28 mm inside it.
    liner_ring = spec.CAVITY_RADIUS / math.cos(spec.STATION_ANGLE * 0.5)
    checks = {
        "bead_l": spec.BEAD_RADIUS,
        "bead_r": spec.BEAD_RADIUS,
        "crn_c": spec.OUTER_RADIUS,
        "lin_c": liner_ring,
        "lin_l": liner_ring,
        "lin_r": liner_ring,
    }
    for station in (0, 7, 19, 31, 44):
        for key, expected in checks.items():
            identifier = f"{spec.MOD_ID}_{key}_j{station:02d}"
            assert radius_of(identifier) == pytest.approx(expected, abs=1e-4), identifier


def test_the_chocks_are_where_a_chock_would_work(spec):
    """The chock's top edge has to touch the carcass, or it is scenery.

    A chock stops a tire by being something it has to climb, so its heel has
    to reach the tread. On a body this size the curve down there is very flat -
    at 6 m from the contact patch the carcass is only 1.34 m up - which is why
    a chock for a 28 m tire is long rather than tall, and why the height is
    derived from the distance rather than typed alongside it.
    """

    # AS BUILT, seat gap included: this is the face the carcass actually
    # meets, and certifying the pre-gap geometry once let the shipped ramp
    # drift two degrees below the gate's floor without a murmur.
    height = (
        spec.OUTER_RADIUS
        - math.sqrt(spec.OUTER_RADIUS**2 - spec.CHOCK_FAR**2)
        - spec.CHOCK_SEAT_GAP
    )
    assert spec.CHOCK_NEAR < spec.CHOCK_FAR, "the wedge points the wrong way"
    assert 0.4 < height < 2.5, (
        f"a chock heel at {spec.CHOCK_FAR:.1f} m makes a {height:.2f} m wedge; "
        f"that is either a speed bump or a wall"
    )
    # It has to be a ramp, not a step: something the carcass can climb only
    # under real force, but not a vertical face it simply leans on.
    slope = math.degrees(math.atan2(height, spec.CHOCK_FAR - spec.CHOCK_NEAR))
    assert 11.0 < slope < 40.0, f"the climb face is at {slope:.0f} degrees"


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
        stem = identifier[len(spec.MOD_ID) + 1 :].rsplit("_j", 1)[0]
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
        centre = [sum(axis) / 3.0 for axis in zip(*points, strict=False)]
        outward = (centre[0] - axle[0], centre[1] - axle[1], centre[2] - axle[2])
        dot = sum(a * b for a, b in zip(normal, outward, strict=False))
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
def test_nothing_fixed_can_ever_be_touched(spec, handoff, nodes):
    """Every fixed node is a buried, collisionless anchor. Nothing else.

    The wedges used to be fixed, and that made them fake twice over: their
    nodes shipped without selfCollision so the tire never actually pressed on
    them, and after release the carcass rolled straight through their meshes.
    Now the wedges are free bodies and the only fixed nodes are the strap
    anchors and the spawn-basis datums - all collisionless, all at or below
    grade, so nothing fixed can ever exchange a force with the world except
    through a strap that the release cuts.
    """

    fixed = [node for node in handoff["nodes"] if node["fixed"]]
    names = sorted(node["id"].replace(f"{spec.MOD_ID}_", "") for node in fixed)
    strays = [name for name in names if not (name.startswith("ground_") or "_anchor_" in name)]
    assert not strays, f"fixed nodes that are neither anchor nor datum: {strays}"
    assert len(fixed) >= 8, f"only {len(fixed)} fixed nodes: {names}"
    for node in fixed:
        assert not node["collision"], f"{node['id']} is fixed AND collidable"
        if "_anchor_" in node["id"]:
            _x, _y, z = nodes[node["id"]]
            assert z <= 0.01, f"anchor above grade: {node['id']} at z={z:.2f}"

    # And the wedges themselves are free bodies that really touch the tire:
    # collidable, selfCollision on, at chock mass - not scenery.
    wedge = [
        node for node in handoff["nodes"] if "chock_" in node["id"] and "_anchor_" not in node["id"]
    ]
    assert len(wedge) == 24, f"{len(wedge)} wedge nodes"
    for node in wedge:
        assert not node["fixed"], f"wedge node is still fixed: {node['id']}"
        assert node["collision"], node["id"]
        assert node["self_collision"], (
            f"{node['id']} has no selfCollision: the tire would roll straight through its own chock"
        )
        assert abs(node["weight"] - spec.WEDGE_NODE_MASS) < 1e-6, node["id"]


def test_no_flexbody_group_contains_a_fixed_node(spec, handoff):
    """A visual skinned to a fixed node stays nailed down while its body leaves.

    Round 5's chair measured the chock visual bound to the default physics
    group: 24 free wedge nodes PLUS all 16 buried anchors and 4 datums, and
    every anchor sits 0.6 m directly under a wedge corner - closer than most
    of the wedge's own nodes - so the winch dragged the wedges 5 m while
    their skins sheared toward nodes that never move. The rule is general:
    no group a flexbody binds may hold a fixed node.
    """

    jbeam_path = EXAMPLE_ROOT / "mod" / "vehicles" / spec.MOD_ID / f"{spec.MOD_ID}.jbeam"
    jbeam = json.loads(jbeam_path.read_text(encoding="utf-8"))
    part = jbeam[spec.MOD_ID]
    bound = {
        group
        for row in part["flexbodies"][1:]
        for group in (row[1] if isinstance(row[1], list) else [row[1]])
    }
    assert bound, "no flexbody binds any group"

    sticky: dict = {}
    offenders = []
    for row in part["nodes"][1:]:
        if isinstance(row, dict):
            sticky = {**sticky, **row}
            continue
        inline = row[4] if len(row) > 4 and isinstance(row[4], dict) else {}
        options = {**sticky, **inline}
        if options.get("fixed") and options.get("group") in bound:
            offenders.append((row[0], options.get("group")))
    assert not offenders, f"fixed nodes inside flexbody-bound groups: {offenders[:6]}"


def test_chock_hazard_faces_look_out_of_the_steel(spec, collada):
    """Every hazard triangle on a chock faces AWAY from its wedge's middle.

    The old stripe decals shipped all sixteen triangles facing (0, +/-0.22,
    -0.97) - INTO the wedge - and rendered on zero pixels in game and in
    every verify render, because the orientation audit never judged ground
    objects. This reads the SHIPPED DAE: for each hazard-material triangle
    below z = 1.5 (the chock region), the normal must point away from that
    wedge's own centroid.
    """

    import numpy as np

    bad = 0
    total = 0
    components_seen = 0
    for _geometry, suffix, positions, _uvs, faces, _uv_faces in collada:
        name = str(suffix)
        if "hazard" not in name:
            continue
        tris = faces.reshape(-1, 3)
        low = np.array([positions[tri].mean(axis=0)[2] < 1.5 for tri in tris])
        tris = tris[low]
        if not len(tris):
            continue
        # Each stripe is its own CLOSED slab and slabs never share a vertex,
        # so connected components over vertex indices recover the solids -
        # and the honest invariant is per-SOLID: every face of a closed slab
        # winds away from that slab's own centre. (A per-wedge centroid test
        # condemned the 6 mm slabs' legitimate back faces.)
        find = _union_find(
            pair
            for tri in tris
            for pair in ((int(tri[0]), int(tri[1])), (int(tri[1]), int(tri[2])))
        )
        groups: dict = {}
        for tri in tris:
            groups.setdefault(find(int(tri[0])), []).append(tri)
        for rows in groups.values():
            components_seen += 1
            pts = positions[np.unique(np.concatenate(rows))]
            centroid = pts.mean(axis=0)
            for tri in rows:
                a, b, c = positions[tri]
                normal = np.cross(b - a, c - a)
                if np.linalg.norm(normal) < 1e-12:
                    continue
                outward = positions[tri].mean(axis=0) - centroid
                total += 1
                if np.dot(normal, outward) <= 0:
                    bad += 1
    assert components_seen >= 16, f"only {components_seen} hazard slabs found in the chock region"
    assert total >= 96, f"only {total} chock hazard triangles found"
    assert bad == 0, f"{bad} of {total} chock hazard triangles face into their own slab"


def test_every_open_tread_component_is_seated_in_its_local_floor(spec, collada):
    """Every open-bottomed tread shell's rim sits BELOW the floor it stands on.

    Per CONNECTED COMPONENT, because per-object checks have now let this
    class ship through green twice: the wear bars weld into the ejectors
    object, so ~72 seated ejectors and 12 seated inner bars vouched for 12
    outer bars floating ~42 mm above their local groove floor - the crown
    arc DROPS base_r off-centre, and a constant seat at GROOVE_RADIUS is
    exactly wrong in the direction round 5's fix assumed. The local floor
    is analytic (a surface of revolution needs no ray cast):

        floor_r(x) = OUTER_RADIUS - x^2 / (2 * TREAD_ARC_RADIUS) - TREAD_DEPTH

    A component with no boundary edges is a closed solid (a glyph) and is
    judged by the volume gate instead; every OPEN component here must put
    its entire boundary rim within LUG_SEAT/2 of its local floor - the
    same tolerance the generator's own seating assert uses, because a ring
    whose floor was sampled at its centre legitimately rides ~1.6 mm of
    crown curvature at its edges, and that is backed by its own dome.
    """

    import numpy as np

    def floor_r(x):
        return spec.OUTER_RADIUS - (x * x) / (2.0 * spec.TREAD_ARC_RADIUS) - spec.TREAD_DEPTH

    offenders = []
    open_components = 0
    for _geometry, suffix, positions, _uvs, faces, _uv_faces in collada:
        if "tread" not in str(suffix):
            continue
        tris = faces.reshape(-1, 3)
        find = _union_find(
            pair
            for tri in tris
            for pair in ((int(tri[0]), int(tri[1])), (int(tri[1]), int(tri[2])))
        )
        edge_count: dict = {}
        for tri in tris:
            a, b, c = (int(v) for v in tri)
            for e in ((a, b), (b, c), (c, a)):
                key = (min(e), max(e))
                edge_count[key] = edge_count.get(key, 0) + 1

        boundary_by_component: dict = {}
        for (a, b), count in edge_count.items():
            if count == 1:
                boundary_by_component.setdefault(find(a), set()).update((a, b))

        for _root, rim in boundary_by_component.items():
            open_components += 1
            rim_idx = np.array(sorted(rim))
            pts = positions[rim_idx]
            radial = np.sqrt(pts[:, 1] ** 2 + (pts[:, 2] - spec.OUTER_RADIUS) ** 2)
            floors = np.array([floor_r(x) for x in pts[:, 0]])
            worst = float((radial - floors).max())
            if worst > spec.LUG_SEAT * 0.5:
                centre = pts.mean(axis=0)
                offenders.append(
                    (
                        tuple(round(v, 2) for v in centre),
                        round(worst * 1000, 1),
                    )
                )
    assert open_components >= 50, (
        f"only {open_components} open tread components found - the furniture did not decompose"
    )
    assert not offenders, (
        f"{len(offenders)} open tread component(s) float above their local "
        f"floor (centre, worst rim proud in mm): {offenders[:8]}"
    )


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
            stiffness[identifier] = stiffness.get(identifier, 0.0) + float(family["beamSpring"])
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
    """Rubber sits in a 0.08-0.35 damping-ratio band; steel cord under 0.12.

    ONE CONVENTION, NAMED: zeta = c / (2*sqrt(k*m)) against the family's
    heaviest node. The band is NOT the material's loss tangent - that lesson
    is on record (tan-delta 0.1-0.25 converts as zeta ~ tan(delta)/2, i.e.
    5-12%, and this gate once blessed a tread at 0.42 because its band was
    argued straight from tan-delta). The shipped band is wider than the
    converted material figure ON PURPOSE: the upper half is settling margin,
    paid for by the live gates' measured ring decay, not by a material claim.
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


def _union_find(pairs):
    """Union the id pairs; returns the find() root function.

    One implementation for the three component decompositions in this file
    (hazard slabs, tread furniture, moulded type) - the loop-closure copies
    it replaced were both a lint fire and a maintenance trap.
    """

    parent: dict[int, int] = {}

    def find(a: int) -> int:
        while parent.get(a, a) != a:
            parent[a] = parent.get(parent[a], parent[a])
            a = parent[a]
        return a

    for a, b in pairs:
        parent.setdefault(a, a)
        parent.setdefault(b, b)
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return find


def carcass_nodes(handoff, nodes):
    """Free nodes that are the TIRE - the wedges are free bodies, not tire."""

    for node in handoff["nodes"]:
        if node["fixed"] or "chock" in node["id"]:
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


def _relax(handoff, spec, residual=None, cap=250_000):
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
    points = np.array([node["source_world_position"] for node in handoff["nodes"]], dtype=float)
    mass = np.array([float(node["weight"]) for node in handoff["nodes"]])
    free = np.array([not node["fixed"] for node in handoff["nodes"]])

    specs = handoff["beam_specs"]
    first = np.array([index[b["nodes"][0]] for b in handoff["beams"]])
    second = np.array([index[b["nodes"][1]] for b in handoff["beams"]])
    spring = np.array([float(specs[b["spec"]]["beamSpring"]) for b in handoff["beams"]])
    rest = np.linalg.norm(points[first] - points[second], axis=1)

    # The convergence criterion scales with what is being converged: a fixed
    # 20 N floor was tuned against a 124 kN body, and when the mass solve
    # moved the tire to 4.2 t the same floor let the relax stop while the
    # ground was still 8% short of the weight.
    if residual is None:
        residual = max(4.0, 1.5e-4 * float(mass[free].sum()) * spec.GRAVITY)
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
    # FREE nodes only: the strap anchors are FIXED 0.6 m below grade, and
    # counting them here books 28.8 MN of imaginary ground force against a
    # 124 kN body. A fixed node in the floor is not carried by anything.
    ground = float((-3.0e6 * np.minimum(points[free, 2], 0.0)).sum())

    # AND WHAT THE STRAPS CARRY. The free set is not only the tire: the
    # four chock wedges hang on their anchor straps, so a slice of the free
    # weight goes to the fixed anchors through webbing rather than through
    # the ground, and demanding the GROUND carry all of it would fail a
    # perfectly converged solve. What has to balance is every path to a
    # fixed node, together.
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
def test_everything_joining_free_to_fixed_is_in_the_release_group(handoff, spec, by_id):
    """Every free-to-fixed beam must be cut by the release, and only those.

    The cage is one connected graph only because the tie-downs hold it, which
    is what makes it legal under the pack's one-cage rule. The invariant is
    that EVERY beam crossing between anything free and anything fixed - the
    tire's eight ties and the wedges' thirty-two anchor straps - carries the
    release break group. One that does not is a weld: the release fires, the
    runtime announces the Colossus is loose, and it stays roped to a buried
    anchor with nothing in the log.
    """

    bridges = []
    for beam in handoff["beams"]:
        first, second = beam["nodes"]
        if by_id[first]["fixed"] != by_id[second]["fixed"]:
            bridges.append(beam)

    assert bridges, "the cage is not connected at all"
    welds = [
        beam
        for beam in bridges
        if beam.get("extra", {}).get("breakGroup") != spec.STRAP_BREAK_GROUP
    ]
    assert not welds, (
        f"{len(welds)} beam(s) cross free-to-fixed outside the release "
        f"group: {[b['nodes'] for b in welds][:4]}"
    )

    families = {beam["spec"] for beam in bridges}
    assert families <= {"strap"}, families
    for family in families:
        entry = handoff["beam_specs"][family]
        assert float(entry["beamStrength"]) < 1e6, f"{family} cannot break; it is a weld"
        assert float(entry["beamDeform"]) < float(entry["beamStrength"])

    # RELEASE MEANS RELEASE. Remove every break-group beam and walk what is
    # left: the carcass must come apart from every wedge and from everything
    # fixed, and each wedge must come apart from its anchors and from the
    # other wedges. One stray beam here is a tow rope nobody can see.
    neighbours: dict[str, set[str]] = {}
    for beam in handoff["beams"]:
        if beam.get("extra", {}).get("breakGroup") == spec.STRAP_BREAK_GROUP:
            continue
        first, second = beam["nodes"]
        neighbours.setdefault(first, set()).add(second)
        neighbours.setdefault(second, set()).add(first)

    def component(seed: str) -> set[str]:
        seen, stack = {seed}, [seed]
        while stack:
            for other in neighbours.get(stack.pop(), ()):
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        return seen

    carcass_seed = next(
        node["id"] for node in handoff["nodes"] if not node["fixed"] and "chock" not in node["id"]
    )
    free_body = component(carcass_seed)
    tethered = sorted(name for name in free_body if "chock" in name or by_id[name]["fixed"])
    assert not tethered, f"cut the release and the tire is still towing: {tethered}"

    wedge_bodies = set()
    for node in handoff["nodes"]:
        if "chock_" not in node["id"] or "_anchor_" in node["id"]:
            continue
        body = frozenset(component(node["id"]))
        anchored = sorted(n for n in body if by_id[n]["fixed"])
        assert not anchored, f"a released wedge is still anchored via {anchored}"
        wedge_bodies.add(body)
    assert len(wedge_bodies) == 4, (
        f"released wedges form {len(wedge_bodies)} bodies, not 4: they are roped together"
    )


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
    # Four queueLuaCommand sites, each named: the strap cut and the chock
    # winch (both in the release beat - a wedge lying against the tread
    # props the carcass even fully unstrapped, measured live), and the two
    # AUDIO dispatch helpers (audioSend and the emitter-node bind), which
    # name cues and a node cid and can move nothing. The tire itself is
    # never touched.
    assert behaviour.count("queueLuaCommand") == 4
    assert "beamstate.breakBreakGroup" in behaviour
    assert "thrusters.applyImpulse" in behaviour
    assert "ctAudioNode" in behaviour and "audioSend" in behaviour
    for _toe, heel in spec.BEHAVIOR["winch_pairs"]:
        assert "chock_" in heel
    marker_names = set(spec.BEHAVIOR["marker_nodes"])
    winch_names = {name for pair in spec.BEHAVIOR["winch_pairs"] for name in pair}
    assert not (winch_names & marker_names)
    assert all("chock_" in name for name in winch_names)


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

    dae = EXAMPLE_ROOT / "mod" / "vehicles" / spec.MOD_ID / f"{spec.MOD_ID}.dae"
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

    import xml.etree.ElementTree as ET

    import numpy as np

    root = ET.parse(path).getroot()
    for geometry in root.findall(".//c:library_geometries/c:geometry", COLLADA_NS):
        mesh = geometry.find("c:mesh", COLLADA_NS)
        sources = {}
        for source in mesh.findall("c:source", COLLADA_NS):
            array = source.find("c:float_array", COLLADA_NS)
            stride = int(source.find("c:technique_common/c:accessor", COLLADA_NS).get("stride"))
            values = np.array(array.text.split(), dtype=float)
            sources[source.get("id")] = values.reshape(-1, stride)
        vertices = mesh.find("c:vertices", COLLADA_NS)
        position_id = vertices.find("c:input", COLLADA_NS).get("source").lstrip("#")
        positions = sources[position_id]

        for primitive in mesh.findall("c:triangles", COLLADA_NS):
            inputs = primitive.findall("c:input", COLLADA_NS)
            stride = max(int(entry.get("offset")) for entry in inputs) + 1
            offsets = {entry.get("semantic"): int(entry.get("offset")) for entry in inputs}
            uv_input = next((e for e in inputs if e.get("semantic") == "TEXCOORD"), None)
            uvs = sources[uv_input.get("source").lstrip("#")] if uv_input is not None else None
            data = np.array(primitive.find("c:p", COLLADA_NS).text.split(), dtype=int)
            data = data.reshape(-1, stride)
            faces = data[:, offsets["VERTEX"]].reshape(-1, 3)
            uv_faces = data[:, offsets["TEXCOORD"]].reshape(-1, 3) if uvs is not None else None
            # "<mod_id>_<suffix>-material" -> "<suffix>", which is the key
            # spec.MATERIAL_TILE and the palette are written in.
            material = (primitive.get("material") or "").replace("-material", "")
            suffix = material.split("ericrolph_colossus_tire_")[-1]
            yield geometry.get("id"), suffix, positions, uvs, faces, uv_faces


@pytest.fixture(scope="module")
def collada(spec):
    path = EXAMPLE_ROOT / "mod" / "vehicles" / spec.MOD_ID / f"{spec.MOD_ID}.dae"
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
    for _geometry, suffix, positions, _uvs, faces, _uv_faces in collada:
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
    for geometry, suffix, positions, uvs, faces, uv_faces in collada:
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
        # KEYED BY GEOMETRY TOO. Three materials - deck, hazard and
        # steel_worn - appear in BOTH the carcass and the dock meshes, and a
        # bare suffix key let the second silently overwrite the first: the
        # gangway kerb measured 2.554 against a 0.55..1.8 band and this went
        # green because the dock's copy of `hazard` landed at 1.255 after it.
        report[(geometry, suffix)] = float(np.median(np.concatenate(ratios)))

    assert report, "no textured streams found"
    # sidewall_print is a DECAL sheet, not a tiling material: v spans the band
    # 0..1 by design, which is how its four printed lines are laid out.
    decals = {"sidewall_print"}
    offenders = {
        f"{geometry}:{suffix}": round(value, 2)
        for (geometry, suffix), value in report.items()
        if suffix not in decals and not 0.55 <= value <= 1.8
    }
    assert not offenders, (
        f"materials rendered off their authored grain size: {offenders} "
        f"(1.00 = metric; full report "
        f"{sorted((f'{g}:{s}', round(v, 2)) for (g, s), v in report.items())})"
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
    for _geometry, suffix, positions, _uvs, faces, _uv_faces in collada:
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
            reference[:, 0] = 0.0  # the radial direction is in y-z
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
    for _geometry, suffix, _positions, _uvs, faces, _uv_faces in collada:
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
    for _geometry, suffix, positions, uvs, faces, uv_faces in collada:
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
    for _geometry, suffix, positions, _uvs, faces, _uv_faces in collada:
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

    for _geometry, suffix, positions, _uvs, faces, _uv_faces in collada:
        if suffix != "sidewall_type":
            continue
        root = _union_find(
            (int(first), int(other)) for first, second, third in faces for other in (second, third)
        )

        volumes: dict[int, float] = {}
        points = positions[faces]
        signed = np.einsum("ij,ij->i", points[:, 0], np.cross(points[:, 1], points[:, 2])) / 6.0
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

    generator = (EXAMPLE_ROOT / "blender" / "create_colossus_tire.py").read_text(encoding="utf-8")
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


def _components(faces):
    """Connected components of a triangle soup, by shared vertex index."""

    parent = {}

    def root(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for first, second, third in faces:
        for other in (second, third):
            a, b = root(int(first)), root(int(other))
            if a != b:
                parent[a] = b
    groups = {}
    for index, face in enumerate(faces):
        groups.setdefault(root(int(face[0])), []).append(index)
    return list(groups.values())


def test_every_closed_solid_in_the_shipped_mesh_has_positive_volume(collada):
    """The orientation rule that has no escape hatch.

    assert_face_orientation declines to judge any face whose normal is not
    dominantly radial or axial, which is how the buttress wrap's two end walls
    and its bottom lip shipped inside out - 1,020 edges in one object - and
    how NINE of the fourteen port gussets shipped inside out after that, on
    the surface the player boards through. Signed volume needs no reference
    direction: a closed shell wound outward encloses a positive volume and one
    wound inward encloses a negative one, and that is true of a bolt head, a
    glyph, a gusset and a lifting lug alike.

    Only CLOSED components are judged. An open shell - a lug sitting on the
    tread, a bezel plate - has no volume to speak of and is judged by the
    winding-consistency gate instead.
    """

    import collections

    import numpy as np

    offenders = {}
    judged = 0
    for _geometry, suffix, positions, _uvs, faces, _uv_faces in collada:
        signed = (
            np.einsum(
                "ij,ij->i",
                positions[faces][:, 0],
                np.cross(positions[faces][:, 1], positions[faces][:, 2]),
            )
            / 6.0
        )
        for group in _components(faces):
            sub = faces[group]
            edges = collections.Counter()
            for first, second, third in sub:
                for edge in ((first, second), (second, third), (third, first)):
                    edges[tuple(sorted(edge))] += 1
            if any(count == 1 for count in edges.values()):
                continue
            judged += 1
            volume = float(signed[group].sum())
            if volume <= 1e-9:
                offenders[suffix] = offenders.get(suffix, 0) + 1

    assert judged > 20, f"only {judged} closed solids found; the sweep is not working"
    assert not offenders, (
        f"closed solids wound inside out or collapsed: {offenders} "
        f"(of {judged} judged); BeamNG culls every one of them to a hole"
    )


def test_the_shipped_mesh_is_already_welded(collada):
    """Nothing coincident may still be separate in the file that ships.

    The generator builds one Blender object per surface so the orientation
    rules can name each one, and joining them for export left every shared
    ring as two coincident vertex sets: 12,026 boundary edges and 4,666 m of
    them shipped, and down both edges of the drive lane 554 vertex pairs
    carried a 30.75 degree median normal split across geometry that bends
    2.5 - a hard false crease running the full 84 m circumference on the
    surface the driver stares at for the whole ride. If welding the shipped
    bytes changes anything, the shipped bytes were not welded.
    """

    import collections

    import numpy as np

    per_geometry = collections.defaultdict(list)
    positions_of = {}
    for geometry, _suffix, positions, _uvs, faces, _uv_faces in collada:
        per_geometry[geometry].append(faces)
        positions_of[geometry] = positions

    report = {}
    for geometry, chunks in per_geometry.items():
        faces = np.concatenate(chunks)
        positions = positions_of[geometry]
        keys = np.round(positions * 1e6).astype(np.int64)
        _, inverse = np.unique(keys, axis=0, return_inverse=True)
        before = collections.Counter()
        after = collections.Counter()
        for triangle, welded in zip(faces, inverse[faces], strict=True):
            for index in range(3):
                pair = (triangle[index], triangle[(index + 1) % 3])
                before[tuple(sorted(pair))] += 1
                pair = (welded[index], welded[(index + 1) % 3])
                after[tuple(sorted(pair))] += 1
        report[geometry] = (
            sum(1 for count in before.values() if count == 1),
            sum(1 for count in after.values() if count == 1),
        )

    offenders = {
        geometry: f"{raw} -> {welded}"
        for geometry, (raw, welded) in report.items()
        if raw != welded
    }
    assert not offenders, (
        f"welding the shipped mesh closes boundary edges that should already "
        f"be closed: {offenders} - every one of those is a shading seam"
    )
