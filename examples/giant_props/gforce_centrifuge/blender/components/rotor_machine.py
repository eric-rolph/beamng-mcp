"""Rotor machine centrepiece — CHIEF hypergravity centrifuge rotor.

Static pieces are named ``{MOD_ID}_rotor_*`` (pedestal dome, skirt band,
inspection hatches, hub bedplate/column/drive housing, C-frame bearing
supports); spinning pieces are named ``{MOD_ID}_rotorarm_*`` (the 14 m arm,
its hub skirts and flanges, fin stacks, end collars, tips, panel straps and
the red auxiliary pod) so the integrator can split them into the rotating
part on the substring alone.

Authored frame: meters, Z-up, bowl centre at origin. Pedestal base sits at
z 0.5 (bowl floor inner edge); the arm centreline is at z 3.4. The arm turns
about its own long (X) axis — that is the only kinematic reading under which
STATIC C-frames can straddle the arm at x = +-2.6, so every clearance below
is a sweep radius measured from the arm axis.

Kinematics are DERIVED AND VERIFIED, not asserted. ``_ROT`` lists every
rotating feature as (x_lo, x_hi, sweep_radius); ``_STATIC`` lists every static
feature as a YZ-projected box. ``_verify_clearances`` runs at build time,
prints the eight tightest margins and RAISES on any violation. It checks
four families: box-vs-sweep for every x-overlapping pair; the three purely
radial faces (the bearing bore, the hub drive-housing bore and the cradle
arc, whose whole working surface lies on a single radius); and each sweep
circle marched over the analytic dome surface. ``RING_IN``, the pillow-block
inner faces and the housing bore are computed from the measured maximum
rotating radius in their own x-window instead of being hard-coded.

Two derivations that drive the whole layout; the margin table is printed on
every build, so nothing below can silently go stale:

  * The pedestal cap is back on brief: r 1.2, z 2.55. The ceiling is the hub
    skirt's 0.745 sweep, 3.40 - 0.745 - 0.05 = 2.605. Cap height then costs
    roll envelope one-for-one, and over the flat cap only 3.40 - 2.55 - 0.05
    = 0.80 m of sweep survives bottom dead centre. A genuinely SLUNG red pod
    (standing off the skin, not faired into it) needs 1.25 m, and every
    station between x 1.8 and 3.15 is occupied by the C-frame cradle and
    pillow blocks. The pod therefore sits at |x| 3.30..4.00: the innermost
    station on the arm where it survives a full 360 deg roll. That is a real
    trade — "near the hub" and an on-brief dome cannot both be had — and the
    dome won, because the dome is the silhouette.

  * The arm is no longer floating. A static machined DRIVE HOUSING
    (``_rotor_hub_housing``) rises off the steel bedplate at z 2.60 and
    saddles the blue band on a 0.735 m bore — a 55 mm labyrinth against the
    0.680 m band. Its shoulders top out exactly at the arm axis (z 3.40), so
    it reads as the lower half of a split bearing, and a rotating flared
    skirt (``_rotorarm_hubskirt_*``, sweep 0.745, painted blue so the 4 m
    centre band stays continuous) shrouds each end of it with a 40 mm axial
    gap. There is no daylight left under the hub from any angle.

The C-frames follow the same split-bearing logic: the pillow blocks ARE the
lower halves, bored to ``RING_IN`` with their top plane as the joint line, and
``_arch_x`` is the bolted cap tucked 0.06 rad below that plane.
"""

from __future__ import annotations

import math

import bpy

import spec
from proplib import blender_kit as bk

P = spec.MOD_ID

# --- pedestal --------------------------------------------------------------
# Brief: r 3.2 z 0.5 -> flat cap r 1.2 z 2.6. The cap is at 2.55: the binding
# constraint is the largest rotating radius that passes over the cap, which is
# the hub skirt at 0.745, so the ceiling is 3.40 - 0.745 - 0.05 = 2.605.
# 2.05 m of rise over 2.0 m of radial run is a true quarter ellipse, not the
# 1.55/2.25 saucer this used to be.
DOME_BASE_R = 3.2
DOME_BASE_Z = 0.5
DOME_TOP_R = 1.2
DOME_TOP_Z = 2.55

# --- rotor arm -------------------------------------------------------------
ARM_Z = 3.4
ARM_R = 0.65
BAND_R = 0.68
BAND_HALF = 2.0  # blue centre band: 4 m wide
HUBSKIRT_X0, HUBSKIRT_X1 = 0.66, 0.80  # rotating labyrinth over the housing
HUBSKIRT_R_IN, HUBSKIRT_R_OUT = 0.745, 0.685
HUBFLANGE_R = 0.71
HUBFLANGE_X = 0.85
HUBFLANGE_W = 0.08
WHITE_END = 6.3  # white section spans |x| 2.0 .. 6.3
# Panel straps: 15 mm proud and 55 mm wide. At 3 mm / 32 mm they z-fought the
# arm skin at BeamNG depth precision and aliased to a shimmer at distance.
LINE_R = 0.665
LINE_X = (3.22, 4.62, 5.32)
LINE_W = 0.055
DUCT_X0, DUCT_X1 = 3.25, 5.95  # spine starts OUTBOARD of the pillow blocks
DUCT_HALF_Y = 0.12
DUCT_Z_LO, DUCT_Z_HI = 3.99, 4.10
FIN_R = 0.74
# Two stacks a side: an inboard pair just outside the bearing window and a
# tip triple. All three rings clustered at the tip left 4.3 m of bare skin.
FIN_X = (4.30, 4.48, 5.72, 5.90, 6.08)
FIN_W = 0.09
COLLAR_X, COLLAR_R, COLLAR_W = 6.35, 0.76, 0.30
# Blunt WHITE nose with a blue collar behind it: the old blue 0.65 -> 0.30
# taper pushed the whole silhouette toward "naval cannon".
CONE_X0, TIP_X, TIP_R = 6.55, 7.00, 0.44

# --- red auxiliary pod, slung under the arm --------------------------------
POD_ANG = math.radians(30.0)  # swung off bottom dead centre toward -Y
POD_D = 1.00  # pod axis offset from the arm axis -> 0.13 m of daylight
POD_R = 0.22
POD_CAP_R = 0.25
# Innermost station that clears the pedestal at bottom dead centre AND the
# east C-frame in x (pillow blocks stop at 3.14).
POD_X0, POD_X1 = 3.30, 4.00
POD_Y = -POD_D * math.sin(POD_ANG)
POD_Z = ARM_Z - POD_D * math.cos(POD_ANG)
STRAP_X = (3.48, 3.82)
STRAP_MID_D = 0.80  # strap box centre, measured radially from the arm axis
STRAP_DIMS = (0.14, 0.26, 0.46)

