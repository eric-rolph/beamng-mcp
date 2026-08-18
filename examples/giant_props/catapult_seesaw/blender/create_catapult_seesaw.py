"""Deterministic Blender generator for Charlie's Catapult Seesaw.

2026-08-13 Acme redesign: the prop now reads as a cartoon Acme contraption
built with real engineering language. Riveted lattice-derrick gantry in
worn Acme red with a crown sheave, deflection sheave and hand-crank winch
on a continuous cable run; a cast-iron inverted-frustum "10 TON" weight
with raised painted lettering and a genuinely interlinked shackle-and-hook;
a plank of four individual cathedral-grain boards (two texture seeds,
staggered grain phase, +-6 mm lay jitter) with steel end banding, red
under-stringers and a painted bullseye; a plate-leg trestle fulcrum with
pillow blocks and an engraved ACME patent plate; hazard edge stripes and
painted chevrons on the entry ramp.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/catapult_seesaw/blender/create_catapult_seesaw.py
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
from mathutils import Matrix, Vector  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"
# Version 1 cached this path as a static-only shape. Keep the physical
# multi-flexbody export on a new filename so BeamNG cannot reuse that old
# .cdae when subscribers update without clearing their cache.
PHYSICS_VISUAL_DAE_NAME = f"{MOD_ID}_physics_v3.dae"

CAR_END_Y = spec.PLANK_CAR_END_Y
WEIGHT_END_Y = spec.PLANK_WEIGHT_END_Y
BACKSTOP_Y = WEIGHT_END_Y + 0.20
PLANK_LENGTH = spec.PLANK_LENGTH
PLANK_CENTER_Y = spec.PLANK_CENTER_Y
HW = spec.PLANK_HALF_WIDTH
THICK = spec.PLANK_THICKNESS
PIVOT_Z = spec.PIVOT_Z
REST = math.radians(spec.REST_ANGLE_DEG)
FLING_STOP = math.radians(spec.FLING_STOP_ANGLE_DEG)
GY = spec.GANTRY_Y
IMPACT_Y = spec.PLANK_IMPACT_STATION_Y
PARK_Y = spec.PLANK_PARK_STATION_Y
GTZ = spec.GANTRY_TOP_Z
LATCH_Z = spec.WEIGHT_REST_CENTER_Z + 1.93

# Battered chords: each gantry side is a laced two-chord column, wide at
# the shoe and closing toward the beam - the derrick silhouette.
CHORD_X = 2.8
CHORD_SPREAD_BASE = 0.85
CHORD_SPREAD_TOP = 0.18
CHORD_SECTION = 0.26

# Rope radius, shared by every cable leg and by both sheave grooves, so
# a leg aimed at "groove radius" really does land in the groove.
CABLE_R = 0.04
CROWN_Z = GTZ - 0.48

# Tessellation tiers. A cylinder's segment count IS its roundness: shading
# can smooth a surface but it cannot smooth a SILHOUETTE, and every round
# part on this prop is something the player parks next to (play-test
# 2026-08-13 round 12, "use way more triangles to make a smooth cylinder").
# Hex hardware stays at 6 deliberately - those are nuts, not circles - and
# the weight's frustum stays at 4.
SEG_LARGE = 64  # drums, sheaves, the pivot tube, spool flanges
SEG_SMALL = 32  # axles, pins, hook stems, grips
SEG_ROPE = 20  # cable legs
TORUS_MAJOR = 48  # shackles, hook bows, collar straps, wound coils
TORUS_MINOR = 16
RIVET_SEG, RIVET_RING = 14, 8
# Winch drum centre and the radius of the wound coil pack on it - the
# drop cable lands on the COILS, so both places share these numbers.
WINCH_X, WINCH_Z = 2.8, 1.85
WINCH_COIL_R = 0.31

HEAVY_FONT = r"C:\Windows\Fonts\ariblk.ttf"

_FONT_CACHE: dict[str, bpy.types.VectorFont] = {}


def _font(path: str) -> bpy.types.VectorFont:
    if path not in _FONT_CACHE:
        _FONT_CACHE[path] = bpy.data.fonts.load(path)
    return _FONT_CACHE[path]


def plank_surface_z(y: float) -> float:
    """Rest-tilt top surface height at plank-local y (authored frame)."""

    return PIVOT_Z + THICK / 2 * math.cos(REST) + y * math.sin(REST)


def plank_point(x: float, y: float, normal_offset: float = 0.0) -> tuple[float, float, float]:
    """A point on the physical plank after its authored rest rotation."""

    return (
        x,
        y * math.cos(REST) - normal_offset * math.sin(REST),
        PIVOT_Z + y * math.sin(REST) + normal_offset * math.cos(REST),
    )


def plank_point_at_angle(
    x: float,
    y: float,
    normal_offset: float,
    angle: float,
) -> tuple[float, float, float]:
    """A physical plank point at an arbitrary hinge angle."""

    return (
        x,
        y * math.cos(angle) - normal_offset * math.sin(angle),
        PIVOT_Z + y * math.sin(angle) + normal_offset * math.cos(angle),
    )


def rotate_about_plank_axle(objects: list[bpy.types.Object]) -> None:
    """Bake the plank's rest pose into its node-bound flexbody mesh."""

    pivot = Vector((0.0, 0.0, PIVOT_Z))
    transform = (
        Matrix.Translation(pivot) @ Matrix.Rotation(REST, 4, "X") @ Matrix.Translation(-pivot)
    )
    for obj in objects:
        obj.matrix_world = transform @ obj.matrix_world


def chord_offset(z: float) -> float:
    """Chord centreline y-offset from GY at height z (0..GTZ)."""

    t = max(0.0, min(1.0, z / GTZ))
    return CHORD_SPREAD_BASE + (CHORD_SPREAD_TOP - CHORD_SPREAD_BASE) * t


def add_bar(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    section: tuple[float, float],
    value,
    *,
    bevel: float = 0.02,
    pad: float = 0.0,
) -> bpy.types.Object:
    """Axis-tilted box member from start to end (YZ-plane tilts only)."""

    dy = end[1] - start[1]
    dz = end[2] - start[2]
    length = math.hypot(dy, dz) + pad
    center = (
        (start[0] + end[0]) / 2.0,
        (start[1] + end[1]) / 2.0,
        (start[2] + end[2]) / 2.0,
    )
    obj = bk.add_box(name, center, (section[0], section[1], length), value, bevel=bevel)
    obj.rotation_euler = (-math.atan2(dy, dz), 0.0, 0.0)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    obj.select_set(False)
    return obj


def add_plate(
    name: str,
    points: tuple,
    y: float,
    thickness: float,
    value,
    *,
    bevel: float = 0.01,
    uv_tile: float = 1.6,
) -> bpy.types.Object:
    """Flat plate in the X-Z plane at depth ``y``, extruded ``thickness``
    in y from a 2-D outline of ``(x, z)`` points.

    Boxes cannot express a gusset: a real one is a triangle whose two
    legs land flat on the two members it ties together. Winding is not
    the caller's problem - normals are recalculated outward - and a
    metric planar UV is authored so the plate samples the same texture
    scale as the boxes it sits against.
    """

    count = len(points)
    verts = [(x, y - thickness / 2.0, z) for x, z in points]
    verts += [(x, y + thickness / 2.0, z) for x, z in points]
    faces = [tuple(range(count)), tuple(range(2 * count - 1, count - 1, -1))]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, j + count, i + count))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    uv0 = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv0.data[loop_index].uv = (co.x / uv_tile, co.z / uv_tile)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return bk._finish_primitive(obj, name, value, bevel)


def add_tube_arc(
    name: str,
    center: tuple,
    radius: float,
    tube_r: float,
    y: float,
    a0: float,
    a1: float,
    value,
    *,
    arc_segments: int = 28,
    tube_segments: int = 16,
) -> bpy.types.Object:
    """Rope wrapped round a sheave: a tube of radius ``tube_r`` swept along
    an arc of radius ``radius`` about ``center`` (x, z) at depth ``y``,
    from angle ``a0`` to ``a1`` (radians from +x toward +z).

    Straight legs alone cannot express a rope on a sheave - they meet at a
    corner the wheel only half hides, which is what made the rope look
    like it ran INTO the wheel. This is the missing wrap.
    """

    cx, cz = center
    verts = []
    for i in range(arc_segments + 1):
        a = a0 + (a1 - a0) * i / arc_segments
        rx, rz = math.cos(a), math.sin(a)
        px, pz = cx + radius * rx, cz + radius * rz
        for j in range(tube_segments):
            b = 2.0 * math.pi * j / tube_segments
            off_r, off_y = tube_r * math.cos(b), tube_r * math.sin(b)
            verts.append((px + rx * off_r, y + off_y, pz + rz * off_r))
    faces = []
    for i in range(arc_segments):
        for j in range(tube_segments):
            k = (j + 1) % tube_segments
            p = i * tube_segments
            faces.append((p + j, p + k, p + k + tube_segments, p + j + tube_segments))
    # Cap both ends - they are buried in the straight legs, but an open
    # tube exports as a one-sided shell and flickers under backface cull.
    faces.append(tuple(range(tube_segments - 1, -1, -1)))
    last = arc_segments * tube_segments
    faces.append(tuple(range(last, last + tube_segments)))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    uv0 = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv0.data[loop_index].uv = (co.x / 0.4, co.z / 0.4)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return bk._finish_primitive(obj, name, value, 0.0)


def add_text_solid(
    name: str,
    text: str,
    cap_height: float,
    depth: float,
    value,
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
    *,
    max_width: float | None = None,
    font_path: str = HEAVY_FONT,
) -> bpy.types.Object:
    """Extruded glyph solid, centred on its bbox, posed via object transform.

    Blender FONT curves author glyphs in local XY with extrusion along Z;
    the marquee recipe (centrifuge, 2026-08-12) converts to mesh and lets
    the object matrix carry the pose - export bakes matrix_world.
    """

    curve = bpy.data.curves.new(f"{name}_curve", type="FONT")
    curve.body = text
    curve.font = _font(font_path)
    curve.size = 1.0
    curve.extrude = depth / 2.0
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    obj = bpy.context.view_layer.objects.active
    mesh = obj.data
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    h_raw = max(ys) - min(ys)
    w_raw = max(xs) - min(xs)
    scale = cap_height / h_raw
    if max_width is not None and w_raw * scale > max_width:
        scale = max_width / w_raw
    x_mid = 0.5 * (max(xs) + min(xs))
    y_mid = 0.5 * (max(ys) + min(ys))
    for v in mesh.vertices:
        v.co.x = (v.co.x - x_mid) * scale
        v.co.y = (v.co.y - y_mid) * scale
    mesh.update()
    obj.name = name
    mesh.name = f"{name}_mesh"
    obj.location = location
    obj.rotation_euler = rotation
    bk.assign_material(obj, value)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        bpy.ops.object.shade_flat()
    obj.select_set(False)
    return obj


def plank_board_uv(obj: bpy.types.Object, board_width: float, u_tile: float, phase: float) -> None:
    """Board-face UVs with the grain running down the LENGTH of the plank.

    The wood family authors grain along texture +X (u). Metric box UVs map
    u to world x on top faces, which would run the grain ACROSS the boards;
    this maps u from the plank's long axis (local y) instead, with a
    per-board phase so no two boards sample the same span of log.
    """

    mesh = obj.data
    uv0 = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        axis = max(range(3), key=lambda a: abs(polygon.normal[a]))
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            if axis == 2:  # face of the board
                uv = (co.y / u_tile + phase, co.x / board_width + 0.5)
            elif axis == 0:  # long edge: a narrow band of the same log
                uv = (co.y / u_tile + phase, 0.5 + co.z / THICK * 0.5)
            else:  # butt end
                uv = (co.x / board_width * 0.3 + phase, 0.5 + co.z / THICK * 0.5)
            uv0.data[loop_index].uv = uv
    mesh.update()


def board_end_faces(obj: bpy.types.Object, end_material, board_width: float) -> None:
    """Give a board's two butt faces their own end-grain material and
    crosscut UVs, in place.

    Call AFTER plank_board_uv (this overwrites those loops). Selection is
    by normal AND position: the routed axle channel is a cylinder along
    x, so its interior walls also carry +-Y normals - only faces sitting
    at the board's extreme y are butt ends. The bevel modifier applied at
    export inherits material indices from its source faces, so the eased
    arris stays wood and the flat end reads as cut timber.
    """

    mesh = obj.data
    slot = len(mesh.materials)
    mesh.materials.append(end_material)
    uv0 = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    ys = [v.co.y for v in mesh.vertices]
    extreme = max(abs(min(ys)), abs(max(ys)))
    for polygon in mesh.polygons:
        if abs(polygon.normal[1]) < 0.9:
            continue
        if abs(abs(polygon.center[1]) - extreme) > 0.02:
            continue
        polygon.material_index = slot
        sign = 1.0 if polygon.normal[1] > 0.0 else -1.0
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv0.data[loop_index].uv = (
                0.5 - sign * co.x / board_width,
                0.5 + co.z / THICK,
            )
    mesh.update()


