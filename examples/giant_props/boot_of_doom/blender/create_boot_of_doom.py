"""Deterministic Blender generator for The Boot of Doom.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/boot_of_doom/blender/create_boot_of_doom.py
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

import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

PIVOT = spec.HINGE_PIVOT
PAD_Y = spec.PAD_CENTER_Y


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def add_tapered_pad(name: str, material) -> object:
    """The kick pad as a poured hump: a flat painted plateau whose edges
    roll down to the ground on all four sides along a smoothstep S-curve
    (flat at the top shoulder, flat again where it meets the road) instead
    of squaring off. Rounded-rect rings are bridged plateau-to-ground; the
    base ring sinks slightly below grade so no raw edge shows on uneven
    terrain.
    """

    import bmesh
    import bpy

    hx, hy = spec.PAD_PLATEAU_HALF
    height = spec.PAD_HEIGHT
    skirt = spec.PAD_SKIRT_WIDTH
    corner_r = 0.12
    arc_segments = 8
    ring_params = (0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 1.0)

    def ring_points(u: float) -> list[tuple[float, float, float]]:
        offset = skirt * u
        smooth = u * u * (3.0 - 2.0 * u)
        z = -0.015 if u >= 1.0 else height * (1.0 - smooth)
        radius = corner_r + offset
        points = []
        # Corner arc centers, CCW from +x/+y; each arc sweeps 90 degrees.
        corners = (
            ((hx - corner_r), (hy - corner_r), 0.0),
            (-(hx - corner_r), (hy - corner_r), 90.0),
            (-(hx - corner_r), -(hy - corner_r), 180.0),
            ((hx - corner_r), -(hy - corner_r), 270.0),
        )
        for cx, cy, start_deg in corners:
            for step in range(arc_segments + 1):
                angle = math.radians(start_deg + 90.0 * step / arc_segments)
                points.append(
                    (cx + radius * math.cos(angle), PAD_Y + cy + radius * math.sin(angle), z)
                )
        return points

    bm = bmesh.new()
    rings = []
    for u in ring_params:
        rings.append([bm.verts.new(p) for p in ring_points(u)])
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
    # One-shot 0..1 skin UVs across the whole footprint: the kick_pad
    # texture family bakes the border frame and red X as PAINT (marking
    # geometry on a drivable surface betrays itself — 2026-08-13).
    full_hx = hx + skirt
    full_hy = hy + skirt
    layer = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        x, y, _ = mesh.vertices[loop.vertex_index].co
        layer.data[loop.index].uv = (
            x / (2.0 * full_hx) + 0.5,
            (y - PAD_Y) / (2.0 * full_hy) + 0.5,
        )
    return bk._finish_primitive(obj, name, material, 0.0)


def crisp_edges(obj, width=None):
    """Re-cut proplib's default bevel as ONE 45-degree chamfer.

    _finish_primitive fits a 2-segment bevel, and on a right-angle corner
    those two 30-degree steps both sit under the 38-degree auto-smooth
    angle, so they shade into each other as a soft round. At 10-20 mm that
    turned every arris on the cabinet into a melted blob. One segment lands
    at 45 degrees to both neighbours — above the smoothing angle — so it
    stays a flat, crisp, machined-looking chamfer.
    """

    modifier = obj.modifiers.get("Bevel")
    if modifier is not None:
        modifier.width = spec.EDGE_EASE if width is None else width
        modifier.segments = 1
    return obj


def timber_uvs(obj, grain_axis, meters_per_tile, seam_axis, seam_sign, reverse=False):
    """Continuous-grain UVs for a piece of solid timber.

    Real wood carries its figure CONTINUOUSLY around an arris: the growth
    rings run through the solid, so the pattern on a face and the pattern
    on the adjacent edge meet at the corner. bk.add_metric_box_uvs maps
    every face off its OWN dominant axis, so at the end panel's front arris
    the outer face read u=y/pitch and the edge read u=x/pitch — utterly
    unrelated numbers. The grain restarted at every corner and the panel
    read as separate slabs glued together (player report 2026-08-13, "the
    wood grain doesn't line up from edge to edge").

    Here `u` runs along `grain_axis` (the board's length) and `v` is the
    UNROLLED PERIMETER distance around the cross-section perpendicular to
    it, so v is continuous across all four long faces and the figure wraps
    the arris exactly as sawn timber does. The wrap point, where v returns
    to its origin, is parked in the middle of the face named by
    `seam_axis`/`seam_sign` — which must be a face that is never visible.
    Faces normal to the grain are board ends and get a plain planar map.

    `reverse` picks which way round the cross-section v runs, and it is NOT
    cosmetic. Rotating the grain by swapping which axis feeds u is a MIRROR
    (determinant -1), and a mirrored UV frame flips the bitangent, so the
    tangent-space normal map renders its grain grooves as raised RIDGES —
    the cap came out looking wet-varnished under a grazing sun. Reversing
    the walk restores a proper rotation. Mirror-image parts (the two end
    panels) therefore need OPPOSITE values to relieve the same way.
    """

    mesh = obj.data
    layer = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    half = [max(abs(vertex.co[i]) for vertex in mesh.vertices) for i in range(3)]
    axis_a, axis_b = [i for i in range(3) if i != grain_axis]
    ha, hb = half[axis_a], half[axis_b]
    perimeter = 4.0 * (ha + hb)

    def arc(normal_axis, sign, ca, cb):
        """Distance counter-clockwise from the corner (a=+ha, b=-hb)."""
        if normal_axis == axis_a and sign > 0:
            return cb + hb
        if normal_axis == axis_b and sign > 0:
            return 2.0 * hb + (ha - ca)
        if normal_axis == axis_a:
            return 2.0 * hb + 2.0 * ha + (hb - cb)
        return 4.0 * hb + 2.0 * ha + (ca + ha)

    seam_ca = seam_sign * half[seam_axis] if seam_axis == axis_a else 0.0
    seam_cb = seam_sign * half[seam_axis] if seam_axis == axis_b else 0.0
    seam_at = arc(seam_axis, seam_sign, seam_ca, seam_cb)

    for polygon in mesh.polygons:
        normal_axis = max(range(3), key=lambda i: abs(polygon.normal[i]))
        sign = 1.0 if polygon.normal[normal_axis] > 0.0 else -1.0
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            if normal_axis == grain_axis:
                uv = (
                    co[axis_a] / meters_per_tile + 0.5,
                    co[axis_b] / meters_per_tile + 0.5,
                )
            else:
                run = arc(normal_axis, sign, co[axis_a], co[axis_b]) - seam_at
                if reverse:
                    run = -run
                uv = (
                    co[grain_axis] / meters_per_tile + 0.5,
                    (run % perimeter) / meters_per_tile,
                )
            layer.data[loop_index].uv = uv

    span = max(perimeter, 2.0 * half[grain_axis])
    if span > meters_per_tile + 1e-6:
        raise ValueError(
            f"{obj.name}: {span:.3f} m of timber will not fit a "
            f"{meters_per_tile:.3f} m tile — the grain would repeat"
        )
    return obj


def back_label_uvs(obj, width, height):
    """0..1 UVs on a plate's BACK (+y) face, un-mirrored.

    Standing behind the console you look along -y, and in a right-handed
    frame that puts authored +x on your LEFT — the exact opposite of the
    fascia, where +x is on your right. So u has to run AGAINST local x here
    or every word comes out backwards. (A 180-degree yaw can never mirror
    text; only the choice of u direction can.)
    """

    mesh = obj.data
    layer = mesh.uv_layers.active or mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        if polygon.normal.y <= 0.5:
            continue
        for loop_index in polygon.loop_indices:
            vx, _vy, vz = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            layer.data[loop_index].uv = (
                (width / 2.0 - vx) / width,
                (vz + height / 2.0) / height,
            )
    return obj


def board_uvs(obj):
    """Shift metric box UVs into a single tile so a panel reads as ONE board.

    bk.add_metric_box_uvs maps straight from local coordinates, which on a
    centred box straddle u=0 and v=0 — so the texture's wrap boundary runs
    right through the middle of every face. On a seamless tile that is
    invisible, but the `wood` family mirrors across it, which put a hard
    cross-shaped seam through the centre of each walnut panel and made a
    solid end panel look like two badly butted veneer offcuts (2026-08-13).
    Shifting the map half a tile lands the whole face inside one tile, so
    any piece whose face is smaller than its tile pitch gets continuous
    grain. The assertion keeps that precondition honest if a size changes.
    """

    layer = obj.data.uv_layers.active
    for loop in layer.data:
        loop.uv = (loop.uv[0] + 0.5, loop.uv[1] + 0.5)
    lo = min(min(loop.uv) for loop in layer.data)
    hi = max(max(loop.uv) for loop in layer.data)
    if lo < -0.001 or hi > 1.001:
        raise ValueError(
            f"{obj.name}: face is larger than its tile pitch "
            f"(uv {lo:.3f}..{hi:.3f}) — it would repeat and seam"
        )
    return obj


def tapered_leg(name, top, foot, r_top, r_foot, material):
    """A tapered splayed leg running from `top` to `foot`.

    `primitive_cone_add` puts radius1 at local -Z and radius2 at local +Z,
    and to_track_quat maps local +Z onto the top->foot direction — so
    radius2 is the FOOT end. Passing the rotation to the primitive (rather
    than setting rotation_euler afterwards) keeps the transform applied
    into the mesh, which is what the flexbody export expects.
    """

    from mathutils import Vector

    a, b = Vector(top), Vector(foot)
    direction = b - a
    return bk.add_cone(
        name,
        tuple((a + b) / 2.0),
        r_top,
        r_foot,
        direction.length,
        material,
        vertices=16,
        rotation=tuple(direction.to_track_quat("Z", "Y").to_euler()),
    )


def strut_between(name, start, end, radius, material):
    """A straight strut between two points (stretchers, braces)."""

    from mathutils import Vector

    a, b = Vector(start), Vector(end)
    direction = b - a
    strut = bk.add_cylinder(
        name, tuple((a + b) / 2.0), radius, direction.length, material, vertices=12
    )
    strut.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return strut


def build_console(materials) -> list:
    """Mid-century kick-control console built as real cabinetry.

    A cream enamel CASE captured between two solid walnut END PANELS, a
    wrap-over walnut cap with a chrome nose, a chrome kick strip closing
    the foot of the fascia well, and an inset steel understructure whose
    bolt plates carry four tapered splayed legs tied by side stretchers.
    Every reveal is a spec constant (see the joinery notes there) so the
    joints register against each other instead of each corner getting its
    own accidental relationship. The moving instruments (amber segments,
    needle) are runtime parts.
    """

    cream = materials[f"{MOD_ID}_console_cream"]
    walnut = materials[f"{MOD_ID}_console_walnut"]
    legend = materials[f"{MOD_ID}_panel_legend"]
    bakelite = materials[f"{MOD_ID}_btn_bakelite"]
    steel = materials[f"{MOD_ID}_steel"]
    data_plate = materials[f"{MOD_ID}_plate_data"]

    # Console faces -y (behind the boot, player request 2026-08-13): the
    # across-the-face axis is authored x, depth is authored y.
    cx, cy = spec.CONSOLE_CX, spec.CONSOLE_CY
    case_h = spec.CASE_Z1 - spec.CASE_Z0
    case_mid_z = (spec.CASE_Z0 + spec.CASE_Z1) / 2.0
    half_w = spec.CASE_W / 2.0 + spec.CHEEK_T       # cabinet silhouette
    front_y = cy - spec.CASE_D / 2.0 - spec.FRAME_PROUD   # frame front plane
    back_y = cy + spec.CASE_D / 2.0                       # frame back (flush)

    objects = []
    # The case. Its front face IS CONSOLE_FACE_Y and never moves — the whole
    # panel layout (plate, sockets, dial, caps, click anchors) is pinned to
    # that plane.
    objects.append(
        board_uvs(
            crisp_edges(
                bk.add_box(
                    f"{MOD_ID}_console_case",
                    (cx, cy, case_mid_z),
                    (spec.CASE_W, spec.CASE_D, case_h),
                    cream,
                    bevel=spec.EDGE_EASE,
                    # Tile pitch wider than the fascia (1.69 x 1.08) so the
                    # enamel's peel wear never repeats across it.
                    metric_uv=(1.8, 1.8),
                )
            )
        )
    )
    # Solid walnut end panels: butt-jointed to the case sides, full case
    # height, flush at the back, standing FRAME_PROUD ahead of the fascia.
    for tag, sx in (("l", -1.0), ("r", 1.0)):
        objects.append(
            # Grain runs VERTICALLY (local z) and wraps the front arris, so
            # the figure carries from the outer face straight onto the
            # 75 mm front edge. The wrap point is parked on the inner face,
            # which is butted against the case and never seen. 1.4 m tile
            # clears the 1.32 m perimeter and the 1.08 m height.
            timber_uvs(
                crisp_edges(
                    bk.add_box(
                        f"{MOD_ID}_console_cheek_{tag}",
                        (
                            cx + sx * (spec.CASE_W / 2.0 + spec.CHEEK_T / 2.0),
                            (front_y + back_y) / 2.0,
                            case_mid_z,
                        ),
                        (spec.CHEEK_T, back_y - front_y, case_h),
                        walnut,
                        bevel=spec.EDGE_EASE,
                    )
                ),
                grain_axis=2,
                meters_per_tile=1.4,
                seam_axis=0,
                seam_sign=-sx,
                # The panels are mirror-image parts, so they need opposite
                # walk directions to relieve the same way.
                reverse=sx > 0,
            )
        )
    # Top cap: overhangs by the SAME lip on all four sides, so no corner
    # can disagree with another.
    cap_front = front_y - spec.CAP_LIP
    cap_back = back_y + spec.CAP_LIP
    cap_w = 2.0 * (half_w + spec.CAP_LIP)
    objects.append(
        # Grain runs along the cabinet (local x) and wraps over the front
        # edge, so the top and its nosing are visibly one board. The wrap
        # point sits on the underside, which rests on the case.
        timber_uvs(
            crisp_edges(
                bk.add_box(
                    f"{MOD_ID}_console_cap",
                    (cx, (cap_front + cap_back) / 2.0, spec.CASE_Z1 + spec.CAP_T / 2.0),
                    (cap_w, cap_back - cap_front, spec.CAP_T),
                    walnut,
                    bevel=spec.EDGE_EASE,
                )
            ),
            grain_axis=0,
            meters_per_tile=2.0,
            seam_axis=2,
            seam_sign=-1.0,
            reverse=True,
        )
    )
    # A chrome kick strip fills the foot of the fascia well. The top of the
    # well is closed by the cap's own underside — an earlier chrome nose
    # across the cap's front face died here: it faced the front edge in
    # metal while the cap's ends stayed wood, so the top corners butted
    # chrome into end grain and read as a tin lid dropped on a wooden box.
    # Metal now means instrument (bezel, knob rings) or understructure;
    # walnut means carcass.
    objects.append(
        crisp_edges(
            bk.add_box(
                f"{MOD_ID}_console_kick_strip",
                (cx, front_y + spec.FRAME_PROUD / 2.0, spec.CASE_Z0 + 0.0125),
                (spec.CASE_W, spec.FRAME_PROUD, 0.025),
                steel,
                bevel=0.003,
            )
        )
    )
    # Back-panel paperwork: one small anodized builder's plate screwed into
    # the bottom corner nearest the viewer's left, where a nameplate
    # actually lives. 3 mm proud because it is a metal plate, not a decal,
    # and carried on four visible corner screws — a plate with no fixings
    # reads as printed-on no matter how good the type is.
    plate_w, plate_h = spec.BACK_PLATE_W, spec.BACK_PLATE_H
    plate_proud = 0.003
    plate_x = spec.CASE_W / 2.0 - spec.BACK_PLATE_MARGIN_X - plate_w / 2.0
    plate_z = spec.CASE_Z0 + spec.BACK_PLATE_MARGIN_Z + plate_h / 2.0
    objects.append(
        back_label_uvs(
            crisp_edges(
                bk.add_box(
                    f"{MOD_ID}_back_plate",
                    (cx + plate_x, back_y + plate_proud / 2.0, plate_z),
                    (plate_w, plate_proud, plate_h),
                    data_plate,
                    bevel=0.0015,
                ),
                width=0.0015,
            ),
            plate_w,
            plate_h,
        )
    )
    screw_inset = spec.BACK_PLATE_SCREW_INSET
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_back_plate_screw_"
                    f"{'l' if sx < 0 else 'r'}{'b' if sz < 0 else 't'}",
                    (
                        cx + plate_x + sx * (plate_w / 2.0 - screw_inset),
                        back_y + plate_proud + 0.002,
                        plate_z + sz * (plate_h / 2.0 - screw_inset),
                    ),
                    spec.BACK_PLATE_SCREW_R,
                    0.004,
                    steel,
                    vertices=12,
                    axis="Y",
                )
            )
    # Understructure: a perimeter rail frame inset on all sides, carrying
    # the case. Rails are inset by half their thickness so the frame's
    # outer surfaces land exactly on the inset planes.
    base_top = spec.CASE_Z0
    base_bot = spec.CASE_Z0 - spec.BASE_RAIL_H
    base_mid_z = (base_top + base_bot) / 2.0
    rail_t = spec.BASE_RAIL_T
    fx = half_w - spec.BASE_INSET
    f_front = front_y + spec.BASE_INSET
    f_back = back_y - spec.BASE_INSET
    for tag, ry in (("front", f_front + rail_t / 2.0), ("back", f_back - rail_t / 2.0)):
        objects.append(
            crisp_edges(
                bk.add_box(
                    f"{MOD_ID}_base_rail_{tag}",
                    (cx, ry, base_mid_z),
                    (2.0 * fx, rail_t, spec.BASE_RAIL_H),
                    steel,
                    bevel=0.004,
                )
            )
        )
    for tag, sx in (("l", -1.0), ("r", 1.0)):
        objects.append(
            crisp_edges(
                bk.add_box(
                    f"{MOD_ID}_base_rail_{tag}",
                    (cx + sx * (fx - rail_t / 2.0), (f_front + f_back) / 2.0, base_mid_z),
                    (rail_t, f_back - f_front, spec.BASE_RAIL_H),
                    steel,
                    bevel=0.004,
                )
            )
        )
    # Legs bolt to visible plates tucked inside the frame corners, and the
    # four feet land exactly under the four corners of the cap — the splay
    # traces the cabinet silhouette instead of picking arbitrary numbers.
    inset = spec.BOLT_PLATE / 2.0
    legs = {}
    for sx in (-1.0, 1.0):
        for tag_y, plate_y, foot_y in (
            ("f", f_front + inset, cap_front),
            ("b", f_back - inset, cap_back),
        ):
            tag = f"{'l' if sx < 0 else 'r'}{tag_y}"
            plate_x = sx * (fx - inset)
            objects.append(
                crisp_edges(
                    bk.add_box(
                        f"{MOD_ID}_leg_plate_{tag}",
                        (cx + plate_x, plate_y, base_bot - 0.006),
                        (spec.BOLT_PLATE, spec.BOLT_PLATE, 0.012),
                        steel,
                        bevel=0.003,
                    )
                )
            )
            top = (cx + plate_x, plate_y, base_bot - 0.012)
            foot = (cx + sx * (half_w + spec.CAP_LIP), foot_y, spec.FOOT_Z)
            legs[tag] = (top, foot)
            objects.append(
                tapered_leg(
                    f"{MOD_ID}_console_leg_{tag}", top, foot, 0.040, 0.026, steel
                )
            )
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_console_foot_{tag}",
                    (foot[0], foot[1], spec.FOOT_Z / 2.0),
                    0.045,
                    spec.FOOT_Z,
                    bakelite,
                    vertices=16,
                )
            )
    # Side stretchers tie each front/back leg pair together, landing exactly
    # on both leg centrelines so the understructure reads as one frame.
    for side in ("l", "r"):
        span = []
        for tag_y in ("f", "b"):
            top, foot = legs[f"{side}{tag_y}"]
            t = 0.58
            span.append(tuple(top[i] + t * (foot[i] - top[i]) for i in range(3)))
        objects.append(
            strut_between(
                f"{MOD_ID}_leg_stretcher_{side}", span[0], span[1], 0.020, steel
            )
        )
    # Legend plate: 12 mm skin whose FRONT (-y) face carries an authored
    # 0..1 UV frame for the panel_legend print. The world mirror puts
    # authored -x on the viewer's LEFT, so u runs WITH local x.
    plate = bk.add_box(
        f"{MOD_ID}_console_legend",
        (cx, spec.PLATE_Y, spec.PLATE_Z0 + spec.PLATE_H / 2.0),
        (spec.PLATE_W, 0.012, spec.PLATE_H),
        legend,
        bevel=0.0,
    )
    pmesh = plate.data
    puv = pmesh.uv_layers.active or pmesh.uv_layers.new(name="UVMap")
    for poly in pmesh.polygons:
        if poly.normal.y < -0.5:
            for li in poly.loop_indices:
                vx, _vy, vz = pmesh.vertices[pmesh.loops[li].vertex_index].co
                puv.data[li].uv = (
                    (vx + spec.PLATE_W / 2.0) / spec.PLATE_W,
                    (vz + spec.PLATE_H / 2.0) / spec.PLATE_H,
                )
    objects.append(plate)
    # Chrome bezel strips framing the plate.
    bezel_y = cy - 0.282
    bz = spec.PLATE_Z0 + spec.PLATE_H / 2.0
    for tag, center, dims in (
        ("top", (cx, bezel_y, spec.PLATE_Z0 + spec.PLATE_H + 0.01),
         (spec.PLATE_W + 0.04, 0.016, 0.02)),
        ("bot", (cx, bezel_y, spec.PLATE_Z0 - 0.01),
         (spec.PLATE_W + 0.04, 0.016, 0.02)),
        ("l", (cx - spec.PLATE_W / 2.0 - 0.01, bezel_y, bz),
         (0.02, 0.016, spec.PLATE_H)),
        ("r", (cx + spec.PLATE_W / 2.0 + 0.01, bezel_y, bz),
         (0.02, 0.016, spec.PLATE_H)),
    ):
        objects.append(
            bk.add_box(f"{MOD_ID}_console_bezel_{tag}", center, dims, steel, bevel=0.004)
        )
    # Power-ladder sockets: static recesses so an unlit level still reads
    # as an empty slot (centrifuge gauge lesson).
    for i in range(10):
        seg_dx = spec.POWER_SEG_DX0 + spec.POWER_SEG_PITCH * i
        objects.append(
            bk.add_box(
                f"{MOD_ID}_pow_socket_{i}",
                (cx + seg_dx, cy - 0.284, spec.POWER_ROW_Z),
                (0.064, 0.008, 0.040),
                steel,
                bevel=0.003,
            )
        )
    # Protractor dial: chrome ticks every 10 degrees from horizontal
    # (authored -x, the viewer's left) to straight up, plus the hub the
    # needle part spins on.
    for k in range(10):
        tick = math.radians(k * 10.0)
        objects.append(
            bk.add_box(
                f"{MOD_ID}_dial_tick_{k}",
                (
                    cx - spec.DIAL_TICK_R * math.cos(tick),
                    cy - 0.287,
                    spec.DIAL_CZ + spec.DIAL_TICK_R * math.sin(tick),
                ),
                (0.045, 0.006, 0.012),
                steel,
                bevel=0.0,
                rotation=(0.0, tick, 0.0),
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_dial_hub",
            (cx, cy - 0.292, spec.DIAL_CZ),
            0.024,
            0.03,
            steel,
            vertices=24,
            axis="Y",
        )
    )
    # Bakelite caps with chrome bezel rings.
    for button in spec.PANEL_BUTTONS:
        bdx, bz2 = button["dx"], button["z"]
        objects.append(
            bk.add_torus(
                f"{MOD_ID}_cap_bezel_{button['id']}",
                (cx + bdx, cy - 0.28, bz2),
                0.06,
                0.009,
                steel,
                rotation=(math.pi / 2.0, 0.0, 0.0),
                major_segments=28,
                minor_segments=8,
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_cap_{button['id']}",
                (cx + bdx, cy - 0.31, bz2),
                0.05,
                0.07,
                bakelite,
                vertices=28,
                axis="Y",
            )
        )
    return objects


def build_visual(materials) -> list:
    steel = materials[f"{MOD_ID}_steel"]
    pad_deck = materials[f"{MOD_ID}_pad_deck"]

    objects = []
    objects.extend(build_console(materials))
    # Kick pad hump: border frame and red X live IN the pad_deck texture.
    objects.append(add_tapered_pad(f"{MOD_ID}_pad", pad_deck))
    # Heel hinge: steel base block and axle.
    # Metric UVs keep the 1024 steel grain at true meter density — without
    # them the map stretched across the 3 m block as soft banding (player
    # report 2026-08-13). Cylinder tile width = own circumference so the
    # wrap is seam-free; visible cylinders need 32+ segments (catapult
    # cylinder law — the 14-vert axle end read as a bolt-head polygon).
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hinge_base",
            (0.0, PIVOT[1], 0.45),
            (3.0, 2.2, 0.9),
            steel,
            bevel=0.08,
            metric_uv=(0.8, 0.8),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_hinge_axle",
            PIVOT,
            0.22,
            3.2,
            steel,
            vertices=40,
            axis="X",
            metric_uv=(2.0 * math.pi * 0.22, 0.7),
        )
    )
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    import bpy
    from mathutils import Matrix

    hero = materials[f"{MOD_ID}_boot_hero"]
    steel = materials[f"{MOD_ID}_steel"]

    # The boot itself is a generated hero mesh checked in as
    # assets/boot_hero.glb (worn brown leather, lugged sole, baked
    # base/normal/roughness maps riding the "external" texture family).
    # Canonical GLB frame: toe +Y, heel -Y, sole resting on z=0. The
    # generator only bakes a fixed scale and placement into the vertices,
    # so rebuilds stay deterministic.
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(EXAMPLE_ROOT / "assets" / "boot_hero.glb"))
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if len(imported) != 1:
        raise RuntimeError(f"expected exactly one boot mesh in GLB, got {len(imported)}")
    boot = imported[0]
    boot.parent = None
    boot.name = f"{MOD_ID}_boot_hero"
    mesh = boot.data
    mesh.transform(boot.matrix_world)
    boot.matrix_world = Matrix.Identity(4)
    # 2.2 m canonical length -> ~7.9 m boot; extra Z stretch keeps the low
    # work-boot shaft reading tall from the road.
    mesh.transform(Matrix.Diagonal((3.6, 3.6, 3.6 * 1.3, 1.0)))
    min_y = min(v.co.y for v in mesh.vertices)
    min_z = min(v.co.z for v in mesh.vertices)
    heel_back_y = PIVOT[1] - 0.35
    mesh.transform(Matrix.Translation((0.0, heel_back_y - min_y, 0.15 - min_z)))
    mesh.update()
    mesh.materials.clear()
    mesh.materials.append(hero)

    objects = [boot]
    # Steel heel collar ties the leather visually into the hinge axle.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_heel_collar",
            PIVOT,
            0.4,
            2.6,
            steel,
            vertices=48,
            axis="X",
            metric_uv=(2.0 * math.pi * 0.4, 0.8),
        )
    )
    parts = {"boot": {"objects": objects, "pivot": PIVOT}}

    # Console instruments: ten power-ladder segments (amber, top three red
    # for the torture zone) and the protractor needle. Runtime pose-swaps
    # an unlit segment +0.12 authored y — back through the plate into the
    # cabinet body (centrifuge bar-graph idiom). Console faces -y behind
    # the boot; the needle rests pointing -x (viewer's left, 0 deg).
    ccx, cy = spec.CONSOLE_CX, spec.CONSOLE_CY
    amber = materials[f"{MOD_ID}_seg_amber"]
    seg_red = materials[f"{MOD_ID}_seg_red"]
    needle_red = materials[f"{MOD_ID}_needle_red"]
    for i in range(1, 11):
        seg_dx = spec.POWER_SEG_DX0 + spec.POWER_SEG_PITCH * (i - 1)
        center = (ccx + seg_dx, cy - 0.298, spec.POWER_ROW_Z)
        parts[f"pow_seg{i}"] = {
            "objects": [
                bk.add_box(
                    f"{MOD_ID}_pow_seg{i}",
                    center,
                    (0.058, 0.02, 0.034),
                    seg_red if i >= 8 else amber,
                    bevel=0.004,
                )
            ],
            "pivot": center,
        }
    hub = (ccx, cy - 0.294, spec.DIAL_CZ)
    needle_objects = [
        bk.add_box(
            f"{MOD_ID}_angle_needle",
            (ccx - spec.NEEDLE_LEN / 2.0, cy - 0.294, spec.DIAL_CZ),
            (spec.NEEDLE_LEN, 0.007, 0.016),
            needle_red,
            bevel=0.0,
        ),
        bk.add_box(
            f"{MOD_ID}_angle_needle_tail",
            (ccx + 0.037, cy - 0.294, spec.DIAL_CZ),
            (0.05, 0.007, 0.022),
            needle_red,
            bevel=0.0,
        ),
    ]
    parts["angle_needle"] = {"objects": needle_objects, "pivot": hub}
    return parts


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    pad = cage.add_box_lattice(
        "pad",
        (-2.1, PAD_Y - 2.3, 0.0),
        (2.1, PAD_Y + 2.3, 0.14),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("top",),
        face_ground_models={"top": "asphalt"},
    )
    hinge = cage.add_box_lattice(
        "hinge",
        (-1.5, PIVOT[1] - 1.1, 0.0),
        (1.5, PIVOT[1] + 1.1, 1.1),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("top", "north", "south", "east", "west"),
    )
    for ix in (0, 1):
        cage.stitch(hinge[(ix, 1, 0)], pad[(ix * 2, 0, 0)])
        cage.stitch(hinge[(ix, 1, 1)], pad[(ix * 2, 0, 1)])
    # Collision skirt matching the tapered visual: fixed base-corner nodes
    # at the skirt footprint, ridden as four sloped trapezoid quads from the
    # plateau top edge down to grade (the S-curve visual deviates from this
    # straight chord by ~1 cm at most).
    hx, hy = spec.PAD_PLATEAU_HALF
    sw = spec.PAD_SKIRT_WIDTH
    skirt = {}
    for corner, sx, sy in (("nw", -1, 1), ("ne", 1, 1), ("se", 1, -1), ("sw", -1, -1)):
        skirt[corner] = cage.add_node(
            f"pad_skirt_{corner}",
            (sx * (hx + sw), PAD_Y + sy * (hy + sw), 0.0),
            fixed=True,
        )
    top = {"nw": pad[(0, 2, 1)], "ne": pad[(2, 2, 1)], "se": pad[(2, 0, 1)], "sw": pad[(0, 0, 1)]}
    bottom = {"nw": pad[(0, 2, 0)], "ne": pad[(2, 2, 0)], "se": pad[(2, 0, 0)], "sw": pad[(0, 0, 0)]}
    for corner in skirt:
        cage.add_beam(skirt[corner], top[corner])
        cage.add_beam(skirt[corner], bottom[corner])
    for a, b in (("nw", "ne"), ("ne", "se"), ("se", "sw"), ("sw", "nw")):
        cage.add_quad_both(
            [skirt[a], skirt[b], top[b], top[a]], ground_model="asphalt"
        )
    # Control console (behind the boot, facing -y): fixed collision box
    # hugging the cabinet. Front face at y ccy-0.26 sits BEHIND the
    # legend plate (ccy-0.287) and caps, so every trigger click box
    # floats in free air in front of the cage (centrifuge round-15 hover
    # lesson). Key semantics keep (depth, across, height) so the beam and
    # quad topology below is unchanged.
    ccx, ccy = spec.CONSOLE_CX, spec.CONSOLE_CY
    console: dict[tuple[int, int, int], str] = {}
    for ix, cyy in ((0, ccy - 0.26), (1, ccy + 0.32)):
        for iy, cxx in ((0, ccx - 0.95), (1, ccx + 0.95)):
            for iz, cz in ((0, 0.0), (1, 1.72)):
                console[(ix, iy, iz)] = cage.add_node(
                    f"console_{ix}_{iy}_{iz}",
                    (cxx, cyy, cz),
                    fixed=True,
                    collision=True,
                    weight=60.0,
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
    cage.add_quad_both(
        [console[(0, 0, 0)], console[(0, 1, 0)], console[(0, 1, 1)], console[(0, 0, 1)]]
    )
    cage.add_quad_both(
        [console[(1, 0, 0)], console[(1, 1, 0)], console[(1, 1, 1)], console[(1, 0, 1)]]
    )
    cage.add_quad_both(
        [console[(0, 0, 0)], console[(1, 0, 0)], console[(1, 0, 1)], console[(0, 0, 1)]]
    )
    cage.add_quad_both(
        [console[(0, 1, 0)], console[(1, 1, 0)], console[(1, 1, 1)], console[(0, 1, 1)]]
    )
    cage.add_quad_both(
        [console[(0, 0, 1)], console[(1, 0, 1)], console[(1, 1, 1)], console[(0, 1, 1)]]
    )
    cage.add_beam(console[(1, 0, 0)], hinge[(0, 0, 0)])
    cage.add_beam(console[(1, 1, 0)], hinge[(1, 0, 0)])

    # Panel click anchors: 9 cm proud of the plate, collisionless, with a
    # per-button orthonormal frame pair in the face plane (x horizontal,
    # z vertical) so no hitbox inherits a skewed shared basis.
    for button in spec.PANEL_BUTTONS:
        anchor = (ccx + button["dx"], spec.BUTTON_ANCHOR_Y, button["z"])
        anchor_id = cage.add_node(
            f"panelbtn_{button['id']}", anchor, fixed=True, collision=False, weight=20.0
        )
        cage.add_beam(anchor_id, console[(0, 0, 1)])
        for tag, off in (("fx", (0.4, 0.0, 0.0)), ("fy", (0.0, 0.0, 0.4))):
            frame_id = cage.add_node(
                f"panel{tag}_{button['id']}",
                (anchor[0] + off[0], anchor[1] + off[1], anchor[2] + off[2]),
                fixed=True,
                collision=False,
                weight=20.0,
            )
            cage.add_beam(frame_id, console[(0, 1, 1)])
    frame_x_node = cage.add_node(
        "panel_frame_x",
        (ccx + 0.9, spec.BUTTON_ANCHOR_Y, 1.5),
        fixed=True,
        collision=False,
        weight=20.0,
    )
    frame_y_node = cage.add_node(
        "panel_frame_y",
        (ccx, spec.BUTTON_ANCHOR_Y, 2.0),
        fixed=True,
        collision=False,
        weight=20.0,
    )
    cage.add_beam(frame_x_node, console[(0, 1, 1)])
    cage.add_beam(frame_y_node, console[(0, 0, 1)])

    cage.set_refnodes_existing(
        ref=pad[(1, 1, 0)],
        back=pad[(1, 0, 0)],
        left=pad[(0, 1, 0)],
        up=pad[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            skirt["nw"],
            skirt["ne"],
            pad[(0, 2, 1)],
            pad[(2, 2, 1)],
            hinge[(0, 0, 0)],
            hinge[(1, 0, 0)],
            hinge[(0, 0, 1)],
            hinge[(1, 0, 1)],
        ]
    )
    cage.auto_base_nodes()
    return cage


def build_studio_stage():
    """Studio stage for the shipped presentation art, and its camera.

    The shared kit's thumbnail helper renders one flat sun against a flat
    sky, which reads as a grey snapshot next to the stock selector cards.
    Stock BeamNG previews are studio shots: subject filling the frame on a
    seamless cyclorama with a soft contact shadow. So this builds that
    stage — screen-space gradient backdrop, key/fill/rim, matte floor.

    Destructive to the scene (replaces the world, adds lights and a floor),
    so everything that calls it runs after the exports.
    """
    import bmesh
    import bpy

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    scene.render.film_transparent = False
    if hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 128

    world = bpy.data.worlds.new("selector_world")
    scene.world = world
    world.use_nodes = True
    tree = world.node_tree
    for node in list(tree.nodes):
        if node.type != "OUTPUT_WORLD":
            tree.nodes.remove(node)
    output = tree.nodes["World Output"]
    tex_co = tree.nodes.new("ShaderNodeTexCoord")
    separate = tree.nodes.new("ShaderNodeSeparateXYZ")
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    background = tree.nodes.new("ShaderNodeBackground")
    tree.links.new(tex_co.outputs["Window"], separate.inputs["Vector"])
    tree.links.new(separate.outputs["Y"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], background.inputs["Color"])
    tree.links.new(background.outputs["Background"], output.inputs["Surface"])
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.52, 0.545, 0.575, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.17, 0.185, 0.205, 1.0)

    for name, kind, energy, size, location, rotation in (
        ("sel_key", "SUN", 4.2, None, None, (56.0, 0.0, -138.0)),
        ("sel_fill", "AREA", 26000.0, 26.0, (-16.0, -22.0, 12.0), (52.0, 0.0, -36.0)),
        ("sel_rim", "AREA", 14000.0, 18.0, (10.0, 14.0, 9.0), (64.0, 0.0, 168.0)),
    ):
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        if kind == "SUN":
            data.angle = math.radians(6.0)
        else:
            data.size = size
        light = bpy.data.objects.new(name, data)
        if location is not None:
            light.location = location
        light.rotation_euler = tuple(math.radians(value) for value in rotation)
        scene.collection.objects.link(light)

    mesh = bpy.data.meshes.new("sel_floor")
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=90.0)
    bm.to_mesh(mesh)
    bm.free()
    floor = bpy.data.objects.new("sel_floor", mesh)
    floor_material = bpy.data.materials.new("sel_floor_mat")
    floor_material.use_nodes = True
    shader = floor_material.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (0.42, 0.435, 0.455, 1.0)
    shader.inputs["Roughness"].default_value = 0.70
    mesh.materials.append(floor_material)
    floor.location = (0.0, 0.0, -0.004)
    scene.collection.objects.link(floor)

    camera_data = bpy.data.cameras.new("sel_cam")
    camera = bpy.data.objects.new("sel_cam", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def shoot(camera, path: Path, *, azimuth, elevation, lens, fit_radius, target,
          resolution) -> None:
    """Orbit the studio camera and render.

    Azimuth 0 is +y (downrange, the direction the boot kicks). Distance
    solves the fit radius against the horizontal field of view, so changing
    the lens reframes instead of just cropping.
    """
    import bpy
    from mathutils import Vector

    scene = bpy.context.scene
    camera.data.lens = lens
    fov = 2.0 * math.atan(18.0 / lens)
    distance = fit_radius / math.tan(fov * 0.5) * 1.02
    a = math.radians(azimuth)
    e = math.radians(elevation)
    focus = Vector(target)
    camera.location = focus + Vector(
        (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e))
    ) * distance
    camera.rotation_euler = (focus - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.resolution_x, scene.render.resolution_y = resolution
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def render_presentation(camera) -> None:
    """The shipped selector card plus the beamng.com listing gallery.

    The selector card frames the whole rig on a 62-degree three-quarter so
    the console, the heel hinge, the boot and the red X all read at 500x281.
    The gallery shots are the same stage at 16:9, each carrying one selling
    point: the rig, the boot, the pad, the console front, the data plate.
    """
    shoot(
        camera,
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        azimuth=62.0, elevation=16.0, lens=52.0, fit_radius=9.0,
        target=(0.0, -4.4, 2.3), resolution=(500, 281),
    )
    gallery = AUTHORING_ROOT / "listing"
    for name, azimuth, elevation, lens, fit_radius, target in (
        ("01_rig", 62.0, 16.0, 52.0, 9.4, (0.0, -4.4, 2.3)),
        ("02_boot", 74.0, 9.0, 62.0, 5.2, (0.0, -5.0, 2.4)),
        ("03_kick_pad", 44.0, 20.0, 46.0, 5.6, (0.0, -1.4, 1.1)),
        # The console faces -y, so azimuth ~190 is its front and ~15 its back.
        ("04_console", 196.0, 14.0, 50.0, 1.35, (0.0, -11.40, 1.16)),
        ("05_data_plate", 15.0, 12.0, 78.0, 0.22, (0.615, -11.12, 0.793)),
    ):
        shoot(
            camera,
            gallery / f"{name}.jpg",
            azimuth=azimuth, elevation=elevation, lens=lens,
            fit_radius=fit_radius, target=target, resolution=(1280, 720),
        )


def render_icon_source(path: Path) -> None:
    """Source art for the beamng.com resource icon (authoring/make_resource_icon.py).

    A 96 px badge cannot hold the whole rig, but it can hold the boot — so
    this renders the boot alone, cocked on its hinge, orthographic side-on
    against transparency. Drawing the profile by hand was worse: the real
    mesh already has the lug row, the collar roll and the lace tongue, and
    they survive the downscale because they are high-contrast.

    Destructive (hides every other object, moves the boot), so it runs last.
    """
    import bpy
    from mathutils import Matrix, Vector

    scene = bpy.context.scene
    boot = [
        obj
        for obj in scene.objects
        if obj.type == "MESH" and obj.name.endswith(("_boot_hero", "_heel_collar"))
    ]
    if not boot:
        raise RuntimeError("icon source: no boot mesh in the scene")
    for obj in scene.objects:
        if obj.type == "MESH" and obj not in boot:
            obj.hide_render = True

    def bounds(objects):
        lo = Vector((1e9, 1e9, 1e9))
        hi = Vector((-1e9, -1e9, -1e9))
        for obj in objects:
            for corner in obj.bound_box:
                world = obj.matrix_world @ Vector(corner)
                for i in range(3):
                    lo[i] = min(lo[i], world[i])
                    hi[i] = max(hi[i], world[i])
        return lo, hi

    lo, _ = bounds(boot)
    pivot = Vector((0.0, lo.y + 0.35, 0.35))
    swing = (
        Matrix.Translation(pivot)
        @ Matrix.Rotation(math.radians(16.0), 4, "X")
        @ Matrix.Translation(-pivot)
    )
    for obj in boot:
        obj.matrix_world = swing @ obj.matrix_world
    lo, hi = bounds(boot)
    center = (lo + hi) * 0.5

    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    if hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = 160

    world = bpy.data.worlds.new("icon_world")
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs[0].default_value = (0.30, 0.30, 0.32, 1.0)
    background.inputs[1].default_value = 0.55

    for name, energy, rotation in (
        ("icon_key", 6.5, (58.0, 0.0, -150.0)),
        ("icon_rim", 3.2, (108.0, 0.0, 30.0)),
        ("icon_top", 2.0, (18.0, 0.0, -95.0)),
    ):
        data = bpy.data.lights.new(name, "SUN")
        data.energy = energy
        data.angle = math.radians(9.0)
        light = bpy.data.objects.new(name, data)
        light.rotation_euler = tuple(math.radians(value) for value in rotation)
        scene.collection.objects.link(light)

    camera_data = bpy.data.cameras.new("icon_cam")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = max(hi.y - lo.y, hi.z - lo.z) * 1.06
    camera = bpy.data.objects.new("icon_cam", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    # Side-on from +x with a few degrees of toe-in, so the boot has volume.
    camera.location = (40.0, center.y - 1.4, center.z + 1.0)
    camera.rotation_euler = (center - Vector(camera.location)).to_track_quat(
        "-Z", "Y"
    ).to_euler()
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


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
            "camera_distance": behavior.get("camera_distance", 30.0),
        },
    )
    # Review renders: close-up evidence for the detail passes (not shipped).
    review = AUTHORING_ROOT / "review"
    for render_name, camera_location, look_at in (
        ("console", (1.7, -13.5, 1.4), (0.0, -11.5, 1.1)),
        ("console_wide", (3.0, -14.6, 2.3), (0.0, -9.6, 1.4)),
        ("boot_side", (7.5, -6.5, 1.5), (0.0, -4.0, 1.6)),
        ("boot_laces", (2.6, -1.8, 4.6), (0.0, -5.4, 3.2)),
        ("pad_paint", (3.4, -3.2, 3.2), (0.0, 1.2, 0.1)),
        ("hinge_steel", (3.4, -6.2, 1.4), (0.0, -8.0, 0.8)),
    ):
        bk.render_thumbnail(
            review / f"{MOD_ID}_{render_name}.jpg",
            camera_location=camera_location,
            look_at=look_at,
            resolution=(640, 480),
        )
    # Both run last and in this order: the studio stage replaces the world
    # and adds a floor, then the icon pass hides everything but the boot.
    render_presentation(build_studio_stage())
    render_icon_source(AUTHORING_ROOT / "icon_source_boot.png")
    print(f"BOOT_OF_DOOM generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
