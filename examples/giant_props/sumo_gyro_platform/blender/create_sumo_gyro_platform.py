"""Deterministic Blender generator for The Free-Pivot Sumo Gyro-Platform.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/sumo_gyro_platform/blender/create_sumo_gyro_platform.py

Structure of this file:

* surface functions (``dish_z``, ``deck_under_z``, ``apron_z``, ``ramp_z``,
  ``ground_z``) - the ONLY place a height is defined. The visual mesh, the
  collision cage and the runtime all sample these, so no dimension is ever
  retyped (AGENTS.md: "cage constants derived half from spec and half from
  literals will drift").
* two local mesh primitives, ``lathe`` and ``strip``. proplib has boxes,
  cylinders and tori but no surface of revolution and no ruled strip, and
  proplib is off limits this round, so they live here.
* ``build_visual`` (static flexbody), ``build_parts`` (the tilting deck and
  the moving hardware), ``build_cage`` (fixed collision), ``main``.

Geometry asserts run inside ``build_cage``/``main``; Blender exits 0 on a
Python error, so the build loop greps the log for ``Traceback``.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))

import bmesh  # noqa: E402
import bpy  # noqa: E402
import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

# 48 azimuth segments everywhere a ring is drawn. Chordal error at the 13.1 m
# rim is r * (1 - cos(3.75 deg)) = 0.028 m, below the 0.035 m the committed
# pose itself can move, so refining further buys nothing a driver can feel.
# The cage and the visual use the SAME number so their circles coincide.
SEGMENTS = 48

DISH_R = spec.DISH_RADIUS
DECK_R = spec.DECK_RADIUS
LIP_CREST_R = spec.LIP_CREST_R
PIVOT_Z = spec.PIVOT_Z
TILT_MAX = spec.TILT_MAX_RAD

RAMP_AZ = math.radians(spec.RAMP_AZIMUTH_DEG)
RAMP_HW = spec.RAMP_HALF_WIDTH
RAMP_OUT_R = spec.RAMP_OUTER_R
RAMP_KERB = spec.RAMP_KERB_HEIGHT
MOUTH_R = spec.MOUTH_CURTAIN_R

# Rim ring girder and the drain moat it sweeps into. Both are derived in
# spec.py from the boarding threshold; nothing here retypes a number.
RIM_SKIRT_Z = spec.RIM_SKIRT_Z
HAUNCH_R = spec.GIRDER_HAUNCH_R
MOAT_IN_R = spec.MOAT_INNER_R
MOAT_Z = spec.MOAT_FLOOR_Z

# Gate windows. Each is derived from the thing that has to pass through it,
# and each is asserted against the filler in build_cage - the centrifuge shipped
# three different numbers for one doorway and lit a slot at every jamb.
#   lip gate  : lane half width + 0.30 m of paint margin, at the lip foot.
#   wall gate : bracketed from both sides. It must clear the ramp kerb
#               (>= 3.82 m of half-chord at 13.30 m, i.e. 16.7 deg) and it must
#               stay narrow enough that the ramp embankment still plugs it once
#               the face-quantised cut has widened it by one 7.5 deg face
#               (<= 18.3 deg). 17.5 sits in the middle; both bounds are
#               asserted in _assert_geometry.
LIP_GATE_HALF = math.asin((RAMP_HW + 0.30) / DISH_R)
WALL_GATE_HALF = math.radians(17.5)

# Ramp crest: interpolate GRADE from the deck's own outward slope at the rim to
# the running grade over RAMP_CREST_RUN metres and integrate. Never blend two
# height datums (AGENTS.md round-14: a smoothstep between two planes peaked at
# 23% mid-window and stalled automatics at creep throttle).
RAMP_TUCK = 0.012  # ramp top parked 12 mm under the deck edge: a hem, not a step
RAMP_Z0 = spec.DECK_TOP_Z + spec.DISH_RISE * (DECK_R / DISH_R) ** 2 - RAMP_TUCK
RAMP_G0 = 2.0 * spec.DISH_RISE * DECK_R / (DISH_R * DISH_R)
RAMP_RUN = spec.RAMP_CREST_RUN
RAMP_LEN = RAMP_OUT_R - DECK_R
# Solve for the running grade that lands the outer end exactly on grade:
#   integral(g) = g0*L + (g1-g0)*(L - run/2) = -RAMP_Z0
RAMP_G1 = (-RAMP_Z0 - RAMP_G0 * RAMP_LEN) / (RAMP_LEN - RAMP_RUN / 2.0) + RAMP_G0

YAW_POST_TOP_Z = 0.90

# The status pylon that used to stand at SCOREBOARD_AZIMUTH_DEG - a colour
# semaphore, a rider tally and a painted plate explaining what the colours
# meant - went out in the 2026-08-13 player round: "having a sign give
# instructions isn't intuitive game design". Everything it said, the match
# board now shows by hardware, so its frame helpers went with it.


def sb_pip_x(side_sign: float, index: int) -> float:
    """Centre x of win-pip cell ``index`` (0..4) on the match scoreboard:
    EAST column at -SB_COL_X (side_sign -1.0), WEST at +SB_COL_X (+1.0).

    ONE function feeds both the face apertures (build_visual) and the gold
    pucks that show through them (build_parts), so the opening and the thing
    that fills it are cut from the same number (AGENTS.md)."""

    return side_sign * spec.SB_COL_X + (index - 2) * spec.SB_PIP_PITCH


# --- spin drive ------------------------------------------------------------
# Frame for the flywheel bay: the drive stands in the same bay as the skid
# that powers it, and every dimension comes from spec (the tread MUST meet
# the deck edge, so nothing here may be drawn by eye).
DRIVE_AZ = math.radians(spec.DRIVE_AZIMUTH_DEG)
DRIVE_CX = spec.DRIVE_AXIS_R * math.cos(DRIVE_AZ)
DRIVE_CY = spec.DRIVE_AXIS_R * math.sin(DRIVE_AZ)
DRIVE_MID_Z = 0.5 * (spec.DRIVE_FACE_LO + spec.DRIVE_FACE_HI)


# --- nobori cloth ----------------------------------------------------------
# The banners are REAL soft-body cloth on BeamNG's physics ground wind, the
# stock utv_flags recipe as proven in the goal-post mod: gram-scale nodes on
# |NM_CLOTH, stiff structural beams, near-zero-stiffness diagonals so the
# sheet folds like textile instead of flexing like a plate, and dragCoef on
# the TRIANGLES - cloth with no triangles is invisible to the air. A posed
# rigid banner could only ever be an animation that ignores the actual wind.
#
# Grid is coarse next to the goal post's 0.12 m ribbon pitch: these are 3 m
# banners, and this is the coarsest grid that still reads as folding.
NOBORI_ROWS = 8
NOBORI_COLS = 4
NOBORI_DRAG_COEF = 10.0   # stock utv_flags value; jbeam scales it by 0.01
# Node mass is NOT the stock 1 gram. Drag scales with triangle AREA and these
# panels carry ~24x the area of a goal-post flag triangle, so stock masses
# would take 24x the acceleration and tear themselves apart. Sized instead by
# AREAL DENSITY: the goal-post flag runs 0.25 kg/m^2 of free cloth, and the
# same figure over a 0.95 x 3.15 m banner's 32 nodes is 23 g a node.
NOBORI_NODE_KG = 0.022
NOBORI_ANCHOR_KG = 0.6
NOBORI_POLE_R = 0.055
NOBORI_HOIST_OFF = 0.135   # hoist edge stands clear of the pole it laces to


def _nobori_sites():
    """Every banner, as ONE list both the render meshes and the cage grid are
    built from. Six ring the arena on the apron crest; two flank the gate."""

    sites = []
    for index, azimuth_deg in enumerate((20.0, 65.0, 110.0, 155.0, 200.0, 335.0)):
        azimuth = math.radians(azimuth_deg)
        radius = 21.5
        sites.append({
            "tag": f"ring_{index}",
            "x": radius * math.cos(azimuth),
            "y": radius * math.sin(azimuth),
            "base_z": apron_z(radius),
            "face": azimuth + math.pi / 2.0,
            "pole_h": 4.6,
            "width": 0.95,
            "height": 3.15,
            "indigo": index % 2 == 1,
        })
    for tag, sign in (("l", -1.0), ("r", 1.0)):
        sites.append({
            "tag": f"gate_{tag}",
            "x": sign * 7.9,
            "y": -22.8,
            "base_z": apron_z(math.hypot(7.9, 22.8)),
            "face": 0.0,
            "pole_h": 5.2,
            "width": 1.05,
            "height": 3.6,
            "indigo": sign > 0,
        })
    for site in sites:
        # Cloth hangs from just under the head rod, laced along it and down
        # the hoist edge to the pole - which is where a real nobori's chichi
        # loops are, and (the goal post's dated lesson) keeps the sheet from
        # spawning INSIDE the pole it hangs on.
        site["top_z"] = site["base_z"] + site["pole_h"] - 0.16
    return tuple(sites)


_NOBORI_SITES = None


def nobori_sites():
    """The site list, built once. Lazy because it reads apron_z, which is
    defined further down the file - and because build_visual and build_cage
    MUST see the identical list or the cloth and its cage would disagree."""

    global _NOBORI_SITES
    if _NOBORI_SITES is None:
        _NOBORI_SITES = _nobori_sites()
    return _NOBORI_SITES


def nobori_surface(site):
    """Rest pose sampler for one banner: ``s`` runs 0..1 from the head rod to
    the free hem, ``w`` runs 0..1 from the hoist edge to the fly edge.

    The SAME sampler feeds the render mesh and the soft-body cage grid, so
    the flexbody's rest pose sits exactly on its nodes - author them apart
    and the skinned mesh spawns distorted. It is a light-air hang, not a
    streaming banner: the solver does the streaming once the wind reaches it,
    and a pre-shaped rest pose only fights it.
    """

    dx, dy = math.cos(site["face"]), math.sin(site["face"])
    nx, ny = -dy, dx

    def sample(s, w):
        along = NOBORI_HOIST_OFF + w * site["width"]
        belly = 0.05 * (w ** 1.5) + 0.03 * s * w
        return (
            site["x"] + dx * along + nx * belly,
            site["y"] + dy * along + ny * belly,
            site["top_z"] - s * site["height"],
        )

    return sample


# ---------------------------------------------------------------------------
# Surface functions - the single source of truth for every height
# ---------------------------------------------------------------------------
def dish_z(radius: float) -> float:
    """Deck top surface, untilted. Quadratic dish, extended past the lip foot
    so the lip band and the boarding gate share one curve."""

    return spec.DECK_TOP_Z + spec.DISH_RISE * (radius / DISH_R) ** 2


def lip_z(radius: float) -> float:
    """Rolled kerb profile over the band [DISH_R, DECK_R]: up to the crest,
    then a small fall so the outer edge reads as rolled rather than sawn."""

    if radius <= DISH_R:
        return dish_z(radius)
    if radius <= LIP_CREST_R:
        frac = (radius - DISH_R) / (LIP_CREST_R - DISH_R)
        return dish_z(radius) + spec.LIP_HEIGHT * math.sin(frac * math.pi / 2.0)
    frac = (radius - LIP_CREST_R) / (DECK_R - LIP_CREST_R)
    return dish_z(radius) + spec.LIP_HEIGHT * (1.0 - 0.27 * frac * frac)


def deck_under_z(radius: float) -> float:
    """Deck soffit over the field of the dish: the dish offset down by the
    box-section depth. Outboard of GIRDER_HAUNCH_R the soffit is replaced by
    the rim ring girder's haunch (see girder_z)."""

    return dish_z(radius) - spec.DECK_THICKNESS


def girder_z(radius: float) -> float:
    """Underside of the deck at the rim: the general soffit haunched down to
    RIM_SKIRT_Z at the deck edge. This is the surface that seals the boarding
    threshold, so it is a straight taper (one plate, one weld line) rather
    than anything a fabricator would have to roll."""

    if radius <= HAUNCH_R:
        return deck_under_z(radius)
    frac = (radius - HAUNCH_R) / (DECK_R - HAUNCH_R)
    return deck_under_z(HAUNCH_R) + (RIM_SKIRT_Z - deck_under_z(HAUNCH_R)) * frac


def deck_bottom_z(radius: float) -> float:
    """Lowest authored point of the deck at this radius, whichever member
    carries it. Used by the clearance asserts."""

    return girder_z(radius) if radius > HAUNCH_R else deck_under_z(radius)


def tilted(radius: float, height: float, angle: float) -> tuple[float, float]:
    """(radius, z) of a deck point after a tilt of ``angle`` about a horizontal
    axis through the bearing. Used only by the clearance asserts."""

    rel = height - PIVOT_Z
    return (
        radius * math.cos(angle) + rel * math.sin(angle),
        PIVOT_Z - radius * math.sin(angle) + rel * math.cos(angle),
    )


def apron_z(radius: float) -> float:
    """Landing apron: a catch berm that rises away from the guard wall and
    falls back to meet the terrain flush at its outer edge."""

    if radius <= spec.APRON_INNER_R or radius >= spec.APRON_OUTER_R:
        return 0.0
    frac = (radius - spec.APRON_INNER_R) / (spec.APRON_OUTER_R - spec.APRON_INNER_R)
    return spec.APRON_CREST_Z * math.sin(frac * math.pi)


def ground_z(radius: float) -> float:
    """Whatever the ramp embankment has to reach down to at this radius.

    Inside the guard wall the floor is the base plate, except across the drain
    moat under the rim girder - the ramp embankment's inner end lands IN the
    moat, so its flanks and its mouth curtain have to be carried down to the
    moat floor or the embankment would stand on nothing at the doorway."""

    if radius <= MOAT_IN_R:
        return spec.UNDER_DECK_Z
    if radius <= spec.WALL_INNER_R:
        return MOAT_Z
    if radius < spec.APRON_INNER_R:
        return 0.0
    return apron_z(radius)


def ramp_z(radius: float) -> float:
    """Boarding ramp running surface, from the integrated grade profile."""

    s = radius - DECK_R
    if s <= 0.0:
        return RAMP_Z0
    if s <= RAMP_RUN:
        return RAMP_Z0 + RAMP_G0 * s + (RAMP_G1 - RAMP_G0) * s * s / (2.0 * RAMP_RUN)
    crest = RAMP_Z0 + RAMP_G0 * RAMP_RUN + (RAMP_G1 - RAMP_G0) * RAMP_RUN / 2.0
    return crest + RAMP_G1 * (s - RAMP_RUN)


def ramp_grade(radius: float) -> float:
    s = max(0.0, radius - DECK_R)
    return RAMP_G0 + (RAMP_G1 - RAMP_G0) * min(1.0, s / RAMP_RUN)


def ramp_flank_x(radius: float) -> float:
    """Outer edge of the ramp embankment: the kerb top let down to grade at
    45 degrees, so a car that leaves the ramp sideways meets a slope, never a
    wall, and the embankment is wide enough to plug the guard-wall gate."""

    drop = ramp_z(radius) + RAMP_KERB - ground_z(radius)
    return RAMP_HW + 0.32 + max(0.0, drop)


def azimuth_in_gate(angle: float, half: float) -> bool:
    delta = (angle - RAMP_AZ + math.pi) % (2.0 * math.pi) - math.pi
    return abs(delta) <= half


def face_in_gate(first: float, second: float, half: float) -> bool:
    """A face belongs to the gate when EITHER of its azimuth edges is inside
    the window. The cage drops nodes by azimuth and therefore drops exactly
    the same faces, so cage and visual cut identical holes - and the filler,
    selected with the same predicate, is the exact complement rather than
    something a couple of degrees narrower (AGENTS.md: an opening and the
    thing that fills it must be cut from the same number)."""

    return azimuth_in_gate(first, half) or azimuth_in_gate(second, half)


