"""Deterministic Blender generator for The Vacuum Cleaner of Doom.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/vacuum_of_doom/blender/create_vacuum_of_doom.py
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

DRUM_Y = spec.DRUM_CENTER_Y
DRUM_R = spec.DRUM_RADIUS

HOSE_POINTS = [
    (0.0, 2.9, 6.2),
    (0.0, 0.8, 4.6),
    (0.0, -1.2, 3.0),
    (0.0, -2.4, 1.9),
    (0.0, -3.2, 1.3),
]


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def add_segment(name, start, end, radius, material_value, vertices=16):
    """Cylinder between two points in the X=0 plane, rotated about X."""

    dy = end[1] - start[1]
    dz = end[2] - start[2]
    length = math.hypot(dy, dz)
    angle = -math.atan2(dy, dz)
    center = (
        (start[0] + end[0]) / 2,
        (start[1] + end[1]) / 2,
        (start[2] + end[2]) / 2,
    )
    return (
        bk.add_cylinder(
            name,
            center,
            radius,
            length,
            material_value,
            vertices=vertices,
            axis="Z",
            bevel=0.0,
            radius_x=None,
            radius_y=None,
        ),
        angle,
        center,
    )


def build_visual(materials) -> list:
    orange = materials[f"{MOD_ID}_vac_orange"]
    charcoal = materials[f"{MOD_ID}_charcoal"]
    hose_gray = materials[f"{MOD_ID}_hose_gray"]
    steel = materials[f"{MOD_ID}_steel"]
    cream = materials[f"{MOD_ID}_cream"]

    objects = []
    # Caster base deck and casters.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_base_deck",
            (0.0, DRUM_Y, 0.55),
            (8.0, 8.4, 0.5),
            charcoal,
            bevel=0.1,
            metric_uv=(2.0, 2.0),
        )
    )
    for index, (cx, cy) in enumerate(
        ((-3.3, DRUM_Y - 3.5), (3.3, DRUM_Y - 3.5), (-3.3, DRUM_Y + 3.5), (3.3, DRUM_Y + 3.5))
    ):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_caster_{index}",
                (cx, cy, 0.3),
                0.3,
                0.25,
                steel,
                vertices=14,
                axis="X",
            )
        )
    # Canister drum with latch band and dome lid.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drum",
            (0.0, DRUM_Y, 3.9),
            DRUM_R,
            6.2,
            orange,
            vertices=28,
            metric_uv=(2.3, 2.3),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drum_band",
            (0.0, DRUM_Y, 1.05),
            DRUM_R + 0.08,
            0.5,
            charcoal,
            vertices=28,
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_lid",
            (0.0, DRUM_Y, 7.25),
            DRUM_R + 0.15,
            0.7,
            charcoal,
            vertices=28,
        )
    )
    for index in range(4):
        angle = math.pi / 4 + index * math.pi / 2
        objects.append(
            bk.add_box(
                f"{MOD_ID}_latch_{index}",
                (
                    math.cos(angle) * (DRUM_R + 0.12),
                    DRUM_Y + math.sin(angle) * (DRUM_R + 0.12),
                    6.9,
                ),
                (0.35, 0.25, 0.8),
                steel,
                bevel=0.04,
                rotation=(0.0, 0.0, angle),
            )
        )
    # Ribbed hose from the lid down to the nozzle bell.
    for index in range(len(HOSE_POINTS) - 1):
        start = HOSE_POINTS[index]
        end = HOSE_POINTS[index + 1]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        length = math.hypot(dy, dz)
        angle = -math.atan2(dy, dz)
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_hose_seg_{index}",
                ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, (start[2] + end[2]) / 2),
                0.72,
                length,
                hose_gray,
                vertices=16,
                axis="Z",
                bevel=0.0,
                metric_uv=(0.9, 0.9),
            )
        )
        objects[-1].rotation_euler = (angle, 0.0, 0.0)
        import bpy

        bpy.context.view_layer.objects.active = objects[-1]
        objects[-1].select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        objects[-1].select_set(False)
        objects.append(
            bk.add_torus(
                f"{MOD_ID}_hose_ring_{index}",
                start,
                0.74,
                0.1,
                charcoal,
                rotation=(angle, 0.0, 0.0),
                major_segments=16,
                minor_segments=8,
            )
        )
    # Nozzle bell: a flattened cone whose wide mouth faces -Y.
    objects.append(
        bk.add_cone(
            f"{MOD_ID}_nozzle_bell",
            (0.0, -3.3, 1.1),
            2.3,
            0.75,
            1.7,
            charcoal,
            vertices=22,
            rotation=(-math.pi / 2, 0.0, 0.0),
        )
    )
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_nozzle_rim",
            (0.0, -4.15, 1.1),
            2.25,
            0.16,
            steel,
            rotation=(-math.pi / 2, 0.0, 0.0),
            major_segments=22,
            minor_segments=10,
        )
    )
    # Exhaust stack angled 25 degrees up at the rear.
    exhaust_dir = spec.EXHAUST_DIR
    angle = -math.atan2(exhaust_dir[1], exhaust_dir[2])
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_exhaust_pipe",
            (0.0, 10.1, 4.6),
            0.72,
            2.4,
            steel,
            vertices=18,
            axis="Z",
            bevel=0.0,
        )
    )
    objects[-1].rotation_euler = (angle, 0.0, 0.0)
    import bpy

    bpy.context.view_layer.objects.active = objects[-1]
    objects[-1].select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    objects[-1].select_set(False)
    # Power switch panel and decal stripe.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_switch_panel",
            (0.0, DRUM_Y - DRUM_R - 0.1, 5.4),
            (1.6, 0.3, 1.0),
            cream,
            bevel=0.06,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_switch",
            (0.0, DRUM_Y - DRUM_R - 0.28, 5.4),
            (0.5, 0.2, 0.5),
            orange,
            bevel=0.04,
        )
    )
    # Approach lane chevrons pointing at the nozzle.
    for index, cy in enumerate((-8.0, -12.0, -16.0)):
        for side in (-1, 1):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_chevron_{index}_{'l' if side < 0 else 'r'}",
                    (side * 1.1, cy, 0.06),
                    (2.4, 0.5, 0.06),
                    cream,
                    bevel=0.0,
                    rotation=(0.0, 0.0, side * math.radians(35.0)),
                )
            )
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    charcoal = materials[f"{MOD_ID}_charcoal"]
    steel = materials[f"{MOD_ID}_steel"]

    parts: dict[str, dict[str, object]] = {}
    cap = bk.add_cylinder(
        f"{MOD_ID}_turbine_cap",
        (0.0, DRUM_Y, 7.85),
        1.25,
        0.5,
        charcoal,
        vertices=20,
    )
    vanes = []
    for index in range(4):
        angle = index * math.pi / 2
        vanes.append(
            bk.add_box(
                f"{MOD_ID}_turbine_vane_{index}",
                (
                    math.cos(angle) * 0.7,
                    DRUM_Y + math.sin(angle) * 0.7,
                    8.2,
                ),
                (1.1, 0.16, 0.22),
                steel,
                bevel=0.02,
                rotation=(0.0, 0.0, angle),
            )
        )
    parts["turbine_cap"] = {
        "objects": [cap, *vanes],
        "pivot": (0.0, DRUM_Y, 7.85),
    }

    exhaust_dir = spec.EXHAUST_DIR
    angle = -math.atan2(exhaust_dir[1], exhaust_dir[2])
    flap = bk.add_cylinder(
        f"{MOD_ID}_exhaust_flap",
        (0.0, 11.15, 5.15),
        0.78,
        0.1,
        charcoal,
        vertices=18,
        axis="Z",
        bevel=0.0,
    )
    import bpy

    flap.rotation_euler = (angle, 0.0, 0.0)
    bpy.context.view_layer.objects.active = flap
    flap.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    flap.select_set(False)
    parts["exhaust_flap"] = {
        "objects": [flap],
        "pivot": (0.0, 10.9, 5.85),
    }
    return parts


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    deck = cage.add_box_lattice(
        "deck",
        (-4.0, DRUM_Y - 4.2, 0.0),
        (4.0, DRUM_Y + 4.2, 0.8),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("top", "north", "south", "east", "west"),
    )
    drum = cage.add_box_lattice(
        "drum",
        (-DRUM_R, DRUM_Y - DRUM_R, 0.8),
        (DRUM_R, DRUM_Y + DRUM_R, 7.6),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("top", "north", "south", "east", "west"),
    )
    for ix in (0, 1):
        for iy in (0, 1):
            cage.stitch(drum[(ix, iy, 0)], deck[(ix * 2, iy * 2, 1)])
    # Nozzle bell: open mouth to the south, collidable top, flanks, and a
    # back wall so the pull pins swallowed vehicles inside the gulp zone
    # instead of dragging them through into the gap under the drum.
    bell = cage.add_box_lattice(
        "bell",
        (-2.3, -4.3, 0.0),
        (2.3, -2.5, 2.3),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("top", "east", "west", "north"),
    )
    for ix in (0, 1):
        for iz in (0, 1):
            cage.stitch(bell[(ix, 1, iz)], deck[(ix * 2, 0, iz)])
    # Lane anchors keep the painted chevrons inside the flexbody hull.
    lane_l = cage.add_node("lane_anchor_l", (-2.4, -16.5, 0.05), fixed=True)
    lane_r = cage.add_node("lane_anchor_r", (2.4, -16.5, 0.05), fixed=True)
    cage.add_beam(lane_l, lane_r)
    cage.add_beam(lane_l, bell[(0, 0, 0)])
    cage.add_beam(lane_r, bell[(1, 0, 0)])
    # Exhaust anchor for the stack and flap visuals.
    exhaust_top = cage.add_node("exhaust_anchor", (0.0, 11.2, 5.9), fixed=True)
    cage.add_beam(exhaust_top, drum[(0, 1, 1)])
    cage.add_beam(exhaust_top, drum[(1, 1, 1)])

    cage.set_refnodes_existing(
        ref=deck[(1, 1, 0)],
        back=deck[(1, 0, 0)],
        left=deck[(0, 1, 0)],
        up=deck[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            deck[(0, 0, 0)],
            deck[(2, 0, 0)],
            deck[(0, 2, 0)],
            deck[(2, 2, 0)],
            drum[(0, 0, 1)],
            drum[(1, 0, 1)],
            drum[(0, 1, 1)],
            drum[(1, 1, 1)],
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
        camera_location=(18.0, -22.0, 11.0),
        look_at=(0.0, 2.0, 3.5),
    )
    print(f"VACUUM_OF_DOOM generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