# --- static hub stack ------------------------------------------------------
# Dark steel bedplate drum standing 5 cm proud of the cap, a ring of proud
# bolt heads, then the machined drive housing. The bolt azimuths are the ones
# whose |x| clears the housing rectangle (0.62) — the rest would be buried.
BED_R, BED_Z0, BED_Z1 = 1.06, 2.40, 2.60
BOLT_RAD, BOLT_R, BOLT_Z0, BOLT_Z1 = 0.99, 0.05, 2.52, 2.66
BOLT_A = (0.0, 20.0, -20.0, 40.0, -40.0)
COL_R, COL_Z0, COL_Z1 = 0.62, 1.60, 2.60
HOUSE_HALF_X = 0.62
HOUSE_Y = 0.94
HOUSE_Z0 = 2.60
HOUSE_BOLT = ((-0.44, -0.86), (-0.44, 0.86), (0.44, -0.86), (0.44, 0.86))

# --- C-frame bearing supports ---------------------------------------------
FRAME_X = 2.6
# Piers are 1.36 m along X at the sole and 0.98 m at the collar — the old
# 0.86 -> 0.80 slab read as a cardboard flipper. The base inner face at
# y 0.67 is the tightest thing in the whole frame against the blue band.
LEG_BASE_C, LEG_BASE_DIMS = (1.98, 1.19), (1.36, 1.04)
LEG_TOP_C, LEG_TOP_DIMS = (2.60, 1.16), (0.98, 0.90)
LEG_TOP_Z = 3.10
LEG_VERIFY_X = 1.30  # inner x of the raked loft at the z 2.62 split plane
LEG_VERIFY_Y = 0.67  # inner y of the raked loft at the same plane
FOOT_C, FOOT_DIMS, FOOT_T = (1.94, 1.18), (1.48, 1.08), 0.12
RIB_BASE_C, RIB_BASE_DIMS = (1.98, 1.77), (0.90, 0.18)
RIB_TOP_C, RIB_TOP_DIMS = (2.60, 1.66), (0.76, 0.18)
# Pillow blocks are the LOWER HALF of a split bearing: their bore face is the
# same radius as the cap arch, and their top plane is the joint line.
PILLOW_X_HALF = 0.54
PILLOW_Y1 = 1.50
PILLOW_Z0, PILLOW_Z1 = 2.78, 3.46
# The bottom member is not a straight beam but a cradle whose top edge is an
# arc concentric with the rotor: it closes the C visibly under the arm and
# reads as machined hardware rather than as a buried spacer.
CRADLE_X, CRADLE_HALF_X = 2.35, 0.40
CRADLE_Y_HALF = 1.40
CRADLE_R = 0.77  # arc radius of the cradle's inner (upper) face
CRADLE_T = 0.34
CRADLE_TOP_Z = 3.28  # the horns stop below the arm axis so the U stays open
RING_HALF_W = 0.34
RING_DEPTH = 0.50  # radial depth of the cap arch section
RING_U_TUCK = 0.06  # radians the cap arch tucks below the pillow joint line
CLEARANCE = 0.05


# ---------------------------------------------------------------------------
# kinematic bookkeeping
# ---------------------------------------------------------------------------
def _rot_features() -> list[tuple[str, float, float, float]]:
    """(name, x_lo, x_hi, sweep_radius) for every rotating piece."""

    f: list[tuple[str, float, float, float]] = [
        ("band", -BAND_HALF, BAND_HALF, BAND_R),
    ]
    for s in (1.0, -1.0):
        lo, hi = sorted((s * HUBSKIRT_X0, s * HUBSKIRT_X1))
        f.append(("hubskirt", lo, hi, HUBSKIRT_R_IN))
        lo, hi = sorted((s * (HUBFLANGE_X - HUBFLANGE_W / 2), s * (HUBFLANGE_X + HUBFLANGE_W / 2)))
        f.append(("hubflange", lo, hi, HUBFLANGE_R))
        lo, hi = sorted((s * BAND_HALF, s * WHITE_END))
        f.append(("white", lo, hi, ARM_R))
        for lx in LINE_X:
            a, b = sorted((s * (lx - LINE_W / 2), s * (lx + LINE_W / 2)))
            f.append(("line", a, b, LINE_R))
        lo, hi = sorted((s * DUCT_X0, s * DUCT_X1))
        f.append(("duct", lo, hi, math.hypot(DUCT_HALF_Y, DUCT_Z_HI - ARM_Z)))
        for fx in FIN_X:
            a, b = sorted((s * (fx - FIN_W / 2), s * (fx + FIN_W / 2)))
            f.append(("fin", a, b, FIN_R))
        a, b = sorted((s * (COLLAR_X - COLLAR_W / 2), s * (COLLAR_X + COLLAR_W / 2)))
        f.append(("endcollar", a, b, COLLAR_R))
        a, b = sorted((s * CONE_X0, s * TIP_X))
        f.append(("tipcone", a, b, ARM_R))
    # red pod assembly (one side only, +X, just outboard of the east bearing)
    f.append(("pod", POD_X0, POD_X1, POD_D + POD_R))
    for px in (POD_X0, POD_X1):
        f.append(("podcap", px - 0.035, px + 0.035, POD_D + POD_CAP_R))
    strap_r = math.hypot(STRAP_MID_D + STRAP_DIMS[2] / 2.0, STRAP_DIMS[1] / 2.0)
    for sx in STRAP_X:
        f.append(("strap", sx - STRAP_DIMS[0] / 2, sx + STRAP_DIMS[0] / 2, strap_r))
    return f


_ROT = _rot_features()


def _max_rot_radius(x_lo: float, x_hi: float) -> float:
    """Largest rotating sweep radius anywhere in an x window."""

    return max(r for _n, a, b, r in _ROT if b > x_lo and a < x_hi)


# The bearing bore, the pillow faces and the hub housing bore are all DERIVED
# from the measured sweep in their own x window, never hard-coded.
RING_IN = round(_max_rot_radius(FRAME_X - RING_HALF_W, FRAME_X + RING_HALF_W) + 0.055, 4)
RING_OUT = round(RING_IN + RING_DEPTH, 4)
PILLOW_Y0 = RING_IN
HOUSE_BORE = round(_max_rot_radius(-HOUSE_HALF_X, HOUSE_HALF_X) + 0.055, 4)


