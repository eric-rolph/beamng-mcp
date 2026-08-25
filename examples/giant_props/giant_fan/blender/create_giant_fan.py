"""Deterministic Blender generator for The Giant Fan.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/giant_fan/blender/create_giant_fan.py

The machine is FOUR bodies, and which body a node belongs to is the whole
design:

  ``_physics``  the fixed base, its deck and ramps, the neck, the ground
                console. Never moves. Carries the spawn envelope and the
                base nodes.
  ``yoke``      free. Hangs off the neck on a two-node pin joint at the yaw
                axis, so it can rotate about vertical and nothing else. The
                sweep hydro commands that one degree of freedom.
  ``head``      free. Hangs off the yoke on a two-node trunnion, so it can
                rotate about the transverse axis and nothing else. The tilt
                hydro commands that one.
  ``rotor``     free, and it is a jbeam ROTATOR group: a compact collar ring
                on the fan axis, beamed to the two hub-axis nodes and to
                nothing else. It is what the motor actually drives.
  ``blade``     free. Three bus-sized blades beamed to the collar, dragged
                round by it - the same way stock large_spinner's arms are
                dragged by its ``spin_center`` collar. They carry the
                collision triangles that wreck cars.

A pin joint here is beam geometry, not a fictional ``hinges`` section: nodes
placed ON the axis, beamed to a surrounding cage on the other body. Rotation
about that axis preserves every one of those beam lengths, and nothing else
does. Stock builds its swing gate exactly this way.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from mathutils import Vector

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

S = spec  # the authored constants; every number below comes from there


# ---------------------------------------------------------------------------
# Geometry helpers.
# ---------------------------------------------------------------------------
def base_outline(count: int = 96) -> list[tuple[float, float]]:
    """The four-lobed rounded square of the reference base.

    Lobes on the DIAGONALS, concave scallops at the four mid-edge centres.
    Sampled as a closed polygon so the slab, the deck and the kerb all key
    off one outline and cannot drift apart.
    """

    points: list[tuple[float, float]] = []
    half = S.BASE_X / 2.0
    n = S.BASE_SQUARENESS
    for i in range(count):
        theta = 2.0 * math.pi * i / count
        cx, sy = math.cos(theta), math.sin(theta)
        # A superellipse |x/a|^n + |y/a|^n = 1 is the rounded SQUARE the
        # reference base is; n = 2 would be a circle and the machine would
        # read as a bollard. The reference's proud diagonal lobes are then
        # added as a small four-fold bulge, and the concave mid-edge scallops
        # as its negative.
        denom = (abs(cx) ** n + abs(sy) ** n) ** (1.0 / n)
        r = half / max(denom, 1e-9)
        lobe = math.cos(4.0 * theta)          # +1 on the axes, -1 on diagonals
        r *= 1.0 + 0.115 * (-lobe)            # lobes proud, scallops in
        points.append((r * cx, r * sy))
    return points


def polygon_prism(name, outline, z0, z1, material, inset=0.0, metric_uv=None):
    """A closed prism from a plan outline. Blender-side helper only."""

    import bmesh
    import bpy

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    scale = 1.0
    if inset:
        # Shrink the outline toward its centroid by `inset` metres.
        mean_r = sum(math.hypot(x, y) for x, y in outline) / len(outline)
        scale = max(0.05, (mean_r - inset) / mean_r)
    lower = [bm.verts.new((x * scale, y * scale, z0)) for x, y in outline]
    upper = [bm.verts.new((x * scale, y * scale, z1)) for x, y in outline]
    bm.verts.ensure_lookup_table()
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lower[i], lower[j], upper[j], upper[i]))
    bm.faces.new(list(reversed(lower)))
    bm.faces.new(upper)
    bm.to_mesh(mesh)
    bm.free()
    bk.assign_material(obj, material)
    if metric_uv is not None:
        bk.add_metric_box_uvs(obj, meters_per_tile=metric_uv)
    return obj


def ramp_wedge(name, cx, crest_y, toe_y, width, height, material, metric_uv=None):
    """A drive-up wedge: full height at the crest, zero at the toe.

    Sits ON the ground for its whole length, which a rotated box does not.
    """

    import bmesh
    import bpy

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    hw = width / 2.0
    verts = {}
    for sx in (-1, 1):
        verts[("crest", sx, "hi")] = bm.verts.new((cx + sx * hw, crest_y, height))
        verts[("crest", sx, "lo")] = bm.verts.new((cx + sx * hw, crest_y, 0.0))
        verts[("toe", sx, "lo")] = bm.verts.new((cx + sx * hw, toe_y, 0.0))
    bm.verts.ensure_lookup_table()
    for sx in (-1, 1):
        bm.faces.new(
            (verts[("crest", sx, "hi")], verts[("crest", sx, "lo")], verts[("toe", sx, "lo")])
        )
    bm.faces.new(
        (
            verts[("crest", -1, "hi")],
            verts[("crest", 1, "hi")],
            verts[("toe", 1, "lo")],
            verts[("toe", -1, "lo")],
        )
    )
    bm.faces.new(
        (
            verts[("crest", -1, "lo")],
            verts[("crest", 1, "lo")],
            verts[("toe", 1, "lo")],
            verts[("toe", -1, "lo")],
        )
    )
    bm.faces.new(
        (
            verts[("crest", -1, "hi")],
            verts[("crest", -1, "lo")],
            verts[("crest", 1, "lo")],
            verts[("crest", 1, "hi")],
        )
    )
    bm.to_mesh(mesh)
    bm.free()
    bk.assign_material(obj, material)
    if metric_uv is not None:
        bk.add_metric_box_uvs(obj, meters_per_tile=metric_uv)
    return obj


def neck_r(z: float) -> float:
    """The neck cone's radius at height ``z``. Anything moulded into the neck
    is placed against THIS, never against a constant: the neck tapers 1.85 m
    over its 8.90 m and a chord across it is either buried or floating."""

    return S.NECK_R_BOT + (S.NECK_R_TOP - S.NECK_R_BOT) * (z - S.DECK_Z) / S.NECK_H


def hsg_r(y: float) -> float:
    """The motor housing cone's radius at station ``y``."""

    return S.HSG_R_REAR + (S.HSG_R_FRONT - S.HSG_R_REAR) * (
        (y - S.HSG_REAR_Y) / S.HSG_L
    )


def band_uv(r_a: float, r_b: float, depth: float, repeats: int = 2):
    """Metres-per-tile for a warning band wrapped round a shell.

    The moulded_warning artwork is a 6:1 plate. One tile stretched round a
    29 m collar would print it at 70 px/m - the density cliff UV_METERS
    exists to prevent - so the band carries a whole number of instances
    instead, which is what a real moulded warning collar does.
    """

    mean_radius = 0.5 * (r_a + r_b)
    slant = math.hypot(depth, r_a - r_b)
    return (2.0 * math.pi * mean_radius / repeats, slant)


# The blade sampler lives in spec.py: the tilt ladder's strike heights are
# solved against the same corner cloud the cage emits, and two copies of the
# sampler would be two different blades.
blade_section = S.blade_section
blade_point = S.blade_point
BLADE_AZIMUTHS = S.BLADE_AZIMUTHS


# ---------------------------------------------------------------------------
# Materials.
# ---------------------------------------------------------------------------
def build_materials():
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def uv(material_key):
    """Metres per texture tile for ``material_key``, or None for a one-tile map.

    The assert is the point: a mistyped or renamed key used to return None
    silently, and the primitive then fell back to Blender's 0..1 default UV -
    one texture tile stretched over a 30 m shell, which is the "tiny blocks"
    density cliff the whole UV_METERS table exists to prevent. Every palette
    entry is in exactly one of the two sets.
    """

    assert (
        material_key in S.UV_METERS or material_key in S.ONE_TILE_MATERIALS
    ), f"no UV policy for {material_key!r}"
    return S.UV_METERS.get(material_key)


def printed_quad(name, corners, material, *, outward=None):
    """A single quad carrying ONE printed artwork across its whole face.

    ``corners`` is (origin, along_width, along_height) in world metres; the UV
    runs 0..1 with u along WIDTH and v along HEIGHT, so a legend drawn wider
    than it is tall arrives on the surface the same way round.

    ``outward`` is the direction the print must FACE, and the triple has to be
    RIGHT-HANDED about it: width x height == outward. That is not pedantry -
    it is the difference between text you can read and text in a mirror, and it
    is easy to get wrong on a raked plate, so it is asserted rather than
    silently corrected.

    This exists because a primitive's default UV does not do that. Measured off
    the shipped DAE, the escutcheon's outward face carried u in [0.378, 0.622]
    and v in [0.251, 0.499] - a 24% x 25% crop - with the texture's U axis
    running along the plate's HEIGHT: the dial showed one sideways "3" with
    4.7 m of blank panel beside it, the console legend was entirely blank, and
    ONE_TILE_MATERIALS could not help because one tile of the wrong window is
    still the wrong window.
    """

    import bmesh
    import bpy

    origin, width, height = (Vector(v) for v in corners)
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    if outward is not None:
        handedness = width.cross(height).normalized().dot(
            Vector(outward).normalized()
        )
        assert handedness > 0.99, (name, handedness)
    places = [
        (origin, (0.0, 0.0)),
        (origin + width, (1.0, 0.0)),
        (origin + width + height, (1.0, 1.0)),
        (origin + height, (0.0, 1.0)),
    ]
    verts = [bm.verts.new(place) for place, _uv in places]
    bm.verts.ensure_lookup_table()
    bm.faces.new(verts)
    bm.to_mesh(mesh)
    bm.free()
    layer = mesh.uv_layers.new(name="UVMap")
    coords = [uv for _place, uv in places]
    for polygon in mesh.polygons:
        for slot, loop_index in enumerate(polygon.loop_indices):
            layer.data[loop_index].uv = coords[slot]
    bk.assign_material(obj, material)
    return obj


def rotate_x(obj, angle):
    """Rotate a finished primitive about its own origin, then bake it in."""

    import bpy

    obj.rotation_euler = (angle, 0.0, 0.0)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    obj.select_set(False)
    return obj


