"""Deterministic Blender generator for the Spin Launch Kinetic Accelerator.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/spin_launch/blender/create_spin_launch.py

Everything the machine is made of is revolved, lofted or extruded from the
constants in ``spec.py``; nothing is hand-placed. The two structures that
matter most - the chamber and the launch tube - are generated from the SAME
tangency identity the runtime aims with, so the bore really does point where
the release tangent points at every one of the eight elevation settings.
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

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID

# Metres per texture tile on every carbon_tether surface. ONE number, because
# the weave has to be the same cloth on the blade, the counterweight arm, the
# hub caps and the cradle ribs - they used to carry 1.2 / 2.0 / 0.6 / 0.7,
# which is four different tow widths on four parts of one moulding. See the
# CARBON_UV_TILE_M derivation in spec.py for where 0.16 comes from.
CARBON_TILE = spec.CARBON_UV_TILE_M
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

HUB = Vector(spec.HUB)
SEG_DEG = 2.0  # angular resolution of every revolved chamber surface


# ---------------------------------------------------------------------------
# Frames.
#
# The chamber's spin axis is authored +X, so every point on it is naturally
# addressed as (x, radius, theta) with theta measured in the Y-Z plane from
# +Y toward +Z. These three functions are the only place that convention is
# written down; everything downstream calls them.
# ---------------------------------------------------------------------------
def ring(theta_deg: float, radius: float, x: float = 0.0) -> tuple[float, float, float]:
    theta = math.radians(theta_deg)
    return (x, radius * math.cos(theta), spec.HUB_Z + radius * math.sin(theta))


def radial_dir(theta_deg: float) -> tuple[float, float, float]:
    theta = math.radians(theta_deg)
    return (0.0, math.cos(theta), math.sin(theta))


def tangent_dir(theta_deg: float) -> tuple[float, float, float]:
    """Direction of travel at ``theta`` - theta DECREASES as the tether turns."""

    theta = math.radians(theta_deg)
    return (0.0, math.sin(theta), -math.cos(theta))


def arcs_excluding(*cuts: tuple[float, float]) -> list[tuple[float, float]]:
    """The full circle minus the given (start, end) degree windows.

    The shell openings are made by OMITTING angular spans, never by boolean
    difference: ``cut_openings`` applies boolean modifiers ahead of a pending
    bevel, which collapses the chamfer to zero area and leaves a pile of
    degenerate triangles behind (see its tombstone in blender_kit).
    """

    windows = sorted((start % 360.0, end % 360.0) for start, end in cuts)
    spans: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in windows:
        if start > cursor:
            spans.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < 360.0:
        spans.append((cursor, 360.0))
    return spans


# ---------------------------------------------------------------------------
# Mesh construction primitives.
# ---------------------------------------------------------------------------
def _finish(obj, material, smooth_angle: float = 38.0):
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(smooth_angle))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def mesh_from(name, verts, faces, material, uvs=None, smooth_angle=38.0):
    """Build one object from explicit vertex/face lists plus per-loop UVs."""

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata([tuple(v) for v in verts], [], [list(f) for f in faces])
    mesh.validate(verbose=False)
    mesh.update()
    if uvs is not None:
        layer = mesh.uv_layers.new(name="UVMap")
        for polygon, face_uv in zip(mesh.polygons, uvs, strict=False):
            for loop_index, uv in zip(polygon.loop_indices, face_uv, strict=False):
                layer.data[loop_index].uv = uv
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return _finish(obj, material, smooth_angle)


def _winding_is_wrong(a, b, c, outward) -> bool:
    """Does the quad (a, b, c, ...) face AWAY from ``outward``?

    Every open surface here is seen from exactly one side, and a backwards
    winding on a single-sided material renders as a hole. Rather than track
    a hand-picked flip flag per call - which is how the lid interiors and
    the bore liner all ended up inside out on the first pass - each builder
    states the direction the surface must FACE and the winding is derived.
    """

    normal = (Vector(b) - Vector(a)).cross(Vector(c) - Vector(a))
    if normal.length < 1e-9:
        return False
    return normal.dot(Vector(outward)) < 0.0


def grid_surface(name, material, rows, *, uv_rows=None, uv_cols=None,
                 outward=None, flip=False, smooth_angle=38.0):
    """Quad-strip surface over a rectangular grid of points.

    ``rows`` is a list of equal-length point lists. ``uv_rows`` / ``uv_cols``
    are the METRIC coordinates of each row/column - real distances in metres,
    divided by the material's tile size by the caller - so texel density
    stays true instead of stretching one tile over a 40 m wall (the Cannon
    Car Wash "tiny blocks" lesson). ``outward`` names the side the surface
    must face and overrides ``flip``.
    """

    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    uvs: list[list[tuple[float, float]]] = []
    width = len(rows[0])
    for row in rows:
        verts.extend(row)
    if uv_rows is None:
        uv_rows = list(range(len(rows)))
    if uv_cols is None:
        uv_cols = list(range(width))
    if outward is not None:
        # Scan for the first face whose normal actually has an opinion about
        # `outward`. A profiled ribbon (the shell's flange steps, a girder's
        # C-section) alternates between faces that point radially and faces
        # that point along the axis, and the first one is often exactly
        # perpendicular to the direction asked about - a zero dot product,
        # which silently reads as "already correct". Handedness is a property
        # of the whole ribbon, so ANY non-degenerate face answers for it.
        for i in range(len(rows) - 1):
            normal = (Vector(rows[i][1]) - Vector(rows[i][0])).cross(
                Vector(rows[i + 1][1]) - Vector(rows[i][0]))
            if normal.length > 1e-9 and abs(
                    normal.normalized().dot(Vector(outward).normalized())) > 0.05:
                flip = normal.dot(Vector(outward)) < 0.0
                break
    for i in range(len(rows) - 1):
        for j in range(width - 1):
            a = i * width + j
            b = i * width + j + 1
            c = (i + 1) * width + j + 1
            d = (i + 1) * width + j
            quad = (a, b, c, d) if not flip else (d, c, b, a)
            faces.append(quad)
            corner_uv = [
                (uv_cols[j], uv_rows[i]),
                (uv_cols[j + 1], uv_rows[i]),
                (uv_cols[j + 1], uv_rows[i + 1]),
                (uv_cols[j], uv_rows[i + 1]),
            ]
            uvs.append(corner_uv if not flip else corner_uv[::-1])
    return mesh_from(name, verts, faces, material, uvs, smooth_angle)


RADIAL_OUT = "radial_out"
RADIAL_IN = "radial_in"


def revolve(name, material, profile, arcs, *, step_deg=SEG_DEG,
            outward=RADIAL_OUT, uv_tile=(2.0, 2.0), smooth_angle=38.0):
    """Revolve an (x, radius) polyline about the chamber axis.

    This is the workhorse for the whole vessel: the outer shell with its
    stiffener flanges, the bore liner, both lid plates, the observation ring
    and the hub boss are all one profile each. ``outward`` is either a fixed
    authored-frame vector or one of the two radial sentinels, which are
    resolved per arc at its first sample.
    """

    objects = []
    for index, (start, end) in enumerate(arcs):
        span = end - start
        steps = max(2, int(round(span / step_deg)))
        thetas = [start + span * k / steps for k in range(steps + 1)]
        rows = []
        for x, radius in profile:
            rows.append([ring(theta, radius, x) for theta in thetas])
        # Metric UVs: u follows arc length at the profile's mean radius, v
        # follows the profile's own developed length.
        mean_r = sum(radius for _, radius in profile) / len(profile)
        uv_cols = [math.radians(theta - start) * mean_r / uv_tile[0] for theta in thetas]
        uv_rows = [0.0]
        for prev, current in zip(profile, profile[1:], strict=False):
            step = math.dist(prev, current)
            uv_rows.append(uv_rows[-1] + step / uv_tile[1])
        mid = (thetas[0] + thetas[1]) * 0.5
        if outward == RADIAL_OUT:
            face = radial_dir(mid)
        elif outward == RADIAL_IN:
            face = tuple(-value for value in radial_dir(mid))
        else:
            face = outward
        suffix = f"_{index:02d}" if len(arcs) > 1 else ""
        objects.append(
            grid_surface(f"{name}{suffix}", material, rows,
                         uv_rows=uv_rows, uv_cols=uv_cols, outward=face,
                         smooth_angle=smooth_angle)
        )
    return objects


def loft(name, material, sections, *, cap_start=True, cap_end=True,
         uv_tile=(1.5, 1.5), smooth_angle=38.0):
    """Closed-section loft through a list of equal-length point rings."""

    count = len(sections[0])
    verts: list[tuple[float, float, float]] = []
    for section in sections:
        verts.extend(section)
    faces: list[list[int]] = []
    uvs: list[list[tuple[float, float]]] = []
    stations = [0.0]
    for previous, current in zip(sections, sections[1:], strict=False):
        centre_a = [sum(axis) / count for axis in zip(*previous, strict=False)]
        centre_b = [sum(axis) / count for axis in zip(*current, strict=False)]
        stations.append(stations[-1] + math.dist(centre_a, centre_b))
    # Section perimeter in metres, so the u axis tiles at true scale.
    perimeter = [0.0]
    for k in range(count):
        perimeter.append(
            perimeter[-1]
            + math.dist(sections[0][k], sections[0][(k + 1) % count])
        )
    for i in range(len(sections) - 1):
        for j in range(count):
            k = (j + 1) % count
            faces.append([
                i * count + j, i * count + k,
                (i + 1) * count + k, (i + 1) * count + j,
            ])
            uvs.append([
                (perimeter[j] / uv_tile[0], stations[i] / uv_tile[1]),
                (perimeter[j + 1] / uv_tile[0], stations[i] / uv_tile[1]),
                (perimeter[j + 1] / uv_tile[0], stations[i + 1] / uv_tile[1]),
                (perimeter[j] / uv_tile[0], stations[i + 1] / uv_tile[1]),
            ])
    # Self-correcting winding: the side faces must face OUT of the section,
    # away from its own centreline. A loft built from a section that happens
    # to run clockwise renders inside out otherwise, and every section here
    # is generated (superellipse rings, circle rings) rather than authored,
    # so which way round it runs is not obvious at the call site.
    centre0 = Vector([sum(axis) / count for axis in zip(*sections[0], strict=False)])
    if _winding_is_wrong(sections[0][0], sections[0][1], sections[1][1],
                         Vector(sections[0][0]) - centre0):
        faces = [face[::-1] for face in faces]
        uvs = [face_uv[::-1] for face_uv in uvs]
    axis_dir = Vector([sum(axis) / count for axis in zip(*sections[-1], strict=False)]) - centre0
    if axis_dir.length < 1e-9:
        axis_dir = Vector((0.0, 0.0, 1.0))
    if cap_start:
        ring_start = list(range(count))
        # Flip on TRUE, exactly like cap_end below. _winding_is_wrong answers
        # "does this ring face AWAY from `outward`" - i.e. "does it need a
        # flip" - so `if not` reversed the start ring precisely when it was
        # ALREADY correct, and left it alone when it was not.
        #
        # The asymmetry that hid it: the two caps genuinely are not the same
        # statement. This one passes -axis_dir and indexes the ring from zero;
        # the other passes +axis_dir and offsets by `base`. Two differences
        # were already expected between the blocks, so a third one - the `not`
        # - read as part of the same mirror rather than as a defect, and both
        # forms looked plausible on the page. Only the render disagreed, and
        # only with backface culling on: Blender previews two-sided, so a
        # reversed cap looks identical to a correct one until it reaches
        # BeamNG's single-sided materials.
        #
        # Measured on the shipped mesh set: 757 single-sided objects carried a
        # reversed start cap before this line changed, 5 after - and those
        # five are not lofts at all. They are the lid_girder_* revolves, which
        # trip the audit's coplanar-pair heuristic by construction: on a
        # closed box-section ring the inner face at theta and the outer face
        # at theta+180 share a normal AND are separated along it. All 16
        # bar-graph segments and all 16 button sockets were among the 757,
        # which is why the LAUNCH POWER and LAUNCH ELEVATION rows rendered as
        # empty corner brackets with nothing lit inside them.
        if _winding_is_wrong(sections[0][0], sections[0][1],
                             sections[0][2], -axis_dir):
            ring_start = ring_start[::-1]
        faces.append(ring_start)
        uvs.append([(perimeter[j] / uv_tile[0], 0.0) for j in ring_start])
    if cap_end:
        base = (len(sections) - 1) * count
        ring_end = list(range(count))
        if _winding_is_wrong(sections[-1][0], sections[-1][1],
                             sections[-1][2], axis_dir):
            ring_end = ring_end[::-1]
        faces.append([base + j for j in ring_end])
        uvs.append([(perimeter[j] / uv_tile[0], stations[-1] / uv_tile[1])
                    for j in ring_end])
    return mesh_from(name, verts, faces, material, uvs, smooth_angle)


def superellipse(count, half_a, half_b, power=0.62):
    """Rounded-rectangle section: power below 1 squares the corners off."""

    points = []
    for k in range(count):
        angle = 2.0 * math.pi * k / count
        cosine, sine = math.cos(angle), math.sin(angle)
        points.append((
            half_a * math.copysign(abs(cosine) ** power, cosine),
            half_b * math.copysign(abs(sine) ** power, sine),
        ))
    return points


def oriented_cylinder(name, material, start, end, radius, *, vertices=32,
                      radius_end=None, uv_tile=(1.5, 1.5), cap=True):
    """Circular loft from ``start`` to ``end`` in any orientation."""

    axis = Vector(end) - Vector(start)
    length = axis.length
    if length < 1e-6:
        raise ValueError(f"degenerate cylinder: {name}")
    axis.normalize()
    reference = Vector((0.0, 0.0, 1.0))
    if abs(axis.dot(reference)) > 0.99:
        reference = Vector((1.0, 0.0, 0.0))
    side = axis.cross(reference).normalized()
    up = axis.cross(side).normalized()
    radius_end = radius if radius_end is None else radius_end
    sections = []
    for point, this_radius in ((start, radius), (end, radius_end)):
        origin = Vector(point)
        section = []
        for k in range(vertices):
            angle = 2.0 * math.pi * k / vertices
            offset = side * (math.cos(angle) * this_radius) + up * (
                math.sin(angle) * this_radius)
            section.append(tuple(origin + offset))
        sections.append(section)
    return loft(name, material, sections, cap_start=cap, cap_end=cap,
                uv_tile=uv_tile)


def panel_quad(name, material, centre, u_axis, v_axis, half_u, half_v,
               outward, *, uv_scale=(1.0, 1.0)):
    """Flat rectangle with PLANAR UVs, u along ``u_axis`` and v along ``v_axis``.

    Anything whose texture has to land in a specific PLACE - the console's
    engraved legend, the marquee, the builder's plate - needs this rather
    than ``oriented_box``. A box is a two-section loft, and a loft maps u
    around the section PERIMETER, so a legend applied to one lands as a
    smear of whichever strip of the image the perimeter happens to cross.

    ``u_axis`` is the direction the texture's +u points in world space. For
    a panel read from -Y that is +X: looking along forward f with up u, the
    viewer's right is f x u, and (0,1,0) x (0,0,1) = (1,0,0).
    """

    origin = Vector(centre)
    across = Vector(u_axis).normalized()
    up = Vector(v_axis).normalized()
    rows = [
        [tuple(origin + across * (su * half_u) + up * (sv * half_v))
         for su in (-1.0, 1.0)]
        for sv in (-1.0, 1.0)
    ]
    return grid_surface(name, material, rows, uv_rows=[0.0, uv_scale[1]],
                        uv_cols=[0.0, uv_scale[0]], outward=outward,
                        smooth_angle=20.0)


def dial_face(name, material, pivot, radius, *, rings=8, segments=64):
    """A gauge face in the X-Z plane with PLANAR POLAR UVs.

    Same problem as ``panel_quad`` solves, one step worse: a disc capped by
    ``loft`` inherits the loft's perimeter strip, so a dial texture mapped
    that way smears its print around the rim instead of laying it flat. The
    gauge print has to sit at specific ANGLES - it is the scale the needle
    reads against - so the face is meshed here with its own mapping, in the
    same screen frame ``spec._dial_scale`` lays the numbers out in.
    """

    cx, cy, cz = pivot
    verts: list[tuple[float, float, float]] = []
    vert_uv: list[tuple[float, float]] = []
    for ring_index in range(rings + 1):
        r = radius * (0.02 + 0.98 * ring_index / rings)
        for step in range(segments):
            angle = 2.0 * math.pi * step / segments
            x, z = math.cos(angle) * r, math.sin(angle) * r
            verts.append((cx + x, cy, cz + z))
            vert_uv.append((0.5 + x / (2.0 * radius), 0.5 + z / (2.0 * radius)))
    faces: list[list[int]] = []
    for ring_index in range(rings):
        base = ring_index * segments
        top = (ring_index + 1) * segments
        for step in range(segments):
            nxt = (step + 1) % segments
            faces.append([base + step, top + step, top + nxt, base + nxt])
    centre_index = len(verts)
    verts.append((cx, cy, cz))
    vert_uv.append((0.5, 0.5))
    for step in range(segments):
        faces.append([centre_index, (step + 1) % segments, step])
    if _winding_is_wrong(verts[faces[0][0]], verts[faces[0][1]],
                         verts[faces[0][2]], (0.0, -1.0, 0.0)):
        faces = [face[::-1] for face in faces]
    uvs = [[vert_uv[index] for index in face] for face in faces]
    return mesh_from(name, verts, faces, material, uvs, 20.0)


def oriented_box(name, material, centre, axis_u, axis_v, axis_w,
                 half_u, half_v, half_w, *, uv_tile=(1.5, 1.5)):
    """Axis-arbitrary box, built as a two-section loft of a rectangle."""

    centre = Vector(centre)
    axis_u = Vector(axis_u).normalized()
    axis_v = Vector(axis_v).normalized()
    axis_w = Vector(axis_w).normalized()
    sections = []
    for sign in (-1.0, 1.0):
        base = centre + axis_w * (sign * half_w)
        sections.append([
            tuple(base - axis_u * half_u - axis_v * half_v),
            tuple(base + axis_u * half_u - axis_v * half_v),
            tuple(base + axis_u * half_u + axis_v * half_v),
            tuple(base - axis_u * half_u + axis_v * half_v),
        ])
    return loft(name, material, sections, uv_tile=uv_tile, smooth_angle=20.0)


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


# ---------------------------------------------------------------------------
# The vacuum chamber.
# ---------------------------------------------------------------------------
def build_chamber(m) -> list:
    """Shell, bore liner, both lids, the observation ring and the hub boss."""

    made: list = []
    # Two arc lists, not one. The airlock opening is a rectangle, and a
    # rectangle subtends a different arc at the bore (r = 20.4) than at the
    # shell (r = 21.6) - see the derivation on TUNNEL_BORE_DEG in spec.py.
    #
    # And the SLOT is omitted from the shell ONLY. It used to be cut out of
    # the liner too, which took 22.79 m of arc by 8.40 m - 191 m^2 of the one
    # surface the payload looks at for the entire ride - and put nothing at
    # bore radius behind it; the only backstop was the shingle stack 1.3 m
    # further out, visible from inside purely because lid_plate is
    # double-sided. The tube pierces the liner obliquely (51.2 deg off radial,
    # crossing at station 12.78) and a 64 deg omission is neither necessary
    # nor sufficient as a pierce hole - it is 2.4 deg SHORT at tilt 72. The
    # shingle convention is the answer on both faces: model the surface closed
    # and let the barrel run through it. The cage keeps its slot omission, so
    # a launched car still leaves through a collision opening rather than into
    # an invisible wall.
    #
    # SLOT_DEG is now DERIVED from the tube's own swept silhouette (63.568 ->
    # 143.472, not the authored 70 -> 134), which is what stops the machined
    # jambs standing inside the barrel at the ends of the ladder - and, for
    # free, widens the CAGE's bore window through arcs_excluding in build_cage,
    # taking the worst collision-node clearance in the corridor from 2.068 m
    # (inside a 2.55 m bore, at tilt 72) to 3.395 m.
    shell_arcs = arcs_excluding(spec.SLOT_DEG, spec.TUNNEL_SHELL_DEG)
    bore_arcs = arcs_excluding(spec.TUNNEL_BORE_DEG)

    # Outer shell: a flat band interrupted by seven circumferential stiffener
    # flanges. Profiled rather than modelled as separate rings so the surface
    # stays one watertight strip with no coincident faces at the joins.
    shell: list[tuple[float, float]] = []
    flange_x = (-5.4, -3.6, -1.8, 0.0, 1.8, 3.6, 5.4)
    crown = spec.SHELL_R + spec.SHELL_FLANGE_PROUD
    for index, x in enumerate(flange_x):
        low = x - 0.16 if index else x
        high = x + 0.16 if index < len(flange_x) - 1 else x
        if index:
            shell.append((low, spec.SHELL_R))
            shell.append((low, crown))
        if index < len(flange_x) - 1:
            shell.append((high, crown))
            shell.append((high, spec.SHELL_R))
    made += revolve("chamber_shell", m[f"{MOD_ID}_shell_steel"], shell,
                    shell_arcs, uv_tile=(2.4, 2.4))

    # PAINT. Four hazard bands, one lip per hole in the vessel; see the
    # "aperture paint" block in spec.py for the placement argument. The
    # profile is the shell's own ribbon lifted by SHELL_PAINT_OFFSET, so a
    # band runs OVER the stiffener flanges the way a coat of paint does.
    painted = [(x, radius + spec.SHELL_PAINT_OFFSET) for x, radius in shell]
    mark_deg = math.degrees(spec.SHELL_MARK_M / spec.SHELL_R)
    # The slot lips, clear of the machined jamb - SLOT_JAMB_HALF_T = 0.60 m
    # of arc either side of the edge - and therefore also clear of the
    # shingle stack, whose leaves overrun the same edge by only
    # span * SLOT_LEAF_OVERLAP = 0.932 deg. theta 145.06 -> 146.92 on the
    # approach lip, 61.98 -> 60.12 on the far one.
    jamb_deg = math.degrees(spec.SLOT_JAMB_HALF_T / spec.SHELL_R)
    for tag, arc in (
        ("near", (spec.SLOT_DEG[1] + jamb_deg,
                  spec.SLOT_DEG[1] + jamb_deg + mark_deg)),
        ("far", (spec.SLOT_DEG[0] - jamb_deg - mark_deg,
                 spec.SLOT_DEG[0] - jamb_deg)),
    ):
        made += revolve(f"slot_lip_mark_{tag}", m[f"{MOD_ID}_hazard"], painted,
                        [arc], step_deg=0.5, uv_tile=(1.2, 1.2),
                        smooth_angle=20.0)
    # The airlock mouth: a head band above the soffit lip and a cheek band
    # down each side of the opening, meeting at the corners, so the three
    # read as one inverted U bounding exactly the hole a car drives into.
    made += revolve(
        "mouth_mark_head", m[f"{MOD_ID}_hazard"],
        _clip_profile(painted, -spec.MOUTH_MARK_HALF_X,
                      spec.MOUTH_MARK_HALF_X),
        [(spec.TUNNEL_SHELL_DEG[0] - mark_deg, spec.TUNNEL_SHELL_DEG[0])],
        step_deg=0.5, uv_tile=(1.2, 1.2), smooth_angle=20.0)
    for sign in (-1.0, 1.0):
        made += revolve(
            f"mouth_mark_{'p' if sign > 0 else 'n'}", m[f"{MOD_ID}_hazard"],
            _clip_profile(painted, sign * spec.TUNNEL_HALF_X,
                          sign * spec.MOUTH_MARK_HALF_X),
            [spec.TUNNEL_SHELL_DEG], step_deg=0.5, uv_tile=(1.2, 1.2),
            smooth_angle=20.0)

    # Bore liner: the surface a payload spends the entire ride looking at.
    made += revolve(
        "chamber_bore", m[f"{MOD_ID}_bore_liner"],
        [(spec.HALF_X, spec.CHAMBER_R), (-spec.HALF_X, spec.CHAMBER_R)],
        bore_arcs, outward=RADIAL_IN, uv_tile=(3.0, 3.0))

    made += build_tunnel_spandrels(m, shell)

    full = [(0.0, 360.0)]
    for sign, tag in ((1.0, "px"), (-1.0, "nx")):
        outer_x = sign * spec.OUTER_HALF_X
        inner_x = sign * spec.HALF_X
        # Lid exterior. On the -X side the observation ring replaces the band
        # between 13.2 and 18.4, so the plate is built in two pieces there.
        if sign > 0:
            bands = [(spec.HUB_HOUSING_R, spec.SHELL_R)]
        else:
            bands = [(spec.HUB_HOUSING_R, 13.2), (18.4, spec.SHELL_R)]
        for index, (r0, r1) in enumerate(bands):
            made += revolve(
                f"lid_out_{tag}_{index}", m[f"{MOD_ID}_lid_plate"],
                [(outer_x, r0), (outer_x, r1)], full,
                outward=(sign, 0.0, 0.0), uv_tile=(2.6, 2.6),
                smooth_angle=20.0)
            made += revolve(
                f"lid_in_{tag}_{index}", m[f"{MOD_ID}_bore_liner"],
                [(inner_x, r0), (inner_x, r1)], full,
                outward=(-sign, 0.0, 0.0), uv_tile=(2.6, 2.6),
                smooth_angle=20.0)
            # Edge return closing the 1.2 m plate thickness at each band end.
            for radius in (r0, r1):
                made += revolve(
                    f"lid_edge_{tag}_{index}_{radius:.0f}",
                    m[f"{MOD_ID}_rib_steel"],
                    [(outer_x, radius), (inner_x, radius)], full,
                    outward=RADIAL_OUT if radius == r1 else RADIAL_IN,
                    uv_tile=(1.2, 1.2), smooth_angle=20.0)

        # Radial stiffener ribs. This fan is the machine's most recognisable
        # feature from outside - a thin welded steel roof cannot span 21 m
        # without them, and the reference article wears 48.
        for index in range(48):
            theta = index * 360.0 / 48.0
            # Ends at LID_RIB_R1, not SHELL_R - 0.3: the collar's roller
            # trucks run at r 21.55 and the fan has to stay under them.
            spans = [(4.2, spec.LID_RIB_R1)] if sign > 0 else [
                (4.2, 13.0), (18.6, spec.LID_RIB_R1)]
            for span_index, (r0, r1) in enumerate(spans):
                mid = ring(theta, (r0 + r1) * 0.5, outer_x + sign * 0.36)
                made.append(oriented_box(
                    f"lid_rib_{tag}_{index:02d}_{span_index}",
                    m[f"{MOD_ID}_rib_steel"], mid,
                    radial_dir(theta), (1.0, 0.0, 0.0), tangent_dir(theta),
                    (r1 - r0) * 0.5, 0.36, 0.13, uv_tile=(1.4, 1.4)))
        # HUB DOUBLER, and this is the other half of the thumbnail crescent.
        #
        # The rib fan starts at r 4.2 and the hub flange stops at
        # HUB_HOUSING_R + 0.55 = 3.65, so a 0.55 m annulus of bare LID PLATE
        # was left ringing the bearing housing - and lid_plate is albedo 0.86,
        # the brightest material on the machine, against rib_steel's 0.44.
        # From an off-axis camera the boss stub, which stands 1.9 m proud,
        # covers that annulus on one side and reveals it on the other, and
        # what a 1.9 m cylinder standing on a bright ring produces is a
        # PARALLAX LUNE: a hard-edged bright crescent with a dark disc inside
        # it. Re-materialling the boss alone did not fix it, it only changed
        # which object was the bright half - measured on the ID pass, the
        # crescent's owner moved from hub_boss (144.5 luma, thirty counts over
        # its own flange) to lid_out (136.6 against a 92.3 flange).
        #
        # A doubler is also what the structure needs on its own terms: forty-
        # eight radial ribs cannot land on a plain lid skin at the hub, they
        # land on a thicker plate that spreads their pull into the bearing
        # housing. It runs from the housing to the fan's own start radius, so
        # there is no third number - if the fan ever moves, this follows.
        made += revolve(
            f"hub_doubler_{tag}", m[f"{MOD_ID}_rib_steel"],
            [(outer_x + sign * 0.02, spec.HUB_HOUSING_R),
             (outer_x + sign * 0.02, 4.2)], full,
            outward=(sign, 0.0, 0.0), uv_tile=(1.2, 1.2), smooth_angle=20.0)

        # Concentric ring girders tying the fan together.
        for radius in (8.4, 14.6, 20.2):
            if sign < 0 and 12.0 < radius < 19.0:
                continue
            made += revolve(
                f"lid_girder_{tag}_{radius:.0f}", m[f"{MOD_ID}_rib_steel"],
                [(outer_x + sign * 0.10, radius - 0.22),
                 (outer_x + sign * 0.50, radius - 0.22),
                 (outer_x + sign * 0.50, radius + 0.22),
                 (outer_x + sign * 0.10, radius + 0.22)],
                # RADIAL_IN, not OUT - the sentinel answers for the FIRST
                # opinionated strip, and this profile's first strip is the
                # girder's INNER cylinder at radius - 0.22, whose outside
                # faces the axis. Handedness is a property of the whole
                # ribbon (grid_surface says so), so binding the wrong strip
                # inverts all three: measured with RADIAL_OUT, the inner
                # cylinder pointed +radial, the axial web pointed -x*sign and
                # the outer cylinder pointed -radial - every face into the
                # steel, so all five rings were invisible on a single-sided
                # material. Same per-profile care as the lid plates two
                # blocks up and the observation frames below.
                full, outward=RADIAL_IN, uv_tile=(1.2, 1.2),
                smooth_angle=20.0)

    # Observation ring: the reason to stand next to this machine at all. A
    # 5.2 m glazed annulus centred exactly on the payload circle, so the car
    # is visible for the whole revolution rather than through portholes.
    glass_x = -spec.OUTER_HALF_X + 0.55
    made += revolve("obs_glass", m[f"{MOD_ID}_obs_glass"],
                    [(glass_x, 13.2), (glass_x, 18.4)], full,
                    outward=(-1.0, 0.0, 0.0), uv_tile=(3.0, 3.0),
                    smooth_angle=20.0)
    for radius in (13.2, 18.4):
        made += revolve(
            f"obs_frame_{radius:.0f}", m[f"{MOD_ID}_mullion"],
            [(-spec.HALF_X, radius), (-spec.OUTER_HALF_X - 0.18, radius)],
            full, outward=RADIAL_OUT if radius > 15.0 else RADIAL_IN,
            uv_tile=(1.0, 1.0), smooth_angle=20.0)
        made += revolve(
            f"obs_seal_{radius:.0f}", m[f"{MOD_ID}_seal_rubber"],
            [(-spec.OUTER_HALF_X - 0.18, radius - 0.20),
             (-spec.OUTER_HALF_X - 0.18, radius + 0.20)],
            full, outward=(-1.0, 0.0, 0.0), uv_tile=(0.6, 0.6),
            smooth_angle=20.0)
    for index in range(32):
        theta = index * 360.0 / 32.0
        mid = ring(theta, 15.8, glass_x - 0.16)
        made.append(oriented_box(
            f"obs_mullion_{index:02d}", m[f"{MOD_ID}_mullion"], mid,
            radial_dir(theta), (1.0, 0.0, 0.0), tangent_dir(theta),
            2.6, 0.22, 0.11, uv_tile=(0.8, 0.8)))

    # Hub bearing housing: one boss straight through both lids, which is what
    # actually carries the tether's radial load.
    #
    # rib_steel, NOT pipe_steel, AND THAT IS THE THUMBNAIL CRESCENT. The
    # reviewer's ship-blocker - "a bright hard-edged crescent on the hub disc
    # with no shading relationship to anything around it", around pixel
    # (215, 150) - is this cylinder. Identified by casting the thumbnail
    # camera's own ray for every pixel in that region and walking the hit
    # chain with backface culling applied, then confirmed with a false-colour
    # ID pass: the crescent is the 1.55 m of bare boss barrel left exposed
    # between the lid face at x = -OUTER_HALF_X and the flange's inboard face
    # at -(OUTER_HALF_X + 1.55), seen from an off-axis camera. It is NOT the
    # loft cap_start defect - that probe found ZERO culled-through faces
    # anywhere in the region.
    #
    # It was bright because of the MATERIAL. pipe_steel is albedo 0.62 at
    # metallic 0.92; the flange it butts against is rib_steel at 0.44 / 0.85.
    # Under the pack's flat-colour world a metal of that metallicity returns
    # albedo x world colour at EVERY normal - it has no shading gradient at
    # all, which is literally the "no shading relationship" the reviewer saw.
    # Measured on a 6x render with the object isolated by ID mask: the barrel
    # sat at luminance 144.5 against its own flange at 114.9 and the rib fan
    # at 113.2, while its normals receive at most N.L = 0.51 of the sun
    # against the flange face's 0.86. Forty percent less light, thirty counts
    # brighter. Re-materialled it measures 117.0 - within two counts of the
    # flange - and the crescent stops being a pasted-on shape.
    #
    # And rib_steel is the true statement anyway: the boss and its flange are
    # ONE bearing housing. pipe_steel is pipework - the status mast and the
    # baffle ties - and a housing is not pipework.
    made.append(oriented_cylinder(
        "hub_boss", m[f"{MOD_ID}_rib_steel"],
        (-spec.OUTER_HALF_X - 1.9, 0.0, spec.HUB_Z),
        (spec.OUTER_HALF_X + 1.9, 0.0, spec.HUB_Z),
        spec.HUB_HOUSING_R, vertices=48, uv_tile=(2.0, 2.0)))
    for sign in (-1.0, 1.0):
        made.append(oriented_cylinder(
            f"hub_flange_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_rib_steel"],
            (sign * (spec.OUTER_HALF_X + 1.55), 0.0, spec.HUB_Z),
            (sign * (spec.OUTER_HALF_X + 1.95), 0.0, spec.HUB_Z),
            spec.HUB_HOUSING_R + 0.55, vertices=48, uv_tile=(1.2, 1.2)))
        for index in range(16):
            angle = index * 360.0 / 16.0
            bolt = ring(angle, spec.HUB_HOUSING_R + 0.30,
                        sign * (spec.OUTER_HALF_X + 1.95))
            made.append(oriented_cylinder(
                f"hub_bolt_{'p' if sign > 0 else 'n'}_{index:02d}",
                m[f"{MOD_ID}_tube_band"], bolt,
                (bolt[0] + sign * 0.12, bolt[1], bolt[2]), 0.09,
                vertices=10, uv_tile=(0.4, 0.4)))
    return made


def _clip_profile(profile, x0, x1):
    """The part of an (x, radius) polyline between two x stations.

    The shell is a stepped ribbon - flat band, stiffener flange, flat band -
    and the tunnel plugs only the middle of it, so the spandrel that closes
    the rest has to be that SAME ribbon clipped. A plain cylinder would work
    right up until someone stood at the portal and watched six stiffener
    flanges stop dead in mid-air. x is monotonic by construction; the radius
    at a cut station is interpolated, and a cut that lands exactly on an
    existing station is kept rather than duplicated (the outermost flange
    face is a vertical step at x = +/-5.24 and a naive clip eats it).
    """

    def radius_at(x):
        for (xa, ra), (xb, rb) in zip(profile, profile[1:], strict=False):
            if xa <= x <= xb:
                return rb if xb == xa else ra + (rb - ra) * (x - xa) / (xb - xa)
        return profile[0][1] if x < profile[0][0] else profile[-1][1]

    lo = max(min(x0, x1), profile[0][0])
    hi = min(max(x0, x1), profile[-1][0])
    clipped = []
    if not any(abs(x - lo) < 1e-9 for x, _ in profile):
        clipped.append((lo, radius_at(lo)))
    clipped += [(x, r) for x, r in profile if lo - 1e-9 <= x <= hi + 1e-9]
    if not any(abs(x - hi) < 1e-9 for x, _ in profile):
        clipped.append((hi, radius_at(hi)))
    return clipped


def build_tunnel_spandrels(m, shell_profile) -> list:
    """Close the envelope either side of the airlock, where the plug is not.

    An omitted arc removes the FULL profile width. The thing that plugs this
    one - the tunnel - is a rectangular box only TUNNEL_HALF_X (3.4 m) half
    wide, while the omission runs to HALF_X (4.2 m) on the bore and to the
    shell ribbon's own 5.24 m outboard. That left a 0.80 m strip open on
    EACH flank of BOTH surfaces: 11.97 m^2 of bore and 11.39 m^2 of shell,
    straight through the wall, at eye level, in the shot the player is
    staring at while the machine says AIRLOCK SEALED.

    The tunnel's y_far / y_near overrun does not help and never could: it is
    an overrun in Y, and the arc escapes the rectangle in X and in Z. Z is
    now handled by deriving each arc from its own radius (spec.py); X is
    handled here, by revolving the same profiles across the residual strips.
    Revolve, not boolean - see the bevel-after-boolean tombstone in
    blender_kit.cut_openings.

    The strips terminate ON the tunnel wall plane at |x| = TUNNEL_HALF_X and
    on the lid interior at |x| = HALF_X, and their arcs are exactly the
    omitted arcs, so above and below them the parent surface simply
    continues. Nothing here is authored: change TUNNEL_HALF_X or DECK_Z and
    the spandrels re-solve.
    """

    made: list = []
    for sign in (-1.0, 1.0):
        tag = "p" if sign > 0 else "n"
        made += revolve(
            f"tunnel_spandrel_bore_{tag}", m[f"{MOD_ID}_bore_liner"],
            [(sign * spec.TUNNEL_HALF_X, spec.CHAMBER_R),
             (sign * spec.HALF_X, spec.CHAMBER_R)],
            [spec.TUNNEL_BORE_DEG], outward=RADIAL_IN, uv_tile=(3.0, 3.0))
        made += revolve(
            f"tunnel_spandrel_shell_{tag}", m[f"{MOD_ID}_shell_steel"],
            _clip_profile(shell_profile, sign * spec.TUNNEL_HALF_X,
                          sign * shell_profile[-1][0]),
            [spec.TUNNEL_SHELL_DEG], uv_tile=(2.4, 2.4))
    return made


def build_slot(m) -> list:
    """The arc slot the launch tube's collar travels in.

    A travelling tube needs a travelling seal, and the real answer on a
    machine this size is a shingled arc: overlapping curved leaves that the
    collar's apron rides over. Modelling them CLOSED and letting the apron
    sit proud gets the look with no animation and no moving seal to bake
    collision for.
    """

    made: list = []
    start, end = spec.SLOT_DEG
    # Machined jambs down both edges of the opening. Straight boxes rather
    # than revolves: over 3.2 degrees the chord error is under 4 mm, and a
    # box has an unambiguous outside.
    for theta in (start, end):
        made.append(oriented_box(
            f"slot_jamb_{theta:.0f}", m[f"{MOD_ID}_tube_band"],
            ring(theta, spec.SLOT_JAMB_R),
            (1.0, 0.0, 0.0), tangent_dir(theta), radial_dir(theta),
            spec.OUTER_HALF_X + 0.35, spec.SLOT_JAMB_HALF_T,
            spec.SLOT_JAMB_HALF_R, uv_tile=(1.0, 1.0)))
    # Guide rails the collar's rollers run on, one per side.
    for sign in (-1.0, 1.0):
        rail_x = sign * spec.SLOT_RAIL_X
        made += revolve(
            f"slot_rail_{'p' if sign > 0 else 'n'}", m[f"{MOD_ID}_tube_band"],
            [(rail_x - 0.16, spec.SLOT_RAIL_R0),
             (rail_x + 0.16, spec.SLOT_RAIL_R0),
             (rail_x + 0.16, spec.SLOT_RAIL_R1),
             (rail_x - 0.16, spec.SLOT_RAIL_R1)],
            [(start - 3.0, end + 3.0)], uv_tile=(0.9, 0.9), smooth_angle=20.0)
    # Shingle leaves, each overlapping its neighbour by a third. The counts,
    # the lap and the radius ladder live in spec.py so the envelope gate can
    # PROVE the union covers SLOT_DEG rather than take this comment's word
    # for it - and so APRON_R can be derived from the TALLEST leaf.
    leaves = spec.SLOT_LEAVES
    lap = spec.SLOT_LEAF_OVERLAP
    span = (end - start) / leaves
    for index in range(leaves):
        theta0 = start + span * index
        leaf_r = spec.SLOT_LEAF_R0 + spec.SLOT_LEAF_STEP * index
        leaf_arc = (theta0 - span * lap, theta0 + span * (1.0 + lap))
        made += revolve(
            f"slot_shingle_{index:02d}", m[f"{MOD_ID}_lid_plate"],
            [(-spec.SLOT_LEAF_HALF_X, leaf_r),
             (spec.SLOT_LEAF_HALF_X, leaf_r)],
            [leaf_arc], step_deg=1.0, uv_tile=(1.4, 1.4), smooth_angle=20.0)
        # Cheeks. The stack stands 0.10 to 0.448 m proud of the shell, but the
        # lid plates it sits over stop dead at r = SHELL_R - so from either
        # flank you could see straight down the length of it: a 0.448 m by
        # 24.38 m annulus per side, 21.84 m^2 of open rim. The jambs close the
        # two ENDS of the arc; these close the two SIDES. Built per leaf so
        # they step out WITH the stack rather than standing 0.348 m proud of
        # leaf 0 as a single fin would.
        for sign in (-1.0, 1.0):
            made += revolve(
                f"slot_cheek_{index:02d}_{'p' if sign > 0 else 'n'}",
                m[f"{MOD_ID}_lid_plate"],
                [(sign * spec.SLOT_LEAF_HALF_X, spec.SHELL_R),
                 (sign * spec.SLOT_LEAF_HALF_X, leaf_r)],
                [leaf_arc], step_deg=1.0, outward=(sign, 0.0, 0.0),
                uv_tile=(1.4, 1.4), smooth_angle=20.0)

    # The slot's own lip PAINT lives in build_chamber, with the shell ribbon
    # it follows.
    return made


def build_tunnel(m) -> list:
    """Airlock tunnel, portal frame and the blast-door hood."""

    made: list = []
    half_x = spec.TUNNEL_HALF_X
    top_z = spec.TUNNEL_TOP_Z
    # Walls and soffit run past the tunnel proper in Y so the omitted arcs
    # never terminate on an open edge; the FLOOR stops at TUNNEL_Y_IN, where
    # the retracting deck begins. Y is ALL this overrun buys: the arc used to
    # escape this rectangle in X and in Z as well, and the comment that once
    # stood here claimed otherwise. Z is closed by deriving each arc from its
    # own radius (TUNNEL_BORE_DEG / TUNNEL_SHELL_DEG), X by
    # build_tunnel_spandrels. Margins on the Y overrun as authored: 0.870 m
    # at the far end, 0.796 m at the near end - both gated.
    y_far, y_near = spec.TUNNEL_Y_FAR, spec.TUNNEL_Y_NEAR
    floor_near = spec.TUNNEL_Y_IN

    # Side walls and soffit. The tunnel deliberately over-runs the shell in
    # both directions so the omitted shell arc never shows an open edge.
    for sign in (-1.0, 1.0):
        wall_x = sign * half_x
        made.append(grid_surface(
            f"tunnel_wall_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_bore_liner"],
            [[(wall_x, y, spec.DECK_Z) for y in
              (y_far, -16.0, -13.0, y_near)],
             [(wall_x, y, top_z) for y in (y_far, -16.0, -13.0, y_near)]],
            uv_rows=[0.0, spec.TUNNEL_CLEAR_Z / 2.5],
            uv_cols=[0.0, 1.36, 2.56, 3.28],
            outward=(-sign, 0.0, 0.0)))
        made.append(oriented_box(
            f"tunnel_kerb_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_hazard"],
            (sign * (half_x - 0.18), (y_far + y_near) * 0.5, spec.DECK_Z + 0.22),
            (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
            (y_near - y_far) * 0.5, 0.18, 0.22, uv_tile=(1.2, 0.5)))
    made.append(grid_surface(
        "tunnel_soffit", m[f"{MOD_ID}_bore_liner"],
        [[(-half_x, y, top_z) for y in (y_far, -16.0, -13.0, y_near)],
         [(half_x, y, top_z) for y in (y_far, -16.0, -13.0, y_near)]],
        uv_rows=[0.0, 2.72], uv_cols=[0.0, 1.36, 2.56, 3.28],
        outward=(0.0, 0.0, -1.0)))
    floor_stations = (y_far, -16.6, -13.8, floor_near)
    made.append(grid_surface(
        "tunnel_floor", m[f"{MOD_ID}_deck_plate"],
        [[(-half_x, y, spec.DECK_Z) for y in floor_stations],
         [(half_x, y, spec.DECK_Z) for y in floor_stations]],
        uv_rows=[0.0, 2.72],
        uv_cols=[(y - y_far) / 2.5 for y in floor_stations],
        outward=(0.0, 0.0, 1.0)))
    # Tunnel lighting strips.
    for index, y in enumerate((-18.0, -15.4, -12.8)):
        made.append(oriented_box(
            f"tunnel_lamp_{index}", m[f"{MOD_ID}_lamp_lens"],
            (0.0, y, top_z - 0.12), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0), 2.4, 0.22, 0.10, uv_tile=(0.6, 0.6)))

    # Portal frame at the outer face, and the hood the door parks in.
    frame_y = spec.TUNNEL_Y_OUT - 0.35
    for sign in (-1.0, 1.0):
        made.append(oriented_box(
            f"portal_jamb_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_tube_band"],
            (sign * (half_x + 0.55), frame_y, (spec.DECK_Z + top_z) * 0.5),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
            0.55, 0.55, (top_z - spec.DECK_Z) * 0.5 + 0.6, uv_tile=(1.0, 1.0)))
        # HAZARD, THE FULL WIDTH OF THE JAMB. This was a 0.52 m strip on a
        # 1.10 m jamb face; the band is now sized off the jamb it sits on
        # rather than authored, so the two cannot drift apart.
        #
        # It is NOT the approach-face marking, and the strip that used to be
        # here was not either - the shell arches 4.6 m out over this frame,
        # so from the ramp everything on the jamb above z = 6.84 is occluded
        # by the vessel itself (the derivation is on MOUTH_MARK_HALF_X). What
        # a driver sees framing the hole is the shell, and build_chamber
        # paints that. This is what you see once you are AT the mouth, which
        # is exactly what a vehicle airlock's jamb marking is for.
        made.append(oriented_box(
            f"portal_chevron_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_hazard"],
            (sign * (half_x + 0.55), frame_y - 0.59,
             (spec.DECK_Z + top_z) * 0.5),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
            0.55, 0.04, (top_z - spec.DECK_Z) * 0.5, uv_tile=(1.2, 1.2)))
    made.append(oriented_box(
        "portal_lintel", m[f"{MOD_ID}_tube_band"],
        (0.0, frame_y, top_z + 0.55), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0), half_x + 1.1, 0.55, 0.55, uv_tile=(1.0, 1.0)))
    made.append(oriented_box(
        "door_hood", m[f"{MOD_ID}_lid_plate"],
        (0.0, frame_y - 0.15, top_z + spec.DOOR_TRAVEL * 0.5 + 0.9),
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        half_x + 1.0, 0.85, spec.DOOR_TRAVEL * 0.5 + 0.4, uv_tile=(1.8, 1.8)))
    for sign in (-1.0, 1.0):
        made.append(oriented_cylinder(
            f"door_ram_{'p' if sign > 0 else 'n'}", m[f"{MOD_ID}_pipe_steel"],
            (sign * (half_x + 0.55), frame_y + 0.1, top_z + 0.9),
            (sign * (half_x + 0.55), frame_y + 0.1,
             top_z + spec.DOOR_TRAVEL + 1.4),
            0.24, vertices=16, uv_tile=(0.8, 0.8)))
    return made


# ---------------------------------------------------------------------------
# Civil works: plinth, ramp, apron, console bay, plaza and plant.
# ---------------------------------------------------------------------------
def ramp_z(y: float) -> float:
    """Approach deck height. Flat on the apron, constant grade below it."""

    if y >= spec.APRON_Y0:
        return spec.DECK_Z
    if y <= spec.RAMP_Y0:
        return spec.GROUND_Z
    span = spec.APRON_Y0 - spec.RAMP_Y0
    return spec.GROUND_Z + (spec.DECK_Z - spec.GROUND_Z) * (y - spec.RAMP_Y0) / span


def bay_gap(y: float) -> bool:
    """Is this station inside the console bay's opening in the +X ramp edge?"""

    return abs(y - spec.BAY_Y) < 3.9


