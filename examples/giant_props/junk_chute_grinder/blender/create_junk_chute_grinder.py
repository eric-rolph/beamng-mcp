"""Deterministic Blender generator for the Junk Chute Grinder Trap.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/junk_chute_grinder/blender/create_junk_chute_grinder.py

Every drivable surface in this prop is a QUAD STRIP generated from a profile
function that lives in ``spec.py``. The visual mesh and the collision cage
consume the SAME function at the SAME stations, so mesh and physics cannot
drift apart (AGENTS.md: "Derive every cage dimension from spec or from the
component's own function; never retype a number").

``add_surface`` is a local helper, not a proplib addition: three sibling
agents are editing this repo concurrently and proplib is off limits.
"""

from __future__ import annotations

import math
import sys
from itertools import pairwise
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))

import bpy  # noqa: E402
import spec  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

S = spec  # short alias; every constant below is spec-owned


# ---------------------------------------------------------------------------
# Local mesh helper: a metric-UV quad strip from a grid of measured points.
# ---------------------------------------------------------------------------
def add_surface(
    name: str,
    grid: list[list[tuple[float, float, float]]],
    material,
    *,
    meters_per_tile: tuple[float, float] = (3.0, 3.0),
    face_up: bool | None = True,
) -> bpy.types.Object:
    """Build a rows x cols quad sheet with arc-length (metric) UVs.

    ``face_up`` orients the sheet by its MEAN normal: True for floors, False
    for soffits, None to leave the authored winding. Open surfaces have no
    "outside" for ``recalc_face_normals`` to find, so the mean-normal rule is
    the one AGENTS.md prescribes. (Every material on this prop is also forced
    double-sided, so this only fixes shading, never visibility.)
    """

    rows = len(grid)
    cols = len(grid[0])
    if rows < 2 or cols < 2:
        raise ValueError(f"surface {name} needs at least a 2x2 grid")
    for row in grid:
        if len(row) != cols:
            raise ValueError(f"surface {name} has ragged rows")

    verts = [Vector(point) for row in grid for point in row]
    faces = []
    for i in range(rows - 1):
        for j in range(cols - 1):
            a = i * cols + j
            b = i * cols + j + 1
            c = (i + 1) * cols + j + 1
            d = (i + 1) * cols + j
            faces.append((a, b, c, d))

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    # Arc-length UVs: u accumulates along the row, v along the column, so a
    # converging chute keeps a constant texel density instead of smearing.
    u_grid = [[0.0] * cols for _ in range(rows)]
    v_grid = [[0.0] * cols for _ in range(rows)]
    for i in range(rows):
        for j in range(1, cols):
            u_grid[i][j] = u_grid[i][j - 1] + (Vector(grid[i][j]) - Vector(grid[i][j - 1])).length
    for j in range(cols):
        for i in range(1, rows):
            v_grid[i][j] = v_grid[i - 1][j] + (Vector(grid[i][j]) - Vector(grid[i - 1][j])).length
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            vertex_index = mesh.loops[loop_index].vertex_index
            i, j = divmod(vertex_index, cols)
            uv_layer.data[loop_index].uv = (
                u_grid[i][j] / meters_per_tile[0],
                v_grid[i][j] / meters_per_tile[1],
            )

    if face_up is not None:
        mean_z = sum(polygon.normal.z for polygon in mesh.polygons)
        if (mean_z < 0.0) == bool(face_up):
            mesh.flip_normals()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, material)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def sign_face_uvs(obj: bpy.types.Object) -> bpy.types.Object:
    """Map the -Y face of a plate to the WHOLE texture, everything else to a
    blank corner of it.

    Blender's ``primitive_cube_add`` does NOT give each face the full 0..1
    image - it writes a six-face CROSS ATLAS, so the -Y face samples only
    u 0.375..0.625, v 0.75..1.0. The legend plate has been reading that
    one-sixteenth window of its own texture: the title, drawn at v = 0.885,
    survived as a smudge and anything placed lower vanished entirely.
    Measured on a factory-startup cube, not assumed
    (`primitive_cube_add` -> per-face UV bounds).

    u runs with authored +x, which is the driver's left-to-right: forward is
    +y and up is +z, so right = forward x up = +x. The world flip is a proper
    180 deg rotation about Z, not a mirror, so the legend still reads.
    """

    mesh = obj.data
    uv = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    xs = [vertex.co.x for vertex in mesh.vertices]
    zs = [vertex.co.z for vertex in mesh.vertices]
    span_x = max(1e-6, max(xs) - min(xs))
    span_z = max(1e-6, max(zs) - min(zs))
    for polygon in mesh.polygons:
        front = polygon.normal.y < -0.5
        for loop_index in polygon.loop_indices:
            coordinate = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            if front:
                uv.data[loop_index].uv = (
                    (coordinate.x - min(xs)) / span_x,
                    (coordinate.z - min(zs)) / span_z,
                )
            else:
                # Blank plate: the texture's own frame margin.
                uv.data[loop_index].uv = (0.012, 0.012)
    return obj


def add_triangle_patch(name, a, b, c, material) -> bpy.types.Object:
    """A single flat triangle. Used only for the hopper's rear corner fillers,
    which are genuinely triangular - forcing them into a quad grid would emit
    a zero-area face."""

    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata([Vector(a), Vector(b), Vector(c)], [], [(0, 1, 2)])
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    span = max((Vector(b) - Vector(a)).length, (Vector(c) - Vector(a)).length, 0.001)
    for loop_index, uv in zip(mesh.polygons[0].loop_indices, ((0, 0), (1, 0), (0, 1)), strict=True):
        uv_layer.data[loop_index].uv = (uv[0] * span / 3.0, uv[1] * span / 3.0)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, material)
    return obj


# ---------------------------------------------------------------------------
# Shared station tables. The cage and the visual both index these, so a
# station added here appears in both or in neither.
# ---------------------------------------------------------------------------
CREST_ROW = 1.5  # crest vertical-curve row spacing


def ramp_stations() -> list[float]:
    """Ramp rows: dense through the toe blend, 4.5 m on the straight, and
    ``CREST_ROW`` apart across the crest vertical curve.

    Row spacing matters on the crest and nowhere else: the collision surface
    is the CHORD between rows, so a coarse row on a curving profile is a kink
    the tyres feel. At 1.5 m rows the grade steps by only
    (RAMP_GRADE + CHUTE_GRADE_MOUTH) / CREST_LEN * CREST_ROW = 0.050 per row
    (2.9 deg), and the build-time gate below measures the resulting chord
    protrusion on this exact polyline rather than on the analytic curve.
    """

    stations = [S.TOE_Y + offset for offset in (0.0, 1.5, 3.0, 4.5, 6.0)]
    y = stations[-1]
    while y < S.CREST_Y0 - 1e-6:
        y = min(S.CREST_Y0, y + 4.5)
        stations.append(y)
    steps = max(2, int(round(S.CREST_LEN / CREST_ROW)))
    for step in range(1, steps + 1):
        stations.append(S.CREST_Y0 + step * S.CREST_LEN / steps)
    return stations


CHUTE_STATIONS = [-14.0, -12.4, -10.6, -8.8, -7.0, -6.0, -5.0]
SLOT_STATIONS = [-5.0, -2.5, 0.0, 2.5, 5.0]
ARC_STEPS = 7  # 0..180 deg of the inner half of each drum, 30 deg apart
BELT_STATIONS = [-6.6, -3.0, 0.0, 4.0, 8.0, 12.0, 15.6]
APRON_X = [-S.APRON_HALF_X, -4.5, 0.0, 4.5, S.APRON_HALF_X]
APRON_Y = [S.APRON_Y_MIN, -6.5, 0.0, 7.5, S.APRON_Y_MAX]
RAMP_RIBS = 10
# Derived from the pile's own three datums so the toe row cannot drift behind
# the conveyor's head toe when either moves.
PILE_STATIONS = (
    S.PILE_TOE_Y,
    (S.PILE_TOE_Y + S.PILE_CREST_Y) / 2.0,
    S.PILE_CREST_Y,
    (S.PILE_CREST_Y + S.PILE_TAIL_Y) / 2.0,
    S.PILE_TAIL_Y,
)


def roller_arc(side: int, alpha: float) -> tuple[float, float]:
    """Point on the inner half of a drum's COLLISION cylinder.

    ``alpha`` is measured from the crown toward the nip: 0 = crown,
    pi/2 = the nip face, pi = the drum underside. ``side`` is -1 (authored
    -x drum) or +1. The radius is ROLL_CAGE_R - the cutter-disc rim, which is
    the surface a body actually rests on - not the hook-tip circle.
    """

    x = side * (S.ROLL_AXIS_X - S.ROLL_CAGE_R * math.sin(alpha))
    z = S.ROLL_AXIS_Z + S.ROLL_CAGE_R * math.cos(alpha)
    return x, z


def lane_polyline() -> list[tuple[float, float]]:
    """The faceted drive lane the tyres actually touch: cage rows only."""

    ys = sorted(set(ramp_stations() + CHUTE_STATIONS))
    return [(y, S.lane_z(y)) for y in ys]


def lane_height(polyline: list[tuple[float, float]], y: float) -> float:
    """Linear interpolation along the faceted lane."""

    if y <= polyline[0][0]:
        return polyline[0][1]
    if y >= polyline[-1][0]:
        return polyline[-1][1]
    for (y0, z0), (y1, z1) in pairwise(polyline):
        if y0 <= y <= y1:
            return z0 + (z1 - z0) * (y - y0) / (y1 - y0)
    return polyline[-1][1]


def worst_chord_protrusion(
    polyline: list[tuple[float, float]], wheelbase: float, step: float = 0.05
) -> tuple[float, float]:
    """Worst surface height above the wheel-contact chord, and where.

    This is the high-centre / breakover metric: put both axles on the faceted
    lane ``wheelbase`` apart and measure how far the surface between them
    stands above the straight line joining the contacts. A compact carries
    0.15-0.20 m of belly clearance, so anything approaching that grounds out.
    """

    start = polyline[0][0]
    finish = polyline[-1][0] - wheelbase
    worst, worst_at = 0.0, start
    samples = int((finish - start) / step)
    for index in range(max(0, samples) + 1):
        rear = start + index * step
        front = rear + wheelbase
        z_rear = lane_height(polyline, rear)
        z_front = lane_height(polyline, front)
        inner = int(wheelbase / step)
        for k in range(1, inner):
            t = k / inner
            y = rear + wheelbase * t
            protrusion = lane_height(polyline, y) - (z_rear + (z_front - z_rear) * t)
            if protrusion > worst:
                worst, worst_at = protrusion, y
    return worst, worst_at


