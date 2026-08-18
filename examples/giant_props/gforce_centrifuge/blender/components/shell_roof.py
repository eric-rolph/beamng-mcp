"""White flowing shell roof — CHIEF facility design language.

A CLOSED-SOLID annular tensile shell.  A single generator surface — the
WARPED top sheet — is defined analytically, and everything else is hung
off its own moving frame (P, N, Tr):

    top sheet   P                      rolled inner rim (r 12.25, z 9.20),
                                       tensioned crest r 17.80 / z 11.50,
                                       eave r 24.85 / z 7.60
    eave roll   tangent semicircle in the (N, Tr) plane at r 24.85
    underside   P - thickness * N, outer -> inner
    rim roll    tangent semicircle in the (N, Tr) plane at r 12.25

The loop closes, so the mesh is a watertight torus-topology solid that
reads correctly from above, from the side, and from a car underneath.

THE SECTION IS A TRUE S, NOT A BELL.  The crest is pulled INBOARD to
r 17.80 so the long taut drape lives outboard (7.05 m of fall against a
5.55 m rise), and the outer limb carries a genuine INFLECTION: the slope
steepens to about -0.73 m/m near r 21.5, then RELAXES to -0.33 m/m at the
hem.  A monotonically steepening limb (the previous revision) is a dome
section and reads as an inflatable float; the flattening hem is what makes
it read as stretched fabric pinned at the edge.  The inner rim is a real
0.65 m reversal (crown 9.20 at r 12.25, valley 8.55 at r 13.70) so the
sheet visibly turns UP into the aperture instead of dishing into it.

Radial stations are sampled by ARC LENGTH along the S profile, so the
crest and the rim reversal get as many rings as the flat drape does and
the surface shades as one continuous sheet.

On the -Y azimuth the whole outer drape LIFTS into an entry swoop.  The
window is a 76 deg sector whose radial onset is at r 18.80 — just outboard
of the crest — with an x**1.5 falloff, so the entire outer wing sweeps up
as ONE gesture instead of blistering a local hump in the hem.  The swoop
also PUSHES the plan-form out by 0.95 m, so the silhouette bulges toward
the entry (r 25.90 at the crown of the drip edge, clear of r 26) rather
than being a perfect circle that only moves in Z.

Two 9.0 x 4.5 m oval oculi are cut at azimuth 60 and 200 deg around r 19
with an EXACT boolean against analytic elliptical prisms.  The 2:1 ratio
is what makes them read as oculi rather than portholes.  The rolled lip is
a tube whose axis sits at MID-THICKNESS of the shell and is offset outward
by sqrt(R^2 - drop^2) along the surface, so it covers both cut edges and
still stands 0.17 m PROUD of the sheet, catching a highlight along the rim.
(The boolean prism is vertical, so the two cut edges are separated
vertically rather than along the normal; on the outer flank of an opening
that is a ~0.03 m mismatch, well inside the 0.30 m bead.)

Panelization is INSET into the shell — 16 primary meridians, 16 secondary
meridians outboard of the third parallel, and 4 parallels, each only
0.022 m deep with a SHELF ring/station 0.090 m out that confines the
shading gradient so panels stay flat.  The inset is applied to the WHOLE
cross-section (top sheet, both rolls, underside) along the surface normal,
which means a seam is a continuous fold that runs from the inner bead to
the drip edge and never dies in the middle of a panel.  The secondary
meridians begin exactly ON the third parallel — a seam terminating on a
ring beam reads as intent; one terminating mid-field reads as a bug.
"""

from __future__ import annotations

import bisect
import math

import bpy

import spec
from proplib import blender_kit as bk

PREFIX = f"{spec.MOD_ID}_shell_roof"

# ---------------------------------------------------------------- geometry
NA = 96  # base azimuth rings (multiple of N_MERIDIANS and of 2*N_MERIDIANS)
NR = 38  # radial samples on the TOP surface (by arc length)
R_IN, R_EAVE = 12.35, 24.85

