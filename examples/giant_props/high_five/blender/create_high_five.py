"""Deterministic Blender generator for Charlie's High Five.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/high_five/blender/create_high_five.py

Everything about the hand lives in ``hand_sculpt.py``; this file owns the
machine that swings it, the console that aims it, and the handoff.
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
sys.path.insert(0, str(SCRIPT_PATH.parent))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import hand_sculpt  # noqa: E402
import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

TWO_PI = 2.0 * math.pi
UP = Vector((0.0, 0.0, 1.0))
U = Vector(spec.U_REST)
N = Vector(spec.N_REST)
#: Toward the THUMB. The mould splits on the silhouette, which in the
#: hand's own frame is +/-V — so this is the axis a parting line has to be
#: photographed along, and until the ulnar_edge camera below there was no
#: view in the review set that could show one.
V = Vector(spec.V_REST)
MAST = Vector((spec.MAST_X, spec.MAST_Y, 0.0))
HUB = Vector((spec.MAST_X, spec.MAST_Y, spec.HUB_Z))
WRIST = Vector(spec.WRIST_POINT)

# Arm frames. E2 is the horizontal sweep tangent — the direction the palm
# faces — and is shared by both members. (A1, A3) span the upper arm plane and
# (F1, F3) the forearm plane. Every structural part is authored in these
# numbers rather than in world coordinates, so re-pitching the arm is one
# constant in spec.py and not a hundred rewritten boxes.
ELBOW = Vector(
    (spec.MAST_X + spec.ELBOW_R * U.x, spec.MAST_Y + spec.ELBOW_R * U.y, spec.ELBOW_Z)
)
#: lateral axis, shared by both members: the direction the palm faces
E2 = N.copy()
#: upper arm, hub -> elbow
A1 = (ELBOW - HUB).normalized()
A3 = A1.cross(E2).normalized()
# Horizontal unit vector from the mast axis toward the elbow: the radial
# direction the knee sits along.
U_RADIAL = Vector((ELBOW.x - HUB.x, ELBOW.y - HUB.y, 0.0)).normalized()
#: forearm, elbow -> wrist
F1 = (WRIST - ELBOW).normalized()
F3 = F1.cross(E2).normalized()

# The unswept sector. The arm sweeps REST_DEG -> FOLLOW_DEG, so everything
# fixed and tall — ladder, guy chains, anchors — is put on the far side of
# the mast where the boom provably never goes.
SAFE_AZIMUTH = 180.0


def azimuth_point(degrees: float, radius: float, z: float) -> Vector:
    angle = math.radians(degrees)
    return Vector(
        (spec.MAST_X + radius * math.cos(angle), spec.MAST_Y + radius * math.sin(angle), z)
    )


# ---------------------------------------------------------------------------
# Generic mesh helpers
# ---------------------------------------------------------------------------


def add_loft(name, rings, material, *, uv_scale=(1.0, 1.0), cap_start=True, cap_end=True):
    """Bridge equal-length rings into a shell, with metric-ish UVs.

    Rings carry a duplicated seam column exactly like the hand's grids, for
    the same reason: a shared seam vertex forces one face to sample the map
    backwards and smears it.
    """

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    verts = [[bm.verts.new(point) for point in ring] for ring in rings]
    bm.verts.ensure_lookup_table()
    # index_update, not just ensure_lookup_table: a freshly created BMVert
    # carries index -1 until this runs, so a degeneracy test written against
    # .index silently rejected EVERY face and exported a mesh of nothing but
    # its end caps.
    bm.verts.index_update()

    columns = len(rings[0])
    lengths = [0.0]
    for lower, upper in zip(rings, rings[1:]):
        a = sum(lower[:-1], Vector()) / max(1, len(lower) - 1)
        b = sum(upper[:-1], Vector()) / max(1, len(upper) - 1)
        lengths.append(lengths[-1] + (b - a).length)

    perimeter = 0.0
    for a, b in zip(rings[0], rings[0][1:]):
        perimeter += (b - a).length
    perimeter = max(perimeter, 1e-4)

    for row in range(len(verts) - 1):
        for column in range(columns - 1):
            corners = (
                verts[row][column],
                verts[row + 1][column],
                verts[row + 1][column + 1],
                verts[row][column + 1],
            )
            # Pole rings collapse several columns onto one point; those faces
            # are zero-area on one edge and legal (it is how a UV sphere
            # closes). Only a face that reuses the SAME vertex is dropped.
            if len({corner.index for corner in corners}) < 3:
                continue
            try:
                face = bm.faces.new(corners)
            except ValueError:
                continue
            for loop, (ci, ri) in zip(
                face.loops,
                ((column, row), (column, row + 1), (column + 1, row + 1), (column + 1, row)),
            ):
                loop[uv_layer].uv = (
                    perimeter * (ci / (columns - 1)) / uv_scale[0],
                    lengths[ri] / uv_scale[1],
                )

    def cap(ring_verts, flip):
        unique = []
        for vertex in ring_verts[:-1]:
            if vertex not in unique:
                unique.append(vertex)
        if len(unique) < 3:
            return
        try:
            face = bm.faces.new(tuple(reversed(unique)) if flip else tuple(unique))
        except ValueError:
            return
        for loop in face.loops:
            loop[uv_layer].uv = (
                loop.vert.co.x / uv_scale[0], loop.vert.co.y / uv_scale[1]
            )
        bmesh.ops.triangulate(bm, faces=[face])

    if cap_start:
        cap(verts[0], True)
    if cap_end:
        cap(verts[-1], False)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        mesh.materials.append(material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def rounded_rect_ring(centre, ex, ey, half_x, half_y, radius, segments=6):
    """Closed loop of a rounded rectangle in the (ex, ey) plane.

    Structural steel has radiused corners because plate is bent, not
    mitred, and a 3 m column with knife edges reads as cardboard.
    """

    radius = min(radius, half_x * 0.95, half_y * 0.95)
    ix, iy = half_x - radius, half_y - radius
    points = []
    corners = ((ix, iy, 0.0), (-ix, iy, 90.0), (-ix, -iy, 180.0), (ix, -iy, 270.0))
    for cx, cy, start in corners:
        for step in range(segments + 1):
            angle = math.radians(start + 90.0 * step / segments)
            points.append(
                centre + ex * (cx + radius * math.cos(angle)) + ey * (cy + radius * math.sin(angle))
            )
    points.append(points[0])
    return points


def ellipse_ring(centre, ex, ey, half_x, half_y, segments=48):
    """Closed elliptical loop in the (ex, ey) plane, seam column duplicated."""

    points = [
        centre + ex * (half_x * math.cos(TWO_PI * step / segments))
        + ey * (half_y * math.sin(TWO_PI * step / segments))
        for step in range(segments)
    ]
    points.append(points[0])
    return points


def add_tapered_column(
    name, base, axis, height, base_half, top_half, material, *, corner=0.14, uv=1.0
):
    """Rounded-square frustum along ``axis``."""

    ex = Vector((1.0, 0.0, 0.0)) if abs(axis.z) > 0.5 else UP.cross(axis).normalized()
    ex = (ex - axis * ex.dot(axis)).normalized()
    ey = axis.cross(ex).normalized()
    rings = []
    stations = 10
    for step in range(stations + 1):
        t = step / stations
        half = base_half + (top_half - base_half) * t
        centre = base + axis * (height * t)
        rings.append(rounded_rect_ring(centre, ex, ey, half, half, corner * (half / base_half)))
    return add_loft(name, rings, material, uv_scale=(uv, uv))


def add_gusset(name, apex, corner_a, corner_b, thickness, direction, material):
    """A triangular stiffener plate as a swept prism."""

    normal = direction.normalized() * (thickness / 2.0)
    front = [apex + normal, corner_a + normal, corner_b + normal]
    back = [apex - normal, corner_a - normal, corner_b - normal]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    fv = [bm.verts.new(point) for point in front]
    bv = [bm.verts.new(point) for point in back]
    faces = [
        (fv[0], fv[1], fv[2]),
        (bv[2], bv[1], bv[0]),
        (fv[0], bv[0], bv[1], fv[1]),
        (fv[1], bv[1], bv[2], fv[2]),
        (fv[2], bv[2], bv[0], fv[0]),
    ]
    for corners in faces:
        try:
            face = bm.faces.new(corners)
        except ValueError:
            continue
        for loop in face.loops:
            loop[uv_layer].uv = (loop.vert.co.x * 0.9, loop.vert.co.z * 0.9)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        mesh.materials.append(material)
    return obj


def _orient(obj, axis):
    """Point a Z-built primitive along ``axis`` and bake it into the mesh."""

    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = UP.rotation_difference(axis.normalized())
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    obj.select_set(False)
    return obj


def _pin(name, centre, radius, length, material):
    """A through-pin lying along the lateral axis E2."""

    pin = bk.add_cylinder(
        name, (centre.x, centre.y, centre.z), radius, length, material,
        vertices=32, axis="Z", metric_uv=(2.0 * math.pi * radius, 0.6),
    )
    return _orient(pin, E2)


def add_bolt(name, centre, normal, radius, material, *, proud=None):
    """One hex bolt head standing proud of a plate. Exposed fasteners are
    the whole visual language of the reference rigging stand, so they are
    real geometry, not a texture."""

    proud = proud if proud is not None else radius * 0.62
    axis = {
        "Z": (0.0, 0.0, 0.0),
        "X": (0.0, math.pi / 2.0, 0.0),
        "Y": (math.pi / 2.0, 0.0, 0.0),
    }
    direction = normal.normalized()
    rotation = Vector((0.0, 0.0, 1.0)).rotation_difference(direction).to_euler()
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=6,
        radius=radius,
        depth=proud,
        location=centre + direction * (proud / 2.0),
        rotation=rotation,
    )
    obj = bpy.context.object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    _ = axis
    return bk._finish_primitive(obj, name, material, radius * 0.12)


def add_chain(name, start, end, material, link_radius, wire_radius, *,
              stretch=1.55, sag=0.0):
    """A run of chain as alternating quarter-turn torus links.

    The link COUNT is derived from the span, never passed in. Authored by
    hand it was 7 links over a 7 m run, which spaced 0.59 m links 1.0 m
    apart: the guy chains rendered as a dotted line of loose rings hanging
    in the air, which reads as broken geometry rather than as a chain.
    Real links interlock, so consecutive links must overlap — pitch is
    0.70 of a link's own length.
    """

    objects = []
    span = end - start
    length = span.length
    if length < 1e-4:
        return objects
    link_length = 2.0 * link_radius * stretch
    links = max(3, int(round(length / (link_length * 0.70))))
    step = span / links
    direction = span.normalized()

    # SAG. A taut guy is a rod that happens to be drawn as links; the
    # reference stand's chains are utility slack. `sag` is the midpoint
    # dip as a fraction of the run, applied as a parabola — close enough
    # to a catenary at these ratios that nobody standing under an 8.6 m
    # hand will take out a theodolite.
    def dip(fraction):
        return UP * (-4.0 * sag * length * fraction * (1.0 - fraction))
    side = direction.cross(UP)
    if side.length < 1e-4:
        side = Vector((1.0, 0.0, 0.0))
    side.normalize()
    for index in range(links):
        fraction = (index + 0.5) / links
        centre = start + step * (index + 0.5) + dip(fraction)
        axis = side if index % 2 == 0 else direction.cross(side).normalized()
        bpy.ops.mesh.primitive_torus_add(
            location=centre,
            major_radius=link_radius,
            minor_radius=wire_radius,
            major_segments=20,
            minor_segments=10,
        )
        obj = bpy.context.object
        rotation = Vector((0.0, 0.0, 1.0)).rotation_difference(axis)
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = rotation
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        # Stretch each link along the run so the chain reads as links, not
        # as a string of doughnuts.
        #
        # NO conjugation about `centre`. transform_apply has already baked
        # the rotation, so the mesh data is object-local and centred on
        # zero — and the conjugation that was here was inverted anyway
        # (scaling about a point is T(c) @ S @ T(-c), not the reverse).
        # Applied to local data it came out as a per-link translation of
        # 0.55*(centre.direction) along the run, which is metres, different
        # for every link: the guy chains rendered as loose rings floating
        # in mid-air. Twice, by two different mechanisms.
        obj.data.transform(Matrix.Scale(stretch, 4, direction))
        objects.append(bk._finish_primitive(obj, f"{name}_{index:02d}", material, 0.0))
    return objects


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------


def build_materials() -> dict[str, object]:
    # preview_emission is the per-mod opt-in blender_kit documents: it puts
    # the beacon's glow into the PREVIEW shader (and this mod's own DAE
    # bytes, which regenerate with every build anyway). Without it the dusk
    # render showed an unlit red dome and proved nothing about the one
    # light the machine owns.
    return bk.materials_from_palette(
        spec, EXAMPLE_ROOT / "textures", preview_emission=True)


# ---------------------------------------------------------------------------
# The mast (static)
# ---------------------------------------------------------------------------


def build_mast(materials) -> list:
    rig = materials[f"{MOD_ID}_rig_black"]
    steel = materials[f"{MOD_ID}_steel"]
    iron = materials[f"{MOD_ID}_cast_iron"]
    hazard = materials[f"{MOD_ID}_hazard"]
    objects = []

    plate_w, plate_d, plate_h = spec.MAST_PLATE
    # Grout pad under the baseplate: a machine this size is not bolted to
    # tarmac, it is bolted to a poured pad.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_mast_grout",
            (spec.MAST_X, spec.MAST_Y, 0.09),
            (plate_w + 1.5, plate_d + 1.5, 0.18),
            iron,
            bevel=0.05,
            metric_uv=(1.6, 1.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_mast_plate",
            (spec.MAST_X, spec.MAST_Y, 0.18 + plate_h / 2.0),
            (plate_w, plate_d, plate_h),
            rig,
            bevel=0.035,
            metric_uv=(1.2, 1.2),
        )
    )
    bolt_top = 0.18 + plate_h
    for index in range(spec.MAST_PLATE_BOLTS):
        angle = TWO_PI * index / spec.MAST_PLATE_BOLTS
        radius = plate_w * 0.40
        centre = Vector(
            (
                spec.MAST_X + radius * math.cos(angle),
                spec.MAST_Y + radius * math.sin(angle),
                bolt_top,
            )
        )
        objects.append(
            add_bolt(f"{MOD_ID}_mast_bolt{index:02d}", centre, UP, spec.MAST_BOLT_R, steel)
        )

    column_base = Vector((spec.MAST_X, spec.MAST_Y, bolt_top))
    column_height = spec.MAST_TOP_Z - bolt_top
    objects.append(
        add_tapered_column(
            f"{MOD_ID}_mast_column",
            column_base,
            UP,
            column_height,
            spec.MAST_BASE / 2.0,
            spec.MAST_TOP / 2.0,
            rig,
            corner=0.16,
            uv=1.4,
        )
    )
    # Welded stiffener bands at the plate splices. Real fabricated columns
    # are ringed; without them an 8 m taper is a featureless wedge. Kept
    # SHALLOW — the first pass stood them 55 mm proud and the mast read as
    # a stack of boxes rather than a tapered column.
    for fraction, over in ((0.34, 0.050), (0.68, 0.042)):
        height = bolt_top + column_height * fraction
        t = (height - bolt_top) / column_height
        half = (spec.MAST_BASE / 2.0) + ((spec.MAST_TOP - spec.MAST_BASE) / 2.0) * t
        objects.append(
            bk.add_box(
                f"{MOD_ID}_mast_band{int(height * 10)}",
                (spec.MAST_X, spec.MAST_Y, height),
                ((half + over) * 2.0, (half + over) * 2.0, 0.14),
                rig,
                bevel=0.02,
                metric_uv=(1.0, 1.0),
            )
        )

    # Hazard band around the base: the one thing on the machine that is not
    # black, and the only warning a driver gets that the mast is solid.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_mast_hazard",
            (spec.MAST_X, spec.MAST_Y, 0.95),
            (spec.MAST_BASE * 1.02, spec.MAST_BASE * 1.02, 0.62),
            hazard,
            bevel=0.02,
            metric_uv=(1.4, 0.62),
        )
    )

    # Base gussets on the four faces.
    for index in range(spec.MAST_GUSSETS):
        angle = math.radians(45.0 + 90.0 * index)
        outward = Vector((math.cos(angle), math.sin(angle), 0.0))
        side = outward.cross(UP)
        apex = column_base + outward * (spec.MAST_BASE * 0.36) + UP * spec.MAST_GUSSET[2]
        corner_a = column_base + outward * (spec.MAST_BASE * 0.36) + UP * 0.02
        corner_b = column_base + outward * spec.MAST_GUSSET[0] + UP * 0.02
        objects.append(
            add_gusset(
                f"{MOD_ID}_mast_gusset{index}",
                apex,
                corner_a,
                corner_b,
                spec.MAST_GUSSET[1],
                side,
                rig,
            )
        )

    # Caged ladder up the unswept face.
    ladder_dir = Vector(
        (math.cos(math.radians(SAFE_AZIMUTH)), math.sin(math.radians(SAFE_AZIMUTH)), 0.0)
    )
    ladder_side = ladder_dir.cross(UP)
    for sign in (-1.0, 1.0):
        base = MAST + ladder_dir * (spec.MAST_BASE / 2.0 + 0.30) + ladder_side * (sign * 0.36)
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ladder_rail{'p' if sign > 0 else 'm'}",
                (base.x, base.y, (spec.MAST_TOP_Z - 0.60) / 2.0 + 0.30),
                (0.13, 0.13, spec.MAST_TOP_Z - 1.30),
                rig,
                bevel=0.012,
                metric_uv=(0.5, 0.9),
                rotation=(0.0, 0.0, math.radians(SAFE_AZIMUTH)),
            )
        )
    for index in range(spec.LADDER_RUNGS):
        height = 0.85 + index * ((spec.MAST_TOP_Z - 1.60) / (spec.LADDER_RUNGS - 1))
        centre = MAST + ladder_dir * (spec.MAST_BASE / 2.0 + 0.30) + UP * height
        rung = bk.add_cylinder(
            f"{MOD_ID}_ladder_rung{index:02d}",
            (centre.x, centre.y, centre.z),
            0.045,
            0.80,
            steel,
            vertices=16,
            axis="X",
            metric_uv=(2.0 * math.pi * 0.045, 0.45),
        )
        rung.rotation_euler = (0.0, 0.0, math.radians(SAFE_AZIMUTH + 90.0))
        bpy.context.view_layer.objects.active = rung
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        objects.append(rung)
    for index in range(5):
        height = 2.35 + index * ((spec.MAST_TOP_Z - 3.20) / 4.0)
        centre = MAST + ladder_dir * (spec.MAST_BASE / 2.0 + 0.52) + UP * height
        bpy.ops.mesh.primitive_torus_add(
            location=centre, major_radius=0.60, minor_radius=0.035,
            major_segments=28, minor_segments=8,
        )
        hoop = bpy.context.object
        hoop.rotation_euler = (math.pi / 2.0, 0.0, math.radians(SAFE_AZIMUTH + 90.0))
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        objects.append(bk._finish_primitive(hoop, f"{MOD_ID}_ladder_hoop{index}", rig, 0.0))

    # Guy chains and their anchors, both in the unswept sector.
    for index, azimuth in enumerate((SAFE_AZIMUTH - 38.0, SAFE_AZIMUTH + 38.0)):
        anchor = azimuth_point(azimuth, 9.80, 0.0)
        objects.append(
            bk.add_box(
                f"{MOD_ID}_guy_anchor{index}",
                (anchor.x, anchor.y, 0.52),
                (2.10, 2.10, 1.04),
                iron,
                bevel=0.05,
                metric_uv=(1.0, 1.0),
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_guy_anchor_cap{index}",
                (anchor.x, anchor.y, 1.10),
                (1.65, 1.65, 0.14),
                hazard,
                bevel=0.02,
                metric_uv=(1.2, 1.2),
            )
        )
        eye = anchor + UP * 1.30
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_guy_eye{index}",
                (eye.x, eye.y, eye.z),
                0.13,
                0.42,
                steel,
                vertices=20,
                axis="Z",
                metric_uv=(2.0 * math.pi * 0.13, 0.4),
            )
        )
        # The old top anchor sat at r = MAST_TOP*0.62 — 0.17 m INSIDE the
        # mast face along this bearing, so the first links grew out of bare
        # plate. A welded lug now stands the eye off the face at r 1.90.
        lug_root = azimuth_point(azimuth, 1.66, spec.MAST_TOP_Z - 0.75)
        lug_tip = azimuth_point(azimuth, 1.94, spec.MAST_TOP_Z - 0.75)
        lug_dir = (lug_tip - lug_root).normalized()
        lug = bk.add_box(
            f"{MOD_ID}_guy_lug{index}",
            ((lug_root.x + lug_tip.x) / 2.0, (lug_root.y + lug_tip.y) / 2.0,
             spec.MAST_TOP_Z - 0.75),
            (0.34, 0.34, 0.30),
            rig,
            bevel=0.02,
            metric_uv=(0.4, 0.4),
            rotation=(0.0, 0.0, math.radians(azimuth)),
        )
        objects.append(lug)
        eye_ring = bk.add_cylinder(
            f"{MOD_ID}_guy_lug_eye{index}",
            (lug_tip.x, lug_tip.y, spec.MAST_TOP_Z - 0.75),
            0.11,
            0.09,
            steel,
            vertices=18,
            axis="Z",
            metric_uv=(0.6, 0.2),
        )
        _orient(eye_ring, lug_dir.cross(UP).normalized())
        objects.append(eye_ring)
        top = azimuth_point(azimuth, 1.94, spec.MAST_TOP_Z - 0.75)
        # Turnbuckle a third of the way down the run, as it is on the
        # reference stand.
        run = eye - top
        # The turnbuckle rides the SAGGED path, not the chord — a tensioner
        # floating above its own slack chain is the old floating-hardware
        # read all over again.
        GUY_SAG = 0.05
        sag_at = lambda fraction: UP * (
            -4.0 * GUY_SAG * run.length * fraction * (1.0 - fraction))
        barrel_centre = top + run * 0.34 + sag_at(0.34)
        # ORIENTED along the run. It was built axis="Z" and never turned,
        # so a tensioner in a diagonal chain stood bolt upright beside its
        # own chain in four separate renders — the same "floating hardware"
        # read the chain links themselves had before they were fixed.
        barrel = bk.add_cylinder(
            f"{MOD_ID}_guy_turnbuckle{index}",
            (barrel_centre.x, barrel_centre.y, barrel_centre.z),
            0.115,
            1.05,
            steel,
            vertices=20,
            axis="Z",
            metric_uv=(2.0 * math.pi * 0.115, 0.5),
        )
        _orient(barrel, run.normalized())
        objects.append(barrel)
        # Blackened utility chain, half the old link. The 0.22 m polished
        # links read as battleship anchor chain against the reference's
        # slack black rigging.
        objects.extend(
            add_chain(
                f"{MOD_ID}_guy_chain{index}",
                top,
                barrel_centre - run.normalized() * 0.50,
                rig,
                0.13,
                0.040,
                sag=0.035,
            )
        )
        objects.extend(
            add_chain(
                f"{MOD_ID}_guy_chain{index}b",
                barrel_centre + run.normalized() * 0.50,
                eye,
                rig,
                0.13,
                0.040,
                sag=0.035,
            )
        )

    # Slew ring: outer race, inner race, and real cut teeth. 96 of them is
    # the tooth count on the plate, so it is the tooth count on the ring.
    ring_z = spec.MAST_TOP_Z + spec.SLEW_RING_H / 2.0
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_slew_outer",
            (spec.MAST_X, spec.MAST_Y, ring_z),
            spec.SLEW_RING_R,
            spec.SLEW_RING_H,
            steel,
            vertices=96,
            axis="Z",
            metric_uv=(2.0 * math.pi * spec.SLEW_RING_R / 6.0, 0.46),
        )
    )
    for index in range(spec.SLEW_TEETH):
        angle = TWO_PI * index / spec.SLEW_TEETH
        centre = (
            spec.MAST_X + (spec.SLEW_RING_R + 0.035) * math.cos(angle),
            spec.MAST_Y + (spec.SLEW_RING_R + 0.035) * math.sin(angle),
            ring_z,
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_slew_tooth{index:02d}",
                centre,
                (0.075, 0.052, spec.SLEW_RING_H * 0.72),
                steel,
                bevel=0.006,
                rotation=(0.0, 0.0, angle),
            )
        )
    # Drive pinion meshing with the ring: the machine has to be driven by
    # something, and a visible pinion is what says "this turns".
    pinion = azimuth_point(spec.DRIVE_AZIMUTH, spec.SLEW_RING_R + 0.44, ring_z)
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_slew_pinion",
            (pinion.x, pinion.y, pinion.z),
            0.38,
            spec.SLEW_RING_H * 0.9,
            steel,
            vertices=18,
            axis="Z",
            metric_uv=(2.0 * math.pi * 0.38 / 3.0, 0.42),
        )
    )
    gearbox = azimuth_point(spec.DRIVE_AZIMUTH, spec.SLEW_RING_R + 0.44, ring_z - 0.95)
    objects.append(
        bk.add_box(
            f"{MOD_ID}_slew_gearbox",
            (gearbox.x, gearbox.y, gearbox.z),
            (0.86, 0.86, 1.30),
            iron,
            bevel=0.03,
            metric_uv=(0.9, 0.9),
        )
    )
    return objects


# ---------------------------------------------------------------------------
# The arm (moving part)
# ---------------------------------------------------------------------------


def build_arm(materials) -> tuple[list, list]:
    """Shoulder, upper arm, elbow, forearm, counterweight — and the cuff.

    Returns TWO part groups. The arm proper turns about the slew axis as
    one rigid body; the elbow is a real pinned joint with a ram across it,
    but the ram sets the break angle at install and does not move in play —
    the same honesty as the shoulder's pitch arc.

    The CUFF is separate because it has to move. The runtime drops the hand
    by up to 0.374 m as the wrist rolls, so the palm stays on a car's flank
    instead of climbing to the roofline at the top tilt detent; a collar
    bolted to the arm would have the foam stump pull straight out through
    its own bore, against 0.17 m of radial clearance. So the collar rides a
    vertical slide in the wrist knuckle. The KNUCKLE stays with the arm as
    the housing, which makes the slide visible — the machine shows you how
    it keeps the palm down.
    """

    rig = materials[f"{MOD_ID}_rig_black"]
    steel = materials[f"{MOD_ID}_steel"]
    iron = materials[f"{MOD_ID}_cast_iron"]
    hazard = materials[f"{MOD_ID}_hazard"]
    objects = []

    deck_z = spec.MAST_TOP_Z + spec.SLEW_RING_H + 0.11
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_arm_deck",
            (spec.MAST_X, spec.MAST_Y, deck_z),
            spec.SLEW_RING_R + 0.20,
            0.26,
            rig,
            vertices=64,
            axis="Z",
            metric_uv=(2.0 * math.pi * (spec.SLEW_RING_R + 0.20) / 6.0, 0.5),
        )
    )
    for index in range(20):
        angle = TWO_PI * index / 20
        centre = Vector(
            (
                spec.MAST_X + (spec.SLEW_RING_R - 0.14) * math.cos(angle),
                spec.MAST_Y + (spec.SLEW_RING_R - 0.14) * math.sin(angle),
                deck_z + 0.13,
            )
        )
        objects.append(add_bolt(f"{MOD_ID}_arm_deckbolt{index:02d}", centre, UP, 0.085, steel))

    # --- shoulder ---------------------------------------------------------
    pedestal_base = Vector((spec.MAST_X, spec.MAST_Y, deck_z + 0.13))
    objects.append(
        add_tapered_column(
            f"{MOD_ID}_arm_pedestal",
            pedestal_base,
            UP,
            spec.HUB_Z - pedestal_base.z,
            1.42,
            1.02,
            rig,
            corner=0.10,
            uv=1.0,
        )
    )
    for sign in (-1.0, 1.0):
        tag = "p" if sign > 0 else "m"
        cheek = HUB + E2 * (sign * 0.88)
        objects.append(
            bk.add_box(
                f"{MOD_ID}_arm_cheek{tag}",
                (cheek.x, cheek.y, cheek.z),
                (2.80, 0.22, 2.80),
                rig,
                bevel=0.03,
                metric_uv=(0.9, 0.9),
                rotation=(0.0, 0.0, math.radians(spec.REST_DEG)),
            )
        )
        # Pitch arc: seven holes, the upper arm pinned through one of them.
        for index in range(7):
            angle = math.radians(-58.0 + index * 9.0)
            radial = (A1 * math.cos(angle) + A3 * math.sin(angle)) * 1.06
            hole = HUB + radial + E2 * (sign * 0.96)
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_arm_arc{tag}{index}",
                    (hole.x, hole.y, hole.z),
                    0.115,
                    0.14,
                    steel,
                    vertices=14,
                    axis="Z",
                )
            )
    objects.append(_pin(f"{MOD_ID}_arm_pin", HUB, 0.42, 2.55, steel))

    # Domed hub cap with the reference stand's ball finial. It is the one
    # piece of the machine that is pure quotation.
    cap_centre = HUB + UP * 1.42
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_arm_cap",
            (cap_centre.x, cap_centre.y, cap_centre.z),
            0.76,
            0.26,
            rig,
            vertices=32,
            axis="Z",
            metric_uv=(2.0 * math.pi * 0.76 / 4.0, 0.4),
        )
    )
    objects.append(
        bk.add_sphere(
            f"{MOD_ID}_arm_finial",
            (cap_centre.x, cap_centre.y, cap_centre.z + 0.13 + spec.FINIAL_R * 0.62),
            spec.FINIAL_R,
            rig,
            # 96 x 56, not 40 x 24. On a 0.62 m ball that was a 0.097 m
            # facet round the equator and 0.081 m pole to pole, and the
            # latitude rings were legible — on rig_black, which is the one
            # material whose entire visual interest is supposed to live in
            # its normal map. The brief for this prop is explicitly not to
            # spare polygon count; this is 5,376 quads.
            segments=96,
            rings=56,
        )
    )

    # --- upper arm and forearm -------------------------------------------
    # Tapered fabricated box girders with bolted splice plates. No lightening
    # holes: a boolean through a tapered loft is the cut_openings
    # bevel-after-boolean trap, and a plate girder with visible splices is
    # the more period-correct answer anyway.
    def girder(name, origin, e1, e3, length, root_depth, tip_depth, root_w, tip_w):
        rings = []
        stations = 12
        for step in range(stations + 1):
            t = step / stations
            centre = origin + e1 * (length * t)
            rings.append(
                rounded_rect_ring(
                    centre,
                    E2,
                    e3,
                    (root_w + (tip_w - root_w) * t) / 2.0,
                    (root_depth + (tip_depth - root_depth) * t) / 2.0,
                    0.10,
                )
            )
        return add_loft(name, rings, rig, uv_scale=(1.4, 1.4))

    # THE KNEE BOOM. See spec.BOOM_KNEE_R for why no straight member can
    # exist here: the shoulder segment runs shallow OVER the slew ring,
    # a gusseted knee turns the corner outside it, and the drop segment
    # takes the 78-degree dive to the elbow. The old root shoe was
    # cosmetic against a path that was wrong.
    KNEE = HUB + U_RADIAL * spec.BOOM_KNEE_R + UP * (spec.BOOM_KNEE_Z - spec.HUB_Z)
    S1 = (KNEE - HUB).normalized()
    S1_3 = S1.cross(E2).normalized()
    S2 = (ELBOW - KNEE).normalized()
    S2_3 = S2.cross(E2).normalized()
    shoulder_len = (KNEE - HUB).length
    drop_len = (ELBOW - KNEE).length
    objects.append(
        add_loft(
            f"{MOD_ID}_arm_root_shoe",
            [
                rounded_rect_ring(
                    HUB + S1 * 0.28, E2, S1_3,
                    spec.BOOM_WIDTH * 0.40, 0.56, 0.10),
                rounded_rect_ring(
                    HUB + S1 * 0.70, E2, S1_3,
                    spec.BOOM_WIDTH / 2.0, 1.35 / 2.0, 0.10),
            ],
            rig,
            uv_scale=(1.2, 1.2),
            cap_start=True,
            cap_end=False,
        )
    )
    objects.append(
        girder(
            f"{MOD_ID}_arm_shoulder", HUB + S1 * 0.70, S1, S1_3,
            shoulder_len - 0.70,
            1.35, 1.15,
            spec.BOOM_WIDTH, spec.BOOM_WIDTH * 0.94,
        )
    )
    # The knee joint: a boxed gusset wrapping the corner, with a bolt ring
    # on each cheek -- the joint a fabricated dogleg actually has.
    knee_axis = (S1 + S2).normalized()
    knee_box = bk.add_box(
        f"{MOD_ID}_arm_knee",
        (KNEE.x, KNEE.y, KNEE.z),
        (spec.BOOM_WIDTH + 0.22, 1.55, 1.55),
        rig,
        bevel=0.05,
        metric_uv=(1.0, 1.0),
        rotation=(0.0, 0.0, math.radians(spec.REST_DEG)),
    )
    objects.append(knee_box)
    for sign in (-1.0, 1.0):
        for angle_index in range(8):
            angle = TWO_PI * angle_index / 8.0
            radial = (S1 * math.cos(angle) + S1_3 * math.sin(angle)) * 0.55
            bolt = KNEE + radial + E2 * (sign * (spec.BOOM_WIDTH / 2.0 + 0.115))
            objects.append(
                add_bolt(
                    f"{MOD_ID}_knee_bolt{int(sign)}{angle_index}",
                    bolt, E2 * sign, 0.055, steel,
                )
            )
    objects.append(
        girder(
            f"{MOD_ID}_upper_arm", KNEE, S2, S2_3,
            drop_len,
            1.15, spec.BOOM_ELBOW_DEPTH,
            spec.BOOM_WIDTH * 0.94, spec.BOOM_WIDTH * 0.88,
        )
    )
    objects.append(
        girder(
            f"{MOD_ID}_forearm", ELBOW, F1, F3, spec.FORE_LENGTH,
            spec.BOOM_ELBOW_DEPTH, spec.BOOM_TIP_DEPTH,
            spec.BOOM_WIDTH * 0.88, spec.BOOM_WIDTH * 0.70,
        )
    )

    def splices(prefix, origin, e1, e3, length, root_depth, tip_depth, root_w, tip_w, stops):
        for index, fraction in enumerate(stops):
            along = length * fraction
            depth = root_depth + (tip_depth - root_depth) * fraction
            width = root_w + (tip_w - root_w) * fraction
            near = rounded_rect_ring(
                origin + e1 * along, E2, e3,
                width / 2.0 + 0.04, depth / 2.0 + 0.04, 0.10)
            far = rounded_rect_ring(
                origin + e1 * (along + 0.40), E2, e3,
                width / 2.0 + 0.04, depth / 2.0 + 0.04, 0.10)
            objects.append(
                add_loft(
                    f"{prefix}_splice{index}", [near, far], rig,
                    uv_scale=(1.0, 1.0), cap_start=False, cap_end=False,
                )
            )
            for side in (-1.0, 1.0):
                for row in (-1, 0, 1):
                    bolt = (
                        origin + e1 * (along + 0.20)
                        + E2 * (side * (width / 2.0 + 0.042))
                        + e3 * (row * depth * 0.30)
                    )
                    objects.append(
                        add_bolt(
                            f"{prefix}_bolt{index}{int(side)}{row}",
                            bolt, E2 * side, 0.062, steel,
                        )
                    )

    splices(
        f"{MOD_ID}_upper", KNEE, S2, S2_3,
        drop_len,
        1.15, spec.BOOM_ELBOW_DEPTH,
        spec.BOOM_WIDTH * 0.94, spec.BOOM_WIDTH * 0.88, (0.34, 0.70),
    )
    splices(
        f"{MOD_ID}_fore", ELBOW, F1, F3, spec.FORE_LENGTH,
        spec.BOOM_ELBOW_DEPTH, spec.BOOM_TIP_DEPTH,
        spec.BOOM_WIDTH * 0.88, spec.BOOM_WIDTH * 0.70, (0.26, 0.58, 0.84),
    )

    # --- elbow ------------------------------------------------------------
    # Two cheek plates outboard of both girders, a through pin, and a bolt
    # circle. The break here is spec.ELBOW_BREAK_DEG, so the number in the
    # docstring and the number in the mesh are one value.
    for sign in (-1.0, 1.0):
        tag = "p" if sign > 0 else "m"
        offset = spec.BOOM_WIDTH / 2.0 + spec.ELBOW_CHEEK / 2.0
        centre = ELBOW + E2 * (sign * offset)
        plate = bk.add_cylinder(
            f"{MOD_ID}_elbow_cheek{tag}",
            (centre.x, centre.y, centre.z),
            spec.BOOM_ELBOW_DEPTH * 0.72,
            spec.ELBOW_CHEEK,
            rig,
            vertices=44,
            axis="Z",
            metric_uv=(2.0 * math.pi * spec.BOOM_ELBOW_DEPTH * 0.72 / 4.0, 0.3),
        )
        _orient(plate, E2)
        objects.append(plate)
        for index in range(8):
            angle = TWO_PI * index / 8
            radial = F1 * math.cos(angle) + F3 * math.sin(angle)
            bolt = centre + radial * (spec.BOOM_ELBOW_DEPTH * 0.52) + E2 * (sign * 0.12)
            objects.append(
                add_bolt(f"{MOD_ID}_elbow_bolt{tag}{index}", bolt, E2 * sign, 0.070, steel)
            )
    objects.append(
        _pin(
            f"{MOD_ID}_elbow_pin", ELBOW, spec.ELBOW_PIN_R,
            spec.BOOM_WIDTH + 2.0 * spec.ELBOW_CHEEK + 0.32, steel,
        )
    )

    # The ram across the elbow. Barrel on the upper arm, rod to a clevis on
    # the forearm: the member that holds the break angle against the load.
    ram_root = HUB + A1 * (spec.UPPER_LENGTH * 0.42) - A3 * (spec.BOOM_ROOT_DEPTH * 0.62)
    ram_head = ELBOW + F1 * (spec.FORE_LENGTH * 0.30) - F3 * (spec.BOOM_ELBOW_DEPTH * 0.60)
    ram_axis = (ram_head - ram_root).normalized()
    ram_length = (ram_head - ram_root).length
    barrel_centre = ram_root + ram_axis * (ram_length * 0.34)
    barrel = bk.add_cylinder(
        f"{MOD_ID}_elbow_ram",
        (barrel_centre.x, barrel_centre.y, barrel_centre.z),
        spec.RAM_BORE_R,
        ram_length * 0.62,
        iron,
        vertices=28,
        axis="Z",
        metric_uv=(2.0 * math.pi * spec.RAM_BORE_R, 0.7),
    )
    _orient(barrel, ram_axis)
    objects.append(barrel)
    rod_centre = ram_root + ram_axis * (ram_length * 0.80)
    rod = bk.add_cylinder(
        f"{MOD_ID}_elbow_rod",
        (rod_centre.x, rod_centre.y, rod_centre.z),
        spec.RAM_BORE_R * 0.52,
        ram_length * 0.44,
        steel,
        vertices=22,
        axis="Z",
        metric_uv=(2.0 * math.pi * spec.RAM_BORE_R * 0.52, 0.5),
    )
    _orient(rod, ram_axis)
    objects.append(rod)
    objects.append(_pin(f"{MOD_ID}_ram_clevis_a", ram_root, 0.16, spec.BOOM_WIDTH * 0.55, steel))
    objects.append(_pin(f"{MOD_ID}_ram_clevis_b", ram_head, 0.16, spec.BOOM_WIDTH * 0.55, steel))

    # --- counterweight ----------------------------------------------------
    # A bolted plate stack on the short side of the hub, sized in spec.py
    # against the arm's own first moment about the slew axis.
    stack = spec.CWT_PLATES * (spec.CWT_PLATE[1] + 0.04)
    for index in range(spec.CWT_PLATES):
        offset = (index - (spec.CWT_PLATES - 1) / 2.0) * (spec.CWT_PLATE[1] + 0.04)
        centre = HUB + U * spec.CWT_R + E2 * offset
        objects.append(
            bk.add_box(
                f"{MOD_ID}_cwt_plate{index}",
                (centre.x, centre.y, spec.CWT_Z),
                spec.CWT_PLATE,
                iron,
                bevel=0.02,
                metric_uv=(0.8, 0.8),
                rotation=(0.0, 0.0, math.radians(spec.REST_DEG)),
            )
        )
    for along in (-1.0, 1.0):
        for level in (-1.0, 1.0):
            centre = HUB + U * (spec.CWT_R + along * spec.CWT_PLATE[0] * 0.34)
            centre = Vector(
                (centre.x, centre.y, spec.CWT_Z + level * spec.CWT_PLATE[2] * 0.30)
            )
            objects.append(
                _pin(
                    f"{MOD_ID}_cwt_rod{int(along)}{int(level)}",
                    centre, 0.065, stack + 0.36, steel,
                )
            )
    # THE CARRIER. The plate stack used to hang beside the hub with
    # nothing visibly holding 29 tonnes — a floating pale block. A tail
    # beam now runs from the shoulder out over the stack and two hanger
    # plates take the weight, which is the whole story a counterweight
    # has to tell.
    tail_dir = U * (-1.0 if spec.CWT_R < 0 else 1.0)
    tail_len = abs(spec.CWT_R) + spec.CWT_PLATE[0] * 0.62
    tail_mid = HUB + tail_dir * (tail_len / 2.0)
    objects.append(
        bk.add_box(
            f"{MOD_ID}_cwt_tail",
            (tail_mid.x, tail_mid.y, spec.HUB_Z - 0.42),
            (tail_len, 0.74, 0.66),
            rig,
            bevel=0.04,
            metric_uv=(1.2, 0.8),
            rotation=(0.0, 0.0, math.radians(spec.REST_DEG)),
        )
    )
    hanger_top = spec.HUB_Z - 0.75
    hanger_bottom = spec.CWT_Z - spec.CWT_PLATE[2] * 0.18
    for along in (-1.0, 1.0):
        hang_centre = HUB + U * (spec.CWT_R + along * spec.CWT_PLATE[0] * 0.40)
        objects.append(
            bk.add_box(
                f"{MOD_ID}_cwt_hanger{int(along)}",
                (hang_centre.x, hang_centre.y,
                 (hanger_top + hanger_bottom) / 2.0),
                (0.30, 0.62, hanger_top - hanger_bottom),
                rig,
                bevel=0.02,
                metric_uv=(0.6, 1.0),
                rotation=(0.0, 0.0, math.radians(spec.REST_DEG)),
            )
        )

    # Nuts on the ends of the tie rods and a pair of lifting eyes on top:
    # 92 tonnes of plate has to LOOK like something that was craned into
    # place and bolted, not like a box glued to the hub.
    for along in (-1.0, 1.0):
        for level in (-1.0, 1.0):
            for side in (-1.0, 1.0):
                nut = (
                    HUB + U * (spec.CWT_R + along * spec.CWT_PLATE[0] * 0.34)
                    + E2 * (side * (stack / 2.0 + 0.10))
                )
                nut = Vector(
                    (nut.x, nut.y, spec.CWT_Z + level * spec.CWT_PLATE[2] * 0.30)
                )
                objects.append(
                    add_bolt(
                        f"{MOD_ID}_cwt_nut{int(along)}{int(level)}{int(side)}",
                        nut, E2 * side, 0.115, steel,
                    )
                )
    for side in (-1.0, 1.0):
        eye = HUB + U * spec.CWT_R + E2 * (side * stack * 0.28)
        eye = Vector((eye.x, eye.y, spec.CWT_Z + spec.CWT_PLATE[2] / 2.0 + 0.16))
        bpy.ops.mesh.primitive_torus_add(
            location=eye, major_radius=0.22, minor_radius=0.055,
            major_segments=24, minor_segments=10,
        )
        loop = bpy.context.object
        loop.rotation_euler = (0.0, math.pi / 2.0, math.radians(spec.REST_DEG))
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        objects.append(
            bk._finish_primitive(
                loop, f"{MOD_ID}_cwt_eye{'p' if side > 0 else 'm'}", steel, 0.0
            )
        )

    cwt_face = HUB + U * (spec.CWT_R - spec.CWT_PLATE[0] * 0.5 - 0.06)
    objects.append(
        bk.add_box(
            f"{MOD_ID}_cwt_hazard",
            (cwt_face.x, cwt_face.y, spec.CWT_Z),
            (0.12, stack, spec.CWT_PLATE[2] * 0.55),
            hazard,
            bevel=0.01,
            metric_uv=(1.0, 0.7),
            rotation=(0.0, 0.0, math.radians(spec.REST_DEG)),
        )
    )

    # --- wrist ------------------------------------------------------------
    # The cast knuckle bridges the forearm's nose-down arrival to the
    # horizontal collar and is the cuff's HOUSING, so it stays with the arm.
    knuckle_centre = WRIST - U * 0.55 + UP * 0.18
    objects.append(
        bk.add_box(
            f"{MOD_ID}_wrist_knuckle",
            (knuckle_centre.x, knuckle_centre.y, knuckle_centre.z),
            (2.30, spec.BOOM_WIDTH * 0.82, 1.95),
            rig,
            bevel=0.10,
            metric_uv=(1.0, 1.0),
            rotation=(0.0, 0.0, math.radians(spec.REST_DEG)),
        )
    )
    # The cuff bore is an ELLIPSE measured off the palm's own section, not a
    # circle. A wrist is 1.72:1 (2.82 m across the styloids, 1.64 m thick),
    # so a round bore wide enough to clear the width stood 0.80 m proud of
    # the thickness and showed a black crescent above and below the stump at
    # every angle. Taking the half-extents from PalmSurface means the cuff
    # cannot drift out of agreement with the hand it swallows.
    palm_surface = hand_sculpt.PalmSurface(spec)
    cuff: list = []
    collar_centre = WRIST - U * 1.35
    mouth_u = -1.35 + spec.COLLAR_LENGTH / 2.0
    heel_u = -1.35 - spec.COLLAR_LENGTH / 2.0
    half_v = max(
        palm_surface.radius(mouth_u, 0.0)[0], palm_surface.radius(heel_u, 0.0)[0]
    ) + spec.COLLAR_CLEARANCE
    half_n = max(
        palm_surface.radius(mouth_u, math.pi / 2.0)[1],
        palm_surface.radius(heel_u, math.pi / 2.0)[1],
    ) + spec.COLLAR_CLEARANCE
    wall = 0.14

    def cuff_ring(along, grow):
        # 128 segments. The collar bore is about 10 m round, so 64 put a
        # 0.157 m flat on a cylinder the player stands beside, and it read
        # as longitudinal strips.
        return ellipse_ring(
            WRIST + U * along, E2, UP, half_n + grow, half_v + grow, 128
        )

    cuff.append(
        add_loft(
            f"{MOD_ID}_collar",
            [cuff_ring(heel_u, wall), cuff_ring(mouth_u, wall)],
            rig,
            uv_scale=(1.2, 1.2),
            cap_start=True,
            cap_end=False,
        )
    )
    # A short inner sleeve so the bore reads as a bore rather than as a
    # shell with a hole in it.
    cuff.append(
        add_loft(
            f"{MOD_ID}_collar_bore",
            [cuff_ring(mouth_u, 0.0), cuff_ring(mouth_u - 0.26, 0.0)],
            rig,
            uv_scale=(1.2, 1.2),
            cap_start=False,
            cap_end=False,
        )
    )
    cuff.append(
        add_loft(
            f"{MOD_ID}_collar_lip",
            [cuff_ring(mouth_u, 0.0), cuff_ring(mouth_u, wall)],
            rig,
            uv_scale=(1.2, 1.2),
            cap_start=False,
            cap_end=False,
        )
    )

    flange_centre = WRIST + U * (heel_u - 0.11)
    cuff.append(
        add_loft(
            f"{MOD_ID}_collar_flange",
            [
                ellipse_ring(flange_centre, E2, UP, half_n + 0.46, half_v + 0.46, 64),
                ellipse_ring(
                    flange_centre - U * 0.22, E2, UP, half_n + 0.46, half_v + 0.46, 64
                ),
            ],
            rig,
            uv_scale=(1.0, 1.0),
        )
    )

    for index in range(spec.COLLAR_BOLTS):
        angle = TWO_PI * index / spec.COLLAR_BOLTS
        radial = E2 * ((half_n + 0.28) * math.cos(angle)) + UP * (
            (half_v + 0.28) * math.sin(angle)
        )
        centre = flange_centre + radial + U * 0.12
        cuff.append(
            add_bolt(f"{MOD_ID}_collar_bolt{index:02d}", centre, U, 0.082, steel)
        )

    # The tilt actuator: a rotary drive on the collar is what physically
    # rolls the wrist, and TILT on the console is its dial. It was one
    # flat light-grey box — the brightest thing on the arm and the only
    # part that read as placeholder. Now it is a machine: gearbox against
    # the collar, finned motor barrel along the roll axis, terminal box.
    drive = collar_centre + UP * (spec.COLLAR_R + 0.34)
    cuff.append(
        bk.add_box(
            f"{MOD_ID}_tilt_gearbox",
            (drive.x, drive.y, drive.z),
            (0.78, 0.86, 0.64),
            iron,
            bevel=0.03,
            metric_uv=(0.7, 0.7),
            rotation=(0.0, 0.0, math.radians(spec.REST_DEG)),
        )
    )
    motor_centre = drive + U * 0.92
    motor = bk.add_cylinder(
        f"{MOD_ID}_tilt_motor",
        (motor_centre.x, motor_centre.y, motor_centre.z),
        0.30,
        1.10,
        rig,
        vertices=28,
        axis="Z",
        metric_uv=(2.0 * math.pi * 0.30, 0.7),
    )
    _orient(motor, U)
    cuff.append(motor)
    for fin in range(4):
        fin_centre = motor_centre - U * 0.35 + U * (fin * 0.22)
        ring = bk.add_cylinder(
            f"{MOD_ID}_tilt_fin{fin}",
            (fin_centre.x, fin_centre.y, fin_centre.z),
            0.345,
            0.045,
            rig,
            vertices=28,
            axis="Z",
            metric_uv=(2.0 * math.pi * 0.345, 0.1),
        )
        _orient(ring, U)
        cuff.append(ring)
    terminal = motor_centre + UP * 0.36 - U * 0.18
    cuff.append(
        bk.add_box(
            f"{MOD_ID}_tilt_terminal",
            (terminal.x, terminal.y, terminal.z),
            (0.30, 0.26, 0.22),
            iron,
            bevel=0.02,
            metric_uv=(0.3, 0.3),
            rotation=(0.0, 0.0, math.radians(spec.REST_DEG)),
        )
    )
    return objects, cuff


# ---------------------------------------------------------------------------
# The hand (moving parts)
# ---------------------------------------------------------------------------


def _place(obj, matrix):
    obj.data.transform(matrix)
    obj.data.update()
    return obj


def build_hand_parts(materials) -> dict[str, dict]:
    """The palm and the five digits, each a separate posable part."""

    skin = materials[f"{MOD_ID}_foam_latex"]
    nail = materials[f"{MOD_ID}_nail"]
    to_world = hand_sculpt.hand_to_world(spec)

    parts: dict[str, dict] = {}

    palm = hand_sculpt.build_palm(spec, f"{MOD_ID}_palm", skin)
    _place(palm, to_world)
    parts["hand"] = {"objects": [palm], "pivot": tuple(WRIST)}

    surfaces = hand_sculpt.digit_surfaces(spec)
    for name in spec.DIGIT_ORDER:
        surface = surfaces[name]
        digit = hand_sculpt.build_digit(spec, f"{MOD_ID}_digit_{name}", surface, skin)
        _place(digit, to_world)
        plate = hand_sculpt.build_nail(spec, f"{MOD_ID}_nail_{name}", surface, nail)
        _place(plate, to_world)
        parts[f"finger_{name}"] = {
            "objects": [digit, plate],
            "pivot": tuple(spec.DIGIT_PIVOTS[name]),
        }

    # THE STRAPS. The reference prop's fingers are bound into one paddle by
    # two black elastic bands — it is the single loudest "this is THAT
    # prop" detail, and it settles the old splay-versus-distance argument
    # honestly: separated fingers SHOULD read as one mass, because on the
    # real prop they are strapped into one. Each band is the convex hull
    # of the four fingers' actual surface sections at its station, offset
    # outward and pillowed at the edges. Built into the HAND part: with
    # the curls at 9-15 deg and the twitch a few degrees of extension, the
    # fingers move millimetres against a rubber band authored proud of the
    # skin, and rubber stretches.
    rig = materials[f"{MOD_ID}_rig_black"]
    # The bands are cut on FIXED PLANES perpendicular to the finger run,
    # not at a per-digit fraction: four digits of four lengths sampled at
    # one t are not coplanar, and the first build's bands came out as
    # diagonal rods binding the knuckles. Each plane collects every digit
    # surface point within its slab, hulls them, and the band hugs
    # whatever actually crosses it.
    finger_names = ("index", "middle", "ring", "little")
    mean_dir = Vector((0.0, 0.0, 0.0))
    for name in finger_names:
        finger_surface = surfaces[name]
        mean_dir = mean_dir + (
            finger_surface.point(0.6, 0.0) - finger_surface.point(0.1, 0.0))
    mean_dir.normalize()
    anchor = surfaces["middle"].point(0.0, 0.0)
    for band_index, along_m in enumerate((1.05, 2.30)):
        plane_point = anchor + mean_dir * along_m
        slab = []
        for name in finger_names:
            finger_surface = surfaces[name]
            for step in range(70):
                t = 0.02 + 0.76 * step / 69.0
                for column in range(16):
                    theta = TWO_PI * column / 16.0
                    point = finger_surface.point(t, theta)
                    if abs((point - plane_point).dot(mean_dir)) < 0.10:
                        slab.append(point)
        if len(slab) < 8:
            continue
        centroid = Vector((0.0, 0.0, 0.0))
        for point in slab:
            centroid = centroid + point
        centroid = centroid / len(slab)
        basis_a = mean_dir.cross(Vector((0.0, 0.0, 1.0)))
        if basis_a.length < 1e-4:
            basis_a = mean_dir.cross(Vector((0.0, 1.0, 0.0)))
        basis_a.normalize()
        basis_b = mean_dir.cross(basis_a).normalized()
        flat = []
        for point in slab:
            offset = point - centroid
            flat.append((offset.dot(basis_a), offset.dot(basis_b)))
        # Chaikin-rounded: the raw hull is a dozen hard corners that
        # rendered as faceted flat bar. Two passes turn it into the soft
        # loop a rubber band actually is.
        hull = _chaikin(_convex_hull_2d(flat), 2)

        def hull_ring(proud, along):
            ring = []
            for u, v in hull:
                length = math.hypot(u, v) or 1e-6
                grow = (length + proud) / length
                ring.append(
                    centroid
                    + basis_a * (u * grow)
                    + basis_b * (v * grow)
                    + mean_dir * along
                )
            ring.append(ring[0])
            return ring

        strap = add_loft(
            f"{MOD_ID}_finger_strap{band_index}",
            [
                hull_ring(0.030, -0.21),
                hull_ring(0.068, -0.13),
                hull_ring(0.068, 0.13),
                hull_ring(0.030, 0.21),
            ],
            rig,
            uv_scale=(0.8, 0.8),
            cap_start=True,
            cap_end=True,
        )
        _place(strap, to_world)
        parts["hand"]["objects"].append(strap)
    return parts


def _chaikin(loop, passes):
    """Corner-cutting for a closed 2D loop: hard hull corners -> rubber."""

    for _ in range(passes):
        smoothed = []
        count = len(loop)
        for index in range(count):
            ax, ay = loop[index]
            bx, by = loop[(index + 1) % count]
            smoothed.append((0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by))
            smoothed.append((0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by))
        loop = smoothed
    return loop


def _convex_hull_2d(points):
    """Andrew's monotone chain. Tiny, dependency-free, deterministic."""

    ordered = sorted(set(points))
    if len(ordered) <= 2:
        return list(ordered)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------