def pile_profile(y: float) -> tuple[float, float]:
    """(crest height, half width) of the scrap mound at station y."""

    if y <= S.PILE_TOE_Y:
        return S.PILE_TOE_Z, S.PILE_HALF_W * 0.7
    if y <= S.PILE_CREST_Y:
        t = (y - S.PILE_TOE_Y) / (S.PILE_CREST_Y - S.PILE_TOE_Y)
        return (
            S.PILE_TOE_Z + (S.PILE_CREST_Z - S.PILE_TOE_Z) * t,
            S.PILE_HALF_W * (0.7 + 0.3 * t),
        )
    t = (y - S.PILE_CREST_Y) / (S.PILE_TAIL_Y - S.PILE_CREST_Y)
    t = min(1.0, t)
    return S.PILE_CREST_Z * (1.0 - t), S.PILE_HALF_W * (1.0 - 0.55 * t)


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


# ---------------------------------------------------------------------------
# Static visual
# ---------------------------------------------------------------------------
def build_visual(materials) -> list:
    steel = materials[f"{MOD_ID}_mill_steel"]
    orange = materials[f"{MOD_ID}_machine_orange"]
    tooth = materials[f"{MOD_ID}_tooth_steel"]
    hazard = materials[f"{MOD_ID}_hazard"]
    grate = materials[f"{MOD_ID}_grate"]
    asphalt = materials[f"{MOD_ID}_deck_asphalt"]
    concrete = materials[f"{MOD_ID}_concrete"]
    rust = materials[f"{MOD_ID}_rust_scrap"]
    black = materials[f"{MOD_ID}_hydraulic_black"]
    amber = materials[f"{MOD_ID}_beacon_amber"]
    legend = materials[f"{MOD_ID}_legend"]

    objects: list[bpy.types.Object] = []

    # ---- ground apron ----------------------------------------------------
    # Top face sits at exactly z = 0, the cage's ground plane, and the slab
    # is buried below it so there is no curb to catch a wheel.
    objects.append(
        bk.add_box(
            f"{MOD_ID}_apron",
            (0.0, (S.APRON_Y_MIN + S.APRON_Y_MAX) / 2.0, -0.15),
            (2 * S.APRON_HALF_X, S.APRON_Y_MAX - S.APRON_Y_MIN, 0.30),
            concrete,
            bevel=0.0,
            metric_uv=(4.0, 4.0),
        )
    )

    # ---- haul ramp: deck, kerbs, embankment skirts ------------------------
    stations = ramp_stations()
    deck_grid, kerb_l, kerb_r, skirt_l, skirt_r = [], [], [], [], []
    for y in stations:
        z = S.ramp_deck_z(y)
        crest = z + S.KERB_RISE
        outer = S.ramp_skirt_x(y)
        deck_grid.append([(-S.RAMP_HALF_W, y, z), (0.0, y, z), (S.RAMP_HALF_W, y, z)])
        kerb_l.append([(-S.RAMP_HALF_W, y, z), (-S.RAMP_HALF_W - S.KERB_RUN, y, crest)])
        kerb_r.append([(S.RAMP_HALF_W, y, z), (S.RAMP_HALF_W + S.KERB_RUN, y, crest)])
        skirt_l.append([(-S.RAMP_HALF_W - S.KERB_RUN, y, crest), (-outer, y, 0.0)])
        skirt_r.append([(S.RAMP_HALF_W + S.KERB_RUN, y, crest), (outer, y, 0.0)])
    objects.append(
        add_surface(f"{MOD_ID}_ramp_deck", deck_grid, asphalt, meters_per_tile=(4.0, 4.0))
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_ramp_kerb_l", kerb_l, hazard, meters_per_tile=(1.6, 1.6), face_up=True
        )
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_ramp_kerb_r", kerb_r, hazard, meters_per_tile=(1.6, 1.6), face_up=True
        )
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_ramp_skirt_l", skirt_l, concrete, meters_per_tile=(3.5, 3.5), face_up=True
        )
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_ramp_skirt_r", skirt_r, concrete, meters_per_tile=(3.5, 3.5), face_up=True
        )
    )
    # Buttress ribs on the skirt: without them a 41 m concrete face reads as a
    # blank wall. Centred ON the skirt surface, so the buried half never shows.
    for rib in range(RAMP_RIBS):
        y = S.TOE_Y + 4.0 + rib * (S.RAMP_RUN - 8.0) / (RAMP_RIBS - 1)
        crest = S.ramp_deck_z(y) + S.KERB_RISE
        outer = S.ramp_skirt_x(y)
        run = outer - (S.RAMP_HALF_W + S.KERB_RUN)
        length = math.hypot(run, crest)
        for side in (-1, 1):
            # Rotation about +Y maps local +Z to (sin, 0, cos); the skirt runs
            # outward in side*x and down in -z, so the angle is per side. (An
            # earlier `side * angle` mirrored BOTH ribs and rendered them as
            # flat decals lying on the slab - caught in the thumbnail.)
            angle = math.atan2(side * run, -crest)
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_ramp_rib_{'l' if side < 0 else 'r'}_{rib}",
                    (side * (S.RAMP_HALF_W + S.KERB_RUN + run / 2.0), y, crest / 2.0),
                    (0.70, 0.75, length),
                    concrete,
                    bevel=0.04,
                    rotation=(0.0, angle, 0.0),
                    metric_uv=(1.8, 1.8),
                )
            )

    # Head wall closing the embankment where the elevated chute takes over.
    head_outer = S.ramp_skirt_x(S.MOUTH_Y)
    head_crest = S.MOUTH_Z + S.KERB_RISE
    objects.append(
        add_surface(
            f"{MOD_ID}_ramp_headwall",
            [
                [
                    (-head_outer, S.MOUTH_Y, 0.0),
                    (0.0, S.MOUTH_Y, 0.0),
                    (head_outer, S.MOUTH_Y, 0.0),
                ],
                [
                    (-S.RAMP_HALF_W - S.KERB_RUN, S.MOUTH_Y, head_crest),
                    (0.0, S.MOUTH_Y, S.MOUTH_Z),
                    (S.RAMP_HALF_W + S.KERB_RUN, S.MOUTH_Y, head_crest),
                ],
            ],
            concrete,
            meters_per_tile=(3.5, 3.5),
            face_up=None,
        )
    )

    # ---- chute floor, soffit and hopper flanks ---------------------------
    floor_grid, soffit_grid, flank_l, flank_r = [], [], [], []
    for y in CHUTE_STATIONS:
        z = S.chute_floor_z(y)
        half = S.chute_half_width(y)
        floor_grid.append([(-half, y, z), (0.0, y, z), (half, y, z)])
        soffit_grid.append([(-half, y, z - 0.55), (0.0, y, z - 0.55), (half, y, z - 0.55)])
        flank_l.append([(-half, y, z), (-S.RIM_HALF_X, y, S.RIM_Z)])
        flank_r.append([(half, y, z), (S.RIM_HALF_X, y, S.RIM_Z)])
    objects.append(
        add_surface(f"{MOD_ID}_chute_floor", floor_grid, steel, meters_per_tile=(2.6, 2.6))
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_chute_soffit", soffit_grid, steel, meters_per_tile=(3.0, 3.0), face_up=False
        )
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_chute_flank_l", flank_l, orange, meters_per_tile=(3.0, 3.0), face_up=True
        )
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_chute_flank_r", flank_r, orange, meters_per_tile=(3.0, 3.0), face_up=True
        )
    )
    # Chute edge beams: without them a generated sheet reads as paper on end.
    for side in (-1, 1):
        for y0, y1 in pairwise(CHUTE_STATIONS):
            ym = (y0 + y1) / 2.0
            half = S.chute_half_width(ym)
            zc = S.chute_floor_z(ym)
            drop = S.chute_floor_z(y0) - S.chute_floor_z(y1)
            pitch = math.atan2(drop, y1 - y0)
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_chute_edge_{'l' if side < 0 else 'r'}_{y0:.0f}".replace("-", "n"),
                    (side * half, ym, zc - 0.28),
                    (0.30, (y1 - y0) + 0.25, 0.60),
                    steel,
                    bevel=0.03,
                    rotation=(-pitch, 0.0, 0.0),
                    metric_uv=(1.5, 1.5),
                )
            )
    # Chute support legs down to the apron.
    for side in (-1, 1):
        for y in (-12.0, -8.5):
            z = S.chute_floor_z(y) - 0.55
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_chute_leg_{'l' if side < 0 else 'r'}_{abs(int(y))}",
                    (side * (S.chute_half_width(y) - 0.4), y, z / 2.0),
                    (0.55, 0.55, z),
                    steel,
                    bevel=0.04,
                    metric_uv=(1.6, 1.6),
                )
            )

    # ---- hopper side flanks over the slot + back plate + corner fillers ---
    # Base line = the SWEPT hook circle's crown (TIP_TOP_Z), never the
    # collision crown: a fixed sheet whose base sits on the collision cylinder
    # would be swept through by every hook, 6 times a revolution.
    throat_l, throat_r = [], []
    for y in SLOT_STATIONS:
        throat_l.append([(-S.ROLL_AXIS_X, y, S.TIP_TOP_Z), (-S.RIM_HALF_X, y, S.RIM_Z)])
        throat_r.append([(S.ROLL_AXIS_X, y, S.TIP_TOP_Z), (S.RIM_HALF_X, y, S.RIM_Z)])
    objects.append(
        add_surface(
            f"{MOD_ID}_throat_flank_l", throat_l, orange, meters_per_tile=(3.0, 3.0), face_up=True
        )
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_throat_flank_r", throat_r, orange, meters_per_tile=(3.0, 3.0), face_up=True
        )
    )
    back_grid = []
    for t in (0.0, 0.5, 1.0):
        y = S.SLOT_HALF_Y + (S.BACK_RIM_Y - S.SLOT_HALF_Y) * t
        z = S.BACK_BASE_Z + (S.RIM_Z - S.BACK_BASE_Z) * t
        half = S.ROLL_AXIS_X + (S.RIM_HALF_X - S.ROLL_AXIS_X) * t
        back_grid.append([(-half, y, z), (0.0, y, z), (half, y, z)])
    objects.append(
        add_surface(
            f"{MOD_ID}_hopper_back", back_grid, orange, meters_per_tile=(3.0, 3.0), face_up=True
        )
    )
    for side in (-1, 1):
        # Rear corner filler: the triangle left between the last side-flank
        # section, the rim and the back plate's outer edge. Without it each
        # rear corner of the hopper is an open slot to the sky.
        objects.append(
            add_triangle_patch(
                f"{MOD_ID}_hopper_corner_{'l' if side < 0 else 'r'}",
                (side * S.ROLL_AXIS_X, S.SLOT_HALF_Y, S.TIP_TOP_Z),
                (side * S.RIM_HALF_X, S.SLOT_HALF_Y, S.RIM_Z),
                (side * S.RIM_HALF_X, S.BACK_RIM_Y, S.RIM_Z),
                orange,
            )
        )
    # Hazard band around the rim: a warning stripe you read from the ramp.
    for side in (-1, 1):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_rim_band_{'l' if side < 0 else 'r'}",
                (side * S.RIM_HALF_X, (S.MOUTH_Y + S.BACK_RIM_Y) / 2.0, S.RIM_Z - 0.22),
                (0.36, S.BACK_RIM_Y - S.MOUTH_Y, 0.44),
                hazard,
                bevel=0.03,
                metric_uv=(1.4, 1.4),
            )
        )

    # ---- machine frame ----------------------------------------------------
    for sx in (-1, 1):
        for sy in (-1, 1):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_column_{'l' if sx < 0 else 'r'}_{'f' if sy < 0 else 'b'}",
                    (sx * S.COLUMN_X, sy * S.COLUMN_Y, S.COLUMN_TOP_Z / 2.0),
                    (2 * S.COLUMN_HALF, 2 * S.COLUMN_HALF, S.COLUMN_TOP_Z),
                    steel,
                    bevel=0.05,
                    metric_uv=(1.8, 1.8),
                )
            )
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_col_band_{'l' if sx < 0 else 'r'}_{'f' if sy < 0 else 'b'}",
                    (sx * S.COLUMN_X, sy * S.COLUMN_Y, 1.10),
                    (2 * S.COLUMN_HALF + 0.06, 2 * S.COLUMN_HALF + 0.06, 1.30),
                    hazard,
                    bevel=0.0,
                    metric_uv=(1.2, 1.2),
                )
            )
    for sy in (-1, 1):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_headbeam_{'f' if sy < 0 else 'b'}",
                (0.0, sy * S.COLUMN_Y, S.COLUMN_TOP_Z + 0.35),
                (2 * S.COLUMN_X + 0.9, 0.8, 0.7),
                steel,
                bevel=0.05,
                metric_uv=(2.0, 2.0),
            )
        )
    for sx in (-1, 1):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_siderail_{'l' if sx < 0 else 'r'}",
                (sx * S.COLUMN_X, 0.0, S.COLUMN_TOP_Z + 0.35),
                (0.7, 2 * S.COLUMN_Y, 0.7),
                steel,
                bevel=0.05,
                metric_uv=(2.0, 2.0),
            )
        )
    # Bearing housings + hydraulic drive motors on the discharge end.
    # Bearing radius 0.85 at y = +/-6.0: measured against the chute soffit by
    # the headless raycast probe - at r 1.00 / y 5.55 the housing punched
    # 0.26 m through the chute underside.
    for sx in (-1, 1):
        for sy in (-1, 1):
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_bearing_{'l' if sx < 0 else 'r'}_{'f' if sy < 0 else 'b'}",
                    (sx * S.ROLL_AXIS_X, sy * (S.SLOT_HALF_Y + 1.0), S.ROLL_AXIS_Z),
                    0.85,
                    1.1,
                    steel,
                    vertices=20,
                    axis="Y",
                    metric_uv=(1.6, 1.6),
                )
            )
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_motor_{'l' if sx < 0 else 'r'}",
                (sx * S.ROLL_AXIS_X, S.SLOT_HALF_Y + 2.05, S.ROLL_AXIS_Z),
                0.60,
                1.2,
                black,
                vertices=16,
                axis="Y",
                metric_uv=(1.2, 1.2),
            )
        )
        for hose in range(3):
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_hose_{'l' if sx < 0 else 'r'}_{hose}",
                    (
                        sx * (S.ROLL_AXIS_X + 0.30 + hose * 0.16),
                        S.SLOT_HALF_Y + 1.9,
                        S.ROLL_AXIS_Z - 1.6,
                    ),
                    0.09,
                    2.8,
                    black,
                    vertices=8,
                )
            )
    # Anti-wrap comb bars: the fixed fingers that strip material off the
    # rotor. Visual only, and they run in the SPACER GROOVES between the
    # cutter discs - which is the whole reason a real rotor has grooves. Their
    # inner face reaches r = 1.06 from the drum axis: outside the collision
    # cylinder (1.00) so they never fight the physics, inside the hook circle
    # (1.15) so they read as combing, and clear of the 0.90 spacer ring by
    # 0.16 m. Groove pitch and width are the rotor's own, so a comb can never
    # land on a disc.
    row_pitch = 2 * S.SLOT_HALF_Y / S.TOOTH_ROWS
    for sx in (-1, 1):
        for groove in range(1, S.TOOTH_ROWS):
            y = -S.SLOT_HALF_Y + groove * row_pitch
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_comb_{'l' if sx < 0 else 'r'}_{groove}",
                    (sx * (S.ROLL_AXIS_X + 0.92), y, S.ROLL_AXIS_Z - 0.95),
                    (0.9, S.ROLL_SPACER_T - 0.16, 0.34),
                    tooth,
                    bevel=0.03,
                    metric_uv=(0.9, 0.9),
                )
            )

    # ---- service walkway + handrails -------------------------------------
    for sx in (-1, 1):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_walkway_{'l' if sx < 0 else 'r'}",
                (sx * (S.WALK_X_IN + S.WALK_X_OUT) / 2.0, 0.0, S.WALK_Z),
                (S.WALK_X_OUT - S.WALK_X_IN, 2 * S.COLUMN_Y + 1.2, 0.12),
                grate,
                bevel=0.0,
                metric_uv=(1.1, 1.1),
            )
        )
        for post in range(7):
            y = -S.COLUMN_Y - 0.4 + post * (2 * S.COLUMN_Y + 0.8) / 6.0
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_rail_post_{'l' if sx < 0 else 'r'}_{post}",
                    (sx * S.WALK_X_OUT, y, S.WALK_Z + 0.58),
                    0.055,
                    1.05,
                    hazard,
                    vertices=8,
                )
            )
        for rail, height in ((0, 1.05), (1, 0.58)):
            objects.append(
                bk.add_cylinder(
                    f"{MOD_ID}_rail_{'l' if sx < 0 else 'r'}_{rail}",
                    (sx * S.WALK_X_OUT, 0.0, S.WALK_Z + height),
                    0.055,
                    2 * S.COLUMN_Y + 0.8,
                    hazard,
                    vertices=8,
                    axis="Y",
                )
            )
        # Access stair stringer down to the apron.
        objects.append(
            bk.add_box(
                f"{MOD_ID}_stair_{'l' if sx < 0 else 'r'}",
                (sx * (S.WALK_X_OUT + 0.6), -S.COLUMN_Y - 2.4, S.WALK_Z / 2.0),
                (1.1, 5.4, 0.16),
                grate,
                bevel=0.0,
                rotation=(math.atan2(S.WALK_Z, 4.6), 0.0, 0.0),
                metric_uv=(1.1, 1.1),
            )
        )

    # ---- hydraulic power pack --------------------------------------------
    objects.append(
        bk.add_box(
            f"{MOD_ID}_pack_skid",
            (S.PACK_X, S.PACK_Y, 0.35),
            (3.4, 6.2, 0.7),
            steel,
            bevel=0.05,
            metric_uv=(2.0, 2.0),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_pack_engine",
            (S.PACK_X, S.PACK_Y + 1.2, 1.75),
            (2.8, 3.4, 2.1),
            orange,
            bevel=0.08,
            metric_uv=(2.2, 2.2),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_pack_tank",
            (S.PACK_X, S.PACK_Y - 1.9, 1.55),
            0.95,
            2.2,
            black,
            vertices=18,
            axis="Y",
            metric_uv=(1.6, 1.6),
        )
    )
    objects.append(
        bk.add_box(
            f"{MOD_ID}_pack_radiator",
            (S.PACK_X + 1.45, S.PACK_Y, 1.70),
            (0.22, 2.4, 2.0),
            grate,
            bevel=0.0,
            metric_uv=(0.8, 0.8),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_pack_stack",
            (S.PACK_X + 1.9, S.PACK_Y - 1.5, S.PACK_STACK_Z / 2.0 + 0.4),
            0.24,
            S.PACK_STACK_Z - 0.4,
            black,
            vertices=12,
            metric_uv=(1.0, 1.0),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_pack_stack_cap",
            (S.PACK_X + 1.9, S.PACK_Y - 1.5, S.PACK_STACK_Z + 0.1),
            0.31,
            0.18,
            steel,
            vertices=12,
        )
    )

    # ---- beacon mast, lens and horn --------------------------------------
    mast_x, mast_y, beacon_z = S.BEACON_PIVOT
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_beacon_mast",
            (mast_x, mast_y, (S.COLUMN_TOP_Z + beacon_z) / 2.0),
            0.11,
            beacon_z - S.COLUMN_TOP_Z + 0.4,
            steel,
            vertices=10,
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_beacon_lens",
            (mast_x, mast_y, beacon_z),
            0.40,
            0.52,
            amber,
            vertices=20,
            metric_uv=(0.7, 0.7),
        )
    )
    objects.append(
        bk.add_cylinder(
            f"{MOD_ID}_beacon_cap",
            (mast_x, mast_y, beacon_z + 0.32),
            0.44,
            0.12,
            black,
            vertices=20,
        )
    )
    objects.append(
        bk.add_cone(
            f"{MOD_ID}_horn",
            (mast_x, mast_y + 1.1, S.COLUMN_TOP_Z + 0.9),
            0.46,
            0.13,
            0.9,
            steel,
            vertices=16,
            rotation=(math.pi / 2.0, 0.0, 0.0),
        )
    )

    # ---- gantry sign over the chute mouth --------------------------------
    for side in (-1, 1):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_sign_post_{'l' if side < 0 else 'r'}",
                (side * (S.RIM_HALF_X - 0.2), S.MOUTH_Y, (S.RIM_Z + S.SIGN_POST_TOP) / 2.0),
                (0.3, 0.3, S.SIGN_POST_TOP - S.RIM_Z + 1.6),
                steel,
                bevel=0.03,
                metric_uv=(1.4, 1.4),
            )
        )
    objects.append(
        sign_face_uvs(
            bk.add_box(
                f"{MOD_ID}_sign_plate",
                (0.0, S.MOUTH_Y, S.SIGN_Z),
                (S.SIGN_W, 0.14, S.SIGN_H),
                legend,
                bevel=0.0,
            )
        )
    )

    # ---- discharge conveyor ----------------------------------------------
    pan_grid, skirt_bl, skirt_br = [], [], []
    for y in BELT_STATIONS:
        z = S.belt_z(y)
        pan_grid.append([(-S.BELT_HALF_W, y, z), (0.0, y, z), (S.BELT_HALF_W, y, z)])
        skirt_bl.append([(-S.BELT_HALF_W, y, z), (-S.BELT_SKIRT_X, y, z + S.BELT_SKIRT_RISE)])
        skirt_br.append([(S.BELT_HALF_W, y, z), (S.BELT_SKIRT_X, y, z + S.BELT_SKIRT_RISE)])
    objects.append(add_surface(f"{MOD_ID}_belt_pan", pan_grid, steel, meters_per_tile=(2.2, 2.2)))
    objects.append(
        add_surface(
            f"{MOD_ID}_belt_skirt_l", skirt_bl, orange, meters_per_tile=(1.8, 1.8), face_up=True
        )
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_belt_skirt_r", skirt_br, orange, meters_per_tile=(1.8, 1.8), face_up=True
        )
    )
    # ---- conveyor plinth --------------------------------------------------
    # Round-1 review: the pan's collision quads are one-sided up-facing and
    # the ground apron ran underneath the whole conveyor, so a car could drive
    # in from the head end (1.94 m of clearance) and clip straight up through
    # the belt. The fix is to stop pretending the conveyor floats: it sits in
    # a plated trough whose faces slope at 58 deg to the apron - shallower
    # than the 62 deg embankment skirt this prop already ships - so the volume
    # under the pan is closed with no vertical collision face anywhere, and
    # the visual says the same thing the cage does. The legs and side frames
    # this replaces were visual-only anyway (the author's own note), so the
    # geometry got MORE honest, not less.
    plinth_l, plinth_r = [], []
    for y in BELT_STATIONS:
        z = S.belt_z(y)
        toe = S.belt_plinth_x(y)
        plinth_l.append([(-S.BELT_HALF_W, y, z), (-toe, y, 0.0)])
        plinth_r.append([(S.BELT_HALF_W, y, z), (toe, y, 0.0)])
    objects.append(
        add_surface(
            f"{MOD_ID}_belt_plinth_l", plinth_l, steel, meters_per_tile=(2.6, 2.6)
        )
    )
    objects.append(
        add_surface(
            f"{MOD_ID}_belt_plinth_r", plinth_r, steel, meters_per_tile=(2.6, 2.6)
        )
    )
    for name, y, toe_y in (
        ("tail", S.BELT_Y_TAIL, S.BELT_TAIL_TOE_Y),
        ("head", S.BELT_Y_HEAD, S.BELT_HEAD_TOE_Y),
    ):
        z = S.belt_z(y)
        objects.append(
            add_surface(
                f"{MOD_ID}_belt_endwall_{name}",
                [
                    [(-S.BELT_HALF_W, y, z), (0.0, y, z), (S.BELT_HALF_W, y, z)],
                    [
                        (-S.BELT_HALF_W, toe_y, 0.0),
                        (0.0, toe_y, 0.0),
                        (S.BELT_HALF_W, toe_y, 0.0),
                    ],
                ],
                steel,
                meters_per_tile=(2.6, 2.6),
                face_up=True,
            )
        )
        for side in (-1, 1):
            objects.append(
                add_triangle_patch(
                    f"{MOD_ID}_belt_endcorner_{name}_{'l' if side < 0 else 'r'}",
                    (side * S.BELT_HALF_W, y, z),
                    (side * S.belt_plinth_x(y), y, 0.0),
                    (side * S.BELT_HALF_W, toe_y, 0.0),
                    steel,
                )
            )
    # Buttress ribs on the plinth face, same idiom as the ramp embankment:
    # a 22 m plain slope reads as a blank wall.
    for rib in range(9):
        y = S.BELT_Y_TAIL + 1.2 + rib * (S.BELT_Y_HEAD - S.BELT_Y_TAIL - 2.4) / 8.0
        z = S.belt_z(y)
        run = S.belt_plinth_x(y) - S.BELT_HALF_W
        length = math.hypot(run, z)
        for side in (-1, 1):
            objects.append(
                bk.add_box(
                    f"{MOD_ID}_belt_rib_{'l' if side < 0 else 'r'}_{rib}",
                    (side * (S.BELT_HALF_W + run / 2.0), y, z / 2.0),
                    (0.50, 0.55, length),
                    steel,
                    bevel=0.04,
                    rotation=(0.0, math.atan2(side * run, -z), 0.0),
                    metric_uv=(1.6, 1.6),
                )
            )
    # Rub rail along the skirt crest: the conveyor's own side frame, now that
    # the plinth carries the load.
    belt_angle = math.atan(S.BELT_GRADE)
    belt_len = S.BELT_Y_HEAD - S.BELT_Y_TAIL
    belt_mid_y = (S.BELT_Y_TAIL + S.BELT_Y_HEAD) / 2.0
    belt_mid_z = S.belt_z(belt_mid_y)
    for side in (-1, 1):
        objects.append(
            bk.add_box(
                f"{MOD_ID}_belt_rail_{'l' if side < 0 else 'r'}",
                (
                    side * (S.BELT_SKIRT_X + 0.12),
                    belt_mid_y,
                    belt_mid_z + S.BELT_SKIRT_RISE + 0.10,
                ),
                (0.30, belt_len / math.cos(belt_angle), 0.34),
                steel,
                bevel=0.04,
                rotation=(belt_angle, 0.0, 0.0),
                metric_uv=(2.0, 2.0),
            )
        )
    for name, y in (("tail", S.BELT_Y_TAIL), ("head", S.BELT_Y_HEAD)):
        objects.append(
            bk.add_cylinder(
                f"{MOD_ID}_belt_pulley_{name}",
                (0.0, y, S.belt_z(y) - 0.42),
                0.42,
                2 * S.BELT_SKIRT_X,
                steel,
                vertices=18,
                axis="X",
                metric_uv=(1.4, 1.4),
            )
        )

    # ---- scrap pile -------------------------------------------------------
    pile_grid = []
    for y in PILE_STATIONS:
        crest, half = pile_profile(y)
        pile_grid.append(
            [
                (-half, y, 0.0),
                (-half * 0.5, y, crest * 0.8),
                (0.0, y, crest),
                (half * 0.5, y, crest * 0.8),
                (half, y, 0.0),
            ]
        )
    objects.append(add_surface(f"{MOD_ID}_scrap_pile", pile_grid, rust, meters_per_tile=(2.4, 2.4)))
    # Deterministic crushed-scrap scatter (no RNG: a fixed lattice with a
    # reproducible pseudo-jitter, so reruns are byte-stable).
    for index in range(16):
        # Golden-ratio low-discrepancy pair: deterministic, byte-stable across
        # reruns, and free of the staircase the modulo lattice produced.
        u = (0.3 + index * 0.61803398875) % 1.0
        v = (0.1 + index * 0.38196601125) % 1.0
        y = S.PILE_TOE_Y + 1.0 + v * (S.PILE_TAIL_Y - S.PILE_TOE_Y - 2.5)
        crest, half = pile_profile(y)
        x = (u - 0.5) * 2.0 * half * 0.8
        objects.append(
            bk.add_box(
                f"{MOD_ID}_scrap_{index}",
                (x, y, crest * (0.5 + 0.4 * u) + 0.25),
                (1.5 + u * 0.9, 1.1 + v * 1.0, 0.45 + v * 0.35),
                rust if index % 2 == 0 else steel,
                bevel=0.05,
                rotation=(0.18 * (u - 0.5), 0.22 * (v - 0.5), 1.7 * u),
                metric_uv=(1.6, 1.6),
            )
        )
    return objects


