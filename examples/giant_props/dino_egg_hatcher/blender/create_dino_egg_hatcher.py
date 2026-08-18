"""Deterministic Blender generator for the Dino Egg Hatcher.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/dino_egg_hatcher/blender/create_dino_egg_hatcher.py
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

EGG_Z = spec.EGG_CENTER_Z
EGG_R = spec.EGG_RADIUS
RING_R = spec.SHELL_RING_RADIUS
Z_LEVELS = spec.SHELL_Z_LEVELS


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def build_visual(materials) -> list:
    eggshell = materials[f"{MOD_ID}_eggshell"]
    straw = materials[f"{MOD_ID}_nest_straw"]
    nest_dark = materials[f"{MOD_ID}_nest_dark"]

    objects = []
    # Nest: base disc, straw torus, scattered straw sticks.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_nest_base",
            (0.0, 0.0, 0.16),
            4.5,
            0.32,
            nest_dark,
            vertices=28,
            metric_uv=(1.8, 1.8),
        )
    )
    objects.append(
        bk.add_torus(
            f"{MOD_ID}_nest_ring",
            (0.0, 0.0, 0.5),
            4.1,
            0.85,
            straw,
            major_segments=24,
            minor_segments=12,
        )
    )
    for index in range(10):
        angle = index * math.pi / 5 + 0.35
        objects.append(
            bk.add_box(
                f"{MOD_ID}_straw_{index}",
                (
                    math.cos(angle) * 4.4,
                    math.sin(angle) * 4.4,
                    1.05,
                ),
                (1.6, 0.12, 0.1),
                straw,
                bevel=0.0,
                rotation=(0.0, math.radians(14.0), angle + 0.5),
            )
        )
    # Lower egg shell: a scaled sphere with the doorway and the dome cut off.
    egg = bk.add_sphere(
        f"{MOD_ID}_egg_shell",
        (0.0, 0.0, EGG_Z),
        EGG_R,
        eggshell,
        segments=28,
        rings=18,
        scale=(1.0, 1.0, spec.EGG_SCALE_Z),
    )
    import bpy

    # Real shell thickness first: hollow the sphere so every cut edge shows
    # a genuine 0.25 m eggshell rim instead of a zero-thickness surface with
    # flat boolean planes behind it (player report 2026-07-23).
    cutters = [
        bk.add_sphere(
            f"{MOD_ID}_shell_inner",
            (0.0, 0.0, EGG_Z),
            EGG_R - 0.25,
            None,
            segments=24,
            rings=16,
            scale=(1.0, 1.0, spec.EGG_SCALE_Z),
        ),
    ]
    # Clean split-arch doorway: one tall opening plus a single diamond peak,
    # reading as the shell split apart (the old three-box cut left messy
    # interior planes, dressed with plank-like edging that made it worse).
    cutters.append(
        bk.add_box(
            f"{MOD_ID}_door_cutter_c",
            (0.0, -3.1, 1.55),
            (3.4, 3.4, 3.1),
            None,
            bevel=0.0,
        )
    )
    cutters.append(
        bk.add_box(
            f"{MOD_ID}_door_cutter_peak",
            (0.0, -2.9, 3.3),
            (2.4, 3.2, 2.4),
            None,
            bevel=0.0,
            rotation=(0.0, math.radians(45.0), 0.0),
        )
    )
    # Player round 5: the static shell is now just a cracked cup — every
    # piece of shell above CUP_RIM_Z is a flying shard part instead.
    cutters.append(
        bk.add_box(
            f"{MOD_ID}_dome_cutter",
            (0.0, 0.0, spec.CUP_RIM_Z + 6.0),
            (12.0, 12.0, 12.0),
            None,
            bevel=0.0,
        )
    )
    rim_z = spec.CUP_RIM_Z
    rim_r = EGG_R * math.sqrt(max(0.0, 1 - ((rim_z - EGG_Z) / (EGG_R * spec.EGG_SCALE_Z)) ** 2))
    for tooth_index, tooth_deg in enumerate((10, 55, 100, 145, 190, 225, 315, 345)):
        tooth = math.radians(tooth_deg)
        cutters.append(
            bk.add_box(
                f"{MOD_ID}_crown_tooth_{tooth_index}",
                (math.cos(tooth) * rim_r, math.sin(tooth) * rim_r, rim_z + 0.15),
                (1.15, 1.15, 1.5),
                None,
                bevel=0.0,
                rotation=(math.radians(38.0), math.radians(32.0), tooth),
            )
        )
    bpy.ops.object.select_all(action="DESELECT")
    bk.cut_openings(egg, cutters)
    bk.scale_uvs(egg, 6.0, 4.0)
    objects.append(egg)
    # Speckle spots live on the SHARDS (build_parts): with everything above
    # the cup rim flying off on hatch, any spot pinned to the static visual
    # would float in mid-air afterwards (post-hatch DAE render 2026-07-23).
    # --- Entrance dressing (play-test fix 2026-07-22: the doorway and its
    # collision ramp were invisible; nobody could find the way in). ---
    straw = materials[f"{MOD_ID}_nest_straw"]
    crack_white = materials[f"{MOD_ID}_crack_white"]
    # Straw entry ramp bridging over the nest ring to the doorway sill.
    ramp_run = 6.8 - 2.6
    ramp_angle = math.atan2(0.42, ramp_run)
    objects.append(
        bk.add_box(
            f"{MOD_ID}_entry_ramp",
            (0.0, -(6.8 + 2.6) / 2, 0.21 - 0.11 * math.cos(ramp_angle)),
            (3.2, math.hypot(ramp_run, 0.42) + 0.6, 0.22),
            straw,
            bevel=0.05,
            rotation=(-ramp_angle, 0.0, 0.0),
            metric_uv=(1.4, 1.4),
        )
    )
    # Painted approach arrows pointing at the doorway.
    for index, ay in enumerate((-9.5, -8.0)):
        for side in (-1, 1):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_arrow_{index}_{'l' if side < 0 else 'r'}",
                    (side * 0.75, ay, 0.05),
                    (1.7, 0.4, 0.06),
                    crack_white,
                    bevel=0.0,
                    rotation=(0.0, 0.0, -side * math.radians(35.0)),
                )
            )
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    import bpy

    eggshell = materials[f"{MOD_ID}_eggshell"]

    def door_arch_cutters(name):
        """The split-arch doorway, matching the static cup's cut exactly."""

        return [
            bk.add_box(
                f"{name}_arch_c",
                (0.0, -3.1, 1.55),
                (3.4, 3.4, 3.1),
                None,
                bevel=0.0,
            ),
            bk.add_box(
                f"{name}_arch_peak",
                (0.0, -2.9, 3.3),
                (2.4, 3.2, 2.4),
                None,
                bevel=0.0,
                rotation=(0.0, math.radians(45.0), 0.0),
            ),
        ]

    def dome_fragment(name, wedge, z_min, z_max, extra_cutters=None):
        """A real curved shell piece: sphere shell clipped to a wedge."""

        outer = bk.add_sphere(
            name,
            (0.0, 0.0, EGG_Z),
            EGG_R,
            eggshell,
            segments=28,
            rings=18,
            scale=(1.0, 1.0, spec.EGG_SCALE_Z),
        )
        bk.scale_uvs(outer, 6.0, 4.0)
        cutters = [
            bk.add_sphere(
                f"{name}_inner",
                (0.0, 0.0, EGG_Z),
                EGG_R - 0.24,
                None,
                segments=22,
                rings=14,
                scale=(1.0, 1.0, spec.EGG_SCALE_Z),
            ),
            bk.add_box(
                f"{name}_below", (0.0, 0.0, z_min - 10.0), (20.0, 20.0, 20.0), None, bevel=0.0
            ),
        ]
        if z_max is not None:
            cutters.append(
                bk.add_box(
                    f"{name}_above",
                    (0.0, 0.0, z_max + 10.0),
                    (20.0, 20.0, 20.0),
                    None,
                    bevel=0.0,
                )
            )
        if wedge is not None:
            a0, a1 = (math.radians(v) for v in wedge)
            for tag, plane_angle, keep_left in (("a", a0, True), ("b", a1, False)):
                normal = (-math.sin(plane_angle), math.cos(plane_angle))
                sign = 1.0 if keep_left else -1.0
                cutters.append(
                    bk.add_box(
                        f"{name}_wedge_{tag}",
                        (-sign * normal[0] * 15.0, -sign * normal[1] * 15.0, EGG_Z + 2.0),
                        (30.0, 30.0, 16.0),
                        None,
                        bevel=0.0,
                        rotation=(0.0, 0.0, plane_angle),
                    )
                )
        if extra_cutters:
            cutters.extend(extra_cutters)
        bpy.ops.object.select_all(action="DESELECT")
        bk.cut_openings(outer, cutters)
        return outer

    parts: dict[str, dict[str, object]] = {}
    shard_zones: list[tuple[str, tuple[float, float], float, float]] = []
    shard_index = 0
    for wedge in spec.SHARD_RING_WEDGES:
        shard_index += 1
        mid = math.radians((wedge[0] + wedge[1]) / 2)
        fragment = dome_fragment(f"{MOD_ID}_shard_{shard_index}", wedge, 5.0, spec.SHARD_CAP_Z)
        pivot = (
            math.cos(mid) * spec.SHARD_RING_RADIUS,
            math.sin(mid) * spec.SHARD_RING_RADIUS,
            5.85,
        )
        parts[f"shard_{shard_index}"] = {"objects": [fragment], "pivot": pivot}
        shard_zones.append((f"shard_{shard_index}", wedge, 5.0, spec.SHARD_CAP_Z))
    for wedge in spec.SHARD_CAP_WEDGES:
        shard_index += 1
        mid = math.radians((wedge[0] + wedge[1]) / 2)
        fragment = dome_fragment(f"{MOD_ID}_shard_{shard_index}", wedge, spec.SHARD_CAP_Z, None)
        pivot = (
            math.cos(mid) * 0.7,
            math.sin(mid) * 0.7,
            spec.SHARD_CAP_Z + 0.45,
        )
        parts[f"shard_{shard_index}"] = {"objects": [fragment], "pivot": pivot}
        shard_zones.append((f"shard_{shard_index}", wedge, spec.SHARD_CAP_Z, 12.0))
    # Player round 5: the former static mid-wall is a band of shards too —
    # seams staggered off the ring wedges; the three door-zone pieces carry
    # the arch notch so the entrance stays open at rest.
    for band_index, wedge in enumerate(spec.SHARD_BAND_WEDGES):
        shard_index += 1
        mid = math.radians((wedge[0] + wedge[1]) / 2)
        name = f"{MOD_ID}_shard_{shard_index}"
        extra = door_arch_cutters(name) if band_index in spec.SHARD_BAND_DOOR else None
        fragment = dome_fragment(name, wedge, spec.CUP_RIM_Z, 5.0, extra_cutters=extra)
        pivot = (
            math.cos(mid) * 2.9,
            math.sin(mid) * 2.9,
            3.6,
        )
        parts[f"shard_{shard_index}"] = {"objects": [fragment], "pivot": pivot}
        shard_zones.append((f"shard_{shard_index}", wedge, spec.CUP_RIM_Z, 5.0))

    # Speckle spots ride their shard so they fly with the shell piece.
    spot_specs = [
        (35.0, 20.0, 0.55, materials[f"{MOD_ID}_spot_green"]),
        (100.0, 35.0, 0.45, materials[f"{MOD_ID}_spot_teal"]),
        (160.0, 12.0, 0.6, materials[f"{MOD_ID}_spot_green"]),
        (205.0, 40.0, 0.5, materials[f"{MOD_ID}_spot_teal"]),
        (330.0, 28.0, 0.55, materials[f"{MOD_ID}_spot_green"]),
        (60.0, -14.0, 0.42, materials[f"{MOD_ID}_spot_teal"]),
    ]

    def owning_shard(azimuth_deg, z):
        for part_name, (a0, a1), z_lo, z_hi in shard_zones:
            if not (z_lo <= z < z_hi):
                continue
            for candidate in (azimuth_deg, azimuth_deg + 360.0):
                if a0 <= candidate < a1:
                    return part_name
        return None

    for index, (azimuth_deg, elevation_deg, radius, mat) in enumerate(spot_specs):
        azimuth = math.radians(azimuth_deg)
        elevation = math.radians(elevation_deg)
        spot_z = EGG_Z + math.sin(elevation) * (EGG_R * spec.EGG_SCALE_Z - 0.05)
        owner = owning_shard(azimuth_deg, spot_z)
        if owner is None:
            raise RuntimeError(f"spot {index} at az {azimuth_deg} z {spot_z:.2f} has no shard")
        surface = (
            math.cos(elevation) * math.cos(azimuth) * (EGG_R - 0.05),
            math.cos(elevation) * math.sin(azimuth) * (EGG_R - 0.05),
            spot_z,
        )
        spot = bk.add_sphere(
            f"{MOD_ID}_spot_{index}",
            surface,
            radius,
            mat,
            segments=14,
            rings=8,
            scale=(1.0, 1.0, 0.45),
        )
        spot.rotation_euler = (0.0, math.pi / 2 - elevation, azimuth)
        bpy.context.view_layer.objects.active = spot
        spot.select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        spot.select_set(False)
        parts[owner]["objects"].append(spot)
    return parts


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    plate = cage.add_box_lattice(
        "floor",
        (-2.6, -2.6, 0.0),
        (2.6, 2.6, 0.4),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("top",),
        face_ground_models={"top": "dirt"},
    )
    # Shell ring: 12 columns, with the two door sectors (240..300 degrees)
    # left open. Quads are wound both inward and outward so the shell is
    # solid from either side.
    columns: dict[int, dict[int, str]] = {}
    count = 12
    for index in range(count):
        angle = math.radians(index * 30.0)
        columns[index] = {}
        for level, z in enumerate(Z_LEVELS):
            columns[index][level] = cage.add_node(
                f"shell_{index:02d}_{level}",
                (math.cos(angle) * RING_R, math.sin(angle) * RING_R, z),
                fixed=True,
                collision=True,
                weight=150.0,
            )
    door_sectors = {7, 8, 9, 10}  # 210-330: a proper cracked-open entry
    for index in range(count):
        column = columns[index]
        for level in range(len(Z_LEVELS) - 1):
            cage.add_beam(column[level], column[level + 1])
        next_column = columns[(index + 1) % count]
        for level in range(len(Z_LEVELS)):
            cage.add_beam(column[level], next_column[level])
        if index not in door_sectors:
            for level in range(len(Z_LEVELS) - 1):
                quad = [
                    column[level],
                    next_column[level],
                    next_column[level + 1],
                    column[level + 1],
                ]
                cage.add_quad_both(quad, ground_model="metal")
    # Stitch the ring to the floor plate.
    stitch_targets = {
        0: (2, 1),
        1: (2, 2),
        2: (1, 2),
        3: (1, 2),
        4: (0, 2),
        5: (0, 1),
        6: (0, 0),
        7: (0, 0),
        8: (1, 0),
        9: (1, 0),
        10: (2, 0),
        11: (2, 0),
    }
    for index, (ix, iy) in stitch_targets.items():
        cage.add_beam(columns[index][0], plate[(ix, iy, 1)])
        cage.add_beam(columns[index][0], plate[(ix, iy, 0)])
    # Doorway ramp from the ground up onto the floor plate.
    ramp_l = cage.add_node("ramp_ground_l", (-1.5, -6.9, 0.0), fixed=True, collision=True)
    ramp_r = cage.add_node("ramp_ground_r", (1.5, -6.9, 0.0), fixed=True, collision=True)
    top_l = cage.add_node("ramp_top_l", (-1.9, -2.7, 0.38), fixed=True, collision=True)
    top_r = cage.add_node("ramp_top_r", (1.9, -2.7, 0.38), fixed=True, collision=True)
    cage.add_beam(ramp_l, ramp_r)
    cage.add_beam(top_l, top_r)
    cage.add_beam(ramp_l, top_l)
    cage.add_beam(ramp_r, top_r)
    cage.add_beam(top_l, plate[(0, 0, 1)])
    cage.add_beam(top_r, plate[(2, 0, 1)])
    cage.add_beam(top_l, plate[(1, 0, 1)])
    cage.add_beam(top_r, plate[(1, 0, 1)])
    cage.add_quad([ramp_l, ramp_r, top_r, top_l], ground_model="dirt")
    cage.add_quad([top_l, top_r, plate[(2, 0, 1)], plate[(0, 0, 1)]], ground_model="dirt")

    cage.set_refnodes_existing(
        ref=plate[(1, 1, 0)],
        back=plate[(1, 0, 0)],
        left=plate[(0, 1, 0)],
        up=plate[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            columns[1][0],
            columns[1][1],
            columns[4][0],
            columns[4][1],
            columns[7][0],
            columns[7][1],
            columns[10][0],
            columns[10][1],
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
        camera_location=(11.0, -14.0, 8.0),
        look_at=(0.0, 0.0, 3.2),
    )
    print(f"DINO_EGG_HATCHER generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
