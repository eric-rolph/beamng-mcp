"""Deterministic Blender generator for the 200MPH Spider Web Catcher.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/spider_web_catcher/blender/create_spider_web_catcher.py
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

CZ = spec.WEB_CENTER_Z
RADII = spec.WEB_RING_RADII
SPOKES = spec.WEB_SPOKES


def spoke_angle(index: int) -> float:
    return math.radians(index * 360.0 / SPOKES)


def ring_position(spoke: int, radius: float) -> tuple[float, float, float]:
    a = spoke_angle(spoke)
    return (math.cos(a) * radius, 0.0, CZ + math.sin(a) * radius)


# Anchor points per spoke: where the outermost strand ties off to the
# rigid world (towers / crossbeam / ground stakes). Spoke 0 = +X.
def anchor_position(spoke: int) -> tuple[float, float, float]:
    a = spoke_angle(spoke)
    dx, dz = math.cos(a), math.sin(a)
    targets = {
        0: (spec.TOWER_X, 0.0, CZ),
        1: (spec.TOWER_X, 0.0, spec.CROSSBEAM_Z - 0.7),
        2: (0.0, 0.0, spec.CROSSBEAM_Z),
        3: (-spec.TOWER_X, 0.0, spec.CROSSBEAM_Z - 0.7),
        4: (-spec.TOWER_X, 0.0, CZ),
        5: (-8.5, 0.0, 0.0),
        6: (0.0, 0.0, 0.0),
        7: (8.5, 0.0, 0.0),
    }
    if spoke in targets:
        return targets[spoke]
    return (dx * (RADII[-1] + 3.0), 0.0, CZ + dz * (RADII[-1] + 3.0))


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def strand_ribbon(name, start, end, material, width=0.18):
    """A flat silk ribbon between two web points (skinned to web nodes)."""

    import bpy
    from mathutils import Vector

    a = Vector(start)
    b = Vector(end)
    direction = b - a
    mid = (a + b) / 2
    ribbon = bk.add_box(
        name,
        tuple(mid),
        (width, 0.05, direction.length),
        material,
        bevel=0.0,
    )
    ribbon.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    bpy.context.view_layer.objects.active = ribbon
    ribbon.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    ribbon.select_set(False)
    return ribbon


def build_web_ribbons(materials) -> list:
    silk = materials[f"{MOD_ID}_web_silk"]
    ribbons = []
    center = (0.0, 0.0, CZ)
    for spoke in range(SPOKES):
        previous = center
        for ring_index, radius in enumerate(RADII):
            position = ring_position(spoke, radius)
            ribbons.append(
                strand_ribbon(f"{MOD_ID}_spoke_{spoke}_{ring_index}", previous, position, silk)
            )
            previous = position
        ribbons.append(
            strand_ribbon(
                f"{MOD_ID}_anchor_{spoke}",
                previous,
                anchor_position(spoke),
                silk,
                width=0.24,
            )
        )
    for ring_index, radius in enumerate(RADII):
        for spoke in range(SPOKES):
            ribbons.append(
                strand_ribbon(
                    f"{MOD_ID}_ring_{ring_index}_{spoke}",
                    ring_position(spoke, radius),
                    ring_position((spoke + 1) % SPOKES, radius),
                    silk,
                    width=0.14 if ring_index < len(RADII) - 1 else 0.2,
                )
            )
    return ribbons


def build_visual(materials) -> list:
    steel = materials[f"{MOD_ID}_tower_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]
    board = materials[f"{MOD_ID}_board_white"]
    paint = materials[f"{MOD_ID}_paint_white"]
    concrete = materials[f"{MOD_ID}_concrete"]

    objects = []
    # Towers: chunky column + cross braces + hazard base collar.
    for side, sx in (("l", -spec.TOWER_X), ("r", spec.TOWER_X)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_tower_{side}",
                (sx, 0.0, spec.TOWER_TOP_Z / 2),
                (1.6, 1.6, spec.TOWER_TOP_Z),
                steel,
                bevel=0.08,
                metric_uv=(2.0, 2.0),
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_tower_base_{side}",
                (sx, 0.0, 0.5),
                (3.0, 3.0, 1.0),
                hazard,
                bevel=0.06,
            )
        )
        for brace_index, bz in enumerate((5.0, 10.0, 14.5)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_tower_brace_{side}_{brace_index}",
                    (sx, 0.0, bz),
                    (2.2, 2.2, 0.4),
                    steel,
                    bevel=0.04,
                )
            )
    # Crossbeam spanning the towers.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_crossbeam",
            (0.0, 0.0, spec.CROSSBEAM_Z),
            (2 * spec.TOWER_X + 1.6, 1.2, 1.2),
            steel,
            bevel=0.08,
            metric_uv=(2.0, 2.0),
        )
    )
    # Ground stakes for the lower anchors.
    for stake_index, sx in enumerate((-8.5, 0.0, 8.5)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_stake_{stake_index}",
                (sx, 0.0, 0.35),
                0.35,
                0.7,
                steel,
                vertices=10,
            )
        )
    # Landing pad slab behind the web (where caught flies end up).
    objects.append(
        bk.add_box(
            f"{MOD_ID}_pad",
            (0.0, 8.0, 0.1),
            (18.0, 16.0, 0.2),
            concrete,
            bevel=0.0,
            metric_uv=(2.4, 2.4),
        )
    )
    # 200 MPH run-up: speed boards on posts plus painted centre dashes.
    for board_index, by in enumerate((-85.0, -60.0, -35.0)):
        post_x = 6.5
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_board_post_{board_index}",
                (post_x, by, 1.4),
                0.12,
                2.8,
                steel,
                vertices=8,
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_board_{board_index}",
                (post_x, by, 3.4),
                (2.6, 0.18, 1.4),
                board,
                bevel=0.04,
            )
        )
        # Stripe count = urgency: 1 stripe at 100 MPH, 3 at 200.
        for stripe in range(board_index + 1):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_board_stripe_{board_index}_{stripe}",
                    (post_x - 0.8 + stripe * 0.8, by - 0.11, 3.4),
                    (0.5, 0.06, 1.0),
                    hazard,
                    bevel=0.0,
                )
            )
    for dash_index in range(12):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_dash_{dash_index}",
                (0.0, -88.0 + dash_index * 7.0, 0.03),
                (0.5, 2.4, 0.06),
                paint,
                bevel=0.0,
            )
        )
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    spider_black = materials[f"{MOD_ID}_spider_black"]
    spider_red = materials[f"{MOD_ID}_spider_red"]
    eye_glow = materials[f"{MOD_ID}_eye_glow"]
    silk = materials[f"{MOD_ID}_web_silk"]

    pivot = spec.SPIDER_PIVOT
    objects = []
    # Silk drop line from the crossbeam to the body.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_silk_line",
            (pivot[0], pivot[1], pivot[2] - 0.9),
            (0.08, 0.08, 1.8),
            silk,
            bevel=0.0,
        )
    )
    body_z = pivot[2] - 2.6
    # Abdomen with a red hourglass, cephalothorax, glowing eyes.
    objects.append(
        bk.add_sphere(
            f"{MOD_ID}_abdomen",
            (pivot[0], pivot[1] + 0.7, body_z),
            1.35,
            spider_black,
            segments=20,
            rings=14,
            scale=(1.0, 1.25, 0.95),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hourglass",
            (pivot[0], pivot[1] + 1.95, body_z - 0.25),
            (0.55, 0.12, 0.8),
            spider_red,
            bevel=0.05,
        )
    )
    objects.append(
        bk.add_sphere(
            f"{MOD_ID}_head",
            (pivot[0], pivot[1] - 0.9, body_z - 0.15),
            0.75,
            spider_black,
            segments=16,
            rings=12,
        )
    )
    for eye_side in (-1, 1):
        objects.append(
            bk.add_sphere(
                f"{MOD_ID}_eye_{'l' if eye_side < 0 else 'r'}",
                (pivot[0] + eye_side * 0.3, pivot[1] - 1.55, body_z - 0.05),
                0.16,
                eye_glow,
                segments=10,
                rings=8,
            )
        )
    # Eight legs: bent boxes fanning out and down.
    for leg_index in range(4):
        ly = body_z + 0.15
        offset_y = -0.55 + leg_index * 0.45
        for leg_side in (-1, 1):
            reach = 2.4 + (1.5 - abs(leg_index - 1.5)) * 0.4
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_leg_{leg_index}_{'l' if leg_side < 0 else 'r'}_up",
                    (
                        pivot[0] + leg_side * reach * 0.45,
                        pivot[1] + offset_y,
                        ly + 0.5,
                    ),
                    (reach * 0.9, 0.16, 0.16),
                    spider_black,
                    bevel=0.03,
                    rotation=(0.0, math.radians(-35.0 * leg_side), 0.0),
                )
            )
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_leg_{leg_index}_{'l' if leg_side < 0 else 'r'}_dn",
                    (
                        pivot[0] + leg_side * reach * 0.95,
                        pivot[1] + offset_y,
                        ly - 0.35,
                    ),
                    (reach * 0.7, 0.14, 0.14),
                    spider_black,
                    bevel=0.03,
                    rotation=(0.0, math.radians(55.0 * leg_side), 0.0),
                )
            )
    return {"spider": {"objects": objects, "pivot": pivot}}


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    # Elastic silk: soft springs, heavy damping (the catch should absorb,
    # not trampoline). Outer ring strands snap on brutal hits.
    cage.define_beam_spec(
        "web_spoke",
        beamSpring=9000.0,
        beamDamp=1400.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "web_ring",
        beamSpring=5000.0,
        beamDamp=700.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "web_anchor",
        beamSpring=13000.0,
        beamDamp=1900.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )

    # Ground pad under the catch pocket (fixed collision floor for the
    # settled fly) + refnode home. Starts at y 1.2 so its front nodes do
    # NOT coincide with the ground-stake anchors at y 0 (zero-length beam
    # lesson).
    plate = cage.add_box_lattice(
        "pad",
        (-9.0, 1.2, 0.0),
        (9.0, 16.0, 0.2),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("top",),
        face_ground_models={"top": "asphalt"},
    )
    # Tower collision boxes (the towers are load-bearing scenery: a car
    # must not drive through them).
    towers: dict[tuple[int, int, int, int], str] = {}
    for tower_index, tx in enumerate((-spec.TOWER_X, spec.TOWER_X)):
        for ix, cx in enumerate((tx - 0.9, tx + 0.9)):
            for iy, cy in enumerate((-0.9, 0.9)):
                for iz, cz in enumerate((0.0, spec.TOWER_TOP_Z)):
                    towers[(tower_index, ix, iy, iz)] = cage.add_node(
                        f"tower_{tower_index}_{ix}_{iy}_{iz}",
                        (cx, cy, cz),
                        fixed=True,
                        collision=True,
                        weight=150.0,
                    )
    for tower_index in (0, 1):
        for ix in (0, 1):
            for iy in (0, 1):
                cage.add_beam(towers[(tower_index, ix, iy, 0)], towers[(tower_index, ix, iy, 1)])
        for iz in (0, 1):
            cage.add_beam(towers[(tower_index, 0, 0, iz)], towers[(tower_index, 1, 0, iz)])
            cage.add_beam(towers[(tower_index, 0, 1, iz)], towers[(tower_index, 1, 1, iz)])
            cage.add_beam(towers[(tower_index, 0, 0, iz)], towers[(tower_index, 0, 1, iz)])
            cage.add_beam(towers[(tower_index, 1, 0, iz)], towers[(tower_index, 1, 1, iz)])
        # All four side faces collide (cars can hit a tower from any side).
        for face in range(4):
            if face == 0:
                quad = [
                    towers[(tower_index, 0, 0, 0)],
                    towers[(tower_index, 1, 0, 0)],
                    towers[(tower_index, 1, 0, 1)],
                    towers[(tower_index, 0, 0, 1)],
                ]
            elif face == 1:
                quad = [
                    towers[(tower_index, 1, 1, 0)],
                    towers[(tower_index, 0, 1, 0)],
                    towers[(tower_index, 0, 1, 1)],
                    towers[(tower_index, 1, 1, 1)],
                ]
            elif face == 2:
                quad = [
                    towers[(tower_index, 0, 1, 0)],
                    towers[(tower_index, 0, 0, 0)],
                    towers[(tower_index, 0, 0, 1)],
                    towers[(tower_index, 0, 1, 1)],
                ]
            else:
                quad = [
                    towers[(tower_index, 1, 0, 0)],
                    towers[(tower_index, 1, 1, 0)],
                    towers[(tower_index, 1, 1, 1)],
                    towers[(tower_index, 1, 0, 1)],
                ]
            cage.add_quad(quad, ground_model="metal")

    # Web nodes: free silk in their own group (their ribbons are a separate
    # flexbody; binding them into the main visual would smear it).
    center = cage.add_node(
        "web_c",
        (0.0, 0.0, CZ),
        fixed=False,
        collision=True,
        weight=30.0,
        group="web",
    )
    web: dict[tuple[int, int], str] = {}
    for spoke in range(SPOKES):
        for ring_index, radius in enumerate(RADII):
            web[(spoke, ring_index)] = cage.add_node(
                f"web_{spoke}_{ring_index}",
                ring_position(spoke, radius),
                fixed=False,
                collision=True,
                weight=32.0,
                group="web",
            )
    anchors: dict[int, str] = {}
    for spoke in range(SPOKES):
        anchors[spoke] = cage.add_node(
            f"web_anchor_{spoke}",
            anchor_position(spoke),
            fixed=True,
            collision=False,
            weight=120.0,
            group="web",
        )

    last_ring = len(RADII) - 1
    for spoke in range(SPOKES):
        cage.add_beam(center, web[(spoke, 0)], "web_spoke")
        for ring_index in range(last_ring):
            cage.add_beam(web[(spoke, ring_index)], web[(spoke, ring_index + 1)], "web_spoke")
        cage.add_beam(web[(spoke, last_ring)], anchors[spoke], "web_anchor")
    for ring_index in range(len(RADII)):
        for spoke in range(SPOKES):
            extra = None
            if ring_index >= last_ring - 1:
                # The two outer rings carry snap groups: hard hits tear
                # visible strands (physics reset re-spins them).
                extra = {
                    "breakGroup": f"{MOD_ID}_snap_{ring_index}_{spoke}",
                    "beamStrength": 95000.0,
                }
            cage.add_beam(
                web[(spoke, ring_index)],
                web[((spoke + 1) % SPOKES, ring_index)],
                "web_ring",
                extra=extra,
            )

    # Catch membrane: collision triangles over the whole face, both
    # windings (the web is hit from the front and bulges backward).
    def face_quad(quad):
        cage.add_quad_both(quad, ground_model="metal")

    for spoke in range(SPOKES):
        nxt = (spoke + 1) % SPOKES
        cage.add_triangle(center, web[(spoke, 0)], web[(nxt, 0)], ground_model="metal")
        cage.add_triangle(web[(nxt, 0)], web[(spoke, 0)], center, ground_model="metal")
        for ring_index in range(last_ring):
            face_quad(
                [
                    web[(spoke, ring_index)],
                    web[(nxt, ring_index)],
                    web[(nxt, ring_index + 1)],
                    web[(spoke, ring_index + 1)],
                ]
            )

    # Stitch everything into ONE cage graph: ground-stake anchors to the
    # pad's front row, towers to the pad edges and their web anchors.
    cage.add_beam(anchors[5], plate[(0, 0, 1)])
    cage.add_beam(anchors[6], plate[(1, 0, 1)])
    cage.add_beam(anchors[7], plate[(2, 0, 1)])
    cage.add_beam(towers[(0, 1, 1, 0)], plate[(0, 0, 0)])
    cage.add_beam(towers[(1, 0, 1, 0)], plate[(2, 0, 0)])
    cage.add_beam(towers[(0, 1, 0, 1)], anchors[4])
    cage.add_beam(towers[(1, 0, 0, 1)], anchors[0])
    cage.add_beam(towers[(0, 0, 0, 1)], anchors[3])
    cage.add_beam(towers[(1, 1, 0, 1)], anchors[1])
    cage.add_beam(towers[(0, 0, 0, 1)], anchors[2])

    cage.set_refnodes_existing(
        ref=plate[(1, 1, 0)],
        back=plate[(1, 0, 0)],
        left=plate[(0, 1, 0)],
        up=plate[(1, 1, 1)],
    )
    cage.set_spawn_envelope(
        [
            towers[(0, 0, 0, 0)],
            towers[(1, 1, 0, 0)],
            towers[(0, 0, 0, 1)],
            towers[(1, 1, 0, 1)],
            plate[(0, 2, 1)],
            plate[(2, 2, 1)],
            web[(2, last_ring)],
            web[(6, last_ring)],
        ]
    )
    cage.auto_base_nodes()
    return cage


def main() -> None:
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)
    web_ribbons = build_web_ribbons(materials)
    part_builds = build_parts(materials)

    parts = []
    for name, build in sorted(part_builds.items()):
        dae_path = VEHICLE_DIR / f"{MOD_ID}_{name}.dae"
        info = bk.export_part_shape(MOD_ID, name, dae_path, build["objects"], build["pivot"])
        info["path"] = f"vehicles/{MOD_ID}/{MOD_ID}_{name}.dae"
        parts.append(info)

    mesh_groups = {
        f"{MOD_ID}_visual": visual_objects,
        f"{MOD_ID}_web_mesh": web_ribbons,
    }
    visual = bk.export_multi_flexbody(MOD_ID, VEHICLE_DIR / f"{MOD_ID}.dae", mesh_groups)

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
        flexbodies_extra=[{"mesh": f"{MOD_ID}_web_mesh", "groups": ["web"]}],
    )
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(20.0, -30.0, 12.0),
        look_at=(0.0, 0.0, 8.0),
    )
    print(f"SPIDER_WEB_CATCHER generator complete: {len(parts)} parts")


if __name__ == "__main__":
    main()
