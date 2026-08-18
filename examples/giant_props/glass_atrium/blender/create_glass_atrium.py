"""Deterministic Blender generator for The Glass Atrium.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/glass_atrium/blender/create_glass_atrium.py
"""

from __future__ import annotations

import itertools
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

G = spec.GLASS_HALF
F = spec.FRAME_HALF


def floor_z(index_from_top: int) -> float:
    """Authored z of glass floor ``index_from_top`` (1 = skylight floor)."""

    return spec.FLOOR_Z0 + (spec.FLOOR_COUNT - index_from_top) * spec.FLOOR_DZ


def ring_points() -> list[tuple[float, float]]:
    """12 anchor/wall points walking the perimeter counter-clockwise from
    the south-west corner. Segment 1 (points 1-2) is the -Y door bay —
    its width comes from DOOR_HALF_WIDTH so the collision opening always
    matches the visual archway (a 2.3 hard-code left invisible 0.3 m jambs
    inside the visible arch; adversarial-review finding 2026-07-23)."""

    e = spec.DOOR_HALF_WIDTH
    return [
        (-F, -F),
        (-e, -F),
        (e, -F),
        (F, -F),
        (F, -e),
        (F, e),
        (F, F),
        (e, F),
        (-e, F),
        (-F, F),
        (-F, e),
        (-F, -e),
    ]


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def build_visual(materials) -> list:
    steel = materials[f"{MOD_ID}_steel_frame"]
    girder = materials[f"{MOD_ID}_girder_red"]
    wall_glass = materials[f"{MOD_ID}_glass_wall"]
    cushion = materials[f"{MOD_ID}_cushion_blue"]
    hazard = materials[f"{MOD_ID}_lift_hazard"]
    asphalt = materials[f"{MOD_ID}_asphalt"]
    white = materials[f"{MOD_ID}_trim_white"]

    objects = []
    # Corner columns carry the whole frame silhouette.
    for sx in (-1, 1):
        for sy in (-1, 1):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_column_{'e' if sx > 0 else 'w'}{'n' if sy > 0 else 's'}",
                    (sx * (F + 0.35), sy * (F + 0.35), spec.RIM_Z / 2),
                    (0.85, 0.85, spec.RIM_Z),
                    steel,
                    bevel=0.06,
                    metric_uv=(1.6, 1.6),
                )
            )
    # Static red edge girders under every glass floor (these stay when the
    # pane falls, keeping each storey line readable).
    for index in range(1, spec.FLOOR_COUNT + 1):
        z = floor_z(index) - 0.3
        for edge, (cx, cy, dx, dy) in {
            "n": (0.0, F, 2 * F + 0.6, 0.42),
            "s": (0.0, -F, 2 * F + 0.6, 0.42),
            "e": (F, 0.0, 0.42, 2 * F + 0.6),
            "w": (-F, 0.0, 0.42, 2 * F + 0.6),
        }.items():
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_girder_{index:02d}_{edge}",
                    (cx, cy, z),
                    (dx, dy, 0.36),
                    girder,
                    bevel=0.03,
                )
            )
    # Curtain walls: translucent glass slabs just outside the anchor ring,
    # the -Y wall gets the exit archway boolean-cut through it.
    wall_height = spec.RIM_Z - 0.6
    wall_z = wall_height / 2 + 0.3
    walls = {
        "n": ((0.0, F + 0.15, wall_z), (2 * F + 1.6, 0.14, wall_height)),
        "s": ((0.0, -F - 0.15, wall_z), (2 * F + 1.6, 0.14, wall_height)),
        "e": ((F + 0.15, 0.0, wall_z), (0.14, 2 * F + 1.6, wall_height)),
        "w": ((-F - 0.15, 0.0, wall_z), (0.14, 2 * F + 1.6, wall_height)),
    }
    for name, (center, dims) in walls.items():
        wall = bk.add_box(f"{MOD_ID}_wall_{name}", center, dims, wall_glass, bevel=0.0)
        if name == "s":
            cutter = bk.add_box(
                f"{MOD_ID}_door_cutter",
                (0.0, -F - 0.15, spec.DOOR_TOP_Z / 2),
                (2 * spec.DOOR_HALF_WIDTH, 2.0, spec.DOOR_TOP_Z),
                None,
                bevel=0.0,
            )
            bk.cut_openings(wall, [cutter])
        objects.append(wall)
    # Steel mullions along the ring lines give the curtain wall its grid.
    mull = spec.DOOR_HALF_WIDTH
    for name, points in (
        ("s", ((-mull, -F - 0.15), (mull, -F - 0.15))),
        ("n", ((-mull, F + 0.15), (mull, F + 0.15))),
        ("e", ((F + 0.15, -mull), (F + 0.15, mull))),
        ("w", ((-F - 0.15, -mull), (-F - 0.15, mull))),
    ):
        for index, (mx, my) in enumerate(points):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_mullion_{name}_{index}",
                    (mx, my, spec.RIM_Z / 2 + 1.4),
                    (0.2, 0.2, spec.RIM_Z - 2.8 - (spec.DOOR_TOP_Z if name == "s" else 0.0)),
                    steel,
                    bevel=0.02,
                )
            )
            if name == "s":
                objects[-1].location.z = (spec.RIM_Z + spec.DOOR_TOP_Z) / 2 + 0.7
    # Archway canopy over the exit.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_door_canopy",
            (0.0, -F - 0.6, spec.DOOR_TOP_Z + 0.45),
            (2 * spec.DOOR_HALF_WIDTH + 1.2, 1.6, 0.5),
            girder,
            bevel=0.06,
        )
    )
    # Open skylight rim.
    for edge, (cx, cy, dx, dy) in {
        "n": (0.0, F + 0.35, 2 * F + 1.9, 0.9),
        "s": (0.0, -F - 0.35, 2 * F + 1.9, 0.9),
        "e": (F + 0.35, 0.0, 0.9, 2 * F + 1.9),
        "w": (-F - 0.35, 0.0, 0.9, 2 * F + 1.9),
    }.items():
        objects.append(
            bk.add_box(
                f"{MOD_ID}_rim_{edge}",
                (cx, cy, spec.RIM_Z + 0.3),
                (dx, dy, 0.7),
                steel,
                bevel=0.06,
                metric_uv=(1.6, 1.6),
            )
        )
    # Lobby crash cushion (collision deck rides on the cage base lattice).
    objects.append(
        bk.add_box(
            f"{MOD_ID}_cushion",
            (0.0, 0.0, spec.CUSHION_TOP_Z / 2),
            (2 * G + 0.8, 2 * G + 0.8, spec.CUSHION_TOP_Z),
            cushion,
            bevel=0.16,
            metric_uv=(2.2, 2.2),
        )
    )
    # Exit ramp down from the lobby deck (matches the cage ramp wedge).
    ramp_rise = spec.CUSHION_TOP_Z - 0.03
    ramp_run = 3.4
    ramp_angle = math.atan2(ramp_rise, ramp_run)
    objects.append(
        bk.add_box(
            f"{MOD_ID}_exit_ramp",
            (0.0, -F - 0.3 - ramp_run / 2, 0.03 + ramp_rise / 2 - 0.06),
            (2 * spec.DOOR_HALF_WIDTH, math.hypot(ramp_run, ramp_rise) + 0.2, 0.12),
            asphalt,
            bevel=0.0,
            rotation=(-ramp_angle, 0.0, 0.0),
            metric_uv=(1.8, 1.8),
        )
    )
    for side in (-1, 1):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ramp_edge_{'l' if side < 0 else 'r'}",
                (
                    side * (spec.DOOR_HALF_WIDTH - 0.12),
                    -F - 0.3 - ramp_run / 2,
                    0.1 + ramp_rise / 2 - 0.06,
                ),
                (0.2, math.hypot(ramp_run, ramp_rise) + 0.2, 0.13),
                white,
                bevel=0.0,
                rotation=(-ramp_angle, 0.0, 0.0),
            )
        )
    # Freight lift pad outside the archway.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_lift_pad",
            (0.0, spec.LIFT_PAD_Y, 0.04),
            (5.2, 5.2, 0.08),
            hazard,
            bevel=0.0,
            metric_uv=(2.6, 2.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_lift_apron",
            (0.0, spec.LIFT_PAD_Y + 4.0, 0.03),
            (4.2, 2.6, 0.06),
            asphalt,
            bevel=0.0,
        )
    )
    for index, ay in enumerate((-19.5, -17.8)):
        for side in (-1, 1):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_arrow_{index}_{'l' if side < 0 else 'r'}",
                    (side * 0.7, ay, 0.05),
                    (1.5, 0.36, 0.06),
                    white,
                    bevel=0.0,
                    rotation=(0.0, 0.0, -side * math.radians(35.0)),
                )
            )
    return objects


