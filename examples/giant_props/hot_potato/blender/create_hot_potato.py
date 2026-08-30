"""Deterministic Blender generator for Hot Potato.

Run with the validated Blender 4.5.4:

    & $blender454 --factory-startup --background \
        --python examples/giant_props/hot_potato/blender/create_hot_potato.py
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(PACK_ROOT))
sys.path.insert(0, str(EXAMPLE_ROOT))

import bpy  # noqa: E402
import spec  # noqa: E402
from mathutils import Vector  # noqa: E402
from proplib import blender_kit as bk  # noqa: E402

MOD_ID = spec.MOD_ID
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_DIR = MOD_ROOT / "vehicles" / MOD_ID
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"

L = spec.ARCH_HALF_SPAN
H = spec.ARCH_HEIGHT
C = spec.ARCH_C
HOME = spec.POTATO_HOME

# --------------------------------------------------------------------------
# The Gateway Arch
#
# The real thing is a WEIGHTED catenary with an equilateral-triangle cross
# section tapering from 54 ft at the base to 17 ft at the top - the taper and
# the triangle are what make it read as the Gateway Arch rather than as a
# croquet hoop. Its published centroid curve is
#     y = 693.8597 - 68.7672 * cosh(0.0100333 x)   (feet, |x| <= 299.2239)
# which is the normalised form below with C = 0.0100333 * 299.2239 = 3.0023
# and a height-to-half-span ratio of 2.089. Both live in spec.py so the cage
# and the visual are sampled from one curve.
# --------------------------------------------------------------------------


def arch_height(x: float) -> float:
    return H * (math.cosh(C) - math.cosh(C * x / L)) / (math.cosh(C) - 1.0)


def arch_side(z: float) -> float:
    """Triangle side length at height z: linear taper, base to apex."""

    t = max(0.0, min(1.0, 1.0 - z / H))
    return spec.ARCH_TOP_SIDE + (spec.ARCH_BASE_SIDE - spec.ARCH_TOP_SIDE) * t


def arch_stations() -> list[dict]:
    """Stations spaced by ARC LENGTH, each with a tangent and outward normal.

    Equal steps in x bunch stations near the apex, where the curve is flat,
    and stretch them down the legs where it is steep - backwards for both the
    mesh and the cage. Resampling on arc length keeps the segments even all
    the way round.
    """

    reach = L * spec.ARCH_FOOT_OVERRUN
    fine = 2000
    points = []
    for index in range(fine + 1):
        x = -reach + 2.0 * reach * index / fine
        points.append(Vector((x, 0.0, arch_height(x))))
    cumulative = [0.0]
    for index in range(1, len(points)):
        cumulative.append(cumulative[-1] + (points[index] - points[index - 1]).length)
    total = cumulative[-1]

    stations = []
    count = spec.ARCH_STATIONS
    cursor = 0
    for index in range(count):
        target = total * index / (count - 1)
        while cursor < len(cumulative) - 2 and cumulative[cursor + 1] < target:
            cursor += 1
        span = cumulative[cursor + 1] - cumulative[cursor]
        blend = 0.0 if span <= 0 else (target - cumulative[cursor]) / span
        position = points[cursor].lerp(points[cursor + 1], blend)
        tangent = (points[min(cursor + 2, fine)] - points[max(cursor - 1, 0)]).normalized()
        # Outward normal in the arch plane: +Z at the apex and +X at the
        # right foot. (-tz, 0, tx) satisfies both.
        normal = Vector((-tangent.z, 0.0, tangent.x)).normalized()
        stations.append({
            "p": position,
            "t": tangent,
            "n": normal,
            "s": target,
            "side": arch_side(position.z),
        })

    # Sit the arch's lowest CORNER exactly on z = 0. BeamNG places a prop by
    # base origin from its ref node, so the ref (the pad centre, z = 0) has to
    # be the lowest node in the cage - and with the feet overrunning past the
    # theoretical foot, the leg corners were dipping 0.5 m below it. Left
    # alone the whole monument would spawn half a metre in the air.
    lowest = min(
        corner.z for station in stations for corner in arch_corners(station)
    )
    if lowest < 0.0:
        for station in stations:
            station["p"] = station["p"] + Vector((0.0, 0.0, -lowest))
    return stations


def arch_corners(station: dict) -> list[Vector]:
    """The three cross-section corners: one vertex outward, flat face in."""

    side = station["side"]
    circum = side / math.sqrt(3.0)
    inradius = side / (2.0 * math.sqrt(3.0))
    position, normal = station["p"], station["n"]
    binormal = Vector((0.0, 1.0, 0.0))
    return [
        position + normal * circum,
        position - normal * inradius + binormal * (side * 0.5),
        position - normal * inradius - binormal * (side * 0.5),
    ]


def build_arch(material) -> bpy.types.Object:
    stations = arch_stations()
    rings = [arch_corners(station) for station in stations]

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    uvs: list[tuple[float, float]] = []
    tile = spec.ARCH_UV_TILE

    # Three separate strips with their own vertices: the arch's three ridges
    # are crisp on the real structure, and duplicating along them buys hard
    # edges for free instead of fighting the auto-smooth angle.
    for corner in range(3):
        nxt = (corner + 1) % 3
        base = len(vertices)
        for index, station in enumerate(stations):
            ring = rings[index]
            vertices.append(tuple(ring[corner]))
            vertices.append(tuple(ring[nxt]))
            # U centred on the face midline, so the stainless panel columns
            # sit symmetric about it the way the prototype's do; V is arc
            # length, so one tile is exactly four 12 ft panel courses at
            # quarter scale (ARCH_UV_TILE = 3.6576).
            half = station["side"] * 0.5 / tile
            uvs.append((-half, station["s"] / tile))
            uvs.append((half, station["s"] / tile))
        for index in range(len(stations) - 1):
            a = base + index * 2
            quad = (a, a + 1, a + 3, a + 2)
            # Wind outward by construction, comparing the face normal against
            # the direction from the section centre to the face centre.
            # Deriving windings by hand is exactly how this pack shipped an
            # invisible ramp and an invisible door leaf.
            p0 = Vector(vertices[quad[0]])
            p1 = Vector(vertices[quad[1]])
            p2 = Vector(vertices[quad[2]])
            centroid = (p0 + p1 + p2 + Vector(vertices[quad[3]])) / 4.0
            middle = (stations[index]["p"] + stations[index + 1]["p"]) / 2.0
            normal = (p1 - p0).cross(p2 - p0)
            faces.append(quad if normal.dot(centroid - middle) > 0 else tuple(reversed(quad)))

    mesh = bpy.data.meshes.new(f"{MOD_ID}_arch_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]
    obj = bpy.data.objects.new(f"{MOD_ID}_arch", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, material)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(40.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


# --------------------------------------------------------------------------
# The potato
# --------------------------------------------------------------------------

# The frequency band is the whole thing. Each entry displaces by
# sin(dot(direction, axis) * pi + phase), so |axis| IS the number of half
# cycles across the sphere - and the first cut used |axis| up to 3.4 for the
# lumps and 11 for the crinkle, which is not a potato, it is a rock: the
# silhouette came out jagged and flat-topped, closer to a pitta than a tuber.
_SHAPE_RNG = random.Random(20260814)  # noqa: S311 - shape authoring, not crypto
LUMPS = [
    (
        Vector((
            _SHAPE_RNG.uniform(-1.0, 1.0),
            _SHAPE_RNG.uniform(-1.0, 1.0),
            _SHAPE_RNG.uniform(-1.0, 1.0),
        )).normalized() * _SHAPE_RNG.uniform(0.55, 1.45),
        _SHAPE_RNG.uniform(0.0, math.tau),
        _SHAPE_RNG.uniform(0.030, 0.070),
    )
    for _ in range(6)
]
CRINKLE = [
    (
        Vector((
            _SHAPE_RNG.uniform(-1.0, 1.0),
            _SHAPE_RNG.uniform(-1.0, 1.0),
            _SHAPE_RNG.uniform(-1.0, 1.0),
        )).normalized() * _SHAPE_RNG.uniform(1.9, 3.2),
        _SHAPE_RNG.uniform(0.0, math.tau),
        _SHAPE_RNG.uniform(0.008, 0.017),
    )
    for _ in range(8)
]
EYE_COUNT = 11
EYE_DEPTH = 0.042
EYE_SIGMA = 0.16
BROW_GAIN = 0.40

POTATO_SEGMENTS = 96
POTATO_RINGS = 64


def eye_directions() -> list[Vector]:
    """Unit directions for the buds, on a golden-angle spiral."""

    directions: list[Vector] = []
    for index in range(EYE_COUNT):
        t = (index + 0.5) / EYE_COUNT
        z = 1.0 - 2.0 * (t**1.35)
        radius = math.sqrt(max(0.0, 1.0 - z * z))
        theta = index * 2.399963229728653
        directions.append(
            Vector((radius * math.cos(theta), radius * math.sin(theta), z)).normalized()
        )
    return directions


def sculpt_potato(obj: bpy.types.Object) -> None:
    """Displace a unit sphere into a tuber, in place."""

    eyes = eye_directions()
    mesh = obj.data
    for vertex in mesh.vertices:
        direction = vertex.co.normalized()
        radius = 1.0
        for axis, phase, amplitude in LUMPS:
            radius += amplitude * math.sin(direction.dot(axis) * math.pi + phase)
        for axis, phase, amplitude in CRINKLE:
            radius += amplitude * math.sin(direction.dot(axis) * math.pi + phase)
        for eye in eyes:
            angle = math.acos(max(-1.0, min(1.0, direction.dot(eye))))
            radius -= EYE_DEPTH * math.exp(-((angle / EYE_SIGMA) ** 2))
            brow = (angle - EYE_SIGMA * 1.45) / (EYE_SIGMA * 0.62)
            radius += EYE_DEPTH * BROW_GAIN * math.exp(-(brow**2))
        vertex.co = direction * radius


def build_materials() -> dict[str, object]:
    return bk.materials_from_palette(spec, EXAMPLE_ROOT / "textures")


def add_annulus(
    name: str,
    z_top: float,
    r_inner: float,
    r_outer: float,
    depth: float,
    material,
    segments: int = 96,
    uv_tile: float = 1.0,
) -> bpy.types.Object:
    """A flat ring: top face plus outer/inner walls, no bottom (buried).

    The v2.1 medallion rings were TORUSES lying on the disc — half-pipes of
    bronze proud of the surface (v2.2 round: "flat and smooth ... with real
    copper rings"). A real plaza inlay is a flush annular band; this builds
    one, sitting ``depth`` into the disc so only the polished top shows.
    UVs are polar: U follows the mid circumference, V the radial width, so
    the copper grain runs around the band.
    """

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    uvs: list[tuple[float, float]] = []
    r_mid = 0.5 * (r_inner + r_outer)
    # segments + 1 columns: the seam column is DUPLICATED so its U keeps
    # counting up instead of snapping back to zero and smearing the last
    # segment's texture backwards across the whole band.
    for index in range(segments + 1):
        angle = math.tau * index / segments
        c, s = math.cos(angle), math.sin(angle)
        u = (angle * r_mid) / uv_tile
        for radius, v_coord in ((r_inner, 0.0), (r_outer, (r_outer - r_inner) / uv_tile)):
            vertices.append((radius * c, radius * s, z_top))
            uvs.append((u, v_coord))
        for radius in (r_inner, r_outer):
            vertices.append((radius * c, radius * s, z_top - depth))
            uvs.append((u, -depth / uv_tile))
    for index in range(segments):
        a = index * 4
        b = (index + 1) * 4
        faces.append((a, a + 1, b + 1, b))          # top, wound +Z out
        faces.append((a + 1, a + 3, b + 3, b + 1))  # outer wall, out
        faces.append((a + 2, a, b, b + 2))          # inner wall, inward-facing
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def add_polar_disc(
    name: str,
    z_top: float,
    radius: float,
    depth: float,
    material,
    segments: int = 128,
    radial_rings: int = 6,
    uv_tile: float = 3.0,
    flare: float = 0.25,
) -> bpy.types.Object:
    """A plaza plate with POLAR UVs and a flared (tapered) rim.

    The round-1 critic on the add_cone version: "brush marks run in one
    straight linear direction across a circular machined plate — a
    lathed/ground disc brushes circumferentially." The texture family's
    grain runs along U, so the fix is the MAPPING: U is arc length around
    the plate (per-vertex, so grain density holds from hub to rim), V is
    radius — linear streaks become the concentric swirl a ground disc
    actually carries, converging at the hub the way the real tool mark
    does. The rim wall flares out ``flare`` at grade: the tapered edge.
    """

    vertices: list[tuple[float, float, float]] = [(0.0, 0.0, z_top)]
    uvs: list[tuple[float, float]] = [(0.0, 0.0)]
    faces: list[tuple[int, ...]] = []
    cols = segments + 1  # seam column duplicated, same law as the annulus
    ring_radii = [radius * i / radial_rings for i in range(1, radial_rings + 1)]
    for r in ring_radii:
        for s in range(cols):
            angle = math.tau * s / segments
            vertices.append((r * math.cos(angle), r * math.sin(angle), z_top))
            uvs.append(((angle * r) / uv_tile, r / uv_tile))
    rim = radius + flare
    for s in range(cols):
        angle = math.tau * s / segments
        vertices.append((rim * math.cos(angle), rim * math.sin(angle), z_top - depth))
        uvs.append(((angle * rim) / uv_tile, (rim + depth) / uv_tile))
    for s in range(segments):
        faces.append((0, 1 + s, 2 + s))
    for ri in range(radial_rings - 1):
        inner = 1 + ri * cols
        outer = 1 + (ri + 1) * cols
        for s in range(segments):
            faces.append((inner + s, outer + s, outer + s + 1, inner + s + 1))
    top_edge = 1 + (radial_rings - 1) * cols
    bottom_edge = 1 + radial_rings * cols
    for s in range(segments):
        faces.append((top_edge + s, bottom_edge + s, bottom_edge + s + 1, top_edge + s + 1))
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bk.assign_material(obj, material)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def flatten_horizontal_uvs(obj: bpy.types.Object, meters_per_tile: float) -> None:
    """Planar-map every near-horizontal face to world XY at metric density.

    The v2.4 footing fix ("the tops look especially bad"): add_cone scales
    the WHOLE primitive UV map for the side walls — U by the circumference,
    V by the slant — which is right for the skirt and catastrophic for the
    cap fans. On the plinths that scaling squashed the top faces ~64:1
    anisotropic, smearing the fine concrete speckle into herringbone
    streaks (player screenshot, 2026-08-29). Caps get an isotropic planar
    XY projection at the same metres-per-tile instead; the side walls keep
    their circumference mapping untouched.
    """

    mesh = obj.data
    layer = mesh.uv_layers.active
    if layer is None:
        return
    for polygon in mesh.polygons:
        if abs(polygon.normal.z) < 0.6:
            continue
        for loop_index in polygon.loop_indices:
            vertex = mesh.vertices[mesh.loops[loop_index].vertex_index]
            layer.data[loop_index].uv = (
                vertex.co.x / meters_per_tile,
                vertex.co.y / meters_per_tile,
            )


def build_visual(materials) -> list:
    steel = materials[f"{MOD_ID}_arch_steel"]
    pad = materials[f"{MOD_ID}_pad_steel"]
    copper = materials[f"{MOD_ID}_copper"]
    concrete = materials[f"{MOD_ID}_plinth_concrete"]

    objects = [build_arch(steel)]

    # The landing medallion: a ground-steel plate under the apex with a
    # tapered rim (wider at grade) and two flush copper inlay bands. It is
    # the pickup pad, the visual "stand here", and the cage's ground datum.
    objects.append(
        add_polar_disc(
            f"{MOD_ID}_medallion",
            spec.MEDALLION_TOP_Z,
            spec.MEDALLION_RADIUS,
            spec.MEDALLION_TOP_Z,
            pad,
            segments=128,
            radial_rings=6,
            uv_tile=3.0,
            flare=0.25,
        )
    )
    # 6 mm proud of the plate: enough that the band catches its own light
    # line and never z-fights, flush to the eye and to a tyre.
    for ring_name, r_inner, r_outer in (
        ("ring", spec.MEDALLION_RADIUS - 0.65, spec.MEDALLION_RADIUS - 0.35),
        ("ring_inner", spec.MEDALLION_RADIUS * 0.37, spec.MEDALLION_RADIUS * 0.42),
    ):
        objects.append(
            add_annulus(
                f"{MOD_ID}_medallion_{ring_name}",
                spec.MEDALLION_TOP_Z + 0.006,
                r_inner,
                r_outer,
                0.03,
                copper,
                segments=128,
                uv_tile=1.0,
            )
        )

    # Foundation plinths (v2.2: "the base plates of the arch don't look
    # great or realistic"). Two stepped triangular pads of fine-cast
    # concrete, each oriented like the leg cross-section it carries (one
    # vertex outward, flat face toward the pad) with a shallow chamfer —
    # the stepped footing the prototype's legs meet the plaza with, in
    # place of v2.1's stone pucks.
    stations = arch_stations()
    # Blender's 3-vertex cone puts vertex 0 at +Y (measured 2026-08-29:
    # primitive_cone_add vertices print (0, 1, z) first), NOT at +X — the
    # first cut assumed +X, rotated the west plinth by pi, and shipped both
    # plinths corner-to-camera: "two stair ramps leaned against the column"
    # with an open seam at the vertex (round-1 critic). -pi/2 brings vertex
    # 0 to +X; the west foot adds pi on top of that.
    for side, station, rotation in (
        ("w", stations[0], math.pi / 2.0),
        ("e", stations[-1], -math.pi / 2.0),
    ):
        foot_x = station["p"].x
        # The leg's grade cross-section is circumradius ~2.38 and its axis
        # leans inboard, so the upper step carries a fatter margin than the
        # first cut (2.78 left a slit where the tilted skin crossed it) and
        # the steps overlap in z so no gap can open between them.
        for step, circum, depth, z_center in (
            (0, 3.20, 0.30, 0.15),
            (1, 2.95, 0.32, 0.40),
        ):
            plinth = bk.add_cone(
                f"{MOD_ID}_plinth_{side}_{step}",
                (foot_x, 0.0, z_center),
                circum,
                circum - 0.10,
                depth,
                concrete,
                vertices=3,
                rotation=(0.0, 0.0, rotation),
                bevel=0.03,
                metric_uv=(2.5, 2.5),
            )
            # v2.4: re-project the step TOPS (see flatten_horizontal_uvs —
            # the cone's side-wall UV scaling smeared them into streaks).
            flatten_horizontal_uvs(plinth, 2.5)
            objects.append(plinth)
    return objects


def sculpt_mash(obj: bpy.types.Object, seed: int) -> None:
    """Displace a unit sphere into a dollop of mashed potato, in place.

    Same frequency-band discipline as sculpt_potato, tuned for whipped
    starch instead of tuber: fewer, softer, DEEPER lumps (mash holds folds,
    not eyes), a vertical squash into a dollop, and a slight soft peak on
    top like it slid off a serving spoon.
    """

    rng = random.Random(seed)  # noqa: S311 - shape authoring, not crypto
    folds = [
        (
            Vector((
                rng.uniform(-1.0, 1.0),
                rng.uniform(-1.0, 1.0),
                rng.uniform(-1.0, 1.0),
            )).normalized() * rng.uniform(0.7, 1.8),
            rng.uniform(0.0, math.tau),
            rng.uniform(0.06, 0.16),
        )
        for _ in range(7)
    ]
    ripple = [
        (
            Vector((
                rng.uniform(-1.0, 1.0),
                rng.uniform(-1.0, 1.0),
                rng.uniform(-1.0, 1.0),
            )).normalized() * rng.uniform(2.2, 3.6),
            rng.uniform(0.0, math.tau),
            rng.uniform(0.015, 0.035),
        )
        for _ in range(9)
    ]
    for vertex in obj.data.vertices:
        direction = vertex.co.normalized()
        radius = 1.0
        for axis, phase, amplitude in folds:
            radius += amplitude * math.sin(direction.dot(axis) * math.pi + phase)
        for axis, phase, amplitude in ripple:
            radius += amplitude * math.sin(direction.dot(axis) * math.pi + phase)
        # Dollop: squash toward the equator, pull a soft peak at the pole.
        squash = 1.0 - 0.28 * abs(direction.z)
        peak = 0.10 * math.exp(-(((1.0 - direction.z) / 0.35) ** 2))
        vertex.co = direction * (radius * squash + peak)


def build_parts(materials) -> dict[str, dict[str, object]]:
    # v2.3 ("remove the wick, keep the potato smoking"): the swept fuse
    # cord, its charred tip and the ember sphere are gone — the tuber ships
    # bare and the runtime's smoke wisp rises off its scorched crown
    # (SMOKE_RISE in spec.py's behaviour).
    skin = materials[f"{MOD_ID}_potato"]
    potato = bk.add_sphere(
        f"{MOD_ID}_potato_body",
        HOME,
        1.0,
        skin,
        segments=POTATO_SEGMENTS,
        rings=POTATO_RINGS,
    )
    sculpt_potato(potato)
    potato.scale = (spec.POTATO_SEMI_X, spec.POTATO_SEMI_Y, spec.POTATO_SEMI_Z)
    bpy.ops.object.select_all(action="DESELECT")
    potato.select_set(True)
    bpy.context.view_layer.objects.active = potato
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(60.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    potato.select_set(False)

    parts: dict[str, dict[str, object]] = {
        "potato": {"objects": [potato], "pivot": HOME}
    }

    # The mash chunks (v2.4, "spare no expense polygon wise"): six sculpted
    # dollops parked at their authored homes under the plaza (spec.MASH_HOMES
    # — shared with the runtime, which flings them out of the detonation and
    # re-parks them). Dense spheres so the fold sculpt survives close-ups:
    # the biggest chunk carries the potato's own 96x64 budget.
    mash = materials[f"{MOD_ID}_mash"]
    for index, (home, radius) in enumerate(
        zip(spec.MASH_HOMES, spec.MASH_RADII, strict=True), start=1
    ):
        segments = 64 if radius < 0.5 else 96
        rings = 48 if radius < 0.5 else 64
        chunk = bk.add_sphere(
            f"{MOD_ID}_mash_{index}",
            tuple(home),
            1.0,
            mash,
            segments=segments,
            rings=rings,
        )
        sculpt_mash(chunk, 47_2400 + index)
        chunk.scale = (radius, radius, radius)
        bpy.ops.object.select_all(action="DESELECT")
        chunk.select_set(True)
        bpy.context.view_layer.objects.active = chunk
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        try:
            bpy.ops.object.shade_auto_smooth(angle=math.radians(60.0))
        except Exception:
            bpy.ops.object.shade_smooth()
        chunk.select_set(False)
        parts[f"mash_{index}"] = {"objects": [chunk], "pivot": tuple(home)}

    return parts


def build_cage() -> bk.CageBuilder:
    cage = bk.CageBuilder(MOD_ID)
    stations = arch_stations()

    medallion = cage.add_box_lattice(
        "pad",
        (-spec.PAD_HALF, -spec.PAD_HALF, 0.0),
        (spec.PAD_HALF, spec.PAD_HALF, spec.MEDALLION_TOP_Z),
        subdivisions=(2, 2, 1),
        fixed=True,
        collision=False,
        collision_faces=("top",),
        face_ground_models={"top": "asphalt"},
    )

    pylons = {}
    for side, sx in (("w", -1.0), ("e", 1.0)):
        foot_x = sx * L
        pylons[side] = cage.add_box_lattice(
            f"pylon_{side}",
            (foot_x - spec.PYLON_HALF, -spec.PYLON_HALF, 0.0),
            (foot_x + spec.PYLON_HALF, spec.PYLON_HALF, spec.PYLON_TOP_Z),
            subdivisions=(1, 1, 2),
            fixed=True,
            collision=False,
            collision_faces=("north", "south", "east", "west", "top"),
        )

    # Cage rings along the arch. The flexbody skins each visual vertex to a
    # local triad of nearby cage nodes, so a 31 m visual over a cage that only
    # covers the feet is how you get invisible bands: the spine has to follow
    # the structure it carries.
    ring_ids: list[list[str]] = []
    for index in range(0, len(stations), spec.CAGE_RING_STRIDE):
        station = stations[index]
        corners = arch_corners(station)
        ids = []
        for corner_index, corner in enumerate(corners):
            ids.append(
                cage.add_node(
                    f"arch_{index:03d}_{corner_index}",
                    corner,
                    fixed=True,
                    collision=corner[2] < spec.ARCH_COLLIDE_MAX_Z,
                    weight=90.0,
                )
            )
        for first in range(3):
            cage.add_beam(ids[first], ids[(first + 1) % 3])
        ring_ids.append(ids)

    for index in range(len(ring_ids) - 1):
        lower, upper = ring_ids[index], ring_ids[index + 1]
        for corner in range(3):
            cage.add_beam(lower[corner], upper[corner])
            cage.add_beam(lower[corner], upper[(corner + 1) % 3])
        first_z = cage.nodes[cage.node_index[lower[0]]]["source_world_position"][2]
        second_z = cage.nodes[cage.node_index[upper[0]]]["source_world_position"][2]
        # Collision skin only where a car can actually reach it.
        if max(first_z, second_z) < spec.ARCH_COLLIDE_MAX_Z:
            for corner in range(3):
                nxt = (corner + 1) % 3
                cage.add_quad([lower[corner], lower[nxt], upper[nxt], upper[corner]])

    # Tie the spine's ends into the pylons and the pylons to the pad, so the
    # whole cage stays one connected graph.
    for side, ring in (("w", ring_ids[0]), ("e", ring_ids[-1])):
        for corner in range(3):
            for ix in (0, 1):
                for iy in (0, 1):
                    cage.stitch(ring[corner], pylons[side][(ix, iy, 2)])
    for side in ("w", "e"):
        for ix in (0, 1):
            for iy in (0, 1):
                for pad_ix in (0, 1, 2):
                    cage.stitch(pylons[side][(ix, iy, 0)], medallion[(pad_ix, 1, 0)])

    # The refnodes double as the runtime's slope-placement FRAME_NODES, and
    # the frame-math gate rejects a poorly conditioned frame. The pad is only
    # 0.05 m tall, so the pad's own top node gave ref->up a 5 cm baseline -
    # exactly the MIN_BASELINE_M floor, and it collapsed under rotation in
    # test_every_viable_pair_recovers_the_same_rotation. The arch apex ring
    # sits 31 m above the ref with zero authored x/y offset: as well
    # conditioned as this monument can offer.
    apex_up = ring_ids[len(ring_ids) // 2][0]
    cage.set_refnodes_existing(
        ref=medallion[(1, 1, 0)],
        back=medallion[(1, 0, 0)],
        left=medallion[(0, 1, 0)],
        up=apex_up,
    )
    cage.set_spawn_envelope(
        [
            pylons["w"][(0, 0, 0)],
            pylons["w"][(0, 1, 0)],
            pylons["w"][(0, 0, 2)],
            pylons["w"][(0, 1, 2)],
            pylons["e"][(1, 0, 0)],
            pylons["e"][(1, 1, 0)],
            pylons["e"][(1, 0, 2)],
            pylons["e"][(1, 1, 2)],
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
        # Pulled back for the quarter-scale monument (47.6 m tall, 46 m
        # span — 1.52x the v2.1 arch).
        camera_location=(52.0, -100.0, 37.0),
        look_at=(0.0, 0.0, 20.5),
    )
    print(f"HOT_POTATO generator complete: {len(parts)} parts, {len(cage.nodes)} nodes")


if __name__ == "__main__":
    main()