def add_decal_plate(name, centre, dimensions, material, *, facing=-1.0):
    """A thin plate whose printed face carries an exact 0..1 UV.

    ``facing`` is the y direction the print looks along: -1 for the console
    fascia, +1 for the builder's plate on the back. u runs with +x on a
    -y-facing plate (the world mirror puts authored -x on the viewer's
    left, which is the convention spec._u documents) and mirrors on a
    +y-facing one; v runs with +z on both.
    """

    plate = bk.add_box(name, centre, dimensions, material, bevel=0.0)
    mesh = plate.data
    layer = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    half_x, _half_y, half_z = (value / 2.0 for value in dimensions)
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            point = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            u = (point.x - centre[0]) / (2.0 * half_x) + 0.5
            if facing > 0.0:
                u = 1.0 - u
            layer.data[loop_index].uv = (
                u, (point.z - centre[2]) / (2.0 * half_z) + 0.5
            )
    return plate


def crisp_edges(obj, width=None):
    """Re-cut proplib's default bevel as ONE 45-degree chamfer.

    _finish_primitive fits a 2-segment bevel, and on a right angle those
    two 30-degree steps both sit under the 38-degree auto-smooth angle, so
    they shade into each other as a soft round. One segment lands at 45
    degrees to both neighbours and stays a crisp machined arris. (Boot of
    Doom console rebuild, 2026-08-13.)
    """

    for modifier in list(obj.modifiers):
        if modifier.type == "BEVEL":
            obj.modifiers.remove(modifier)
    modifier = obj.modifiers.new("Bevel", "BEVEL")
    modifier.width = width if width is not None else spec.EDGE_EASE
    modifier.segments = 1
    modifier.limit_method = "ANGLE"
    return obj


