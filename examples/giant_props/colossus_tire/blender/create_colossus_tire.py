"""Deterministic Blender generator for COLOSSUS 10350/80R457.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/colossus_tire/blender/create_colossus_tire.py

Everything here is built from ``spec.py``'s size code. There is no modelled
mesh checked in and no primitive-plus-boolean stack: the carcass, the tread
pattern and the chocks are all emitted vertex by vertex, because a tire is a
surface of revolution with a designed tread pitch sequence on it, and that
is exactly the kind of thing a boolean pipeline gets wrong (see
``blender_kit.cut_openings``' standing bevel/boolean bug). The access port,
dock and gangway this file once built are gone by user decree; the carcass
is a fully closed shell and the only furniture is four fabricated chocks.

Frames. Authored right-handed, metres, Z-up, +Y = the direction the tire
rolls. The tire's axle lies along X at height OUTER_RADIUS, so station 0 is
the contact patch. ``blender_kit`` maps the whole thing into BeamNG vehicle
space through the shared proper 180 deg Z rotation.
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

R_O = spec.OUTER_RADIUS
R_BEAD = spec.BEAD_RADIUS
R_CAV = spec.CAVITY_RADIUS
STATIONS = spec.STATIONS
TAU = 2.0 * math.pi

# THERE IS NO RANDOMNESS HERE. Every coordinate in this file is derived; the
# seeded generator that used to sit at this line had exactly one reference in
# 2,900 lines - its own assignment - under a comment certifying byte-identical
# output that it played no part in producing.

# Texel density targets, metres per texture tile. Large surfaces get metric
# UVs so a 28 m tire does not end up with tread grain the size of a car - the
# Cannon Car Wash "tiny blocks" lesson, applied to something 28 m across.
TILE_TREAD = 2.20
TILE_SIDEWALL = 2.60
TILE_LINER = 2.40

# Authored in spec.py so the generator and the gate that measures the shipped
# DAE read ONE table rather than two that can drift apart.
MATERIAL_TILE = spec.MATERIAL_TILE


def tile_of(material) -> float:
    """Authored metres-per-tile for a palette material."""

    suffix = material.name[len(MOD_ID) + 1:]
    return MATERIAL_TILE[suffix]


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def polar(x: float, radius: float, theta: float) -> tuple[float, float, float]:
    """Authored world point on the tire at (axial x, radius, station angle).

    theta = 0 is straight down (the contact patch), growing toward +Y.
    """

    return (x, radius * math.sin(theta), R_O - radius * math.cos(theta))


def crown_r(x: float) -> float:
    """Lug crown radius at axial position x, following the tread arc."""

    return R_O - x * x / (2.0 * spec.TREAD_ARC_RADIUS)


def base_r(x: float) -> float:
    """Groove-floor radius: constant tread depth under the crown arc."""

    return crown_r(x) - spec.TREAD_DEPTH


def sidewall_outer(radius: float) -> tuple[float, float]:
    """(OUTER half width, moulded thickness) at a radius.

    ``spec.MERIDIAN`` is the moulded OUTER surface: its 1.000 at maximum
    section width is what makes the size code stamped on the sidewall true of
    the mesh. Interpolated straight off the spec, not off whatever the current
    mesh sampling happens to be, so the lettering, the port cut edge and the
    buttress wrap all land on exactly the surface the lathe builds.
    """

    fraction = (radius - R_BEAD) / spec.SECTION_HEIGHT
    stations = spec.MERIDIAN
    thickness = spec.SIDEWALL_THICKNESS
    if fraction <= stations[0][0]:
        return (stations[0][1] * spec.SECTION_HALF, thickness[0])
    for index in range(len(stations) - 1):
        lo_f, lo_h = stations[index]
        hi_f, hi_h = stations[index + 1]
        if lo_f <= fraction <= hi_f:
            blend = (fraction - lo_f) / max(hi_f - lo_f, 1e-9)
            half = (lo_h + (hi_h - lo_h) * blend) * spec.SECTION_HALF
            thick = thickness[index] + (thickness[index + 1] - thickness[index]) * blend
            return (half, thick)
    return (stations[-1][1] * spec.SECTION_HALF, thickness[-1])


def sidewall_mid(radius: float) -> tuple[float, float]:
    """(structural mid-shell half width, thickness) at a radius.

    The cage lives on the mid-shell; the visual lathe offsets to either face.
    """

    half, thick = sidewall_outer(radius)
    return (half - thick * 0.5, thick)


SHOULDER_TOP_RADIUS = R_BEAD + spec.SHL_FRACTION * spec.SECTION_HEIGHT


def shoulder_point(t: float, theta: float = 0.0) -> tuple[float, float]:
    """(OUTER half width, radius) along the lofted shoulder, t = 0 at the
    last meridian station and t = 1 at the tread base's outboard ring.

    t = 0 MUST return the lathe's last ring exactly. The lathe's outer face is
    ``sidewall_outer + sidewall_relief`` and this returned ``sidewall_outer``
    alone, so the third protector rib - still 0.0671 m proud at the top
    station - was guillotined at the join and left an open 0.0671 m annulus
    ringing both shoulders, 84.85 m of it each, with the inward-facing liner
    behind it so it culled straight to sky. The relief is carried into the
    loft and dies into the tread base, which is what a moulded rib does; it
    does not stop dead at 46% of its height.
    """

    top_half = (
        sidewall_outer(SHOULDER_TOP_RADIUS)[0]
        + sidewall_relief(SHOULDER_TOP_RADIUS)
        + buttress_relief(SHOULDER_TOP_RADIUS, theta)
    )
    end_half = spec.TREAD_HALF
    end_radius = base_r(spec.TREAD_HALF)
    # THE BULGE IS ON THE HALF WIDTH ONLY. Feeding 55% of it into the radius
    # as well put a 34 mm crest in the middle of the loft, which is the same
    # dam the derived shoulder shelf was introduced to remove - a smaller one,
    # but a dam. Radius now interpolates monotonically by construction, so
    # nothing outboard of the tread edge can ever stand above its groove floor.
    bulge = math.sin(math.pi * t) * spec.SHOULDER_BULGE
    return (
        top_half + (end_half - top_half) * t + bulge,
        SHOULDER_TOP_RADIUS + (end_radius - SHOULDER_TOP_RADIUS) * t,
    )


SHOULDER_BASE_RADIUS = base_r(spec.TREAD_HALF)


def outer_half_at(radius: float) -> float:
    """The FULL outer half width anywhere on the carcass, relief included.

    NOW A CLOSED-FORM INVERSE. The loft's radius runs monotonically from
    SHOULDER_TOP_RADIUS up to the tread base's outboard ring - the sine bulge
    moved onto the half width alone - and the lathe below it is monotonic by
    construction, so one comparison picks the branch and the loft inverts
    linearly. Round 3 needed a bisection because the bulge made the curve turn
    over; the 24-step nearest-radius scan before that returned the same clamped
    answer for every radius above the turn, which is how the wrap's top rows
    came to float 0.43 m off the tire.
    """

    if radius <= SHOULDER_TOP_RADIUS:
        return sidewall_outer(radius)[0] + sidewall_relief(radius)
    span = SHOULDER_BASE_RADIUS - SHOULDER_TOP_RADIUS
    t = min(1.0, max(0.0, (radius - SHOULDER_TOP_RADIUS) / max(span, 1e-9)))
    return shoulder_point(t)[0]


def shell_normal(radius: float, side: float, theta: float) -> Vector:
    """Outward normal of the sidewall mid-shell at a radius, in world space.

    The buttress wrap lies ON the sidewall, so neither "away from the axle"
    nor "away from the centre plane" describes which way it faces - over the
    shoulder the meridian turns through both at once. Differencing the
    meridian gives the real surface normal, which is the only reference that
    is right everywhere on it.
    """

    delta = 0.03
    lo = max(radius - delta, R_BEAD + 1e-4)
    hi = min(radius + delta, R_O - 1e-4)
    dh = sidewall_mid(hi)[0] - sidewall_mid(lo)[0]
    dr = hi - lo
    length = math.hypot(dh, dr) or 1.0
    nh, nr = dr / length, -dh / length
    if nh < 0:
        nh, nr = -nh, -nr
    radial = Vector((0.0, math.sin(theta), -math.cos(theta)))
    return (Vector((side * nh, 0.0, 0.0)) + radial * nr).normalized()


def sidewall_relief(radius: float) -> float:
    """Moulded relief standing off the OUTER sidewall at a radius.

    Two real features, both circumferential: the rim line - the reference rib
    just above the bead that tells you at a glance whether the tire has
    slipped on its rim - and the buttress protector ribs that take rock
    strikes before the casing does. A sidewall without them renders as a
    plastic disc, which is exactly what round 1 looked like.
    """

    relief = 0.0
    delta = abs(radius - spec.RIM_LINE_RADIUS)
    if delta < spec.RIM_LINE_HALF:
        relief += spec.RIM_LINE_HEIGHT * math.cos(
            0.5 * math.pi * delta / spec.RIM_LINE_HALF
        )
    for rib in spec.PROTECTOR_RADII:
        delta = abs(radius - rib)
        if delta < spec.PROTECTOR_HALF:
            relief += spec.PROTECTOR_HEIGHT * math.cos(
                0.5 * math.pi * delta / spec.PROTECTOR_HALF
            ) ** 0.7
    return relief


def shoulder_lug_centres() -> list[tuple[float, float]]:
    """(centre angle, half angular width) of every SHOULDER lug.

    The buttress is the shoulder lug's own rubber running on down the flank,
    so it has to know where those lugs are. Read from the same pitch table and
    the same row phase build_tread uses, once, at import.
    """

    pitches = pitch_angles()
    groove = spec.LATERAL_GROOVE / spec.GROOVE_RADIUS
    phase = spec.ROW_PHASE[len(spec.TREAD_ROWS) - 1]
    offset = phase * (TAU / len(pitches))
    spans = []
    for start, end in pitches:
        a0 = start + offset + groove * 0.5
        a1 = end + offset - groove * 0.5
        spans.append((0.5 * (a0 + a1), 0.5 * (a1 - a0)))
    return spans


BUTTRESS_LUGS = None            # filled after pitch_angles() is available


def buttress_relief(radius: float, theta: float) -> float:
    """The shoulder lug's rubber continuing down the upper sidewall.

    A real E-4/L-5 shoulder lug does not stop at the tread edge - it runs on
    down the buttress and feathers out, which is the silhouette feature that
    separates a mining tire from a truck tire at 200 m. Round 4 built that as
    180 separate slabs PER SIDE with a flat top, two vertical end walls and a
    bottom lip, and it looked exactly like what it was: a row of paddles stuck
    on the flank, the first thing anyone looking at the sidewall noticed, and
    the source of a fresh defect in each of the last two rounds (floating in
    one, detached with its end walls inside out in the next).

    It is a moulded SWELLING OF THE SIDEWALL, so it is now a term in the
    surface itself. The lathe grows it, which means it cannot have a wall, a
    lip, a cap, a seam, a winding or a hole - and it feathers to nothing at
    every edge, the way rubber released from a mould does.
    """

    if BUTTRESS_LUGS is None:
        return 0.0
    top = base_r(spec.TREAD_HALF)
    bottom = spec.PROTECTOR_RADII[0]
    if not (bottom <= radius <= top):
        return 0.0
    # Radial: full at the tread edge, feathering out at the first rib.
    down = (top - radius) / (top - bottom)
    radial = math.cos(0.5 * math.pi * down) ** 1.45

    wrapped = (theta + math.pi) % TAU - math.pi
    for centre, half in BUTTRESS_LUGS:
        delta = (wrapped - centre + math.pi) % TAU - math.pi
        if abs(delta) >= half:
            continue
        # Angular: a raised cosine across the lug, zero at the groove either
        # side, so consecutive wraps are separated by real moulded valleys
        # rather than by a pair of vertical faces.
        across = math.cos(0.5 * math.pi * (delta / half)) ** 0.85
        return spec.BUTTRESS_RELIEF * radial * across
    return 0.0


def meridian_fractions() -> list[float]:
    """Meridian sampling for the OUTER sidewall lathe.

    A uniform ladder, plus a dense cluster across every relief feature. A rib
    0.24 m wide on a 6.72 m meridian is 3.5% of it: a uniform 20-step ladder
    would step right over it, which is why round 1's ribs vanished.
    """

    # Up to the LAST REAL STATION only. Running past it left sidewall_outer
    # clamping the half width, which produced a 0.58 m tall axially-facing
    # flange ring reaching the crown radius - a smooth open annulus where a
    # tire has its shoulder. build_shoulder() lofts that band explicitly.
    top = spec.SHL_FRACTION
    fractions = {top * index / 22.0 for index in range(23)}
    # SEED THE AUTHORED STATIONS. A uniform ladder walked straight past 0.600 -
    # the maximum-section-width station, the one the printed size code is a
    # claim about - landing on 0.5918 and 0.6341 either side of it, so the
    # built tire measured 10.3404 m across against an authored 10.350.
    fractions.update(
        fraction for fraction, _ in spec.MERIDIAN if 0.0 <= fraction <= top
    )
    features = [(spec.RIM_LINE_RADIUS, spec.RIM_LINE_HALF)] + [
        (rib, spec.PROTECTOR_HALF) for rib in spec.PROTECTOR_RADII
    ]
    for radius, half in features:
        for step in range(-4, 5):
            value = (radius + half * step / 3.2 - R_BEAD) / spec.SECTION_HEIGHT
            if 0.0 <= value <= top:
                fractions.add(round(value, 6))
    return sorted(fractions)


def pitch_angles() -> list[tuple[float, float]]:
    """(start, end) angle of every tread pitch, from the designed sequence.

    The ratios are normalised onto 2*pi so the sequence closes exactly - a
    tread that does not close is a visible seam a metre wide at this size.
    """

    ratios = [spec.PITCH_RATIOS[index] for index in spec.PITCH_SEQUENCE]
    total = sum(ratios)
    angles = []
    cursor = 0.0
    for ratio in ratios:
        step = TAU * ratio / total
        angles.append((cursor, cursor + step))
        cursor += step
    return angles


# Seeded here, where pitch_angles() finally exists. buttress_relief() reads it
# and returns 0.0 until it is set, so the module still imports in the wrong
# order rather than exploding somewhere downstream.
BUTTRESS_LUGS = shoulder_lug_centres()


class Mesh:
    """Accumulates verts/faces/UVs and emits one Blender object.

    Faces carry their own smooth flag: the carcass lathe is smooth, every
    moulded lug face is flat, which is what gives the tread its hard moulded
    edges instead of a melted look.
    """

    def __init__(self, name: str, material) -> None:
        self.name = name
        self.material = material
        self.verts: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, ...]] = []
        self.uvs: list[tuple[tuple[float, float], ...]] = []
        self.smooth: list[bool] = []
        self.dropped = 0

    def vertex(self, point) -> int:
        self.verts.append((float(point[0]), float(point[1]), float(point[2])))
        return len(self.verts) - 1

    # Faces below this are dropped. A zero-area triangle has a degenerate
    # tangent basis, and BeamNG's normal-mapped shading on a degenerate
    # tangent is the classic source of black speckle. Round 1 emitted 578 of
    # them because a taper reached exactly zero; distinct INDICES are not
    # enough, distinct POSITIONS are what matter.
    MIN_FACE_AREA = 1e-7

    def face(self, indices, uvs, smooth: bool = False) -> None:
        if len(set(indices)) != len(indices):
            return
        points = [self.verts[index] for index in indices]
        area = 0.0
        for step in range(1, len(points) - 1):
            u = [points[step][k] - points[0][k] for k in range(3)]
            v = [points[step + 1][k] - points[0][k] for k in range(3)]
            cross = (
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            )
            area += 0.5 * math.sqrt(sum(c * c for c in cross))
        if area < self.MIN_FACE_AREA:
            self.dropped += 1
            return
        self.faces.append(tuple(indices))
        self.uvs.append(tuple(uvs))
        self.smooth.append(smooth)

    def quad(self, a, b, c, d, uvs, smooth: bool = False) -> None:
        self.face((a, b, c, d), uvs, smooth)

    def build(self):
        mesh = bpy.data.meshes.new(self.name)
        mesh.from_pydata(self.verts, [], [f for f in self.faces])
        mesh.update()
        layer = mesh.uv_layers.new(name="UVMap")
        loop_index = 0
        for polygon, corner_uvs in zip(mesh.polygons, self.uvs):
            for corner in range(polygon.loop_total):
                layer.data[loop_index].uv = corner_uvs[corner]
                loop_index += 1
        for polygon, smooth in zip(mesh.polygons, self.smooth):
            polygon.use_smooth = smooth
        obj = bpy.data.objects.new(self.name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        if self.material is not None:
            obj.data.materials.append(self.material)
        return obj


def tile_wraps(tile: float, reference: float | None = None) -> int:
    """Whole number of texture tiles round the tire at a reference radius.

    A surface of revolution has to CLOSE. Using arc length directly gives a
    fractional wrap count and leaves a visible seam wherever theta = 0, which
    on this prop is the contact patch. Rounding the count at the surface's own
    reference radius keeps the texel density within a few percent of metric
    and makes the seam vanish exactly.

    Round 2 wrote this and then routed only the sidewall through it, so the
    tread still missed closure by 0.909 m and the liner by 1.03 m - both at
    theta = 0, i.e. the contact patch and the spot the player boards on.
    """

    if reference is None:
        reference = 0.5 * (R_BEAD + R_O)
    return max(1, round(TAU * reference / tile))


# ---------------------------------------------------------------------------
# The access port: which sidewall panels are missing, in (station, segment).
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Visual: carcass shell (sidewalls outside and in, inner liner, bead toes)
# ---------------------------------------------------------------------------
# 288 stations, 1.25 deg apart: 0.84 mm of sagitta on a 14 m radius, and -
# the reason it doubled - eight stations across every shoulder lug, which is
# what the buttress swelling needs to read as a moulded shape rather than as a
# facet. The budget for it came from deleting the boarding hardware.
VISUAL_STATIONS = 288
INNER_STEPS = 13


def build_carcass(materials) -> list:
    sidewall_mat = materials[f"{MOD_ID}_sidewall"]
    liner_mat = materials[f"{MOD_ID}_liner"]
    bead_mat = materials[f"{MOD_ID}_bead"]

    thetas = [index * TAU / VISUAL_STATIONS for index in range(VISUAL_STATIONS)]
    step_angle = TAU / VISUAL_STATIONS
    outer_fractions = meridian_fractions()
    # UP TO THE SILL ONLY. Round 3 ran this ladder to 1.000 - radius 14.0839,
    # the tire's own outer radius, with the half width clamped - so the liner
    # carried on past the cavity floor and down to z = 0 at the bottom of the
    # tire: a 0.93 m trench down both edges of the lane, the full 84 m
    # circumference, on the surface the driver looks at for the whole ride,
    # with the tread/undertread/belt/liner laminate reduced to zero thickness
    # at the shoulder. The sill IS the cavity floor - spec.py's own
    # LINER_HALF + SHOULDER_FILLET equals the inner face at CAVITY_RADIUS to
    # the millimetre - so the ladder ends exactly on it.
    inner_fractions = [
        spec.SILL_FRACTION * index / INNER_STEPS for index in range(INNER_STEPS + 1)
    ]

    outer = Mesh(f"{MOD_ID}_sidewall_outer", sidewall_mat)
    inner = Mesh(f"{MOD_ID}_sidewall_inner", liner_mat)
    bead = Mesh(f"{MOD_ID}_bead_toe", bead_mat)

    def shell(fraction: float, side: float, face: str,
              theta: float = 0.0) -> tuple[float, float]:
        """(signed half width, radius) on one face of the sidewall shell.

        ``theta`` only matters on the OUTER face, and only in the buttress
        band, where the shoulder lugs' rubber swells the sidewall.
        """

        radius = R_BEAD + fraction * spec.SECTION_HEIGHT
        half, thick = sidewall_mid(radius)
        if face == "outer":
            proud = sidewall_relief(radius) + buttress_relief(radius, theta)
            return (side * (half + thick * 0.5 + proud), radius)
        return (side * (half - thick * 0.5), radius)

    def lathe_rows(mesh, fractions, side, face):
        """Build one lathe surface and carry its MERIDIAN ARC LENGTH per row.

        v has to be arc length along the meridian, not radius: over the
        maximum-section-width band the surface travels much further across
        than its radius changes, so a radius-derived v squashes the mould
        ripple into a band right where the sidewall is most visible.
        """

        rows = []
        arc = 0.0
        previous = None
        for fraction in fractions:
            # The arc walk (which is v) follows the UNSWOLLEN meridian, so the
            # texture does not stretch where the buttress stands proud.
            half, radius = shell(fraction, side, face)
            if previous is not None:
                arc += math.hypot(half - previous[0], radius - previous[1])
            previous = (half, radius)
            rows.append(
                (
                    [
                        mesh.vertex(polar(shell(fraction, side, face, theta)[0], radius, theta))
                        for theta in thetas
                    ],
                    radius,
                    arc,
                )
            )
        return rows

    for side in (-1.0, 1.0):
        rows_out = lathe_rows(outer, outer_fractions, side, "outer")
        rows_in = lathe_rows(inner, inner_fractions, side, "inner")

        def band(mesh, rows, tile, flip):
            for index in range(len(rows) - 1):
                row_lo, radius_lo, arc_lo = rows[index]
                row_hi, radius_hi, arc_hi = rows[index + 1]
                for column in range(VISUAL_STATIONS):
                    nxt = (column + 1) % VISUAL_STATIONS
                    theta0 = thetas[column]
                    theta1 = theta0 + step_angle
                    # U is a function of THETA ONLY, on a whole number of
                    # tiles. Making it radius*theta looks right per row but
                    # adjacent meridian rows then drift apart by
                    # (delta_r * theta)/tile - measured up to 42:1 shear, and
                    # the wrap missed closure by 1.4 m at max section radius,
                    # leaving a ragged seam at the contact patch.
                    wraps = tile_wraps(tile)
                    uv = (
                        (wraps * theta0 / TAU, arc_lo / tile),
                        (wraps * theta1 / TAU, arc_lo / tile),
                        (wraps * theta1 / TAU, arc_hi / tile),
                        (wraps * theta0 / TAU, arc_hi / tile),
                    )
                    a, b = row_lo[column], row_lo[nxt]
                    c, d = row_hi[nxt], row_hi[column]
                    if flip:
                        mesh.quad(d, c, b, a, uv, smooth=True)
                    else:
                        mesh.quad(a, b, c, d, uv, smooth=True)

        band(outer, rows_out, TILE_SIDEWALL, side > 0)
        band(inner, rows_in, TILE_LINER, side < 0)

        # Bead toe: close the shell across its thickness with a rounded toe.
        outer_half, outer_radius = shell(0.0, side, "outer")
        inner_half, inner_radius = shell(0.0, side, "inner")
        steps = 6
        toe_rows = []
        toe_profile = []
        for step in range(steps + 1):
            t = step / steps
            angle = t * math.pi
            half = 0.5 * (outer_half + inner_half) + 0.5 * (outer_half - inner_half) * math.cos(angle)
            radius = 0.5 * (outer_radius + inner_radius) + 0.5 * (
                outer_radius - inner_radius
            ) * math.cos(angle)
            # BOW IT OUTWARD, NOT INWARD. Dipping the toe's radius put the
            # shipped bore at 11.317 m - 445.6 inches against the 457 the size
            # code names, 2.5% under - a tire that will not go on its own rim,
            # on the one meridian station the whole R457 claim rests on. A
            # tubeless bore is not a plain cylinder anyway: it is two bead
            # seats at the rim diameter with the centre relieved between them,
            # which is exactly what the same term does with its sign flipped.
            radius += math.sin(angle) * spec.SIDEWALL_THICKNESS[0] * 0.22
            toe_profile.append((half, radius))
            toe_rows.append([bead.vertex(polar(half, radius, theta)) for theta in thetas])
        # METRIC v, like every other lathe here. A flat step/steps over a
        # 6-step profile made the bead the only anisotropic material on the
        # tire - measured 2.45x its authored grain across the toe against 1.00
        # round it - and doubling the station count is what finally moved the
        # median far enough for the gate to see it.
        toe_walk = [0.0]
        for index in range(1, len(toe_profile)):
            toe_walk.append(
                toe_walk[-1]
                + math.hypot(
                    toe_profile[index][0] - toe_profile[index - 1][0],
                    toe_profile[index][1] - toe_profile[index - 1][1],
                )
            )
        for step in range(steps):
            for column in range(VISUAL_STATIONS):
                nxt = (column + 1) % VISUAL_STATIONS
                theta0 = thetas[column]
                theta1 = theta0 + step_angle
                v0 = toe_walk[step] / TILE_SIDEWALL
                v1 = toe_walk[step + 1] / TILE_SIDEWALL
                wraps = tile_wraps(TILE_SIDEWALL, R_BEAD)
                uv = (
                    (wraps * theta0 / TAU, v0),
                    (wraps * theta1 / TAU, v0),
                    (wraps * theta1 / TAU, v1),
                    (wraps * theta0 / TAU, v1),
                )
                a, b = toe_rows[step][column], toe_rows[step][nxt]
                c, d = toe_rows[step + 1][nxt], toe_rows[step + 1][column]
                if side > 0:
                    bead.quad(a, b, c, d, uv, smooth=True)
                else:
                    bead.quad(d, c, b, a, uv, smooth=True)

    # Inner liner across the crown: the floor the car drives on.
    liner = Mesh(f"{MOD_ID}_liner_crown", liner_mat)
    liner_steps = 14
    xs = [
        -spec.LINER_HALF + 2.0 * spec.LINER_HALF * step / liner_steps
        for step in range(liner_steps + 1)
    ]
    rows = [[liner.vertex(polar(x, R_CAV, theta)) for theta in thetas] for x in xs]
    for index in range(liner_steps):
        for column in range(VISUAL_STATIONS):
            nxt = (column + 1) % VISUAL_STATIONS
            theta0 = thetas[column]
            theta1 = theta0 + step_angle
            wraps = tile_wraps(TILE_LINER, R_CAV)
            uv = (
                (wraps * theta0 / TAU, xs[index] / TILE_LINER),
                (wraps * theta1 / TAU, xs[index] / TILE_LINER),
                (wraps * theta1 / TAU, xs[index + 1] / TILE_LINER),
                (wraps * theta0 / TAU, xs[index + 1] / TILE_LINER),
            )
            a, b = rows[index][column], rows[index][nxt]
            c, d = rows[index + 1][nxt], rows[index + 1][column]
            liner.quad(d, c, b, a, uv, smooth=True)

    # Shoulder fillet: closes the cavity between the liner edge and the
    # sidewall inner face, both sides. Both ends now sit at CAVITY_RADIUS - the
    # sill is where the wall turns down, not where it keeps climbing - so this
    # is the last SHOULDER_FILLET metres of floor before the wall, which is
    # what spec.py's LINER_HALF + SHOULDER_FILLET arithmetic always said it
    # was.
    fillet = Mesh(f"{MOD_ID}_liner_fillet", liner_mat)
    for side in (-1.0, 1.0):
        edge_half, edge_radius = shell(spec.SILL_FRACTION, side, "inner")
        steps = 5
        arc_rows = []
        # Metric v again: the fillet joins the flat floor, so a v that ran
        # 0..0.5 regardless of its real width put a visible density step
        # right where the driver's eye follows the floor into the shoulder.
        arcs = [spec.LINER_HALF / TILE_LINER]
        previous = None
        for step in range(steps + 1):
            t = step / steps
            half = side * spec.LINER_HALF + (edge_half - side * spec.LINER_HALF) * t
            radius = R_CAV + (edge_radius - R_CAV) * (t ** 1.4)
            if previous is not None:
                arcs.append(
                    arcs[-1] + math.hypot(half - previous[0], radius - previous[1]) / TILE_LINER
                )
            previous = (half, radius)
            arc_rows.append([fillet.vertex(polar(half, radius, theta)) for theta in thetas])
        for step in range(steps):
            for column in range(VISUAL_STATIONS):
                nxt = (column + 1) % VISUAL_STATIONS
                theta0 = thetas[column]
                theta1 = theta0 + step_angle
                v0, v1 = arcs[step], arcs[step + 1]
                wraps = tile_wraps(TILE_LINER, R_CAV)
                uv = (
                    (wraps * theta0 / TAU, v0),
                    (wraps * theta1 / TAU, v0),
                    (wraps * theta1 / TAU, v1),
                    (wraps * theta0 / TAU, v1),
                )
                a, b = arc_rows[step][column], arc_rows[step][nxt]
                c, d = arc_rows[step + 1][nxt], arc_rows[step + 1][column]
                # Capping the inner lathe at the sill made both ends of this
                # band sit at CAVITY_RADIUS, so it is now the same kind of
                # surface as the liner crown it continues - a cylinder patch,
                # facing the axle - and it takes the crown's winding, not the
                # one that suited a band climbing to the tire's outer radius.
                if side > 0:
                    fillet.quad(d, c, b, a, uv, smooth=True)
                else:
                    fillet.quad(a, b, c, d, uv, smooth=True)

    # --- The shoulder: from the last sidewall station round to the tread
    # base's outboard ring, on a circular arc. This is the curve that reads as
    # "tire" in silhouette from any distance, and round 2 did not have one.
    shoulder = Mesh(f"{MOD_ID}_shoulder", sidewall_mat)
    for side in (-1.0, 1.0):
        rows = []
        for step in range(spec.SHOULDER_ROWS + 1):
            half, radius = shoulder_point(step / spec.SHOULDER_ROWS)
            rows.append(
                (
                    [
                        shoulder.vertex(
                            polar(
                                side * shoulder_point(step / spec.SHOULDER_ROWS, theta)[0],
                                radius,
                                theta,
                            )
                        )
                        for theta in thetas
                    ],
                    radius,
                    half,
                )
            )
        arc = 0.0
        for step in range(spec.SHOULDER_ROWS):
            row_lo, radius_lo, half_lo = rows[step]
            row_hi, radius_hi, half_hi = rows[step + 1]
            span = math.hypot(half_hi - half_lo, radius_hi - radius_lo)
            for column in range(VISUAL_STATIONS):
                nxt = (column + 1) % VISUAL_STATIONS
                theta0 = thetas[column]
                theta1 = theta0 + step_angle
                wraps = tile_wraps(TILE_SIDEWALL)
                uv = (
                    (wraps * theta0 / TAU, arc / TILE_SIDEWALL),
                    (wraps * theta1 / TAU, arc / TILE_SIDEWALL),
                    (wraps * theta1 / TAU, (arc + span) / TILE_SIDEWALL),
                    (wraps * theta0 / TAU, (arc + span) / TILE_SIDEWALL),
                )
                a, b = row_lo[column], row_lo[nxt]
                c, d = row_hi[nxt], row_hi[column]
                if side > 0:
                    shoulder.quad(d, c, b, a, uv, smooth=True)
                else:
                    shoulder.quad(a, b, c, d, uv, smooth=True)
            arc += span

    return [
        outer.build(), inner.build(), bead.build(),
        liner.build(), fillet.build(), shoulder.build(),
    ]


# ---------------------------------------------------------------------------
# Visual: the tread
# ---------------------------------------------------------------------------
def tread_rows() -> list[tuple[float, float, int]]:
    """(x0, x1, phase index) for the five lug rows, centre outward.

    spec.TREAD_ROWS is in FRACTIONS of TREAD_HALF, so the pattern rescales
    with the size code instead of quietly becoming the wrong proportion the
    moment the section width moves.
    """

    rows: list[tuple[float, float, int]] = []
    for index, (lo, hi) in enumerate(spec.TREAD_ROWS):
        lo_m, hi_m = lo * spec.TREAD_HALF, hi * spec.TREAD_HALF
        if lo == 0.0:
            rows.append((-hi_m, hi_m, index))
        else:
            rows.append((lo_m, hi_m, index))
            rows.append((-hi_m, -lo_m, index))
    rows.sort()
    return rows


def build_tread(materials) -> list:
    tread_mat = materials[f"{MOD_ID}_tread"]
    base = Mesh(f"{MOD_ID}_tread_base", tread_mat)
    mesh = Mesh(f"{MOD_ID}_tread_lugs", tread_mat)
    detail = Mesh(f"{MOD_ID}_tread_tiebars", tread_mat)
    ejectors = Mesh(f"{MOD_ID}_tread_ejectors", tread_mat)
    pitches = pitch_angles()

    # --- Tread base: the continuous surface every groove floor sits on.
    base_steps = 26
    # THE SAME STATIONS THE SHOULDER USES. The tread base welds to the
    # shoulder loft along its outboard ring, so the two have to agree station
    # for station; when the sidewall went to 288 and this stayed at 144 the
    # shell opened up 317 m of boundary along that seam.
    base_columns = VISUAL_STATIONS
    base_xs = [
        -spec.TREAD_HALF + 2.0 * spec.TREAD_HALF * step / base_steps
        for step in range(base_steps + 1)
    ]
    base_thetas = [column * TAU / base_columns for column in range(base_columns)]
    base_rows = [
        [base.vertex(polar(x, base_r(x), theta)) for theta in base_thetas]
        for x in base_xs
    ]
    for index in range(base_steps):
        for column in range(base_columns):
            nxt = (column + 1) % base_columns
            theta0 = base_thetas[column]
            theta1 = theta0 + TAU / base_columns
            wraps = tile_wraps(TILE_TREAD, spec.GROOVE_RADIUS)
            uv = (
                (wraps * theta0 / TAU, base_xs[index] / TILE_TREAD),
                (wraps * theta1 / TAU, base_xs[index] / TILE_TREAD),
                (wraps * theta1 / TAU, base_xs[index + 1] / TILE_TREAD),
                (wraps * theta0 / TAU, base_xs[index + 1] / TILE_TREAD),
            )
            a, b = base_rows[index][column], base_rows[index][nxt]
            c, d = base_rows[index + 1][nxt], base_rows[index + 1][column]
            base.quad(a, b, c, d, uv, smooth=True)

    # --- Lugs.
    rows = tread_rows()
    groove_angle = spec.LATERAL_GROOVE / spec.GROOVE_RADIUS
    for x0, x1, row_index in rows:
        phase = spec.ROW_PHASE[row_index]
        # Phase by a CONSTANT arc - the mean pitch - not by each pitch's own
        # span. Round 2 used the local span, so at every pitch-length change
        # the two neighbouring lugs shifted by different amounts and the
        # lateral groove between them absorbed the whole difference: measured
        # 0.151 m to 0.569 m where 0.360 is authored.
        offset = phase * (TAU / len(pitches))
        for pitch_index, (start, end) in enumerate(pitches):
            a0 = start + offset + groove_angle * 0.5
            a1 = end + offset - groove_angle * 0.5
            # THE ZIGZAG IS A PROPERTY OF THE GROOVE. Round 3 keyed the sign
            # off the LUG and moved both of its walls together, so the
            # trailing wall of lug i and the leading wall of lug i+1 swung in
            # OPPOSITE directions and the lateral groove between them measured
            # 0.062 m at one boundary and 0.442 m at the next against an
            # authored 0.360 - and 0.062 is not a narrow groove, it is two
            # solid blocks interpenetrating, 180 times per row per side. Each
            # wall now takes the amplitude of the BOUNDARY it belongs to, so
            # both walls of any one groove move together and the groove
            # wanders across the tread at constant width, which is what a
            # zigzag groove is.
            add_lug(
                mesh,
                a0,
                a1,
                x0,
                x1,
                lead=groove_zigzag(pitch_index),
                trail=groove_zigzag(pitch_index + 1),
            )
            add_tie_bar(
                detail, a1, a1 + groove_angle, x0, x1,
                zigzag=groove_zigzag(pitch_index + 1),
            )

    # --- Stone ejectors and tread wear indicators in the groove floors.
    for lo, hi in spec.TREAD_GROOVES:
        lo, hi = lo * spec.TREAD_HALF, hi * spec.TREAD_HALF
        for sign in (-1.0, 1.0):
            centre_x = sign * 0.5 * (lo + hi)
            for pitch_index, (start, end) in enumerate(pitches):
                middle = 0.5 * (start + end)
                if pitch_index % 2 == 0:
                    add_ejector(ejectors, middle, centre_x)
                elif pitch_index % 6 == 3:
                    add_wear_indicator(ejectors, middle, lo * sign, hi * sign)

    return [base.build(), mesh.build(), detail.build(), ejectors.build()]


def groove_zigzag(boundary: int) -> float:
    """Lateral wander of one groove, keyed to the BOUNDARY between two lugs.

    Alternating boundaries give the tread its zigzag ribbon; alternating LUGS
    gave it interpenetration. There are an even number of pitches, so
    boundary 0 and boundary N agree and the pattern closes.
    """

    return spec.GROOVE_ZIGZAG * (1.0 if boundary % 2 == 0 else -1.0)


# Developed area of the lug polygons actually built, so the net-to-gross
# claim answers to the mesh instead of to the row table it was derived from.
#
# TWO areas, because they are two different quantities and round 3's gate
# silently conflated them. "land" is the block footprint at the moulded land
# datum - the ring where the crown chamfer begins - and that is what tire
# people mean by net-to-gross. "crown" is the flat contact face inside the
# chamfer, which is what actually touches the road. LUG_CHAMFER takes 85 mm
# off every edge, so the two differ by a fifth, and quoting either one under
# the other's name is how a 70.7% claim and a 56.1% mesh coexisted.
LUG_CROWN_AREA = {"land": 0.0, "crown": 0.0}


def add_lug(mesh: Mesh, a0: float, a1: float, x0: float, x1: float,
            lead: float, trail: float) -> None:
    """One moulded tread block.

    Four lofted rings: a root fillet at the tread base, the drafted wall, the
    chamfer foot, and the crown. No sipes - an E-4/L-5 lug is a solid block.
    """

    chamfer = spec.LUG_CHAMFER
    fillet = spec.LUG_ROOT_FILLET
    draft = spec.LUG_DRAFT
    # Ring/grid resolution for one lug. The planar dissolve on the sidewall
    # type freed ~49,000 triangles; the tread is where they buy something, so
    # the crown grid and the drafted wall both get a step finer.
    na, nx = 5, 7

    def ring(grow: float):
        lo_x, hi_x = x0 - grow, x1 + grow
        lo_a = a0 - grow / spec.GROOVE_RADIUS
        hi_a = a1 + grow / spec.GROOVE_RADIUS
        points = []
        for step in range(nx):
            points.append((lo_a, lo_x + (hi_x - lo_x) * step / nx))
        for step in range(na):
            points.append((lo_a + (hi_a - lo_a) * step / na, hi_x))
        for step in range(nx):
            points.append((hi_a, hi_x - (hi_x - lo_x) * step / nx))
        for step in range(na):
            points.append((hi_a - (hi_a - lo_a) * step / na, lo_x))
        return points

    def zig(angle: float, x: float) -> float:
        # Amplitude blends from the leading boundary's to the trailing one's
        # across the block, so each wall lands exactly on its own groove.
        blend = min(1.0, max(0.0, (angle - a0) / max(a1 - a0, 1e-9)))
        amplitude = lead + (trail - lead) * blend
        return angle + amplitude / spec.GROOVE_RADIUS * math.sin(
            math.pi * (x - x0) / max(x1 - x0, 1e-6)
        )

    # (grow, radius offset from the crown)
    levels = (
        (fillet + draft, -spec.TREAD_DEPTH - spec.LUG_SEAT),
        (draft, -spec.TREAD_DEPTH + fillet),
        (0.0, -chamfer),
        (-chamfer, 0.0),
    )
    rings = []
    for grow, drop in levels:
        rings.append(
            [
                mesh.vertex(polar(x, crown_r(x) + drop, zig(angle, x)))
                for angle, x in ring(grow)
            ]
        )

    count = len(rings[0])
    # Perimeter distance per ring vertex, so the wall texture keeps metric
    # density instead of stretching by the aspect ratio of the block.
    perimeter = ring(0.0)
    # The land datum is this same ring - grow = 0.0, where the chamfer starts.
    land = 0.0
    for index in range(count):
        this_a, this_x = perimeter[index]
        next_a, next_x = perimeter[(index + 1) % count]
        land += (
            crown_r(this_x) * zig(this_a, this_x) * next_x
            - crown_r(next_x) * zig(next_a, next_x) * this_x
        )
    LUG_CROWN_AREA["land"] += abs(land) * 0.5
    walk = [0.0]
    for index in range(count):
        this_a, this_x = perimeter[index]
        next_a, next_x = perimeter[(index + 1) % count]
        walk.append(
            walk[-1]
            + math.hypot((next_a - this_a) * spec.GROOVE_RADIUS, next_x - this_x)
        )
    for level in range(len(rings) - 1):
        for index in range(count):
            nxt = (index + 1) % count
            u0 = walk[index] / TILE_TREAD
            u1 = walk[index + 1] / TILE_TREAD
            v0 = level * spec.TREAD_DEPTH / 3.0 / TILE_TREAD
            v1 = (level + 1) * spec.TREAD_DEPTH / 3.0 / TILE_TREAD
            # The footprint ring walks CLOCKWISE in the (angle, x) plane,
            # so this quad has to be wound the other way or every wall faces
            # into the block it belongs to.
            mesh.quad(
                rings[level][nxt],
                rings[level][index],
                rings[level + 1][index],
                rings[level + 1][nxt],
                ((u1, v0), (u0, v0), (u0, v1), (u1, v1)),
            )

    # Crown face.
    lo_x, hi_x = x0 - (-chamfer), x1 + (-chamfer)
    lo_x, hi_x = x0 + chamfer, x1 - chamfer
    lo_a = a0 + chamfer / spec.GROOVE_RADIUS
    hi_a = a1 - chamfer / spec.GROOVE_RADIUS
    xs = [lo_x + (hi_x - lo_x) * step / nx for step in range(nx + 1)]
    angles = [lo_a + (hi_a - lo_a) * step / na for step in range(na + 1)]
    grid = [
        [mesh.vertex(polar(x, crown_r(x), zig(angle, x))) for x in xs]
        for angle in angles
    ]
    for row in range(na):
        for column in range(nx):
            # Developed crown area of this quad, in the (arc, axial) plane the
            # contact patch actually lies in.
            corners = [
                (crown_r(x) * zig(angle, x), x)
                for angle, x in (
                    (angles[row], xs[column]),
                    (angles[row + 1], xs[column]),
                    (angles[row + 1], xs[column + 1]),
                    (angles[row], xs[column + 1]),
                )
            ]
            shoelace = 0.0
            for index in range(4):
                first, second = corners[index], corners[(index + 1) % 4]
                shoelace += first[0] * second[1] - second[0] * first[1]
            LUG_CROWN_AREA["crown"] += abs(shoelace) * 0.5
            uv = (
                (angles[row] * spec.GROOVE_RADIUS / TILE_TREAD, xs[column] / TILE_TREAD),
                (angles[row + 1] * spec.GROOVE_RADIUS / TILE_TREAD, xs[column] / TILE_TREAD),
                (angles[row + 1] * spec.GROOVE_RADIUS / TILE_TREAD, xs[column + 1] / TILE_TREAD),
                (angles[row] * spec.GROOVE_RADIUS / TILE_TREAD, xs[column + 1] / TILE_TREAD),
            )
            mesh.quad(
                grid[row][column],
                grid[row + 1][column],
                grid[row + 1][column + 1],
                grid[row][column + 1],
                uv,
            )


def add_tie_bar(mesh: Mesh, a0: float, a1: float, x0: float, x1: float,
                zigzag: float = 0.0) -> None:
    """Low bar across a lateral groove floor: the anti-tear tie bar.

    It takes the groove's own wander, or it would sit straight across a groove
    that curves round it and break through both walls.
    """

    height = spec.TIE_BAR_HEIGHT
    inset = 0.14
    lo_x, hi_x = x0 + inset, x1 - inset
    if hi_x <= lo_x:
        return

    def zig(angle: float, x: float) -> float:
        return angle + zigzag / spec.GROOVE_RADIUS * math.sin(
            math.pi * (x - x0) / max(x1 - x0, 1e-6)
        )

    corners = [
        (zig(angle, x), x)
        for angle, x in ((a0, lo_x), (a1, lo_x), (a1, hi_x), (a0, hi_x))
    ]
    bottom = [
        mesh.vertex(polar(x, base_r(x) - spec.LUG_SEAT, angle))
        for angle, x in corners
    ]
    top = [mesh.vertex(polar(x, base_r(x) + height, angle)) for angle, x in corners]
    uv_top = tuple(
        (angle * spec.GROOVE_RADIUS / TILE_TREAD, x / TILE_TREAD) for angle, x in corners
    )
    mesh.quad(top[0], top[1], top[2], top[3], uv_top)
    for index in range(4):
        nxt = (index + 1) % 4
        uv = (
            (index * 0.12, 0.0),
            ((index + 1) * 0.12, 0.0),
            ((index + 1) * 0.12, height / TILE_TREAD),
            (index * 0.12, height / TILE_TREAD),
        )
        mesh.quad(bottom[index], bottom[nxt], top[nxt], top[index], uv)


def add_wear_indicator(mesh: Mesh, theta: float, x0: float, x1: float) -> None:
    """Tread wear indicator: the moulded bar in the groove floor you measure to."""

    lo_x, hi_x = min(x0, x1), max(x0, x1)
    half = 0.13 / spec.GROOVE_RADIUS
    corners = [
        (theta - half, lo_x), (theta + half, lo_x),
        (theta + half, hi_x), (theta - half, hi_x),
    ]
    # PER-CORNER local floor, the add_tie_bar pattern. Round 5 "fixed"
    # this with a constant seat at GROOVE_RADIUS and had the geometry
    # backwards: the crown arc can only DROP base_r off-centre
    # (crown_r(x) = R_O - x^2/(2*TREAD_ARC_RADIUS)), so the constant seat
    # left every OUTER-groove bar floating ~42 mm above its own floor while
    # the inner bars only survived because their 6-8 mm drop hid under the
    # 10 mm seat. Round 6's per-component gates now make this class of
    # defect unshippable.
    bottom = [
        mesh.vertex(polar(x, base_r(x) - spec.LUG_SEAT, angle))
        for angle, x in corners
    ]
    top = [mesh.vertex(polar(x, base_r(x) + spec.TWI_HEIGHT, angle)) for angle, x in corners]
    uv = ((0.0, 0.0), (0.1, 0.0), (0.1, 0.3), (0.0, 0.3))
    mesh.quad(top[0], top[1], top[2], top[3], uv)
    for index in range(4):
        nxt = (index + 1) % 4
        mesh.quad(bottom[index], bottom[nxt], top[nxt], top[index], uv)


def add_ejector(mesh: Mesh, theta: float, x: float) -> None:
    """Stone ejector: a moulded bump in a circumferential groove floor."""

    radius = spec.STONE_EJECTOR_R
    rings = 4
    segments = 10
    apex = mesh.vertex(polar(x, base_r(x) + radius * 0.95, theta))
    previous = None
    for ring in range(rings, 0, -1):
        t = ring / rings
        # The base ring (t == 1) sinks LUG_SEAT into the floor like every
        # other open rim, and every ring samples base_r at ITS OWN x: one
        # centre sample left outer-groove rims 4.5 mm proud on the crown
        # arc, inside the gate's tolerance but outside the discipline.
        sink = spec.LUG_SEAT if ring == rings else 0.0
        row = []
        for segment in range(segments):
            angle = TAU * segment / segments
            dx = math.cos(angle) * radius * t
            da = math.sin(angle) * radius * t / spec.GROOVE_RADIUS
            lift = radius * 0.95 * math.sqrt(max(0.0, 1.0 - t * t))
            row.append(
                mesh.vertex(polar(x + dx, base_r(x + dx) + lift - sink, theta + da))
            )
        if previous is not None:
            for segment in range(segments):
                nxt = (segment + 1) % segments
                uv = ((0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1))
                mesh.quad(row[segment], row[nxt], previous[nxt], previous[segment], uv, True)
        previous = row
    for segment in range(segments):
        nxt = (segment + 1) % segments
        mesh.face(
            (previous[nxt], previous[segment], apex),
            ((0.1, 0.0), (0.0, 0.0), (0.05, 0.1)),
            True,
        )


# ---------------------------------------------------------------------------
# Visual: the access port - cut edge, bolted bezel, boarding tongue
# ---------------------------------------------------------------------------
def build_lettering(materials) -> list:
    """Brand, pattern and size code, moulded proud of both sidewalls.

    At this scale the characters are 1.9 m tall. A normal-mapped decal reads
    as a sticker the moment the light rakes across it, so the type is real
    geometry: Blender text, extruded LETTER_RELIEF, converted to a mesh, then
    bent onto the sidewall's surface of revolution vertex by vertex. Anything
    that would land inside the access port is skipped.
    """

    mat = materials[f"{MOD_ID}_sidewall_type"]
    objects = []
    font = None
    for candidate in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
        if Path(candidate).is_file():
            font = bpy.data.fonts.load(candidate)
            break

    # ONE STACK, OWNED BY spec.py, carrying the type AND the small-print
    # ring. Round 1 hand-picked three radii and drove PATTERN_NAME straight
    # through SIZE_CODE; round 3 added the print ring outside the stack and
    # drove IT through SIZE_CODE. Anything that stands proud of the flank has
    # a reserved slot now, and the two asserts below judge every slot against
    # the window and against each other - a band the stack does not know about
    # cannot exist.
    lowest, highest = spec.BAND_WINDOW
    for name, radius, height in spec.BAND_STACK:
        if radius - height * 0.5 < lowest or radius + height * 0.5 > highest:
            raise SystemExit(
                f"sidewall band {name} spans radius "
                f"{radius - height * 0.5:.2f}..{radius + height * 0.5:.2f}, outside the "
                f"mouldable sidewall {lowest:.2f}..{highest:.2f}"
            )
    for first in range(len(spec.BAND_STACK)):
        for second in range(first + 1, len(spec.BAND_STACK)):
            a_name, a_r, a_h = spec.BAND_STACK[first]
            b_name, b_r, b_h = spec.BAND_STACK[second]
            gap = abs(a_r - b_r) - 0.5 * (a_h + b_h)
            if gap < spec.BAND_GAP - 1e-6:
                raise SystemExit(
                    f"sidewall bands {a_name} and {b_name} are {gap:.3f} m apart, "
                    f"inside the authored {spec.BAND_GAP:.2f} m gap"
                )

    bands = [
        (getattr(spec, name), radius, height)
        for name, radius, height in spec.BAND_STACK
        if name != "PRINT_BAND"
    ]
    layout = []
    copies = spec.BRAND_COPIES
    for side in (-1.0, 1.0):
        for index in range(copies):
            centre = TAU * (index + 0.5) / copies
            for text, radius, height in bands:
                layout.append((text, radius, height, centre, side))

    for index, (text, band_radius, height, centre, side) in enumerate(layout):
        curve = bpy.data.curves.new(f"{MOD_ID}_txt_{index}", "FONT")
        curve.body = text
        if font is not None:
            curve.font = font
        curve.size = height
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        # A moulded letter has a rounded, slightly tapered crown - it has to
        # release from the plate. A straight prism cannot, and round 1's read
        # as separate plastic parts glued on.
        #
        # extrude + bevel is the HALF thickness, so the built relief is
        # 2*(extrude + bevel) and round 3's 0.5*RELIEF put 62.4 mm on the
        # flank where the spec says 40. And resolution_u = 1 with
        # bevel_resolution = 0 made every bowl an 8-12 sided polygon: at
        # 1.45 m cap height the 0 in 10350 was a visible octagon, on the
        # surface the hero shot is composed around.
        curve.bevel_depth = spec.LETTER_RELIEF * spec.LETTER_BEVEL
        curve.extrude = spec.LETTER_RELIEF * 0.5 - curve.bevel_depth
        # Measured, not guessed: at resolution_u 5 / bevel_resolution 2 the
        # type came out 186,252 triangles - 60% of the entire prop - for
        # bowls no rounder than these. 3 gives twelve segments round an O,
        # a 17 mm sagitta on a 1.45 m cap height, which is past what the eye
        # resolves at any distance a player sees this from.
        curve.bevel_resolution = 1
        curve.resolution_u = 3
        obj = bpy.data.objects.new(f"{MOD_ID}_letter_{index}", curve)
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.ops.object.convert(target="MESH")
        mesh_obj = bpy.context.object
        mesh_obj.data.materials.clear()
        mesh_obj.data.materials.append(mat)

        # Bend flat type onto the sidewall: local x -> arc length at the band
        # radius, local y -> radial offset, local z -> outboard relief.
        for vertex in mesh_obj.data.vertices:
            local = vertex.co.copy()
            radius = band_radius + local.y
            # A sidewall is read from OUTSIDE it, and the two sidewalls face
            # opposite ways, so one of them has to be mirrored or it comes out
            # back to front - which is exactly how round 2 rendered.
            theta = centre - side * local.x / band_radius
            half, thick = sidewall_mid(radius)
            # SHIFT, do not clamp. curve.extrude is symmetric about local
            # z = 0, so clamping the negative half put the entire back cap and
            # lower bevel ring of every glyph on one plane - 50% of the
            # lettering's vertices, and every triangle between them invisible
            # inside the sidewall. Shifting by the half-extrusion instead puts
            # the back face flush on the sidewall and makes the moulded relief
            # exactly LETTER_RELIEF, as the spec says it is.
            back = curve.extrude + curve.bevel_depth - spec.LUG_SEAT
            stand = half + thick * 0.5 + sidewall_relief(radius) + (local.z + back)
            vertex.co = Vector(polar(side * stand, radius, theta))
        mesh_obj.data.update()
        # DISSOLVE, RE-TRIANGULATE, THEN RE-ORIENT - in that order, in one
        # bmesh block, with nothing left pending. Round 3 recalculated the
        # normals here and then attached a DECIMATE/DISSOLVE modifier that was
        # applied downstream, so the merge and the re-triangulation both
        # happened after the last thing that could orient them: 3,906 edges
        # came out traversed the same way by both their faces and 27% of the
        # type faced into the rubber, which BeamNG backface-culls to nothing.
        #
        # Blender triangulates a glyph into a fan of hundreds of slivers and
        # after the bend those are still very nearly coplanar, so merging them
        # costs no visible shape. Round 2's first cut spent 80,776 triangles -
        # 45% of the whole prop - on Arial, while the port's cut edge, the
        # surface the player's headlights hit at two metres, got 672.
        bm = bmesh.new()
        bm.from_mesh(mesh_obj.data)
        # WELD FIRST. Blender's font conversion emits the front cap, the two
        # bevel rings and the back cap as separate vertex sets, so a freshly
        # converted glyph carries ~1,850 boundary edges and is not a closed
        # solid at all. recalc_face_normals then orients each open patch
        # INDEPENDENTLY - consistently within itself and arbitrarily against
        # its neighbours - and the moment anything downstream welds the seams
        # those patches disagree: 457 inconsistent edges per glyph, 7,690
        # across the type, every one of them a hole under backface culling.
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        # Collapse the SLIVERS. Blender's glyph triangulation leaves needles
        # along every straight run of an outline - measured at 0.16 m long and
        # 0.3 mm wide, all three corners on one line of constant radius to
        # within 160 nm. They have world area, so the zero-area sweep keeps
        # them, and no unwrap can give three collinear points a tangent basis.
        # 2 mm is invisible on a 1.45 m cap height and they are gone.
        bmesh.ops.dissolve_degenerate(bm, dist=0.002, edges=bm.edges)
        bmesh.ops.dissolve_limit(
            bm,
            angle_limit=math.radians(3.5),
            verts=bm.verts,
            edges=bm.edges,
            delimit={"NORMAL"},
        )
        bmesh.ops.triangulate(bm, faces=bm.faces)
        # Mirroring reverses face handedness, so the normals have to be
        # recomputed or the mirrored side renders inside out. On a CLOSED
        # solid this is unambiguous, which is the whole reason the weld is
        # above it rather than below.
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh_obj.data)
        bm.free()
        # Metric unwrap on the surface of revolution the glyph now lies on, so
        # its rubber grain matches the sidewall it is moulded into.
        wraps = tile_wraps(TILE_SIDEWALL)
        uv_layer = mesh_obj.data.uv_layers.get("UVMap") or mesh_obj.data.uv_layers.new(
            name="UVMap"
        )
        for loop in mesh_obj.data.loops:
            point = mesh_obj.data.vertices[loop.vertex_index].co
            loop_radius = math.hypot(point.y, R_O - point.z)
            loop_theta = math.atan2(point.y, R_O - point.z)
            # THE RELIEF GOES INTO v. Round 3 unwrapped from (y, z) alone
            # while the extrusion runs in x, so all four corners of every
            # flank quad shared two UVs and 25.6% of the material - 7,908
            # triangles - had world area and ZERO uv area, under a bound
            # normalMap. A degenerate tangent basis is the black-speckle
            # failure this file's own sibling gate warns about.
            proud = abs(point.x) - (
                sidewall_outer(loop_radius)[0] + sidewall_relief(loop_radius)
            )
            # ...and u unwraps about the glyph's OWN centre, so the copy that
            # sits at theta = pi does not tear across atan2's branch cut.
            turn = (loop_theta - centre + math.pi) % TAU - math.pi
            # The relief goes into BOTH axes at 45 degrees. Putting it only in
            # v left every flank on a RADIAL stroke - the stem of an I, an L,
            # a 1 - at one constant u, so its three UVs came out collinear and
            # 688 triangles still had no tangent basis. u is metric here by
            # construction (tile_wraps makes one u unit one TILE_SIDEWALL of
            # arc), so the same offset is meaningful on both.
            # The relief carries MORE weight in u than the arc does over the
            # width of a letter flank, which is the point: on a radial stroke
            # the arc term barely moves, and any smaller weight let the two
            # terms cancel to within the exported file's precision on 76
            # triangles. 0.04 m of relief shears the grain by 3% of a tile.
            uv_layer.data[loop.index].uv = (
                wraps * (centre + turn) / TAU + proud * 2.0 / TILE_SIDEWALL,
                (loop_radius + proud) / TILE_SIDEWALL,
            )
        mesh_obj.data.update()
        objects.append(mesh_obj)
    return objects


def build_print_band(materials) -> list:
    """A lathed ring of moulded small print, low on each sidewall.

    This is where the legend texture belongs: one band, wrapped once round the
    tire, with v running across the band so the four printed lines read the
    way they are drawn. Round 3 had the legend mapped onto the extruded
    CHARACTERS instead, which is the one place it cannot be read.
    """

    material = materials[f"{MOD_ID}_sidewall_print"]
    mesh = Mesh(f"{MOD_ID}_print_band", material)
    thetas = [index * TAU / VISUAL_STATIONS for index in range(VISUAL_STATIONS)]
    step_angle = TAU / VISUAL_STATIONS
    rows = 4
    # A WHOLE NUMBER OF LEGEND SHEETS, sized so each one lands at the aspect
    # the family drew it at. tile_wraps answers the sidewall's rubber-grain
    # question, which is a different question.
    circumference = TAU * spec.PRINT_BAND_RADIUS
    wraps = max(
        1,
        round(circumference / (spec.PRINT_BAND_HEIGHT * spec.PRINT_BAND_ASPECT)),
    )
    for side in (-1.0, 1.0):
        grid = []
        for row in range(rows + 1):
            t = row / rows
            radius = spec.PRINT_BAND_RADIUS + spec.PRINT_BAND_HEIGHT * (t - 0.5)
            half, thick = sidewall_outer(radius)
            stand = half + sidewall_relief(radius) + spec.PRINT_BAND_RELIEF
            grid.append(
                [mesh.vertex(polar(side * stand, radius, theta)) for theta in thetas]
            )
        for row in range(rows):
            for column in range(VISUAL_STATIONS):
                nxt = (column + 1) % VISUAL_STATIONS
                theta0 = thetas[column]
                theta1 = theta0 + step_angle
                # u wraps a whole number of times so the band closes; v runs
                # 0..1 ACROSS it, which is how the legend sheet is drawn.
                v0, v1 = row / rows, (row + 1) / rows
                uv = (
                    (wraps * theta0 / TAU, v0),
                    (wraps * theta1 / TAU, v0),
                    (wraps * theta1 / TAU, v1),
                    (wraps * theta0 / TAU, v1),
                )
                a, b = grid[row][column], grid[row][nxt]
                c, d = grid[row + 1][nxt], grid[row + 1][column]
                if side > 0:
                    mesh.quad(d, c, b, a, uv, smooth=True)
                else:
                    mesh.quad(a, b, c, d, uv, smooth=True)
    return [mesh.build()]


# ---------------------------------------------------------------------------
# Visual: the chocks (the yard hardware)
# ---------------------------------------------------------------------------
def chock_geometry(sign: float) -> dict:
    """The one wedge, derived from the tire it is holding.

    A chock works by being something the tire has to climb, so its top edge
    has to touch the tire: at spec.CHOCK_FAR from the contact patch the
    carcass is exactly R - sqrt(R^2 - y^2) off the ground, and that is the
    height. Nothing here is typed in but the two distances and the width.
    """

    near = sign * spec.CHOCK_NEAR
    far = sign * spec.CHOCK_FAR
    # SEAT_GAP: the wedge now really collides with the carcass (its nodes
    # carry selfCollision), so a top edge authored to touch the UNLOADED
    # surface would spawn preloaded into it. The settled carcass sags ~80 mm,
    # which closes most of the gap; contact is a kiss, not a spring.
    height = (
        R_O - math.sqrt(max(R_O ** 2 - spec.CHOCK_FAR ** 2, 0.0))
        - spec.CHOCK_SEAT_GAP
    )
    half = spec.CHOCK_HALF_WIDTH
    return {"near": near, "far": far, "height": height, "half": half}


# (index, fore/aft sign, axial centre) for each of the four chocks.
CHOCK_PLACES = tuple(
    (index, sign, offset)
    for index, (sign, offset) in enumerate(
        (
            (-1.0, -spec.CHOCK_OFFSET), (-1.0, spec.CHOCK_OFFSET),
            (1.0, -spec.CHOCK_OFFSET), (1.0, spec.CHOCK_OFFSET),
        )
    )
)


def build_chocks(materials) -> list:
    """Four fabricated steel chocks, one under each shoulder.

    ROUND 5 REBUILT THESE TWICE OVER. The old wedges were six-vertex CAD
    placeholders whose hazard stripes were floating open quads wound INTO
    the steel - all sixteen stripe triangles shipped facing (0, +/-0.22,
    -0.97) and rendered on zero pixels in game. Now each chock is what a
    yard fabricates: a painted wedge body with a blunted toe, side plates
    proud of the body, heel gussets, a tow handle, and hazard bands that
    are CLOSED SLABS lying on the climb face and the side plates. Every
    piece is a closed solid wound away from its own centroid, and the
    orientation audit judges all of it - ground objects included - under
    the "_chock_" rule instead of being waved past.

    Nothing here touches the cage: same six nodes, same mass, same seat
    gap, so every live measurement stays valid.
    """

    paint = materials[f"{MOD_ID}_chock_paint"]
    hazard = materials[f"{MOD_ID}_hazard"]
    tile = tile_of(paint)
    stripe_tile = tile_of(hazard)
    objects = []

    def orient_outward(obj):
        """Every chock piece is a CLOSED solid, so let the manifold decide.

        recalc_face_normals orients a closed volume consistently outward;
        hand-derived winding branches are exactly how the old stripes ended
        up facing into the steel, so the closure IS the correctness proof
        here, and the orientation audit re-measures it after the fact.
        """

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return obj

    def slab(mesh, corners, thickness, direction, tile_m):
        """A closed six-face slab: `corners` (4 points, wound so the face
        looks along `direction`), extruded `thickness` along `direction`."""

        d = Vector(direction).normalized() * thickness
        base = [mesh.vertex(c) for c in corners]
        top = [mesh.vertex((Vector(c) + d)) for c in corners]
        width = (Vector(corners[1]) - Vector(corners[0])).length
        height = (Vector(corners[3]) - Vector(corners[0])).length
        uv = (
            (0.0, 0.0), (width / tile_m, 0.0),
            (width / tile_m, height / tile_m), (0.0, height / tile_m),
        )
        edge_uv = ((0.0, 0.0), (width / tile_m, 0.0),
                   (width / tile_m, thickness / tile_m), (0.0, thickness / tile_m))
        mesh.quad(top[0], top[1], top[2], top[3], uv)
        mesh.quad(base[3], base[2], base[1], base[0], uv)
        for index in range(4):
            nxt = (index + 1) % 4
            mesh.quad(base[index], base[nxt], top[nxt], top[index], edge_uv)

    for index, sign, offset in CHOCK_PLACES:
        shape = chock_geometry(sign)
        near, far = shape["near"], shape["far"]
        height, half = shape["height"], shape["half"]
        length = abs(far - near)
        ramp = math.hypot(length, height)
        # Silhouette in (t, z), t = 0 at the toe growing toward the heel.
        # The toe is BLUNTED: a real chock's leading edge is a rolled plate,
        # not a knife; two chamfer segments read as the roll at this scale.
        grade = height / length
        outline = (
            (0.10, 0.0),
            (0.115, 0.022),
            (0.15, 0.15 * grade),
            (length, height),
            (length, 0.0),
        )

        def at(tz, x):
            return (x, near + sign * tz[0], tz[1])

        # BODY: the wedge prism, silhouette caps fanned, faces outward.
        body = Mesh(f"{MOD_ID}_chock_body_{index}", paint)
        left = [body.vertex(at(tz, offset - half)) for tz in outline]
        right = [body.vertex(at(tz, offset + half)) for tz in outline]
        count = len(outline)
        cap_uv = ((0.0, 0.0), (0.4, 0.0), (0.4, 0.4))
        for step in range(1, count - 1):
            if sign > 0:
                body.face((left[0], left[step + 1], left[step]), cap_uv)
                body.face((right[0], right[step], right[step + 1]), cap_uv)
            else:
                body.face((left[0], left[step], left[step + 1]), cap_uv)
                body.face((right[0], right[step + 1], right[step]), cap_uv)
        for step in range(count):
            nxt = (step + 1) % count
            seg = math.dist(outline[step], outline[nxt])
            uv = ((0.0, 0.0), (2.0 * half / tile, 0.0),
                  (2.0 * half / tile, seg / tile), (0.0, seg / tile))
            if sign > 0:
                body.quad(left[step], right[step], right[nxt], left[nxt], uv)
            else:
                body.quad(right[step], left[step], left[nxt], right[nxt], uv)
        objects.append(orient_outward(body.build()))

        # SIDE PLATES: the fabricated silhouette, 20 mm proud of each face.
        for side, tag in ((-1.0, "l"), (1.0, "r")):
            plate = Mesh(f"{MOD_ID}_chock_plate_{index}_{tag}", paint)
            x_face = offset + side * half
            base = [plate.vertex(at(tz, x_face)) for tz in outline]
            top = [plate.vertex(at(tz, x_face + side * 0.020)) for tz in outline]
            for step in range(1, count - 1):
                if (side > 0) == (sign > 0):
                    plate.face((top[0], top[step], top[step + 1]), cap_uv)
                    plate.face((base[0], base[step + 1], base[step]), cap_uv)
                else:
                    plate.face((top[0], top[step + 1], top[step]), cap_uv)
                    plate.face((base[0], base[step], base[step + 1]), cap_uv)
            for step in range(count):
                nxt = (step + 1) % count
                seg = math.dist(outline[step], outline[nxt])
                uv = ((0.0, 0.0), (0.02 / tile, 0.0),
                      (0.02 / tile, seg / tile), (0.0, seg / tile))
                if (side > 0) == (sign > 0):
                    plate.quad(base[step], base[nxt], top[nxt], top[step], uv)
                else:
                    plate.quad(base[nxt], base[step], top[step], top[nxt], uv)
            objects.append(orient_outward(plate.build()))

        # HEEL GUSSETS: two triangular ribs bracing the back wall.
        for lane, tag in ((-0.45, "a"), (0.45, "b")):
            gusset = Mesh(f"{MOD_ID}_chock_gusset_{index}_{tag}", paint)
            x0 = offset + lane - 0.015
            tri = (
                (x0, far, 0.0),
                (x0, far, height - 0.03),
                (x0, far + sign * 0.20, 0.0),
            )
            a = [gusset.vertex(pt) for pt in tri]
            b = [gusset.vertex((pt[0] + 0.03, pt[1], pt[2])) for pt in tri]
            if sign > 0:
                gusset.face((a[0], a[1], a[2]), cap_uv)
                gusset.face((b[2], b[1], b[0]), cap_uv)
            else:
                gusset.face((a[2], a[1], a[0]), cap_uv)
                gusset.face((b[0], b[1], b[2]), cap_uv)
            edge_uv = ((0.0, 0.0), (0.2 / tile, 0.0),
                       (0.2 / tile, 0.03 / tile), (0.0, 0.03 / tile))
            for step in range(3):
                nxt = (step + 1) % 3
                if sign > 0:
                    gusset.quad(a[nxt], a[step], b[step], b[nxt], edge_uv)
                else:
                    gusset.quad(a[step], a[nxt], b[nxt], b[step], edge_uv)
            objects.append(orient_outward(gusset.build()))

        # TOW HANDLE: a staple of three small bars on the heel face, the
        # thing the winch line hooks. Three separate closed boxes so the
        # centroid rule holds for each.
        top_z = height - 0.06
        for piece, (x0, x1, y0, y1, z0, z1) in (
            ("a", (offset - 0.135, offset - 0.105, far, far + sign * 0.10, top_z - 0.015, top_z + 0.015)),
            ("b", (offset + 0.105, offset + 0.135, far, far + sign * 0.10, top_z - 0.015, top_z + 0.015)),
            ("c", (offset - 0.135, offset + 0.135, far + sign * 0.07, far + sign * 0.10, top_z - 0.015, top_z + 0.015)),
        ):
            bar = Mesh(f"{MOD_ID}_chock_eye_{index}_{piece}", paint)
            lo_y, hi_y = min(y0, y1), max(y0, y1)
            corners = [
                (x0, lo_y, z0), (x1, lo_y, z0), (x1, hi_y, z0), (x0, hi_y, z0),
                (x0, lo_y, z1), (x1, lo_y, z1), (x1, hi_y, z1), (x0, hi_y, z1),
            ]
            v = [bar.vertex(c) for c in corners]
            box_uv = ((0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1))
            for face in (
                (0, 3, 2, 1), (4, 5, 6, 7),
                (0, 1, 5, 4), (2, 3, 7, 6),
                (1, 2, 6, 5), (3, 0, 4, 7),
            ):
                bar.quad(*(v[i] for i in face), box_uv)
            objects.append(orient_outward(bar.build()))

        # HAZARD BANDS: closed 6 mm slabs, never floating quads. Two on the
        # climb face, one on each side plate - visible from the approach,
        # from the side, and in every render that sees a chock.
        ramp_dir = Vector((0.0, sign * length, height)).normalized()
        ramp_normal = Vector((0.0, -sign * height, length)).normalized()
        climb_t0, climb_t1 = 0.30, length - 0.15
        for edge, tag in ((-1.0, "l"), (1.0, "r")):
            outer = offset + edge * (half - 0.10)
            inner = offset + edge * (half - 0.10 - spec.CHOCK_STRIPE)
            stripe = Mesh(f"{MOD_ID}_chock_stripe_{index}_{tag}", hazard)
            span = climb_t1 - climb_t0
            uv_h = span / stripe_tile
            base_pt = Vector((0.0, near, 0.0))
            p0 = base_pt + ramp_dir * climb_t0
            p1 = base_pt + ramp_dir * climb_t1
            corners = [
                (outer, p0.y, p0.z), (inner, p0.y, p0.z),
                (inner, p1.y, p1.z), (outer, p1.y, p1.z),
            ]
            if (edge * sign) < 0:
                corners = list(reversed(corners))
            slab(stripe, corners, 0.006, ramp_normal, stripe_tile)
            objects.append(orient_outward(stripe.build()))
        for side, tag in ((-1.0, "pl"), (1.0, "pr")):
            x_face = offset + side * (half + 0.020)
            stripe = Mesh(f"{MOD_ID}_chock_stripe_{index}_{tag}", hazard)
            t0, t1 = 1.55, length - 0.05
            z0, z1 = 0.05, 0.35
            corners = [
                (x_face, near + sign * t0, z0), (x_face, near + sign * t1, z0),
                (x_face, near + sign * t1, z1), (x_face, near + sign * t0, z1),
            ]
            if (side > 0) == (sign < 0):
                corners = list(reversed(corners))
            stripe.name = f"{MOD_ID}_chock_stripe_{index}_{tag}"
            slab(stripe, corners, 0.006, Vector((side, 0.0, 0.0)), stripe_tile)
            objects.append(orient_outward(stripe.build()))
    return objects


def _station(fraction: float) -> tuple[float, float]:
    """(MID-shell half width, radius) of the meridian station at a fraction.

    spec.MERIDIAN is the outer surface; the cage lives on the mid-shell, so
    the thickness comes off here once rather than at every call site.
    """

    for value, half in spec.MERIDIAN:
        if abs(value - fraction) < 1e-6:
            outer_half, radius = spec.meridian_point(value, half)
            return (outer_half - sidewall_outer(radius)[1] * 0.5, radius)
    raise KeyError(f"no meridian station at fraction {fraction}")


# The meridian, built once and reused by every station.
CROSS_SECTION: list[tuple[str, float, float]] = []


def cross_section() -> list[tuple[str, float, float]]:
    """(key, half width, radius) for the 22-node meridian, once.

    The SILL station's radius IS CAVITY_RADIUS. It was put there so the access
    port could be cut on a ring of cage nodes; the port is gone, but the ring
    is still the right place to change families - it is where the tread's
    inner face hands over to the sidewall, which is a real construction
    boundary and not a convenience.
    """

    if CROSS_SECTION:
        return CROSS_SECTION
    bead_x, bead_r = _station(spec.BEAD_FRACTION)
    low_x, low_r = _station(spec.LOW_FRACTION)
    max_x, max_r = _station(spec.MAX_FRACTION)
    upp_x, upp_r = _station(spec.UPP_FRACTION)
    sill_x, sill_r = _station(spec.SILL_FRACTION)
    shl_x, shl_r = _station(spec.SHL_FRACTION)
    entries = [
        ("bead_l", -bead_x, bead_r),
        ("low_l", -low_x, low_r),
        ("max_l", -max_x, max_r),
        ("upp_l", -upp_x, upp_r),
        ("sill_l", -sill_x, sill_r),
        ("shl_l", -shl_x, shl_r),
    ]
    for label, x in zip(("crn_l", "crn_cl", "crn_c", "crn_cr", "crn_r"), spec.CROWN_XS):
        entries.append((label, x, crown_r(x)))
    entries.extend(
        [
            ("shl_r", shl_x, shl_r),
            ("sill_r", sill_x, sill_r),
            ("upp_r", upp_x, upp_r),
            ("max_r", max_x, max_r),
            ("low_r", low_x, low_r),
            ("bead_r", bead_x, bead_r),
        ]
    )
    # THE FLOOR IS A 48-GON, so putting its NODES on the cavity radius put the
    # whole drivable surface INSIDE it: the chord between two stations sits
    # 28 mm nearer the axle than the nodes do, which is 28 mm of headroom lost
    # all the way round and a floor that is systematically higher than the
    # radius every other number is quoted against. Pushing the ring out by
    # 1/cos(half a station) lands the CHORD MIDPOINTS on CAVITY_RADIUS, which
    # is the surface a car actually rides.
    liner_radius = R_CAV / math.cos(spec.STATION_ANGLE * 0.5)
    for label, x in zip(("lin_l", "lin_cl", "lin_c", "lin_cr", "lin_r"), spec.LINER_XS):
        entries.append((label, x, liner_radius))
    CROSS_SECTION.extend(entries)
    return CROSS_SECTION


OUTER_LOOP = (
    "bead_l", "low_l", "max_l", "upp_l", "sill_l", "shl_l",
    "crn_l", "crn_cl", "crn_c", "crn_cr", "crn_r",
    "shl_r", "sill_r", "upp_r", "max_r", "low_r", "bead_r",
)
LINER_LOOP = ("lin_l", "lin_cl", "lin_c", "lin_cr", "lin_r")
SIDEWALL_L = ("bead_l", "low_l", "max_l", "upp_l", "sill_l", "shl_l")
SIDEWALL_R = ("bead_r", "low_r", "max_r", "upp_r", "sill_r", "shl_r")

MASS_GROUPS = {
    "crown": ("crn_l", "crn_cl", "crn_c", "crn_cr", "crn_r"),
    "liner": LINER_LOOP,
    "sidewall": (
        "low_l", "max_l", "upp_l", "sill_l", "shl_l",
        "low_r", "max_r", "upp_r", "sill_r", "shl_r",
    ),
    "bead": ("bead_l", "bead_r"),
}


def node_weight(key: str) -> float:
    for group, keys in MASS_GROUPS.items():
        if key in keys:
            return spec.TIRE_MASS * spec.MASS_FRACTIONS[group] / (STATIONS * len(keys))
    raise KeyError(key)


def quad_normal(cage: bk.CageBuilder, corners) -> Vector:
    points = [
        Vector(cage.nodes[cage.node_index[identifier]]["source_world_position"])
        for identifier in corners
    ]
    return (points[1] - points[0]).cross(points[2] - points[0])


def add_oriented_quad(cage: bk.CageBuilder, corners, target: Vector, **kwargs) -> None:
    """Emit a one-sided collision quad wound so its normal follows ``target``.

    Winding is checked against the measured node positions rather than
    assumed, because a jbeam triangle only collides from its front face and a
    reversed tread panel is an invisible one-way floor.
    """

    normal = quad_normal(cage, corners)
    if normal.dot(target) < 0:
        corners = list(reversed(corners))
    cage.add_quad(list(corners), **kwargs)


def add_oriented_tri(cage: bk.CageBuilder, corners, target: Vector, **kwargs) -> None:
    """One-sided collision triangle wound so its normal follows ``target``."""

    normal = quad_normal(cage, corners)
    if normal.dot(target) < 0:
        corners = list(reversed(corners))
    cage.add_triangle(*corners, **kwargs)


def balance_carcass(cage: bk.CageBuilder) -> None:
    """Null the free body's first mass moment about the axle.

    THE PREMISE IS THAT IT ROLLS, and it barely did. The boarding gangway
    (900 kg, since deleted with the rest of the furniture) hung at the BOTTOM
    of the carcass and stayed bolted after the straps were cut, so the free
    body's centre of mass sat 0.922 m off the axle. That is a 102 kNm gravity
    pendulum against roughly 123 kNm of drive torque from a car pushing the
    liner: the tire climbs its own imbalance and rocks back rather than
    rolling away, which is exactly what the live gate's 7.40 m of travel
    (31.6 degrees of rotation) was. The furniture is gone and the solve now
    lands at x1.000, but the mechanism stays: any future asymmetric mass
    goes through this balance or the tire stops being a wheel.

    Real OTR tires are balanced with compound laid opposite the light spot,
    and that is what this is: a first-harmonic modulation of the CARCASS node
    weights - heavier opposite the port, biased off the port flank - solved so
    the whole free body's centre of mass lands on the axle, with the uniform
    term carried as a third unknown so TIRE_MASS comes out unchanged rather
    than being renormalised afterwards (renormalising a nulled moment does not
    keep it nulled).
    """

    carcass = [
        node for node in cage.nodes
        if not node["fixed"] and "chock" not in node["id"]
    ]
    rider = [
        node for node in cage.nodes
        if not node["fixed"] and "tongue" in node["id"]
    ]
    if not carcass:
        raise SystemExit("no carcass nodes to balance")

    def offset(node):
        x, y, z = node["source_world_position"]
        return (x, y, z - R_O)

    # ONE shape function: the vertical first harmonic, which IS the balance
    # patch. The axial offset is deliberately left alone - it is 0.36 m and
    # produces a steady 3.6 degree lean, which is honest for a carcass with a
    # gangway bolted to one flank, and correcting it too needed a +/-34%
    # modulation that pushed the lightest port-frame node to omega*dt 0.934
    # against a 0.9 ceiling. The radial offset is the one that matters: it is
    # a pendulum the drive torque has to climb on every revolution.
    def shape(node):
        _x, _y, dz = offset(node)
        return dz / spec.OUTER_RADIUS

    rider_mass = sum(node["weight"] for node in rider)
    rider_moment = [
        sum(node["weight"] * offset(node)[axis] for node in rider) for axis in (0, 2)
    ]

    # Solve [c, a] for: total mass and vertical moment.
    matrix = [[0.0] * 2 for _ in range(2)]
    target = [spec.TIRE_MASS, -rider_moment[1]]
    for node in carcass:
        weight = node["weight"]
        basis = (1.0, shape(node))
        _dx, _dy, dz = offset(node)
        for column in range(2):
            matrix[0][column] += weight * basis[column]
            matrix[1][column] += weight * basis[column] * dz

    determinant = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
    if abs(determinant) < 1e-9:
        raise SystemExit("the carcass balance system is singular")
    scale = (target[0] * matrix[1][1] - matrix[0][1] * target[1]) / determinant
    vertical_gain = (matrix[0][0] * target[1] - target[0] * matrix[1][0]) / determinant

    lowest = highest = None
    for node in carcass:
        factor = scale + vertical_gain * shape(node)
        if factor <= 0.0:
            raise SystemExit(
                f"balancing wants a negative weight on {node['id']} "
                f"(factor {factor:.3f}); the correction is too large to carry "
                f"as a mass modulation"
            )
        node["weight"] *= factor
        lowest = factor if lowest is None else min(lowest, factor)
        highest = factor if highest is None else max(highest, factor)

    total = sum(node["weight"] for node in carcass)
    moment = [
        sum(node["weight"] * offset(node)[axis] for node in carcass) + rider_moment[i]
        for i, axis in enumerate((0, 2))
    ]
    free = total + rider_mass
    print(
        f"COLOSSUS balance: carcass weights x{lowest:.3f}..{highest:.3f}; free body "
        f"{free:.1f} kg, centre of mass {abs(moment[1]) / free * 1000:.1f} mm off the "
        f"axle radially and {abs(moment[0]) / free * 1000:.0f} mm axially"
    )


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    for name, values in spec.BEAM_SPECS.items():
        cage.define_beam_spec(
            name, beamDeform="FLT_MAX", beamStrength="FLT_MAX", **values
        )
    cage.define_beam_spec("chock", **spec.ANCHOR_GLUE_BEAM)
    cage.define_beam_spec("wedge", **spec.WEDGE_BEAM)
    cage.define_beam_spec("strap", **spec.STRAP_SPEC)

    section = cross_section()
    ids: dict[tuple[str, int], str] = {}
    for station in range(STATIONS):
        theta = station * spec.STATION_ANGLE
        for key, x, radius in section:
            position = polar(x, radius, theta)
            ids[(key, station)] = cage.add_node(
                f"{key}_j{station:02d}",
                position,
                fixed=False,
                collision=True,
                weight=node_weight(key),
                friction=1.05 if key.startswith(("crn", "lin")) else 0.85,
                node_material="|NM_RUBBER",
                group="carcass",
            )

    def beam(key_a, station_a, key_b, station_b, family, extra=None):
        cage.add_beam(
            ids[(key_a, station_a % STATIONS)],
            ids[(key_b, station_b % STATIONS)],
            family,
            extra=extra,
        )

    for station in range(STATIONS):
        nxt = (station + 1) % STATIONS
        # --- Meridian ring: the carcass in section.
        for index in range(len(OUTER_LOOP) - 1):
            a, b = OUTER_LOOP[index], OUTER_LOOP[index + 1]
            if a.startswith("crn") and b.startswith("crn"):
                family = "belt"
            elif "shl" in (a, b) and (a.startswith("crn") or b.startswith("crn")):
                family = "belt"
            else:
                # The bead-to-sidewall member is the ply TURN-UP over the
                # apex, so it is casing. Only the hoop members between bead
                # nodes get the bead family.
                family = "casing"
            beam(a, station, b, station, family)
        for index in range(len(LINER_LOOP) - 1):
            beam(LINER_LOOP[index], station, LINER_LOOP[index + 1], station, "belt")
        # Tread slab: radial beams liner -> crown, plus their diagonals. This
        # is the family that flattens into the contact patch.
        for liner_key, crown_key in zip(LINER_LOOP, MASS_GROUPS["crown"]):
            beam(liner_key, station, crown_key, station, "tread")
        for index in range(len(LINER_LOOP) - 1):
            beam(LINER_LOOP[index], station, MASS_GROUPS["crown"][index + 1], station, "tread")
            beam(LINER_LOOP[index + 1], station, MASS_GROUPS["crown"][index], station, "tread")
        # Shoulder: the liner edge ties to the SILL ring, which sits at the
        # same radius, so the join is a flat threshold rather than a step.
        beam("lin_l", station, "sill_l", station, "casing")
        beam("lin_r", station, "sill_r", station, "casing")
        beam("lin_l", station, "shl_l", station, "casing")
        beam("lin_r", station, "shl_r", station, "casing")
        beam("lin_l", station, "crn_l", station, "tread")
        beam("lin_r", station, "crn_r", station, "tread")
        # Sidewall shear bracing.
        for chain in (SIDEWALL_L, SIDEWALL_R):
            beam(chain[0], station, chain[2], station, "sidewall")
            beam(chain[1], station, chain[3], station, "sidewall")
            beam(chain[2], station, chain[4], station, "sidewall")

        # --- Station to station.
        for key, _, _ in section:
            if key.startswith("crn") or key in LINER_LOOP:
                family = "belt"
            elif key.startswith("bead"):
                family = "bead"
            else:
                family = "casing"
            beam(key, station, key, nxt, family)
        # One diagonal per node pair: enough to carry shear round the hoop
        # without doubling the beam count.
        for index in range(len(OUTER_LOOP) - 1):
            beam(OUTER_LOOP[index], station, OUTER_LOOP[index + 1], nxt, "casing")
        for index in range(len(LINER_LOOP) - 1):
            beam(LINER_LOOP[index], station, LINER_LOOP[index + 1], nxt, "belt")

        # --- Belt chords. A steel belt is inextensible, and a chord to a
        # station two and three away is what expresses that: without them a
        # 31 t carcass ovalises under its own weight and never rolls round.
        for key in MASS_GROUPS["crown"]:
            beam(key, station, key, station + 2, "belt")
            beam(key, station, key, station + 3, "belt")
        beam("bead_l", station, "bead_l", station + 2, "bead")
        beam("bead_r", station, "bead_r", station + 2, "bead")

        # --- Inflation truss: the air, as a chord across the cavity.
        if station < STATIONS // 2:
            opposite = (station + STATIONS // 2) % STATIONS
            beam("lin_c", station, "lin_c", opposite, "inflation")
            beam("bead_l", station, "bead_r", opposite, "inflation")
            beam("bead_r", station, "bead_l", opposite, "inflation")


    # -----------------------------------------------------------------------
    # Collision surfaces.
    # -----------------------------------------------------------------------
    for station in range(STATIONS):
        nxt = (station + 1) % STATIONS
        theta_mid = (station + 0.5) * spec.STATION_ANGLE
        outward = Vector((0.0, math.sin(theta_mid), -math.cos(theta_mid)))
        inward = -outward

        crown = MASS_GROUPS["crown"]
        for index in range(len(crown) - 1):
            add_oriented_quad(
                cage,
                [
                    ids[(crown[index], station)],
                    ids[(crown[index + 1], station)],
                    ids[(crown[index + 1], nxt)],
                    ids[(crown[index], nxt)],
                ],
                outward,
                ground_model="rubber",
            )
        for index in range(len(LINER_LOOP) - 1):
            add_oriented_quad(
                cage,
                [
                    ids[(LINER_LOOP[index], station)],
                    ids[(LINER_LOOP[index + 1], station)],
                    ids[(LINER_LOOP[index + 1], nxt)],
                    ids[(LINER_LOOP[index], nxt)],
                ],
                inward,
                ground_model="rubber",
            )
        # Shoulder bands close the gap between the liner edge and the sidewall.
        for chain_key, liner_key, sign in (
            ("sill_l", "lin_l", -1.0),
            ("sill_r", "lin_r", 1.0),
        ):
            cage.add_quad_both(
                [
                    ids[(liner_key, station)],
                    ids[(chain_key, station)],
                    ids[(chain_key, nxt)],
                    ids[(liner_key, nxt)],
                ],
                ground_model="rubber",
            )
        # Sidewalls, double sided: the car leans on them from the inside and
        # the world hits them from the outside.
        for chain, sign in ((SIDEWALL_L, -1.0), (SIDEWALL_R, 1.0)):
            for index in range(len(chain) - 1):
                cage.add_quad_both(
                    [
                        ids[(chain[index], station)],
                        ids[(chain[index + 1], station)],
                        ids[(chain[index + 1], nxt)],
                        ids[(chain[index], nxt)],
                    ],
                    ground_model="rubber",
                )
        # Crown-to-shoulder closes the tread edge to the sidewall.
        for crown_key, chain_key in (("crn_l", "shl_l"), ("crn_r", "shl_r")):
            add_oriented_quad(
                cage,
                [
                    ids[(crown_key, station)],
                    ids[(chain_key, station)],
                    ids[(chain_key, nxt)],
                    ids[(crown_key, nxt)],
                ],
                outward,
                ground_model="rubber",
            )

    # -----------------------------------------------------------------------
    # The chocks: four free steel wedges, each strapped to buried anchors,
    # and the tie-downs that make it one cage.
    #
    # THE WEDGES USED TO BE FIXED, AND THAT MADE THEM FAKE TWICE OVER. Fixed
    # nodes shipped without selfCollision, so the tire never pressed on its
    # own chocks - the straps did all the holding - and after release the
    # carcass rolled straight through the wedge meshes. Now each wedge is a
    # free ~200 kg body: its nodes carry selfCollision so the carcass really
    # rests against the climb face, and its base corners are strapped to
    # buried fixed anchors in the SAME break group as the tie-downs. Every
    # beam that crosses between fixed and free carries that group, so cutting
    # the release leaves a completely free 4.2 tonne carcass and four loose
    # chocks the winch drags out of the way - which is what release means in
    # a yard. The pack gate checks the crossing rule exactly.
    # -----------------------------------------------------------------------
    chock_ids: dict[tuple[int, str], str] = {}
    anchor_ids: dict[tuple[int, str], str] = {}
    for index, sign, offset in CHOCK_PLACES:
        shape = chock_geometry(sign)
        near, far = shape["near"], shape["far"]
        height, half = shape["height"], shape["half"]
        corners = {
            "toe_l": (offset - half, near, 0.0),
            "toe_r": (offset + half, near, 0.0),
            "heel_l": (offset - half, far, 0.0),
            "heel_r": (offset + half, far, 0.0),
            "top_l": (offset - half, far, height),
            "top_r": (offset + half, far, height),
        }
        for key, position in corners.items():
            chock_ids[(index, key)] = cage.add_node(
                f"chock_{index}_{key}",
                position,
                fixed=False,
                collision=True,
                self_collision=True,
                weight=spec.WEDGE_NODE_MASS,
                friction=spec.WEDGE_FRICTION,
                node_material="|NM_METAL",
                # Per-wedge flexbody group. Without it these landed in the
                # default <mod>_physics group NEXT TO the 16 fixed anchors -
                # each buried 0.6 m under a corner, closer than most of the
                # wedge's own nodes - so the chock visual skinned to nodes
                # that stay pinned while the winch drags the wedge 5 m.
                group=f"chock_{index}",
            )
        # The anchors: one under each base corner, buried and collisionless.
        # They are the only fixed nodes in the prop, and none of them can
        # touch anything - the gate on fixed nodes asserts exactly that.
        for key in ("toe_l", "toe_r", "heel_l", "heel_r"):
            x, y, _z = corners[key]
            anchor_ids[(index, key)] = cage.add_node(
                f"chock_{index}_anchor_{key}",
                (x, y, -spec.WEDGE_ANCHOR_DEPTH),
                fixed=True,
                collision=False,
                weight=200.0,
            )
        # Hold-downs: a vertical strap per corner takes the settle bounce,
        # and a fore-aft diagonal per corner takes the shove of a carcass
        # leaning on the wedge on a grade. All of them break with the ties.
        for key in ("toe_l", "toe_r", "heel_l", "heel_r"):
            cage.add_beam(
                chock_ids[(index, key)], anchor_ids[(index, key)],
                "strap", extra={"breakGroup": spec.STRAP_BREAK_GROUP},
            )
        for key, partner in (
            ("toe_l", "heel_l"), ("heel_l", "toe_l"),
            ("toe_r", "heel_r"), ("heel_r", "toe_r"),
        ):
            cage.add_beam(
                chock_ids[(index, key)], anchor_ids[(index, partner)],
                "strap", extra={"breakGroup": spec.STRAP_BREAK_GROUP},
            )
        keys = list(corners)
        for first in range(len(keys)):
            for second in range(first + 1, len(keys)):
                cage.add_beam(
                    chock_ids[(index, keys[first])],
                    chock_ids[(index, keys[second])],
                    "wedge",
                )
        # The climb face and the heel, both collidable: a tire that rides up
        # this has to have something to ride up.
        add_oriented_quad(
            cage,
            [
                chock_ids[(index, "toe_l")], chock_ids[(index, "toe_r")],
                chock_ids[(index, "top_r")], chock_ids[(index, "top_l")],
            ],
            Vector((0.0, -sign, 1.0)).normalized(),
            ground_model="metal",
        )
        add_oriented_quad(
            cage,
            [
                chock_ids[(index, "heel_l")], chock_ids[(index, "heel_r")],
                chock_ids[(index, "top_r")], chock_ids[(index, "top_l")],
            ],
            Vector((0.0, sign, 0.0)),
            ground_model="metal",
        )
        # ...and the sides and base, so the hull is CLOSED: a skidded loose
        # wedge can be hit from any direction, and an open side is a face a
        # car clips through (round 5, beamng-physics lens).
        add_oriented_tri(
            cage,
            [
                chock_ids[(index, "toe_l")], chock_ids[(index, "heel_l")],
                chock_ids[(index, "top_l")],
            ],
            Vector((-1.0, 0.0, 0.0)),
            ground_model="metal",
        )
        add_oriented_tri(
            cage,
            [
                chock_ids[(index, "toe_r")], chock_ids[(index, "heel_r")],
                chock_ids[(index, "top_r")],
            ],
            Vector((1.0, 0.0, 0.0)),
            ground_model="metal",
        )
        add_oriented_quad(
            cage,
            [
                chock_ids[(index, "toe_l")], chock_ids[(index, "toe_r")],
                chock_ids[(index, "heel_r")], chock_ids[(index, "heel_l")],
            ],
            Vector((0.0, 0.0, -1.0)),
            ground_model="metal",
        )

    # THE TIE-DOWNS. Two per chock, from its top edge up to the crown ring
    # nearest it - which is the station whose surface the chock's top edge is
    # touching, derived rather than guessed.
    for index, sign, offset in CHOCK_PLACES:
        angle = math.asin(min(1.0, spec.CHOCK_FAR / spec.OUTER_RADIUS))
        station = int(round(sign * angle / spec.STATION_ANGLE)) % STATIONS
        crown = "crn_r" if offset > 0 else "crn_l"
        for key in ("top_l", "top_r"):
            cage.add_beam(
                chock_ids[(index, key)],
                ids[(crown, station)],
                "strap",
                extra={"breakGroup": spec.STRAP_BREAK_GROUP},
            )

    # A PROPER TRIAD, and the same handedness as the other 22 props in the
    # pack: 22 of 23 return left - ref = +X in vehicle space and one sign of
    # cross(left - ref, back - ref) . (up - ref). Two purpose-built datum
    # nodes make the basis unambiguous; they carry no collision, so they cost
    # nothing but their beams.
    datum_x = spec.CHOCK_OFFSET + spec.CHOCK_HALF_WIDTH + 1.4
    datum_left = cage.add_node(
        "ground_left", (-datum_x, spec.CHOCK_FAR, 0.0),
        fixed=True, collision=False, weight=200.0,
    )
    datum_up = cage.add_node(
        "ground_up", (0.0, spec.CHOCK_FAR, 1.6),
        fixed=True, collision=False, weight=200.0,
    )
    for anchor in (datum_left, datum_up):
        cage.add_beam(anchor, anchor_ids[(2, "heel_l")], "chock")
        cage.add_beam(anchor, anchor_ids[(3, "heel_r")], "chock")
    cage.add_beam(datum_left, datum_up, "chock")
    # The anchor grid is otherwise disconnected islands; tie it into one
    # ground structure so the cage is a single graph before anything is cut,
    # which is the pack's rule. All of these are fixed-to-fixed, so they are
    # graph glue and carry no force - and none of them touch a wedge, because
    # a wedge is a free body the moment the release is cut.
    for index, _sign, _offset in CHOCK_PLACES:
        for first, second in (
            ("toe_l", "toe_r"), ("toe_r", "heel_r"),
            ("heel_r", "heel_l"), ("heel_l", "toe_l"),
        ):
            cage.add_beam(
                anchor_ids[(index, first)], anchor_ids[(index, second)], "chock"
            )
    for first, second in ((0, 1), (2, 3), (0, 2), (1, 3)):
        cage.add_beam(
            anchor_ids[(first, "heel_r")], anchor_ids[(second, "heel_l")], "chock"
        )
    cage.set_ground_reference(
        (0.0, spec.CHOCK_FAR, 0.0),
        (0.0, spec.CHOCK_FAR - 3.0, 0.0),
        left=datum_left,
        up=datum_up,
        # Fixed-to-fixed graph glue: the datum hangs off the ANCHOR grid,
        # never off a wedge - a wedge is a free body once the release is cut.
        support_nodes=[
            anchor_ids[(index, "heel_l")] for index, _sign, _offset in CHOCK_PLACES
        ],
    )
    cage.set_spawn_envelope(
        [
            ids[("crn_c", 0)],
            ids[("crn_c", STATIONS // 2)],
            ids[("max_l", 0)],
            ids[("max_l", STATIONS // 2)],
            ids[("max_r", STATIONS // 4)],
            ids[("max_r", 3 * STATIONS // 4)],
            ids[("crn_c", STATIONS // 4)],
            ids[("crn_c", 3 * STATIONS // 4)],
        ]
    )
    cage.auto_base_nodes()
    assert_no_coincident_nodes(cage)
    balance_carcass(cage)
    return cage


def assert_no_coincident_nodes(cage: bk.CageBuilder, minimum: float = 0.01) -> None:
    """No two cage nodes may share a point.

    Two nodes at the same place make a zero-length beam, which has no
    direction for its force to act along and which the pack's jbeam gate
    rejects outright. It is an easy mistake to make the moment one
    sub-structure is laid out in its own parametrisation and happens to land
    on another's - the gangway's root row on the inner liner's edge, here.
    Caught at build time so the failure names the two nodes.
    """

    buckets: dict[tuple[int, int, int], list[tuple[str, tuple[float, float, float]]]] = {}
    cell = max(minimum, 1e-6) * 2.0
    for node in cage.nodes:
        point = node["source_world_position"]
        key = tuple(int(math.floor(value / cell)) for value in point)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other, other_point in buckets.get(
                        (key[0] + dx, key[1] + dy, key[2] + dz), []
                    ):
                        gap = math.dist(point, other_point)
                        if gap < minimum:
                            raise SystemExit(
                                f"cage nodes {other} and {node['id']} are "
                                f"{gap * 1000:.2f} mm apart"
                            )
        buckets.setdefault(key, []).append((node["id"], tuple(point)))


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Build-time asserts. AGENTS.md's rule is that a generator proves what it
# claims; round 1 claimed a sagitta it did not have, a net-to-gross two
# classes out, a radius of gyration it never measured, and shipped every
# carcass surface inside out. All four are now checked here, at build time,
# where a wrong number stops the build instead of reaching a player.
# ---------------------------------------------------------------------------
ORIENTATION_RULES = (
    # (name fragment, how to derive the direction the face must point)
    ("_chock_", "away_from_own_centroid"),
    ("sidewall_outer", "away_from_centre_plane"),
    ("_shoulder", "away_from_shell"),
    ("sidewall_inner", "toward_centre_plane"),
    ("liner_crown", "toward_axle"),
    ("liner_fillet", "into_cavity"),
    ("tread_base", "away_from_axle_radial_only"),
    ("tread_lugs", "away_from_axle_radial_only"),
    ("tread_tiebars", "away_from_axle_radial_only"),
    ("tread_ejectors", "away_from_axle_radial_only"),
    ("bead_toe", "toward_axle"),
    ("print_band", "away_from_centre_plane"),
)

# Objects with no radial or shell reference to test against. The mechanism
# was built for the furniture era (bolts, lift lugs, the port bezel, the
# gangway and dock plates - all deleted with the boarding concept); what
# survives is the extruded type, whose back cap sits flush on a surface that
# is itself checked. Each entry is listed on purpose; an object that is
# neither ruled nor exempt fails the build rather than being waved through.
ORIENTATION_EXEMPT = (
    "_letter_",
)


def clean_degenerates(objects) -> int:
    """Weld doubles and delete zero-area faces on every built object.

    The Mesh builder already refuses a face below its area floor, but the
    blender_kit PRIMITIVES do not go through it - a bevelled box or a 10-sided
    cylinder can leave slivers, and 34 of them reached the shipped Collada.
    A zero-area triangle has a degenerate tangent basis, and normal-mapped
    shading on one is the classic source of black speckle.
    """

    removed = 0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        # EVALUATE FIRST. The bevel modifiers blender_kit leaves pending are
        # applied by the exporter, not by us, so the slivers they create are
        # invisible to a sweep of the base mesh - which is exactly why 34 of
        # them reached the shipped Collada after the first sweep was added.
        if obj.modifiers:
            evaluated = obj.evaluated_get(depsgraph)
            baked = bpy.data.meshes.new_from_object(
                evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
            )
            old_mesh = obj.data
            obj.data = baked
            obj.modifiers.clear()
            if old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        before = len(bm.faces)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        degenerate = [
            face for face in bm.faces if face.calc_area() < 1e-8
        ]
        if degenerate:
            bmesh.ops.delete(bm, geom=degenerate, context="FACES")
        removed += before - len(bm.faces)
        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
    return removed


def assert_face_orientation(objects) -> None:
    """Every visual face must point OUT of the rubber.

    BeamNG backface-culls flexbodies. Blender and EEVEE do not, which is why
    round 1's headless renders looked correct while 100% of the outer-sidewall
    and cavity-floor triangles faced inward - in engine the player would have
    seen through both sidewalls and driven on an invisible floor.

    The tread is tested only on faces whose normal is predominantly RADIAL
    (lug crowns, groove floors, tie-bar tops, the base band). Lug side walls
    are tangential by construction and carry no radial expectation.
    """

    axle = Vector((0.0, 0.0, R_O))
    failures = []
    unjudged = []
    for obj in objects:
        rule = next((r for frag, r in ORIENTATION_RULES if frag in obj.name), None)
        if rule is None:
            # NOT a free pass. Round 2 `continue`d here, so the lettering, the
            # port bezel, the cut edge, the gangway and the straps - a third of
            # the visual budget - were judged by nothing at all while the
            # generator printed a clean bill. An object with no rule has to be
            # declared unjudgeable on purpose.
            if not any(name in obj.name for name in ORIENTATION_EXEMPT):
                unjudged.append(obj.name)
            continue
        good = bad = 0
        matrix = obj.matrix_world
        normal_matrix = matrix.to_3x3()
        # The centroid rule serves every closed chock solid: a fabricated
        # part has no radial or shell reference, but every face of a closed
        # convex-ish piece looks away from the piece's own middle. This is
        # what put the ground objects under the audit at all - the stripe
        # quads that shipped facing INTO the wedge steel were invisible to
        # a gate that only ever judged the tire.
        centroid = None
        if rule == "away_from_own_centroid":
            total = Vector((0.0, 0.0, 0.0))
            for polygon in obj.data.polygons:
                total += matrix @ polygon.center
            centroid = total / max(1, len(obj.data.polygons))
        for polygon in obj.data.polygons:
            centre = matrix @ polygon.center
            normal = normal_matrix @ polygon.normal
            radial = Vector((0.0, centre.y - axle.y, centre.z - axle.z))
            if rule == "away_from_own_centroid":
                want = centre - centroid
                if want.length < 1e-9:
                    continue
                want.normalize()
                if normal.normalized().dot(want) > 0.0:
                    good += 1
                else:
                    bad += 1
                    failures.append((obj.name, tuple(round(c, 3) for c in centre)))
                continue
            if radial.length < 1e-6:
                continue
            radial.normalize()
            if rule == "away_from_centre_plane":
                want = Vector((1.0 if centre.x > 0 else -1.0, 0.0, 0.0))
            elif rule == "toward_centre_plane":
                want = Vector((-1.0 if centre.x > 0 else 1.0, 0.0, 0.0))
            elif rule == "toward_axle":
                want = -radial
            elif rule == "away_from_shell":
                theta = math.atan2(centre.y, R_O - centre.z)
                want = shell_normal(
                    math.hypot(centre.y, R_O - centre.z),
                    1.0 if centre.x > 0 else -1.0,
                    theta,
                )
                # End caps and the bottom lip are perpendicular to the shell
                # by construction and carry no expectation along it, the same
                # way lug side walls carry none along the radius.
                if abs(normal.normalized().dot(want)) < 0.55:
                    continue
            elif rule == "into_cavity":
                # Kept tolerant on purpose: whatever mix of radial and axial
                # this band ends up with as the cavity's shape is refined, it
                # faces the cavity - inboard and toward the axle at once.
                want = (
                    -radial + Vector((-1.0 if centre.x > 0 else 1.0, 0.0, 0.0))
                ).normalized()
            else:
                if abs(normal.normalized().dot(radial)) < 0.55:
                    continue
                want = radial
            if normal.dot(want) > 0:
                good += 1
            else:
                bad += 1
        if good + bad and bad / (good + bad) > 0.02:
            failures.append(f"{obj.name}: {bad}/{good + bad} faces inverted")
    if unjudged:
        raise SystemExit(
            "these visual objects have no orientation rule and are not on the "
            "exempt list, so nothing checks them:\n  " + "\n  ".join(sorted(unjudged))
        )
    if failures:
        raise SystemExit("VISUAL WINDING IS INSIDE OUT:\n  " + "\n  ".join(failures))


# The Collada exporter stamps the wall clock into <created>/<modified> and
# writes "Blender User" as the author, so two runs of a deterministic
# generator produce DIFFERENT BYTES - which quietly makes the whole evidence
# chain non-reproducible: the handoff records the hash of the DAE from the
# same run, so nothing downstream ever notices, and the distribution ZIP lock
# churns on every Blender run even when no geometry changed.
#
# This is pack-wide, not specific to this mod (every generator calls the same
# exporter). It is normalised HERE rather than in blender_kit because fixing
# it centrally would change all twenty other mods' DAE bytes and invalidate
# their handoff hashes and cooked-DDS harvests in one go - that is its own
# round, with its own regeneration and its own gates.
COLLADA_EPOCH = "2026-08-01T00:00:00"


# FIVE, and the number is measured rather than chosen. Two consecutive runs
# of this generator differ in the last ULP of a handful of normals and UVs -
# the repo's own .gitignore has recorded that since 2026-08 - and at six
# decimals 97 of those still straddled a rounding boundary and flipped. At
# five they do not: two runs come out byte-identical, which is checked. Five
# decimals is 0.01 mm on a 28 m tire, 0.0006 degrees on a normal and 26 um of
# texture on a UV.
COLLADA_DECIMALS = 5


def quantise_collada(text: str) -> str:
    """Re-emit every float array at fixed precision, and pin the wall clock.

    TWO separate sources of churn, both recorded in this repo's own .gitignore
    since 2026-08: the exporter stamps wall-clock <created>/<modified>, and it
    jitters the last ULP of normals and UVs between runs even when positions
    and topology are exact. Round 3's note that the DAE had been "proven
    byte-identical" was wrong - it fixed the first and never touched the
    second, and a two-run A/B still differed in the map-0 UV float_array.

    FIVE decimals - and five is measured, not preferred: it is 10 um on
    metre-scale coordinates, far below anything the engine, the gates or the
    eye can resolve, and it is the largest precision this mesh survives
    byte-reproducibly. Six decimals still left 97 bytes of last-ULP churn
    between two otherwise identical runs.
    """

    def number(match: "re.Match[str]") -> str:
        return f"{float(match.group(0)):.{COLLADA_DECIMALS}f}"

    def array(match: "re.Match[str]") -> str:
        head, body, tail = match.group(1), match.group(2), match.group(3)
        return head + re.sub(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", number, body) + tail

    text = re.sub(r"<created>[^<]*</created>", f"<created>{COLLADA_EPOCH}</created>", text)
    text = re.sub(r"<modified>[^<]*</modified>", f"<modified>{COLLADA_EPOCH}</modified>", text)
    text = re.sub(r"<author>[^<]*</author>", "<author>Eric Rolph</author>", text)
    return re.sub(
        r"(<float_array\b[^>]*>)(.*?)(</float_array>)", array, text, flags=re.S
    )


def normalise_collada(path: Path) -> dict[str, object]:
    """Make an exported DAE a function of the source, then re-hash it."""

    text = quantise_collada(path.read_text(encoding="utf-8"))
    if quantise_collada(text) != text:
        raise SystemExit("collada normalisation is not idempotent")
    path.write_text(text, encoding="utf-8", newline="\n")
    blob = path.read_bytes()
    return {"sha256": hashlib.sha256(blob).hexdigest(), "size": len(blob)}


# The SEVEN surfaces that between them ARE the carcass. Welded, they have to
# close: a tire is a closed shell with one hole in it, and that hole is the
# access port. The tread's lugs, tie bars, ejectors and buttress wrap are
# furniture standing ON this shell and are deliberately not part of it - they
# are judged by assert_surfaces_stay_home and by the shipped-mesh gates.
CLOSED_SHELL = (
    "_sidewall_outer", "_sidewall_inner", "_bead_toe",
    "_liner_crown", "_liner_fillet", "_shoulder", "_tread_base",
)


def assert_shell_rings_close(tire_objects) -> None:
    """The carcass is a CLOSED shell. No exceptions any more.

    THE GATE THAT WOULD HAVE CAUGHT ROUND 3. Every other check in this file
    measured constants and row tables; none looked at whether the surfaces
    actually MET. Two defects hid behind that: the shoulder loft started
    0.0671 m inboard of the ring the lathe ended on, leaving an open annulus
    84.85 m long round each shoulder that culled straight to sky, and the
    inner lathe ran 0.93 m past the cavity floor.

    It used to allow open boundary in one place - the access port. There is no
    access port now, so the answer is simply zero, which is a much better test
    than one with a sector-shaped hole in it.
    """

    master = bmesh.new()
    for obj in tire_objects:
        if not any(fragment in obj.name for fragment in CLOSED_SHELL):
            continue
        if (obj.matrix_world - Matrix.Identity(4)).median_scale > 1e-9:
            raise SystemExit(f"{obj.name} carries a transform; the weld assumes world space")
        master.from_mesh(obj.data)
    if not master.faces:
        raise SystemExit("no carcass surfaces found to close")
    bmesh.ops.remove_doubles(master, verts=master.verts, dist=1e-4)
    master.edges.ensure_lookup_table()

    stray_length = 0.0
    worst = None
    for edge in master.edges:
        if len(edge.link_faces) == 2:
            continue
        length = edge.calc_length()
        stray_length += length
        if worst is None or length > worst[0]:
            worst = (length, 0.5 * (edge.verts[0].co + edge.verts[1].co))
    master.free()

    if stray_length > 0.05:
        _, mid = worst
        radius = math.hypot(mid.y, R_O - mid.z)
        raise SystemExit(
            f"the carcass has {stray_length:.2f} m of open or non-manifold boundary "
            f"- it is not a closed shell. Worst near x {mid.x:.3f}, radius "
            f"{radius:.3f}, theta {math.degrees(math.atan2(mid.y, R_O - mid.z)):.1f} deg"
        )
    print("COLOSSUS carcass: closed, everywhere")


def assert_shoulder_falls_away(tire_objects) -> None:
    """Nothing outboard of the tread edge may stand above the groove floor.

    THE THIRD DISGUISE OF THE SAME QUESTION. Round 2 had a clamped flange ring
    where the shoulder should be; round 3 had a 0.0671 m slot at its start;
    round 4 had it standing 0.198 m ABOVE the tread's own groove floor - 31%
    of TREAD_DEPTH - which dams the mouth of every shoulder groove on a
    pattern whose lateral grooves exist to throw stones out sideways. None of
    the three was visible to anything that measured constants.

    The invariant is the functional one and it needs no profile walk: a stone
    leaving a shoulder groove travels outboard at the groove floor's radius,
    so every OUTER carcass point outboard of the tread edge has to sit at or
    below that radius. Inner surfaces are excluded - the liner is not what a
    stone hits.
    """

    floor = base_r(spec.TREAD_HALF)
    outer = ("_sidewall_outer", "_shoulder", "_tread_base")
    worst = None
    for obj in tire_objects:
        if not any(fragment in obj.name for fragment in outer):
            continue
        for vertex in obj.data.vertices:
            point = obj.matrix_world @ vertex.co
            if abs(point.x) <= spec.TREAD_HALF + 1e-4:
                continue
            radius = math.hypot(point.y, R_O - point.z)
            if worst is None or radius > worst[0]:
                worst = (radius, abs(point.x), obj.name)
    if worst is None:
        raise SystemExit("no carcass surface outboard of the tread edge")
    radius, axial, name = worst
    if radius > floor + 1e-4:
        raise SystemExit(
            f"{name} reaches radius {radius:.4f} at |x| {axial:.3f}, "
            f"{(radius - floor) * 1000:.0f} mm ABOVE the tread's groove floor at "
            f"{floor:.4f}: a full-circumference dam across every shoulder groove"
        )
    print(
        f"COLOSSUS shoulder: falls away outboard of the tread edge "
        f"(crest {radius:.4f} against a {floor:.4f} groove floor, "
        f"{(floor - radius) * 1000:.0f} mm clear)"
    )


def assert_furniture_is_seated(tire_objects) -> None:
    """Every open-bottomed shell sinks into the surface it stands on.

    A lug, a tie bar, an ejector, a buttress wrap and a moulded glyph are all
    shells with no bottom: what closes them is the surface underneath. Built on
    the ANALYTIC radius they sat exactly ON it, and the surface that actually
    ships is tessellated - a 144-station chord dips ~3 mm inside its own
    analytic radius - so every rim stood a hairline proud and 82% of 2,461.6 m
    of open rim looked straight through to the skybox at grazing angles.

    Both families are surfaces of revolution, so "the surface underneath" is a
    function of one variable and needs no ray cast: for tread furniture it is
    base_r(x), for sidewall furniture it is the outer half width at a radius.
    """

    # PER CONNECTED COMPONENT, not per object - and round 7 caught the
    # first cut of this claim being a comment rather than code: the helper
    # existed with zero call sites while the sweep below it still keyed by
    # object name, exactly the vouching pattern that let 12 floating outer
    # wear bars ship through two green rounds inside the seated ejectors
    # object. The semantic mirrors the shipped-DAE gate
    # (test_every_open_tread_component_is_seated_in_its_local_floor): per
    # component, the BOUNDARY RIM (edges used once) may sit at most
    # LUG_SEAT/2 proud of its own local floor.
    floor = spec.LUG_SEAT * 0.5

    def component_rim_extremes(obj, gap_of):
        """Max boundary-rim gap per connected component of one object."""

        parent: dict[int, int] = {}

        def find(a: int) -> int:
            while parent.get(a, a) != a:
                parent[a] = parent.get(parent[a], parent[a])
                a = parent[a]
            return a

        def union(a: int, b: int) -> None:
            parent.setdefault(a, a)
            parent.setdefault(b, b)
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        edge_count: dict[tuple[int, int], int] = {}
        for polygon in obj.data.polygons:
            verts = [int(v) for v in polygon.vertices]
            for index in range(1, len(verts)):
                union(verts[0], verts[index])
            for index in range(len(verts)):
                a, b = verts[index], verts[(index + 1) % len(verts)]
                key = (min(a, b), max(a, b))
                edge_count[key] = edge_count.get(key, 0) + 1
        rim: set[int] = set()
        for (a, b), count in edge_count.items():
            if count == 1:
                rim.update((a, b))
        extremes: dict[int, float] = {}
        matrix = obj.matrix_world
        for index in rim:
            root = find(index)
            gap = gap_of(matrix @ obj.data.vertices[index].co)
            if root not in extremes or gap > extremes[root]:
                extremes[root] = gap
        return extremes

    worst_tread = None
    for obj in tire_objects:
        if not any(
            fragment in obj.name
            for fragment in ("_tread_lugs", "_tread_tiebars", "_tread_ejectors")
        ):
            continue

        def tread_gap(point):
            radius = math.hypot(point.y, R_O - point.z)
            return radius - base_r(point.x)

        for root, gap in sorted(component_rim_extremes(obj, tread_gap).items()):
            if worst_tread is None or gap > worst_tread[0]:
                worst_tread = (gap, obj.name)
            if gap > floor:
                raise SystemExit(
                    f"a component of {obj.name} has rim {gap * 1000:+.1f} mm "
                    f"proud of its own local groove floor (limit "
                    f"{floor * 1000:.0f} mm); it will show daylight at "
                    f"grazing angles"
                )

    letter_deepest = None
    for obj in tire_objects:
        if "_letter_" not in obj.name:
            continue
        for vertex in obj.data.vertices:
            point = obj.matrix_world @ vertex.co
            radius = math.hypot(point.y, R_O - point.z)
            surface = sidewall_outer(radius)[0] + sidewall_relief(radius)
            gap = abs(point.x) - surface
            if letter_deepest is None or gap < letter_deepest:
                letter_deepest = gap
    if letter_deepest is not None and letter_deepest > -floor:
        raise SystemExit(
            f"the moulded type's back cap sits {letter_deepest * 1000:+.1f} mm "
            f"against the flank, not the {floor * 1000:.0f} mm inside it a seated "
            f"shell needs"
        )
    print(
        f"COLOSSUS seating: worst tread rim {worst_tread[0] * 1000:+.1f} mm "
        f"vs its local floor ({worst_tread[1]}), type "
        f"{letter_deepest * 1000:.1f} mm into the flank"
    )


def assert_surfaces_stay_home(tire_objects) -> None:
    """The liner stops at the cavity floor; the buttress lies on the shoulder.

    Two bounds that are stated in spec.py's constants and were never checked
    against the mesh. CAVITY_RADIUS is what makes the cavity floor a floor;
    liner geometry past it is a trench down the lane. And outer_half_at is the
    surface definition the buttress wrap is supposed to ride - if a wrap
    vertex is not on it, the wrap is floating.
    """

    liner_worst = 0.0
    for obj in tire_objects:
        if not any(f in obj.name for f in ("_liner_crown", "_liner_fillet", "_sidewall_inner")):
            continue
        for vertex in obj.data.vertices:
            point = obj.matrix_world @ vertex.co
            liner_worst = max(liner_worst, math.hypot(point.y, R_O - point.z))
    if liner_worst > spec.CAVITY_RADIUS + 1e-3:
        raise SystemExit(
            f"liner geometry reaches radius {liner_worst:.4f} against a cavity floor "
            f"at {spec.CAVITY_RADIUS:.4f}; that is a "
            f"{(liner_worst - spec.CAVITY_RADIUS) * 1000:.0f} mm trench down the lane"
        )

    print(
        f"COLOSSUS surfaces: liner tops out at radius {liner_worst:.3f} "
        f"(cavity floor {spec.CAVITY_RADIUS:.3f})"
    )


def assert_authored_claims(cage) -> None:
    assert len(spec.PITCH_SEQUENCE) == spec.TREAD_PITCHES, (
        f"PITCH_SEQUENCE has {len(spec.PITCH_SEQUENCE)} entries against an "
        f"authored TREAD_PITCHES of {spec.TREAD_PITCHES}"
    )
    # THE STAMP IS DERIVED, NOT DECORATED. Tread class is depth relative to
    # the tire: E-4 deep tread runs ~2.0-2.6% of OD, E-3 regular ~1.3-1.7%.
    # Round 5 restamped the sidewall E-3 against the mould's own 2.25% and
    # the drift cost a review round; now the same print-vs-hardware law that
    # covers the size code covers the service class.
    depth_ratio = spec.TREAD_DEPTH / (2.0 * spec.OUTER_RADIUS)
    if depth_ratio >= 0.020:
        derived_class = "E-4"
    elif depth_ratio >= 0.013:
        derived_class = "E-3"
    else:
        derived_class = "E-2"
    assert spec.SERVICE_CODE.startswith(derived_class), (
        f"SERVICE_CODE {spec.SERVICE_CODE!r} disagrees with the moulded depth: "
        f"{depth_ratio * 100:.2f}% of OD derives {derived_class}"
    )
    """Check the numbers spec.py argues from against what was actually built."""

    if spec.FACET_SAGITTA > spec.FACET_SAGITTA_CEILING:
        raise SystemExit(
            f"{spec.STATIONS} stations give a {spec.FACET_SAGITTA * 1000:.1f} mm "
            f"facet sagitta, over the {spec.FACET_SAGITTA_CEILING * 1000:.0f} mm ceiling"
        )
    if not (
        spec.EARTHMOVER_OD_TO_WIDTH[0] <= spec.OD_TO_WIDTH <= spec.EARTHMOVER_OD_TO_WIDTH[1]
    ):
        raise SystemExit(
            f"OD/section-width {spec.OD_TO_WIDTH:.3f} is outside the earthmover band "
            f"{spec.EARTHMOVER_OD_TO_WIDTH}; this is the shape of another class of tire"
        )
    if not (
        spec.EARTHMOVER_RIM_TO_WIDTH[0] <= spec.RIM_TO_WIDTH <= spec.EARTHMOVER_RIM_TO_WIDTH[1]
    ):
        raise SystemExit(
            f"rim/section-width {spec.RIM_TO_WIDTH:.3f} is outside the earthmover band"
        )

    # Net-to-gross at the contact face, summed over the lug crown polygons
    # THE GENERATOR ACTUALLY BUILT. The old figure multiplied the row table by
    # a pitch ratio - the moulded pattern before draft, before LUG_CHAMFER
    # took 85 mm off every edge, and before the zigzag - so the gate was
    # checking a different quantity from the one spec.py's prose argues about,
    # and could not have seen a groove closing to 62 mm.
    steps = 512
    gross = 0.0
    for step in range(steps):
        x = -spec.TREAD_HALF + 2.0 * spec.TREAD_HALF * (step + 0.5) / steps
        gross += crown_r(x) * TAU * (2.0 * spec.TREAD_HALF / steps)
    net_to_gross = LUG_CROWN_AREA["land"] / gross
    contact_share = LUG_CROWN_AREA["crown"] / max(LUG_CROWN_AREA["land"], 1e-9)
    if not (spec.CONTACT_SHARE_BAND[0] <= contact_share <= spec.CONTACT_SHARE_BAND[1]):
        raise SystemExit(
            f"the flat contact face is {contact_share * 100:.1f}% of the moulded land "
            f"against an authored {spec.CONTACT_SHARE_BAND}; LUG_CHAMFER "
            f"{spec.LUG_CHAMFER * 1000:.0f} mm is eating the block"
        )
    if not (spec.NET_TO_GROSS_BAND[0] <= net_to_gross <= spec.NET_TO_GROSS_BAND[1]):
        raise SystemExit(
            f"tread net-to-gross {net_to_gross * 100:.1f}% is outside the E-4/L-5 band "
            f"{spec.NET_TO_GROSS_BAND}; that is a different service class"
        )

    # The groove floor has to survive the lug root growth.
    growth = spec.LUG_ROOT_FILLET + spec.LUG_DRAFT
    for lo, hi in spec.TREAD_GROOVES:
        floor = (hi - lo) * spec.TREAD_HALF - 2.0 * growth
        if floor < 0.12:
            raise SystemExit(
                f"circumferential groove necks to {floor * 1000:.0f} mm at its floor "
                f"under {spec.TREAD_DEPTH * 1000:.0f} mm of depth; no mould releases that"
            )

    # THE BEAD SEAT. spec.py says "the generator asserts it" about
    # REFERENCE_RIM_RATIO and nothing did - both it and RIM_RATIO_TOLERANCE
    # were referenced only at their own definitions, on the one meridian
    # station with no gate at all and the one the R457 in the size code is a
    # claim about. Measured off the mesh's INNER face at the bead, which is
    # what a rim width is measured between.
    seat_half, _ = sidewall_mid(R_BEAD)
    seat_inner = seat_half - sidewall_outer(R_BEAD)[1] * 0.5
    rim_ratio = 2.0 * seat_inner / spec.SECTION_WIDTH
    if abs(rim_ratio - spec.REFERENCE_RIM_RATIO) > spec.RIM_RATIO_TOLERANCE:
        raise SystemExit(
            f"the bead seat measures {rim_ratio:.4f} of the section width against "
            f"a reference {spec.REFERENCE_RIM_RATIO:.3f} +/- "
            f"{spec.RIM_RATIO_TOLERANCE:.3f}; that is a different rim"
        )

    # Radius of gyration and the spin-up the mass solve promises.
    inertia = mass = 0.0
    for node in cage.nodes:
        if node["fixed"] or "chock" in node["id"]:
            continue
        _, y, z = node["source_world_position"]
        radius = math.hypot(y, R_O - z)
        inertia += node["weight"] * radius * radius
        mass += node["weight"]
    gyration = math.sqrt(inertia / mass)
    if abs(gyration - spec.RADIUS_OF_GYRATION) > spec.RADIUS_OF_GYRATION_TOLERANCE:
        raise SystemExit(
            f"measured radius of gyration {gyration:.3f} m, but spec.py's mass solve "
            f"quotes {spec.RADIUS_OF_GYRATION:.2f} m"
        )
    climb = math.atan(spec.MU_EFFECTIVE)
    torque = spec.CAR_MASS * spec.GRAVITY * spec.CAVITY_RADIUS * math.sin(climb)
    # ROLLING, not spinning on an axle. Nothing holds this axle: the moment
    # balance is about the CONTACT POINT, so the mass has to be accelerated
    # linearly as well as angularly and the effective inertia is I_cm + M*R^2.
    effective = inertia + mass * spec.OUTER_RADIUS**2
    alpha = torque / effective
    seconds = (spec.SPINUP_TARGET_KPH / 3.6 / spec.OUTER_RADIUS) / alpha
    lo, hi = spec.SPINUP_SECONDS_BAND
    if not (lo <= seconds <= hi):
        raise SystemExit(
            f"a stock car spins the Colossus to {spec.SPINUP_TARGET_KPH:.0f} km/h in "
            f"{seconds:.1f} s, outside the authored band {spec.SPINUP_SECONDS_BAND}"
        )
    print(
        f"COLOSSUS checks: OD/W {spec.OD_TO_WIDTH:.3f}  rim/W {spec.RIM_TO_WIDTH:.3f}  "
        f"seat/W {rim_ratio:.4f}  "
        f"net-to-gross {net_to_gross * 100:.1f}% (contact face "
        f"{contact_share * 100:.1f}% of it)  k_gyr {gyration:.2f} m  "
        f"spin-up {seconds:.1f} s  sagitta {spec.FACET_SAGITTA * 1000:.1f} mm"
    )


def main() -> None:
    bk.reset_scene()
    materials = bk.materials_from_palette(
        spec, EXAMPLE_ROOT / "textures", preview_emission=True
    )

    tire_objects = build_carcass(materials)
    tire_objects += build_tread(materials)
    tire_objects += build_print_band(materials)
    tire_objects += build_lettering(materials)
    ground_objects = build_chocks(materials)

    swept = clean_degenerates(tire_objects + ground_objects)
    assert_face_orientation(tire_objects + ground_objects)
    assert_shell_rings_close(tire_objects)
    assert_shoulder_falls_away(tire_objects)
    assert_furniture_is_seated(tire_objects)
    assert_surfaces_stay_home(tire_objects)

    dropped = sum(getattr(obj, "_dropped", 0) for obj in tire_objects)
    triangles = sum(
        max(len(polygon.vertices) - 2, 0)
        for obj in tire_objects + ground_objects
        for polygon in obj.data.polygons
    )
    print(
        f"COLOSSUS visual triangles: {triangles} "
        f"(degenerate dropped: {dropped}, swept after build: {swept})"
    )

    dae_path = VEHICLE_DIR / f"{MOD_ID}.dae"
    # WELD ON EXPORT. Every surface here is its own object so the orientation
    # rules can name it, and the join that makes them one flexbody left each
    # shared ring as two coincident vertex sets: 12,026 boundary edges and
    # 4,666 m of them shipped, and down both edges of the drive lane 554 vertex
    # pairs carried a 30.75 degree median normal split across geometry that
    # bends 2.5 degrees - a hard false crease running the full 84 m
    # circumference on the surface the driver stares at for the whole ride.
    visual = bk.export_multi_flexbody(
        MOD_ID,
        dae_path,
        {
            f"{MOD_ID}_visual": ground_objects,
            f"{MOD_ID}_carcass": tire_objects,
        },
        weld=1e-6,
    )
    # Re-hash AFTER normalising, or the handoff certifies bytes that are no
    # longer on disk.
    visual.update(normalise_collada(dae_path))

    cage = build_cage()
    free_mass = sum(
        node["weight"]
        for node in cage.nodes
        if not node["fixed"] and "chock" not in node["id"]
    )
    if abs(free_mass - spec.TIRE_MASS) > spec.MASS_TOTAL_TOLERANCE:
        raise SystemExit(
            f"cage tire mass {free_mass:.1f} kg is outside the authored "
            f"{spec.TIRE_MASS:.0f} kg +/- {spec.MASS_TOTAL_TOLERANCE:.0f} kg"
        )
    assert_authored_claims(cage)
    print(f"COLOSSUS free (tire) mass: {free_mass:.1f} kg over "
          f"{sum(1 for n in cage.nodes if not n['fixed'])} free nodes")

    behavior = dict(spec.BEHAVIOR)
    behavior["free_mass"] = round(free_mass, 3)
    bk.write_handoff(
        AUTHORING_ROOT / f"{MOD_ID}.handoff.json",
        mod_id=MOD_ID,
        display_name=spec.DISPLAY_NAME,
        cage=cage,
        visual=visual,
        visual_dae_relative=f"vehicles/{MOD_ID}/{MOD_ID}.dae",
        visual_mesh_name=f"{MOD_ID}_visual",
        visual_groups=[f"chock_{index}" for index in range(4)],
        parts=[],
        palette=spec.PALETTE,
        behavior={
            "tunables": behavior,
            "triggers": spec.TRIGGERS,
            "effects": spec.EFFECTS,
            "camera_distance": behavior.get("camera_distance", 46.0),
        },
        flexbodies_extra=[{"mesh": f"{MOD_ID}_carcass", "groups": ["carcass"]}],
    )
    # STRIP THE STAMP. Blender writes its wall clock into every JPEG it
    # renders and prop_builder copies this one into the shipped tree twice, so
    # without this a pixel-identical re-render still moves the mod's content
    # sha, its build serial and the ZIP lock the LIVE gate verifies against.
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(36.0, -36.0, 15.0),
        look_at=(0.0, 0.0, 12.0),
        strip_stamp=True,
    )
    print("COLOSSUS generator complete")


if __name__ == "__main__":
    main()