# Elegant S profile (r, z).
#
#   inner rim   crown 9.20 -> valley 8.55  (a 0.65 m UPTURN, legible at 50 m)
#   rise        valley -> crest, steepest ~1.0 m/m
#   crest       17.80 / 11.50, straddled symmetrically by 17.35 / 18.25 at
#               the same height so the Catmull-Rom tangent there is exactly
#               horizontal and the true maximum lands on the control point
#   outer limb  slopes -0.46, -0.54, -0.73, -0.64, -0.56, -0.33
#               ^ steepens to r ~21.5 then RELAXES: the inflection that
#                 turns a bell section into an S.
PROFILE_CTRL = [
    (12.35, 9.20),  # upturned inner rim (bead bottoms out at r 12.10)
    (13.70, 8.55),  # valley — a real reversal, not a 0.17 m dimple
    (15.10, 9.25),
    (16.45, 10.35),
    (17.35, 11.28),
    (17.80, 11.50),  # crest, pulled INBOARD so the drape is outboard
    (18.25, 11.28),
    (19.40, 10.75),
    (20.80, 10.00),
    (22.10, 9.05),  # steepest limb
    (23.20, 8.35),
    (24.10, 7.85),
    (24.85, 7.60),  # hem: shallowest slope of the whole limb
]

# Shell thickness: a slim rolled bead at the inner rim, thinner at the eave.
THICK_IN, THICK_OUT = 0.34, 0.20

# ------------------------------------------------------------- entry swoop
SWOOP_AZ = math.radians(270.0)  # -Y entry azimuth
SWOOP_HALF = math.radians(42.0)  # 84 degree sector — one wing, not a bump
SWOOP_LIFT = 2.40  # eave 7.60 -> 10.00 on the centreline
SWOOP_R0 = 18.80  # onset just outboard of the crest: the WHOLE drape lifts
SWOOP_POW = 1.5  # softer than x**2 -> the lift is a sweep, not a hook
# Outward push at the swoop: the plan-form flares toward the entry.  The
# eave roll is swept in the WARPED tangent plane, and in the swoop that
# plane is horizontal, so the roll crown reaches its full radius outboard
# instead of tucking under.  Budget: 24.85 + 0.95 + 0.10 = 25.90 < 26.
# (Verified by the extents print in _build_shell.)
PUSH_MAX = 0.95

# ------------------------------------------------------------------ oculi
OCULI_AZ = (math.radians(60.0), math.radians(200.0))
# Radial centre of the openings.  Kept OUTBOARD of the r 17.80 crest: with
# OC_B 2.25 an opening centred on r 19 would span r 16.75..21.25 and eat a
# 9 m bite straight out of the ridge line, which reads in silhouette as a
# chipped edge rather than a hole through a surface.  At 20.30 the aperture
# spans 18.05..22.55, so the crest runs unbroken all the way round and the
# oculi sit on the taut outer drape where the light rakes across them.
OC_R = 20.30
OC_A = 4.50  # semi-axis along azimuth  -> 9.0 m
OC_B = 2.25  # semi-axis radially       -> 4.5 m  (an unmistakable 2:1 oval)
# Gentle upturn of the shell around each opening.  Kept small and local: a
# 0.20 m swell reaching e = 1.7 lifted the sheet at r 17.8 enough to beat
# the r 17.80 crest (11.69 against 11.50), which put the global high point
# on a hole instead of on the ridge.
OC_UPTURN = 0.13
OC_UPTURN_E = 1.50  # upturn fades out by this ellipse fraction (kept local)
LIP_RADIUS = 0.30  # bead radius; stands ~0.17 m proud of the sheet

# --------------------------------------------------------- panelization
N_MERIDIANS = 16
GROOVE_D = 0.022  # inset depth along the surface normal (slim + flush)
GROOVE_HW = 0.045  # metric half-width of a meridian groove (m, constant)
GROOVE_DR = 0.050  # radial half-width of a parallel groove (m)
GROOVE_SHELF = 0.090  # SHELF ring/station just outside each groove shoulder
SEC_RAMP = 1.20  # secondary meridians reach full depth over this run