def build_civil(m) -> list:
    made: list = []

    # Plinth: the saddle the disc sits in. Its top is a walkable apron and
    # its flanks are battered, so the buried third of the chamber never
    # shows an edge against the terrain.
    plinth_y = (-16.5, 16.5)
    made.append(grid_surface(
        "plinth_top", m[f"{MOD_ID}_concrete"],
        [[(x, y, spec.PLINTH_TOP) for y in
          (plinth_y[0], plinth_y[0] + 6.0, 0.0, plinth_y[1] - 6.0, plinth_y[1])]
         for x in (-13.5, -9.0, 9.0, 13.5)],
        uv_rows=[0.0, 1.8, 9.0, 10.8], uv_cols=[0.0, 2.4, 5.0, 7.6, 10.0],
        outward=(0.0, 0.0, 1.0)))
    for sign in (-1.0, 1.0):
        made.append(grid_surface(
            f"plinth_flank_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_concrete"],
            [[(sign * 13.5, y, spec.PLINTH_TOP) for y in
              (plinth_y[0], 0.0, plinth_y[1])],
             [(sign * 15.6, y, spec.PLINTH_BOTTOM) for y in
              (plinth_y[0] - 1.4, 0.0, plinth_y[1] + 1.4)]],
            uv_rows=[0.0, 2.4], uv_cols=[0.0, 6.6, 13.2],
            outward=(sign, 0.0, 0.0)))
    for sign, y_edge in ((-1.0, plinth_y[0]), (1.0, plinth_y[1])):
        made.append(grid_surface(
            f"plinth_end_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_concrete"],
            [[(x, y_edge, spec.PLINTH_TOP) for x in (-13.5, 0.0, 13.5)],
             [(x, y_edge + sign * 1.4, spec.PLINTH_BOTTOM)
              for x in (-15.6, 0.0, 15.6)]],
            uv_rows=[0.0, 2.4], uv_cols=[0.0, 5.4, 10.8],
            outward=(0.0, sign, 0.0)))

    # Approach ramp and apron, one continuous surface so there is no seam to
    # catch a wheel at the grade break.
    # The visual deck stops where the tunnel's steel floor takes over, edge
    # to edge - the two surfaces used to overlap by 5 m of coplanar z = 3.0.
    # 24 spans, not 12: the ramp run doubled with the re-datum (24 -> 48 m)
    # and this list also sets the guard-rail post pitch (every other
    # station), so keeping the count would have thinned the posts from one
    # every 4 m to one every 8 m. 48 / 24 = 2.0 m, exactly as authored.
    stations = [spec.RAMP_Y0 + (spec.APRON_Y0 - spec.RAMP_Y0) * k / 24.0
                for k in range(25)]
    stations += [-26.4, -24.6, -22.8, -21.0, -19.4]
    lanes = (-spec.RAMP_HALF_W, -2.2, 0.0, 2.2, spec.RAMP_HALF_W)
    made.append(grid_surface(
        "ramp_deck", m[f"{MOD_ID}_ramp_deck"],
        [[(x, y, ramp_z(y)) for y in stations] for x in lanes],
        uv_rows=[(x + spec.RAMP_HALF_W) / 4.0 for x in lanes],
        uv_cols=[(y - spec.RAMP_Y0) / 4.0 for y in stations],
        outward=(0.0, 0.0, 1.0)))
    made.append(grid_surface(
        "ramp_soffit", m[f"{MOD_ID}_concrete"],
        [[(x, y, ramp_z(y) - 1.1) for y in stations]
         for x in (-spec.RAMP_HALF_W, 0.0, spec.RAMP_HALF_W)],
        uv_rows=[0.0, 2.2, 4.4],
        uv_cols=[(y - spec.RAMP_Y0) / 4.0 for y in stations],
        outward=(0.0, 0.0, -1.0)))
    for sign in (-1.0, 1.0):
        made.append(grid_surface(
            f"ramp_fascia_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_concrete"],
            [[(sign * spec.RAMP_HALF_W, y, ramp_z(y)) for y in stations],
             [(sign * spec.RAMP_HALF_W, y, ramp_z(y) - 1.1) for y in stations]],
            uv_rows=[0.0, 0.55],
            uv_cols=[(y - spec.RAMP_Y0) / 4.0 for y in stations],
            outward=(sign, 0.0, 0.0)))
        # Kerb plus a run of guard rail with posts. Both are broken over the
        # bay on the +X side; a 0.3 m kerb across a pull-in is a jump.
        kerb_runs = [stations]
        if sign > 0:
            kerb_runs = [
                run for run in (
                    [y for y in stations if not bay_gap(y) and y < spec.BAY_Y],
                    [y for y in stations if not bay_gap(y) and y > spec.BAY_Y],
                ) if len(run) > 1
            ]
        for kerb_index, run in enumerate(kerb_runs):
            made.append(grid_surface(
                f"ramp_kerb_{'p' if sign > 0 else 'n'}_{kerb_index}",
                m[f"{MOD_ID}_hazard"],
                [[(sign * (spec.RAMP_HALF_W - 0.35), y, ramp_z(y) + 0.30)
                  for y in run],
                 [(sign * spec.RAMP_HALF_W, y, ramp_z(y) + 0.30) for y in run],
                 [(sign * spec.RAMP_HALF_W, y, ramp_z(y)) for y in run]],
                uv_rows=[0.0, 0.35, 0.65],
                uv_cols=[(y - spec.RAMP_Y0) / 2.0 for y in run],
                outward=(-sign, 0.0, 1.0)))
        for index in range(0, len(stations) - 1, 2):
            y = stations[index]
            if sign > 0 and bay_gap(y):
                continue
            base = ramp_z(y)
            made.append(oriented_cylinder(
                f"rail_post_{'p' if sign > 0 else 'n'}_{index:02d}",
                m[f"{MOD_ID}_rail_steel"],
                (sign * (spec.RAMP_HALF_W - 0.18), y, base + 0.25),
                (sign * (spec.RAMP_HALF_W - 0.18), y, base + 1.25),
                0.075, vertices=10, uv_tile=(0.5, 0.5)))
        # The right-hand rail is broken over the console bay. Without the
        # gap the panel is behind a guard rail: reachable on foot, not from
        # the driver's seat, which is the whole point of putting the bay
        # beside the ramp in the first place.
        runs = [stations]
        if sign > 0:
            before = [y for y in stations if not bay_gap(y) and y < spec.BAY_Y]
            after = [y for y in stations if not bay_gap(y) and y > spec.BAY_Y]
            runs = [run for run in (before, after) if len(run) > 1]
        for run_index, run in enumerate(runs):
            for height in (0.72, 1.18):
                made.append(grid_surface(
                    f"rail_run_{'p' if sign > 0 else 'n'}_{run_index}_{height:.2f}",
                    m[f"{MOD_ID}_rail_steel"],
                    [[(sign * (spec.RAMP_HALF_W - 0.18), y, ramp_z(y) + height)
                      for y in run],
                     [(sign * (spec.RAMP_HALF_W - 0.18), y,
                       ramp_z(y) + height - 0.13) for y in run]],
                    uv_rows=[0.0, 0.13],
                    uv_cols=[(y - spec.RAMP_Y0) / 1.2 for y in run],
                    outward=(-sign, 0.0, 0.0)))
        # End posts flanking the gap, so it reads as an opening and not as
        # missing rail.
        if sign > 0:
            for y in (spec.BAY_Y - 3.9, spec.BAY_Y + 3.9):
                made.append(oriented_cylinder(
                    f"rail_endpost_{y:.0f}", m[f"{MOD_ID}_rail_steel"],
                    (spec.RAMP_HALF_W - 0.18, y, ramp_z(y) + 0.25),
                    (spec.RAMP_HALF_W - 0.18, y, ramp_z(y) + 1.35),
                    0.11, vertices=12, uv_tile=(0.5, 0.5)))

    # Console bay: a level pull-in on the right of the ramp so the panel is
    # reachable from the driver's seat rather than from a walk.
    bay_rows = [[(x, y, spec.BAY_Z) for y in (spec.BAY_Y - 3.4, spec.BAY_Y,
                                              spec.BAY_Y + 3.4)]
                for x in (spec.RAMP_HALF_W, 7.0, 11.4)]
    made.append(grid_surface("bay_deck", m[f"{MOD_ID}_asphalt"], bay_rows,
                             uv_rows=[0.0, 0.63, 1.73],
                             uv_cols=[0.0, 0.85, 1.70],
                             outward=(0.0, 0.0, 1.0)))
    made.append(grid_surface(
        "bay_fascia", m[f"{MOD_ID}_concrete"],
        [[(x, spec.BAY_Y - 3.4, spec.BAY_Z) for x in
          (spec.RAMP_HALF_W, 11.4)],
         [(x, spec.BAY_Y - 3.4, spec.BAY_BOTTOM_Z) for x in
          (spec.RAMP_HALF_W, 11.4)]],
        uv_rows=[0.0, 1.45], uv_cols=[0.0, 1.73],
        outward=(0.0, -1.0, 0.0)))
    made.append(grid_surface(
        "bay_side", m[f"{MOD_ID}_concrete"],
        [[(11.4, y, spec.BAY_Z) for y in (spec.BAY_Y - 3.4, spec.BAY_Y + 3.4)],
         [(11.4, y, spec.BAY_BOTTOM_Z) for y in
          (spec.BAY_Y - 3.4, spec.BAY_Y + 3.4)]],
        uv_rows=[0.0, 1.45], uv_cols=[0.0, 1.70],
        outward=(1.0, 0.0, 0.0)))

    # Ground plaza, so the machine is not standing on bare terrain.
    made.append(grid_surface(
        "plaza", m[f"{MOD_ID}_asphalt"],
        # The outer edge is RAMP_Y0 - 4.0, the same 4 m of apron beyond the
        # ramp foot the plaza always had (-56.0 back when the foot was at
        # -52.0). Derived, or a longer ramp runs off the end of the asphalt
        # onto bare terrain. uv_cols are metres / 4.0 m tile: spans of
        # 24, 38 and 38 give 6.0, 15.5, 25.0.
        [[(x, y, spec.GROUND_Z - 0.02)
          for y in (spec.RAMP_Y0 - 4.0, -56.0, -18.0, 20.0)]
         for x in (-26.0, -8.0, 8.0, 26.0)],
        uv_rows=[0.0, 4.5, 8.5, 13.0], uv_cols=[0.0, 6.0, 15.5, 25.0],
        outward=(0.0, 0.0, 1.0)))
    return made


