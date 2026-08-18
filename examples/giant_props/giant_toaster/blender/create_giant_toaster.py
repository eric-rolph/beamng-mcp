"""Deterministic Blender generator for The Giant Toaster (upright redesign).

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/giant_toaster/blender/create_giant_toaster.py

2026-07-23 redesign: real two-slice silhouette — tall rounded chrome body
with art-deco end domes on a bakelite plinth, DEEP slots the car sits down
inside (glowing element strips on the slot walls), a trestle ramp to a
rooftop landing, the lever on a side track, and the browning dial on the
east face of the base.
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
TEXTURE_DIR = EXAMPLE_ROOT / "textures"

HX = spec.BODY_HALF_X
HY = spec.BODY_HALF_Y
TOP = spec.BODY_TOP_Z
BASE = spec.BASE_TOP_Z
SCX = spec.SLOT_CENTER_X
SFZ = spec.SLOT_FLOOR_Z
SY0 = spec.SLOT_Y_MIN
SY1 = spec.SLOT_Y_MAX
LAND_Y0 = spec.LANDING_Y_MIN
RAMP_Y = spec.RAMP_GROUND_Y
INNER_X = 0.1  # slot inner wall |x|
OUTER_X = 3.0  # slot outer wall |x|


def build_visual(materials) -> list:
    chrome = materials[f"{MOD_ID}_chrome"]
    chrome_dark = materials[f"{MOD_ID}_chrome_dark"]
    slot_dark = materials[f"{MOD_ID}_slot_dark"]
    element = materials[f"{MOD_ID}_element_glow"]
    bakelite = materials[f"{MOD_ID}_bakelite"]
    dial_cream = materials[f"{MOD_ID}_dial_cream"]
    ramp_steel = materials[f"{MOD_ID}_ramp_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]

    objects = []
    # Bakelite plinth and puck feet.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_plinth",
            (0.0, 0.0, BASE / 2),
            (2 * HX + 0.5, 2 * HY + 0.5, BASE),
            bakelite,
            bevel=0.16,
            metric_uv=(2.0, 2.0),
        )
    )
    for index, (fx, fy) in enumerate(
        ((-HX + 0.3, -HY + 0.3), (HX - 0.3, -HY + 0.3), (-HX + 0.3, HY - 0.3), (HX - 0.3, HY - 0.3))
    ):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_foot_{index}",
                (fx, fy, 0.08),
                0.5,
                0.16,
                bakelite,
                vertices=16,
            )
        )
    # Chrome shell: tall rounded body plus art-deco end domes.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_shell",
            (0.0, 0.0, (BASE + TOP) / 2),
            (2 * HX, 2 * HY - 1.6, TOP - BASE),
            chrome,
            bevel=0.85,
            metric_uv=(2.6, 2.6),
        )
    )
    for side, sy in (("s", -(HY - 0.85)), ("n", HY - 0.85)):
        objects.append(
            bk.add_sphere(
                f"{MOD_ID}_dome_{side}",
                (0.0, sy, (BASE + TOP) / 2),
                2.15,
                chrome,
                segments=28,
                rings=18,
                scale=(HX / 2.15, 0.62, (TOP - BASE) / 2 / 2.15),
            )
        )
    # Cut the two slot openings down through the crown (shell + domes).
    import bpy

    shell = objects[-3]
    dome_s = objects[-2]
    dome_n = objects[-1]
    for target in (shell, dome_s, dome_n):
        cutters = []
        for sx in (-SCX, SCX):
            cutters.append(
                bk.add_box(
                    f"{MOD_ID}_slot_cutter_{target.name[-6:]}_{'l' if sx < 0 else 'r'}",
                    (sx, (SY0 + SY1) / 2, TOP - 0.9),
                    (2.75, SY1 - SY0 + 0.4, 2.6),
                    None,
                    bevel=0.0,
                )
            )
        bpy.ops.object.select_all(action="DESELECT")
        bk.cut_openings(target, cutters)
    # Slot mouth trim rings: thin dark frames around each opening (a full
    # lid here previously hid the slot cuts entirely).
    for side, sx in (("l", -SCX), ("r", SCX)):
        for edge, (cx, cy, dx, dy) in {
            "e": (sx + 1.45, (SY0 + SY1) / 2, 0.16, SY1 - SY0 + 0.3),
            "w": (sx - 1.45, (SY0 + SY1) / 2, 0.16, SY1 - SY0 + 0.3),
            "n": (sx, SY1 + 0.12, 2.9, 0.16),
        }.items():
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_mouth_trim_{side}_{edge}",
                    (cx, cy, TOP + 0.04),
                    (dx, dy, 0.1),
                    chrome_dark,
                    bevel=0.03,
                )
            )
    # Slot cavities: dark liner walls, far-end wall, and element strips.
    for side, sx in (("l", -SCX), ("r", SCX)):
        for wall, wx in (
            ("inner", math.copysign(INNER_X, sx)),
            ("outer", math.copysign(OUTER_X, sx)),
        ):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_slot_wall_{side}_{wall}",
                    (wx, (SY0 + SY1) / 2, (SFZ + TOP) / 2 - 0.02),
                    (0.08, SY1 - SY0, TOP - SFZ + 0.25),
                    slot_dark,
                    bevel=0.0,
                )
            )
            for e_index, ey in enumerate((-3.6, -1.6, 0.4, 2.4)):
                objects.append(
                    bk.add_box(
                        f"{MOD_ID}_element_{side}_{wall}_{e_index}",
                        (wx + math.copysign(0.06, -wx), ey, SFZ + 0.45),
                        (0.05, 1.1, 0.55),
                        element,
                        bevel=0.0,
                    )
                )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_slot_end_{side}",
                (sx, SY1 + 0.06, (SFZ + TOP) / 2),
                (2.75, 0.12, TOP - SFZ + 0.2),
                slot_dark,
                bevel=0.0,
            )
        )
    # Entry lip wedges: visible chrome down-ramps into each slot.
    lip_run = 2.6
    lip_drop = TOP - SFZ
    lip_len = math.hypot(lip_run, lip_drop)
    lip_angle = math.atan2(lip_drop, lip_run)
    for side, sx in (("l", -SCX), ("r", SCX)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_slot_lip_{side}",
                (sx, SY0 + lip_run / 2, (TOP + SFZ) / 2 - 0.09),
                (2.8, lip_len, 0.14),
                chrome_dark,
                bevel=0.02,
                rotation=(-lip_angle, 0.0, 0.0),
            )
        )
    # Rooftop landing shelf with hazard nose and guard rails.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_landing",
            (0.0, (LAND_Y0 - HY) / 2 + 0.0, TOP - 0.14),
            (2 * HX, HY - -LAND_Y0, 0.28),
            ramp_steel,
            bevel=0.04,
            metric_uv=(1.6, 1.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_landing_nose",
            (0.0, LAND_Y0 + 0.1, TOP - 0.02),
            (2 * HX, 0.2, 0.05),
            hazard,
            bevel=0.0,
        )
    )
    for side, sx in (("l", -HX + 0.12), ("r", HX - 0.12)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_landing_rail_{side}",
                (sx, (LAND_Y0 - HY) / 2, TOP + 0.55),
                0.07,
                HY - -LAND_Y0,
                chrome_dark,
                vertices=10,
                axis="Y",
            )
        )
    # Trestle ramp with guard rails and legs.
    run = LAND_Y0 - RAMP_Y
    ramp_len = math.hypot(run, TOP)
    angle = math.atan2(TOP, run)
    normal = (0.0, -math.sin(angle), math.cos(angle))
    mid_y = (RAMP_Y + LAND_Y0) / 2
    objects.append(
        bk.add_box(
            f"{MOD_ID}_ramp",
            (0.0, mid_y - normal[1] * 0.14, TOP / 2 - normal[2] * 0.14),
            (2 * HX, ramp_len, 0.28),
            ramp_steel,
            bevel=0.0,
            rotation=(angle, 0.0, 0.0),
            metric_uv=(1.6, 1.6),
        )
    )
    for side, sx in (("l", -HX + 0.12), ("r", HX - 0.12)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_ramp_rail_{side}",
                (sx, mid_y - normal[1] * 0.14, TOP / 2 - normal[2] * 0.14 + 0.75),
                0.07,
                ramp_len - 0.6,
                chrome_dark,
                vertices=10,
                axis="Z",
            )
        )
        objects[-1].rotation_euler = (angle, 0.0, 0.0)
        import bpy

        bpy.context.view_layer.objects.active = objects[-1]
        objects[-1].select_set(True)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
        objects[-1].select_set(False)
    for leg_index, leg_y in enumerate((-20.5, -16.5, -12.5, -9.0)):
        leg_top = TOP * (leg_y - RAMP_Y) / run - 0.2
        if leg_top <= 0.3:
            continue
        for side, sx in (("l", -HX + 0.5), ("r", HX - 0.5)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_trestle_{leg_index}_{side}",
                    (sx, leg_y, leg_top / 2),
                    (0.3, 0.3, leg_top),
                    ramp_steel,
                    bevel=0.02,
                )
            )
    # Browning dial on the east base face.
    dial_x, dial_y, dial_z = spec.DIAL_CENTER
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_dial_ring",
            (dial_x - 0.06, dial_y, dial_z),
            spec.DIAL_RADIUS + 0.16,
            0.18,
            bakelite,
            vertices=28,
            axis="X",
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_dial_face",
            (dial_x + 0.02, dial_y, dial_z),
            spec.DIAL_RADIUS,
            0.1,
            dial_cream,
            vertices=28,
            axis="X",
        )
    )
    for index, angle_deg in enumerate(spec.BEHAVIOR["dial_angles_deg"]):
        tick_angle = math.radians(angle_deg)
        radius = spec.DIAL_RADIUS - 0.18
        objects.append(
            bk.add_box(
                f"{MOD_ID}_dial_tick_{index}",
                (
                    dial_x + 0.08,
                    dial_y - math.sin(tick_angle) * radius,
                    dial_z + math.cos(tick_angle) * radius,
                ),
                (0.05, 0.08, 0.26),
                bakelite,
                bevel=0.0,
                rotation=(tick_angle, 0.0, 0.0),
            )
        )
    # Lever track on the east shell face.
    lx, ly, lz = spec.LEVER_PIVOT
    objects.append(
        bk.add_box(
            f"{MOD_ID}_lever_track",
            (lx - 0.04, ly, lz - 0.95),
            (0.09, 0.4, 2.4),
            chrome_dark,
            bevel=0.02,
        )
    )
    # Cord and plug at the north base, toast slices leaning on the plinth.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_cord",
            (1.6, HY + 1.0, 0.18),
            0.12,
            1.8,
            bakelite,
            vertices=12,
            axis="Y",
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_plug",
            (1.6, HY + 2.2, 0.3),
            (0.9, 1.3, 0.6),
            bakelite,
            bevel=0.08,
        )
    )
    for prong in range(2):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_plug_prong_{prong}",
                (1.35 + prong * 0.5, HY + 3.1, 0.3),
                (0.14, 0.5, 0.08),
                chrome_dark,
                bevel=0.0,
            )
        )
    # Crumb tray drawer inset low on the east flank (real toasters carry
    # one; the leaning giant toast slices were cut 2026-07-23 — player
    # called them out as the cartoon giveaway).
    objects.append(
        bk.add_box(
            f"{MOD_ID}_crumb_tray",
            (HX + 0.28, 0.0, 0.38),
            (0.1, 4.6, 0.42),
            chrome_dark,
            bevel=0.03,
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_crumb_tray_handle",
            (HX + 0.36, 0.0, 0.38),
            (0.12, 1.4, 0.16),
            bakelite,
            bevel=0.05,
        )
    )
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    chrome_dark = materials[f"{MOD_ID}_chrome_dark"]
    plate_steel = materials[f"{MOD_ID}_plate_steel"]
    pointer_red = materials[f"{MOD_ID}_pointer_red"]
    bakelite = materials[f"{MOD_ID}_bakelite"]

    parts: dict[str, dict[str, object]] = {}
    for side, sx in (("l", -SCX), ("r", SCX)):
        plate = bk.add_box(
            f"{MOD_ID}_plate_{side}",
            (sx, (SY0 + SY1) / 2 + 0.6, SFZ - 0.06),
            (2.8, SY1 - SY0 - 1.5, 0.12),
            plate_steel,
            bevel=0.04,
        )
        parts[f"plate_{side}"] = {
            "objects": [plate],
            "pivot": (sx, (SY0 + SY1) / 2 + 0.6, SFZ - 0.06),
        }

    lx, ly, lz = spec.LEVER_PIVOT
    knob = bk.add_box(
        f"{MOD_ID}_lever_knob",
        (lx + 0.28, ly, lz),
        (0.42, 0.7, 0.42),
        bakelite,
        bevel=0.12,
    )
    stem = bk.add_cylinder(
        f"{MOD_ID}_lever_stem",
        (lx + 0.05, ly, lz),
        0.08,
        0.34,
        chrome_dark,
        vertices=12,
        axis="X",
    )
    parts["lever_knob"] = {"objects": [knob, stem], "pivot": (lx, ly, lz)}

    dial_x, dial_y, dial_z = spec.DIAL_CENTER
    pointer = bk.add_box(
        f"{MOD_ID}_dial_pointer",
        (dial_x + 0.12, dial_y, dial_z + 0.38),
        (0.09, 0.15, 0.8),
        pointer_red,
        bevel=0.03,
    )
    cap = bk.add_cylinder(
        f"{MOD_ID}_dial_cap",
        (dial_x + 0.12, dial_y, dial_z),
        0.14,
        0.12,
        pointer_red,
        vertices=16,
        axis="X",
    )
    parts["dial_pointer"] = {
        "objects": [pointer, cap],
        "pivot": (dial_x + 0.12, dial_y, dial_z),
    }
    return parts


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    body = cage.add_box_lattice(
        "body",
        (-HX, -HY, 0.0),
        (HX, HY, TOP),
        subdivisions=(2, 2, 2),
        fixed=True,
        collision=False,
        collision_faces=("north", "east", "west"),
    )
    # South face: collide only the lower band (the landing shelf covers the
    # upper approach).
    for ix in range(2):
        quad = [
            body[(ix, 0, 0)],
            body[(ix + 1, 0, 0)],
            body[(ix + 1, 0, 1)],
            body[(ix, 0, 1)],
        ]
        for node in quad:
            cage.nodes[cage.node_index[node]]["collision"] = True
        cage.add_quad(quad, ground_model="metal")

    # Slot interiors: floors, walls, far-end walls, and entry lips.
    # First station pushed out so the entry lip runs ~2.6 m (14 degrees).
    stations = (-2.65, -0.55, 1.5, SY1)
    for side, sign in (("l", -1), ("r", 1)):
        inner_x = INNER_X * sign
        outer_x = OUTER_X * sign
        floor: dict[tuple[str, int], str] = {}
        top_nodes: dict[tuple[str, int], str] = {}
        for j, y in enumerate(stations):
            floor[("i", j)] = cage.add_node(
                f"slot_{side}_floor_i_{j}", (inner_x, y, SFZ), fixed=True, collision=True
            )
            floor[("o", j)] = cage.add_node(
                f"slot_{side}_floor_o_{j}", (outer_x, y, SFZ), fixed=True, collision=True
            )
            top_nodes[("i", j)] = cage.add_node(
                f"slot_{side}_top_i_{j}", (inner_x, y, TOP), fixed=True, collision=True
            )
            top_nodes[("o", j)] = cage.add_node(
                f"slot_{side}_top_o_{j}", (outer_x, y, TOP), fixed=True, collision=True
            )
        lip_i = cage.add_node(f"slot_{side}_lip_i", (inner_x, SY0, TOP), fixed=True, collision=True)
        lip_o = cage.add_node(f"slot_{side}_lip_o", (outer_x, SY0, TOP), fixed=True, collision=True)
        # Connectivity beams.
        previous = None
        for j in range(len(stations)):
            cage.add_beam(floor[("i", j)], floor[("o", j)])
            cage.add_beam(top_nodes[("i", j)], top_nodes[("o", j)])
            cage.add_beam(floor[("i", j)], top_nodes[("i", j)])
            cage.add_beam(floor[("o", j)], top_nodes[("o", j)])
            if previous is not None:
                for key in (("i",), ("o",)):
                    cage.add_beam(floor[(key[0], previous)], floor[(key[0], j)])
                    cage.add_beam(top_nodes[(key[0], previous)], top_nodes[(key[0], j)])
            previous = j
        cage.add_beam(lip_i, lip_o)
        cage.add_beam(lip_i, floor[("i", 0)])
        cage.add_beam(lip_o, floor[("o", 0)])
        cage.add_beam(lip_i, top_nodes[("i", 0)])
        cage.add_beam(lip_o, top_nodes[("o", 0)])
        cage.add_beam(lip_i, body[(1, 0, 2)])
        cage.add_beam(lip_o, body[(0 if sign < 0 else 2, 0, 2)])
        cage.add_beam(floor[("o", len(stations) - 1)], body[(0 if sign < 0 else 2, 1, 2)])
        cage.add_beam(top_nodes[("o", len(stations) - 1)], body[(0 if sign < 0 else 2, 2, 2)])
        # Floor quads (upward).
        for j in range(len(stations) - 1):
            quad = [
                floor[("i", j)],
                floor[("o", j)],
                floor[("o", j + 1)],
                floor[("i", j + 1)],
            ]
            if sign > 0:
                quad = [
                    floor[("o", j)],
                    floor[("i", j)],
                    floor[("i", j + 1)],
                    floor[("o", j + 1)],
                ]
            cage.add_quad(quad, ground_model="metal")
        # Entry lip ramp from the landing edge down to the first floor row.
        lip_quad = [lip_i, lip_o, floor[("o", 0)], floor[("i", 0)]]
        if sign > 0:
            lip_quad = [lip_o, lip_i, floor[("i", 0)], floor[("o", 0)]]
        cage.add_quad(lip_quad, ground_model="metal")
        # Walls: inner and outer, facing INTO the slot, plus the far end.
        for j in range(len(stations) - 1):
            inner_wall = [
                floor[("i", j)],
                floor[("i", j + 1)],
                top_nodes[("i", j + 1)],
                top_nodes[("i", j)],
            ]
            outer_wall = [
                floor[("o", j + 1)],
                floor[("o", j)],
                top_nodes[("o", j)],
                top_nodes[("o", j + 1)],
            ]
            if sign > 0:
                inner_wall = list(reversed(inner_wall))
                outer_wall = list(reversed(outer_wall))
            cage.add_quad(inner_wall, ground_model="metal")
            cage.add_quad(outer_wall, ground_model="metal")
        end_wall = [
            floor[("i", len(stations) - 1)],
            floor[("o", len(stations) - 1)],
            top_nodes[("o", len(stations) - 1)],
            top_nodes[("i", len(stations) - 1)],
        ]
        if sign < 0:
            end_wall = list(reversed(end_wall))
        cage.add_quad(end_wall, ground_model="metal")
        # Rim caps: outer rim (slot outer wall -> body edge) and half the
        # centre bar (slot inner wall -> x 0).
        edge_x = HX * sign
        rim_nodes = {
            j: cage.add_node(f"slot_{side}_rim_{j}", (edge_x, y, TOP), fixed=True, collision=True)
            for j, y in enumerate(stations)
        }
        for j in range(len(stations) - 1):
            cage.add_beam(rim_nodes[j], rim_nodes[j + 1])
            cage.add_beam(rim_nodes[j], top_nodes[("o", j)])
            rim_quad = [
                top_nodes[("o", j)],
                rim_nodes[j],
                rim_nodes[j + 1],
                top_nodes[("o", j + 1)],
            ]
            if sign > 0:
                rim_quad = list(reversed(rim_quad))
            cage.add_quad(rim_quad, ground_model="metal")
        cage.add_beam(rim_nodes[len(stations) - 1], top_nodes[("o", len(stations) - 1)])
        if sign < 0:
            bar_nodes_left = top_nodes
        else:
            bar_nodes_right = top_nodes
    # Centre bar between the two slots' inner top lines.
    for j in range(len(stations) - 1):
        quad = [
            bar_nodes_left[("i", j)],
            bar_nodes_left[("i", j + 1)],
            bar_nodes_right[("i", j + 1)],
            bar_nodes_right[("i", j)],
        ]
        cage.add_quad(quad, ground_model="metal")
        cage.add_beam(bar_nodes_left[("i", j)], bar_nodes_right[("i", j)])

    # Landing shelf.
    land: dict[tuple[int, int], str] = {}
    for i, x in enumerate((-HX, 0.0, HX)):
        land[(i, 0)] = cage.add_node(
            f"landing_{i}_0", (x, LAND_Y0, TOP), fixed=True, collision=True
        )
        # The back row coincides with the body's south-top lattice nodes:
        # reuse them rather than minting zero-length-beam duplicates.
        land[(i, 1)] = body[(i, 0, 2)]
        cage.nodes[cage.node_index[land[(i, 1)]]]["collision"] = True
    for i in range(3):
        cage.add_beam(land[(i, 0)], land[(i, 1)])
        if i > 0:
            cage.add_beam(land[(i - 1, 0)], land[(i, 0)])
    for i in range(2):
        cage.add_quad(
            [land[(i, 0)], land[(i + 1, 0)], land[(i + 1, 1)], land[(i, 1)]],
            ground_model="metal",
        )

    # Trestle ramp: 3x3 node grid from the ground to the landing edge.
    ramp: dict[tuple[int, int], str] = {}
    run = LAND_Y0 - RAMP_Y
    for j, y in enumerate((RAMP_Y, RAMP_Y + run / 2, LAND_Y0)):
        z = TOP * (y - RAMP_Y) / run
        for i, x in enumerate((-HX, 0.0, HX)):
            if j == 2:
                ramp[(i, j)] = land[(i, 0)]
            else:
                ramp[(i, j)] = cage.add_node(
                    f"ramp_{i}_{j}", (x, y, max(z, 0.0)), fixed=True, collision=True
                )
    for j in range(2):
        for i in range(3):
            cage.add_beam(ramp[(i, j)], ramp[(i, j + 1)])
            if i > 0:
                cage.add_beam(ramp[(i - 1, j)], ramp[(i, j)])
        for i in range(2):
            cage.add_quad(
                [ramp[(i, j)], ramp[(i + 1, j)], ramp[(i + 1, j + 1)], ramp[(i, j + 1)]],
                ground_model="metal",
            )

    cage.set_refnodes_existing(
        ref=body[(1, 1, 0)],
        back=body[(1, 0, 0)],
        left=body[(0, 1, 0)],
        up=body[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            ramp[(0, 0)],
            ramp[(2, 0)],
            body[(0, 2, 0)],
            body[(2, 2, 0)],
            body[(0, 2, 2)],
            body[(2, 2, 2)],
            land[(0, 0)],
            land[(2, 0)],
        ]
    )
    cage.auto_base_nodes()
    return cage


def main() -> None:
    bk.reset_scene()
    materials = bk.materials_from_palette(spec, TEXTURE_DIR)
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
        camera_location=(14.0, -17.0, 4.8),
        look_at=(0.0, -1.5, 3.4),
    )
    print(f"GIANT_TOASTER generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
