"""Deterministic Blender generator for Hot Potato.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/hot_potato/blender/create_hot_potato.py
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))

import bpy  # noqa: E402
import spec  # noqa: E402
from mathutils import Vector  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

AHX = spec.APRON_HALF_X
AHY = spec.APRON_HALF_Y
ATZ = spec.APRON_TOP_Z
POST_X = spec.POST_X
POST_HALF = spec.POST_HALF
POST_TOP_Z = spec.POST_TOP_Z
HHX = spec.HEADER_HALF_X
HHY = spec.HEADER_HALF_Y
HZ0 = spec.HEADER_Z0
HZ1 = spec.HEADER_Z1
HOME = spec.POTATO_HOME

# The tuber's silhouette: a fixed bank of spherical ripples over the
# ellipsoid, drawn once from a seeded RNG so the shape is identical on every
# machine, forever.
#
# The frequency band is the whole thing. Each entry displaces by
# sin(dot(direction, axis) * pi + phase), so |axis| IS the number of half
# cycles across the sphere - and the first cut used |axis| up to 3.4 for the
# lumps and 11 for the crinkle, which is not a potato, it is a rock: the
# silhouette came out jagged and flat-topped, closer to a pitta than a tuber.
# A real potato is smooth at every scale you can see from a car; its
# character is a few broad swellings, not high-frequency noise.
_SHAPE_RNG = random.Random(20260814)  # noqa: S311 - shape authoring, not crypto
LUMPS = [
    (
        Vector((
            _SHAPE_RNG.uniform(-1.0, 1.0),
            _SHAPE_RNG.uniform(-1.0, 1.0),
            _SHAPE_RNG.uniform(-1.0, 1.0),
        )).normalized() * _SHAPE_RNG.uniform(0.55, 1.45),
        _SHAPE_RNG.uniform(0.0, math.tau),
        _SHAPE_RNG.uniform(0.030, 0.070),
    )
    for _ in range(6)
]
# One octave up: the gentle undulation that keeps the surface from being a
# clean arc anywhere, still well below the scale that reads as damage.
CRINKLE = [
    (
        Vector((
            _SHAPE_RNG.uniform(-1.0, 1.0),
            _SHAPE_RNG.uniform(-1.0, 1.0),
            _SHAPE_RNG.uniform(-1.0, 1.0),
        )).normalized() * _SHAPE_RNG.uniform(1.9, 3.2),
        _SHAPE_RNG.uniform(0.0, math.tau),
        _SHAPE_RNG.uniform(0.008, 0.017),
    )
    for _ in range(8)
]
EYE_COUNT = 11
EYE_DEPTH = 0.042
EYE_SIGMA = 0.16
BROW_GAIN = 0.40

POTATO_SEGMENTS = 96
POTATO_RINGS = 64


def eye_directions() -> list[Vector]:
    """Unit directions for the buds, on a golden-angle spiral.

    Real eyes crowd toward the bud end and sit on a loose spiral, never on a
    grid. The same distribution is used by the potato_skin texture family, so
    the modelled dimples and the painted ones are the same idea at two
    scales (they are deliberately NOT registered to each other - a UV-exact
    match would need the texture to know the mesh's unwrap, and the eye is
    read as a dimple with a dark centre either way).
    """

    directions: list[Vector] = []
    for index in range(EYE_COUNT):
        # Bias z toward the +X (bud) end rather than spreading evenly.
        t = (index + 0.5) / EYE_COUNT
        z = 1.0 - 2.0 * (t ** 1.35)
        radius = math.sqrt(max(0.0, 1.0 - z * z))
        theta = index * 2.399963229728653
        directions.append(Vector((
            radius * math.cos(theta),
            radius * math.sin(theta),
            z,
        )).normalized())
    return directions


def sculpt_potato(obj: bpy.types.Object) -> None:
    """Displace a unit sphere into a tuber, in place.

    Everything is radial on the UNIT sphere and the triaxial scale is applied
    afterwards, so lump amplitudes stay proportional to the tuber instead of
    stretching with its long axis.
    """

    eyes = eye_directions()
    mesh = obj.data
    for vertex in mesh.vertices:
        direction = vertex.co.normalized()
        radius = 1.0
        for axis, phase, amplitude in LUMPS:
            radius += amplitude * math.sin(direction.dot(axis) * math.pi + phase)
        for axis, phase, amplitude in CRINKLE:
            radius += amplitude * math.sin(direction.dot(axis) * math.pi + phase)
        for eye in eyes:
            # Angular distance to the bud, so the dimple stays round on the
            # sphere rather than smearing near the poles.
            angle = math.acos(max(-1.0, min(1.0, direction.dot(eye))))
            radius -= EYE_DEPTH * math.exp(-((angle / EYE_SIGMA) ** 2))
            # The brow ridge: the raised lip just outside the bowl is what
            # separates a real eye from a drilled hole.
            brow = (angle - EYE_SIGMA * 1.45) / (EYE_SIGMA * 0.62)
            radius += EYE_DEPTH * BROW_GAIN * math.exp(-(brow ** 2))
        vertex.co = direction * radius


def panel_uvs(obj: bpy.types.Object, half_x: float, half_z: float) -> None:
    """Map a flat board's faces to the FULL 0..1 texture in x/z.

    Blender's primitive cube unwraps its six faces into separate regions of
    UV space, so a sign board left on default UVs shows a sliver of the map
    rather than the artwork - the first render put "HOT POTATO" as a few blue
    marks in the corner. bk.add_metric_box_uvs is no help here either: it is
    deliberately metric and origin-relative, so a centred board would sample
    -0.5..0.5 and split the lettering across the wrap seam.
    """

    mesh = obj.data
    layer = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            co = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            layer.data[loop_index].uv = (
                0.5 + co.x / (2.0 * half_x),
                0.5 + co.z / (2.0 * half_z),
            )


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def build_visual(materials) -> list:
    concrete = materials[f"{MOD_ID}_concrete"]
    steel = materials[f"{MOD_ID}_steel"]
    red = materials[f"{MOD_ID}_paint_red"]
    hazard = materials[f"{MOD_ID}_hazard"]
    sign = materials[f"{MOD_ID}_sign"]

    objects = []
    objects.append(
        bk.add_box(
            f"{MOD_ID}_apron",
            (0.0, 0.0, ATZ / 2),
            (2 * AHX, 2 * AHY, ATZ),
            concrete,
            bevel=0.0,
            metric_uv=(3.0, 3.0),
        )
    )
    # Approach chevrons painted on the apron, pointing through the gate.
    for index in range(4):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_apron_chevron_{index}",
                (0.0, -5.6 + index * 1.5, ATZ + 0.004),
                (5.4, 0.42, 0.008),
                hazard,
                bevel=0.0,
                metric_uv=(1.2, 0.5),
            )
        )

    for side, sx in (("w", -POST_X), ("e", POST_X)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_post_{side}",
                (sx, 0.0, POST_TOP_Z / 2),
                (2 * POST_HALF, 2 * POST_HALF, POST_TOP_Z),
                steel,
                bevel=0.05,
                metric_uv=(1.6, 1.6),
            )
        )
        # Hazard collar at bumper height, where a post actually gets hit.
        objects.append(
            bk.add_box(
                f"{MOD_ID}_post_collar_{side}",
                (sx, 0.0, 0.62),
                (2 * POST_HALF + 0.06, 2 * POST_HALF + 0.06, 1.05),
                hazard,
                bevel=0.02,
                metric_uv=(0.9, 0.9),
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_post_base_{side}",
                (sx, 0.0, 0.09),
                (2 * POST_HALF + 0.44, 2 * POST_HALF + 0.44, 0.18),
                steel,
                bevel=0.03,
                metric_uv=(1.2, 1.2),
            )
        )
        # Beacon housing on the cap: dressing only. The beacon the player
        # actually sees is a real light on the CARRIER, made at runtime.
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_post_lamp_{side}",
                (sx, 0.0, POST_TOP_Z + 0.18),
                0.24,
                0.36,
                red,
                vertices=16,
            )
        )

    objects.append(
        bk.add_box(
            f"{MOD_ID}_header",
            (0.0, 0.0, (HZ0 + HZ1) / 2),
            (2 * HHX, 2 * HHY, HZ1 - HZ0),
            steel,
            bevel=0.05,
            metric_uv=(2.0, 2.0),
        )
    )
    # 9.4 x 0.98 m board = 9.59:1, which is the aspect the marquee family
    # draws its lettering at. A sign panel at any other aspect gets the text
    # squashed, because the family stretches one strip into the square map.
    sign_face = bk.add_box(
        f"{MOD_ID}_sign_face",
        (0.0, -HHY - 0.05, spec.SIGN_MID_Z),
        (2 * spec.SIGN_HALF_X, 0.1, 2 * spec.SIGN_HALF_Z),
        sign,
        bevel=0.0,
    )
    panel_uvs(sign_face, spec.SIGN_HALF_X, spec.SIGN_HALF_Z)
    objects.append(sign_face)
    objects.append(
        bk.add_box(
            f"{MOD_ID}_sign_frame",
            (0.0, -HHY - 0.03, spec.SIGN_MID_Z),
            (2 * spec.SIGN_HALF_X + 0.16, 0.08, 2 * spec.SIGN_HALF_Z + 0.16),
            red,
            bevel=0.02,
        )
    )
    # The release claw the potato hangs under at idle.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_claw_mount",
            (0.0, 0.0, HZ0 - 0.16),
            (0.7, 0.7, 0.32),
            red,
            bevel=0.04,
        )
    )
    for index, angle in enumerate((0.0, math.pi / 2)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_claw_arm_{index}",
                (0.0, 0.0, HZ0 - 0.5),
                (0.9, 0.12, 0.5),
                steel,
                bevel=0.03,
                rotation=(0.0, 0.0, angle),
            )
        )
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    skin = materials[f"{MOD_ID}_potato"]
    potato = bk.add_sphere(
        f"{MOD_ID}_potato_body",
        HOME,
        1.0,
        skin,
        segments=POTATO_SEGMENTS,
        rings=POTATO_RINGS,
    )
    sculpt_potato(potato)
    # Triaxial scale AFTER the radial sculpt, so lump amplitudes are
    # proportional to the tuber rather than stretched along its long axis.
    potato.scale = (spec.POTATO_SEMI_X, spec.POTATO_SEMI_Y, spec.POTATO_SEMI_Z)
    bpy.ops.object.select_all(action="DESELECT")
    potato.select_set(True)
    bpy.context.view_layer.objects.active = potato
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # Re-assert smooth shading: the sculpt moved every vertex, and a faceted
    # hero object is the one thing a 2048 skin map cannot rescue. The
    # join-and-export path flattens Blender's smoothing marks anyway, so the
    # real defence is the 96 x 64 segment count above.
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(60.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    potato.select_set(False)
    return {"potato": {"objects": [potato], "pivot": HOME}}


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    apron = cage.add_box_lattice(
        "apron",
        (-AHX, -AHY, 0.0),
        (AHX, AHY, ATZ),
        subdivisions=(2, 4, 1),
        fixed=True,
        collision=False,
        collision_faces=("top",),
        face_ground_models={"top": "asphalt"},
    )
    posts = {}
    for side, sx in (("w", -POST_X), ("e", POST_X)):
        posts[side] = cage.add_box_lattice(
            f"post_{side}",
            (sx - POST_HALF, -POST_HALF, 0.0),
            (sx + POST_HALF, POST_HALF, POST_TOP_Z),
            subdivisions=(1, 1, 3),
            fixed=True,
            collision=False,
            collision_faces=("north", "south", "east", "west", "top"),
        )
    header = cage.add_box_lattice(
        "header",
        (-HHX, -HHY, HZ0),
        (HHX, HHY, HZ1),
        subdivisions=(4, 1, 1),
        fixed=True,
        collision=False,
    )

    # One connected graph. Each post's four base corners tie to the apron
    # edge beside it; each post cap ties to the header end above it. The
    # apron is 2 x 4 cells (ix 0..2, iy 0..4) and the header 4 x 1 (ix 0..4).
    for side, apron_ix in (("w", 0), ("e", 2)):
        for corner_x in (0, 1):
            for corner_y in (0, 1):
                base = posts[side][(corner_x, corner_y, 0)]
                for apron_iy in (1, 2, 3):
                    cage.stitch(base, apron[(apron_ix, apron_iy, 0)])
                    cage.stitch(base, apron[(apron_ix, apron_iy, 1)])
    for side, header_ix in (("w", 0), ("e", 4)):
        for corner_x in (0, 1):
            for corner_y in (0, 1):
                cap = posts[side][(corner_x, corner_y, 3)]
                for header_iz in (0, 1):
                    cage.stitch(cap, header[(header_ix, corner_y, header_iz)])

    cage.set_refnodes_existing(
        ref=apron[(1, 2, 0)],
        back=apron[(1, 1, 0)],
        left=apron[(0, 2, 0)],
        up=apron[(1, 2, 1)],
    )
    # The envelope rides the POSTS, not the apron: set_spawn_envelope forces
    # collision on its eight corners, and a collidable node on the driveable
    # apron edge is the tyre-slicer class the pack has already paid for.
    cage.set_spawn_envelope(
        [
            posts["w"][(0, 0, 0)],
            posts["w"][(0, 1, 0)],
            posts["w"][(0, 0, 3)],
            posts["w"][(0, 1, 3)],
            posts["e"][(1, 0, 0)],
            posts["e"][(1, 1, 0)],
            posts["e"][(1, 0, 3)],
            posts["e"][(1, 1, 3)],
        ]
    )
    cage.auto_base_nodes()
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
        behavior={
            "tunables": behavior,
            "triggers": spec.TRIGGERS,
            "effects": spec.EFFECTS,
            "camera_distance": behavior.get("camera_distance", 30.0),
        },
    )
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(9.5, -16.0, 6.4),
        look_at=(0.0, 0.0, 3.8),
    )
    print(f"HOT_POTATO generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