UV_TILE = 8.0  # metres per UV tile
# Seam walls run at atan(GROOVE_D / GROOVE_HW) = 26 deg, comfortably under
# the auto-smooth threshold, so nothing on the shell splits except the
# boolean cut walls (90 deg), which the oculus lips cover.  The panels stay
# flat because of the SHELF ring, not because of the shading angle.
SMOOTH_ANGLE = 50.0


# ------------------------------------------------------------ profile math
def _cr(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return tuple(
        0.5
        * (
            2.0 * p1[k]
            + (-p0[k] + p2[k]) * t
            + (2.0 * p0[k] - 5.0 * p1[k] + 4.0 * p2[k] - p3[k]) * t2
            + (-p0[k] + 3.0 * p1[k] - 3.0 * p2[k] + p3[k]) * t3
        )
        for k in (0, 1)
    )


def _profile_table(samples_per_seg: int = 64):
    pts = [PROFILE_CTRL[0]] + list(PROFILE_CTRL) + [PROFILE_CTRL[-1]]
    table = []
    for s in range(len(PROFILE_CTRL) - 1):
        p0, p1, p2, p3 = pts[s], pts[s + 1], pts[s + 2], pts[s + 3]
        for k in range(samples_per_seg):
            table.append(_cr(p0, p1, p2, p3, k / samples_per_seg))
    table.append(PROFILE_CTRL[-1])
    cleaned = [table[0]]
    for r, z in table[1:]:
        if r > cleaned[-1][0] + 1e-6:
            cleaned.append((min(r, R_EAVE), z))
    return cleaned


_TABLE = _profile_table()
_TABLE_R = [p[0] for p in _TABLE]


def _arc_table():
    """Cumulative arc length along the (r, z) profile table."""
    out = [0.0]
    for k in range(1, len(_TABLE)):
        r0, z0 = _TABLE[k - 1]
        r1, z1 = _TABLE[k]
        out.append(out[-1] + math.hypot(r1 - r0, z1 - z0))
    return out


_ARC = _arc_table()
_ARC_TOTAL = _ARC[-1]


def _r_at_arc(s: float) -> float:
    """Radius at a given arc length along the profile."""
    s = max(0.0, min(_ARC_TOTAL, s))
    i = bisect.bisect_left(_ARC, s)
    if i <= 0:
        return _TABLE[0][0]
    if i >= len(_ARC):
        return _TABLE[-1][0]
    s0, s1 = _ARC[i - 1], _ARC[i]
    t = (s - s0) / max(1e-9, s1 - s0)
    return _TABLE[i - 1][0] + (_TABLE[i][0] - _TABLE[i - 1][0]) * t


# Parallel seams at EVEN ARC LENGTH (uniform dr bunches them near the crest).
PARALLELS = tuple(
    round(_r_at_arc(_ARC_TOTAL * f), 4) for f in (0.20, 0.40, 0.60, 0.80)
)
SEC_START = PARALLELS[2]  # secondary meridians are born ON the third parallel


def _z_base(r: float) -> float:
    r = max(R_IN, min(R_EAVE, r))
    i = bisect.bisect_left(_TABLE_R, r)
    if i <= 0:
        return _TABLE[0][1]
    if i >= len(_TABLE):
        return _TABLE[-1][1]
    r0, z0 = _TABLE[i - 1]
    r1, z1 = _TABLE[i]
    t = (r - r0) / max(1e-9, r1 - r0)
    return z0 + (z1 - z0) * t


def _thickness(r: float) -> float:
    t = max(0.0, min(1.0, (r - R_IN) / (R_EAVE - R_IN)))
    s = t * t * (3.0 - 2.0 * t)
    return THICK_IN + (THICK_OUT - THICK_IN) * s


# --------------------------------------------------------- swoop (unified)
def _ang_diff(a: float, b: float) -> float:
    return math.atan2(math.sin(a - b), math.cos(a - b))


def _smootherstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


def _swoop_w(theta: float, r: float) -> float:
    """ONE window for both the lift and the outward push.

    Azimuthally it is a smootherstep bump (C2 where it rejoins the ring),
    now spanning 76 deg so the swoop is a wing rather than a scallop.
    RADIALLY it is x**1.5 from an onset just outboard of the crest: value
    and slope both vanish at the onset (no crease), and because the
    exponent is well under 2 the middle of the drape lifts too, so the
    whole outer band sweeps up as one surface.  The r 17.80 crest still
    wins globally (11.50 against 11.10 at the highest point of the swoop).
    """
    d = abs(_ang_diff(theta, SWOOP_AZ))
    if d >= SWOOP_HALF:
        return 0.0
    az_w = _smootherstep(1.0 - d / SWOOP_HALF)
    x = (r - SWOOP_R0) / (R_EAVE - SWOOP_R0)
    x = max(0.0, min(1.0, x))
    return az_w * (x ** SWOOP_POW)


# ------------------------------------------------------------- oculi math
def _hole_e(theta: float, r: float, hole_az: float) -> float:
    u = OC_R * _ang_diff(theta, hole_az)
    v = r - OC_R
    return math.sqrt((u / OC_A) ** 2 + (v / OC_B) ** 2)


def _min_hole_e(theta: float, r: float) -> float:
    return min(_hole_e(theta, r, az) for az in OCULI_AZ)


def _upturn(theta: float, r: float) -> float:
    e = _min_hole_e(theta, r)
    if e >= OC_UPTURN_E:
        return 0.0
    t = min(1.0, (OC_UPTURN_E - e) / (OC_UPTURN_E - 1.0))
    return OC_UPTURN * t * t * (3.0 - 2.0 * t)


# ------------------------------------------------------- panelization math
def _sec_factor(r: float) -> float:
    """Secondary meridian depth: 0 exactly ON the third parallel, 1 outboard.

    Real tensile shells subdivide as the panels widen; at r 24.85 a 16-way
    panelization means 9.8 m panels.  Splitting to 32 outboard halves that.
    The ramp STARTS on a parallel seam, so the eye reads the new seams as
    springing from a ring beam instead of stopping in mid-panel.
    """
    return _smootherstep((r - SEC_START) / SEC_RAMP)


# ------------------------------------------------------------ mesh helpers
def _vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _vscale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _vcross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _vnorm(a):
    n = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)
    if n < 1e-9:
        return (0.0, 0.0, 1.0)
    return (a[0] / n, a[1] / n, a[2] / n)


