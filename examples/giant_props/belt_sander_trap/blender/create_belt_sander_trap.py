"""Deterministic Blender generator for The Belt Sander Conveyor Trap.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/belt_sander_trap/blender/create_belt_sander_trap.py

Structure of this file:

  * ``_loft`` - the one mesh primitive this prop needs that ``blender_kit``
    does not provide: a swept solid built from a list of cross-section
    rings. Both the lane (ramp / frames / walkways / guards / decks) and
    the belt loop are lofts, and the lane's rings come from the SAME
    ``spec.deck_z`` / ``spec.skirt_rise`` functions the physics cage reads,
    so a visual/collision divergence is impossible by construction rather
    than by inspection.
  * ``build_visual`` - everything welded to the machine.
  * ``build_parts``  - the kinematic pieces: 16 splice bars that traverse
    the belt loop, both drums, and the console gauge needle.
  * ``build_cage``   - the physics cage, generated from the same station
    list and the same height functions as the visual.
  * ``main``         - export + handoff + a block of build-time assertions
    that fail the Blender stage (grep the log for Traceback) if any of the
    invariants this prop is built on ever stop holding.
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))

import bmesh  # noqa: E402
import bpy  # noqa: E402

import spec  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

BH = spec.BELT_HALF_WIDTH
DEF_X = spec.DEFLECTOR_X
WALK_X = spec.WALKWAY_X
KICK_BAND = 0.35  # solid hazard kickplate at the foot of every guard panel
# Ring edge indices of the side-frame cross section (see ``side_ring``).
# Cutting these two over a drum station opens the inspection window.
FRAME_EDGE_OUTER_SKIN = 0
FRAME_EDGE_INNER_FACE = 3
# Collada writes the build machine's wall clock into every DAE's <asset>
# block, which makes an otherwise deterministic generator produce a new
# handoff hash on every run. main() rewrites both stamps to this fixed
# epoch and re-hashes. Together with _bake_and_quantise this makes all 29
# kinematic part DAEs byte-identical across runs (measured: 29/30 files
# stable over repeated back-to-back builds, was 0/30). The one that still
# moves is the single JOINED flexbody visual, whose normal table is
# permuted by bpy.ops.object.join()/collada_export inside proplib's
# export_flexbody_visual - same size, same geometry, different byte order.
# Fixing that needs a proplib change, which is out of scope for this mod.
DAE_EPOCH = b"2026-01-01T00:00:00"


# ---------------------------------------------------------------------------
# Local mesh helpers (deliberately kept in this mod: proplib is shared)
# ---------------------------------------------------------------------------
def _loft(name, sections, material, uv_meters=(2.5, 2.5), closed_loop=False, skip=None):
    """Sweep a closed cross-section ring along a list of stations.

    ``sections`` is a list of rings; every ring is the same length and each
    entry is an (x, y, z) point. Consecutive rings are bridged with quads;
    open sweeps get fan caps at both ends. Face windings are then fixed by
    ``bmesh.ops.recalc_face_normals`` (valid here because every ring is a
    simple polygon, so each loft is a closed manifold solid) - Blender does
    not backface-cull and BeamNG does, so winding is never left to hand
    reasoning on this prop.

    ``skip(span_index, edge_index) -> bool`` suppresses individual bridge
    quads; that is how the drum inspection windows are cut out of the side
    frame. A skipped quad leaves a genuine hole (the loft stops being
    closed), which is safe here only because every palette entry on this
    prop is double-sided, so the exposed interior still draws.
    """

    ring = len(sections[0])
    verts: list[tuple[float, float, float]] = []
    for section in sections:
        if len(section) != ring:
            raise ValueError(f"{name}: ragged loft section")
        verts.extend(tuple(float(v) for v in point) for point in section)
    faces: list[list[int]] = []
    spans = len(sections) if closed_loop else len(sections) - 1
    for j in range(spans):
        j2 = (j + 1) % len(sections)
        for i in range(ring):
            if skip is not None and skip(j, i):
                continue
            i2 = (i + 1) % ring
            faces.append(
                [j * ring + i, j * ring + i2, j2 * ring + i2, j2 * ring + i]
            )
    if not closed_loop:
        faces.append(list(reversed(range(ring))))
        base = (len(sections) - 1) * ring
        faces.append([base + i for i in range(ring)])
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    working = bmesh.new()
    working.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(working, faces=working.faces)
    working.to_mesh(mesh)
    working.free()
    bk.add_metric_box_uvs(obj, meters_per_tile=uv_meters)
    bk.assign_material(obj, material)
    return obj


def _stations(coarse: bool) -> list[float]:
    """Longitudinal sample stations for the lane.

    Intervals where the GRADE varies (the ramp toe and crest blends, the
    kicker toe, the outfeed toe) are sampled finely because ``deck_z`` is
    quadratic there; constant-grade intervals only need their end points.
    Every interval is additionally cut at the machine's structural ends so
    the cage always has a station exactly where the visual changes piece.
    The cage uses the coarse list and the visual the fine one, so the two
    surfaces share every slope discontinuity by construction.
    """

    fine, plain = (1.0, 3.0) if coarse else (0.5, 2.5)
    profile = list(spec.LANE_GRADE_PROFILE) + list(spec.OUTFEED_GRADE_PROFILE)
    # Structural cuts. Every one of these is a place where the lane changes
    # PIECE, so a station has to land on it exactly or a span straddles two
    # different things and its midpoint decides for both: the machine ends,
    # the two drum tangents (where the belt's high-grip ground model has to
    # start and stop), the drum inspection window edges, and the tail
    # gantry (so its legs tie into a real station).
    cuts = (
        spec.MACHINE_TAIL_Y,
        spec.MACHINE_HEAD_Y,
        spec.IDLER_Y,
        spec.DRIVE_Y,
        spec.IDLER_Y + spec.DRUM_WINDOW_HALF,
        spec.DRIVE_Y - spec.DRUM_WINDOW_HALF,
        spec.GANTRY_Y,
    )
    pieces: list[tuple[float, float, float]] = []
    for (y0, g0), (y1, g1) in zip(profile, profile[1:]):
        if y1 <= y0 + 1e-9:
            continue
        step = fine if abs(g1 - g0) > 1e-9 else plain
        marks = [y0] + sorted(c for c in cuts if y0 < c < y1) + [y1]
        for a, b in zip(marks, marks[1:]):
            pieces.append((a, b, step))
    out: list[float] = []
    for a, b, step in pieces:
        count = max(1, int(math.ceil((b - a) / step - 1e-9)))
        out.extend(a + (b - a) * i / count for i in range(count))
    out.append(pieces[-1][1])
    return out


def _window_edges() -> list[float]:
    """The four y stations where a drum inspection window starts or ends.

    Derived from ``spec.in_drum_window`` itself (clamped to the machine's
    structural ends) so the jamb plates, the loft cut and the cage's
    skipped skin spans can never disagree about where an opening is.
    """

    edges: list[float] = []
    for axis in (spec.IDLER_Y, spec.DRIVE_Y):
        edges.append(max(spec.MACHINE_TAIL_Y, axis - spec.DRUM_WINDOW_HALF))
        edges.append(min(spec.MACHINE_HEAD_Y, axis + spec.DRUM_WINDOW_HALF))
    return edges


def belt_outer_z(y: float) -> float | None:
    """Height of the belt's outer face at authored y, or None off the loop.

    Straight over the carrying run, circular over each wrap. This is the
    curve the transfer nose plates are cut to.
    """

    rw = spec.BELT_WRAP_R
    if y < spec.IDLER_Y:
        dy = spec.IDLER_Y - y
    elif y > spec.DRIVE_Y:
        dy = y - spec.DRIVE_Y
    else:
        return spec.BELT_Z
    if dy >= rw:
        return None
    return spec.DRUM_AXIS_Z + math.sqrt(rw * rw - dy * dy)


def nose_tip_offset() -> float:
    """Distance from a drum tangent to where a nose plate has thinned out.

    Solved, never typed: the plate's underside is the wrap curve raised by
    LIP_TIP_CLEAR, its top is the BELT_Z deck plane, and it ends where that
    leaves LIP_TIP_THICK of steel.
    """

    rw = spec.BELT_WRAP_R
    tip_outer = spec.BELT_Z - spec.LIP_TIP_THICK - spec.LIP_TIP_CLEAR
    return math.sqrt(max(0.0, rw * rw - (tip_outer - spec.DRUM_AXIS_Z) ** 2))


def _lip_bottom(y: float) -> float:
    outer = belt_outer_z(y)
    floor = spec.BELT_Z - spec.LIP_ROOT_DROP
    if outer is None:
        return floor
    return max(floor, outer + spec.LIP_TIP_CLEAR)


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


# ---------------------------------------------------------------------------
# Visual
# ---------------------------------------------------------------------------
def _build_lane(objects, materials) -> None:
    steel = materials[f"{MOD_ID}_frame_steel"]
    tread = materials[f"{MOD_ID}_tread_plate"]
    hazard = materials[f"{MOD_ID}_hazard"]
    mesh_guard = materials[f"{MOD_ID}_guard_mesh"]

    stations = _stations(coarse=False)

    def side_ring(y, sign):
        deck = spec.deck_z(y)
        bottom = spec.lane_bottom_z(y)
        walk = deck + spec.skirt_rise(y)
        points = [
            (WALK_X, bottom),
            (WALK_X, walk),
            (DEF_X, walk),
            (BH, deck),
            (BH, bottom),
        ]
        return [(sign * x, y, z) for x, z in points]

    def band_ring(y, sign, z0, z1):
        # The guard panel is RAKED (spec.guard_face_x): its outer face
        # leans outboard with height, so a car that ever reached it is
        # deflected over the side instead of stopped by a plumb wall. The
        # cage's guard column reads the same function.
        deck = spec.deck_z(y)
        walk = deck + spec.skirt_rise(y)
        out0 = spec.guard_face_x(z0)
        out1 = spec.guard_face_x(z1)
        points = [
            (out0, walk + z0),
            (out1, walk + z1),
            (out1 - spec.GUARD_PANEL_T, walk + z1),
            (out0 - spec.GUARD_PANEL_T, walk + z0),
        ]
        return [(sign * x, y, z) for x, z in points]

    # Drum inspection windows: the span midpoints whose outer skin and
    # inner face are cut away. The cage skips exactly the same spans, so
    # the opening is real - there is no invisible wall behind it.
    window_span = [
        spec.in_drum_window(0.5 * (stations[j] + stations[j + 1]))
        for j in range(len(stations) - 1)
    ]

    def frame_skip(span, edge):
        return window_span[span] and edge in (
            FRAME_EDGE_OUTER_SKIN,
            FRAME_EDGE_INNER_FACE,
        )

    for tag, sign in (("l", -1.0), ("r", 1.0)):
        # Machine side frame: outer skin, walkway top, 34% deflector down to
        # the belt edge, inner face back to grade. ONE loft, ramp foot to
        # outfeed toe - a single authority for the lane edge (the round-15
        # "two interleaved shoulder strips became a W-canyon" lesson) - with
        # the two drum stations opened up.
        objects.append(
            _loft(
                f"{MOD_ID}_frame_{tag}",
                [side_ring(y, sign) for y in stations],
                steel,
                uv_meters=(2.2, 2.2),
                skip=frame_skip,
            )
        )
        # Window jamb plates: a closing plate just inside each end of every
        # opening, so the cut edge reads as a fabricated frame rather than
        # a torn hole. Placed from the window bounds, never from a literal.
        for index, edge_y in enumerate(_window_edges()):
            inward = 0.07 if index % 2 == 0 else -0.07
            plate_y = edge_y + inward
            walk = spec.deck_z(plate_y) + spec.skirt_rise(plate_y)
            bottom = spec.lane_bottom_z(plate_y)
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_jamb_{tag}{index}",
                    (
                        sign * (WALK_X + BH) / 2.0,
                        plate_y,
                        (walk + bottom) / 2.0,
                    ),
                    (WALK_X - BH, 0.14, walk - bottom),
                    steel,
                    bevel=0.0,
                    metric_uv=(1.4, 1.4),
                )
            )
        # Guard panel kickplate (solid hazard band) and the perforated
        # panel above it. Both outboard of the walkway, never in a lane.
        objects.append(
            _loft(
                f"{MOD_ID}_guardkick_{tag}",
                [band_ring(y, sign, 0.0, KICK_BAND) for y in stations],
                hazard,
                uv_meters=(1.6, 1.6),
            )
        )
        objects.append(
            _loft(
                f"{MOD_ID}_guardmesh_{tag}",
                [band_ring(y, sign, KICK_BAND, spec.GUARD_H) for y in stations],
                mesh_guard,
                uv_meters=(1.1, 1.1),
            )
        )

    def deck_ring(y):
        deck = spec.deck_z(y)
        bottom = spec.lane_bottom_z(y)
        return [
            (-BH, y, deck),
            (BH, y, deck),
            (BH, y, bottom),
            (-BH, y, bottom),
        ]

    entry = [y for y in stations if y <= spec.MACHINE_TAIL_Y]
    entry.append(spec.MACHINE_TAIL_Y)
    exit_run = [spec.MACHINE_HEAD_Y]
    exit_run.extend(y for y in stations if y > spec.MACHINE_HEAD_Y)
    objects.append(
        _loft(
            f"{MOD_ID}_deck_entry",
            [deck_ring(y) for y in sorted(set(entry))],
            tread,
            uv_meters=(2.0, 2.0),
        )
    )
    objects.append(
        _loft(
            f"{MOD_ID}_deck_exit",
            [deck_ring(y) for y in sorted(set(exit_run))],
            tread,
            uv_meters=(2.0, 2.0),
        )
    )

    # Transfer nose plates over each drum. Top on the deck plane, underside
    # cut to the belt's own wrap curve - see nose_tip_offset().
    tip = nose_tip_offset()
    for tag, y0, y1 in (
        ("feed", spec.MACHINE_TAIL_Y, spec.IDLER_Y - tip),
        ("disch", spec.DRIVE_Y + tip, spec.MACHINE_HEAD_Y),
    ):
        count = 12
        rings = []
        for i in range(count + 1):
            y = y0 + (y1 - y0) * i / count
            rings.append(
                [
                    (-BH, y, spec.deck_z(y)),
                    (BH, y, spec.deck_z(y)),
                    (BH, y, _lip_bottom(y)),
                    (-BH, y, _lip_bottom(y)),
                ]
            )
        objects.append(
            _loft(f"{MOD_ID}_lip_{tag}", rings, steel, uv_meters=(1.8, 1.8))
        )

    # Hazard chevron toe strips: one across the ramp foot, one across the
    # kicker lip. These are LOFTS following deck_z, not axis-aligned boxes:
    # a flat 0.9 m box laid on the 18% kicker measured 84 mm proud at one
    # edge and buried at the other, which the probe caught as a 93 mm
    # wheel-track spread (the AGENTS.md relief cap is 20 mm).
    for tag, y0, y1 in (
        ("rampfoot", spec.RAMP_FOOT_Y + 0.3, spec.RAMP_FOOT_Y + 2.1),
        ("kicklip", spec.KICK_LIP_Y - 0.9, spec.KICK_LIP_Y),
    ):
        steps = max(2, int(math.ceil((y1 - y0) / 0.2)))
        rings = []
        for i in range(steps + 1):
            y = y0 + (y1 - y0) * i / steps
            deck = spec.deck_z(y)
            rings.append(
                [
                    (-BH, y, deck + 0.006),
                    (BH, y, deck + 0.006),
                    (BH, y, deck - 0.03),
                    (-BH, y, deck - 0.03),
                ]
            )
        objects.append(
            _loft(f"{MOD_ID}_toe_{tag}", rings, hazard, uv_meters=(1.4, 1.4))
        )


def _build_belt(objects, materials) -> None:
    grit = materials[f"{MOD_ID}_belt_grit"]
    steel = materials[f"{MOD_ID}_frame_steel"]

    # The belt carcass: a closed band swept along the loop. Its outer face
    # IS spec.BELT_Z over the carrying run, which is exactly where the
    # physics cage puts the drivable plane.
    # 36 facets per half wrap: sagitta 0.80*(1-cos(2.5 deg)) = 0.76 mm.
    # (Facet density is the honest lever - object.join() at export flattens
    # every Blender smooth-shading mark, so a "smooth" drum still renders
    # faceted in game.) Raised from 24 (1.7 mm) for two reasons: the wrap is
    # now visible from outside through the drum inspection windows, and the
    # chord sag adds directly to the one relief number on the lane - the
    # measured divergence at the tangent went 10.9 mm -> 10.3 mm with it.
    facets = 36
    wrap = math.pi * spec.BELT_WRAP_R
    top = spec.TOP_RUN
    samples: list[float] = [0.0, top]
    samples += [top + wrap * i / facets for i in range(1, facets)]
    samples += [top + wrap, 2 * top + wrap]
    samples += [2 * top + wrap + wrap * i / facets for i in range(1, facets)]

    rings = []
    for s in samples:
        y, z, theta = _loop_point(s)
        ny, nz = -math.sin(theta), math.cos(theta)
        inner = (y - ny * spec.BELT_THICK, z - nz * spec.BELT_THICK)
        rings.append(
            [
                (-BH, y, z),
                (BH, y, z),
                (BH, inner[0], inner[1]),
                (-BH, inner[0], inner[1]),
            ]
        )
    objects.append(
        _loft(
            f"{MOD_ID}_belt_loop",
            rings,
            grit,
            uv_meters=(2.4, 2.4),
            closed_loop=True,
        )
    )

    # The flat platen the carrying run is pressed against - the reason a
    # belt sander has a straight cut between two round drums. Held off the
    # side frames by cross beams that pass clear over the return run.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_platen",
            (0.0, 0.0, spec.BELT_Z - spec.BELT_THICK - 0.15),
            (2 * BH, 2 * (spec.DRIVE_Y - 1.6), 0.30),
            steel,
            bevel=0.03,
            metric_uv=(2.0, 2.0),
        )
    )
    for i in range(9):
        y = -8.0 + i * 2.0
        objects.append(
            bk.add_box(
                f"{MOD_ID}_crossbeam_{i}",
                (0.0, y, spec.BELT_Z - spec.BELT_THICK - 0.42),
                (2 * WALK_X - 0.4, 0.26, 0.30),
                steel,
                bevel=0.02,
                metric_uv=(2.0, 2.0),
            )
        )
    # Return-run rollers: the belt has to be carried on the way back.
    for i in range(5):
        y = -8.0 + i * 4.0
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_return_roller_{i}",
                (0.0, y, spec.RETURN_RUN_Z - 0.22),
                0.20,
                2 * BH + 0.3,
                steel,
                vertices=16,
                axis="X",
                metric_uv=(1.2, 1.2),
            )
        )
    # Drum bearing housings (pillow blocks), one per shaft end, inboard of
    # the frame skin so nothing pokes through the walkway.
    for tag, dy in (("tail", spec.IDLER_Y), ("head", spec.DRIVE_Y)):
        for side in (-1.0, 1.0):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_pillow_{tag}_{'l' if side < 0 else 'r'}",
                    (side * (BH + 0.55), dy, spec.DRUM_AXIS_Z),
                    (0.7, 0.9, 0.9),
                    steel,
                    bevel=0.05,
                    metric_uv=(1.4, 1.4),
                )
            )
    # Tail take-up screws: how a real belt gets its tension.
    for side in (-1.0, 1.0):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_takeup_{'l' if side < 0 else 'r'}",
                (side * (BH + 0.55), spec.IDLER_Y - 0.95, spec.DRUM_AXIS_Z),
                0.09,
                1.5,
                steel,
                vertices=10,
                axis="Y",
                metric_uv=(0.4, 0.4),
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_takeup_yoke_{'l' if side < 0 else 'r'}",
                (side * (BH + 0.55), spec.IDLER_Y - 1.7, spec.DRUM_AXIS_Z),
                (0.75, 0.22, 1.0),
                steel,
                bevel=0.03,
                metric_uv=(1.2, 1.2),
            )
        )


def _build_hood(objects, materials) -> None:
    paint = materials[f"{MOD_ID}_machine_paint"]
    steel = materials[f"{MOD_ID}_frame_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]

    hood_mid_y = (spec.HOOD_Y0 + spec.HOOD_Y1) / 2.0
    hood_len = spec.HOOD_Y1 - spec.HOOD_Y0
    hood_h = spec.HOOD_TOP_Z - spec.HOOD_UNDER_Z
    objects.append(
        bk.add_box(
            f"{MOD_ID}_hood_shell",
            (0.0, hood_mid_y, spec.HOOD_UNDER_Z + hood_h / 2.0),
            (2 * spec.HOOD_HALF_X, hood_len, hood_h),
            paint,
            bevel=0.08,
            metric_uv=(2.2, 2.2),
        )
    )
    # Hood skirt: the flexible curtain that keeps dust in. Stops 3.15 m
    # over the belt, so a 1.5 m car still has 1.65 m of air.
    for tag, y in (("in", spec.HOOD_Y0), ("out", spec.HOOD_Y1)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_hood_curtain_{tag}",
                (0.0, y, spec.HOOD_UNDER_Z - 0.225),
                (2 * spec.HOOD_HALF_X, 0.14, 0.45),
                hazard,
                bevel=0.0,
                metric_uv=(1.2, 1.2),
            )
        )
    # Four legs, planted OUTBOARD of the guard line so nothing stands on
    # the walkway or in the deflection path, plus their headers.
    for sx in (-1.0, 1.0):
        for sy, y in (("a", spec.HOOD_Y0 + 0.4), ("b", spec.HOOD_Y1 - 0.4)):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_hood_leg_{'l' if sx < 0 else 'r'}{sy}",
                    (sx * spec.HOOD_LEG_X, y, spec.HOOD_TOP_Z / 2.0),
                    (0.42, 0.42, spec.HOOD_TOP_Z),
                    steel,
                    bevel=0.03,
                    metric_uv=(1.6, 1.6),
                )
            )
    for sy, y in (("a", spec.HOOD_Y0 + 0.4), ("b", spec.HOOD_Y1 - 0.4)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_hood_header_{sy}",
                (0.0, y, spec.HOOD_TOP_Z - 0.25),
                (2 * spec.HOOD_LEG_X + 0.4, 0.4, 0.5),
                steel,
                bevel=0.03,
                metric_uv=(1.6, 1.6),
            )
        )
    # Extraction duct: it takes off from the hood's +X wall at barrel
    # height and runs straight into the cyclone, so both ends are actually
    # inside the things they connect.
    duct_z = spec.CYCLONE_CAB[2] + 3.6
    duct_x0, duct_x1 = 1.9, spec.CYCLONE_X - spec.CYCLONE_R - 0.1
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_duct_run",
            ((duct_x0 + duct_x1) / 2.0, spec.CYCLONE_Y, duct_z),
            0.62,
            duct_x1 - duct_x0 + 1.24,
            paint,
            vertices=16,
            axis="X",
            metric_uv=(1.6, 1.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_duct_flange",
            (spec.HOOD_HALF_X + 0.08, spec.CYCLONE_Y, duct_z),
            (0.12, 1.6, 1.6),
            paint,
            bevel=0.02,
            metric_uv=(1.2, 1.2),
        )
    )
    # Equipment cabinet: the ONLY part of the extraction stack a car can
    # reach, and the cage lattice under it is this exact box. Everything
    # above 3.0 m (cone, barrel, stack) is visual.
    cab_w, cab_d, cab_h = spec.CYCLONE_CAB
    objects.append(
        bk.add_box(
            f"{MOD_ID}_cyclone_cabinet",
            (spec.CYCLONE_X, spec.CYCLONE_Y, cab_h / 2.0),
            (cab_w, cab_d, cab_h),
            paint,
            bevel=0.05,
            metric_uv=(1.8, 1.8),
        )
    )
    for i in range(3):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_cabinet_louvre_{i}",
                (spec.CYCLONE_X - cab_w / 2.0 - 0.01, spec.CYCLONE_Y, 0.9 + i * 0.45),
                (0.04, cab_d - 0.7, 0.22),
                steel,
                bevel=0.0,
                metric_uv=(0.8, 0.8),
            )
        )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_cabinet_band",
            (spec.CYCLONE_X, spec.CYCLONE_Y, 0.28),
            (cab_w + 0.02, cab_d + 0.02, 0.36),
            hazard,
            bevel=0.0,
            metric_uv=(1.2, 1.2),
        )
    )
    objects.append(
        bk.add_cone(
            f"{MOD_ID}_cyclone_cone",
            (spec.CYCLONE_X, spec.CYCLONE_Y, cab_h + 0.8),
            0.4,
            spec.CYCLONE_R,
            1.6,
            paint,
            vertices=24,
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_cyclone_barrel",
            (spec.CYCLONE_X, spec.CYCLONE_Y, cab_h + 3.2),
            spec.CYCLONE_R,
            3.2,
            paint,
            vertices=24,
            axis="Z",
            metric_uv=(2.0, 2.0),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_cyclone_stack",
            (spec.CYCLONE_X, spec.CYCLONE_Y, spec.CYCLONE_TOP_Z - 0.6),
            0.5,
            1.4,
            paint,
            vertices=16,
            metric_uv=(1.2, 1.2),
        )
    )


def _build_drive(objects, materials) -> None:
    """Belt drive package on the -X flank (extraction owns +X).

    One sheet-metal enclosure whose box IS its collision lattice; the
    motor, the V-belt and the motor sheave live inside it, which is where
    a real machine keeps them - so no static object is left pretending to
    be a rotating one. Only surface detail (vents, hazard band, cowl,
    junction box) sits proud of the collision, all under 0.2 m.
    """

    paint = materials[f"{MOD_ID}_machine_paint"]
    steel = materials[f"{MOD_ID}_frame_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]
    cx, cy, cz = spec.DRIVE_ENC_CENTER
    w, d, h = spec.DRIVE_ENC_SIZE
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_enclosure",
            (cx, cy, cz),
            (w, d, h),
            paint,
            bevel=0.05,
            metric_uv=(1.8, 1.8),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_band",
            (cx, cy, 0.3),
            (w + 0.02, d + 0.02, 0.4),
            hazard,
            bevel=0.0,
            metric_uv=(1.2, 1.2),
        )
    )
    for i in range(4):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_drive_louvre_{i}",
                (cx - w / 2.0 - 0.01, cy, 1.05 + i * 0.34),
                (0.04, d - 0.9, 0.2),
                steel,
                bevel=0.0,
                metric_uv=(0.8, 0.8),
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drive_cowl",
            (cx - w / 2.0 - 0.14, cy - d / 2.0 + 0.8, 1.9),
            0.42,
            0.3,
            steel,
            vertices=18,
            axis="X",
            metric_uv=(0.8, 0.8),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_junction",
            (cx - w / 2.0 - 0.09, cy + d / 2.0 - 0.7, 1.3),
            (0.18, 0.5, 0.66),
            steel,
            bevel=0.02,
            metric_uv=(0.8, 0.8),
        )
    )
    # V-belt guard: a sheet-metal run at shaft height from the drum shaft
    # back to the enclosure. The enclosure sits BEHIND the head drum (so it
    # does not stand in the drum inspection window), so the drive has to
    # visibly reach forward to the shaft - which is what a real machine's
    # belt guard does. Its far end is buried in the enclosure wall and its
    # near end in the frame, so neither end floats.
    guard_y0 = spec.DRIVE_Y - 0.35
    guard_y1 = cy - d / 2.0 + 0.3
    objects.append(
        bk.add_box(
            f"{MOD_ID}_drive_beltguard",
            (
                spec.DRIVE_GUARD_X,
                (guard_y0 + guard_y1) / 2.0,
                spec.DRUM_AXIS_Z + 0.05,
            ),
            (0.36, guard_y1 - guard_y0, 1.5),
            paint,
            bevel=0.06,
            metric_uv=(1.2, 1.2),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drive_beltguard_nose",
            (spec.DRIVE_GUARD_X, guard_y0, spec.DRUM_AXIS_Z + 0.05),
            0.75,
            0.36,
            paint,
            vertices=20,
            axis="X",
            metric_uv=(1.2, 1.2),
        )
    )
    # Shaft tunnel: a short sleeve bridges the frame skin to the belt
    # guard's nose so the shaft end is enclosed.
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_drive_sleeve",
            ((-WALK_X + spec.DRIVE_GUARD_X) / 2.0, spec.DRIVE_Y, spec.DRUM_AXIS_Z),
            0.42,
            abs(-WALK_X - spec.DRIVE_GUARD_X) + 0.4,
            steel,
            vertices=16,
            axis="X",
            metric_uv=(1.0, 1.0),
        )
    )


def _build_gantry(objects, materials) -> None:
    """Tail end frame: the portal the driver climbs the ramp toward.

    The whole 14.5 m ramp climb points at one place, and the first build
    put nothing there - so from the only viewpoint that matters the machine
    read as a conveyor in a shed. This is a real fabricated end frame: two
    legs on the machine's own leg line, a deep header, knee braces, and the
    machine's nameplate printed on the header face at a 15-20 degree
    elevation from the ramp foot (a comfortable read at 15 m). The header
    box IS its collision lattice, so the sign is not a ghost, and its
    underside is above HOOD_UNDER_Z so the portal never becomes the lowest
    ceiling on the lane.

    The legs also carry the belt take-up tension rockers (build_parts).
    """

    steel = materials[f"{MOD_ID}_frame_steel"]
    paint = materials[f"{MOD_ID}_machine_paint"]
    hazard = materials[f"{MOD_ID}_hazard"]
    sign_material = materials[f"{MOD_ID}_machine_sign"]

    gy = spec.GANTRY_Y
    half = spec.GANTRY_LEG_HALF
    for tag, sign in (("l", -1.0), ("r", 1.0)):
        lx = sign * spec.GANTRY_LEG_X
        objects.append(
            bk.add_box(
                f"{MOD_ID}_gantry_leg_{tag}",
                (lx, gy, spec.GANTRY_TOP_Z / 2.0),
                (2 * half, 2 * half, spec.GANTRY_TOP_Z),
                steel,
                bevel=0.03,
                metric_uv=(1.6, 1.6),
            )
        )
        objects.append(
            bk.add_box(
                f"{MOD_ID}_gantry_band_{tag}",
                (lx, gy, 0.55),
                (2 * half + 0.02, 2 * half + 0.02, 0.9),
                hazard,
                bevel=0.0,
                metric_uv=(1.0, 1.0),
            )
        )
        # Knee brace into the header - a portal with square corners reads
        # as scenery; a braced one reads as a weldment.
        objects.append(
            bk.add_box(
                f"{MOD_ID}_gantry_knee_{tag}",
                (lx - sign * 0.55, gy, spec.GANTRY_HEADER_Z0 - 0.55),
                (1.7, 0.34, 0.22),
                steel,
                bevel=0.0,
                rotation=(0.0, sign * math.radians(45.0), 0.0),
                metric_uv=(1.2, 1.2),
            )
        )
        # Bracket shelf off the leg carrying the tension rocker's spring
        # guide cup. Both are static; only the rocker itself moves.
        objects.append(
            bk.add_box(
                f"{MOD_ID}_tension_shelf_{tag}",
                (sign * (spec.TENSION_X - 0.10), gy + 0.75, 2.78),
                (0.9, 1.2, 0.20),
                steel,
                bevel=0.03,
                metric_uv=(1.0, 1.0),
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_tension_cup_{tag}",
                (sign * spec.TENSION_X, gy + 1.25, 3.10),
                0.45,
                0.50,
                steel,
                vertices=18,
                axis="Z",
                metric_uv=(1.0, 1.0),
            )
        )

    header_h = spec.GANTRY_TOP_Z - spec.GANTRY_HEADER_Z0
    objects.append(
        bk.add_box(
            f"{MOD_ID}_gantry_header",
            (0.0, gy, (spec.GANTRY_HEADER_Z0 + spec.GANTRY_TOP_Z) / 2.0),
            (
                2 * (spec.GANTRY_LEG_X + half),
                2 * spec.GANTRY_HEADER_HALF_Y,
                header_h,
            ),
            paint,
            bevel=0.06,
            metric_uv=(2.2, 2.2),
        )
    )
    # Nameplate skin on the header's -Y face, hand-unwrapped to the plate's
    # own 0..1 frame exactly like the console legend (bk.add_box UVs are
    # metric). A painted backing box behind it keeps the double-sided
    # policy from showing the print mirrored from the head end.
    sign_obj = bk.add_box(
        f"{MOD_ID}_gantry_sign",
        (0.0, gy - spec.GANTRY_HEADER_HALF_Y - 0.01, spec.SIGN_Z),
        (2 * spec.SIGN_HALF_X, 0.02, 2 * spec.SIGN_HALF_Z),
        sign_material,
        bevel=0.0,
    )
    smesh = sign_obj.data
    suv = smesh.uv_layers.active or smesh.uv_layers.new(name="UVMap")
    for polygon in smesh.polygons:
        if polygon.normal.y < -0.5:
            for loop_index in polygon.loop_indices:
                vx, _vy, vz = smesh.vertices[smesh.loops[loop_index].vertex_index].co
                suv.data[loop_index].uv = (
                    (vx + spec.SIGN_HALF_X) / (2 * spec.SIGN_HALF_X),
                    (vz + spec.SIGN_HALF_Z) / (2 * spec.SIGN_HALF_Z),
                )
    objects.append(sign_obj)
    for side, sz in ((-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_sign_bolt_{'p' if side > 0 else 'm'}{'t' if sz > 0 else 'b'}",
                (
                    side * (spec.SIGN_HALF_X - 0.18),
                    gy - spec.GANTRY_HEADER_HALF_Y - 0.04,
                    spec.SIGN_Z + sz * (spec.SIGN_HALF_Z - 0.16),
                ),
                (0.14, 0.06, 0.14),
                steel,
                bevel=0.0,
                metric_uv=(0.4, 0.4),
            )
        )


def _build_console(objects, materials) -> None:
    paint = materials[f"{MOD_ID}_machine_paint"]
    steel = materials[f"{MOD_ID}_frame_steel"]
    dark = materials[f"{MOD_ID}_panel_dark"]
    legend = materials[f"{MOD_ID}_panel_legend"]
    dial = materials[f"{MOD_ID}_dial_face"]
    concrete = materials[f"{MOD_ID}_concrete"]
    caps = {
        "green": materials[f"{MOD_ID}_btn_green"],
        "red": materials[f"{MOD_ID}_btn_red"],
        "amber": materials[f"{MOD_ID}_btn_amber"],
        "white": materials[f"{MOD_ID}_btn_white"],
    }
    cx, cy = spec.CONSOLE_X, spec.CONSOLE_Y

    objects.append(
        bk.add_box(
            f"{MOD_ID}_console_pad",
            (cx, cy, 0.09),
            (3.4, 2.6, 0.18),
            concrete,
            bevel=0.03,
            metric_uv=(1.6, 1.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_console_plinth",
            (cx, cy, 0.32),
            (2.6, 1.7, 0.46),
            steel,
            bevel=0.03,
            metric_uv=(1.6, 1.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_console_body",
            (cx, cy, 1.14),
            (2.4, 1.45, 1.30),
            paint,
            bevel=0.05,
            metric_uv=(1.6, 1.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_console_plate",
            (cx, cy - 0.70, spec.PLATE_Z0 + spec.PLATE_H / 2.0),
            (spec.PLATE_W, 0.06, spec.PLATE_H),
            dark,
            bevel=0.02,
        )
    )
    # Engraved legend skin: an 11 mm sheet over the faceplate whose FRONT
    # face carries an authored 0..1 UV frame (bk.add_box UVs are metric, so
    # this face is hand-unwrapped). Label positions come from the same
    # PANEL_BUTTONS table as the caps and the cage anchors.
    legend_obj = bk.add_box(
        f"{MOD_ID}_console_legend",
        (cx, cy - 0.7355, spec.PLATE_Z0 + spec.PLATE_H / 2.0),
        (spec.PLATE_W, 0.011, spec.PLATE_H),
        legend,
        bevel=0.0,
    )
    lmesh = legend_obj.data
    luv = lmesh.uv_layers.active or lmesh.uv_layers.new(name="UVMap")
    for polygon in lmesh.polygons:
        if polygon.normal.y < -0.5:
            for loop_index in polygon.loop_indices:
                vx, _vy, vz = lmesh.vertices[lmesh.loops[loop_index].vertex_index].co
                luv.data[loop_index].uv = (
                    (vx + spec.PLATE_W / 2.0) / spec.PLATE_W,
                    (vz + spec.PLATE_H / 2.0) / spec.PLATE_H,
                )
    objects.append(legend_obj)

    # Gauge binnacle: hood, dial face (its own printed legend sheet) and a
    # bezel. The NEEDLE is a kinematic part, built in build_parts.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_binnacle",
            (cx, cy - 0.30, spec.DIAL_Z),
            (2 * spec.DIAL_HALF + 0.24, 0.72, 2 * spec.DIAL_HALF + 0.24),
            paint,
            bevel=0.05,
            metric_uv=(1.2, 1.2),
        )
    )
    dial_obj = bk.add_box(
        f"{MOD_ID}_dial_face",
        (spec.DIAL_X, spec.DIAL_Y, spec.DIAL_Z),
        (2 * spec.DIAL_HALF, 0.02, 2 * spec.DIAL_HALF),
        dial,
        bevel=0.0,
    )
    dmesh = dial_obj.data
    duv = dmesh.uv_layers.active or dmesh.uv_layers.new(name="UVMap")
    for polygon in dmesh.polygons:
        if polygon.normal.y < -0.5:
            for loop_index in polygon.loop_indices:
                vx, _vy, vz = dmesh.vertices[dmesh.loops[loop_index].vertex_index].co
                duv.data[loop_index].uv = (
                    (vx + spec.DIAL_HALF) / (2 * spec.DIAL_HALF),
                    (vz + spec.DIAL_HALF) / (2 * spec.DIAL_HALF),
                )
    objects.append(dial_obj)

    for button in spec.PANEL_BUTTONS:
        bx, by, bz = button["position"]
        radius = button["radius"]
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_collar_{button['id']}",
                (bx, by + 0.045, bz),
                radius + 0.022,
                0.05,
                steel,
                vertices=18,
                axis="Y",
                metric_uv=(0.4, 0.4),
            )
        )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_cap_{button['id']}",
                (bx, by, bz),
                radius,
                0.07,
                caps[button["cap"]],
                vertices=18,
                axis="Y",
                metric_uv=(0.4, 0.4),
            )
        )
    for sx, sz in ((-0.87, 0.66), (0.87, 0.66), (-0.87, 1.62), (0.87, 1.62)):
        objects.append(
            bk.add_sphere(
                f"{MOD_ID}_console_screw_{'p' if sx > 0 else 'm'}{int(sz * 100)}",
                (cx + sx, cy - 0.742, sz),
                0.022,
                steel,
                segments=8,
                rings=6,
            )
        )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_console_conduit",
            (cx + 0.85, cy + 0.6, 0.5),
            0.07,
            1.0,
            steel,
            vertices=10,
            metric_uv=(0.4, 0.4),
        )
    )


def build_visual(materials) -> list:
    objects: list = []
    _build_lane(objects, materials)
    _build_belt(objects, materials)
    _build_hood(objects, materials)
    _build_drive(objects, materials)
    _build_gantry(objects, materials)
    _build_console(objects, materials)
    return objects


# ---------------------------------------------------------------------------
# Kinematic parts
# ---------------------------------------------------------------------------
def _loop_point(s: float) -> tuple[float, float, float]:
    """Python twin of BS.point in LUA_BEHAVIOR - the belt-loop arc-length
    parameterisation. The generator authors each splice bar at ``s`` and
    the runtime poses it at ``s + travel``; if these two functions ever
    disagreed the bars would jump at spawn, so they are written to be read
    side by side and main() asserts their shared invariants.
    """

    top = spec.TOP_RUN
    rw = spec.BELT_WRAP_R
    wrap = math.pi * rw
    s = s % spec.LOOP_LENGTH
    if s <= top:
        return spec.IDLER_Y + s, spec.BELT_Z, 0.0
    if s <= top + wrap:
        phi = (s - top) / rw
        return (
            spec.DRIVE_Y + rw * math.sin(phi),
            spec.DRUM_AXIS_Z + rw * math.cos(phi),
            -phi,
        )
    if s <= 2 * top + wrap:
        return spec.DRIVE_Y - (s - top - wrap), spec.DRUM_AXIS_Z - rw, -math.pi
    alpha = (s - 2 * top - wrap) / rw
    return (
        spec.IDLER_Y - rw * math.sin(alpha),
        spec.DRUM_AXIS_Z - rw * math.cos(alpha),
        -(math.pi + alpha),
    )


def _drum_objects(materials, tag: str, axis_y: float, with_sheave: bool) -> list:
    steel = materials[f"{MOD_ID}_frame_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]
    parts = [
        bk.add_cylinder(
            f"{MOD_ID}_{tag}_shell",
            (0.0, axis_y, spec.DRUM_AXIS_Z),
            spec.DRUM_R,
            2 * BH,
            steel,
            vertices=36,
            axis="X",
            metric_uv=(1.5, 1.5),
        ),
        bk.add_cylinder(
            f"{MOD_ID}_{tag}_shaft",
            (0.0, axis_y, spec.DRUM_AXIS_Z),
            0.16,
            2 * (WALK_X + 1.1),
            steel,
            vertices=12,
            axis="X",
            metric_uv=(0.8, 0.8),
        ),
    ]
    for side in (-1.0, 1.0):
        parts.append(
            bk.add_cylinder(
                f"{MOD_ID}_{tag}_flange_{'l' if side < 0 else 'r'}",
                (side * (BH - 0.06), axis_y, spec.DRUM_AXIS_Z),
                spec.DRUM_R + 0.04,
                0.10,
                steel,
                vertices=36,
                axis="X",
                metric_uv=(1.0, 1.0),
            )
        )
    # Diamond-groove lagging: 14 strips at the drum surface. Without a
    # surface feature a rotating cylinder is indistinguishable from a
    # stationary one, and the drum rotation is one of the three motion
    # cues this machine sells.
    for k in range(14):
        angle = 2.0 * math.pi * k / 14.0
        parts.append(
            bk.add_box(
                f"{MOD_ID}_{tag}_lag_{k:02d}",
                (
                    0.0,
                    axis_y - spec.DRUM_R * math.sin(angle),
                    spec.DRUM_AXIS_Z + spec.DRUM_R * math.cos(angle),
                ),
                (2 * BH - 0.25, 0.14, 0.05),
                steel,
                bevel=0.0,
                rotation=(angle, 0.0, 0.0),
                metric_uv=(1.0, 1.0),
            )
        )
    if with_sheave:
        # FLYWHEEL on the free (+X) end of the head shaft - the drive motor
        # is enclosed on the -X flank, so this end carries the inertia disc
        # and the brake. It is the one large rotating object visible from
        # outside the guarding, and because it is keyed to the same shaft
        # its angular rate is the drum's by construction: omega = v / r.
        parts.append(
            bk.add_cylinder(
                f"{MOD_ID}_{tag}_flywheel",
                (WALK_X + 0.55, axis_y, spec.DRUM_AXIS_Z),
                0.95,
                0.20,
                steel,
                vertices=28,
                axis="X",
                metric_uv=(1.2, 1.2),
            )
        )
        for k in range(5):
            angle = 2.0 * math.pi * k / 5.0
            parts.append(
                bk.add_box(
                    f"{MOD_ID}_{tag}_spoke_{k}",
                    (
                        WALK_X + 0.55,
                        axis_y - 0.48 * math.sin(angle),
                        spec.DRUM_AXIS_Z + 0.48 * math.cos(angle),
                    ),
                    (0.22, 0.16, 0.92),
                    hazard,
                    bevel=0.0,
                    rotation=(angle, 0.0, 0.0),
                    metric_uv=(0.6, 0.6),
                )
            )
    return parts


def build_parts(materials) -> dict[str, dict[str, object]]:
    splice = materials[f"{MOD_ID}_belt_splice"]
    needle_red = materials[f"{MOD_ID}_needle_red"]
    steel = materials[f"{MOD_ID}_frame_steel"]

    parts: dict[str, dict[str, object]] = {}

    # 16 splice bars, authored AT their home loop station with their home
    # tilt baked in. The runtime applies the DELTA from home, so at
    # travel = 0 the pose is the identity and the thumbnail shows exactly
    # what spawns. Every bar travels the whole loop: over the carrying run,
    # around the head drum, back along the return run, up over the tail
    # drum. Nothing about the motion is a texture trick.
    for k in range(spec.BAR_COUNT):
        home = k * spec.BAR_PITCH
        y, z, theta = _loop_point(home)
        normal = (-math.sin(theta), math.cos(theta))
        # The slab is 50 mm thick and sits so BAR_PROUD of it stands above
        # the belt face; the rest is buried in the 100 mm carcass, which is
        # what a vulcanised splice looks like.
        centre = (
            y + normal[0] * (spec.BAR_PROUD - 0.025),
            z + normal[1] * (spec.BAR_PROUD - 0.025),
        )
        bar = bk.add_box(
            f"{MOD_ID}_bar{k:02d}",
            (0.0, centre[0], centre[1]),
            (2 * spec.BAR_HALF_WIDTH, spec.BAR_LENGTH_Y, 0.05),
            splice,
            bevel=0.0,
            rotation=(theta, 0.0, 0.0),
            metric_uv=(1.2, 1.2),
        )
        parts[f"bar{k:02d}"] = {"objects": [bar], "pivot": (0.0, y, z)}

    parts["drum_head"] = {
        "objects": _drum_objects(materials, "drumhead", spec.DRIVE_Y, True),
        "pivot": (0.0, spec.DRIVE_Y, spec.DRUM_AXIS_Z),
    }
    parts["drum_tail"] = {
        "objects": _drum_objects(materials, "drumtail", spec.IDLER_Y, False),
        "pivot": (0.0, spec.IDLER_Y, spec.DRUM_AXIS_Z),
    }

    # Console needle, authored ON THE ZERO STOP (rotated -NEEDLE_SPAN_DEG
    # about the hub) so the shipped mesh is the machine's rest reading and
    # the runtime applies the delta from zero: axisAngle(+Y, 2*span*frac).
    # Same discipline as the splice bars - a zero-input pose is always the
    # identity, so the DAE and the spawn state cannot disagree.
    needle_y = spec.DIAL_Y - 0.05
    zero = math.radians(-spec.NEEDLE_SPAN_DEG)

    def _about_hub(dz):
        """Point dz above the hub, rotated onto the zero stop."""

        return (
            spec.DIAL_X + math.sin(zero) * dz,
            needle_y,
            spec.DIAL_Z + math.cos(zero) * dz,
        )

    needle_objects = [
        bk.add_box(
            f"{MOD_ID}_needle_blade",
            _about_hub(spec.NEEDLE_LENGTH / 2.0),
            (0.045, 0.024, spec.NEEDLE_LENGTH),
            needle_red,
            bevel=0.0,
            rotation=(0.0, zero, 0.0),
        ),
        bk.add_box(
            f"{MOD_ID}_needle_tail",
            _about_hub(-0.075),
            (0.06, 0.024, 0.15),
            needle_red,
            bevel=0.0,
            rotation=(0.0, zero, 0.0),
        ),
        bk.add_cylinder(
            f"{MOD_ID}_needle_hub",
            (spec.DIAL_X, needle_y - 0.01, spec.DIAL_Z),
            0.055,
            0.05,
            steel,
            vertices=14,
            axis="Y",
            metric_uv=(0.3, 0.3),
        ),
    ]
    parts["needle"] = {
        "objects": needle_objects,
        "pivot": (spec.DIAL_X, needle_y, spec.DIAL_Z),
    }

    # Belt take-up tension rockers, one per gantry leg. The brief asks for
    # a tension arm and take-up SCREWS buried inside the frame were not
    # one: these are 3 m fore-aft rockers standing 1.9 m clear above the
    # walkway, counterweight aft, spring canister forward standing in its
    # guide cup. Authored AT REST (frac = 0 is the identity pose) and
    # driven by the same b.speed as the drums and the needle, because belt
    # tension really does climb with belt speed.
    dark = materials[f"{MOD_ID}_panel_dark"]
    hazard = materials[f"{MOD_ID}_hazard"]
    cast = materials[f"{MOD_ID}_concrete"]
    # King post + two tie rods over the pivot. A plain bar rocker
    # disappeared against the grey gantry in the first render; the trussed
    # silhouette is what makes a tension arm read as a tension arm from
    # 20 m, and it is what a real counterweighted take-up looks like.
    post_top = 0.80
    rod_drop = 0.70
    rod_reach = spec.TENSION_ARM_HALF - 0.05
    rod_length = math.hypot(rod_reach, rod_drop)
    rod_angle = math.atan2(rod_drop, rod_reach)
    for tag, sign in (("l", -1.0), ("r", 1.0)):
        px = sign * spec.TENSION_X
        py = spec.GANTRY_Y
        pz = spec.TENSION_PIVOT_Z
        rocker_objects = [
            bk.add_box(
                f"{MOD_ID}_rocker{tag}_arm",
                (px, py, pz),
                (0.30, 2 * spec.TENSION_ARM_HALF, 0.46),
                # Hazard-striped on purpose: it is the only large member on
                # the machine that MOVES where a person could stand, and in
                # grey it vanished against the grey gantry in every render.
                hazard,
                bevel=0.03,
                metric_uv=(1.2, 1.2),
            ),
            bk.add_box(
                f"{MOD_ID}_rocker{tag}_post",
                (px, py, pz + 0.45),
                (0.22, 0.22, 0.72),
                steel,
                bevel=0.02,
                metric_uv=(0.6, 0.6),
            ),
            bk.add_cylinder(
                f"{MOD_ID}_rocker{tag}_hub",
                (px, py, pz),
                0.20,
                0.44,
                steel,
                vertices=16,
                axis="X",
                metric_uv=(0.6, 0.6),
            ),
            bk.add_box(
                f"{MOD_ID}_rocker{tag}_weight",
                (px, py - 1.30, pz),
                (0.62, 0.78, 0.78),
                cast,
                bevel=0.03,
                metric_uv=(0.9, 0.9),
            ),
            bk.add_box(
                f"{MOD_ID}_rocker{tag}_weightband",
                (px, py - 1.30, pz - 0.30),
                (0.64, 0.80, 0.20),
                hazard,
                bevel=0.0,
                metric_uv=(0.6, 0.6),
            ),
            bk.add_cylinder(
                f"{MOD_ID}_rocker{tag}_spring",
                (px, py + 1.25, pz - 0.70),
                0.22,
                1.40,
                dark,
                vertices=16,
                axis="Z",
                metric_uv=(0.5, 0.5),
            ),
            bk.add_cylinder(
                f"{MOD_ID}_rocker{tag}_shoe",
                (px, py + 1.25, pz - 1.36),
                0.26,
                0.12,
                steel,
                vertices=16,
                axis="Z",
                metric_uv=(0.5, 0.5),
            ),
        ]
        for end, way in (("f", 1.0), ("a", -1.0)):
            rocker_objects.append(
                bk.add_box(
                    f"{MOD_ID}_rocker{tag}_rod{end}",
                    (
                        px,
                        py + way * rod_reach / 2.0,
                        pz + (post_top - rod_drop / 2.0),
                    ),
                    (0.10, rod_length, 0.10),
                    steel,
                    bevel=0.0,
                    rotation=(-way * rod_angle, 0.0, 0.0),
                    metric_uv=(0.4, 0.4),
                )
            )
        parts[f"tension_{tag}"] = {
            "objects": rocker_objects,
            "pivot": (px, py, pz),
        }
    return parts


# ---------------------------------------------------------------------------
# Physics cage
# ---------------------------------------------------------------------------
def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    stations = _stations(coarse=True)

    # One row of 13 nodes per station, generated from the SAME height
    # functions the visual lofts use. Column order runs left to right so
    # every quad below can be wound x-increasing / y-increasing, whose
    # cross product is +Z (the AGENTS.md winding trap: (a, a+1, b+1, b)
    # walking +y then +x is -Z, not +Z).
    # guard_* sit OUTBOARD of walk_* by the panel rake (spec.guard_face_x),
    # which is why this list is not monotone in x. Nothing below depends on
    # that: the collision quads are named pairs, and the only quads whose
    # winding matters (the deck) are all inside deck_columns.
    guard_x = spec.guard_face_x(spec.GUARD_H)
    columns = (
        ("found_l", -WALK_X, "found"),
        ("guard_l", -guard_x, "guard"),
        ("walk_l", -WALK_X, "walk"),
        ("defl_l", -DEF_X, "walk"),
        ("deck_0", spec.DECK_COLUMNS[0], "deck"),
        ("deck_1", spec.DECK_COLUMNS[1], "deck"),
        ("deck_2", spec.DECK_COLUMNS[2], "deck"),
        ("deck_3", spec.DECK_COLUMNS[3], "deck"),
        ("deck_4", spec.DECK_COLUMNS[4], "deck"),
        ("defl_r", DEF_X, "walk"),
        ("walk_r", WALK_X, "walk"),
        ("guard_r", guard_x, "guard"),
        ("found_r", WALK_X, "found"),
    )
    grid: dict[str, list[str]] = {name: [] for name, _x, _kind in columns}
    for index, y in enumerate(stations):
        deck = spec.deck_z(y)
        walk = deck + spec.skirt_rise(y)
        for name, x, kind in columns:
            if kind == "deck":
                z = deck
            elif kind == "walk":
                z = walk
            elif kind == "guard":
                z = walk + spec.GUARD_H
            else:
                z = 0.0
            grid[name].append(
                cage.add_node(
                    f"{name}_{index:02d}",
                    (x, y, z),
                    fixed=True,
                    collision=True,
                    weight=140.0,
                    friction=0.95,
                )
            )
    order = [name for name, _x, _kind in columns]

    # Lateral chain + a shear diagonal at every station.
    for index in range(len(stations)):
        for a, b in zip(order, order[1:]):
            cage.add_beam(grid[a][index], grid[b][index])
        cage.add_beam(grid["found_l"][index], grid["defl_l"][index])
        cage.add_beam(grid["found_r"][index], grid["defl_r"][index])
        cage.add_beam(grid["guard_l"][index], grid["defl_l"][index])
        cage.add_beam(grid["guard_r"][index], grid["defl_r"][index])
        cage.add_beam(grid["deck_0"][index], grid["deck_2"][index])
        cage.add_beam(grid["deck_2"][index], grid["deck_4"][index])

    # Longitudinal beams + diagonals, and the collision surfaces.
    deck_columns = ["deck_0", "deck_1", "deck_2", "deck_3", "deck_4"]
    for index in range(len(stations) - 1):
        nxt = index + 1
        for name in order:
            cage.add_beam(grid[name][index], grid[name][nxt])
        for a, b in zip(order, order[1:]):
            cage.add_beam(grid[a][index], grid[b][nxt])
        # The drivable lane: one-way floors wound +Z. The belt region is
        # part of this same continuous plane - the cage never asks whether
        # the surface under a wheel is steel or rubber.
        y_mid = 0.5 * (stations[index] + stations[nxt])
        # Ground models tell the truth about what the tyre is on. The lane
        # deck is one continuous plane, but it is not one material: the
        # loading ramp is a road surface, the belt band between the two
        # drum tangents is a coated abrasive, and the transfer nose plates
        # and the discharge apron are smooth sheet steel. BeamNG has no
        # abrasive model, so the belt takes "asphalt" - the highest-grip
        # stock model this pack ships, and the surface the injected drag
        # ceiling (mu 0.92, spec.BEHAVIOR) was sized against. Shipping the
        # belt as "metal" meant the car pushed back through a smooth-steel
        # model while the belt pulled with abrasive numbers, which biased
        # the winnable half of the design. _stations() cuts a station at
        # each drum tangent so this test never straddles a boundary.
        if y_mid <= spec.RAMP_CREST_Y:
            ground = "asphalt"
        elif spec.IDLER_Y <= y_mid <= spec.DRIVE_Y:
            ground = "asphalt"
        else:
            ground = "metal"
        for a, b in zip(deck_columns, deck_columns[1:]):
            cage.add_quad(
                [grid[a][index], grid[b][index], grid[b][nxt], grid[a][nxt]],
                ground_model=ground,
            )
        # Deflectors (34% - slopes deflect, vertical faces pop tyres) and
        # the walkway grating outboard of them.
        for a, b in (
            ("defl_l", "deck_0"),
            ("deck_4", "defl_r"),
            ("walk_l", "defl_l"),
            ("defl_r", "walk_r"),
        ):
            cage.add_quad(
                [grid[a][index], grid[b][index], grid[b][nxt], grid[a][nxt]],
                ground_model="metal",
            )
        # Outer skin and guard panel: near-vertical, so add_quad_both's
        # crossed-diagonal pair (four distinct triples, no zero-thickness
        # twin) is the sanctioned pattern. Over a drum station the OUTER
        # SKIN is dropped, exactly matching the visual loft's cut, so the
        # inspection window is a real opening and not a hole in front of an
        # invisible wall. The guard panel above it is kept: on a real
        # machine the rail over an open drum station is the LAST thing you
        # remove, and it is now raked so it deflects rather than stops.
        skins = [("walk_l", "guard_l"), ("walk_r", "guard_r")]
        if not spec.in_drum_window(y_mid):
            skins = [("found_l", "walk_l"), ("found_r", "walk_r")] + skins
        for a, b in skins:
            cage.add_quad_both(
                [grid[a][index], grid[b][index], grid[b][nxt], grid[a][nxt]],
                ground_model="metal",
            )

    def nearest_station(y: float) -> int:
        return min(range(len(stations)), key=lambda i: abs(stations[i] - y))

    # --- dust hood: a ceiling 3.6 m over the belt, on outboard legs ------
    # The lattice bounds ARE the visual hood box, and it gets every face:
    # the shell is a solid box, so collision matching it exactly can never
    # outreach it. A car on the belt passes 2.1 m under it.
    hood = cage.add_box_lattice(
        "hood",
        (-spec.HOOD_HALF_X, spec.HOOD_Y0, spec.HOOD_UNDER_Z),
        (spec.HOOD_HALF_X, spec.HOOD_Y1, spec.HOOD_TOP_Z),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("bottom", "top", "north", "south", "east", "west"),
    )
    # One lattice per LEG, matching each 0.42 m column exactly. A single
    # lattice spanning both legs would have been a 6.8 m long invisible
    # wall where the visual has two posts.
    legs: dict[tuple[str, str], dict] = {}
    leg_ys = (("a", spec.HOOD_Y0 + 0.4), ("b", spec.HOOD_Y1 - 0.4))
    for tag, sign in (("l", -1.0), ("r", 1.0)):
        for sy, ly in leg_ys:
            legs[(tag, sy)] = cage.add_box_lattice(
                f"hoodleg_{tag}{sy}",
                (sign * spec.HOOD_LEG_X - 0.21, ly - 0.21, 0.0),
                (sign * spec.HOOD_LEG_X + 0.21, ly + 0.21, spec.HOOD_TOP_Z),
                subdivisions=(1, 1, 3),
                fixed=True,
                collision=False,
                collision_faces=("north", "south", "east", "west"),
            )
    for tag, key in (("l", "found_l"), ("r", "found_r")):
        for iy, (sy, ly) in enumerate(leg_ys):
            leg = legs[(tag, sy)]
            index = nearest_station(ly)
            hood_ix = 0 if tag == "l" else 2
            hood_iy = 0 if iy == 0 else 2
            for ix in (0, 1):
                cage.add_beam(leg[(ix, 0, 0)], grid[key][index])
                cage.add_beam(leg[(ix, 1, 0)], grid[key][index])
                cage.add_beam(leg[(ix, 0, 3)], hood[(hood_ix, hood_iy, 1)])
                cage.add_beam(leg[(ix, 1, 3)], hood[(hood_ix, hood_iy, 1)])
            cage.add_beam(leg[(0, 0, 2)], hood[(hood_ix, hood_iy, 0)])

    # --- extraction cabinet ----------------------------------------------
    # Only the cabinet is collidable, and its lattice is exactly the shell
    # box. The cyclone cone/barrel/stack sit on its roof from 3.0 m up and
    # are visual only - nothing a car can reach is a ghost.
    cab_w, cab_d, cab_h = spec.CYCLONE_CAB
    cyclone = cage.add_box_lattice(
        "cabinet",
        (spec.CYCLONE_X - cab_w / 2.0, spec.CYCLONE_Y - cab_d / 2.0, 0.0),
        (spec.CYCLONE_X + cab_w / 2.0, spec.CYCLONE_Y + cab_d / 2.0, cab_h),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("north", "south", "east", "west", "top"),
    )
    cyclone_station = nearest_station(spec.CYCLONE_Y)
    for ix in (0, 1):
        for iy in (0, 1):
            cage.add_beam(cyclone[(ix, iy, 0)], grid["found_r"][cyclone_station])
    # Skinning support for the barrel/stack column above the cabinet, so
    # those vertices bind to nearby nodes instead of smearing to the deck.
    stack_nodes = []
    for level, z in enumerate((cab_h + 2.2, spec.CYCLONE_TOP_Z)):
        node = cage.add_node(
            f"stack_{level}",
            (spec.CYCLONE_X, spec.CYCLONE_Y, z),
            fixed=True,
            collision=False,
            weight=60.0,
        )
        stack_nodes.append(node)
    cage.add_beam(stack_nodes[0], cyclone[(0, 0, 1)])
    cage.add_beam(stack_nodes[0], cyclone[(1, 1, 1)])
    cage.add_beam(stack_nodes[0], cyclone[(1, 0, 1)])
    cage.add_beam(stack_nodes[0], cyclone[(0, 1, 1)])
    cage.add_beam(stack_nodes[0], stack_nodes[1])
    cage.add_beam(stack_nodes[1], legs[("r", "b")][(1, 1, 3)])

    # --- belt drive enclosure (-X flank) ---------------------------------
    dcx, dcy, _dcz = spec.DRIVE_ENC_CENTER
    dw, dd, dh = spec.DRIVE_ENC_SIZE
    drive = cage.add_box_lattice(
        "driveenc",
        (dcx - dw / 2.0, dcy - dd / 2.0, 0.0),
        (dcx + dw / 2.0, dcy + dd / 2.0, dh),
        subdivisions=(1, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("north", "south", "west", "top"),
    )
    for iy in range(3):
        y = dcy - dd / 2.0 + dd * iy / 2.0
        index = nearest_station(y)
        cage.add_beam(drive[(1, iy, 0)], grid["found_l"][index])
        cage.add_beam(drive[(1, iy, 1)], grid["walk_l"][index])

    # --- operator console + panel anchors --------------------------------
    # Front face at CONSOLE_Y - 0.62, i.e. 8 cm BEHIND the legend plate, so
    # no collision plane stands in front of the click boxes and swallows
    # the mouse ray (round-15 lesson).
    console = cage.add_box_lattice(
        "console",
        (spec.CONSOLE_X - 1.3, spec.CONSOLE_Y - 0.62, 0.0),
        (spec.CONSOLE_X + 1.3, spec.CONSOLE_Y + 0.85, spec.CONSOLE_TOP_Z),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("north", "south", "east", "west", "top"),
    )
    console_station = nearest_station(spec.CONSOLE_Y)
    for ix in (0, 1):
        for iy in (0, 1):
            cage.add_beam(console[(ix, iy, 0)], grid["found_r"][console_station])
    # The gauge binnacle stands 1.2 m above the console body, so it gets
    # its own lattice rather than being a ghost (or being swallowed by an
    # oversized console box that would be collision without a visual).
    binnacle_half = spec.DIAL_HALF + 0.12
    binnacle = cage.add_box_lattice(
        "binnacle",
        (
            spec.CONSOLE_X - binnacle_half,
            spec.CONSOLE_Y - 0.62,
            spec.DIAL_Z - binnacle_half,
        ),
        (
            spec.CONSOLE_X + binnacle_half,
            spec.CONSOLE_Y + 0.04,
            spec.DIAL_Z + binnacle_half,
        ),
        subdivisions=(1, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("north", "south", "east", "west", "top"),
    )
    for ix in (0, 1):
        for iy in (0, 1):
            cage.add_beam(binnacle[(ix, iy, 0)], console[(ix, iy, 1)])
    panel_nodes: list[str] = []
    for button in spec.PANEL_BUTTONS:
        # 9 cm proud of the caps: anchored AT the cap the click boxes sit
        # behind the console's own collision and hover never fires.
        anchor = (
            button["position"][0],
            button["position"][1] - 0.09,
            button["position"][2],
        )
        node = cage.add_node(
            f"panelbtn_{button['id']}",
            anchor,
            fixed=True,
            collision=False,
            weight=20.0,
        )
        panel_nodes.append(node)
        # Per-button orthonormal frame: the triggers2 basis is
        # (idX - idRef, idY - idRef), so a shared frame pair gives every
        # off-row button a skewed AND translated hitbox.
        for tag, offset in (("fx", (0.4, 0.0, 0.0)), ("fy", (0.0, 0.0, 0.4))):
            frame = cage.add_node(
                f"panel{tag}_{button['id']}",
                (
                    anchor[0] + offset[0],
                    anchor[1] + offset[1],
                    anchor[2] + offset[2],
                ),
                fixed=True,
                collision=False,
                weight=20.0,
            )
            cage.add_beam(frame, console[(1, 1, 1)])
    frame_x = cage.add_node(
        "panel_frame_x", spec.PANEL_FRAME_X, fixed=True, collision=False, weight=20.0
    )
    frame_y = cage.add_node(
        "panel_frame_y", spec.PANEL_FRAME_Y, fixed=True, collision=False, weight=20.0
    )
    for node in [*panel_nodes, frame_x, frame_y]:
        cage.add_beam(node, console[(1, 1, 1)])
        cage.add_beam(node, console[(0, 1, 1)])

    # --- tail end frame (gantry portal + nameplate) ----------------------
    # Two leg lattices matching the 0.56 m columns exactly (one lattice
    # spanning both would be a 13 m invisible wall across the feed end) and
    # a header lattice that IS the header box, so the nameplate hanging on
    # its face is backed by collision instead of being a ghost 3.75 m over
    # the lane.
    gantry_legs: dict[str, dict] = {}
    leg_half = spec.GANTRY_LEG_HALF
    for tag, sign in (("l", -1.0), ("r", 1.0)):
        gantry_legs[tag] = cage.add_box_lattice(
            f"gantryleg_{tag}",
            (
                sign * spec.GANTRY_LEG_X - leg_half,
                spec.GANTRY_Y - leg_half,
                0.0,
            ),
            (
                sign * spec.GANTRY_LEG_X + leg_half,
                spec.GANTRY_Y + leg_half,
                spec.GANTRY_TOP_Z,
            ),
            subdivisions=(1, 1, 3),
            fixed=True,
            collision=False,
            collision_faces=("north", "south", "east", "west"),
        )
    header = cage.add_box_lattice(
        "gantryhead",
        (
            -(spec.GANTRY_LEG_X + leg_half),
            spec.GANTRY_Y - spec.GANTRY_HEADER_HALF_Y,
            spec.GANTRY_HEADER_Z0,
        ),
        (
            spec.GANTRY_LEG_X + leg_half,
            spec.GANTRY_Y + spec.GANTRY_HEADER_HALF_Y,
            spec.GANTRY_TOP_Z,
        ),
        subdivisions=(4, 1, 1),
        fixed=True,
        collision=False,
        collision_faces=("bottom", "top", "north", "south", "east", "west"),
    )
    gantry_station = nearest_station(spec.GANTRY_Y)
    for tag, key in (("l", "found_l"), ("r", "found_r")):
        leg = gantry_legs[tag]
        hx = 0 if tag == "l" else 4
        for ix in (0, 1):
            for iy in (0, 1):
                cage.add_beam(leg[(ix, iy, 0)], grid[key][gantry_station])
                cage.add_beam(leg[(ix, iy, 3)], header[(hx, iy, 1)])
        cage.add_beam(leg[(0, 0, 2)], header[(hx, 0, 0)])
        cage.add_beam(leg[(1, 1, 2)], header[(hx, 1, 0)])

    # --- ground datum ----------------------------------------------------
    # Under the belt, on the machine centreline: a min-Z pair so the prop
    # spawns with its foundation on the map surface. "back" must map to +Y
    # in vehicle space, i.e. sit at SMALLER authored y than "ref".
    mid = nearest_station(0.0)
    back = nearest_station(-6.0)
    cage.set_ground_reference(
        (0.0, stations[mid], 0.0),
        (0.0, stations[back], 0.0),
        left=grid["found_l"][mid],
        up=grid["deck_2"][mid],
        support_nodes=[
            grid["found_l"][mid],
            grid["found_r"][mid],
            grid["found_l"][back],
            grid["found_r"][back],
        ],
    )

    last = len(stations) - 1
    # The spawn-relocation volume has to contain the MACHINE, not just its
    # kerbs: the first build declared eight nodes spanning z 0.0-1.22 on a
    # prop whose structure reaches z 7.6, so the engine's relocation box
    # ignored the hood, the extraction stack and the drive package
    # entirely. These eight are the extreme corners in all three axes -
    # both foundation ends (z 0, the full 57.5 m of lane), the gantry
    # header top (z 7.6), the drive enclosure on -X (x -8.2) and the
    # extraction cabinet on +X (x 10.3) - and every one of them is already
    # a collidable lattice corner, so set_spawn_envelope's forced
    # collision=True changes nothing.
    cage.set_spawn_envelope(
        [
            grid["found_l"][0],
            grid["found_r"][0],
            grid["found_l"][last],
            grid["found_r"][last],
            header[(0, 0, 1)],
            header[(4, 1, 1)],
            drive[(0, 0, 1)],
            cyclone[(1, 1, 1)],
        ]
    )
    cage.auto_base_nodes()
    return cage


# ---------------------------------------------------------------------------
# Build-time invariants
# ---------------------------------------------------------------------------
def _assert_invariants(
    cage: bk.CageBuilder, visual_bounds, belt_bounds, used, part_names
) -> None:
    # 1. No two cage nodes within 1 cm. A flexbody vertex skinned to a
    #    triad containing two coincident nodes has a degenerate basis and
    #    its triangles simply do not draw (centrifuge 2026-08-08, three
    #    days of an invisible deck band).
    points = [tuple(node["position"]) for node in cage.nodes]
    buckets: dict[tuple[int, int, int], list[tuple[float, float, float]]] = {}
    worst = (1e9, None, None)
    for point in points:
        key = (int(point[0] // 0.5), int(point[1] // 0.5), int(point[2] // 0.5))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other in buckets.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        distance = math.dist(point, other)
                        if distance < worst[0]:
                            worst = (distance, point, other)
        buckets.setdefault(key, []).append(point)
    assert worst[0] >= 0.01, f"coincident cage nodes {worst}"

    # 2. The belt's outer face over the carrying run IS the deck plane the
    #    cage drives on. Measured from the built mesh, not from the source.
    assert abs(belt_bounds["max"][2] - spec.BELT_Z) < 1e-4, belt_bounds
    assert belt_bounds["min"][2] > 0.15, "return run must clear grade"

    # 3. Lane grade never exceeds 20.1% anywhere (the centrifuge measured
    #    ~16% as fine and 23% as a creep-throttle stall; the only 20% here
    #    is the DESCENDING outfeed).
    y = spec.RAMP_FOOT_Y
    worst_grade = 0.0
    while y < spec.OUTFEED_END_Y - 0.05:
        grade = abs(spec.deck_z(y + 0.05) - spec.deck_z(y)) / 0.05
        worst_grade = max(worst_grade, grade)
        y += 0.05
    assert worst_grade <= 0.201, f"lane grade {worst_grade}"
    climb = max(abs(spec.deck_z(y0 + 0.05) - spec.deck_z(y0)) / 0.05
                for y0 in [spec.RAMP_FOOT_Y + i * 0.05
                           for i in range(int(spec.RAMP_RUN / 0.05))])
    assert climb <= 0.161, f"climbing grade {climb}"

    # 4. The collision plane and the visible surface can only diverge in
    #    the two short bands between a nose plate's tip and its drum
    #    tangent, and there by at most the relief cap.
    #    An independent cull-aware raycast measured the shipped mesh at
    #    0.0205 m here, marginally OVER the AGENTS.md cap, so the nose
    #    plate tips were thinned and this bound was halved with them. It is
    #    now the tightest relief tolerance on the prop.
    tip = nose_tip_offset()
    divergence = 0.0
    for i in range(200):
        y = spec.IDLER_Y - tip + tip * i / 199.0
        outer = belt_outer_z(y)
        if outer is not None:
            divergence = max(divergence, abs(spec.deck_z(y) - outer))
    assert divergence <= 0.0101, f"deck/belt divergence {divergence}"

    # 5. Splice bars are inside the relief cap, carry no collision, and
    #    still pass UNDER the thinned nose plate tips.
    assert spec.BAR_PROUD <= 0.02
    assert spec.BAR_HALF_WIDTH < spec.BELT_HALF_WIDTH
    assert spec.LIP_TIP_CLEAR > spec.BAR_PROUD, "nose plate would foul a splice bar"

    # 6. Hood clearance for a 1.5 m car on the belt.
    assert spec.HOOD_UNDER_Z - 0.45 >= spec.BELT_Z + 3.0, "hood too low"

    # 7. Every palette material is worn by a real object, and every material
    #    worn is in the palette. A looked-up-but-never-assigned material
    #    means a whole object was never built (the centrifuge's 0.95 m
    #    annular hole, 2026-08-07); the set is harvested from the BUILT
    #    meshes, not from bookkeeping that could drift.
    unused = sorted(set(spec.PALETTE) - used)
    assert not unused, f"palette entries with no object: {unused}"
    stray = sorted(used - set(spec.PALETTE))
    assert not stray, f"objects wearing materials outside the palette: {stray}"

    # 8. The runtime's belt loop and the generator's must agree: the loop
    #    must close, and every bar home must land on the belt's own
    #    surface.
    y0, z0, t0 = _loop_point(0.0)
    y1, z1, t1 = _loop_point(spec.LOOP_LENGTH - 1e-9)
    assert abs(y0 - y1) < 1e-3 and abs(z0 - z1) < 1e-3, "belt loop does not close"
    assert abs(t0) < 1e-9 and abs(t1 + 2 * math.pi) < 1e-3, (t0, t1)
    for k in range(spec.BAR_COUNT):
        y, z, _theta = _loop_point(k * spec.BAR_PITCH)
        radius = math.hypot(
            y - (spec.IDLER_Y if y < spec.IDLER_Y else spec.DRIVE_Y),
            z - spec.DRUM_AXIS_Z,
        )
        on_run = abs(z - spec.BELT_Z) < 1e-6 or abs(z - spec.RETURN_RUN_Z) < 1e-6
        assert on_run or abs(radius - spec.BELT_WRAP_R) < 1e-6, (k, y, z)

    # 9. The whole machine fits inside the prop's own footprint claim.
    assert visual_bounds["min"][2] >= -spec.LANE_UNDERCUT - 0.01, visual_bounds

    # 10. The guard panel is genuinely raked, and its top edge clears the
    #     machine's leg line (hood legs, gantry legs) and the belt drive
    #     enclosure so the rake cannot silently intersect them.
    top_x = spec.guard_face_x(spec.GUARD_H)
    assert top_x > spec.WALKWAY_X + 0.1, f"guard panel is not raked: {top_x}"
    assert top_x < spec.HOOD_LEG_X - 0.21, (top_x, spec.HOOD_LEG_X)
    assert top_x < spec.GANTRY_LEG_X - spec.GANTRY_LEG_HALF, top_x
    drive_inner = abs(spec.DRIVE_ENC_CENTER[0]) - spec.DRIVE_ENC_SIZE[0] / 2.0
    drive_top = spec.DRIVE_ENC_CENTER[2] + spec.DRIVE_ENC_SIZE[2] / 2.0
    drive_y = spec.DRIVE_ENC_CENTER[1]
    walk_at_drive = spec.deck_z(drive_y) + spec.skirt_rise(drive_y)
    assert spec.guard_face_x(drive_top - walk_at_drive) <= drive_inner, drive_inner

    # 11. The drum inspection windows are REAL: no collision triangle may
    #     survive on the outer-skin plane inside a window's y span, or the
    #     opening would be a hole in front of an invisible wall.
    positions = {node["id"]: node["position"] for node in cage.nodes}
    edges = _window_edges()
    windows = [(edges[0], edges[1]), (edges[2], edges[3])]
    offenders = 0
    for triangle in cage.triangles:
        points = [positions[name] for name in triangle["nodes"]]
        if any(abs(abs(point[0]) - spec.WALKWAY_X) > 1e-6 for point in points):
            continue
        for low, high in windows:
            if all(low + 1e-6 < point[1] < high - 1e-6 for point in points):
                offenders += 1
    assert offenders == 0, f"{offenders} collision triangles inside a drum window"
    # ... and the window is not merely an empty list of spans.
    coarse = _stations(coarse=True)
    assert any(
        spec.in_drum_window(0.5 * (a + b)) for a, b in zip(coarse, coarse[1:])
    ), "no cage span falls inside a drum window"
    # ... and no service package is parked in front of an opening. Cutting
    # a window and then standing the extraction cabinet in it would be
    # worse than leaving the skin solid, so the two big flank packages are
    # required to clear both windows by a real margin.
    for label, centre_y, depth in (
        ("cyclone cabinet", spec.CYCLONE_Y, spec.CYCLONE_CAB[1]),
        ("drive enclosure", spec.DRIVE_ENC_CENTER[1], spec.DRIVE_ENC_SIZE[1]),
    ):
        near, far = centre_y - depth / 2.0, centre_y + depth / 2.0
        for low, high in windows:
            overlap = min(far, high) - max(near, low)
            assert overlap <= 0.35 * (high - low), (label, overlap)

    # 12. Every part the runtime poses by name exists in the export set.
    #     The Lua and this generator are the two halves of one contract and
    #     a typo on either side is a silent nil pose.
    named = ("drum_head", "drum_tail", "needle", "tension_l", "tension_r")
    posed = set(named) | {f"bar{k:02d}" for k in range(spec.BAR_COUNT)}
    missing = sorted(posed - set(part_names))
    assert not missing, f"runtime poses parts that were never exported: {missing}"
    extra = sorted(set(part_names) - posed)
    assert not extra, f"parts exported that the runtime never poses: {extra}"
    for name in named:
        assert f'"{name}"' in spec.LUA_BEHAVIOR, f"runtime never poses {name}"
    assert '"bar%02d"' in spec.LUA_BEHAVIOR, "runtime never poses the splice bars"

    # 13. The tail portal must never become the lowest ceiling over the
    #     lane: its header bottom sits above the dust hood's own datum.
    assert spec.GANTRY_HEADER_Z0 >= spec.HOOD_UNDER_Z, (
        spec.GANTRY_HEADER_Z0,
        spec.HOOD_UNDER_Z,
    )
    assert spec.SIGN_Z - spec.SIGN_HALF_Z > spec.GANTRY_HEADER_Z0
    assert spec.SIGN_Z + spec.SIGN_HALF_Z < spec.GANTRY_TOP_Z
    assert spec.SIGN_HALF_X < spec.GANTRY_LEG_X + spec.GANTRY_LEG_HALF


def _bake_and_quantise(objects, places: int = 5) -> None:
    """Freeze modifier output and snap it onto a fixed numeric grid.

    Two things made this generator non-reproducible even though it has no
    randomness. The DAE ``<asset>`` clock is one (see ``_pin_dae_epoch``);
    the other is last-bit float noise: every primitive carries a Bevel and
    a Smooth-by-Angle modifier, they are evaluated lazily at export time,
    and consecutive runs differed by ~300 tokens of 1-ulp drift in the
    normal and UV streams (measured: 0.5666667 vs 0.5666668).

    This performs the SAME evaluation the exporter would (evaluated_get +
    new_from_object, preserving data layers), stores the result, and then
    rounds coordinates and UVs to 1e-5 - 10 microns of geometry and about
    a hundredth of a texel on a 1024 map. The exported shape is unchanged
    to any measurement a player or a probe can make; the bytes stop
    moving.
    """

    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        baked = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
        )
        previous = obj.data
        baked.name = f"{previous.name}_baked"
        obj.modifiers.clear()
        obj.data = baked
        if previous.users == 0:
            bpy.data.meshes.remove(previous)
        for vertex in baked.vertices:
            vertex.co = (
                round(vertex.co[0], places),
                round(vertex.co[1], places),
                round(vertex.co[2], places),
            )
        for layer in baked.uv_layers:
            for datum in layer.data:
                datum.uv = (round(datum.uv[0], places), round(datum.uv[1], places))


def _pin_dae_epoch(dae_path: Path) -> dict[str, object]:
    """Rewrite a DAE's wall-clock <asset> stamps and re-hash it.

    Blender's Collada exporter writes the build machine's clock into
    ``<created>``/``<modified>``, which is the ONLY reason two identical
    runs of this otherwise deterministic generator produced different
    handoff hashes (measured: the structural diff was DAE sha256/size and
    nothing else). Pinning both stamps to a fixed epoch makes this mod's
    zip byte-reproducible. Byte-level rewrite on purpose - text mode would
    translate line endings on Windows and change the file for real.
    """

    payload = dae_path.read_bytes()
    for tag in (b"created", b"modified"):
        payload = re.sub(
            b"<" + tag + b">[^<]*</" + tag + b">",
            b"<" + tag + b">" + DAE_EPOCH + b"</" + tag + b">",
            payload,
        )
    dae_path.write_bytes(payload)
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    }


def main() -> None:
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)
    part_builds = build_parts(materials)

    # Bake modifiers and snap the numbers BEFORE anything measures or
    # exports, so the bounds asserts below and the shipped DAEs describe
    # exactly the same geometry.
    _bake_and_quantise(visual_objects)
    for build in part_builds.values():
        _bake_and_quantise(build["objects"])

    belt_object = next(
        obj for obj in visual_objects if obj.name == f"{MOD_ID}_belt_loop"
    )
    belt_bounds = bk.evaluated_object_bounds(belt_object)

    # Harvest the material set from the BUILT meshes (the exports below
    # join and destroy the source objects, so this has to happen first).
    used: set[str] = set()
    for obj in visual_objects:
        used.update(m.name for m in obj.data.materials if m is not None)
    for build in part_builds.values():
        for obj in build["objects"]:
            used.update(m.name for m in obj.data.materials if m is not None)

    parts = []
    for name, build in sorted(part_builds.items()):
        dae_path = VEHICLE_DIR / f"{MOD_ID}_{name}.dae"
        info = bk.export_part_shape(
            MOD_ID, name, dae_path, build["objects"], build["pivot"]
        )
        info["path"] = f"vehicles/{MOD_ID}/{MOD_ID}_{name}.dae"
        info.update(_pin_dae_epoch(dae_path))
        parts.append(info)

    visual_dae = VEHICLE_DIR / f"{MOD_ID}.dae"
    visual = bk.export_flexbody_visual(
        MOD_ID,
        visual_dae,
        visual_objects,
        f"{MOD_ID}_visual",
    )
    visual.update(_pin_dae_epoch(visual_dae))

    cage = build_cage()
    _assert_invariants(
        cage, visual["bounds"], belt_bounds, used, [part["name"] for part in parts]
    )

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
        panel={
            "frame_x_node": f"{MOD_ID}_panel_frame_x",
            "frame_y_node": f"{MOD_ID}_panel_frame_y",
            "button_size": 0.16,
            "buttons": [
                {
                    "id": button["id"],
                    "title": button["title"],
                    "node": f"{MOD_ID}_panelbtn_{button['id']}",
                    "frame_x_node": f"{MOD_ID}_panelfx_{button['id']}",
                    "frame_y_node": f"{MOD_ID}_panelfy_{button['id']}",
                    "size": round(2.1 * button["radius"], 4),
                }
                for button in spec.PANEL_BUTTONS
            ],
        },
    )
    # Framed on the MACHINE, not the ramp. The first framing stood far
    # enough back to fit all 57 m of lane in, which made 14.5 m of grey
    # approach ramp the subject and shrank the belt to a brown stripe.
    # This one sits off the feed quarter: the tail portal and its nameplate
    # lead, the belt and its chevrons run away from the viewer to the head
    # drum, and the hood, cyclone and console all stay in frame.
    bk.render_thumbnail(
        AUTHORING_ROOT / f"{MOD_ID}_thumbnail.jpg",
        camera_location=(21.0, -28.0, 9.5),
        look_at=(-1.0, 4.0, 3.2),
    )
    print(
        "BELT_SANDER_TRAP generator complete: "
        f"{len(parts)} parts, {len(cage.nodes)} nodes, "
        f"{len(cage.beams)} beams, {len(cage.triangles)} triangles"
    )


if __name__ == "__main__":
    main()