def _static_features() -> list[tuple[str, float, float, float, float, float, float]]:
    """(name, x0, x1, y0, y1, z0, z1) conservative boxes for static pieces.

    The hub drive housing and the bearing arches are NOT in this list: their
    working faces are single radii about the arm axis, so a YZ box would
    straddle the axis and report a nonsense zero distance. They are checked
    analytically in ``_verify_clearances`` instead.
    """

    s: list[tuple[str, float, float, float, float, float, float]] = [
        ("hub_bedplate", -BED_R, BED_R, -BED_R, BED_R, BED_Z0, BED_Z1),
        ("hub_column", -COL_R, COL_R, -COL_R, COL_R, COL_Z0, COL_Z1),
    ]
    # Each bedplate bolt head is boxed SEPARATELY. A single ring box spanning
    # +-1.04 in both axes would falsely claim material directly under the hub
    # skirt, which is where the tightest margin in the model lives.
    for sgn in (1.0, -1.0):
        for adeg in BOLT_A:
            a = math.radians(adeg) + (0.0 if sgn > 0 else math.pi)
            bx, by = BOLT_RAD * math.cos(a), BOLT_RAD * math.sin(a)
            s.append(
                ("hub_bolt", bx - BOLT_R, bx + BOLT_R, by - BOLT_R, by + BOLT_R, BOLT_Z0, BOLT_Z1)
            )
    for hx, hy in HOUSE_BOLT:
        s.append(
            ("hub_housing_bolt", hx - 0.07, hx + 0.07, hy - 0.07, hy + 0.07, ARM_Z - 0.03, ARM_Z + 0.13)
        )
    fx0 = FOOT_C[0] - FOOT_DIMS[0] / 2
    fx1 = FOOT_C[0] + FOOT_DIMS[0] / 2
    fy0 = FOOT_C[1] - FOOT_DIMS[1] / 2
    fy1 = FOOT_C[1] + FOOT_DIMS[1] / 2
    foot_top = _dome_z_at(math.hypot(fx0, fy0)) + FOOT_T
    bx0 = LEG_BASE_C[0] - LEG_BASE_DIMS[0] / 2
    bx1 = LEG_BASE_C[0] + LEG_BASE_DIMS[0] / 2
    by0 = LEG_BASE_C[1] - LEG_BASE_DIMS[1] / 2
    by1 = LEG_BASE_C[1] + LEG_BASE_DIMS[1] / 2
    tx1 = LEG_TOP_C[0] + LEG_TOP_DIMS[0] / 2
    ty1 = LEG_TOP_C[1] + LEG_TOP_DIMS[1] / 2
    rby0 = min(RIB_BASE_C[1] - RIB_BASE_DIMS[1] / 2, RIB_TOP_C[1] - RIB_TOP_DIMS[1] / 2)
    rby1 = max(RIB_BASE_C[1] + RIB_BASE_DIMS[1] / 2, RIB_TOP_C[1] + RIB_TOP_DIMS[1] / 2)
    rbx0 = min(RIB_BASE_C[0] - RIB_BASE_DIMS[0] / 2, RIB_TOP_C[0] - RIB_TOP_DIMS[0] / 2)
    rbx1 = max(RIB_BASE_C[0] + RIB_BASE_DIMS[0] / 2, RIB_TOP_C[0] + RIB_TOP_DIMS[0] / 2)
    for sx in (1.0, -1.0):
        for sy in (1.0, -1.0):
            a, b = sorted((sx * fx0, sx * fx1))
            c, d = sorted((sy * fy0, sy * fy1))
            s.append(("cframe_foot", a, b, c, d, 0.60, foot_top))
            # lower rake (base quad up to z 2.62) and upper column, separately
            # boxed so the conservative bound is not absurdly pessimistic.
            a, b = sorted((sx * bx0, sx * bx1))
            c, d = sorted((sy * by0, sy * by1))
            s.append(("cframe_leg_low", a, b, c, d, 0.90, 2.62))
            a, b = sorted((sx * LEG_VERIFY_X, sx * tx1))
            c, d = sorted((sy * LEG_VERIFY_Y, sy * ty1))
            s.append(("cframe_leg_top", a, b, c, d, 2.62, LEG_TOP_Z))
            a, b = sorted((sx * rbx0, sx * rbx1))
            c, d = sorted((sy * rby0, sy * rby1))
            s.append(("cframe_rib", a, b, c, d, 0.80, LEG_TOP_Z))
            a, b = sorted((sx * (FRAME_X - PILLOW_X_HALF), sx * (FRAME_X + PILLOW_X_HALF)))
            c, d = sorted((sy * PILLOW_Y0, sy * PILLOW_Y1))
            s.append(("cframe_pillow", a, b, c, d, PILLOW_Z0, PILLOW_Z1))
            a, b = sorted((sx * (FRAME_X - 0.475), sx * (FRAME_X + 0.475)))
            c, d = sorted((sy * 0.80, sy * 1.00))
            s.append(("cframe_capbolt", a, b, c, d, PILLOW_Z1, PILLOW_Z1 + 0.30))
    return s


def _axis_distance(y0: float, y1: float, z0: float, z1: float) -> float:
    """Distance from the arm axis (y=0, z=ARM_Z) to a YZ rectangle."""

    dy = max(y0, -y1, 0.0)
    dz = max(z0 - ARM_Z, ARM_Z - z1, 0.0)
    return math.hypot(dy, dz)


