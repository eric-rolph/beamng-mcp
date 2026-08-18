"""Deterministic Blender generator for the G-Force Centrifuge Torture Test.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/gforce_centrifuge/blender/create_gforce_centrifuge.py
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
# Component modules (worker-built CHIEF geometry) live beside this script.
sys.path.insert(0, str(SCRIPT_PATH.parent))

import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def add_bank_cone(name, material, radius1=None, radius2=None, z0=None, z1=None):
    """Open truncated cone band: banked wall / rim curl in one surface."""

    import bpy

    radius1 = spec.FLOOR_R if radius1 is None else radius1
    radius2 = spec.BANK_TOP_R if radius2 is None else radius2
    z0 = spec.FLOOR_TOP_Z if z0 is None else z0
    z1 = spec.BANK_TOP_Z if z1 is None else z1
    bpy.ops.mesh.primitive_cone_add(
        vertices=48,
        radius1=radius1,
        radius2=radius2,
        depth=z1 - z0,
        end_fill_type="NOTHING",
        location=(0.0, 0.0, (z0 + z1) / 2),
    )
    cone = bpy.context.object
    cone.name = name
    cone.data.name = name
    bk.assign_material(cone, material)
    bpy.ops.object.select_all(action="DESELECT")
    cone.select_set(True)
    bpy.context.view_layer.objects.active = cone
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    cone.select_set(False)
    return cone




def add_helix_ribbon(
    name,
    material,
    r_inner,
    r_outer,
    z_top_of=lambda t: 0.0,
    thickness=0.25,
    steps=140,
    dashed=False,
    t_stop=1.0,
):
    """Continuously swept helical ribbon (2026-08-05 round 2: segmented
    box decks read as broken planks - a single smooth mesh or nothing)."""

    import bpy

    verts = []
    faces = []
    for j in range(steps + 1):
        t_frac = j / steps
        theta = math.radians(spec.SPIRAL_START_DEG - spec.SPIRAL_WRAP_DEG * t_frac)
        c, s = math.cos(theta), math.sin(theta)
        z_top = z_top_of(t_frac)
        verts.append((c * r_inner, s * r_inner, z_top))
        verts.append((c * r_outer, s * r_outer, z_top))
        verts.append((c * r_inner, s * r_inner, z_top - thickness))
        verts.append((c * r_outer, s * r_outer, z_top - thickness))
    flat = thickness <= 0.02
    for j in range(steps):
        if dashed and j % 4 >= 2:
            continue
        if (j + 1) / steps > t_stop:
            continue
        a = 4 * j
        faces.append((a, a + 1, a + 5, a + 4))
        if not flat:
            faces.append((a + 2, a + 6, a + 7, a + 3))
            faces.append((a, a + 4, a + 6, a + 2))
            faces.append((a + 1, a + 3, a + 7, a + 5))
    if not dashed and not flat:
        faces.append((0, 2, 3, 1))
        b = 4 * steps
        faces.append((b, b + 1, b + 3, b + 2))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(40.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj




def _wedge_cutter(name):
    """Radial wedge spanning the entry azimuth, from just above the deck
    up past the rim. Box cutters left jagged stair-step edges across the
    curved bank (player: "the track is transparent" - you saw ground
    through the ragged notch); a wedge cuts along the bank's own radial
    lines so the opening reads as a clean doorway the plug fills exactly.
    """

    import bpy

    az0, az1 = math.radians(253.0), math.radians(287.0)
    r0, r1 = spec.CONE_OUTER_R + 0.02, 21.0
    z0, z1 = spec.CONE_OUTER_Z + 0.02, 9.4
    verts = []
    for a in (az0, az1):
        c, s = math.cos(a), math.sin(a)
        for radius in (r0, r1):
            for z in (z0, z1):
                verts.append((c * radius, s * radius, z))
    faces = [
        (0, 1, 3, 2), (4, 6, 7, 5), (0, 2, 6, 4),
        (1, 5, 7, 3), (2, 3, 7, 6), (0, 4, 5, 1),
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


RAMP_HALF_WIDTH = 3.35
RAMP_OUTER_Y = -30.60
# Crest window. Two generations of crest here, both wrong in opposite
# directions: a hard corner at the lip (17.3 deg break - cars BEACHED,
# breakover is ~11.4 deg), then a smoothstep blend of the two HEIGHT
# datums (2026-08-05). The blend un-beached the crest but mid-window it
# must out-dive the approach plane to catch it: measured dz/dr peaks at
# ~23% around r 17-18.5, and an automatic at creep throttle stalls on
# 23% (player: "hung up on the mesh at slow speeds"; probe 2026-08-08:
# centre crawl stuck at r 17.9, 2 m/s runs side-dependent, full-speed
# entries fine). ramp_surface_z now interpolates the SLOPE across this
# window and integrates - a true vertical curve from the dish's +15% to
# the plane's -16.1% whose grade never exceeds either end anywhere.
RAMP_R_IN, RAMP_R_OUT = 13.4, 18.6


def ramp_slope() -> float:
    from components import track_bowl as _tb

    return _tb.CONE_SLOPE * 1.0736  # 0.1610, the authored tunnel pitch


def ramp_surface_z(x: float, y: float, half_width: float = RAMP_HALF_WIDTH) -> float:
    """Height of the entry ramp surface at (x, y).

    Single source of truth: the visual ramp mesh, the plaza, the reveal
    walls AND the collision cage's tunnel stations all sample this.

    The crest is a slope-interpolated vertical curve: dz/dr runs the
    dish's +CONE_SLOPE for r <= RAMP_R_IN, the approach plane's
    -ramp_slope() for r >= RAMP_R_OUT, linear between, integrated from
    the lip (where z is pinned to the dish's own height). Grade is
    therefore monotone through the crest and NEVER exceeds 16.1%
    anywhere - the height-datum blend this replaces peaked at ~23%
    mid-window, which is what stranded crawling cars.
    """

    from components import track_bowl as _tb

    lip_r = _tb.BANK_R0
    lip_z = _tb.cone_z(lip_r)
    s_in = _tb.CONE_SLOPE
    s_out = -ramp_slope()
    a, b = RAMP_R_IN, RAMP_R_OUT

    def slope_run(r0: float, r1: float) -> float:
        """Integral of dz/dr over [r0, r1] (requires r1 >= r0)."""

        total = 0.0
        if r0 < a:
            total += s_in * (min(r1, a) - r0)
        lo, hi = max(r0, a), min(r1, b)
        if hi > lo:
            t0 = (lo - a) / (b - a)
            t1 = (hi - a) / (b - a)
            total += (s_in + (s_out - s_in) * 0.5 * (t0 + t1)) * (hi - lo)
        if r1 > b:
            total += s_out * (r1 - max(r0, b))
        return total

    r = math.hypot(x, y)
    if r >= lip_r:
        z = lip_z + slope_run(lip_r, r)
    else:
        z = lip_z - slope_run(r, lip_r)
    # Round 15, THE mouth pin finally named: the blend window starts at
    # RAMP_R_IN 13.4 - INSIDE the physical lip (15.2) - so the softened
    # crest slope bulged the approach 9-10 cm above the dish over the
    # last 1.6 m and the collision tongue ended in an exposed cross-edge
    # (jbeam: tunnel_1_0 z 2.33 vs cone 2.24). Two hard-cap attempts
    # (15 mm laterally-tapered, then a global min) fixed the pin but
    # left a slope KNUCKLE at the lip - probes stop AT the lip so their
    # gauntlet missed it, and the player felt it on every real entry.
    # Final form: C1 tongue-to-dish blend. The excess over the cone
    # fades in with a cubic smoothstep whose derivative is ZERO at the
    # lip, so the surface meets the outside curve with MATCHING slope
    # (no knuckle), eases onto the dish by ~r 14, and has no lateral
    # term (no cross-lane twist). Outside the lip: untouched.
    if r < lip_r:
        deck = _tb.cone_z(r)
        t = max(0.0, min(1.0, (r - RAMP_R_IN) / (lip_r - RAMP_R_IN)))
        s = t * t * (3.0 - 2.0 * t)
        z = deck + (z - deck) * s
    return z


def add_vomitory_ramp(name, material, half_width=RAMP_HALF_WIDTH,
                      outer_y=RAMP_OUTER_Y, slope=None, thickness=0.18):
    """Entry ramp built as a RADIAL surface off the cone lip.

    The ramp used to be a single pitched box.  A box ends on a straight
    line and the deck ends on a circle, so the two could never meet:
    measured on the built mesh, the box overshot the lip by 0.83 m,
    rode 40-80 mm proud of the deck, then fell off a 166 mm cliff at
    r 14.35 - and at the corners (x +/-3) it left a 0.30 m crescent of
    open air between the ramp end and the lip arc.  That crescent is the
    "gap where nothing exists" in the player's screenshot and the cliff
    is what the car hung up on.

    Here the height is a function of RADIUS using the deck's own cone_z,
    so the inner edge lies exactly on the r = BANK_R0 arc at exactly the
    deck's height.  The handoff is flush by construction, not by tuning.
    """

    import bpy

    from components import track_bowl as _tb

    del _tb, slope
    cols, rows = 25, 52
    top, bottom = [], []
    for i in range(cols):
        x = -half_width + 2.0 * half_width * i / (cols - 1)
        # Inner end of this column sits on the blend's inner arc, where
        # the surface is already tangent to (and level with) the deck.
        y_in = -math.sqrt(max(RAMP_R_IN * RAMP_R_IN - x * x, 0.0))
        for j in range(rows):
            t = j / (rows - 1)
            y = outer_y + (y_in - outer_y) * t
            z = ramp_surface_z(x, y, half_width)
            top.append((x, y, z))
            # Solid embankment, not a 0.18 m plank on stilts. Near the lip
            # the ramp deck floats 2.0-2.4 m over the concourse, and with
            # the skirt's doorway open underneath it that left a
            # 6.8 x 2.5 m hole a car could drop straight into. Carrying the
            # underside down to grade closes the void and reads as a real
            # ramp embankment.
            under = z - thickness
            bottom.append((x, y, 0.0 if under > 0.0 else under))

    verts = top + bottom
    offset = len(top)
    faces = []
    for i in range(cols - 1):
        for j in range(rows - 1):
            a = i * rows + j
            b = a + rows
            # WINDING MATTERS. (a, a+1, b+1, b) walks +y then +x, whose
            # cross product is -Z: that puts the ramp's TOP normals facing
            # DOWN and its underside facing UP. Blender does not backface
            # cull, so it renders correctly in every headless check while
            # being INVISIBLE in game (ramp_steel is not doubleSided) -
            # the player filmed a car driving on thin air.
            faces.append((a, b, b + 1, a + 1))                      # top, +Z
            faces.append((offset + a, offset + a + 1, offset + b + 1,
                          offset + b))                              # underside, -Z
    for i in range(cols - 1):                                       # inner lip
        a = i * rows + (rows - 1)
        b = a + rows
        faces.append((a, b, offset + b, offset + a))
    for i in range(cols - 1):                                       # outer end
        a = i * rows
        b = a + rows
        faces.append((b, a, offset + a, offset + b))
    for j in range(rows - 1):                                       # side walls
        a = j
        faces.append((a + 1, a, offset + a, offset + a + 1))
        c = (cols - 1) * rows + j
        faces.append((c, c + 1, offset + c + 1, offset + c))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    # The ramp is a closed solid (top, underside, inner lip, outer end, two
    # flanks), so let bmesh orient every face outward rather than trusting
    # six hand-derived windings - three of them were wrong.
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    up = sum(1 for p in mesh.polygons if p.normal.z > 0.35)
    down = sum(1 for p in mesh.polygons if p.normal.z < -0.35)
    assert up > 0 and abs(up - down) <= 2, (
        f"{name}: ramp deck must face +Z ({up} up / {down} down)"
    )
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    # Metric UVs (1.8 m tile) so the steel matches the tunnel walls.
    # Vertical faces get a WALL mapping (round 15: the top-planar radial
    # map renders as stretched pinstripes on side faces).
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        wall = abs(poly.normal.z) < 0.5
        by_y = abs(poly.normal.x) > abs(poly.normal.y)
        for li in poly.loop_indices:
            vx, vy, vz = verts[mesh.loops[li].vertex_index]
            if wall:
                uv.data[li].uv = ((vy if by_y else vx) / 1.8, vz / 1.8)
            else:
                uv.data[li].uv = (vx / 1.8, math.hypot(vx, vy) / 1.8)
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(30.0))
    except Exception:
        bpy.ops.object.shade_flat()
    obj.select_set(False)
    return obj


JAMB_TAN = math.tan(math.radians(13.0))  # jamb planes at az 257 / 283


def pier_inner_x(ay: float) -> float:
    """+x pier's INNER tangential face, as an x at station ``y = -ay``.

    The entry piers are boxes rotated to the ring tangent, so the face the
    corridor wall has to die into is a PLANE, not a radius: its normal is
    the tangential unit at PIER_MID_DEG and it sits PIER_T/2 inboard of the
    pier centre. Solving that plane for x at a given y is what lets the
    reveal wall track it exactly (2026-08-10 brown-sliver round).
    """

    from components import louver_facade as _lf

    a = math.radians(_lf.ENTRY_DEG + _lf.PIER_MID_DEG)
    cx, cy = _lf.FIN_R * math.cos(a), _lf.FIN_R * math.sin(a)
    tx, ty = -math.sin(a), math.cos(a)          # tangential unit, points +x
    return cx + (-_lf.PIER_T / 2.0 - (-ay - cy) * ty) / tx


def corridor_wall_x(y: float) -> float:
    """Inner face of the corridor's flank wall at station ``y`` (+x side).

    ONE plan authority for everything vertical beside the entry lane: the
    visual reveal walls, the trench-fill shoulders (buried 0.45 m past it)
    and the cage's wall collision all sample this. Inside the drum it is
    the bank doorway's 26 deg wedge jamb (x = tan(13 deg) * |y| + 0.02,
    tucked 2 cm behind the jamb sheets). From the jamb walls' outer edge
    (ay 17.9, x 4.153) to the portal it runs essentially straight
    (-> 4.19), then flares over the last half metre to 4.38 - 2 cm inside
    the pier jamb plane (4.36 with the 20 deg entry gap), so the wall
    dies INTO solid terracotta instead of stopping beside it.
    """

    ay = abs(y)
    if ay <= 17.9:
        return JAMB_TAN * ay + 0.02
    if ay <= 23.2:
        t = (ay - 17.9) / (23.2 - 17.9)
        return 4.153 + (4.19 - 4.153) * t
    # End flare deepened 4.38 -> 4.55 at 23.95 (player 2026-08-08, green
    # marks): 4.38 landed 3 mm inside the pier's tangential face and the
    # pier's 0.05 corner bevel ate it, so the wall/kick/stripe/cap END
    # CAPS all showed as a raw slot beside the pier. 4.55 at 23.95 is
    # 11 cm inside the pier solid - 6 cm past the bevel - so every strip
    # terminates in terracotta.
    #
    # 2026-08-10 (player, green marks again: "the copper brown column
    # over-runs slightly the grey steel entrance wall"). The flare buried
    # the wall at its END but not along the way. The pier's inner face is
    # a PLANE at 13.09 deg to the lane while the wall ran essentially
    # straight, so the two crossed twice: measured, the wall sat INBOARD
    # of that plane from ay 22.86 to 23.55, peaking 7.6 cm short at
    # ay 23.2. Seen down the corridor, those few centimetres of pier face
    # are a full-height brown sliver - the exposure is thin in plan but
    # 8 m tall.
    #
    # A straight line chasing a slanted plane will always lose somewhere,
    # so the wall now FOLLOWS the plane: max() of the old linear flare and
    # the pier face offset 6 cm into the solid. Both terms are monotonic
    # in ay, so their max is too (no kink), and at the 22.60 handover the
    # two agree to within a millimetre by construction - which is why the
    # flare starts there now instead of at 23.2.
    t = (min(ay, 23.95) - 22.60) / 1.35
    linear = 4.186 + (4.55 - 4.186) * t
    return max(linear, pier_inner_x(ay) + 0.06)


PLAZA_HALF_W_OUT = 5.0  # 10 m wide at the approach, per the facade brief
PLAZA_Y_KNEE = -26.3  # full width held to here, then the funnel begins
PLAZA_Y_IN = -23.55  # inner edge, 0.35 m PAST the steel ramp's outer end
# The slope-interpolated crest spends height more honestly than the old
# datum blend, so the surface reaches grade at r ~32.75 (was 30.6); the
# plaza follows it out and dies into open ground past the apron edge.
PLAZA_Y_OUT = -33.5


def plaza_half_w(y: float) -> float:
    """Half-width of the concrete entry plaza.

    The plan shape is the facade's old 10 m -> portal funnel, but the
    SURFACE now samples ramp_surface_z like everything else a wheel can
    touch - the facade's rival 6.8%-to-z-0.45 grade system is gone. The
    throat runs 0.26 m wider than the portal's clear half-width so the
    slab flows under the pier bases instead of leaving an upstand slot
    beside them.
    """

    from components import louver_facade as _lf

    throat = _lf.OPENING_HALF_W + 0.26
    if y <= PLAZA_Y_KNEE:
        return PLAZA_HALF_W_OUT
    t = (y - PLAZA_Y_KNEE) / (PLAZA_Y_IN - PLAZA_Y_KNEE)
    t = min(max(t, 0.0), 1.0)
    return PLAZA_HALF_W_OUT + (throat - PLAZA_HALF_W_OUT) * t


def add_ramp_shoulder(name, material, side):
    """Solid fill of the trench between the ramp flank and the flank wall.

    The vomitory corridor is a 26 deg wedge (jambs at az 257/283) but the
    ramp is a constant-width 6.7 m slab, so a grade-deep open trench ran
    between the ramp's side wall and each jamb: ~0.1 m wide at the skirt
    line, ~1.1 m at the drum skin. Looking down from the bank you saw the
    raw ground through it, and from grade you could sight up past the
    deck to the gantry (player 2026-08-08: "I can look from the floor
    through the centrifuge... the middle floor should extend into the
    curved walls up to the ramp"). This fills each trench solid from
    grade up to 8 mm under the ramp surface (a rebate, so the shared
    edge cannot z-fight), making the tunnel floor run wall to wall. It
    stops at the portal line (-23.95): outside, the concrete entry plaza
    owns the full funnel width.
    """

    import bpy

    cols, rows = 4, 28
    y_in, y_out = -14.35, -23.95
    top, bottom = [], []
    for j in range(rows):
        y = y_out + (y_in - y_out) * j / (rows - 1)
        xo = corridor_wall_x(y) + 0.45
        for i in range(cols):
            x = side * (3.33 + (xo - 3.33) * i / (cols - 1))
            z = ramp_surface_z(x, y) - 0.008
            top.append((x, y, z))
            bottom.append((x, y, 0.0))

    verts = top + bottom
    offset = len(top)
    faces = []
    for j in range(rows - 1):
        for i in range(cols - 1):
            a = j * cols + i
            b = a + cols
            faces.append((a, b, b + 1, a + 1))
            faces.append((offset + a, offset + a + 1, offset + b + 1, offset + b))
    for j in range(rows - 1):                       # inner + outer x walls
        a = j * cols
        faces.append((a, a + cols, offset + a + cols, offset + a))
        c = j * cols + (cols - 1)
        faces.append((c + cols, c, offset + c, offset + c + cols))
    for i in range(cols - 1):                       # y end walls
        a = i
        faces.append((a + 1, a, offset + a, offset + a + 1))
        c = (rows - 1) * cols + i
        faces.append((c, c + 1, offset + c + 1, offset + c))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    # Closed solid: orient every face outward, same recipe as the ramp.
    import bmesh

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    up = sum(1 for p in mesh.polygons if p.normal.z > 0.35)
    assert up >= (rows - 1) * (cols - 1), f"{name}: shoulder top must face +Z"
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        wall = abs(poly.normal.z) < 0.5
        by_y = abs(poly.normal.x) > abs(poly.normal.y)
        for li in poly.loop_indices:
            vx, vy, vz = verts[mesh.loops[li].vertex_index]
            if wall:
                uv.data[li].uv = ((vy if by_y else vx) / 1.8, vz / 1.8)
            else:
                uv.data[li].uv = (vx / 1.8, math.hypot(vx, vy) / 1.8)
    bk.assign_material(obj, material)
    return obj


def _station_strip(name, material, side, stations, thickness, *, uv_tile=1.8,
                   smooth=40.0, crown=None):
    """Closed swept box along y-stations, extruded away from the lane.

    ``stations`` is [(y, x_in, z_lo, z_hi)] in +x terms; ``side`` mirrors.
    This is how every reveal-wall element is built: because each station's
    feet are computed FROM the surface underneath, a strip cannot float -
    the failure mode of the old fixed-z liner boxes (player's green-marked
    gaps, 2026-08-08) is unrepresentable.

    ``crown`` turns the flat top into a rounded HUMP instead of a slab with
    two square shoulders (player 2026-08-10: "give this yellow and black
    speed bump a gentle curve to each of the sides so that it transitions
    its surface cleaner for vehicles passing over it"). It is the fraction
    of the width each shoulder eases over, and the ease is a smoothstep
    pair, so the crest carries full height in the middle and the section
    meets the deck TANGENTIALLY at both edges - a tyre rolls on instead of
    hitting a 4 cm step. Default None keeps the square section every
    reveal-wall layer relies on.
    """

    import bmesh
    import bpy

    if crown is None:
        ring = [(0.0, 1.0), (0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]
    else:
        # (u across the width, height fraction of z_hi over z_lo).
        f = min(max(float(crown), 0.02), 0.5)
        span = 9  # odd, so one sample lands exactly on the crest

        def ease(t):
            t = min(max(t, 0.0), 1.0)
            return t * t * (3.0 - 2.0 * t)

        top = []
        for k in range(span):
            u = k / (span - 1)
            top.append((u, ease(u / f) * ease((1.0 - u) / f)))
        # Walk the closed section: top left->right, then the flat underside
        # right->left. Height 0 at both top ends means the shoulders die
        # into the deck and the side walls are only the buried z_lo depth.
        ring = top + [(1.0, 0.0), (0.0, 0.0)]

    m = len(ring)
    verts = []
    for y, x_in, z_lo, z_hi in stations:
        for u, hf in ring:
            verts.append((side * (x_in + u * thickness), y,
                          z_lo + (z_hi - z_lo) * hf))
    faces = []
    for i in range(len(stations) - 1):
        p, q = m * i, m * (i + 1)
        for k in range(m):
            faces.append((p + k, p + (k + 1) % m, q + (k + 1) % m, q + k))
    faces.append(tuple(range(m - 1, -1, -1)))
    e = m * (len(stations) - 1)
    faces.append(tuple(e + k for k in range(m)))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    uv = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        vx, vy, vz = verts[loop.vertex_index]
        uv.data[loop.index].uv = (vy / uv_tile, vz / uv_tile)
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(smooth))
    except Exception:
        bpy.ops.object.shade_flat()
    obj.select_set(False)
    return obj


REVEAL_Y_IN, REVEAL_Y_OUT = 17.70, 23.95  # jamb-wall overlap -> pier burial
REVEAL_TOP_IN, REVEAL_TOP_OUT = 5.60, 6.80  # raked crest, doorway -> portal


def add_reveal_walls(materials):
    """Splayed portal reveals: ONE continuous wall per side, bank to pier.

    Replaces the four floating liner boxes per side. Each wall's inner
    face rides corridor_wall_x, its FEET follow the grade authority minus
    a burial, and its crest rakes from 5.6 m at the bank doorway to 6.8 m
    under the portal header - so the corridor reads as a stadium
    vomitory: dark kick at the floor, steel field, one hazard guide
    stripe at driver eye height following the grade, machined capping
    lip. The inner end tucks 2 cm behind the doorway jamb sheets; the
    outer end flares into the pier solids. Nothing can float and nothing
    stops mid-air, by construction.
    """

    ramp_steel = materials[f"{MOD_ID}_ramp_steel"]
    pylon_dark = materials[f"{MOD_ID}_pylon_dark"]
    hazard = materials[f"{MOD_ID}_bank_hazard"]
    track_grey = materials[f"{MOD_ID}_track_grey"]

    objs = []
    n = 13
    ys = [REVEAL_Y_IN + (REVEAL_Y_OUT - REVEAL_Y_IN) * k / (n - 1) for k in range(n)]

    def wall_x(ay):
        return corridor_wall_x(-ay)

    def floor_z(ay):
        return ramp_surface_z(wall_x(ay), -ay)

    def top_z(ay):
        t = (ay - REVEAL_Y_IN) / (REVEAL_Y_OUT - REVEAL_Y_IN)
        top = REVEAL_TOP_IN + (REVEAL_TOP_OUT - REVEAL_TOP_IN) * t
        # Inner-end dive (round 15 coda, the black knobs - player circled
        # them twice). The bank leans OUTWARD going up, so anything in
        # the corridor standing above the bank's local crest line
        # (z ~5.1 at r ~18.1) shows INSIDE the bowl as a knob over the
        # doorway: the DAE vertex dump matched the knob exactly to the
        # jamb post top at z 5.62-5.65, and the cap rail tops out there
        # too. The wall crest now ducks from 5.60 at ay 18.9 down to
        # 4.55 at the drum, taking the cap and the post (top_z + 0.05)
        # safely below the bank line - a vomitory wall dropping into the
        # throat, and nothing pokes into the bowl.
        if ay < 18.9:
            top -= (18.9 - ay) / 1.2 * 1.05
        return top

    for side_tag, side in (("l", -1.0), ("r", 1.0)):
        body = [(-ay, wall_x(ay), floor_z(ay) - 0.06, top_z(ay)) for ay in ys]
        objs.append(_station_strip(
            f"{MOD_ID}_reveal_{side_tag}", ramp_steel, side, body, 0.34))
        kick = [(-ay, wall_x(ay) - 0.035, floor_z(ay) - 0.05, floor_z(ay) + 0.62)
                for ay in ys]
        objs.append(_station_strip(
            f"{MOD_ID}_reveal_kick_{side_tag}", pylon_dark, side, kick, 0.10))
        stripe = [(-ay, wall_x(ay) - 0.022, floor_z(ay) + 2.12, floor_z(ay) + 2.40)
                  for ay in ys]
        objs.append(_station_strip(
            f"{MOD_ID}_reveal_stripe_{side_tag}", hazard, side, stripe, 0.08))
        cap = [(-ay, wall_x(ay) - 0.045, top_z(ay) - 0.05, top_z(ay) + 0.07)
               for ay in ys]
        objs.append(_station_strip(
            f"{MOD_ID}_reveal_cap_{side_tag}", track_grey, side, cap, 0.42))

        # --- Round 15 junction trims ---------------------------------
        # (a) The wall line dives into the pier around ay 22.7 through
        # the pier's bowl-side face at a glancing angle, so each layer
        # (kick / stripe / cap, proud at different depths) exited at a
        # slightly different spot along the pier's 5 cm bevel - the
        # player's green-marked sliver. A dark cover trim ON the pier
        # face turns the exit into a detail, the way a wall dying into
        # masonry gets trimmed.
        from components import louver_facade as _lf
        pier_rad = math.radians(_lf.ENTRY_DEG + side * _lf.PIER_MID_DEG)
        nx, ny = -math.cos(pier_rad), -math.sin(pier_rad)
        # 2026-08-10, third round on this sliver, and the trim itself was
        # the bug: its section is (0.20 radial, 0.95 tangential). Local X
        # is RADIAL, so it presented a 0.20 m wide face to a viewer down
        # the corridor while sticking 0.95 m ACROSS the lane - a thin
        # vertical strip of cover on a pier face it was supposed to sheet.
        # The terracotta each side of that 20 cm was the green mark, three
        # times. A cover on a plane must be WIDE in the plane and THIN
        # through it: the section is now 0.90 radial x 0.14 tangential.
        # It rides pier_inner_x at its own station instead of a hardcoded
        # 4.19 (which stopped matching the wall when b125 made the wall
        # follow the pier plane), offset 0.05 into the corridor so it
        # cannot z-fight the face it covers.
        trim_ay = 23.30
        tz0 = floor_z(trim_ay) - 0.10
        tz1 = top_z(22.70) + 0.28
        face_x = pier_inner_x(trim_ay)
        objs.append(bk.add_box(
            f"{MOD_ID}_reveal_piertrim_{side_tag}",
            (side * face_x + nx * 0.05, -trim_ay + ny * 0.05,
             (tz0 + tz1) / 2.0),
            (0.90, 0.14, tz1 - tz0),
            pylon_dark,
            bevel=0.03,
            rotation=(0.0, 0.0, pier_rad),
            metric_uv=(2.0, 2.0),
        ))
        # (b) The wall's bowl end stopped mid-air beside the drum skin
        # (the green-marked floating bracket): a vomitory gets a door
        # frame. One dark post per side, buried below the floor and past
        # the cap top, that the kick, stripe and cap all die into.
        post_z0 = floor_z(17.70) - 0.30
        # +0.05, NOT +0.30 (round 15 finale): the taller posts' top 30 cm
        # poked through the bank's interior face and hung under the
        # hazard band as two black knobs inside the bowl (player, green
        # circles - twice). The cap still dies into the post; nothing
        # shows on the bowl side.
        post_z1 = top_z(17.70) + 0.05
        objs.append(bk.add_box(
            f"{MOD_ID}_reveal_jambpost_{side_tag}",
            (side * (wall_x(17.70) + 0.12), -17.62,
             (post_z0 + post_z1) / 2.0),
            (0.55, 0.42, post_z1 - post_z0),
            pylon_dark,
            bevel=0.03,
            metric_uv=(2.0, 2.0),
        ))
    return objs


def add_entry_plaza(materials):
    """Concrete entry plaza: the facade's funnel plan on the ONE grade.

    A single lofted solid from the apron (where ramp_surface_z sinks to
    apron level, it simply dies in - no toe, no curb) up to the portal,
    full funnel width, its top 4 mm under the steel ramp in their 0.35 m
    overlap so the handoff shows a crisp steel nosing and can never
    z-fight. Edge nosings ride the taper exactly as before. The hazard
    threshold band that used to cross the lane here (a 6.7 m striped bar
    proud 29 mm at the concrete->steel handoff) was DELETED 2026-08-12 -
    player: "remove the speed bump hazard bar on the ramp". The handoff
    is marked well enough by the steel nosing itself.
    """

    import bmesh
    import bpy

    concrete = materials[f"{MOD_ID}_floor_concrete"]
    hazard = materials[f"{MOD_ID}_bank_hazard"]

    objs = []
    cols, rows = 15, 26

    def plaza_top(x, y):
        return max(ramp_surface_z(x, y) - 0.004, 0.056)

    top, bottom = [], []
    for j in range(rows):
        y = PLAZA_Y_OUT + (PLAZA_Y_IN - PLAZA_Y_OUT) * j / (rows - 1)
        w = plaza_half_w(y)
        for i in range(cols):
            x = -w + 2.0 * w * i / (cols - 1)
            top.append((x, y, plaza_top(x, y)))
            bottom.append((x, y, -0.02))
    verts = top + bottom
    offset = len(top)
    faces = []
    for j in range(rows - 1):
        for i in range(cols - 1):
            a = j * cols + i
            b = a + cols
            faces.append((a, b, b + 1, a + 1))
            faces.append((offset + a, offset + a + 1, offset + b + 1, offset + b))
    for j in range(rows - 1):
        a = j * cols
        faces.append((a, a + cols, offset + a + cols, offset + a))
        c = j * cols + (cols - 1)
        faces.append((c + cols, c, offset + c, offset + c + cols))
    for i in range(cols - 1):
        a = i
        faces.append((a + 1, a, offset + a, offset + a + 1))
        c = (rows - 1) * cols + i
        faces.append((c, c + 1, offset + c + 1, offset + c))
    mesh = bpy.data.meshes.new(f"{MOD_ID}_entry_plaza")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    up = sum(1 for p in mesh.polygons if p.normal.z > 0.35)
    assert up >= (rows - 1) * (cols - 1), "plaza top must face +Z"
    obj = bpy.data.objects.new(f"{MOD_ID}_entry_plaza", mesh)
    bpy.context.scene.collection.objects.link(obj)
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        wall = abs(poly.normal.z) < 0.5
        by_y = abs(poly.normal.x) > abs(poly.normal.y)
        for li in poly.loop_indices:
            vx, vy, vz = verts[mesh.loops[li].vertex_index]
            if wall:
                # Round 15 (player: the raised edge "needs detail and to
                # make sense"): the top-planar map stretched into
                # pinstripes on the funnel's side faces. Walls map like
                # walls: run-along x height.
                uv.data[li].uv = ((vy if by_y else vx) / 2.4, vz / 2.4)
            else:
                uv.data[li].uv = (vx / 2.4, math.hypot(vx, vy) / 2.4)
    bk.assign_material(obj, concrete)
    objs.append(obj)

    # Edge nosings: sunk hazard strips following the funnel taper. They
    # STOP at -24.6, before the portal throat: run to the portal plane
    # they poked out from under the reveal-wall bases as a stray sliver
    # on the concrete (player's green floor mark, 2026-08-08). The final
    # station feathers to 6 mm so the tip chamfers into the deck instead
    # of presenting a square end.
    n = 18
    ys = [-32.60 + (-24.60 + 32.60) * k / (n - 1) for k in range(n)]
    for side_tag, side in (("l", -1.0), ("r", 1.0)):
        stations = []
        for k, y in enumerate(ys):
            w = plaza_half_w(y)
            t = plaza_top(side * (w - 0.26), y)
            hi = t + (0.006 if k == n - 1 else 0.041)
            stations.append((y, w - 0.47, t - 0.055, hi))
        # crown 0.34: a rolled speed-hump section instead of a 4 cm slab
        # with two square shoulders (player 2026-08-10). The shoulders ease
        # down THROUGH the deck line - z_lo is 5.5 cm buried - so the edges
        # emerge from the concrete rather than standing on it, and a tyre
        # crossing at any angle meets a tangent, never a lip.
        objs.append(_station_strip(
            f"{MOD_ID}_plaza_nosing_{side_tag}", hazard, side, stations, 0.42,
            uv_tile=1.2, crown=0.34))

    return objs


ROTOR_ARM_OBJECTS: list = []


def build_visual(materials) -> list:
    hazard = materials[f"{MOD_ID}_bank_hazard"]
    concrete = materials[f"{MOD_ID}_floor_concrete"]
    cream = materials[f"{MOD_ID}_console_cream"]
    pylon_dark = materials[f"{MOD_ID}_pylon_dark"]
    dial_white = materials[f"{MOD_ID}_dial_white"]
    beacon = materials[f"{MOD_ID}_beacon_amber"]
    ramp_steel = materials[f"{MOD_ID}_ramp_steel"]

    import bpy
    from components import (
        interior_vault,
        louver_facade,
        rotor_machine,
        shell_roof,
        track_bowl,
    )

    objects = []
    # Ground apron slab under everything (terrain-level concourse).
    # Foundation disc, not a 54 m square pad (player 2026-08-08: "remove
    # the concrete pad from around the structure"): a round building gets
    # a round plinth. r 24.5 shows a 0.2 m foundation reveal past the fin
    # ring; outside it, the map's own ground runs to the plaza tongue.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_apron",
            (0.0, 0.0, 0.025),
            24.5,
            0.05,
            concrete,
            vertices=72,
            axis="Z",
        )
    )
    # Components (worker-built). The ENTIRE hub machine - dome, bedplate,
    # C-frame bearing stands AND the arm - is one rigid spinning part.
    # Splitting it (arm meshes to the "rotor" part, everything else to the
    # static building) had the arm orbiting over its own frozen bearing
    # stands (player 2026-08-08: the arm and the pedestal "should be
    # spinning together and not disconnected"). The machine is a body of
    # revolution at its deck junction, so yawing all of it is seamless,
    # and the part is visual-only (collisionType None) so nothing changes
    # for physics.
    objects += track_bowl.build(materials)
    ROTOR_ARM_OBJECTS.clear()
    ROTOR_ARM_OBJECTS.extend(rotor_machine.build(materials))
    objects += shell_roof.build(materials)
    objects += louver_facade.build(materials)
    objects += interior_vault.build(materials)

    # Vomitory tunnel. The bank's doorway is AUTHORED by the track_bowl
    # component (skip_az), not boolean-cut: booleans against those open
    # surface meshes fragmented the track (player screenshots).
    # Steel ramp stops at the portal line: outside, the concrete plaza owns
    # the full funnel width on the SAME grade function.
    objects.append(
        add_vomitory_ramp(f"{MOD_ID}_vomitory_ramp", ramp_steel, outer_y=-23.9)
    )
    for side_tag, side in (("l", -1.0), ("r", 1.0)):
        objects.append(
            add_ramp_shoulder(
                f"{MOD_ID}_vomitory_shoulder_{side_tag}", ramp_steel, side
            )
        )
    # The corridor lining is the reveal-wall system (bank jambs -> piers),
    # which replaced the four fixed-z liner boxes per side: pitched boxes
    # over a radially curved floor either floated (green-marked daylight
    # slots under their bases, 2026-08-08) or beached their corners in the
    # bank. Station-swept walls whose feet SAMPLE the floor cannot do
    # either.
    objects += add_reveal_walls(materials)
    objects += add_entry_plaza(materials)
    # Portal header: graphite beam pier-to-pier over the opening. Ends
    # bury 0.09 into each pier solid, top buries into the canopy's
    # recessed reveal band (z0 7.42), bottom closes the clerestory slot
    # over the reveal crests (6.80). Piers + header + reveals + plaza =
    # one composed portal instead of loose slabs.
    facade_steel = materials[f"{MOD_ID}_facade_steel"]
    objects.append(
        bk.add_box(
            f"{MOD_ID}_vomitory_header",
            (0.0, -23.6, 7.125),
            (8.9, 0.5, 0.75),
            facade_steel,
            bevel=0.03,
            metric_uv=(2.4, 2.4),
        )
    )
    # Painted lane lines on the raceway: two concentric rings.
    lane_paint = materials[f"{MOD_ID}_lane_paint"]
    for ring_index, lane_r in enumerate((8.5, 13.5)):
        frac = (lane_r - spec.CONE_INNER_R) / (spec.CONE_OUTER_R - spec.CONE_INNER_R)
        lane_z = spec.CONE_INNER_Z + frac * (spec.CONE_OUTER_Z - spec.CONE_INNER_Z)
        # Sunk until only a sliver shows: a 0.05 minor-radius torus centred
        # 0.015 ABOVE the deck stood 65 mm proud - two full rumble-strip
        # rings across a raceway. Sinking it to -0.044 leaves a 54 mm wide
        # painted line standing 6 mm proud, which reads the same and drives
        # like paint.
        objects.append(
            bk.add_torus(
                f"{MOD_ID}_lane_line_{ring_index}",
                (0.0, 0.0, lane_z - 0.044),
                lane_r,
                0.05,
                lane_paint,
                major_segments=96,
                minor_segments=6,
            )
        )
    # Rim beacons DELETED (player 2026-08-08): they were authored on the
    # open bowl lip before the CHIEF shell landed; under the roof their
    # posts and amber globes skewered the vault's light cans from inside
    # ("black bar with golden sphere... within the structure"). The
    # trolley's rotating beacon part is the facility's warning light now.
    # Operator console, round 14 (player: "a real control panel for a
    # centrifuge... highly detailed"): dark plinth, cream pedestal
    # cabinet, graphite front plate carrying five colour-coded caps (the
    # E-STOP a red mushroom on an amber collar, PURGE an emissive amber
    # mushroom in a dark guard ring), a gauge BINNACLE on top with bezel,
    # red-zone ticks and a glass over the dial (obs_glass, so the gauge
    # glows faintly at night), an annunciator lamp row, corner screws,
    # side vents and a cable drop. Every cap centre comes from
    # spec.PANEL_BUTTONS, which also drives the cage anchors and the
    # triggers2 click boxes - one table, calibrated by construction.
    btn_green = materials[f"{MOD_ID}_btn_green"]
    btn_red = materials[f"{MOD_ID}_btn_red"]
    btn_blue = materials[f"{MOD_ID}_btn_blue"]
    btn_white = materials[f"{MOD_ID}_btn_white"]
    btn_orange = materials[f"{MOD_ID}_btn_orange"]
    beacon_amber = materials[f"{MOD_ID}_beacon_amber"]
    drum_steel = materials[f"{MOD_ID}_drum_steel"]
    obs_glass = materials[f"{MOD_ID}_obs_glass"]
    cx = spec.CONSOLE_X
    objects.append(
        bk.add_box(
            f"{MOD_ID}_console_plinth", (cx, 0.0, 0.24), (2.5, 1.6, 0.48),
            pylon_dark, bevel=0.03, metric_uv=(1.6, 1.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_console_body", (cx, 0.0, 1.09), (2.3, 1.35, 1.22),
            cream, bevel=0.05, metric_uv=(1.6, 1.6),
        )
    )
    # Faceplate LOWERED 2026-08-09h (player: "lower the HYPER-G DRUM
    # CONTROL black faceplate ... to give room to the field coupling and
    # controls and labels"). It used to stop at z 0.745 with a 0.265 m
    # cream apron doing nothing underneath it; it now runs to z 0.545,
    # and that 0.20 m is exactly the band the coupling instrument needed.
    # Geometry and print share spec._PLATE_* so they cannot drift.
    _pz0, _ph = spec._PLATE_Z0, spec._PLATE_H
    objects.append(
        bk.add_box(
            f"{MOD_ID}_console_plate", (cx, -0.70, _pz0 + _ph / 2.0),
            (1.9, 0.06, _ph), pylon_dark, bevel=0.02,
        )
    )
    for sx, sz in ((-0.85, 0.62), (0.85, 0.62), (-0.85, 1.62), (0.85, 1.62)):
        objects.append(
            bk.add_sphere(
                f"{MOD_ID}_console_screw_{'p' if sx > 0 else 'm'}{int(sz * 100)}",
                (cx + sx, -0.735, sz), 0.022, drum_steel, segments=8, rings=6,
            )
        )
    # Engraved legend sheet (round 15, player: "professionally and
    # realistically labeled buttons"). A 11 mm skin over the plate whose
    # FRONT face carries an authored 0..1 UV frame: the panel_legend
    # family prints the title plus a label under each cap at coordinates
    # computed from spec.PANEL_BUTTONS, so print and caps cannot drift.
    # bk.add_box UVs are metric, hence the hand re-unwrap of that face.
    # Thin enough that the plate screws (y -0.735, r 0.022) still poke
    # through in front of it.
    legend = bk.add_box(
        f"{MOD_ID}_console_legend",
        (cx, -0.7355, _pz0 + _ph / 2.0), (1.9, 0.011, _ph),
        materials[f"{MOD_ID}_panel_legend"], bevel=0.0,
    )
    lmesh = legend.data
    luv = lmesh.uv_layers.active
    if luv is None:
        luv = lmesh.uv_layers.new(name="UVMap")
    for poly in lmesh.polygons:
        if poly.normal.y < -0.5:
            for li in poly.loop_indices:
                vx, _vy, vz = lmesh.vertices[lmesh.loops[li].vertex_index].co
                luv.data[li].uv = ((vx + 0.95) / 1.9, (vz + _ph / 2.0) / _ph)
    objects.append(legend)
    # Field-coupling bar-graph SOCKETS: the machined recesses the amber
    # segments sit in (the segments themselves are moving parts, built in
    # build_parts). Static, so an unlit level still reads as an empty
    # slot rather than as nothing at all - that is what makes the gauge
    # legible as "3 of 5" instead of "3 blocks".
    for gauge in ("adh", "drag"):
        for i, seg_x in enumerate(spec.BAR_SEG_X[gauge], start=1):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_{gauge}_socket{i}",
                    (seg_x, -0.7450, spec.BAR_SEG_Z), (0.060, 0.008, 0.034),
                    drum_steel, bevel=0.003,
                )
            )
    for side in (-1.0, 1.0):
        for v in range(3):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_console_vent_{'l' if side < 0 else 'r'}{v}",
                    (cx + side * 1.16, 0.15, 0.78 + 0.17 * v),
                    (0.05, 0.62, 0.05), pylon_dark, bevel=0.0,
                )
            )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_console_conduit", (cx + 0.75, 0.45, 0.35), 0.06, 0.72,
            pylon_dark, vertices=10, axis="Z",
        )
    )
    # Annunciator lamp row over the plate.
    for k, lamp_mat in enumerate((btn_green, beacon_amber, btn_red)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_console_lamp_{k}",
                (cx - 0.22 + 0.22 * k, -0.685, 1.62), 0.035, 0.05,
                lamp_mat, vertices=10, axis="Y",
            )
        )
    # Gauge binnacle: drum + face + bezel + ticks + red zone + glass.
    dx, dy, dz = spec.DIAL_PIVOT
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_dial_drum", (dx, dy, dz - 0.17), 0.62, 0.35,
            pylon_dark, vertices=24, axis="Z",
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_dial_face", (dx, dy, dz - 0.035), 0.55, 0.07,
            dial_white, vertices=28, axis="Z",
        )
    )
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_dial_bezel", (dx, dy, dz + 0.005), 0.56, 0.045,
            drum_steel, major_segments=28, minor_segments=8,
        )
    )
    sweep = math.radians(270.0)
    for tick in range(12):
        frac = tick / 11.0
        a = -frac * sweep + math.radians(90.0)
        major = tick % 2 == 0
        objects.append(
            bk.add_box(
                f"{MOD_ID}_dial_tick_{tick}",
                (dx + math.cos(a) * 0.44, dy + math.sin(a) * 0.44, dz + 0.001),
                (0.11 if major else 0.06, 0.025, 0.012),
                pylon_dark, bevel=0.0, rotation=(0.0, 0.0, a),
            )
        )
    # Red zone: the last fifth of the sweep (400+ RPM), matching the
    # needle convention (+90 deg base, clockwise).
    for k in range(4):
        frac = 0.82 + 0.06 * k
        a = -frac * sweep + math.radians(90.0)
        objects.append(
            bk.add_box(
                f"{MOD_ID}_dial_redzone_{k}",
                (dx + math.cos(a) * 0.50, dy + math.sin(a) * 0.50, dz + 0.001),
                (0.075, 0.05, 0.010),
                btn_red, bevel=0.0, rotation=(0.0, 0.0, a),
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_dial_glass", (dx, dy, dz + 0.085), 0.545, 0.018,
            obs_glass, vertices=28, axis="Z",
        )
    )
    # Button caps from the single PANEL_BUTTONS table.
    for button in spec.PANEL_BUTTONS:
        bx, by, bz = button["position"]
        style = button.get("cap", "round_blue")
        if style == "round_green":
            cap_mat, cap_r = btn_green, 0.075
        elif style == "round_blue":
            cap_mat, cap_r = btn_blue, 0.065
        elif style == "round_white":
            # RPM pair (2026-08-09g relayout).
            cap_mat, cap_r = btn_white, 0.065
        elif style == "round_small":
            # C.H.I.E.F. field-coupling cluster (2026-08-09f).
            cap_mat, cap_r = btn_blue, 0.045
        elif style == "estop":
            cap_mat, cap_r = btn_red, 0.115
        else:
            cap_mat, cap_r = beacon_amber, 0.10
        if style in ("estop", "purge"):
            collar_mat = btn_orange if style == "estop" else pylon_dark
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_collar_{button['id']}", (bx, by + 0.005, bz),
                    cap_r + 0.055, 0.035, collar_mat, vertices=18, axis="Y",
                )
            )
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_stem_{button['id']}", (bx, by - 0.035, bz),
                    cap_r * 0.55, 0.07, pylon_dark, vertices=12, axis="Y",
                )
            )
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_cap_{button['id']}", (bx, by - 0.085, bz),
                    cap_r, 0.05, cap_mat, vertices=18, axis="Y",
                )
            )
        else:
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_bezel_{button['id']}", (bx, by + 0.008, bz),
                    cap_r + 0.035, 0.04, pylon_dark, vertices=16, axis="Y",
                )
            )
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_cap_{button['id']}", (bx, by - 0.028, bz),
                    cap_r, 0.06, cap_mat, vertices=16, axis="Y",
                )
            )
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    dial_white = materials[f"{MOD_ID}_dial_white"]
    needle_red = materials[f"{MOD_ID}_needle_red"]

    import bpy as _bpy2

    # Door plug: a bank-profile segment sealing the vomitory mouth while
    # spinning; rotates about the drum axis to open (round-7 machinery).
    # Plug = the missing BANK segment, swept on the exact bank curve so a
    # closed door continues the banked raceway with no lip or seam.  The
    # cone deck is CONTINUOUS through the doorway (only the bank is cut),
    # so the plug starts at BANK_R0 - reaching further in only stacked a
    # second surface on top of the deck.
    #
    # The previous profile ran 13.2 -> 14.6 -> 16.0 -> 15.758 -> 16.317:
    # non-monotonic, so the swept surface folded back through itself at
    # the doorway.  Radii must increase all the way out.
    #
    # DOOR_INSET sinks the leaf just under the track line: closed it is a
    # shutline rather than a step, open it tucks under the solid bank in
    # the neighbouring sector instead of z-fighting it.  0.06 was a felt
    # lip at speed; 0.025 matches the deck's own seam depth.
    DOOR_INSET = 0.025
    plug_steps = 10
    # Exactly the bank surface, nothing more: an outward return here used
    # to run to RIM_TOP_R + 0.75, which now lands past the cornice and
    # through the outer drum skin.
    door_profile = [(r, z - DOOR_INSET) for r, z in spec.BANK_PROFILE]
    assert all(
        door_profile[i][0] <= door_profile[i + 1][0]
        for i in range(len(door_profile) - 1)
    ), "door profile must be monotonic in radius or the sweep self-folds"
    # SPLIT at the hazard course (2026-08-09, "grey metal door" round):
    # the static hazard band now skips the doorway like every other ring,
    # so the sealed leaf's UPPER COURSE must wear bank_hazard or the
    # chevron warning ring shows a 26-deg gap across the closed mouth
    # (seamless-closure law: restore the FULL surface, stripes included).
    from components import track_bowl as _tb0

    _hz_r, _hz_z = _tb0._bank_frame(_tb0.BANK_S_HAZARD)[:2]
    _hz_z -= DOOR_INSET
    lower_profile = [p for p in door_profile if p[0] < _hz_r - 1e-6]
    upper_profile = [p for p in door_profile if p[0] > _hz_r + 1e-6]
    lower_profile.append((_hz_r, _hz_z))
    upper_profile.insert(0, (_hz_r, _hz_z))

    def _build_plug(suffix, profile, material, metric_uv=None):
        # Sweep 2 deg WIDER than the bank's 257-283 opening on each side.
        # _swept_mesh decides the opening per FACE MIDPOINT, so at 192
        # azimuth steps the real hole runs about a face wider than its
        # nominal window; a plug cut to exactly 257-283 left a thin lit
        # slit at each jamb. The overlap tucks under the bank (the leaf
        # is inset 25 mm) and is invisible both closed and parked.
        verts = []
        faces = []
        count = len(profile)
        slope = [0.0]
        for k in range(1, count):
            dr = profile[k][0] - profile[k - 1][0]
            dz = profile[k][1] - profile[k - 1][1]
            slope.append(slope[-1] + math.hypot(dr, dz))
        for j in range(plug_steps + 1):
            a = math.radians(255.0 + 30.0 * j / plug_steps)
            c, s = math.cos(a), math.sin(a)
            for radius, z in profile:
                verts.append((c * radius, s * radius, z))
        for j in range(plug_steps):
            base = j * count
            nxt = (j + 1) * count
            for k in range(count - 1):
                faces.append((base + k, nxt + k, nxt + k + 1, base + k + 1))
        mesh = _bpy2.data.meshes.new(f"{MOD_ID}_door_{suffix}")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        # The plug is an OPEN surface, so recalc_face_normals has no
        # "outside" to work from - decide by the mean normal instead.
        # Wound the way the sweep runs, all faces pointed DOWN: with the
        # material backface culled, the closed door was invisible from
        # the deck and the doorway still read as a hole while shut.
        if sum(p.normal.z for p in mesh.polygons) < 0.0:
            mesh.flip_normals()
            mesh.update()
        assert sum(p.normal.z for p in mesh.polygons) > 0.0, \
            f"door {suffix} faces down"
        if metric_uv:
            # Cylindrical metric UVs matching the static band's 1.4 m
            # tile (the b101 law: hazard trim ALWAYS gets metric UVs -
            # a raw-unwrapped chevron reads as diagonal smears).
            layer = mesh.uv_layers.new(name="UVMap")
            for poly in mesh.polygons:
                for li in poly.loop_indices:
                    vi = mesh.loops[li].vertex_index
                    j = vi // count
                    k = vi % count
                    a = math.radians(255.0 + 30.0 * j / plug_steps)
                    arc = a * profile[k][0]
                    layer.data[li].uv = (arc / metric_uv, slope[k] / metric_uv)
        obj = _bpy2.data.objects.new(f"{MOD_ID}_door_{suffix}", mesh)
        _bpy2.context.scene.collection.objects.link(obj)
        bk.assign_material(obj, material)
        _bpy2.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        _bpy2.context.view_layer.objects.active = obj
        try:
            _bpy2.ops.object.shade_auto_smooth(angle=math.radians(40.0))
        except Exception:
            _bpy2.ops.object.shade_smooth()
        obj.select_set(False)
        return obj

    door_objects = [
        _build_plug("plug", lower_profile, materials[f"{MOD_ID}_track_grey"]),
        _build_plug(
            "plug_hazard",
            upper_profile,
            materials[f"{MOD_ID}_bank_hazard"],
            metric_uv=1.4,
        ),
    ]

    # C.H.I.E.F. FIELD COUPLING bar graphs (2026-08-09h, player: "a
    # better visual indicator of how much of an adjustment we've made").
    # The 0.025 m/level sliders were unreadable from a car; each gauge is
    # now a five-segment lit bar between its own [-] and [+] caps. The
    # machined SOCKETS behind these blocks are static console furniture
    # (build_console) so the unlit part of the ladder still reads; these
    # amber blocks are the moving half - the runtime shoves an unlit one
    # +0.12 m in authored y, straight back through the opaque plate into
    # the cabinet. Top segment is red: past NOM is the torture zone.
    #   legend front face: y -0.7355 - 0.011/2 = -0.7410
    #   socket  -0.7450 (front -0.7490)   segment -0.7580 (front -0.7670)
    bar_parts: dict[str, dict[str, object]] = {}
    for gauge in ("adh", "drag"):
        for i, seg_x in enumerate(spec.BAR_SEG_X[gauge], start=1):
            seg_mat = materials[
                f"{MOD_ID}_btn_red" if i == 5 else f"{MOD_ID}_btn_orange"
            ]
            bar_parts[f"{gauge}_seg{i}"] = {
                "objects": [
                    bk.add_box(
                        f"{MOD_ID}_{gauge}_seg{i}",
                        (seg_x, -0.7580, spec.BAR_SEG_Z),
                        (0.052, 0.018, 0.028),
                        seg_mat, bevel=0.004,
                    )
                ],
                "pivot": (seg_x, -0.7580, spec.BAR_SEG_Z),
            }

    # Dial needle: flat spinner on the binnacle gauge (Z-axis, sign-safe),
    # sized for the round-14 0.55 m face and tucked under its glass.
    needle = bk.add_box(
        f"{MOD_ID}_needle",
        (spec.DIAL_PIVOT[0] + 0.33, spec.DIAL_PIVOT[1], spec.DIAL_PIVOT[2] + 0.045),
        (0.80, 0.10, 0.035),
        needle_red,
        bevel=0.0,
    )
    hub_cap = bk.add_cylinder(
        f"{MOD_ID}_needle_hub",
        (spec.DIAL_PIVOT[0], spec.DIAL_PIVOT[1], spec.DIAL_PIVOT[2] + 0.045),
        0.10,
        0.045,
        dial_white,
        vertices=16,
    )

    # Rotating warning beacon head (player 2026-08-08): emissive amber
    # drum with two dark shroud quadrants and a dark cap. The runtime
    # retracts it into the trolley's housing collar at idle (pose offset
    # -0.36) and spins it about +Z while the protocol runs - amber
    # windows sweeping past = a working rotating warning lamp, no engine
    # lights needed.
    from components import interior_vault as _iv

    bxp, byp, bzp = _iv.BEACON_POS
    # The runtime's rotating beacon LIGHTS (spec BEHAVIOR beacon_light_pos,
    # 2026-08-09 cop-light round) must ride this same anchor - drift here
    # means beams sweeping out of thin air next to the head.
    _blp = spec.BEHAVIOR["beacon_light_pos"]
    assert (
        abs(_blp[0] - bxp) < 1e-6
        and abs(_blp[1] - byp) < 1e-6
        and abs(_blp[2] - (bzp + 0.09)) < 1e-6
    ), f"beacon_light_pos {_blp} drifted from BEACON_POS {_iv.BEACON_POS}"
    amber_mat = materials[f"{MOD_ID}_beacon_amber"]
    beacon_dark = materials[f"{MOD_ID}_pylon_dark"]
    beacon_objs = [
        bk.add_cylinder(
            f"{MOD_ID}_beacon_head", (bxp, byp, bzp + 0.03), 0.125, 0.20,
            amber_mat, vertices=14, axis="Z",
        ),
        bk.add_box(
            f"{MOD_ID}_beacon_shroud_a", (bxp + 0.088, byp, bzp + 0.03),
            (0.07, 0.24, 0.21), beacon_dark, bevel=0.01,
        ),
        bk.add_box(
            f"{MOD_ID}_beacon_shroud_b", (bxp - 0.088, byp, bzp + 0.03),
            (0.07, 0.24, 0.21), beacon_dark, bevel=0.01,
        ),
        bk.add_cylinder(
            f"{MOD_ID}_beacon_cap", (bxp, byp, bzp + 0.145), 0.135, 0.035,
            beacon_dark, vertices=14, axis="Z",
        ),
    ]

    from components import track_bowl as _tb

    parts = {
        # collision False (round 15): the leaf's baked static collision
        # repeatedly went stale mid-slide - r15e photographed it parked
        # HALF-OPEN across the lane while the machine idled, and every
        # unexplained centre-lane deflation traced to its arc (r 15-17,
        # az 262-267). The leaf stays theater; the SHELF below is the
        # physics (build 95) - the split exists because a sliding leaf
        # has an unsafe stale pose and a vertically-buried shelf does
        # not.
        "door": {"objects": door_objects, "pivot": (0.0, 0.0, 0.0),
                 "collision": False},
        # Mouth shelf (build 95, player: "vehicles fall into entrance...
        # the mesh doesn't close up properly"): the doorway aperture's
        # rideable floor while the protocol runs. collision TRUE - the
        # runtime buries it at idle and bakes collision only at travel
        # endpoints, both of which are safe surfaces (raised = the
        # faired swale continuing the flank columns, buried = under the
        # ramp lattice), so the round-15 stale-bake trap cannot recur.
        "shelf": {"objects": _tb.build_mouth_shelf(materials),
                  "pivot": (0.0, 0.0, 0.0), "collision": True},
        "dial_needle": {"objects": [needle, hub_cap], "pivot": spec.DIAL_PIVOT},
        "rotor": {"objects": list(ROTOR_ARM_OBJECTS), "pivot": (0.0, 0.0, 3.4)},
        "beacon": {"objects": beacon_objs, "pivot": (bxp, byp, bzp)},
    }
    parts.update(bar_parts)
    if not ROTOR_ARM_OBJECTS:
        parts.pop("rotor")
    return parts


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    # Concourse ground plate (big flat collision under everything).
    # Shrunk with the visual apron (54 m square -> r 24.5 disc). The plate
    # must never outreach the concrete or its corners become an invisible
    # 8 cm shelf over raw terrain, so the square inscribes the disc
    # (17.2 * sqrt(2) = 24.3 < 24.5). Outside it, cars ride the map's own
    # terrain (5 cm visual sink into the disc, the site-wide contract);
    # the corridor floor is the tunnel lattice, which is independent.
    plate = cage.add_box_lattice(
        "ground",
        (-17.2, -17.2, 0.0),
        (17.2, 17.2, 0.08),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("top",),
        face_ground_models={"top": "asphalt"},
    )

    def nearest_plate(x: float, y: float) -> str:
        ix = max(0, min(2, round((x + 17.2) / 17.2)))
        iy = max(0, min(2, round((y + 17.2) / 17.2)))
        return plate[(int(ix), int(iy), 1)]


    def add_quad_both(quad, ground_model):
        """Double-sided quad: HIGHER diagonal wound up, lower wound down.

        Two failed idioms preceded this (round 15 coda):
        1. add_quad(q) + add_quad(reversed(q)) re-triangulated the
           reversed copy on the OPPOSITE diagonal. On twisted quads the
           two tilings split up to 34 cm; whenever the DOWN-facing
           tiling was the higher one it hovered as an invisible one-way
           ceiling and wheels wedged in the taper (b83 sweep defect 1,
           five sites; the player's wedged-wagon screenshot).
        2. Exactly-coincident mirrored twins (same diagonal, both
           windings - b85) popped tires ON FLAT PLANAR GROUND: jbeam
           triangles carry pressure/contact state and an exact
           zero-thickness twin generates spike forces on contact (the
           b85 entry regression: FL deflated at 3 m/s on the bare
           apron). NEVER emit the same node triple twice.
        This version computes both tilings' centre heights and winds
        the HIGHER tiling as the floor (normals up) and the LOWER as
        the one-way underside: the ride surface is always the true
        upper envelope, a ceiling can never sit above a floor, and all
        four triples are distinct. Planar quads degrade to the proven
        crossed-diagonal b76-b84 emission exactly.
        """
        a, b, c, d = quad
        pos = {n["id"]: n["position"] for n in cage.nodes
               if n["id"] in (a, b, c, d)}
        za, zb, zc, zd = (pos[a][2], pos[b][2], pos[c][2], pos[d][2])

        def wind_up(t1, t2, t3):
            p1, p2, p3 = pos[t1], pos[t2], pos[t3]
            nz = ((p2[0] - p1[0]) * (p3[1] - p1[1])
                  - (p2[1] - p1[1]) * (p3[0] - p1[0]))
            return (t1, t2, t3) if nz >= 0 else (t3, t2, t1)

        def wind_down(t1, t2, t3):
            u = wind_up(t1, t2, t3)
            return (u[2], u[1], u[0])

        pa, pb, pc, pd = pos[a], pos[b], pos[c], pos[d]
        d1 = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
        d2 = (pd[0] - pb[0], pd[1] - pb[1], pd[2] - pb[2])
        qn = (d1[1] * d2[2] - d1[2] * d2[1],
              d1[2] * d2[0] - d1[0] * d2[2],
              d1[0] * d2[1] - d1[1] * d2[0])
        qlen = math.sqrt(qn[0] ** 2 + qn[1] ** 2 + qn[2] ** 2) or 1.0
        # Degenerate/sliver guard (b87): a quad whose area is tiny has
        # near-zero tri normals - the up/down classification becomes a
        # coin flip and the contact solver spikes on the sliver. Emit
        # the proven crossed-diagonal pair instead of guessing.
        if qlen < 0.02:
            cage.add_triangle(a, b, c, ground_model=ground_model)
            cage.add_triangle(a, c, d, ground_model=ground_model)
            cage.add_triangle(d, c, b, ground_model=ground_model)
            cage.add_triangle(d, b, a, ground_model=ground_model)
            return
        if abs(qn[2]) / qlen < 0.35:
            # Near-vertical (wall) quad: projected-z winding is
            # meaningless. Walls here are planar - the proven crossed-
            # diagonal b76 idiom is exact for them and has no twins.
            cage.add_triangle(a, b, c, ground_model=ground_model)
            cage.add_triangle(a, c, d, ground_model=ground_model)
            cage.add_triangle(d, c, b, ground_model=ground_model)
            cage.add_triangle(d, b, a, ground_model=ground_model)
            return
        if (za + zc) >= (zb + zd):
            up_tris = ((a, b, c), (a, c, d))
            down_tris = ((b, c, d), (b, d, a))
        else:
            up_tris = ((b, c, d), (b, d, a))
            down_tris = ((a, b, c), (a, c, d))
        for t in up_tris:
            cage.add_triangle(*wind_up(*t), ground_model=ground_model)
        for t in down_tris:
            cage.add_triangle(*wind_down(*t), ground_model=ground_model)

    # Cone floor: 4 radial rings x 14 azimuths, quads (asphalt).
    def cone_z(radius: float) -> float:
        frac = (radius - spec.CONE_INNER_R) / (spec.CONE_OUTER_R - spec.CONE_INNER_R)
        return spec.CONE_INNER_Z + frac * (spec.CONE_OUTER_Z - spec.CONE_INNER_Z)

    # Outer ring sits ON the visual lip. It used to be 16.0 - 0.8 m PAST
    # the lip - carrying the cone slope out to z 2.60 where the visual
    # ramp is at 2.48. That put an invisible 0.12-0.25 m ledge right
    # across the doorway, in the collision only, exactly where the entry
    # line crosses.
    # CIRCUMSCRIBE THE COLLISION RINGS (2026-08-10, player: "always
    # popping a tire even at the lowest RPM when crossing the closed
    # entrance"). The dish and bank cage rings are 28-gons INSCRIBED in
    # their nominal radius, so between node columns the chord cuts
    # 15.8*(1-cos(6.43deg)) = 10 cm inside the circle. Sampling the
    # surface at a fixed cartesian radius therefore lands further DOWN
    # the ring interpolation at mid-chord than at a column: measured
    # 2.725 m at a column versus 2.662 m mid-chord at r 15.8, a 6.3 cm
    # scallop repeating every 12.86 deg, all the way round. The mouth
    # shelf is a fine mesh built at the TRUE bank height, so it lands on
    # the scallop's floor and every jamb crossing steps off a column onto
    # it - which is why the pop is speed-independent and why it shows at
    # the entrance, the one place a car crosses a surface boundary.
    #
    # Scaling the placement radius by sec(pi/n) while keeping z from the
    # TRUE radius makes the polygon CIRCUMSCRIBE instead: mid-chord now
    # sits exactly on the nominal radius and the scallop collapses.
    # Topology, azimuths, beams, quads and every downstream index are
    # untouched - it is a 0.63% outward nudge of the ring nodes only.
    # The bank reuses the cone's outer ring for its level 0, so both must
    # take the same correction or the bank foot gains the step the fix
    # was meant to remove.
    CAGE_SEC = 1.0 / math.cos(math.pi / 28)
    cone_radii = (2.0, 7.0, 11.5, spec.CONE_OUTER_R)
    cone_azimuths = 28
    cone: dict[tuple[int, int], str] = {}
    for ring_index, radius in enumerate(cone_radii):
        for az in range(cone_azimuths):
            a = math.radians(az * 360.0 / cone_azimuths)
            # NO collision spheres on ANY dish node (round 15 coda). The
            # history of this flag is a slow retreat: first the mouth
            # ring-3 nodes (invisible doorway pillars), then az 20-22 at
            # every ring (the r15d spin car popped both right tires on
            # the ring-2 az-21 sphere), and finally - b81 wreck-site
            # audit - the WHOLE dish: the spin sample wedged immovably
            # against the az-23 rim sphere flanked by two bank spheres,
            # and the player's wagon beached on bank spheres at other
            # azimuths. The entire dish is driveable, so every sphere is
            # an invisible boulder waiting for a line that crosses it.
            # The quads carry the surface; the prop is fully fixed, so
            # spheres add nothing structural. Rule: a node a WHEEL can
            # reach never collides.
            cone[(ring_index, az)] = cage.add_node(
                f"cone_{ring_index}_{az:02d}",
                (math.cos(a) * radius * CAGE_SEC,
                 math.sin(a) * radius * CAGE_SEC,
                 cone_z(radius)),
                fixed=True,
                collision=False,
                weight=140.0,
            )
    for ring_index in range(len(cone_radii)):
        for az in range(cone_azimuths):
            nxt = (az + 1) % cone_azimuths
            cage.add_beam(cone[(ring_index, az)], cone[(ring_index, nxt)])
            if ring_index > 0:
                cage.add_beam(cone[(ring_index - 1, az)], cone[(ring_index, az)])
                # ONE surface, ONE authority (round 15 coda, b81 sweep
                # defect 2): the outermost-ring dish cells under the arc
                # tongue are NOT built - the tongue (now extended inward
                # to ring 2) is the sole driveable sheet in the mouth
                # sector. Leaving the dish there stacked two double-
                # sided sheets 0.3-4.3 cm apart across the whole mouth
                # footprint - the W-canyon tire-popping class. Beams
                # stay (graph connectivity); only the quads go.
                if (ring_index == len(cone_radii) - 1
                        and az in spec.GARAGE_SEGMENTS):
                    continue
                cone_quad = [
                    cone[(ring_index - 1, az)],
                    cone[(ring_index, az)],
                    cone[(ring_index, nxt)],
                    cone[(ring_index - 1, nxt)],
                ]
                # BOTH windings: a single-wound quad collides from one side
                # only, and the functional gate proved cars drive straight
                # through the cone from above (2026-08-05).
                add_quad_both(cone_quad, "asphalt")
    for az in range(cone_azimuths):
        angle = math.radians(az * 360.0 / cone_azimuths)
        cage.add_beam(cone[(0, az)], nearest_plate(0.0, 0.0))
        cage.add_beam(
            cone[(3, az)],
            nearest_plate(math.cos(angle) * 16.0, math.sin(angle) * 16.0),
        )

    # HUB PLINTH (round 15 coda, player screenshot: car beached nose-up
    # on the pedestal flank, wheels lifted, couldn't reverse off). The
    # cage had NOTHING here: the cone floor's innermost ring is r 2.0 (a
    # 4 m collision HOLE dead centre) and the pedestal/rotor visuals
    # carry no cage at all - whatever a car climbed was part-TSStatic
    # baked collision the cage never fenced. Fix is a proper plinth: a
    # vertical bumper ring at r 4.6 (outside the dome, fins and
    # bedplate, so a car meets one clean wall face and backs away - no
    # climbable flank) capped with a solid disc at the pedestal top,
    # which also closes the r<2 hole for anything dropped from above.
    # A wall at r 4.6 does NOT violate the wall-in-orbit law: drag
    # orbits live at r 14..16 (hold_radius 15.9); only deliberate
    # driving visits the hub.
    plinth_r = 4.6
    plinth_top = 2.75
    plinth_segments = 16
    plinth_centre = cage.add_node(
        "plinth_c", (0.0, 0.0, plinth_top),
        fixed=True, collision=False, weight=160.0,
    )
    cage.add_beam(plinth_centre, nearest_plate(0.0, 0.0))
    plinth: dict[tuple[int, int], str] = {}
    for k in range(plinth_segments):
        a = math.radians(k * 360.0 / plinth_segments)
        px = math.cos(a) * plinth_r
        py = math.sin(a) * plinth_r
        pz0 = cone_z(plinth_r) - 0.05
        plinth[(k, 0)] = cage.add_node(
            f"plinth_{k}_0", (px, py, pz0),
            fixed=True, collision=False, weight=120.0,
        )
        plinth[(k, 1)] = cage.add_node(
            f"plinth_{k}_1", (px, py, plinth_top),
            fixed=True, collision=False, weight=120.0,
        )
        cage.add_beam(plinth[(k, 0)], plinth[(k, 1)])
        cage.add_beam(plinth[(k, 0)], nearest_plate(px, py))
        cage.add_beam(plinth[(k, 1)], plinth_centre)
    for k in range(plinth_segments):
        nxt = (k + 1) % plinth_segments
        cage.add_beam(plinth[(k, 0)], plinth[(nxt, 0)])
        cage.add_beam(plinth[(k, 1)], plinth[(nxt, 1)])
        wall_quad = [plinth[(k, 0)], plinth[(nxt, 0)],
                     plinth[(nxt, 1)], plinth[(k, 1)]]
        add_quad_both(wall_quad, "metal")
        # Single UP winding only (round 15 coda law: NEVER emit the same
        # node triple in both windings - exact twins spike the contact
        # solver and pop tires; the b85 entry regression). The space
        # under the cap is sealed by the plinth ring, so nothing can
        # ever touch it from below.
        cage.add_triangle(plinth[(k, 1)], plinth[(nxt, 1)], plinth_centre,
                          ground_model="metal")

    # PERIMETER SKIRT (2026-08-05 functional gate): the cone floor is a
    # RAISED dish (z 0.5..2.6) over the ground plate, so without this wall
    # a car simply drives into the void underneath from any azimuth - the
    # probe cruised "inside the bowl" at z 0.3 the whole time. The skirt
    # drops the cone's outer edge to grade, leaving only the vomitory
    # tunnel as a way in.
    skirt: dict[tuple[int, int], str] = {}
    skirt_azimuths = 28
    for az in range(skirt_azimuths):
        a = math.radians(az * 360.0 / skirt_azimuths)
        # No spheres on the skirt base ring either (round 15 coda,
        # b81 wheel-reach rule): these sit at grade where plaza traffic
        # rolls past the drum. Previously only the mouth columns were
        # exempt (the invisible-doorway-pillar incident).
        skirt[(az, 0)] = cage.add_node(
            f"skirt_{az:02d}_0",
            (math.cos(a) * spec.CONE_OUTER_R, math.sin(a) * spec.CONE_OUTER_R, 0.0),
            fixed=True,
            collision=False,
            weight=120.0,
        )
        # Skirt level 1 IS the cone rim ring. Building a second ring at
        # (15.2, 2.48) left 28 node pairs EXACTLY coincident with
        # cone[(3, az)] - and the FLEXBODY binds visual vertices to local
        # node triads, so every deck vertex nearer the rim than the 11.5
        # ring could pick a triad containing two coincident nodes: a
        # degenerate basis that collapsed its triangles. That is the
        # player's see-through outer deck ring (r ~13.4..15.2, the
        # midpoint boundary matches), present since the skirt landed
        # 2026-08-05 and invisible to every mesh-level probe - the same
        # DAE spawned as a plain TSStatic rendered perfectly.
        skirt[(az, 1)] = cone[(len(cone_radii) - 1, az)]
    for az in range(skirt_azimuths):
        nxt = (az + 1) % skirt_azimuths
        # Beams ALWAYS (every node must stay reachable in the cage graph);
        # only the collision quads drop at the tunnel mouth so cars can
        # drive in through the -Y segments. Level-1 hoop beams are NOT
        # re-added: they are the cone rim's own hoop, already built.
        cage.add_beam(skirt[(az, 0)], skirt[(az, 1)])
        cage.add_beam(skirt[(az, 0)], skirt[(nxt, 0)])
        # Mouth azimuths must match the vomitory (authored -Y = az 20/21
        # on the 28-segment ring), not an eyeballed index.
        if az in spec.GARAGE_SEGMENTS:
            continue
        quad = [skirt[(az, 0)], skirt[(nxt, 0)], skirt[(nxt, 1)], skirt[(az, 1)]]
        add_quad_both(quad, "metal")
    for az in range(skirt_azimuths):
        a = math.radians(az * 360.0 / skirt_azimuths)
        cage.add_beam(
            skirt[(az, 0)],
            nearest_plate(math.cos(a) * spec.CONE_OUTER_R, math.sin(a) * spec.CONE_OUTER_R),
        )

    # Velodrome bank + inward curl: profile levels x 28 segments.
    levels = (*spec.BANK_PROFILE, (18.4, 8.8))
    columns: dict[int, dict[int, str]] = {}
    count = spec.WALL_SEGMENTS
    # FLANK FAIRING (round 15 coda - the critic's b81 conviction). The
    # bank cut's side faces stood as a 22 cm exposed step plus open
    # corner slots dropping to ground at r 16.0..16.8, ang 77/103 -
    # exactly the pocket the deleted guard walls used to fence, and
    # exactly where the b81 spin sample and the player's wagon wedged.
    # No face can stand there (the drag orbit sweeps r up to ~16.8), so
    # the CUT-EDGE COLUMNS themselves are pulled down toward the mouth
    # deck: the two bank segments flanking the cut become smooth ramps
    # from full bank height down to deck level at the doorway - the
    # velodrome-transition shape - and the corner lids below stitch the
    # remaining wedge to the corridor rails. Collision dips under the
    # visual bank near the cut (cars sink visually a little riding the
    # fairing); that beats wedging forever.
    fair_cols = (min(spec.GARAGE_SEGMENTS), max(spec.GARAGE_SEGMENTS) + 1)
    # CAMBER-PRESERVING fairing (the b92 frame-by-frame autopsy). The
    # 0.05 foot keep FLATTENED the bank foot through the gap - an
    # orbiting car arrives ROLLED onto the 38% foot band and its roll
    # snapped level in 0.3 s at the cut: load flipped to the outside
    # wheels (RR 6615 / RL 835 in one tick), snap-oversteer spin, tire
    # popped in the slide, and the spinning wreck's corner caught on
    # the cut-edge strip - pinned by the field at 10 kN forever. Foot
    # keep 0.55 preserves most of the camber through the crossing (a
    # 9 cm oblique step instead of a camber cliff); upper levels stay
    # faired so no wall stands for chord-flyers. The higher foot also
    # gives the inner lid links real extent again (no b87 slivers), so
    # they return below and bury the catch-strip.
    # Keep factors + deck datum are shared spec constants (build 95):
    # the visual bank's faired sheet and the mouth-shelf part sample the
    # SAME numbers, which is what makes all three surfaces one swale.
    fair_keep = spec.FAIR_KEEP
    deck_ref = max(ramp_surface_z(0.0, -15.2), 0.08)
    assert abs(deck_ref - spec.FAIR_DECK_Z) < 0.002, (
        f"fairing deck datum drifted: blend {deck_ref:.4f} vs "
        f"spec.FAIR_DECK_Z {spec.FAIR_DECK_Z:.4f} - the shelf and visual "
        "fairing would no longer be flush with the cage"
    )
    deck_ref = spec.FAIR_DECK_Z
    for index in range(count):
        a = math.radians(index * 360.0 / count)
        columns[index] = {}
        for level, (radius, z) in enumerate(levels):
            if index in fair_cols and level in fair_keep:
                z = deck_ref + (z - deck_ref) * fair_keep[level]
            if level == 0:
                # Bank level 0 IS the cone rim ring now that the cone ends
                # at the lip: same radius, same height, same azimuths.
                # Building a second ring there would leave 28 coincident
                # node pairs and zero-length stitch beams.
                columns[index][0] = cone[(len(cone_radii) - 1, index)]
                continue
            # NO collision spheres on the bank (round 15 coda - THE b81
            # wreck-site conviction). wall_22_1 and wall_23_1 spheres at
            # z 2.67 sat proud of the bank incline 1.6 m apart and the
            # spin sample wedged between them at 30 RPM (ang 110, one
            # tire ground off while the drum climbed to 331); the
            # player's wagon beached the same way mid-bank elsewhere.
            # Every bank level is wheel-reachable on a velodrome - the
            # quads are the surface, spheres are invisible boulders.
            # Same sec(pi/n) circumscription as the cone rings above -
            # see the CAGE_SEC note; the bank foot is where the scallop
            # actually bites, because that is the radius the field holds
            # a circulating sample at.
            sec = 1.0 / math.cos(math.pi / count)
            # Doorway arch (spec.door_arch): lifts the lintel over the
            # mouth so a truck fits under it WITHOUT putting a hole in
            # the banked wall. COLLISION-ONLY by construction - the arch
            # window ends inside the visual cut sector, so the visual
            # bank (which samples the same function via _fair_z) gets
            # zero at every visible vertex, and the mouth shelf stays
            # deliberately unarched (seamless closure).
            z = z + spec.door_arch(index * 360.0 / count, radius)
            columns[index][level] = cage.add_node(
                f"wall_{index:02d}_{level}",
                (math.cos(a) * radius * sec, math.sin(a) * radius * sec, z),
                fixed=True,
                collision=False,
                weight=150.0,
            )
    for index in range(count):
        column = columns[index]
        next_column = columns[(index + 1) % count]
        for level in range(len(levels)):
            # level 0 aliases the cone rim ring, whose hoop beams the cone
            # loop already added - re-adding them would duplicate.
            if level > 0 and not (level < 5 and index in spec.GARAGE_SEGMENTS):
                cage.add_beam(column[level], next_column[level])
            if level < len(levels) - 1:
                cage.add_beam(column[level], column[level + 1])
        for level in range(len(levels) - 1):
            # Doorway cut depth is spec.DOOR_CUT_LEVELS (7 since the
            # 2026-08-11 headroom round; it was a bare 5, which left an
            # invisible lintel at z 4.877 that stopped anything taller
            # than a car). Only the QUADS go - the hoop beams above are
            # still added by the loop before this one, same as the cone's
            # "beams stay (graph connectivity); only the quads go".
            if level < spec.DOOR_CUT_LEVELS and index in spec.GARAGE_SEGMENTS:
                continue
            quad = [
                column[level],
                next_column[level],
                next_column[level + 1],
                column[level + 1],
            ]
            add_quad_both(quad, "metal")
    # No stitch loop: the bank's base ring and the cone's rim ring are now
    # the same nodes, so there is nothing left to join.

    # Vomitory tunnel ramp: concourse (y -23.3, z 0) up to the cone edge.
    tunnel: dict[tuple[int, int], str] = {}
    # Stations regraded 2026-08-05: the old ramp topped out at z 1.56
    # where it crossed r 16, i.e. UNDER the cone lip (z 2.6) - the probe
    # car jammed against the dish underside. It now crests exactly on the
    # lip at 18.6% grade and hands off to the cone ring.
    # Cage tunnel sampled from the SAME blended surface the visual ramp
    # uses, at the same x the cage rails sit on. Four hand-typed stations
    # with a hard corner at the lip could not represent the crest curve,
    # so the collision kept the 17.3 deg break the visual no longer has.
    # Sixteen stations to y -31.0 (was twelve to -30.0). The old first
    # station sat at y -30 where the surface is already 0.10 m up - with
    # NOTHING outboard of it, the collision began as an invisible 10 cm
    # wall standing 0.6 m inside the visual ramp toe. At crawl speed a
    # wheel stalls against exactly that (player 2026-08-08: "I sometimes
    # get hung up on the mesh... at slow speeds"). Station z is clamped to
    # the ground plate's 0.08 datum, so at the toe the lattice flattens
    # INTO the datum cars already ride: a zero-step onramp, and 1.16 m
    # spacing keeps every crest facet under 3 deg (breakover is ~11 deg).
    # Straight stations now START at y -16.125: the two innermost rows
    # (13.6, 14.86) are replaced by the constant-radius ARC TONGUE below
    # - a straight row sampling the radial blend warps ~20 cm from
    # centre to rail inside the mouth, which is what kept catching
    # creeping off-centre cars however smooth the formula got.
    tunnel_stations = tuple(
        (-(13.6 + (33.8 - 13.6) * k / 16.0), None) for k in range(2, 17)
    )
    # THREE rails, not two: a quad spanning the full 7 m chords straight
    # across the crest, so the centreline rounding the visual now has was
    # invisible to the physics.
    tunnel_x = (-3.5, 0.0, 3.5)
    toe_j = len(tunnel_stations) - 1
    for j, (ty, _tz) in enumerate(tunnel_stations):
        for i, tx in enumerate(tunnel_x):
            # Toe station feathers to 15 mm over raw terrain: without it,
            # clamping to the 0.08 datum just moves the plate edge's 8 cm
            # curb out to the entry lane's first contact line.
            z = 0.015 if j == toe_j else max(ramp_surface_z(tx, ty), 0.08)
            # collision=False (round 15 coda, b81 wheel-reach rule): the
            # corridor rails ARE the entry lane surface - every one of
            # these spheres sat in the driving line. Flat ground masked
            # them; the rule doesn't care.
            tunnel[(i, j)] = cage.add_node(
                f"tunnel_{i}_{j}",
                (tx, ty, z),
                fixed=True,
                collision=False,
                weight=150.0,
            )
    for j in range(len(tunnel_stations)):
        for i in range(len(tunnel_x) - 1):
            cage.add_beam(tunnel[(i, j)], tunnel[(i + 1, j)])
        if j > 0:
            for i in range(len(tunnel_x)):
                cage.add_beam(tunnel[(i, j - 1)], tunnel[(i, j)])
            for i in range(len(tunnel_x) - 1):
                tunnel_quad = [
                    tunnel[(i, j - 1)],
                    tunnel[(i + 1, j - 1)],
                    tunnel[(i + 1, j)],
                    tunnel[(i, j)],
                ]
                add_quad_both(tunnel_quad, "asphalt")
    # --- Arc tongue (round 15 finale: "wowed by the smooth transition").
    # Constant-RADIUS rows through the mouth: the blend surface is a pure
    # function of r, so every node in an arc row shares ONE z - zero
    # cross-lane warp by construction, at any x, at any speed. 0.4 m row
    # spacing keeps each facet's slope change under ~1.5 deg. The
    # outermost row stitches to the first straight station (y 16.125,
    # where the surface is gentle and straight rows are honest again);
    # the innermost rests on the cone it already matches to ~12 mm. No
    # node presents a collision sphere in the lane - quads only.
    # 15.25/15.65, NOT 15.2/15.6: a row at exactly the rim radius drops
    # its centre node onto cone_3_21 - the coincident-node assert (the
    # build-56 flexbody lesson) rejects the cage.
    # Rows now START at 11.6 (round 15 coda): with the mouth dish cells
    # removed (one authority - see the cone loop), the tongue must carry
    # the surface all the way in to ring 2 (r 11.5). Inboard of the
    # blend window the row height IS cone_z(r), so the new rows are
    # exactly coplanar with the dish they replace - zero step, zero
    # warp, by the same constant-radius construction.
    arc_rows = (11.6, 12.1, 12.6, 13.1,
                13.6, 14.0, 14.4, 14.8, 15.25, 15.65, 16.0)
    arc: dict[tuple[int, int], str] = {}
    for k, ar in enumerate(arc_rows):
        rz = max(ramp_surface_z(0.0, -ar), 0.08)
        for i, tx in enumerate(tunnel_x):
            ay = math.sqrt(max(ar * ar - tx * tx, 0.25))
            arc[(i, k)] = cage.add_node(
                f"arctongue_{i}_{k}", (tx, -ay, rz),
                fixed=True, collision=False, weight=140.0,
            )
        for i in range(len(tunnel_x) - 1):
            cage.add_beam(arc[(i, k)], arc[(i + 1, k)])
        if k > 0:
            for i in range(len(tunnel_x)):
                cage.add_beam(arc[(i, k - 1)], arc[(i, k)])
            for i in range(len(tunnel_x) - 1):
                arc_quad = [arc[(i, k - 1)], arc[(i + 1, k - 1)],
                            arc[(i + 1, k)], arc[(i, k)]]
                add_quad_both(arc_quad, "asphalt")
    for i in range(len(tunnel_x)):
        cage.add_beam(arc[(i, 0)], cone[(2, 21)])
        cage.add_beam(arc[(i, len(arc_rows) - 1)], tunnel[(i, 0)])
        cage.add_beam(arc[(i, 0)], nearest_plate(tunnel_x[i], -13.0))
    # Inner stitch: close the 10 cm annulus between ring 2 (r 11.5) and
    # the tongue's new innermost row (11.6) across the mouth cells whose
    # dish quads were removed above.
    inner_stitch = (
        [cone[(2, 20)], cone[(2, 21)], arc[(1, 0)], arc[(0, 0)]],
        [cone[(2, 21)], cone[(2, 22)], arc[(2, 0)], arc[(1, 0)]],
    )
    for quad in inner_stitch:
        add_quad_both(quad, "asphalt")
    for i in range(len(tunnel_x) - 1):
        stitch_quad = [arc[(i, len(arc_rows) - 1)],
                       arc[(i + 1, len(arc_rows) - 1)],
                       tunnel[(i + 1, 0)], tunnel[(i, 0)]]
        add_quad_both(stitch_quad, "asphalt")
    last_station = len(tunnel_stations) - 1
    cage.add_beam(tunnel[(0, last_station)], cone[(len(cone_radii) - 1, 20)])
    cage.add_beam(tunnel[(2, last_station)], cone[(len(cone_radii) - 1, 22)])
    cage.add_beam(tunnel[(1, last_station)], cone[(2, 21)])
    cage.add_beam(tunnel[(0, 0)], nearest_plate(-3.0, -30.0))
    cage.add_beam(tunnel[(2, 0)], nearest_plate(3.0, -30.0))

    # CORNER LIDS (round 15 coda, paired with the flank fairing above):
    # seal the wedge between the corridor rail line (x +-3.5) and the
    # faired cut-edge bank columns. Before this, the wedge was an OPEN
    # SLOT to the ground plane, 2.4-3.3 m deep, plus a 22 cm free step
    # where the tongue ended against the bank cut - the b81 wreck pit.
    # No new nodes: quads stitch EXISTING chains (tongue side columns +
    # corridor rails inboard, cone rim + faired wall columns outboard),
    # so the coincident-node assert has nothing new to trip on.
    for arc_i, tun_i, edge_col in ((0, 0, fair_cols[0]), (2, 2, fair_cols[1])):
        inner_chain = [arc[(arc_i, 8)], arc[(arc_i, 9)], arc[(arc_i, 10)],
                       tunnel[(tun_i, 0)], tunnel[(tun_i, 1)]]
        outer_chain = [cone[(len(cone_radii) - 1, edge_col)],
                       columns[edge_col][1], columns[edge_col][2],
                       columns[edge_col][3], columns[edge_col][4]]
        for k in range(len(inner_chain) - 1):
            cage.add_beam(inner_chain[k], outer_chain[k])
            # Inner links restored (b92 autopsy): with the camber-
            # preserving fairing the outer chain sits 9+ cm above the
            # tongue edge, so these quads have real extent (the b87
            # sliver instability came from near-equal chain heights,
            # cured by geometry, not by the b88 removal - which
            # re-opened the catch-strip the spinning wreck's corner
            # jammed into). The v2 emitter's degenerate guard still
            # protects if a future tweak collapses them again.
            lid_quad = [inner_chain[k], inner_chain[k + 1],
                        outer_chain[k + 1], outer_chain[k]]
            add_quad_both(lid_quad, "asphalt")
        cage.add_beam(inner_chain[-1], outer_chain[-1])

    # Corridor shoulders: collision for everything a wheel can reach beside
    # the 7 m lane, over the WHOLE run. It used to stop at station 4
    # (y -19.6) while the visual shoulder ran to -29.8: a wheel out there
    # sank through the visual floor, then slammed the shoulder quads' end
    # edge - the second slow-speed trap. Inside the portal the shoulders
    # reach 0.45 m past the flank-wall plane (buried); outside they follow
    # the plaza funnel to its edges. Nodes are collision-off (a sphere at
    # the jamb line is an invisible pillar in the doorway - the exact trap
    # removed in an earlier round); the QUADS still collide.
    shoulder: dict[tuple[int, int], str] = {}
    shoulder_stations = tuple(range(1, len(tunnel_stations)))
    for j in shoulder_stations:
        ty = tunnel_stations[j][0]
        if abs(ty) > 23.65:
            xo = plaza_half_w(ty) - 0.10
        else:
            xo = corridor_wall_x(ty) + 0.45
        for i, side in enumerate((-1.0, 1.0)):
            sz = (0.012 if j == len(tunnel_stations) - 1
                  else max(ramp_surface_z(side * xo, ty) - 0.008, 0.072))
            shoulder[(i, j)] = cage.add_node(
                f"shoulder_{i}_{j}",
                (side * xo, ty, sz),
                fixed=True,
                collision=False,
                weight=120.0,
            )
    for i, rail in enumerate((0, 2)):
        for j in shoulder_stations:
            cage.add_beam(shoulder[(i, j)], tunnel[(rail, j)])
            if j > shoulder_stations[0]:
                cage.add_beam(shoulder[(i, j - 1)], shoulder[(i, j)])
                quad = [
                    tunnel[(rail, j - 1)],
                    tunnel[(rail, j)],
                    shoulder[(i, j)],
                    shoulder[(i, j - 1)],
                ]
                add_quad_both(quad, "asphalt")

    # GUTTER CAPS (b83 sweep defect 3): the lens-shaped void between the
    # corner lid's outer end (faired wall col 4, r 17.35), the shoulder
    # strip start (r 17.96) and the corridor floor was a 0.43 m wheel-
    # wide slot dropping 2.3 m to the plate - or clean through the prop
    # where the plate has no sector. One triangle per jamb closes it,
    # ~30 deg now that the fairing tops out near deck. (Lives after the
    # shoulder block because it stitches shoulder nodes.)
    for sh_i, tun_i, edge_col in ((0, 0, fair_cols[0]), (1, 2, fair_cols[1])):
        cap = (columns[edge_col][4], shoulder[(sh_i, 1)],
               tunnel[(tun_i, 1)])
        cage.add_beam(columns[edge_col][4], shoulder[(sh_i, 1)])
        # Single winding, up-facing (no-exact-twins law): orient by the
        # computed normal so the rideable side faces the sky; the slot
        # below is sealed.
        p1, p2, p3 = (next(n["position"] for n in cage.nodes
                           if n["id"] == t) for t in cap)
        nz = ((p2[0] - p1[0]) * (p3[1] - p1[1])
              - (p2[1] - p1[1]) * (p3[0] - p1[0]))
        wound = cap if nz >= 0 else tuple(reversed(cap))
        cage.add_triangle(*wound, ground_model="asphalt")

    # Corridor wall collision on the corridor_wall_x plane: a car angling
    # into the reveals scrubs steel instead of phasing through the visual
    # into the service cavity. Nodes collision-off for the same doorway-
    # pillar reason; both windings so the wall works from either side.
    wall: dict[tuple[int, int, int], str] = {}
    wall_js = [
        j for j in shoulder_stations
        if 16.4 <= abs(tunnel_stations[j][0]) <= 23.7
    ]
    # Crest CLAMP (round 15 coda, b81 sweep defect 5): the flat +2.6 m
    # crest put cwall_x_1_1 at z 4.96 - 12.5 cm ABOVE the local bank
    # surface (z 4.835 at r 17.9) - so the zero-thickness wall sheet
    # crossed the bank riding face as an across-travel blade at the top
    # of the multi-g contact band: the wagon-stuck-on-the-bank
    # screenshot. Every crest node now stays >= 0.15 m UNDER the local
    # bank surface wherever the panel stands inside the bank's radial
    # span, so the wall never pierces the face a car rides.
    def bank_z_at(radius: float) -> float:
        # Monotonic-radius prefix only: the appended curl entry bends
        # back INWARD (18.4, 8.8) and would corrupt interpolation.
        pts = [levels[0]]
        for lv in levels[1:]:
            if lv[0] > pts[-1][0]:
                pts.append(lv)
        if radius <= pts[0][0]:
            return pts[0][1]
        for (r0, z0), (r1, z1) in zip(pts, pts[1:]):
            if radius <= r1:
                t = (radius - r0) / max(r1 - r0, 1e-9)
                return z0 + (z1 - z0) * t
        return pts[-1][1]

    bank_span_r = max(r for r, _ in levels)

    for j in wall_js:
        ty = tunnel_stations[j][0]
        wx = corridor_wall_x(ty)
        for i, side in enumerate((-1.0, 1.0)):
            zb = max(ramp_surface_z(side * wx, ty) - 0.02, 0.06)
            node_r = math.hypot(wx, ty)
            zt = zb + 2.6
            if node_r <= bank_span_r:
                zt = min(zt, bank_z_at(node_r) - 0.15)
            zt = max(zt, zb + 1.2)
            wall[(i, j, 0)] = cage.add_node(
                f"cwall_{i}_{j}_0", (side * wx, ty, zb),
                fixed=True, collision=False, weight=90.0,
            )
            wall[(i, j, 1)] = cage.add_node(
                f"cwall_{i}_{j}_1", (side * wx, ty, zt),
                fixed=True, collision=False, weight=90.0,
            )
            cage.add_beam(wall[(i, j, 0)], wall[(i, j, 1)])
            cage.add_beam(wall[(i, j, 0)], tunnel[(0 if side < 0 else 2, j)])
            cage.add_beam(wall[(i, j, 1)], tunnel[(1, j)])
    for i in range(2):
        for a, b in zip(wall_js, wall_js[1:]):
            for level in (0, 1):
                cage.add_beam(wall[(i, a, level)], wall[(i, b, level)])
            quad = [wall[(i, a, 0)], wall[(i, b, 0)],
                    wall[(i, b, 1)], wall[(i, a, 1)]]
            add_quad_both(quad, "metal")

    # NO doorway throat guards (round 15 coda). They lived here for two
    # builds: vertical panes on the jamb planes spanning z 2.4..5.3 at
    # r 15.2..16.8, plus 45-degree corner wedges at r 15.2. The b78
    # analytic mouth audit + spin watch convicted them as THE
    # dragged-sample killer the player kept reporting: a car circulating
    # at the ~15.2 m hold line broadsided a pane every doorway pass (all
    # four tires gone by t=10 s at 30 RPM, launched 9 m). No winding
    # fixes a wall that stands inside the orbit - one-way panes just
    # pick which lap direction dies, and once a car crosses the jamb
    # plane inward, the "safe" side is a head-on wall on the way out.
    # And their reason to exist was a phantom: the audit shows the cone
    # deck's quads span the whole mouth sector at every radius (the
    # swept-arc profiles are hole-free and step-free), so the skirt
    # boundary "knife blades" top out AT deck height, buried under the
    # continuous floor seam where no tire on the surface can reach them.
    # The 13-line entry gauntlet (including both scrape lines that hug
    # the jambs) passes without them; the Lua doorway bridge tightens
    # the hold line to 14.6 through the mouth sector for extra margin.
    # If a future round is tempted to put ANY vertical collision inside
    # r 17 near the mouth: don't. Floors and slopes only.
    #
    # (Earlier round-15 post-mortem, kept for the record: a "shrail"
    # outer-rail strip also briefly lived here on the theory that the
    # shoulder had no floor collision. It did - the legacy `shoulder_i_j`
    # strip covers wall to wall - and the duplicate interleaved with it
    # into a W-shaped canyon that itself popped tires. One surface, one
    # authority.)

    # Interactive panel anchors (console on the concourse).
    panel_nodes: dict[str, str] = {}
    for button in spec.PANEL_BUTTONS:
        # 9 cm proud of the plate (round 15): anchored AT the cap the
        # click boxes sat behind the console collision plane, so the
        # mouse ray hit the cage first and hover never fired. Proud
        # anchors + the pulled-back cage front put the whole box in
        # free air in front of the glass.
        anchor = (button["position"][0], button["position"][1] - 0.09,
                  button["position"][2])
        panel_nodes[button["id"]] = cage.add_node(
            f"panelbtn_{button['id']}",
            anchor,
            fixed=True,
            collision=False,
            weight=20.0,
        )
        # Per-button orthonormal frame (round 15, player: "button
        # locations are somewhat off in mouse over"): the trigger basis
        # is (idX-idRef, idY-idRef), so the old shared frame pair gave
        # every off-row button a skewed, translated hitbox.
        for tag, off in (("fx", (0.4, 0.0, 0.0)), ("fy", (0.0, 0.0, 0.4))):
            frame_id = cage.add_node(
                f"panel{tag}_{button['id']}",
                (anchor[0] + off[0], anchor[1] + off[1], anchor[2] + off[2]),
                fixed=True,
                collision=False,
                weight=20.0,
            )
            cage.add_beam(frame_id, nearest_plate(24.0, 0.0))
    frame_x_node = cage.add_node(
        "panel_frame_x", spec.PANEL_FRAME_X, fixed=True, collision=False, weight=20.0
    )
    frame_y_node = cage.add_node(
        "panel_frame_y", spec.PANEL_FRAME_Y, fixed=True, collision=False, weight=20.0
    )
    for identifier in [*panel_nodes.values(), frame_x_node, frame_y_node]:
        cage.add_beam(identifier, nearest_plate(24.0, 0.0))

    # Console collision box, hugging the round-14 pedestal (the old fridge
    # was 2.6 x 3.4 x 2.1 - leaving that cage would wrap the new cabinet
    # in an invisible oversize box).
    console: dict[tuple[int, int, int], str] = {}
    # Front face at -0.62, NOT -0.9 (round 15): the legend plate sits at
    # y -0.73 and the caps at ~-0.76, so a -0.9 cage face stood 15 cm
    # proud of the buttons and swallowed the trigger raycast.
    for ix, cx in enumerate((20.35, 22.85)):
        for iy, cy in enumerate((-0.62, 0.9)):
            for iz, cz in enumerate((0.0, 2.15)):
                console[(ix, iy, iz)] = cage.add_node(
                    f"console_{ix}_{iy}_{iz}",
                    (cx, cy, cz),
                    fixed=True,
                    collision=True,
                    weight=120.0,
                )
    for ix in (0, 1):
        for iy in (0, 1):
            cage.add_beam(console[(ix, iy, 0)], console[(ix, iy, 1)])
            cage.add_beam(console[(ix, iy, 0)], nearest_plate(21.6, 0.0))
    cage.add_quad(
        [
            console[(0, 0, 0)],
            console[(1, 0, 0)],
            console[(1, 1, 0)],
            console[(0, 1, 0)],
        ],
        ground_model="metal",
    )
    # Top face double-sided via the v2 emitter - the old hand-rolled
    # second copy was the same diagonal reversed = EXACT TWINS (the
    # no-exact-twins law; harmless only because nothing ever drove on
    # the cabinet).
    add_quad_both(
        [console[(0, 0, 1)], console[(1, 0, 1)],
         console[(1, 1, 1)], console[(0, 1, 1)]],
        "metal",
    )

    cage.set_refnodes_existing(
        ref=plate[(1, 1, 0)],
        back=plate[(1, 0, 0)],
        left=plate[(0, 1, 0)],
        up=plate[(1, 1, 1)],
    )
    # Spawn envelope corners moved OFF driveable surfaces (round 15
    # coda): set_spawn_envelope FORCES collision=True on its 8 nodes -
    # the old corners (corridor crest rails + bank-face level 4) were
    # the last invisible spheres in the swept band, including one dead
    # centre over the doorway. Buried plate corners + the curl ring
    # (r 18.4, z 8.8, beyond any tire) span the same footprint.
    cage.set_spawn_envelope(
        [
            plate[(0, 0, 0)],
            plate[(2, 0, 0)],
            plate[(0, 2, 0)],
            plate[(2, 2, 0)],
            columns[0][len(levels) - 1],
            columns[7][len(levels) - 1],
            columns[14][len(levels) - 1],
            columns[21][len(levels) - 1],
        ]
    )
    cage.auto_base_nodes()
    # No two cage nodes may coincide. The flexbody skins visual vertices
    # to local node triads; a triad containing two coincident nodes is a
    # degenerate basis and the bound vertices collapse - the skirt's
    # duplicate rim ring made the whole outer deck band (r ~13.4..15.2)
    # invisible in game while every mesh-level probe passed.
    positions = [(n["id"], n["position"]) for n in cage.nodes]
    cell: dict[tuple[int, int, int], list[tuple[str, list[float]]]] = {}
    for identifier, p in positions:
        key = (int(p[0] * 10), int(p[1] * 10), int(p[2] * 10))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other_id, q in cell.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        d2 = sum((a - b) ** 2 for a, b in zip(p, q))
                        assert d2 > 0.01 ** 2, (
                            f"coincident cage nodes: {identifier} and {other_id} at {p}"
                        )
        cell.setdefault(key, []).append((identifier, p))
    return cage


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

    visual = bk.export_flexbody_visual(
        MOD_ID,
        VEHICLE_DIR / f"{MOD_ID}.dae",
        visual_objects,
        f"{MOD_ID}_visual",
    )

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
        parts=parts,
        palette=spec.PALETTE,
        panel={
            "frame_x_node": f"{MOD_ID}_panel_frame_x",
            "frame_y_node": f"{MOD_ID}_panel_frame_y",
            "button_size": 0.12,
            # Per-button FRAME nodes (2026-08-09e, player: hover box
            # misaligned with the modeled button): the cage has built
            # panelfx_/panelfy_ nodes per button since round 15, but the
            # handoff never linked them - prop_builder fell back to the
            # shared frame pair, whose (idX-idRef, idY-idRef) basis skews
            # and translates every box not co-located with it. Per-button
            # SIZES match the cap diameters (mushrooms are twice the blue
            # caps; one 0.12 box fit neither).
            "buttons": [
                {"id": button["id"], "title": button["title"],
                 "node": f"{MOD_ID}_panelbtn_{button['id']}",
                 "frame_x_node": f"{MOD_ID}_panelfx_{button['id']}",
                 "frame_y_node": f"{MOD_ID}_panelfy_{button['id']}",
                 "size": {"round_green": 0.16, "round_blue": 0.14,
                          "round_white": 0.14, "round_small": 0.11,
                          "estop": 0.24, "purge": 0.21}[
                              button.get("cap", "round_blue")]}
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
    # Selector thumbnail, reframed 2026-08-10 (player: "zoom out enough to
    # capture the entire structure as seen from the entrance").
    # The old (22, -26, 14) stood 34 m from a 55 m wide building and
    # off-axis, so the frame was a corner of facade with the entrance out
    # of shot. The entrance faces authored -Y (louver_facade.ENTRY_DEG
    # 270), so the shot is down that axis.
    # Framing maths, at the default 50 mm on a 36 mm sensor (39.6 deg
    # horizontal) and the 500x281 output: the structure spans ~55 m across
    # the fin ring (r 24.28) and canopy (r 27.35). Fitting 66 m of width
    # with margin needs 33 / tan(19.8 deg) = 92 m of standoff. Vertical
    # FOV is 22.9 deg, which covers 37 m at that range - ample for a
    # ~14 m tall building, so the height budget is spent on standing the
    # camera at z 18 for enough elevation to read the roof form rather
    # than a flat elevation.
    # Standoff set by MEASURING the first render rather than trusting the
    # lens maths: at 92 m the building filled 58% of the frame width, so
    # 92 * 58/85 = 63 m puts it at ~85% - full structure, no dead margin.
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(0.0, -63.0, 13.0),
        look_at=(0.0, 0.0, 4.5),
    )
    print(f"GFORCE_CENTRIFUGE generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