def printed_disc(name, centre, radius_x, radius_z, material, *, segments=28,
                 station=None):
    """A disc facing +Y whose UV samples the WHOLE of a round printed artwork.

    Blender's stock cylinder cap packs its UV into one quadrant of the map -
    measured on the shipped DAE the hub badge's front cap carried u [0.51, 0.99]
    x v [0.01, 0.49], so the roundel rendered as one arc and a stub of a letter.
    A hand-built fan puts (0.5, 0.5) at the centre and the unit circle at the
    rim, which is what fit_circle artwork is drawn against.

    ``station(dx, dz) -> y`` optionally curves the disc onto a surface, so a
    badge on a dome hugs the dome instead of floating off its pole.

    u runs along -X and v along +Z, because u x v then points +Y: a roundel
    mapped the other way round is a roundel in a mirror.
    """

    import bmesh
    import bpy

    def place(dx, dz):
        y = station(dx, dz) if station else centre[1]
        return (centre[0] + dx, y, centre[2] + dz)

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    hub = bm.verts.new(place(0.0, 0.0))
    rim = []
    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        rim.append(
            bm.verts.new(
                place(radius_x * math.cos(angle), radius_z * math.sin(angle))
            )
        )
    bm.verts.ensure_lookup_table()
    # Wound so the face normal points +Y, which is FORWARD in the authored
    # frame: the badge looks out of the front of the hub cap, not into it.
    for i in range(segments):
        bm.faces.new((hub, rim[(i + 1) % segments], rim[i]))
    bm.to_mesh(mesh)
    bm.free()
    layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            layer.data[loop_index].uv = (
                0.5 - 0.5 * (co[0] - centre[0]) / radius_x,
                0.5 + 0.5 * (co[2] - centre[2]) / radius_z,
            )
    bk.assign_material(obj, material)
    return obj


# ---------------------------------------------------------------------------
# The fixed body: base, deck, ramps, neck, console.
# ---------------------------------------------------------------------------
def build_base(m) -> list:
    yellowed = m[f"{MOD_ID}_shell_yellowed"]
    rubber = m[f"{MOD_ID}_foot_rubber"]
    steel = m[f"{MOD_ID}_machine_steel"]
    gantry = m[f"{MOD_ID}_gantry_steel"]
    legend = m[f"{MOD_ID}_panel_legend"]
    dial_face = m[f"{MOD_ID}_dial_face"]
    chrome = m[f"{MOD_ID}_chrome"]
    warning = m[f"{MOD_ID}_moulded_warning"]
    hazard = m[f"{MOD_ID}_hazard"]

    objects = []
    outline = base_outline()

    # The fallen guard's warning sticker, on the ground between the two front
    # kick ramps where it landed. It belongs to the BASE, not the head: built
    # into build_head() it joined the head mesh, which yaws for the sweep and
    # tilts for the strike ladder, and a 4.2 m chevron then skated 19 m across
    # the ground and lifted 6.8 m into the air.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_guard_sticker",
            (0.0, 16.80, 0.06),
            (S.STICKER_W, S.STICKER_H, 0.04),
            hazard,
            rotation=(0.0, 0.0, math.radians(24.0)),
            metric_uv=uv(f"{MOD_ID}_hazard"),
        )
    )

    # The slab. Its underside is FOOT_PROUD above ground; the four pads carry
    # it, and their undersides are the machine's spawn datum at z = 0.
    objects.append(
        polygon_prism(
            f"{MOD_ID}_base_slab",
            outline,
            S.BASE_UNDERSIDE_Z,
            S.DECK_Z,
            yellowed,
            metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
        )
    )
    # Kerb: a low lip round the drivable deck, so the edge reads.
    objects.append(
        polygon_prism(
            f"{MOD_ID}_kerb",
            outline,
            S.DECK_Z,
            S.DECK_Z + S.KERB_H,
            yellowed,
            inset=S.DECK_INSET * 0.35,
            metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
        )
    )
    # Four rubber feet on the diagonals.
    for i, (sx, sy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_foot_{i}",
                (sx * S.FOOT_C, sy * S.FOOT_C, S.FOOT_PROUD / 2.0),
                S.FOOT_R,
                S.FOOT_PROUD,
                rubber,
                vertices=20,
                metric_uv=uv(f"{MOD_ID}_foot_rubber"),
            )
        )
    # Ramps: two at the front (the approach) and one at the rear (service).
    for name, sx, sy in (
        ("kick_l", -S.KICK_RAMP_X, 1.0),
        ("kick_r", S.KICK_RAMP_X, 1.0),
        ("rear", S.REAR_RAMP_X, -1.0),
    ):
        crest_y = sy * S.RAMP_CREST_Y
        toe_y = sy * (S.RAMP_CREST_Y + S.RAMP_RUN)
        # A WEDGE, not a rotated box. Rotating a 9 m box 15 degrees swings its
        # far end 1.16 m underground, which both buries geometry and lies about
        # where the machine's lowest point is.
        objects.append(
            ramp_wedge(
                f"{MOD_ID}_ramp_{name}",
                sx,
                crest_y,
                toe_y,
                S.RAMP_W,
                S.DECK_Z,
                yellowed,
                metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
            )
        )

    # The machine's own dial face, on the FRONT scallop: the thing you READ.
    #
    # The plate is RAKED back by ESC_TILT_DEG, so everything on it has to be
    # placed in the plate's own frame, not in world z. esc_n is its outward
    # normal, esc_v runs up its face.
    esc_y = 12.45 - S.ESC_RECESS
    esc_tilt = math.radians(-S.ESC_TILT_DEG)
    esc_c = Vector((0.0, esc_y, S.ESC_C_Z))
    esc_u = Vector((1.0, 0.0, 0.0))
    esc_v = Vector((0.0, -math.sin(esc_tilt), math.cos(esc_tilt)))
    esc_n = Vector((0.0, math.cos(esc_tilt), math.sin(esc_tilt)))
    objects.append(
        bk.add_box(
            f"{MOD_ID}_esc_recess_face",
            tuple(esc_c),
            (S.ESC_W, 0.10, S.ESC_H),
            yellowed,
            rotation=(esc_tilt, 0.0, 0.0),
            bevel=0.02,
            metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
        )
    )
    # The printed dial itself: one quad, one tile, u across the plate's WIDTH
    # and v up its HEIGHT. A bevelled box could not carry it - see printed_quad.
    objects.append(
        printed_quad(
            f"{MOD_ID}_dial_print",
            (
                esc_c + esc_n * 0.052 + esc_u * (S.ESC_W / 2.0) - esc_v * (S.ESC_H / 2.0),
                -esc_u * S.ESC_W,
                esc_v * S.ESC_H,
            ),
            dial_face,
            outward=esc_n,
        )
    )
    # An open BEZEL FRAME, four rails, not a lid. What shipped was a single
    # solid box 0.06 m IN FRONT of the dial and larger than it in both
    # directions: a closed 108-triangle slab over the whole escutcheon, with
    # the chrome knob 0.10 m BEHIND the dial face. From the front the machine
    # had no dial on it at all - and "the dial adjusts power" is the headline
    # verb.
    for label, offset, dims in (
        ("top", esc_v * ((S.ESC_H + S.ESC_BEZEL) / 2.0),
         (S.ESC_W + 2 * S.ESC_BEZEL, 0.12, S.ESC_BEZEL)),
        ("bottom", -esc_v * ((S.ESC_H + S.ESC_BEZEL) / 2.0),
         (S.ESC_W + 2 * S.ESC_BEZEL, 0.12, S.ESC_BEZEL)),
        ("left", -esc_u * ((S.ESC_W + S.ESC_BEZEL) / 2.0),
         (S.ESC_BEZEL, 0.12, S.ESC_H)),
        ("right", esc_u * ((S.ESC_W + S.ESC_BEZEL) / 2.0),
         (S.ESC_BEZEL, 0.12, S.ESC_H)),
    ):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_esc_bezel_{label}",
                tuple(esc_c + esc_n * 0.06 + offset),
                dims,
                yellowed,
                rotation=(esc_tilt, 0.0, 0.0),
                bevel=0.04,
                metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
            )
        )
    # The knob stands PROUD of the bezel's lip, normal to the raked face, which
    # is where a rotary knob lives.
    objects.append(
        rotate_x(
            bk.add_cylinder(
                f"{MOD_ID}_dial_knob_disc",
                tuple(esc_c + esc_n * 0.14),
                S.KNOB_R,
                0.10,
                chrome,
                axis="Y",
                vertices=18,
                metric_uv=uv(f"{MOD_ID}_chrome"),
            ),
            esc_tilt,
        )
    )

    # The working console, in the rear bay.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_console_box",
            (S.PANEL_X - 0.35, S.BAY_C[1], S.DECK_Z + 0.85),
            (0.70, S.PANEL_W + 0.60, 1.70),
            steel,
            bevel=0.05,
            metric_uv=uv(f"{MOD_ID}_machine_steel"),
        )
    )
    # The console legend. A quad with explicit UVs for the same reason the dial
    # is: as a box its outward face carried a 25% window of the map with the u
    # axis running up the plate's HEIGHT, so the GALEFORCE title was not in the
    # window at all and five buttons had no labels beside them. u runs along
    # the plate's width (+Y, the direction _plate_u measures) and v up its
    # height (+Z, which is what _plate_v measures), so the label table in
    # spec.py lands exactly where it says it does.
    objects.append(
        printed_quad(
            f"{MOD_ID}_console_plate",
            (
                (
                    S.PANEL_X + 0.045,
                    S.BAY_C[1] - S.PANEL_W / 2.0,
                    S.PANEL_Z - S.PANEL_H / 2.0,
                ),
                (0.0, S.PANEL_W, 0.0),
                (0.0, 0.0, S.PANEL_H),
            ),
            legend,
            outward=(1.0, 0.0, 0.0),
        )
    )
    for button in S.PANEL_BUTTONS:
        if button["id"] == "plunger":
            continue
        cap_material = m[f"{MOD_ID}_cap_{button['cap']}"]
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_cap_{button['id']}",
                button["position"],
                button["size"] / 2.0,
                0.10,
                cap_material,
                axis="X",
                vertices=16,
                metric_uv=uv(f"{MOD_ID}_cap_{button['cap']}"),
            )
        )

    # The neck. Fixed, and part of the base.
    objects.append(
        bk.add_cone(
            f"{MOD_ID}_neck_cone",
            (0.0, 0.0, (S.DECK_Z + S.NECK_TOP_Z) / 2.0),
            S.NECK_R_BOT,
            S.NECK_R_TOP,
            S.NECK_H,
            yellowed,
            vertices=32,
            bevel=0.05,
            metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
        )
    )
    for i, v in enumerate(S.NECK_SWAGE_V):
        z = S.DECK_Z + S.NECK_H * v
        r = S.NECK_R_BOT + (S.NECK_R_TOP - S.NECK_R_BOT) * v
        objects.append(
            bk.add_torus(
                f"{MOD_ID}_neck_swage_{i}",
                (0.0, 0.0, z),
                r + S.NECK_SWAGE_MINOR_R * 0.5,
                S.NECK_SWAGE_MINOR_R,
                yellowed,
                major_segments=32,
                minor_segments=10,
                metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
            )
        )
    # The moulded-in warning, on the one continuous convex surface that can
    # carry it. ink == base, so it reads by relief alone.
    band_lo = neck_r(S.NECK_WARN_Z[0]) + 0.06
    band_hi = neck_r(S.NECK_WARN_Z[1]) + 0.06
    band_h = S.NECK_WARN_Z[1] - S.NECK_WARN_Z[0]
    objects.append(
        bk.add_cone(
            f"{MOD_ID}_neck_warning_band",
            (0.0, 0.0, (S.NECK_WARN_Z[0] + S.NECK_WARN_Z[1]) / 2.0),
            band_lo,
            band_hi,
            band_h,
            warning,
            vertices=48,
            metric_uv=band_uv(band_lo, band_hi, band_h),
        )
    )

    # Service gantry up the back of the neck: the industrial read, and what
    # makes the crown plunger reachable on foot.
    #
    # Two things the first cut got wrong. The rungs sat at a CONSTANT y while
    # the neck is a cone that loses 1.85 m of radius over its rise, so the top
    # rung floated 2.60 m clear of the shell and the whole ladder read as ten
    # planks levitating. And the rise was NECK_H/10 = 0.89 m, which is not a
    # step - GANTRY_STAIR_RISE is authored at 0.28 for exactly this.
    # A LADDER, not ten planks: rungs at the authored 0.28 m rise, each one
    # buried 0.10 m into the shell it climbs, carried by two stringers.
    rung_depth, rung_thick, rung_bury = 0.34, 0.10, 0.10
    rung_count = int(S.NECK_H / S.GANTRY_STAIR_RISE)

    def rung_y(z: float) -> float:
        return -(neck_r(z) - rung_bury + rung_depth / 2.0)

    for i in range(rung_count):
        z = S.DECK_Z + (i + 1) * S.GANTRY_STAIR_RISE
        objects.append(
            bk.add_box(
                f"{MOD_ID}_gantry_stair_{i}",
                (0.0, rung_y(z), z),
                (S.GANTRY_W, rung_depth, rung_thick),
                gantry,
                bevel=0.02,
                metric_uv=uv(f"{MOD_ID}_gantry_steel"),
            )
        )
    # The two stringers. They follow the cone with the rungs, so a single
    # straight box does the job exactly - neck_r is linear in z.
    z_lo = S.DECK_Z + S.GANTRY_STAIR_RISE
    z_hi = S.DECK_Z + rung_count * S.GANTRY_STAIR_RISE

    def rail_y(z: float) -> float:
        return rung_y(z) - rung_depth / 2.0 + 0.10

    y_lo, y_hi = rail_y(z_lo), rail_y(z_hi)
    rail_len = math.hypot(y_hi - y_lo, z_hi - z_lo)
    # add_box rotates about X first, and Rx(t) sends local +Z to
    # (0, -sin t, cos t) - so the tilt that lays the rail along the cone is
    # the NEGATIVE of the rail's own y-over-z slope angle.
    rail_tilt = -math.atan2(y_hi - y_lo, z_hi - z_lo)
    for side, sx in (("l", -1.0), ("r", 1.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_gantry_stringer_{side}",
                (
                    sx * (S.GANTRY_W / 2.0 - 0.10),
                    0.5 * (y_lo + y_hi),
                    0.5 * (z_lo + z_hi),
                ),
                (0.16, 0.20, rail_len),
                gantry,
                bevel=0.02,
                rotation=(rail_tilt, 0.0, 0.0),
                metric_uv=uv(f"{MOD_ID}_gantry_steel"),
            )
        )
    return objects