def build_plant(m) -> list:
    """Vacuum pump skids, pipework, masts, the service block and the plate.

    The MARQUEE used to live here too, on the plinth's end face. It is now
    build_facade's, on the shell - see the derivation on SIGN_FACE_Y.
    """

    made: list = []
    for index, (x, y) in enumerate(spec.PUMP_POSITIONS):
        base_z = spec.PLINTH_TOP
        made.append(oriented_box(
            f"pump_skid_{index}", m[f"{MOD_ID}_pump_paint"],
            (x, y, base_z + 0.9), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0), 1.7, 2.4, 0.9, uv_tile=(1.6, 1.6)))
        made.append(oriented_cylinder(
            f"pump_body_{index}", m[f"{MOD_ID}_pump_paint"],
            (x, y - 1.9, base_z + 2.3), (x, y + 1.9, base_z + 2.3),
            1.25, vertices=28, uv_tile=(1.4, 1.4)))
        made.append(oriented_cylinder(
            f"pump_motor_{index}", m[f"{MOD_ID}_pipe_steel"],
            (x, y + 1.9, base_z + 2.3), (x, y + 3.3, base_z + 2.3),
            0.78, vertices=20, uv_tile=(1.0, 1.0)))
        # Suction line climbing to a flange on the shell.
        top = ring(250.0 if x < 0 else 290.0, spec.SHELL_R + 0.35,
                   max(-4.6, min(4.6, x * 0.3)))
        made.append(oriented_cylinder(
            f"pump_riser_{index}", m[f"{MOD_ID}_pipe_steel"],
            (x, y, base_z + 3.4), (x * 0.55, y * 0.7, base_z + 7.6),
            0.42, vertices=18, uv_tile=(1.2, 1.2)))
        made.append(oriented_cylinder(
            f"pump_link_{index}", m[f"{MOD_ID}_pipe_steel"],
            (x * 0.55, y * 0.7, base_z + 7.6), top, 0.42, vertices=18,
            uv_tile=(1.2, 1.2)))
        made.append(oriented_cylinder(
            f"pump_valve_{index}", m[f"{MOD_ID}_copper_bus"],
            (x * 0.78, y * 0.85, base_z + 5.5),
            (x * 0.78, y * 0.85, base_z + 6.1), 0.60, vertices=16,
            uv_tile=(0.8, 0.8)))

    for index, (x, y) in enumerate(spec.MAST_POSITIONS):
        made.append(oriented_cylinder(
            f"mast_{index}", m[f"{MOD_ID}_pipe_steel"],
            (x, y, spec.GROUND_Z), (x, y, spec.MAST_HEIGHT), 0.30,
            radius_end=0.20, vertices=14, uv_tile=(1.2, 1.2)))
        for lamp in range(3):
            offset = (lamp - 1) * 0.85
            made.append(oriented_box(
                f"mast_head_{index}_{lamp}", m[f"{MOD_ID}_lamp_lens"],
                (x + offset, y - 0.55, spec.MAST_HEIGHT + 0.15),
                (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
                0.34, 0.20, 0.26, uv_tile=(0.5, 0.5)))
        made.append(oriented_box(
            f"mast_gantry_{index}", m[f"{MOD_ID}_rib_steel"],
            (x, y - 0.3, spec.MAST_HEIGHT + 0.5), (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 1.5, 0.45, 0.20,
            uv_tile=(0.9, 0.9)))

    bx, by = spec.BUILDING_CENTER
    sx, sy, sz = spec.BUILDING_SIZE
    made.append(oriented_box(
        "service_block", m[f"{MOD_ID}_building_wall"],
        (bx, by, spec.GROUND_Z + sz * 0.5), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0), sx * 0.5, sy * 0.5, sz * 0.5, uv_tile=(2.2, 2.2)))
    made.append(oriented_box(
        "service_roof", m[f"{MOD_ID}_building_roof"],
        (bx, by, spec.GROUND_Z + sz + 0.20), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0), sx * 0.5 + 0.35, sy * 0.5 + 0.35, 0.22,
        uv_tile=(2.2, 2.2)))
    for index in range(4):
        made.append(oriented_box(
            f"service_hvac_{index}", m[f"{MOD_ID}_building_roof"],
            (bx - 2.6 + index * 1.8, by + 4.0 - index * 2.4,
             spec.GROUND_Z + sz + 0.90), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0), 0.85, 0.85, 0.55, uv_tile=(0.9, 0.9)))
    for index in range(6):
        made.append(panel_quad(
            f"service_window_{index}", m[f"{MOD_ID}_obs_glass"],
            (bx - sx * 0.5 - 0.05, by - 7.0 + index * 2.8,
             spec.GROUND_Z + 3.6), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
            1.0, 0.85, (-1.0, 0.0, 0.0)))
    made.append(oriented_box(
        "service_door", m[f"{MOD_ID}_mullion"],
        (bx - sx * 0.5 - 0.05, by - 9.4, spec.GROUND_Z + 1.35),
        (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), 0.75, 1.35, 0.07,
        uv_tile=(1.0, 1.0)))

    # Machined builder's plate, beside the portal at reading distance. This is
    # where the machine's DESIGNATION lives - PLATE_TEXT, "A-1" - so the shell
    # board carries the operator's name and nothing else.
    made.append(panel_quad(
        "builder_plate", m[f"{MOD_ID}_builder_plate"],
        (4.2, spec.TUNNEL_Y_OUT - 0.76, spec.DECK_Z + 2.2),
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), 0.62, 0.62, (0.0, -1.0, 0.0)))
    return made