# ---------------------------------------------------------------------------
# Kinematic parts (TSStatics posed by the runtime). All collision-free:
# a spinning drum's *swept* envelope is what a body actually touches, and
# that envelope is static geometry, so it lives in the cage instead.
# ---------------------------------------------------------------------------
def build_parts(materials) -> dict[str, dict[str, object]]:
    steel = materials[f"{MOD_ID}_mill_steel"]
    tooth = materials[f"{MOD_ID}_tooth_steel"]
    black = materials[f"{MOD_ID}_hydraulic_black"]

    parts: dict[str, dict[str, object]] = {}

    for side, tag in ((-1, "left"), (1, "right")):
        pivot = (side * S.ROLL_AXIS_X, 0.0, S.ROLL_AXIS_Z)
        drum: list[bpy.types.Object] = [
            bk.add_cylinder(
                f"{MOD_ID}_drum_{tag}",
                pivot,
                S.ROLL_BARREL_R,
                2 * S.SLOT_HALF_Y,
                steel,
                vertices=36,
                axis="Y",
                metric_uv=(1.6, 1.6),
            ),
            bk.add_cylinder(
                f"{MOD_ID}_shaft_{tag}",
                pivot,
                0.30,
                2 * S.SLOT_HALF_Y + 3.4,
                steel,
                vertices=12,
                axis="Y",
                metric_uv=(1.2, 1.2),
            ),
        ]
        # Rotor build order matters for what a player sees:
        #   10 cutter discs, r = ROLL_CAGE_R exactly, 0.62 m thick. These ARE
        #      the collision cylinder - flush, no air behind it at all.
        #   6 hooks on each disc rim reaching ROLL_TIP_R, i.e. 0.15 m PROUD of
        #      the collision skin. When the scrub presses a car onto a shroud
        #      the body stops at the rim and the hooks are already 0.15 m
        #      inside its flank: teeth visibly biting.
        #   11 spacer rings at r = 0.90 filling the 0.38 m grooves the fixed
        #      combs run in - so the deepest air anywhere behind the skin is
        #      0.10 m, over 38% of the length.
        # Every cylinder's vertex count is a multiple of TEETH_PER_ROW so the
        # whole drum is exactly 6-fold symmetric about its own axis, which is
        # what the spin-axis proof at the end of this function checks.
        row_pitch = 2 * S.SLOT_HALF_Y / S.TOOTH_ROWS
        hook_mid_r = (S.HOOK_ROOT_R + S.HOOK_TIP_R) / 2.0
        hook_depth = S.HOOK_TIP_R - S.HOOK_ROOT_R
        for row in range(S.TOOTH_ROWS):
            y = -S.SLOT_HALF_Y + (row + 0.5) * row_pitch
            drum.append(
                bk.add_cylinder(
                    f"{MOD_ID}_disc_{tag}_{row}",
                    (pivot[0], y, pivot[2]),
                    S.CUTTER_DISC_R,
                    S.CUTTER_DISC_T,
                    tooth,
                    vertices=36,
                    axis="Y",
                    metric_uv=(1.0, 1.0),
                )
            )
            stagger = math.radians(S.TOOTH_STAGGER_DEG) * (row % 2)
            for index in range(S.TEETH_PER_ROW):
                theta = stagger + index * 2.0 * math.pi / S.TEETH_PER_ROW
                drum.append(
                    bk.add_box(
                        f"{MOD_ID}_hook_{tag}_{row}_{index}",
                        (
                            pivot[0] + hook_mid_r * math.sin(theta),
                            y,
                            pivot[2] + hook_mid_r * math.cos(theta),
                        ),
                        (S.HOOK_TANGENTIAL, S.HOOK_AXIAL, hook_depth),
                        tooth,
                        bevel=0.03,
                        rotation=(0.0, theta, 0.0),
                        metric_uv=(0.7, 0.7),
                    )
                )
        for groove in range(S.TOOTH_ROWS + 1):
            drum.append(
                bk.add_cylinder(
                    f"{MOD_ID}_spacer_{tag}_{groove}",
                    (pivot[0], -S.SLOT_HALF_Y + groove * row_pitch, pivot[2]),
                    S.ROLL_SPACER_R,
                    S.ROLL_SPACER_T,
                    steel,
                    vertices=24,
                    axis="Y",
                    metric_uv=(1.2, 1.2),
                )
            )
        parts[f"roller_{tag}"] = {"objects": drum, "pivot": pivot, "collision": False}

    # Slat pan. Slats overrun BOTH pulleys by a full pitch so the modulo wrap
    # can never expose bare pan at either end.
    belt_angle = math.atan(S.BELT_GRADE)
    slat_pivot = (0.0, 0.0, S.belt_z(0.0))
    slats: list[bpy.types.Object] = []
    count = int((S.BELT_Y_HEAD - S.BELT_Y_TAIL + 2 * S.SLAT_PITCH) / S.SLAT_PITCH) + 1
    for index in range(count):
        y = S.BELT_Y_TAIL - S.SLAT_PITCH + index * S.SLAT_PITCH
        slats.append(
            bk.add_box(
                f"{MOD_ID}_slat_{index}",
                (0.0, y, S.belt_z(y) + 0.09),
                (2 * S.BELT_HALF_W - 0.1, 0.30, 0.16),
                steel,
                bevel=0.02,
                rotation=(belt_angle, 0.0, 0.0),
                metric_uv=(1.3, 1.3),
            )
        )
    parts["belt_slats"] = {"objects": slats, "pivot": slat_pivot, "collision": False}

    # Beacon reflector: a dark vane inside the amber lens. Two-fold symmetric,
    # so its apparent direction of rotation is deliberately ambiguous - the
    # one moving part on this prop whose spin sign cannot be read wrong.
    beacon = [
        bk.add_box(
            f"{MOD_ID}_beacon_vane",
            S.BEACON_PIVOT,
            (0.62, 0.10, 0.40),
            black,
            bevel=0.02,
        ),
        bk.add_cylinder(
            f"{MOD_ID}_beacon_hub",
            S.BEACON_PIVOT,
            0.09,
            0.44,
            black,
            vertices=10,
        ),
    ]
    parts["beacon"] = {"objects": beacon, "pivot": S.BEACON_PIVOT, "collision": False}

    # Cooling fan: a disc in the authored Y-Z plane, so its axis is authored
    # X and it is posed about authored X (spec.PART_SPIN). Blade placement and
    # blade rotation are now derived from the SAME rotation: a box rotated by
    # `angle` about X sends its local +Z to (0, -sin, cos), so the offset uses
    # that vector and the blade's long axis is genuinely radial. The old build
    # placed blades on (0, cos, sin) while rotating them by `angle`, which put
    # every blade 90 deg out of its own radius as well as posing the whole
    # disc about the wrong axis.
    fan = [
        bk.add_cylinder(
            f"{MOD_ID}_fan_hub",
            S.FAN_PIVOT,
            0.20,
            0.22,
            black,
            vertices=20,
            axis="X",
        )
    ]
    for blade in range(S.FAN_BLADES):
        angle = blade * 2.0 * math.pi / S.FAN_BLADES
        fan.append(
            bk.add_box(
                f"{MOD_ID}_fan_blade_{blade}",
                (
                    S.FAN_PIVOT[0],
                    S.FAN_PIVOT[1] - 0.55 * math.sin(angle),
                    S.FAN_PIVOT[2] + 0.55 * math.cos(angle),
                ),
                (0.06, 0.30, 0.95),
                steel,
                bevel=0.01,
                rotation=(angle, 0.0, 0.0),
            )
        )
    parts["power_fan"] = {"objects": fan, "pivot": S.FAN_PIVOT, "collision": False}

    # ---- build-time proofs on the parts we just built ---------------------
    for name, build in parts.items():
        spin = S.PART_SPIN.get(name)
        if spin:
            assert_spin_symmetry(name, build["objects"], build["pivot"], spin)
    for tag in ("left", "right"):
        probe_rotor_envelope(f"roller_{tag}", parts[f"roller_{tag}"]["objects"])
    return parts


