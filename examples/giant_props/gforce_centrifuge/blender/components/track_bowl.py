"""Track bowl: CHIEF-style hypergravity dish.

A cool light-grey machined cone floor (r 2..15.2, z 0.5..2.48) carrying
16 parallel-sided radial seam grooves and four circumferential inspection
channels, rolling tangent-continuously into a DRIVABLE concave velodrome
bank (r 15.2..19.5, ~44 deg average, 53.7 deg peak, 50 deg at the lip)
in the same machined grey.  Four single-line shutlines ring the bank, a
flush bolted apron strap crosses the r 16 datum, eight royal-blue
spokes are inlaid from a blue hub band out to r 15.8, the lip carries a
hazard band / cornice / bead, and 24 tapered triangular gussets brace the
full height of the outer drum.  Centre r < 2.0 stays open for the rotor
pedestal.

Everything is a surface of revolution built on ONE azimuth resolution
(``AZIMUTH_STEPS``) so no ring can dive under or over another.
"""

from __future__ import annotations

import math

import bmesh
import bpy

import spec
from proplib import blender_kit as bk

TAU = 2.0 * math.pi

# Single azimuth resolution for the whole component.  Every ring uses
# this (or an exact divisor at tiny radii) so concentric details never
# cross-thread the dish tessellation.
AZIMUTH_STEPS = 192

# --- Cone floor -------------------------------------------------------
CONE_R0, CONE_Z0 = 2.0, 0.5
CONE_SLOPE = 0.15  # (2.6 - 0.5) / (16.0 - 2.0)

# --- Velodrome bank ---------------------------------------------------
# Critic round 1: BANK_R0 = 16.65 gave 4.4 m of rise over 2.85 m of run
# (57 deg average, 74.5 deg at the lip) - a bucket, not a velodrome.
# Starting the roll at 15.2 buys 4.30 m of run for 4.52 m of rise:
# 44 deg average, 8.5 deg at the foot, 53.7 deg peak, 50 deg at the lip.
# The Hermite is tangent-matched to the cone at s = 0, so the surface
# still reads as the contract cone out past r 16 (0.23 m high there).
BANK_R0 = 15.20
BANK_R1, BANK_Z1 = 19.50, 7.00
BANK_DR = BANK_R1 - BANK_R0
BANK_Z0 = CONE_Z0 + (BANK_R0 - CONE_R0) * CONE_SLOPE
# Round 2: 1.43 (55 deg) made the top metre a wall-ride.  1.19 caps the
# lip at 50 deg and drops the profile's steepest point from 55.3 to 53.7
# deg (measured over the whole arc), moving it off the lip and down to
# s 0.72 where a car still has the wall under it.  Costs 0.03 m of extra
# rise at r 16.
BANK_SLOPE_TOP = 1.19  # tan(50 deg)

# --- Rim ---------------------------------------------------------------
CORNICE_R = 19.74  # widest circle in the component; nothing exceeds it
BEAD_MAJOR, BEAD_MINOR = 19.62, 0.10
HAZARD_ARC = 1.55  # metres of profile taken by the hazard band
HAZARD_TILE = 6.0  # world-square texture tile -> ~0.75 m chevrons

# --- Outer drum wall ---------------------------------------------------
WALL_Z_TOP = 6.86
WALL_R_BOT, WALL_R_TOP = 18.60, 19.72
# The plinth is the machined base course every gusset foot stands on, so
# it has to reach past them (19.48).  Round 2 pulled it in 0.15 m, gave it
# a chamfered two-step section, a bolt row and drum_steel instead of
# near-black pylon_dark, so it reads as a base and not a rubber mat.
PLINTH_Z, PLINTH_R = 0.40, 19.55
GIRTH_Z = 6.10  # hoop above the gusset apexes, below the rim bolt row

# --- Bolted apron strap straddling the r 16 datum ----------------------
# Round 2: this crosses the racing line at the exact radius a car climbs
# onto the bank, so the strap is now a flush inlay and the bolt heads are
# 16 mm domes, not 75 mm studs.
STRAP_R0, STRAP_R1 = 15.90, 16.55
STRAP_PROUD = 0.012
STRAP_BOLTS = 72

# --- Recessed radial seam grooves in the cone floor -------------------
# Two tiers so the floor has more than one detail frequency: 16 long
# joints run from the hub field out to the apron, and 16 short joints
# interleave between them across the outer third only.  32 * 11.25 deg,
# offset 5.625 deg, so no seam ever lands on a spoke (multiples of 45).
SEAM_COUNT = 32
SEAM_AZ0 = math.radians(5.625)
# A machined joint is a thin deep shutline, not a trough: 0.36 m wide by
# 0.09 deep read as soft drainage swales in the zoom.  0.15 m wide by
# 0.13 deep with a 76 deg wall holds a hard shadow instead.
#
# DRIVABILITY (2026-08-07, player: "gets hung up on stuff"): 0.13 deep was
# chosen for the zoom render with no regard for the tyre.  A 0.15 m wide
# by 0.13 m deep slot is narrower than a contact patch and deeper than a
# sidewall - 32 of them per lap ate the suspension.  A shutline only has
# to out-shadow its own chamfer to read, so 0.02 keeps the hard line and
# gives back a raceway.  Same reasoning for every other relief constant
# in this file: nothing on the driven surface exceeds +/-0.02 m.
SEAM_HALF = 0.075
SEAM_CHAMFER = 0.035
SEAM_DEPTH = 0.02
SEAM_R_IN_LONG, SEAM_R_IN_SHORT = 3.20, 9.60
SEAM_R_OUT = 14.60
SEAM_TERMINUS = 0.16  # short chamfered end ramp, not a long taper
# Fixed angular window reserved per seam: keeps the vertex ordering
# identical on every profile row even though the seam is a constant
# METRIC width (so its angular half-width shrinks with radius).
SEAM_WINDOW = (SEAM_HALF + SEAM_CHAMFER) / SEAM_R_IN_LONG * 1.22

# --- Circumferential inspection channels in the cone floor ------------
CHANNELS = (4.20, 6.30, 9.40, 12.50)
CH_HALF, CH_CHAMFER, CH_DEPTH = 0.11, 0.04, 0.015

# --- Spokes ------------------------------------------------------------
SPOKE_COUNT = 8
# R1 stops AT the cone lip.  Running the spokes 0.6 m up onto the bank
# looked right over solid bank, but the doorway sector has no bank: the
# az-270 spoke hung over the void as a 1.44 m wide tongue standing 0.31 m
# above the ramp - a step across the entry threshold, exactly where the
# player's car stopped.  Spokes belong to the flat deck.
SPOKE_R0, SPOKE_R1 = 2.46, BANK_R0
SPOKE_HALF_HUB, SPOKE_HALF_MAIN = 0.30, 0.72  # 1.44 m wide on the flat
SPOKE_HALF_R = 6.0
SPOKE_CHAMFER = 0.05  # 46 deg bevel: stays above any auto-smooth angle
# PROUD 0.062 / SINK 0.130 put a 0.05 m wide, 0.19 m deep slot down BOTH
# edges of all eight spokes - sixteen radial wheel-traps across the track
# (measured worst step inside a 1.6 m wheel track: 197 mm).  The inlay
# reads from the colour change, not the relief, so both shrink to a lip.
SPOKE_PROUD, SPOKE_SINK = 0.010, 0.018

# --- Hub -------------------------------------------------------------
# Round 2: a 0.36 m band standing 0.046 proud lost the centre silhouette
# to the 0.10-minor steel opening bead.  The band is now 0.64 m wide and
# 0.115 proud and the bead's minor radius is halved, so the blue collar
# wins the hub read and the spokes visibly spring from it.
HUB_R0, HUB_R1 = 2.06, 2.70
HUB_PROUD = 0.115
OPENING_BEAD_MINOR = 0.055