def _verify_clearances() -> None:
    tol = CLEARANCE - 0.001
    ring_face = RING_IN * math.cos(RING_U_TUCK)
    margins: list[tuple[float, str]] = []
    for rname, rx0, rx1, rr in _ROT:
        for sname, sx0, sx1, sy0, sy1, sz0, sz1 in _STATIC:
            if sx1 <= rx0 or sx0 >= rx1:
                continue
            gap = _axis_distance(sy0, sy1, sz0, sz1) - rr
            margins.append((gap, f"{rname}({rr:.4f}) vs {sname}"))
        # the bearing arch, the hub drive housing and the cradle are swept,
        # not boxed: their whole working face lies on one radius, so the
        # constraint is purely radial and exact.
        if rx1 > FRAME_X - RING_HALF_W and rx0 < FRAME_X + RING_HALF_W:
            margins.append((ring_face - rr, f"{rname}({rr:.4f}) vs bearing bore"))
        if rx1 > -HOUSE_HALF_X and rx0 < HOUSE_HALF_X:
            margins.append((HOUSE_BORE - rr, f"{rname}({rr:.4f}) vs hub housing bore"))
        for sx in (1.0, -1.0):
            c0, c1 = sorted((sx * (CRADLE_X - CRADLE_HALF_X), sx * (CRADLE_X + CRADLE_HALF_X)))
            if rx1 > c0 and rx0 < c1:
                margins.append((CRADLE_R - rr, f"{rname}({rr:.4f}) vs cradle arc"))
        # analytic dome surface
        worst = 1e9
        for i in range(9):
            x = rx0 + (rx1 - rx0) * i / 8.0
            for j in range(41):
                y = -rr + 2.0 * rr * j / 40.0
                zs = ARM_Z - math.sqrt(max(rr * rr - y * y, 0.0))
                worst = min(worst, zs - _dome_z_at(math.hypot(x, y)))
        margins.append((worst, f"{rname}({rr:.4f}) vs dome surface"))
    margins.sort()
    print("[rotor_machine] tightest static/rotating margins (mm):")
    for gap, what in margins[:8]:
        print(f"    {gap * 1000:8.1f}  {what}")
    if margins[0][0] < tol:
        raise ValueError(
            f"rotor clearance fail: {margins[0][1]} -> {margins[0][0] * 1000:.1f} mm"
        )


# ---------------------------------------------------------------------------
# mesh helpers
# ---------------------------------------------------------------------------
def _smooth(obj: bpy.types.Object, angle_deg: float | None = 40.0) -> None:
    if angle_deg is None:
        return
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(angle_deg))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)


def _mesh_object(name, verts, faces, material, *, smooth=40.0) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, material)
    _smooth(obj, smooth)
    return obj


def _dome_z_at(radial: float) -> float:
    """Height of the dome surface at a radial distance (quarter-ellipse).

    Clamped at both ends: inside ``DOME_TOP_R`` the surface is the flat cap,
    outside ``DOME_BASE_R`` it is the base plane.
    """

    if radial <= DOME_TOP_R:
        return DOME_TOP_Z
    if radial >= DOME_BASE_R:
        return DOME_BASE_Z
    c = (radial - DOME_TOP_R) / (DOME_BASE_R - DOME_TOP_R)
    theta = math.acos(max(0.0, min(1.0, c)))
    return DOME_BASE_Z + (DOME_TOP_Z - DOME_BASE_Z) * math.sin(theta)


def _dome_r_at(z: float) -> float:
    """Radius of the dome surface at a height (inverse of ``_dome_z_at``)."""

    s = (z - DOME_BASE_Z) / (DOME_TOP_Z - DOME_BASE_Z)
    s = max(-1.0, min(1.0, s))
    theta = math.asin(s)
    return DOME_TOP_R + (DOME_BASE_R - DOME_TOP_R) * math.cos(theta)


_STATIC = _static_features()


def _dome(name, material, *, azimuth=56, steps=14) -> bpy.types.Object:
    """Swept quarter-ellipse pedestal: r 3.2 at z 0.5 -> flat cap r 1.2 z 2.55.

    56 x 14 with a 60 deg auto-smooth: the silhouette must read as a cast
    shell, not a polygon, from every in-game angle.
    """

    verts: list[tuple[float, float, float]] = []
    for i in range(steps + 1):
        theta = (math.pi / 2.0) * i / steps
        r = DOME_TOP_R + (DOME_BASE_R - DOME_TOP_R) * math.cos(theta)
        z = DOME_BASE_Z + (DOME_TOP_Z - DOME_BASE_Z) * math.sin(theta)
        for j in range(azimuth):
            a = 2.0 * math.pi * j / azimuth
            verts.append((r * math.cos(a), r * math.sin(a), z))
    top_center = len(verts)
    verts.append((0.0, 0.0, DOME_TOP_Z))
    bottom_center = len(verts)
    verts.append((0.0, 0.0, DOME_BASE_Z))
    faces: list[tuple[int, ...]] = []
    for i in range(steps):
        for j in range(azimuth):
            a = i * azimuth + j
            b = i * azimuth + (j + 1) % azimuth
            c = (i + 1) * azimuth + (j + 1) % azimuth
            d = (i + 1) * azimuth + j
            faces.append((a, b, c, d))
    top_ring = steps * azimuth
    for j in range(azimuth):
        faces.append((top_ring + j, top_ring + (j + 1) % azimuth, top_center))
    for j in range(azimuth):
        faces.append(((j + 1) % azimuth, j, bottom_center))
    return _mesh_object(name, verts, faces, material, smooth=60.0)


def _arch_x(name, center, r_in, r_out, half_w, material, *, u0, u1, nu=30):
    """Box-section arch swept about an X-axis line — the bearing cap.

    A rectangular section (``r_in``..``r_out`` radially, +-``half_w`` along X)
    reads as a machined bearing cap. Auto-smoothed at 30 deg so the swept
    curve is a machined arc while the box-section corners stay crisp.
    """

    cx, cy, cz = center
    section = [
        (r_in, half_w),
        (r_out, half_w),
        (r_out, -half_w),
        (r_in, -half_w),
    ]
    nv = len(section)
    verts: list[tuple[float, float, float]] = []
    for iu in range(nu + 1):
        u = u0 + (u1 - u0) * iu / nu
        for r, xo in section:
            verts.append((cx + xo, cy + r * math.cos(u), cz + r * math.sin(u)))
    faces: list[tuple[int, ...]] = []
    for iu in range(nu):
        for iv in range(nv):
            a = iu * nv + iv
            b = iu * nv + (iv + 1) % nv
            c = (iu + 1) * nv + (iv + 1) % nv
            d = (iu + 1) * nv + iv
            faces.append((a, b, c, d))
    faces.append(tuple(range(nv - 1, -1, -1)))
    faces.append(tuple(range(nu * nv, (nu + 1) * nv)))
    return _mesh_object(name, verts, faces, material, smooth=30.0)