def _activate(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _new_mesh_obj(name, verts, faces, mat, smooth_angle=SMOOTH_ANGLE, uvs=None):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if uvs is not None:
        layer = mesh.uv_layers.new(name="UVMap")
        for poly, face_uv in zip(mesh.polygons, uvs):
            for k, loop_index in enumerate(poly.loop_indices):
                layer.data[loop_index].uv = face_uv[k]
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, mat)
    _activate(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    if smooth_angle:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(smooth_angle))
    return obj


# --------------------------------------------------- station / ring tables
def _top_radii():
    """Radial samples spaced by ARC LENGTH, with parallel-seam triplets in.

    Sampling by table index (as an earlier revision did) crowds stations
    where the profile table happens to be dense in r and starves the crest
    and the rim reversal, which is exactly where the shading needs them.
    """
    base = [_r_at_arc(_ARC_TOTAL * j / (NR - 1)) for j in range(NR)]
    forced = []
    for rc in PARALLELS:
        forced.extend((rc - GROOVE_SHELF, rc - GROOVE_DR, rc,
                       rc + GROOVE_DR, rc + GROOVE_SHELF))
    keep = [r for r in base if all(abs(r - f) > GROOVE_SHELF * 1.6 for f in forced)]
    rs = sorted(round(r, 6) for r in keep + forced)
    rs[0] = R_IN
    rs[-1] = R_EAVE
    return rs


_TOP_R = _top_radii()
_PAR_SET = set(round(rc, 6) for rc in PARALLELS)