# --- Bank profile rings ------------------------------------------------
# Round 2: four rings bunched into the top half (0.46..0.93), each a
# flat-bottomed recess contributing TWO chamfer lines, read as a stamped
# tin pie dish.  They are now single V shutlines spread over the whole
# arc, and the bank's sharp angle is raised so only the V bottom breaks
# shading - one line per ring, four rings, evenly spaced.
# 0.10 deep was the deck-seam mistake repeated on the banked wall: four
# 0.20 m wide, 0.10 m deep circumferential grooves right where the car
# wall-rides at 100 m/s (the player's 50 RPM frame shows it bouncing over
# them). Same reasoning as SEAM_DEPTH - the shutline only has to out-shadow
# its own chamfer. Nothing driven exceeds +/-0.02 m.
BANK_RING_HALF, BANK_RING_DEPTH = 0.10, 0.02
BANK_RING_FRACTIONS = (0.18, 0.38, 0.58, 0.78)

# --- Gussets -----------------------------------------------------------
GUSSET_COUNT = 24
GUSSET_Z_BOT = PLINTH_Z - 0.04  # sunk into the plinth: no coplanar fight
# Round 2: an apex at 3.05 on a 6.86 m wall braced nothing and left the
# whole upper drum blank.  5.60 runs the ribs up under the rim hoop.
GUSSET_Z_TOP = 5.60
GUSSET_R_FOOT = 19.48  # lands on the plinth (19.55), under the cornice
GUSSET_HALF_T = 0.12
GUSSET_ROLL = 0.05  # rolled edge along the exposed hypotenuse


def cone_z(r: float) -> float:
    """Ideal (ungrooved) cone line."""

    return CONE_Z0 + (r - CONE_R0) * CONE_SLOPE


def bank_z(s: float) -> float:
    """Cubic Hermite bank, tangent-continuous with the cone at s = 0."""

    h00 = 2 * s**3 - 3 * s**2 + 1
    h10 = s**3 - 2 * s**2 + s
    h01 = -2 * s**3 + 3 * s**2
    h11 = s**3 - s**2
    return (
        h00 * BANK_Z0
        + h10 * BANK_DR * CONE_SLOPE
        + h01 * BANK_Z1
        + h11 * BANK_DR * BANK_SLOPE_TOP
    )


def bank_point(s: float) -> tuple[float, float]:
    return BANK_R0 + BANK_DR * s, bank_z(s)


def deck_z(r: float) -> float:
    """Ideal drivable surface height: cone below r 15.2, bank above."""

    if r <= BANK_R0:
        return cone_z(r)
    return bank_z(min((r - BANK_R0) / BANK_DR, 1.0))


def deck_frame(r: float) -> tuple[float, float, float]:
    """(z, normal_r, normal_z) of the ideal deck at radius ``r``."""

    h = 2e-3
    slope = (deck_z(r + h) - deck_z(max(CONE_R0, r - h))) / (r + h - max(CONE_R0, r - h))
    length = math.hypot(1.0, slope)
    return deck_z(r), -slope / length, 1.0 / length


def _bank_frame(s: float) -> tuple[float, float, float, float, float]:
    """(r, z, normal_r, normal_z, arc_rate) at parameter ``s``."""

    h = 1e-4
    s0, s1 = max(0.0, s - h), min(1.0, s + h)
    r0, z0 = bank_point(s0)
    r1, z1 = bank_point(s1)
    dr, dz = r1 - r0, z1 - z0
    length = math.hypot(dr, dz)
    tr, tz = dr / length, dz / length
    # Rotate the tangent +90 deg: points up out of the bowl interior.
    return (*bank_point(s), -tz, tr, length / (s1 - s0))


def _bank_arc_table(steps: int = 600) -> tuple[list[float], list[float]]:
    ss = [i / steps for i in range(steps + 1)]
    arc = [0.0]
    for a, b in zip(ss, ss[1:]):
        ra, za = bank_point(a)
        rb, zb = bank_point(b)
        arc.append(arc[-1] + math.hypot(rb - ra, zb - za))
    return ss, arc


def _s_at_arc(target: float) -> float:
    ss, arc = _bank_arc_table()
    for i in range(len(arc) - 1):
        if arc[i + 1] >= target:
            span = arc[i + 1] - arc[i]
            t = 0.0 if span <= 0.0 else (target - arc[i]) / span
            return ss[i] + (ss[i + 1] - ss[i]) * t
    return 1.0


BANK_ARC_TOTAL = _bank_arc_table()[1][-1]
BANK_S_HAZARD = _s_at_arc(BANK_ARC_TOTAL - HAZARD_ARC)


def wall_r(z: float) -> float:
    return WALL_R_BOT + (WALL_R_TOP - WALL_R_BOT) * (z / WALL_Z_TOP)


def _smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


# ----------------------------------------------------------------------
# Mesh helpers
# ----------------------------------------------------------------------


def _sharpen(mesh, sharp_deg: float) -> None:
    """Mark edges sharper than ``sharp_deg`` as sharp.

    ``bpy.ops.object.shade_auto_smooth`` is a NO-OP under
    ``--factory-startup --background``: it wants the "Smooth by Angle"
    node group from the bundled essentials asset library, which never
    loads (the "Asset loading is unfinished" warnings in the harness log),
    so it silently adds no modifier.  Every mesh in this component was
    therefore fully smooth-shaded with zero sharp edges - that is what
    melted the gusset plates and pillowed the spokes into blue tubes.
    Blender 4.1+ honours the ``sharp_edge`` attribute directly when it
    computes normals, so setting it by hand needs no modifier at all.
    """

    threshold = math.radians(sharp_deg)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.normal_update()
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            edge.smooth = edge.calc_face_angle(math.pi) <= threshold
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


def _finish_mesh(
    name,
    verts,
    faces,
    material,
    *,
    sharp_deg=32.0,
    uv=None,
    uv_tile=4.0,
    smooth=True,
):
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if uv == "planar":
        layer = mesh.uv_layers.new(name="UVMap")
        for poly in mesh.polygons:
            for loop_index in poly.loop_indices:
                co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
                layer.data[loop_index].uv = (co.x / uv_tile, co.y / uv_tile)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, material)
    if not smooth:
        for poly in mesh.polygons:
            poly.use_smooth = False
        return obj
    for poly in mesh.polygons:
        poly.use_smooth = True
    _sharpen(mesh, sharp_deg)
    return obj