def _dome_band(name, z_lo, z_hi, material, *, out=0.035, sink=0.11, az=128,
               steps=20):
    # az 64->128, steps 8->20 (round 15, player: "too blocky geometric"):
    # the join/export path flattens the smooth-shading marks, so facet
    # density is the honest lever - at 2.8 deg per facet the dome reads
    # round even flat-shaded.
    """Closed band that follows the dome profile — the royal-blue skirt.

    A straight frustum crosses the dome's curvature and lets the white shell
    punch through at mid height; this sweeps the true profile so the band
    stays a constant 3.5 cm proud from bottom rim to top rim.
    """

    rows_out: list[list[int]] = []
    rows_in: list[list[int]] = []
    verts: list[tuple[float, float, float]] = []
    for i in range(steps + 1):
        z = z_lo + (z_hi - z_lo) * i / steps
        ro = _dome_r_at(z) + out
        ri = _dome_r_at(z) - sink
        row_o, row_i = [], []
        for j in range(az):
            a = 2.0 * math.pi * j / az
            row_o.append(len(verts))
            verts.append((ro * math.cos(a), ro * math.sin(a), z))
        for j in range(az):
            a = 2.0 * math.pi * j / az
            row_i.append(len(verts))
            verts.append((ri * math.cos(a), ri * math.sin(a), z))
        rows_out.append(row_o)
        rows_in.append(row_i)
    faces: list[tuple[int, ...]] = []
    for i in range(steps):
        for j in range(az):
            k = (j + 1) % az
            faces.append(
                (rows_out[i][j], rows_out[i][k], rows_out[i + 1][k], rows_out[i + 1][j])
            )
            faces.append(
                (rows_in[i + 1][j], rows_in[i + 1][k], rows_in[i][k], rows_in[i][j])
            )
    for j in range(az):
        k = (j + 1) % az
        faces.append((rows_out[-1][j], rows_out[-1][k], rows_in[-1][k], rows_in[-1][j]))
        faces.append((rows_in[0][j], rows_in[0][k], rows_out[0][k], rows_out[0][j]))
    return _mesh_object(name, verts, faces, material, smooth=50.0)


def _dome_patch(
    name, phi_c, half_phi, z_lo, z_hi, out, material, *, sink=0.10, naz=10, nz=6
):
    """Rectangular shell-conforming plate on the dome — the inspection hatches.

    Circular covers standing proud on a white dome read as EYES from the
    entry azimuth; a shallow rectangular panel that follows the curvature
    reads as an access hatch and nothing else.
    """

    verts: list[tuple[float, float, float]] = []
    o: list[list[int]] = []
    n: list[list[int]] = []
    for iz in range(nz + 1):
        z = z_lo + (z_hi - z_lo) * iz / nz
        rr = _dome_r_at(z)
        ro, ri = rr + out, rr - sink
        row_o, row_i = [], []
        for ia in range(naz + 1):
            a = phi_c - half_phi + 2.0 * half_phi * ia / naz
            ca, sa = math.cos(a), math.sin(a)
            row_o.append(len(verts))
            verts.append((ro * ca, ro * sa, z))
        for ia in range(naz + 1):
            a = phi_c - half_phi + 2.0 * half_phi * ia / naz
            ca, sa = math.cos(a), math.sin(a)
            row_i.append(len(verts))
            verts.append((ri * ca, ri * sa, z))
        o.append(row_o)
        n.append(row_i)
    faces: list[tuple[int, ...]] = []
    for iz in range(nz):
        for ia in range(naz):
            faces.append((o[iz][ia], o[iz][ia + 1], o[iz + 1][ia + 1], o[iz + 1][ia]))
            faces.append((n[iz + 1][ia], n[iz + 1][ia + 1], n[iz][ia + 1], n[iz][ia]))
    for ia in range(naz):
        faces.append((n[0][ia], n[0][ia + 1], o[0][ia + 1], o[0][ia]))
        faces.append((o[nz][ia], o[nz][ia + 1], n[nz][ia + 1], n[nz][ia]))
    for iz in range(nz):
        faces.append((o[iz][0], o[iz + 1][0], n[iz + 1][0], n[iz][0]))
        faces.append((n[iz][naz], n[iz + 1][naz], o[iz + 1][naz], o[iz][naz]))
    return _mesh_object(name, verts, faces, material, smooth=30.0)


def _saddle(
    name, xc, half_x, y_half, r_in, material, *, thickness=None, base_z=None,
    top_cap_z=None, ny=44, smooth=30.0,
):
    """A body whose TOP face is an arc concentric with the rotor.

    Two shapes come out of this one sweep, both of which have to hug the
    rotating envelope exactly:

    * ``thickness`` given -> a constant-thickness U (the C-frame cradle). A
      straight tie beam either buries itself in the pedestal or sits as a dumb
      spacer; this hugs the envelope at a constant ``r_in`` and rises into
      horns that meet the piers, so the frame reads as a C from every angle
      that can see under the arm.
    * ``base_z`` given -> a flat-bottomed block with a cylindrical groove
      through it (the hub drive housing).

    Because the whole inner face lies on one radius the kinematic check is
    exact: clearance = ``r_in`` - sweep radius.
    """

    if top_cap_z is None:
        top_cap_z = ARM_Z
    x0, x1 = xc - half_x, xc + half_x
    verts: list[tuple[float, float, float]] = []
    idx: list[list[tuple[int, int]]] = []
    for x in (x0, x1):
        col: list[tuple[int, int]] = []
        for j in range(ny + 1):
            y = -y_half + 2.0 * y_half * j / ny
            top = ARM_Z - math.sqrt(max(r_in * r_in - y * y, 0.0))
            top = min(top, top_cap_z)
            bot = top - thickness if thickness is not None else base_z
            t = len(verts)
            verts.append((x, y, top))
            b = len(verts)
            verts.append((x, y, bot))
            col.append((t, b))
        idx.append(col)
    faces: list[tuple[int, ...]] = []
    for p in range(2):
        for j in range(ny):
            t0, b0 = idx[p][j]
            t1, b1 = idx[p][j + 1]
            faces.append((t0, b0, b1, t1) if p == 0 else (t1, b1, b0, t0))
    for j in range(ny):
        a0, _ = idx[0][j]
        a1, _ = idx[0][j + 1]
        c0, _ = idx[1][j]
        c1, _ = idx[1][j + 1]
        faces.append((a0, a1, c1, c0))
        _, d0 = idx[0][j]
        _, d1 = idx[0][j + 1]
        _, e0 = idx[1][j]
        _, e1 = idx[1][j + 1]
        faces.append((e0, e1, d1, d0))
    for j in (0, ny):
        t0, b0 = idx[0][j]
        t1, b1 = idx[1][j]
        faces.append((t0, b0, b1, t1) if j == 0 else (t1, b1, b0, t0))
    return _mesh_object(name, verts, faces, material, smooth=smooth)