def _azimuths():
    """Base rings plus the floor / shoulder / shelf rings of every meridian.

    Each ring is (theta, centre, offset, is_floor, is_sec).  When `centre`
    is not None the ring's vertices are re-placed at a CONSTANT METRIC
    `offset` from the meridian at EVERY station — top sheet, rolls and
    underside alike — so a seam is the same width at the inner rim as at
    the eave and the whole solid stays in register.
    """
    rings = {}
    for i in range(NA):
        th = round(2.0 * math.pi * i / NA, 9)
        rings[th] = (None, 0.0, False, False)
    for m in range(2 * N_MERIDIANS):
        sec = bool(m % 2)
        c = 2.0 * math.pi * m / (2 * N_MERIDIANS)
        rings[round(c, 9)] = (c, 0.0, True, sec)
        for side in (-1.0, 1.0):
            for off in (GROOVE_HW, GROOVE_SHELF):
                th = round((c + side * off / OC_R) % (2.0 * math.pi), 9)
                rings[th] = (c, side * off, False, sec)
    return [(th,) + rings[th] for th in sorted(rings)]


_RINGS = _azimuths()


# ------------------------------------------- warped top sheet, in 3D
def _top_point(theta: float, r: float):
    """World XYZ of the WARPED top sheet (base profile + swoop + upturn)."""
    w = _swoop_w(theta, r)
    z = _z_base(r) + SWOOP_LIFT * w + _upturn(theta, r)
    rr = r + PUSH_MAX * w
    return (rr * math.cos(theta), rr * math.sin(theta), z)


_FRAME_H = 0.03


def _top_frame(theta: float, r: float):
    """(P, N, Tr) on the WARPED top sheet: point, unit outward normal and
    unit in-surface radial tangent.

    Everything hung off the top sheet — the underside offset, the eave roll,
    the inner rim roll, the oculus lip, the seam inset — is built in this
    frame rather than from the flat base profile.  That matters most in the
    entry swoop, where the lift tilts the real surface at the eave by more
    than 40 deg; a roll built on the base profile's tangent would be that
    far out of alignment with the sheet it is supposed to wrap.
    """
    h = _FRAME_H
    ra = max(R_IN, min(R_EAVE - 2.0 * h, r - h))
    rb = ra + 2.0 * h
    dth = h / r
    p = _top_point(theta, r)
    tr = _vnorm(_vsub(_top_point(theta, rb), _top_point(theta, ra)))
    tt = _vnorm(_vsub(_top_point(theta + dth, r), _top_point(theta - dth, r)))
    n = _vnorm(_vcross(tr, tt))
    if n[2] < 0.0:
        n = _vscale(n, -1.0)
    return p, n, tr


# --------------------------------------------------------------- stations
# A station is (kind, value, par_flag, r_ref).
#   kind 0 = top sheet at radius `value`
#   kind 1 = underside  at radius `value`
#   kind 2 = eave roll,      `value` = sweep angle 0..pi   from N to -N
#   kind 3 = inner rim roll, `value` = sweep angle pi..2pi from -N to N
ROLL_SEG = 8


def _stations():
    st = []
    for r in _TOP_R:
        st.append((0, r, 1.0 if round(r, 6) in _PAR_SET else 0.0, r))
    for k in range(1, ROLL_SEG):
        st.append((2, math.pi * k / ROLL_SEG, 0.0, R_EAVE))
    for r in reversed(_TOP_R):
        st.append((1, r, 0.0, r))
    for k in range(1, ROLL_SEG):
        st.append((3, math.pi + math.pi * k / ROLL_SEG, 0.0, R_IN))
    return st


_SECTION = _stations()