def _swept_mesh(
    name: str,
    profile: list[tuple[float, float]],
    material,
    *,
    flip: bool = False,
    sharp_deg: float = 32.0,
    tile_m: float | None = None,
    skip_az: tuple[float, float] | None = None,
    skip_frac: float = 0.72,
    z_remap=None,
):
    """Closed surface of revolution from an (r, z) profile polyline.

    ``tile_m`` lays a cylindrical UV grid whose tiles are ``tile_m``
    metres square in world space, so diagonal textures stay diagonal.
    ``z_remap(r, z, az_deg)`` may reshape individual vertices (the
    doorway fairing) - the UV arc lengths stay those of the base
    profile, which is exact everywhere the remap is identity and a
    centimetre-level stretch inside the faired sector.
    """

    verts = []
    for r, z in profile:
        for j in range(AZIMUTH_STEPS):
            a = TAU * j / AZIMUTH_STEPS
            zz = z if z_remap is None else z_remap(r, z, math.degrees(a))
            verts.append((r * math.cos(a), r * math.sin(a), zz))
    arc = [0.0]
    for (r0, z0), (r1, z1) in zip(profile, profile[1:]):
        arc.append(arc[-1] + math.hypot(r1 - r0, z1 - z0))
    mean_r = sum(r for r, _ in profile) / len(profile)
    faces = []
    face_uvs = []
    for i in range(len(profile) - 1):
        for j in range(AZIMUTH_STEPS):
            jn = (j + 1) % AZIMUTH_STEPS
            if skip_az is not None:
                # Native doorway: omit faces inside the azimuth window.
                # Booleans against these OPEN surfaces shredded the mesh
                # (player: "the track is transparent"), so the opening is
                # authored instead of cut.
                mid_deg = math.degrees(TAU * (j + 0.5) / AZIMUTH_STEPS) % 360.0
                lo, hi = skip_az
                inside = lo <= mid_deg <= hi if lo <= hi else (mid_deg >= lo or mid_deg <= hi)
                # skip_frac: how much of the profile (from the low end)
                # the window opens. The historic 0.72 default made every
                # doorway "a portal, not a missing sector" - right for
                # the outer shell, but on the BANK it left the top 28% of
                # rows standing as a jamb-to-jamb wall across the mouth:
                # the player's green-circled "grey metal door" (found by
                # DAE raycast + Blender face census, 2026-08-09, after
                # the hazard-band cut alone proved insufficient). Rings
                # whose closed state is restored by the door leaf pass
                # 1.0 for a true full-height opening.
                low_enough = (i + 1) <= max(
                    1, int((len(profile) - 1) * skip_frac))
                if inside and low_enough:
                    continue
            a = i * AZIMUTH_STEPS + j
            b = (i + 1) * AZIMUTH_STEPS + j
            c = (i + 1) * AZIMUTH_STEPS + jn
            d = i * AZIMUTH_STEPS + jn
            face = (a, b, c, d)  # normal +Z for inner->outer ring order
            quad_uv = None
            if tile_m is not None:
                # WHOLE-TILE WRAP (2026-08-10, player: "the seam doesn't
                # cleanly fit together with the yellow and black strips").
                # u ran 0 .. circumference/tile_m, which is essentially
                # never an integer - so at azimuth 0, where the last
                # column meets the first, u fell back to 0 from a
                # FRACTIONAL tile and the chevrons jumped phase. One
                # straight radial seam in an otherwise perfect ring, and
                # unmissable on a diagonal pattern.
                #
                # Rounding the span to whole tiles makes the wrap exact by
                # construction. It stretches the tile by at most half a
                # tile spread over the whole circumference (here well
                # under 1%), which no eye can see - unlike the seam.
                # Applies to every ring this builder makes, so the same
                # latent seam is gone from the bank and cornice too.
                tiles = max(1.0, round(TAU * mean_r / tile_m))
                u0 = j / AZIMUTH_STEPS * tiles
                u1 = (j + 1) / AZIMUTH_STEPS * tiles
                v0 = arc[i] / tile_m
                v1 = arc[i + 1] / tile_m
                quad_uv = ((u0, v0), (u0, v1), (u1, v1), (u1, v0))
            if flip:
                face = tuple(reversed(face))
                if quad_uv is not None:
                    quad_uv = tuple(reversed(quad_uv))
            faces.append(face)
            face_uvs.append(quad_uv)

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    if tile_m is not None:
        layer = mesh.uv_layers.new(name="UVMap")
        for poly, quad_uv in zip(mesh.polygons, face_uvs):
            for loop_index, uv in zip(poly.loop_indices, quad_uv):
                layer.data[loop_index].uv = uv
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, material)
    for poly in mesh.polygons:
        poly.use_smooth = True
    _sharpen(mesh, sharp_deg)
    return obj


# --- Doorway fairing (build 95) ----------------------------------------
# The collision cage has faired the doorway-flank bank columns toward the
# mouth deck since b93 (spec.FAIR_KEEP), but the VISUAL bank stayed full
# height - a car riding the faired collision looked sunk INSIDE the bank
# sheet, which is the player's "vehicles fall into entrance / the mesh
# doesn't close up" screenshot (2026-08-09). These helpers pull the
# visual sheet (and the jamb tops) onto the same swale so what you see
# is what you ride. Cut planes sit at the CAGE's column azimuths
# (20/22 of 28), and the blend spans exactly one wall segment - the same
# span the cage's flank quads interpolate over.
_DOOR_CUT_LO = 20 * 360.0 / spec.WALL_SEGMENTS
_DOOR_CUT_HI = 22 * 360.0 / spec.WALL_SEGMENTS
_FAIR_BLEND_DEG = 360.0 / spec.WALL_SEGMENTS


def _fair_keep_at(radius: float) -> float:
    """FAIR_KEEP factor at ``radius``: linear between bank level radii,
    1.0 at and beyond level 5 (the lintel band stays full height)."""
    knots = [
        (r, spec.FAIR_KEEP.get(level, 1.0))
        for level, (r, _z) in enumerate(spec.BANK_PROFILE)
    ]
    if radius <= knots[0][0]:
        return 1.0
    for (r0, k0), (r1, k1) in zip(knots, knots[1:]):
        if radius <= r1:
            t = (radius - r0) / (r1 - r0)
            return k0 + (k1 - k0) * t
    return 1.0


def _fair_weight(az_deg: float) -> float:
    a = az_deg % 360.0
    if _DOOR_CUT_LO <= a <= _DOOR_CUT_HI:
        return 1.0
    d = min(abs(a - _DOOR_CUT_LO), abs(a - _DOOR_CUT_HI))
    return max(0.0, 1.0 - d / _FAIR_BLEND_DEG)


def _fair_z(r: float, z: float, az_deg: float) -> float:
    # Doorway arch rides ON TOP of the fairing, not instead of it: the
    # fairing pulls levels 1..4 DOWN to the mouth deck (the drivable
    # swale) while the arch lifts the lintel band UP over the opening
    # (r >= DOOR_ARCH_R0 = 17.35). On THIS mesh the arch term is zero at
    # every vertex that exists - the arch window ends inside the visual
    # cut sector (see spec) - it is kept here so the jambs, which sample
    # _fair_z at the cut boundary, and any future ring that samples this
    # remap stay consistent with the cage by construction.
    arch = spec.door_arch(az_deg, r)
    if z <= spec.FAIR_DECK_Z:
        return z + arch
    w = _fair_weight(az_deg)
    if w <= 0.0:
        return z + arch
    keep = _fair_keep_at(r)
    factor = 1.0 - w * (1.0 - keep)
    return spec.FAIR_DECK_Z + (z - spec.FAIR_DECK_Z) * factor + arch


def _bank_z_full(radius: float) -> float:
    """FULL bank profile height at ``radius``: linear between the cage's
    BANK_PROFILE knots, so the raised patch is chord-exact with the
    unfaired cage quads it hands cars to at its azimuth edges."""
    knots = list(spec.BANK_PROFILE)
    if radius <= knots[0][0]:
        return knots[0][1]
    for (r0, z0), (r1, z1) in zip(knots, knots[1:]):
        if radius <= r1:
            return z0 + (z1 - z0) * (radius - r0) / (r1 - r0)
    return knots[-1][1]