# ---------------------------------------------------------------------------
# Console.
# ---------------------------------------------------------------------------
def build_console(m) -> list:
    made: list = []
    front = spec.CONSOLE_FACE_Y
    back = front + spec.CONSOLE_DEPTH
    mid_y = (front + back) * 0.5
    made.append(oriented_box(
        "console_case", m[f"{MOD_ID}_console_case"],
        (spec.CONSOLE_X, mid_y, (spec.BAY_Z + spec.CONSOLE_TOP_Z) * 0.5),
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        spec.CONSOLE_HALF_X, spec.CONSOLE_DEPTH * 0.5,
        (spec.CONSOLE_TOP_Z - spec.BAY_Z) * 0.5, uv_tile=(1.4, 1.4)))
    made.append(oriented_box(
        "console_plinth", m[f"{MOD_ID}_concrete"],
        (spec.CONSOLE_X, mid_y, spec.BAY_Z + 0.09), (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), spec.CONSOLE_HALF_X + 0.25,
        spec.CONSOLE_DEPTH * 0.5 + 0.25, 0.09, uv_tile=(1.0, 1.0)))
    # Engraved legend plate. It is the SAME plate frame the label UVs were
    # solved in (spec._u / _v), so the print lands on the caps it names.
    made.append(panel_quad(
        "console_legend", m[f"{MOD_ID}_panel_legend"],
        (spec.CONSOLE_X, front - 0.03,
         spec._PLATE_Z0 + spec._PLATE_H * 0.5),
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
        spec._PLATE_W * 0.5, spec._PLATE_H * 0.5, (0.0, -1.0, 0.0)))
    # BEHIND the legend, not straddling it: this used to be centred 1.5 cm
    # in front of the plate with a 2.5 cm half-depth, so a near-black
    # bakelite box enclosed the print and the panel rendered blank.
    made.append(oriented_box(
        "console_bezel", m[f"{MOD_ID}_panel_dark"],
        (spec.CONSOLE_X, front + 0.03,
         spec._PLATE_Z0 + spec._PLATE_H * 0.5),
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0),
        spec._PLATE_W * 0.5 + 0.09, spec._PLATE_H * 0.5 + 0.09, 0.025,
        uv_tile=(1.0, 1.0)))

    # Caps. Cap geometry is authored from the SAME table the cage anchors and
    # the triggers2 click boxes come from - one source, or the hitboxes drift
    # off the paint (the car-wash calibration lesson).
    for button in spec.PANEL_BUTTONS:
        x, y, z = button["position"]
        cap = button.get("cap", "round_white")
        radius = spec.CAP_RADII[cap]
        colour = {
            "round_green": f"{MOD_ID}_cap_green",
            "round_white": f"{MOD_ID}_cap_white",
            "round_small": f"{MOD_ID}_cap_white",
            "estop": f"{MOD_ID}_cap_red",
            "purge": f"{MOD_ID}_cap_amber",
        }[cap]
        # Machined collar. Proportional to the cap (spec.CAP_SOCKET_R), not
        # a constant 0.028 m annulus - that gave round_small a hole
        # two-thirds again its own radius while estop hugged.
        made.append(oriented_cylinder(
            f"cap_ring_{button['id']}", m[f"{MOD_ID}_bar_socket"],
            (x, y + 0.02, z), (x, y - 0.035, z), spec.CAP_SOCKET_R[cap],
            vertices=20, uv_tile=(0.4, 0.4)))
        made.append(oriented_cylinder(
            f"cap_{button['id']}", m[colour],
            (x, y - 0.02, z), (x, y - 0.02 - (0.075 if cap == "estop" else 0.045), z),
            radius, vertices=20, uv_tile=(0.4, 0.4)))
        if cap == "estop":
            made.append(oriented_cylinder(
                f"cap_dome_{button['id']}", m[colour],
                (x, y - 0.095, z), (x, y - 0.125, z), radius,
                radius_end=radius * 0.78, vertices=20, uv_tile=(0.4, 0.4)))
        if cap == "purge":
            # Guarded: a wire flip-guard over the purge cap, because purging
            # is the one control that throws things. A U-BAIL - two legs
            # STRAIGHT out of the plate and a crossbar joining their tips in
            # front of the cap. The first cut emitted the legs only, and
            # raked them 0.32 m in z across a 0.20 m run in y, so what
            # actually shipped was two yellow diagonals scribbled across the
            # button with nothing joining them, standing 0.065 m PROUDER
            # than the E-STOP mushroom. Nothing on a safety panel outreaches
            # the E-STOP; this bail stops 0.010 m short of it.
            guard_z = z + spec.PURGE_GUARD_DZ
            for sign in (-1.0, 1.0):
                made.append(oriented_cylinder(
                    f"cap_guard_{button['id']}_{'p' if sign > 0 else 'n'}",
                    m[f"{MOD_ID}_rail_steel"],
                    (x + sign * spec.PURGE_GUARD_LEG_X,
                     y + spec.PURGE_GUARD_ROOT_Y, guard_z),
                    (x + sign * spec.PURGE_GUARD_LEG_X,
                     y - spec.PURGE_GUARD_Y, guard_z),
                    spec.PURGE_GUARD_WIRE_R, vertices=10, uv_tile=(0.3, 0.3)))
            made.append(oriented_cylinder(
                f"cap_guard_{button['id']}_bar", m[f"{MOD_ID}_rail_steel"],
                (x - spec.PURGE_GUARD_LEG_X, y - spec.PURGE_GUARD_Y, guard_z),
                (x + spec.PURGE_GUARD_LEG_X, y - spec.PURGE_GUARD_Y, guard_z),
                spec.PURGE_GUARD_WIRE_R, vertices=10, uv_tile=(0.3, 0.3)))

    # BAR GRAPHS: EIGHT WINDOWS THAT READ WHETHER OR NOT THEY ARE LIT.
    #
    # The old socket was ONE BOX in bar_socket (0.13, 0.135, 0.145) sitting
    # 25 mm proud of a panel_dark plate at (0.07, 0.06, 0.06). Six hundredths
    # of contrast on a matte face at arm's length is nothing, and a solid box
    # has no window in it anyway: the row read as four lit blocks and then
    # bare panel, with the printed "182" over position 8 above nothing.
    #
    # A real bargraph's empty positions read because each is a moulded lens
    # inside a bright bezel. So each position is now a FRAME - four bars of
    # console_case, the cabinet's own cream paint, around a recessed
    # bar_lens_off lens. console_case and not a machined metal on purpose:
    # rendered 2026-08-25 with backface culling on, a pipe_steel bezel
    # (metallic 0.92) caught the sun dead ahead and went BLACK at three
    # quarters, because a metal with nothing to reflect reflects nothing. A
    # diffuse 0.80 cream against a panel_dark plate of 0.07 is 11:1 of albedo
    # from every angle, and it reads as a window machined out of the case
    # rather than as a part bolted on. It also costs no new texture and no
    # new bake. Depths, all relative to the console face (+y is into the
    # cabinet, so smaller y is closer to the driver):
    #
    #   bezel front face   front - 0.030
    #   lens front face    front - 0.030     FLUSH with the bezel
    #   lit block front    front - 0.065     (35 mm proud of both)
    #   lit block back     front - 0.005     (25 mm INTO the lens, no seam)
    #   hidden block       front + 0.095 .. + 0.155, behind the lens
    #
    # FLUSH, not recessed, and the render is why. Rendered 2026-08-25 with
    # backface culling on, a lens sunk 16 mm behind its bezel disappeared
    # completely at three quarters: at a grazing angle you see the near wall
    # of the recess and never its floor, so the empty windows read as holes
    # in shadow exactly as they did before. A moulded lens sits IN its bezel,
    # not down a well, and flush it reads from every angle a driver has.
    #
    # The frame's clear opening (0.062 x 0.048 half) is 2 mm larger than the
    # block (0.060 x 0.046 half) on each axis, so a lit block passes through
    # its own window instead of resting on the bezel.
    lens_half_x, lens_half_z = 0.062, 0.048
    bezel_half_x, bezel_half_z = 0.078, 0.062
    rail_x = (bezel_half_x - lens_half_x) * 0.5     # 0.008
    rail_z = (bezel_half_z - lens_half_z) * 0.5     # 0.007
    for gauge in ("pwr", "tilt"):
        z = spec.BAR_SEG_Z[gauge]
        for index, x in enumerate(spec.BAR_SEG_X, start=1):
            made.append(oriented_box(
                f"bar_lens_{gauge}{index}", m[f"{MOD_ID}_bar_lens_off"],
                (x, front - 0.012, z), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
                (0.0, 1.0, 0.0), lens_half_x, lens_half_z, 0.018,
                uv_tile=(0.3, 0.3)))
            for tag, centre, half in (
                ("t", (x, front - 0.014, z + lens_half_z + rail_z),
                 (bezel_half_x, rail_z, 0.016)),
                ("b", (x, front - 0.014, z - lens_half_z - rail_z),
                 (bezel_half_x, rail_z, 0.016)),
                ("l", (x - lens_half_x - rail_x, front - 0.014, z),
                 (rail_x, lens_half_z, 0.016)),
                ("r", (x + lens_half_x + rail_x, front - 0.014, z),
                 (rail_x, lens_half_z, 0.016)),
            ):
                made.append(oriented_box(
                    f"bar_bezel_{gauge}{index}{tag}",
                    m[f"{MOD_ID}_console_case"], centre,
                    (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0),
                    half[0], half[1], half[2], uv_tile=(0.3, 0.3)))

    # Instrument binnacle with two dials. Every dimension of the case, and
    # the two rows on its front, come from spec.BINNACLE_* - see the front
    # elevation stacked there. They used to be four independent copies of
    # the same three numbers spread over this function and spec.py, which is
    # how the dials came to hang over the nameplate with nothing complaining.
    made.append(oriented_box(
        "binnacle", m[f"{MOD_ID}_console_case"],
        (spec.CONSOLE_X, spec.BINNACLE_Y, spec.BINNACLE_Z),
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        spec.BINNACLE_HALF_X, spec.BINNACLE_HALF_Y, spec.BINNACLE_HALF_Z,
        uv_tile=(1.2, 1.2)))
    # ONE RIM, NOT TWO. The dial stack is quoted here as depths in front of
    # the pivot (-y is the driver), because the defect was entirely about the
    # order of these six numbers:
    #
    #   THE DOUBLED BEZEL. The can was authored at GAUGE_R and the bezel at
    #   GAUGE_R + 0.055, both of them visible face-on, so every dial showed
    #   TWO concentric rims 55 mm apart - and off-axis the can's rim slid out
    #   from behind the bezel's as the dark crescent visible past the right
    #   edge of both dials in the CP-3 console shot. Two rims on one
    #   instrument is not a bezel, it is a mistake that looks like depth.
    #   The can is at the bezel's radius now: one silhouette, and the can's
    #   own front cap becomes the machined shoulder the face sits in.
    #
    #   THE OVERHANG. The bezel ran from 0.040 BEHIND the pivot to 0.070 in
    #   front of it - a 110 mm tube around a 65 mm can - so a third of its
    #   length hung in space behind the instrument with nothing inside it. It
    #   is 44 mm long now and every millimetre of it sits on the can, and it
    #   stands 8 mm proud of the glass instead of 12, which is the crescent's
    #   own depth halved.
    #
    # The stack has to clear itself in y as well: ticks 0.008..0.032 (centre
    # 0.020, half 0.012), pointer 0.037..0.049 (centre 0.043, half 0.006),
    # glass 0.052..0.058. Every gap is 3 mm and none of them is zero.
    can_back = 0.060       # behind the pivot: the body of the instrument
    shoulder = 0.018       # can front cap - the machined land, in bar_socket
    face_d = 0.020         # printed face, 2 mm proud of its own land
    glass_d = 0.052        # inner surface of the cover glass
    bezel_d = 0.062        # bezel rim, 10 mm proud of the glass' inner face
    bezel_r = spec.GAUGE_BEZEL_R
    for pivot, face, tag in ((spec.GAUGE_VEL_PIVOT, f"{MOD_ID}_dial_vel", "vel"),
                             (spec.GAUGE_VAC_PIVOT, f"{MOD_ID}_dial_vac", "vac")):
        made.append(dial_face(
            f"dial_face_{tag}", m[face],
            (pivot[0], pivot[1] - face_d, pivot[2]), spec.GAUGE_R))
        made.append(oriented_cylinder(
            f"dial_can_{tag}", m[f"{MOD_ID}_bar_socket"],
            (pivot[0], pivot[1] + can_back, pivot[2]),
            (pivot[0], pivot[1] - shoulder, pivot[2]), bezel_r,
            vertices=40, uv_tile=(0.5, 0.5)))
        # OPEN ring, sitting ON the can rather than around it. Capped, its
        # front cap would be a solid steel disc the exact size of the dial -
        # which is what hid both faces on the first pass. mullion, not
        # tube_band. tube_band is metallic 0.9, so the bezel rendered as a
        # near-white ring sandwiched between a 0.93 face and the 0.80 cream
        # binnacle - three near-identical luminances stacked, and the
        # instrument dissolved into the cabinet. At 0.14 / metallic 0.4 the
        # ring separates the (now near-black) face from the case. mullion is
        # single-sided, so the bore of this ring is a back-face and never
        # renders: what you see through it is the face and its land.
        made.append(oriented_cylinder(
            f"dial_bezel_{tag}", m[f"{MOD_ID}_mullion"],
            (pivot[0], pivot[1] - shoulder, pivot[2]),
            (pivot[0], pivot[1] - bezel_d, pivot[2]), bezel_r,
            vertices=40, uv_tile=(0.5, 0.5), cap=False))
        # dial_glass, NOT obs_glass. obs_glass is the chamber window - it
        # carries emissive [0.40, 0.72, 0.90] at 170 nits, so glazing an
        # instrument with it puts a self-luminous blue pane 6 mm in front of
        # the only fine print on the machine. Set INSIDE the bezel now, so
        # the rim is the outermost thing on the instrument.
        made.append(oriented_cylinder(
            f"dial_glass_{tag}", m[f"{MOD_ID}_dial_glass"],
            (pivot[0], pivot[1] - glass_d, pivot[2]),
            (pivot[0], pivot[1] - glass_d - 0.006, pivot[2]),
            spec.GAUGE_R + 0.01, vertices=40, uv_tile=(0.5, 0.5)))
        # Tick ring. The modulus is spec.DIAL_TICK_MAJOR_EVERY, NOT 5: with
        # 5 the long ticks fell at indices 0/5/10/15/20 while _dial_scale
        # printed its six numerals at 0/4/8/12/16/20, so "40", "80", "120"
        # and "160" were printed against SHORT ticks and three long ticks
        # carried no number. spec asserts the count divides exactly.
        last = spec.DIAL_TICK_COUNT - 1
        for index in range(spec.DIAL_TICK_COUNT):
            radians = math.radians(spec.gauge_angle_deg(index / last))
            major = index % spec.DIAL_TICK_MAJOR_EVERY == 0
            outer = spec.DIAL_TICK_OUTER
            inner = (spec.DIAL_TICK_INNER_MAJOR if major
                     else spec.DIAL_TICK_INNER_MINOR)
            length = outer - inner
            direction = (math.sin(radians), 0.0, math.cos(radians))
            centre = (
                pivot[0] + direction[0] * (outer + inner) * 0.5,
                pivot[1] - 0.02,
                pivot[2] + direction[2] * (outer + inner) * 0.5,
            )
            # cap_white, not mullion: the face is now the panel's near-black
            # and a 0.14 tick on a 0.06 field is not a mark, it is a rumour.
            made.append(oriented_box(
                f"dial_tick_{tag}_{index:02d}", m[f"{MOD_ID}_cap_white"],
                centre, direction, (0.0, 1.0, 0.0),
                (direction[2], 0.0, -direction[0]),
                length * 0.5, 0.012, 0.018 if major else 0.010,
                uv_tile=(0.2, 0.2)))
        # Zero peg. A needle parked at the end of its scale reads as broken;
        # a needle parked AGAINST A STOP reads as parked. Offset just past
        # the end of the sweep by the blade's and the peg's own angular
        # half-widths at the tip, so the blade comes to rest touching it.
        peg_deg = (spec.gauge_angle_deg(spec.GAUGE_REST_FRAC[tag])
                   + (spec.DIAL_PEG_OFFSET_DEG
                      if spec.GAUGE_REST_FRAC[tag] > 0.5
                      else -spec.DIAL_PEG_OFFSET_DEG))
        peg_rad = math.radians(peg_deg)
        # ...and it has to stop BEHIND the glass like everything else on the
        # face: it used to run to 0.056, which is 4 mm through the pane.
        made.append(oriented_cylinder(
            f"dial_peg_{tag}", m[f"{MOD_ID}_mullion"],
            (pivot[0] + math.sin(peg_rad) * spec.NEEDLE_TIP_R,
             pivot[1] - face_d,
             pivot[2] + math.cos(peg_rad) * spec.NEEDLE_TIP_R),
            (pivot[0] + math.sin(peg_rad) * spec.NEEDLE_TIP_R,
             pivot[1] - (glass_d - 0.003),
             pivot[2] + math.cos(peg_rad) * spec.NEEDLE_TIP_R),
            spec.DIAL_PEG_R, vertices=10, uv_tile=(0.2, 0.2)))

    # Status tower, standing on the binnacle roof. It used to hang off the
    # cabinet's +X flank on a horizontal bracket - 0.30 m BEHIND the legend
    # plate, where the panel bezel occluded it from the driver's seat. It is
    # a signal tower now, so it gets a base flange rather than a bracket.
    sx, sy, sz = spec.STATUS_STACK
    made.append(oriented_cylinder(
        "status_base", m[f"{MOD_ID}_pipe_steel"],
        (sx, sy, sz - 0.04), (sx, sy, sz + 0.06),
        0.135, vertices=16, uv_tile=(0.4, 0.4)))
    made.append(oriented_cylinder(
        "status_post", m[f"{MOD_ID}_pipe_steel"], (sx, sy, sz - 0.30),
        (sx, sy, sz + 0.98), 0.055, vertices=12, uv_tile=(0.4, 0.4)))
    for index, dz in enumerate(spec.STATUS_LAMP_DZ):
        lens = (f"{MOD_ID}_cap_green", f"{MOD_ID}_cap_amber",
                f"{MOD_ID}_cap_red")[index]
        made.append(oriented_cylinder(
            f"status_lens_{index}", m[lens], (sx, sy, sz + dz),
            (sx, sy, sz + dz + 0.24), spec.STATUS_LAMP_R, vertices=18,
            uv_tile=(0.3, 0.3)))
        made.append(oriented_cylinder(
            f"status_collar_{index}", m[f"{MOD_ID}_mullion"],
            (sx, sy, sz + dz + 0.24), (sx, sy, sz + dz + 0.30),
            spec.STATUS_LAMP_R + 0.015, vertices=18, uv_tile=(0.3, 0.3)))

    # Binnacle nameplate. The dial faces were carrying their own instrument
    # names at 0.040 m on a surface read from 2.5 m; the names belong on an
    # engraved strip in the panel's type, where they are read once and then
    # never squinted at again. panel_quad, not oriented_box: a box is a loft
    # and a loft maps u around the perimeter, which smears the print.
    made.append(panel_quad(
        "binnacle_plate", m[f"{MOD_ID}_binnacle_plate"],
        (spec.CONSOLE_X, spec.BINNACLE_FRONT_Y - 0.01, spec.BINNACLE_PLATE_Z),
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
        spec.BINNACLE_PLATE_W * 0.5, spec.BINNACLE_PLATE_H * 0.5,
        (0.0, -1.0, 0.0)))
    return made