# ---------------------------------------------------------------------------
# Proof 1: the geometry of every posed part really is laid out about the axis
# the runtime rotates it around.
#
# Round-1 review found the cooling fan built in the Y-Z plane and posed about
# Y: one blade never moved and the other four swung 0.52 m out of a 0.22 m
# radiator, permanently, at 9 rad/s. A corrected literal would fix that one
# bug; this check makes the whole class impossible. spec.PART_SPIN is the
# single source for the pose axis AND for this test, so a part whose mesh and
# whose animation disagree fails the build.
# ---------------------------------------------------------------------------
def assert_spin_symmetry(name, objects, pivot, spin) -> None:
    axis = Vector(spin["axis"]).normalized()
    fold = int(spin["fold"])
    origin = Vector(pivot)
    points = []
    for obj in objects:
        matrix = obj.matrix_world
        for vertex in obj.data.vertices:
            points.append(matrix @ vertex.co - origin)

    def bucket(cloud):
        table: dict[tuple[int, int, int], list] = {}
        for point in cloud:
            key = (round(point.x * 500), round(point.y * 500), round(point.z * 500))
            table.setdefault(key, []).append(point)
        return table

    table = bucket(points)

    def maps_onto_itself(spin_axis) -> bool:
        angle = 2.0 * math.pi / fold
        for point in points:
            turned = point.copy()
            turned.rotate(Matrix.Rotation(angle, 3, spin_axis))
            key = (round(turned.x * 500), round(turned.y * 500), round(turned.z * 500))
            found = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for candidate in table.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                            if (candidate - turned).length < 3e-3:
                                found = True
                                break
                        if found:
                            break
                    if found:
                        break
                if found:
                    break
            if not found:
                return False
        return True

    if not maps_onto_itself(axis):
        raise AssertionError(
            f"{name}: geometry is not {fold}-fold symmetric about its declared "
            f"spin axis {tuple(spin['axis'])} - the runtime would animate it "
            f"about an axis its mesh was not built around"
        )
    if fold >= 3:
        # Discrimination: a 5-fold fan is symmetric about X and nothing else,
        # so a mis-declared axis cannot pass by accident. Skipped at fold 2,
        # where a box is symmetric about all three of its own axes.
        for other in (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))):
            if abs(other.dot(axis)) > 0.99:
                continue
            if maps_onto_itself(other):
                raise AssertionError(
                    f"{name}: {fold}-fold symmetry about {tuple(other)} too - "
                    f"the axis test cannot discriminate and proves nothing"
                )


