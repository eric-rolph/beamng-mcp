"""Deterministic Blender generator for the Whale Blowhole Geyser.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/whale_geyser/blender/create_whale_geyser.py
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


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def build_visual(materials) -> list:
    import bpy
    from mathutils import Matrix

    hero = materials[f"{MOD_ID}_whale_hero"]
    pupil = materials[f"{MOD_ID}_pupil_black"]
    blowhole_dark = materials[f"{MOD_ID}_blowhole_dark"]
    ramp_steel = materials[f"{MOD_ID}_ramp_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]
    paint = materials[f"{MOD_ID}_paint_white"]

    objects = []
    # The whale itself is a generated hero mesh (assets/whale_hero.glb,
    # checked in): realistic fin-whale body, welded, dorsal fin pre-squashed
    # to a drivable bump, 22% height-flattened for a beached stance, tail
    # at -Y, belly on z=0, 33 m long. Authored coords match the sampled
    # WHALE_DECK constants in spec.py, so it imports at identity.
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(EXAMPLE_ROOT / "assets" / "whale_hero.glb"))
    imported = [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]
    if len(imported) != 1:
        raise RuntimeError(f"expected one whale mesh in GLB, got {len(imported)}")
    whale = imported[0]
    whale.parent = None
    whale.name = f"{MOD_ID}_whale_hero"
    whale.data.transform(whale.matrix_world)
    whale.matrix_world = Matrix.Identity(4)
    whale.data.materials.clear()
    whale.data.materials.append(hero)
    objects.append(whale)

    # Blowhole crater on the pad (the bake has no readable blowhole).
    pad = spec.PAD_CENTER
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_blowhole_rim",
            (pad[0], pad[1], pad[2] - 0.08),
            1.6,
            0.35,
            blowhole_dark,
            major_segments=20,
            minor_segments=10,
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_crater_floor",
            (pad[0], pad[1], pad[2] - 0.05),
            2.5,
            0.16,
            blowhole_dark,
            vertices=24,
            metric_uv=(1.8, 1.8),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_blowhole_pit",
            (pad[0], pad[1], pad[2] - 0.22),
            1.35,
            0.2,
            pupil,
            vertices=20,
        )
    )

    # Research trestle: long shallow ramp from the ground onto the back,
    # passing under the raised fluke.
    run = spec.RAMP_LAND_Y - spec.RAMP_GROUND_Y
    land_z = spec.WHALE_DECK[0][2][2] - spec.DECK_EMBED
    angle = math.atan2(land_z, run)
    length = math.hypot(run, land_z)
    mid_y = (spec.RAMP_GROUND_Y + spec.RAMP_LAND_Y) / 2
    objects.append(
        bk.add_box(
            f"{MOD_ID}_ramp_deck",
            (0.0, mid_y, land_z / 2 + 0.02),
            (2 * spec.RAMP_HALF_W, length + 0.6, 0.24),
            ramp_steel,
            bevel=0.03,
            rotation=(angle, 0.0, 0.0),
            metric_uv=(1.8, 1.8),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_ramp_nose",
            (0.0, spec.RAMP_GROUND_Y + 0.3, 0.06),
            (2 * spec.RAMP_HALF_W, 0.7, 0.12),
            hazard,
            bevel=0.0,
        )
    )
    for side, sx in (("l", -spec.RAMP_HALF_W + 0.1), ("r", spec.RAMP_HALF_W - 0.1)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ramp_rail_{side}",
                (sx, mid_y, land_z / 2 + 0.62),
                (0.12, length - 0.6, 0.14),
                ramp_steel,
                bevel=0.02,
                rotation=(angle, 0.0, 0.0),
            )
        )
    for leg_index, leg_y in enumerate((-23.0, -18.5, -14.0, -9.5, -5.5)):
        leg_top = (leg_y - spec.RAMP_GROUND_Y) / run * land_z
        for side, sx in (("l", -spec.RAMP_HALF_W + 0.3), ("r", spec.RAMP_HALF_W - 0.3)):
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_ramp_leg_{leg_index}_{side}",
                    (sx, leg_y, leg_top / 2),
                    0.14,
                    max(0.3, leg_top),
                    ramp_steel,
                    vertices=10,
                )
            )
    # Painted centre dashes up the ramp toward the blowhole.
    for dash_index in range(7):
        dash_y = spec.RAMP_GROUND_Y + 2.5 + dash_index * 3.2
        dash_z = (dash_y - spec.RAMP_GROUND_Y) / run * land_z
        objects.append(
            bk.add_box(
                f"{MOD_ID}_path_dash_{dash_index}",
                (0.0, dash_y, dash_z + 0.16),
                (0.5, 1.2, 0.06),
                paint,
                bevel=0.0,
                rotation=(angle, 0.0, 0.0),
            )
        )
    return objects


def build_cage() -> bk.CageBuilder:
    """Collision sampled from the hero mesh (spec.WHALE_DECK): five rails
    follow the real back surface so mid-lane chord sag stays ~5 cm (the
    old 3-rail chords let tires sink half a wheel into the skin), plus a
    flat 3-rail trestle ramp and flank skirts down to the ground."""

    cage = bk.CageBuilder(MOD_ID)
    embed = spec.DECK_EMBED
    fractions = (-0.84, -0.42, 0.0, 0.42, 0.84)

    surface: dict[tuple[int, int], str] = {}
    ground: dict[tuple[int, int], str] = {}
    pad_rows = {6, 7, 8}  # y 5.0..8.0: flat parking pad (cars slid off the crown)
    for j, (y, half_w, cols, flank) in enumerate(spec.WHALE_DECK):
        if j in pad_rows:
            deck_z = [spec.PAD_Z - embed - 0.02] * 5
            half_w = max(half_w, 2.0)
        else:
            deck_z = [max(0.2, z - embed) for z in cols]
        for i, fraction in enumerate(fractions):
            surface[(i, j)] = cage.add_node(
                f"deck_{i}_{j}",
                (fraction * half_w, y, deck_z[i]),
                fixed=True,
                collision=True,
                weight=150.0,
            )
        for i, sx in ((0, -flank), (1, flank)):
            ground[(i, j)] = cage.add_node(f"flank_{i}_{j}", (sx, y, 0.0), fixed=True, weight=180.0)
    for j in range(len(spec.WHALE_DECK)):
        for i in range(4):
            cage.add_beam(surface[(i, j)], surface[(i + 1, j)])
        cage.add_beam(ground[(0, j)], ground[(1, j)])
        cage.add_beam(surface[(0, j)], ground[(0, j)])
        cage.add_beam(surface[(4, j)], ground[(1, j)])
        cage.add_beam(surface[(2, j)], ground[(0, j)])
        if j > 0:
            for i in range(5):
                cage.add_beam(surface[(i, j - 1)], surface[(i, j)])
            for i in range(2):
                cage.add_beam(ground[(i, j - 1)], ground[(i, j)])
            for i in range(4):
                cage.add_quad(
                    [
                        surface[(i, j - 1)],
                        surface[(i + 1, j - 1)],
                        surface[(i + 1, j)],
                        surface[(i, j)],
                    ],
                    ground_model="asphalt",
                )
            cage.add_quad(
                [ground[(0, j - 1)], surface[(0, j - 1)], surface[(0, j)], ground[(0, j)]],
                ground_model="metal",
            )
            cage.add_quad(
                [ground[(1, j - 1)], ground[(1, j)], surface[(4, j)], surface[(4, j - 1)]],
                ground_model="metal",
            )

    # Trestle ramp: flat 3-rail run from the ground to the first deck row.
    run = spec.RAMP_LAND_Y - spec.RAMP_GROUND_Y
    land_z = spec.WHALE_DECK[0][2][2] - embed
    ramp: dict[tuple[int, int], str] = {}
    ramp_ys = [spec.RAMP_GROUND_Y + step * run / 10.0 for step in range(10)]
    for j, y in enumerate(ramp_ys):
        z = max(0.0, (y - spec.RAMP_GROUND_Y) / run * land_z)
        for i, sx in enumerate((-spec.RAMP_HALF_W, 0.0, spec.RAMP_HALF_W)):
            ramp[(i, j)] = cage.add_node(
                f"ramp_{i}_{j}",
                (sx, y, z),
                fixed=True,
                collision=True,
                weight=150.0,
            )
    for j in range(len(ramp_ys)):
        cage.add_beam(ramp[(0, j)], ramp[(1, j)])
        cage.add_beam(ramp[(1, j)], ramp[(2, j)])
        if j > 0:
            for i in range(3):
                cage.add_beam(ramp[(i, j - 1)], ramp[(i, j)])
            cage.add_quad(
                [ramp[(0, j - 1)], ramp[(1, j - 1)], ramp[(1, j)], ramp[(0, j)]],
                ground_model="asphalt",
            )
            cage.add_quad(
                [ramp[(1, j - 1)], ramp[(2, j - 1)], ramp[(2, j)], ramp[(1, j)]],
                ground_model="asphalt",
            )
    # Transition: last ramp row onto the first deck row.
    last_ramp = len(ramp_ys) - 1
    cage.add_beam(ramp[(0, last_ramp)], surface[(0, 0)])
    cage.add_beam(ramp[(1, last_ramp)], surface[(2, 0)])
    cage.add_beam(ramp[(2, last_ramp)], surface[(4, 0)])
    cage.add_quad(
        [ramp[(0, last_ramp)], ramp[(1, last_ramp)], surface[(2, 0)], surface[(0, 0)]],
        ground_model="asphalt",
    )
    cage.add_quad(
        [ramp[(1, last_ramp)], ramp[(2, last_ramp)], surface[(4, 0)], surface[(2, 0)]],
        ground_model="asphalt",
    )

    # Head slide-off lip so cars roll off the nose instead of beaching.
    last = len(spec.WHALE_DECK) - 1
    lip_l = cage.add_node("head_lip_l", (-1.8, 15.0, 2.2), fixed=True, collision=True)
    lip_r = cage.add_node("head_lip_r", (1.8, 15.0, 2.2), fixed=True, collision=True)
    cage.add_beam(lip_l, lip_r)
    cage.add_beam(lip_l, surface[(0, last)])
    cage.add_beam(lip_r, surface[(4, last)])
    cage.add_beam(lip_l, ground[(0, last)])
    cage.add_beam(lip_r, ground[(1, last)])
    cage.add_triangle(surface[(0, last)], surface[(2, last)], lip_l, ground_model="metal")
    cage.add_triangle(surface[(2, last)], lip_r, lip_l, ground_model="metal")
    cage.add_triangle(surface[(2, last)], surface[(4, last)], lip_r, ground_model="metal")

    cage.set_ground_reference(
        (0.0, -1.0, 0.0),
        (0.0, -5.0, 0.0),
        left=ground[(0, 2)],
        up=surface[(2, 2)],
        support_nodes=[ground[(0, 2)], ground[(1, 2)], ground[(0, 3)], ground[(1, 3)]],
    )
    cage.set_spawn_envelope(
        [
            ramp[(0, 0)],
            ramp[(2, 0)],
            surface[(0, 8)],
            surface[(4, 8)],
            lip_l,
            lip_r,
            surface[(0, 0)],
            surface[(4, 0)],
        ]
    )
    cage.auto_base_nodes()
    return cage


def main() -> None:
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)

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
        parts=[],
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
        camera_location=(15.0, 19.0, 7.5),
        look_at=(0.0, 1.0, 3.2),
    )
    print("WHALE_GEYSER generator complete")


if __name__ == "__main__":
    main()
