"""Deterministic Blender generator for the Wrecking Ball Pendulum Gauntlet.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/pendulum_gauntlet/blender/create_pendulum_gauntlet.py
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

DECK_Z = spec.DECK_TOP_Z
HW = spec.DECK_HALF_WIDTH
SUB_Z = spec.SUBFRAME_Z
YS = spec.STATION_YS
GXS = spec.GANTRY_POST_X
L = spec.CABLE_LENGTH
BALL_R = spec.BALL_RADIUS


def ball_center(gy: float, angle_deg: float) -> tuple[float, float, float]:
    angle = math.radians(angle_deg)
    return (
        math.sin(angle) * L,
        gy,
        spec.ANCHOR_Z - math.cos(angle) * L,
    )


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def build_visual(materials) -> list:
    import bpy

    mat_red = materials[f"{MOD_ID}_mat_red"]
    mat_blue = materials[f"{MOD_ID}_mat_blue"]
    bumper_yellow = materials[f"{MOD_ID}_bumper_yellow"]
    steel = materials[f"{MOD_ID}_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]
    ball_dark = materials[f"{MOD_ID}_ball_dark"]
    asphalt = materials[f"{MOD_ID}_ramp_asphalt"]

    objects = []
    # Inflated mat deck: one pillow per bay, alternating colours.
    for bay in range(len(YS) - 1):
        y_center = (YS[bay] + YS[bay + 1]) / 2
        objects.append(
            bk.add_box(
                f"{MOD_ID}_mat_{bay}",
                (0.0, y_center, DECK_Z - 0.32),
                (2 * HW + 0.5, (YS[1] - YS[0]) + 0.15, 0.62),
                mat_red if bay % 2 == 0 else mat_blue,
                bevel=0.24,
                metric_uv=(2.1, 2.1),
            )
        )
        # Side bumper bolsters.
        for side, sx in (("l", -spec.BUMPER_X), ("r", spec.BUMPER_X)):
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_bumper_{bay}_{side}",
                    (sx, y_center, spec.BUMPER_Z - 0.15),
                    0.38,
                    (YS[1] - YS[0]) + 0.05,
                    bumper_yellow if bay % 2 == 0 else mat_red,
                    vertices=14,
                    axis="Y",
                )
            )
    # Undercarriage trusses.
    for j, y in enumerate(YS):
        for side, sx in (("l", -HW), ("r", HW)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_truss_{j}_{side}",
                    (sx, y, SUB_Z / 2),
                    (0.4, 0.4, SUB_Z),
                    steel,
                    bevel=0.03,
                )
            )
    # Ramps at both ends.
    for end, sign in (("south", -1.0), ("north", 1.0)):
        run = spec.RAMP_GROUND_Y - 20.0
        ramp_len = math.hypot(run, DECK_Z)
        angle = math.atan2(DECK_Z, run)
        mid_y = sign * (20.0 + run / 2)
        rotation_x = -sign * angle
        normal_y = math.sin(angle) * sign
        objects.append(
            bk.add_box(
                f"{MOD_ID}_ramp_{end}",
                (0.0, mid_y + normal_y * 0.12, DECK_Z / 2 - math.cos(angle) * 0.12),
                (2 * HW + 0.6, ramp_len, 0.24),
                asphalt,
                bevel=0.0,
                rotation=(rotation_x, 0.0, 0.0),
                metric_uv=(2.4, 2.4),
            )
        )
    # Gantries with hazard-striped crossbeams, cables, and wrecking balls.
    for index, gy in enumerate(spec.GANTRY_YS):
        for side, sx in (("l", -GXS), ("r", GXS)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_post_{index}_{side}",
                    (sx, gy, spec.GANTRY_TOP_Z / 2),
                    (0.7, 0.7, spec.GANTRY_TOP_Z),
                    steel,
                    bevel=0.04,
                    metric_uv=(1.7, 1.7),
                )
            )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_crossbeam_{index}",
                (0.0, gy, spec.GANTRY_TOP_Z + 0.35),
                (2 * GXS + 0.9, 0.65, 0.7),
                hazard,
                bevel=0.05,
                metric_uv=(1.3, 1.3),
            )
        )
    # The cables and balls are deliberately ABSENT from this flexbody: a
    # visual spanning fast-moving free nodes and static gantry nodes smears
    # into morphing blades under flexbody skinning (observed in play-testing
    # 2026-07-22). Each pendulum is instead a rigid runtime part posed every
    # frame from the physics ball's live node position.
    del bpy, ball_dark
    return objects


def build_parts(materials) -> dict[str, dict[str, object]]:
    steel = materials[f"{MOD_ID}_steel"]
    ball_dark = materials[f"{MOD_ID}_ball_dark"]

    # Each pendulum part is authored hanging straight DOWN from its anchor
    # (angle zero); the runtime rotates it about the authored Y axis to match
    # the live physics ball position.
    parts: dict[str, dict[str, object]] = {}
    # Real demolition rigs hang a FORGED PEAR ball from chain, not smooth
    # cable (reference pass 2026-07-22): alternating torus links, a clevis
    # shackle, and a pear body (sphere + tapered crown with a cut-off top).
    for index, gy in enumerate(spec.GANTRY_YS):
        pivot = (0.0, gy, spec.ANCHOR_Z)
        objects = []
        chain_top = spec.ANCHOR_Z
        chain_bottom = spec.ANCHOR_Z - L + BALL_R + 0.55
        links = 9
        pitch = (chain_top - chain_bottom) / links
        for link in range(links):
            lz = chain_top - (link + 0.5) * pitch
            objects.append(
                bk.add_torus(
                    f"{MOD_ID}_chain_{index}_{link}",
                    (0.0, gy, lz),
                    pitch * 0.42,
                    0.075,
                    steel,
                    rotation=(math.pi / 2, 0.0, 0.0)
                    if link % 2 == 0
                    else (math.pi / 2, math.pi / 2, 0.0),
                    major_segments=12,
                    minor_segments=8,
                )
            )
        # Clevis shackle plates gripping the crown eye.
        for side, sy in (("a", -0.22), ("b", 0.22)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_shackle_{index}_{side}",
                    (0.0, gy + sy, chain_bottom - 0.25),
                    (0.5, 0.09, 0.6),
                    steel,
                    bevel=0.03,
                )
            )
        # Pear crown: truncated cone from the shackle down onto the sphere.
        objects.append(
            bk.add_cone(
                f"{MOD_ID}_pear_crown_{index}",
                (0.0, gy, spec.ANCHOR_Z - L + BALL_R * 0.55),
                BALL_R * 0.82,
                0.3,
                BALL_R * 1.15,
                ball_dark,
                vertices=18,
            )
        )
        ball = bk.add_sphere(
            f"{MOD_ID}_pend_ball_{index}",
            (0.0, gy, spec.ANCHOR_Z - L),
            BALL_R + 0.08,
            ball_dark,
            segments=22,
            rings=16,
        )
        bk.scale_uvs(ball, 2.0, 1.0)
        objects.append(ball)
        parts[f"pendulum_{index}"] = {
            "objects": objects,
            "pivot": pivot,
        }
    return parts


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    cage.define_beam_spec(
        "deck_support",
        beamSpring=150000.0,
        beamDamp=800.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "deck_membrane",
        beamSpring=220000.0,
        beamDamp=550.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "bumper",
        beamSpring=30000.0,
        beamDamp=220.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )
    cage.define_beam_spec(
        "cable",
        beamSpring=2000000.0,
        # High damping is free on a constant-length rod (no chain links to
        # jiggle) and keeps the assembly numerically stable.
        beamDamp=6000.0,
        beamDeform="FLT_MAX",
        beamStrength="FLT_MAX",
    )

    ground: dict[tuple[int, int], str] = {}
    sub: dict[tuple[int, int], str] = {}
    deck: dict[tuple[int, int], str] = {}
    bumper: dict[tuple[int, int], str] = {}
    end_stations = {0, len(YS) - 1}
    deck_xs = (-HW, 0.0, HW)
    for j, y in enumerate(YS):
        for i, x in enumerate((-HW, HW)):
            ground[(i, j)] = cage.add_node(f"ground_{i}_{j}", (x, y, 0.0), fixed=True, weight=220.0)
            sub[(i, j)] = cage.add_node(f"sub_{i}_{j}", (x, y, SUB_Z), fixed=True, weight=160.0)
            cage.add_beam(ground[(i, j)], sub[(i, j)])
        cage.add_beam(sub[(0, j)], sub[(1, j)])
        cage.add_beam(ground[(0, j)], ground[(1, j)])
        fixed_station = j in end_stations
        for i, x in enumerate(deck_xs):
            deck[(i, j)] = cage.add_node(
                f"deck_{i}_{j}",
                (x, y, DECK_Z),
                fixed=fixed_station,
                collision=True,
                weight=45.0,
                friction=1.0,
            )
        for i, x in enumerate((-spec.BUMPER_X, spec.BUMPER_X)):
            bumper[(i, j)] = cage.add_node(
                f"bumper_{i}_{j}",
                (x, y, spec.BUMPER_Z),
                fixed=fixed_station,
                collision=True,
                weight=25.0,
                friction=0.8,
            )
    for j in range(len(YS)):
        # Deck support springs down to the fixed sub-frame.
        cage.add_beam(deck[(0, j)], sub[(0, j)], "deck_support")
        cage.add_beam(deck[(2, j)], sub[(1, j)], "deck_support")
        cage.add_beam(deck[(1, j)], sub[(0, j)], "deck_support")
        cage.add_beam(deck[(1, j)], sub[(1, j)], "deck_support")
        if j > 0:
            cage.add_beam(deck[(0, j)], sub[(0, j - 1)], "deck_support")
            cage.add_beam(deck[(2, j)], sub[(1, j - 1)], "deck_support")
        if j < len(YS) - 1:
            cage.add_beam(deck[(0, j)], sub[(0, j + 1)], "deck_support")
            cage.add_beam(deck[(2, j)], sub[(1, j + 1)], "deck_support")
        # Deck membrane.
        cage.add_beam(deck[(0, j)], deck[(1, j)], "deck_membrane")
        cage.add_beam(deck[(1, j)], deck[(2, j)], "deck_membrane")
        if j > 0:
            for i in range(3):
                cage.add_beam(deck[(i, j - 1)], deck[(i, j)], "deck_membrane")
            cage.add_beam(deck[(0, j - 1)], deck[(1, j)], "deck_membrane")
            cage.add_beam(deck[(1, j - 1)], deck[(0, j)], "deck_membrane")
            cage.add_beam(deck[(1, j - 1)], deck[(2, j)], "deck_membrane")
            cage.add_beam(deck[(2, j - 1)], deck[(1, j)], "deck_membrane")
        # Bumpers spring to the sub-frame and tie to the deck edge.
        for i, deck_i in ((0, 0), (1, 2)):
            cage.add_beam(bumper[(i, j)], sub[(i, j)], "bumper")
            cage.add_beam(bumper[(i, j)], deck[(deck_i, j)], "bumper")
            if j > 0:
                cage.add_beam(bumper[(i, j - 1)], bumper[(i, j)], "bumper")
        # Collision quads.
        if j > 0:
            cage.add_quad(
                [deck[(0, j - 1)], deck[(1, j - 1)], deck[(1, j)], deck[(0, j)]],
                ground_model="asphalt",
            )
            cage.add_quad(
                [deck[(1, j - 1)], deck[(2, j - 1)], deck[(2, j)], deck[(1, j)]],
                ground_model="asphalt",
            )
            # Bumper faces (inward).
            left_face = [
                deck[(0, j - 1)],
                deck[(0, j)],
                bumper[(0, j)],
                bumper[(0, j - 1)],
            ]
            right_face = [
                deck[(2, j - 1)],
                bumper[(1, j - 1)],
                bumper[(1, j)],
                deck[(2, j)],
            ]
            cage.add_quad(left_face, ground_model="metal")
            cage.add_quad(right_face, ground_model="metal")

    # Ramps: fixed slabs from the ground to the fixed end stations.
    for end, j, sign in (("south", 0, -1.0), ("north", len(YS) - 1, 1.0)):
        ramp_l = cage.add_node(
            f"ramp_{end}_l",
            (-HW, sign * spec.RAMP_GROUND_Y, 0.0),
            fixed=True,
            collision=True,
        )
        ramp_r = cage.add_node(
            f"ramp_{end}_r",
            (HW, sign * spec.RAMP_GROUND_Y, 0.0),
            fixed=True,
            collision=True,
        )
        cage.add_beam(ramp_l, ramp_r)
        cage.add_beam(ramp_l, ground[(0, j)])
        cage.add_beam(ramp_r, ground[(1, j)])
        cage.add_beam(ramp_l, deck[(0, j)])
        cage.add_beam(ramp_r, deck[(2, j)])
        quad = [ramp_l, ramp_r, deck[(2, j)], deck[(0, j)]]
        if sign > 0:
            quad = [ramp_r, ramp_l, deck[(0, j)], deck[(2, j)]]
        cage.add_quad(quad, ground_model="asphalt")

    # Gantries and the physics pendulums.
    for index, gy in enumerate(spec.GANTRY_YS):
        station = YS.index(gy - 1.0) if (gy - 1.0) in YS else None
        del station
        posts = {}
        for side, sx in (("l", -GXS), ("r", GXS)):
            base = cage.add_node(
                f"post_{index}_{side}_base", (sx, gy, 0.0), fixed=True, collision=True
            )
            top = cage.add_node(
                f"post_{index}_{side}_top",
                (sx, gy, spec.GANTRY_TOP_Z),
                fixed=True,
                collision=True,
            )
            cage.add_beam(base, top)
            posts[side] = (base, top)
        anchor = cage.add_node(
            f"anchor_{index}", (0.0, gy, spec.ANCHOR_Z), fixed=True, weight=200.0
        )
        cage.add_beam(posts["l"][1], anchor)
        cage.add_beam(posts["r"][1], anchor)
        cage.add_beam(posts["l"][1], posts["r"][1])
        # Tie the gantry into the bridge structure.
        nearest = min(range(len(YS)), key=lambda j: abs(YS[j] - gy))
        cage.add_beam(posts["l"][0], ground[(0, nearest)])
        cage.add_beam(posts["r"][0], ground[(1, nearest)])

        # Pendulum: cable chain plus a heavy octahedron ball, authored
        # displaced so gravity swings it immediately.
        angle_deg = spec.SWING_ANGLES_DEG[index]
        bx, by, bz = ball_center(gy, angle_deg)
        # Rigid rod only: the light 15 kg chain-link nodes rang unstably
        # against their 2 MN/m springs once damping was lowered for swing
        # life (pendulums collapsed in play 2026-07-23). A rod's length is
        # constant during a swing, so high damping here costs no amplitude —
        # stable AND long-swinging. The visible chain is a rigid part.
        center = cage.add_node(
            f"ball_{index}_c", (bx, by, bz), fixed=False, collision=False, weight=300.0
        )
        cage.add_beam(anchor, center, "cable")
        outer = {}
        for key, offset in {
            "xp": (BALL_R, 0.0, 0.0),
            "xm": (-BALL_R, 0.0, 0.0),
            "yp": (0.0, BALL_R, 0.0),
            "ym": (0.0, -BALL_R, 0.0),
            "zp": (0.0, 0.0, BALL_R),
            "zm": (0.0, 0.0, -BALL_R),
        }.items():
            outer[key] = cage.add_node(
                f"ball_{index}_{key}",
                (bx + offset[0], by + offset[1], bz + offset[2]),
                fixed=False,
                collision=True,
                weight=250.0,
                friction=0.6,
                group="pendulum",
            )
            cage.add_beam(center, outer[key])
        ring = [
            ("xp", "yp"),
            ("yp", "xm"),
            ("xm", "ym"),
            ("ym", "xp"),
            ("xp", "zp"),
            ("yp", "zp"),
            ("xm", "zp"),
            ("ym", "zp"),
            ("xp", "zm"),
            ("yp", "zm"),
            ("xm", "zm"),
            ("ym", "zm"),
        ]
        for first, second in ring:
            cage.add_beam(outer[first], outer[second])
        for a, b, c in (
            ("xp", "yp", "zp"),
            ("yp", "xm", "zp"),
            ("xm", "ym", "zp"),
            ("ym", "xp", "zp"),
            ("yp", "xp", "zm"),
            ("xm", "yp", "zm"),
            ("ym", "xm", "zm"),
            ("xp", "ym", "zm"),
        ):
            cage.add_triangle(outer[a], outer[b], outer[c], ground_model="metal")

    cage.set_ground_reference(
        (0.0, 0.0, 0.0),
        (0.0, -4.0, 0.0),
        left=ground[(0, 5)],
        up=cage.nodes[cage.node_index[f"{MOD_ID}_anchor_1"]]["id"],
        support_nodes=[ground[(0, 5)], ground[(1, 5)], ground[(0, 4)], ground[(1, 4)]],
    )
    cage.set_spawn_envelope(
        [
            f"{MOD_ID}_ramp_south_l",
            f"{MOD_ID}_ramp_south_r",
            f"{MOD_ID}_ramp_north_l",
            f"{MOD_ID}_ramp_north_r",
            f"{MOD_ID}_post_0_l_top",
            f"{MOD_ID}_post_0_r_top",
            f"{MOD_ID}_post_3_l_top",
            f"{MOD_ID}_post_3_r_top",
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
    # Each rigid pendulum part is posed at runtime from its physics ball's
    # live node position; the node CID equals the node's row index in the
    # generated JBeam, which is the CageBuilder insertion order.
    behavior["pendulums"] = [
        {
            "anchor": [0.0, gy, spec.ANCHOR_Z],
            # Node NAME, resolved to a live cid at runtime: the game does
            # not number nodes in jbeam row order, so authored indices
            # point at the wrong nodes in-game (frozen-arms bug 2026-07-23).
            "node": f"{MOD_ID}_ball_{index}_c",
            "length": L,
        }
        for index, gy in enumerate(spec.GANTRY_YS)
    ]
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
        camera_location=(30.0, -38.0, 16.0),
        look_at=(0.0, 0.0, 5.0),
    )
    print("PENDULUM_GAUNTLET generator complete")


if __name__ == "__main__":
    main()