def build_console(materials) -> list:
    cream = materials[f"{MOD_ID}_console_cream"]
    walnut = materials[f"{MOD_ID}_console_walnut"]
    legend = materials[f"{MOD_ID}_panel_legend"]
    plate_data = materials[f"{MOD_ID}_plate_data"]
    steel = materials[f"{MOD_ID}_steel"]
    bakelite = materials[f"{MOD_ID}_btn_bakelite"]
    objects = []

    cx, cy = spec.CONSOLE_CX, spec.CONSOLE_CY
    case_h = spec.CASE_Z1 - spec.CASE_Z0
    case_cz = (spec.CASE_Z0 + spec.CASE_Z1) / 2.0
    case_cy = spec.CONSOLE_FACE_Y + spec.CASE_D / 2.0

    objects.append(
        crisp_edges(
            bk.add_box(
                f"{MOD_ID}_case",
                (cx, case_cy, case_cz),
                (spec.CASE_W - 2.0 * spec.CHEEK_T, spec.CASE_D, case_h),
                cream,
                bevel=spec.EDGE_EASE,
                metric_uv=(1.9, 1.9),
            )
        )
    )
    for sign in (-1.0, 1.0):
        cheek_x = cx + sign * (spec.CASE_W - spec.CHEEK_T) / 2.0
        objects.append(
            crisp_edges(
                bk.add_box(
                    f"{MOD_ID}_cheek{'p' if sign > 0 else 'm'}",
                    (cheek_x, case_cy - spec.FRAME_PROUD / 2.0, case_cz),
                    (spec.CHEEK_T, spec.CASE_D + spec.FRAME_PROUD, case_h),
                    walnut,
                    bevel=spec.EDGE_EASE,
                    metric_uv=(2.4, 2.4),
                )
            )
        )
    objects.append(
        crisp_edges(
            bk.add_box(
                f"{MOD_ID}_cap",
                (cx, case_cy - spec.FRAME_PROUD / 2.0, spec.CASE_Z1 + spec.CAP_T / 2.0),
                (
                    spec.CASE_W + 2.0 * spec.CAP_LIP,
                    spec.CASE_D + spec.FRAME_PROUD + 2.0 * spec.CAP_LIP,
                    spec.CAP_T,
                ),
                walnut,
                bevel=spec.EDGE_EASE,
                metric_uv=(2.4, 2.4),
            )
        )
    )
    objects.append(
        crisp_edges(
            bk.add_box(
                f"{MOD_ID}_kick",
                (cx, case_cy - spec.FRAME_PROUD / 2.0, spec.CASE_Z0 - 0.055),
                (spec.CASE_W, spec.CASE_D + spec.FRAME_PROUD, 0.11),
                cream,
                bevel=spec.EDGE_EASE,
                metric_uv=(1.9, 1.9),
            )
        )
    )
    # Understructure and four splayed feet under the four cap corners.
    for sign_x in (-1.0, 1.0):
        for sign_y in (-1.0, 1.0):
            foot_x = cx + sign_x * (spec.CASE_W / 2.0 - spec.BASE_INSET)
            foot_y = case_cy + sign_y * (spec.CASE_D / 2.0 - spec.BASE_INSET)
            objects.append(
                crisp_edges(
                    bk.add_box(
                        f"{MOD_ID}_leg{'p' if sign_x > 0 else 'm'}{'p' if sign_y > 0 else 'm'}",
                        (foot_x, foot_y, (spec.CASE_Z0 - 0.11) / 2.0 + spec.FOOT_Z),
                        (0.055, 0.055, spec.CASE_Z0 - 0.11),
                        steel,
                        bevel=spec.EDGE_EASE,
                        metric_uv=(0.4, 0.6),
                    )
                )
            )
            objects.append(
                crisp_edges(
                    bk.add_box(
                        f"{MOD_ID}_foot{'p' if sign_x > 0 else 'm'}{'p' if sign_y > 0 else 'm'}",
                        (foot_x, foot_y, spec.FOOT_Z / 2.0),
                        (spec.BOLT_PLATE, spec.BOLT_PLATE, spec.FOOT_Z),
                        steel,
                        bevel=spec.EDGE_EASE,
                        metric_uv=(0.3, 0.3),
                    )
                )
            )
    for sign_y in (-1.0, 1.0):
        rail_y = case_cy + sign_y * (spec.CASE_D / 2.0 - spec.BASE_INSET)
        objects.append(
            crisp_edges(
                bk.add_box(
                    f"{MOD_ID}_baserail{'p' if sign_y > 0 else 'm'}",
                    (cx, rail_y, spec.CASE_Z0 - 0.145),
                    (
                        spec.CASE_W - 2.0 * spec.BASE_INSET,
                        spec.BASE_RAIL_T,
                        spec.BASE_RAIL_H,
                    ),
                    steel,
                    bevel=spec.EDGE_EASE,
                    metric_uv=(0.6, 0.4),
                )
            )
        )

    # EXPLICIT 0..1 UVs on the face that carries the text. This box had
    # neither metric_uv nor any UV assignment, so it inherited whatever
    # Blender's default cube unwrap gave it — while spec._u() and spec._v()
    # author every label position against a mapping the geometry never
    # provided. The panel read as "AP | CO | TR" with the type running
    # bottom to top. It is the one surface in the build whose texture is
    # TEXT, so orientation is not cosmetic.
    objects.append(
        add_decal_plate(
            f"{MOD_ID}_legend",
            (cx, spec.PLATE_Y, spec.PLATE_Z0 + spec.PLATE_H / 2.0),
            (spec.PLATE_W, 0.012, spec.PLATE_H),
            legend,
            facing=-1.0,
        )
    )
    # Builder's plate on the back, screwed down at four corners.
    back_y = case_cy + spec.CASE_D / 2.0 + 0.007
    plate_x = cx + (spec.CASE_W / 2.0 - spec.BACK_PLATE_MARGIN_X - spec.BACK_PLATE_W / 2.0)
    plate_z = spec.CASE_Z0 + spec.BACK_PLATE_MARGIN_Z + spec.BACK_PLATE_H / 2.0
    objects.append(
        add_decal_plate(
            f"{MOD_ID}_dataplate",
            (plate_x, back_y, plate_z),
            (spec.BACK_PLATE_W, 0.008, spec.BACK_PLATE_H),
            plate_data,
            facing=1.0,
        )
    )
    for sign_x in (-1.0, 1.0):
        for sign_z in (-1.0, 1.0):
            screw = Vector(
                (
                    plate_x + sign_x * (spec.BACK_PLATE_W / 2.0 - spec.BACK_PLATE_SCREW_INSET),
                    back_y + 0.004,
                    plate_z + sign_z * (spec.BACK_PLATE_H / 2.0 - spec.BACK_PLATE_SCREW_INSET),
                )
            )
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_dataplate_screw{int(sign_x)}{int(sign_z)}",
                    (screw.x, screw.y, screw.z),
                    spec.BACK_PLATE_SCREW_R,
                    0.006,
                    steel,
                    vertices=10,
                    axis="Y",
                )
            )

    for button in spec.PANEL_BUTTONS:
        cap_centre = (cx + button["dx"], spec.PLATE_Y - 0.032, button["z"])
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_{button['id']}_cap",
                cap_centre,
                0.062,
                0.058,
                bakelite,
                vertices=28,
                axis="Y",
                metric_uv=(2.0 * math.pi * 0.062, 0.06),
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_{button['id']}_bezel",
                (cap_centre[0], spec.PLATE_Y - 0.010, cap_centre[2]),
                0.082,
                0.016,
                steel,
                vertices=28,
                axis="Y",
            )
        )
    return objects


