"""Deterministic Blender generator for the Monster Flyswatter.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/monster_flyswatter/blender/create_monster_flyswatter.py
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

LHX = spec.LANE_HALF_X
LHY = spec.LANE_HALF_Y
LTZ = spec.LANE_TOP_Z
PMIN = spec.PEDESTAL_MIN
PMAX = spec.PEDESTAL_MAX
PIVOT = spec.PIVOT


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def build_visual(materials) -> list:
    asphalt = materials[f"{MOD_ID}_asphalt"]
    paint = materials[f"{MOD_ID}_paint_white"]
    steel = materials[f"{MOD_ID}_steel"]
    hazard = materials[f"{MOD_ID}_hazard_yellow"]

    objects = []
    # The swat lane: a low slab with painted edge lines and a target ring
    # where the head lands.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_lane",
            (0.0, 0.0, LTZ / 2),
            (2 * LHX, 2 * LHY, LTZ),
            asphalt,
            bevel=0.0,
            metric_uv=(2.5, 2.5),
        )
    )
    for side, sx in (("l", -LHX + 0.2), ("r", LHX - 0.2)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_lane_line_{side}",
                (sx, 0.0, LTZ + 0.005),
                (0.22, 2 * LHY - 0.4, 0.01),
                paint,
                bevel=0.0,
            )
        )
    # Dashed centre line.
    for index in range(7):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_lane_dash_{index}",
                (0.0, -9.0 + index * 3.0, LTZ + 0.005),
                (0.2, 1.4, 0.01),
                paint,
                bevel=0.0,
            )
        )
    # Pedestal with hazard stripes and the hinge bracket.
    pcx = (PMIN[0] + PMAX[0]) / 2
    pcy = (PMIN[1] + PMAX[1]) / 2
    pcz = (PMIN[2] + PMAX[2]) / 2
    pdx = PMAX[0] - PMIN[0]
    pdy = PMAX[1] - PMIN[1]
    pdz = PMAX[2] - PMIN[2]
    objects.append(
        bk.add_box(
            f"{MOD_ID}_pedestal",
            (pcx, pcy, pcz),
            (pdx, pdy, pdz),
            steel,
            bevel=0.06,
            metric_uv=(1.8, 1.8),
        )
    )
    for index in range(3):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_hazard_stripe_{index}",
                (PMIN[0] - 0.01, pcy - 1.0 + index * 1.0, 0.75),
                (0.04, 0.5, 1.4),
                hazard,
                bevel=0.0,
                rotation=(0.0, math.radians(18.0), 0.0),
            )
        )
    for side, sy in (("a", -0.55), ("b", 0.55)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_hinge_plate_{side}",
                (PIVOT[0], sy, PIVOT[2]),
                (1.2, 0.18, 1.1),
                steel,
                bevel=0.03,
            )
        )
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    plastic = materials[f"{MOD_ID}_plastic_red"]
    mesh_green = materials[f"{MOD_ID}_mesh_green"]
    steel = materials[f"{MOD_ID}_steel"]

    # The whole arm is one kinematic part, authored at the SLAM pose
    # (angle 0 = arm flat along -X); the runtime holds it at the raised rest
    # angle and animates the slam.
    px, py, pz = PIVOT
    objects = []
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_hinge_axle",
            (px, py, pz),
            0.16,
            1.4,
            steel,
            vertices=14,
            axis="Y",
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_handle",
            (px - 2.1, py, pz),
            0.28,
            4.2,
            plastic,
            vertices=16,
            axis="X",
        )
    )
    # Head frame: rounded border plus the green mesh face.
    head_cx = px + spec.HEAD_CENTER_OFFSET
    hw = spec.HEAD_WIDTH
    hl = spec.HEAD_LENGTH
    objects.append(
        bk.add_box(
            f"{MOD_ID}_head_frame_n",
            (head_cx, hl / 2 - 0.15, pz),
            (hw, 0.3, 0.34),
            plastic,
            bevel=0.1,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_head_frame_s",
            (head_cx, -(hl / 2 - 0.15), pz),
            (hw, 0.3, 0.34),
            plastic,
            bevel=0.1,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_head_frame_e",
            (head_cx + hw / 2 - 0.15, 0.0, pz),
            (0.3, hl - 0.6, 0.34),
            plastic,
            bevel=0.1,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_head_frame_w",
            (head_cx - (hw / 2 - 0.15), 0.0, pz),
            (0.3, hl - 0.6, 0.34),
            plastic,
            bevel=0.1,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_head_mesh",
            (head_cx, 0.0, pz),
            (hw - 0.5, hl - 0.5, 0.1),
            mesh_green,
            bevel=0.0,
            metric_uv=(0.55, 0.55),
        )
    )
    # Mesh rib lines to suggest the weave.
    for index in range(5):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_head_rib_x_{index}",
                (head_cx, -hl / 2 + 0.8 + index * (hl - 1.6) / 4, pz + 0.04),
                (hw - 0.6, 0.08, 0.05),
                plastic,
                bevel=0.0,
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_head_rib_y_{index}",
                (head_cx - hw / 2 + 0.8 + index * (hw - 1.6) / 4, 0.0, pz + 0.04),
                (0.08, hl - 0.6, 0.05),
                plastic,
                bevel=0.0,
            )
        )
    return {"swatter_arm": {"objects": objects, "pivot": PIVOT}}


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    lane = cage.add_box_lattice(
        "lane",
        (-LHX, -LHY, 0.0),
        (LHX, LHY, LTZ),
        subdivisions=(2, 4, 1),
        fixed=True,
        collision=False,
        collision_faces=("top",),
        face_ground_models={"top": "asphalt"},
    )
    pedestal = cage.add_box_lattice(
        "pedestal",
        PMIN,
        PMAX,
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("top", "north", "south", "east", "west"),
    )
    # Stitch the pedestal to the lane so the cage stays one connected graph.
    for iy in (0, 1):
        for iz in (0, 1):
            cage.stitch(lane[(2, 2, iz)], pedestal[(0, iy, iz)])
    cage.set_refnodes_existing(
        ref=lane[(1, 2, 0)],
        back=lane[(1, 1, 0)],
        left=lane[(0, 2, 0)],
        up=lane[(1, 2, 1)],
    )
    cage.set_spawn_envelope(
        [
            lane[(0, 0, 0)],
            lane[(0, 4, 0)],
            lane[(0, 0, 1)],
            lane[(0, 4, 1)],
            pedestal[(1, 0, 0)],
            pedestal[(1, 1, 0)],
            pedestal[(1, 0, 1)],
            pedestal[(1, 1, 1)],
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
        camera_location=(16.0, -20.0, 10.0),
        look_at=(0.0, -1.0, 2.5),
    )
    print(f"MONSTER_FLYSWATTER generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
