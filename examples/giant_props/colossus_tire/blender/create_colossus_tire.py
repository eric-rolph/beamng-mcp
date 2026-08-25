"""Deterministic Blender generator for COLOSSUS 10350/80R457.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/colossus_tire/blender/create_colossus_tire.py

Everything here is built from ``spec.py``'s size code. There is no modelled
mesh checked in and no primitive-plus-boolean stack: the carcass, the tread
pattern and the access port are all emitted vertex by vertex, because a tire
is a surface of revolution with a designed tread pitch sequence on it, and
that is exactly the kind of thing a boolean pipeline gets wrong (see
``blender_kit.cut_openings``' standing bevel/boolean bug).

Frames. Authored right-handed, metres, Z-up, +Y = the direction the tire
rolls. The tire's axle lies along X at height OUTER_RADIUS, so station 0 is
the contact patch and the access port is at the bottom, facing the dock at
+X. ``blender_kit`` maps the whole thing into BeamNG vehicle space through
the shared proper 180 deg Z rotation.
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
TILE_STEEL = 1.60

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


def shoulder_point(t: float) -> tuple[float, float]:
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
        sidewall_outer(SHOULDER_TOP_RADIUS)[0] + sidewall_relief(SHOULDER_TOP_RADIUS)
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


def outer_half_at(radius: float) -> float:
    """The FULL outer half width anywhere on the carcass, relief included.

    Above the tread base's outboard ring the surface is the lofted shoulder,
    not a clamped sidewall, and the loft has to be inverted properly: a
    24-step nearest-radius scan returns the SAME clamped answer for every
    radius above the loft's peak, which is how the buttress wrap's top two
    rows ended up sharing one half width and floating 0.43 m off the tire.
    Bisection on the loft's descending branch is a real inverse.
    """

    if radius < SHOULDER_BASE_RADIUS:
        return sidewall_outer(radius)[0] + sidewall_relief(radius)
    target = min(radius, SHOULDER_PEAK_RADIUS)
    lo, hi = SHOULDER_PEAK_T, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if shoulder_point(mid)[1] > target:
            lo = mid
        else:
            hi = mid
    return shoulder_point(0.5 * (lo + hi))[0]


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


def _shoulder_extent() -> tuple[float, float, float]:
    """(t at the loft's widest radius, that radius, the radius at t = 1).

    The loft is NOT monotonic in radius: the bulge lifts it 5 mm above the top
    station before it turns over and runs down to the tread base. Anything
    inverting the loft has to know where the turn is, or it inverts onto the
    wrong branch.
    """

    samples = [step / 4096.0 for step in range(4097)]
    peak_t = max(samples, key=lambda t: shoulder_point(t)[1])
    return peak_t, shoulder_point(peak_t)[1], shoulder_point(1.0)[1]


SHOULDER_PEAK_T, SHOULDER_PEAK_RADIUS, SHOULDER_BASE_RADIUS = _shoulder_extent()


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
PORT_QUADS = {
    (index % STATIONS)
    for index in range(-spec.PORT_STATIONS // 2, spec.PORT_STATIONS // 2)
}
PORT_HALF_ANGLE = math.radians(spec.PORT_SPAN_DEG) * 0.5


def port_open_at(station: int, radius_lo: float, radius_hi: float) -> bool:
    """True where the +X sidewall panel is inside the access port."""

    if station % STATIONS not in PORT_QUADS:
        return False
    mid = 0.5 * (radius_lo + radius_hi)
    return spec.PORT_INNER_RADIUS - 1e-6 <= mid <= spec.PORT_OUTER_RADIUS + 1e-6


def port_open_theta(theta: float, radius: float) -> bool:
    """True for a VISUAL sample inside the port opening (angle resolution)."""

    wrapped = (theta + math.pi) % TAU - math.pi
    return (
        abs(wrapped) <= PORT_HALF_ANGLE
        and spec.PORT_INNER_RADIUS <= radius <= spec.PORT_OUTER_RADIUS
    )


# ---------------------------------------------------------------------------
# Visual: carcass shell (sidewalls outside and in, inner liner, bead toes)
# ---------------------------------------------------------------------------
VISUAL_STATIONS = 144           # 2.5 deg: 3.3 mm sagitta on a 14 m radius
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

    def shell(fraction: float, side: float, face: str) -> tuple[float, float]:
        """(signed half width, radius) on one face of the sidewall shell."""

        radius = R_BEAD + fraction * spec.SECTION_HEIGHT
        half, thick = sidewall_mid(radius)
        if face == "outer":
            return (side * (half + thick * 0.5 + sidewall_relief(radius)), radius)
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
            half, radius = shell(fraction, side, face)
            if previous is not None:
                arc += math.hypot(half - previous[0], radius - previous[1])
            previous = (half, radius)
            rows.append(
                ([mesh.vertex(polar(half, radius, theta)) for theta in thetas], radius, arc)
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
                    if side > 0 and (
                        port_open_theta(theta0 + step_angle * 0.5, 0.5 * (radius_lo + radius_hi))
                    ):
                        continue
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
        for step in range(steps + 1):
            t = step / steps
            angle = t * math.pi
            half = 0.5 * (outer_half + inner_half) + 0.5 * (outer_half - inner_half) * math.cos(angle)
            radius = 0.5 * (outer_radius + inner_radius) + 0.5 * (
                outer_radius - inner_radius
            ) * math.cos(angle)
            radius -= math.sin(angle) * spec.SIDEWALL_THICKNESS[0] * 0.22
            toe_rows.append([bead.vertex(polar(half, radius, theta)) for theta in thetas])
        for step in range(steps):
            for column in range(VISUAL_STATIONS):
                nxt = (column + 1) % VISUAL_STATIONS
                theta0 = thetas[column]
                theta1 = theta0 + step_angle
                v0, v1 = step / steps, (step + 1) / steps
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
                # Skip only where the boarding gangway replaces it. The
                # gangway is narrower than the port, so skipping the whole
                # port span left a 3.5 deg sliver of open cavity either side
                # of it - a black slot along the threshold.
                mid = (theta0 + step_angle * 0.5 + math.pi) % TAU - math.pi
                if side > 0 and abs(mid) <= math.radians(spec.TONGUE_HALF_ARC_DEG):
                    continue
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
                    [shoulder.vertex(polar(side * half, radius, theta)) for theta in thetas],
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
    buttress = Mesh(f"{MOD_ID}_tread_buttress", tread_mat)
    pitches = pitch_angles()

    # --- Tread base: the continuous surface every groove floor sits on.
    base_steps = 26
    base_columns = len(pitches) * 4
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
        shoulder = row_index == len(spec.TREAD_ROWS) - 1
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
            if shoulder:
                side = 1.0 if x1 > 0 else -1.0
                # The port's outer edge sits 0.70 m below the tread edge, so a
                # buttress wrap over the opening has no sidewall to lie on and
                # hangs in the doorway. The bolted frame replaces the rubber
                # buttress across the port sector; the wrap stops either side.
                centre = (0.5 * (a0 + a1) + math.pi) % TAU - math.pi
                keep_out = math.radians(spec.PORT_CLEAR_DEG)
                if not (side > 0 and abs(centre) < keep_out):
                    add_buttress(buttress, a0, a1, side)

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

    return [
        base.build(), mesh.build(), detail.build(),
        ejectors.build(), buttress.build(),
    ]


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
        (fillet + draft, -spec.TREAD_DEPTH),
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


def add_buttress(mesh: Mesh, a0: float, a1: float, side: float) -> None:
    """Wrap a shoulder lug down over the buttress.

    Earthmover shoulder lugs do not stop at the tread edge; they continue
    down the upper sidewall. This is the silhouette feature that separates a
    mining tire from a truck tire at 200 m, and round 1 did not have it.
    """

    steps = 5
    edge = 3
    # Start on the SHOULDER the wrap lies on. crown_r(TREAD_HALF) is 13.9457
    # and the shoulder loft never reaches it - it tops out at 13.5094 - so the
    # first two rows both took outer_half_at's clamp, came out at the same
    # half width, and hung 0.44 m proud of any surface as an open-topped
    # shell: the hooked spurs on the shoulder silhouette in every hero render.
    top_radius = SHOULDER_PEAK_RADIUS
    rows = []
    for step in range(steps + 1):
        t = step / steps
        radius = top_radius - spec.BUTTRESS_DROP * t
        stand = outer_half_at(radius)
        # Ends on a real thickness. Round 1's taper hit exactly zero at the
        # last row, so outer_row and inner_row were coincident vertex for
        # vertex and 544 triangles collapsed to zero area. A real buttress
        # wrap feathers; it does not vanish.
        relief = spec.BUTTRESS_RELIEF * (1.0 - t * t) * 0.88 + spec.BUTTRESS_FEATHER
        outer_row = []
        inner_row = []
        for corner in range(edge + 1):
            angle = a0 + (a1 - a0) * corner / edge
            taper = 1.0 - 0.18 * t
            centre = 0.5 * (a0 + a1)
            angle = centre + (angle - centre) * taper
            outer_row.append(mesh.vertex(polar(side * (stand + relief), radius, angle)))
            inner_row.append(mesh.vertex(polar(side * stand, radius, angle)))
        rows.append((outer_row, inner_row, radius))

    # Top cap. The wrap continues the shoulder lug, so its upper rim has to be
    # closed onto the surface; left open it read as mould flash standing off
    # the one feature that separates a mining tire from a truck tire at
    # distance.
    outer_first, inner_first, _ = rows[0]
    for corner in range(edge):
        uv = ((0.0, 0.0), (0.3, 0.0), (0.3, 0.12), (0.0, 0.12))
        if side > 0:
            mesh.quad(
                inner_first[corner], inner_first[corner + 1],
                outer_first[corner + 1], outer_first[corner], uv,
            )
        else:
            mesh.quad(
                outer_first[corner], outer_first[corner + 1],
                inner_first[corner + 1], inner_first[corner], uv,
            )

    # V ACCUMULATES down the wrap. Round 1 restarted it at 0.0 -> 0.4 for
    # every one of the five bands, so the tread texture began again five times
    # down the most recognisable silhouette feature on the tire: five hard
    # horizontal seams, at 0.775 m/tile against the tread's 2.20.
    drop_v = [0.0]
    for step in range(steps):
        drop_v.append(drop_v[-1] + (spec.BUTTRESS_DROP / steps) / TILE_TREAD)
    for step in range(steps):
        outer_lo, inner_lo, radius_lo = rows[step]
        outer_hi, inner_hi, radius_hi = rows[step + 1]
        for corner in range(edge):
            uv = (
                (radius_lo * a0 / TILE_TREAD, drop_v[step]),
                (radius_lo * a1 / TILE_TREAD, drop_v[step]),
                (radius_hi * a1 / TILE_TREAD, drop_v[step + 1]),
                (radius_hi * a0 / TILE_TREAD, drop_v[step + 1]),
            )
            if side > 0:
                mesh.quad(
                    outer_lo[corner], outer_lo[corner + 1],
                    outer_hi[corner + 1], outer_hi[corner], uv,
                )
            else:
                mesh.quad(
                    outer_hi[corner], outer_hi[corner + 1],
                    outer_lo[corner + 1], outer_lo[corner], uv,
                )
        for corner, direction in ((0, -1), (edge, 1)):
            uv = ((0.0, 0.0), (0.3, 0.0), (0.3, 0.3), (0.0, 0.3))
            a = outer_lo[corner]
            b = outer_hi[corner]
            c = inner_hi[corner]
            d = inner_lo[corner]
            # INVERTED FROM ROUND 3. Both end walls traversed their shared
            # edge the same way the outer face does, which is the definition
            # of a face wound inside out - 1,020 such edges in this one
            # object. The orientation assert could not see it: an end wall is
            # perpendicular to the shell, so the away_from_shell rule
            # explicitly declines to judge it, and nothing else did either.
            if direction * side < 0:
                mesh.quad(a, b, c, d, uv)
            else:
                mesh.quad(d, c, b, a, uv)
    # Bottom lip.
    outer_last, inner_last, _ = rows[-1]
    for corner in range(edge):
        uv = ((0.0, 0.0), (0.3, 0.0), (0.3, 0.15), (0.0, 0.15))
        if side > 0:
            mesh.quad(
                inner_last[corner + 1], inner_last[corner],
                outer_last[corner], outer_last[corner + 1], uv,
            )
        else:
            mesh.quad(
                outer_last[corner + 1], outer_last[corner],
                inner_last[corner], inner_last[corner + 1], uv,
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
    bottom = [mesh.vertex(polar(x, base_r(x), angle)) for angle, x in corners]
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
    bottom = [mesh.vertex(polar(x, base_r(x), angle)) for angle, x in corners]
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
    base = base_r(x)
    apex = mesh.vertex(polar(x, base + radius * 0.95, theta))
    previous = None
    for ring in range(rings, 0, -1):
        t = ring / rings
        row = []
        for segment in range(segments):
            angle = TAU * segment / segments
            dx = math.cos(angle) * radius * t
            da = math.sin(angle) * radius * t / spec.GROOVE_RADIUS
            lift = radius * 0.95 * math.sqrt(max(0.0, 1.0 - t * t))
            row.append(mesh.vertex(polar(x + dx, base + lift, theta + da)))
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
def port_perimeter(per_edge: int = 14) -> list[tuple[float, float, float, float]]:
    """(theta, radius, outward_theta, outward_radius) around the opening.

    The outward direction is carried per point so the bezel can be grown out
    of the opening in the sidewall plane without re-deriving which edge each
    point is on - the round-1 bezel guessed that per point and produced a
    frame with kinked corners.
    """

    half = PORT_HALF_ANGLE
    r0, r1 = spec.PORT_INNER_RADIUS, spec.PORT_OUTER_RADIUS
    points: list[tuple[float, float, float, float]] = []

    def edge(theta_a, radius_a, theta_b, radius_b, out_t, out_r):
        for step in range(per_edge):
            t = step / per_edge
            points.append(
                (
                    theta_a + (theta_b - theta_a) * t,
                    radius_a + (radius_b - radius_a) * t,
                    out_t,
                    out_r,
                )
            )

    edge(-half, r0, half, r0, 0.0, -1.0)
    edge(half, r0, half, r1, 1.0, 0.0)
    edge(half, r1, -half, r1, 0.0, 1.0)
    edge(-half, r1, -half, r0, -1.0, 0.0)

    # Round the four corners by blending the outward direction across the
    # points either side of each corner.
    span = 3
    smoothed = []
    count = len(points)
    for index, (theta, radius, out_t, out_r) in enumerate(points):
        acc_t = acc_r = 0.0
        for offset in range(-span, span + 1):
            _, _, ot, orr = points[(index + offset) % count]
            weight = 1.0 - abs(offset) / (span + 1.0)
            acc_t += ot * weight
            acc_r += orr * weight
        length = math.hypot(acc_t, acc_r) or 1.0
        smoothed.append((theta, radius, acc_t / length, acc_r / length))
    return smoothed


def strap_lug_points() -> tuple[tuple[float, float], ...]:
    """(theta, radius) of the two tie-down lugs on the port frame's side rails.

    These are the SAME two places the cage anchors its strap beams, so the
    webbing you see and the beam that holds the tire are one strap and not
    two. Both sit outside the opening.
    """

    radius = spec.PORT_INNER_RADIUS + (
        spec.PORT_OUTER_RADIUS - spec.PORT_INNER_RADIUS
    ) * 0.53
    offset = PORT_HALF_ANGLE + spec.PORT_BEZEL_WIDTH * 0.5 / radius
    return ((-offset, radius), (offset, radius))


def build_port(materials) -> list:
    laminate_mat = materials[f"{MOD_ID}_laminate"]
    steel_mat = materials[f"{MOD_ID}_steel"]
    deck_mat = materials[f"{MOD_ID}_deck"]
    hazard_mat = materials[f"{MOD_ID}_hazard"]

    cut = Mesh(f"{MOD_ID}_port_cut", laminate_mat)
    bezel = Mesh(f"{MOD_ID}_port_bezel", steel_mat)
    perimeter = port_perimeter(per_edge=26)
    count = len(perimeter)

    arcs: list[float] = []
    arc = 0.0
    for index, (theta, radius, _, _) in enumerate(perimeter):
        if index:
            prev_theta, prev_radius, _, _ = perimeter[index - 1]
            arc += math.hypot(
                (theta - prev_theta) * 0.5 * (radius + prev_radius), radius - prev_radius
            )
        arcs.append(arc)
    arcs.append(arc + 0.35)

    # --- Cut edge: the carcass laminate in section, right round the opening.
    # UV v runs 1 -> 0 from the CAVITY side to the ROAD side, because the
    # laminate texture is authored liner-first at array row 0, which lands at
    # the top of the image, which is UV v = 1.
    #
    # STEPPED, not flat. Round 1 spent one quad band on the whole 0.6 m
    # section - a plank with a texture on it, which is exactly what forty
    # lines of spec prose say it must not be. Each ply now sits at its own
    # slight relief, so raking light finds the laminate as geometry and the
    # texture only has to supply the material.
    steps = spec.PORT_CUT_STEPS

    def ply_relief(t: float) -> float:
        for lo, hi, relief in spec.CUT_PLIES:
            if lo <= t <= hi:
                return relief
        return 0.0

    rows = []
    for step in range(steps):
        t = step / (steps - 1)
        row = []
        for theta, radius, _, _ in perimeter:
            half, thick = sidewall_mid(radius)
            across = half - thick * 0.5 + thick * t
            row.append(cut.vertex(polar(across, radius + ply_relief(t), theta)))
        rows.append(row)
    for step in range(steps - 1):
        v0 = 1.0 - step / (steps - 1)
        v1 = 1.0 - (step + 1) / (steps - 1)
        for index in range(count):
            nxt = (index + 1) % count
            u0 = arcs[index] / TILE_SIDEWALL
            u1 = arcs[index + 1] / TILE_SIDEWALL
            uv = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
            cut.quad(
                rows[step][index], rows[step][nxt],
                rows[step + 1][nxt], rows[step + 1][index], uv, False,
            )

    # --- Bezel: a BOX SECTION ring frame, not a sheet. Inner wall on the
    # opening, a face plate standing PORT_BEZEL_PROUD off the sidewall, an
    # outer wall, and a return onto the carcass.
    width = spec.PORT_BEZEL_WIDTH
    proud = spec.PORT_BEZEL_PROUD
    depth = spec.PORT_BEZEL_DEPTH

    def grow(theta, radius, out_t, out_r, distance):
        out_radius = min(radius + out_r * distance, spec.PORT_BEZEL_MAX_RADIUS)
        return (theta + out_t * distance / max(radius, 1e-6), out_radius)

    profile = (
        (0.0, 0.0),                    # lip on the opening, at the sidewall face
        (0.0, proud),                  # up the inner wall
        (width * 0.5, proud + depth * 0.35),
        (width, proud),                # across the face plate
        (width, 0.0),                  # down the outer wall
        (width + 0.22, -0.06),         # return, tucked onto the carcass
    )
    def sill_blend(out_r):
        """1 on the SILL edge of the opening, 0 on the other three.

        The sill is the edge you drive over. A frame that stands 0.30 m proud
        there is a kerb across the doorway, and it collided with the boarding
        gangway that has to lie on top of it. Everywhere else the frame is a
        raised bolted ring; along the sill it flattens into a threshold plate.
        """

        return max(0.0, min(1.0, out_r))

    profile_walk = [0.0]
    for index in range(1, len(profile)):
        profile_walk.append(
            profile_walk[-1]
            + math.hypot(
                profile[index][0] - profile[index - 1][0],
                profile[index][1] - profile[index - 1][1],
            )
        )
    rows = []
    for distance, stand in profile:
        row = []
        for theta, radius, out_t, out_r in perimeter:
            blend = sill_blend(out_r)
            out_theta, out_radius = grow(
                theta, radius, out_t, out_r, distance * (1.0 - 0.55 * blend)
            )
            half, thick = sidewall_mid(out_radius)
            row.append(
                bezel.vertex(
                    polar(
                        half + thick * 0.5 + stand * (1.0 - 0.88 * blend),
                        out_radius,
                        out_theta,
                    )
                )
            )
        rows.append(row)
    for level in range(len(rows) - 1):
        for index in range(count):
            nxt = (index + 1) % count
            # v is the distance ALONG the box section's profile, not the
            # level index: the frame is steel and has to read at the same
            # grain as every other steel surface beside it.
            u0 = arcs[index] / TILE_STEEL
            u1 = arcs[index + 1] / TILE_STEEL
            v0 = profile_walk[level] / TILE_STEEL
            v1 = profile_walk[level + 1] / TILE_STEEL
            uv = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
            bezel.quad(
                rows[level][index], rows[level][nxt],
                rows[level + 1][nxt], rows[level + 1][index], uv,
            )

    # --- Bolts, on a bolt CIRCLE set in from the opening.
    #
    # Round 3 sat them at width * 0.5 across the profile. On the port's outer
    # edge the frame is clamped to PORT_BEZEL_MAX_RADIUS and only 0.34 m wide,
    # so "half way across" landed on the clamp boundary and the heads stood
    # out past the silhouette - 46 of them made the frame read as a cog. A
    # fixed inset from the opening keeps them on the plate all the way round,
    # and real inspection-port fasteners are smaller and closer together than
    # this than round 3 made them.
    inset = min(spec.PORT_BOLT_INSET, width * 0.55)
    for bolt in range(spec.PORT_BOLTS):
        index = int(bolt / spec.PORT_BOLTS * count) % count
        theta, radius, out_t, out_r = perimeter[index]
        blend = sill_blend(out_r)
        out_theta, out_radius = grow(
            theta, radius, out_t, out_r, inset * (1.0 - 0.55 * blend)
        )
        half, thick = sidewall_mid(out_radius)
        add_bolt(
            bezel,
            half + thick * 0.5 + (proud + depth * 0.32) * (1.0 - 0.88 * blend),
            out_radius,
            out_theta,
            spec.PORT_BOLT_ACROSS,
            spec.PORT_BOLT_HEIGHT,
        )

    # --- Radial gussets between the face plate and the carcass.
    for gusset in range(spec.PORT_GUSSETS):
        index = int((gusset + 0.5) / spec.PORT_GUSSETS * count) % count
        theta, radius, out_t, out_r = perimeter[index]
        add_gusset(bezel, theta, radius, out_t, out_r, width, proud, depth)

    # --- Lifting lugs. Placed deliberately, not spread evenly: the two SIDE
    # rails carry the tie-downs (a strap anchored anywhere else runs straight
    # across the doorway you have to drive through), and the two top corners
    # are the crane picks.
    for _theta, _radius in strap_lug_points() + (
        (-PORT_HALF_ANGLE * 0.72, spec.PORT_OUTER_RADIUS - 0.30),
        (PORT_HALF_ANGLE * 0.72, spec.PORT_OUTER_RADIUS - 0.30),
    ):
        half, thick = sidewall_mid(_radius)
        add_lift_lug(bezel, half + thick * 0.5 + spec.PORT_BEZEL_PROUD * 0.4, _radius, _theta)

    tongue_objects = build_tongue(deck_mat, hazard_mat, steel_mat)
    return [cut.build(), bezel.build()] + tongue_objects


def add_gusset(mesh: Mesh, theta: float, radius: float, out_t: float, out_r: float,
               width: float, proud: float, depth: float) -> None:
    """Stiffener wedge from the bezel face plate down onto the carcass.

    Round 2 grew these 1.2 m outward with no bound on the resulting radius, so
    every gusset on the outer edge speared straight out through the shoulder.
    The reach is now short, the radius is clamped to the same bound the bezel
    uses, and the wedge is closed rather than two loose triangles.
    """

    thickness = 0.050
    reach = 0.42

    def point(distance, stand, offset):
        out_radius = min(radius + out_r * distance, spec.PORT_BEZEL_MAX_RADIUS)
        out_theta = theta + (out_t * distance + offset) / max(radius, 1e-6)
        half, thick = sidewall_mid(out_radius)
        return polar(half + thick * 0.5 + stand, out_radius, out_theta)

    profile = (
        (width * 0.45, proud + depth * 0.30),
        (width * 0.45 + reach, 0.02),
        (width * 0.45, 0.02),
    )
    rings = []
    for offset in (-thickness, thickness):
        rings.append([mesh.vertex(point(d, s, offset)) for d, s in profile])
    scale = reach / TILE_STEEL
    uv3 = ((0.0, 0.0), (scale, 0.0), (0.0, scale))
    mesh.face(tuple(rings[1]), uv3)
    mesh.face(tuple(reversed(rings[0])), uv3)
    for index in range(3):
        nxt = (index + 1) % 3
        uv = (
            (0.0, 0.0), (scale, 0.0),
            (scale, 2.0 * thickness / TILE_STEEL), (0.0, 2.0 * thickness / TILE_STEEL),
        )
        mesh.quad(rings[0][index], rings[0][nxt], rings[1][nxt], rings[1][index], uv)


def add_lift_lug(mesh: Mesh, x: float, radius: float, theta: float) -> None:
    """A plate eye welded to the bezel: where a strap or a crane hook goes."""

    plate = 0.06
    height = spec.PORT_LUG_HEIGHT
    length = 0.40
    corners = [
        (radius - length * 0.5, x + 0.02),
        (radius + length * 0.5, x + 0.02),
        (radius + length * 0.32, x + height),
        (radius - length * 0.32, x + height),
    ]
    for offset in (-plate, plate):
        ring = [
            mesh.vertex(polar(cx + offset, cr, theta))
            for cr, cx in corners
        ]
        uv = (
            (0.0, 0.0), (length / TILE_STEEL, 0.0),
            (length / TILE_STEEL, height / TILE_STEEL), (0.0, height / TILE_STEEL),
        )
        if offset > 0:
            mesh.quad(ring[0], ring[1], ring[2], ring[3], uv)
        else:
            mesh.quad(ring[3], ring[2], ring[1], ring[0], uv)


TONGUE_HALF_ARC = math.radians(spec.TONGUE_HALF_ARC_DEG)


def tongue_station(t: float) -> tuple[float, float]:
    """(axial x, radius) along the gangway, t = 0 at the sill, 1 at the tip.

    The CAGE and the VISUAL both call this. Round 1 modelled the gangway as
    Blender meshes only and gave it no cage at all, so the drivable surface
    ended at the dock edge and resumed 0.7 m away inside the tire with
    nothing in between - a flexbody is paint, collision comes from triangles.
    """

    x = spec.LINER_HALF + (spec.TONGUE_REACH_X - spec.LINER_HALF) * t
    radius = R_CAV + (spec.TONGUE_TIP_RADIUS - R_CAV) * (t ** 1.25)
    return (x, radius)


def tongue_thickness(t: float) -> float:
    return spec.TONGUE_ROOT_THICK + (spec.TONGUE_TIP_THICK - spec.TONGUE_ROOT_THICK) * t


# Where along the gangway the dock's leading edge passes underneath, in the
# same parameter build_tongue's stations run on.
QUAY_T = (spec.DOCK_CLEAR_X - spec.LINER_HALF) / (spec.TONGUE_REACH_X - spec.LINER_HALF)


def build_tongue(deck_mat, hazard_mat, steel_mat) -> list:
    """The boarding gangway: bolted to the port sill, resting on the dock."""

    tongue = Mesh(f"{MOD_ID}_tongue", deck_mat)
    kerb = Mesh(f"{MOD_ID}_tongue_kerb", hazard_mat)
    ribs = Mesh(f"{MOD_ID}_tongue_ribs", steel_mat)

    half_arc = TONGUE_HALF_ARC
    steps = 8
    columns = 8
    thetas = [-half_arc + 2.0 * half_arc * step / columns for step in range(columns + 1)]

    station = tongue_station
    plate_thickness = tongue_thickness
    x_start = spec.LINER_HALF

    top_rows, bottom_rows = [], []
    for step in range(steps + 1):
        t = step / steps
        x, radius = station(t)
        thick = plate_thickness(t)
        top_rows.append([tongue.vertex(polar(x, radius, theta)) for theta in thetas])
        bottom_rows.append(
            [tongue.vertex(polar(x, radius + thick, theta)) for theta in thetas]
        )
    # METRIC UVs. The first cut used 0.24 per step, which put a whole diamond
    # plate tile on a 0.17 m step - 400 mm teardrops on a walkway, a metre of
    # plate per tread. Both axes are now real distances in metres.
    def uv_u(step):
        x, radius = station(step / steps)
        return math.hypot(x - x_start, radius - R_CAV) / TILE_STEEL

    def uv_v(column, step):
        _, radius = station(step / steps)
        return radius * thetas[column] / TILE_STEEL

    for step in range(steps):
        for column in range(columns):
            u0, u1 = uv_u(step), uv_u(step + 1)
            v0, v1 = uv_v(column, step), uv_v(column + 1, step)
            uv = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
            tongue.quad(
                top_rows[step][column], top_rows[step + 1][column],
                top_rows[step + 1][column + 1], top_rows[step][column + 1], uv,
            )
            tongue.quad(
                bottom_rows[step][column + 1], bottom_rows[step + 1][column + 1],
                bottom_rows[step + 1][column], bottom_rows[step][column], uv,
            )
    for step in range(steps):
        for column, direction in ((0, -1), (columns, 1)):
            uv = ((0.0, 0.0), (0.3, 0.0), (0.3, 0.2), (0.0, 0.2))
            a, b = top_rows[step][column], top_rows[step + 1][column]
            c, d = bottom_rows[step + 1][column], bottom_rows[step][column]
            if direction > 0:
                tongue.quad(a, b, c, d, uv)
            else:
                tongue.quad(d, c, b, a, uv)
    # Leading lip, so the gangway does not end in a raw edge on the landing.
    x_tip, radius_tip = station(1.0)
    for column in range(columns):
        uv = ((0.0, 0.0), (0.3, 0.0), (0.3, 0.1), (0.0, 0.1))
        tongue.quad(
            top_rows[steps][column + 1], top_rows[steps][column],
            bottom_rows[steps][column], bottom_rows[steps][column + 1], uv,
        )

    # Hazard kerbs down both sides.
    for column, direction in ((0, -1.0), (columns, 1.0)):
        theta = thetas[column]
        rows = []
        for step in range(steps + 1):
            x, radius = station(step / steps)
            rows.append(
                [
                    kerb.vertex(polar(x, radius, theta)),
                    kerb.vertex(polar(x, radius - 0.24, theta)),
                    kerb.vertex(polar(x, radius - 0.24, theta + direction * 0.014)),
                    kerb.vertex(polar(x, radius, theta + direction * 0.014)),
                ]
            )
        kerb_tile = tile_of(hazard_mat)
        for step in range(steps):
            u0 = step / steps * spec.TONGUE_REACH_X / kerb_tile
            u1 = (step + 1) / steps * spec.TONGUE_REACH_X / kerb_tile
            for corner in range(4):
                nxt = (corner + 1) % 4
                v0 = corner * 0.36 / kerb_tile
                v1 = (corner + 1) * 0.36 / kerb_tile
                uv = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
                kerb.quad(
                    rows[step][corner], rows[step + 1][corner],
                    rows[step + 1][nxt], rows[step][nxt], uv,
                )

    # Underside stiffener ribs.
    def rib_drop(t: float) -> float:
        # THE RIBS DIE BEFORE THE QUAY. The tongue's tip radius is derived so
        # its PLATE lands exactly on DOCK_LANDING_Z - but the stiffener ribs
        # hang below the plate, and they were still 75 mm deep where the
        # tongue crosses the dock's leading girder: 15 mm inside it at rest,
        # 19 mm inside the landing deck a little further out. A gangway rests
        # on a quay plate-down; its ribs stop short of it.
        fade = min(1.0, max(0.0, (QUAY_T - 0.06 - t) / 0.25))
        return 0.30 * math.sin(math.pi * min(1.0, t + 0.05)) * (1.0 - t * 0.8) * fade

    # ...and they stop where they are still a rib. Running the fade to zero
    # collapsed the box section onto its own top face for the last stations,
    # which the post-build weld then turned into five edges shared by two
    # faces pointing opposite ways - a rib that is a sheet is not a rib.
    rib_last = max(
        step for step in range(steps + 1) if rib_drop(step / steps) >= 0.020
    )
    for rib in range(spec.TONGUE_RIBS):
        theta = -half_arc + 2.0 * half_arc * (rib + 0.5) / spec.TONGUE_RIBS
        rows = []
        for step in range(rib_last + 1):
            t = step / steps
            x, radius = station(t)
            base = radius + plate_thickness(t)
            drop = rib_drop(t)
            rows.append(
                [
                    ribs.vertex(polar(x, base, theta - 0.004)),
                    ribs.vertex(polar(x, base + drop, theta - 0.004)),
                    ribs.vertex(polar(x, base + drop, theta + 0.004)),
                    ribs.vertex(polar(x, base, theta + 0.004)),
                ]
            )
        rib_tile = tile_of(steel_mat)
        for step in range(rib_last):
            u0 = step / steps * spec.TONGUE_REACH_X / rib_tile
            u1 = (step + 1) / steps * spec.TONGUE_REACH_X / rib_tile
            for corner in range(4):
                nxt = (corner + 1) % 4
                v0 = corner * 0.30 / rib_tile
                v1 = (corner + 1) * 0.30 / rib_tile
                uv = ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
                ribs.quad(
                    rows[step][corner], rows[step + 1][corner],
                    rows[step + 1][nxt], rows[step][nxt], uv,
                )
        end = rows[rib_last]
        cap_uv = ((0.0, 0.0), (0.06, 0.0), (0.06, 0.2), (0.0, 0.2))
        ribs.quad(end[3], end[2], end[1], end[0], cap_uv)
    del x_tip, radius_tip
    return [tongue.build(), kerb.build(), ribs.build()]


def add_bolt(mesh: Mesh, x: float, radius: float, theta: float,
             across: float, height: float) -> None:
    """Hex-head bolt standing off the sidewall plane at +X."""

    faces = 6
    top_ring, base_ring = [], []
    for index in range(faces):
        angle = TAU * index / faces + math.pi / 6.0
        dr = math.cos(angle) * across
        dt = math.sin(angle) * across / radius
        base_ring.append(mesh.vertex(polar(x, radius + dr, theta + dt)))
        top_ring.append(mesh.vertex(polar(x + height, radius + dr * 0.92, theta + dt * 0.92)))
    for index in range(faces):
        nxt = (index + 1) % faces
        span = across * 2.0 * math.pi / faces / TILE_STEEL
        uv = (
            (index * span, 0.0),
            ((index + 1) * span, 0.0),
            ((index + 1) * span, height / TILE_STEEL),
            (index * span, height / TILE_STEEL),
        )
        mesh.quad(base_ring[index], base_ring[nxt], top_ring[nxt], top_ring[index], uv)
    centre = mesh.vertex(polar(x + height, radius, theta))
    for index in range(faces):
        nxt = (index + 1) % faces
        span = across / TILE_STEEL
        mesh.face(
            (top_ring[index], top_ring[nxt], centre),
            ((0.0, 0.0), (span, 0.0), (span * 0.5, span)),
        )


def build_lane_marks(materials) -> list:
    """Emissive chevrons down the middle of the cavity floor.

    The inside of a closed torus whose only aperture rotates away is
    genuinely pitch black, and everything after "STRAPS CUT" happens in
    there. Round 1 shipped a near-black liner with no light and no landmark,
    so once the port passed about 40 degrees the player was driving a black
    drum with no directional cue and no way to find the exit.

    These are moulded-in emissive chevrons at LANE_MARK_EVERY stations. They
    do three jobs at once: they light the floor, they point the way round,
    and because they stream past at a rate you can read they are the only
    speed cue inside a surface with no horizon.
    """

    material = materials[f"{MOD_ID}_lane_mark"]
    mesh = Mesh(f"{MOD_ID}_lane_marks", material)
    radius = R_CAV - spec.LANE_MARK_OFFSET
    half_len = spec.LANE_MARK_LENGTH * 0.5 / radius
    half_w = spec.LANE_MARK_WIDTH * 0.5
    for index in range(0, STATIONS, spec.LANE_MARK_EVERY):
        theta = index * spec.STATION_ANGLE
        # A chevron: two arms meeting on the centre line, pointing the way the
        # tire turns when the car drives forward.
        for sign in (-1.0, 1.0):
            tip = (theta + half_len, 0.0)
            root = (theta - half_len, sign * (spec.LANE_MARK_LENGTH * 0.42))
            corners = (
                (tip[0], tip[1]),
                (root[0], root[1]),
                (root[0] - half_w / radius, root[1]),
                (tip[0] - half_w / radius * 1.6, tip[1]),
            )
            ring = [mesh.vertex(polar(x, radius, angle)) for angle, x in corners]
            tile = MATERIAL_TILE["lane_mark"]
            uv = tuple(
                (radius * angle / tile, x / tile) for angle, x in corners
            )
            if sign > 0:
                mesh.quad(ring[3], ring[2], ring[1], ring[0], uv)
            else:
                mesh.quad(ring[0], ring[1], ring[2], ring[3], uv)
    return [mesh.build()]


# ---------------------------------------------------------------------------
# Visual: moulded sidewall lettering, as real extruded geometry
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
        if side > 0 and port_open_theta(centre, band_radius):
            continue
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
            back = curve.extrude + curve.bevel_depth
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
# Visual: the loading dock (fixed structure)
# ---------------------------------------------------------------------------
def build_dock(materials) -> list:
    steel = materials[f"{MOD_ID}_steel_worn"]
    deck = materials[f"{MOD_ID}_deck"]
    hazard = materials[f"{MOD_ID}_hazard"]
    strap_mat = materials[f"{MOD_ID}_strap"]
    concrete = materials[f"{MOD_ID}_concrete"]

    objects = []
    x0 = spec.DOCK_CLEAR_X
    x1 = spec.DOCK_LANDING_X1
    x2 = spec.DOCK_RUN_X
    hy = spec.DOCK_HALF_Y
    z = spec.DOCK_LANDING_Z

    objects.append(
        bk.add_box(
            f"{MOD_ID}_dock_landing",
            ((x0 + x1) / 2.0, 0.0, z - 0.09),
            (x1 - x0, 2 * hy, 0.18),
            deck,
            bevel=0.0,
            metric_uv=(tile_of(deck), tile_of(deck)),
        )
    )
    run = x2 - x1
    ramp_len = math.hypot(run, z)
    angle = math.atan2(z, run)
    objects.append(
        bk.add_box(
            f"{MOD_ID}_dock_ramp",
            ((x1 + x2) / 2.0, 0.0, z / 2.0 - math.cos(angle) * 0.10),
            (ramp_len, 2 * hy, 0.20),
            deck,
            bevel=0.0,
            rotation=(0.0, -angle, 0.0),
            metric_uv=(tile_of(deck), tile_of(deck)),
        )
    )
    # Kerbs and handrail START AT THE LANDING'S INBOARD EDGE, not at x0. A
    # real loading dock's ship side is open - it is where the gangway lands -
    # and running them to x0 put a kerb at y = +/-4.74 and a stanchion
    # spanning z 0.78..1.88 exactly where the tongue's corner passes: at 6 deg
    # of roll, about a second after the straps cut, that corner reaches
    # y 4.750, z 1.710. It clipped on the one beat every player watches.
    kerb_x0 = x1
    for side, sy in (("l", -hy - 0.14), ("r", hy + 0.14)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_dock_kerb_{side}",
                ((kerb_x0 + x2) / 2.0, sy, z * 0.5 + spec.DOCK_KERB_H * 0.5),
                (x2 - kerb_x0, 0.24, spec.DOCK_KERB_H),
                hazard,
                bevel=0.03,
                rotation=(0.0, -angle * 0.5, 0.0),
                metric_uv=(tile_of(hazard), tile_of(hazard)),
            )
        )
        # Handrail: stanchions and two runs of tube, the whole length.
        posts = 7
        for index in range(posts):
            t = index / (posts - 1)
            px = kerb_x0 + (x2 - kerb_x0) * t
            deck_z = z if px <= x1 else max(0.0, z * (1.0 - (px - x1) / run))
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_dock_post_{side}_{index}",
                    (px, sy, deck_z + spec.DOCK_RAIL_H * 0.5),
                    (0.10, 0.10, spec.DOCK_RAIL_H),
                    steel,
                    bevel=0.01,
                    metric_uv=(tile_of(steel), tile_of(steel)),
                )
            )
        for level, height in (("top", spec.DOCK_RAIL_H), ("mid", spec.DOCK_RAIL_H * 0.55)):
            rail = bk.add_cylinder(
                f"{MOD_ID}_dock_rail_{side}_{level}",
                ((kerb_x0 + x2) / 2.0, sy, z * 0.5 + height),
                0.055,
                x2 - kerb_x0,
                steel,
                vertices=10,
                axis="X",
            )
            # add_cylinder bakes the axis rotation into the mesh, so the ramp
            # grade goes on the object transform on top of it.
            rail.rotation_euler = (0.0, -angle * 0.5, 0.0)
            objects.append(rail)
    # Under-structure.
    girders = 5
    for index in range(girders):
        t = index / (girders - 1)
        gx = x0 + (x2 - x0) * t
        gz = z if gx <= x1 else max(0.10, z * (1.0 - (gx - x1) / run))
        objects.append(
            bk.add_box(
                f"{MOD_ID}_dock_girder_{index}",
                (gx, 0.0, gz * 0.5 - 0.02),
                (0.42, 2 * hy + 0.5, max(gz - 0.04, 0.06)),
                steel,
                bevel=0.03,
                metric_uv=(tile_of(steel), tile_of(steel)),
            )
        )
        for side, sy in (("l", -hy - 0.05), ("r", hy + 0.05)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_dock_pad_{index}_{side}",
                    (gx, sy, 0.07),
                    (0.9, 0.9, 0.14),
                    concrete,
                    bevel=0.02,
                    metric_uv=(tile_of(concrete), tile_of(concrete)),
                )
            )
    # Strap anchor posts.
    for side, sy in (("l", -hy + 0.6), ("r", hy - 0.6)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_dock_anchor_{side}",
                (x0 + 1.2, sy, z + 0.30),
                0.17,
                0.90,
                steel,
                vertices=12,
                axis="Z",
            )
        )
    # Sign board at the foot of the ramp: the scale reference that tells the
    # eye how big the tire behind it is.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_dock_sign_post_l",
            (x2 - 0.6, -hy - 1.9, 1.35),
            (0.14, 0.14, 2.70),
            steel,
            bevel=0.01,
            metric_uv=(tile_of(steel), tile_of(steel)),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_dock_sign_post_r",
            (x2 - 0.6, -hy - 4.5, 1.35),
            (0.14, 0.14, 2.70),
            steel,
            bevel=0.01,
            metric_uv=(0.8, 0.8),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_dock_sign",
            (x2 - 0.6, -hy - 3.2, 2.25),
            (0.08, 2.9, 1.30),
            hazard,
            bevel=0.02,
            metric_uv=(tile_of(hazard), tile_of(hazard)),
        )
    )

    # Two ratchet straps, dock anchor to the port frame's side-rail lugs. The
    # lug positions come from the same helper the bezel and the cage use, so
    # the webbing, the eye and the beam are all one strap. They are returned
    # SEPARATELY and skinned to the carcass group: round 1 appended them into
    # the dock's object list, so the visible webbing was bound to the 16 FIXED
    # dock nodes and stayed welded to the quay after the physics beams broke -
    # two orange ribbons pointing at a tire 200 m away.
    straps = []
    for index, (theta, radius) in enumerate(strap_lug_points()):
        half, thick = sidewall_mid(radius)
        lug = polar(half + thick * 0.5 + spec.PORT_BEZEL_PROUD * 0.4 + 0.30, radius, theta)
        sy = (-hy + 0.6) if theta < 0 else (hy - 0.6)
        anchor = (x0 + 1.2, sy, z + 0.62)
        straps.extend(
            strap_ribbon(f"{MOD_ID}_strap_{index}", anchor, lug, strap_mat, steel)
        )
    return objects, straps


def strap_ribbon(name: str, start, end, webbing_mat, steel_mat) -> list:
    """A flat webbing strap with a ratchet body, start to end."""

    start_v = Vector(start)
    end_v = Vector(end)
    span = end_v - start_v
    length = span.length
    mid = (start_v + end_v) * 0.5
    direction = span.normalized()
    quat = direction.to_track_quat("X", "Z")
    strap = bk.add_box(
        name,
        tuple(mid),
        (length, 0.32, 0.024),
        webbing_mat,
        bevel=0.0,
        rotation=tuple(quat.to_euler()),
        metric_uv=(tile_of(webbing_mat), tile_of(webbing_mat)),
    )
    body = bk.add_box(
        f"{name}_ratchet",
        tuple(start_v + direction * (length * 0.30)),
        (0.44, 0.36, 0.22),
        steel_mat,
        bevel=0.02,
        rotation=tuple(quat.to_euler()),
        metric_uv=(tile_of(steel_mat), tile_of(steel_mat)),
    )
    return [strap, body]


# ---------------------------------------------------------------------------
# Physics cage
# ---------------------------------------------------------------------------
CROSS_SECTION: list[tuple[str, float, float]] = []


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


def cross_section() -> list[tuple[str, float, float]]:
    """(key, half width, radius) for the 22-node meridian, once.

    SILL is the station that makes the access port cuttable. Its radius IS
    CAVITY_RADIUS, so the port's outer edge lands on a ring of cage nodes and
    every band above it can be removed cleanly. Round 1 had no such ring, so
    the band spanning the port's outer edge stayed in the collision mesh -
    an invisible panel standing across the doorway.
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
    for label, x in zip(("lin_l", "lin_cl", "lin_c", "lin_cr", "lin_r"), spec.LINER_XS):
        entries.append((label, x, R_CAV))
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


def balance_carcass(cage: bk.CageBuilder) -> None:
    """Null the free body's first mass moment about the axle.

    THE PREMISE IS THAT IT ROLLS, and it barely did. The boarding gangway is
    {} kg bolted to the port sill at the BOTTOM of the carcass, and it stays
    bolted after the straps are cut - so the free body's centre of mass sat
    0.922 m off the axle. That is a 102 kNm gravity pendulum against roughly
    123 kNm of drive torque from a car pushing the liner: the tire climbs its
    own imbalance and rocks back rather than rolling away, which is exactly
    what the live gate's 7.40 m of travel (31.6 degrees of rotation) was.

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
        if not node["fixed"] and "tongue" not in node["id"]
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

    # Two shape functions, both mean-zero over a symmetric ring: the vertical
    # first harmonic (which is the balance patch) and the axial one.
    def shapes(node):
        x, _y, dz = offset(node)
        return (dz / spec.OUTER_RADIUS, x / spec.SECTION_HALF)

    rider_mass = sum(node["weight"] for node in rider)
    rider_moment = [
        sum(node["weight"] * offset(node)[axis] for node in rider) for axis in (0, 2)
    ]

    # Solve [c, a, b] for: total mass, axial moment, vertical moment.
    matrix = [[0.0] * 3 for _ in range(3)]
    target = [spec.TIRE_MASS, -rider_moment[0], -rider_moment[1]]
    for node in carcass:
        weight = node["weight"]
        vertical, axial = shapes(node)
        basis = (1.0, vertical, axial)
        dx, _dy, dz = offset(node)
        for column in range(3):
            matrix[0][column] += weight * basis[column]
            matrix[1][column] += weight * basis[column] * dx
            matrix[2][column] += weight * basis[column] * dz

    solution = _solve3(matrix, target)
    if solution is None:
        raise SystemExit("the carcass balance system is singular")
    scale, vertical_gain, axial_gain = solution

    lowest = highest = None
    for node in carcass:
        vertical, axial = shapes(node)
        factor = scale + vertical_gain * vertical + axial_gain * axial
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
        f"{free:.1f} kg, centre of mass {math.hypot(moment[0], moment[1]) / free * 1000:.1f} mm "
        f"from the axle"
    )


def _solve3(matrix, target):
    """Gaussian elimination with partial pivoting on a 3x3 system."""

    rows = [list(matrix[index]) + [target[index]] for index in range(3)]
    for column in range(3):
        pivot = max(range(column, 3), key=lambda r: abs(rows[r][column]))
        if abs(rows[pivot][column]) < 1e-12:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for other in range(3):
            if other == column:
                continue
            factor = rows[other][column] / rows[column][column]
            for index in range(column, 4):
                rows[other][index] -= factor * rows[column][index]
    return [rows[index][3] / rows[index][index] for index in range(3)]


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    for name, values in spec.BEAM_SPECS.items():
        cage.define_beam_spec(
            name, beamDeform="FLT_MAX", beamStrength="FLT_MAX", **values
        )
    cage.define_beam_spec("dock", **spec.DOCK_BEAM)
    cage.define_beam_spec("strap", **spec.STRAP_SPEC)
    cage.define_beam_spec("landing", **spec.LANDING_SPEC)

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

    port_columns = {station % STATIONS for station in range(-2, 3)}

    # The bolted ring frame REPLACES the carcass beams it runs along; it does
    # not sit beside them. Collect its edges first so the one beam that spans
    # each pair is emitted once, in the port_frame family. (Adding a second
    # beam over the same pair is what CageBuilder refuses, and rightly -
    # doubled beams double the stiffness silently.)
    frame_edges: set[frozenset[str]] = set()
    port_ring = ("low_r", "max_r", "upp_r", "sill_r")
    for station in port_columns:
        for index in range(len(port_ring) - 1):
            frame_edges.add(
                frozenset((ids[(port_ring[index], station)], ids[(port_ring[index + 1], station)]))
            )
        following = (station + 1) % STATIONS
        if following in port_columns:
            for key in port_ring:
                frame_edges.add(frozenset((ids[(key, station)], ids[(key, following)])))

    def beam(key_a, station_a, key_b, station_b, family, extra=None):
        first = ids[(key_a, station_a % STATIONS)]
        second = ids[(key_b, station_b % STATIONS)]
        if frozenset((first, second)) in frame_edges:
            family = "port_frame"
        cage.add_beam(first, second, family, extra=extra)

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

        # --- Bolted port ring frame. The edges themselves were claimed above;
        # what is left is the lin_r member, which no carcass beam covers.
        if station in port_columns:
            for index in range(len(port_ring) - 1):
                beam(port_ring[index], station, port_ring[index + 1], station, "port_frame")
            following = (station + 1) % STATIONS
            if following in port_columns:
                for key in port_ring:
                    beam(key, station, key, following, "port_frame")

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
            # Over the port sector the boarding gangway IS this surface.
            if sign > 0 and station in PORT_QUADS:
                continue
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
                radius_lo = section[[k for k, _, _ in section].index(chain[index])][2]
                radius_hi = section[[k for k, _, _ in section].index(chain[index + 1])][2]
                if sign > 0 and port_open_at(station, radius_lo, radius_hi):
                    continue
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
    # The dock: fixed steel, and the two straps that make this one cage.
    # -----------------------------------------------------------------------
    x0 = spec.DOCK_CLEAR_X
    x1 = spec.DOCK_LANDING_X1
    x2 = spec.DOCK_RUN_X
    hy = spec.DOCK_HALF_Y
    z = spec.DOCK_LANDING_Z
    dock: dict[tuple[str, int], str] = {}
    columns = [(x0, z), (x1, z), (0.5 * (x1 + x2), z * 0.5), (x2, 0.0)]
    for index, (dx, dz) in enumerate(columns):
        for side, sy in (("l", -hy), ("r", hy)):
            deck = cage.add_node(
                f"dock_{side}_{index}", (dx, sy, dz), fixed=True, collision=True, weight=400.0
            )
            dock[("deck_" + side, index)] = deck
            # At the ramp's ground end the deck IS the ground, so there is no
            # second node to put under it - authoring one anyway produced a
            # zero-length beam, which the pack's jbeam gate rejects outright.
            if dz > 0.25:
                dock[("base_" + side, index)] = cage.add_node(
                    f"dock_base_{side}_{index}", (dx, sy, 0.0), fixed=True,
                    collision=True, weight=400.0,
                )
            else:
                dock[("base_" + side, index)] = deck
    for index in range(len(columns)):
        cage.add_beam(dock[("deck_l", index)], dock[("deck_r", index)], "dock")
        cage.add_beam(dock[("base_l", index)], dock[("base_r", index)], "dock")
        for side in ("l", "r"):
            cage.add_beam(dock[(f"deck_{side}", index)], dock[(f"base_{side}", index)], "dock")
        if index:
            for side in ("l", "r"):
                cage.add_beam(
                    dock[(f"deck_{side}", index - 1)], dock[(f"deck_{side}", index)], "dock"
                )
                cage.add_beam(
                    dock[(f"base_{side}", index - 1)], dock[(f"base_{side}", index)], "dock"
                )
                cage.add_beam(
                    dock[(f"base_{side}", index - 1)], dock[(f"deck_{side}", index)], "dock"
                )
            cage.add_beam(dock[("deck_l", index - 1)], dock[("deck_r", index)], "dock")
            cage.add_beam(dock[("deck_r", index - 1)], dock[("deck_l", index)], "dock")
    for index in range(len(columns) - 1):
        # Route it through the SAME guard the tire's own surfaces use. Round 1
        # called add_quad directly and the corner order walked -y then +x,
        # whose cross product is -Z: all six triangles faced down, and a
        # jbeam coltri only collides from its front face.
        add_oriented_quad(
            cage,
            [
                dock[("deck_l", index)],
                dock[("deck_r", index)],
                dock[("deck_r", index + 1)],
                dock[("deck_l", index + 1)],
            ],
            Vector((0.0, 0.0, 1.0)),
            ground_model="metal",
        )

    # The tie-downs. Station +-2 is the port frame's side rail (the port spans
    # +-2 stations), and max_r there is the cage node under the lifting lug the
    # visible webbing hooks - so the strap you see and the beam that holds the
    # Colossus down are the same strap, pulling in the same direction.
    for station in (-2, 2):
        cage.add_beam(
            dock[("deck_l" if station < 0 else "deck_r", 0)],
            ids[("max_r", station % STATIONS)],
            "strap",
            extra={"breakGroup": spec.STRAP_BREAK_GROUP},
        )

    # -----------------------------------------------------------------------
    # The boarding gangway, as real physics. Free nodes on the carcass, so it
    # is drivable AND it lifts away with the tire when the straps are cut.
    # -----------------------------------------------------------------------
    columns_n = spec.TONGUE_CAGE_COLUMNS
    rows_n = spec.TONGUE_CAGE_ROWS
    tongue: dict[tuple[int, int], str] = {}
    # Provisional; the real per-node share is set once the grid is built,
    # because reuse_or_add folds two of the eighteen slots onto liner nodes
    # that already exist and dividing by the slot count silently lost 100 kg.
    tongue_mass = spec.GANGWAY_MASS / (columns_n * rows_n)
    # The gangway's half arc is exactly half the port span, so its root row's
    # end columns land ON the liner-edge nodes at the port's boundary
    # stations. Those are the same point, and the gangway really is bolted to
    # the sill there - so REUSE the cage node rather than authoring a second
    # one on top of it, which would be a zero-length beam.
    existing = {
        identifier: cage.nodes[index]["source_world_position"]
        for identifier, index in cage.node_index.items()
    }

    def reuse_or_add(name, point):
        for identifier, other in existing.items():
            if math.dist(point, other) < 0.01:
                return identifier
        return cage.add_node(
            name,
            point,
            fixed=False,
            collision=True,
            weight=tongue_mass,
            friction=0.85,
            node_material="|NM_METAL",
            group="carcass",
        )

    for row in range(rows_n):
        t = row / (rows_n - 1)
        tx, tradius = tongue_station(t)
        for column in range(columns_n):
            theta = -TONGUE_HALF_ARC + 2.0 * TONGUE_HALF_ARC * column / (columns_n - 1)
            tongue[(row, column)] = reuse_or_add(
                f"tongue_r{row}_c{column}", polar(tx, tradius, theta)
            )
    # THE GANGWAY WEIGHS WHAT IT WEIGHS. Spread spec.GANGWAY_MASS over the
    # nodes that were actually created, not over the grid slots that were
    # asked for.
    tongue_ids = sorted(set(tongue.values()) - set(existing))
    for identifier in tongue_ids:
        cage.nodes[cage.node_index[identifier]]["weight"] = (
            spec.GANGWAY_MASS / len(tongue_ids)
        )

    def link(first, second, family):
        """Add a beam unless the carcass already claims that pair.

        The gangway reuses the liner-edge nodes at the port boundary, so some
        of its bolts land on pairs the carcass has already joined with its own
        family. Re-adding them would be a doubled beam - silently twice the
        stiffness - which CageBuilder rightly refuses.
        """

        key = (min(first, second), max(first, second))
        if first == second or key in cage.beams:
            return
        cage.add_beam(first, second, family)

    for row in range(rows_n):
        for column in range(columns_n):
            if column:
                link(tongue[(row, column - 1)], tongue[(row, column)], "gangway")
            if row:
                link(tongue[(row - 1, column)], tongue[(row, column)], "gangway")
            if row and column:
                link(tongue[(row - 1, column - 1)], tongue[(row, column)], "gangway")
                link(tongue[(row - 1, column)], tongue[(row, column - 1)], "gangway")
    # Bolt the root row into the port sill ring and the liner edge.
    for column in range(columns_n):
        theta = -TONGUE_HALF_ARC + 2.0 * TONGUE_HALF_ARC * column / (columns_n - 1)
        nearest = int(round(theta / spec.STATION_ANGLE)) % STATIONS
        for key in ("sill_r", "lin_r"):
            link(tongue[(0, column)], ids[(key, nearest)], "port_frame")
        link(tongue[(1, column)], ids[("sill_r", nearest)], "gangway")
    # Landing struts. The gangway "rests on the dock landing the way a ship's
    # gangway rests on a quay" - but the tongue and the dock are nodes of the
    # SAME jbeam vehicle, and BeamNG only tests a node against its own
    # vehicle's triangles when selfCollision is set. It is not, so nothing was
    # holding the tongue up at all. Authoring the resting as two struts in the
    # tie-down break group makes it a real bridge that is carried while it is
    # strapped and swings away with the tire the moment it is cut, which is
    # both the honest physics and the fiction.
    #
    # FOUR NEAR-VERTICAL POSTS, not two diagonals. The struts used to run from
    # the tongue's two outer corners across to deck_l/deck_r[0] at y = +/-4.6:
    # a vertical direction cosine of 0.383, nothing at all under the middle,
    # and selfCollision is false so the tongue could not rest on the deck it
    # is lying over. The mid-span sagged onto the terrain and left a step in
    # the middle of the boarding centreline. The landing pads sit on the quay
    # DIRECTLY BENEATH the tongue's tip row, which is what a gangway rests on.
    landing_columns = (0, 2, 3, columns_n - 1)
    tip_x, tip_radius = tongue_station(1.0)
    for column in landing_columns:
        theta = -TONGUE_HALF_ARC + 2.0 * TONGUE_HALF_ARC * column / (columns_n - 1)
        point = polar(tip_x, tip_radius, theta)
        pad = cage.add_node(
            f"dock_pad_{column}",
            (tip_x, point[1], spec.DOCK_LANDING_Z),
            fixed=True,
            collision=False,
            weight=400.0,
        )
        # Tie the pad into the deck lattice it stands on, and down to grade,
        # so it is a part of the quay rather than a floating anchor.
        cage.add_beam(pad, dock[("deck_l", 0)], "dock")
        cage.add_beam(pad, dock[("deck_r", 0)], "dock")
        cage.add_beam(pad, dock[("deck_l", 1)], "dock")
        cage.add_beam(pad, dock[("deck_r", 1)], "dock")
        cage.add_beam(
            tongue[(rows_n - 1, column)],
            pad,
            "landing",
            extra={"breakGroup": spec.STRAP_BREAK_GROUP},
        )

    for row in range(rows_n - 1):
        for column in range(columns_n - 1):
            add_oriented_quad(
                cage,
                [
                    tongue[(row, column)],
                    tongue[(row, column + 1)],
                    tongue[(row + 1, column + 1)],
                    tongue[(row + 1, column)],
                ],
                Vector((0.0, 0.0, 1.0)),
                ground_model="metal",
            )

    # -----------------------------------------------------------------------
    # Clear the doorway. port_open_at gates the SKIN, and a node keeps
    # colliding after its skin is gone - BeamNG tests node spheres as well as
    # triangles. Round 2 left nine collidable nodes standing in the opening,
    # one of them at y = 0, 0.47 m above the sill: a car driving in hit an
    # invisible post in the middle of the door. The nodes and their port_frame
    # beams stay, because they are the bolted ring that holds the opening
    # open; only their collision comes off.
    cleared = 0
    interior = {station % STATIONS for station in range(-1, 2)}
    for key in ("low_r", "max_r", "upp_r"):
        for station in interior:
            node = cage.nodes[cage.node_index[ids[(key, station)]]]
            node["collision"] = False
            cleared += 1
    print(f"COLOSSUS doorway: {cleared} nodes taken out of the collision set")

    # A PROPER TRIAD. The engine builds the prop's reported orientation from
    # the three edges ref->back, ref->left, ref->up, so they have to be
    # independent and each dominant along its own axis. Round 2 reused deck
    # corners: ref->left came out (0, +4.6, 0), exactly parallel to ref->back,
    # and ref->up came out 94% along +X. Two purpose-built datum nodes cost
    # nothing and make the basis unambiguous.
    # -X, NOT +X. Measured across all 23 shipped jbeams, 22 return
    # left - ref = +X in vehicle space and one sign of
    # cross(left - ref, back - ref) . (up - ref); colossus alone returned the
    # opposite of both, because the pipeline yaws the authored frame 180 deg.
    # BeamNG builds the spawn basis from this table, so the prop could spawn
    # mirrored with the dock, the port and the whole boarding approach on the
    # wrong side - and the runtime's propFrame maps authored baselines onto
    # live ones using the same roles on both sides, so nothing downstream
    # would ever have reported it.
    datum_left = cage.add_node(
        "ground_left", (x2 - 3.2, 0.0, 0.0), fixed=True, collision=False, weight=200.0
    )
    datum_up = cage.add_node(
        "ground_up", (x2, 0.0, 1.6), fixed=True, collision=False, weight=200.0
    )
    for anchor in (datum_left, datum_up):
        cage.add_beam(anchor, dock[("deck_l", 3)], "dock")
        cage.add_beam(anchor, dock[("deck_r", 3)], "dock")
    cage.add_beam(datum_left, datum_up, "dock")
    cage.set_ground_reference(
        (x2, 0.0, 0.0),
        (x2, -3.0, 0.0),
        left=datum_left,
        up=datum_up,
        support_nodes=[
            dock[("deck_l", 3)],
            dock[("deck_r", 3)],
            dock[("base_l", 2)],
            dock[("base_r", 2)],
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
            dock[("deck_l", 3)],
            dock[("deck_r", 3)],
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
    ("sidewall_outer", "away_from_centre_plane"),
    ("_shoulder", "away_from_shell"),
    ("sidewall_inner", "toward_centre_plane"),
    ("liner_crown", "toward_axle"),
    ("liner_fillet", "into_cavity"),
    ("tread_base", "away_from_axle_radial_only"),
    ("tread_lugs", "away_from_axle_radial_only"),
    ("tread_tiebars", "away_from_axle_radial_only"),
    ("tread_ejectors", "away_from_axle_radial_only"),
    # The buttress wrap lies on the SIDEWALL, so it faces outboard, not out
    # from the axle - the tread rule would judge it against the wrong normal.
    ("tread_buttress", "away_from_shell"),
    ("bead_toe", "toward_axle"),
    ("lane_marks", "toward_axle"),
    ("print_band", "away_from_centre_plane"),
)

# Objects with no radial or shell reference to test against: closed solids
# built as loops (bolts, lift lugs, the bezel box section), flat plates whose
# "outward" is their own local up (the gangway, the dock), and the extruded
# type, whose back cap sits flush on a surface that is itself checked. Each is
# listed on purpose; an object that is neither ruled nor exempt fails the
# build rather than being waved through.
ORIENTATION_EXEMPT = (
    "_letter_",
    "_port_bezel",
    "_port_cut",
    "_tongue",
    "_strap",
    "_dock_",
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
        for polygon in obj.data.polygons:
            centre = matrix @ polygon.center
            normal = normal_matrix @ polygon.normal
            radial = Vector((0.0, centre.y - axle.y, centre.z - axle.z))
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

    Six decimals is a micrometre on a 28 m tire and 1e-6 on a unit normal:
    far below anything the engine, the gates or the eye can resolve, and it
    makes the file a function of the source rather than of the run.
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


# The six surfaces that between them ARE the carcass. Welded, they have to
# close: a tire is a closed shell with one hole in it, and that hole is the
# access port.
CLOSED_SHELL = (
    "_sidewall_outer", "_sidewall_inner", "_bead_toe",
    "_liner_crown", "_liner_fillet", "_shoulder", "_tread_base",
)


def assert_shell_rings_close(tire_objects) -> None:
    """The carcass is closed everywhere except the doorway.

    THE GATE THAT WOULD HAVE CAUGHT ROUND 3. Every check in this file measured
    constants and row tables; none of them looked at whether the surfaces
    actually MET. Three separate defects hid behind that: the shoulder loft
    started 0.0671 m inboard of the ring the lathe ended on, leaving an open
    annulus 84.85 m long round each shoulder that culled straight to sky; the
    inner lathe ran 0.93 m past the cavity floor; and the buttress wrap's top
    rows floated off the surface entirely. A boundary-edge count on the welded
    shell sees all three, and it will see the next one too.

    Open edges are legal ONLY in the port sector - the doorway itself, and the
    slot in the shoulder fillet the boarding gangway comes through.
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

    door_half = math.radians(spec.PORT_SPAN_DEG * 0.5) + math.radians(4.0)
    stray_length = 0.0
    worst = None
    for edge in master.edges:
        if len(edge.link_faces) != 1:
            continue
        allowed = True
        for vertex in edge.verts:
            point = vertex.co
            radius = math.hypot(point.y, R_O - point.z)
            theta = math.atan2(point.y, R_O - point.z)
            if not (
                point.x > 0.0
                and abs(theta) <= door_half
                and radius <= spec.PORT_OUTER_RADIUS + 0.40
            ):
                allowed = False
        if allowed:
            continue
        length = edge.calc_length()
        stray_length += length
        if worst is None or length > worst[0]:
            mid = 0.5 * (edge.verts[0].co + edge.verts[1].co)
            worst = (length, mid)
    master.free()

    if stray_length > 0.05:
        _, mid = worst
        radius = math.hypot(mid.y, R_O - mid.z)
        raise SystemExit(
            f"the carcass has {stray_length:.2f} m of open boundary outside the "
            f"doorway - it is not a closed shell. Worst near x {mid.x:.3f}, "
            f"radius {radius:.3f}, theta {math.degrees(math.atan2(mid.y, R_O - mid.z)):.1f} deg"
        )
    print("COLOSSUS carcass: closed everywhere except the doorway")


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

    wrap_worst = 0.0
    for obj in tire_objects:
        if "_tread_buttress" not in obj.name:
            continue
        for vertex in obj.data.vertices:
            point = obj.matrix_world @ vertex.co
            radius = math.hypot(point.y, R_O - point.z)
            gap = abs(point.x) - outer_half_at(radius)
            # The wrap stands BUTTRESS_RELIEF proud on its outer face; only
            # its inner face is expected to lie on the surface, so this bounds
            # how far the whole wrap can be off it, not how thick it is.
            if gap < 0.0:
                wrap_worst = min(wrap_worst, gap)
    if wrap_worst < -0.005:
        raise SystemExit(
            f"the buttress wrap sinks {-wrap_worst * 1000:.0f} mm into the shoulder "
            f"it is supposed to lie on"
        )
    print(
        f"COLOSSUS surfaces: liner tops out at radius {liner_worst:.3f} "
        f"(cavity floor {spec.CAVITY_RADIUS:.3f})"
    )


SWEPT_BINS = 512


def swept_profile(tire_objects, crossing=("_tongue", "_strap")) -> list:
    """Half width the tire occupies at each radius from the axle, as built.

    This is the shape that actually sweeps past the dock. The tire is a solid
    of revolution about the axle, so a vertex at radius r and half width |x|
    will, at some point in the roll, be at EVERY point of the circle of radius
    r - which is why the constant-plane test was answering a question nobody
    asked. Binned by radius so the answer is a profile, not a single number.
    """

    profile = [0.0] * (SWEPT_BINS + 1)
    for obj in tire_objects:
        if any(fragment in obj.name for fragment in crossing):
            continue
        matrix = obj.matrix_world
        for vertex in obj.data.vertices:
            point = matrix @ vertex.co
            radius = math.hypot(point.y, R_O - point.z)
            index = min(SWEPT_BINS, int(radius / R_O * SWEPT_BINS))
            profile[index] = max(profile[index], abs(point.x))
    # Dilate by one bin either way: a dock vertex landing on a bin boundary
    # must answer to the widest tire section that can reach it.
    return [
        max(profile[max(0, index - 1):min(len(profile), index + 2)])
        for index in range(len(profile))
    ]


def assert_outboard_clearance(tire_objects, dock_objects,
                              crossing=("_tongue", "_strap")) -> None:
    """Nothing FIXED may enter the volume the tire sweeps as it rolls past.

    DOCK_CLEAR_X is the whole reason the dock survives the first revolution,
    and rounds 2 and 3 defended the CONSTANT: they measured the tire against
    5.675 and stopped. The dock's own geometry never answered to it - the
    first girder reaches 5.465 and its pier pads 5.225, both inboard of the
    plane spec.py says everything fixed lives outboard of, and inboard of the
    port bezel's own reach. They are in fact clear, because at the radius
    where they sit the tire is only 4.65 m wide, but nothing here knew that.
    This measures the real swept solid against the real dock and reports the
    true minimum approach.

    Two things cross on purpose and are exempt: the boarding gangway, which
    lifts away on the first quarter turn, and the tie-down webbing, which
    spans tire to dock by definition. Both are in the release break group.
    """

    profile = swept_profile(tire_objects, crossing)
    reach = max(profile)
    worst = None
    for obj in dock_objects:
        matrix = obj.matrix_world
        for vertex in obj.data.vertices:
            point = matrix @ vertex.co
            radius = math.hypot(point.y, R_O - point.z)
            index = min(SWEPT_BINS, int(radius / R_O * SWEPT_BINS))
            tire_half = profile[index] if radius <= R_O else 0.0
            margin = abs(point.x) - tire_half
            if worst is None or margin < worst[0]:
                worst = (margin, obj.name, radius, abs(point.x), tire_half)
    if worst is None:
        raise SystemExit("no dock geometry to check clearance against")
    margin, name, radius, dock_x, tire_half = worst
    if margin <= 0.0:
        raise SystemExit(
            f"{name} sits {-margin:.3f} m INSIDE the tire's swept volume "
            f"(|x| {dock_x:.3f} against a {tire_half:.3f} m half width at radius "
            f"{radius:.3f}); the first revolution would destroy it"
        )
    print(
        f"COLOSSUS outboard reach: {reach:.3f} m; nearest fixed approach "
        f"{margin:.3f} m ({name} at radius {radius:.2f})"
    )


def assert_tongue_sweep(tire_objects, dock_objects) -> None:
    """The gangway swings away through 90 degrees without touching the quay.

    The tongue is the ONE piece of tire geometry allowed outboard of the
    clearance plane, so it is the one piece whose swept arc has to be checked
    explicitly - and nothing did. At 6 degrees of roll, about a second after
    the straps cut, its corner reached y 4.750, z 1.710: through the dock kerb
    at y +/-4.74 and through the first stanchion's z span, on the beat the
    whole prop is built around.
    """

    boxes = []
    for obj in dock_objects:
        matrix = obj.matrix_world
        points = [matrix @ vertex.co for vertex in obj.data.vertices]
        if not points:
            continue
        boxes.append((
            obj.name,
            min(p.x for p in points), max(p.x for p in points),
            min(p.y for p in points), max(p.y for p in points),
            min(p.z for p in points), max(p.z for p in points),
        ))
    steps = 90
    worst = None
    for obj in tire_objects:
        if "_tongue" not in obj.name:
            continue
        matrix = obj.matrix_world
        for vertex in obj.data.vertices:
            point = matrix @ vertex.co
            radius = math.hypot(point.y, R_O - point.z)
            angle0 = math.atan2(point.y, R_O - point.z)
            for step in range(steps + 1):
                angle = angle0 + math.radians(step)
                y = radius * math.sin(angle)
                z = R_O - radius * math.cos(angle)
                for name, x0, x1, y0, y1, z0, z1 in boxes:
                    if not (x0 <= point.x <= x1):
                        continue
                    if not (y0 <= y <= y1 and z0 <= z <= z1):
                        continue
                    depth = min(y - y0, y1 - y, z - z0, z1 - z)
                    # Surfaces that TOUCH are the point - the gangway rests on
                    # the quay. Only real penetration is a failure.
                    if depth < 0.008:
                        continue
                    if worst is None or depth > worst[0]:
                        worst = (depth, obj.name, name, step, y, z)
    if worst is not None:
        depth, tongue_name, dock_name, step, y, z = worst
        raise SystemExit(
            f"{tongue_name} sweeps {depth * 1000:.0f} mm into {dock_name} at "
            f"{step} deg of roll (y {y:.3f}, z {z:.3f}); the gangway would tear "
            f"the dock apart on its way up"
        )
    print("COLOSSUS gangway sweep: clear of every fixed object through 90 deg")


def assert_authored_claims(cage) -> None:
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

    # Radius of gyration and the spin-up the mass solve promises.
    inertia = mass = 0.0
    for node in cage.nodes:
        if node["fixed"]:
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
    tire_objects += build_port(materials)
    tire_objects += build_lane_marks(materials)
    tire_objects += build_print_band(materials)
    tire_objects += build_lettering(materials)
    dock_objects, strap_objects = build_dock(materials)
    # The webbing rides away with the carcass, not with the quay.
    tire_objects += strap_objects

    swept = clean_degenerates(tire_objects + dock_objects)
    assert_face_orientation(tire_objects)
    assert_outboard_clearance(tire_objects, dock_objects)
    assert_tongue_sweep(tire_objects, dock_objects)
    assert_shell_rings_close(tire_objects)
    assert_surfaces_stay_home(tire_objects)

    dropped = sum(getattr(obj, "_dropped", 0) for obj in tire_objects)
    triangles = sum(
        max(len(polygon.vertices) - 2, 0)
        for obj in tire_objects + dock_objects
        for polygon in obj.data.polygons
    )
    print(
        f"COLOSSUS visual triangles: {triangles} "
        f"(degenerate dropped: {dropped}, swept after build: {swept})"
    )

    dae_path = VEHICLE_DIR / f"{MOD_ID}.dae"
    visual = bk.export_multi_flexbody(
        MOD_ID,
        dae_path,
        {
            f"{MOD_ID}_visual": dock_objects,
            f"{MOD_ID}_carcass": tire_objects,
        },
    )
    # Re-hash AFTER normalising, or the handoff certifies bytes that are no
    # longer on disk.
    visual.update(normalise_collada(dae_path))

    cage = build_cage()
    free_mass = sum(
        node["weight"] for node in cage.nodes if not node["fixed"] and "tongue" not in node["id"]
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
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(36.0, -36.0, 15.0),
        look_at=(0.0, 0.0, 12.0),
    )
    print("COLOSSUS generator complete")


if __name__ == "__main__":
    main()