def plate_face_uv(
    obj: bpy.types.Object, width: float, height: float, axis: str, sign: float
) -> None:
    """Map one outward face of a thin plate to the full 0..1 legend texture.

    ``axis``/``sign`` name the outward face normal; u must increase to the
    viewer's right (viewed from +X that is +y, from -Y it is +x, etc).
    Every other face parks on a corner texel of the brushed field.
    """

    a = 0 if axis == "x" else 1
    mesh = obj.data
    uv0 = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        outward = abs(polygon.normal[a]) > 0.9 and polygon.normal[a] * sign > 0
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            if outward and a == 0:
                uv = (0.5 + sign * co.y / width, 0.5 + co.z / height)
            elif outward:
                uv = (0.5 - sign * co.x / width, 0.5 + co.z / height)
            else:
                uv = (0.02, 0.02)
            uv0.data[loop_index].uv = uv
    mesh.update()


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def _gantry(materials) -> list:
    red = materials[f"{MOD_ID}_acme_red"]
    steel = materials[f"{MOD_ID}_steel"]
    concrete = materials[f"{MOD_ID}_concrete"]
    hazard = materials[f"{MOD_ID}_hazard_yellow"]
    white = materials[f"{MOD_ID}_paint_white"]
    target = materials[f"{MOD_ID}_target_red"]

    objects = []
    z_shoe_top = 0.57
    # The beam soffit - underside of the lower flange plate - is the one
    # datum every top-of-column joint is measured from (play-test
    # 2026-08-13 round 11, "make these connect in a way that makes more
    # sense"). The head batten, the knee gussets and the deflection
    # block all land on this line, so the column head reads as one
    # connection instead of three parts that each guessed their own
    # height.
    beam_z = GTZ + 0.32
    flange_under = beam_z - 0.395 - 0.035
    batten_half_h = 0.21
    batten_top_z = flange_under - batten_half_h
    for side, sx in (("l", -CHORD_X), ("r", CHORD_X)):
        # Concrete footing with four steel base shoes.
        objects.append(
            bk.add_box(
                f"{MOD_ID}_gantry_footing_{side}",
                (sx, GY, 0.175),
                (1.25, 2.9, 0.35),
                concrete,
                bevel=0.04,
                metric_uv=(1.6, 1.6),
            )
        )
        for leg, ly in (("f", -1), ("b", 1)):
            shoe_y = GY + ly * CHORD_SPREAD_BASE
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_gantry_shoe_{side}_{leg}",
                    (sx, shoe_y, 0.46),
                    (0.56, 0.56, 0.22),
                    red,
                    bevel=0.03,
                )
            )
            for bx in (-0.2, 0.2):
                for by in (-0.2, 0.2):
                    objects.append(
                        bk.add_cylinder(
                            (
                                f"{MOD_ID}_anchor_{side}_{leg}_"
                                f"{'p' if bx > 0 else 'm'}{'p' if by > 0 else 'm'}"
                            ),
                            (sx + bx, shoe_y + by, 0.60),
                            0.035,
                            0.08,
                            steel,
                            vertices=6,
                        )
                    )
            # Battered chord from shoe to beam seat.
            objects.append(
                add_bar(
                    f"{MOD_ID}_chord_{side}_{leg}",
                    (sx, GY + ly * chord_offset(z_shoe_top - 0.12), z_shoe_top - 0.12),
                    (sx, GY + ly * CHORD_SPREAD_TOP, GTZ),
                    (CHORD_SECTION, CHORD_SECTION),
                    red,
                    bevel=0.025,
                    pad=0.1,
                )
            )
        # Zigzag lacing between the two chords of this side.
        z_lace = [0.9 + i * ((GTZ - 0.8) - 0.9) / 7.0 for i in range(8)]
        for i in range(7):
            z0, z1 = z_lace[i], z_lace[i + 1]
            side0 = -1 if i % 2 == 0 else 1
            objects.append(
                add_bar(
                    f"{MOD_ID}_lace_{side}_{i}",
                    (sx, GY + side0 * chord_offset(z0), z0),
                    (sx, GY - side0 * chord_offset(z1), z1),
                    (0.05, 0.14),
                    red,
                    bevel=0.012,
                    pad=0.16,
                )
            )
        # Batten plates closing the lattice top and bottom. The bottom
        # batten doubles as the hazard panel at bumper height - painted
        # stripe plates floating across the OPEN lattice read as loose
        # boards (review render 2026-08-13), a solid batten does not.
        # Batten y extent is set at each batten's WIDE end (chords are
        # battered, so a face flush at the batten's centre height lets
        # the chord poke through the skin at the wide edge - play-test
        # 2026-08-13 round 5, green circle on the post base), plus 2 cm
        # of wrap margin.
        # The head batten now caps the column TIGHT under the beam
        # soffit. It used to float 23 cm below it, leaving a bare strip
        # of chord between column and beam and reading as a collar
        # slipped over a post rather than the head of a column.
        objects.append(
            bk.add_box(
                f"{MOD_ID}_batten_{side}_top",
                (sx, GY, batten_top_z),
                (
                    0.34,
                    2 * chord_offset(batten_top_z - batten_half_h) + CHORD_SECTION + 0.04,
                    2 * batten_half_h,
                ),
                red,
                bevel=0.02,
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_batten_{side}_bot",
                (sx, GY, 0.88),
                (0.34, 2 * chord_offset(0.88 - 0.275) + CHORD_SECTION + 0.04, 0.55),
                hazard,
                bevel=0.02,
                metric_uv=(1.2, 1.2),
            )
        )

    # Riveted crossbeam with top/bottom flange plates.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_gantry_beam",
            (0.0, GY, beam_z),
            (6.4, 0.55, 0.72),
            red,
            bevel=0.03,
            metric_uv=(1.6, 1.6),
        )
    )
    for fz in (beam_z + 0.395, beam_z - 0.395):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_beam_flange_{int(fz * 100)}",
                (0.0, GY, fz),
                (6.6, 0.74, 0.07),
                red,
                bevel=0.02,
            )
        )
    rivet_i = 0
    for face in (-1, 1):
        for rz in (beam_z - 0.27, beam_z + 0.27):
            for k in range(13):
                rx = -2.9 + k * (5.8 / 12.0)
                objects.append(
                    bk.add_sphere(
                        f"{MOD_ID}_rivet_{rivet_i}",
                        (rx, GY + face * 0.30, rz),
                        0.034,
                        red,
                        segments=RIVET_SEG,
                        rings=RIVET_RING,
                        scale=(1.0, 0.55, 1.0),
                    )
                )
                rivet_i += 1
    # Knee gussets tying the beam soffit to the column heads.
    #
    # The old detail here was a 45-degree diamond plate at x = +-2.5 -
    # 30 cm inboard of the columns at +-2.8. Its upper half hid behind
    # the lower flange and its lower half hung in open air below the
    # flange, riveted to nothing at all (play-test 2026-08-13 round 11).
    # A gusset is not an ornament stuck near a joint; it IS the joint,
    # so this one is a right triangle whose two legs lie FLAT on the two
    # members it ties - the horizontal leg under the beam soffit, the
    # vertical leg down the batten's inboard face - with the hypotenuse
    # facing out and rivet lines on both legs.
    knee_run = 0.62  # inboard along the beam soffit
    knee_rise = 2 * batten_half_h  # down the column head, batten height
    for side, sx in (("l", -CHORD_X), ("r", CHORD_X)):
        # Inboard face of the head batten (0.34 wide, centred on sx).
        inner = sx - math.copysign(0.17, sx)
        toe = inner - math.copysign(knee_run, sx)
        for face, fy in (("f", -1.0), ("b", 1.0)):
            # Just proud of the chord's outer face, and still inside the
            # flange's 0.37 half-depth so nothing overhangs the beam.
            py = GY + fy * (CHORD_SPREAD_TOP + CHORD_SECTION / 2.0 + 0.022)
            objects.append(
                add_plate(
                    f"{MOD_ID}_knee_{side}_{face}",
                    (
                        (inner, flange_under),
                        (toe, flange_under),
                        (inner, flange_under - knee_rise),
                    ),
                    py,
                    0.044,
                    red,
                )
            )
            rivet_y = GY + fy * (CHORD_SPREAD_TOP + CHORD_SECTION / 2.0 + 0.05)
            seats = [
                (inner - math.copysign(dx, sx), flange_under - 0.06) for dx in (0.13, 0.28, 0.43)
            ]
            seats += [(inner - math.copysign(0.09, sx), flange_under - dz) for dz in (0.17, 0.29)]
            for ri, (rx, rz) in enumerate(seats):
                objects.append(
                    bk.add_sphere(
                        f"{MOD_ID}_knee_rivet_{side}_{face}_{ri}",
                        (rx, rivet_y, rz),
                        0.032,
                        red,
                        segments=RIVET_SEG,
                        rings=RIVET_RING,
                        scale=(1.0, 0.55, 1.0),
                    )
                )

    # ACME header board on the beam, letters extruded toward the approach.
    board_z = beam_z + 0.395 + 0.035 + 0.675
    objects.append(
        bk.add_box(
            f"{MOD_ID}_sign_board",
            (0.0, GY, board_z),
            (5.7, 0.14, 1.35),
            white,
            bevel=0.02,
        )
    )
    for tag, tz in (("head", board_z + 0.675), ("foot", board_z - 0.675)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_sign_trim_{tag}",
                (0.0, GY, tz),
                (5.82, 0.17, 0.1),
                target,
                bevel=0.015,
            )
        )
    for tag, tx in (("w", -2.86), ("e", 2.86)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_sign_trim_{tag}",
                (tx, GY, board_z),
                (0.1, 0.17, 1.45),
                target,
                bevel=0.015,
            )
        )
    # Letterspaced brand line - the mid-century cartoon signage idiom
    # (wide tracking on a heavy gothic, generous margins).
    objects.append(
        add_text_solid(
            f"{MOD_ID}_sign_acme",
            "A C M E",
            0.72,
            0.07,
            target,
            (0.0, GY - 0.095, board_z + 0.18),
            (math.pi / 2.0, 0.0, 0.0),
            max_width=4.9,
        )
    )
    objects.append(
        add_text_solid(
            f"{MOD_ID}_sign_sub",
            "CATAPULT CO.",
            0.235,
            0.05,
            target,
            (0.0, GY - 0.085, board_z - 0.44),
            (math.pi / 2.0, 0.0, 0.0),
            max_width=4.6,
        )
    )
    # Sign brackets: foot plate ON the beam flange, vertical cleat
    # against the board's back, diagonal running foot-to-cleat with both
    # ends embedded (play-test 2026-08-13: the old free-floating diagonal
    # hung past the beam's back corner - "look how they're detached").
    # Foot plate lands ON the flange's top surface and stays INSIDE its
    # back edge, then is riveted down (play-test 2026-08-13 round 8: the
    # plate's underside sat 35 mm below the flange top - "the edge of the
    # sign holder should not be embedded ... use rivets to hold it down").
    flange_top = beam_z + 0.395 + 0.035
    foot_t = 0.05
    foot_z = flange_top + foot_t / 2.0
    foot_y, foot_depth = GY + 0.22, 0.28
    for bx in (-2.3, 2.3):
        tag = "w" if bx < 0 else "e"
        objects.append(
            bk.add_box(
                f"{MOD_ID}_sign_foot_{tag}",
                (bx, foot_y, foot_z),
                (0.18, foot_depth, foot_t),
                steel,
                bevel=0.008,
            )
        )
        for ri, (rx, ry) in enumerate(
            ((-0.05, -0.095), (0.05, -0.095), (-0.05, 0.095), (0.05, 0.095))
        ):
            objects.append(
                bk.add_sphere(
                    f"{MOD_ID}_sign_foot_rivet_{tag}_{ri}",
                    (bx + rx, foot_y + ry, foot_z + foot_t / 2.0),
                    0.028,
                    steel,
                    segments=RIVET_SEG,
                    rings=RIVET_RING,
                    scale=(1.0, 1.0, 0.6),
                )
            )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_sign_cleat_{tag}",
                (bx, GY + 0.095, board_z + 0.05),
                (0.14, 0.06, 1.15),
                steel,
                bevel=0.008,
            )
        )
        objects.append(
            add_bar(
                f"{MOD_ID}_sign_brace_{tag}",
                (bx, GY + 0.3, board_z - 0.67),
                (bx, GY + 0.1, board_z + 0.44),
                (0.06, 0.06),
                steel,
                bevel=0.01,
                pad=0.12,
            )
        )

    # Crown block: one continuous stack from beam to hook (play-test
    # 2026-08-13 "this crane holder needs to be more cohesive" - the old
    # loose discs and floating axle stub read as separate parts). Full-
    # height steel cheek plates hang from the beam flange; the sheave
    # wheel, axle and end bosses live BETWEEN them; the release housing
    # bolts straight onto the cheek bottoms; the hook stem leaves the
    # housing underside.
    # Sheave plane lies ALONG the cable run (play-test 2026-08-13 round
    # 4: "rotate ... 90 degrees so the cable lines up with what looks
    # like the cable return"). The run travels in x-z at y=GY, so the
    # wheel spins about Y and the cheek plates flank it in y.
    # Cheek plates are WAISTED, not rectangular. A rectangle wider than
    # the wheel hides the wheel, and then the whole block reads as a
    # slab with a disc lost behind it; a block reads as a block when the
    # sheave rim stands proud of its straps. Wide at the beam, pinched
    # to 0.22 at the axle so the 0.30 wheel shows, then back out to
    # carry the release housing.
    for py in (-0.13, 0.13):
        objects.append(
            add_plate(
                f"{MOD_ID}_sheave_cheek_{'n' if py > 0 else 's'}",
                (
                    (-0.14, flange_under),
                    (0.14, flange_under),
                    (0.22, CROWN_Z + 0.05),
                    (0.17, CROWN_Z - 0.33),
                    (-0.17, CROWN_Z - 0.33),
                    (-0.22, CROWN_Z + 0.05),
                ),
                GY + py,
                0.05,
                red,
            )
        )
    # Grooved wheel, not a plain disc: a narrow core between two proud
    # rim flanges is what makes a sheave read as a sheave, and it gives
    # the rope a groove to actually sit in. CABLE_R above the core is
    # the rope's centreline radius - every cable leg is aimed at it.
    # The FLANGE MUST STAND PROUD OF THE ROPE. The first grooved wheel put
    # the rope centreline 15 mm inside a 0.26 rim, so the rope's own 40 mm
    # radius carried it 25 mm PAST the rim - it cut through the flange and
    # its sawn-off end hung over the wheel ("the pully wheel ... runs into
    # the cable", play-test 2026-08-13 round 12). Groove depth now exceeds
    # the rope diameter: core + CABLE_R is the rope centreline, and the rim
    # clears the rope's outer surface by another 40 mm.
    crown_core_r = 0.18
    crown_groove_r = crown_core_r + CABLE_R
    crown_rim_r = crown_groove_r + CABLE_R + 0.04
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_sheave_wheel",
            (0.0, GY, CROWN_Z),
            crown_core_r,
            0.115,
            steel,
            vertices=SEG_LARGE,
            axis="Y",
        )
    )
    for py in (-0.075, 0.075):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_sheave_rim_{'n' if py > 0 else 's'}",
                (0.0, GY + py, CROWN_Z),
                crown_rim_r,
                0.035,
                steel,
                vertices=SEG_LARGE,
                axis="Y",
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_sheave_axle",
            (0.0, GY, CROWN_Z),
            0.07,
            0.34,
            steel,
            vertices=SEG_SMALL,
            axis="Y",
        )
    )
    for py in (-0.17, 0.17):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_sheave_boss_{'n' if py > 0 else 's'}",
                (0.0, GY + py, CROWN_Z),
                0.11,
                0.05,
                steel,
                vertices=SEG_SMALL,
                axis="Y",
            )
        )
    # Release housing bolted to the cheek bottoms, comedy lever anchored
    # INSIDE it with the knob on the lever's free end (the old -38 deg
    # rotation put the knob off the wrong end - it floated).
    objects.append(
        bk.add_box(
            f"{MOD_ID}_release_housing",
            (0.0, GY, CROWN_Z - 0.35),
            (0.46, 0.62, 0.3),
            red,
            bevel=0.03,
        )
    )
    lever = bk.add_box(
        f"{MOD_ID}_release_lever",
        (0.42, GY - 0.2, CROWN_Z - 0.10),
        (0.06, 0.07, 0.62),
        steel,
        bevel=0.01,
        rotation=(0.0, math.radians(38.0), 0.0),
    )
    objects.append(lever)
    objects.append(
        bk.add_sphere(
            f"{MOD_ID}_release_knob",
            (0.615, GY - 0.2, CROWN_Z + 0.15),
            0.075,
            target,
            segments=32,
            rings=16,
        )
    )
    # (The hook stem and hook now live in the WEIGHT part - play-test
    # 2026-08-13 round 7: the latch must ride down with the weight, cable
    # attached, while the drum free-spools. The stretching drop cable is
    # its own posable part, built in build_parts.)

    # --- Deflection block: a hung snatch block, not a lump.
    #
    # What was here was a 0.16 r disc half-buried in a plain box, with
    # the run cable plunging into the disc's CENTRE and the drop cable
    # leaving from the same centre - so the rope visibly vanished into a
    # blob ("let's create a better spool here for the cable", play-test
    # 2026-08-13 round 11). This is the real article: a lug hung off the
    # beam soffit, a clevis pin, two cheek plates, and a grooved wheel
    # on an axle between them - the crown block's language, one size
    # down. It sits inboard of the head batten so the two never fight
    # for the same volume.
    dx_c, dz_c = 2.30, GTZ - 0.70
    defl_core_r = 0.18
    defl_groove_r = defl_core_r + CABLE_R
    defl_rim_r = defl_groove_r + CABLE_R + 0.04
    # Pin sits clear ABOVE the rim, or the wheel eats its own hanger.
    pin_z = dz_c + defl_rim_r + 0.08
    lug_h = flange_under - pin_z + 0.12
    objects.append(
        bk.add_box(
            f"{MOD_ID}_deflect_lug",
            (dx_c, GY, flange_under - lug_h / 2.0 + 0.03),
            (0.17, 0.15, lug_h),
            red,
            bevel=0.012,
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_deflect_pin",
            (dx_c, GY, pin_z),
            0.05,
            0.32,
            steel,
            vertices=SEG_SMALL,
            axis="Y",
        )
    )
    for py in (-0.13, 0.13):
        objects.append(
            add_plate(
                f"{MOD_ID}_deflect_cheek_{'n' if py > 0 else 's'}",
                (
                    (dx_c - 0.09, pin_z + 0.08),
                    (dx_c + 0.09, pin_z + 0.08),
                    (dx_c + 0.20, dz_c + 0.02),
                    (dx_c + 0.13, dz_c - 0.18),
                    (dx_c - 0.13, dz_c - 0.18),
                    (dx_c - 0.20, dz_c + 0.02),
                ),
                GY + py,
                0.045,
                red,
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_deflect_wheel",
            (dx_c, GY, dz_c),
            defl_core_r,
            0.11,
            steel,
            vertices=SEG_LARGE,
            axis="Y",
        )
    )
    for py in (-0.07, 0.07):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_deflect_rim_{'n' if py > 0 else 's'}",
                (dx_c, GY + py, dz_c),
                defl_rim_r,
                0.03,
                steel,
                vertices=SEG_LARGE,
                axis="Y",
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_deflect_axle",
            (dx_c, GY, dz_c),
            0.055,
            0.34,
            steel,
            vertices=SEG_SMALL,
            axis="Y",
        )
    )
    for py in (-0.16, 0.16):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_deflect_boss_{'n' if py > 0 else 's'}",
                (dx_c, GY + py, dz_c),
                0.085,
                0.04,
                steel,
                vertices=SEG_SMALL,
                axis="Y",
            )
        )

    # Cable run: crown groove -> deflection groove -> winch drum, on the
    # UPPER EXTERNAL TANGENT of the two groove circles. Aiming a leg at
    # a wheel's centre is what made the rope look swallowed; a tangent
    # leg ends INSIDE the rim, so the rim itself covers the corner where
    # the two legs meet and the rope reads as running over the sheave.
    span_x, span_z = dx_c, dz_c - CROWN_Z
    span = math.hypot(span_x, span_z)
    beta = math.asin((crown_groove_r - defl_groove_r) / span) - math.atan2(span_z, span_x)
    nx, nz = math.sin(beta), math.cos(beta)
    t1 = (crown_groove_r * nx, CROWN_Z + crown_groove_r * nz)
    t2 = (dx_c + defl_groove_r * nx, dz_c + defl_groove_r * nz)
    run = bk.add_cylinder(
        f"{MOD_ID}_cable_run_top",
        ((t1[0] + t2[0]) / 2.0, GY, (t1[1] + t2[1]) / 2.0),
        CABLE_R,
        math.hypot(t2[0] - t1[0], t2[1] - t1[1]),
        steel,
        vertices=SEG_ROPE,
        axis="X",
    )
    run.rotation_euler = (0.0, math.atan2(t1[1] - t2[1], t2[0] - t1[0]), 0.0)
    bpy.context.view_layer.objects.active = run
    run.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    run.select_set(False)
    objects.append(run)
    # Drop leg: tangent to the groove on the far side, straight down to
    # where the wound coils actually are, not into the drum's middle.
    drop_top, drop_bot = dz_c, WINCH_Z + WINCH_COIL_R
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_cable_drop",
            (dx_c + defl_groove_r, GY, (drop_top + drop_bot) / 2.0),
            CABLE_R,
            drop_top - drop_bot,
            steel,
            vertices=SEG_ROPE,
        )
    )
    # ...and the wraps that join the legs. The deflection sheave turns the
    # rope from the run down to the drop (tangent angle round to 0, where
    # the drop leaves); the crown carries it from the run over the top and
    # down the far side into the release housing.
    lead_a = math.atan2(nz, nx)
    objects.append(
        add_tube_arc(
            f"{MOD_ID}_cable_wrap_deflect",
            (dx_c, dz_c),
            defl_groove_r,
            CABLE_R,
            GY,
            lead_a,
            0.0,
            steel,
            tube_segments=SEG_ROPE // 2 + 6,
        )
    )
    objects.append(
        add_tube_arc(
            f"{MOD_ID}_cable_wrap_crown",
            (0.0, CROWN_Z),
            crown_groove_r,
            CABLE_R,
            GY,
            lead_a,
            math.radians(250.0),
            steel,
            tube_segments=SEG_ROPE // 2 + 6,
        )
    )
    # Hand winch on a red pedestal between the chords.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_winch_pedestal",
            (2.8, GY, 0.75),
            (0.8, 0.55, 1.5),
            red,
            bevel=0.03,
            metric_uv=(1.6, 1.6),
        )
    )
    # (Spool, gear and crank live in the posable "winch" part - see
    # build_parts - so the crank winds with the cable.)
    return objects