# ---------------------------------------------------------------------------
# The moving bodies: yoke, head, rotor.
# ---------------------------------------------------------------------------
def build_yoke(m) -> list:
    yellowed = m[f"{MOD_ID}_shell_yellowed"]
    steel = m[f"{MOD_ID}_machine_steel"]
    objects = [
        bk.add_cylinder(
            f"{MOD_ID}_yoke_collar",
            (0.0, 0.0, sum(S.YOKE_COLLAR_Z) / 2.0),
            S.YOKE_COLLAR_R,
            S.YOKE_COLLAR_Z[1] - S.YOKE_COLLAR_Z[0],
            yellowed,
            vertices=28,
            bevel=0.05,
            metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
        )
    ]
    # Each arm needs a SHOULDER carrying it down onto the collar. Without one
    # the arm's inboard face stands at |x| 5.795 and its foot at z 11.30, while
    # the collar stops at r 3.55 and z 10.90: a 2.245 m horizontal and 0.40 m
    # vertical gap, so the whole upper yoke - arms, trunnions, tie rails, cross
    # tie - was a mesh island 2.304 m from the nearest surface of its own body.
    # Two 6.84 m slabs standing on daylight, plainly visible from the front.
    #
    # The shoulder bites 0.30 m into the collar's radius and overlaps both the
    # collar's top course and the arm's foot, so the load path reads.
    shoulder_in = S.YOKE_COLLAR_R - 0.30
    shoulder_out = S.YOKE_HALF_SPAN + S.YOKE_ARM_T / 2.0
    shoulder_lo = S.YOKE_COLLAR_Z[1] - 1.00
    shoulder_hi = (S.YAWPIVOT_HI_Z + S.HUB_Z) / 2.0 - S.YOKE_ARM_H / 2.0 + 0.30
    for side, sx in (("l", -1.0), ("r", 1.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_yoke_shoulder_{side}",
                (
                    sx * (shoulder_in + shoulder_out) / 2.0,
                    0.0,
                    (shoulder_lo + shoulder_hi) / 2.0,
                ),
                (
                    shoulder_out - shoulder_in,
                    S.YOKE_ARM_W,
                    shoulder_hi - shoulder_lo,
                ),
                yellowed,
                bevel=0.07,
                metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_yoke_arm_{side}",
                (sx * S.YOKE_HALF_SPAN, 0.0, (S.YAWPIVOT_HI_Z + S.HUB_Z) / 2.0),
                (S.YOKE_ARM_T, S.YOKE_ARM_W, S.YOKE_ARM_H),
                yellowed,
                bevel=0.07,
                metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_trunnion_{side}",
                (sx * S.TRUNNION_HALF_SPAN, 0.0, S.HUB_Z),
                S.TRUNNION_PIN_R,
                0.90,
                steel,
                axis="X",
                vertices=18,
                metric_uv=uv(f"{MOD_ID}_machine_steel"),
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_yoke_cross_tie",
            (0.0, S.YOKE_TIE_Y, S.YOKE_TIE_Z),
            (2 * S.YOKE_HALF_SPAN, 0.90, 0.90),
            steel,
            bevel=0.05,
            metric_uv=uv(f"{MOD_ID}_machine_steel"),
        )
    )
    # The tie carries the TILT ANCHOR, 9.60 m behind the trunnion, so without
    # these two rails it is a 13 m steel bar hanging in mid air with the tilt
    # hydro apparently bolted to nothing. Each runs from inside its arm back
    # to the tie.
    rail_front = -S.YOKE_ARM_W / 2.0 + 0.30  # 0.30 m INTO the arm
    rail_rear = S.YOKE_TIE_Y  # and through to the tie's own axis
    for side, sx in (("l", -1.0), ("r", 1.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_yoke_tie_rail_{side}",
                (
                    sx * S.YOKE_HALF_SPAN,
                    0.5 * (rail_front + rail_rear),
                    S.YOKE_TIE_Z,
                ),
                (0.80, rail_front - rail_rear, 0.80),
                steel,
                bevel=0.05,
                metric_uv=uv(f"{MOD_ID}_machine_steel"),
            )
        )
    return objects