# ---------------------------------------------------------------------------
# Local mesh primitives
# ---------------------------------------------------------------------------
def _finish(obj, material, orient: str) -> object:
    """Assign, orient and smooth. ``orient`` is 'solid' (bmesh decides outward),
    'up' (mean +Z: the AGENTS.md rule for open surfaces, which recalc cannot
    orient because they have no inside), or 'none'."""

    mesh = obj.data
    if orient == "solid":
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()
    elif orient == "up":
        mesh.calc_loop_triangles()
        if sum(polygon.normal.z for polygon in mesh.polygons) < 0.0:
            mesh.flip_normals()
    mesh.update()
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(34.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def _build(name, material, verts, faces, uvs, orient):
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return _finish(obj, material, orient)


def lathe(
    name,
    material,
    profile,
    *,
    segments=SEGMENTS,
    gate_half=None,
    inside_gate=False,
    tile=(1.6, 1.6),
    orient="up",
):
    """Surface of revolution about +Z through a (radius, z) profile.

    ``gate_half`` skips (or, with ``inside_gate``, keeps only) the faces whose
    azimuth midpoint falls in the boarding window. Deciding per MIDPOINT means
    the real hole is up to one face wider than nominal - the filler geometry is
    sized with that margin (AGENTS.md).

    UVs are metric: u runs along the circumference (r * theta), v along the
    profile arc length, both divided by ``tile``. Uniform texel density on a
    cone band cannot be had from primitive UVs.
    """

    arc = [0.0]
    for index in range(1, len(profile)):
        previous, current = profile[index - 1], profile[index]
        arc.append(arc[-1] + math.hypot(current[0] - previous[0], current[1] - previous[1]))

    # A profile that starts on the axis collapses its first ring to a point;
    # emitting 48 coincident vertices there would make 48 degenerate quads.
    pole = abs(profile[0][0]) < 1e-6
    verts = []
    uvs = []
    if pole:
        verts.append((0.0, 0.0, profile[0][1]))
        uvs.append((0.0, 0.0))
    for index, (radius, height) in enumerate(profile):
        if pole and index == 0:
            continue
        for j in range(segments):
            angle = 2.0 * math.pi * j / segments
            verts.append((radius * math.cos(angle), radius * math.sin(angle), height))
            uvs.append((radius * angle / tile[0], arc[index] / tile[1]))

    def vindex(index, j):
        if pole and index == 0:
            return 0
        return (1 if pole else 0) + (index - (1 if pole else 0)) * segments + j

    faces = []
    for index in range(len(profile) - 1):
        for j in range(segments):
            k = (j + 1) % segments
            if gate_half is not None:
                first = 2.0 * math.pi * j / segments
                second = 2.0 * math.pi * k / segments
                if face_in_gate(first, second, gate_half) != inside_gate:
                    continue
            a = vindex(index, j)
            b = vindex(index, k)
            c = vindex(index + 1, k)
            d = vindex(index + 1, j)
            # (inner_j, outer_j, outer_k, inner_k) has normal r_hat x theta_hat
            # = +Z for a profile that advances outward; deriving quad winding by
            # hand is the classic own-goal, so this one ordering is used
            # everywhere and 'orient' fixes the rest.
            if a == b:
                faces.append((a, d, c))
            else:
                faces.append((a, d, c, b))
    return _build(name, material, verts, faces, uvs, orient)


def _tube(name, start, end, radius, material, *, sides=16, tile=0.9):
    """Cylinder between two arbitrary authored points. proplib's add_cylinder
    only offers the three world axes, and every ram member on this machine is
    raked, so the primitive is built along +Z and then rotated onto the span
    and the rotation is APPLIED (a live rotation would not survive the join
    at export)."""

    from mathutils import Vector

    first, second = Vector(start), Vector(end)
    span = second - first
    length = span.length
    middle = (first + second) / 2.0
    obj = bk.add_cylinder(
        name,
        (middle.x, middle.y, middle.z),
        radius,
        length,
        material,
        vertices=sides,
        metric_uv=(tile, tile),
    )
    obj.rotation_euler = (
        Vector((0.0, 0.0, 1.0)).rotation_difference(span.normalized()).to_euler()
    )
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    obj.select_set(False)
    return obj


def revolved_solid(
    name: str,
    loop: list[tuple[float, float]],
    material,
    *,
    origin: tuple[float, float, float],
    axis: tuple[float, float, float],
    segments: int = 20,
    uv_meters: float = 0.9,
) -> object:
    """Solid of revolution: a CLOSED ``(t, r)`` loop swept about ``axis``.

    ``lathe`` above turns about +Z through an OPEN profile, which is right for
    every ring on this machine and useless for a PA horn: the bells hang off
    the pole horizontally, and a bell is a SHELL - outer flare, throat, inner
    flare, rolled lip - so you can see down the inside of the mouth to the
    driver badge. A capped cone can never show that, and four stacked cones
    shade with visible steps because they are four objects under one
    auto-smooth. Ported from the pachinko tower's horn pole, which is where
    this whole assembly comes from.

    ``t`` runs along +axis from ``origin``, ``r`` is the distance off it. A
    station with ``r == 0`` collapses to one pole vertex and its neighbouring
    ring fans to it, so a capped cylinder and a dome are the same call, and
    ``segments=6`` makes a hex nut out of the same machinery.
    """

    from mathutils import Vector

    ax = Vector(axis).normalized()
    seed = Vector((0.0, 0.0, 1.0))
    if abs(ax.dot(seed)) > 0.9:
        seed = Vector((1.0, 0.0, 0.0))
    u = ax.cross(seed).normalized()
    v = ax.cross(u)
    base = Vector(origin)

    verts: list[tuple[float, float, float]] = []
    rings: list[list[int]] = []
    for t, r in loop:
        centre = base + ax * t
        if abs(r) < 1e-6:
            rings.append([len(verts)])
            verts.append(tuple(centre))
            continue
        ring = []
        for k in range(segments):
            angle = 2.0 * math.pi * k / segments
            point = centre + u * (r * math.cos(angle)) + v * (r * math.sin(angle))
            ring.append(len(verts))
            verts.append(tuple(point))
        rings.append(ring)

    faces = []
    count = len(rings)
    for index in range(count):
        a_ring, b_ring = rings[index], rings[(index + 1) % count]
        if len(a_ring) == 1 and len(b_ring) == 1:
            continue
        if len(a_ring) == 1:
            apex = a_ring[0]
            for k in range(segments):
                faces.append((apex, b_ring[k], b_ring[(k + 1) % segments]))
        elif len(b_ring) == 1:
            apex = b_ring[0]
            for k in range(segments):
                faces.append((a_ring[k], a_ring[(k + 1) % segments], apex))
        else:
            for k in range(segments):
                j = (k + 1) % segments
                faces.append((a_ring[k], a_ring[j], b_ring[j], b_ring[k]))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.add_metric_box_uvs(obj, meters_per_tile=(uv_meters, uv_meters))
    return _finish(obj, material, "solid")


def _along(origin, direction, distance):
    return (
        origin[0] + direction[0] * distance,
        origin[1] + direction[1] * distance,
        origin[2] + direction[2] * distance,
    )


def ram_frame(index):
    """Foot, eye and the as-built unit axis of one centring ram.

    The runtime rebuilds exactly this from the same four handoff constants
    (ram_foot_r/z, ram_eye_r/z), so the aim rotation it applies is the
    identity at rest and the authored pose IS the rest pose."""

    angle = index * math.pi / 2.0
    cosine, sine = math.cos(angle), math.sin(angle)
    foot = (spec.RAM_FOOT_R * cosine, spec.RAM_FOOT_R * sine, spec.RAM_FOOT_Z)
    eye = (spec.RAM_EYE_R * cosine, spec.RAM_EYE_R * sine, spec.RAM_EYE_Z)
    length = math.dist(foot, eye)
    return {
        "foot": foot,
        "eye": eye,
        "length": length,
        "axis": tuple((eye[i] - foot[i]) / length for i in range(3)),
        # Tangential: the pin axis of both clevises.
        "cross": (-sine, cosine, 0.0),
    }


def strip(name, material, rows, *, tile=(2.5, 2.5), orient="up"):
    """Ruled surface over a grid of rows x columns of authored points."""

    verts = []
    uvs = []
    columns = len(rows[0])
    across = [0.0]
    for index in range(1, columns):
        first, second = rows[0][index - 1], rows[0][index]
        across.append(across[-1] + math.dist(first, second))
    along = [0.0]
    for index in range(1, len(rows)):
        along.append(along[-1] + math.dist(rows[index - 1][0], rows[index][0]))
    for row_index, row in enumerate(rows):
        for column_index, point in enumerate(row):
            verts.append(point)
            uvs.append((across[column_index] / tile[0], along[row_index] / tile[1]))
    faces = []
    for row_index in range(len(rows) - 1):
        for column_index in range(columns - 1):
            a = row_index * columns + column_index
            b = row_index * columns + column_index + 1
            c = (row_index + 1) * columns + column_index + 1
            d = (row_index + 1) * columns + column_index
            faces.append((a, b, c, d))
    return _build(name, material, verts, faces, uvs, orient)


def marquee_sheet(name, material, bl, br, tl, tr, width, height):
    """One quad carrying a marquee-family texture at TRUE letter proportions.

    The marquee family draws its text for a ~9.55:1 panel
    (texture_kit.marquee): mapping the full 0..1 range onto a squarer plate
    condenses the type by the aspect mismatch (the scoreboard's 2.7:1 result
    plates would show 3.5x-condensed capitals). Mapping only the CENTRAL
    ``aspect / 9.55`` window of u keeps the letters true on any plate - the
    short words this board uses span < 0.24 of u, so nothing is cropped, and
    outside the letters the texture is uniform field colour anyway.

    Corners are given in the READER's frame (``bl`` = their lower-left), so
    the caller owns the torii boards' reading-direction law; the winding
    bl->br->tr->tl then faces the reader by construction."""

    frac = min(1.0, (width / height) / 9.55)
    u0, u1 = 0.5 - frac / 2.0, 0.5 + frac / 2.0
    verts = [bl, br, tl, tr]
    uvs = [(u0, 0.0), (u1, 0.0), (u0, 1.0), (u1, 1.0)]
    return _build(name, material, verts, [(0, 1, 3, 2)], uvs, "none")


def display_sheet(name, material, bl, br, tl, tr, u0, u1):
    """One quad sampling the u range [u0, u1] of a LIVE page.

    The name webview is one 1510x256 texture holding BOTH corners side by
    side, so a panel takes its own half of u rather than the whole 0..1
    frame. Corners are in the READER's frame (``bl`` = their lower-left),
    like marquee_sheet, so the winding faces them by construction and each
    of the board's two faces reads the right way round."""

    verts = [bl, br, tl, tr]
    uvs = [(u0, 0.0), (u1, 0.0), (u0, 1.0), (u1, 1.0)]
    return _build(name, material, verts, [(0, 1, 3, 2)], uvs, "none")


def ramp_radii(stations=12):
    """Row radii. Station 0 is the deck edge (the nosing) and station 1 is the
    mouth curtain, 0.16 m outboard of it; the rest are evenly spaced out to
    the ground. The curtain has to stand clear of the deck's widest swept
    point (r 13.171, the lip's outer top corner at full down-tilt) or the deck
    slices through it every time the ring leans toward the ramp."""

    radii = [DECK_R, MOUTH_R]
    for index in range(1, stations):
        radii.append(DECK_R + RAMP_LEN * index / (stations - 1))
    return radii


def ramp_rows():
    """Constant-RADIUS rows. A straight-ended slab can never meet a circular
    lip (AGENTS.md): its corners leave crescents of open air. Sampling the ramp
    on arcs makes its inner edge the deck's own circle by construction, and
    since z is a function of radius alone every row is dead level across the
    lane - zero cross-lane warp, the round-15 arc-tongue lesson."""

    rows = []
    for radius in ramp_radii():
        surface = ramp_z(radius)
        flank = ramp_flank_x(radius)
        row = []
        for offset, height in (
            (-flank, ground_z(radius)),
            (-(RAMP_HW + 0.32), surface + RAMP_KERB),
            (-RAMP_HW, surface),
            (-RAMP_HW / 2.0, surface),
            (0.0, surface),
            (RAMP_HW / 2.0, surface),
            (RAMP_HW, surface),
            (RAMP_HW + 0.32, surface + RAMP_KERB),
            (flank, ground_z(radius)),
        ):
            # Rotate the (x, -sqrt(r^2-x^2)) arc point onto the ramp azimuth.
            depth = math.sqrt(max(0.0, radius * radius - offset * offset))
            local_x, local_y = offset, -depth
            cos_a = math.cos(RAMP_AZ + math.pi / 2.0)
            sin_a = math.sin(RAMP_AZ + math.pi / 2.0)
            row.append(
                (
                    local_x * cos_a - local_y * sin_a,
                    local_x * sin_a + local_y * cos_a,
                    height,
                )
            )
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


# ---------------------------------------------------------------------------
# Static structure (flexbody visual)
# ---------------------------------------------------------------------------
def build_horn_pole(materials) -> list:
    """The PA horn pole: a street-light-height steel standard beside the
    scoreboard carrying four horns at 90 degrees.

    Ported from the pachinko tower's round-8 cluster, item for item, because
    the player asked for that one. The hardware vocabulary is its reference
    photo's: a flared bell whose INSIDE you can see (so the driver badge reads
    through the mouth), a cylindrical driver body with a clamp seam, a
    U-bracket with a row of adjuster holes and a wing bolt at the pivot, and -
    because a real pole is mostly fixings - a bolted base flange, a hand-hole
    cover, a junction box and a clipped conduit riser feeding the cluster.

    TWO SCALES ON PURPOSE. The POLE is a genuine 9-10 m street light, which is
    what was asked for. The horn ASSEMBLY outboard of the yoke is scaled by
    spec.HORN_SCALE for legibility from the deck, because a real 0.4 m bell
    9 m up would be a speck. Pachinko says the same thing about the same
    hardware: the pole has to read as a street light, the horns have to read
    as horns.

    Unlike pachinko's, this pole stands on a LANDING APRON, so it is not
    theatre - build_cage gives it the scoreboard tower's box-lattice body and
    cars bounce off it.
    """

    steel = materials[f"{MOD_ID}_steel"]
    chrome = materials[f"{MOD_ID}_rod_chrome"]
    enamel = materials[f"{MOD_ID}_horn_enamel"]
    brass = materials[f"{MOD_ID}_pip_gold"]
    dark = materials[f"{MOD_ID}_lacquer_black"]

    px, py = spec.HORN_POLE_X, spec.HORN_POLE_Y
    grade = spec.HORN_APRON_Z
    # The generator's own berm profile has to agree with the one spec derived,
    # or the flange floats or buries.
    assert abs(apron_z(spec.HORN_POLE_R) - grade) < 1e-9, "horn pole grade drift"
    base_z = grade - spec.HORN_POLE_BURY
    bury = spec.HORN_POLE_BURY
    height = spec.HORN_POLE_H
    axis_h = spec.HORN_AXIS_H
    axis_z = spec.HORN_AXIS_Z
    r0, r1 = spec.HORN_POLE_R0, spec.HORN_POLE_R1
    objects: list = []

    def shaft_r(above: float) -> float:
        """Radius of the tapered shaft at ``above`` metres over grade."""

        t = (above - 0.75) / (height - 0.10 - 0.75)
        return r0 + (r1 - r0) * min(max(t, 0.0), 1.0)

    # ---- shaft: one tapered tube, base swage included ---------------------
    swell = r0 + 0.030
    shaft_loop = [(0.0, 0.0), (0.0, swell), (bury + 0.55, swell), (bury + 0.75, r0)]
    for above in (2.6, 5.0, 7.4, height - 0.10):
        shaft_loop.append((bury + above, shaft_r(above)))
    shaft_loop += [(bury + height, r1 - 0.020), (bury + height, 0.0)]
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_pole_shaft", shaft_loop, steel,
        origin=(px, py, base_z), axis=(0.0, 0.0, 1.0), segments=18,
        uv_meters=1.1))

    # ---- pole cap: a real standard is capped, not left open ---------------
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_pole_cap",
        [(0.0, 0.0), (0.0, r1 + 0.018), (0.045, r1 + 0.030),
         (0.115, r1 - 0.010), (0.150, 0.0)],
        steel, origin=(px, py, grade + height - 0.02), axis=(0.0, 0.0, 1.0),
        segments=18, uv_meters=0.5))

    # ---- base flange and its four anchor bolts ----------------------------
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_base_flange",
        [(0.0, 0.0), (0.0, spec.HORN_FLANGE_R),
         (0.030, spec.HORN_FLANGE_R + 0.012),
         (0.075, spec.HORN_FLANGE_R - 0.010), (0.075, 0.0)],
        steel, origin=(px, py, grade), axis=(0.0, 0.0, 1.0), segments=18,
        uv_meters=0.6))
    for index, (dx, dy) in enumerate(spec.HORN_DIRS):
        bx, by = px + dx * 0.325, py + dy * 0.325
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_base_stud_{index}",
            [(0.0, 0.0), (0.0, 0.030), (0.145, 0.030), (0.145, 0.0)],
            steel, origin=(bx, by, grade + 0.070), axis=(0.0, 0.0, 1.0),
            segments=10, uv_meters=0.25))
        # A six-segment revolve IS a hex nut; no separate primitive needed.
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_base_nut_{index}",
            [(0.0, 0.0), (0.0, 0.055), (0.055, 0.055), (0.055, 0.0)],
            chrome, origin=(bx, by, grade + 0.075), axis=(0.0, 0.0, 1.0),
            segments=6, uv_meters=0.25))

    # ---- hand-hole cover: the detail that says "this pole is wired" -------
    cover_y = py - shaft_r(1.05) - 0.020
    objects.append(bk.add_box(
        f"{MOD_ID}_horn_handhole", (px, cover_y, grade + 1.05),
        (0.17, 0.045, 0.34), steel, bevel=0.012, metric_uv=(0.5, 0.5)))
    for index, sz in enumerate((-0.115, 0.115)):
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_handhole_screw_{index}",
            [(0.0, 0.0), (0.0, 0.026), (0.020, 0.022), (0.020, 0.0)],
            chrome, origin=(px, cover_y - 0.022, grade + 1.05 + sz),
            axis=(0.0, -1.0, 0.0), segments=8, uv_meters=0.2))

    # ---- junction box, lid, gland -----------------------------------------
    box_y = py - shaft_r(1.90) - 0.140
    objects.append(bk.add_box(
        f"{MOD_ID}_horn_jbox", (px, box_y, grade + 1.90), (0.34, 0.26, 0.46),
        enamel, bevel=0.02, metric_uv=(0.7, 0.7)))
    lid_y = box_y - 0.130 - 0.018
    objects.append(bk.add_box(
        f"{MOD_ID}_horn_jbox_lid", (px, lid_y, grade + 1.90),
        (0.30, 0.036, 0.42), enamel, bevel=0.012, metric_uv=(0.7, 0.7)))
    for index, (sx, sz) in enumerate(((-0.125, -0.175), (0.125, -0.175),
                                      (-0.125, 0.175), (0.125, 0.175))):
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_jbox_screw_{index}",
            [(0.0, 0.0), (0.0, 0.024), (0.018, 0.020), (0.018, 0.0)],
            chrome, origin=(px + sx, lid_y - 0.020, grade + 1.90 + sz),
            axis=(0.0, -1.0, 0.0), segments=8, uv_meters=0.2))
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_jbox_gland",
        [(0.0, 0.0), (0.0, 0.052), (0.055, 0.052), (0.075, 0.038), (0.075, 0.0)],
        chrome, origin=(px, box_y, grade + 1.60), axis=(0.0, 0.0, -1.0),
        segments=10, uv_meters=0.25))

    # ---- conduit riser, stood off on P-clips ------------------------------
    riser_y = py - 0.245
    riser_z0, riser_z1 = grade + 2.10, axis_z - 0.80
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_conduit",
        [(0.0, 0.0), (0.0, 0.046), (riser_z1 - riser_z0, 0.046),
         (riser_z1 - riser_z0, 0.0)],
        steel, origin=(px, riser_y, riser_z0), axis=(0.0, 0.0, 1.0),
        segments=12, uv_meters=0.5))
    # ... and the elbow that takes it into the yoke collar.
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_conduit_elbow",
        [(0.0, 0.0), (0.0, 0.046), (0.245, 0.046), (0.245, 0.0)],
        steel, origin=(px, riser_y, riser_z1 - 0.005), axis=(0.0, 1.0, 0.0),
        segments=12, uv_meters=0.5))
    for index, above in enumerate((3.20, 4.90, 6.60)):
        # A P-clip bridges the standoff: from the shaft's own (tapering)
        # surface out to the far side of the pipe.
        y_out = riser_y - 0.046
        y_in = py - shaft_r(above)
        objects.append(bk.add_box(
            f"{MOD_ID}_horn_conduit_clip_{index}",
            (px, (y_out + y_in) / 2.0, grade + above),
            (0.075, y_in - y_out, 0.055),
            steel, bevel=0.008, metric_uv=(0.35, 0.35)))

    # ---- yoke collar: what the four arms hang off -------------------------
    collar_lo, collar_hi = axis_z - 0.86, axis_z + 0.34
    collar_r = shaft_r(axis_h) + 0.075
    objects.append(revolved_solid(
        f"{MOD_ID}_horn_yoke_collar",
        [(0.0, 0.0), (0.0, collar_r - 0.030), (0.045, collar_r),
         (collar_hi - collar_lo - 0.045, collar_r),
         (collar_hi - collar_lo, collar_r - 0.030), (collar_hi - collar_lo, 0.0)],
        steel, origin=(px, py, collar_lo), axis=(0.0, 0.0, 1.0), segments=16,
        uv_meters=0.6))

    # ---- the four horns ---------------------------------------------------
    k = spec.HORN_SCALE
    bell_d = spec.HORN_BELL_D
    bell_len = spec.HORN_BELL_LEN
    drv_len = spec.HORN_DRIVER_LEN
    drv_r = spec.HORN_DRIVER_R
    throat_r = spec.HORN_THROAT_R
    mouth_r = bell_d / 2.0
    rear_r = spec.HORN_REAR_R
    wall = 0.020
    # The U-bracket clamps the driver a quarter of the way along its body,
    # and the arm bridges the collar to it. Both DERIVED from the driver, so
    # re-sizing the bell can never leave the bracket clamping thin air.
    brk_r = rear_r + 0.252 * drv_len
    arm_r0, arm_r1 = collar_r - 0.02, brk_r + 0.06

    # Exponential flare, sampled at eight stations. An exponential horn is what
    # a re-entrant PA driver actually loads into, and it is also the profile
    # whose silhouette reads as "horn" rather than "traffic cone".
    flare = []
    for index in range(8):
        s = index / 7.0
        flare.append((bell_len * s, throat_r * (mouth_r / throat_r) ** s))

    for index, (dx, dy) in enumerate(spec.HORN_DIRS):
        axis = (dx, dy, 0.0)
        yaw = math.atan2(dy, dx)
        wx, wy = -dy, dx                       # the across-the-horn direction

        def at(radial: float, across: float = 0.0, dz: float = 0.0,
               dx=dx, dy=dy, wx=wx, wy=wy):
            return (px + dx * radial + wx * across,
                    py + dy * radial + wy * across,
                    axis_z + dz)

        # yoke arm + diagonal brace back to the collar
        objects.append(bk.add_box(
            f"{MOD_ID}_horn_arm_{index}",
            at((arm_r0 + arm_r1) / 2.0, 0.0, -0.62 * k),
            (arm_r1 - arm_r0, 0.17, 0.15), steel, bevel=0.02,
            rotation=(0.0, 0.0, yaw), metric_uv=(0.5, 0.5)))
        objects.append(bk.add_box(
            f"{MOD_ID}_horn_brace_{index}",
            at((arm_r0 + arm_r1) / 2.0, 0.0, -0.90 * k),
            (arm_r1 - arm_r0 + 0.02, 0.075, 0.055), steel, bevel=0.0,
            rotation=(0.0, math.radians(-52.0), yaw), metric_uv=(0.4, 0.4)))

        # U-bracket: base strap, two arms straddling the driver body
        objects.append(bk.add_box(
            f"{MOD_ID}_horn_ubase_{index}", at(brk_r, 0.0, -0.545 * k),
            (0.42 * k, 0.64 * k, 0.055 * k), steel, bevel=0.012,
            rotation=(0.0, 0.0, yaw), metric_uv=(0.45, 0.45)))
        for side, across in enumerate((-0.292 * k, 0.292 * k)):
            objects.append(bk.add_box(
                f"{MOD_ID}_horn_uarm_{index}_{side}",
                at(brk_r, across, -0.245 * k),
                (0.40 * k, 0.055 * k, 0.605 * k), steel, bevel=0.010,
                rotation=(0.0, 0.0, yaw), metric_uv=(0.45, 0.45)))
            # The reference's row of adjuster holes. Drawn as recessed dark
            # discs rather than booleaned holes: at any camera distance this
            # prop is ever seen from, a dark disc IS a hole, and a boolean
            # through a 43 mm strap costs geometry and a shading seam. The
            # plug spans the whole strap and stands proud on both faces, so it
            # reads as a hole THROUGH the arm from either side rather than as
            # a sticker on one of them.
            for hole in range(4):
                objects.append(revolved_solid(
                    f"{MOD_ID}_horn_uhole_{index}_{side}_{hole}",
                    [(0.0, 0.0), (0.0, 0.034 * k), (0.060 * k, 0.034 * k),
                     (0.060 * k, 0.0)],
                    dark,
                    origin=at(brk_r - 0.14 * k + 0.093 * k * hole,
                              across - 0.030 * k if side == 0
                              else across + 0.030 * k,
                              -0.395 * k),
                    axis=(wx, wy, 0.0) if side == 0 else (-wx, -wy, 0.0),
                    segments=10, uv_meters=0.2))

        # pivot bolt through both arms, with a wing nut on one side
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_pivot_{index}",
            [(0.0, 0.0), (0.0, 0.042 * k), (0.74 * k, 0.042 * k), (0.74 * k, 0.0)],
            chrome, origin=at(brk_r, -0.37 * k, 0.0), axis=(wx, wy, 0.0),
            segments=10, uv_meters=0.25))
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_wingnut_hub_{index}",
            [(0.0, 0.0), (0.0, 0.070 * k), (0.075 * k, 0.070 * k),
             (0.075 * k, 0.0)],
            chrome, origin=at(brk_r, 0.360 * k, 0.0), axis=(wx, wy, 0.0),
            segments=8, uv_meters=0.2))
        for ear, dzz in enumerate((-0.115 * k, 0.115 * k)):
            objects.append(bk.add_box(
                f"{MOD_ID}_horn_wingear_{index}_{ear}",
                at(brk_r, 0.395 * k, dzz),
                (0.075 * k, 0.070 * k, 0.135 * k), chrome, bevel=0.010,
                rotation=(0.0, 0.0, yaw), metric_uv=(0.25, 0.25)))

        # driver body: cylinder with a domed rear and a clamp seam
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_driver_{index}",
            [(0.0, 0.0), (0.0, 0.185 * k), (0.048 * k, 0.240 * k),
             (0.080 * k, drv_r), (drv_len - 0.075 * k, drv_r),
             (drv_len - 0.030 * k, drv_r - 0.020 * k),
             (drv_len, throat_r + 0.010), (drv_len, 0.0)],
            enamel, origin=at(rear_r), axis=axis, segments=20, uv_meters=0.55))
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_seam_{index}",
            [(0.0, 0.0), (0.0, drv_r + 0.022), (0.042 * k, drv_r + 0.022),
             (0.042 * k, 0.0)],
            enamel, origin=at(rear_r + 0.50 * drv_len), axis=axis, segments=20,
            uv_meters=0.3))

        # the bell: a real SHELL, so the badge shows through the mouth
        bell_loop: list[tuple[float, float]] = list(flare)
        bell_loop += [(bell_len + 0.032, mouth_r + 0.014),
                      (bell_len + 0.052, mouth_r),
                      (bell_len + 0.032, mouth_r - 0.016)]
        bell_loop += [(t, max(r - wall, 0.006)) for t, r in reversed(flare)]
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_bell_{index}", bell_loop, enamel,
            origin=at(rear_r + drv_len), axis=axis, segments=24,
            uv_meters=0.65))
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_throat_band_{index}",
            [(0.0, 0.0), (0.0, throat_r + 0.028), (0.055 * k, throat_r + 0.028),
             (0.055 * k, 0.0)],
            chrome, origin=at(rear_r + drv_len - 0.028), axis=axis, segments=20,
            uv_meters=0.25))
        # the badge on the driver throat, seen down the bell
        objects.append(revolved_solid(
            f"{MOD_ID}_horn_badge_{index}",
            [(0.0, 0.0), (0.0, 0.122 * k), (0.024 * k, 0.118 * k),
             (0.024 * k, 0.0)],
            brass, origin=at(rear_r + drv_len + 0.012), axis=axis, segments=16,
            uv_meters=0.2))

    return objects