def _fulcrum(materials) -> list:
    red = materials[f"{MOD_ID}_acme_red"]
    steel = materials[f"{MOD_ID}_steel"]
    concrete = materials[f"{MOD_ID}_concrete"]

    objects = []
    leg_bottom_y = 1.65
    leg_top_y = 0.30
    leg_bottom_z = 0.30
    leg_top_z = PIVOT_Z - 0.38

    def leg_y_at(z: float) -> float:
        t = (z - leg_bottom_z) / (leg_top_z - leg_bottom_z)
        return leg_bottom_y + (leg_top_y - leg_bottom_y) * t

    for side, sx in (("l", -(HW + 0.35)), ("r", HW + 0.35)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_base_pad_{side}",
                (sx, 0.0, 0.16),
                (1.3, 4.2, 0.32),
                concrete,
                bevel=0.05,
                metric_uv=(1.6, 1.6),
            )
        )
        for leg, ly in (("f", -1), ("b", 1)):
            objects.append(
                add_bar(
                    f"{MOD_ID}_trestle_leg_{side}_{leg}",
                    (sx, ly * leg_bottom_y, leg_bottom_z),
                    (sx, ly * leg_top_y, leg_top_z),
                    (0.5, 0.14),
                    red,
                    bevel=0.02,
                    pad=0.18,
                )
            )
        # Two ties and crossed lacing turn the raised 4.8 m bearing into a
        # real trestle instead of leaving its axle floating over the old
        # waist-high playground stand.
        tie_levels = (1.45, 3.05)
        for tie_index, tie_z in enumerate(tie_levels):
            tie_y = leg_y_at(tie_z)
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_trestle_tie_{side}_{tie_index}",
                    (sx, 0.0, tie_z),
                    (0.5, 2 * tie_y + 0.42, 0.14),
                    red,
                    bevel=0.02,
                )
            )
            for tag, ty in (("f", -tie_y), ("b", tie_y)):
                objects.append(
                    bk.add_cylinder(
                        f"{MOD_ID}_tie_bolt_{side}_{tie_index}_{tag}",
                        (sx, ty, tie_z + 0.09),
                        0.045,
                        0.035,
                        steel,
                        vertices=6,
                    )
                )
        lower_z, upper_z = 1.0, 3.72
        for brace_index, (a_sign, b_sign) in enumerate(((-1, 1), (1, -1))):
            objects.append(
                add_bar(
                    f"{MOD_ID}_trestle_brace_{side}_{brace_index}",
                    (sx, a_sign * leg_y_at(lower_z), lower_z),
                    (sx, b_sign * leg_y_at(upper_z), upper_z),
                    (0.10, 0.18),
                    red,
                    bevel=0.012,
                    pad=0.12,
                )
            )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_pillow_block_{side}",
                (sx, 0.0, PIVOT_Z - 0.265),
                (0.62, 0.9, 0.34),
                red,
                bevel=0.04,
            )
        )
        # Cap spans the full block footprint so its bolts land on the
        # flats BESIDE the shaft - at +-0.24 they sat inside the axle's
        # 0.28 radius and bored straight through it (play-test
        # 2026-08-13, green arrows: expand the cap outward).
        objects.append(
            bk.add_box(
                f"{MOD_ID}_pillow_cap_{side}",
                (sx, 0.0, PIVOT_Z + 0.225),
                (0.5, 0.9, 0.2),
                red,
                bevel=0.05,
            )
        )
        for by in (-0.345, 0.345):
            for bx in (-0.17, 0.17):
                objects.append(
                    bk.add_cylinder(
                        (
                            f"{MOD_ID}_cap_bolt_{side}_"
                            f"{'p' if by > 0 else 'm'}{'p' if bx > 0 else 'm'}"
                        ),
                        (sx + bx, by, PIVOT_Z + 0.075),
                        0.04,
                        0.55,
                        steel,
                        vertices=6,
                    )
                )
    # Pivot axle. End hardware SEATS against the bearing block's outer
    # face (x 2.86) - the first pass floated the cap disc 3 cm off the
    # block, which read as disconnected parts (play-test 2026-08-13):
    # thrust washer tight on the face, then the retaining hex nut, with
    # the axle ending inside the nut.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_pivot_tube",
            (0.0, 0.0, PIVOT_Z),
            0.28,
            5.94,
            steel,
            vertices=SEG_LARGE,
            axis="X",
        )
    )
    for side, sx in (("l", -1.0), ("r", 1.0)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_tube_cap_{side}",
                (sx * 2.885, 0.0, PIVOT_Z),
                0.31,
                0.05,
                steel,
                vertices=SEG_LARGE,
                axis="X",
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_tube_nut_{side}",
                (sx * 2.945, 0.0, PIVOT_Z),
                0.14,
                0.12,
                steel,
                vertices=6,
                axis="X",
            )
        )
    return objects