# ------------------------------------------------------------------ shell
def _seam_depth(ring, station) -> float:
    """Inset depth for this (ring, station), in metres along the normal.

    Applied to the WHOLE cross-section, so a seam is a continuous fold that
    runs from the inner bead, across the top sheet, around the eave roll and
    back along the underside.  Nothing tapers to zero in mid-field: the only
    seams that start anywhere are the secondary meridians, and they start
    exactly on a parallel.
    """
    _theta, _centre, _offset, is_floor, is_sec = ring
    _kind, _value, par, r_ref = station
    g = 1.0 if par else 0.0
    if is_floor:
        g = max(g, _sec_factor(r_ref) if is_sec else 1.0)
    return GROOVE_D * g


def _shell_vertex(ring, station):
    theta, centre, offset, _is_floor, _is_sec = ring
    kind, value, _par, r_ref = station
    if centre is not None and offset:
        # Constant-metric-width seam ring, keyed on r_ref so every station
        # of one cross-section shares a single azimuth: the seam is then a
        # true ruled line through the solid instead of twisting between the
        # top sheet, the rolls and the underside.
        theta = centre + offset / r_ref
    g = _seam_depth(ring, station)
    if kind == 0:
        p, n, _tr = _top_frame(theta, value)
        return _vsub(p, _vscale(n, g))
    if kind == 1:
        p, n, _tr = _top_frame(theta, value)
        return _vsub(p, _vscale(n, _thickness(value) + g))
    # Tangent semicircle wrapping the sheet edge, swept in the (N, Tr) plane
    # of the WARPED surface.  At value = 0 / 2pi it lands exactly on the top
    # sheet, at value = pi exactly on the underside offset point.  The seam
    # inset simply translates the whole circle along -N, so the roll stays
    # perfectly circular and the groove wraps it without a notch.
    r_edge = R_EAVE if kind == 2 else R_IN
    p, n, tr = _top_frame(theta, r_edge)
    rad = _thickness(r_edge) * 0.5
    cen = _vsub(p, _vscale(n, rad + g))
    return _vadd(
        cen,
        _vadd(_vscale(n, rad * math.cos(value)),
              _vscale(tr, rad * math.sin(value))),
    )


def _section_arclen():
    """Cross-section arc length (for V), measured on the unwarped azimuth."""
    ring = (0.0, None, 0.0, False, False)
    pts = [_shell_vertex(ring, st) for st in _SECTION]
    s, out = 0.0, [0.0]
    for k in range(1, len(pts)):
        s += math.dist(pts[k - 1], pts[k])
        out.append(s)
    out.append(s + math.dist(pts[-1], pts[0]))
    return out


_SECTION_S = _section_arclen()


def _build_shell(mat):
    n_st = len(_SECTION)
    n_az = len(_RINGS)
    verts = []
    for ring in _RINGS:
        for st in _SECTION:
            verts.append(_shell_vertex(ring, st))

    faces, uvs = [], []
    total_s = _SECTION_S[-1]
    for i in range(n_az):
        i2 = (i + 1) % n_az
        th0 = _RINGS[i][0]
        th1 = _RINGS[i2][0] if i2 != 0 else 2.0 * math.pi
        for j in range(n_st):
            j2 = (j + 1) % n_st
            v0 = _SECTION_S[j] / UV_TILE
            v1 = (_SECTION_S[j + 1] if j2 != 0 else total_s) / UV_TILE
            # U is TRUE azimuthal arc length at each station's own radius,
            # not at a fixed r = 19: otherwise texel density is ~35% off
            # between the inner rim and the eave, which is invisible on flat
            # white and lethal the moment a panel/normal map lands on it.
            ra, rb = _SECTION[j][3], _SECTION[j2][3]
            u0a, u1a = th0 * ra / UV_TILE, th1 * ra / UV_TILE
            u0b, u1b = th0 * rb / UV_TILE, th1 * rb / UV_TILE
            a = i * n_st + j
            b = i2 * n_st + j
            c = i2 * n_st + j2
            d = i * n_st + j2
            faces.append((a, b, c, d))
            uvs.append(((u0a, v0), (u1a, v0), (u1b, v1), (u0b, v1)))

    rad = [math.hypot(v[0], v[1]) for v in verts]
    zs = [v[2] for v in verts]
    print(f"[shell_roof] parallels (arc-spaced): "
          f"{['%.2f' % p for p in PARALLELS]}")
    print(f"[shell_roof] extents: r {min(rad):.3f}..{max(rad):.3f}  "
          f"z {min(zs):.3f}..{max(zs):.3f}")
    obj = _new_mesh_obj(f"{PREFIX}_surface", verts, faces, mat, uvs=uvs)
    print(f"[shell_roof] surface: {len(obj.data.polygons)} polys "
          f"({n_az} rings x {n_st} stations)")
    return obj