# ---------------------------------------------------------------------------
# Proof 2: how much AIR is behind the roller collision skin, measured on the
# built mesh rather than asserted in a comment.
#
# Round-1 review measured the old rotor: ~40% of the collision surface had no
# visible solid until r = 0.62 (0.53 m of air) and the thumbnail showed
# daylight through the rotor. This casts rays inward at the drum from just
# outside the hook circle on a (station x azimuth) grid and reports, for every
# sample, the radius of the outermost rotor solid.
# ---------------------------------------------------------------------------
def probe_rotor_envelope(name, objects, stations: int = 41, azimuths: int = 72) -> None:
    # Hide everything that is not this drum, so a single ray per sample is
    # unambiguous - marching past the hopper flank, the combs and the bearing
    # housings would otherwise decide the answer.
    keep = set(objects)
    hidden = [
        obj
        for obj in bpy.context.scene.objects
        if obj not in keep and not obj.hide_viewport
    ]
    for obj in hidden:
        obj.hide_viewport = True
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    scene = bpy.context.scene
    axis_x = objects[0].matrix_world.translation.x
    start_r = S.ROLL_TIP_R + 0.60
    worst_air, worst_at = 0.0, None
    max_radius = 0.0
    try:
        for station in range(stations):
            span = 2 * S.SLOT_HALF_Y - 0.04
            y = -S.SLOT_HALF_Y + 0.02 + span * station / (stations - 1)
            for step in range(azimuths):
                alpha = 2.0 * math.pi * step / azimuths
                direction = Vector((-math.sin(alpha), 0.0, -math.cos(alpha)))
                origin = Vector(
                    (
                        axis_x - start_r * direction.x,
                        y,
                        S.ROLL_AXIS_Z - start_r * direction.z,
                    )
                )
                hit, location, _n, _i, _o, _m = scene.ray_cast(depsgraph, origin, direction)
                radius = (
                    math.hypot(location.x - axis_x, location.z - S.ROLL_AXIS_Z)
                    if hit
                    else 0.0
                )
                max_radius = max(max_radius, radius)
                air = S.ROLL_CAGE_R - radius
                if air > worst_air:
                    worst_air, worst_at = air, (round(y, 2), round(math.degrees(alpha)))
    finally:
        for obj in hidden:
            obj.hide_viewport = False
        bpy.context.view_layer.update()
    print(
        f"  rotor probe {name}: worst air behind the collision skin "
        f"{worst_air:.3f} m at {worst_at}, max swept radius {max_radius:.4f} m"
    )
    # 0.12 m: the groove floor is 0.10 m inside the skin by construction, so
    # this fails the moment the disc/spacer stack stops being continuous.
    assert worst_air <= 0.12, (name, worst_air, worst_at)
    # Nothing may sweep outside the hook circle the fixed hopper is built to
    # clear; 0.02 m is the corner overshoot of a straight-sided hook whose
    # OUTER FACE is tangent to that circle (sqrt(1.15^2 + 0.15^2) - 1.15).
    assert max_radius <= S.ROLL_TIP_R + 0.02, (name, max_radius)