def deck_sheet_uv(
    obj: bpy.types.Object, width: float, length: float, park: tuple = (0.5, 0.06)
) -> None:
    """Map the sheet's top face 0..1 onto a one-shot deck texture
    (u across, v along); every other face parks on ``park`` - a
    known-asphalt texel for the ramp deck, a guaranteed-transparent
    texel (0.5, 0.02) for the alpha-cutout paint decals."""

    mesh = obj.data
    uv0 = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        top = polygon.normal[2] > 0.5
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            if top:
                uv = (co.x / width + 0.5, co.y / length + 0.5)
            else:
                uv = park
            uv0.data[loop_index].uv = uv
    mesh.update()


def _ramp(materials) -> list:
    asphalt = materials[f"{MOD_ID}_ramp_asphalt"]
    deck = materials[f"{MOD_ID}_ramp_deck"]
    red = materials[f"{MOD_ID}_acme_red"]
    steel = materials[f"{MOD_ID}_steel"]

    objects = []
    _, end_y, end_z = plank_point(0.0, CAR_END_Y, THICK / 2)
    run = end_y - spec.RAMP_GROUND_Y
    ramp_len = math.hypot(run, end_z)
    angle = math.atan2(end_z, run)
    normal = (0.0, -math.sin(angle), math.cos(angle))
    mid_y = (spec.RAMP_GROUND_Y + end_y) / 2
    center = (0.0, mid_y - normal[1] * 0.11, end_z / 2 - normal[2] * 0.11)
    objects.append(
        bk.add_box(
            f"{MOD_ID}_ramp",
            center,
            (2 * HW + 0.4, ramp_len, 0.22),
            asphalt,
            bevel=0.0,
            rotation=(angle, 0.0, 0.0),
            metric_uv=(2.5, 2.5),
        )
    )
    # Deck sheet: a 3 mm skin over the whole top face carrying the
    # one-shot painted surface (chevrons + hazard edge bands IN the
    # texture). Marking geometry - even 4 mm plates - casts shadows and
    # catches edge light in-engine (play-test 2026-08-13, "no shadow or
    # edge"); a full-coverage skin has no interior edges to betray it.
    # UVs are authored while the box is axis-aligned, then the slope
    # rotation is baked on top (chevron two-step pattern).
    sheet = bk.add_box(
        f"{MOD_ID}_ramp_deck_sheet",
        (
            center[0] + normal[0] * 0.1115,
            center[1] + normal[1] * 0.1115,
            center[2] + normal[2] * 0.1115,
        ),
        (2 * HW + 0.4, ramp_len, 0.003),
        deck,
        bevel=0.0,
    )

    # Support frame under the deck (play-test 2026-08-13 round 9: "create
    # proper supports for this steel ramp" - the ramp was a bare slab
    # floating over its own shadow). A fabricated steel ramp carries its
    # deck on two side rails with cross ribs between them, standing on
    # short posts with base plates; the low end simply dies into the
    # ground, which is why the posts only appear up-slope where there is
    # real air to span. Everything is placed off the deck's own slope so
    # the frame stays parallel to the surface it carries.
    def deck_point(t: float, x: float, drop: float) -> tuple:
        """Point at fraction t along the ramp (0 = toe, 1 = plank end),
        lateral x, `drop` metres beneath the deck's top surface."""

        y = spec.RAMP_GROUND_Y + (end_y - spec.RAMP_GROUND_Y) * t
        z = end_z * t
        return (x, y - normal[1] * drop, z - normal[2] * drop)

    rail_drop = 0.34  # rail centreline below the deck top
    rail_depth = 0.24
    rail_x = 2.15
    for tag, sx in (("w", -rail_x), ("e", rail_x)):
        objects.append(
            add_bar(
                f"{MOD_ID}_ramp_rail_{tag}",
                deck_point(0.34, sx, rail_drop),
                # Stops short of the deck's top edge: the plank's tip
                # occupies everything past the car end and swings through it.
                deck_point(0.97, sx, rail_drop),
                # Wider than the 0.14 posts so the rail visibly carries
                # them instead of the post edges hanging out in air.
                (0.17, rail_depth),
                red,
                bevel=0.012,
                pad=0.06,
            )
        )
    # Cross ribs tying the rails, plus posts wherever the underside has
    # cleared the ground enough to need one.
    #
    # Ribs share the rails' drop AND depth so the frame has continuous top
    # and bottom faces. They used to sit 1 cm higher and be 2 cm shallower,
    # which put a step along the bottom edge of every crossing - one of the
    # things that read as "disjointed" in play-test round 12.
    #
    # Ribs also die into the rails' CENTRELINES rather than reaching for
    # their outer faces, so the rail face is the frame's only silhouette
    # and no rib end has to be mitred flush against a bevelled one.
    #
    # And the leg stations stop SHORT of the rails' end. The last station
    # used to sit exactly where the rails stop, so a post centred there had
    # 5 cm of itself hanging past the rail's cut end with its sawn top face
    # in full sun - the joint the player circled. Legs now stand under
    # continuous rail with the rail cantilevering 18 cm past the last one.
    rib_thick = 0.20
    for ri, t in enumerate((0.46, 0.66, 0.80, 0.93)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ramp_rib_{ri}",
                deck_point(t, 0.0, rail_drop),
                (2 * rail_x, rib_thick, rail_depth),
                red,
                bevel=0.01,
                rotation=(angle, 0.0, 0.0),
            )
        )
        # Post tops run all the way to the rail's CENTRELINE, not to its
        # underside (play-test 2026-08-13 round 10: "attach the feet to
        # the frame properly"). Butting a post against the rail left only
        # 3 mm of overlap while both parts carry a 12 mm bevel, so the
        # two chamfers ate the entire contact and opened a V-groove at
        # the joint. Buried 12 cm inside the rail, the joint cannot come
        # apart.
        #
        # Round 10 also put an angled bearing plate under the rail here.
        # It had to go (round 11, "fix how all this is put together
        # because it's a bit sloppy"): this ramp tops out at 0.70 m, so
        # the rail underside is only 13-21 cm off the ground at the
        # stations that get legs, and a 5 cm cap in that gap left the
        # post showing as a 4 cm sliver below it and a 12 cm sliver
        # above - the leg read as a stack of loose plates. THE LESSON is
        # that a detail needs room to be read: a bearing cap on a 25 cm
        # leg is not more construction, it is less. Base plate, post,
        # rail. Nothing between them. The cap was belt-and-braces anyway
        # once the post ran to the rail's centreline.
        post_h = deck_point(t, rail_x, rail_drop)[2]
        if post_h < 0.16:
            continue
        for tag, sx in (("w", -rail_x), ("e", rail_x)):
            py = deck_point(t, sx, rail_drop)[1]
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_ramp_post_{ri}_{tag}",
                    (sx, py, post_h / 2.0),
                    (0.16, 0.16, post_h),
                    red,
                    bevel=0.012,
                )
            )
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_ramp_pad_{ri}_{tag}",
                    (sx, py, 0.025),
                    (0.30, 0.30, 0.05),
                    steel,
                    bevel=0.008,
                )
            )
            # Anchor bolts through the base plate into the ground.
            for bi, (bx, by) in enumerate(
                ((-0.10, -0.10), (0.10, -0.10), (-0.10, 0.10), (0.10, 0.10))
            ):
                objects.append(
                    bk.add_cylinder(
                        f"{MOD_ID}_ramp_anchor_{ri}_{tag}_{bi}",
                        (sx + bx, py + by, 0.062),
                        0.03,
                        0.03,
                        steel,
                        vertices=6,
                    )
                )
    deck_sheet_uv(sheet, 2 * HW + 0.4, ramp_len)
    sheet.rotation_euler = (angle, 0.0, 0.0)
    bpy.context.view_layer.objects.active = sheet
    sheet.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    sheet.select_set(False)
    objects.append(sheet)
    return objects