def build_facade(m) -> list:
    """What the approach face carries: the nameboard and its service walk.

    See the "approach face" block in spec.py for why any of this is here and
    why all of it hangs at theta 180. Two objects do the reading and the rest
    is what makes them believable as hardware:

    * the NAMEBOARD, standoff-mounted on the flange crowns at the disc's own
      axis height, which is the only station on the face pointing straight
      down the ramp;
    * the SERVICE WALK 3.1 m under it, whose 1.10 m handrail is the machine's
      only human-sized object visible from the drive in.

    Everything is built flat rather than revolved. The shell is a cylinder of
    radius 21.6 and the tallest thing here spans 1.60 m of it, so a plane
    tangent at theta 180 departs from the surface by
    21.6 * (1 - cos(0.80/21.6)) = 15 mm at its edges - against a standoff of
    420 mm. A board bolted across five stiffeners IS flat; modelling it curved
    would be less true, not more.
    """

    made: list = []
    # Deck. The inboard edge is the shell SURFACE at this height, derived in
    # spec.py so the swept-keepout box and the geometry describe one object.
    inboard = spec.WALK_IN_Y
    outboard = spec.WALK_OUT_Y
    walk_x = (-spec.WALK_HALF_X, 0.0, spec.WALK_HALF_X)
    made.append(grid_surface(
        "walk_deck", m[f"{MOD_ID}_deck_plate"],
        [[(x, inboard, spec.WALK_Z) for x in walk_x],
         [(x, outboard, spec.WALK_Z) for x in walk_x]],
        uv_rows=[0.0, abs(outboard - inboard) / 1.2],
        uv_cols=[(x + spec.WALK_HALF_X) / 1.2 for x in walk_x],
        outward=(0.0, 0.0, 1.0)))
    # Toe board. Hazard rather than plate: it is the edge of a 13 m drop, and
    # the kerbs on the ramp and in the tunnel already carry the same paint.
    made.append(oriented_box(
        "walk_toe", m[f"{MOD_ID}_hazard"],
        (0.0, outboard - 0.03, spec.WALK_Z + spec.WALK_TOE_H * 0.5),
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0),
        spec.WALK_HALF_X, spec.WALK_TOE_H * 0.5, 0.03, uv_tile=(0.8, 0.8)))
    rail_y = outboard + 0.06
    for index in range(6):
        post_x = -spec.WALK_HALF_X + index * (spec.WALK_HALF_X * 2.0 / 5.0)
        made.append(oriented_cylinder(
            f"walk_post_{index}", m[f"{MOD_ID}_rail_steel"],
            (post_x, rail_y, spec.WALK_Z),
            (post_x, rail_y, spec.WALK_Z + spec.WALK_RAIL_H),
            0.06, vertices=10, uv_tile=(0.4, 0.4)))
    for height in (spec.WALK_MID_H, spec.WALK_RAIL_H):
        made.append(oriented_box(
            f"walk_rail_{height:.2f}", m[f"{MOD_ID}_rail_steel"],
            (0.0, rail_y, spec.WALK_Z + height), (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), 0.045, 0.045,
            spec.WALK_HALF_X, uv_tile=(0.4, 0.4)))
        # Ends returned to the vessel. An unterminated handrail reads as a
        # rail that has been cut off, which is worse than no rail.
        for sign in (-1.0, 1.0):
            made.append(oriented_box(
                f"walk_rail_end_{'p' if sign > 0 else 'n'}_{height:.2f}",
                m[f"{MOD_ID}_rail_steel"],
                (sign * spec.WALK_HALF_X, (rail_y + inboard) * 0.5,
                 spec.WALK_Z + height), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
                (0.0, 1.0, 0.0), 0.045, 0.045, abs(rail_y - inboard) * 0.5,
                uv_tile=(0.4, 0.4)))
    # Knee braces. A 1.30 m deck cantilevered off a shell has them, and from
    # the ramp you look at the UNDERSIDE of this walk, not the top of it.
    brace_z = spec.WALK_BRACE_Z
    brace_y = spec.WALK_BRACE_Y
    for index, brace_x in enumerate((-4.6, -1.8, 1.8, 4.6)):
        made.append(oriented_cylinder(
            f"walk_brace_{index}", m[f"{MOD_ID}_rib_steel"],
            (brace_x, outboard + 0.05, spec.WALK_Z - 0.05),
            (brace_x, brace_y, brace_z), 0.09, vertices=8, uv_tile=(0.5, 0.5)))

    # The nameboard. Frame first, so the print reads as inset in a cabinet
    # rather than stuck on the steel: 0.276 m of frame above and below the
    # panel, 0.20 m either side.
    made.append(oriented_box(
        "sign_frame", m[f"{MOD_ID}_mullion"],
        (0.0, spec.SIGN_FRAME_Y, spec.SIGN_Z), (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0), (0.0, 1.0, 0.0), spec.SIGN_FRAME_HALF_X,
        spec.SIGN_FRAME_HALF_Z, spec.SIGN_FRAME_HALF_Y, uv_tile=(1.6, 1.6)))
    made.append(panel_quad(
        "sign_panel", m[f"{MOD_ID}_sign_panel"],
        (0.0, spec.SIGN_FACE_Y, spec.SIGN_Z),
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), spec.SIGN_HALF_X, spec.SIGN_HALF_Z,
        (0.0, -1.0, 0.0)))

    # THE DRIVE FEEDERS - the only saturated, non-hazard-yellow hardware at
    # eye level on this face, and the only thing on the approach that says
    # what the machine is FOR. Derivation and colours: the "drive feeders"
    # block in spec.py. Two cabinets flanking the portal, each with a
    # three-phase copper run climbing into a gland on the vessel.
    for sign in (-1.0, 1.0):
        tag = "p" if sign > 0 else "n"
        cabinet_x = sign * spec.FEED_X
        made.append(oriented_box(
            f"feed_cabinet_{tag}", m[f"{MOD_ID}_clamp_paint"],
            (cabinet_x, spec.FEED_Y, (spec.FEED_Z0 + spec.FEED_Z1) * 0.5),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
            spec.FEED_HALF_X, spec.FEED_HALF_Y, spec.FEED_HEIGHT * 0.5,
            uv_tile=(1.4, 1.4)))
        # Roof cap and plinth, so a 4 m box reads as switchgear standing on
        # concrete rather than as a crate dropped on the apron.
        made.append(oriented_box(
            f"feed_roof_{tag}", m[f"{MOD_ID}_mullion"],
            (cabinet_x, spec.FEED_Y, spec.FEED_Z1 + 0.07),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
            spec.FEED_HALF_X + 0.10, spec.FEED_HALF_Y + 0.10, 0.07,
            uv_tile=(1.0, 1.0)))
        made.append(oriented_box(
            f"feed_base_{tag}", m[f"{MOD_ID}_concrete"],
            (cabinet_x, spec.FEED_Y, spec.FEED_Z0 + 0.09),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
            spec.FEED_HALF_X + 0.18, spec.FEED_HALF_Y + 0.18, 0.09,
            uv_tile=(1.0, 1.0)))
        # Louvre band at reading height: a blank 2.6 m orange face is a
        # shipping container, a louvred one is a converter.
        for index in range(3):
            made.append(oriented_box(
                f"feed_louvre_{tag}_{index}", m[f"{MOD_ID}_mullion"],
                (cabinet_x, spec.FEED_Y - spec.FEED_HALF_Y - 0.02,
                 spec.FEED_Z0 + 2.10 + index * 0.42),
                (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0),
                spec.FEED_HALF_X - 0.22, 0.13, 0.03, uv_tile=(0.5, 0.5)))
        # The three-phase riser. Insulator, then the bar, per phase - the bar
        # leans inboard AND up, from the cabinet roof to its end of the
        # header, which is what makes the vessel's overhang legible from the
        # ramp instead of being a shadow.
        for index in range(spec.FEED_BARS):
            offset = (index - (spec.FEED_BARS - 1) * 0.5) * spec.FEED_BAR_PITCH
            foot = (cabinet_x + sign * offset,
                    spec.FEED_Y - spec.FEED_HALF_Y * 0.4,
                    spec.FEED_Z1 + 0.14 + 0.34)
            head = (sign * spec.FEED_HEADER_HALF_X,
                    spec.FEED_HEADER_Y,
                    spec.FEED_HEADER_Z + offset)
            made.append(oriented_cylinder(
                f"feed_insul_{tag}_{index}", m[f"{MOD_ID}_mullion"],
                (foot[0], foot[1], spec.FEED_Z1 + 0.14),
                (foot[0], foot[1], foot[2]), spec.FEED_INSULATOR_R,
                vertices=12, uv_tile=(0.3, 0.3)))
            made.append(oriented_cylinder(
                f"feed_bar_{tag}_{index}", m[f"{MOD_ID}_copper_bus"],
                foot, head, spec.FEED_BAR_R, vertices=12, uv_tile=(0.6, 0.6)))

    # THE HEADER. Three horizontal bars straight across the approach face,
    # standing off the shell on four insulator pairs, with the gland box on
    # the machine's axis where they enter it. See the FEED_HEADER_Z block in
    # spec.py: this is the element the frame was short of, and it is the only
    # horizontal line on a face whose furniture is otherwise all vertical.
    for index in range(spec.FEED_BARS):
        offset = (index - (spec.FEED_BARS - 1) * 0.5) * spec.FEED_BAR_PITCH
        made.append(oriented_cylinder(
            f"feed_header_{index}", m[f"{MOD_ID}_copper_bus"],
            (-spec.FEED_HEADER_HALF_X, spec.FEED_HEADER_Y,
             spec.FEED_HEADER_Z + offset),
            (spec.FEED_HEADER_HALF_X, spec.FEED_HEADER_Y,
             spec.FEED_HEADER_Z + offset),
            spec.FEED_BAR_R, vertices=12, uv_tile=(0.6, 0.6)))
    for index, stand_x in enumerate((-3.40, -1.40, 1.40, 3.40)):
        # Back to the shell surface at this height, not to a constant y: the
        # shell is a cylinder about X, so the standoff length is the same for
        # every one of these and the bracket line is straight.
        made.append(oriented_cylinder(
            f"feed_stand_{index}", m[f"{MOD_ID}_mullion"],
            (stand_x, spec.FEED_HEADER_Y + spec.FEED_HEADER_STANDOFF,
             spec.FEED_HEADER_Z),
            (stand_x, spec.FEED_HEADER_Y - 0.10, spec.FEED_HEADER_Z),
            spec.FEED_INSULATOR_R, vertices=12, uv_tile=(0.3, 0.3)))
    made.append(oriented_box(
        "feed_gland", m[f"{MOD_ID}_copper_bus"],
        (spec.FEED_GLAND_X, spec.FEED_GLAND_Y + 0.20, spec.FEED_GLAND_Z),
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        0.98, 0.30, 0.72, uv_tile=(0.6, 0.6)))
    return made


def build_beacon_housing(m) -> list:
    """The pedestal the rotating beacon retracts into."""

    bx, by, bz = spec.BEACON_PIVOT
    return [
        oriented_cylinder(
            "beacon_housing", m[f"{MOD_ID}_rib_steel"], (bx, by, bz - 1.35),
            (bx, by, bz - 0.05), 0.62, vertices=20, uv_tile=(0.8, 0.8)),
        oriented_box(
            "beacon_base", m[f"{MOD_ID}_lid_plate"], (bx, by, bz - 1.50),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 1.1, 1.1, 0.18,
            uv_tile=(1.0, 1.0)),
    ]


def build_visual(m) -> list:
    objects: list = []
    objects += build_chamber(m)
    objects += build_slot(m)
    objects += build_tunnel(m)
    objects += build_civil(m)
    objects += build_plant(m)
    objects += build_console(m)
    objects += build_facade(m)
    objects += build_beacon_housing(m)
    return objects


# ---------------------------------------------------------------------------
# Kinematic runtime parts.
# ---------------------------------------------------------------------------
def build_tether(m) -> list:
    """Composite blade, hub rotor, counterweight and the payload cradle.

    Authored PARKED at bottom-dead-centre, which is the pose the cradle has
    to be in for a car to be driven onto it; the runtime rotates the whole
    part about the hub from there.
    """

    made: list = []
    load = spec.LOAD_THETA_DEG
    out = radial_dir(load)  # points down at BDC
    travel = tangent_dir(load)
    across = (1.0, 0.0, 0.0)

    made.append(oriented_cylinder(
        "tether_rotor", m[f"{MOD_ID}_cradle_steel"],
        (-2.6, 0.0, spec.HUB_Z), (2.6, 0.0, spec.HUB_Z), 3.35, vertices=44,
        uv_tile=(1.8, 1.8)))
    for sign in (-1.0, 1.0):
        made.append(oriented_cylinder(
            f"tether_hubcap_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_carbon_tether"],
            (sign * 2.6, 0.0, spec.HUB_Z), (sign * 3.1, 0.0, spec.HUB_Z),
            3.35, radius_end=2.2, vertices=44,
            uv_tile=(CARBON_TILE, CARBON_TILE)))

    # Main blade: a lofted composite strap, thick and wide at the root where
    # the tension is, tapering to the cradle.
    sections = []
    stations = [3.0, 5.0, 7.5, 10.0, 12.5, 14.6, 16.0]
    for radius in stations:
        fraction = (radius - stations[0]) / (stations[-1] - stations[0])
        chord = 2.30 - 0.72 * fraction
        thick = 0.86 - 0.44 * fraction
        centre = Vector(ring(load, radius))
        section = []
        for u, v in superellipse(20, chord * 0.5, thick * 0.5, power=0.55):
            section.append(tuple(
                centre + Vector(across) * u + Vector(travel) * v))
        sections.append(section)
    made.append(loft("tether_blade", m[f"{MOD_ID}_carbon_tether"], sections,
                     uv_tile=(CARBON_TILE, CARBON_TILE)))

    # Counterweight arm on the opposite side, deliberately short and fat:
    # this is the mass that keeps the bearing loads finite.
    back = (load + 180.0) % 360.0
    back_out = radial_dir(back)
    back_travel = tangent_dir(back)
    sections = []
    for radius in (3.0, 5.0, 7.0, 8.6):
        fraction = (radius - 3.0) / 5.6
        chord = 2.30 - 0.30 * fraction
        thick = 0.86 - 0.16 * fraction
        centre = Vector(ring(back, radius))
        sections.append([
            tuple(centre + Vector(across) * u + Vector(back_travel) * v)
            for u, v in superellipse(20, chord * 0.5, thick * 0.5, power=0.55)
        ])
    made.append(loft("tether_cwarm", m[f"{MOD_ID}_carbon_tether"], sections,
                     uv_tile=(CARBON_TILE, CARBON_TILE)))
    cw_centre = ring(back, 9.9)
    made.append(oriented_box(
        "tether_cw", m[f"{MOD_ID}_counterweight"], cw_centre, across,
        back_travel, back_out, 1.45, 0.95, 1.45, uv_tile=(1.2, 1.2)))
    for index in range(4):
        offset = -1.05 + index * 0.70
        made.append(oriented_box(
            f"tether_cw_fin_{index}", m[f"{MOD_ID}_counterweight"],
            tuple(Vector(cw_centre) + Vector(back_out) * (1.55)
                  + Vector(across) * offset),
            across, back_travel, back_out, 0.16, 0.85, 0.22,
            uv_tile=(0.6, 0.6)))

    # Payload cradle. At bottom-dead-centre radius maps straight to height
    # (z = HUB_Z - r), so the whole assembly is authored by radius: the
    # blade stops at r 16.0 (z 3.5, half a metre CLEAR above the deck), two
    # posts drop through the deck's slots, and the bed hangs at r 16.65
    # (z 2.85) inside the slab where nothing can see it until the deck goes.
    yoke_r = spec.TETHER_R - 0.40  # 16.10 -> z 3.40, above the deck
    bed_r = spec.HUB_Z - (spec.CRADLE_BED_TOP - 0.10)  # 16.65 -> z 2.85
    made.append(oriented_box(
        "cradle_yoke", m[f"{MOD_ID}_cradle_steel"], ring(load, yoke_r),
        across, travel, out, spec.CRADLE_RAIL_X + 0.28, 0.55, 0.16,
        uv_tile=(0.9, 0.9)))
    for sign in (-1.0, 1.0):
        tag = "p" if sign > 0 else "n"
        rail_x = sign * spec.CRADLE_RAIL_X
        # Post through the deck slot, from the yoke down to the bed.
        made.append(oriented_box(
            f"cradle_post_{tag}", m[f"{MOD_ID}_cradle_steel"],
            tuple(Vector(ring(load, (yoke_r + bed_r) * 0.5))
                  + Vector(across) * rail_x),
            across, travel, out, 0.18, 0.26, (bed_r - yoke_r) * 0.5 + 0.12,
            uv_tile=(0.6, 0.6)))
        # The rail that sits IN the slot, 2 cm proud of the deck so the slot
        # reads as machinery rather than as a gap.
        made.append(oriented_box(
            f"cradle_rail_{tag}", m[f"{MOD_ID}_cradle_steel"],
            tuple(Vector(ring(load, spec.TETHER_R + 0.14))
                  + Vector(across) * rail_x),
            across, travel, out, 0.19, spec.CRADLE_HALF_Y, 0.16,
            uv_tile=(0.8, 0.8)))
        for index in range(5):
            along = -spec.CRADLE_HALF_Y + 0.7 + index * 1.25
            made.append(oriented_box(
                f"cradle_roller_{tag}_{index}", m[f"{MOD_ID}_tube_band"],
                tuple(Vector(ring(load, spec.TETHER_R + 0.02))
                      + Vector(across) * rail_x + Vector(travel) * along),
                across, travel, out, 0.13, 0.14, 0.05, uv_tile=(0.3, 0.3)))
    made.append(oriented_box(
        "cradle_bed", m[f"{MOD_ID}_cradle_steel"], ring(load, bed_r),
        across, travel, out, spec.CRADLE_HALF_X, spec.CRADLE_HALF_Y, 0.10,
        uv_tile=(1.2, 1.2)))
    for index in range(6):
        along = -spec.CRADLE_HALF_Y + 0.45 + index * 1.10
        made.append(oriented_box(
            f"cradle_bed_rib_{index}", m[f"{MOD_ID}_carbon_tether"],
            tuple(Vector(ring(load, bed_r + 0.22)) + Vector(travel) * along),
            across, travel, out, spec.CRADLE_HALF_X - 0.1, 0.14, 0.14,
            uv_tile=(CARBON_TILE, CARBON_TILE)))
    # Gussets tying the yoke back into the blade, above the deck plane.
    for sign in (-1.0, 1.0):
        made.append(oriented_box(
            f"cradle_web_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_carbon_tether"],
            tuple(Vector(ring(load, yoke_r - 0.55))
                  + Vector(across) * (sign * 0.95)),
            across, travel, out, 0.12, 0.42, 0.55,
            uv_tile=(CARBON_TILE, CARBON_TILE)))
    return made