# ------------------------------------------- analytic oculus cut boundary
def _oculus_edge(hole_az: float, k_steps: int):
    """Cut-edge samples: (theta, r, nu, nv) with (nu, nv) the unit outward
    ellipse normal in the (azimuthal-metres, radial-metres) plane."""
    out = []
    for k in range(k_steps):
        phi = 2.0 * math.pi * k / k_steps
        u, v = OC_A * math.cos(phi), OC_B * math.sin(phi)
        nu, nv = u / (OC_A * OC_A), v / (OC_B * OC_B)
        n = math.hypot(nu, nv)
        out.append((hole_az + u / OC_R, OC_R + v, nu / n, nv / n))
    return out


def _cut_oculi(shell):
    """EXACT boolean against vertical elliptical prisms.

    The cut edge is therefore the analytic ellipse itself, so the opening
    truly measures 9.0 x 4.5 m and the swept lip lands on it exactly.
    """
    for tag, az in (("a", OCULI_AZ[0]), ("b", OCULI_AZ[1])):
        ring = _oculus_edge(az, 96)
        verts, faces = [], []
        n = len(ring)
        for theta, r, _nu, _nv in ring:
            verts.append((r * math.cos(theta), r * math.sin(theta), 4.0))
        for theta, r, _nu, _nv in ring:
            verts.append((r * math.cos(theta), r * math.sin(theta), 15.0))
        # Outward-facing winding: EXACT boolean treats an inverted prism as
        # negative volume and silently leaves the shell uncut.
        for k in range(n):
            k2 = (k + 1) % n
            faces.append((k2, k, n + k, n + k2))
        faces.append(tuple(range(n)))
        faces.append(tuple(range(2 * n - 1, n - 1, -1)))
        mesh = bpy.data.meshes.new(f"{PREFIX}_cutter_{tag}")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        cutter = bpy.data.objects.new(mesh.name, mesh)
        bpy.context.scene.collection.objects.link(cutter)

        _activate(shell)
        mod = shell.modifiers.new(f"oculus_{tag}", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter, do_unlink=True)
    _activate(shell)
    bpy.ops.object.shade_auto_smooth(angle=math.radians(SMOOTH_ANGLE))
    print(f"[shell_roof] surface after oculi boolean: "
          f"{len(shell.data.polygons)} polys")


# -------------------------------------------------------------- oculus lip
def _lip_axis(theta: float, r: float, nu: float, nv: float):
    """Tube axis for the rolled lip.

    Start at the TOP cut edge, walk `off` metres OUTWARD ALONG THE WARPED
    SURFACE (azimuthally by nu, radially by nv), then drop half the local
    shell thickness along that surface's NORMAL.  With
    off = sqrt(LIP_RADIUS^2 - drop^2) the tube of radius LIP_RADIUS passes
    through the top cut edge and, by symmetry about mid-thickness, through
    the bottom one.  (The cutter is a VERTICAL prism, so the two edges are
    separated vertically rather than along the normal; where the sheet is
    steepest that is a ~0.03 m mismatch, still well inside the 0.30 m bead.)
    With LIP_RADIUS 0.30 against a 0.26 m sheet the tube also stands about
    0.17 m PROUD of the surface, so the rim reads as a lit bead instead of
    dissolving into the crest curvature.
    """
    p, n, tr = _top_frame(theta, r)
    tt = _vnorm(_vcross(n, tr))  # in-surface azimuthal tangent
    drop = 0.5 * _thickness(r)
    off = math.sqrt(max(1e-6, LIP_RADIUS * LIP_RADIUS - drop * drop))
    return _vsub(
        _vadd(p, _vadd(_vscale(tt, off * nu), _vscale(tr, off * nv))),
        _vscale(n, drop),
    )