def build_console_parts(materials) -> dict[str, dict]:
    amber = materials[f"{MOD_ID}_seg_amber"]
    red = materials[f"{MOD_ID}_seg_red"]
    green = materials[f"{MOD_ID}_seg_green"]
    parts: dict[str, dict] = {}

    cx = spec.CONSOLE_CX
    face_y = spec.PLATE_Y - 0.014
    for index in range(1, spec.BEHAVIOR["power_levels"] + 1):
        dx = spec.POWER_SEG_DX0 + spec.POWER_SEG_PITCH * (index - 1)
        centre = (cx + dx, face_y, spec.POWER_ROW_Z)
        parts[f"pow_seg{index}"] = {
            "objects": [
                bk.add_box(
                    f"{MOD_ID}_pow_seg{index}",
                    centre,
                    (0.060, 0.020, 0.036),
                    red if index >= 8 else amber,
                    bevel=0.004,
                )
            ],
            "pivot": centre,
        }
    for index in range(1, spec.BEHAVIOR["tilt_levels"] + 1):
        dx = spec.TILT_SEG_DX0 + spec.TILT_SEG_PITCH * (index - 1)
        centre = (cx + dx, face_y, spec.TILT_ROW_Z)
        parts[f"tilt_seg{index}"] = {
            "objects": [
                bk.add_box(
                    f"{MOD_ID}_tilt_seg{index}",
                    centre,
                    (0.060, 0.020, 0.036),
                    amber if index >= 6 else green,
                    bevel=0.004,
                )
            ],
            "pivot": centre,
        }
    # THE ARMED BEACON: a dome on the console roof, glowing at the
    # centrifuge's 1800-nit conspicuity so the approach lane can read the
    # machine's state at range, day or dusk. The 9 cm arming slide the old
    # 8 cm jelly-bean performed invisibly now moves something a driver can
    # actually see.
    beacon_mat = materials[f"{MOD_ID}_beacon_red"]
    steel = materials[f"{MOD_ID}_steel"]
    cy = spec.CONSOLE_CY
    roof_z = spec.CASE_Z1 + 0.02
    lamp = (cx, cy, roof_z + 0.10)
    beacon_parts = [
        bk.add_cylinder(
            f"{MOD_ID}_beacon_base",
            (cx, cy, roof_z + 0.03),
            0.115,
            0.06,
            steel,
            vertices=28,
            axis="Z",
            metric_uv=(2.0 * math.pi * 0.115, 0.1),
        ),
        bk.add_sphere(
            f"{MOD_ID}_armed_lamp",
            lamp,
            0.105,
            beacon_mat,
            segments=48,
            rings=28,
            scale=(1.0, 1.0, 1.25),
        ),
    ]
    parts["armed_lamp"] = {
        "objects": beacon_parts,
        "pivot": lamp,
    }
    return parts