def build_head(m) -> list:
    yellowed = m[f"{MOD_ID}_shell_yellowed"]
    white = m[f"{MOD_ID}_shell_white"]
    chrome = m[f"{MOD_ID}_chrome"]
    badge = m[f"{MOD_ID}_hub_badge"]
    bore = m[f"{MOD_ID}_bore_shadow"]
    dark = m[f"{MOD_ID}_blade_smoke_dark"]
    warning = m[f"{MOD_ID}_moulded_warning"]
    beacon = m[f"{MOD_ID}_beacon_lens"]

    objects = []
    # The motor housing: a truncated cone on the fan axis, symmetric about the
    # trunnion station.
    objects.append(
        bk.add_cone(
            f"{MOD_ID}_hsg_cone",
            (0.0, (S.HSG_FRONT_Y + S.HSG_REAR_Y) / 2.0, S.HUB_Z),
            S.HSG_R_FRONT,
            S.HSG_R_REAR,
            S.HSG_L,
            yellowed,
            vertices=36,
            # +90 about X, not -90: primitive_cone_add puts radius1 at local
            # -Z, and Rx(+90) maps local -Z to world +Y. With -90 the cone was
            # built back-to-front - 5.30 m of radius at the REAR, where the
            # 4.05 m dome caps it, and 4.05 m at the FRONT under a 6.35 m
            # flange, with every louvre buried a metre inside the shell.
            rotation=(math.radians(90.0), 0.0, 0.0),
            bevel=0.06,
            metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
        )
    )
    objects.append(
        bk.add_sphere(
            f"{MOD_ID}_hsg_rear_dome",
            (0.0, S.HSG_REAR_Y, S.HUB_Z),
            S.HSG_R_REAR,
            yellowed,
            segments=32,
            rings=16,
            scale=(1.0, S.HSG_REAR_DOME_RISE / S.HSG_R_REAR, 1.0),
            metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
        )
    )
    # Moulded cooling louvres round the housing.
    for i in range(S.HSG_LOUVRE_N):
        a = 2.0 * math.pi * i / S.HSG_LOUVRE_N
        r = S.HSG_R_AT_TRUNNION - S.HSG_LOUVRE_DEPTH / 2.0
        objects.append(
            bk.add_box(
                f"{MOD_ID}_hsg_louvre_{i}",
                (r * math.cos(a), S.HSG_REAR_Y + 2.40, S.HUB_Z + r * math.sin(a)),
                (0.30, 2.60, S.HSG_LOUVRE_PITCH * 0.55),
                yellowed,
                rotation=(0.0, 0.0, 0.0),
                bevel=0.02,
                metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
            )
        )
    # A flat plate can never lie on a cone: it is buried at the middle and
    # floating at the ends. Both moulded bands are coaxial shells 0.06 proud,
    # so the relief reads all the way round and nothing hangs in the air.
    hsg_band_front = hsg_r(S.WARN_BAND_Y[0]) + 0.06
    hsg_band_rear = hsg_r(S.WARN_BAND_Y[1]) + 0.06
    hsg_band_len = S.WARN_BAND_Y[0] - S.WARN_BAND_Y[1]
    objects.append(
        bk.add_cone(
            f"{MOD_ID}_hsg_warning_band",
            (0.0, sum(S.WARN_BAND_Y) / 2.0, S.HUB_Z),
            hsg_band_front,
            hsg_band_rear,
            hsg_band_len,
            warning,
            vertices=48,
            rotation=(math.radians(90.0), 0.0, 0.0),
            metric_uv=band_uv(hsg_band_front, hsg_band_rear, hsg_band_len),
        )
    )

    # --- THE AMPUTATED GUARD -------------------------------------------
    # Somebody cut the grate off. The flange is still here, its bosses are
    # empty, four stubs are snapped off and bent, and the ring of shell the
    # guard shaded is the only factory-white plastic left on the machine.
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_rim_bead",
            (0.0, S.HSG_FRONT_Y, S.HUB_Z),
            S.FLANGE_OD / 2.0,
            S.RIM_BEAD_R,
            white,
            rotation=(math.radians(90.0), 0.0, 0.0),
            major_segments=40,
            minor_segments=12,
            metric_uv=uv(f"{MOD_ID}_shell_white"),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_flange",
            (0.0, S.HSG_FRONT_Y - S.FLANGE_T / 2.0, S.HUB_Z),
            S.FLANGE_OD / 2.0,
            S.FLANGE_T,
            white,
            axis="Y",
            vertices=40,
            metric_uv=uv(f"{MOD_ID}_shell_white"),
        )
    )
    for i in range(S.BOSS_N):
        a = 2.0 * math.pi * i / S.BOSS_N
        px = (S.BOSS_PCD / 2.0) * math.cos(a)
        pz = S.HUB_Z + (S.BOSS_PCD / 2.0) * math.sin(a)
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_boss_{i}",
                (px, S.HSG_FRONT_Y + S.BOSS_PROUD / 2.0, pz),
                S.BOSS_R,
                S.BOSS_PROUD,
                white,
                axis="Y",
                vertices=14,
                metric_uv=uv(f"{MOD_ID}_shell_white"),
            )
        )
        # The bore is EMPTY. That is the point.
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_boss_bore_{i}",
                (px, S.HSG_FRONT_Y + S.BOSS_PROUD * 0.75, pz),
                S.BOSS_BORE_R,
                S.BOSS_PROUD * 0.65,
                bore,
                axis="Y",
                vertices=10,
                metric_uv=uv(f"{MOD_ID}_bore_shadow"),
            )
        )
    # The stubs run RADIALLY out of the flange bead and bend forward by
    # STUB_BEND_DEG - they are the snapped-off remains of the guard's wire
    # spokes. add_cylinder can only point along X/Y/Z, so an axis="Y" rod
    # occupies a single radius and hangs in mid air; add_cone takes a
    # rotation, so the rod can actually leave the flange it grew out of.
    bend = math.radians(S.STUB_BEND_DEG)
    for i in range(S.STUB_N):
        a = 2.0 * math.pi * (i + 0.5) / S.STUB_N
        # Root ON the bead's outer surface, not on the flange's nominal OD.
        r0 = S.FLANGE_OD / 2.0 + S.RIM_BEAD_R
        root = (
            r0 * math.cos(a),
            S.HSG_FRONT_Y,
            S.HUB_Z + r0 * math.sin(a),
        )
        # Unit vector: radially outward, tipped STUB_BEND_DEG toward +Y.
        direction = (
            math.cos(a) * math.cos(bend),
            math.sin(bend),
            math.sin(a) * math.cos(bend),
        )
        # Blender's cone runs along local +Z. Take the minimal-arc rotation
        # from +Z onto `direction` rather than hand-composing Eulers: the fan
        # axis is +Y, so the radial plane is XZ and the obvious Rz*Ry compose
        # is wrong by a coordinate swap.
        orientation = tuple(
            Vector((0.0, 0.0, 1.0))
            .rotation_difference(Vector(direction))
            .to_euler("XYZ")
        )

        def along(distance: float) -> tuple[float, float, float]:
            return (
                root[0] + direction[0] * distance,
                root[1] + direction[1] * distance,
                root[2] + direction[2] * distance,
            )

        objects.append(
            bk.add_cone(
                f"{MOD_ID}_stub_{i}",
                along(S.STUB_ROOT_L / 2.0),
                S.STUB_R,
                S.STUB_R,
                S.STUB_ROOT_L,
                white,
                vertices=10,
                rotation=orientation,
                metric_uv=uv(f"{MOD_ID}_shell_white"),
            )
        )
        # The torn end: dark, because the plastic tore rather than cut. It
        # sits ON the rod's outer end, sharing its axis.
        objects.append(
            bk.add_cone(
                f"{MOD_ID}_stub_frac_{i}",
                along(S.STUB_ROOT_L - 0.30),
                S.STUB_R * 1.05,
                S.STUB_R * 1.05,
                0.60,
                dark,
                vertices=10,
                rotation=orientation,
                metric_uv=uv(f"{MOD_ID}_blade_smoke_dark"),
            )
        )

    # Hub cap, badge, and the oscillation plunger on the crown.
    objects.append(
        bk.add_sphere(
            f"{MOD_ID}_cap_dome",
            (0.0, S.DISC_OFFSET_Y + S.CAP_PROUD * 0.35, S.HUB_Z),
            S.CAP_R,
            yellowed,
            segments=32,
            rings=16,
            scale=(1.0, S.CAP_DOME_RISE / S.CAP_R, 1.0),
            metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
        )
    )
    # The cap is an ellipsoid, so "a bit past its centre" is INSIDE it. Every
    # detail on the cap is seated by solving the ellipsoid at that detail's own
    # radius, never by a fudge factor times CAP_DOME_RISE.
    cap_centre_y = S.DISC_OFFSET_Y + S.CAP_PROUD * 0.35
    # The roundel is MOULDED ONTO the dome, one vertex station at a time, so it
    # hugs the cap instead of floating off its pole - and its UV runs the whole
    # unit circle, which a cylinder cap's stock unwrap does not: the shipped
    # badge sampled only u [0.51, 0.99] x v [0.01, 0.49] and rendered as one
    # ring arc and a stub of a letter.
    def _cap_station(dx, dz):
        radius = math.hypot(dx, dz)
        drop = max(0.0, 1.0 - (radius / S.CAP_R) ** 2)
        return cap_centre_y + S.CAP_DOME_RISE * math.sqrt(drop) + S.BADGE_PROUD * 0.5

    objects.append(
        printed_disc(
            f"{MOD_ID}_badge_face",
            (0.0, cap_centre_y, S.HUB_Z),
            S.BADGE_A / 2.0,
            S.BADGE_B / 2.0,
            badge,
            segments=28,
            station=_cap_station,
        )
    )
    # The eight cap nibs, seated with the SAME arithmetic the badge uses one
    # block above. `CAP_DOME_RISE * 0.42` put them 0.399 m forward of the
    # ellipsoid's centre where the surface at NIB_R is 0.786 m forward, so all
    # eight sat 0.337 m INSIDE the shell: 864 triangles that could never be
    # seen, on a cap that then had nothing on it but the badge.
    nib_surface_y = cap_centre_y + S.CAP_DOME_RISE * math.sqrt(
        1.0 - (S.NIB_R / S.CAP_R) ** 2
    )
    for i in range(S.NIB_N):
        a = 2.0 * math.pi * i / S.NIB_N
        objects.append(
            bk.add_box(
                f"{MOD_ID}_nib_{i}",
                (
                    S.NIB_R * math.cos(a),
                    nib_surface_y + 0.05,
                    S.HUB_Z + S.NIB_R * math.sin(a),
                ),
                (S.NIB_W, 0.10, S.NIB_L),
                yellowed,
                rotation=(0.0, a, 0.0),
                bevel=0.02,
                metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_crown_boss",
            (0.0, S.HSG_FRONT_Y, S.HUB_Z + S.HSG_R_FRONT * 0.86),
            S.CROWN_BOSS_R,
            1.10,
            yellowed,
            vertices=16,
            metric_uv=uv(f"{MOD_ID}_shell_yellowed"),
        )
    )
    objects.append(
        bk.add_sphere(
            f"{MOD_ID}_plunger_dome",
            (0.0, S.HSG_FRONT_Y, S.HUB_Z + S.HSG_R_FRONT * 0.86 + S.PLUNGER_PROUD),
            S.PLUNGER_R,
            chrome,
            segments=24,
            rings=12,
            scale=(1.0, 1.0, 0.72),
            metric_uv=uv(f"{MOD_ID}_chrome"),
        )
    )
    for side, sx in (("l", -1.0), ("r", 1.0)):
        objects.append(
            bk.add_sphere(
                f"{MOD_ID}_beacon_{side}",
                (
                    sx * S.HSG_R_FRONT * S.BEACON_AZ,
                    S.HSG_REAR_Y + 3.0,
                    S.HUB_Z + S.HSG_R_AT_TRUNNION * 0.94,
                ),
                S.BEACON_R,
                beacon,
                segments=16,
                rings=10,
                metric_uv=uv(f"{MOD_ID}_beacon_lens"),
            )
        )
    return objects