def build_mouth_shelf(materials):
    """The doorway's SEAMLESS closure (build 100, player: "the entrance
    when closed should be seamless, there shouldn't be a divot both
    visually or in mesh").

    The b95-b99 shelf continued the FAIRED swale, which fixed fall-ins
    but left the closed mouth a visible scooped depression. This patch
    is the FULL BANK PROFILE carried straight across the doorway: it
    spans cage columns 19..23 (the doorway plus both faired flank
    segments), its top is _bank_z_full everywhere, and every boundary
    vertex tucks 6 mm UNDER the surrounding static geometry (the
    bowl's own junction-band hem trick) so the patch emerges through
    the faired sheet with a hairline shutline seam instead of an
    exposed edge. At the azimuth ends (cols 19/23) the static bank is
    unfaired, so the hand-off is a 6 mm hem over an already-flush
    chord; the sagging faired flank collision is buried beneath the
    patch when raised and becomes the surface again when the patch is
    buried at idle. The closed leaf sits 25 mm below the track line
    and vanishes under this skin entirely.
    """
    ramp_steel = materials[f"{spec.MOD_ID}_ramp_steel"]
    drum_steel = materials[f"{spec.MOD_ID}_drum_steel"]

    # Base grid: unchanged since b101 - it spans cols 19..23 because the
    # faired flank swale needs covering. The b140 full-height rows live
    # in a SEPARATE window-only grid below: putting them in this grid
    # would lay pure-profile collision over the flank azimuths where the
    # static bank already stands at pure profile - coincident
    # double-wound sheets, the b85 tire-popper class.
    radii = [15.22, 15.45, 15.737, 16.275, 16.812, 17.35, 17.6, 17.867]
    floor_z = 1.95
    az_steps = 16
    az0 = math.radians(19 * 360.0 / spec.WALL_SEGMENTS)
    az1 = math.radians(23 * 360.0 / spec.WALL_SEGMENTS)
    hem = 0.006

    cols = az_steps + 1
    rows = len(radii)
    verts: list[tuple[float, float, float]] = []
    for i, r in enumerate(radii):
        for j in range(cols):
            a = az0 + (az1 - az0) * j / az_steps
            # Deliberately NO spec.door_arch here (2026-08-12): the
            # closed mouth is the seamless-closure law's surface - pure
            # BANK_PROFILE, an unbroken velodrome. The arch is a
            # collision-only soffit ABOVE this patch; the pocket between
            # patch top and arched soffit is unreachable while sealed
            # (orbits r 14..16.8, pocket starts r 17.35 above z 4.9).
            # b137 briefly arched this patch and the raised closure grew
            # a 2.4 m hump - exactly the divot-in-reverse the law bans.
            z = _bank_z_full(r)
            if i == 0 or i == rows - 1 or j == 0 or j == az_steps:
                z -= hem
            verts.append((r * math.cos(a), r * math.sin(a), z))
    top = [(r, _bank_z_full(r)) for r in radii]
    floor_rows = []
    for r in (radii[0], radii[-1]):
        row = len(verts) // cols
        floor_rows.append(row)
        for j in range(cols):
            a = az0 + (az1 - az0) * j / az_steps
            verts.append((r * math.cos(a), r * math.sin(a), floor_z))

    def vid(row: int, col: int) -> int:
        return row * cols + col

    deck_faces = []
    body_faces = []
    for i in range(len(top) - 1):
        for j in range(az_steps):
            deck_faces.append(
                (vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1))
            )
    fin, fout = floor_rows
    for j in range(az_steps):
        # Floor, wound down; inner lip faces inboard; back wall outboard.
        body_faces.append(
            (vid(fin, j), vid(fin, j + 1), vid(fout, j + 1), vid(fout, j))
        )
        body_faces.append(
            (vid(0, j), vid(0, j + 1), vid(fin, j + 1), vid(fin, j))
        )
        body_faces.append(
            (vid(len(top) - 1, j + 1), vid(len(top) - 1, j),
             vid(fout, j), vid(fout, j + 1))
        )
    for col, first in ((0, True), (az_steps, False)):
        ring = [vid(i, col) for i in range(len(top))]
        cap = ring + [vid(fout, col), vid(fin, col)]
        # Wind each cap so its normal faces AWAY from the doorway span.
        if first:
            cap = list(reversed(cap))
        body_faces.append(tuple(cap))

    # --- The lintel, resurrected as part geometry (b141) ---------------
    # The static lintel is gone (spec.DOOR_CUT_LEVELS = 8); while SEALED
    # this sub-grid IS the wall across the window. b140 built it as a
    # fresh grid at NOMINAL radii, 30 mm recessed, 3.2-deg chords - and
    # the player caught cars on it immediately ("catching on the
    # geometry surrounding the door once spinning"): the cage is
    # CIRCUMSCRIBED (radius * sec(pi/28)), so nominal radii sat ~11 cm
    # INBOARD of the static flank surface, and the recess added a 3 cm
    # z-step - two ledges per crossing, hit twice per revolution under
    # multi-g field load. The b136 lintel, by contrast, was ridden for
    # days without complaint. So THIS IS THAT LINTEL, verbatim: the
    # exact node positions (sec radii, pure z) and the exact 12.857-deg
    # chords of the quads DOOR_CUT_LEVELS removed - three columns
    # (cage cols 20/21/22), BANK_PROFILE levels 5..8, six quads. When
    # raised, the sealed wall is bit-identical to the geometry that was
    # always there; when buried, the window is open to the containment
    # ring. Shared boundary LINES with the static quads at the window
    # edges are mesh adjacency, not overlap - no hems on this grid, a
    # tucked edge here would be a step on the riding face.
    # Closed-state cosmetics: at pure profile this skins 25 mm over the
    # door leaf's courses, so the sealed doorway's upper band reads as
    # plain steel instead of the leaf's hazard course. Accepted: the
    # sealed state is only ever seen by the sample being spun, and
    # collision correctness beat cosmetics three regressions running.
    sec = 1.0 / math.cos(math.pi / spec.WALL_SEGMENTS)
    lin_levels = list(spec.BANK_PROFILE[5:])          # levels 5..8
    lin_cols = (20, 21, 22)
    lbase = len(verts)
    for r, zl in lin_levels:
        for k in lin_cols:
            a = math.radians(k * 360.0 / spec.WALL_SEGMENTS)
            verts.append((math.cos(a) * r * sec, math.sin(a) * r * sec, zl))

    def lvid(row: int, col: int) -> int:
        return lbase + row * len(lin_cols) + col

    for i in range(len(lin_levels) - 1):
        for j in range(len(lin_cols) - 1):
            deck_faces.append(
                (lvid(i, j), lvid(i + 1, j), lvid(i + 1, j + 1),
                 lvid(i, j + 1))
            )

    def submesh(name, faces, material, tile):
        # Each object carries only the vertices its faces use - loose
        # verts in a part DAE are exporter noise.
        used = sorted({index for face in faces for index in face})
        remap = {old: new for new, old in enumerate(used)}
        return _finish_mesh(
            name,
            [verts[index] for index in used],
            [tuple(remap[index] for index in face) for face in faces],
            material,
            sharp_deg=40.0, uv="planar", uv_tile=tile,
        )

    deck = submesh(
        f"{spec.MOD_ID}_mouth_shelf_deck", deck_faces, ramp_steel, 1.4)
    body = submesh(
        f"{spec.MOD_ID}_mouth_shelf_body", body_faces, drum_steel, 2.0)
    return [deck, body]


def _wrap_pi(a: float) -> float:
    while a > math.pi:
        a -= TAU
    while a < -math.pi:
        a += TAU
    return a