def build_visual(materials) -> list:
    steel = materials[f"{MOD_ID}_steel"]
    concrete = materials[f"{MOD_ID}_concrete"]
    hazard = materials[f"{MOD_ID}_deck_hazard"]
    asphalt = materials[f"{MOD_ID}_ramp_asphalt"]
    chrome = materials[f"{MOD_ID}_rod_chrome"]
    signage = materials[f"{MOD_ID}_signage"]
    torii_red = materials[f"{MOD_ID}_torii_red"]
    lacquer = materials[f"{MOD_ID}_lacquer_black"]
    marquee = materials[f"{MOD_ID}_marquee"]
    banner_red = materials[f"{MOD_ID}_banner_red"]
    banner_indigo = materials[f"{MOD_ID}_banner_indigo"]
    concrete_dark = materials[f"{MOD_ID}_concrete_dark"]
    cream = materials[f"{MOD_ID}_paint_cream"]
    hpu_legend = materials[f"{MOD_ID}_hpu_legend"]

    objects = []

    # --- landing apron -----------------------------------------------------
    # Ja-no-me: the sand annulus is the largest surface in every wide shot,
    # and one uniform tone read as bare concrete. The same lathe profile is
    # emitted band by band, alternating the raked-sand tone with its ~13%
    # darker sibling (a ~6% delta drowned in the concrete family's own value
    # noise and the annulus went back to one cream disc), so the apron reads
    # as concentric rake bands from distance. Full rings, uniform along their
    # whole arc: bands, never blotches, so nothing here is a pointable
    # landmark (Law 17).
    apron_radii = [
        spec.APRON_INNER_R,
        16.0,
        17.8,
        spec.APRON_CREST_R,
        22.2,
        23.7,
        spec.APRON_OUTER_R,
    ]
    for index, (near, far) in enumerate(zip(apron_radii, apron_radii[1:])):
        objects.append(
            lathe(
                f"{MOD_ID}_apron_band_{index}",
                concrete if index % 2 == 0 else concrete_dark,
                [(near, apron_z(near)), (far, apron_z(far))],
                tile=(3.0, 3.0),
            )
        )

    # --- perimeter guard kerb ---------------------------------------------
    # The installation used to just stop: sand feathered to nothing at r 25
    # and every wide shot bled into bare terrain. A kerbstone ring course at
    # the apron's outermost radius closes the composition - dark concrete
    # curb with an amber painted cap - and tells a driver from any distance
    # where the venue ends. Visual only: the apron still meets the terrain
    # flush for driving and the cage is untouched. Gated at the boarding
    # corridor: 9 deg nominal quantises to a hole of exactly +/-15 deg
    # (faces are 7.5 deg and the ramp azimuth sits on a face boundary),
    # which clears the embankment flank (+/-10.2 deg out here) and the
    # torii posts (+/-12.3 deg at r 25.17); end blocks cap the open lathe
    # sections at the mouth.
    kerb_gate_half = math.radians(9.0)
    kerb_in_r, kerb_out_r = 24.62, 25.14
    kerb_face_in_r, kerb_face_out_r, kerb_top_z = 24.70, 25.06, 0.26
    objects.append(
        lathe(
            f"{MOD_ID}_perimeter_kerb_in",
            concrete_dark,
            [(kerb_in_r, apron_z(kerb_in_r) - 0.02), (kerb_face_in_r, kerb_top_z)],
            gate_half=kerb_gate_half,
            tile=(1.6, 1.6),
            orient="none",
        )
    )
    objects.append(
        lathe(
            f"{MOD_ID}_perimeter_kerb_out",
            concrete_dark,
            [(kerb_face_out_r, kerb_top_z), (kerb_out_r, -0.02)],
            gate_half=kerb_gate_half,
            tile=(1.6, 1.6),
            orient="none",
        )
    )
    # Amber cap: the kerb's top face IS the band (shared profile corners
    # with the curb faces, so nothing is coplanar). Tile derived for
    # on-pattern closure at the band's mean radius - the wall-toe recipe -
    # 130 whole wraps of ~1.2 m tile, ~30 cm stripes.
    kerb_cap_mid = 0.5 * (kerb_face_in_r + kerb_face_out_r)
    kerb_cap_tile = (
        2.0 * math.pi * kerb_cap_mid / round(2.0 * math.pi * kerb_cap_mid / 1.2)
    )
    objects.append(
        lathe(
            f"{MOD_ID}_perimeter_kerb_cap",
            # Concrete, not the chevron it used to wear (2026-08-13 player
            # round: "remove the yellow and black stripe pattern from the
            # outside top edge"). The kerb now reads as one poured curb, and
            # the only hazard yellow left in a wide shot is on surfaces a car
            # can actually meet.
            concrete_dark,
            [(kerb_face_in_r, kerb_top_z), (kerb_face_out_r, kerb_top_z)],
            gate_half=kerb_gate_half,
            tile=(kerb_cap_tile, kerb_cap_tile),
            orient="none",
        )
    )
    for tag, sign in (("l", -1.0), ("r", 1.0)):
        end_az = RAMP_AZ + sign * math.radians(15.0)
        objects.append(
            bk.add_box(
                f"{MOD_ID}_perimeter_kerb_end_{tag}",
                (
                    kerb_cap_mid * math.cos(end_az),
                    kerb_cap_mid * math.sin(end_az),
                    kerb_top_z / 2.0,
                ),
                (kerb_out_r - kerb_in_r + 0.10, 0.30, kerb_top_z),
                concrete_dark,
                bevel=0.02,
                rotation=(0.0, 0.0, end_az),
                metric_uv=(0.8, 0.8),
            )
        )

    # --- guard kerb --------------------------------------------------------
    # The toe keeps the hazard warning (it is the surface a car actually
    # meets); the vertical face above it is painted arena vermilion, so the
    # only yellow band sweeping past a bystander is the deck's own moving one
    # and the fixed wall reads as the arena, not as roadworks. Same profile
    # points, same gate window - only the material seam moved.
    # (Hazard tile 1.2 m, not the 0.6 the short flat pads use: the chevron
    # family draws FOUR stripe periods per tile, so 0.6 put a 15 cm stripe on
    # an 88 m circumference - 148 wraps of sub-pixel gold bead from any wide
    # shot, with a shear seam where the non-integer wrap closed. 1.2 gives
    # 30 cm stripes that cross the 0.49 m band cleanly and 74.0 wraps at the
    # band's mean radius, so the closure lands on-pattern. The b101 law still
    # holds the other way round: the band shows ~1.6 periods of the tile, so
    # the stripes resolve as stripes, not as arbitrary smears.)
    objects.append(
        lathe(
            f"{MOD_ID}_wall_toe",
            hazard,
            [
                (spec.WALL_TOE_R, 0.0),
                (spec.WALL_OUTER_R, spec.WALL_TOE_Z),
            ],
            gate_half=WALL_GATE_HALF,
            tile=(1.2, 1.2),
            orient="none",
        )
    )
    objects.append(
        lathe(
            f"{MOD_ID}_wall_face",
            torii_red,
            [
                (spec.WALL_OUTER_R, spec.WALL_TOE_Z),
                (spec.WALL_OUTER_R, spec.WALL_TOP_Z),
            ],
            gate_half=WALL_GATE_HALF,
            tile=(1.4, 1.4),
            orient="none",
        )
    )
    objects.append(
        lathe(
            f"{MOD_ID}_wall_cap",
            steel,
            [
                (spec.WALL_OUTER_R, spec.WALL_TOP_Z),
                (spec.WALL_INNER_R, spec.WALL_TOP_Z),
                (spec.WALL_INNER_R, spec.UNDER_DECK_Z),
            ],
            gate_half=WALL_GATE_HALF,
            tile=(1.4, 1.4),
            orient="none",
        )
    )

    # --- fixed base under the deck ----------------------------------------
    objects.append(
        lathe(
            f"{MOD_ID}_base_plate",
            concrete,
            [
                (0.9, spec.UNDER_DECK_Z),
                (6.65, spec.UNDER_DECK_Z),
                (MOAT_IN_R, spec.UNDER_DECK_Z),
            ],
            tile=(3.0, 3.0),
        )
    )
    # Drain moat. The rim girder's bottom flange swings to z = -0.554 at full
    # down-tilt, so the pit floor is stepped down under it. Full circle: a
    # gated trench would need end caps, gated cage rings and a THIRD gate
    # window to keep consistent with, and an opening and the thing that fills
    # it must be cut from the same number (AGENTS.md). Its outer wall is the
    # guard kerb's own foundation, aliased rather than rebuilt.
    objects.append(
        lathe(
            f"{MOD_ID}_moat",
            concrete,
            [
                (MOAT_IN_R, spec.UNDER_DECK_Z),
                (MOAT_IN_R, MOAT_Z),
                (spec.WALL_INNER_R, MOAT_Z),
                (spec.WALL_INNER_R, spec.UNDER_DECK_Z),
            ],
            tile=(1.6, 1.6),
            orient="none",
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_pedestal",
            (0.0, 0.0, (spec.UNDER_DECK_Z + PIVOT_Z) / 2.0),
            0.90,
            PIVOT_Z - spec.UNDER_DECK_Z,
            steel,
            vertices=20,
            metric_uv=(1.2, 1.2),
        )
    )
    # The spherical bearing itself. A ball is invariant under rotation about
    # its own centre, which is the whole reason this machine has no trunnions
    # for the tilting deck to strike.
    objects.append(
        bk.add_sphere(
            f"{MOD_ID}_bearing_ball",
            (0.0, 0.0, PIVOT_Z),
            spec.BALL_RADIUS,
            chrome,
            segments=28,
            rings=18,
        )
    )

    # --- ram foot towers and anti-yaw posts -------------------------------
    for index in range(4):
        angle = index * math.pi / 2.0
        fx = spec.RAM_FOOT_R * math.cos(angle)
        fy = spec.RAM_FOOT_R * math.sin(angle)
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ram_tower_{index}",
                (fx, fy, (spec.UNDER_DECK_Z + spec.RAM_FOOT_Z) / 2.0),
                (1.35, 1.35, spec.RAM_FOOT_Z - spec.UNDER_DECK_Z),
                concrete,
                bevel=0.05,
                metric_uv=(1.2, 1.2),
            )
        )
    # Anti-yaw guides. A ball joint leaves the deck free to spin about Z; two
    # vertical guide posts, straddled by forks on the deck, take that out. Post
    # tops sit at 0.90 m - the soffit dips to 1.085 m at r = 3.4 m and full
    # tilt, so there is 0.185 m of clearance (asserted).
    for sign in (-1.0, 1.0):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_yaw_post_{'p' if sign > 0 else 'n'}",
                (sign * 3.4, 0.0, (spec.UNDER_DECK_Z + YAW_POST_TOP_Z) / 2.0),
                (0.46, 0.46, YAW_POST_TOP_Z - spec.UNDER_DECK_Z),
                steel,
                bevel=0.03,
                metric_uv=(1.0, 1.0),
            )
        )

    # --- boarding ramp -----------------------------------------------------
    # Cross section, per constant-radius station: lane (cols 2..6), a 45 deg
    # kerb up to cols 1/7, a 45 deg embankment flank down to grade at cols
    # 0/8, and a soffit closing the bottom. Each band is ONE surface with ONE
    # material - the first cut of this drew the lane over the full width and
    # then drew the kerbs and flanks on top of it, i.e. two coplanar copies of
    # the same geometry (the centrifuge's "W-canyon" duplicate-strip bug in
    # miniature: one surface, one authority).
    rows = ramp_rows()
    objects.append(
        strip(
            f"{MOD_ID}_ramp_deck",
            asphalt,
            [row[2:7] for row in rows],
            tile=(2.8, 2.8),
        )
    )
    # Kerb tops get the hazard chevron so the lane edge reads at speed.
    for side, columns in (("l", (1, 2)), ("r", (6, 7))):
        objects.append(
            strip(
                f"{MOD_ID}_ramp_kerb_{side}",
                hazard,
                [[row[columns[0]], row[columns[1]]] for row in rows],
                tile=(0.6, 0.6),
                orient="none",
            )
        )
    # Embankment flanks (kerb top let down to grade at 45 deg). These also plug
    # the guard-wall gate; build_cage asserts the plug covers it.
    for side, columns in (("l", (0, 1)), ("r", (7, 8))):
        objects.append(
            strip(
                f"{MOD_ID}_ramp_flank_{side}",
                concrete,
                [[row[columns[0]], row[columns[1]]] for row in rows],
                tile=(2.2, 2.2),
                orient="none",
            )
        )
    # Ramp soffit, carried to grade so the ramp is an embankment and not a
    # plank with a hole under it (AGENTS.md). Parked 30 mm under grade: it
    # shares its footprint with the apron for most of its length and two
    # coplanar surfaces z-fight.
    objects.append(
        strip(
            f"{MOD_ID}_ramp_soffit",
            concrete,
            [
                [
                    (row[0][0], row[0][1], row[0][2] - 0.03),
                    (row[8][0], row[8][1], row[8][2] - 0.03),
                ]
                for row in rows
            ],
            tile=(3.0, 3.0),
            orient="none",
        )
    )
    # Mouth curtain. The embankment is a tube and its inner end was an open
    # 12 m x 2.3 m hole a car could drive into and be stuck inside. It is
    # closed with a VERTICAL curtain - not a chamfer, because anything leaning
    # inboard would be inside the deck's swept volume, and anything leaning
    # outboard would be inside the ramp. It stands at station 1 (0.16 m
    # outboard of the deck edge) so the deck's lip cannot slice through it at
    # full down-tilt, and it is carried all the way down to the moat floor so
    # the embankment does not end in mid-air over the trench.
    objects.append(
        strip(
            f"{MOD_ID}_ramp_mouth",
            hazard,
            [rows[1], [(p[0], p[1], ground_z(MOUTH_R)) for p in rows[1]]],
            tile=(0.7, 0.7),
            orient="none",
        )
    )

    # --- ramp lane paint ---------------------------------------------------
    # The 7 m two-abreast ramp was a blank asphalt slab, and it is the whole
    # foreground of the approach shot. Painted furniture at the deck marks'
    # own 15 mm relief: a cream centre dash splitting the two lanes, solid
    # edge lines, and a cross-hatched KEEP CLEAR box celebrating the
    # travelling-seal threshold - the junction the listing sells. Every piece
    # is a top sheet with its long edges hemmed 10 mm INTO the lane (the b101
    # raised-patch idiom, so grazing views meet paint, not a floating card),
    # and every piece samples the SAME radius stations as the lane strip, so
    # over the crest curve the paint keeps a constant offset above the lane's
    # own chords instead of sinking through one mid-bay (chord sag there is
    # 15 mm - exactly the relief).
    paint_lift = 0.015
    paint_tuck = 0.010
    paint_stations = ramp_radii()
    paint_cos = math.cos(RAMP_AZ + math.pi / 2.0)
    paint_sin = math.sin(RAMP_AZ + math.pi / 2.0)

    def lane_chord_z(radius):
        for near, far in zip(paint_stations, paint_stations[1:]):
            if radius <= far + 1e-9:
                frac = max(0.0, min(1.0, (radius - near) / (far - near)))
                return ramp_z(near) + (ramp_z(far) - ramp_z(near)) * frac
        return ramp_z(radius)

    def paint_pt(radius, across, height):
        # Same arc-row construction as ramp_rows: the point sits ON the
        # constant-radius circle, so paint follows the lane's own curvature.
        depth = math.sqrt(max(0.0, radius * radius - across * across))
        return (
            across * paint_cos + depth * paint_sin,
            across * paint_sin - depth * paint_cos,
            height,
        )

    def paint_run(name, r_in, r_out, d_of, half_w):
        # A painted ribbon ALONG the ramp; d_of(radius) steers the centreline
        # so the same helper draws straight lines and hatch diagonals.
        radii = [r_in] + [s for s in paint_stations if r_in < s < r_out] + [r_out]
        run_rows = []
        for radius in radii:
            surface = lane_chord_z(radius)
            d = d_of(radius)
            run_rows.append(
                [
                    paint_pt(radius, d - half_w, surface - paint_tuck),
                    paint_pt(radius, d - half_w, surface + paint_lift),
                    paint_pt(radius, d + half_w, surface + paint_lift),
                    paint_pt(radius, d + half_w, surface - paint_tuck),
                ]
            )
        objects.append(strip(name, cream, run_rows, tile=(1.0, 1.0), orient="up"))

    def paint_bar(name, r_mid, half_r, d_min, d_max):
        # A painted bar ACROSS the lane, sampled every ~0.4 m of chord so the
        # bar follows the lane arc; hems face up/down the ramp - the grazing
        # direction a driver actually sees a transverse bar from.
        near, far = r_mid - half_r, r_mid + half_r
        z_near = lane_chord_z(near)
        z_far = lane_chord_z(far)
        count = max(8, int(abs(d_max - d_min) / 0.4))
        bar_rows = []
        for index in range(count + 1):
            d = d_min + (d_max - d_min) * index / count
            bar_rows.append(
                [
                    paint_pt(near, d, z_near - paint_tuck),
                    paint_pt(near, d, z_near + paint_lift),
                    paint_pt(far, d, z_far + paint_lift),
                    paint_pt(far, d, z_far - paint_tuck),
                ]
            )
        objects.append(strip(name, cream, bar_rows, tile=(1.0, 1.0), orient="up"))

    # Solid edge lines framing the two-abreast lane.
    for tag, edge_d in (("l", -3.16), ("r", 3.16)):
        paint_run(
            f"{MOD_ID}_ramp_edge_line_{tag}",
            13.55, 25.85, lambda radius, d=edge_d: d, 0.08,
        )
    # Centre dash splitting the lanes, clear of the KEEP CLEAR box.
    for index, start in enumerate((16.55, 19.25, 21.95, 24.65)):
        paint_run(
            f"{MOD_ID}_ramp_centre_dash_{index}",
            start, start + 1.20, lambda radius: 0.0, 0.09,
        )
    # KEEP CLEAR box at the deck junction: two transverse bars, two side
    # runs, and an X cross-hatch clipped to the box interior. It starts
    # 0.34 m outboard of the mouth curtain so the nosing shutline - the
    # travelling seal itself - stays clean.
    paint_bar(f"{MOD_ID}_ramp_keep_bar_in", 13.68, 0.08, -2.85, 2.85)
    paint_bar(f"{MOD_ID}_ramp_keep_bar_out", 16.02, 0.08, -2.85, 2.85)
    for tag, run_d in (("l", -2.77), ("r", 2.77)):
        paint_run(
            f"{MOD_ID}_ramp_keep_side_{tag}",
            13.76, 15.94, lambda radius, d=run_d: d, 0.08,
        )
    hatch_slope = 2.2
    hatch_index = 0
    for anchor in (12.2, 13.3, 14.4, 15.5):
        for sign in (1.0, -1.0):
            r_lo = max(13.80, anchor + 0.16 / hatch_slope)
            r_hi = min(15.90, anchor + (2.85 + 2.69) / hatch_slope)
            if r_hi - r_lo < 0.45:
                continue
            paint_run(
                f"{MOD_ID}_ramp_keep_hatch_{hatch_index}",
                r_lo,
                r_hi,
                lambda radius, a=anchor, s=sign: s * (-2.85 + hatch_slope * (radius - a)),
                0.075,
            )
            hatch_index += 1

    # --- embankment flank livery -------------------------------------------
    # The flanking wedges are the two largest fixed faces in the approach
    # shot, and plain raked concrete read as blank formwork framing the whole
    # view. They are painted like the arena instead: a vermilion base band
    # with a cream coping stripe, concrete above, echoing the guard kerb's
    # red band so the approach corridor wears one livery. Overlay sheets at
    # paint relief with tucked hems (the b101 raised-patch idiom), sampling
    # the SAME rows as the flank strips so the bands follow the wedge
    # exactly; the functional wedge geometry underneath is untouched.
    def flank_band(name, material, out_col, in_col, f_lo, f_hi, lift):
        tuck = 0.012
        band_rows = []
        for row in rows:
            p_out, p_in = row[out_col], row[in_col]
            run = math.hypot(p_out[0] - p_in[0], p_out[1] - p_in[1])
            if run < 1e-6:
                continue
            # 45 deg slope normal: half horizontal-outward, half up.
            nx = (p_out[0] - p_in[0]) / run * 0.7071
            ny = (p_out[1] - p_in[1]) / run * 0.7071
            nz = 0.7071

            def at(f, off):
                return (
                    p_out[0] + (p_in[0] - p_out[0]) * f + nx * off,
                    p_out[1] + (p_in[1] - p_out[1]) * f + ny * off,
                    p_out[2] + (p_in[2] - p_out[2]) * f + nz * off,
                )

            band_rows.append(
                [at(f_lo, -tuck), at(f_lo, lift), at(f_hi, lift), at(f_hi, -tuck)]
            )
        objects.append(strip(name, material, band_rows, tile=(1.4, 1.4), orient="up"))

    for side, out_col, in_col in (("l", 0, 1), ("r", 8, 7)):
        flank_band(
            f"{MOD_ID}_flank_band_{side}", torii_red, out_col, in_col, 0.0, 0.62, 0.016
        )
        flank_band(
            f"{MOD_ID}_flank_stripe_{side}", cream, out_col, in_col, 0.68, 0.80, 0.019
        )

    # --- hydraulic power unit ---------------------------------------------
    # The bearing, the gimbal and all four rams live under a 26 m lid and are
    # invisible from anywhere a player stands. So the machine's power train is
    # put where they DO stand: a skid on the apron with a reservoir, a pump
    # set, an accumulator bank and a pipe run that dives under the guard kerb
    # toward the pit. It is the only thing on this prop that explains, from
    # outside, what makes 212 tonnes of deck lean.
    hpu_az = math.radians(spec.HPU_AZIMUTH_DEG)
    hpu_r = spec.HPU_RADIUS
    hpu_cos, hpu_sin = math.cos(hpu_az), math.sin(hpu_az)
    hpu_base = apron_z(hpu_r)

    def hpu_at(radial, tangential, height):
        return (
            (hpu_r + radial) * hpu_cos - tangential * hpu_sin,
            (hpu_r + radial) * hpu_sin + tangential * hpu_cos,
            height,
        )

    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_plinth",
            hpu_at(0.0, 0.0, hpu_base + 0.18),
            (2.4, 4.2, 0.36),
            concrete,
            bevel=0.05,
            rotation=(0.0, 0.0, hpu_az),
            metric_uv=(1.5, 1.5),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_tank",
            hpu_at(0.30, 0.0, hpu_base + 0.36 + 0.62),
            (1.5, 3.2, 1.24),
            steel,
            bevel=0.05,
            rotation=(0.0, 0.0, hpu_az),
            metric_uv=(1.2, 1.2),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_tank_band",
            hpu_at(0.30, 0.0, hpu_base + 0.52),
            (1.53, 3.23, 0.22),
            hazard,
            bevel=0.0,
            rotation=(0.0, 0.0, hpu_az),
            metric_uv=(0.35, 0.35),
        )
    )
    # Pump set lying across the tank top.
    objects.append(
        _tube(
            f"{MOD_ID}_hpu_pump",
            hpu_at(0.30, -1.05, hpu_base + 1.85),
            hpu_at(0.30, 0.95, hpu_base + 1.85),
            0.30, steel, sides=16, tile=0.7,
        )
    )
    objects.append(
        _tube(
            f"{MOD_ID}_hpu_motor",
            hpu_at(0.30, 0.95, hpu_base + 1.85),
            hpu_at(0.30, 1.55, hpu_base + 1.85),
            0.22, chrome, sides=14, tile=0.5,
        )
    )
    # Accumulator bank: four nitrogen bottles standing on the skid's outer
    # edge, which is what actually holds 212 tonnes of deck up when the pumps
    # are off (the "gas-charged rams" of the spec's own stiffness budget).
    for index in range(4):
        objects.append(
            _tube(
                f"{MOD_ID}_hpu_bottle_{index}",
                hpu_at(-0.75, -1.35 + index * 0.90, hpu_base + 0.36),
                hpu_at(-0.75, -1.35 + index * 0.90, hpu_base + 1.96),
                0.21, chrome, sides=14, tile=0.6,
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_hpu_bottle_cap_{index}",
                hpu_at(-0.75, -1.35 + index * 0.90, hpu_base + 2.02),
                (0.22, 0.22, 0.16),
                steel,
                bevel=0.02,
            )
        )
    # Control cabinet with a legend plate, facing the ring.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_cabinet",
            hpu_at(-0.10, 2.30, hpu_base + 0.36 + 0.70),
            (0.70, 1.10, 1.40),
            steel,
            bevel=0.04,
            rotation=(0.0, 0.0, hpu_az),
            metric_uv=(0.8, 0.8),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_cabinet_panel",
            hpu_at(-0.46, 2.30, hpu_base + 0.36 + 0.80),
            (0.06, 0.92, 0.92),
            signage,
            bevel=0.01,
            rotation=(0.0, 0.0, hpu_az),
        )
    )
    # --- HPU livery --------------------------------------------------------
    # Primer-grey boxes told no story beside a vermilion arena. The tank and
    # the control cabinet wear torii-red lacquer panels (proud overlay sheets,
    # existing families only) and the outward tank face carries the cream
    # service legend, so the power skid reads as furniture of THIS venue and
    # says what it is. Panels start above the hazard wrap at the tank foot.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_tank_panel_out",
            hpu_at(1.08, 0.0, hpu_base + 1.08),
            (0.05, 2.90, 0.84),
            torii_red,
            bevel=0.0,
            rotation=(0.0, 0.0, hpu_az),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_tank_panel_in",
            hpu_at(-0.48, 0.0, hpu_base + 1.08),
            (0.05, 2.90, 0.84),
            torii_red,
            bevel=0.0,
            rotation=(0.0, 0.0, hpu_az),
        )
    )
    for tag, t_sign in (("s", -1.0), ("n", 1.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_hpu_tank_panel_{tag}",
                hpu_at(0.30, t_sign * 1.63, hpu_base + 1.08),
                (1.30, 0.05, 0.84),
                torii_red,
                bevel=0.0,
                rotation=(0.0, 0.0, hpu_az),
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_hpu_tank_strip_{tag}",
                hpu_at(0.30, t_sign * 1.67, hpu_base + 1.30),
                (1.00, 0.04, 0.20),
                cream,
                bevel=0.0,
                rotation=(0.0, 0.0, hpu_az),
            )
        )
    # Service legend on the outward face: a strip so the panel_legend texture
    # maps 0..1 exactly (primitive-cube UVs fragment the type). A reader
    # standing outboard looking in has their left hand at -tangential.
    objects.append(
        strip(
            f"{MOD_ID}_hpu_legend_sheet",
            hpu_legend,
            [
                [
                    hpu_at(1.113, -1.25, hpu_base + 0.79),
                    hpu_at(1.113, 1.25, hpu_base + 0.79),
                ],
                [
                    hpu_at(1.113, -1.25, hpu_base + 1.41),
                    hpu_at(1.113, 1.25, hpu_base + 1.41),
                ],
            ],
            tile=(2.50, 0.62),
            orient="none",
        )
    )
    # Cream strip on the inward red panel (the outward face carries the
    # legend; the other faces echo it plain).
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_tank_strip_in",
            hpu_at(-0.515, 0.0, hpu_base + 1.30),
            (0.03, 2.50, 0.20),
            cream,
            bevel=0.0,
            rotation=(0.0, 0.0, hpu_az),
        )
    )
    # Control cabinet: red door panel on the outward face and outer end, with
    # a cream strip at the door head.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_cab_panel_out",
            hpu_at(0.285, 2.30, hpu_base + 1.06),
            (0.05, 0.94, 1.16),
            torii_red,
            bevel=0.0,
            rotation=(0.0, 0.0, hpu_az),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_cab_panel_end",
            hpu_at(-0.10, 2.885, hpu_base + 1.06),
            (0.56, 0.05, 1.16),
            torii_red,
            bevel=0.0,
            rotation=(0.0, 0.0, hpu_az),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hpu_cab_strip_out",
            hpu_at(0.32, 2.30, hpu_base + 1.50),
            (0.03, 0.70, 0.18),
            cream,
            bevel=0.0,
            rotation=(0.0, 0.0, hpu_az),
        )
    )
    # Pressure and return lines, ducking under the guard kerb toe.
    for index, offset in enumerate((-0.55, 0.55)):
        objects.append(
            _tube(
                f"{MOD_ID}_hpu_line_{index}",
                hpu_at(-1.20, offset, hpu_base + 0.62),
                (
                    spec.WALL_TOE_R * hpu_cos - offset * hpu_sin,
                    spec.WALL_TOE_R * hpu_sin + offset * hpu_cos,
                    spec.WALL_TOE_Z - 0.06,
                ),
                0.10, steel, sides=10, tile=0.6,
            )
        )

    # --- spin drive (2026-08-13 player round) ------------------------------
    # "An electric motor fly wheel that rotates against the larger sumo arena
    # circle to create the motion for spinning." Everything that turns the
    # ring used to be under the lid with the gimbal, so the spin had no
    # visible cause at all - the deck simply started moving. Now a tyred
    # flywheel leans on the arena's own rim above the guard wall, an overhead
    # motor belts down to it, and the skid beside it feeds the motor. The
    # cause is on the outside of the machine where a player can watch it.
    #
    # It is a FRICTION drive, which is why it can exist at all: the wheel
    # only ever touches the deck's outer cylinder, and that surface is a
    # circle about the spin axis, so contact does not care what angle the
    # ring is at. The tread stands DRIVE_KISS_GAP clear (derived in spec,
    # asserted over the whole tilt sweep) - it kisses, it never bites.
    drive_iron = materials[f"{MOD_ID}_drive_iron"]
    drive_tyre = materials[f"{MOD_ID}_drive_tyre"]
    drive_cos, drive_sin = math.cos(DRIVE_AZ), math.sin(DRIVE_AZ)

    def drive_at(radial, tangential, height):
        """A point in the drive bay's frame -> authored world.

        ``radial`` is measured OUT from the flywheel axis, ``tangential``
        across it, so every dimension below reads as an offset from the one
        thing whose position is not free: the wheel that has to touch the
        deck.
        """

        return (
            (spec.DRIVE_AXIS_R + radial) * drive_cos - tangential * drive_sin,
            (spec.DRIVE_AXIS_R + radial) * drive_sin + tangential * drive_cos,
            height,
        )

    # Foundation. Inner edge stops outboard of the wall toe (a slab that ran
    # under the wall would be a step in the apron a car lands on).
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_pad",
            drive_at(1.15, 0.0, 0.03),
            (3.2, 2.8, 0.30),
            concrete,
            bevel=0.04,
            rotation=(0.0, 0.0, DRIVE_AZ),
            metric_uv=(1.5, 1.5),
        )
    )
    # Wheel column and its thrust collar, carrying the flywheel from BELOW so
    # nothing has to bridge over the ring to hold it up.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drive_column",
            drive_at(0.0, 0.0, spec.DRIVE_FACE_LO / 2.0),
            0.45,
            spec.DRIVE_FACE_LO,
            steel,
            vertices=20,
            metric_uv=(0.9, 0.9),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drive_collar",
            drive_at(0.0, 0.0, spec.DRIVE_FACE_LO - 0.11),
            0.62,
            0.20,
            steel,
            vertices=20,
            metric_uv=(0.7, 0.7),
        )
    )
    for tag, side in (("l", 1.0), ("r", -1.0)):
        objects.append(
            _tube(
                f"{MOD_ID}_drive_brace_{tag}",
                drive_at(1.95, side * 0.95, 0.17),
                drive_at(0.10, side * 0.32, spec.DRIVE_FACE_LO - 0.20),
                0.075, steel, sides=10, tile=0.6,
            )
        )
    # Motor pedestal, tall enough to put the motor over the wheel with the
    # belt in clear air between them.
    motor_r = 2.15
    stand_top = spec.DRIVE_HUB_Z + 0.19
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_stand",
            drive_at(motor_r, 0.0, stand_top / 2.0),
            (0.46, 0.46, stand_top),
            steel,
            bevel=0.03,
            rotation=(0.0, 0.0, DRIVE_AZ),
            metric_uv=(0.9, 0.9),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_stand_foot",
            drive_at(motor_r, 0.0, 0.22),
            (0.86, 0.86, 0.24),
            steel,
            bevel=0.03,
            rotation=(0.0, 0.0, DRIVE_AZ),
            metric_uv=(0.7, 0.7),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_stand_cap",
            drive_at(motor_r, 0.0, stand_top + 0.06),
            (0.92, 0.92, 0.12),
            steel,
            bevel=0.02,
            rotation=(0.0, 0.0, DRIVE_AZ),
            metric_uv=(0.7, 0.7),
        )
    )
    # The motor: a totally-enclosed fan-cooled frame, which is a shape people
    # know on sight - finned barrel, terminal box on the flank, cowl over the
    # fan - hung shaft-DOWN over its pulley the way a real belted drive sits.
    motor_lo = stand_top + 0.12
    motor_hi = motor_lo + 0.92
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drive_motor",
            drive_at(motor_r, 0.0, (motor_lo + motor_hi) / 2.0),
            0.34,
            motor_hi - motor_lo,
            steel,
            vertices=24,
            metric_uv=(0.8, 0.8),
        )
    )
    for index in range(7):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_drive_motor_fin_{index}",
                drive_at(motor_r, 0.0, motor_lo + 0.14 + index * 0.107),
                0.40,
                0.045,
                steel,
                vertices=24,
                metric_uv=(0.4, 0.4),
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_motor_terminal",
            drive_at(motor_r + 0.40, 0.0, motor_lo + 0.30),
            (0.30, 0.36, 0.32),
            steel,
            bevel=0.02,
            rotation=(0.0, 0.0, DRIVE_AZ),
            metric_uv=(0.6, 0.6),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drive_motor_cowl",
            drive_at(motor_r, 0.0, motor_hi + 0.09),
            0.30,
            0.18,
            steel,
            vertices=20,
            metric_uv=(0.5, 0.5),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_motor_plate",
            drive_at(motor_r - 0.355, 0.0, motor_lo + 0.52),
            (0.02, 0.30, 0.16),
            cream,
            bevel=0.0,
            rotation=(0.0, 0.0, DRIVE_AZ),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drive_motor_shaft",
            drive_at(motor_r, 0.0, (spec.DRIVE_HUB_Z + motor_lo) / 2.0),
            0.085,
            motor_lo - spec.DRIVE_HUB_Z,
            chrome,
            vertices=12,
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drive_motor_sheave",
            drive_at(motor_r, 0.0, spec.DRIVE_HUB_Z),
            0.24,
            0.16,
            steel,
            vertices=20,
            metric_uv=(0.4, 0.4),
        )
    )
    # Flat belt: two straight runs between the sheaves. A uniform belt looks
    # the same moving as it does still, which is the one piece of luck in
    # animating a drive with static geometry.
    for tag, side in (("l", 1.0), ("r", -1.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_drive_belt_{tag}",
                drive_at(motor_r / 2.0, side * 0.33, spec.DRIVE_HUB_Z),
                (motor_r, 0.025, 0.14),
                materials[f"{MOD_ID}_lacquer_black"],
                bevel=0.0,
                rotation=(0.0, 0.0, DRIVE_AZ),
            )
        )
    # Supply conduit from the skid's control cabinet to the terminal box: the
    # visible link that makes the skid the motor's power, not scenery.
    objects.append(
        _tube(
            f"{MOD_ID}_drive_conduit_run",
            hpu_at(-0.10, 2.885, hpu_base + 0.92),
            drive_at(motor_r + 0.40, 0.0, 0.30),
            0.075, steel, sides=10, tile=0.7,
        )
    )
    objects.append(
        _tube(
            f"{MOD_ID}_drive_conduit_rise",
            drive_at(motor_r + 0.40, 0.0, 0.30),
            drive_at(motor_r + 0.40, 0.0, motor_lo + 0.16),
            0.075, steel, sides=10, tile=0.7,
        )
    )

    # --- match scoreboard tower (2026-08-13 match round) -------------------
    # Replaces the round-4 leaning kanban at the same site: a double-faced
    # banzuke tower at SB_X/SB_Y, one display face to the ring (-Y) and one
    # to the world (+Y). No runtime text exists in this engine, so the board
    # is pose-driven HARDWARE showing through apertured faces: each face is
    # assembled from opaque strips that LEAVE the openings (house style - no
    # boolean cuts), and everything that moves lives in build_parts, hiding
    # by sliding behind these strips into the enclosed shells. A lacquer
    # baffle stands on the cabinet's centre plane so an empty window reads
    # dark instead of being a see-through hole with sky behind it.
    sign_east = materials[f"{MOD_ID}_sign_east"]
    sign_west = materials[f"{MOD_ID}_sign_west"]
    flag_live = materials[f"{MOD_ID}_flag_live"]
    name_lcd = materials[f"{MOD_ID}_name_lcd"]

    sb_y = spec.SB_Y
    cab_hw, cab_hd = spec.SB_CAB_W / 2.0, spec.SB_CAB_D / 2.0
    pip_lo = spec.SB_PIP_Z - spec.SB_PIP_CELL / 2.0
    pip_hi = spec.SB_PIP_Z + spec.SB_PIP_CELL / 2.0
    res_lo = spec.SB_RESULT_Z - spec.SB_RESULT_H / 2.0
    res_hi = spec.SB_RESULT_Z + spec.SB_RESULT_H / 2.0
    label_hw, label_hh = 0.80, 0.21
    rail_z0, rail_z1 = pip_lo - 0.135, res_hi + 0.14

    # Layout proofs: the bands the faces are assembled from must be disjoint,
    # hidden hardware must actually be hidden, and posed hardware must fit.
    assert spec.SB_PED_TOP < pip_lo < pip_hi < res_lo < res_hi < spec.SB_LABEL_Z - label_hh
    assert spec.SB_LABEL_Z + label_hh < spec.SB_TOP
    assert spec.SB_PIP_Z - spec.SB_PIP_HIDE + spec.SB_PIP_R < pip_lo - 0.05, "hidden pip peeks"
    assert spec.SB_RESULT_Z + spec.SB_RESULT_SHIFT + spec.SB_RESULT_H / 2.0 < spec.SB_TOP
    assert rail_z1 < spec.SB_LABEL_Z - label_hh
    assert spec.SB_COL_X - label_hw > 0.40, "labels reach the face-centre mon"
    assert cab_hw - (spec.SB_COL_X + 1.31) > 0.0, "identity rails leave the face"
    # Parked result plates sit at y = SB_Y -/+ SB_FACE_RECESS - PROUD of the
    # 1.05 m pedestal - so a collar skirt on the CABINET's slightly larger
    # footprint swallows them instead of deepening the contract pedestal.
    parked_lo = (spec.SB_RESULT_Z - spec.SB_RESULT_SHIFT - spec.SB_RESULT_HIDE
                 - spec.SB_RESULT_H / 2.0)
    skirt_z0 = parked_lo - 0.14
    assert 0.70 < skirt_z0 < spec.SB_PED_TOP
    assert spec.SB_FACE_RECESS < spec.SB_CAB_D / 2.0 + 0.02
    # Depth stack per face, outside in: face strips at cab_hd, pucks at
    # cab_hd - 0.05 (0.06 deep), cell sockets at cab_hd - 0.09, result
    # plates at SB_FACE_RECESS. The sockets must clear both neighbours.
    assert cab_hd - 0.09 > spec.SB_FACE_RECESS + 0.005, "sockets touch the result plates"
    assert (cab_hd - 0.05) - 0.03 > cab_hd - 0.09, "sockets touch the pucks"

    objects.append(
        bk.add_box(
            f"{MOD_ID}_sb_pedestal",
            (spec.SB_X, sb_y, spec.SB_PED_TOP / 2.0),
            (spec.SB_PED_W, spec.SB_PED_D, spec.SB_PED_TOP),
            lacquer,
            bevel=0.03,
            metric_uv=(1.4, 1.4),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_sb_skirt",
            (spec.SB_X, sb_y, (skirt_z0 + spec.SB_PED_TOP) / 2.0),
            (spec.SB_CAB_W + 0.06, spec.SB_CAB_D + 0.06, spec.SB_PED_TOP - skirt_z0),
            steel,
            bevel=0.03,
            metric_uv=(1.2, 1.2),
        )
    )
    # Pedestal livery: the guard wall's own storey - a vermilion base course
    # with a cream coping stripe (sleeves envelop the pedestal, so no decor
    # face is coplanar with it) - so the tower foot reads as arena plant.
    # The foot itself is buried in the apron dome (sand stands at z
    # 0.31..0.37 here), so nothing hovers.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_sb_kick",
            (spec.SB_X, sb_y, 0.30),
            (spec.SB_PED_W + 0.06, spec.SB_PED_D + 0.06, 0.56),
            torii_red,
            bevel=0.0,
            metric_uv=(1.2, 1.2),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_sb_kick_stripe",
            (spec.SB_X, sb_y, 0.64),
            (spec.SB_PED_W + 0.08, spec.SB_PED_D + 0.08, 0.10),
            cream,
            bevel=0.0,
        )
    )

    # Cabinet shell: steel side and top caps, lacquer centre baffle.
    for cap_tag, cap_sx in (("w", -1.0), ("e", 1.0)):
        objects.append(
            strip(
                f"{MOD_ID}_sb_side_{cap_tag}",
                steel,
                [
                    [(cap_sx * cab_hw, sb_y - cab_hd, spec.SB_PED_TOP),
                     (cap_sx * cab_hw, sb_y + cab_hd, spec.SB_PED_TOP)],
                    [(cap_sx * cab_hw, sb_y - cab_hd, spec.SB_TOP),
                     (cap_sx * cab_hw, sb_y + cab_hd, spec.SB_TOP)],
                ],
                tile=(1.2, 1.2),
                orient="none",
            )
        )
    objects.append(
        strip(
            f"{MOD_ID}_sb_top_cap",
            steel,
            [
                [(-cab_hw, sb_y - cab_hd, spec.SB_TOP), (cab_hw, sb_y - cab_hd, spec.SB_TOP)],
                [(-cab_hw, sb_y + cab_hd, spec.SB_TOP), (cab_hw, sb_y + cab_hd, spec.SB_TOP)],
            ],
            tile=(1.5, 1.5),
        )
    )
    objects.append(
        strip(
            f"{MOD_ID}_sb_baffle",
            lacquer,
            [
                [(-cab_hw, sb_y, spec.SB_PED_TOP), (cab_hw, sb_y, spec.SB_PED_TOP)],
                [(-cab_hw, sb_y, spec.SB_TOP), (cab_hw, sb_y, spec.SB_TOP)],
            ],
            tile=(2.0, 2.0),
            orient="none",
        )
    )

    # Display faces. Solid segments between the apertures, band by band:
    # 10 pip cells (SB_PIP_CELL squares on sb_pip_x centres) and 2 result
    # windows (SB_RESULT_W x SB_RESULT_H on the column centres) per face.
    sb_cells = sorted(sb_pip_x(side, i) for side in (-1.0, 1.0) for i in range(5))
    pip_edges = [-cab_hw]
    for cell_x in sb_cells:
        pip_edges.extend([cell_x - spec.SB_PIP_CELL / 2.0, cell_x + spec.SB_PIP_CELL / 2.0])
    pip_edges.append(cab_hw)
    res_edges = [-cab_hw]
    for col_sign in (-1.0, 1.0):
        res_edges.extend([col_sign * spec.SB_COL_X - spec.SB_RESULT_W / 2.0,
                          col_sign * spec.SB_COL_X + spec.SB_RESULT_W / 2.0])
    res_edges.append(cab_hw)
    assert pip_edges == sorted(pip_edges), "pip cells overlap or leave the face"
    assert res_edges == sorted(res_edges), "result windows overlap or leave the face"
    assert min(b - a for a, b in zip(pip_edges, pip_edges[1:])) > 0.04

    # Name windows: one per column in the low band, holding the dark display
    # panel the runtime writes each competitor's name onto.
    name_lo = spec.SB_NAME_Z - spec.SB_NAME_H / 2.0
    name_hi = spec.SB_NAME_Z + spec.SB_NAME_H / 2.0
    name_edges = [-cab_hw]
    for col_sign in (-1.0, 1.0):
        name_edges.extend([col_sign * spec.SB_COL_X - spec.SB_NAME_W / 2.0,
                           col_sign * spec.SB_COL_X + spec.SB_NAME_W / 2.0])
    name_edges.append(cab_hw)
    assert name_edges == sorted(name_edges), "name windows overlap or leave the face"
    assert spec.SB_PED_TOP + 0.10 < name_lo and name_hi + 0.08 < pip_lo, \
        "name window does not fit the low band"
    # A hidden pip must not park in a window that frames it - which is why
    # SB_PIP_HIDE went from 0.80 to 1.10 when these windows were cut.
    assert spec.SB_PIP_Z - spec.SB_PIP_HIDE + spec.SB_PIP_R < name_lo - 0.05, \
        "hidden pips park inside the name window"
    assert spec.SB_NAME_W / 2.0 < 1.26, "name window reaches the identity rails"

    def sb_face_sheet(name, x0, x1, z0, z1, face_y):
        objects.append(
            strip(
                name,
                lacquer,
                [[(x0, face_y, z0), (x1, face_y, z0)],
                 [(x0, face_y, z1), (x1, face_y, z1)]],
                tile=(1.5, 1.5),
                orient="none",
            )
        )

    for face_tag, outward in (("ring", -1.0), ("world", 1.0)):
        face_y = sb_y + outward * cab_hd
        # The low band carries the two NAME windows (2026-08-13 player round:
        # "incorporate the cars names into the score board appropriately").
        # Same aperture idiom as the pips and the result plates - opaque
        # strips that leave the opening - so the band is emitted in three
        # pieces: below the windows, the row containing them, and above.
        sb_face_sheet(f"{MOD_ID}_sb_face_{face_tag}_low", -cab_hw, cab_hw,
                      spec.SB_PED_TOP, name_lo, face_y)
        for seg, (x0, x1) in enumerate(zip(name_edges[0::2], name_edges[1::2])):
            sb_face_sheet(f"{MOD_ID}_sb_face_{face_tag}_name_{seg}", x0, x1,
                          name_lo, name_hi, face_y)
        sb_face_sheet(f"{MOD_ID}_sb_face_{face_tag}_lowtop", -cab_hw, cab_hw,
                      name_hi, pip_lo, face_y)
        sb_face_sheet(f"{MOD_ID}_sb_face_{face_tag}_mid", -cab_hw, cab_hw,
                      pip_hi, res_lo, face_y)
        sb_face_sheet(f"{MOD_ID}_sb_face_{face_tag}_high", -cab_hw, cab_hw,
                      res_hi, spec.SB_TOP, face_y)
        for seg, (x0, x1) in enumerate(zip(pip_edges[0::2], pip_edges[1::2])):
            sb_face_sheet(f"{MOD_ID}_sb_face_{face_tag}_pip_{seg}", x0, x1,
                          pip_lo, pip_hi, face_y)
        for seg, (x0, x1) in enumerate(zip(res_edges[0::2], res_edges[1::2])):
            sb_face_sheet(f"{MOD_ID}_sb_face_{face_tag}_res_{seg}", x0, x1,
                          res_lo, res_hi, face_y)

        # Pip row socket panels: one lacquer back sheet per COLUMN, 4 cm
        # behind the pucks and 1 cm proud of the result-plate plane.
        # Without it a cell frames whatever slides past at SB_FACE_RECESS -
        # and the parked LOSS plate's z-run crosses the pip band by
        # construction (RESULT_Z - SHIFT sits inside the cell band), so the
        # first cut showed LOSS letter fragments behind the pucks. Per-cell
        # 2 cm-margin sockets still leaked maroon slivers at raking angles
        # (9 cm of aperture-to-socket depth = 5 cm of parallax at 30 deg);
        # a continuous panel with 12 cm margins covers every rake a ground
        # viewer can reach. A shown pip reads puck-against-socket, a hidden
        # one reads a shallow dark socket.
        socket_y = sb_y + outward * (cab_hd - 0.09)
        for col_sign, col_tag in ((-1.0, "e"), (1.0, "w")):
            panel_x = col_sign * spec.SB_COL_X
            objects.append(
                strip(
                    f"{MOD_ID}_sb_socket_{face_tag}_{col_tag}",
                    lacquer,
                    [[(panel_x - 1.29, socket_y, pip_lo - 0.06),
                      (panel_x + 1.29, socket_y, pip_lo - 0.06)],
                     [(panel_x - 1.29, socket_y, pip_hi + 0.06),
                      (panel_x + 1.29, socket_y, pip_hi + 0.06)]],
                    tile=(1.0, 1.0),
                    orient="none",
                )
            )
        assert pip_hi + 0.06 < res_lo, "socket panel reaches the result window"

        # Name window backing and surround. The panel sits only 35 mm behind
        # the face - IN FRONT of everything that moves in this shaft - so the
        # window can never frame a parked plate or a retracted pip, and it
        # reads as a dark display rather than a hole into the cabinet. The
        # surround is a machined bezel standing 14 mm proud, which is what
        # makes an empty window still look like equipment.
        name_back_y = sb_y + outward * (cab_hd - 0.035)
        bezel_y = face_y + outward * 0.014
        # The LIVE panels. Each is the full window aperture exactly - the
        # page's own cell borders are its margins - and each samples its
        # corner's half of the shared webview, so the two faces of a corner
        # can never show different names.
        for col_sign, col_tag, u0, u1 in ((-1.0, "e", 0.0, 0.5),
                                          (1.0, "w", 0.5, 1.0)):
            col_x = col_sign * spec.SB_COL_X
            half_w = spec.SB_NAME_W / 2.0
            objects.append(
                display_sheet(
                    f"{MOD_ID}_sb_name_lcd_{face_tag}_{col_tag}",
                    name_lcd,
                    (col_x + outward * half_w, name_back_y, name_lo),
                    (col_x - outward * half_w, name_back_y, name_lo),
                    (col_x + outward * half_w, name_back_y, name_hi),
                    (col_x - outward * half_w, name_back_y, name_hi),
                    u0, u1,
                )
            )
            for edge_tag, edge_z in (("t", name_hi), ("b", name_lo)):
                objects.append(
                    bk.add_box(
                        f"{MOD_ID}_sb_name_rail_{face_tag}_{col_tag}{edge_tag}",
                        (col_x, bezel_y, edge_z),
                        (spec.SB_NAME_W + 0.14, 0.034, 0.075),
                        steel,
                        bevel=0.0,
                        metric_uv=(0.5, 0.5),
                    )
                )
            for edge_tag, edge_x in (("l", -1.0), ("r", 1.0)):
                objects.append(
                    bk.add_box(
                        f"{MOD_ID}_sb_name_post_{face_tag}_{col_tag}{edge_tag}",
                        (col_x + edge_x * (spec.SB_NAME_W / 2.0 + 0.035),
                         bezel_y, spec.SB_NAME_Z),
                        (0.075, 0.034, spec.SB_NAME_H + 0.15),
                        steel,
                        bevel=0.0,
                        metric_uv=(0.5, 0.5),
                    )
                )

        # Column identity rails: banzuke convention, EAST vermilion / WEST
        # cream - the same hues the label strips carry, standing 12 mm proud
        # of the face (they straddle the sheet, so nothing is coplanar).
        for col_sign, rail_mat, col_tag in ((-1.0, flag_live, "e"), (1.0, cream, "w")):
            for rail_tag, rail_x in (("l", col_sign * spec.SB_COL_X - 1.26),
                                     ("r", col_sign * spec.SB_COL_X + 1.26)):
                objects.append(
                    bk.add_box(
                        f"{MOD_ID}_sb_rail_{face_tag}_{col_tag}{rail_tag}",
                        (rail_x, face_y + outward * 0.012, (rail_z0 + rail_z1) / 2.0),
                        (0.10, 0.030, rail_z1 - rail_z0),
                        rail_mat,
                        bevel=0.0,
                    )
                )

        # EAST / WEST label strips over their columns, BOTH faces, at true
        # letter proportions (marquee_sheet). Reading-direction law: a ring-
        # side reader faces +Y so their left hand is -X; a world-side reader
        # faces -Y so their left hand is +X - bl flips with ``outward``.
        for col_sign, label_mat, label_tag in ((-1.0, sign_east, "east"),
                                               (1.0, sign_west, "west")):
            col_x = col_sign * spec.SB_COL_X
            label_y = face_y + outward * 0.012
            objects.append(
                marquee_sheet(
                    f"{MOD_ID}_sb_label_{face_tag}_{label_tag}",
                    label_mat,
                    (col_x + outward * label_hw, label_y, spec.SB_LABEL_Z - label_hh),
                    (col_x - outward * label_hw, label_y, spec.SB_LABEL_Z - label_hh),
                    (col_x + outward * label_hw, label_y, spec.SB_LABEL_Z + label_hh),
                    (col_x - outward * label_hw, label_y, spec.SB_LABEL_Z + label_hh),
                    2.0 * label_hw,
                    2.0 * label_hh,
                )
            )

        # Face-centre mon: a proud vermilion roundel between the labels,
        # where a real banzuke stamps the stable crest.
        objects.append(
            _tube(
                f"{MOD_ID}_sb_mon_{face_tag}",
                (0.0, face_y + outward * 0.010, spec.SB_LABEL_Z),
                (0.0, face_y + outward * 0.042, spec.SB_LABEL_Z),
                0.26,
                torii_red,
                sides=24,
                tile=0.8,
            )
        )

    # Steel corner posts enveloping the shell's vertical edges, and a
    # vermilion cap rail enveloping the roof edge (sleeves, never coplanar).
    for post_sx in (-1.0, 1.0):
        for post_sy in (-1.0, 1.0):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_sb_post_"
                    f"{'e' if post_sx > 0 else 'w'}{'n' if post_sy > 0 else 's'}",
                    (post_sx * cab_hw, sb_y + post_sy * cab_hd,
                     (spec.SB_PED_TOP + spec.SB_TOP) / 2.0),
                    (0.16, 0.16, spec.SB_TOP - spec.SB_PED_TOP + 0.04),
                    steel,
                    bevel=0.02,
                    metric_uv=(0.8, 0.8),
                )
            )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_sb_cap_rail",
            (spec.SB_X, sb_y, spec.SB_TOP + 0.04),
            (spec.SB_CAB_W + 0.14, spec.SB_CAB_D + 0.14, 0.14),
            torii_red,
            bevel=0.02,
        )
    )

    # Reset button dressing on BOTH pedestal faces: cream ring pad, dark
    # bezel, cream cap - the centrifuge cap recipe with the axis run signed
    # by each button's outward normal ("face": +1 outward, -1 toward the
    # ring). No painted legend: the panel tooltip carries the words. The
    # cage anchor sits 9 cm proud of each face (build_cage), so cap front
    # at +/-0.085 stays behind the anchor and the whole click box stays
    # OUTSIDE the pedestal collision plane (centrifuge law: click boxes
    # outside collision).
    for button in spec.PANEL_BUTTONS:
        bx, by, bz = button["position"]
        face = button.get("face", 1.0)
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_sb_pad_{button['id']}", (bx, by + 0.012 * face, bz),
                0.155, 0.024, cream, vertices=20, axis="Y",
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_bezel_{button['id']}", (bx, by + 0.030 * face, bz),
                0.10, 0.05, lacquer, vertices=18, axis="Y",
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_cap_{button['id']}", (bx, by + 0.055 * face, bz),
                0.065, 0.06, cream, vertices=16, axis="Y",
            )
        )

    # --- entrance gate (torii) --------------------------------------------
    # Sumo is a ritual: a real dohyo hangs a shrine roof over the ring and
    # every venue names itself over the way in. This machine's shrine
    # furniture is a vermilion torii over the boarding approach, carrying the
    # ring's name where a real gate carries its tablet - the one view every
    # player gets. Decorative only: the posts stand ~0.9 m clear of the
    # embankment flanks and the tie beam leaves 5.1 m of air over the running
    # surface, so nothing on the driving line can reach it.
    gate_y = -24.6
    for tag, sign in (("l", -1.0), ("r", 1.0)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_torii_post_{tag}",
                (sign * 5.35, gate_y, 3.55),
                0.44,
                7.70,
                torii_red,
                vertices=20,
                metric_uv=(1.4, 1.4),
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_torii_collar_{tag}",
                (sign * 5.35, gate_y, 0.50),
                0.50,
                1.0,
                lacquer,
                vertices=20,
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_torii_nuki",
            (0.0, gate_y, 5.62),
            (12.4, 0.42, 0.46),
            torii_red,
            bevel=0.03,
            metric_uv=(1.2, 1.2),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_torii_board_back",
            (0.0, gate_y, 6.47),
            (9.0, 0.30, 1.06),
            lacquer,
            bevel=0.02,
        )
    )
    # Name boards, one sheet per reading direction (a single double-sided
    # sheet would mirror the type on its far side). Column order flips so
    # both read left-to-right for their own viewer.
    for tag, y_off, x0, x1 in (
        ("front", -0.157, -4.3, 4.3),
        ("back", 0.157, 4.3, -4.3),
    ):
        objects.append(
            strip(
                f"{MOD_ID}_torii_board_{tag}",
                marquee,
                [
                    [(x0, gate_y + y_off, 6.02), (x1, gate_y + y_off, 6.02)],
                    [(x0, gate_y + y_off, 6.92), (x1, gate_y + y_off, 6.92)],
                ],
                tile=(8.6, 0.90),
                orient="none",
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_torii_shimaki",
            (0.0, gate_y, 7.19),
            (13.0, 0.55, 0.36),
            torii_red,
            bevel=0.03,
            metric_uv=(1.2, 1.2),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_torii_kasagi",
            (0.0, gate_y, 7.60),
            (14.6, 0.80, 0.44),
            lacquer,
            bevel=0.04,
        )
    )
    # Kasagi end lift (sori): the roof beam's tips sweep up, which is most of
    # what makes the silhouette read torii rather than goal post.
    for tag, sign in (("l", -1.0), ("r", 1.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_torii_sori_{tag}",
                (sign * 7.6, gate_y, 7.82),
                (1.7, 0.80, 0.44),
                lacquer,
                bevel=0.04,
                rotation=(0.0, sign * -0.16, 0.0),
            )
        )

    # --- nobori banners ----------------------------------------------------
    # Rows of tall banners are how a sumo venue announces itself from afar:
    # six ring the arena on the apron crest and two flank the gate. They also
    # give the flat side elevations their only vertical colour.
    #
    # The POLES are rigid and live here; the CLOTH is soft-body and is built
    # by build_banner_cloth into its own flexbody meshes (2026-08-13 player
    # round: "let's use cloth material like in our field goal mod repo for
    # our banners"). All the venue artwork - header band, edge piping, glyph
    # column - that used to be proud cream slabs is now painted INTO the
    # banner texture: proud geometry cannot ride a waving sheet, and this
    # pack's own law is that marking geometry betrays itself in-engine while
    # paint lives in the texture.
    for site in nobori_sites():
        top = site["base_z"] + site["pole_h"]
        dx, dy = math.cos(site["face"]), math.sin(site["face"])
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_nobori_pole_{site['tag']}",
                (site["x"], site["y"], site["base_z"] + site["pole_h"] / 2.0),
                NOBORI_POLE_R,
                site["pole_h"],
                steel,
                vertices=10,
            )
        )
        # Head rod, running from just behind the pole out past the fly edge -
        # the cloth hangs UNDER it, not off the pole's centreline.
        objects.append(
            _tube(
                f"{MOD_ID}_nobori_arm_{site['tag']}",
                (site["x"] - dx * 0.10, site["y"] - dy * 0.10, top - 0.06),
                (site["x"] + dx * (NOBORI_HOIST_OFF + site["width"] + 0.08),
                 site["y"] + dy * (NOBORI_HOIST_OFF + site["width"] + 0.08),
                 top - 0.06),
                0.04,
                steel,
                sides=8,
                tile=0.5,
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_nobori_finial_{site['tag']}",
                (site["x"], site["y"], top + 0.05),
                0.075,
                0.14,
                steel,
                vertices=10,
            )
        )

    # --- the PA horn pole ---------------------------------------------------
    objects.extend(build_horn_pole(materials))

    return objects


