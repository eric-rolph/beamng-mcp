"""Deterministic Blender generator for the Bouncy Castle Landing Zone.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/bouncy_castle/blender/create_bouncy_castle.py

Cage layout (authored frame, +Y drive):

- 6x6 fixed base grid at z=0 under a 6x6 *free* floor grid at z=0.8 on
  low-damping springs: the trampoline.
- Fixed outer frame walls at |x|=11 / y=+/-11 with *free* inner pillow rows;
  the south wall has a one-cell gate (x -2..2) with a fixed entry ramp.
- Corner towers and battlements are visual dressing bound to fixed nodes.
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

S = [-10.0, -6.0, -2.0, 2.0, 6.0, 10.0]
# Fine floor/base grid (spec.GRID cells): the coarse 6x6 floor let cars punch
# through to the terrain in the 2026-07-22 live run.
F = [-10.0 + 20.0 * i / spec.GRID for i in range(spec.GRID + 1)]
# Nearest fine-grid index for each coarse wall station.
NEAREST_F = {0: 0, 1: 2, 2: 3, 3: 5, 4: 6, 5: 8}
GATE_F = (3, 5)  # fine columns bounding the south gate (x -2.5 .. 2.5)
FLOOR_Z = spec.FLOOR_Z
FRAME = 11.0
INNER = 9.6
WALL_Z = (1.5, 2.9)
FRAME_Z = (0.0, 1.7, 3.4)
GATE_COLUMNS = (2, 3)  # station indices bounding the south gate


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def build_visual(materials) -> list:
    blue = materials[f"{MOD_ID}_vinyl_blue"]
    red = materials[f"{MOD_ID}_vinyl_red"]
    yellow = materials[f"{MOD_ID}_vinyl_yellow"]
    cream = materials[f"{MOD_ID}_vinyl_cream"]
    green = materials[f"{MOD_ID}_flag_green"]

    objects = []
    # Quilted floor pad.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_floor_pad",
            (0.0, 0.0, FLOOR_Z / 2),
            (20.6, 20.6, FLOOR_Z),
            blue,
            bevel=0.28,
            metric_uv=(2.5, 2.5),
        )
    )
    for index, station in enumerate(S[1:-1]):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_floor_seam_x_{index}",
                (station, 0.0, FLOOR_Z + 0.01),
                (0.14, 19.8, 0.02),
                cream,
                bevel=0.0,
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_floor_seam_y_{index}",
                (0.0, station, FLOOR_Z + 0.01),
                (19.8, 0.14, 0.02),
                cream,
                bevel=0.0,
            )
        )
    # Inflatable wall tubes: two stacked bolsters per closed wall, split
    # around the gate on the south side.
    tube_specs = [
        ("wall_e", "Y", (10.3, 0.0), 20.6, red),
        ("wall_w", "Y", (-10.3, 0.0), 20.6, red),
        ("wall_n", "X", (0.0, 10.3), 20.6, red),
        ("wall_s_left", "X", (-6.5, -10.3), 7.6, red),
        ("wall_s_right", "X", (6.5, -10.3), 7.6, red),
    ]
    for name, axis, (cx, cy), length, mat in tube_specs:
        for level, tz in enumerate(WALL_Z):
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_{name}_tube_{level}",
                    (cx, cy, tz),
                    0.85,
                    length,
                    mat if level == 0 else yellow,
                    vertices=18,
                    axis=axis,
                    metric_uv=(1.7, 1.7),
                )
            )
    # Battlement blocks along wall tops.
    for index in range(5):
        for name, (bx, by) in {
            f"bat_e_{index}": (10.3, -8.0 + index * 4.0),
            f"bat_w_{index}": (-10.3, -8.0 + index * 4.0),
            f"bat_n_{index}": (-8.0 + index * 4.0, 10.3),
        }.items():
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_{name}",
                    (bx, by, spec.WALL_TOP_Z + 0.45),
                    (1.5, 1.5, 0.9),
                    red if index % 2 == 0 else yellow,
                    bevel=0.18,
                )
            )
    # Corner towers with cone roofs and flags.
    for index, (tx, ty) in enumerate(((-11.3, -11.3), (11.3, -11.3), (-11.3, 11.3), (11.3, 11.3))):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_tower_{index}",
                (tx, ty, 2.6),
                1.7,
                5.2,
                cream,
                vertices=20,
                metric_uv=(2.2, 2.2),
            )
        )
        objects.append(
            bk.add_cone(
                f"{MOD_ID}_tower_roof_{index}",
                (tx, ty, 6.2),
                2.0,
                0.05,
                2.0,
                red,
                vertices=20,
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_flag_pole_{index}",
                (tx, ty, 7.9),
                0.06,
                1.4,
                cream,
                vertices=8,
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_flag_{index}",
                (tx + 0.55, ty, 8.35),
                (1.1, 0.05, 0.6),
                green,
                bevel=0.0,
            )
        )
    # Entry ramp: red wedge up to the gate.
    run = -10.3 - spec.RAMP_GROUND_Y
    ramp_len = math.hypot(run, FLOOR_Z)
    angle = math.atan2(FLOOR_Z, run)
    normal = (0.0, -math.sin(angle), math.cos(angle))
    mid_y = (spec.RAMP_GROUND_Y + -10.3) / 2
    objects.append(
        bk.add_box(
            f"{MOD_ID}_ramp",
            (0.0, mid_y - normal[1] * 0.14, FLOOR_Z / 2 - normal[2] * 0.14),
            (4.0, ramp_len, 0.28),
            red,
            bevel=0.06,
            rotation=(angle, 0.0, 0.0),
            metric_uv=(2.0, 2.0),
        )
    )
    for side, sx in (("l", -2.2), ("r", 2.2)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_ramp_bumper_{side}",
                (sx, mid_y, 0.55),
                0.35,
                ramp_len - 0.4,
                yellow,
                vertices=12,
                axis="Y",
                bevel=0.0,
            )
        )
    return objects


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    cage.define_beam_spec(
        "bounce_support",
        beamSpring=130000.0,
        beamDamp=700.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "bounce_shear",
        beamSpring=60000.0,
        beamDamp=400.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "membrane",
        beamSpring=160000.0,
        beamDamp=450.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "pillow",
        beamSpring=26000.0,
        beamDamp=200.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )

    base: dict[tuple[int, int], str] = {}
    floor: dict[tuple[int, int], str] = {}
    for i, x in enumerate(F):
        for j, y in enumerate(F):
            base[(i, j)] = cage.add_node(f"base_{i}_{j}", (x, y, 0.0), fixed=True, weight=200.0)
            floor[(i, j)] = cage.add_node(
                f"floor_{i}_{j}",
                (x, y, FLOOR_Z),
                fixed=False,
                collision=True,
                weight=35.0,
                friction=1.0,
            )
    for (i, j), node in base.items():
        for di, dj in ((1, 0), (0, 1)):
            neighbour = base.get((i + di, j + dj))
            if neighbour:
                cage.add_beam(node, neighbour)
    for (i, j), node in floor.items():
        cage.add_beam(node, base[(i, j)], "bounce_support")
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            anchor = base.get((i + di, j + dj))
            if anchor:
                cage.add_beam(node, anchor, "bounce_shear")
        for di, dj in ((1, 0), (0, 1), (1, 1), (1, -1)):
            neighbour = floor.get((i + di, j + dj))
            if neighbour:
                cage.add_beam(node, neighbour, "membrane")
    for i in range(len(F) - 1):
        for j in range(len(F) - 1):
            cage.add_quad(
                [floor[(i, j)], floor[(i + 1, j)], floor[(i + 1, j + 1)], floor[(i, j + 1)]],
                ground_model="asphalt",
            )

    def build_wall(
        prefix: str,
        stations: list[int],
        frame_point,
        inner_point,
        floor_edge,
        flip_inner: bool,
        flip_outer: bool,
    ) -> None:
        frame_nodes: dict[tuple[int, int], str] = {}
        inner_nodes: dict[tuple[int, int], str] = {}
        for order, station in enumerate(stations):
            for level, z in enumerate(FRAME_Z):
                frame_nodes[(order, level)] = cage.add_node(
                    f"{prefix}_frame_{order}_{level}",
                    frame_point(station, z),
                    fixed=True,
                    collision=True,
                    weight=150.0,
                )
            for level, z in enumerate(WALL_Z):
                inner_nodes[(order, level)] = cage.add_node(
                    f"{prefix}_inner_{order}_{level}",
                    inner_point(station, z),
                    fixed=False,
                    collision=True,
                    weight=30.0,
                    friction=0.8,
                )
        for order, station in enumerate(stations):
            for level in range(len(FRAME_Z) - 1):
                cage.add_beam(frame_nodes[(order, level)], frame_nodes[(order, level + 1)])
            if order > 0:
                for level in range(len(FRAME_Z)):
                    cage.add_beam(frame_nodes[(order - 1, level)], frame_nodes[(order, level)])
                for level in range(len(WALL_Z)):
                    cage.add_beam(
                        inner_nodes[(order - 1, level)],
                        inner_nodes[(order, level)],
                        "membrane",
                    )
            cage.add_beam(frame_nodes[(order, 0)], base[floor_edge(station)])
            cage.add_beam(inner_nodes[(order, 0)], frame_nodes[(order, 0)], "pillow")
            cage.add_beam(inner_nodes[(order, 0)], frame_nodes[(order, 1)], "pillow")
            cage.add_beam(inner_nodes[(order, 1)], frame_nodes[(order, 1)], "pillow")
            cage.add_beam(inner_nodes[(order, 1)], frame_nodes[(order, 2)], "pillow")
            cage.add_beam(inner_nodes[(order, 0)], inner_nodes[(order, 1)], "membrane")
            cage.add_beam(inner_nodes[(order, 0)], floor[floor_edge(station)], "pillow")
        for order in range(len(stations) - 1):
            a = floor[floor_edge(stations[order])]
            b = floor[floor_edge(stations[order + 1])]
            c = inner_nodes[(order + 1, 0)]
            d = inner_nodes[(order, 0)]
            lower = [a, b, c, d]
            upper = [
                inner_nodes[(order, 0)],
                inner_nodes[(order + 1, 0)],
                inner_nodes[(order + 1, 1)],
                inner_nodes[(order, 1)],
            ]
            outer = [
                frame_nodes[(order, 0)],
                frame_nodes[(order + 1, 0)],
                frame_nodes[(order + 1, 2)],
                frame_nodes[(order, 2)],
            ]
            if flip_inner:
                lower.reverse()
                upper.reverse()
            if flip_outer:
                outer.reverse()
            cage.add_quad(lower, ground_model="metal")
            cage.add_quad(upper, ground_model="metal")
            cage.add_quad(outer, ground_model="metal")

    all_columns = list(range(len(S)))
    # East wall: interior is -X, so inner quads flip; outer quads face +X.
    build_wall(
        "wall_e",
        all_columns,
        lambda j, z: (FRAME, S[j], z),
        lambda j, z: (INNER, S[j], z),
        lambda j: (spec.GRID, NEAREST_F[j]),
        flip_inner=True,
        flip_outer=False,
    )
    build_wall(
        "wall_w",
        all_columns,
        lambda j, z: (-FRAME, S[j], z),
        lambda j, z: (-INNER, S[j], z),
        lambda j: (0, NEAREST_F[j]),
        flip_inner=False,
        flip_outer=True,
    )
    build_wall(
        "wall_n",
        all_columns,
        lambda i, z: (S[i], FRAME, z),
        lambda i, z: (S[i], INNER, z),
        lambda i: (NEAREST_F[i], spec.GRID),
        flip_inner=False,
        flip_outer=True,
    )
    build_wall(
        "wall_s_left",
        [0, 1, 2],
        lambda i, z: (S[i], -FRAME, z),
        lambda i, z: (S[i], -INNER, z),
        lambda i: (NEAREST_F[i], 0),
        flip_inner=True,
        flip_outer=False,
    )
    build_wall(
        "wall_s_right",
        [3, 4, 5],
        lambda i, z: (S[i], -FRAME, z),
        lambda i, z: (S[i], -INNER, z),
        lambda i: (NEAREST_F[i], 0),
        flip_inner=True,
        flip_outer=False,
    )

    # Entry ramp through the south gate.
    ramp_ground = {}
    ramp_top = {}
    for side, x in (("l", F[GATE_F[0]]), ("r", F[GATE_F[1]])):
        ramp_ground[side] = cage.add_node(
            f"ramp_ground_{side}",
            (x, spec.RAMP_GROUND_Y, 0.0),
            fixed=True,
            collision=True,
        )
        ramp_top[side] = cage.add_node(
            f"ramp_top_{side}",
            (x, -10.3, FLOOR_Z - 0.05),
            fixed=True,
            collision=True,
        )
    cage.add_beam(ramp_ground["l"], ramp_ground["r"])
    cage.add_beam(ramp_top["l"], ramp_top["r"])
    for side, column in (("l", GATE_F[0]), ("r", GATE_F[1])):
        cage.add_beam(ramp_ground[side], ramp_top[side])
        cage.add_beam(ramp_top[side], base[(column, 0)])
        cage.add_beam(ramp_top[side], floor[(column, 0)], "pillow")
    cage.add_quad(
        [ramp_ground["l"], ramp_ground["r"], ramp_top["r"], ramp_top["l"]],
        ground_model="asphalt",
    )
    cage.add_quad(
        [
            ramp_top["l"],
            ramp_top["r"],
            floor[(GATE_F[1], 0)],
            floor[(GATE_F[0], 0)],
        ],
        ground_model="asphalt",
    )

    cage.set_refnodes_existing(
        ref=base[(4, 4)],
        back=base[(4, 3)],
        left=base[(0, 4)],
        up=cage.nodes[cage.node_index[f"{MOD_ID}_wall_e_frame_2_2"]]["id"],
    )
    cage.set_spawn_envelope(
        [
            f"{MOD_ID}_wall_e_frame_0_0",
            f"{MOD_ID}_wall_e_frame_5_0",
            f"{MOD_ID}_wall_e_frame_0_2",
            f"{MOD_ID}_wall_e_frame_5_2",
            f"{MOD_ID}_wall_w_frame_0_0",
            f"{MOD_ID}_wall_w_frame_5_0",
            f"{MOD_ID}_wall_w_frame_0_2",
            f"{MOD_ID}_wall_w_frame_5_2",
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
        camera_location=(24.0, -30.0, 16.0),
        look_at=(0.0, 0.0, 2.5),
    )
    print("BOUNCY_CASTLE generator complete")


if __name__ == "__main__":
    main()