def build_floor_meshes(materials) -> dict[str, list]:
    """One flexbody mesh per glass floor: the pane plus its crossbeams,
    skinned to that floor's free nodes so the whole sheet falls when the
    hangers snap."""

    glass = materials[f"{MOD_ID}_glass_pane"]
    girder = materials[f"{MOD_ID}_girder_red"]
    meshes: dict[str, list] = {}
    for index in range(1, spec.FLOOR_COUNT + 1):
        z = floor_z(index)
        pane = bk.add_box(
            f"{MOD_ID}_pane_{index:02d}",
            (0.0, 0.0, z + 0.02),
            (2 * G + 0.3, 2 * G + 0.3, 0.13),
            glass,
            bevel=0.0,
            metric_uv=(3.0, 3.0),
        )
        beams = []
        for beam_index, by in enumerate((-2.0, 2.0)):
            beams.append(
                bk.add_box(
                    f"{MOD_ID}_crossbeam_{index:02d}_{beam_index}",
                    (0.0, by, z - 0.16),
                    (2 * G + 0.3, 0.34, 0.22),
                    girder,
                    bevel=0.03,
                )
            )
        meshes[f"{MOD_ID}_floor_{index:02d}"] = [pane, *beams]
    return meshes


def build_cage() -> tuple[bk.CageBuilder, list[dict[str, object]]]:
    cage = bk.CageBuilder(MOD_ID)
    cage.define_beam_spec(
        "glass_sheet",
        beamSpring=1600000.0,
        beamDamp=2600.0,
        beamDeform=60000.0,
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "hanger",
        beamSpring=5000000.0,
        beamDamp=5000.0,
        beamDeform=200000.0,
        beamStrength="FLT_MAX",
    )

    # Lobby deck: fixed collision top doubles as the crash cushion surface.
    # Side faces close the 1.05 m skirt so cars cannot nose under the deck
    # from outside (footprint matches the wall line so the skirt sits flush
    # behind the visual glass).
    base = cage.add_box_lattice(
        "base",
        (-F - 0.15, -F - 0.15, 0.0),
        (F + 0.15, F + 0.15, spec.CUSHION_TOP_Z),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("top", "north", "south", "east", "west"),
        face_ground_models={"top": "asphalt"},
    )
    # Exit ramp: the deck is 1.05 m proud of the terrain and the archway
    # otherwise ends in a sheer ledge. Fixed wedge, asphalt top.
    ramp_top: list[str] = []
    ramp_bottom: list[str] = []
    for column, x in enumerate((-spec.DOOR_HALF_WIDTH, 0.0, spec.DOOR_HALF_WIDTH)):
        ramp_top.append(
            cage.add_node(
                f"ramp_t_{column}",
                (x, -F - 0.3, spec.CUSHION_TOP_Z),
                fixed=True,
                collision=True,
            )
        )
        ramp_bottom.append(
            cage.add_node(
                f"ramp_b_{column}",
                (x, -F - 3.7, 0.03),
                fixed=True,
                collision=True,
            )
        )
    for column in range(2):
        cage.add_beam(ramp_top[column], ramp_top[column + 1])
        cage.add_beam(ramp_bottom[column], ramp_bottom[column + 1])
    for column in range(3):
        cage.add_beam(ramp_top[column], ramp_bottom[column])
    cage.add_beam(ramp_top[0], ramp_bottom[1])
    cage.add_beam(ramp_top[2], ramp_bottom[1])
    cage.stitch(ramp_top[1], base[(1, 0, 1)])
    cage.stitch(ramp_top[0], base[(0, 0, 1)])
    cage.stitch(ramp_top[2], base[(2, 0, 1)])
    for column in range(2):
        cage.add_quad(
            [
                ramp_top[column],
                ramp_bottom[column],
                ramp_bottom[column + 1],
                ramp_top[column + 1],
            ],
            ground_model="asphalt",
        )

    # Anchor/wall rings: ground, one per glass floor, one at the rim.
    points = ring_points()
    ring_zs = [spec.CUSHION_TOP_Z]
    ring_zs.extend(floor_z(index) for index in range(spec.FLOOR_COUNT, 0, -1))
    ring_zs.append(spec.RIM_Z)
    rings: list[list[str]] = []
    for level, z in enumerate(ring_zs):
        ring = [
            cage.add_node(
                f"ring_{level:02d}_{point_index:02d}",
                (px, py, z),
                fixed=True,
                collision=True,
            )
            for point_index, (px, py) in enumerate(points)
        ]
        for point_index in range(12):
            cage.add_beam(ring[point_index], ring[(point_index + 1) % 12])
        rings.append(ring)
    for lower, upper in itertools.pairwise(rings):
        for point_index in range(12):
            cage.add_beam(lower[point_index], upper[point_index])
            cage.add_beam(lower[point_index], upper[(point_index + 1) % 12])
    # Wall collision quads between rings; segment 1 on the -Y face stays
    # open below the archway top. Quads wind toward the shaft interior —
    # the side cars hit.
    for level, (lower, upper) in enumerate(itertools.pairwise(rings)):
        lower_z = ring_zs[level]
        for point_index in range(12):
            if point_index == 1 and lower_z < spec.DOOR_TOP_Z:
                continue
            a = lower[point_index]
            b = lower[(point_index + 1) % 12]
            c = upper[(point_index + 1) % 12]
            d = upper[point_index]
            cage.add_quad([b, a, d, c], ground_model="metal")
    # Tie the ground ring into the base lattice so the cage graph is one
    # component (corner ring points onto the nearest base top corners).
    corner_map = {0: (0, 0), 3: (2, 0), 6: (2, 2), 9: (0, 2)}
    for point_index, (bx, by) in corner_map.items():
        cage.stitch(rings[0][point_index], base[(bx, by, 1)])

    # Glass floors: 4x4 free nodes per pane, breakable hangers to the ring.
    span = [-G, -G / 3, G / 3, G]
    floors: list[dict[str, object]] = []
    for index in range(1, spec.FLOOR_COUNT + 1):
        z = floor_z(index)
        strength = spec.GLASS_BREAK_TOP_N + (index - 1) * spec.GLASS_BREAK_STEP_N
        group = f"floor_{index:02d}"
        break_group = f"{MOD_ID}_{group}"
        ring = rings[1 + (spec.FLOOR_COUNT - index)]
        grid: dict[tuple[int, int], str] = {}
        for ix, x in enumerate(span):
            for iy, y in enumerate(span):
                grid[(ix, iy)] = cage.add_node(
                    f"{group}_{ix}{iy}",
                    (x, y, z),
                    fixed=False,
                    collision=True,
                    weight=55.0,
                    friction=0.55,
                    group=group,
                )
        for (ix, iy), node in grid.items():
            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                neighbour = grid.get((ix + dx, iy + dy))
                if neighbour:
                    cage.add_beam(node, neighbour, "glass_sheet")
        # Perimeter pane node -> nearest ring anchor, one brittle hanger
        # each, all in the floor's breakGroup so one failure drops the lot.
        anchor_for = {
            (0, 0): 0,
            (1, 0): 1,
            (2, 0): 2,
            (3, 0): 3,
            (3, 1): 4,
            (3, 2): 5,
            (3, 3): 6,
            (2, 3): 7,
            (1, 3): 8,
            (0, 3): 9,
            (0, 2): 10,
            (0, 1): 11,
        }
        for pane_key, ring_index in anchor_for.items():
            cage.add_beam(
                grid[pane_key],
                ring[ring_index],
                "hanger",
                extra={
                    "breakGroup": break_group,
                    "beamStrength": strength,
                    "beamDeform": strength,
                },
            )
        # Pane collision surface, gone the instant the breakGroup fires.
        for ix in range(3):
            for iy in range(3):
                cage.add_quad(
                    [
                        grid[(ix, iy)],
                        grid[(ix + 1, iy)],
                        grid[(ix + 1, iy + 1)],
                        grid[(ix, iy + 1)],
                    ],
                    ground_model="metal",
                    extra={"breakGroup": break_group},
                )
        floors.append(
            {
                "index": index,
                "z": round(z, 3),
                "cid": cage.node_index[grid[(1, 1)]],
            }
        )

    cage.set_refnodes_existing(
        ref=base[(1, 1, 0)],
        back=base[(1, 0, 0)],
        left=base[(0, 1, 0)],
        up=base[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            rings[0][0],
            rings[0][3],
            rings[0][6],
            rings[0][9],
            rings[-1][0],
            rings[-1][3],
            rings[-1][6],
            rings[-1][9],
        ]
    )
    cage.auto_base_nodes()
    return cage, floors


def main() -> None:
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)
    floor_meshes = build_floor_meshes(materials)

    mesh_groups = {f"{MOD_ID}_visual": visual_objects, **floor_meshes}
    visual = bk.export_multi_flexbody(MOD_ID, VEHICLE_DIR / f"{MOD_ID}.dae", mesh_groups)

    cage, floors = build_cage()
    behavior = dict(spec.BEHAVIOR)
    behavior["floors"] = floors
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
        flexbodies_extra=[
            {"mesh": f"{MOD_ID}_floor_{index:02d}", "groups": [f"floor_{index:02d}"]}
            for index in range(1, spec.FLOOR_COUNT + 1)
        ],
    )
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(30.0, -34.0, 20.0),
        look_at=(0.0, 0.0, 16.0),
    )
    print(f"GLASS_ATRIUM generator complete: {spec.FLOOR_COUNT} glass floors")


if __name__ == "__main__":
    main()