def build_banner_cloth(materials) -> dict:
    """One zero-thickness render mesh per banner, keyed by its flexbody mesh
    name. Each is skinned at runtime to its OWN cloth node group - binding
    two banners into one mesh would skin each to the other's nodes.

    Denser than the cage grid on purpose (the solver moves nodes, the
    flexbody interpolates the mesh between them), and zero thickness because
    real banner cloth has no silhouette - the palette entry carries
    double_sided plus invertBackFaceNormals so the back face lights right.
    """

    import bpy

    meshes = {}
    for site in nobori_sites():
        material = materials[
            f"{MOD_ID}_banner_indigo" if site["indigo"] else f"{MOD_ID}_banner_red"
        ]
        # The flexbody KEY and the source object must not share a name.
        # export_multi_flexbody renames its merged copy to the key, and if an
        # object already holds that name Blender hands it "<name>.001" - which
        # the DAE writes as a scene node BeamNG can never match to the jbeam
        # flexbody row. The banners shipped invisible exactly once this way
        # (player: "the banners seemed to have disappeared", 2026-08-14).
        key = f"{MOD_ID}_nobori_{site['tag']}_mesh"
        name = f"{MOD_ID}_nobori_{site['tag']}_cloth"
        sample = nobori_surface(site)
        segments, ribs = 22, 6
        stride = ribs + 1
        vertices = []
        for i in range(segments + 1):
            for j in range(stride):
                vertices.append(sample(i / segments, j / ribs))
        faces = []
        for i in range(segments):
            for j in range(ribs):
                a = i * stride + j
                faces.append((a, a + 1, a + stride + 1, a + stride))
        mesh = bpy.data.meshes.new(f"{name}_data")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        # u ACROSS the width, v ALONG the length: the nobori texture paints a
        # whole banner into 0..1 in exactly that frame - header band at v 0,
        # piping at the u edges, glyph column down the middle.
        layer = mesh.uv_layers.new(name="UVMap")
        for poly in mesh.polygons:
            for loop_index in poly.loop_indices:
                vertex = mesh.loops[loop_index].vertex_index
                layer.data[loop_index].uv = (
                    (vertex % stride) / ribs,
                    (vertex // stride) / segments,
                )
        bk.assign_material(obj, material)
        meshes[key] = [obj]
    return meshes


# ---------------------------------------------------------------------------
# Moving parts
# ---------------------------------------------------------------------------
def build_parts(materials) -> dict[str, dict[str, object]]:
    steel = materials[f"{MOD_ID}_steel"]
    hazard = materials[f"{MOD_ID}_deck_hazard"]
    plate = materials[f"{MOD_ID}_deck_plate"]
    chrome = materials[f"{MOD_ID}_rod_chrome"]
    tawara = materials[f"{MOD_ID}_tawara"]
    cream = materials[f"{MOD_ID}_paint_cream"]
    flags = [
        materials[f"{MOD_ID}_flag_open"],
        materials[f"{MOD_ID}_flag_arm"],
        materials[f"{MOD_ID}_flag_live"],
        materials[f"{MOD_ID}_flag_reset"],
    ]

    parts: dict[str, dict[str, object]] = {}

    # --- the deck ----------------------------------------------------------
    deck: list = []
    dish_radii = [0.0, 1.55, 3.15, 4.75, 6.35, 7.95, 9.55, 11.1, DISH_R]
    deck.append(
        lathe(
            f"{MOD_ID}_deck_dish",
            plate,
            [(radius, dish_z(radius)) for radius in dish_radii],
            tile=(2.4, 2.4),
        )
    )
    # The rolled kerb wears rice-straw, not construction amber: on a real
    # dohyo the ring boundary IS the tawara bale course, and amber here was
    # the loudest remaining "machine" note inside the clay (round-3 rim-trim
    # recipe: straw family at ~0.7 m tile on lip + lip face). The moving
    # amber that warns bystanders is the girder band below, which keeps its
    # chevron.
    lip_radii = [DISH_R, 12.62, LIP_CREST_R, 12.95, DECK_R]
    deck.append(
        lathe(
            f"{MOD_ID}_deck_lip",
            tawara,
            [(radius, lip_z(radius)) for radius in lip_radii],
            gate_half=LIP_GATE_HALF,
            tile=(0.7, 0.7),
        )
    )
    # Inside the boarding gate the lip is replaced by plain dish carried out to
    # the deck's own edge - the opening and the thing that fills it are cut
    # from the SAME LIP_GATE_HALF.
    deck.append(
        lathe(
            f"{MOD_ID}_deck_gate",
            plate,
            [(DISH_R, dish_z(DISH_R)), (12.8, dish_z(12.8)), (DECK_R, dish_z(DECK_R))],
            gate_half=LIP_GATE_HALF,
            inside_gate=True,
            tile=(2.4, 2.4),
        )
    )
    # Rim ring girder. This is the member that makes the boarding threshold
    # safe: 1.40 m of web hanging off the deck edge, so that at every up-tilt
    # its bottom flange still stands below the fixed ramp lip and a car at the
    # threshold meets a wall instead of a 1.97 m drop into the pit. See
    # spec.RIM_SKIRT_Z for the derivation and _assert_gate_seal for the proof
    # over the whole tilt range. It also stops the deck reading as a floating
    # disc from the apron, which a 0.50 m plate edge only just managed.
    deck.append(
        lathe(
            f"{MOD_ID}_deck_girder_web",
            steel,
            [(DECK_R, dish_z(DECK_R)), (DECK_R, 1.00)],
            tile=(1.2, 1.2),
            orient="none",
        )
    )
    # Rubbing band along the bottom of the web - the part of the machine that
    # sweeps past a bystander's eye line. ~1.2 m tile, the guard-kerb toe's
    # own reasoning: the old 0.35 put 8.75 cm stripes on an 82 m
    # circumference - sub-pixel gold bead from every wide shot (the b101
    # smear law cuts both ways). 2*pi*R/69 lands the closure on-pattern:
    # 69 whole wraps, ~30 cm stripes that resolve as stripes.
    girder_band_tile = 2.0 * math.pi * DECK_R / 69.0
    deck.append(
        lathe(
            f"{MOD_ID}_deck_girder_band",
            hazard,
            [(DECK_R, 1.00), (DECK_R, RIM_SKIRT_Z)],
            tile=(girder_band_tile, girder_band_tile),
            orient="none",
        )
    )
    # Haunch: the girder's bottom flange tapered back up to the general
    # soffit. One straight plate, one weld line.
    deck.append(
        lathe(
            f"{MOD_ID}_deck_girder_haunch",
            steel,
            [(DECK_R, RIM_SKIRT_Z), (HAUNCH_R, deck_under_z(HAUNCH_R))],
            tile=(1.4, 1.4),
            orient="none",
        )
    )
    deck.append(
        lathe(
            f"{MOD_ID}_deck_lip_face",
            tawara,
            [(DECK_R, lip_z(DECK_R)), (DECK_R, dish_z(DECK_R))],
            gate_half=LIP_GATE_HALF,
            tile=(0.7, 0.7),
            orient="none",
        )
    )
    # The soffit stops where the girder haunch takes over - sampling it out to
    # DECK_R as well would lay a second surface inside the girder.
    soffit_radii = [1.30, 3.4, 5.6, 7.8, 10.0, 11.4, HAUNCH_R]
    deck.append(
        lathe(
            f"{MOD_ID}_deck_soffit",
            steel,
            [(radius, deck_under_z(radius)) for radius in soffit_radii],
            tile=(2.6, 2.6),
            orient="none",
        )
    )
    # Hub boss and spherical socket. The socket is a concave cap of radius
    # BALL_RADIUS + 0.04 centred on the bearing, so the joint has 40 mm of oil
    # film and no running clearance problem at any tilt.
    socket_r = spec.BALL_RADIUS + 0.04
    deck.append(
        lathe(
            f"{MOD_ID}_deck_hub",
            steel,
            [
                (1.30, deck_under_z(1.30)),
                (1.30, PIVOT_Z),
                (socket_r, PIVOT_Z),
            ],
            tile=(1.2, 1.2),
            orient="none",
        )
    )
    socket_profile = []
    for step in range(9):
        angle = math.pi / 2.0 * step / 8.0
        socket_profile.append(
            (socket_r * math.cos(angle), PIVOT_Z + socket_r * math.sin(angle))
        )
    deck.append(
        lathe(
            f"{MOD_ID}_deck_socket",
            chrome,
            list(reversed(socket_profile)),
            tile=(0.8, 0.8),
            orient="none",
        )
    )
    # Lane markings. 15 mm of relief - the pack caps anything a car drives
    # over at +/-0.02 m, because a seam deeper than a sidewall and narrower
    # than a contact patch destroyed the centrifuge's tyres. Green marks the
    # refuge (inside it the dish's own slope dominates the tilt), red marks the
    # radius where one car alone can already lean the deck past 3 degrees.
    # 0.40 m bands (round 4): 0.30 m thinned to pinstripes in wide shots,
    # and half the old pastel read was sheer lack of line weight - a 26 m
    # dish carries fat paint, same centres 4.0 / 8.5.
    for tag, inner, outer, flag in (
        ("safe", 3.80, 4.20, materials[f"{MOD_ID}_flag_open"]),
        ("danger", 8.30, 8.70, materials[f"{MOD_ID}_flag_live"]),
    ):
        deck.append(
            lathe(
                f"{MOD_ID}_deck_mark_{tag}",
                flag,
                [
                    (inner, dish_z(inner)),
                    (inner, dish_z(inner) + 0.015),
                    (outer, dish_z(outer) + 0.015),
                    (outer, dish_z(outer)),
                ],
                tile=(1.0, 1.0),
                orient="none",
            )
        )
    # Shikiri-sen: the two start lines a real dohyo paints where the
    # wrestlers crouch - here where two cars stare each other down across
    # the centre. Human-scale on purpose (0.90 m bars, 0.60 m apart,
    # astride the gate axis so an entering car drives up between them): a
    # familiar-size relic at the middle of a 26 m dish is what sells the
    # giant. They live in the DECK part so they ride the tilt - a
    # build_visual mark would hover level while the deck leans - as thin
    # proud plates: 12 mm proud (inside the 20 mm drivable-relief cap),
    # bodies buried 48 mm so a grazing view meets paint, not card edge.
    for tag, y_off in (("s", -0.30), ("n", 0.30)):
        deck.append(
            bk.add_box(
                f"{MOD_ID}_deck_shikiri_{tag}",
                (0.0, y_off, dish_z(0.0) - 0.018),
                (0.90, 0.13, 0.06),
                cream,
                bevel=0.0,
                metric_uv=(0.5, 0.5),
            )
        )

    # Ram eyes on the soffit and the anti-yaw lugs that ride the fixed posts.
    for index in range(4):
        angle = index * math.pi / 2.0
        deck.append(
            bk.add_cylinder(
                f"{MOD_ID}_deck_ram_eye_{index}",
                (
                    spec.RAM_EYE_R * math.cos(angle),
                    spec.RAM_EYE_R * math.sin(angle),
                    spec.RAM_EYE_Z - 0.12,
                ),
                0.28,
                0.34,
                steel,
                vertices=14,
            )
        )
    # Fork plates straddling each anti-yaw post (y = +/-0.40, post half-width
    # 0.23, plate half-thickness 0.08: 0.09 m of running clearance each side).
    lug_top = deck_under_z(3.4)
    lug_height = 0.72
    for sign in (-1.0, 1.0):
        for side in (-1.0, 1.0):
            deck.append(
                bk.add_box(
                    f"{MOD_ID}_deck_yaw_fork_"
                    f"{'p' if sign > 0 else 'n'}{'p' if side > 0 else 'n'}",
                    (sign * 3.4, side * 0.40, lug_top - lug_height / 2.0),
                    (0.60, 0.16, lug_height),
                    steel,
                    bevel=0.02,
                    metric_uv=(0.8, 0.8),
                )
            )
    parts["deck"] = {
        "objects": deck,
        "pivot": (0.0, 0.0, PIVOT_Z),
        # The ONLY collision part. be:reloadCollision is global, so exactly one
        # owner may request it (AGENTS.md mouth-shelf law 2).
        "collision": True,
    }

    # --- centring rams -----------------------------------------------------
    # Authored in the TRUE REST ATTITUDE (foot -> eye), split the way a real
    # hydraulic cylinder is: a rigid steel barrel pinned at the foot and a
    # chrome rod that slides out of it. The runtime aims both with the same
    # rotation and translates only the rod along its own axis, so:
    #   * the identity pose of every ram part is already the correct pose -
    #     the previous cut authored them along +Z, which stood four cylinders
    #     1.04 m through the deck whenever behavior.init did not run;
    #   * nothing is scaled, so the barrel does not stretch (which is not what
    #     a ram does) and the pose carries no scale vector at all.
    rest = spec.RAM_REST_LENGTH
    barrel_len = rest * spec.RAM_BARREL_FRACTION
    rod_start = rest * (spec.RAM_BARREL_FRACTION - spec.RAM_ROD_OVERLAP)
    for index in range(4):
        frame = ram_frame(index)
        foot, axis, cross = frame["foot"], frame["axis"], frame["cross"]
        parts[f"ram_{index + 1}"] = {
            "objects": [
                _tube(
                    f"{MOD_ID}_ram_barrel_{index}",
                    _along(foot, axis, 0.0),
                    _along(foot, axis, barrel_len),
                    0.24, steel, sides=16, tile=0.9,
                ),
                # Clevis pin at the foot, across the ram - a pin boss, not a
                # world-axis box that would sit crooked on a raked strut.
                _tube(
                    f"{MOD_ID}_ram_foot_pin_{index}",
                    _along(foot, cross, -0.31),
                    _along(foot, cross, 0.31),
                    0.095, steel, sides=12, tile=0.5,
                ),
                _tube(
                    f"{MOD_ID}_ram_gland_{index}",
                    _along(foot, axis, barrel_len - 0.12),
                    _along(foot, axis, barrel_len + 0.05),
                    0.275, steel, sides=16, tile=0.5,
                ),
            ],
            "pivot": foot,
        }
        eye = _along(foot, axis, rest)
        parts[f"ram_rod_{index + 1}"] = {
            "objects": [
                _tube(
                    f"{MOD_ID}_ram_rod_{index}",
                    _along(foot, axis, rod_start),
                    eye,
                    0.135, chrome, sides=14, tile=0.6,
                ),
                _tube(
                    f"{MOD_ID}_ram_eye_pin_{index}",
                    _along(eye, cross, -0.27),
                    _along(eye, cross, 0.27),
                    0.085, steel, sides=12, tile=0.5,
                ),
            ],
            # Same pivot as the barrel: the aim rotation is about the foot for
            # both, and the rod's stroke is then a pure translation along the
            # aimed axis.
            "pivot": foot,
        }

    # --- spin drive flywheel -----------------------------------------------
    # The one moving part of the drive train. It turns about its own vertical
    # axis at DRIVE_RATIO times the deck's rate, the other way round, and the
    # runtime derives that from the deck's OWN angle change - so it is right
    # during spin-up, during the decay after a KO, and during the wind-back
    # home, with no second clock to drift.
    #
    # NOTHING on this part may exceed the tread radius anywhere the deck can
    # reach. A wide flange looks right on a drive wheel and would have been
    # eaten by the ring: at a couple of degrees of lean the deck's top-outer
    # corner swings out to r 13.134 and passes clean through the plane a
    # 1.30 m flange would occupy. The wheel is therefore a plain tyred drum
    # with everything decorative ABOVE the deck's reach, on the top web.
    drive_iron = materials[f"{MOD_ID}_drive_iron"]
    drive_tyre = materials[f"{MOD_ID}_drive_tyre"]
    web_z = spec.DRIVE_FACE_HI + 0.05
    wheel = [
        bk.add_cylinder(
            f"{MOD_ID}_drive_wheel_tyre",
            (DRIVE_CX, DRIVE_CY, DRIVE_MID_Z),
            spec.DRIVE_WHEEL_R,
            spec.DRIVE_FACE_HI - spec.DRIVE_FACE_LO,
            drive_tyre,
            vertices=32,
            metric_uv=(0.55, 0.55),
        ),
        # Bearing boss under the drum, sitting over the column's collar.
        bk.add_cylinder(
            f"{MOD_ID}_drive_wheel_boss",
            (DRIVE_CX, DRIVE_CY, spec.DRIVE_FACE_LO - 0.04),
            0.42,
            0.16,
            drive_iron,
            vertices=20,
            metric_uv=(0.5, 0.5),
        ),
        # Cast web across the top: this is the face a player standing on the
        # deck looks down at, so the spokes, the bolt circle and the painted
        # marks all live here - a smooth drum at 3 rev/s reads as standing
        # still, and this is what makes the rotation legible.
        bk.add_cylinder(
            f"{MOD_ID}_drive_wheel_web",
            (DRIVE_CX, DRIVE_CY, web_z),
            spec.DRIVE_WHEEL_R - 0.06,
            0.10,
            drive_iron,
            vertices=32,
            metric_uv=(0.6, 0.6),
        ),
        bk.add_cylinder(
            f"{MOD_ID}_drive_wheel_hub",
            (DRIVE_CX, DRIVE_CY, web_z + 0.20),
            0.34,
            0.42,
            drive_iron,
            vertices=20,
            metric_uv=(0.5, 0.5),
        ),
        bk.add_cylinder(
            f"{MOD_ID}_drive_wheel_sheave",
            (DRIVE_CX, DRIVE_CY, spec.DRIVE_HUB_Z),
            0.44,
            0.16,
            steel,
            vertices=24,
            metric_uv=(0.4, 0.4),
        ),
    ]
    for index in range(8):
        angle = DRIVE_AZ + index * math.pi / 4.0
        mid = 0.5 * (0.34 + spec.DRIVE_WHEEL_R - 0.06)
        wheel.append(
            bk.add_box(
                f"{MOD_ID}_drive_wheel_spoke_{index}",
                (
                    DRIVE_CX + mid * math.cos(angle),
                    DRIVE_CY + mid * math.sin(angle),
                    web_z + 0.11,
                ),
                (spec.DRIVE_WHEEL_R - 0.40, 0.15, 0.12),
                drive_iron,
                bevel=0.02,
                rotation=(0.0, 0.0, angle),
                metric_uv=(0.5, 0.5),
            )
        )
        wheel.append(
            bk.add_cylinder(
                f"{MOD_ID}_drive_wheel_bolt_{index}",
                (
                    DRIVE_CX + (spec.DRIVE_WHEEL_R - 0.20) * math.cos(angle),
                    DRIVE_CY + (spec.DRIVE_WHEEL_R - 0.20) * math.sin(angle),
                    web_z + 0.09,
                ),
                0.075,
                0.08,
                steel,
                vertices=6,
            )
        )
    # Two painted marks at 180 deg: enough to read the direction of rotation
    # without strobing into a standstill the way an even ring of marks does.
    for tag, turn in (("a", 0.0), ("b", math.pi)):
        angle = DRIVE_AZ + turn
        mid = 0.5 * (0.40 + spec.DRIVE_WHEEL_R - 0.06)
        wheel.append(
            bk.add_box(
                f"{MOD_ID}_drive_wheel_mark_{tag}",
                (
                    DRIVE_CX + mid * math.cos(angle),
                    DRIVE_CY + mid * math.sin(angle),
                    web_z + 0.185,
                ),
                (spec.DRIVE_WHEEL_R - 0.46, 0.11, 0.03),
                cream,
                bevel=0.0,
                rotation=(0.0, 0.0, angle),
            )
        )
    parts["drive_wheel"] = {
        "objects": wheel,
        "pivot": (DRIVE_CX, DRIVE_CY, DRIVE_MID_Z),
    }

    # --- match scoreboard hardware (2026-08-13 match round) ----------------
    # Everything the tower shows is a POSED PART sliding behind the apertured
    # faces built in build_visual; part names below are a hard contract with
    # the runtime. None carries collision (the tower's cage is fixed).
    pip_gold = materials[f"{MOD_ID}_pip_gold"]
    sign_win = materials[f"{MOD_ID}_sign_win"]
    sign_loss = materials[f"{MOD_ID}_sign_loss"]
    cab_hd = spec.SB_CAB_D / 2.0

    # Win pips: one part per pip, carrying a gold puck for BOTH faces, each
    # 5 cm behind its face's aperture plane. The runtime hides a pip by
    # dropping it SB_PIP_HIDE behind the face strips.
    for side_tag, side_sign in (("e", -1.0), ("w", 1.0)):
        for pip_index in range(5):
            pip_x = sb_pip_x(side_sign, pip_index)
            pucks = []
            for face_tag, outward in (("ring", -1.0), ("world", 1.0)):
                pucks.append(
                    bk.add_cylinder(
                        f"{MOD_ID}_pip_{side_tag}{pip_index + 1}_{face_tag}",
                        (pip_x, spec.SB_Y + outward * (cab_hd - 0.05), spec.SB_PIP_Z),
                        spec.SB_PIP_R,
                        0.06,
                        pip_gold,
                        vertices=18,
                        axis="Y",
                    )
                )
            parts[f"pip_{side_tag}_{pip_index + 1}"] = {
                "objects": pucks,
                "pivot": (pip_x, spec.SB_Y, spec.SB_PIP_Z),
            }

    # Result plates: WIN authored AT the window for both faces, LOSS one
    # SB_RESULT_SHIFT below. Runtime: offset 0 shows WIN, +shift shows LOSS,
    # -SB_RESULT_HIDE parks both in the pedestal shaft (inside the collar
    # skirt). Reading-direction law as for the labels: bl flips per face.
    res_hw, res_hh = spec.SB_RESULT_W / 2.0, spec.SB_RESULT_H / 2.0
    for side_tag, side_sign in (("e", -1.0), ("w", 1.0)):
        col_x = side_sign * spec.SB_COL_X
        plates = []
        for word, word_mat, word_z in (
            ("win", sign_win, spec.SB_RESULT_Z),
            ("loss", sign_loss, spec.SB_RESULT_Z - spec.SB_RESULT_SHIFT),
        ):
            for face_tag, outward in (("ring", -1.0), ("world", 1.0)):
                plate_y = spec.SB_Y + outward * spec.SB_FACE_RECESS
                plates.append(
                    marquee_sheet(
                        f"{MOD_ID}_result_{side_tag}_{word}_{face_tag}",
                        word_mat,
                        (col_x + outward * res_hw, plate_y, word_z - res_hh),
                        (col_x - outward * res_hw, plate_y, word_z - res_hh),
                        (col_x + outward * res_hw, plate_y, word_z + res_hh),
                        (col_x - outward * res_hw, plate_y, word_z + res_hh),
                        spec.SB_RESULT_W,
                        spec.SB_RESULT_H,
                    )
                )
        parts[f"result_{side_tag}"] = {
            "objects": plates,
            "pivot": (col_x, spec.SB_Y, spec.SB_RESULT_Z),
        }

    # Fluoro match lines over the deck's dull marks: the same lathe recipe as
    # deck_mark_*, 2 mm above the 15 mm paint so the swap SNAPS. Separate
    # parts (the runtime hides them by dropping them 0.30 into the deck
    # body), but with the DECK's own pivot verbatim - the runtime aims them
    # with the deck's tiltQuat and any other pivot would skew the pose.
    fluoro_live = materials[f"{MOD_ID}_fluoro_live"]
    fluoro_ko = materials[f"{MOD_ID}_fluoro_ko"]
    for ring_tag, ring_in, ring_out, ring_mat in (
        ("live", 3.78, 4.22, fluoro_live),
        ("ko", 8.28, 8.72, fluoro_ko),
    ):
        parts[f"ring_{ring_tag}"] = {
            "objects": [
                lathe(
                    f"{MOD_ID}_ring_{ring_tag}",
                    ring_mat,
                    [
                        (ring_in, dish_z(ring_in)),
                        (ring_in, dish_z(ring_in) + 0.017),
                        (ring_out, dish_z(ring_out) + 0.017),
                        (ring_out, dish_z(ring_out)),
                    ],
                    tile=(1.0, 1.0),
                    orient="none",
                )
            ],
            "pivot": (0.0, 0.0, PIVOT_Z),
        }
    return parts


# ---------------------------------------------------------------------------
# Collision cage (fixed structure only - the deck carries its own)
# ---------------------------------------------------------------------------
def _ring(cage, prefix, radius, height, *, collision, weight=110.0, gate_half=None):
    ids = []
    for j in range(SEGMENTS):
        angle = 2.0 * math.pi * j / SEGMENTS
        if gate_half is not None and azimuth_in_gate(angle, gate_half):
            ids.append(None)
            continue
        ids.append(
            cage.add_node(
                f"{prefix}_{j:02d}",
                (radius * math.cos(angle), radius * math.sin(angle), height),
                fixed=True,
                collision=collision,
                weight=weight,
            )
        )
    for j in range(SEGMENTS):
        first, second = ids[j], ids[(j + 1) % SEGMENTS]
        if first and second:
            cage.add_beam(first, second)
    return ids


def _bridge(cage, inner, outer, *, ground_model="metal", collide=True):
    for j in range(SEGMENTS):
        k = (j + 1) % SEGMENTS
        a, b, c, d = inner[j], inner[k], outer[k], outer[j]
        if a and d:
            cage.add_beam(a, d)
        if a and c:
            cage.add_beam(a, c)
        if collide and a and b and c and d:
            cage.add_quad_both([a, d, c, b], ground_model=ground_model)


def add_banner_cloth(cage, site, mount) -> None:
    """One banner's soft-body grid, the stock utv_flags recipe.

    Fixed along the head rod AND down the hoist edge - which is where a real
    nobori's chichi loops are - so it streams off the free corner instead of
    flying like a rectangle on a string. Everything else is loose.
    """

    sample = nobori_surface(site)
    nodes = {}
    for row in range(NOBORI_ROWS):
        s = row / (NOBORI_ROWS - 1)
        for col in range(NOBORI_COLS):
            w = col / (NOBORI_COLS - 1)
            held = row == 0 or col == 0
            nodes[(row, col)] = cage.add_node(
                f"nobori_{site['tag']}_{row}_{col}",
                tuple(sample(s, w)),
                fixed=held,
                collision=False,
                weight=NOBORI_ANCHOR_KG if held else NOBORI_NODE_KG,
                node_material="|NM_CLOTH",
                group=f"nobori_{site['tag']}",
            )
    # Rigid ties from every held node to the pole. Both ends are fixed, so
    # these carry no load - they exist because the cage has to be ONE
    # connected graph and cloth would otherwise be an island the validator
    # rejects.
    for (row, col), identifier in nodes.items():
        if row == 0 or col == 0:
            cage.add_beam(identifier, mount)
    for row in range(NOBORI_ROWS):
        for col in range(NOBORI_COLS):
            if row + 1 < NOBORI_ROWS:
                cage.add_beam(nodes[(row, col)], nodes[(row + 1, col)], "cloth_weave")
            if col + 1 < NOBORI_COLS:
                cage.add_beam(nodes[(row, col)], nodes[(row, col + 1)], "cloth_weave")
            if row + 1 < NOBORI_ROWS and col + 1 < NOBORI_COLS:
                cage.add_beam(
                    nodes[(row, col)], nodes[(row + 1, col + 1)], "cloth_shear"
                )
                cage.add_beam(
                    nodes[(row, col + 1)], nodes[(row + 1, col)], "cloth_shear"
                )
    # The aero surface. Cloth with no triangles is invisible to the air - the
    # beams do nothing aerodynamically, the solver derives drag and lift from
    # (wind - node velocity) on each TRIANGLE. SINGLE winding: it already
    # reads the flow on either face, so a double-sided helper would just
    # double the drag off stock's numbers.
    for row in range(NOBORI_ROWS - 1):
        for col in range(NOBORI_COLS - 1):
            cage.add_quad(
                [
                    nodes[(row, col)],
                    nodes[(row, col + 1)],
                    nodes[(row + 1, col + 1)],
                    nodes[(row + 1, col)],
                ],
                ground_model="rubber",
                extra={"dragCoef": NOBORI_DRAG_COEF},
            )


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    # Banner cloth beam specs (stock utv_flags numbers): the weave holds the
    # sheet together, the shear diagonals are essentially free - a 4000:1
    # ratio - so it folds and twists like textile rather than flexing like a
    # plate. That ratio IS the recipe.
    cage.define_beam_spec(
        "cloth_weave",
        beamSpring=1000.0,
        beamDamp=0.1,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "cloth_shear",
        beamSpring=0.25,
        beamDamp=0.05,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )

    # Rings, inner to outer. The base plate's outer ring IS the guard wall's
    # inner foot - aliased, never rebuilt: two rings 1 cm apart is the
    # coincident-node trap that made a whole deck band invisible in game.
    hub = cage.add_node(
        "base_hub", (0.0, 0.0, spec.UNDER_DECK_Z), fixed=True, collision=False, weight=160.0
    )
    base_mid = _ring(cage, "base_mid", 6.65, spec.UNDER_DECK_Z, collision=False)
    # The base plate's outer ring doubles as the guard wall's foot, so it is
    # NOT gated - the plate stays whole under the deck. The three rings that
    # make the wall proper ARE gated, on the same window the visual lathes use,
    # so the boarding ramp does not drive through an invisible kerb.
    # Drain moat, matching the visual profile exactly (same three radii, same
    # floor). Modelling it rather than letting the cage keep a flat floor at
    # 0.12 keeps collision from claiming a surface the eye cannot see - and it
    # is the one place on this prop where the two could have silently drifted.
    moat_lip = _ring(cage, "moat_lip", MOAT_IN_R, spec.UNDER_DECK_Z, collision=False, weight=70.0)
    moat_in = _ring(cage, "moat_in", MOAT_IN_R, MOAT_Z, collision=False, weight=70.0)
    moat_out = _ring(cage, "moat_out", spec.WALL_INNER_R, MOAT_Z, collision=False, weight=70.0)
    wall_foot = _ring(cage, "wall_foot", spec.WALL_INNER_R, spec.UNDER_DECK_Z, collision=False)
    # collision=False on the kerb-top rings. The bridging quads still carry the
    # surface (collision on a NODE does not arm or disarm a face, AGENTS.md),
    # so nothing is lost - but the kerb top is exactly where a car thrown off
    # the lip comes down, and 86 fixed collision spheres on a landing surface
    # is the b81 wheel-reach mistake that took the centrifuge fourteen
    # build-probe cycles to convict.
    wall_in = _ring(
        cage, "wall_in", spec.WALL_INNER_R, spec.WALL_TOP_Z,
        collision=False, gate_half=WALL_GATE_HALF,
    )
    wall_out = _ring(
        cage, "wall_out", spec.WALL_OUTER_R, spec.WALL_TOP_Z,
        collision=False, gate_half=WALL_GATE_HALF,
    )
    wall_toe = _ring(
        cage, "wall_toe", spec.WALL_OUTER_R, spec.WALL_TOE_Z,
        collision=False, gate_half=WALL_GATE_HALF,
    )
    apron_rings = []
    apron_radii = [spec.APRON_INNER_R, 16.9, 19.4, 21.9, spec.APRON_OUTER_R]
    for index, radius in enumerate(apron_radii):
        apron_rings.append(
            _ring(
                cage,
                f"apron_{index}",
                radius,
                apron_z(radius),
                collision=False,
            )
        )

    # --- nobori poles and their cloth --------------------------------------
    # Two fixed nodes per pole (foot and head rod) tied into the nearest apron
    # ring, then the soft-body sheet hung off the head. The poles carry no
    # collision: they are 55 mm masts on a landing apron, and fixed collision
    # spheres on a surface cars come down on is the b81 wheel-reach mistake.
    for site in nobori_sites():
        foot = cage.add_node(
            f"nobori_foot_{site['tag']}",
            (site["x"], site["y"], site["base_z"]),
            fixed=True, collision=False, weight=60.0,
        )
        head = cage.add_node(
            f"nobori_head_{site['tag']}",
            (site["x"], site["y"], site["base_z"] + site["pole_h"] - 0.06),
            fixed=True, collision=False, weight=40.0,
        )
        cage.add_beam(foot, head)
        nearest = min(
            (identifier for ring in apron_rings for identifier in ring if identifier),
            key=lambda identifier: _distance(cage, identifier, foot),
        )
        cage.add_beam(foot, nearest)
        add_banner_cloth(cage, site, head)

    for j in range(SEGMENTS):
        cage.add_beam(hub, base_mid[j])
    for j in range(SEGMENTS):
        k = (j + 1) % SEGMENTS
        # ONE triangle per fan face, wound (+r_j x +r_k) = +Z. Emitting the
        # mirrored twin as well would be the exact-coincident-twin trap that
        # popped tyres on flat ground (proplib add_quad_both docstring).
        cage.add_triangle(hub, base_mid[j], base_mid[k], ground_model="metal")
    _bridge(cage, base_mid, moat_lip)
    _bridge(cage, moat_lip, moat_in, ground_model="metal")
    _bridge(cage, moat_in, moat_out, ground_model="metal")
    _bridge(cage, moat_out, wall_foot, ground_model="metal")
    # Guard-wall inner face: unreachable while the deck is in place, but a
    # closed box under there beats an open edge if anything ever lands in it.
    _bridge(cage, wall_foot, wall_in, ground_model="metal")
    _bridge(cage, wall_in, wall_out, ground_model="metal")
    _bridge(cage, wall_out, wall_toe, ground_model="metal")
    _bridge(cage, wall_toe, apron_rings[0], ground_model="asphalt")
    for index in range(len(apron_rings) - 1):
        _bridge(cage, apron_rings[index], apron_rings[index + 1], ground_model="asphalt")

    # --- boarding ramp -----------------------------------------------------
    rows = ramp_rows()
    ramp: list[list[str]] = []
    for row_index, row in enumerate(rows):
        entries = []
        for column_index, point in enumerate(row):
            entries.append(
                cage.add_node(
                    f"ramp_{row_index:02d}_{column_index}",
                    point,
                    fixed=True,
                    collision=False,
                    weight=95.0,
                )
            )
        for column_index in range(len(entries) - 1):
            cage.add_beam(entries[column_index], entries[column_index + 1])
        ramp.append(entries)
    for row_index in range(len(ramp) - 1):
        for column_index in range(len(ramp[0])):
            cage.add_beam(ramp[row_index][column_index], ramp[row_index + 1][column_index])
        for column_index in range(len(ramp[0]) - 1):
            cage.add_beam(ramp[row_index][column_index], ramp[row_index + 1][column_index + 1])
            cage.add_quad_both(
                [
                    ramp[row_index][column_index],
                    ramp[row_index][column_index + 1],
                    ramp[row_index + 1][column_index + 1],
                    ramp[row_index + 1][column_index],
                ],
                ground_model="asphalt",
            )
    # Mouth curtain collision, matching the visual curtain exactly - same
    # station (1, at MOUTH_CURTAIN_R), same foot (the moat floor). Columns 0
    # and 8 of that row are ALREADY at grade, so they are ALIASED rather than
    # rebuilt - a second node a centimetre from an old one is the coincident
    # triad that makes flexbody bands vanish.
    mouth: list[str] = []
    moat_ids = [identifier for identifier in moat_out + wall_foot if identifier]
    for column_index, point in enumerate(rows[1]):
        if column_index in (0, len(rows[1]) - 1):
            mouth.append(ramp[1][column_index])
            continue
        foot = (point[0], point[1], ground_z(MOUTH_R))
        # The curtain lands in the moat, 4 cm inboard of its outer wall - so
        # the centre column would otherwise plant a brand new node 4 cm from
        # the moat ring's node at the same azimuth. AGENTS.md: end a strip by
        # REUSING the neighbouring wall's node; a new node 4 cm from an old
        # one is the flexbody coincident-triad trap that made a whole deck
        # band invisible in game for three days.
        alias = _nearest_within(cage, foot, moat_ids, 0.12)
        if alias:
            mouth.append(alias)
            continue
        mouth.append(
            cage.add_node(
                f"ramp_mouth_{column_index}",
                foot,
                fixed=True,
                collision=False,
                weight=95.0,
            )
        )
    for column_index in range(len(mouth) - 1):
        top_a, top_b = ramp[1][column_index], ramp[1][column_index + 1]
        bottom_a, bottom_b = mouth[column_index], mouth[column_index + 1]
        cage.add_beam(bottom_a, bottom_b)
        cage.add_beam(bottom_a, top_a)
        cage.add_beam(bottom_b, top_b)
        if bottom_a == top_a and bottom_b == top_b:
            continue
        if bottom_a == top_a or bottom_b == top_b:
            # Aliased corner: the quad collapses to a triangle. Emit ONE,
            # faced at the deck - never a triangle and its mirror, which is
            # the exact-coincident-twin that spikes the solver.
            third = bottom_b if bottom_a == top_a else bottom_a
            _inward_triangle(cage, top_a, top_b, third)
            continue
        cage.add_quad_both(
            [top_a, top_b, bottom_b, bottom_a],
            ground_model="metal",
        )

    # Tie the ramp into the ring structure so the cage is one graph.
    for column_index in (0, 4, 8):
        nearest = min(
            (identifier for identifier in apron_rings[1] if identifier),
            key=lambda identifier: _distance(cage, identifier, ramp[-1][column_index]),
        )
        cage.add_beam(ramp[-1][column_index], nearest)
        inner = min(
            (identifier for identifier in wall_out if identifier),
            key=lambda identifier: _distance(cage, identifier, ramp[0][column_index]),
        )
        cage.add_beam(ramp[0][column_index], inner)

    # --- match scoreboard tower --------------------------------------------
    # Two stacked box lattices on the tower's own footprints (the score_base
    # idiom): wall quads all round so cars hit the pedestal and the cabinet,
    # a top on the cabinet so nothing falls into it, NO top on the pedestal
    # (that plane is the cabinet's floor - a wheel can never reach it) and no
    # bottoms. Corner nodes only: the b81 wheel-reach rule keeps collision
    # spheres off surfaces cars land on, and eight corners per box is the
    # score_base precedent.
    ped = cage.add_box_lattice(
        "sbtower_ped",
        (spec.SB_X - spec.SB_PED_W / 2.0, spec.SB_Y - spec.SB_PED_D / 2.0, 0.0),
        (spec.SB_X + spec.SB_PED_W / 2.0, spec.SB_Y + spec.SB_PED_D / 2.0, spec.SB_PED_TOP),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("north", "south", "east", "west"),
    )
    cab = cage.add_box_lattice(
        "sbtower_cab",
        (spec.SB_X - spec.SB_CAB_W / 2.0, spec.SB_Y - spec.SB_CAB_D / 2.0, spec.SB_PED_TOP),
        (spec.SB_X + spec.SB_CAB_W / 2.0, spec.SB_Y + spec.SB_CAB_D / 2.0, spec.SB_TOP),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("north", "south", "east", "west", "top"),
    )
    for ix in (0, 1):
        for iy in (0, 1):
            cage.add_beam(ped[(ix, iy, 1)], cab[(ix, iy, 0)])
            nearest = min(
                (identifier for identifier in apron_rings[1] if identifier),
                key=lambda identifier: _distance(cage, identifier, ped[(ix, iy, 0)]),
            )
            cage.add_beam(ped[(ix, iy, 0)], nearest)

    # --- PA horn pole -------------------------------------------------------
    # A lamp standard on a LANDING APRON. Pachinko's pole is pure theatre and
    # is kept clear of every drive line by arithmetic; that answer is not
    # available here, because cars come off this deck in every direction and
    # the apron IS where they come down. A drawn-but-non-collidable thing a
    # car can stand inside is a defect this pack has already had to take back
    # once, so the pole gets a body - the scoreboard tower's own idiom, corner
    # nodes only with collision on the four wall faces and no top (nothing can
    # land on a 0.38 m cap 10 m up).
    horn_box = cage.add_box_lattice(
        "hornpole",
        (spec.HORN_POLE_X - 0.19, spec.HORN_POLE_Y - 0.19, spec.HORN_APRON_Z),
        (spec.HORN_POLE_X + 0.19, spec.HORN_POLE_Y + 0.19, spec.HORN_POLE_TOP_Z),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("north", "south", "east", "west"),
    )
    for ix in (0, 1):
        for iy in (0, 1):
            nearest = min(
                (identifier for ring in apron_rings for identifier in ring
                 if identifier),
                key=lambda identifier: _distance(cage, identifier, horn_box[(ix, iy, 0)]),
            )
            cage.add_beam(horn_box[(ix, iy, 0)], nearest)

    # Interactive panel anchors (reset buttons, one per pedestal face).
    # The centrifuge recipe wholesale, with the sign taken from each
    # button's "face" normal: anchors sit at position + 0.09*face in y.
    # Anchored proud of the cap the whole click box floats in free air
    # OUTSIDE the pedestal collision plane; anchored at the face the mouse
    # ray hits the cage first and hover never fires (centrifuge round 15).
    panel_nodes: dict[str, str] = {}
    for button in spec.PANEL_BUTTONS:
        anchor = (button["position"][0],
                  button["position"][1] + 0.09 * button.get("face", 1.0),
                  button["position"][2])
        panel_nodes[button["id"]] = cage.add_node(
            f"panelbtn_{button['id']}",
            anchor,
            fixed=True,
            collision=False,
            weight=20.0,
        )
        # Per-button orthonormal frame: the trigger basis is (idX-idRef,
        # idY-idRef), so a shared frame pair gives every off-row button a
        # skewed, translated hitbox (centrifuge round 15, documented
        # history).
        for frame_tag, frame_off in (("fx", (0.4, 0.0, 0.0)), ("fy", (0.0, 0.0, 0.4))):
            frame_id = cage.add_node(
                f"panel{frame_tag}_{button['id']}",
                (anchor[0] + frame_off[0], anchor[1] + frame_off[1],
                 anchor[2] + frame_off[2]),
                fixed=True,
                collision=False,
                weight=20.0,
            )
            cage.add_beam(frame_id, ped[(1, 1, 0)])
    frame_x_node = cage.add_node(
        "panel_frame_x", spec.PANEL_FRAME_X, fixed=True, collision=False, weight=20.0
    )
    frame_y_node = cage.add_node(
        "panel_frame_y", spec.PANEL_FRAME_Y, fixed=True, collision=False, weight=20.0
    )
    for identifier in [*panel_nodes.values(), frame_x_node, frame_y_node]:
        cage.add_beam(identifier, ped[(1, 1, 0)])

    # --- spawn datum -------------------------------------------------------
    datum_ref = cage.add_node("datum_ref", (0.0, 0.0, 0.0), fixed=True, weight=400.0)
    datum_back = cage.add_node("datum_back", (0.0, -3.2, 0.0), fixed=True, weight=400.0)
    datum_left = cage.add_node("datum_left", (-3.2, 0.0, 0.0), fixed=True, weight=400.0)
    datum_up = cage.add_node("datum_up", (0.0, 0.0, 1.6), fixed=True, weight=200.0)
    for identifier in (datum_ref, datum_back, datum_left, datum_up):
        cage.add_beam(identifier, hub)
    cage.add_beam(datum_ref, datum_back)
    cage.add_beam(datum_ref, datum_left)
    cage.add_beam(datum_ref, datum_up)
    for j in (0, 12, 24, 36):
        cage.add_beam(datum_ref, base_mid[j])

    cage.set_refnodes_existing(ref=datum_ref, back=datum_back, left=datum_left, up=datum_up)
    # set_spawn_envelope FORCES collision=True on its eight nodes, so they must
    # never sit on a surface a wheel can reach (AGENTS.md b81 wheel-reach rule:
    # ~370 surface spheres were one of the centrifuge's stuck-vehicle causes).
    # Four are under the deck behind the guard wall and four are the match
    # tower's cabinet top, which already carries collision - nothing drives on
    # either, and between them they still span the structure in x, y and z.
    # (They used to be the old status pylon's plinth, which left with it.)
    cage.set_spawn_envelope(
        [wall_foot[j] for j in (0, 12, 24, 36)]
        + [cab[(i, j, 1)] for i in (0, 1) for j in (0, 1)]
    )
    cage.auto_base_nodes()

    _assert_geometry(cage)
    return cage


def _inward_triangle(cage, first, second, third) -> None:
    """One collision triangle wound so its normal points back at the platform
    axis. Used where a wall quad degenerates onto an aliased corner."""

    points = [
        cage.nodes[cage.node_index[identifier]]["source_world_position"]
        for identifier in (first, second, third)
    ]
    ux = [points[1][axis] - points[0][axis] for axis in range(3)]
    vx = [points[2][axis] - points[0][axis] for axis in range(3)]
    normal = (
        ux[1] * vx[2] - ux[2] * vx[1],
        ux[2] * vx[0] - ux[0] * vx[2],
        ux[0] * vx[1] - ux[1] * vx[0],
    )
    centroid = [sum(point[axis] for point in points) / 3.0 for axis in range(3)]
    outward = normal[0] * centroid[0] + normal[1] * centroid[1]
    if outward > 0.0:
        first, second = second, first
    cage.add_triangle(first, second, third, ground_model="metal")


def _nearest_within(cage, point, candidates, limit):
    """Existing cage node within ``limit`` of ``point``, or None. Used to ALIAS
    rather than duplicate wherever two structures meet."""

    best = None
    best_distance = limit
    for identifier in candidates:
        if not identifier:
            continue
        other = cage.nodes[cage.node_index[identifier]]["source_world_position"]
        distance = math.dist(point, other)
        if distance < best_distance:
            best, best_distance = identifier, distance
    return best


def _distance(cage, first, second) -> float:
    a = cage.nodes[cage.node_index[first]]["source_world_position"]
    b = cage.nodes[cage.node_index[second]]["source_world_position"]
    return math.dist(a, b)


def _assert_geometry(cage) -> None:
    """Every clearance this machine depends on, checked at build time."""

    # 1. No two cage nodes within 8 cm. Exactly coincident nodes give the
    #    flexbody a degenerate skinning triad and its triangles stop drawing,
    #    but AGENTS.md puts the working limit at "a new node 4 cm from an old
    #    one" - the triad is nearly degenerate long before it is exactly so.
    #    The threshold is deliberately well above any pair this cage builds
    #    (closest is 0.12 m, the spawn datum over the base hub) so a later
    #    radius tweak that quietly parks two structures on top of each other
    #    fails the build instead of shipping. It caught exactly that when the
    #    mouth curtain moved outboard: its centre foot landed 4 cm from the
    #    moat ring, and the fix was to ALIAS rather than loosen the bound.
    positions = [tuple(node["source_world_position"]) for node in cage.nodes]
    buckets: dict[tuple[int, int, int], list[tuple[float, float, float]]] = {}
    closest = 1e9
    for point in positions:
        key = (int(point[0] // 0.5), int(point[1] // 0.5), int(point[2] // 0.5))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other in buckets.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        closest = min(closest, math.dist(point, other))
                        if math.dist(point, other) < 0.08:
                            raise AssertionError(f"cage nodes too close at {point}")
        buckets.setdefault(key, []).append(point)

    # 2. The deck's underside clears the fixed floor, the ram towers and the
    #    anti-yaw posts at FULL tilt, at every radius. The floor is the base
    #    plate inboard of the moat and the moat floor across it, so the test
    #    asks which floor is actually under the swept point.
    for step in range(261):
        radius = DECK_R * step / 260.0
        reach, height = tilted(radius, deck_bottom_z(radius), TILT_MAX)
        floor = MOAT_Z if reach >= MOAT_IN_R + 0.02 else spec.UNDER_DECK_Z
        assert height >= floor + 0.15, ("deck fouls floor", radius, reach, height)
        if abs(radius - spec.RAM_FOOT_R) < 0.35:
            assert height >= spec.RAM_FOOT_Z + 0.15, ("ram tower", radius, height)
        if abs(radius - 3.4) < 0.35:
            assert height >= YAW_POST_TOP_Z + 0.12, ("yaw post", radius, height)

    # 3. The deck never reaches the guard wall, and never reaches the fixed
    #    mouth curtain. Sweep EVERY authored profile corner over the whole
    #    tilt range rather than the four the previous cut checked - the corner
    #    that turned out to be widest (the lip's outer top, r 13.171 at z
    #    1.056) was in that set, but the girder's corners were not, and a
    #    later profile change could easily add a new worst case.
    worst = 0.0
    for radius, height in (
        (DECK_R, lip_z(DECK_R)),
        (DECK_R, dish_z(DECK_R)),
        (DECK_R, 1.00),
        (DECK_R, RIM_SKIRT_Z),
        (HAUNCH_R, deck_under_z(HAUNCH_R)),
        (LIP_CREST_R, lip_z(LIP_CREST_R)),
        (DISH_R, lip_z(DISH_R)),
    ):
        for step in range(41):
            angle = -TILT_MAX + 2.0 * TILT_MAX * step / 40.0
            reach, _z = tilted(radius, height, angle)
            worst = max(worst, reach)
    assert spec.WALL_INNER_R - worst >= 0.10, ("deck fouls wall", worst)
    assert MOUTH_R - worst >= 0.05, ("deck slices the mouth curtain", worst)

    # 4. The guard-wall gate is bracketed from both sides. Face quantisation
    #    widens the hole by at most one face beyond the nominal window and
    #    narrows the GUARANTEED hole to the nominal window, so:
    #      - the ramp embankment must plug the widest possible hole, and
    #      - the narrowest guaranteed hole must still clear the ramp kerb.
    slop = 2.0 * math.pi / SEGMENTS
    for radius in (spec.WALL_INNER_R, spec.WALL_OUTER_R, spec.WALL_TOE_R):
        opening = radius * math.sin(min(WALL_GATE_HALF + slop, math.pi / 2.0))
        assert ramp_flank_x(radius) >= opening, ("wall gate unplugged", radius, opening)
        cleared = radius * math.sin(WALL_GATE_HALF)
        assert cleared >= RAMP_HW + 0.32, ("wall gate clips the ramp kerb", radius, cleared)

    # 5. The lip gate is wide enough for the lane and the ramp actually reaches
    #    the deck's edge at the same height the deck presents there.
    assert DISH_R * math.sin(LIP_GATE_HALF) >= RAMP_HW + 0.25
    assert abs(ramp_z(DECK_R) - (dish_z(DECK_R) - RAMP_TUCK)) < 1e-9
    assert abs(ramp_z(RAMP_OUT_R)) < 1e-6, ramp_z(RAMP_OUT_R)

    # 6. The ramp's grade is monotone between its end grades and never exceeds
    #    either - the round-14 stall rule - and stays under the 23% that stalls
    #    an automatic at creep throttle.
    previous = RAMP_G0
    for step in range(201):
        radius = DECK_R + RAMP_LEN * step / 200.0
        grade = ramp_grade(radius)
        assert grade <= previous + 1e-9, ("grade not monotone", radius)
        assert RAMP_G1 - 1e-9 <= grade <= RAMP_G0 + 1e-9, ("grade out of band", radius)
        previous = grade
    assert abs(RAMP_G1) < 0.23, ("ramp too steep", RAMP_G1)

    # 7. The committed-pose bound the whole collision story rests on. The
    #    runtime clamps each committed move to ONE bake step and carries the
    #    remainder, so the delivered step at the rim is bake_step * R exactly,
    #    at any frame rate. (The previous cut snapped com = psi and asserted
    #    only bake_step * R, which never saw the per-frame overshoot: the real
    #    delivered step was (bake_step + rate_max*dt)*R = 26.67 mm at 60 fps
    #    and 34.28 mm at the dt clamp, both measured in the harness against a
    #    claimed 22.86 mm and a +/-0.02 m budget.)
    assert abs(spec.TILT_RATE_MAX_RAD_S - spec.TILT_BAKE_STEP_RAD / spec.TILT_BAKE_INTERVAL) < 1e-12
    assert spec.TILT_BAKE_STEP_RAD * DECK_R <= 0.020, "committed step over the relief budget"
    # What an UNCLAMPED loop would have delivered, kept as a live tripwire: if
    # anyone reverts commitPose to com = psi this number is the one that
    # matters, and it is over budget.
    unclamped = (spec.TILT_BAKE_STEP_RAD
                 + spec.TILT_RATE_MAX_RAD_S * spec.BEHAVIOR["dt_max"]) * DECK_R
    assert unclamped > 0.020, "clamp no longer load-bearing - re-derive the bound"
    assert 1.0 / spec.TILT_BAKE_INTERVAL <= 8.0, "collision rebuild ceiling above 8 Hz"
    assert spec.TILT_MAX_RAD / spec.TILT_RATE_MAX_RAD_S < 10.0, "bleed backstop too slow"
    assert spec.BEHAVIOR["relevel_hard_seconds"] + spec.BEHAVIOR["relevel_bleed_ramp"] \
        + spec.TILT_MAX_RAD / spec.TILT_RATE_MAX_RAD_S < 20.0, "re-level unbounded"

    # 8. The boarding threshold is a WALL at every up-tilt, and a bounded drop
    #    onto the deck at every down-tilt. This is the assert that stands in
    #    for the blocker: with a 0.50 m deck edge the ramp lip opened onto a
    #    1.97 m fall into the pit as soon as the ring leaned away, and no
    #    FIXED geometry can close that annulus (it is swept by the deck at
    #    small tilts). The 1.40 m rim girder closes it instead, and this walks
    #    the whole tilt range rather than trusting the endpoints.
    _assert_gate_seal()

    # 9. The drive wheel KISSES the ring; it never bites it. The deck's outer
    #    corners swing OUTWARD as the ring leans toward the drive, so the
    #    clearance has to be checked over the whole tilt sweep and only where
    #    the tread actually is - the deck passes through the tread's height
    #    band at small leans and is well below it at large ones. Walk it.
    reach = 0.0
    for step in range(-600, 601):
        tilt = spec.TILT_MAX_RAD * step / 600.0
        for corner_z in (spec.DECK_TOP_Z, spec.DECK_TOP_Z - spec.DECK_THICKNESS):
            local = corner_z - spec.PIVOT_Z
            swept_r = DECK_R * math.cos(tilt) + local * math.sin(tilt)
            swept_z = spec.PIVOT_Z + local * math.cos(tilt) - DECK_R * math.sin(tilt)
            if spec.DRIVE_FACE_LO <= swept_z <= spec.DRIVE_FACE_HI:
                reach = max(reach, swept_r)
    tread_inner = spec.DRIVE_AXIS_R - spec.DRIVE_WHEEL_R
    assert reach > DECK_R, "tilt sweep never reaches past the deck edge - check the sign"
    assert tread_inner > reach + 0.005, (
        f"drive tread at {tread_inner:.4f} m is inside the deck's swept reach "
        f"{reach:.4f} m - widen DRIVE_KISS_GAP"
    )
    # ... and the whole wheel has to clear the ring at every height, not just
    # at the tread: a wide flange or a proud mark is the classic way to put
    # hardware back into the deck's path.
    assert spec.DRIVE_HUB_Z > spec.DRIVE_FACE_HI, "sheave inside the tread band"

    # 10. The PA pole shares the apron with eight nobori masts. spec asserts
    #     the pole against the deck and the scoreboard (both of which it knows
    #     about); the banners live HERE, so their clearance is checked here.
    #     The bells hang at 9.0 m and the tallest banner head rod reaches
    #     about 5.6, so this is a plan check on the masts and their cloth.
    for site in nobori_sites():
        gap = math.hypot(spec.HORN_POLE_X - site["x"], spec.HORN_POLE_Y - site["y"])
        assert gap >= spec.HORN_ENVELOPE_R + site["width"] + 0.60, (
            f"horn pole crowds nobori {site['tag']}: {gap:.2f} m")
    #     ... and the mouths must actually be on the pole, not floating: every
    #     one sits exactly HORN_MOUTH_R out from the axis at the cluster
    #     height, which is what the runtime hangs its emitters on.
    for mouth, (dx, dy) in zip(spec.HORN_MOUTHS, spec.HORN_DIRS):
        assert abs(math.hypot(mouth[0] - spec.HORN_POLE_X,
                              mouth[1] - spec.HORN_POLE_Y)
                   - spec.HORN_MOUTH_R) < 1e-3, ("horn mouth off axis", mouth)
        assert abs(mouth[2] - spec.HORN_AXIS_Z) < 1e-3, ("horn mouth off height", mouth)
        assert abs(math.hypot(dx, dy) - 1.0) < 1e-6, ("horn aim not a unit vector", dx, dy)


def _assert_meshes_exported(dae_path, mesh_groups) -> None:
    """Every flexbody group must exist in the Collada under its EXACT key.

    A flexbody binds its mesh by name, and a name that does not resolve fails
    silently: BeamNG draws nothing and logs nothing. The one way this goes
    wrong is a name COLLISION - Blender appends .001 to a duplicate object
    name, the exporter writes that suffix into the scene node, and the jbeam
    row then points at a mesh that does not exist. Read the file back and
    prove it, because no later stage can.
    """

    import re

    text = dae_path.read_text(encoding="utf-8", errors="replace")
    exported = set(re.findall(r'<node id="([^"]+)" name="[^"]+" type="NODE"', text))
    missing = sorted(name for name in mesh_groups if name not in exported)
    assert not missing, (
        f"flexbody meshes absent from {dae_path.name}: {missing}; "
        f"exported instead: {sorted(exported)}"
    )


def _assert_gate_seal() -> None:
    """Walk the whole tilt range and prove the boarding threshold is never a
    hole. Reported numbers are printed by main() so the claim in spec.py can
    be checked without re-deriving it."""

    lip_z_ramp = RAMP_Z0  # ramp running surface at the deck edge
    worst_gap = 0.0
    worst_below = 1e9
    steps = 120
    for step in range(steps + 1):
        up = TILT_MAX * step / steps
        # Girder outer web, bottom and top corners, at this up-tilt.
        bottom_r, bottom_z = tilted(DECK_R, RIM_SKIRT_Z, -up)
        top_r, top_z = tilted(DECK_R, dish_z(DECK_R), -up)
        # The web must straddle the ramp lip's own height...
        assert bottom_z <= lip_z_ramp - 0.10, ("gate unsealed - web foot too high", up, bottom_z)
        assert top_z >= lip_z_ramp - 1e-9, ("gate unsealed - web head too low", up, top_z)
        worst_below = min(worst_below, lip_z_ramp - bottom_z)
        # ...and it must do so within a slot no car can enter.
        frac = (lip_z_ramp - bottom_z) / (top_z - bottom_z)
        web_r = bottom_r + (top_r - bottom_r) * frac
        gap = DECK_R - web_r
        assert -1e-6 <= gap <= 0.08, ("gate slot too wide", up, gap)
        worst_gap = max(worst_gap, gap)

    # Down-tilt: the deck must still be UNDER the ramp lip (a bounded drop
    # onto a floor), never withdrawn past it into a void.
    down_r, down_z = tilted(DECK_R, dish_z(DECK_R), TILT_MAX)
    assert down_r >= DECK_R, ("gate withdrawn at down-tilt", down_r)
    drop = lip_z_ramp - down_z
    assert 0.0 < drop <= 1.30, ("gate drop out of band", drop)
    return worst_gap, worst_below, drop


def pose_for_thumbnail(part_builds) -> None:
    """Render-only dressing, applied AFTER every DAE is exported.

    Every part is authored in the pose the runtime expects as its identity -
    the deck level and each ram already aimed foot-to-eye - so the authored
    scene is a legal state of the machine on its own. The thumbnail then puts
    it in a more interesting legal state: full 5.5 deg lean about +Y (the
    boarding azimuth's own axis, so the ramp/deck junction stays flush and the
    rim girder's seal is visible edge-on), rams aimed and extended by the same
    arithmetic the Lua uses.
    """

    from mathutils import Matrix, Vector

    pivot = Vector((0.0, 0.0, PIVOT_Z))
    rotation = Matrix.Rotation(TILT_MAX, 4, "Y")
    about_pivot = Matrix.Translation(pivot) @ rotation @ Matrix.Translation(-pivot)
    for obj in part_builds["deck"]["objects"]:
        obj.matrix_world = about_pivot @ obj.matrix_world
    # The fluoro match lines ride the deck (same pivot, same tiltQuat at
    # runtime), so the render pose must carry them too or they slice
    # level through the leaning dish.
    for ring_name in ("ring_live", "ring_ko"):
        for obj in part_builds[ring_name]["objects"]:
            obj.matrix_world = about_pivot @ obj.matrix_world

    for index in range(4):
        frame = ram_frame(index)
        foot = Vector(frame["foot"])
        eye = about_pivot @ Vector(frame["eye"])
        reach = eye - foot
        # Aim from the AS-BUILT axis, exactly as poseRams does.
        aim = Vector(frame["axis"]).rotation_difference(reach.normalized())
        rotate = (
            Matrix.Translation(foot)
            @ aim.to_matrix().to_4x4()
            @ Matrix.Translation(-foot)
        )
        stroke = Matrix.Translation(
            reach.normalized() * (reach.length - frame["length"])
        )
        for obj in part_builds[f"ram_{index + 1}"]["objects"]:
            obj.matrix_world = rotate @ obj.matrix_world
        for obj in part_builds[f"ram_rod_{index + 1}"]["objects"]:
            obj.matrix_world = stroke @ rotate @ obj.matrix_world



# ---------------------------------------------------------------------------
def main() -> None:
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)
    part_builds = build_parts(materials)

    parts = []
    for name, build in sorted(part_builds.items()):
        dae_path = VEHICLE_DIR / f"{MOD_ID}_{name}.dae"
        info = bk.export_part_shape(MOD_ID, name, dae_path, build["objects"], build["pivot"])
        info["path"] = f"vehicles/{MOD_ID}/{MOD_ID}_{name}.dae"
        if build.get("collision"):
            info["collision"] = True
        parts.append(info)

    # Every banner is its own flexbody bound to its own cloth node group, so
    # the solver deforms each render mesh directly. One shared mesh would
    # skin every banner to every other banner's nodes.
    banner_meshes = build_banner_cloth(materials)
    mesh_groups = {f"{MOD_ID}_visual": visual_objects}
    mesh_groups.update(banner_meshes)
    visual = bk.export_multi_flexbody(
        MOD_ID,
        VEHICLE_DIR / f"{MOD_ID}.dae",
        mesh_groups,
    )
    # A flexbody binds by NAME, and a name that does not resolve fails
    # SILENTLY - the mesh simply never draws, with nothing in any log. Prove
    # every group actually landed in the Collada under its exact key.
    _assert_meshes_exported(VEHICLE_DIR / f"{MOD_ID}.dae", mesh_groups)

    cage = build_cage()
    behavior = dict(spec.BEHAVIOR)
    bk.write_handoff(
        AUTHORING_ROOT / f"{MOD_ID}.handoff.json",
        mod_id=MOD_ID,
        display_name=spec.DISPLAY_NAME,
        cage=cage,
        visual=visual,
        visual_dae_relative=f"vehicles/{MOD_ID}/{MOD_ID}.dae",
        visual_mesh_name=f"{MOD_ID}_visual",
        # Group names are prefixed with the mod id on BOTH sides (the node's
        # "group" option and the flexbody's group list), so these must be the
        # bare suffixes add_banner_cloth passed to add_node.
        flexbodies_extra=[
            {"mesh": f"{MOD_ID}_nobori_{site['tag']}_mesh",
             "groups": [f"nobori_{site['tag']}"]}
            for site in nobori_sites()
        ],
        parts=parts,
        palette=spec.PALETTE,
        panel={
            "frame_x_node": f"{MOD_ID}_panel_frame_x",
            "frame_y_node": f"{MOD_ID}_panel_frame_y",
            "button_size": 0.12,
            # Per-button FRAME nodes and cap-diameter sizes, the centrifuge
            # 2026-08-09e recipe: prop_builder derives the click-box basis
            # from (idX-idRef, idY-idRef), and without the per-button links
            # it falls back to the shared frame pair, which skews every box
            # not co-located with it.
            "buttons": [
                {"id": button["id"], "title": button["title"],
                 "node": f"{MOD_ID}_panelbtn_{button['id']}",
                 "frame_x_node": f"{MOD_ID}_panelfx_{button['id']}",
                 "frame_y_node": f"{MOD_ID}_panelfy_{button['id']}",
                 "size": {"round_white": 0.14}[button.get("cap", "round_white")]}
                for button in spec.PANEL_BUTTONS
            ],
        },
        behavior={
            "tunables": behavior,
            "triggers": spec.TRIGGERS,
            "effects": spec.EFFECTS,
            "camera_distance": behavior.get("camera_distance", 30.0),
        },
    )
    pose_for_thumbnail(part_builds)
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        # Driver's approach: low, off the ramp's shoulder, so the frame reads
        # ramp -> threshold -> tilted deck, with the rim ring girder edge-on
        # (the member the whole boarding-safety argument rests on), the
        # scoreboard mast on the left and the hydraulic power unit on the
        # right. A high three-quarter view flattens the lean into a disc.
        camera_location=(-7.5, -33.0, 10.5),
        look_at=(-1.0, -4.0, 2.6),
    )
    gap, below, drop = _assert_gate_seal()
    print(
        f"SUMO_GYRO_PLATFORM generator complete: {len(parts)} parts, "
        f"{len(cage.nodes)} nodes, {len(cage.beams)} beams, "
        f"{len(cage.triangles)} triangles, ramp grade {RAMP_G1 * 100:.1f}%"
    )
    print(
        "  gate seal: worst slot at the ramp lip "
        f"{gap * 1000:.0f} mm wide, girder foot at least {below * 1000:.0f} mm "
        f"below the lip at every up-tilt; down-tilt drop onto the deck "
        f"{drop:.2f} m"
    )
    print(
        f"  committed step at the rim {spec.TILT_BAKE_STEP_RAD * DECK_R * 1000:.2f} mm, "
        f"collision rebuild ceiling {1.0 / spec.TILT_BAKE_INTERVAL:.1f}/s, "
        f"rim speed {spec.TILT_RATE_MAX_RAD_S * DECK_R:.3f} m/s"
    )


if __name__ == "__main__":
    main()