# ---------------------------------------------------------------------------
# Physics cage
# ---------------------------------------------------------------------------
def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    metal = "metal"

    def node(suffix, position, weight=90.0):
        return cage.add_node(suffix, position, fixed=True, collision=False, weight=weight)

    def floor_quad(corners, ground_model=metal):
        """One-sided collision quad GUARANTEED to face up.

        jbeam collision triangles are one-sided and hand-derived windings are
        the single most error-prone thing in a generator like this (AGENTS.md:
        three of the centrifuge ramp's six windings were wrong), so the winding
        is COMPUTED from the stored vehicle-space positions instead of typed.
        Surfaces a car rides on get exactly ONE skin: a mirrored twin on a flat
        quad spikes the solver (proplib add_quad_both docstring).
        """

        positions = [cage.nodes[cage.node_index[i]]["position"] for i in corners]
        pa, pb, pc = positions[0], positions[1], positions[2]
        normal_z = (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0])
        if normal_z < 0.0:
            corners = list(reversed(corners))
        cage.add_quad(corners, ground_model=ground_model)

    def strip(columns_a, columns_b, ground_model=metal, floor=False):
        """Collision quads between two node columns of equal length.

        ``floor`` picks the computed-up single skin above; everything else gets
        proplib's two-sided add_quad_both, which is the right tool for walls,
        flanks and the curved roller shrouds (no winding to get wrong, and a
        body cannot pop through a hopper wall from the far side).
        """

        for k in range(len(columns_a) - 1):
            quad = [columns_a[k], columns_a[k + 1], columns_b[k + 1], columns_b[k]]
            if floor:
                floor_quad(quad, ground_model)
            else:
                cage.add_quad_both(quad, ground_model=ground_model)

    def beam_row(ids):
        for first, second in pairwise(ids):
            cage.add_beam(first, second)

    # ---- ground apron -----------------------------------------------------
    apron: dict[tuple[int, int], str] = {}
    for i, x in enumerate(APRON_X):
        for j, y in enumerate(APRON_Y):
            apron[(i, j)] = node(f"apron_{i}_{j}", (x, y, 0.0), weight=140.0)
    for i in range(len(APRON_X)):
        beam_row([apron[(i, j)] for j in range(len(APRON_Y))])
    for j in range(len(APRON_Y)):
        beam_row([apron[(i, j)] for i in range(len(APRON_X))])
    for i in range(len(APRON_X) - 1):
        for j in range(len(APRON_Y) - 1):
            cage.add_beam(apron[(i, j)], apron[(i + 1, j + 1)])
            cage.add_beam(apron[(i + 1, j)], apron[(i, j + 1)])
            floor_quad(
                [apron[(i, j)], apron[(i + 1, j)], apron[(i + 1, j + 1)], apron[(i, j + 1)]],
                "asphalt",
            )

    # ---- haul ramp --------------------------------------------------------
    stations = ramp_stations()
    order = ("sl", "kl", "dl", "dc", "dr", "kr", "sr")
    ramp: dict[str, list[str]] = {key: [] for key in order}
    for index, y in enumerate(stations):
        z = S.ramp_deck_z(y)
        crest = z + S.KERB_RISE
        outer = S.ramp_skirt_x(y)
        ramp["sl"].append(node(f"ramp_sl_{index}", (-outer, y, 0.0)))
        ramp["kl"].append(node(f"ramp_kl_{index}", (-S.RAMP_HALF_W - S.KERB_RUN, y, crest)))
        ramp["dl"].append(node(f"ramp_dl_{index}", (-S.RAMP_HALF_W, y, z)))
        ramp["dc"].append(node(f"ramp_dc_{index}", (0.0, y, z)))
        ramp["dr"].append(node(f"ramp_dr_{index}", (S.RAMP_HALF_W, y, z)))
        ramp["kr"].append(node(f"ramp_kr_{index}", (S.RAMP_HALF_W + S.KERB_RUN, y, crest)))
        ramp["sr"].append(node(f"ramp_sr_{index}", (outer, y, 0.0)))
    for key in order:
        beam_row(ramp[key])
    for left, right in pairwise(order):
        for index in range(len(stations)):
            cage.add_beam(ramp[left][index], ramp[right][index])
        for index in range(len(stations) - 1):
            cage.add_beam(ramp[left][index], ramp[right][index + 1])
            cage.add_beam(ramp[right][index], ramp[left][index + 1])
    strip(ramp["dl"], ramp["dc"], ground_model="asphalt", floor=True)
    strip(ramp["dc"], ramp["dr"], ground_model="asphalt", floor=True)
    strip(ramp["kl"], ramp["dl"])
    strip(ramp["dr"], ramp["kr"])
    strip(ramp["sl"], ramp["kl"], ground_model="dirt")
    strip(ramp["kr"], ramp["sr"], ground_model="dirt")
    # Tie the ramp head into the apron so the graph is one component and a car
    # cannot find bare ground between the embankment and the pad.
    cage.add_beam(ramp["sl"][-1], apron[(0, 0)])
    cage.add_beam(ramp["sr"][-1], apron[(len(APRON_X) - 1, 0)])
    cage.add_beam(ramp["dl"][-1], apron[(1, 0)])
    cage.add_beam(ramp["dr"][-1], apron[(3, 0)])
    # Embankment head wall. Its TOP EDGE is the deck edge line, never the kerb
    # crest: a wall whose top sits above the deck plane is a wall standing in
    # the driving lane, and the lane crosses y = MOUTH_Y at deck height.
    cage.add_quad_both(
        [ramp["sl"][-1], ramp["sr"][-1], ramp["dr"][-1], ramp["dl"][-1]],
        ground_model="dirt",
    )

    # ---- chute ------------------------------------------------------------
    # Station 0 sits at y = MOUTH_Y with the ramp's own half width, height and
    # grade, so the ramp deck edge nodes ARE the chute floor edge nodes. They
    # are ALIASED, never rebuilt (coincident nodes collapse the flexbody triad
    # that skins every vertex bound to them - AGENTS.md 2026-08-08).
    chute: dict[str, list[str]] = {key: [] for key in ("fl", "el", "ct", "er", "fr")}
    for index, y in enumerate(CHUTE_STATIONS):
        z = S.chute_floor_z(y)
        half = S.chute_half_width(y)
        chute["fl"].append(node(f"chute_fl_{index}", (-S.RIM_HALF_X, y, S.RIM_Z)))
        chute["fr"].append(node(f"chute_fr_{index}", (S.RIM_HALF_X, y, S.RIM_Z)))
        if index == 0:
            chute["el"].append(ramp["dl"][-1])
            chute["ct"].append(ramp["dc"][-1])
            chute["er"].append(ramp["dr"][-1])
        else:
            chute["el"].append(node(f"chute_el_{index}", (-half, y, z)))
            chute["ct"].append(node(f"chute_ct_{index}", (0.0, y, z)))
            chute["er"].append(node(f"chute_er_{index}", (half, y, z)))
    chute_order = ("fl", "el", "ct", "er", "fr")
    for key in chute_order:
        beam_row(chute[key])
    for left, right in pairwise(chute_order):
        for index in range(len(CHUTE_STATIONS)):
            cage.add_beam(chute[left][index], chute[right][index])
        for index in range(len(CHUTE_STATIONS) - 1):
            cage.add_beam(chute[left][index], chute[right][index + 1])
            cage.add_beam(chute[right][index], chute[left][index + 1])
    strip(chute["el"], chute["ct"], floor=True)
    strip(chute["ct"], chute["er"], floor=True)
    strip(chute["fl"], chute["el"])
    strip(chute["er"], chute["fr"])
    cage.add_beam(ramp["kl"][-1], chute["fl"][0])
    cage.add_beam(ramp["kr"][-1], chute["fr"][0])
    for index in (1, 2, 3):
        cage.add_beam(chute["ct"][index], apron[(2, 0)])

    # ---- rotor datum line -------------------------------------------------
    # Every FIXED surface that borders a drum - chute lip, hopper flank base,
    # hopper back plate - lands on the SWEPT hook circle (TIP_TOP_Z), because
    # that is the cylinder the hooks actually occupy. Index 0 is the chute
    # floor's own edge node, aliased rather than rebuilt (a second node 0 mm
    # away is the coincident-triad flexbody trap, AGENTS.md 2026-08-08).
    lipline: dict[int, list[str]] = {}
    for side in (-1, 1):
        tag = "l" if side < 0 else "r"
        column = []
        for index, y in enumerate(SLOT_STATIONS):
            if index == 0:
                column.append(chute["el"][-1] if side < 0 else chute["er"][-1])
            else:
                column.append(
                    node(f"lip_{tag}_{index}", (side * S.ROLL_AXIS_X, y, S.TIP_TOP_Z))
                )
        lipline[side] = column
        beam_row(column)

    # ---- roller collision cylinders --------------------------------------
    # The cage models each drum's CUTTER-DISC cylinder (ROLL_CAGE_R): the
    # surface a body actually rests on, continuous visible steel behind every
    # square metre of it, and static - so there is no moving collision
    # anywhere in this machine. The hooks sweep 0.15 m outside it with no
    # collision of their own, which is the safe direction to err in.
    rollers: dict[int, list[list[str]]] = {}
    for side in (-1, 1):
        columns: list[list[str]] = []
        for a in range(ARC_STEPS):
            alpha = math.pi * a / (ARC_STEPS - 1)
            column: list[str] = []
            for index, y in enumerate(SLOT_STATIONS):
                x, z = roller_arc(side, alpha)
                tag = "l" if side < 0 else "r"
                column.append(node(f"roll_{tag}_{a}_{index}", (x, y, z)))
            columns.append(column)
        rollers[side] = columns
        for column in columns:
            beam_row(column)
        for first, second in pairwise(columns):
            for index in range(len(SLOT_STATIONS)):
                cage.add_beam(first[index], second[index])
            for index in range(len(SLOT_STATIONS) - 1):
                cage.add_beam(first[index], second[index + 1])
                cage.add_beam(second[index], first[index + 1])
            strip(first, second)
        # Tie the crown row to the datum line 0.15 m above it. Deliberately
        # beams only, no collision quad: the 0.15 m between the chute lip and
        # the disc crown is the step the car noses over as the teeth take it,
        # and skinning it would put a vertical collision face along both edges
        # of the throat. There is nothing to fall into - the drum surface is
        # directly beneath, curving away.
        for index in range(len(SLOT_STATIONS)):
            cage.add_beam(rollers[side][0][index], lipline[side][index])

    # ---- hopper flanks over the slot --------------------------------------
    rim: dict[int, list[str]] = {}
    for side in (-1, 1):
        tag = "l" if side < 0 else "r"
        column: list[str] = []
        for index, y in enumerate(SLOT_STATIONS):
            if index == 0:
                column.append(chute["fl"][-1] if side < 0 else chute["fr"][-1])
            else:
                column.append(node(f"rim_{tag}_{index}", (side * S.RIM_HALF_X, y, S.RIM_Z)))
        rim[side] = column
        beam_row(column)
        base = lipline[side]
        for index in range(len(SLOT_STATIONS)):
            cage.add_beam(base[index], column[index])
        if side < 0:
            strip(column, base)
        else:
            strip(base, column)

    # ---- hopper back plate + rear corner fillers --------------------------
    # Row 0 lies exactly on the rotor datum line at y = SLOT_HALF_Y, so its
    # outer nodes ARE the lipline nodes: aliased, never rebuilt.
    back_rows: list[list[str]] = []
    for step, t in enumerate((0.0, 0.5, 1.0)):
        y = S.SLOT_HALF_Y + (S.BACK_RIM_Y - S.SLOT_HALF_Y) * t
        z = S.BACK_BASE_Z + (S.RIM_Z - S.BACK_BASE_Z) * t
        half = S.ROLL_AXIS_X + (S.RIM_HALF_X - S.ROLL_AXIS_X) * t
        centre = node(f"back_{step}_1", (0.0, y, z))
        if step == 0:
            row = [lipline[-1][-1], centre, lipline[1][-1]]
        else:
            row = [
                node(f"back_{step}_0", (-half, y, z)),
                centre,
                node(f"back_{step}_2", (half, y, z)),
            ]
        back_rows.append(row)
        beam_row(row)
    for first, second in pairwise(back_rows):
        for k in range(3):
            cage.add_beam(first[k], second[k])
        cage.add_quad_both([first[0], first[1], second[1], second[0]])
        cage.add_quad_both([first[1], first[2], second[2], second[1]])
    for side in (-1, 1):
        outer = 0 if side < 0 else 2
        cage.add_beam(back_rows[-1][outer], rim[side][-1])
        # Corner filler: the triangle between the last flank section, the rim
        # and the back plate's outer edge. Without it each rear corner of the
        # hopper is an open slot. Emitted both ways round (two distinct node
        # triples) because jbeam collision triangles are one-sided.
        cage.add_triangle(
            lipline[side][-1],
            rim[side][-1],
            back_rows[-1][outer],
            ground_model=metal,
        )
        cage.add_triangle(
            back_rows[-1][outer],
            rim[side][-1],
            lipline[side][-1],
            ground_model=metal,
        )

    # ---- discharge conveyor ----------------------------------------------
    belt: dict[str, list[str]] = {
        key: [] for key in ("gl", "sl", "pl", "pc", "pr", "sr", "gr")
    }
    for index, y in enumerate(BELT_STATIONS):
        z = S.belt_z(y)
        top = z + S.BELT_SKIRT_RISE
        toe = S.belt_plinth_x(y)
        belt["gl"].append(node(f"belt_gl_{index}", (-toe, y, 0.0)))
        belt["sl"].append(node(f"belt_sl_{index}", (-S.BELT_SKIRT_X, y, top)))
        belt["pl"].append(node(f"belt_pl_{index}", (-S.BELT_HALF_W, y, z)))
        belt["pc"].append(node(f"belt_pc_{index}", (0.0, y, z), weight=120.0))
        belt["pr"].append(node(f"belt_pr_{index}", (S.BELT_HALF_W, y, z)))
        belt["sr"].append(node(f"belt_sr_{index}", (S.BELT_SKIRT_X, y, top)))
        belt["gr"].append(node(f"belt_gr_{index}", (toe, y, 0.0)))
    belt_order = ("sl", "pl", "pc", "pr", "sr")
    for key in ("gl", "sl", "pl", "pc", "pr", "sr", "gr"):
        beam_row(belt[key])
    for left, right in pairwise(belt_order):
        for index in range(len(BELT_STATIONS)):
            cage.add_beam(belt[left][index], belt[right][index])
        for index in range(len(BELT_STATIONS) - 1):
            cage.add_beam(belt[left][index], belt[right][index + 1])
            cage.add_beam(belt[right][index], belt[left][index + 1])
    strip(belt["pl"], belt["pc"], floor=True)
    strip(belt["pc"], belt["pr"], floor=True)
    strip(belt["sl"], belt["pl"])
    strip(belt["pr"], belt["sr"])
    # Plinth faces. The pan quads are one-sided up-facing (a mirrored twin on a
    # flat quad spikes the solver), so without these the whole 22 m under-belt
    # volume was drivable and a car could clip up through the conveyor from
    # below - round-1 review. 58 deg faces, no vertical collision anywhere.
    for index in range(len(BELT_STATIONS)):
        cage.add_beam(belt["pl"][index], belt["gl"][index])
        cage.add_beam(belt["pr"][index], belt["gr"][index])
    strip(belt["pl"], belt["gl"], ground_model="dirt")
    strip(belt["gr"], belt["pr"], ground_model="dirt")
    # Sloped end caps, and the two corner fillers each one needs where it
    # meets the side face. Emitted both ways round: jbeam triangles are
    # one-sided and these are the faces a car reaches from open ground.
    for tag, index, toe_y in (
        ("tail", 0, S.BELT_TAIL_TOE_Y),
        ("head", len(BELT_STATIONS) - 1, S.BELT_HEAD_TOE_Y),
    ):
        toes = [
            node(f"belt_toe_{tag}_{k}", (x, toe_y, 0.0))
            for k, x in enumerate((-S.BELT_HALF_W, 0.0, S.BELT_HALF_W))
        ]
        beam_row(toes)
        pan = [belt["pl"][index], belt["pc"][index], belt["pr"][index]]
        for k in range(3):
            cage.add_beam(pan[k], toes[k])
        cage.add_quad_both([pan[0], pan[1], toes[1], toes[0]], ground_model="dirt")
        cage.add_quad_both([pan[1], pan[2], toes[2], toes[1]], ground_model="dirt")
        for side, corner, ground in ((-1, 0, "gl"), (1, 2, "gr")):
            cage.add_beam(toes[corner], belt[ground][index])
            cage.add_triangle(
                pan[corner], belt[ground][index], toes[corner], ground_model="dirt"
            )
            cage.add_triangle(
                toes[corner], belt[ground][index], pan[corner], ground_model="dirt"
            )
    for index, y in enumerate(BELT_STATIONS):
        nearest = min(range(len(APRON_Y)), key=lambda j: abs(APRON_Y[j] - y))
        cage.add_beam(belt["pc"][index], apron[(2, nearest)])
    for side, key in ((-1, "gl"), (1, "gr")):
        for index in range(len(BELT_STATIONS)):
            column = 0 if side < 0 else len(APRON_X) - 1
            nearest = min(range(len(APRON_Y)), key=lambda j: abs(APRON_Y[j] - BELT_STATIONS[index]))
            cage.add_beam(belt[key][index], apron[(column, nearest)])

    # ---- scrap pile -------------------------------------------------------
    pile_rows: list[list[str]] = []
    pile_ys = PILE_STATIONS
    for index, y in enumerate(pile_ys):
        crest, half = pile_profile(y)
        row = [
            node(f"pile_{index}_0", (-half, y, 0.0)),
            node(f"pile_{index}_1", (0.0, y, crest)),
            node(f"pile_{index}_2", (half, y, 0.0)),
        ]
        pile_rows.append(row)
        beam_row(row)
    for first, second in pairwise(pile_rows):
        for k in range(3):
            cage.add_beam(first[k], second[k])
        cage.add_quad_both([first[0], first[1], second[1], second[0]], ground_model="dirt")
        cage.add_quad_both([first[1], first[2], second[2], second[1]], ground_model="dirt")
    for k in range(3):
        cage.add_beam(pile_rows[0][k], belt["pc"][-1])
    cage.add_beam(pile_rows[0][0], apron[(0, len(APRON_Y) - 1)])
    cage.add_beam(pile_rows[0][2], apron[(len(APRON_X) - 1, len(APRON_Y) - 1)])

    # ---- frame columns ----------------------------------------------------
    column_lattices = {}
    for sx in (-1, 1):
        for sy in (-1, 1):
            tag = f"{'l' if sx < 0 else 'r'}{'f' if sy < 0 else 'b'}"
            lattice = cage.add_box_lattice(
                f"col_{tag}",
                (sx * S.COLUMN_X - S.COLUMN_HALF, sy * S.COLUMN_Y - S.COLUMN_HALF, 0.0),
                (sx * S.COLUMN_X + S.COLUMN_HALF, sy * S.COLUMN_Y + S.COLUMN_HALF, S.COLUMN_TOP_Z),
                subdivisions=(1, 1, 2),
                fixed=True,
                collision=False,
                weight=110.0,
                collision_faces=("north", "south", "east", "west"),
            )
            column_lattices[(sx, sy)] = lattice
            corner = (0 if sx < 0 else len(APRON_X) - 1, 1 if sy < 0 else 3)
            for ix in (0, 1):
                for iy in (0, 1):
                    cage.add_beam(lattice[(ix, iy, 0)], apron[corner])
    # Tie the columns to the hopper rim so the machine is one stiff frame.
    for sx in (-1, 1):
        for sy, index in ((-1, 0), (1, len(SLOT_STATIONS) - 1)):
            cage.add_beam(column_lattices[(sx, sy)][(0, 0, 2)], rim[sx][index])
            cage.add_beam(column_lattices[(sx, sy)][(1, 1, 2)], rim[sx][index])
    cage.add_beam(column_lattices[(-1, 1)][(1, 1, 2)], back_rows[-1][0])
    cage.add_beam(column_lattices[(1, 1)][(0, 1, 2)], back_rows[-1][2])

    # ---- service walkway --------------------------------------------------
    for sx in (-1, 1):
        tag = "l" if sx < 0 else "r"
        inner, outer = [], []
        for index, y in enumerate((-S.COLUMN_Y, 0.0, S.COLUMN_Y)):
            inner.append(
                node(f"walk_{tag}_in_{index}", (sx * S.WALK_X_IN, y, S.WALK_Z), weight=70.0)
            )
            outer.append(
                node(f"walk_{tag}_out_{index}", (sx * S.WALK_X_OUT, y, S.WALK_Z), weight=70.0)
            )
        beam_row(inner)
        beam_row(outer)
        for index in range(3):
            cage.add_beam(inner[index], outer[index])
        for index in range(2):
            cage.add_beam(inner[index], outer[index + 1])
            cage.add_beam(outer[index], inner[index + 1])
        if sx < 0:
            strip(outer, inner)
        else:
            strip(inner, outer)
        for sy, index in ((-1, 0), (1, 2)):
            cage.add_beam(inner[index], column_lattices[(sx, sy)][(0, 0, 1)])
            cage.add_beam(outer[index], column_lattices[(sx, sy)][(1, 1, 1)])
        cage.add_beam(inner[1], column_lattices[(sx, -1)][(0, 1, 1)])

    # ---- reference frame, spawn envelope, ground datum --------------------
    cage.set_refnodes_existing(
        ref=apron[(2, 2)],  # authored (0, 0, 0)
        back=apron[(2, 1)],  # authored (0, -6.5, 0): smaller y = vehicle +Y
        left=apron[(0, 2)],  # authored -x
        up=belt["pc"][2],  # authored (0, 0, belt_z(0)): straight above ref
    )
    cage.set_spawn_envelope(
        [
            ramp["sl"][0],
            ramp["sr"][0],
            apron[(0, len(APRON_Y) - 1)],
            apron[(len(APRON_X) - 1, len(APRON_Y) - 1)],
            chute["fl"][0],
            chute["fr"][0],
            back_rows[-1][0],
            back_rows[-1][2],
        ]
    )
    cage.auto_base_nodes()

    # ---- build-time asserts ----------------------------------------------
    positions = {n["id"]: n["source_world_position"] for n in cage.nodes}
    ids = list(positions)
    for i in range(len(ids)):
        ax, ay, az = positions[ids[i]]
        for j in range(i + 1, len(ids)):
            bx, by, bz = positions[ids[j]]
            if abs(ax - bx) < 0.01 and abs(ay - by) < 0.01 and abs(az - bz) < 0.01:
                raise AssertionError(
                    f"coincident cage nodes (flexbody skinning trap): {ids[i]} / {ids[j]}"
                )
    # The chute lip must land exactly on the SWEPT hook circle's crown, and
    # the collision crown must sit exactly one hook length below it.
    lip = positions[chute["er"][-1]]
    assert abs(lip[0] - S.ROLL_AXIS_X) < 1e-9, lip
    assert abs(lip[2] - S.TIP_TOP_Z) < 1e-9, lip
    crown = roller_arc(1, 0.0)
    assert abs(crown[0] - S.ROLL_AXIS_X) < 1e-9, crown
    assert abs((S.TIP_TOP_Z - crown[1]) - (S.ROLL_TIP_R - S.ROLL_CAGE_R)) < 1e-9, crown

    # ---- the drive-in gate -------------------------------------------------
    # The single path every player takes, checked in ONE signed convention on
    # the faceted surface the tyres actually touch.
    #
    # The assert this replaces compared a +y forward difference on the ramp
    # against a -y difference on the chute and demanded they be EQUAL - which
    # certifies a sign flip, i.e. certifies exactly the crest it was meant to
    # forbid. Round-1 review measured the shipped result: +0.2000 at y=-14.20
    # and -0.2043 at y=-13.80, a 22.6 deg breakover ridge with 0.36 m of chord
    # protrusion under a 3.60 m wheelbase.
    eps = 0.02
    grade_in = (S.ramp_deck_z(S.MOUTH_Y) - S.ramp_deck_z(S.MOUTH_Y - eps)) / eps
    grade_out = (S.chute_floor_z(S.MOUTH_Y + eps) - S.chute_floor_z(S.MOUTH_Y)) / eps
    assert grade_in < 0.0 and grade_out < 0.0, (grade_in, grade_out)
    assert abs(grade_in - grade_out) < 5e-3, (grade_in, grade_out)
    lane = lane_polyline()
    steepest = max(abs(S.lane_grade(y)) for y, _ in lane)
    assert steepest <= S.CHUTE_GRADE_LIP + 1e-3, steepest
    worst_overall = 0.0
    for wheelbase in (2.30, 2.70, 3.20, S.CAR_WHEELBASE_MAX):
        protrusion, where = worst_chord_protrusion(lane, wheelbase)
        print(
            f"  drive-in gate: wheelbase {wheelbase:.2f} m -> chord protrusion "
            f"{protrusion:.4f} m at y = {where:.2f}"
        )
        worst_overall = max(worst_overall, protrusion)
        # 0.10 m: two thirds of a compact's 0.15 m belly clearance, and half a
        # typical 0.20 m. Anything above this is a high-centre risk on the one
        # path the player must drive.
        assert protrusion < 0.10, (wheelbase, protrusion, where)
    print(f"  drive-in gate: worst chord protrusion {worst_overall:.4f} m (limit 0.10)")

    # The nip must clear a reference car by a real margin on both sides.
    assert 2 * S.NIP_HALF - S.CAR_WIDTH > 0.8, 2 * S.NIP_HALF
    # The pan must be wider than the span the drums drop material through.
    assert S.BELT_HALF_W > S.ROLL_AXIS_X, (S.BELT_HALF_W, S.ROLL_AXIS_X)
    # The pan must span the whole slot: nothing may fall onto bare apron.
    assert S.BELT_Y_TAIL < -S.SLOT_HALF_Y and S.BELT_Y_HEAD > S.SLOT_HALF_Y
    # The conveyor plinth must reach the apron on both sides at every station,
    # or the under-belt volume is drivable again.
    for y in BELT_STATIONS:
        assert S.belt_plinth_x(y) > S.BELT_HALF_W + 0.4, y
    # The scrap pile must start clear of the conveyor's head toe.
    assert S.PILE_TOE_Y > S.BELT_HEAD_TOE_Y + 0.5, (S.PILE_TOE_Y, S.BELT_HEAD_TOE_Y)
    return cage