# ---------------------------------------------------------------------------
# Road markings and shoulder furniture
# ---------------------------------------------------------------------------


def add_tapered_pad(name, material) -> object:
    """The slap pad as a poured hump: a flat painted plateau whose edges
    roll to grade on all four sides along a smoothstep S-curve. Border,
    hazard chevrons and the painted hand are PAINT in the map, never
    geometry — marking plates on a drivable surface betray themselves by
    casting shadows and catching edge light."""

    half_x, half_y = 4.30, 4.30
    height = 0.11
    skirt = 0.55
    corner_r = 0.16
    arc_segments = 8
    ring_params = (0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.0)

    def ring_points(u):
        offset = skirt * u
        smooth = u * u * (3.0 - 2.0 * u)
        z = -0.015 if u >= 1.0 else height * (1.0 - smooth)
        radius = corner_r + offset
        points = []
        corners = (
            ((half_x - corner_r), (half_y - corner_r), 0.0),
            (-(half_x - corner_r), (half_y - corner_r), 90.0),
            (-(half_x - corner_r), -(half_y - corner_r), 180.0),
            ((half_x - corner_r), -(half_y - corner_r), 270.0),
        )
        for cx, cy, start in corners:
            for step in range(arc_segments + 1):
                angle = math.radians(start + 90.0 * step / arc_segments)
                points.append(
                    (cx + radius * math.cos(angle), cy + radius * math.sin(angle), z)
                )
        return points

    bm = bmesh.new()
    rings = [[bm.verts.new(point) for point in ring_points(u)] for u in ring_params]
    count = len(rings[0])
    for inner, outer in zip(rings, rings[1:]):
        for i in range(count):
            j = (i + 1) % count
            bm.faces.new((inner[i], outer[i], outer[j], inner[j]))
    cap = bm.faces.new(tuple(reversed(rings[0])))
    bmesh.ops.triangulate(bm, faces=[cap])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    full_x, full_y = half_x + skirt, half_y + skirt
    layer = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        x, y, _z = mesh.vertices[loop.vertex_index].co
        layer.data[loop.index].uv = (x / (2.0 * full_x) + 0.5, y / (2.0 * full_y) + 0.5)
    return bk._finish_primitive(obj, name, material, 0.0)