def build_visual(materials) -> list:
    objects = []
    objects.extend(_gantry(materials))
    objects.extend(_fulcrum(materials))
    objects.extend(_ramp(materials))
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    wood_a = materials[f"{MOD_ID}_plank_wood"]
    wood_b = materials[f"{MOD_ID}_plank_wood_b"]
    steel = materials[f"{MOD_ID}_steel"]
    red = materials[f"{MOD_ID}_acme_red"]
    iron = materials[f"{MOD_ID}_cast_iron"]
    white = materials[f"{MOD_ID}_paint_white"]
    target = materials[f"{MOD_ID}_target_red"]
    impact_rubber = materials[f"{MOD_ID}_impact_rubber"]

    parts: dict[str, dict[str, object]] = {}

    # --- Plank: four individual boards, authored FLAT (runtime holds the
    # rest tilt matching the collision cage).
    plank_objects = []
    board_width = 1.06
    gap = (2 * HW - 4 * board_width) / 3.0
    # +-2 mm lay jitter: enough that boards still catch light individually,
    # small enough that the painted deck markings can lie FLAT across all
    # four boards without floating (player marked the raised markings,
    # play-test 2026-08-13: "should be flat ... like it's painted on").
    jitters = (0.002, -0.002, 0.001, -0.0015)
    phases = (0.0, 0.37, 0.74, 0.19)
    for i in range(4):
        bx = -1.5 * (board_width + gap) + i * (board_width + gap)
        board = bk.add_box(
            f"{MOD_ID}_board_{i}",
            (bx, PLANK_CENTER_Y, PIVOT_Z + jitters[i]),
            (board_width, PLANK_LENGTH, THICK),
            wood_a if i % 2 == 0 else wood_b,
            bevel=0.03,
        )
        # Rout the axle channel through the middle boards so the pivot
        # collar nests instead of bursting through the deck.
        cutter = bk.add_cylinder(
            f"{MOD_ID}_board_cutter_{i}",
            (bx, 0.0, PIVOT_Z + jitters[i]),
            0.29,
            board_width + 0.4,
            None,
            vertices=48,
            axis="X",
        )
        bk.cut_openings(board, [cutter])
        plank_board_uv(board, board_width, 6.0, phases[i])
        # Crosscut ring arcs go ON the board's own butt faces - no cap
        # geometry (play-test 2026-08-13 round 8: the 12 mm caps were
        # full board_width x THICK boxes butted against a BEVELLED board
        # end, so their square corners overhung the eased arris and read
        # as "a very badly applied veneer"). A second material slot has
        # no silhouette of its own, so there is nothing left to overhang.
        board_end_faces(board, materials[f"{MOD_ID}_plank_end"], board_width)
        plank_objects.append(board)
    # Steel pivot collar nested in the routed channel (r 0.26: half-buried
    # in the deck reads as a through-axle; the first cut at 0.34 rode
    # 16 cm proud and read as a pipe laid across the boards).
    plank_objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_plank_collar",
            (0.0, 0.0, PIVOT_Z),
            0.26,
            2 * HW + 0.5,
            steel,
            vertices=SEG_LARGE,
            axis="X",
        )
    )
    # Saddle clamps marrying the rotating sleeve to the plank: U-bolt
    # strap over the top, red saddle block wrapping the underside into
    # the board bellies at the same stations - so the sleeve visibly
    # belongs to the plank (play-test 2026-08-13: "think about realistic
    # mechanical part").
    for ui, ux in enumerate((-1.55, -0.45, 0.45, 1.55)):
        plank_objects.append(
            bk.add_torus(
                f"{MOD_ID}_collar_strap_{ui}",
                (ux, 0.0, PIVOT_Z + 0.02),
                0.29,
                0.03,
                steel,
                rotation=(0.0, math.pi / 2.0, 0.0),
                major_segments=TORUS_MAJOR,
                minor_segments=TORUS_MINOR,
            )
        )
        plank_objects.append(
            bk.add_box(
                f"{MOD_ID}_collar_saddle_{ui}",
                (ux, 0.0, PIVOT_Z - 0.2),
                (0.2, 0.58, 0.14),
                red,
                bevel=0.02,
            )
        )
    # End banding: a single U-strap wrapped round the plank, not four
    # loose plates. Round 11 fixed the same bevel trap as the ramp feet
    # (play-test 2026-08-13): the top and bottom plates used to run
    # 4.5 m - dead flush with the OUTER face of the 0.05 side plates -
    # so the two 8 mm chamfers met edge-on and opened a nick down every
    # corner, and the bottom plate's tips read as slabs floating past
    # the boards. Now the plates die at the side plates' CENTRELINE and
    # the side plates set the whole band's outer silhouette; the side
    # plates are also cut to exactly the plates' outer faces, so the
    # band closes flush top and bottom. Bolt heads on all four faces.
    band_t, band_side_t = 0.04, 0.05
    band_x = HW + band_side_t / 2.0
    band_half_h = THICK / 2.0 + band_t
    for end, ey in (("car", CAR_END_Y + 0.45), ("weight", WEIGHT_END_Y - 0.45)):
        for tag, tz in (
            ("top", PIVOT_Z + THICK / 2.0 + band_t / 2.0),
            ("bot", PIVOT_Z - THICK / 2.0 - band_t / 2.0),
        ):
            plank_objects.append(
                bk.add_box(
                    f"{MOD_ID}_strap_{end}_{tag}",
                    (0.0, ey, tz),
                    (2 * band_x, 0.55, band_t),
                    steel,
                    bevel=0.008,
                )
            )
        for tag, tx in (("w", -band_x), ("e", band_x)):
            plank_objects.append(
                bk.add_box(
                    f"{MOD_ID}_strap_{end}_{tag}",
                    (tx, ey, PIVOT_Z),
                    (band_side_t, 0.55, 2 * band_half_h),
                    steel,
                    bevel=0.008,
                )
            )
            for bi, bz in enumerate((-0.11, 0.11)):
                plank_objects.append(
                    bk.add_cylinder(
                        f"{MOD_ID}_strap_sidebolt_{end}_{tag}_{bi}",
                        (tx + math.copysign(0.0425, tx), ey, PIVOT_Z + bz),
                        0.04,
                        0.035,
                        steel,
                        vertices=6,
                        axis="X",
                    )
                )
        for bi, bx in enumerate((-1.65, -0.55, 0.55, 1.65)):
            plank_objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_strap_bolt_{end}_{bi}",
                    (bx, ey, PIVOT_Z + band_half_h + 0.013),
                    0.045,
                    0.035,
                    steel,
                    vertices=6,
                )
            )
    # Red under-stringers with cross blocking.
    for tag, sx in (("w", -1.25), ("e", 1.25)):
        plank_objects.append(
            bk.add_box(
                f"{MOD_ID}_stringer_{tag}",
                (sx, PLANK_CENTER_Y, PIVOT_Z - 0.295),
                (0.2, PLANK_LENGTH - 1.4, 0.24),
                red,
                bevel=0.02,
                metric_uv=(1.6, 1.6),
            )
        )
    for bi, by in enumerate((-8.0, -4.0, 4.0, 8.0)):
        plank_objects.append(
            bk.add_box(
                f"{MOD_ID}_blocking_{bi}",
                (0.0, by, PIVOT_Z - 0.295),
                (2.3, 0.2, 0.22),
                red,
                bevel=0.02,
            )
        )
    # Painted bullseye and kicker bands: alpha-cutout DECAL sheets, not
    # geometry (play-test 2026-08-13 round 4: "look like it's painted
    # onto the wood" - even the 4 mm flat discs read as slabs). Only the
    # paint itself renders; it breaks at every board seam, casts no
    # shadow, and the wood shows through the flaked chips. The sheet
    # bottoms sit at the highest board's jittered top; their side and
    # bottom faces park on a transparent texel so no edge ever draws.
    deck_top = PIVOT_Z + THICK / 2
    # A visible 25 cm replaceable impact mat occupies exactly the BOUNDED
    # transfer stroke. The hydraulic force therefore begins when the shoe
    # visibly touches rubber, not while it is suspended above the deck.
    plank_objects.append(
        bk.add_box(
            f"{MOD_ID}_weight_impact_mat",
            (0.0, IMPACT_Y, deck_top + spec.IMPACT_TRANSFER_STROKE / 2.0),
            (2 * HW, 2.35, spec.IMPACT_TRANSFER_STROKE),
            impact_rubber,
            bevel=0.025,
            metric_uv=(1.0, 1.0),
        )
    )
    # The moving weight-end headboard is both visible structure and a direct
    # match for the rubber collision wall in the JBeam.  It keeps the dropped
    # casting engaged through the lever stroke instead of letting it skate off
    # the short end onto the terrain.
    plank_objects.append(
        bk.add_box(
            f"{MOD_ID}_weight_backstop_frame",
            (0.0, BACKSTOP_Y, deck_top + 0.50),
            (2 * HW + 0.16, 0.18, 1.00),
            red,
            bevel=0.025,
        )
    )
    plank_objects.append(
        bk.add_box(
            f"{MOD_ID}_weight_backstop_rubber",
            (0.0, BACKSTOP_Y - 0.105, deck_top + 0.50),
            (2 * HW, 0.04, 0.94),
            impact_rubber,
            bevel=0.015,
            metric_uv=(0.8, 0.8),
        )
    )
    deck_target = materials[f"{MOD_ID}_deck_target"]
    deck_stripes = materials[f"{MOD_ID}_deck_stripes"]
    bull = bk.add_box(
        f"{MOD_ID}_target_decal",
        (0.0, PARK_Y, deck_top + 0.003),
        (2 * HW, 2 * HW, 0.002),
        deck_target,
        bevel=0.0,
    )
    deck_sheet_uv(bull, 2 * HW, 2 * HW, park=(0.5, 0.02))
    plank_objects.append(bull)
    for end, ey in (("car", CAR_END_Y + 1.15), ("weight", WEIGHT_END_Y - 1.15)):
        band = bk.add_box(
            f"{MOD_ID}_plank_end_{end}",
            # The painted band is v 0.1..0.9 of the sheet: 0.875 m of
            # sheet carries the same 0.7 m band the old plates did.
            (0.0, ey, deck_top + 0.003),
            (2 * HW, 0.875, 0.002),
            deck_stripes,
            bevel=0.0,
        )
        deck_sheet_uv(band, 2 * HW, 0.875, park=(0.5, 0.02))
        plank_objects.append(band)
    # (No rubber tip bumpers. A dark 0.22 r puck stuck on the underside
    # of a sunlit plank does not read as rubber - it reads as a hole
    # punched through the boards, which is exactly how the player called
    # it: "the black circle doesn't work here visually". The stringers
    # and blocking already give the underside its structure.)
    parts["plank"] = {"objects": plank_objects, "pivot": (0.0, 0.0, PIVOT_Z)}

    # --- Winch spool + crank: a posable part slaved to cable length in
    # the runtime, so it pays out during the fall and winds back with the
    # crank orbiting as the weight rises (play-test 2026-08-13). Wound
    # cable is a row of near-touching coil tori between the flanges.
    wpx, wpz = WINCH_X, WINCH_Z
    winch_objects = [
        bk.add_cylinder(
            f"{MOD_ID}_winch_drum",
            (wpx, GY, wpz),
            0.28,
            0.7,
            steel,
            vertices=SEG_LARGE,
            axis="X",
        ),
        bk.add_cylinder(
            f"{MOD_ID}_winch_gear",
            (3.2, GY, wpz),
            0.44,
            0.06,
            steel,
            vertices=SEG_LARGE,
            axis="X",
        ),
        bk.add_cylinder(
            f"{MOD_ID}_crank_shaft",
            (3.3, GY, wpz),
            0.04,
            0.26,
            steel,
            vertices=SEG_SMALL,
            axis="X",
        ),
        bk.add_box(
            f"{MOD_ID}_crank_arm",
            (3.4, GY, wpz - 0.21),
            (0.06, 0.09, 0.46),
            steel,
            bevel=0.01,
        ),
        bk.add_cylinder(
            f"{MOD_ID}_crank_grip",
            (3.47, GY, wpz - 0.41),
            0.035,
            0.16,
            target,
            vertices=SEG_SMALL,
            axis="X",
        ),
    ]
    for fx in (2.45, 3.15):
        winch_objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_winch_flange_{int(fx * 100)}",
                (fx, GY, wpz),
                0.42,
                0.05,
                red,
                vertices=SEG_LARGE,
                axis="X",
            )
        )
    for ci in range(9):
        winch_objects.append(
            bk.add_torus(
                f"{MOD_ID}_winch_coil_{ci}",
                (2.51 + ci * 0.0725, GY, wpz),
                WINCH_COIL_R,
                0.034,
                steel,
                rotation=(0.0, math.pi / 2.0, 0.0),
                major_segments=TORUS_MAJOR,
                minor_segments=TORUS_MINOR,
            )
        )
    parts["winch"] = {"objects": winch_objects, "pivot": (wpx, GY, wpz)}

    # --- The ten-ton weight: cast-iron inverted frustum, raised painted
    # lettering, foundry plinth, interlinked shackle under the hook.
    wz = spec.WEIGHT_REST_CENTER_Z
    half_h = 1.3
    bottom_half, top_half = 1.2, 1.7
    slope = math.atan2(top_half - bottom_half, 2 * half_h)
    body = bk.add_cone(
        f"{MOD_ID}_weight_body",
        (0.0, GY, wz),
        bottom_half * math.sqrt(2.0),
        top_half * math.sqrt(2.0),
        2 * half_h,
        materials[f"{MOD_ID}_cast_iron"],
        vertices=4,
        rotation=(0.0, 0.0, math.pi / 4.0),
    )
    # Metric box UVs on the frustum: the primitive cone's default UVs
    # wrapped the whole tile around it and smeared the map (play-test
    # 2026-08-13); the faces are only 11 degrees off axis-aligned, so
    # dominant-axis projection is clean.
    bk.add_metric_box_uvs(body, meters_per_tile=(1.7, 1.7))
    striker_shoe_height = 0.08
    striker_body_height = spec.WEIGHT_STRIKER_DEPTH - striker_shoe_height
    body_bottom_z = wz - spec.WEIGHT_BOTTOM_OFFSET
    weight_objects = [
        body,
        bk.add_box(
            f"{MOD_ID}_weight_plinth",
            (0.0, GY, wz - half_h - 0.08),
            (2.55, 2.55, 0.16),
            iron,
            bevel=0.03,
            metric_uv=(1.4, 1.4),
        ),
        bk.add_box(
            f"{MOD_ID}_weight_striker",
            (0.0, GY, body_bottom_z - striker_body_height / 2.0),
            (2 * HW, 0.70, striker_body_height),
            iron,
            bevel=0.04,
            metric_uv=(1.0, 1.0),
        ),
        bk.add_box(
            f"{MOD_ID}_weight_striker_shoe",
            (
                0.0,
                GY,
                body_bottom_z
                - striker_body_height
                - striker_shoe_height / 2.0,
            ),
            (2 * HW + 0.12, 0.82, striker_shoe_height),
            impact_rubber,
            bevel=0.02,
            metric_uv=(0.7, 0.7),
        ),
        bk.add_box(
            f"{MOD_ID}_weight_cap",
            (0.0, GY, wz + half_h + 0.07),
            (3.6, 3.6, 0.14),
            iron,
            bevel=0.03,
            metric_uv=(1.4, 1.4),
        ),
    ]
    cap_top = wz + half_h + 0.14
    for tag, ly in (("f", -0.15), ("b", 0.15)):
        weight_objects.append(
            bk.add_box(
                f"{MOD_ID}_weight_lug_{tag}",
                (0.0, GY + ly, cap_top + 0.18),
                (0.5, 0.09, 0.4),
                iron,
                bevel=0.02,
            )
        )
    weight_objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_shackle_pin",
            (0.0, GY, cap_top + 0.16),
            0.05,
            0.46,
            steel,
            vertices=SEG_SMALL,
            axis="Y",
        )
    )
    weight_objects.append(
        bk.add_torus(
            f"{MOD_ID}_weight_shackle",
            (0.0, GY, cap_top + 0.42),
            0.26,
            0.075,
            steel,
            rotation=(math.pi / 2.0, 0.0, 0.0),
            major_segments=TORUS_MAJOR,
            minor_segments=TORUS_MINOR,
        )
    )
    # Hook + stem ride WITH the weight (play-test 2026-08-13 round 7:
    # "the latch should follow the weight down ... and have the cable
    # attached" - the hook used to stay latched at the crown while the
    # weight fell bare). Same authored coords as before, so the
    # interlink with the shackle is unchanged at rest; being in this
    # part, they inherit the drop pose every frame.
    weight_objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_hook_stem",
            (0.0, GY, LATCH_Z - 0.05),
            0.05,
            0.14,
            steel,
            vertices=SEG_SMALL,
        )
    )
    weight_objects.append(
        bk.add_torus(
            f"{MOD_ID}_release_hook",
            (0.0, GY, LATCH_Z - 0.29),
            0.3,
            0.08,
            steel,
            rotation=(0.0, math.pi / 2.0, 0.0),
            major_segments=TORUS_MAJOR,
            minor_segments=TORUS_MINOR,
        )
    )
    # Builder's plate riveted to both sloped side faces. (Both earlier
    # mounts - fulcrum pillow blocks, winch pedestal - sat behind the
    # pivot end caps / lattice battens and were eclipsed; the weight's
    # side faces are the one big clean surface, review renders
    # 2026-08-13.)
    for tag, sgn in (("w", -1.0), ("e", 1.0)):
        z_plate = wz - 0.45
        face_off = bottom_half + (z_plate - (wz - half_h)) * math.tan(slope)
        plate = bk.add_box(
            f"{MOD_ID}_patent_plate_{tag}",
            (sgn * (face_off + 0.03), GY, z_plate),
            (0.04, 0.86, 0.5),
            materials[f"{MOD_ID}_plate_legend"],
            bevel=0.0,
            rotation=(0.0, sgn * slope, 0.0),
        )
        plate_face_uv(plate, 0.86, 0.5, "x", sgn)
        weight_objects.append(plate)

    # Raised cast "10 TON" on both sloped road-facing faces. Two solids
    # per line (play-test 2026-08-13 round 6, Titan-plate reference: "the
    # face is painted white, but it's black on the edges"): the letter
    # BODY is bare cast iron at full depth, and a 3 mm white CAP of the
    # same glyphs stacks flush on its front face - so the paint sits only
    # on the face and every extrusion side stays iron.
    for face, flip in (("f", 0.0), ("b", math.pi)):
        y_dir = -1.0 if face == "f" else 1.0
        face_off_main = bottom_half + (2 * half_h * 0.62) * math.tan(slope)
        face_off_sub = bottom_half + (2 * half_h * 0.28) * math.tan(slope)
        # Outward normal of the sloped face for rotation
        # (pi/2 + slope, 0, flip): local +Z lands on this.
        normal = (0.0, y_dir * math.cos(slope), -math.sin(slope))
        for tag, text, cap_h, depth, base_z, face_off, max_w in (
            ("ton", "10 TON", 0.6, 0.06, wz - half_h + 2 * half_h * 0.62, face_off_main, 2.4),
            (
                "brand",
                "ACME FOUNDRY",
                0.17,
                0.045,
                wz - half_h + 2 * half_h * 0.28,
                face_off_sub,
                1.9,
            ),
        ):
            loc = (0.0, GY + y_dir * (face_off + 0.005), base_z)
            weight_objects.append(
                add_text_solid(
                    f"{MOD_ID}_weight_{tag}_{face}",
                    text,
                    cap_h,
                    depth,
                    iron,
                    loc,
                    (math.pi / 2.0 + slope, 0.0, flip),
                    max_width=max_w,
                )
            )
            lift = depth / 2.0 + 0.0015
            weight_objects.append(
                add_text_solid(
                    f"{MOD_ID}_weight_{tag}_face_{face}",
                    text,
                    cap_h,
                    0.003,
                    white,
                    (
                        loc[0] + normal[0] * lift,
                        loc[1] + normal[1] * lift,
                        loc[2] + normal[2] * lift,
                    ),
                    (math.pi / 2.0 + slope, 0.0, flip),
                    max_width=max_w,
                )
            )
    parts["weight"] = {"objects": weight_objects, "pivot": (0.0, GY, wz)}

    # --- Stretching drop cable: pivot at the crown block, geometry
    # hanging down into the hook stem. The runtime scales it along Z by
    # (rest_len + drop) / rest_len every frame (setPartPose grew scale
    # support for exactly this), so the cable visibly pays out of the
    # release housing underside while the drum free-spools. Top end
    # hides inside the housing (z 12.02..12.32); bottom laps 2 cm into
    # the stem so the joint never shows a gap.
    cable = bk.add_cylinder(
        f"{MOD_ID}_drop_cable",
        (0.0, GY, LATCH_Z + 0.125),
        0.04,
        0.25,
        steel,
        vertices=SEG_ROPE,
    )
    parts["cable"] = {"objects": [cable], "pivot": (0.0, GY, LATCH_Z + 0.25)}
    return parts


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    cage.define_beam_spec(
        "plank_rigid",
        # The 100-node deck is much denser than the stock tilt board; 5 MN/m
        # crosses BeamNG's stable local-mode limit here.  Three MN/m is the
        # strongest cold-start-stable value for this topology.
        beamSpring=3000000.0,
        beamDamp=1200.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "weight_rigid",
        beamSpring=8000000.0,
        beamDamp=2000.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "hinge",
        beamSpring=5000000.0,
        beamDamp=1200.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "release_latch",
        beamSpring=5000000.0,
        beamDamp=20000.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "hydraulic_catcher",
        beamSpring=0.0,
        beamDamp=0.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
        beamType="|BOUNDED",
        beamLongBound=20.0,
        beamShortBound=20.0,
        beamLimitSpring=500000.0,
        # A one-metre progressive stroke absorbs the lever's remaining
        # energy without the sharp near-rigid kick of the old 4 MN/m,
        # 25 cm stop. Damping is resolved at each 7 kg plank node, so keep
        # each dashpot below the local explicit-solver stability limit.
        beamLimitDamp=8000.0,
        beamLimitDampRebound=10000.0,
        boundZone=0.20,
    )
    cage.define_beam_spec(
        "rest_hold",
        # A physical parking latch, not a suspension: it keeps the loaded
        # plank at its authored angle without storing preload energy, then
        # breaks with the counterweight release group before the swing.
        beamSpring=3000000.0,
        beamDamp=10000.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "impact_transfer",
        beamSpring=0.0,
        beamDamp=0.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
        beamType="|BOUNDED",
        beamLongBound=20.0,
        beamShortBound=20.0,
        # Five compact accumulators turn part of the 534 kJ gravity impact
        # into useful lever momentum. Their 25 cm stroke matches the visible
        # rubber mat; the separate one-way overhead
        # snubbers arrest the casting's physical rebound after the impulse.
        beamLimitSpring=1000000.0,
        beamLimitDamp=12000.0,
        beamLimitDampRebound=30000.0,
        dampCutoffHz=250.0,
        boundZone=0.08,
    )
    cage.define_beam_spec(
        "rebound_snubber",
        beamSpring=0.0,
        beamDamp=0.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
        beamType="|BOUNDED",
        beamLongBound=20.0,
        beamShortBound=20.0,
        # A nearly springless overhead hydraulic stage is one-way in effect:
        # it offers negligible resistance while the casting descends, then
        # dissipates the upward rebound after impact.  This acts only on the
        # prop's own weight and guide frame.
        beamLimitSpring=1.0,
        beamLimitDamp=30000.0,
        beamLimitDampRebound=200.0,
        dampCutoffHz=250.0,
        boundZone=0.20,
    )
    base = cage.add_box_lattice(
        "base",
        (-2.2, -1.6, 0.0),
        (2.2, 1.6, 0.4),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("north", "south", "east", "west"),
    )
    xs = (-HW, -HW / 2.0, 0.0, HW / 2.0, HW)
    stations = (
        CAR_END_Y,
        PARK_Y,
        -7.2,
        -3.6,
        0.0,
        3.6,
        IMPACT_Y,
        7.2,
        8.0,
        WEIGHT_END_Y,
    )
    layers = (("bottom", -THICK / 2), ("top", THICK / 2))
    plank: dict[tuple[int, int, str], str] = {}
    for j, y in enumerate(stations):
        for i, x in enumerate(xs):
            for layer, normal_offset in layers:
                plank[(i, j, layer)] = cage.add_node(
                    f"plank_{i}_{j}_{layer}",
                    plank_point(x, y, normal_offset),
                    fixed=False,
                    collision=True,
                    self_collision=False,
                    # The five lower impact-rib nodes take the hydraulic
                    # impulse directly.  Matching their 80 kg endpoints to
                    # the 80 kg spreader nodes avoids a one-tick velocity jump
                    # that made the earlier 7 kg receivers chatter or lag.
                    weight=(
                        80.0
                        if y == IMPACT_Y and layer == "bottom"
                        else 7.0
                    ),
                    friction=1.05,
                    node_material="|NM_WOOD",
                    group="plank",
                )

    # Fully triangulated two-layer beam cage.  The old 2x5 plane would fold
    # immediately if merely made dynamic; these cross braces make the board
    # transfer impact as one physical lever while remaining a softbody.
    for j in range(len(stations)):
        for i in range(len(xs) - 1):
            for layer, _ in layers:
                cage.add_beam(
                    plank[(i, j, layer)],
                    plank[(i + 1, j, layer)],
                    "plank_rigid",
                )
            cage.add_beam(
                plank[(i, j, "bottom")],
                plank[(i + 1, j, "top")],
                "plank_rigid",
            )
            cage.add_beam(
                plank[(i, j, "top")],
                plank[(i + 1, j, "bottom")],
                "plank_rigid",
            )
        for i in range(len(xs)):
            cage.add_beam(
                plank[(i, j, "bottom")],
                plank[(i, j, "top")],
                "plank_rigid",
            )
        if j == 0:
            continue
        for i in range(len(xs)):
            for layer, _ in layers:
                cage.add_beam(
                    plank[(i, j - 1, layer)],
                    plank[(i, j, layer)],
                    "plank_rigid",
                )
            cage.add_beam(
                plank[(i, j - 1, "bottom")],
                plank[(i, j, "top")],
                "plank_rigid",
            )
            cage.add_beam(
                plank[(i, j - 1, "top")],
                plank[(i, j, "bottom")],
                "plank_rigid",
            )
        for i in range(len(xs) - 1):
            for layer, _ in layers:
                cage.add_beam(
                    plank[(i, j - 1, layer)],
                    plank[(i + 1, j, layer)],
                    "plank_rigid",
                )
                cage.add_beam(
                    plank[(i + 1, j - 1, layer)],
                    plank[(i, j, layer)],
                    "plank_rigid",
                )
            cage.add_quad(
                [
                    plank[(i, j - 1, "top")],
                    plank[(i + 1, j - 1, "top")],
                    plank[(i + 1, j, "top")],
                    plank[(i, j, "top")],
                ],
                ground_model="rubber" if stations[j - 1] >= 6.0 else "wood",
            )
            cage.add_quad(
                [
                    plank[(i, j, "bottom")],
                    plank[(i + 1, j, "bottom")],
                    plank[(i + 1, j - 1, "bottom")],
                    plank[(i, j - 1, "bottom")],
                ],
                ground_model="wood",
            )

    # A reinforced rubber-faced headboard at the weight end keeps the
    # casting on the moving lever after impact.  With a tilted deck the old
    # flat mat ended only centimetres ahead of the block's leading edge, so
    # the weight simply slid off and finished its fall on the terrain.
    backstop_station = stations.index(WEIGHT_END_Y)
    backstop_upper: dict[int, str] = {}
    for i, x in enumerate(xs):
        backstop_upper[i] = cage.add_node(
            f"plank_backstop_{i}",
            plank_point(x, BACKSTOP_Y, THICK / 2 + 1.0),
            fixed=False,
            collision=True,
            self_collision=False,
            weight=5.0,
            friction=1.1,
            node_material="|NM_RUBBER",
            group="plank",
        )
        cage.add_beam(
            plank[(i, backstop_station, "top")],
            backstop_upper[i],
            "plank_rigid",
        )
        cage.add_beam(
            plank[(i, backstop_station, "bottom")],
            backstop_upper[i],
            "plank_rigid",
        )
        if i == 0:
            continue
        cage.add_beam(backstop_upper[i - 1], backstop_upper[i], "plank_rigid")
        cage.add_beam(
            plank[(i - 1, backstop_station, "top")],
            backstop_upper[i],
            "plank_rigid",
        )
        cage.add_beam(
            plank[(i, backstop_station, "top")],
            backstop_upper[i - 1],
            "plank_rigid",
        )
        cage.add_quad(
            [
                plank[(i - 1, backstop_station, "top")],
                plank[(i, backstop_station, "top")],
                backstop_upper[i],
                backstop_upper[i - 1],
            ],
            ground_model="rubber",
        )

    # Stock-style shared collinear hinge nodes. Each pin is fixed to the
    # grounded trestle and connected radially to the plank's top/bottom
    # pivot section. Beam joints preserve radius but allow free rotation
    # about X; there is no hydro, prescribed angle, or overconstrained rail.
    hinge_pin: dict[int, str] = {}
    pivot_station = stations.index(0.0)
    for i, x in enumerate(xs):
        hinge_pin[i] = cage.add_node(
            f"plank_hinge_{i}",
            (x, 0.0, PIVOT_Z),
            fixed=True,
            collision=False,
            weight=250.0,
            group="plank",
        )
        for layer, _ in layers:
            cage.add_beam(hinge_pin[i], plank[(i, pivot_station, layer)], "hinge")
        if i > 0:
            cage.add_beam(hinge_pin[i - 1], hinge_pin[i], "hinge")
    for i in range(len(xs)):
        base_x = min(2, round(i * 2 / (len(xs) - 1)))
        cage.add_beam(hinge_pin[i], base[(base_x, 1, 1)], "hinge")
    cage.add_beam(hinge_pin[0], base[(0, 0, 1)], "hinge")
    cage.add_beam(hinge_pin[len(xs) - 1], base[(2, 2, 1)], "hinge")

    # Gantry posts as slim collidable towers. Widened in y (0.6 -> 2.0)
    # for the Acme redesign: the battered lattice chords spread to
    # GY +- ~0.98 at the shoes, and the collision tower must cover the
    # steel a bumper can actually reach.
    posts = {}
    for side, sx in (("l", -CHORD_X), ("r", CHORD_X)):
        posts[side] = cage.add_box_lattice(
            f"post_{side}",
            (sx - 0.35, GY - 1.0, 0.0),
            (sx + 0.35, GY + 1.0, GTZ),
            subdivisions=(1, 1, 2),
            fixed=True,
            collision=False,
            collision_faces=("north", "south", "east", "west"),
        )
        base_x = 0 if side == "l" else 2
        cage.add_beam(posts[side][(0, 0, 0)], base[(base_x, 2, 0)], "hinge")
        cage.add_beam(posts[side][(1, 0, 0)], base[(base_x, 2, 1)], "hinge")
        cage.add_beam(posts[side][(0, 1, 0)], base[(base_x, 1, 0)], "hinge")
        cage.add_beam(posts[side][(1, 1, 0)], base[(base_x, 1, 1)], "hinge")
    cage.add_beam(posts["l"][(1, 0, 2)], posts["r"][(0, 0, 2)])
    cage.add_beam(posts["l"][(1, 1, 2)], posts["r"][(0, 1, 2)])

    # A dense 5x5x3 truncated-pyramid cage spreads the 9,070 kg casting over
    # 75 moderate-mass nodes.  The old eight 4,995 kg corners struck the deck
    # like spring-loaded point hammers and are the main reason the 40-ton
    # prototype bounced instead of transferring its energy.
    weight: dict[tuple[int, int, int], str] = {}
    weight_layers = (
        (spec.WEIGHT_REST_CENTER_Z - spec.WEIGHT_BOTTOM_OFFSET, 1.275),
        (spec.WEIGHT_REST_CENTER_Z, 1.45),
        (spec.WEIGHT_REST_CENTER_Z + 1.44, 1.8),
    )
    weight_grid = range(5)
    hook_mass = 40.0
    striker_node_mass = 80.0
    weight_node_mass = (
        spec.COUNTERWEIGHT_MASS_KG - hook_mass - 5.0 * striker_node_mass
    ) / 75.0
    for iz, (z, half) in enumerate(weight_layers):
        for ix in weight_grid:
            x = half * (-1.0 + ix / 2.0)
            for iy in weight_grid:
                y = GY + half * (-1.0 + iy / 2.0)
                boundary = iz in (0, 2) or ix in (0, 4) or iy in (0, 4)
                bottom_contact = iz == 0
                weight[(ix, iy, iz)] = cage.add_node(
                    f"weight_{ix}_{iy}_{iz}",
                    (x, y, z),
                    fixed=False,
                    collision=boundary,
                    self_collision=bottom_contact,
                    weight=weight_node_mass,
                    friction=1.1,
                    node_material="|NM_RUBBER" if bottom_contact else "|NM_METAL",
                    group="weight",
                )

    # 26-neighbour local bracing gives every cell face and body diagonals
    # without the numerically hostile all-to-all beams of the eight-node box.
    for iz in weight_grid[:3]:
        for ix in weight_grid:
            for iy in weight_grid:
                first = weight[(ix, iy, iz)]
                for dz in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            if (dz, dx, dy) <= (0, 0, 0):
                                continue
                            nz, nx, ny = iz + dz, ix + dx, iy + dy
                            if nz not in range(3) or nx not in range(5) or ny not in range(5):
                                continue
                            cage.add_beam(first, weight[(nx, ny, nz)], "weight_rigid")

    # A full-width central spreader is the casting's first physical contact.
    # Raising the broad plinth by the same 0.75 m leaves the shoe exactly six
    # metres above the target. Its five nodes align one-to-one with the heavy
    # structural impact rib, eliminating diagonal force loss.
    striker: dict[int, str] = {}
    for ix in weight_grid:
        x = xs[ix]
        striker[ix] = cage.add_node(
            f"weight_striker_{ix}",
            (x, GY, spec.WEIGHT_BOTTOM_REST_Z),
            fixed=False,
            collision=True,
            self_collision=True,
            weight=striker_node_mass,
            friction=1.1,
            node_material="|NM_RUBBER",
            group="weight",
        )
        for iy in (1, 2, 3):
            cage.add_beam(striker[ix], weight[(ix, iy, 0)], "weight_rigid")
        if ix > 0:
            cage.add_beam(striker[ix - 1], striker[ix], "weight_rigid")
    # The straight crossbar and same-column fan leave one first-order rack
    # mode. Two symmetric diagonals triangulate the full-width spreader into
    # the casting without adding any world or deck constraint.
    cage.add_beam(striker[0], weight[(2, 2, 0)], "weight_rigid")
    cage.add_beam(striker[4], weight[(2, 2, 0)], "weight_rigid")

    # Five no-force bounded pushrods model the visible rubber impact mat. They
    # remain slack through the six-metre fall, then compress over the mat's
    # final 25 cm. Each rod terminates directly on one heavy lower-rib node:
    # there is no auxiliary linkage that can run ahead of, or bypass, the arm.
    impact_station = stations.index(IMPACT_Y)
    receiver_local_y = IMPACT_Y
    receiver_normal_offset = spec.IMPACT_RECEIVER_NORMAL_OFFSET
    for ix in weight_grid:
        weight_x = xs[ix]
        weight_spawn = (weight_x, GY, spec.WEIGHT_BOTTOM_REST_Z)
        plank_spawn = plank_point(
            weight_x, receiver_local_y, receiver_normal_offset
        )
        spawned_length = math.dist(weight_spawn, plank_spawn)
        weight_at_contact = (
            weight_x,
            GY,
            spec.SURFACE_REST_AT_WEIGHT,
        )
        contact_length = math.dist(weight_at_contact, plank_spawn)
        activation_length = contact_length + spec.IMPACT_TRANSFER_STROKE
        cage.add_beam(
            striker[ix],
            plank[(ix, impact_station, "bottom")],
            "impact_transfer",
            extra={
                "shortBoundRange": spawned_length - activation_length,
                "longBoundRange": 20.0,
            },
        )
    hook = cage.add_node(
        "weight_hook",
        (0.0, GY, LATCH_Z),
        fixed=False,
        collision=False,
        weight=hook_mass,
        group="weight",
    )
    for ix, iy in ((0, 0), (0, 4), (2, 2), (4, 0), (4, 4)):
        cage.add_beam(hook, weight[(ix, iy, 2)], "weight_rigid")

    # Fully tiled exterior. The rubber bottom works with the visible impact
    # mat to suppress a second hard bounce while all motion remains contact.
    for ix in range(4):
        for iy in range(4):
            cage.add_quad(
                [
                    weight[(ix, iy + 1, 0)],
                    weight[(ix + 1, iy + 1, 0)],
                    weight[(ix + 1, iy, 0)],
                    weight[(ix, iy, 0)],
                ],
                ground_model="rubber",
            )
            cage.add_quad(
                [
                    weight[(ix, iy, 2)],
                    weight[(ix + 1, iy, 2)],
                    weight[(ix + 1, iy + 1, 2)],
                    weight[(ix, iy + 1, 2)],
                ],
                ground_model="metal",
            )
    for iz in range(2):
        for i in range(4):
            cage.add_quad(
                [
                    weight[(i, 0, iz)],
                    weight[(i + 1, 0, iz)],
                    weight[(i + 1, 0, iz + 1)],
                    weight[(i, 0, iz + 1)],
                ],
                ground_model="metal",
            )
            cage.add_quad(
                [
                    weight[(i + 1, 4, iz)],
                    weight[(i, 4, iz)],
                    weight[(i, 4, iz + 1)],
                    weight[(i + 1, 4, iz + 1)],
                ],
                ground_model="metal",
            )
            cage.add_quad(
                [
                    weight[(0, i + 1, iz)],
                    weight[(0, i, iz)],
                    weight[(0, i, iz + 1)],
                    weight[(0, i + 1, iz + 1)],
                ],
                ground_model="metal",
            )
            cage.add_quad(
                [
                    weight[(4, i, iz)],
                    weight[(4, i + 1, iz)],
                    weight[(4, i + 1, iz + 1)],
                    weight[(4, i, iz + 1)],
                ],
                ground_model="metal",
            )

    latch_l = cage.add_node(
        "latch_l", (-0.18, GY, LATCH_Z + 0.25), fixed=True, collision=False, weight=80.0
    )
    latch_r = cage.add_node(
        "latch_r", (0.18, GY, LATCH_Z + 0.25), fixed=True, collision=False, weight=80.0
    )
    latch_center = cage.add_node(
        "latch_center",
        (0.0, GY, LATCH_Z),
        fixed=True,
        collision=False,
        weight=80.0,
    )
    cage.add_beam(latch_l, latch_r, "hinge")
    cage.add_beam(latch_center, latch_l, "hinge")
    cage.add_beam(latch_center, latch_r, "hinge")
    cage.add_beam(latch_l, posts["l"][(1, 1, 2)], "hinge")
    cage.add_beam(latch_r, posts["r"][(0, 1, 2)], "hinge")
    # BeamNG couplers do not attach nodes that already belong to the same
    # vehicle object.  Two physical latch links therefore suspend the
    # casting until vehicle Lua breaks their shared group.  They act only on
    # the weight, never on the subject vehicle, and a physics reset restores
    # them for the next launch.
    for latch in (latch_l, latch_r):
        cage.add_beam(
            hook,
            latch,
            "release_latch",
            extra={"breakGroup": "catapult_weight_release"},
        )

    # The casting runs in a fixed vertical guide, as a real industrial drop
    # weight would. Two collinear slider nodes stop the cage skating off the
    # tilted lever while leaving its Z motion entirely to gravity, impact,
    # and the plank. The low cap is only a ground-strike failsafe.
    guide_nodes: list[str] = []
    for index, z in enumerate((0.5, 8.0, 14.0, 18.0, GTZ)):
        guide_node = cage.add_node(
            f"weight_guide_{index}",
            (0.0, GY, z),
            fixed=True,
            collision=False,
            weight=80.0,
        )
        guide_nodes.append(guide_node)
        if index > 0:
            cage.add_beam(guide_nodes[index - 1], guide_node, "hinge")
    cage.add_beam(guide_nodes[0], base[(1, 2, 1)], "hinge")
    cage.add_beam(guide_nodes[-1], posts["l"][(1, 1, 2)], "hinge")
    cage.add_beam(guide_nodes[-1], posts["r"][(0, 1, 2)], "hinge")

    # Five guide-head rebound arrestors remain outside their long bound for
    # the full six-metre free fall.  Past 6.5 m they pay out almost freely on
    # descent, but their compression damping absorbs the casting's upward
    # bounce instead of sending it through a second impact cycle.
    snubber_anchors: list[str] = []
    _, top_half = weight_layers[2]
    for ix in weight_grid:
        x = top_half * (-1.0 + ix / 2.0)
        # The centre arrestor shares the existing guide-head node. Creating a
        # second coincident fixed node and tying them together emitted a
        # zero-length beam warning on every spawn.
        anchor = (
            guide_nodes[-1]
            if ix == 2
            else cage.add_node(
                f"weight_snubber_anchor_{ix}",
                (x, GY, GTZ),
                fixed=True,
                collision=False,
                weight=80.0,
            )
        )
        snubber_anchors.append(anchor)
        cage.add_beam(
            anchor,
            weight[(ix, 2, 2)],
            "rebound_snubber",
            extra={"longBoundRange": 6.5, "shortBoundRange": 20.0},
        )
        if ix > 0:
            cage.add_beam(snubber_anchors[ix - 1], anchor, "hinge")
    cage.add_beam(snubber_anchors[0], posts["l"][(1, 1, 2)], "hinge")
    cage.add_beam(snubber_anchors[-1], posts["r"][(0, 1, 2)], "hinge")

    guide_name = f"{MOD_ID}_weight_guide"
    cage.add_rail(guide_name, guide_nodes, capped=True)
    for slider in (weight[(2, 2, 0)], hook):
        cage.add_slidenode(
            slider,
            guide_name,
            tolerance=0.01,
            spring=10001000.0,
            strength="FLT_MAX",
            cap_strength="FLT_MAX",
        )

    # Entry ramp up to the plank's low end.
    ramp_l = cage.add_node(
        "ramp_ground_l", (-HW, spec.RAMP_GROUND_Y, 0.0), fixed=True, collision=True
    )
    ramp_r = cage.add_node(
        "ramp_ground_r", (HW, spec.RAMP_GROUND_Y, 0.0), fixed=True, collision=True
    )
    car_top_l = plank_point(-HW, CAR_END_Y, THICK / 2)
    car_top_r = plank_point(HW, CAR_END_Y, THICK / 2)
    ramp_top_l = cage.add_node(
        "ramp_top_l",
        (car_top_l[0], car_top_l[1] - 0.10, car_top_l[2]),
        fixed=True,
        collision=True,
    )
    ramp_top_r = cage.add_node(
        "ramp_top_r",
        (car_top_r[0], car_top_r[1] - 0.10, car_top_r[2]),
        fixed=True,
        collision=True,
    )
    cage.add_beam(ramp_l, ramp_r)
    cage.add_beam(ramp_top_l, ramp_top_r)
    cage.add_beam(ramp_l, base[(0, 0, 0)])
    cage.add_beam(ramp_r, base[(2, 0, 0)])
    cage.add_beam(ramp_top_l, base[(0, 0, 1)])
    cage.add_beam(ramp_top_r, base[(2, 0, 1)])
    cage.add_quad(
        [ramp_l, ramp_r, ramp_top_r, ramp_top_l],
        ground_model="asphalt",
    )

    # BeamNG-native hydraulic bump stops hold the unladen board quietly at
    # its rest angle and catch it progressively at -32 degrees.  They exert
    # no spring or damping force through the free stroke; the limit fields
    # engage only at the two endpoints.  Five parallel units distribute the
    # load across the reinforced width rows.
    car_end_station = stations.index(CAR_END_Y)
    rest_station = stations.index(PARK_Y)
    catcher_station = stations.index(8.0)
    rest_stop_center = plank_point_at_angle(0.0, PARK_Y, -THICK / 2, REST)
    fling_stop_center = plank_point_at_angle(0.0, 8.0, -THICK / 2, FLING_STOP)
    tip_latch_anchors: dict[int, str] = {}
    impact_latch_anchors: dict[int, str] = {}
    for i, x in enumerate(xs):
        # The parked car straddles the 2.7 m overhang beyond PARK_Y.  A
        # second row of temporary ramp latches prevents that cantilever from
        # flexing visibly while the countdown runs.  The diagonal link has
        # first-order vertical stiffness; a horizontal tether would not.
        tip_top = plank_point_at_angle(x, CAR_END_Y, THICK / 2, REST)
        tip_latch_anchors[i] = cage.add_node(
            f"tip_latch_anchor_{i}",
            (x, tip_top[1] - 0.25, tip_top[2] - 0.25),
            fixed=True,
            collision=False,
            weight=80.0,
        )
        cage.add_beam(
            tip_latch_anchors[i],
            plank[(i, car_end_station, "top")],
            "rest_hold",
            extra={"breakGroup": "catapult_weight_release"},
        )
        if i > 0:
            cage.add_beam(tip_latch_anchors[i - 1], tip_latch_anchors[i], "hinge")

        rest_point = plank_point_at_angle(x, PARK_Y, -THICK / 2, REST)
        rest_anchor_position = (x, rest_point[1], max(0.05, rest_point[2] - 0.72))
        rest_anchor = cage.add_node(
            f"rest_catcher_anchor_{i}",
            rest_anchor_position,
            fixed=True,
            collision=False,
            weight=80.0,
        )
        cage.add_beam(rest_anchor, base[(1, 0, 0)], "hinge")
        cage.add_beam(
            rest_anchor,
            plank[(i, rest_station, "bottom")],
            "rest_hold",
            extra={
                "breakGroup": "catapult_weight_release",
            },
        )

        # Clamp the heavy impact rib as well as the loaded car arm during the
        # countdown. These exact-rest, zero-preload transport latches remove
        # the weight-side bending mode that otherwise made the 22 m deck rock
        # by about a degree. They break in the same physical release group and
        # exert no force during the throw.
        impact_point = plank_point_at_angle(x, IMPACT_Y, -THICK / 2, REST)
        impact_latch_anchors[i] = cage.add_node(
            f"impact_latch_anchor_{i}",
            (x, impact_point[1], impact_point[2] - 0.72),
            fixed=True,
            collision=False,
            weight=80.0,
        )
        cage.add_beam(impact_latch_anchors[i], base[(1, 2, 1)], "hinge")
        cage.add_beam(
            impact_latch_anchors[i],
            plank[(i, impact_station, "bottom")],
            "rest_hold",
            extra={"breakGroup": "catapult_weight_release"},
        )
        if i > 0:
            cage.add_beam(
                impact_latch_anchors[i - 1],
                impact_latch_anchors[i],
                "hinge",
            )

        spawn_point = plank_point_at_angle(x, 8.0, -THICK / 2, REST)
        target_point = plank_point_at_angle(x, 8.0, -THICK / 2, FLING_STOP)
        fling_anchor_position = (x, target_point[1], 0.05)
        spawned_length = math.dist(spawn_point, fling_anchor_position)
        # Begin a one-metre progressive stroke before the authored -32-degree
        # stop. The longer, softer catch dissipates the same order of energy
        # without hammering the car nearly straight upward at the endpoint.
        target_length = math.dist(target_point, fling_anchor_position)
        activation_length = target_length + 1.0
        fling_anchor = cage.add_node(
            f"fling_catcher_anchor_{i}",
            fling_anchor_position,
            fixed=True,
            collision=False,
            weight=80.0,
        )
        cage.add_beam(fling_anchor, base[(1, 2, 0)], "hinge")
        cage.add_beam(
            fling_anchor,
            plank[(i, catcher_station, "bottom")],
            "hydraulic_catcher",
            extra={
                "shortBoundRange": spawned_length - activation_length,
                "longBoundRange": 20.0,
            },
        )
    cage.add_beam(tip_latch_anchors[0], ramp_top_l, "hinge")
    cage.add_beam(tip_latch_anchors[len(xs) - 1], ramp_top_r, "hinge")

    # Wide rubber-faced quads sit 11 cm beyond each hydraulic limit as a
    # fail-safe only.  Unlike the old narrow pads, every outer plank row
    # actually overlaps these collision surfaces.
    def add_stop(prefix: str, y: float, z: float) -> list[str]:
        corners = [
            cage.add_node(
                f"{prefix}_{tag}",
                (x, sy, z),
                fixed=True,
                collision=True,
                self_collision=True,
                weight=180.0,
            )
            for tag, x, sy in (
                ("sw", -(HW + 0.2), y - 0.42),
                ("se", HW + 0.2, y - 0.42),
                ("ne", HW + 0.2, y + 0.42),
                ("nw", -(HW + 0.2), y + 0.42),
            )
        ]
        cage.add_quad(corners, ground_model="rubber")
        cage.add_beam(corners[0], corners[1], "hinge")
        cage.add_beam(corners[1], corners[2], "hinge")
        cage.add_beam(corners[2], corners[3], "hinge")
        cage.add_beam(corners[3], corners[0], "hinge")
        cage.add_beam(corners[0], corners[2], "hinge")
        cage.add_beam(corners[1], corners[3], "hinge")
        for corner in corners:
            cage.add_beam(corner, base[(1, 1, 0)], "hinge")
        return corners

    add_stop("rest_stop", rest_stop_center[1], rest_stop_center[2] - 0.11)
    add_stop("fling_stop", fling_stop_center[1], fling_stop_center[2] - 0.11)

    cage.set_refnodes_existing(
        ref=base[(1, 1, 0)],
        back=base[(1, 0, 0)],
        left=base[(0, 1, 0)],
        up=base[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            ramp_l,
            ramp_r,
            plank[(0, len(stations) - 1, "top")],
            plank[(len(xs) - 1, len(stations) - 1, "top")],
            posts["l"][(0, 0, 2)],
            posts["l"][(0, 1, 2)],
            posts["r"][(1, 0, 2)],
            posts["r"][(1, 1, 2)],
        ]
    )
    cage.auto_base_nodes()
    return cage