def _dome_foot(name, cx, cy, dx, dy, material, *, thickness=FOOT_T, sink=0.07, nx=7, ny=7):
    """Splayed sole plate sampled onto the dome under a C-frame pier.

    A flat quad across 1.5 m of a 3.2 m dome either floats at the corners or
    buries itself at the edges. Every vertex here is projected onto the
    analytic surface, so the plate skins the curvature and the pier lands on
    a real foot rather than on four sampled points.
    """

    verts: list[tuple[float, float, float]] = []
    top: list[list[int]] = []
    bot: list[list[int]] = []
    for i in range(nx + 1):
        x = cx - dx / 2.0 + dx * i / nx
        rt, rb = [], []
        for j in range(ny + 1):
            y = cy - dy / 2.0 + dy * j / ny
            zs = _dome_z_at(math.hypot(x, y))
            rt.append(len(verts))
            verts.append((x, y, zs + thickness))
            rb.append(len(verts))
            verts.append((x, y, zs - sink))
        top.append(rt)
        bot.append(rb)
    faces: list[tuple[int, ...]] = []
    for i in range(nx):
        for j in range(ny):
            faces.append((top[i][j], top[i][j + 1], top[i + 1][j + 1], top[i + 1][j]))
            faces.append((bot[i + 1][j], bot[i + 1][j + 1], bot[i][j + 1], bot[i][j]))
    for i in range(nx):
        faces.append((top[i][0], top[i + 1][0], bot[i + 1][0], bot[i][0]))
        faces.append((bot[i][ny], bot[i + 1][ny], top[i + 1][ny], top[i][ny]))
    for j in range(ny):
        faces.append((bot[0][j], bot[0][j + 1], top[0][j + 1], top[0][j]))
        faces.append((top[nx][j], top[nx][j + 1], bot[nx][j + 1], bot[nx][j]))
    return _mesh_object(name, verts, faces, material, smooth=None)


def _raked_leg(name, base_xy, base_dims, top_xy, top_dims, top_z, material, *, base_dz=0.08):
    """C-frame pier: a raked slab lofted from a dome-conforming base quad.

    Every base corner's z is sampled from ``_dome_z_at`` and offset by
    ``base_dz`` — positive when the pier stands on a sole plate, negative when
    it is planted straight into the shell — so no corner floats.
    """

    def rect(cx, cy, dims):
        hx, hy = dims[0] / 2.0, dims[1] / 2.0
        return [
            (cx - hx, cy - hy),
            (cx + hx, cy - hy),
            (cx + hx, cy + hy),
            (cx - hx, cy + hy),
        ]

    base = rect(base_xy[0], base_xy[1], base_dims)
    top = rect(top_xy[0], top_xy[1], top_dims)
    verts = [(x, y, _dome_z_at(math.hypot(x, y)) + base_dz) for x, y in base]
    verts += [(x, y, top_z) for x, y in top]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7)]
    for i in range(4):
        j = (i + 1) % 4
        faces.append((i, j, j + 4, i + 4))
    return _mesh_object(name, verts, faces, material, smooth=None)