def build_rotor(m) -> list:
    """Hub ring, spider and the three bus-sized blades."""

    smoke = m[f"{MOD_ID}_blade_smoke"]
    dark = m[f"{MOD_ID}_blade_smoke_dark"]
    transfer = m[f"{MOD_ID}_blade_transfer"]
    steel = m[f"{MOD_ID}_machine_steel"]

    import bmesh
    import bpy

    objects = [
        bk.add_cylinder(
            f"{MOD_ID}_hub_backplate",
            (0.0, S.DISC_OFFSET_Y - 0.30, S.HUB_Z),
            S.HUB_R,
            0.55,
            smoke,
            axis="Y",
            vertices=28,
            metric_uv=uv(f"{MOD_ID}_blade_smoke"),
        ),
        bk.add_cylinder(
            f"{MOD_ID}_hub_spider",
            (0.0, S.DISC_OFFSET_Y, S.HUB_Z),
            S.HUB_R * 0.55,
            1.10,
            steel,
            axis="Y",
            vertices=20,
            metric_uv=uv(f"{MOD_ID}_machine_steel"),
        ),
    ]

    # The blades. Lofted from the authored stations so the twist is real
    # geometry, not a texture: the section at the root is set 32 degrees and
    # the tip 14, which is what makes a fan blade read as a fan blade.
    for b, azimuth in enumerate(BLADE_AZIMUTHS):
        for half, chord_lo, chord_hi, material in (
            ("fwd", -0.50, 0.15, smoke),
            ("aft", 0.15, 0.50, dark),
        ):
            mesh = bpy.data.meshes.new(f"{MOD_ID}_blade{b}_{half}_mesh")
            obj = bpy.data.objects.new(f"{MOD_ID}_blade{b}_{half}", mesh)
            bpy.context.collection.objects.link(obj)
            bm = bmesh.new()
            rings = []
            for s in S.BLADE_STATIONS_S:
                loop = []
                for cf, tf in (
                    (chord_lo, -0.5),
                    (chord_hi, -0.5),
                    (chord_hi, 0.5),
                    (chord_lo, 0.5),
                ):
                    loop.append(bm.verts.new(blade_point(azimuth, s, cf, tf)))
                rings.append(loop)
            bm.verts.ensure_lookup_table()
            for r0, r1 in zip(rings, rings[1:]):
                for i in range(4):
                    j = (i + 1) % 4
                    bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
            bm.faces.new(list(reversed(rings[0])))
            bm.faces.new(rings[-1])
            bm.to_mesh(mesh)
            bm.free()
            bk.assign_material(obj, material)
            bk.add_metric_box_uvs(
                obj, meters_per_tile=uv(f"{MOD_ID}_blade_smoke")
            )
            objects.append(obj)

    # The paint transfer on the leading blade: what a car leaves behind.
    #
    # Sampled off blade_point, not placed as an axis-aligned box: the station
    # is pitched 22.1 degrees and a flat box in the disc plane cuts straight
    # through the shell - 0.22 m buried at one edge and 1.09 m clear of it at
    # the other, strobing free of a spinning blade once a revolution.
    _r_mid, chord_mid, _pitch_mid = blade_section(0.55)
    smear_ds = 0.90 / S.BLADE_SPAN / 2.0  # 0.90 m of span, half either side
    smear_dc = 2.40 / chord_mid / 2.0  # 2.40 m of chord, half either side
    smear_s = (0.55 - smear_ds, 0.55 + smear_ds)
    smear_c = (-0.10 - smear_dc, -0.10 + smear_dc)
    # Just proud of the front skin (tf -0.5) by 0.06 m of shell thickness.
    smear_t = (-0.50, -0.50 - 0.06 / S.BLADE_THICK)
    mesh = bpy.data.meshes.new(f"{MOD_ID}_blade0_smear_mesh")
    obj = bpy.data.objects.new(f"{MOD_ID}_blade0_smear", mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    rings = []
    for tf in smear_t:
        rings.append(
            [
                bm.verts.new(
                    blade_point(BLADE_AZIMUTHS[0], sf, cf, tf)
                )
                for sf, cf in (
                    (smear_s[0], smear_c[0]),
                    (smear_s[0], smear_c[1]),
                    (smear_s[1], smear_c[1]),
                    (smear_s[1], smear_c[0]),
                )
            ]
        )
    bm.verts.ensure_lookup_table()
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((rings[0][i], rings[0][j], rings[1][j], rings[1][i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[1])
    bm.to_mesh(mesh)
    bm.free()
    bk.assign_material(obj, transfer)
    bk.add_metric_box_uvs(obj, meters_per_tile=uv(f"{MOD_ID}_blade_transfer"))
    objects.append(obj)
    return objects


# ---------------------------------------------------------------------------
# The cage.
#
# Four bodies and three joints. Each joint is BEAM GEOMETRY, because BeamNG
# has no `hinges` section and inventing one is the pack's oldest tombstone:
#
#   yaw    the yoke's two pivot nodes sit ON the vertical axis and are beamed
#          to a ring of FIXED neck-top nodes. Every one of those beam lengths
#          is preserved by rotation about that axis and by nothing else, so
#          the yoke has exactly one degree of freedom. Stock's swing gate is
#          built this way.
#   tilt   the head's nodes are beamed to the two trunnion nodes, which sit ON
#          the transverse axis. Same argument, one degree of freedom.
#   spin   the rotor collar is beamed to the two hub-axis nodes, which sit ON
#          the fan axis - and that pair is also the jbeam rotator's node1/node2,
#          so the physics core drives the one DOF the geometry leaves open.
#
# The blades are NOT in the rotator group. They hang off the collar on beams
# and are dragged round by it, exactly as stock large_spinner's arms hang off
# its eight-node `spin_center`.
# ---------------------------------------------------------------------------
def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)

    # Beam specs. The rotor's are stiff because a 33 t rotor at 15.39 m pulls
    # hard: at setting 3 the tip sees omega^2 * r = 300 m/s^2, so a tip node
    # of 333 kg is hanging on 100 kN of centripetal load.
    cage.define_beam_spec(
        "structure",
        beamSpring=15_000_000.0,
        beamDamp=1500.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "pivot",
        beamSpring=180_000_000.0,
        beamDamp=6_000.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "rotor",
        beamSpring=250_000_000.0,
        beamDamp=10_000.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    # The blade shell yields before the rotor shaft does. FLT_MAX everywhere
    # would make a bus-sized blade a perfectly rigid bar, which is neither
    # true nor fun; a finite deform lets a blade take a set after a big hit
    # while beamStrength keeps it attached.
    cage.define_beam_spec(
        "blade",
        beamSpring=190_000_000.0,
        beamDamp=9_000.0,
        beamDeform=42_000_000.0,
        beamStrength="FLT_MAX",
    )

    # ---------------- the fixed base ------------------------------------
    # The lattice is the STRUCTURE. It is a rectangular prism and the visible
    # base is a 26 m four-lobed superellipse, so it can never be the whole
    # drivable surface: the skirt below carries the deck out to the outline.
    # The four side faces are skinned too, because a 21.6 m x 1.88 m plinth
    # whose flanks are 5.4 m apart is a slab a 4.5 m car drives straight into
    # and through.
    half = S.BASE_X / 2.0 - 2.20
    base = cage.add_box_lattice(
        "base",
        (-half, -half, S.BASE_UNDERSIDE_Z),
        (half, half, S.DECK_Z),
        subdivisions=(4, 4, 1),
        fixed=True,
        collision=False,
        weight=900.0,
        collision_faces=("top", "north", "south", "east", "west"),
        face_ground_models={
            "top": "asphalt",
            "north": "asphalt",
            "south": "asphalt",
            "east": "asphalt",
            "west": "asphalt",
        },
    )
    # The deck SKIRT: an annulus of collision quads from the lattice's top
    # perimeter out to the visible outline, so the surface you can drive on
    # ends exactly where the slab you can see ends.
    #
    # Without it the drivable top stopped on the +-10.800 ring while the
    # visible deck reached |x| 13.565 and a radius of 17.511: 185 m2 of the
    # 652 m2 deck top - 28 % of it - was a hole a car flung by the blade
    # dropped through, landing on the terrain INSIDE the plinth. The pack's
    # own precedent is high_five's pad skirt.
    # The lattice's top perimeter, walked anticlockwise: 16 nodes.
    perimeter = (
        [(ix, 0) for ix in range(5)]
        + [(4, iy) for iy in range(1, 5)]
        + [(ix, 4) for ix in range(3, -1, -1)]
        + [(0, iy) for iy in range(3, 0, -1)]
    )
    inner_xy = [
        (-half + 2.0 * half * ix / 4.0, -half + 2.0 * half * iy / 4.0)
        for ix, iy in perimeter
    ]

    def outline_radius(theta: float) -> float:
        """base_outline()'s own radius on a bearing, solved not sampled."""

        cx, sy = math.cos(theta), math.sin(theta)
        n = S.BASE_SQUARENESS
        denom = (abs(cx) ** n + abs(sy) ** n) ** (1.0 / n)
        return (
            (S.BASE_X / 2.0)
            / max(denom, 1e-9)
            * (1.0 + 0.115 * (-math.cos(4.0 * theta)))
        )

    # FOUR edge nodes per lattice segment, 64 in all. The skirt's outer boundary
    # is a chord between consecutive edge nodes, so its error against the
    # outline falls with the square of the step: one node per segment leaves the
    # chord 0.9 m inside the diagonal lobes, two leave 0.20 m, four leave 0.05 m
    # - a fifth of the kerb the deck already carries there.
    EDGE_PER_SEGMENT = 4
    edge: list[str] = []
    for index, (x, y) in enumerate(inner_xy):
        nxt = inner_xy[(index + 1) % len(inner_xy)]
        for step in range(EDGE_PER_SEGMENT):
            fraction = step / EDGE_PER_SEGMENT
            bx = x + (nxt[0] - x) * fraction
            by = y + (nxt[1] - y) * fraction
            theta = math.atan2(by, bx)
            radius = outline_radius(theta)
            edge.append(
                cage.add_node(
                    f"deckedge_{len(edge):02d}",
                    (radius * math.cos(theta), radius * math.sin(theta), S.DECK_Z),
                    fixed=True,
                    collision=True,
                    weight=300.0,
                )
            )
    for index in range(len(inner_xy)):
        nxt = (index + 1) % len(inner_xy)
        p_a = base[perimeter[index] + (1,)]
        p_b = base[perimeter[nxt] + (1,)]
        fan = [
            edge[(EDGE_PER_SEGMENT * index + step) % len(edge)]
            for step in range(EDGE_PER_SEGMENT + 1)
        ]
        cage.add_beam(p_a, fan[0], "structure")
        for step in range(EDGE_PER_SEGMENT):
            cage.add_beam(fan[step], fan[step + 1], "structure")
        # Wound anticlockwise in plan, which is the same "up" the lattice's own
        # top face uses. The inner edge is ONE segment, so the outer arc fans
        # off whichever inner node it is nearer.
        pivot = EDGE_PER_SEGMENT // 2
        for step in range(pivot):
            cage.add_triangle(p_a, fan[step], fan[step + 1], ground_model="asphalt")
        cage.add_triangle(p_a, fan[pivot], p_b, ground_model="asphalt")
        for step in range(pivot, EDGE_PER_SEGMENT):
            cage.add_triangle(p_b, fan[step], fan[step + 1], ground_model="asphalt")
    # The four rubber pads. Their UNDERSIDES are the machine's spawn datum:
    # exactly z = 0, which is what test_reference_node_is_the_lowest_node
    # measures against the ref node (the spin_launch tombstone).
    pads = {}
    for label, sx, sy in (("ne", 1, 1), ("nw", -1, 1), ("se", 1, -1), ("sw", -1, -1)):
        pads[label] = cage.add_node(
            f"foot_{label}",
            (sx * S.FOOT_C, sy * S.FOOT_C, 0.0),
            fixed=True,
            collision=True,
            weight=700.0,
        )
        # Tie each pad up into the slab.
        for ix in (0, 4):
            for iy in (0, 4):
                cage.add_beam(pads[label], base[(ix, iy, 0)], "structure")

    # Approach and service ramps. Authored node by node rather than through
    # add_box_lattice, because a lattice is a RECTANGULAR prism: its top face
    # is flat at DECK_Z, which is a wall, not a ramp. Nothing could drive up
    # it. The top row's z is interpolated from the toe to the crest and the
    # collision triangles go on that sloped surface.
    ramps: dict[str, dict] = {}
    RAMP_NY = 4
    for name, cx, sy in (
        ("kickl", -S.KICK_RAMP_X, 1.0),
        ("kickr", S.KICK_RAMP_X, 1.0),
        ("rear", S.REAR_RAMP_X, -1.0),
    ):
        # The SAME crest the visible wedge uses. They used to disagree by
        # 1.58 m along y, which put the drivable ramp 0.41 m below the ramp you
        # can see at the crest and left its outer 1.48 m with no collision at
        # all - every approach run was made with the wheels buried to the axle.
        y_crest = sy * S.RAMP_CREST_Y
        y_toe = sy * (S.RAMP_CREST_Y + S.RAMP_RUN)
        grid: dict[tuple[int, int, int], str] = {}
        for iy in range(RAMP_NY + 1):
            f = iy / RAMP_NY  # 0 at the crest, 1 at the toe
            y = y_crest + (y_toe - y_crest) * f
            z_top = S.DECK_Z * (1.0 - f)
            for ix in range(3):
                x = cx + S.RAMP_W * (ix / 2.0 - 0.5)
                grid[(ix, iy, 1)] = cage.add_node(
                    f"ramp_{name}_{ix}_{iy}_t",
                    (x, y, max(z_top, 0.0)),
                    fixed=True,
                    collision=True,
                    weight=300.0,
                )
                grid[(ix, iy, 0)] = cage.add_node(
                    f"ramp_{name}_{ix}_{iy}_b",
                    (x, y, 0.02),
                    fixed=True,
                    collision=False,
                    weight=300.0,
                )
        ramps[name] = grid
        # Brace it: the ramp is fixed, so the beams are for connectivity and
        # for binding the flexbody, not for stiffness.
        for iy in range(RAMP_NY + 1):
            for ix in range(3):
                cage.add_beam(grid[(ix, iy, 0)], grid[(ix, iy, 1)], "structure")
                if ix < 2:
                    for iz in (0, 1):
                        cage.add_beam(grid[(ix, iy, iz)], grid[(ix + 1, iy, iz)], "structure")
                    cage.add_beam(grid[(ix, iy, 0)], grid[(ix + 1, iy, 1)], "structure")
                if iy < RAMP_NY:
                    for iz in (0, 1):
                        cage.add_beam(grid[(ix, iy, iz)], grid[(ix, iy + 1, iz)], "structure")
                    cage.add_beam(grid[(ix, iy, 0)], grid[(ix, iy + 1, 1)], "structure")
        # The drivable surface. add_quad_both so the ramp is solid from either
        # side without ever emitting the same node triple twice.
        for iy in range(RAMP_NY):
            for ix in range(2):
                cage.add_quad_both(
                    [
                        grid[(ix, iy, 1)],
                        grid[(ix + 1, iy, 1)],
                        grid[(ix + 1, iy + 1, 1)],
                        grid[(ix, iy + 1, 1)],
                    ],
                    ground_model="asphalt",
                )
        # Tie the crest into the deck edge so the cage is one graph and the
        # transition onto the deck has no step.
        edge = 4 if sy > 0 else 0
        for ix in range(3):
            cage.stitch(grid[(ix, 0, 1)], base[(2, edge, 1)])
            cage.stitch(grid[(ix, 0, 0)], base[(2, edge, 0)])

    # The neck, and the fixed ring at its top that carries the yaw pivot.
    neck = cage.add_box_lattice(
        "neck",
        (-S.NECK_R_TOP, -S.NECK_R_TOP, S.DECK_Z),
        (S.NECK_R_TOP, S.NECK_R_TOP, S.NECK_TOP_Z),
        subdivisions=(1, 1, 2),
        fixed=True,
        collision=False,
        weight=1400.0,
        collision_faces=("north", "south", "east", "west"),
    )
    for ix in (0, 1):
        for iy in (0, 1):
            cage.stitch(neck[(ix, iy, 0)], base[(2, 2, 1)])

    neck_ring = []
    for i in range(6):
        a = 2.0 * math.pi * i / 6.0
        neck_ring.append(
            cage.add_node(
                f"neckring_{i}",
                (
                    S.NECK_R_TOP * 0.92 * math.cos(a),
                    S.NECK_R_TOP * 0.92 * math.sin(a),
                    S.NECK_TOP_Z,
                ),
                fixed=True,
                collision=False,
                weight=600.0,
            )
        )
        for ix in (0, 1):
            for iy in (0, 1):
                cage.add_beam(neck_ring[-1], neck[(ix, iy, 2)], "structure")

    # The sweep hydro's ground end: a stanchion on the deck behind the neck.
    yaw_anchor = cage.add_node(
        "yaw_anchor",
        (0.0, -S.YAW_ANCHOR_BACK, S.YAW_ANCHOR_Z),
        fixed=True,
        collision=False,
        weight=S.ACTUATOR_NODE_KG,
    )
    for ix in (1, 2, 3):
        cage.add_beam(yaw_anchor, base[(ix, 0, 1)], "pivot")
        cage.add_beam(yaw_anchor, base[(ix, 1, 1)], "pivot")

    # ---------------- the yoke (free, one DOF about vertical) -----------
    yawpivot_lo = cage.add_node(
        "yawpivot_lo",
        (0.0, 0.0, S.YAWPIVOT_LO_Z),
        fixed=False,
        collision=False,
        weight=S.PIVOT_NODE_KG,
        group="yoke",
    )
    yawpivot_hi = cage.add_node(
        "yawpivot_hi",
        (0.0, 0.0, S.YAWPIVOT_HI_Z),
        fixed=False,
        collision=False,
        weight=S.PIVOT_NODE_KG,
        group="yoke",
    )
    # THE YAW JOINT. Both pivot nodes are ON the axis, so every beam to the
    # fixed ring keeps its length under rotation about that axis - and under
    # nothing else.
    for anchor in neck_ring:
        cage.add_beam(yawpivot_lo, anchor, "pivot")
        cage.add_beam(yawpivot_hi, anchor, "pivot")
    cage.add_beam(yawpivot_lo, yawpivot_hi, "pivot")

    collar = {}
    for i in range(4):
        a = 2.0 * math.pi * i / 4.0 + math.pi / 4.0
        for iz, z in enumerate(S.YOKE_COLLAR_Z):
            node = cage.add_node(
                f"yokecollar_{i}_{iz}",
                (S.YOKE_COLLAR_R * math.cos(a), S.YOKE_COLLAR_R * math.sin(a), z),
                fixed=False,
                collision=True,
                weight=1500.0,
                group="yoke",
            )
            collar[(i, iz)] = node
            cage.add_beam(node, yawpivot_lo, "pivot")
            cage.add_beam(node, yawpivot_hi, "pivot")
    for i in range(4):
        j = (i + 1) % 4
        for iz in (0, 1):
            cage.add_beam(collar[(i, iz)], collar[(j, iz)], "structure")
        cage.add_beam(collar[(i, 0)], collar[(i, 1)], "structure")
        cage.add_beam(collar[(i, 0)], collar[(j, 1)], "structure")
    # The collar's own skin. Same reason as the housing: collision nodes with
    # no collision triangles between them is a hole, not a surface.
    for i in range(4):
        j = (i + 1) % 4
        cage.add_quad_both(
            [collar[(i, 0)], collar[(j, 0)], collar[(j, 1)], collar[(i, 1)]],
            ground_model="metal",
            extra={"dragCoef": 1},
        )

    # Each yoke arm is a 1.51 x 2.30 x 6.84 m slab you can SEE. As two nodes on
    # its centreline it was 6.84 m of nothing: a car-sized box at mid-height
    # contained no node and crossed no triangle, and fell through the arm. It
    # is authored as its real box now. The centreline pair is KEPT - the
    # rotator's `nodeArm:` and the tilt-joint beams name `yoke_arm_r_lo` - and
    # the arm's 4400 kg is REDISTRIBUTED over the ten nodes, not added to.
    arms = {}
    arm_corners: dict[tuple[str, int, int], str] = {}
    ARM_TOTAL_KG = 4400.0
    ARM_CENTRE_KG = 300.0
    ARM_CORNER_KG = (ARM_TOTAL_KG - 2 * ARM_CENTRE_KG) / 8.0
    for side, sx in (("l", -1.0), ("r", 1.0)):
        for iz, z in enumerate((S.YAWPIVOT_HI_Z, S.HUB_Z)):
            node = cage.add_node(
                f"yoke_arm_{side}_{'lo' if iz == 0 else 'hi'}",
                (sx * S.YOKE_HALF_SPAN, 0.0, z),
                fixed=False,
                collision=True,
                weight=ARM_CENTRE_KG,
                group="yoke",
            )
            arms[(side, iz)] = node
            for ic, (dx, dy) in enumerate(
                ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))
            ):
                arm_corners[(side, iz, ic)] = cage.add_node(
                    f"yokearm_{side}_{iz}_{ic}",
                    (
                        sx * S.YOKE_HALF_SPAN + dx * S.YOKE_ARM_T,
                        dy * S.YOKE_ARM_W,
                        z,
                    ),
                    fixed=False,
                    collision=True,
                    weight=ARM_CORNER_KG,
                    group="yoke",
                )
        cage.add_beam(arms[(side, 0)], arms[(side, 1)], "structure")
        for iz in (0, 1):
            for ic in range(4):
                jc = (ic + 1) % 4
                cage.add_beam(
                    arm_corners[(side, iz, ic)],
                    arm_corners[(side, iz, jc)],
                    "structure",
                )
                cage.add_beam(arm_corners[(side, iz, ic)], arms[(side, iz)], "structure")
            cage.add_beam(
                arm_corners[(side, iz, 0)], arm_corners[(side, iz, 2)], "structure"
            )
        for ic in range(4):
            jc = (ic + 1) % 4
            cage.add_beam(
                arm_corners[(side, 0, ic)], arm_corners[(side, 1, ic)], "structure"
            )
            cage.add_beam(
                arm_corners[(side, 0, ic)], arm_corners[(side, 1, jc)], "structure"
            )
            cage.add_quad_both(
                [
                    arm_corners[(side, 0, ic)],
                    arm_corners[(side, 0, jc)],
                    arm_corners[(side, 1, jc)],
                    arm_corners[(side, 1, ic)],
                ],
                ground_model="metal",
                extra={"dragCoef": 1},
            )
        for iz in (0, 1):
            cage.add_quad_both(
                [arm_corners[(side, iz, k)] for k in range(4)],
                ground_model="metal",
                extra={"dragCoef": 1},
            )
        for i in range(4):
            cage.add_beam(arms[(side, 0)], collar[(i, 1)], "structure")
            cage.add_beam(arms[(side, 1)], collar[(i, 1)], "structure")

    trunnion = {}
    for side, sx in (("l", -1.0), ("r", 1.0)):
        trunnion[side] = cage.add_node(
            f"trunnion_{side}",
            (sx * S.TRUNNION_HALF_SPAN, 0.0, S.HUB_Z),
            fixed=False,
            collision=False,
            weight=S.TRUNNION_NODE_KG,
            group="yoke",
        )
        cage.add_beam(trunnion[side], arms[(side, 1)], "pivot")
        cage.add_beam(trunnion[side], arms[(side, 0)], "pivot")
        for i in range(4):
            cage.add_beam(trunnion[side], collar[(i, 1)], "pivot")
    cage.add_beam(trunnion["l"], trunnion["r"], "pivot")

    # The sweep hydro's moving end: a crank pin out on the yoke collar. The
    # hydro is a variable-length BEAM, so the crank's lever arm is what turns
    # a length command into an angle - and what supplies a joint stiffness
    # three orders past anything a torsion spring in this engine ships with.
    yaw_crank_pin = cage.add_node(
        "yaw_crank_pin",
        (S.YAW_CRANK_R, 0.0, S.YAW_PIN_Z),
        fixed=False,
        collision=False,
        weight=S.ACTUATOR_NODE_KG,
        group="yoke",
    )
    for i in range(4):
        cage.add_beam(yaw_crank_pin, collar[(i, 0)], "pivot")
        cage.add_beam(yaw_crank_pin, collar[(i, 1)], "pivot")

    # The tilt hydro's fixed end, on the yoke's rear cross-tie.
    tilt_anchor = cage.add_node(
        "tilt_anchor",
        S.TILT_ANCHOR,
        fixed=False,
        collision=False,
        weight=S.ACTUATOR_NODE_KG,
        group="yoke",
    )
    for side in ("l", "r"):
        cage.add_beam(tilt_anchor, arms[(side, 1)], "pivot")
        cage.add_beam(tilt_anchor, trunnion[side], "pivot")

    # ---------------- the head (free, one DOF about the trunnion) -------
    head_ring = {}
    for iy, y in enumerate((S.HSG_REAR_Y, 0.0, S.HSG_FRONT_Y)):
        radius = (
            S.HSG_R_REAR
            + (S.HSG_R_FRONT - S.HSG_R_REAR) * (y - S.HSG_REAR_Y) / S.HSG_L
        )
        for i in range(6):
            a = 2.0 * math.pi * i / 6.0
            node = cage.add_node(
                f"hsg_{iy}_{i}",
                (radius * math.cos(a), y, S.HUB_Z + radius * math.sin(a)),
                fixed=False,
                collision=True,
                weight=1900.0,
                group="head",
            )
            head_ring[(iy, i)] = node
    for iy in range(3):
        for i in range(6):
            j = (i + 1) % 6
            cage.add_beam(head_ring[(iy, i)], head_ring[(iy, j)], "structure")
            if iy < 2:
                cage.add_beam(head_ring[(iy, i)], head_ring[(iy + 1, i)], "structure")
                cage.add_beam(head_ring[(iy, i)], head_ring[(iy + 1, j)], "structure")
    # Cross-brace the middle ring so the housing is a solid, not a tube.
    for i in range(3):
        cage.add_beam(head_ring[(1, i)], head_ring[(1, i + 3)], "structure")

    # THE HOUSING GETS ITS OWN SKIN. Without triangles the head is a GHOST:
    # BeamNG collides node against TRIANGLE, so a body carrying only collision
    # nodes can push a car only when one of its own nodes happens to land
    # inside the car shell - and these rings are 5.70 m apart, wider than a
    # car. A car thrown up by a blade (30 m/s of vertical is 46 m of rise)
    # passes clean through the z = 11..23 m band where 92 tonnes of visible
    # motor housing lives.
    #
    # Triangles alone close it, with no new lattice: a car node cannot enter
    # the housing without crossing the skin. dragCoef is STATED because the
    # engine default is 100, i.e. Cd 1.0, and the head is a free body on the
    # trunnion - a default-drag skin would load the tilt hydro with wind.
    HEAD_SKIN = {"dragCoef": 1}
    for iy in (0, 1):
        for i in range(6):
            j = (i + 1) % 6
            cage.add_quad_both(
                [
                    head_ring[(iy, i)],
                    head_ring[(iy, j)],
                    head_ring[(iy + 1, j)],
                    head_ring[(iy + 1, i)],
                ],
                ground_model="metal",
                extra=HEAD_SKIN,
            )
    # Both hexagon ends get a real cap, fanned off a centre node on the axis,
    # so the housing is a closed solid rather than an open pipe.
    head_caps = {}
    for iy, y in ((0, S.HSG_REAR_Y), (2, S.HSG_FRONT_Y)):
        head_caps[iy] = cage.add_node(
            f"hsg_cap_{iy}",
            (0.0, y, S.HUB_Z),
            fixed=False,
            collision=True,
            weight=900.0,
            group="head",
        )
        for i in range(6):
            cage.add_beam(head_caps[iy], head_ring[(iy, i)], "structure")
        for i in range(6):
            j = (i + 1) % 6
            cage.add_triangle(
                head_caps[iy],
                head_ring[(iy, i)],
                head_ring[(iy, j)],
                ground_model="metal",
                extra=HEAD_SKIN,
            )
            cage.add_triangle(
                head_caps[iy],
                head_ring[(iy, j)],
                head_ring[(iy, i)],
                ground_model="metal",
                extra=HEAD_SKIN,
            )

    # THE TILT JOINT. Every head node is beamed to BOTH trunnion nodes, and
    # both sit on the transverse axis, so the head can only rotate about it.
    for key, node in head_ring.items():
        for side in ("l", "r"):
            cage.add_beam(node, trunnion[side], "pivot")

    # The motor's torque reaction nodes: where the motor pushes back. Their
    # own nodes rather than aliased ring members, because the authored motor
    # block names hsg_rr_0..2 and check_jbeam_section_refs resolves those
    # names against this cage.
    reaction = []
    for i in range(3):
        a = 2.0 * math.pi * i / 3.0 + math.pi / 6.0
        node = cage.add_node(
            f"hsg_rr_{i}",
            (
                S.HSG_R_REAR * 0.62 * math.cos(a),
                S.HSG_REAR_Y + 1.60,
                S.HUB_Z + S.HSG_R_REAR * 0.62 * math.sin(a),
            ),
            fixed=False,
            collision=False,
            weight=S.MOTOR_BELL_KG / 3.0,
            group="head",
        )
        reaction.append(node)
        for k in range(6):
            cage.add_beam(node, head_ring[(0, k)], "structure")
            cage.add_beam(node, head_ring[(1, k)], "structure")
    for i in range(3):
        cage.add_beam(reaction[i], reaction[(i + 1) % 3], "structure")

    # The fan axis: the rotator's node1 / node2. Both ON the axis, both free,
    # both on the head - which is what lets the whole rotor ride a head that
    # yaws and tilts. A rotator on a moving hub is a steered wheel.
    hubaxis_rear = cage.add_node(
        "hubaxis_rear",
        (0.0, S.HUB_RING_Y[0], S.HUB_Z),
        fixed=False,
        collision=False,
        weight=S.PIVOT_NODE_KG,
        group="head",
    )
    hubaxis_front = cage.add_node(
        "hubaxis_front",
        (0.0, S.HUB_RING_Y[1], S.HUB_Z),
        fixed=False,
        collision=False,
        weight=S.PIVOT_NODE_KG,
        group="head",
    )
    for node in (hubaxis_rear, hubaxis_front):
        for key in ((0, 0), (0, 2), (0, 4), (1, 1), (1, 3), (1, 5), (2, 0), (2, 2), (2, 4)):
            cage.add_beam(node, head_ring[key], "pivot")
    cage.add_beam(hubaxis_rear, hubaxis_front, "pivot")

    # The tilt hydro's moving end, on a lug under the head.
    tilt_pin = cage.add_node(
        "tilt_pin",
        (S.TILT_PIN[0], S.TILT_PIN[1], S.HUB_Z + S.TILT_PIN[2]),
        fixed=False,
        collision=False,
        weight=S.ACTUATOR_NODE_KG,
        group="head",
    )
    for key in ((0, 3), (0, 4), (1, 3), (1, 4), (2, 3), (2, 4)):
        cage.add_beam(tilt_pin, head_ring[key], "pivot")

    # ---------------- the rotor collar (the ROTATOR group) --------------
    # Eight nodes, on the fan axis, beamed to the two axis nodes and to each
    # other and to NOTHING else on the head. This is the only group the jbeam
    # rotator names; the blades are dragged by it.
    collar_nodes = {}
    for iy, y in enumerate(S.HUB_RING_Y):
        for i in range(4):
            a = 2.0 * math.pi * i / 4.0 + math.pi / 4.0
            node = cage.add_node(
                f"rotorcollar_{iy}_{i}",
                (
                    S.HUB_RING_R * math.cos(a),
                    y,
                    S.HUB_Z + S.HUB_RING_R * math.sin(a),
                ),
                fixed=False,
                collision=True,
                weight=S.HUB_KG / 8.0,
                group="rotor",
                self_collision=False,
            )
            collar_nodes[(iy, i)] = node
            cage.add_beam(node, hubaxis_rear, "rotor")
            cage.add_beam(node, hubaxis_front, "rotor")
    for iy in (0, 1):
        for i in range(4):
            j = (i + 1) % 4
            cage.add_beam(collar_nodes[(iy, i)], collar_nodes[(iy, j)], "rotor")
    for i in range(4):
        j = (i + 1) % 4
        cage.add_beam(collar_nodes[(0, i)], collar_nodes[(1, i)], "rotor")
        cage.add_beam(collar_nodes[(0, i)], collar_nodes[(1, j)], "rotor")
    # The hub is a SOLID, not a ring of points. A car that lands dead centre on
    # the rotor would otherwise find nothing there: collision needs triangles,
    # and eight collision nodes with nothing spanning them is a hole. The
    # collar turns at HUB_RING_R, so its own surface speed at the top setting
    # is 14.1 m/s - a fifth of the tip - and selfCollision is already off on
    # this group, so the skin cannot fight the blades bolted to it.
    for i in range(4):
        j = (i + 1) % 4
        cage.add_quad_both(
            [
                collar_nodes[(0, i)],
                collar_nodes[(0, j)],
                collar_nodes[(1, j)],
                collar_nodes[(1, i)],
            ],
            ground_model="metal",
            extra={"dragCoef": 7},
        )
    for iy in (0, 1):
        cage.add_quad_both(
            [collar_nodes[(iy, k)] for k in range(4)],
            ground_model="metal",
            extra={"dragCoef": 7},
        )

    # ---------------- the blades ----------------------------------------
    # Six stations, four corners each. The corner positions come from the SAME
    # blade_point() the visual mesh uses, so the collision hull and the thing
    # you can see are the same twisted paddle.
    blade_mass = (S.BLADE_SHELL_KG + S.ROOT_FERRULE_KG + S.TIP_CAP_KG)
    per_node = blade_mass / (len(S.BLADE_STATIONS_S) * 4)
    for b, azimuth in enumerate(BLADE_AZIMUTHS):
        ring_nodes = []
        for si, s in enumerate(S.BLADE_STATIONS_S):
            loop = []
            for ci, (cf, tf) in enumerate(
                ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))
            ):
                loop.append(
                    cage.add_node(
                        f"blade{b}_{si}_{ci}",
                        blade_point(azimuth, s, cf, tf),
                        fixed=False,
                        collision=True,
                        weight=per_node,
                        group="blade",
                        self_collision=False,
                        friction=0.6,
                    )
                )
            ring_nodes.append(loop)
            # section perimeter + both diagonals: a rigid quad, not a hinge
            for ci in range(4):
                cj = (ci + 1) % 4
                cage.add_beam(loop[ci], loop[cj], "blade")
            cage.add_beam(loop[0], loop[2], "blade")
            cage.add_beam(loop[1], loop[3], "blade")
        # spanwise, with X bracing between adjacent stations
        for r0, r1 in zip(ring_nodes, ring_nodes[1:]):
            for ci in range(4):
                cj = (ci + 1) % 4
                cage.add_beam(r0[ci], r1[ci], "blade")
                cage.add_beam(r0[ci], r1[cj], "blade")
                cage.add_beam(r0[cj], r1[ci], "blade")
        # root into the collar: the blade hangs off the drive ring
        for ci in range(4):
            for iy in (0, 1):
                for k in range(4):
                    cage.add_beam(ring_nodes[0][ci], collar_nodes[(iy, k)], "rotor")

        # Collision. add_quad_both emits the higher tiling wound up and the
        # lower wound down - four DISTINCT triples - because emitting the same
        # node triple twice spikes the solver and pops tyres (the TWIN-TILING
        # law). dragCoef is set deliberately: a fan's load IS its blades, and
        # the engine's default of 100 would leave the motor fighting its own
        # rotor for a third of its torque.
        for r0, r1 in zip(ring_nodes, ring_nodes[1:]):
            for ci in range(4):
                cj = (ci + 1) % 4
                cage.add_quad_both(
                    [r0[ci], r0[cj], r1[cj], r1[ci]],
                    ground_model="metal",
                    extra={"dragCoef": 7},
                )
        cage.add_quad_both(
            list(reversed(ring_nodes[-1])), ground_model="metal", extra={"dragCoef": 7}
        )

    # ---------------- console anchors -----------------------------------
    # Every cap gets its OWN frame pair: the triggers2 box basis is
    # (idX - idRef, idY - idRef), so one shared pair skews and translates the
    # hitbox of every cap not co-located with it.
    for button in S.PANEL_BUTTONS:
        px, py, pz = button["position"]
        on_head = button["id"] == "plunger"
        group = "head" if on_head else None
        fixed = not on_head
        weight = 90.0
        anchor = cage.add_node(
            f"panelbtn_{button['id']}",
            (px, py, pz),
            fixed=fixed,
            collision=False,
            weight=weight,
            group=group,
        )
        fx = cage.add_node(
            f"panelfx_{button['id']}",
            (px, py + 0.42, pz),
            fixed=fixed,
            collision=False,
            weight=weight,
            group=group,
        )
        fy = cage.add_node(
            f"panelfy_{button['id']}",
            (px, py, pz + 0.42),
            fixed=fixed,
            collision=False,
            weight=weight,
            group=group,
        )
        if on_head:
            for key in ((2, 0), (2, 1), (2, 5), (1, 0), (1, 1), (1, 5)):
                for node in (anchor, fx, fy):
                    cage.add_beam(node, head_ring[key], "structure")
        else:
            for ix in (0, 1):
                for node in (anchor, fx, fy):
                    cage.add_beam(node, base[(ix, 1, 1)], "structure")
                    cage.add_beam(node, base[(ix, 2, 1)], "structure")

    # ---------------- refnodes, envelope, base nodes --------------------
    # ref is on a pad underside at z = 0, so the prop spawns on its feet.
    # ref sits on a pad UNDERSIDE at z = 0, so the machine spawns on its feet
    # rather than 0.52 m in the air. vehicle_frame is a 180-degree yaw,
    # (x, y, z) -> (-x, -y, z), so a node that must land at vehicle +Y has to
    # be authored at a SMALLER y than ref, and vehicle +X (left) at a smaller
    # authored x. ref is the +Y +X pad, back the -Y one, left the -X one.
    cage.set_refnodes_existing(
        ref=pads["ne"],
        back=pads["se"],
        left=pads["nw"],
        up=base[(2, 2, 1)],
    )
    cage.set_spawn_envelope(
        [
            base[(0, 0, 0)],
            base[(4, 0, 0)],
            base[(0, 4, 0)],
            base[(4, 4, 0)],
            base[(0, 0, 1)],
            base[(4, 0, 1)],
            base[(0, 4, 1)],
            base[(4, 4, 1)],
        ]
    )
    cage.auto_base_nodes()
    return cage