def main() -> None:
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)
    part_builds = build_parts(materials)

    plank_build = part_builds.pop("plank")
    weight_build = part_builds.pop("weight")
    rotate_about_plank_axle(plank_build["objects"])

    parts = []
    for name, build in sorted(part_builds.items()):
        dae_path = VEHICLE_DIR / f"{MOD_ID}_{name}.dae"
        info = bk.export_part_shape(MOD_ID, name, dae_path, build["objects"], build["pivot"])
        info["path"] = f"vehicles/{MOD_ID}/{MOD_ID}_{name}.dae"
        parts.append(info)

    visual = bk.export_multi_flexbody(
        MOD_ID,
        VEHICLE_DIR / PHYSICS_VISUAL_DAE_NAME,
        {
            f"{MOD_ID}_visual": visual_objects,
            f"{MOD_ID}_plank_mesh": plank_build["objects"],
            f"{MOD_ID}_weight_mesh": weight_build["objects"],
        },
    )

    cage = build_cage()
    behavior = dict(spec.BEHAVIOR)
    bk.write_handoff(
        AUTHORING_ROOT / f"{MOD_ID}.handoff.json",
        mod_id=MOD_ID,
        display_name=spec.DISPLAY_NAME,
        cage=cage,
        visual=visual,
        visual_dae_relative=f"vehicles/{MOD_ID}/{PHYSICS_VISUAL_DAE_NAME}",
        visual_mesh_name=f"{MOD_ID}_visual",
        parts=parts,
        palette=spec.PALETTE,
        behavior={
            "tunables": behavior,
            "triggers": spec.TRIGGERS,
            "effects": spec.EFFECTS,
            "camera_distance": behavior.get("camera_distance", 30.0),
        },
        flexbodies_extra=[
            {"mesh": f"{MOD_ID}_plank_mesh", "groups": ["plank"]},
            {"mesh": f"{MOD_ID}_weight_mesh", "groups": ["weight"]},
        ],
    )
    # Selector picture. The old camera sat 35 m out and left the machine
    # small in an empty grey field. This one is near-broadside so the
    # plank runs ACROSS the frame with the bullseye readable, the gantry
    # and its sign stack up on the right, and the ramp's chevrons just
    # enter bottom-left. The raised physical redesign reaches about 19 m,
    # so this wider view keeps both the ground-contacting ramp and sign.
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(31.0, -25.0, 13.0),
        look_at=(-1.2, -2.5, 9.2),
    )
    print(f"CATAPULT_SEESAW generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