def build_clamp(m, side: str) -> list:
    """One cradle clamp arm, authored OPEN - straight up, gates raised."""

    sign = -1.0 if side == "l" else 1.0
    pivot = Vector(spec.CLAMP_PIVOT_L if side == "l" else spec.CLAMP_PIVOT_R)
    length = spec.CLAMP_ARM
    made: list = []
    made.append(oriented_cylinder(
        f"clamp_hinge_{side}", m[f"{MOD_ID}_tube_band"],
        tuple(pivot + Vector((0.0, -0.62, 0.0))),
        tuple(pivot + Vector((0.0, 0.62, 0.0))), 0.17, vertices=16,
        uv_tile=(0.5, 0.5)))
    made.append(oriented_box(
        f"clamp_arm_{side}", m[f"{MOD_ID}_clamp_paint"],
        tuple(pivot + Vector((0.0, 0.0, length * 0.5))),
        (0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0),
        length * 0.5, 0.40, 0.15, uv_tile=(0.7, 0.7)))
    # Pad faces INBOARD: once the arm has swung over, this is the face that
    # meets the payload's flank.
    made.append(oriented_box(
        f"clamp_pad_{side}", m[f"{MOD_ID}_seal_rubber"],
        tuple(pivot + Vector((-sign * 0.20, 0.0, length - 0.06))),
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        0.13, 0.50, 0.26, uv_tile=(0.4, 0.4)))
    made.append(oriented_box(
        f"clamp_head_{side}", m[f"{MOD_ID}_clamp_paint"],
        tuple(pivot + Vector((0.0, 0.0, length + 0.10))),
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        0.20, 0.44, 0.16, uv_tile=(0.5, 0.5)))
    made.append(oriented_cylinder(
        f"clamp_ram_{side}", m[f"{MOD_ID}_pipe_steel"],
        tuple(pivot + Vector((sign * 0.34, -0.46, 0.05))),
        tuple(pivot + Vector((sign * 0.06, -0.46, length * 0.62))),
        0.10, vertices=12, uv_tile=(0.4, 0.4)))
    made.append(oriented_cylinder(
        f"clamp_ram_b_{side}", m[f"{MOD_ID}_pipe_steel"],
        tuple(pivot + Vector((sign * 0.34, 0.46, 0.05))),
        tuple(pivot + Vector((sign * 0.06, 0.46, length * 0.62))),
        0.10, vertices=12, uv_tile=(0.4, 0.4)))
    return made


def tube_ring(name, material, at_fn, station, r_inner, r_outer, outward, *,
              vertices=40, uv_tile=(1.0, 1.0)):
    """An ANNULAR face in the tube's own frame, so a flange is a ring not a plug.

    ``oriented_cylinder`` defaults ``cap=True``, and every flange, collar,
    seal, muzzle and hazard band on this tube took that default - fifteen
    SOLID DISCS across a 2.55 m bore between stations 0.35 and 30. tube_bore
    is cap=False and does not hide them, so looking down the muzzle of the
    launch tube you saw a wall. cap=False on its own is not the fix either:
    it exposes the 0.37 m annulus between TUBE_WALL_R and TUBE_RIB_R and the
    ring becomes an open edge. The face has to be an ANNULUS, and
    grid_surface takes arbitrary equal-length rows, so this needs no toolkit
    change - two rings of ``vertices + 1`` points in the tube's own frame.

    ``outward`` is the tube AXIS or its negative, never a radial sentinel: a
    flat annulus has no radial opinion, and grid_surface's own handedness
    scan needs a direction the face actually has a dot product with. Pass
    the direction the face LOOKS - aft for the low-station end of a section,
    fore for the high-station end - and the winding is derived, the same
    discipline _winding_is_wrong exists to enforce. Get it backwards and the
    ring renders as a hole, which is a fresh instance of the defect it
    closes.

    ``at_fn`` is build_tube's own ``at(station, radial, lateral)`` closure.
    radial runs along tube_radial and lateral along authored +X, and those
    two are orthonormal and both perpendicular to the axis (tube_axis has no
    x component), so cos/sin over them sweeps a true circle.
    """

    radius_mid = (r_inner + r_outer) * 0.5
    angles = [2.0 * math.pi * k / vertices for k in range(vertices + 1)]
    rows = [[at_fn(station, math.cos(a) * radius, math.sin(a) * radius)
             for a in angles]
            for radius in (r_inner, r_outer)]
    return grid_surface(
        name, material, rows,
        # Metric UVs, same rule as revolve: v is the ring's radial width and
        # u is arc length at the MID radius, both over the tile size.
        uv_rows=[0.0, (r_outer - r_inner) / uv_tile[1]],
        uv_cols=[radius_mid * a / uv_tile[0] for a in angles],
        outward=outward, smooth_angle=20.0)


def build_tube(m) -> list:
    """Barrel, flange rings, sonic-baffle case, travelling collar, muzzle head."""

    made: list = []
    tilt = spec.TILT_REF_DEG
    axis = Vector(spec.tube_axis(tilt))
    normal = Vector(spec.tube_radial(tilt))
    lateral = Vector((1.0, 0.0, 0.0))
    # The only two directions a flat face on this tube can look: aft, back
    # toward the breech, and fore, out of the muzzle. Every annular flange
    # face below is one or the other - see tube_ring.
    aft = tuple(-axis)
    fore = tuple(axis)

    def at(station, radial=0.0, side=0.0):
        return spec.tube_point(tilt, station, radial, side)

    # THE DRIVE BANDS: the two barrel flanges that clear the collar.
    #
    # The reviewer's approach note was that the barrel root "reads as a grey
    # duct entering a grey shell", and the round that answered it put the
    # copper-and-orange switchgear vocabulary on the GROUND (the drive-feeder
    # cabinets and the copper bus header) while concluding the tube itself
    # could not be in the approach frame at all. That conclusion was
    # overstated: the muzzle is out at tilt 72, but the BARREL ROOT is in
    # frame at every rung from both closer cameras - 14.04 to 15.49 degrees
    # above centre at approach_low against a 19.88 degree vertical half-FOV,
    # and 17.25 to 18.43 at approach_high.
    #
    # So the vocabulary continues up the barrel, and WHICH bands is measured
    # rather than picked. The tube pierces the shell at station
    # sqrt(SHELL_R^2 - PAYLOAD_R^2) = 14.62, the collar spans that +/-1.15,
    # and the eleven flanges land at -0.45, 2.59, 5.64, 8.68, 11.73, 14.77,
    # 17.82, 20.86, 23.91, 26.95, 30.00. Everything below 13.47 is inside the
    # pressure vessel and flange 05 at 14.77 is buried inside the collar
    # (radius TUBE_RIB_R = 3.62 against the collar's 4.04) - confirmed on a
    # false-colour ID render from approach_low, where 05 is a two-pixel
    # sliver at the collar's lip. The first two bands a driver can actually
    # see are 06 and 07.
    #
    # copper_bus, not a new colour: the barrel root is where the accelerator's
    # drive terminates, and the run it terminates from is the same copper
    # header climbing into the gland at FEED_GLAND_Z 30 m below. One facility,
    # one metal.
    DRIVE_BANDS = (6, 7)
    length = spec.TUBE_S1 - spec.TUBE_S0
    for index in range(spec.TUBE_SEGMENTS):
        s0 = spec.TUBE_S0 + length * index / spec.TUBE_SEGMENTS
        s1 = spec.TUBE_S0 + length * (index + 1) / spec.TUBE_SEGMENTS
        band = m[f"{MOD_ID}_copper_bus" if index in DRIVE_BANDS
                 else f"{MOD_ID}_tube_band"]
        made.append(oriented_cylinder(
            f"tube_barrel_{index:02d}", m[f"{MOD_ID}_tube_shell"],
            at(s0 + 0.06), at(s1 - 0.06), spec.TUBE_WALL_R, vertices=40,
            uv_tile=(2.0, 2.0), cap=False))
        # cap=False plus two ANNULI. Capped, each of these eleven flanges
        # was a solid disc of radius TUBE_RIB_R straight across the bore.
        # The faces run from the barrel's own outer skin out to the rim.
        made.append(oriented_cylinder(
            f"tube_flange_{index:02d}", band,
            at(s1 - 0.20), at(s1 + 0.20), spec.TUBE_RIB_R, vertices=40,
            uv_tile=(1.0, 1.0), cap=False))
        for face, (face_s, face_out) in enumerate(
                ((s1 - 0.20, aft), (s1 + 0.20, fore))):
            made.append(tube_ring(
                f"tube_flange_{index:02d}_face_{face}", band, at, face_s,
                spec.TUBE_WALL_R, spec.TUBE_RIB_R, face_out,
                uv_tile=(1.0, 1.0)))
        for bolt in range(20):
            angle = 2.0 * math.pi * bolt / 20.0
            offset = normal * (math.cos(angle) * (spec.TUBE_RIB_R + 0.02)) \
                + lateral * (math.sin(angle) * (spec.TUBE_RIB_R + 0.02))
            centre = Vector(at(s1)) + offset
            made.append(oriented_cylinder(
                f"tube_bolt_{index:02d}_{bolt:02d}", m[f"{MOD_ID}_tube_band"],
                tuple(centre - axis * 0.22), tuple(centre + axis * 0.22),
                0.055, vertices=8, uv_tile=(0.25, 0.25)))
    # Dark bore, so looking down the tube reads as a hole and not a wall.
    made.append(oriented_cylinder(
        "tube_bore", m[f"{MOD_ID}_bore_dark"], at(spec.TUBE_S0 - 0.2),
        at(spec.TUBE_S1 + 0.1), spec.TUBE_BORE_R, vertices=40,
        uv_tile=(2.0, 2.0), cap=False))
    made.append(oriented_cylinder(
        "tube_breech", m[f"{MOD_ID}_tube_band"], at(spec.TUBE_S0 - 0.5),
        at(spec.TUBE_S0), spec.TUBE_RIB_R, radius_end=spec.TUBE_WALL_R,
        vertices=40, uv_tile=(1.0, 1.0)))

    # Sonic-damping baffle case running alongside the barrel, the boxy
    # structure that reads as the second half of the launch tube. It is 3.3 m
    # across including its ribs, so it can never pass through the shell
    # furniture and has to BEGIN outboard of it - see BAFFLE_S0. Hung inboard
    # from station 3.0 its aft corner sat at chamber radius 13.2, buried in
    # the +X lid and ploughing the rib fan at every rung.
    baffle_start, baffle_end = spec.BAFFLE_S0, spec.BAFFLE_S1
    made.append(oriented_box(
        "tube_baffle", m[f"{MOD_ID}_baffle_case"],
        at((baffle_start + baffle_end) * 0.5, spec.BAFFLE_RADIAL,
           spec.BAFFLE_LATERAL),
        lateral, normal, axis, spec.BAFFLE_HALF_LATERAL,
        spec.BAFFLE_HALF_RADIAL, (baffle_end - baffle_start) * 0.5,
        uv_tile=(2.0, 2.0)))
    for index in range(9):
        station = baffle_start + (baffle_end - baffle_start) * index / 8.0
        made.append(oriented_box(
            f"tube_baffle_rib_{index}", m[f"{MOD_ID}_tube_band"],
            at(station, spec.BAFFLE_RADIAL, spec.BAFFLE_LATERAL),
            lateral, normal, axis, spec.BAFFLE_RIB_HALF_LATERAL,
            spec.BAFFLE_RIB_HALF_RADIAL, spec.BAFFLE_RIB_HALF_AXIAL,
            uv_tile=(0.8, 0.8)))
        made.append(oriented_cylinder(
            f"tube_baffle_tie_{index}", m[f"{MOD_ID}_pipe_steel"],
            at(station, spec.BAFFLE_RADIAL, 3.05),
            at(station, spec.BAFFLE_RADIAL, 3.30), 0.14,
            vertices=10, uv_tile=(0.4, 0.4)))

    # Travelling collar at the shell pierce station, with the rollers that
    # ride the slot rails and the curved apron that seals the shingles.
    pierce = math.sqrt(spec.SHELL_R**2 - spec.PAYLOAD_R**2)
    # clamp_paint, the machine's MOVING-HARDWARE orange. This collar is the
    # travelling seal carriage - it rides the slot rails through a 79.9 degree
    # arc every time the elevation changes - and it is the largest single
    # object in the approach frame's barrel root (measured on the ID render:
    # the collar is the ring, flanges 06 and 07 are the two bands above it).
    # It carries the same paint as the cradle clamps and the feeder cabinets
    # below, which is this facility's colour for "this part moves or this part
    # is live", and its saturation (S = 0.93) is the highest on the machine.
    made.append(oriented_cylinder(
        "tube_collar", m[f"{MOD_ID}_clamp_paint"], at(pierce - 1.15),
        at(pierce + 1.15), spec.TUBE_RIB_R + 0.42, vertices=40,
        uv_tile=(1.2, 1.2), cap=False))
    for face, (face_s, face_out) in enumerate(
            ((pierce - 1.15, aft), (pierce + 1.15, fore))):
        made.append(tube_ring(
            f"tube_collar_face_{face}", m[f"{MOD_ID}_clamp_paint"], at, face_s,
            spec.TUBE_WALL_R, spec.TUBE_RIB_R + 0.42, face_out,
            uv_tile=(1.2, 1.2)))
    made.append(oriented_cylinder(
        "tube_collar_seal", m[f"{MOD_ID}_seal_rubber"], at(pierce - 1.32),
        at(pierce - 1.15), spec.TUBE_RIB_R + 0.46, vertices=40,
        uv_tile=(0.5, 0.5), cap=False))
    for face, (face_s, face_out) in enumerate(
            ((pierce - 1.32, aft), (pierce - 1.15, fore))):
        made.append(tube_ring(
            f"tube_collar_seal_face_{face}", m[f"{MOD_ID}_seal_rubber"], at,
            face_s, spec.TUBE_WALL_R, spec.TUBE_RIB_R + 0.46, face_out,
            uv_tile=(0.5, 0.5)))
    apron_theta = spec.release_theta_deg(tilt) - spec.TANGENT_OFFSET_OUT_DEG
    for apron_index, arc in enumerate(((apron_theta - 13.0, apron_theta - 4.5),
                                       (apron_theta + 4.5, apron_theta + 13.0))):
        # APRON_R, not SHELL_R + 0.22: the leaves step OUTWARD, so the apron
        # has to clear the LAST one (22.048), not the first (21.700).
        made += revolve(f"tube_apron_{apron_index}", m[f"{MOD_ID}_lid_plate"],
                        [(-spec.OUTER_HALF_X - 0.55, spec.APRON_R),
                         (spec.OUTER_HALF_X + 0.55, spec.APRON_R)],
                        [arc], step_deg=1.0, uv_tile=(1.4, 1.4),
                        smooth_angle=20.0)
    for sign in (-1.0, 1.0):
        for index, offset in enumerate(spec.ROLLER_OFFSETS):
            # Each truck gets its OWN radial offset. A straight beam riding a
            # curved rail cannot have all three on the bore axis.
            centre = Vector(
                at(pierce + offset, spec.ROLLER_RADIAL[index])
            ) + lateral * (sign * spec.SLOT_RAIL_X)
            made.append(oriented_cylinder(
                f"tube_roller_{'p' if sign > 0 else 'n'}_{index}",
                m[f"{MOD_ID}_tube_band"],
                tuple(centre - lateral * (sign * 0.14)),
                tuple(centre + lateral * (sign * 0.14)), spec.ROLLER_R,
                vertices=14, uv_tile=(0.3, 0.3)))

    # Muzzle head: a flared crown with a hazard band, then the hatch (its own
    # part) hinged on the lip.
    # The one the player actually looks down. Flared, so the two faces do
    # NOT share an outer radius: aft at TUBE_RIB_R where it meets the last
    # barrel section, fore at the crown's full 4.17 m lip.
    made.append(oriented_cylinder(
        "tube_muzzle", m[f"{MOD_ID}_tube_band"], at(spec.TUBE_S1 - 1.4),
        at(spec.TUBE_S1), spec.TUBE_RIB_R, radius_end=spec.TUBE_RIB_R + 0.55,
        vertices=40, uv_tile=(1.0, 1.0), cap=False))
    for face, (face_s, face_r, face_out) in enumerate((
            (spec.TUBE_S1 - 1.4, spec.TUBE_RIB_R, aft),
            (spec.TUBE_S1, spec.TUBE_RIB_R + 0.55, fore))):
        made.append(tube_ring(
            f"tube_muzzle_face_{face}", m[f"{MOD_ID}_tube_band"], at, face_s,
            spec.TUBE_WALL_R, face_r, face_out, uv_tile=(1.0, 1.0)))
    # A 30 mm sleeve on the barrel, so its faces are 30 mm rings - but
    # capped they were 3.28 m discs, and the hazard band is the LAST wall
    # before the muzzle.
    made.append(oriented_cylinder(
        "tube_muzzle_band", m[f"{MOD_ID}_hazard"], at(spec.TUBE_S1 - 2.4),
        at(spec.TUBE_S1 - 1.4), spec.TUBE_WALL_R + 0.03, vertices=40,
        uv_tile=(1.2, 0.9), cap=False))
    for face, (face_s, face_out) in enumerate(
            ((spec.TUBE_S1 - 2.4, aft), (spec.TUBE_S1 - 1.4, fore))):
        made.append(tube_ring(
            f"tube_muzzle_band_face_{face}", m[f"{MOD_ID}_hazard"], at,
            face_s, spec.TUBE_WALL_R, spec.TUBE_WALL_R + 0.03, face_out,
            uv_tile=(1.2, 0.9)))
    for index in range(3):
        station = spec.TUBE_S1 - 3.6 - index * 6.0
        made.append(oriented_box(
            f"tube_beacon_{index}", m[f"{MOD_ID}_cap_amber"],
            at(station, spec.TUBE_WALL_R + 0.10), lateral, normal, axis,
            0.16, 0.13, 0.16, uv_tile=(0.3, 0.3)))
    return made


def build_muzzle_hatch(m) -> list:
    tilt = spec.TILT_REF_DEG
    axis = Vector(spec.tube_axis(tilt))
    normal = Vector(spec.tube_radial(tilt))
    lateral = Vector((1.0, 0.0, 0.0))
    hinge = Vector(spec.MUZZLE_PIVOT)
    centre = hinge - normal * spec.TUBE_WALL_R + axis * 0.30
    made = [
        oriented_cylinder(
            "muzzle_lid", m[f"{MOD_ID}_lid_plate"],
            tuple(centre - axis * 0.12), tuple(centre + axis * 0.12),
            spec.TUBE_RIB_R + 0.50, vertices=40, uv_tile=(1.4, 1.4)),
        oriented_cylinder(
            "muzzle_lid_seal", m[f"{MOD_ID}_seal_rubber"],
            tuple(centre - axis * 0.16), tuple(centre - axis * 0.12),
            spec.TUBE_RIB_R + 0.20, vertices=40, uv_tile=(0.5, 0.5)),
        oriented_box(
            "muzzle_lid_rib", m[f"{MOD_ID}_tube_band"],
            tuple(centre + axis * 0.20), lateral, normal, axis,
            spec.TUBE_RIB_R + 0.30, 0.18, 0.10, uv_tile=(0.6, 0.6)),
        oriented_cylinder(
            "muzzle_hinge", m[f"{MOD_ID}_tube_band"],
            tuple(hinge - lateral * 0.55), tuple(hinge + lateral * 0.55),
            0.16, vertices=14, uv_tile=(0.4, 0.4)),
    ]
    return made