def build(materials):
    _verify_clearances()

    white = materials[f"{P}_rotor_white"]
    blue = materials[f"{P}_rotor_blue"]
    steel = materials[f"{P}_drum_steel"]  # dark fasteners and small hardware
    casting = materials[f"{P}_ramp_steel"]  # painted light-grey C-frame castings
    machined = materials[f"{P}_track_grey"]  # bright machined faces: bores, straps
    red = materials[f"{P}_needle_red"]  # asserted, never silently orange

    objs: list[bpy.types.Object] = []

    # --- pedestal dome + skirt band + inspection hatches -------------------
    objs.append(_dome(f"{P}_rotor_dome", white))

    # Royal-blue skirt: a profile-following band, 3.5 cm proud all the way up.
    # It tops out at 1.20 (with its lip occupying 1.15..1.25) so that NOTHING
    # else on the shell shares its z range — the old hatch "b" sat 5 mm off
    # the skirt over 22 cm of overlap and shimmered.
    skirt_lo, skirt_hi = 0.52, 1.20
    objs.append(_dome_band(f"{P}_rotor_skirt", skirt_lo, skirt_hi, blue))
    objs.append(
        bk.add_torus(
            f"{P}_rotor_skirt_lip",
            (0.0, 0.0, skirt_hi),
            _dome_r_at(skirt_hi) + 0.025,
            0.05,
            machined,
            major_segments=96,
            minor_segments=16,
        )
    )

    # Machined joint ring where the cap plate meets the swept shell — gives
    # the big white field a scale reference without adding another silhouette.
    objs.append(
        _dome_band(
            f"{P}_rotor_cap_joint", 2.36, 2.40, machined, out=0.022, sink=0.05, steps=2
        )
    )

    # Radial shell seams every 30 deg, INTERRUPTED wherever a hatch sits: the
    # dome was a featureless white field at 6.4 m across, which is the one
    # place the pedestal stopped reading as fabricated hardware.
    hatches = ((-128.0, 12.0), (-70.0, 9.0))
    for k in range(12):
        seam_deg = -180.0 + 30.0 * k
        if any(
            abs(((seam_deg - hc + 180.0) % 360.0) - 180.0) < hh + 3.0 for hc, hh in hatches
        ):
            continue
        objs.append(
            _dome_patch(
                f"{P}_rotor_seam_{k}",
                math.radians(seam_deg),
                math.radians(0.55),
                1.30,
                2.32,
                0.018,
                machined,
                sink=0.05,
                naz=2,
            )
        )

    # Two rectangular inspection hatches, deliberately ASYMMETRIC in azimuth,
    # height and size so the -Y dome face cannot read as a pair of eyes. Both
    # now live strictly ABOVE the skirt lip (1.25) and below the cap joint
    # (2.18): no shell feature shares a z band with another any more.
    for tag, phi_deg, half_deg, hz0, hz1, hw in (
        ("a", -128.0, 12.0, 1.68, 2.26, 0.040),
        ("b", -70.0, 9.0, 1.36, 1.80, 0.040),
    ):
        phi = math.radians(phi_deg)
        half = math.radians(half_deg)
        objs.append(
            _dome_patch(
                f"{P}_rotor_hatch_{tag}_frame", phi, half, hz0, hz1, hw, white
            )
        )
        objs.append(
            _dome_patch(
                f"{P}_rotor_hatch_{tag}_cover",
                phi,
                half * 0.72,
                hz0 + 0.10,
                hz1 - 0.10,
                hw + 0.016,
                machined,
                sink=0.02,
            )
        )
        # rivet line around the frame
        for k in range(5):
            zt = hz0 + 0.05 + (hz1 - hz0 - 0.10) * k / 4.0
            for side in (-1.0, 1.0):
                a = phi + side * half * 0.86
                rr = _dome_r_at(zt) + hw * 0.6
                objs.append(
                    bk.add_sphere(
                        f"{P}_rotor_hatch_{tag}_rivet_{k}{'p' if side > 0 else 'm'}",
                        (rr * math.cos(a), rr * math.sin(a), zt),
                        0.035,
                        steel,
                        segments=10,
                        rings=6,
                    )
                )

    # --- static hub stack: bedplate -> steel column -> drive housing -------
    # The stack is what carries the arm. Its top member saddles the blue band
    # on a derived bore, so the 14 m rotor is visibly BORNE rather than hung
    # in the air over a doorknob.
    objs.append(
        bk.add_cylinder(
            f"{P}_rotor_hub_bedplate",
            (0.0, 0.0, (BED_Z0 + BED_Z1) / 2.0),
            BED_R,
            BED_Z1 - BED_Z0,
            steel,
            vertices=72,
            bevel=0.02,
            # Round 15 (player: "curved floor... way too basic"): the
            # default cylinder UVs stretch the whole texture across the
            # cap, smearing the family's features into giant soft blobs.
            metric_uv=(2.0, 2.0),
        )
    )
    for sgn in (1.0, -1.0):
        for k, adeg in enumerate(BOLT_A):
            a = math.radians(adeg) + (0.0 if sgn > 0 else math.pi)
            objs.append(
                bk.add_cylinder(
                    f"{P}_rotor_hub_bolt_{'p' if sgn > 0 else 'm'}{k}",
                    (BOLT_RAD * math.cos(a), BOLT_RAD * math.sin(a), (BOLT_Z0 + BOLT_Z1) / 2.0),
                    BOLT_R,
                    BOLT_Z1 - BOLT_Z0,
                    machined,
                    vertices=10,
                    bevel=0.012,
                )
            )
    objs.append(
        bk.add_cylinder(
            f"{P}_rotor_hub_column",
            (0.0, 0.0, (COL_Z0 + COL_Z1) / 2.0),
            COL_R,
            COL_Z1 - COL_Z0,
            steel,
            vertices=72,
        )
    )
    # THE fix for the floating arm: a flat-bottomed machined block whose top
    # face is a 0.735 m groove concentric with the arm. Its shoulders stop
    # exactly at the arm axis (z 3.40), so it reads as the lower half of a
    # split bearing and the blue band is still the thing you see above it.
    objs.append(
        _saddle(
            f"{P}_rotor_hub_housing",
            0.0,
            HOUSE_HALF_X,
            HOUSE_Y,
            HOUSE_BORE,
            machined,
            base_z=HOUSE_Z0,
            ny=52,
        )
    )
    for kb, (hx, hy) in enumerate(HOUSE_BOLT):
        objs.append(
            bk.add_cylinder(
                f"{P}_rotor_hub_housing_bolt_{kb}",
                (hx, hy, ARM_Z + 0.05),
                0.07,
                0.16,
                steel,
                vertices=8,
            )
        )

    # --- rotor arm (all pieces named rotorarm_: the spinning assembly) -----
    objs.append(
        bk.add_cylinder(
            f"{P}_rotorarm_band",
            (0.0, 0.0, ARM_Z),
            BAND_R,
            2.0 * BAND_HALF,
            blue,
            vertices=64,
            axis="X",
            bevel=0.03,
        )
    )
    for tag, sx in (("e", 1.0), ("w", -1.0)):
        # Rotating labyrinth skirt: flares INBOARD to 0.745, overlapping the
        # static housing's 0.735 bore radially while standing 40 mm clear of
        # it along X. Nothing can be seen through the hub joint from any angle.
        objs.append(
            bk.add_cone(
                f"{P}_rotorarm_hubskirt_{tag}",
                (sx * (HUBSKIRT_X0 + HUBSKIRT_X1) / 2.0, 0.0, ARM_Z),
                HUBSKIRT_R_IN,
                HUBSKIRT_R_OUT,
                HUBSKIRT_X1 - HUBSKIRT_X0,
                blue,
                vertices=72,
                rotation=(0.0, sx * math.pi / 2.0, 0.0),
            )
        )
        objs.append(
            bk.add_cylinder(
                f"{P}_rotorarm_hubflange_{tag}",
                (sx * HUBFLANGE_X, 0.0, ARM_Z),
                HUBFLANGE_R,
                HUBFLANGE_W,
                steel,
                vertices=64,
                axis="X",
                bevel=0.02,
            )
        )

    for tag, sx in (("e", 1.0), ("w", -1.0)):
        mid = sx * (BAND_HALF + WHITE_END) / 2.0
        objs.append(
            bk.add_cylinder(
                f"{P}_rotorarm_white_{tag}",
                (mid, 0.0, ARM_Z),
                ARM_R,
                WHITE_END - BAND_HALF,
                white,
                vertices=64,
                axis="X",
                bevel=0.02,
            )
        )
        # Panel straps: 15 mm proud, 55 mm wide, matte machined grey. At the
        # old 3 mm / 32 mm they were a z-fight and an aliasing source rather
        # than a read; now they are real skin straps.
        for lk, lx in enumerate(LINE_X):
            objs.append(
                bk.add_cylinder(
                    f"{P}_rotorarm_line_{tag}{lk}",
                    (sx * lx, 0.0, ARM_Z),
                    LINE_R,
                    LINE_W,
                    machined,
                    vertices=64,
                    axis="X",
                    bevel=0.008,
                )
            )
        # Machined service duct: a directional spine along the white skin. It
        # STOPS at |x| 3.25, outboard of the pillow blocks, because a raised
        # spine physically cannot pass through a bearing bore.
        objs.append(
            bk.add_box(
                f"{P}_rotorarm_duct_{tag}",
                (
                    sx * (DUCT_X0 + DUCT_X1) / 2.0,
                    0.0,
                    (DUCT_Z_LO + DUCT_Z_HI) / 2.0,
                ),
                (DUCT_X1 - DUCT_X0, 2.0 * DUCT_HALF_Y, DUCT_Z_HI - DUCT_Z_LO),
                machined,
                bevel=0.02,
            )
        )
        # Two cooling-fin stacks per side: an inboard pair just outside the
        # bearing window and a triple at the tip.
        for k, fx in enumerate(FIN_X):
            objs.append(
                bk.add_cylinder(
                    f"{P}_rotorarm_fin_{tag}{k}",
                    (sx * fx, 0.0, ARM_Z),
                    FIN_R,
                    FIN_W,
                    machined,
                    vertices=64,
                    axis="X",
                    bevel=0.018,
                )
            )
        # Blue end collar, then a BLUNT WHITE nose: a blue taper to a 0.30 m
        # point read as a naval cannon rather than as rotor hardware.
        objs.append(
            bk.add_cylinder(
                f"{P}_rotorarm_collar_{tag}",
                (sx * COLLAR_X, 0.0, ARM_Z),
                COLLAR_R,
                COLLAR_W,
                blue,
                vertices=64,
                axis="X",
                bevel=0.03,
            )
        )
        objs.append(
            bk.add_cone(
                f"{P}_rotorarm_cap_{tag}",
                (sx * (CONE_X0 + TIP_X) / 2.0, 0.0, ARM_Z),
                ARM_R,
                TIP_R,
                TIP_X - CONE_X0,
                white,
                vertices=64,
                rotation=(0.0, sx * math.pi / 2.0, 0.0),
            )
        )
        objs.append(
            bk.add_cylinder(
                f"{P}_rotorarm_nose_{tag}",
                (sx * (TIP_X + 0.03), 0.0, ARM_Z),
                TIP_R + 0.02,
                0.06,
                machined,
                vertices=64,
                axis="X",
                bevel=0.015,
            )
        )

    # --- red auxiliary pod, genuinely SLUNG under the arm ------------------
    # 0.13 m of daylight between the pod skin and the arm skin, on two steel
    # straps. Sited at |x| 3.30..4.00 — see the module docstring: this is the
    # innermost station where a standing-off pod survives bottom dead centre
    # against the on-brief pedestal cap.
    objs.append(
        bk.add_cylinder(
            f"{P}_rotorarm_aux",
            ((POD_X0 + POD_X1) / 2.0, POD_Y, POD_Z),
            POD_R,
            POD_X1 - POD_X0,
            red,
            vertices=72,
            axis="X",
            bevel=0.03,
        )
    )
    for tag, ex in (("in", POD_X0), ("out", POD_X1)):
        objs.append(
            bk.add_cylinder(
                f"{P}_rotorarm_aux_cap_{tag}",
                (ex, POD_Y, POD_Z),
                POD_CAP_R,
                0.07,
                steel,
                vertices=72,
                axis="X",
                bevel=0.02,
            )
        )
    for tag, sxp in (("a", STRAP_X[0]), ("b", STRAP_X[1])):
        objs.append(
            bk.add_box(
                f"{P}_rotorarm_aux_strap_{tag}",
                (
                    sxp,
                    -STRAP_MID_D * math.sin(POD_ANG),
                    ARM_Z - STRAP_MID_D * math.cos(POD_ANG),
                ),
                STRAP_DIMS,
                steel,
                rotation=(math.pi - POD_ANG, 0.0, 0.0),
                bevel=0.02,
            )
        )

    # --- C-frame bearing supports flanking the hub at x = +-2.6 ------------
    # Each frame is: two dome-conforming sole plates, two raked cast piers
    # with a raised rib down the outer face, a pillow block per pier (the
    # LOWER half of the bearing, bored to the same radius as the cap), an
    # arced cradle closing the C under the arm, and a bolted cap arch.
    for tag, sx in (("e", 1.0), ("w", -1.0)):
        fx = sx * FRAME_X
        for side, sy in (("n", 1.0), ("s", -1.0)):
            objs.append(
                _dome_foot(
                    f"{P}_rotor_cframe_{tag}_foot_{side}",
                    sx * FOOT_C[0],
                    sy * FOOT_C[1],
                    FOOT_DIMS[0],
                    FOOT_DIMS[1],
                    casting,
                )
            )
            objs.append(
                _raked_leg(
                    f"{P}_rotor_cframe_{tag}_leg_{side}",
                    (sx * LEG_BASE_C[0], sy * LEG_BASE_C[1]),
                    LEG_BASE_DIMS,
                    (sx * LEG_TOP_C[0], sy * LEG_TOP_C[1]),
                    LEG_TOP_DIMS,
                    LEG_TOP_Z,
                    casting,
                )
            )
            objs.append(
                _raked_leg(
                    f"{P}_rotor_cframe_{tag}_rib_{side}",
                    (sx * RIB_BASE_C[0], sy * RIB_BASE_C[1]),
                    RIB_BASE_DIMS,
                    (sx * RIB_TOP_C[0], sy * RIB_TOP_C[1]),
                    RIB_TOP_DIMS,
                    LEG_TOP_Z,
                    casting,
                )
            )
            objs.append(
                bk.add_box(
                    f"{P}_rotor_cframe_{tag}_pillow_{side}",
                    (
                        fx,
                        sy * (PILLOW_Y0 + PILLOW_Y1) / 2.0,
                        (PILLOW_Z0 + PILLOW_Z1) / 2.0,
                    ),
                    (
                        2.0 * PILLOW_X_HALF,
                        PILLOW_Y1 - PILLOW_Y0,
                        PILLOW_Z1 - PILLOW_Z0,
                    ),
                    casting,
                    bevel=0.05,
                )
            )
            for bi, bxo in enumerate((-0.40, 0.40)):
                objs.append(
                    bk.add_cylinder(
                        f"{P}_rotor_cframe_{tag}_capbolt_{side}{bi}",
                        (fx + bxo, sy * 0.90, PILLOW_Z1 + 0.06),
                        0.075,
                        0.22,
                        steel,
                        vertices=8,
                    )
                )
        objs.append(
            _saddle(
                f"{P}_rotor_cframe_{tag}_tie",
                sx * CRADLE_X,
                CRADLE_HALF_X,
                CRADLE_Y_HALF,
                CRADLE_R,
                casting,
                thickness=CRADLE_T,
                top_cap_z=CRADLE_TOP_Z,
                ny=36,
            )
        )
        # Bearing cap arch: light-grey machined casting, not dark steel — a
        # near-black boot clamped on the white arm read as a rubber gaiter.
        # It tucks below the pillow joint line so its ends are swallowed.
        objs.append(
            _arch_x(
                f"{P}_rotor_cframe_{tag}_bearing_ring",
                (fx, 0.0, ARM_Z),
                RING_IN,
                RING_OUT,
                RING_HALF_W,
                casting,
                u0=-RING_U_TUCK,
                u1=math.pi + RING_U_TUCK,
            )
        )

    return objs