def build_ground(materials) -> list:
    pad = materials[f"{MOD_ID}_slap_pad"]
    hazard = materials[f"{MOD_ID}_hazard"]
    rig = materials[f"{MOD_ID}_rig_black"]
    objects = [add_tapered_pad(f"{MOD_ID}_pad", pad)]
    # Shoulder bollards on the mast side only: the far shoulder is where
    # the car is supposed to end up.
    for index, along in enumerate(spec.BOLLARD_Y):
        centre = Vector((spec.BOLLARD_X, along, 0.0))
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_bollard{index}",
                (centre.x, centre.y, 0.16 + spec.BOLLARD_HEIGHT / 2.0),
                0.20,
                spec.BOLLARD_HEIGHT,
                hazard,
                vertices=20,
                axis="Z",
                metric_uv=(2.0 * math.pi * 0.16, 0.6),
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_bollard_base{index}",
                (centre.x, centre.y, 0.08),
                0.42,
                0.16,
                rig,
                vertices=24,
                axis="Z",
                metric_uv=(2.0 * math.pi * 0.42, 0.3),
            )
        )
    return objects


# ---------------------------------------------------------------------------
# Cage
# ---------------------------------------------------------------------------


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)

    pad = cage.add_box_lattice(
        "pad",
        (-4.30, -4.30, 0.0),
        (4.30, 4.30, 0.11),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("top",),
        face_ground_models={"top": "asphalt"},
    )
    # Skirt matching the tapered visual, ridden as four sloped quads.
    skirt = {}
    for corner, sx, sy in (("nw", -1, 1), ("ne", 1, 1), ("se", 1, -1), ("sw", -1, -1)):
        skirt[corner] = cage.add_node(
            f"pad_skirt_{corner}", (sx * 4.85, sy * 4.85, 0.0), fixed=True
        )
    top = {"nw": pad[(0, 2, 1)], "ne": pad[(2, 2, 1)], "se": pad[(2, 0, 1)], "sw": pad[(0, 0, 1)]}
    bottom = {"nw": pad[(0, 2, 0)], "ne": pad[(2, 2, 0)], "se": pad[(2, 0, 0)], "sw": pad[(0, 0, 0)]}
    for corner in skirt:
        cage.add_beam(skirt[corner], top[corner])
        cage.add_beam(skirt[corner], bottom[corner])
    for a, b in (("nw", "ne"), ("ne", "se"), ("se", "sw"), ("sw", "nw")):
        cage.add_quad_both([skirt[a], skirt[b], top[b], top[a]], ground_model="asphalt")

    # The mast is the only genuinely solid thing on the machine, and a
    # driver WILL hit it. Full collision box, grout pad to slew ring.
    mast = cage.add_box_lattice(
        "mast",
        (spec.MAST_X - spec.MAST_BASE / 2.0, spec.MAST_Y - spec.MAST_BASE / 2.0, 0.0),
        (spec.MAST_X + spec.MAST_BASE / 2.0, spec.MAST_Y + spec.MAST_BASE / 2.0,
         spec.MAST_TOP_Z),
        subdivisions=(1, 1, 2),
        fixed=True,
        collision=False,
        collision_faces=("top", "north", "south", "east", "west"),
    )
    plate = cage.add_box_lattice(
        "mastplate",
        (spec.MAST_X - spec.MAST_PLATE[0] / 2.0, spec.MAST_Y - spec.MAST_PLATE[1] / 2.0, 0.0),
        (spec.MAST_X + spec.MAST_PLATE[0] / 2.0, spec.MAST_Y + spec.MAST_PLATE[1] / 2.0, 0.64),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("top", "north", "south", "east", "west"),
    )
    for ix in (0, 1):
        for iy in (0, 1):
            cage.stitch(mast[(ix, iy, 0)], plate[(ix, iy, 0)])
            cage.stitch(mast[(ix, iy, 1)], plate[(ix, iy, 1)])
    cage.add_beam(plate[(0, 0, 0)], pad[(0, 0, 0)])
    cage.add_beam(plate[(1, 1, 0)], pad[(0, 2, 0)])

    # Console cage. Front face sits BEHIND the legend plate and the caps,
    # so every click box floats in free air ahead of the cage (the
    # centrifuge round-15 hover lesson).
    cx = spec.CONSOLE_CX
    ccy = spec.CONSOLE_FACE_Y + spec.CASE_D / 2.0
    console: dict[tuple[int, int, int], str] = {}
    for ix, cyy in ((0, ccy - 0.26), (1, ccy + 0.32)):
        for iy, cxx in ((0, cx - 0.95), (1, cx + 0.95)):
            for iz, cz in ((0, 0.0), (1, 1.78)):
                console[(ix, iy, iz)] = cage.add_node(
                    f"console_{ix}_{iy}_{iz}", (cxx, cyy, cz),
                    fixed=True, collision=True, weight=60.0,
                )
    for ix in (0, 1):
        for iy in (0, 1):
            cage.add_beam(console[(ix, iy, 0)], console[(ix, iy, 1)])
    for iz in (0, 1):
        cage.add_beam(console[(0, 0, iz)], console[(1, 0, iz)])
        cage.add_beam(console[(0, 1, iz)], console[(1, 1, iz)])
        cage.add_beam(console[(0, 0, iz)], console[(0, 1, iz)])
        cage.add_beam(console[(1, 0, iz)], console[(1, 1, iz)])
    cage.add_beam(console[(0, 0, 0)], console[(1, 1, 1)])
    for quad in (
        [console[(0, 0, 0)], console[(0, 1, 0)], console[(0, 1, 1)], console[(0, 0, 1)]],
        [console[(1, 0, 0)], console[(1, 1, 0)], console[(1, 1, 1)], console[(1, 0, 1)]],
        [console[(0, 0, 0)], console[(1, 0, 0)], console[(1, 0, 1)], console[(0, 0, 1)]],
        [console[(0, 1, 0)], console[(1, 1, 0)], console[(1, 1, 1)], console[(0, 1, 1)]],
        [console[(0, 0, 1)], console[(1, 0, 1)], console[(1, 1, 1)], console[(0, 1, 1)]],
    ):
        cage.add_quad_both(quad)
    cage.add_beam(console[(1, 0, 0)], mast[(0, 0, 0)])
    cage.add_beam(console[(1, 1, 0)], mast[(1, 0, 0)])
    cage.add_beam(console[(0, 0, 0)], pad[(0, 0, 0)])

    # Panel click anchors: 9 cm proud of the plate, collisionless, with a
    # per-button orthonormal frame pair in the face plane so no hitbox
    # inherits a skewed shared basis.
    for button in spec.PANEL_BUTTONS:
        anchor = (cx + button["dx"], spec.BUTTON_ANCHOR_Y, button["z"])
        anchor_id = cage.add_node(
            f"panelbtn_{button['id']}", anchor, fixed=True, collision=False, weight=20.0
        )
        cage.add_beam(anchor_id, console[(0, 0, 1)])
        # 0.28, not 0.4: the button row pitch is 0.36, so a 0.4 frame
        # offset put one button's vertical frame node 40 mm from the next
        # button's anchor. Same family as the centrifuge's invisible-band
        # trap, and it costs nothing to avoid.
        for tag, off in (("fx", (0.28, 0.0, 0.0)), ("fy", (0.0, 0.0, 0.28))):
            frame_id = cage.add_node(
                f"panel{tag}_{button['id']}",
                (anchor[0] + off[0], anchor[1] + off[1], anchor[2] + off[2]),
                fixed=True, collision=False, weight=20.0,
            )
            cage.add_beam(frame_id, console[(0, 1, 1)])
    frame_x_node = cage.add_node(
        "panel_frame_x", (cx + 0.9, spec.BUTTON_ANCHOR_Y, 1.5),
        fixed=True, collision=False, weight=20.0,
    )
    frame_y_node = cage.add_node(
        "panel_frame_y", (cx, spec.BUTTON_ANCHOR_Y, 2.0),
        fixed=True, collision=False, weight=20.0,
    )
    cage.add_beam(frame_x_node, console[(0, 1, 1)])
    cage.add_beam(frame_y_node, console[(0, 0, 1)])

    # Guy anchor blocks, so the chains land on something solid.
    for index, azimuth in enumerate((SAFE_AZIMUTH - 38.0, SAFE_AZIMUTH + 38.0)):
        anchor = azimuth_point(azimuth, 9.80, 0.0)
        block = cage.add_box_lattice(
            f"guy{index}",
            (anchor.x - 1.05, anchor.y - 1.05, 0.0),
            (anchor.x + 1.05, anchor.y + 1.05, 1.04),
            subdivisions=(1, 1, 1),
            fixed=True,
            collision=False,
            collision_faces=("top", "north", "south", "east", "west"),
        )
        cage.add_beam(block[(0, 0, 0)], mast[(0, 0, 0)])
        cage.add_beam(block[(1, 1, 0)], mast[(1, 1, 0)])

    # refNodes. The datum is the pad centre at grade, which is also the
    # strike point, so everything the runtime dead-reckons is measured from
    # the place the palm actually arrives. back/left/up are picked for
    # CONDITIONING, not for distance: 4.3 m and 4.3 m of genuinely
    # perpendicular baseline, and a 1.78 m up node on the console, give
    # propFrame three well-separated pairs to choose from.
    cage.set_refnodes_existing(
        ref=pad[(1, 1, 0)],
        back=pad[(1, 0, 0)],
        left=pad[(0, 1, 0)],
        up=console[(0, 0, 1)],
    )
    cage.set_spawn_envelope(
        [
            skirt["nw"], skirt["ne"], skirt["se"], skirt["sw"],
            mast[(0, 0, 2)], mast[(1, 1, 2)],
            plate[(0, 0, 0)], plate[(1, 1, 0)],
        ]
    )
    cage.auto_base_nodes()
    return cage


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------