def build_deck(m) -> list:
    """Retracting load deck: a slab with two slots for the cradle beams.

    The slots are why the cradle can be flush with the driving surface
    without a 3 m hole in the middle of the lane: they sit at +/-1.95 m,
    outside every stock car's wheel track, and the cradle's side beams live
    in them.
    """

    made: list = []
    top = spec.DECK_Z
    bottom = top - spec.DECK_THICK
    slot_half = 0.30
    lanes = [
        (-spec.DECK_HALF_X, -1.95 - slot_half),
        (-1.95 + slot_half, 1.95 - slot_half),
        (1.95 + slot_half, spec.DECK_HALF_X),
    ]
    stations = [spec.DECK_Y0, -8.0, -4.0, -spec.CRADLE_HALF_Y - 0.2,
                spec.CRADLE_HALF_Y + 0.2, 4.4, spec.DECK_Y1]
    for index, (x0, x1) in enumerate(lanes):
        made.append(grid_surface(
            f"deck_top_{index}", m[f"{MOD_ID}_deck_plate"],
            [[(x, y, top) for y in stations] for x in (x0, (x0 + x1) * 0.5, x1)],
            uv_rows=[0.0, (x1 - x0) * 0.5 / 2.5, (x1 - x0) / 2.5],
            uv_cols=[(y - spec.DECK_Y0) / 2.5 for y in stations],
            outward=(0.0, 0.0, 1.0)))
        made.append(grid_surface(
            f"deck_bottom_{index}", m[f"{MOD_ID}_deck_plate"],
            [[(x, y, bottom) for y in stations] for x in (x0, x1)],
            uv_rows=[0.0, (x1 - x0) / 2.5],
            uv_cols=[(y - spec.DECK_Y0) / 2.5 for y in stations],
            outward=(0.0, 0.0, -1.0)))
        for edge_x in (x0, x1):
            made.append(grid_surface(
                f"deck_edge_{index}_{edge_x:.2f}", m[f"{MOD_ID}_cradle_steel"],
                [[(edge_x, y, top) for y in stations],
                 [(edge_x, y, bottom) for y in stations]],
                uv_rows=[0.0, spec.DECK_THICK / 1.5],
                uv_cols=[(y - spec.DECK_Y0) / 1.5 for y in stations],
                outward=(1.0 if edge_x == x1 else -1.0, 0.0, 0.0)))
    for y in (spec.DECK_Y0, spec.DECK_Y1):
        made.append(oriented_box(
            f"deck_end_{y:.0f}", m[f"{MOD_ID}_hazard"],
            (0.0, y, top - spec.DECK_THICK * 0.5), (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), spec.DECK_HALF_X, 0.10,
            spec.DECK_THICK * 0.5, uv_tile=(1.4, 0.6)))
    # End-of-deck guard: the thing that stops a car going into the sump.
    # See the tombstone on PAYLOAD_STOP_Y in spec.py - it is a guard, NOT a
    # parking stop, and nothing may be left resting against it. Part of the
    # DECK, so it sinks with the floor and never fouls the tether.
    stop_y0 = spec.PAYLOAD_STOP_Y
    stop_y1 = stop_y0 + spec.PAYLOAD_STOP_DEPTH
    made.append(oriented_box(
        "deck_stop", m[f"{MOD_ID}_hazard"],
        (0.0, (stop_y0 + stop_y1) * 0.5, top + spec.PAYLOAD_STOP_H * 0.5),
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        spec.PAYLOAD_STOP_HALF_X, spec.PAYLOAD_STOP_DEPTH * 0.5,
        spec.PAYLOAD_STOP_H * 0.5, uv_tile=(1.2, 0.5)))
    # Rubber facing on the side the car arrives from.
    made.append(oriented_box(
        "deck_stop_face", m[f"{MOD_ID}_seal_rubber"],
        (0.0, stop_y0 - 0.05, top + spec.PAYLOAD_STOP_H * 0.5),
        (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
        spec.PAYLOAD_STOP_HALF_X - 0.06, 0.05,
        spec.PAYLOAD_STOP_H * 0.5 - 0.06, uv_tile=(0.6, 0.6)))
    # Scissor legs, so a deck that has sunk 3.6 m still reads as machinery.
    for sign_x in (-1.0, 1.0):
        for y in (-8.6, -1.0, 5.6):
            made.append(oriented_box(
                f"deck_leg_{'p' if sign_x > 0 else 'n'}_{y:.0f}",
                m[f"{MOD_ID}_pipe_steel"],
                (sign_x * 2.85, y, bottom - 0.75), (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 0.16, 0.16, 0.75,
                uv_tile=(0.5, 0.5)))
    return made


def build_door(m) -> list:
    """Guillotine blast door, authored RAISED (open)."""

    half_x = spec.TUNNEL_HALF_X + 0.5
    closed_z0 = spec.DECK_Z - 0.1
    closed_z1 = closed_z0 + 6.0
    lift = spec.DOOR_TRAVEL
    y = spec.TUNNEL_Y_OUT - 0.35
    made = [
        oriented_box("door_slab", m[f"{MOD_ID}_lid_plate"],
                     (0.0, y, (closed_z0 + closed_z1) * 0.5 + lift),
                     (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
                     half_x, 0.42, (closed_z1 - closed_z0) * 0.5,
                     uv_tile=(2.0, 2.0)),
        oriented_box("door_seal", m[f"{MOD_ID}_seal_rubber"],
                     (0.0, y - 0.44, (closed_z0 + closed_z1) * 0.5 + lift),
                     (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
                     half_x - 0.05, 0.05, (closed_z1 - closed_z0) * 0.5 - 0.05,
                     uv_tile=(0.6, 0.6)),
    ]
    for index in range(5):
        z = closed_z0 + 0.6 + index * 1.2 + lift
        made.append(oriented_box(
            f"door_rib_{index}", m[f"{MOD_ID}_rib_steel"], (0.0, y + 0.48, z),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), half_x - 0.12,
            0.10, 0.20, uv_tile=(0.8, 0.8)))
    for sign in (-1.0, 1.0):
        made.append(oriented_box(
            f"door_stripe_{'p' if sign > 0 else 'n'}", m[f"{MOD_ID}_hazard"],
            (sign * (half_x - 0.42), y - 0.44,
             (closed_z0 + closed_z1) * 0.5 + lift),
            (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 0.40, 0.04,
            (closed_z1 - closed_z0) * 0.5 - 0.10, uv_tile=(0.8, 1.6)))
        made.append(oriented_cylinder(
            f"door_rod_{'p' if sign > 0 else 'n'}", m[f"{MOD_ID}_pipe_steel"],
            (sign * (half_x - 0.30), y + 0.20, closed_z1 + lift),
            (sign * (half_x - 0.30), y + 0.20, closed_z1 + lift + 2.6),
            0.13, vertices=12, uv_tile=(0.5, 0.5)))
    return made


def build_pump_rotor(m, side: str) -> list:
    x, y = spec.PUMP_POSITIONS[0 if side == "l" else 1]
    z = spec.PLINTH_TOP + 2.3
    made = [
        oriented_cylinder(
            f"pump_hub_{side}", m[f"{MOD_ID}_pipe_steel"],
            (x, y + 3.30, z), (x, y + 3.55, z), 0.30, vertices=16,
            uv_tile=(0.4, 0.4)),
    ]
    for index in range(9):
        angle = 2.0 * math.pi * index / 9.0
        blade = (x + math.cos(angle) * spec.PUMP_ROTOR_R * 0.6,
                 y + 3.45,
                 z + math.sin(angle) * spec.PUMP_ROTOR_R * 0.6)
        made.append(oriented_box(
            f"pump_blade_{side}_{index}", m[f"{MOD_ID}_tube_band"], blade,
            (math.cos(angle), 0.0, math.sin(angle)), (0.0, 1.0, 0.0),
            (-math.sin(angle), 0.0, math.cos(angle)),
            spec.PUMP_ROTOR_R * 0.55, 0.10, 0.13, uv_tile=(0.3, 0.3)))
    return made


def build_beacon(m) -> list:
    bx, by, bz = spec.BEACON_PIVOT
    made = [
        oriented_cylinder("beacon_stem", m[f"{MOD_ID}_pipe_steel"],
                          (bx, by, bz - 0.55), (bx, by, bz), 0.16,
                          vertices=12, uv_tile=(0.4, 0.4)),
        oriented_cylinder("beacon_head", m[f"{MOD_ID}_beacon_lens"],
                          (bx, by, bz), (bx, by, bz + 0.42), 0.36,
                          vertices=20, uv_tile=(0.5, 0.5)),
        oriented_cylinder("beacon_cap", m[f"{MOD_ID}_rib_steel"],
                          (bx, by, bz + 0.42), (bx, by, bz + 0.56), 0.40,
                          radius_end=0.22, vertices=20, uv_tile=(0.4, 0.4)),
    ]
    for sign in (-1.0, 1.0):
        made.append(oriented_box(
            f"beacon_reflector_{'p' if sign > 0 else 'n'}",
            m[f"{MOD_ID}_lamp_lens"],
            (bx, by + sign * 0.30, bz + 0.21), (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 0.14, 0.06, 0.16,
            uv_tile=(0.3, 0.3)))
    return made


def build_needle(m, tag: str) -> list:
    """One gauge pointer, authored at ITS OWN REST READING.

    Both needles used to be authored pointing +Z with no rotation, and +Z
    is gauge_angle_deg(0.5) - so a machine standing on the apron showed
    100 m/s exit velocity and 50 kPa chamber pressure. The rest readings
    are not the same for the two dials and that is the whole point: no
    tether speed and a chamber full of air puts the velocity needle on its
    zero peg and the vacuum needle on its 100 kPa peg, the two ENDS of the
    sweep. poseMachine subtracts B.needle_rest_*_deg to compensate.

    Rotation about +Y carries +Z to (sin phi, 0, cos phi) and +X to
    (cos phi, 0, -sin phi) - the same frame spec._dial_scale lays the
    numerals out in, so blade, numerals and ticks cannot disagree.

    THE BLADE IS A THREE-SECTION LOFT, NOT A BOX, and the taper is the whole
    point: see the NEEDLE_TIP_HALF_W derivation in spec.py. A constant-width
    blade is 18.4 mm on this dial against numeral strokes of 9-11 mm, so at
    rest it obliterated the numeral it was pointing at. Sections at
    -NEEDLE_TAIL_R (counterweight), 0 (the hub, widest) and +NEEDLE_TIP_R,
    so the width at DIAL_NUMERAL_R is exactly one numeral stroke.
    """

    pivot = spec.GAUGE_VEL_PIVOT if tag == "vel" else spec.GAUGE_VAC_PIVOT
    phi = math.radians(spec.NEEDLE_REST_DEG[tag])
    along = Vector((math.sin(phi), 0.0, math.cos(phi)))
    across = Vector((math.cos(phi), 0.0, -math.sin(phi)))
    face_y = Vector((0.0, 1.0, 0.0))
    root = Vector((pivot[0], pivot[1] - 0.043, pivot[2]))

    def section(radius, half_w):
        centre = root + along * radius
        # Wound consistently in the (across, y) plane; loft's own handedness
        # scan then decides which way the side faces point.
        return [tuple(centre + across * (sign_u * half_w) + face_y * (sign_v * 0.006))
                for sign_u, sign_v in ((-1.0, -1.0), (1.0, -1.0),
                                       (1.0, 1.0), (-1.0, 1.0))]

    return [
        loft(
            f"needle_{tag}", m[f"{MOD_ID}_needle"],
            [section(-spec.NEEDLE_TAIL_R, spec.NEEDLE_TAIL_HALF_W),
             section(0.0, spec.NEEDLE_HALF_W),
             section(spec.NEEDLE_TIP_R, spec.NEEDLE_TIP_HALF_W)],
            uv_tile=(0.2, 0.2)),
        oriented_cylinder(
            f"needle_hub_{tag}", m[f"{MOD_ID}_tube_band"],
            (pivot[0], pivot[1] - 0.035, pivot[2]),
            (pivot[0], pivot[1] - 0.053, pivot[2]), spec.NEEDLE_HUB_R,
            vertices=14, uv_tile=(0.2, 0.2)),
    ]


# The exact translation poseMachine uses to hide a segment. Read from
# BEHAVIOR rather than re-typed: author and runtime differing by even a
# millimetre leaves an "unlit" block sticking through the plate.
BEHAVIOR_BAR_HIDDEN_DY = spec.BEHAVIOR["bar_hidden_dy"]


def build_bar_segment(m, gauge: str, index: int) -> list:
    """One lit block. Authored AT THE NOMINAL SETPOINT, not full scale.

    The runtime hides a segment by translating it +bar_hidden_dy into the
    opaque cabinet, so authoring all eight proud gave a static console that
    read 8/8 - 182 m/s and 72 degrees - directly above its own ladder print
    saying NOM 82 M/S and NOM 50 DEG. Authoring the above-nominal blocks
    already translated makes the authored pose identical to the runtime's
    idle pose (`b.powerIndex or B.power_nom_index`), so the print and the
    hardware agree before a frame of Lua has run. Same defect as the two
    needles authored at mid-scale, in another costume.
    """

    x = spec.BAR_SEG_X[index - 1]
    z = spec.BAR_SEG_Z[gauge]
    nominal = (spec.POWER_NOM_INDEX if gauge == "pwr"
               else spec.TILT_NOM_INDEX)
    dy = 0.0 if index <= nominal else BEHAVIOR_BAR_HIDDEN_DY
    return [oriented_box(
        f"{gauge}_seg{index}", m[f"{MOD_ID}_bar_lit"],
        (x, spec.CONSOLE_FACE_Y - 0.035 + dy, z),
        (1.0, 0.0, 0.0), (0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0), 0.060, 0.046, 0.030, uv_tile=(0.2, 0.2))]


def build_parts(m) -> dict[str, dict[str, object]]:
    parts: dict[str, dict[str, object]] = {
        "tether": {"objects": build_tether(m), "pivot": spec.HUB},
        "clamp_l": {"objects": build_clamp(m, "l"), "pivot": spec.CLAMP_PIVOT_L},
        "clamp_r": {"objects": build_clamp(m, "r"), "pivot": spec.CLAMP_PIVOT_R},
        "tube": {"objects": build_tube(m), "pivot": spec.HUB},
        "muzzle": {"objects": build_muzzle_hatch(m), "pivot": spec.MUZZLE_PIVOT},
        "deck": {
            "objects": build_deck(m),
            "pivot": (0.0, 0.0, spec.DECK_Z),
            "collision": True,
        },
        "door": {
            "objects": build_door(m),
            "pivot": (0.0, spec.TUNNEL_Y_OUT - 0.35, spec.DECK_Z),
            "collision": True,
        },
        "beacon": {"objects": build_beacon(m), "pivot": spec.BEACON_PIVOT},
        "needle_vel": {"objects": build_needle(m, "vel"),
                       "pivot": spec.GAUGE_VEL_PIVOT},
        "needle_vac": {"objects": build_needle(m, "vac"),
                       "pivot": spec.GAUGE_VAC_PIVOT},
    }
    for side, position in (("l", 0), ("r", 1)):
        x, y = spec.PUMP_POSITIONS[position]
        parts[f"pump_rotor_{side}"] = {
            "objects": build_pump_rotor(m, side),
            "pivot": (x, y + 3.45, spec.PLINTH_TOP + 2.3),
        }
    for gauge in ("pwr", "tilt"):
        for index in range(1, 9):
            parts[f"{gauge}_seg{index}"] = {
                "objects": build_bar_segment(m, gauge, index),
                "pivot": (spec.BAR_SEG_X[index - 1], spec.CONSOLE_FACE_Y,
                          spec.BAR_SEG_Z[gauge]),
            }
    return parts


# ---------------------------------------------------------------------------
# Physics cage.
# ---------------------------------------------------------------------------
def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    spine: list[str] = []

    # --- chamber interior ------------------------------------------------
    # The bore is what catches anything the field is not holding: an aborted
    # payload, debris, a purge that clips a jamb. Collision is omitted over
    # the slot and the tunnel so a launched car leaves through the opening
    # rather than into an invisible wall. CAGE_TUNNEL_DEG, not TUNNEL_DEG:
    # this ring is inset 5 cm inside the liner, which on the bottom of the
    # circle puts it HIGHER than the liner at the same angle - see the
    # tombstone on CAGE_TUNNEL_DEG in spec.py.
    bore_arcs = arcs_excluding(spec.SLOT_DEG, spec.CAGE_TUNNEL_DEG)
    bore_columns: list[list[str]] = []
    for arc_index, (start, end) in enumerate(bore_arcs):
        steps = max(2, int(round((end - start) / 7.5)))
        columns: list[list[str]] = []
        for step in range(steps + 1):
            theta = start + (end - start) * step / steps
            column = []
            for x_index, x in enumerate((-spec.HALF_X, 0.0, spec.HALF_X)):
                column.append(cage.add_node(
                    f"bore_{arc_index}_{step:02d}_{x_index}",
                    ring(theta, spec.CAGE_BORE_R, x),
                    fixed=True, collision=True, weight=90.0))
            columns.append(column)
        for step in range(steps + 1):
            for x_index in range(3):
                if x_index:
                    cage.add_beam(columns[step][x_index - 1],
                                  columns[step][x_index])
                if step:
                    cage.add_beam(columns[step - 1][x_index],
                                  columns[step][x_index])
                    if x_index:
                        cage.add_beam(columns[step - 1][x_index - 1],
                                      columns[step][x_index])
        for step in range(steps):
            for x_index in range(2):
                cage.add_quad_both([
                    columns[step][x_index], columns[step + 1][x_index],
                    columns[step + 1][x_index + 1], columns[step][x_index + 1],
                ])
        bore_columns.append(columns)
        spine.append(columns[0][1])
        spine.append(columns[-1][1])

    # Lid interiors, coarse: they only have to stop a tumbling wreck from
    # leaving sideways.
    lid_rings: dict[tuple[float, float], str] = {}
    for sign in (-1.0, 1.0):
        x = sign * (spec.HALF_X - 0.05)
        previous: list[str] | None = None
        first: list[str] | None = None
        for step in range(24):
            theta = step * 360.0 / 24.0
            column = []
            for radius in (spec.HUB_HOUSING_R + 0.4, 11.0, spec.CHAMBER_R - 0.2):
                node = cage.add_node(
                    f"lid_{'p' if sign > 0 else 'n'}_{step:02d}_{radius:.0f}",
                    ring(theta, radius, x), fixed=True, collision=True,
                    weight=70.0)
                column.append(node)
                lid_rings[(sign, theta, radius)] = node
            for index in range(1, 3):
                cage.add_beam(column[index - 1], column[index])
            if previous is not None:
                for index in range(3):
                    cage.add_beam(previous[index], column[index])
                for index in range(2):
                    cage.add_quad_both([
                        previous[index], column[index],
                        column[index + 1], previous[index + 1],
                    ])
            else:
                first = column
            previous = column
        if previous is not None and first is not None:
            for index in range(3):
                cage.add_beam(previous[index], first[index])
            for index in range(2):
                cage.add_quad_both([
                    previous[index], first[index],
                    first[index + 1], previous[index + 1],
                ])
            spine.append(first[0])

    # Hub boss: a short axial spine that ties both lids together.
    hub_nodes = []
    for index, x in enumerate((-spec.HALF_X, 0.0, spec.HALF_X)):
        hub_nodes.append(cage.add_node(
            f"hub_{index}", (x, 0.0, spec.HUB_Z), fixed=True, collision=True,
            weight=180.0))
    for index in range(1, 3):
        cage.add_beam(hub_nodes[index - 1], hub_nodes[index])
    for sign in (-1.0, 1.0):
        for step in range(0, 24, 4):
            theta = step * 360.0 / 24.0
            cage.add_beam(
                hub_nodes[1],
                lid_rings[(sign, theta, spec.HUB_HOUSING_R + 0.4)])
    spine.append(hub_nodes[1])

    # --- plinth ----------------------------------------------------------
    plinth = cage.add_box_lattice(
        "plinth", (-13.5, -16.5, spec.PLINTH_BOTTOM),
        (13.5, 16.5, spec.PLINTH_TOP), subdivisions=(3, 4, 1),
        fixed=True, weight=220.0,
        collision_faces=("top", "east", "west", "north", "south"),
        face_ground_models={"top": "concrete"})
    for step in range(0, 24, 3):
        theta = step * 360.0 / 24.0
        for sign in (-1.0, 1.0):
            cage.add_beam(lid_rings[(sign, theta, spec.CHAMBER_R - 0.2)],
                          plinth[(1, 2, 1)])
    for columns in bore_columns:
        for column in columns[::4]:
            cage.add_beam(column[1], plinth[(1, 2, 1)])
    spine.append(plinth[(1, 2, 1)])

    # --- approach ramp, apron and tunnel floor ---------------------------
    #
    # ONE surface, from the ramp foot all the way to where the retracting
    # deck takes over. The first cut built the ramp and the tunnel floor as
    # separate grids and they OVERLAPPED by 5 m of coplanar collision at
    # z = 3.0 - which is the twin-tiling trap from add_quad_both's docstring
    # in its worst form: two independently triangulated surfaces at the same
    # height, each carrying its own contact state, right where every car
    # that uses this machine drives. Lanes 1 and 5 sit at +/-3.4 so the
    # tunnel's wall nodes have floor to stand on.
    ramp_grid: dict[tuple[int, int], str] = {}
    # 16 spans, not 8: this is COLLISION on the surface every car that uses
    # the machine drives up, and the run doubled with the re-datum. Left at
    # 8 the node pitch would go 3.0 -> 6.0 m and the ramp would be paved in
    # 6 m triangles. 48 / 16 = 3.0 m, exactly as authored.
    ramp_stations = [spec.RAMP_Y0 + (spec.APRON_Y0 - spec.RAMP_Y0) * k / 16.0
                     for k in range(17)]
    ramp_stations += [-25.6, -22.0, -19.4, -16.6, -13.8, spec.TUNNEL_Y_IN]
    ramp_lanes = (-4.5, -3.4, -1.7, 0.0, 1.7, 3.4, 4.5)
    for iy, y in enumerate(ramp_stations):
        for ix, x in enumerate(ramp_lanes):
            ramp_grid[(ix, iy)] = cage.add_node(
                f"ramp_{ix}_{iy}", (x, y, ramp_z(y)), fixed=True,
                collision=True, weight=110.0, friction=1.0)
    for iy in range(len(ramp_stations)):
        for ix in range(len(ramp_lanes)):
            if ix:
                cage.add_beam(ramp_grid[(ix - 1, iy)], ramp_grid[(ix, iy)])
            if iy:
                cage.add_beam(ramp_grid[(ix, iy - 1)], ramp_grid[(ix, iy)])
                if ix:
                    cage.add_beam(ramp_grid[(ix - 1, iy - 1)],
                                  ramp_grid[(ix, iy)])
                    cage.add_beam(ramp_grid[(ix, iy - 1)],
                                  ramp_grid[(ix - 1, iy)])
    for iy in range(len(ramp_stations) - 1):
        for ix in range(len(ramp_lanes) - 1):
            model = "asphalt" if ramp_stations[iy] < -19.4 else "metal"
            cage.add_quad([
                ramp_grid[(ix, iy)], ramp_grid[(ix + 1, iy)],
                ramp_grid[(ix + 1, iy + 1)], ramp_grid[(ix, iy + 1)],
            ], ground_model=model)
    spine.append(ramp_grid[(3, 0)])
    spine.append(ramp_grid[(3, len(ramp_stations) - 1)])

    # Tunnel side walls, so a car that clips a jamb is deflected rather than
    # wedged into the omitted shell arc.
    tunnel_tops: dict[tuple[int, int], str] = {}
    tunnel_range = [iy for iy, y in enumerate(ramp_stations) if y >= -19.4]
    for ix in (1, 5):
        previous = None
        for iy in tunnel_range:
            top = cage.add_node(
                f"tunnel_top_{ix}_{iy}",
                (ramp_lanes[ix], ramp_stations[iy],
                 spec.DECK_Z + spec.TUNNEL_CLEAR_Z),
                fixed=True, collision=True, weight=80.0)
            tunnel_tops[(ix, iy)] = top
            cage.add_beam(top, ramp_grid[(ix, iy)])
            if previous is not None:
                cage.add_beam(top, tunnel_tops[(ix, previous)])
                cage.add_quad_both([
                    ramp_grid[(ix, previous)], ramp_grid[(ix, iy)],
                    top, tunnel_tops[(ix, previous)],
                ])
            previous = iy
    for iy in tunnel_range[::2]:
        cage.add_beam(ramp_grid[(3, iy)], plinth[(1, 1, 1)])

    # Ramp kerbs: low, so they read as a lane edge rather than a wall. The
    # +X run is BROKEN over the console bay to match the visual - a kerb the
    # eye cannot see is exactly the invisible ledge that catches a wheel -
    # and both runs stop at the tunnel mouth, where the jamb takes over.
    for ix, sign in ((0, -1.0), (len(ramp_lanes) - 1, 1.0)):
        previous = None
        for iy, y in enumerate(ramp_stations):
            if y > -19.4 or (sign > 0 and bay_gap(y)):
                previous = None
                continue
            node = cage.add_node(
                f"kerb_{ix}_{iy}",
                (sign * (spec.RAMP_HALF_W + 0.02), y, ramp_z(y) + 0.32),
                fixed=True, collision=True, weight=60.0)
            cage.add_beam(node, ramp_grid[(ix, iy)])
            if previous is not None:
                cage.add_beam(previous, node)
                cage.add_quad_both([
                    ramp_grid[(ix, iy - 1)], ramp_grid[(ix, iy)],
                    node, previous,
                ])
            previous = node

    # --- console bay ------------------------------------------------------
    bay = cage.add_box_lattice(
        "bay", (spec.RAMP_HALF_W, spec.BAY_Y - 3.4, spec.BAY_BOTTOM_Z),
        (11.4, spec.BAY_Y + 3.4, spec.BAY_Z), subdivisions=(2, 2, 1),
        fixed=True, weight=140.0, friction=1.0,
        collision_faces=("top", "east", "south", "north"),
        face_ground_models={"top": "asphalt"})
    for iy in range(len(ramp_stations)):
        if abs(ramp_stations[iy] - spec.BAY_Y) < 4.0:
            cage.add_beam(ramp_grid[(len(ramp_lanes) - 1, iy)], bay[(1, 1, 1)])
    cage.add_beam(bay[(0, 0, 0)], ramp_grid[(len(ramp_lanes) - 1, 0)])

    # --- console cabinet + panel anchors ---------------------------------
    console = cage.add_box_lattice(
        "console",
        (spec.CONSOLE_X - spec.CONSOLE_HALF_X, spec.CONSOLE_FACE_Y + 0.10,
         spec.BAY_Z),
        (spec.CONSOLE_X + spec.CONSOLE_HALF_X,
         spec.CONSOLE_FACE_Y + spec.CONSOLE_DEPTH, spec.CONSOLE_TOP_Z),
        subdivisions=(1, 1, 1), fixed=True, weight=120.0,
        collision_faces=("top", "north", "south", "east", "west"))
    for ix in (0, 1):
        for iy in (0, 1):
            cage.add_beam(console[(ix, iy, 0)], bay[(1, 1, 1)])

    # Panel anchors: 9 cm PROUD of the plate. Anchored flush, the click box
    # sits behind the console's own collision plane and the mouse ray hits
    # the cage first, so hover never fires (centrifuge round 15).
    panel_nodes: list[str] = []
    for button in spec.PANEL_BUTTONS:
        x, y, z = button["position"]
        anchor = (x, y - 0.09, z)
        panel_nodes.append(cage.add_node(
            f"panelbtn_{button['id']}", anchor, fixed=True, collision=False,
            weight=15.0))
        # Per-button orthonormal frame. The trigger box basis is
        # (idX - idRef, idY - idRef), so ONE shared frame pair skews and
        # translates the hitbox of every button not co-located with it.
        for tag, offset in (("fx", (0.4, 0.0, 0.0)), ("fy", (0.0, 0.0, 0.4))):
            panel_nodes.append(cage.add_node(
                f"panel{tag}_{button['id']}",
                (anchor[0] + offset[0], anchor[1] + offset[1],
                 anchor[2] + offset[2]),
                fixed=True, collision=False, weight=15.0))
    panel_nodes.append(cage.add_node(
        "panel_frame_x", spec.PANEL_FRAME_X, fixed=True, collision=False,
        weight=15.0))
    panel_nodes.append(cage.add_node(
        "panel_frame_y", spec.PANEL_FRAME_Y, fixed=True, collision=False,
        weight=15.0))
    for node in panel_nodes:
        cage.add_beam(node, console[(0, 0, 1)])

    # --- service block, masts and pump skids ------------------------------
    bx, by = spec.BUILDING_CENTER
    sx, sy, sz = spec.BUILDING_SIZE
    building = cage.add_box_lattice(
        "building", (bx - sx * 0.5, by - sy * 0.5, spec.GROUND_Z),
        (bx + sx * 0.5, by + sy * 0.5, spec.GROUND_Z + sz),
        subdivisions=(1, 2, 1), fixed=True, weight=160.0,
        collision_faces=("top", "north", "south", "east", "west"))
    cage.add_beam(building[(0, 1, 0)], plinth[(3, 2, 1)])
    cage.add_beam(building[(0, 0, 0)], plinth[(3, 1, 1)])

    for index, (x, y) in enumerate(spec.MAST_POSITIONS):
        foot = cage.add_node(f"mast_foot_{index}", (x, y, spec.GROUND_Z),
                             fixed=True, collision=True, weight=90.0)
        head = cage.add_node(f"mast_head_{index}", (x, y, spec.MAST_HEIGHT),
                             fixed=True, collision=True, weight=40.0)
        cage.add_beam(foot, head)
        cage.add_beam(foot, plinth[(0 if x < 0 else 3, 1 if y < 0 else 3, 0)])

    for index, (x, y) in enumerate(spec.PUMP_POSITIONS):
        skid = cage.add_box_lattice(
            f"pump{index}", (x - 1.7, y - 2.4, spec.PLINTH_TOP),
            (x + 1.7, y + 2.4, spec.PLINTH_TOP + 3.6), subdivisions=(1, 1, 1),
            fixed=True, weight=100.0,
            collision_faces=("top", "north", "south", "east", "west"))
        cage.add_beam(skid[(0, 0, 0)], plinth[(0 if x < 0 else 3,
                                               1 if y < 0 else 2, 1)])

    # --- datum ------------------------------------------------------------
    # The ref node is the SPAWN DATUM and it has to be the LOWEST node in
    # the cage, because BeamNG places by base origin (the lowest node) and
    # then measures origin from the ref. The first cut put the ref at the
    # ramp foot (authored z 0) while the plinth was deliberately "buried" at
    # -3.0, on the theory that the sunk third of the chamber would end up
    # under the terrain. A prop cannot bury anything: the plinth landed on
    # the surface and the ramp foot with it, three metres up, and origin.z
    # read 3.0 for a prop spawned at surface z = 0 (live 2026-08-24). The
    # machine was un-drivable-onto for its whole first life. PLINTH_BOTTOM
    # is GROUND_Z now, so this node is the minimum-z node it always claimed
    # to be - and tests/test_giant_props_pack.py asserts exactly that, for
    # every prop in the pack.
    cage.set_ground_reference(
        (0.0, spec.RAMP_Y0, spec.GROUND_Z),
        (0.0, spec.RAMP_Y0 - 2.4, spec.GROUND_Z),
        left=ramp_grid[(0, 0)],
        up=hub_nodes[1],
        support_nodes=[ramp_grid[(0, 0)], ramp_grid[(4, 0)],
                       ramp_grid[(0, 1)], ramp_grid[(4, 1)]],
    )
    cage.set_spawn_envelope([
        plinth[(0, 0, 0)], plinth[(3, 0, 0)], plinth[(3, 4, 0)],
        plinth[(0, 4, 0)], plinth[(0, 0, 1)], plinth[(3, 0, 1)],
        plinth[(3, 4, 1)], plinth[(0, 4, 1)],
    ])
    cage.auto_base_nodes()
    # One connected graph: everything above hangs off the plinth or the ramp
    # already, and these ties close the last loops.
    for node in spine:
        cage.add_beam(node, plinth[(1, 2, 1)])
    return cage


# blender_kit.render_thumbnail builds its camera with camera_data.lens =
# 32.0. That is the ONE number this solver has to know and cannot read, so it
# is named here rather than buried in an expression; if the shared helper's
# lens ever moves, this is what has to move with it. The resolution is passed
# to both the solver and the render from spec.THUMB_RESOLUTION, so that half
# of the coupling cannot drift at all.
THUMB_LENS_MM = 32.0
THUMB_SENSOR_MM = 36.0


def add_thumbnail_scale_car():
    """RENDER-ONLY scale prop for the selector thumbnail. Never shipped.

    THE THUMBNAIL HAD NO SCALE CUE AND SO HAD NO SIZE. A 43 m disc with a
    33 m barrel photographs exactly like a 4 m bench model when the only
    other objects in frame are its own light masts, and the reviewer's
    reading of the shipped thumbnail was that nothing in it says the machine
    throws CARS. The service walk is the scale cue on the approach FACE (see
    WALK_Z in spec.py) and it works there, at 20 m up - but the thumbnail is
    a 500 x 281 tile seen at a glance, and at that size a handrail is three
    pixels.

    A previous round concluded no car mesh was available. That was wrong:
    cannon_car_wash ships one, 344 verts, 0.200 x 0.095 x 0.048 m, so x22
    is a 4.40 m car - and its own paint material is (1.00, 0.22, 0.03),
    which is the second saturated non-yellow thing in the frame.

    IT IS IMPORTED AFTER EVERY EXPORT AND DELETED AFTER THE RENDER, and both
    halves matter. thumbnail_camera() measures every MESH object's bounding
    corners, export_part_shape and export_flexbody_visual join and reparent
    what they are given, and write_handoff stamps the hashes of what came
    out. Calling this before any of them would put a Mini in the shipped
    visual DAE, in the zip and in the release lock. main() calls it as the
    LAST statement before render_thumbnail and asserts the scene is restored
    afterwards; tests/test_spin_launch_geometry.py asserts no shipped
    artefact mentions it.
    """

    source = PACK_ROOT.parent / "cannon_car_wash" / "mod" / "vehicles" \
        / "ericrolph_cannon_car_wash" / "mini_car.dae"
    if not source.is_file():
        print(f"THUMBNAIL scale car missing at {source}; rendering without it")
        return []
    before = {obj.name for obj in bpy.data.objects}
    bpy.ops.wm.collada_import(filepath=str(source))
    imported = [obj for obj in bpy.data.objects if obj.name not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if not meshes:
        for obj in imported:
            bpy.data.objects.remove(obj, do_unlink=True)
        return []

    # Measure what arrived rather than trusting the 0.200 x 0.095 x 0.048
    # note above: an importer that changed its axis convention would
    # otherwise silently ship a car lying on its side.
    corners = [obj.matrix_world @ Vector(corner)
               for obj in meshes for corner in obj.bound_box]
    low = Vector((min(p.x for p in corners), min(p.y for p in corners),
                  min(p.z for p in corners)))
    high = Vector((max(p.x for p in corners), max(p.y for p in corners),
                   max(p.z for p in corners)))
    size = high - low
    scale = spec.THUMB_CAR_LENGTH_M / max(size.x, size.y)
    # Nose toward +Y, which is the drive direction: the car reads as ABOUT
    # to be launched rather than as parked scenery. The mesh's long axis is
    # x on import, so a quarter turn about z puts it down the ramp.
    turn = size.x > size.y
    centre = (low + high) * 0.5
    target = Vector(spec.THUMB_CAR_POSITION)
    for obj in imported:
        if obj.parent is None:
            obj.location = obj.location - centre
    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported:
        obj.select_set(True)
    root = bpy.data.objects.new("thumb_scale_car_root", None)
    bpy.context.collection.objects.link(root)
    for obj in imported:
        if obj.parent is None:
            obj.parent = root
            obj.matrix_parent_inverse.identity()
    root.location = target + Vector((0.0, 0.0, size.z * scale * 0.5))
    root.scale = (scale, scale, scale)
    # ZYX, and the order is the whole point: yaw has to happen FIRST so the
    # pitch is applied about the car's LATERAL axis. In Blender's default XYZ
    # order the x rotation is applied before the yaw, so it would land on the
    # mesh's long axis and roll the car onto its side instead of tipping its
    # nose up. The pitch itself is the ramp's own grade - the car stands on a
    # 12.5 percent slope now, and a 4.40 m body laid flat on it buries its
    # nose 0.27 m in the asphalt (see THUMB_CAR_POSITION).
    root.rotation_mode = "ZYX"
    root.rotation_euler = (math.radians(spec.THUMB_CAR_PITCH_DEG), 0.0,
                           math.radians(90.0) if turn else 0.0)
    bpy.context.view_layer.update()
    print(f"THUMBNAIL scale car x{scale:.1f} at {tuple(root.location)} "
          f"({len(meshes)} meshes)")
    return [*imported, root]


def thumbnail_camera():
    """Solve the smallest standoff that frames the whole machine.

    Returns ``(camera_location, look_at)`` for bk.render_thumbnail.

    The test is run against every mesh object's eight world-space bounding
    corners, which is the same set the render will draw, so "in frame" here
    means in frame there. Bisection on the standoff rather than a closed form
    because the frustum test is cheap and a closed form would have to assume
    the machine is a sphere - it is a 58 m tall disc with a 33 m barrel out
    of one side and a 48 m ramp out of the other, and a bounding sphere on
    that wastes most of the frame.

    Called BEFORE the DAE exports, deliberately: the exporters join and
    reparent objects, and a camera solved off the post-export scene would be
    solved off a different object set than the one measured here.
    """

    lens = THUMB_LENS_MM
    half_sensor = THUMB_SENSOR_MM * 0.5
    width, height = spec.THUMB_RESOLUTION
    half_u = half_sensor / lens
    half_v = (half_sensor / (width / height)) / lens

    corners = [obj.matrix_world @ Vector(corner)
               for obj in bpy.data.objects if obj.type == "MESH"
               for corner in obj.bound_box]
    corners = [point for point in corners if point.y > spec.THUMB_Y_CUT]
    look = Vector((sum(p.x for p in corners) / len(corners),
                   sum(p.y for p in corners) / len(corners),
                   sum(p.z for p in corners) / len(corners)))

    azimuth = math.radians(spec.THUMB_AZIMUTH_DEG)
    elevation = math.radians(spec.THUMB_ELEVATION_DEG)
    offset = Vector((-math.sin(azimuth) * math.cos(elevation),
                     -math.cos(azimuth) * math.cos(elevation),
                     math.sin(elevation)))
    forward = -offset.normalized()
    right = forward.cross(Vector((0.0, 0.0, 1.0))).normalized()
    up = right.cross(forward).normalized()

    def frames(distance):
        camera = look - forward * distance
        for point in corners:
            delta = point - camera
            depth = delta.dot(forward)
            if depth <= 0.2:
                return False
            if abs(delta.dot(right) / depth) > half_u / spec.THUMB_MARGIN:
                return False
            if abs(delta.dot(up) / depth) > half_v / spec.THUMB_MARGIN:
                return False
        return True

    low, high = 5.0, 1000.0
    if not frames(high):
        raise ValueError("no standoff frames the machine at this lens")
    for _ in range(52):
        middle = (low + high) * 0.5
        if frames(middle):
            high = middle
        else:
            low = middle
    return tuple(look - forward * high), tuple(look)


def main() -> None:
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)
    part_builds = build_parts(materials)
    thumb_camera, thumb_look = thumbnail_camera()

    parts = []
    for name, build in sorted(part_builds.items()):
        dae_path = VEHICLE_DIR / f"{MOD_ID}_{name}.dae"
        info = bk.export_part_shape(
            MOD_ID, name, dae_path, build["objects"], build["pivot"])
        info["path"] = f"vehicles/{MOD_ID}/{MOD_ID}_{name}.dae"
        if build.get("collision"):
            info["collision"] = True
        parts.append(info)

    visual = bk.export_flexbody_visual(
        MOD_ID, VEHICLE_DIR / f"{MOD_ID}.dae", visual_objects,
        f"{MOD_ID}_visual")

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
            "button_size": 0.15,
            "buttons": [
                {
                    "id": button["id"],
                    "title": button["title"],
                    "node": f"{MOD_ID}_panelbtn_{button['id']}",
                    "frame_x_node": f"{MOD_ID}_panelfx_{button['id']}",
                    "frame_y_node": f"{MOD_ID}_panelfy_{button['id']}",
                    "size": spec.CAP_SIZES[button.get("cap", "round_white")],
                }
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

    # Selector thumbnail. Direction and light are authorial (see the block on
    # THUMB_AZIMUTH_DEG in spec.py); the standoff is solved off the scene's
    # own bounding corners by thumbnail_camera, so the launch tube cannot go
    # back to being cropped by the top frame edge.
    #
    # THE SCALE CAR GOES IN HERE AND NOWHERE ELSE. Every export above has
    # already run and written its hashes; the handoff is on disk. See
    # add_thumbnail_scale_car's docstring.
    scene_before = {obj.name for obj in bpy.data.objects}
    scale_car = add_thumbnail_scale_car()
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=thumb_camera,
        look_at=thumb_look,
        resolution=spec.THUMB_RESOLUTION,
        sun_direction=spec.THUMB_SUN,
        # See THUMB_WORLD_STRENGTH: the pack's default 1.0 ambient is a 69
        # count pedestal that halves every chroma, and this tile's problem is
        # hue. The sun is raised with it so the lit faces keep their exposure.
        sun_energy=spec.THUMB_SUN_ENERGY,
        world_strength=spec.THUMB_WORLD_STRENGTH,
    )
    for obj in scale_car:
        bpy.data.objects.remove(obj, do_unlink=True)
    assert {obj.name for obj in bpy.data.objects} == scene_before, (
        "the thumbnail scale car did not leave the scene it was borrowed for")
    print(f"THUMBNAIL camera={tuple(round(v, 2) for v in thumb_camera)} "
          f"look={tuple(round(v, 2) for v in thumb_look)}")
    print(f"SPIN_LAUNCH generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