def _dedupe(values: list[float], tol: float = 0.022) -> list[float]:
    out: list[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


# ----------------------------------------------------------------------
# Cone floor: radial seams + circumferential channels
# ----------------------------------------------------------------------


def _seam_azimuths() -> list[float]:
    return [SEAM_AZ0 + TAU * k / SEAM_COUNT for k in range(SEAM_COUNT)]


def _seam_start(index: int) -> float:
    """Long joints on even indices, short interleaved joints on odd."""

    return SEAM_R_IN_LONG if index % 2 == 0 else SEAM_R_IN_SHORT


def _seam_depth(r: float, index: int) -> float:
    """Parallel-sided groove with a short chamfered terminus at each end."""

    r_in = _seam_start(index)
    if r <= r_in or r >= SEAM_R_OUT:
        return 0.0
    ramp = min(
        (r - r_in) / SEAM_TERMINUS,
        (SEAM_R_OUT - r) / SEAM_TERMINUS,
        1.0,
    )
    return SEAM_DEPTH * ramp


def _channel_depth(r: float) -> float:
    best = 0.0
    for centre in CHANNELS:
        d = abs(r - centre)
        if d <= CH_HALF:
            best = max(best, CH_DEPTH)
        elif d <= CH_HALF + CH_CHAMFER:
            best = max(best, CH_DEPTH * (CH_HALF + CH_CHAMFER - d) / CH_CHAMFER)
    return best


def _spoke_half(r: float) -> float:
    """Spoke half-width: smoothstep taper, C1 at BOTH ends (no chevron)."""

    if r >= SPOKE_HALF_R:
        return SPOKE_HALF_MAIN
    t = (r - SPOKE_R0) / (SPOKE_HALF_R - SPOKE_R0)
    return SPOKE_HALF_HUB + (SPOKE_HALF_MAIN - SPOKE_HALF_HUB) * _smoothstep(t)


def _spoke_mask(r: float, a: float) -> float:
    """0 under a spoke, 1 in open floor: interrupts the ring channels."""

    d = min(abs(_wrap_pi(a - TAU * k / SPOKE_COUNT)) for k in range(SPOKE_COUNT)) * r
    edge = _spoke_half(r) + SPOKE_CHAMFER + 0.07
    return _smoothstep((d - edge) / 0.24)


def _cone_radii() -> list[float]:
    values: list[float] = []
    steps = 30
    for i in range(steps + 1):
        values.append(CONE_R0 + (BANK_R0 - CONE_R0) * i / steps)
    for centre in CHANNELS:
        for off in (
            -(CH_HALF + CH_CHAMFER) - 0.03,
            -(CH_HALF + CH_CHAMFER),
            -CH_HALF,
            CH_HALF,
            CH_HALF + CH_CHAMFER,
            (CH_HALF + CH_CHAMFER) + 0.03,
        ):
            values.append(centre + off)
    for edge in (SEAM_R_IN_LONG, SEAM_R_IN_SHORT, SEAM_R_OUT):
        values.extend((edge - 0.03, edge, edge + 0.03))
    values.extend(
        (
            SEAM_R_IN_LONG + SEAM_TERMINUS,
            SEAM_R_IN_SHORT + SEAM_TERMINUS,
            SEAM_R_OUT - SEAM_TERMINUS,
            BANK_R0 - 0.12,
            BANK_R0,
        )
    )
    return [r for r in _dedupe(values) if CONE_R0 - 1e-6 <= r <= BANK_R0 + 1e-6]


CONE_RADII = _cone_radii()


def _cone_azimuth_samples():
    """Azimuth schedule: (base_angle, metric_offset|None, seam_index|None,
    is_groove_floor, clamp_fraction).

    Uniform samples are dropped inside a fixed window around each seam and
    replaced by six seam samples, so every profile row shares one topology.
    The clamp fractions differ per sample role, so a seam's chamfer and
    floor rows never collapse onto each other at small radii.
    """

    seams = _seam_azimuths()
    # Reserve the window PLUS half a uniform step, so no surviving uniform
    # sample can land a hair outside a window edge and make a sliver face.
    guard = SEAM_WINDOW + 0.5 * TAU / AZIMUTH_STEPS
    samples = []
    for j in range(AZIMUTH_STEPS):
        a = TAU * j / AZIMUTH_STEPS
        if any(abs(_wrap_pi(a - sa)) < guard for sa in seams):
            continue
        samples.append((a, None, None, False, 1.0))
    for index, sa in enumerate(seams):
        samples.append((sa - SEAM_WINDOW, None, None, False, 1.0))
        samples.append((sa, -(SEAM_HALF + SEAM_CHAMFER), index, False, 0.92))
        samples.append((sa, -SEAM_HALF, index, True, 0.66))
        samples.append((sa, SEAM_HALF, index, True, 0.66))
        samples.append((sa, SEAM_HALF + SEAM_CHAMFER, index, False, 0.92))
        samples.append((sa + SEAM_WINDOW, None, None, False, 1.0))

    # Ordering is evaluated at the innermost grooved radius, where the
    # metric offsets subtend their largest (still sub-window) angle.
    samples.sort(key=lambda sample: _sample_angle(sample, SEAM_R_IN_LONG) % TAU)
    return samples


def _sample_angle(sample, r: float) -> float:
    a0, off, _index, _floor, clamp = sample
    if off is None:
        return a0
    return a0 + math.copysign(min(abs(off) / r, SEAM_WINDOW * clamp), off)


def _build_cone(name: str, material):
    samples = _cone_azimuth_samples()
    count = len(samples)
    verts = []
    for r in CONE_RADII:
        base_z = cone_z(r)
        channel = _channel_depth(r)
        for sample in samples:
            a = _sample_angle(sample, r)
            depth = channel * _spoke_mask(r, a) if channel > 0.0 else 0.0
            if sample[3]:
                depth = max(depth, _seam_depth(r, sample[2]))
            verts.append((r * math.cos(a), r * math.sin(a), base_z - depth))
    faces = []
    for i in range(len(CONE_RADII) - 1):
        for j in range(count):
            jn = (j + 1) % count
            faces.append(
                (
                    i * count + j,
                    (i + 1) * count + j,
                    (i + 1) * count + jn,
                    i * count + jn,
                )
            )
    # uv_tile 1.0: the aggregate map read as loose 1-2 m sand blobs at a
    # 5 m tile.  At 1 m the grain is below the eye's detail threshold for
    # a 30 m floor and averages into an even matte machined finish.
    return _finish_mesh(name, verts, faces, material, sharp_deg=22.0, uv="planar", uv_tile=0.6)


# ----------------------------------------------------------------------
# Bank
# ----------------------------------------------------------------------


def _hazard_profile() -> list[tuple[float, float]]:
    """Top band of the drum wall: from where _bank_profile() stops
    (BANK_S_HAZARD) up to the rim at s = 1.0.

    This band was specified (see the module docstring: "hazard band /
    cornice / bead") and its material is built in build() - but nothing
    ever swept it, so `bank_hazard` sat assigned-and-unused and the drum
    carried a 0.95 m radial by 1.2 m tall annular HOLE between the bank's
    top edge (r 18.551) and the rim cornice (r 19.5), all the way around,
    with no collision either.  That is the "visible geometric gap between
    the inner rotating ring and the outer structural ring/wall".

    Doorway window CUT (player 2026-08-09, green-circled screenshot:
    "this grey metal door should be open before a vehicle enters"): this
    band was the last ring still bridging the doorway, and its dark
    under-face hung into the upper half of the portal at IDLE - every
    state variable said OPEN while the entrance read half-closed (the
    b107 approach probe + a DAE raycast at the player's exact camera
    pinned the slab to this object). The old "continuous on purpose"
    guarded against the FULL-RING void of the unswept era, not against
    the portal: the door leaf spans spec.BANK_PROFILE to the crest, so
    the sealed state still restores the entire wall (its upper course
    wears bank_hazard to keep the chevron ring unbroken - see the door
    plug builder). Open = portal clear to the cornice, exactly the
    player's cycle.
    """

    steps = 8
    rows = []
    for i in range(steps + 1):
        s = BANK_S_HAZARD + (1.0 - BANK_S_HAZARD) * i / steps
        r, z, _nr, _nz, _rate = _bank_frame(min(max(s, 0.0), 1.0))
        rows.append((r, z))
    return rows


def _bank_profile() -> list[tuple[float, float]]:
    """Bank rows from the cone tangent up to the hazard band, with rings."""

    base = [BANK_S_HAZARD * i / 34.0 for i in range(35)]
    ring_centres = [BANK_S_HAZARD * f for f in BANK_RING_FRACTIONS]
    points: list[tuple[float, float]] = []
    for sc in ring_centres:
        rate = _bank_frame(sc)[4]
        guard = (BANK_RING_HALF + 0.05) / rate
        base = [s for s in base if abs(s - sc) > guard]
        # Symmetric V shutline: the two lips sit at 45 deg to the deck, so
        # the bank's 50 deg sharp angle leaves them shading-smooth and
        # only the 90 deg vee bottom draws a line - one line per ring.
        for off, depth in (
            (-BANK_RING_HALF, 0.0),
            (0.0, BANK_RING_DEPTH),
            (BANK_RING_HALF, 0.0),
        ):
            points.append((sc + off / rate, depth))
    points.extend((s, 0.0) for s in base)
    points.sort()
    profile = []
    for s, depth in points:
        r, z, nr, nz, _ = _bank_frame(min(max(s, 0.0), 1.0))
        profile.append((r - nr * depth, z - nz * depth))
    return profile


# ----------------------------------------------------------------------
# Spokes: real inlay with a chamfered edge row and a buried skirt
# ----------------------------------------------------------------------


def _spoke_radii() -> list[float]:
    values = [SPOKE_R0 + (SPOKE_R1 - SPOKE_R0) * i / 54.0 for i in range(55)]
    values.extend((BANK_R0 - 0.05, BANK_R0, BANK_R0 + 0.05))
    return [r for r in _dedupe(values, 0.02) if SPOKE_R0 <= r <= SPOKE_R1]


def _build_spokes(name: str, material):
    radii = _spoke_radii()
    rows = len(radii)
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for k in range(SPOKE_COUNT):
        az = TAU * k / SPOKE_COUNT
        base = len(verts)
        for r in radii:
            w = _spoke_half(r)
            surface = deck_z(r)
            outer = (w + SPOKE_CHAMFER) / r
            inner = w / r
            for da, dz in (
                (-outer, -SPOKE_SINK),
                (-outer, 0.010),
                (-inner, SPOKE_PROUD),
                (inner, SPOKE_PROUD),
                (outer, 0.010),
                (outer, -SPOKE_SINK),
            ):
                a = az + da
                verts.append((r * math.cos(a), r * math.sin(a), surface + dz))
        for i in range(rows - 1):
            v0 = base + i * 6
            v1 = base + (i + 1) * 6
            for j in range(5):
                faces.append((v0 + j, v1 + j, v1 + j + 1, v0 + j + 1))
        first = base
        last = base + (rows - 1) * 6
        faces.append(tuple(reversed(range(first, first + 6))))  # inner cap
        faces.append(tuple(range(last, last + 6)))  # outer cap
    # sharp_deg 30 blurred the 30 deg bevel into a pillow: the spokes read
    # as inflated plastic tubes in the zoom.  20 deg keeps every bevel and
    # both end caps crisp while the deck still follows the bank smoothly.
    return _finish_mesh(name, verts, faces, material, sharp_deg=20.0)


# ----------------------------------------------------------------------
# Bolts, plate seams, hatches: the second detail frequency
# ----------------------------------------------------------------------


def _basis(n: tuple[float, float, float]):
    nx, ny, nz = n
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / length, ny / length, nz / length
    hx, hy, hz = (0.0, 0.0, 1.0) if abs(nz) < 0.9 else (1.0, 0.0, 0.0)
    ux, uy, uz = hy * nz - hz * ny, hz * nx - hx * nz, hx * ny - hy * nx
    length = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / length, uy / length, uz / length
    vx, vy, vz = ny * uz - nz * uy, nz * ux - nx * uz, nx * uy - ny * ux
    return (nx, ny, nz), (ux, uy, uz), (vx, vy, vz)


def _build_bolts(
    name: str,
    placements,
    material,
    *,
    radius: float = 0.115,
    height: float = 0.05,
    sides: int = 8,
    cap: float = 0.74,
    sink: float = 0.015,
):
    """One mesh holding every bolt head: cheap, deterministic scale cue."""

    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for px, py, pz, nx, ny, nz in placements:
        n, u, v = _basis((nx, ny, nz))
        base = len(verts)
        for rr, hh in ((radius, -sink), (radius * cap, height)):
            for j in range(sides):
                a = TAU * j / sides
                cu, sv = math.cos(a) * rr, math.sin(a) * rr
                verts.append(
                    (
                        px + u[0] * cu + v[0] * sv + n[0] * hh,
                        py + u[1] * cu + v[1] * sv + n[1] * hh,
                        pz + u[2] * cu + v[2] * sv + n[2] * hh,
                    )
                )
        for j in range(sides):
            jn = (j + 1) % sides
            faces.append((base + j, base + jn, base + sides + jn, base + sides + j))
        faces.append(tuple(base + sides + j for j in range(sides)))
    obj = _finish_mesh(name, verts, faces, material, smooth=False)
    bk.add_metric_box_uvs(obj, meters_per_tile=(1.0, 1.0))
    return obj


def _wall_normal() -> tuple[float, float]:
    slope = (WALL_R_TOP - WALL_R_BOT) / WALL_Z_TOP
    length = math.hypot(1.0, slope)
    return 1.0 / length, -slope / length


def _build_hatches(name: str, material, azimuths, z0: float, z1: float, half_arc: float):
    """Low-relief inspection panels on the drum wall."""

    nu, nv = 9, 6
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    nr, nz = _wall_normal()
    for az in azimuths:
        base = len(verts)
        for iv in range(nv):
            tv = iv / (nv - 1)
            z = z0 + (z1 - z0) * tv
            for iu in range(nu):
                tu = iu / (nu - 1)
                a = az + (tu - 0.5) * 2.0 * half_arc
                border = iu in (0, nu - 1) or iv in (0, nv - 1)
                proud = 0.010 if border else 0.115
                r = wall_r(z) + nr * proud
                zz = z + nz * proud
                verts.append((r * math.cos(a), r * math.sin(a), zz))
        for iv in range(nv - 1):
            for iu in range(nu - 1):
                a0 = base + iv * nu + iu
                faces.append((a0, a0 + 1, a0 + nu + 1, a0 + nu))
    obj = _finish_mesh(name, verts, faces, material, smooth=False)
    bk.add_metric_box_uvs(obj, meters_per_tile=(2.0, 2.0))
    return obj


# ----------------------------------------------------------------------
# Gussets: flat-shaded plates with a legible triangle and a rolled edge
# ----------------------------------------------------------------------


def _build_gussets(name: str, material):
    r_apex = wall_r(GUSSET_Z_TOP) - 0.02
    r_wall_bot = wall_r(GUSSET_Z_BOT) - 0.06  # buried inside the drum wall
    apex = (r_apex, GUSSET_Z_TOP)
    foot_out = (GUSSET_R_FOOT, GUSSET_Z_BOT)
    foot_in = (r_wall_bot, GUSSET_Z_BOT)

    # Inset the exposed hypotenuse (foot_out -> apex) by GUSSET_ROLL so the
    # plate carries a rolled edge band instead of a knife edge.
    hr, hz = apex[0] - foot_out[0], apex[1] - foot_out[1]
    hl = math.hypot(hr, hz)
    # Interior side of the hypotenuse points back toward the wall (-r).
    ir, iz = hz / hl, -hr / hl
    if (foot_in[0] - foot_out[0]) * ir + (foot_in[1] - foot_out[1]) * iz < 0.0:
        ir, iz = -ir, -iz
    foot_i = (foot_out[0] + ir * GUSSET_ROLL, foot_out[1] + iz * GUSSET_ROLL)
    apex_i = (apex[0] + ir * GUSSET_ROLL, apex[1] + iz * GUSSET_ROLL)

    thin = GUSSET_HALF_T - GUSSET_ROLL
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for k in range(GUSSET_COUNT):
        az = TAU * k / GUSSET_COUNT + math.radians(7.5)
        ca, sa = math.cos(az), math.sin(az)
        tx, ty = -sa, ca
        base = len(verts)

        def place(point, half):
            r, z = point
            verts.append((r * ca + tx * half, r * sa + ty * half, z))
            verts.append((r * ca - tx * half, r * sa - ty * half, z))

        place(foot_in, GUSSET_HALF_T)  # 0 +, 1 -
        place(foot_i, GUSSET_HALF_T)  # 2 +, 3 -
        place(apex_i, GUSSET_HALF_T)  # 4 +, 5 -
        place(foot_out, thin)  # 6 +, 7 -
        place(apex, thin)  # 8 +, 9 -
        b = base
        faces.append((b + 0, b + 2, b + 4))  # + flank
        faces.append((b + 5, b + 3, b + 1))  # - flank
        faces.append((b + 2, b + 6, b + 8, b + 4))  # + roll chamfer
        faces.append((b + 5, b + 9, b + 7, b + 3))  # - roll chamfer
        faces.append((b + 6, b + 7, b + 9, b + 8))  # outer edge strip
        faces.append((b + 0, b + 1, b + 3, b + 2))  # buried foot
        faces.append((b + 0, b + 4, b + 5, b + 1))  # wall-side face
    obj = _finish_mesh(name, verts, faces, material, smooth=False)
    bk.add_metric_box_uvs(obj, meters_per_tile=(2.0, 2.0))
    return obj


# ----------------------------------------------------------------------


def build(materials):
    mid = spec.MOD_ID
    ramp_steel = materials[f"{mid}_ramp_steel"]
    rotor_blue = materials[f"{mid}_rotor_blue"]
    drum_steel = materials[f"{mid}_drum_steel"]
    bank_hazard = materials[f"{mid}_bank_hazard"]

    objects = []

    # --- Machined cone floor -------------------------------------------
    # Round 2: floor_concrete's colour map is a WARM beige aggregate
    # (mean 153/148/140, speckle 104..165) - sandy plaza slab, the exact
    # skatepark read the brief warns against, and it is the largest
    # surface in every view.  ramp_steel is the palette's cool machined
    # grey (map mean 140/148/153, blue-shifted, near-uniform so the 0.6 m
    # planar tile stays a fine machining grain rather than aggregate) at
    # metallic 0.3 / roughness 0.5 - painted machined plate, not concrete.
    # Raceway asphalt, not painted steel (player round 2026-08-05).
    objects.append(_build_cone(f"{mid}_track_bowl_cone", materials[f"{mid}_track_asphalt"]))

    # --- Concave velodrome bank, 4 single-line profile rings ------------
    # Starts exactly on the cone's last row (BANK_R0 / BANK_Z0) with a
    # matched tangent: no step, no crack, no connecting wall needed.
    # Same painted machined grey as the cone: the deck is ONE surface that
    # happens to curve up, and the drivable region has to read that way.
    # drum_steel was tried here and its 0.8 metallic put a mirror sweep
    # across the concave arc - the exact stamped-tin read to avoid.  The
    # cylindrical tile drops 5.0 -> 1.4 m: at 5 m the map's own tile edges
    # printed phantom rings across the 4.3 m of bank run, at 1.4 m the
    # grain is below the eye's detail threshold and averages out.
    # Opening window must equal the door plug's sweep (257-283) and the
    # cage's GARAGE_SEGMENTS (segments 20-21 of 28 = 257.1-282.9). It was
    # 253-287, four degrees wider on each flank than anything that fills
    # it, so the closed door left a ~1.2 m slot down both sides of the
    # doorway with the concourse apron showing through - the gap the
    # player ringed in magenta. The drum SKIN outside still opens wider
    # (see the outer wall below); only this ring has to match the leaf.
    # z_remap fairs the sheet onto the collision swale at the doorway
    # flanks (build 95): before this the visual stayed full height over
    # faired collision and riding cars looked swallowed by the bank.
    # skip_frac 1.0 (2026-08-09, the "grey metal door" round): the bank's
    # doorway window opens the FULL profile - the historic 0.72 cap left
    # its top rows as a wall across the mouth. The door leaf spans
    # spec.BANK_PROFILE, so the sealed state still restores every row.
    bank = _swept_mesh(
        f"{mid}_track_bowl_bank",
        _bank_profile(),
        ramp_steel,
        sharp_deg=50.0,
        tile_m=1.4,
        skip_az=(257.0, 283.0),
        skip_frac=1.0,
        z_remap=_fair_z,
    )
    objects.append(bank)

    # --- Dish skirt: the raised deck's own outside face ----------------
    # The cone is a single-sided surface raised 2.48 m over the concourse
    # and NOTHING was ever built down its outer edge, so the dish read as a
    # floating disc: from anywhere below the lip you looked straight under
    # it at the pale concrete apron.  That pale surface inside the drum is
    # what the player filmed and called "the inside roadway is missing".
    # The collision cage has had a skirt at this exact radius all along
    # (build_cage -> `skirt`), so this closes a VISUAL-only hole and adds
    # no new collision.  Skipped across the doorway, where the ramp passes.
    objects.append(
        _swept_mesh(
            f"{mid}_track_bowl_dish_skirt",
            [(BANK_R0, BANK_Z0), (BANK_R0, 0.0)],
            drum_steel,
            flip=True,
            sharp_deg=60.0,
            tile_m=2.0,
            skip_az=(257.0, 283.0),
        )
    )

    # --- Deck-to-bank junction band ------------------------------------
    # The cone rim and the bank base share the r 15.2 circle but NOT the
    # same azimuth samples (the cone drops uniform samples near each seam
    # and adds six metric-offset ones), so the two polygonal rims cross:
    # lens-shaped hairline cracks, a few mm wide, all along the junction.
    # Player 2026-08-08: "the middle floor should extend INTO the curved
    # walls" - this band is that extension, a strip 4 mm under both
    # surfaces bridging r 15.0..15.45 so every hairline is backed by
    # steel instead of the dark service cavity. Skipped at the doorway,
    # where the ramp's own blend owns the junction.
    objects.append(
        _swept_mesh(
            f"{mid}_track_bowl_junction_band",
            [
                (15.00, deck_z(15.00) - 0.004),
                (BANK_R0, BANK_Z0 - 0.004),
                (15.45, deck_z(15.45) - 0.004),
            ],
            ramp_steel,
            sharp_deg=50.0,
            tile_m=1.4,
            skip_az=(257.0, 283.0),
        )
    )

    # --- Portal jamb walls ---------------------------------------------
    # The doorway cut through the bank previously opened SIDEWAYS into the
    # annular service cavity under the bank (skirt / apron strip / outer
    # wall). Every wall of that cavity presents its BACK face to a viewer
    # in the portal, so the player looked straight through the building at
    # the raw ground (video 2026-08-07 22:51). These radial walls seal the
    # portal's flanks so it reads as a real tunnel. Both windings, so no
    # culling question ever arises. Top edge sits 45 mm under the bank
    # line: the door leaf (inset 25 mm) slides through that reveal like a
    # pocket door without ever intersecting the jamb.
    # Jambs sit ON the rings' shared cut boundary, not on the nominal
    # window edge (2026-08-12, player's green-circled yellow tab). Every
    # swept ring cuts on CELL boundaries: with AZIMUTH_STEPS=192 the
    # retained cells nearest the 257/283 window end at 256.875/283.125.
    # A jamb at exactly 257.0 stood 0.125 deg INSIDE the opening - past
    # every ring's end face - so 4.3 cm of hazard-band end face poked
    # out beside the post on each side. Snapping the jamb onto the cut
    # boundary covers all the end faces at once.
    _cut_cell = 360.0 / AZIMUTH_STEPS
    for jamb_az in (math.floor(257.0 / _cut_cell) * _cut_cell,
                    math.ceil(283.0 / _cut_cell) * _cut_cell):
        a = math.radians(jamb_az)
        ca, sa = math.cos(a), math.sin(a)
        jamb_verts = []
        steps = 10
        prev_r = None
        for i in range(steps + 1):
            s = i / steps
            r, z, _nr, _nz, _rate = _bank_frame(min(max(s, 0.0), 1.0))
            # Stop at the rim curl (round 15, player: dark fins poking
            # proud of the smooth bowl under the hazard band). Once the
            # profile turns back INBOARD, a radial sheet that keeps
            # following it wraps in front of the bank face and reads as
            # a wedge stuck to the wall. The curl zone sits above the
            # doorway header, where the continuous band ring owns the
            # surface - nothing up there needs sealing.
            if prev_r is not None and r < prev_r - 1e-6:
                break
            prev_r = r
            # Jamb tops follow the FAIRED bank line (build 95): at the
            # cut azimuth the fairing weight is ~1, so the sheet these
            # jambs seal against now dips to the swale - an unfaired
            # jamb would stand proud of it as a tall fin in the doorway.
            jamb_verts.append((ca * r, sa * r, _fair_z(r, z, jamb_az) - 0.045))
            jamb_verts.append((ca * r, sa * r, 0.0))
        jamb_faces = []
        for i in range(len(jamb_verts) // 2 - 1):
            q = (2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2)
            jamb_faces.append(q)
            jamb_faces.append(tuple(reversed(q)))
        objects.append(
            _finish_mesh(
                f"{mid}_track_bowl_jamb_{int(jamb_az)}",
                jamb_verts,
                jamb_faces,
                drum_steel,
                sharp_deg=40.0,
                uv="planar",
                uv_tile=2.0,
            )
        )

    # --- Hazard band: the bank's missing top course --------------------
    # skip_az: the doorway window, same as every other ring (2026-08-09,
    # the "grey metal door" round - see _hazard_profile's docstring).
    objects.append(
        _swept_mesh(
            f"{mid}_track_bowl_hazard_band",
            _hazard_profile(),
            bank_hazard,
            sharp_deg=50.0,
            tile_m=1.4,
            skip_az=(257.0, 283.0),
            skip_frac=1.0,
        )
    )

    # Apron strap + bolt heads REMOVED 2026-08-05: a 55-75 mm proud stud
    # belt laid across the deck at r 15.9-16.55, precisely where cars cross
    # in from the tunnel. The player's car high-centred on it (and the
    # probe stopped at the identical coordinate on every build).

    # --- Rim cornice: overhangs every gusset tip -----------------------
    objects.append(
        _swept_mesh(
            f"{mid}_track_bowl_rim_cornice",
            [
                (BANK_R1, BANK_Z1),
                (CORNICE_R - 0.04, BANK_Z1 + 0.02),
                (CORNICE_R, BANK_Z1 - 0.16),
            ],
            drum_steel,
            tile_m=2.0,
        )
    )

    objects.append(
        bk.add_torus(
            f"{mid}_track_bowl_rim_bead",
            (0.0, 0.0, BANK_Z1 + 0.05),
            BEAD_MAJOR,
            BEAD_MINOR,
            drum_steel,
            major_segments=AZIMUTH_STEPS,
            minor_segments=10,
        )
    )

    # --- Outer drum wall: leans out, with two recessed plate seams -----
    wall_rows: list[tuple[float, float]] = []
    for z in (0.0, 0.85):
        wall_rows.append((wall_r(z), z))
    for seam_z in (1.70, 5.55):
        wall_rows.extend(
            (
                (wall_r(seam_z - 0.07), seam_z - 0.07),
                (wall_r(seam_z - 0.05) - 0.045, seam_z - 0.05),
                (wall_r(seam_z + 0.05) - 0.045, seam_z + 0.05),
                (wall_r(seam_z + 0.07), seam_z + 0.07),
            )
        )
        if seam_z < 5.0:
            wall_rows.extend((wall_r(z), z) for z in (2.6, 3.45, 4.3))
    wall_rows.extend((wall_r(z), z) for z in (6.2, WALL_Z_TOP))
    wall_rows.sort()
    objects.append(
        _swept_mesh(
            f"{mid}_track_bowl_outer_wall",
            wall_rows,
            drum_steel,
            flip=True,
            sharp_deg=24.0,
            tile_m=4.0,
            # The entry ramp passes THROUGH the drum skin: without this the
            # ramp dead-ends on a solid wall (player screenshot 2026-08-05).
            skip_az=(257.0, 283.0),
        )
    )

    # --- Girth flange stiffening the drum ------------------------------
    objects.append(
        _swept_mesh(
            f"{mid}_track_bowl_girth_flange",
            [
                (wall_r(GIRTH_Z - 0.20) - 0.01, GIRTH_Z - 0.20),
                (wall_r(GIRTH_Z) + 0.10, GIRTH_Z - 0.06),
                (wall_r(GIRTH_Z) + 0.10, GIRTH_Z + 0.06),
                (wall_r(GIRTH_Z + 0.20) - 0.01, GIRTH_Z + 0.20),
            ],
            drum_steel,
            flip=True,
            tile_m=2.0,
        )
    )

    # --- 24 tapered ribs bracing the full height of the bank face ------
    # These replace the old vertical butt straps: the ribs now run 0.36 ->
    # 5.60 on the same 24 lines the straps used, so the drum keeps its
    # plate rhythm without doubling the vertical element count.
    # Gussets removed 2026-08-05 (player): the triangular fins broke the
    # smooth curve of the bank wall and read as an obstruction.

    # --- Inspection hatches + bolt rows on the drum --------------------
    hatch_half_arc = 1.60 / 19.2
    hatch_z0, hatch_z1 = 3.95, 5.35
    hatch_az = [math.radians(45.0 + 90.0 * k) for k in range(4)]
    objects.append(
        _build_hatches(
            f"{mid}_track_bowl_hatches",
            drum_steel,
            hatch_az,
            hatch_z0,
            hatch_z1,
            half_arc=hatch_half_arc,
        )
    )

    wall_nr, wall_nz = _wall_normal()

    def wall_bolt(a: float, z: float):
        r = wall_r(z)
        return (
            r * math.cos(a),
            r * math.sin(a),
            z,
            wall_nr * math.cos(a),
            wall_nr * math.sin(a),
            wall_nz,
        )

    wall_bolts = []
    for z in (0.85, 6.42):
        for j in range(GUSSET_COUNT * 3):
            wall_bolts.append(wall_bolt(TAU * j / (GUSSET_COUNT * 3), z))
    for az in hatch_az:
        for tv in (0.05, 0.5, 0.95):
            z = hatch_z0 + (hatch_z1 - hatch_z0) * tv
            for tu in (-1.0, 1.0):
                wall_bolts.append(wall_bolt(az + tu * hatch_half_arc * 0.86, z))
    objects.append(
        _build_bolts(
            f"{mid}_track_bowl_wall_bolts",
            wall_bolts,
            drum_steel,
            radius=0.15,
            height=0.08,
        )
    )

    # --- Machined base course the drum and every gusset stands on ------
    # Two chamfered steps in drum_steel: a machined base, not the black
    # gasket the old flat pylon_dark ring read as.
    objects.append(
        _swept_mesh(
            f"{mid}_track_bowl_plinth",
            [
                (WALL_R_BOT - 0.05, PLINTH_Z),
                (PLINTH_R - 0.14, PLINTH_Z),
                (PLINTH_R, PLINTH_Z - 0.14),
                (PLINTH_R, 0.16),
                (PLINTH_R - 0.09, 0.07),
                (PLINTH_R - 0.09, 0.0),
            ],
            drum_steel,
            sharp_deg=26.0,
            tile_m=2.0,
        )
    )

    # Anchor bolts on the plinth's outer face - the one part of the base
    # a viewer standing on the ground can actually see, since the drum
    # leans out over the top face.
    plinth_bolts = []
    for j in range(GUSSET_COUNT * 2):
        a = TAU * (j + 0.5) / (GUSSET_COUNT * 2)
        plinth_bolts.append(
            (
                PLINTH_R * math.cos(a),
                PLINTH_R * math.sin(a),
                0.24,
                math.cos(a),
                math.sin(a),
                0.0,
            )
        )
    objects.append(
        _build_bolts(
            f"{mid}_track_bowl_plinth_bolts",
            plinth_bolts,
            drum_steel,
            radius=0.13,
            height=0.055,
        )
    )

    # --- Royal-blue radial spokes, inlaid into the deck ----------------
    # Round 2: spoke_blue's palette colour is LINEAR and untextured, so
    # [0.10, 0.22, 0.58] resolves to #5981C8 - powder blue.  rotor_blue
    # [0.07, 0.14, 0.44] resolves to #4B69B1, which is the royal blue the
    # brief asks for, and it ties the deck inlay to the rotor above it.
    objects.append(_build_spokes(f"{mid}_track_bowl_spokes", rotor_blue))

    # --- Blue hub band the spokes run from -----------------------------
    objects.append(
        _swept_mesh(
            f"{mid}_track_bowl_hub_band",
            [
                (HUB_R0, cone_z(HUB_R0) - 0.16),
                (HUB_R0, cone_z(HUB_R0) + 0.010),
                (HUB_R0 + 0.07, cone_z(HUB_R0 + 0.07) + HUB_PROUD),
                (HUB_R1 - 0.07, cone_z(HUB_R1 - 0.07) + HUB_PROUD),
                (HUB_R1, cone_z(HUB_R1) + 0.010),
                (HUB_R1, cone_z(HUB_R1) - 0.16),
            ],
            rotor_blue,
            sharp_deg=20.0,
            tile_m=1.5,
        )
    )

    objects.append(
        bk.add_torus(
            f"{mid}_track_bowl_hub_ring",
            (0.0, 0.0, cone_z(HUB_R1) + 0.055),
            HUB_R1,
            0.09,
            rotor_blue,
            major_segments=AZIMUTH_STEPS // 2,
            minor_segments=10,
        )
    )

    # --- Centre opening bead (rotor pedestal goes inside r < 2.0) ------
    # Minor radius halved and the ring dropped 0.02 so it no longer runs
    # tangent to the cone at r ~2.1 (shading seam) and no longer out-reads
    # the blue hub collar it sits inside.
    objects.append(
        bk.add_torus(
            f"{mid}_track_bowl_opening_ring",
            (0.0, 0.0, CONE_Z0 - 0.02),
            CONE_R0,
            OPENING_BEAD_MINOR,
            drum_steel,
            major_segments=AZIMUTH_STEPS // 2,
            minor_segments=10,
        )
    )

    return objects