def _build_oculus_lip(mat, hole_az, tag):
    K, S = 112, 14
    centers = [_lip_axis(*e) for e in _oculus_edge(hole_az, K)]

    verts, faces, uvs = [], [], []
    for k in range(K):
        p = centers[k]
        tangent = _vnorm(_vsub(centers[(k + 1) % K], centers[k - 1]))
        n1 = _vnorm(_vcross(tangent, (0.0, 0.0, 1.0)))
        n2 = _vnorm(_vcross(n1, tangent))
        for s in range(S):
            psi = 2.0 * math.pi * s / S
            verts.append(
                _vadd(
                    p,
                    _vadd(
                        _vscale(n1, LIP_RADIUS * math.cos(psi)),
                        _vscale(n2, LIP_RADIUS * math.sin(psi)),
                    ),
                )
            )
    circ = 2.0 * math.pi * LIP_RADIUS
    for k in range(K):
        k2 = (k + 1) % K
        for s in range(S):
            s2 = (s + 1) % S
            faces.append((k * S + s, k * S + s2, k2 * S + s2, k2 * S + s))
            u0 = k / K * 2.0 * math.pi * OC_A / UV_TILE
            u1 = (k + 1) / K * 2.0 * math.pi * OC_A / UV_TILE
            v0, v1 = s / S * circ / UV_TILE, (s + 1) / S * circ / UV_TILE
            uvs.append(((u0, v0), (u0, v1), (u1, v1), (u1, v0)))
    return _new_mesh_obj(
        f"{PREFIX}_oculus_lip_{tag}", verts, faces, mat, uvs=uvs
    )




def _build_oculus_glass(mat, hole_az, tag):
    """Curved rounded window filling a secondary oculus (player request).

    A shallow lens: the rim ring sits on the shell surface at the cut
    ellipse (so it tucks under the rolled lip) and bows DOWNWARD toward
    the hall by GLASS_SAG, giving a domed pane you look through into the
    interior. Triangle fan from a centre pole keeps it watertight.
    """

    K = 96
    RINGS = 6
    GLASS_SAG = 0.55

    edge = [_lip_axis(*e) for e in _oculus_edge(hole_az, K)]
    cx = sum(p[0] for p in edge) / K
    cy = sum(p[1] for p in edge) / K
    cz = sum(p[2] for p in edge) / K
    centre = (cx, cy, cz - GLASS_SAG)

    verts = [centre]
    for ring_index in range(1, RINGS + 1):
        frac = ring_index / RINGS
        # Circular-arc profile: full sag at the centre, zero at the rim.
        sag = GLASS_SAG * math.sqrt(max(0.0, 1.0 - frac * frac))
        for k in range(K):
            ex, ey, ez = edge[k]
            verts.append(
                (
                    cx + (ex - cx) * frac,
                    cy + (ey - cy) * frac,
                    cz + (ez - cz) * frac - sag,
                )
            )

    faces = []
    for k in range(K):
        faces.append((0, 1 + k, 1 + (k + 1) % K))
    for ring_index in range(1, RINGS):
        base = 1 + (ring_index - 1) * K
        nxt = 1 + ring_index * K
        for k in range(K):
            k2 = (k + 1) % K
            faces.append((base + k, nxt + k, nxt + k2, base + k2))
    return _new_mesh_obj(f"{PREFIX}_oculus_glass_{tag}", verts, faces, mat)


# -------------------------------------------------------------------- build
def build(materials):
    shell_white = materials[f"{spec.MOD_ID}_shell_white"]

    shell = _build_shell(shell_white)
    _cut_oculi(shell)

    objects = [shell]
    for tag, az in (("a", OCULI_AZ[0]), ("b", OCULI_AZ[1])):
        objects.append(_build_oculus_lip(shell_white, az, tag))

    return objects