def build_studio_stage():
    """Neutral studio floor + three-point light rig for the review and
    listing renders. Replaces the world, so it runs last."""

    world = bpy.data.worlds.new("high_five_studio")
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.055, 0.058, 0.065, 1.0)
    background.inputs[1].default_value = 1.0
    bpy.context.scene.world = world

    bpy.ops.mesh.primitive_plane_add(size=260.0, location=(0.0, 0.0, -0.02))
    floor = bpy.context.object
    floor.name = f"{MOD_ID}_studio_floor"
    material = bpy.data.materials.new("high_five_studio_floor")
    material.use_nodes = True
    bsdf = material.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.16, 0.165, 0.175, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.86
    floor.data.materials.append(material)

    # Area lights in the megawatts blew the thumbnail to pure white. The
    # thumbnail pass already adds its own sun (render_thumbnail), so these
    # are FILLS: enough to open the shadow side of a matte black machine
    # and no more.
    lights = []
    for name, location, energy, size in (
        ("key", (18.0, -34.0, 30.0), 90000.0, 22.0),
        ("fill", (-30.0, -18.0, 16.0), 34000.0, 30.0),
        ("rim", (-6.0, 26.0, 24.0), 52000.0, 18.0),
    ):
        data = bpy.data.lights.new(f"high_five_{name}", type="AREA")
        data.energy = energy
        data.size = size
        light = bpy.data.objects.new(f"high_five_{name}", data)
        bpy.context.collection.objects.link(light)
        light.location = location
        direction = Vector((-6.0, -8.0, 3.0)) - Vector(location)
        light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        lights.append(light)
    return [floor] + lights


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    bk.reset_scene()
    materials = build_materials()

    visual_objects: list = []
    visual_objects.extend(build_mast(materials))
    visual_objects.extend(build_console(materials))
    visual_objects.extend(build_ground(materials))

    part_builds: dict[str, dict] = {}
    arm_objects, cuff_objects = build_arm(materials)
    part_builds["arm"] = {"objects": arm_objects, "pivot": (spec.MAST_X, spec.MAST_Y, 0.0)}
    # Pivoted on the WRIST, like the hand it holds, so the two take the
    # same roll drop and the stump cannot pull out of its own bore.
    part_builds["wrist"] = {"objects": cuff_objects, "pivot": tuple(WRIST)}
    part_builds.update(build_hand_parts(materials))
    part_builds.update(build_console_parts(materials))

    parts = []
    for name, build in sorted(part_builds.items()):
        dae_path = VEHICLE_DIR / f"{MOD_ID}_{name}.dae"
        info = bk.export_part_shape(MOD_ID, name, dae_path, build["objects"], build["pivot"])
        info["path"] = f"vehicles/{MOD_ID}/{MOD_ID}_{name}.dae"
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
            "buttons": [
                {
                    "id": button["id"],
                    "title": button["title"],
                    "node": f"{MOD_ID}_panelbtn_{button['id']}",
                    "frame_x_node": f"{MOD_ID}_panelfx_{button['id']}",
                    "frame_y_node": f"{MOD_ID}_panelfy_{button['id']}",
                    "size": 0.12,
                }
                for button in spec.PANEL_BUTTONS
            ],
        },
        behavior={
            "tunables": behavior,
            "triggers": spec.TRIGGERS,
            "effects": spec.EFFECTS,
            "camera_distance": behavior.get("camera_distance", 40.0),
        },
    )

    # Review renders, framed off the geometry rather than off remembered
    # coordinates: every camera in the first pass was authored against the
    # pre-rescale machine and pointed at open sky afterwards.
    hand_centre = WRIST + U * (spec.HAND_LENGTH * 0.42) + N * 0.20
    tip = WRIST + U * (spec.HAND_LENGTH * 0.88)
    thumb = Vector(spec.DIGIT_PIVOTS["thumb"]) + N * 1.2 + UP * 2.6
    console = Vector((spec.CONSOLE_CX, spec.CONSOLE_CY, 1.25))
    # The review rig's own lighting, and it is evidence-grade rather than
    # pretty. The kit's default is a full-strength sky at 0.72/0.82/0.92,
    # which on this prop measured as a 69-count neutral pedestal: it halved
    # the rendered chroma (R-B 35 against the authored 72) and put the
    # darkest 15% of the hand at luma 135 where the reference photograph
    # reaches 63. Two material changes came out as a ONE-count difference
    # under it. A dim sky plus a stronger sun gives shadows that reach, so
    # what these frames show is what the material does.
    REVIEW_LIGHT = {
    # MEASURED against the reference photograph, not guessed, and the metric
    # that matters is SATURATION because it is exposure-invariant. The kit's
    # default sky put a 69-count neutral pedestal on every frame: rendered
    # saturation 0.22 against the reference hand's 0.41, shadows bottoming
    # out at luma 135 against 66, and two separate material changes
    # measuring as a ONE-count difference. A dim sky with a strong sun gets
    # saturation back to within about a tenth of the photograph, which is
    # what makes these frames evidence rather than decoration.
        # 8.5, measured. Pushing it to 26 to match the photograph's MEAN
        # luma blew the matte-black mast out to a grey specular sheen and
        # took saturation back down to 0.33: a photograph carries its own
        # exposure and matching it is not the goal. Matching SATURATION is,
        # because that is the exposure-invariant one, and at 8.5/0.55 it
        # lands at 0.407 against the reference hand's 0.407.
        "sun_energy": 8.5,
        "world_color": (0.20, 0.24, 0.31),
        "world_strength": 0.55,
    }
    review = AUTHORING_ROOT / "review"
    # CLEAR THE FOLDER FIRST. Renaming a camera writes the new frame and
    # leaves the old one sitting there, and a stale render in an evidence
    # folder is worse than a missing one: two frames called `ulnar_edge`
    # and `ulnar_close` survived a rename here, and they were shots of a
    # crest lit on 0 of 955 sampled points — the two images in the set that
    # proved nothing, under names that read like they were about the seam.
    # Nothing ships from this folder and no gate reads it, which is exactly
    # why a ghost would have stayed indefinitely.
    review.mkdir(parents=True, exist_ok=True)
    for stale in review.glob("*.jpg"):
        stale.unlink()
    for render_name, camera_location, look_at in (
        ("wide", (14.0, -30.0, 11.0), (-8.0, -7.0, 4.5)),
        ("machine", (4.0, -22.0, 8.0), (-9.5, -6.0, 5.0)),
        ("mast", (-1.0, -12.0, 5.0), (spec.MAST_X, spec.MAST_Y, 5.5)),
        ("hub", (-4.0, -10.0, 13.5), (spec.MAST_X, spec.MAST_Y, 9.6)),
        ("elbow", (-5.0, -11.0, 7.5), tuple(ELBOW)),
        # The console FACES -Y. Shooting it from +N framed the blank cream
        # side panel and its vent, and you cannot sign off a legend plate
        # you never photographed.
        # From the ROAD side, not from straight in front. The cabinet faces
        # -Y, and the parked arm sits at azimuth REST_DEG on exactly that
        # bearing — so a face-on camera puts the wrist collar between the
        # lens and the panel, which is what the first two console renders
        # actually photographed.
        ("console", (-4.6, spec.CONSOLE_CY - 2.6, 1.65), tuple(console)),
        ("console_wide", (-2.4, spec.CONSOLE_CY - 6.0, 2.8),
         (spec.CONSOLE_CX, spec.CONSOLE_CY + 1.0, 1.5)),
        # Driver's eye, 40 m up the road: the only view that matters, and
        # the only one that answers "would you know that was a hand".
        ("driver_far", (0.0, -44.0, 1.25), (-6.0, -12.0, 3.0)),
        ("driver_near", (0.0, -20.0, 1.25), (-7.0, -11.0, 3.0)),
        ("palm", tuple(hand_centre + N * 15.0 + UP * 4.0), tuple(hand_centre)),
        ("palm_close", tuple(hand_centre + N * 6.0 + UP * 1.4), tuple(hand_centre)),
        ("back_of_hand", tuple(hand_centre - N * 14.0 + UP * 5.0), tuple(hand_centre)),
        ("fingertips", tuple(tip + N * 6.5 + UP * 2.6), tuple(tip)),
        ("thumb", tuple(thumb + N * 6.0 + UP * 1.5), tuple(thumb - UP * 1.2)),
        ("wrist", tuple(WRIST - U * 2.0 + N * 7.5 + UP * 3.0), tuple(WRIST - U * 1.2)),
        ("pad", (5.0, -9.0, 5.0), (0.0, 0.0, 0.2)),
        # The machine's BACK: counterweight, hangers, tail beam. Every
        # other camera faces the boom side, which is how 29 tonnes of
        # carried plate went entirely unphotographed for a full review
        # round.
        ("head_rear", (-22.0, 9.0, 12.5),
         (spec.MAST_X, spec.MAST_Y, 9.6)),
        # THE SEAM SHOTS, and the side matters more than the obliquity.
        #
        # A two-part mould splits on the SILHOUETTE, so the parting line
        # runs along +/-V and no camera looking down the volar/dorsal axis
        # can show it — that much was right, and it is why three rounds of
        # critics could not find a seam that was really there. What was
        # wrong was which edge. V_REST is (0, 0, 1): the thumb axis points
        # at the sky in the rest pose, so the RADIAL crest faces up and is
        # lit on every one of its 955 sampled points, while the ulnar crest
        # faces the ground and is lit on NONE of them. The first pair of
        # these cameras was aimed at the ulnar edge and returned zero
        # seam evidence — a correct diagnosis pointed at the dark side.
        #
        # Solved rather than guessed: swept camera bearings counting crest
        # samples that are both front-facing and lit, weighted against
        # face-on views because a bead seen square shows neither flank.
        # Azimuth 95 deg, elevation 28 deg takes 869 of 955.
        # ONE seam shot, BROADSIDE to the line. Two earlier attempts at
        # this failed for two different reasons and both were mine.
        #
        # The first pair went to the ulnar edge, which V_REST = (0, 0, 1)
        # makes the permanently unlit side: 955 of 955 crest samples lit on
        # the radial meridian, 0 of 955 on the ulnar.
        #
        # The second pair was solved, but against a metric that could not
        # discriminate — front-facing AND lit scores ~91% at almost every
        # bearing, because it omits self-shadowing, framing and
        # self-occlusion. Worse, it ignored ORIENTATION: the crest runs
        # along the hand's long axis U, and that bearing looked 31 degrees
        # off U, i.e. down the length of the line. Foreshortened to nothing
        # with the hand's own mass stacked in front of it — 82 and 11
        # unoccluded samples, and a cross-crest gradient BELOW their own
        # no-bead controls. Optimising a proxy that cannot tell good from
        # bad returns an arbitrary answer with a confident number attached.
        #
        # Scored properly (visible AND the crest normal 30-75 degrees off
        # the view ray, so a flank shows without becoming the outline):
        # those two rated 31 and 5, `back_of_hand` 105, `thumb` 139. This
        # bearing rates 290.
        ("seam", tuple(hand_centre + Vector((-0.6124, 0.3536, 0.7071)) * 15.0),
         tuple(hand_centre)),
    ):
        bk.render_thumbnail(
            review / f"{MOD_ID}_{render_name}.jpg",
            camera_location=camera_location,
            look_at=look_at,
            resolution=(880, 660),
            **REVIEW_LIGHT,
        )
    # THE LAMP AT DUSK: the one shot the review set never had. The armed
    # lamp is the machine's only self-illumination and no daylight frame
    # can prove it reads; this is the approach-lane view a driver gets at
    # nightfall, rendered before the studio stage exists so the scene is
    # lit by the dusk sky and the lamp's own emissive alone.
    bk.render_thumbnail(
        AUTHORING_ROOT / "review" / f"{MOD_ID}_lamp_dusk.jpg",
        camera_location=(0.5, -34.0, 2.1),
        look_at=(-7.0, -4.0, 3.2),
        resolution=(880, 660),
        sun_energy=0.55,
        world_color=(0.10, 0.09, 0.15),
        world_strength=0.30,
    )
    stage = build_studio_stage()
    # THE SAME LIGHTING AS THE REVIEW SET. The studio stage adds three
    # fills on top of render_thumbnail's own sun, and the thumbnail was
    # coming out a stop hotter than _wide.jpg on the identical scene —
    # measured, the hand at (208, 199, 182) against (164, 155, 134). Every
    # bit of surface detail added this round (the crazing, the parting
    # seam, the mottle) flattened into blank pale clay in the one image
    # that is the storefront.
    # 0.05, and the number is measured rather than guessed at. 0.42 gave
    # foam saturation 0.330 and 0.22 gave 0.368, against 0.407 on the
    # reference and 0.431-0.471 across all sixteen review frames — the ONE
    # image a player sees before downloading was the only one below the
    # band. Two points on the same scene fit `foam mean R = 136.6 + 73.9 *
    # fill` with the chroma INVARIANT at 51.8, which is what proves these
    # fills are a neutral pedestal and not a light: saturation falls purely
    # because the denominator rises. Solving for 0.407 puts the multiplier
    # at essentially zero, i.e. the storefront should be lit by
    # REVIEW_LIGHT alone — which is what all sixteen review frames use and
    # what REVIEW_LIGHT's own comment argues for. 0.05 keeps the stage
    # lamps present without letting them pedestal the frame.
    for light in stage[1:]:
        light.data.energy *= 0.05
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(19.0, -36.0, 13.0),
        look_at=(-7.5, -8.0, 4.0),
        resolution=(1024, 768),
        **REVIEW_LIGHT,
    )
    print(f"HIGH_FIVE generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