# ---------------------------------------------------------------------------
# Proof 3: the runtime cannot read a tunable that does not exist, and cannot
# ship one nothing reads.
#
# The centrifuge froze mid-eject on a nil BEHAVIOR key; round-1 review found
# two keys shipped into B that no Lua line touches. Both directions are a
# build failure here, so neither can happen again silently.
# ---------------------------------------------------------------------------
def assert_tunables_match() -> None:
    import re

    referenced = set(re.findall(r"\bB\.([A-Za-z_][A-Za-z0-9_]*)", spec.LUA_BEHAVIOR))
    declared = set(spec.BEHAVIOR)
    missing = sorted(referenced - declared)
    orphan = sorted(declared - referenced - set(spec.FRAMEWORK_TUNABLES))
    if missing:
        raise AssertionError(f"LUA_BEHAVIOR reads tunables that do not exist: {missing}")
    if orphan:
        raise AssertionError(f"BEHAVIOR ships tunables no Lua line reads: {orphan}")
    # The pose axes the runtime uses and the axes the geometry proof uses must
    # be the same three vectors, not two copies that can drift.
    for key, part in (
        ("spin_axis_roller", "roller_left"),
        ("spin_axis_fan", "power_fan"),
        ("spin_axis_beacon", "beacon"),
    ):
        assert tuple(spec.BEHAVIOR[key]) == tuple(spec.PART_SPIN[part]["axis"]), key
    print(f"  tunable gate: {len(referenced)} keys referenced, 0 missing, 0 orphaned")