def main() -> None:
    bk.reset_scene()
    materials = build_materials()

    base_objects = build_base(materials)
    yoke_objects = build_yoke(materials)
    head_objects = build_head(materials)
    rotor_objects = build_rotor(materials)

    visual = bk.export_multi_flexbody(
        MOD_ID,
        VEHICLE_DIR / f"{MOD_ID}.dae",
        {
            f"{MOD_ID}_visual": base_objects,
            f"{MOD_ID}_yoke_mesh": yoke_objects,
            f"{MOD_ID}_head_mesh": head_objects,
            f"{MOD_ID}_rotor_mesh": rotor_objects,
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
        visual_dae_relative=f"vehicles/{MOD_ID}/{MOD_ID}.dae",
        visual_mesh_name=f"{MOD_ID}_visual",
        parts=[],
        palette=spec.PALETTE,
        panel={
            "frame_x_node": f"{MOD_ID}_panelfx_dial_cw",
            "frame_y_node": f"{MOD_ID}_panelfy_dial_cw",
            "button_size": 0.60,
            "buttons": [
                {
                    "id": button["id"],
                    "title": button["title"],
                    "node": f"{MOD_ID}_panelbtn_{button['id']}",
                    "frame_x_node": f"{MOD_ID}_panelfx_{button['id']}",
                    "frame_y_node": f"{MOD_ID}_panelfy_{button['id']}",
                    "size": button["size"],
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
        flexbodies_extra=[
            {"mesh": f"{MOD_ID}_yoke_mesh", "groups": ["yoke"]},
            {"mesh": f"{MOD_ID}_head_mesh", "groups": ["head"]},
            {"mesh": f"{MOD_ID}_rotor_mesh", "groups": ["rotor", "blade"]},
        ],
    )
    # The selector picture: three-quarter from the approach side, low enough
    # that the machine towers and the missing guard is the first thing you
    # notice.
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(30.0, 58.0, 16.0),
        look_at=(0.0, 6.0, 15.0),
    )
    structure = cage.structure()
    print(
        f"GIANT_FAN generator complete: {len(structure['nodes'])} nodes, "
        f"{len(structure['beams'])} beams, {len(structure['triangles'])} triangles"
    )


if __name__ == "__main__":
    main()