def main() -> None:
    assert_tunables_match()
    bk.reset_scene()
    materials = build_materials()
    visual_objects = build_visual(materials)
    part_builds = build_parts(materials)

    parts = []
    for name, build in sorted(part_builds.items()):
        dae_path = VEHICLE_DIR / f"{MOD_ID}_{name}.dae"
        info = bk.export_part_shape(MOD_ID, name, dae_path, build["objects"], build["pivot"])
        info["path"] = f"vehicles/{MOD_ID}/{MOD_ID}_{name}.dae"
        info["collision"] = bool(build.get("collision", False))
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
        # Pulled back and raised after the crest curve lengthened the ramp:
        # the embankment skirt is 10 m wide and 9 m tall at the apex and it
        # ate the old camera's foreground. This station clears it and keeps
        # the whole machine in frame - haul ramp, hopper, rotors, walkway,
        # discharge conveyor and scrap pile.
        camera_location=(30.0, -15.5, 16.5),
        look_at=(-0.5, 2.5, 4.8),
    )
    structure = cage.structure()
    print(
        f"JUNK_CHUTE_GRINDER generator complete: {len(parts)} parts, "
        f"{len(structure['nodes'])} nodes, {len(structure['beams'])} beams, "
        f"{len(structure['triangles'])} triangles"
    )


if __name__ == "__main__":
    main()
