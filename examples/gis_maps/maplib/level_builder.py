"""Emit a complete BeamNG level tree from a spec plus the terrain stage's outputs.

Every file the game reads is generated here, never hand-edited (the giant props law):

    levels/<mod_id>/
      info.json                          level selector metadata + spawn points
      <mod_id>_preview.jpg               main thumbnail; spawn_<name>.jpg per spawn
      <mod_id>_minimap.png               orthoimagery minimap
      theTerrain.ter                     TerrainFile v9 (heights, layer map, materials)
      theTerrain.terrain.json            descriptive metadata the engine writes on save
      theTerrain.terrainheightmap.png    16-bit heightmap, north-up, for the Import Terrain tool
      main/items.level.json              MissionGroup
      main/MissionGroup/.../items.level.json   terrain, sky, level info, time, spawns, roads
      art/terrains/main.materials.json   TerrainMaterialTextureSet + one TerrainMaterial per layer
      art/terrains/*.png                 base set from imagery + DEM, procedural detail/macro sets
      art/road/main.materials.json       the DecalRoad material and its textures

Formats follow documentation.beamng.com (level_formats/terrain, level_classes/*) and a
real shipped level's files, verified byte-level for the .ter material-name encoding
(u8 length prefix) and the version 9 payload (no v8 layerTextureMap block).
"""

from __future__ import annotations

import itertools
import json
import math
import uuid
from pathlib import Path

import numpy as np

from . import heightmap as hm
from . import texture_kit

PID_NAMESPACE = uuid.UUID("6f4a4d3a-9b1e-4a83-9f7e-2c1c4b6b5e11")

GROUNDMODEL_BY_FAMILY = {
    "cliff_beds": "ROCK",
    "shale_plates": "GRAVEL",
    "tussock": "GRASS",
    "limestone": "ROCK",
    "talus_blocks": "ROCK",
    "ejecta": "GRAVEL",
    "asphalt": "ASPHALT",
    "asphalt_bed": "ASPHALT",
    "water": "MUD",
    "dirt_track": "DIRT",
    "gravel_track": "GRAVEL",
    "desert_floor": "DIRT_DUSTY",
    "gravel": "GRAVEL",
    "rock_strata": "ROCK",
    "scree": "GRAVEL",
    "dry_grass": "GRASS",
    "clay_pan": "DIRT",
    "shale": "DIRT_DUSTY",
    "volcanic_ash": "SAND",
    "snow": "SNOW",
    "alpine_tundra": "GRASS",
    "gravel_bed": "GRAVEL",
    "dirt_bed": "DIRT",
    "forest_floor": "DIRT",
    "dark_strata": "ROCK",
    "rim_rubble": "ROCK",
}

BASE_TEX_PX = 2048
DETAIL_TEX_PX = 512
MACRO_TEX_PX = 512
DETAIL_TILE_M = 2
MACRO_TILE_M = 60


def pid(mod_id: str, key: str) -> str:
    return str(uuid.uuid5(PID_NAMESPACE, f"{mod_id}:{key}"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


# What the AI's route planner should think of each class of way. A DecalRoad's
# drivability is a preference weight, not a flag, and the pack was giving every way
# the same 1: a 3.2 m shelf road with a 20 % ledge on it was being offered to traffic
# on the same terms as a two-lane tertiary. These are the defaults; a spec's
# ROADS["drivability"] overrides any of them by highway class.
DRIVABILITY_BY_HIGHWAY = {
    "motorway": 1.0,
    "trunk": 1.0,
    "primary": 0.9,
    "secondary": 0.8,
    "tertiary": 0.7,
    "unclassified": 0.5,
    "residential": 0.5,
    "service": 0.4,
    "track": 0.2,
    "path": 0.1,
}


def write_items(path: Path, objects: list[dict]) -> None:
    """items.level.json is line-delimited JSON: one complete object per line, no array."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(obj, separators=(",", ":"), sort_keys=False) for obj in objects]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def yaw_matrix(heading_deg: float) -> list[float]:
    """Row-major 3x3 rotation about Z for a compass heading (0 = north, clockwise).

    BeamNG vehicles spawn nose toward the spawn's -Y axis (the vehicle frame is +Y
    backward), so a heading of 0 (north, +Y) needs the marker turned 180 degrees.
    """

    yaw = math.radians(180.0 - heading_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    return [round(c, 9), round(s, 9), 0.0, round(-s, 9), round(c, 9), 0.0, 0.0, 0.0, 1.0]


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------


class Frame:
    """Level frame: metres east/north of the footprint centre; terrain samples north-up."""

    def __init__(self, fp, dem: np.ndarray, res: float, min_elevation: float):
        self.fp = fp
        self.dem = dem
        self.res = res
        self.min_elevation = min_elevation
        self.cx, self.cy = fp.center

    def to_level(self, easting: float, northing: float) -> tuple[float, float]:
        return (easting - self.cx, northing - self.cy)

    def lonlat_to_level(self, lon: float, lat: float) -> tuple[float, float]:
        from rasterio.warp import transform

        xs, ys = transform("EPSG:4326", f"EPSG:{self.fp.epsg}", [lon], [lat])
        return self.to_level(xs[0], ys[0])

    def inside(self, x: float, y: float, margin: float = 2.0) -> bool:
        half = self.fp.size_m / 2.0 - margin
        return -half <= x <= half and -half <= y <= half

    def height_at(self, x: float, y: float) -> float:
        """World Z (terrain position z = 0, heights relative to the lowest sample)."""

        size = self.dem.shape[0]
        col = (x + self.fp.size_m / 2.0) / self.res
        row = (self.fp.size_m / 2.0 - y) / self.res
        col = min(max(col, 0.0), size - 1.001)
        row = min(max(row, 0.0), size - 1.001)
        c0, r0 = int(col), int(row)
        fc, fr = col - c0, row - r0
        z = (
            self.dem[r0, c0] * (1 - fc) * (1 - fr)
            + self.dem[r0, c0 + 1] * fc * (1 - fr)
            + self.dem[r0 + 1, c0] * (1 - fc) * fr
            + self.dem[r0 + 1, c0 + 1] * fc * fr
        )
        return float(z - self.min_elevation)


# ---------------------------------------------------------------------------
# Roads
# ---------------------------------------------------------------------------


def _max_grade_over(nodes: list, window_m: float) -> float:
    """The largest |rise / run| over any stretch of at least half ``window_m`` and at
    most ``window_m`` along the polyline of ``[x, y, z, w]`` nodes."""
    if len(nodes) < 2:
        return 0.0
    dist = [0.0]
    for a, b in itertools.pairwise(nodes):
        dist.append(dist[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    worst = 0.0
    j = 0
    for i in range(len(nodes)):
        j = max(j, i)
        while j + 1 < len(nodes) and dist[j + 1] - dist[i] <= window_m:
            j += 1
        run = dist[j] - dist[i]
        if run >= window_m / 2.0:
            worst = max(worst, abs(nodes[j][2] - nodes[i][2]) / run)
    return worst


def _resample_polyline(
    points: list[tuple[float, float]], max_step: float
) -> list[tuple[float, float]]:
    out = [points[0]]
    for (x0, y0), (x1, y1) in itertools.pairwise(points):
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, math.ceil(length / max_step))
        for i in range(1, steps + 1):
            t = i / steps
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def build_roads(
    spec, frame: Frame, osm_path: Path, *, max_step_m: float = 12.0
) -> tuple[list[dict], dict]:
    """OSM highway ways -> DecalRoad objects clipped to the footprint and draped on the DEM."""

    payload = json.loads(osm_path.read_text(encoding="utf-8"))
    include = set(spec.ROADS["include"])
    widths = spec.ROADS["widths"]
    material = spec.ROADS["material"]["name"]
    roads: list[dict] = []
    stats: dict = {"ways_seen": 0, "roads": 0, "length_m": 0.0, "by_type": {}}
    for element in payload.get("elements", []):
        if element.get("type") != "way":
            continue
        tags = element.get("tags", {})
        highway = tags.get("highway")
        if highway not in include:
            continue
        stats["ways_seen"] += 1
        width = float(widths.get(highway, 4.0))
        points = [frame.lonlat_to_level(p["lon"], p["lat"]) for p in element.get("geometry", [])]
        # Split into runs that stay inside the footprint.
        runs: list[list[tuple[float, float]]] = [[]]
        for point in points:
            if frame.inside(*point):
                runs[-1].append(point)
            elif runs[-1]:
                runs.append([])
        for index, run in enumerate(r for r in runs if len(r) >= 2):
            dense = _resample_polyline(run, max_step_m)
            nodes = [
                [round(x, 3), round(y, 3), round(frame.height_at(x, y), 3), width] for x, y in dense
            ]
            length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(nodes))
            if length < 15.0:
                continue
            name = f"road_{element['id']}_{index}"
            roads.append(
                {
                    "name": name,
                    "class": "DecalRoad",
                    "persistentId": pid(spec.MOD_ID, name),
                    "__parent": "roads",
                    "position": nodes[0][:3],
                    "improvedSpline": True,
                    "material": material,
                    "textureLength": 8,
                    "renderPriority": 10,
                    "startEndFade": [2, 2],
                    "drivability": DRIVABILITY_BY_HIGHWAY.get(highway, 0.3),
                    "nodes": nodes,
                }
            )
            stats["roads"] += 1
            stats["length_m"] += length
            stats["by_type"][highway] = stats["by_type"].get(highway, 0) + 1
    stats["length_m"] = round(stats["length_m"], 1)
    return roads, stats


def _trim_end_kinks(nodes: list, cap: float, max_drop: int = 12) -> list:
    """Drop end nodes until the decal stops ending in a step.

    A free end lands where the carved bed has feathered back into raw ground, and on a
    coarse grid that last metre can turn over sharply. The window is the same three
    intervals the ledger measures: reading only the outermost change misses a kink two
    nodes in, which is how the first version of this trimmed nothing.
    """

    def change_at(seq, at_start: bool) -> float:
        if len(seq) < 5:
            return 0.0
        grades = [
            (b[2] - a[2]) / max(math.hypot(b[0] - a[0], b[1] - a[1]), 1e-3)
            for a, b in itertools.pairwise(seq)
        ]
        changes = [abs(g2 - g1) for g1, g2 in itertools.pairwise(grades)]
        window = changes[:3] if at_start else changes[-3:]
        return max(window) if window else 0.0

    for at_start in (True, False):
        for _ in range(max_drop):
            if len(nodes) < 6 or change_at(nodes, at_start) <= cap:
                break
            nodes = nodes[1:] if at_start else nodes[:-1]
    return nodes


def _drop_step_nodes(nodes: list, cap: float, max_share: float = 0.02) -> list:
    """Remove the samples that make a decal step, worst first.

    One interval in 2,408 on the Imogene Pass track drops six metres between
    consecutive 8 m nodes: the way crosses something the ground does not carry through.
    Smoothing cannot fix a discontinuity and a wider carve does not reach it, but a
    road does span a washout - so the sample that makes the step goes, and the decal
    bridges it. Bounded to ``max_share`` of the way's nodes so this can never quietly
    rewrite a road's shape.
    """

    budget = max(1, int(len(nodes) * max_share))
    for _ in range(budget):
        if len(nodes) < 5:
            break
        grades = [
            (b[2] - a[2]) / max(math.hypot(b[0] - a[0], b[1] - a[1]), 1e-3)
            for a, b in itertools.pairwise(nodes)
        ]
        changes = [abs(g2 - g1) for g1, g2 in itertools.pairwise(grades)]
        worst = max(range(len(changes)), key=lambda i: changes[i])
        if changes[worst] <= cap:
            break
        nodes = nodes[: worst + 1] + nodes[worst + 2 :]
    return nodes


def _relax_node_heights(
    nodes: list, cap: float, max_lift_m: float = 0.25, rounds: int = 24
) -> list:
    """Take the creases out of a decal's node heights without letting it float.

    A DecalRoad drapes onto the terrain when drawn, so node heights inform the spline
    rather than fix it - but a node-to-node grade change still reads as a crease. Each
    interior node relaxes toward the mean of its neighbours and is then clamped to
    within ``max_lift_m`` of the ground it was sampled from, so the decal is never more
    than a quarter metre off the terrain it lies on. Ends are pinned: they are already
    trimmed and junction-joined.
    """

    if len(nodes) < 5:
        return nodes
    ground = [n[2] for n in nodes]
    z = list(ground)
    for _ in range(rounds):
        worst = 0.0
        for i in range(1, len(z) - 1):
            a = math.hypot(nodes[i][0] - nodes[i - 1][0], nodes[i][1] - nodes[i - 1][1])
            b = math.hypot(nodes[i + 1][0] - nodes[i][0], nodes[i + 1][1] - nodes[i][1])
            if a < 1e-3 or b < 1e-3:
                continue
            worst = max(worst, abs((z[i + 1] - z[i]) / b - (z[i] - z[i - 1]) / a))
        if worst <= cap:
            break
        for i in range(1, len(z) - 1):
            moved = z[i] + 0.5 * (0.5 * (z[i - 1] + z[i + 1]) - z[i])
            z[i] = min(max(moved, ground[i] - max_lift_m), ground[i] + max_lift_m)
    return [[n[0], n[1], round(zi, 3), n[3]] for n, zi in zip(nodes, z, strict=True)]


def build_surface_roads(spec, frame: Frame, osm_path: Path, fp, *, max_step_m: float = 8.0):
    """DecalRoads with a material per surface (paved / dirt), draped on the carved DEM."""

    from . import roads as road_tools

    polylines = road_tools.road_polylines(spec, fp, osm_path)
    if spec.ROADS.get("max_grade"):
        polylines, _cuts = road_tools.drop_cliff_segments(
            polylines,
            frame.dem,
            frame.res,
            frame.fp.size_m,
            float(spec.ROADS["max_grade"]),
            min_length_m=float(spec.ROADS.get("cliff_cut_min_length_m", 100.0)),
        )
    carve_cfg = spec.ROADS.get("carve") or {}
    # The decal stops where the carved bed stops: an unjoined end is trimmed by the
    # carve's end feather, so no first node steps off the bed onto natural ground.
    polylines = road_tools.trim_free_ends(
        polylines,
        float(carve_cfg.get("end_feather_m", 0.0)),
        float(carve_cfg.get("junction_snap_m", 8.0)),
    )
    surfaces = spec.ROADS["surfaces"]
    roads: list[dict] = []
    stats: dict = {
        "ways_seen": len(polylines),
        "roads": 0,
        "length_m": 0.0,
        "by_type": {},
        "by_surface": {},
        "max_grade_change": 0.0,
        "max_end_grade_change": 0.0,
        "max_grade_10m": {},
    }
    for road in polylines:
        cfg = surfaces.get(road["surface"]) or next(iter(surfaces.values()))
        dense = _resample_polyline(road["points"], max_step_m)
        width = road["width"]
        nodes = [
            [round(x, 3), round(y, 3), round(frame.height_at(x, y), 3), width] for x, y in dense
        ]
        # The gate's contracts are what ships, so they are met before the ledger
        # measures: no decal ends in a step, none steps in the middle, and none creases.
        carve_cfg = spec.ROADS.get("carve") or {}
        node_cap = float(carve_cfg.get("node_kink_cap", 0.25))
        nodes = _drop_step_nodes(nodes, node_cap)
        nodes = _trim_end_kinks(nodes, float(carve_cfg.get("end_kink_cap", 0.10)))
        nodes = _relax_node_heights(nodes, node_cap, float(carve_cfg.get("node_max_lift_m", 0.25)))
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in itertools.pairwise(nodes))
        if length < 15.0:
            continue
        # The largest node-to-node change of grade along the decal: a step at a
        # free end or a seam shows here as a jump.
        grades = [
            (b[2] - a[2]) / max(math.hypot(b[0] - a[0], b[1] - a[1]), 1e-3)
            for a, b in itertools.pairwise(nodes)
        ]
        if len(grades) > 1:
            changes = [abs(g2 - g1) for g1, g2 in itertools.pairwise(grades)]
            stats["max_grade_change"] = round(max(stats["max_grade_change"], max(changes)), 4)
            # The first and last three intervals: a step off the bed at an end.
            ends = changes[:3] + changes[-3:]
            stats["max_end_grade_change"] = round(max(stats["max_end_grade_change"], max(ends)), 4)
        # The steepest 10 m of the decal, per surface: a road plunging off a pad's
        # batter or down a rim flank shows here, whatever its node-to-node smoothness.
        steepest = _max_grade_over(nodes, 10.0)
        by_surface_grade = stats["max_grade_10m"]
        by_surface_grade[road["surface"]] = round(
            max(by_surface_grade.get(road["surface"], 0.0), steepest), 4
        )
        name = f"road_{road['id']}"
        roads.append(
            {
                "name": name,
                "class": "DecalRoad",
                "persistentId": pid(spec.MOD_ID, name),
                "__parent": "roads",
                "position": nodes[0][:3],
                "improvedSpline": True,
                "material": cfg["decal"]["name"],
                "textureLength": float(cfg.get("texture_length_m", 6.0)),
                "breakAngle": 3.0,
                "renderPriority": 10 if road["surface"] == "paved" else 11,
                "startEndFade": [3, 3],
                "drivability": float(
                    (getattr(spec, "ROADS", {}).get("drivability") or {}).get(
                        road["highway"], DRIVABILITY_BY_HIGHWAY.get(road["highway"], 0.3)
                    )
                ),
                "nodes": nodes,
            }
        )
        stats["roads"] += 1
        stats["length_m"] += length
        stats["by_type"][road["highway"]] = stats["by_type"].get(road["highway"], 0) + 1
        stats["by_surface"][road["surface"]] = stats["by_surface"].get(road["surface"], 0) + 1
    stats["length_m"] = round(stats["length_m"], 1)
    return roads, stats


def spawn_apron(frame, x: float, y: float, heading_deg: float, length_m=14.0, width_m=7.0) -> dict:
    """The ground a line of vehicles stands on at a spawn: a ``length_m`` by ``width_m``
    rectangle at ``heading_deg``, sampled every metre.

    Reports the plane it sits on (the tilt along the heading and across it, in
    degrees), how far the ground departs from that plane, and its total relief. A
    shelf road is 3.2 m wide, so a spawn on one can be smooth along the bed and still
    put a wheel over the edge; this measures what the vehicle actually rests on."""

    th = math.radians(heading_deg)
    fx, fy = math.sin(th), math.cos(th)
    px, py = -fy, fx
    offsets, heights = [], []
    steps_a = np.arange(-length_m / 2.0, length_m / 2.0 + 0.01, 1.0)
    steps_b = np.arange(-width_m / 2.0, width_m / 2.0 + 0.01, 1.0)
    for a in steps_a:
        for b in steps_b:
            offsets.append((a, b))
            heights.append(frame.height_at(x + a * fx + b * px, y + a * fy + b * py))
    offsets_a = np.asarray(offsets, dtype="float64")
    z = np.asarray(heights, dtype="float64")
    design = np.c_[offsets_a, np.ones(len(offsets))]
    coef, *_ = np.linalg.lstsq(design, z, rcond=None)
    residual = z - design @ coef
    return {
        "along_deg": round(math.degrees(math.atan(abs(float(coef[0])))), 2),
        "across_deg": round(math.degrees(math.atan(abs(float(coef[1])))), 2),
        "relief_m": round(float(z.max() - z.min()), 2),
        "roughness_m": round(float(np.abs(residual).max()), 2),
        "size_m": [length_m, width_m],
    }


def snap_to_road(
    x: float,
    y: float,
    polylines: list[dict],
    frame: Frame,
    radius_m: float,
    prefer_heading: float | None = None,
):
    """Nearest road-bed point within ``radius_m`` and the heading down the road there.

    Returns (x, y, heading_deg) or None. The heading follows the way's tangent in the
    descending direction, so a spawn on a pass road looks down the descent.
    """

    # At a junction several ways are within reach; the longest one is the road the
    # spawn is named for (the pass road, not the spur to the mine).
    best = None
    for road in polylines:
        dense = _resample_polyline(road["points"], 2.0)
        nearest = min(range(len(dense)), key=lambda k: math.hypot(dense[k][0] - x, dense[k][1] - y))
        d = math.hypot(dense[nearest][0] - x, dense[nearest][1] - y)
        if d > radius_m:
            continue
        if best is None or len(dense) > len(best[2]):
            best = (d, nearest, dense)
    if best is None:
        return None
    _, i, dense = best
    # The road's 20 m tangent through the point (through, so a spawn at the end of a
    # way still has one); the author's heading picks the sense along it, else the
    # sense that descends, so a spawn on a pass road looks down the descent.
    lo, hi = max(0, i - 10), min(len(dense) - 1, i + 10)
    if lo == hi:
        return None
    (ax, ay), (bx, by) = dense[lo], dense[hi]
    tangent = math.degrees(math.atan2(bx - ax, by - ay)) % 360.0
    if prefer_heading is not None:
        diff = abs((tangent - prefer_heading + 180.0) % 360.0 - 180.0)
        forward = diff <= 90.0
    else:
        forward = frame.height_at(*dense[hi]) <= frame.height_at(*dense[lo])
    # The heading is the bearing to the bed 15 m down the road in the chosen
    # sense, not the chord through the point: on a bend the chord looks off the
    # bed within 20 m.
    j = min(len(dense) - 1, i + 7) if forward else max(0, i - 7)
    if j != i:
        (px0, py0), (px1, py1) = dense[i], dense[j]
        heading = math.degrees(math.atan2(px1 - px0, py1 - py0)) % 360.0
    else:
        heading = tangent if forward else (tangent + 180.0) % 360.0
    px, py = dense[i]
    return float(px), float(py), heading


# ---------------------------------------------------------------------------
# Base textures from orthoimagery and the DEM
# ---------------------------------------------------------------------------


def naip_mosaic(naip_dir: Path, fp, out_px: int) -> np.ndarray:
    """Mosaic the cached NAIP tiles onto the footprint and resize to ``out_px`` (RGB8)."""

    from PIL import Image

    tiles = sorted(naip_dir.glob("naip_*.json"))
    if not tiles:
        raise FileNotFoundError(f"no NAIP tiles in {naip_dir}")
    meta = [json.loads(p.read_text(encoding="utf-8")) for p in tiles]
    res = float(meta[0]["resolution_m"])
    full = round(fp.size_m / res)
    canvas = np.zeros((full, full, 3), dtype="uint8")
    for sidecar, info in zip(tiles, meta, strict=True):
        image = Image.open(sidecar.with_suffix(".png")).convert("RGB")
        west, _south, _east, north = info["bounds"]
        col = round((west - fp.west) / res)
        row = round((fp.north - north) / res)
        array = np.asarray(image)
        h, w = array.shape[:2]
        canvas[row : row + h, col : col + w] = array[: full - row, : full - col]
    if full != out_px:
        canvas = np.asarray(Image.fromarray(canvas).resize((out_px, out_px), Image.LANCZOS))
    return canvas


def _resize_gray(array: np.ndarray, out_px: int) -> np.ndarray:
    from PIL import Image

    if array.shape[0] == out_px:
        return array
    image = Image.fromarray(array.astype("float32"), mode="F").resize(
        (out_px, out_px), Image.BILINEAR
    )
    return np.asarray(image)


def conditioned_colour(
    dem: np.ndarray,
    res: float,
    fp,
    naip_dir: Path,
    imagery_spec: dict | None,
    canopy_cover=None,
    canopy_chm=None,
    source_exclude=None,
) -> tuple[np.ndarray, dict]:
    """The full-resolution orthoimagery, de-lit against the DEM when the spec asks."""

    colour = naip_mosaic(naip_dir, fp, dem.shape[0])
    source = source_colour_stats(colour)
    stats: dict = {"delight": False, "source": source}
    if imagery_spec and imagery_spec.get("delight"):
        from . import imagery

        sun = imagery.fit_sun(
            colour,
            dem,
            res,
            altitude_range=tuple(imagery_spec.get("sun_altitude_range", (30.0, 80.0))),
            azimuth_hint=imagery_spec.get("sun_azimuth_hint"),
            azimuth_window=float(imagery_spec.get("sun_azimuth_window", 60.0)),
        )
        colour, dstats = imagery.delight(
            colour,
            dem,
            res,
            azimuth_deg=sun["azimuth_deg"],
            altitude_deg=sun["altitude_deg"],
            strength=float(imagery_spec.get("strength", 1.0)),
            max_gain=float(imagery_spec.get("max_gain", 2.2)),
            shadow_texture_gain=float(imagery_spec.get("shadow_texture_gain", 1.0)),
            # The damp is a crown's, not a cover fraction's: under a crown (CHM
            # over 2 m) the gain is held, in the gap between crowns it is not.
            damp_mask=(canopy_chm > 2.0)
            if canopy_chm is not None
            else (canopy_cover > 0.35)
            if canopy_cover is not None
            else None,
            damp=float(imagery_spec.get("canopy_gain_damp", 0.3)),
            canopy_chm=canopy_chm if imagery_spec.get("canopy_shadow", True) else None,
            canopy_refill=imagery_spec.get("canopy_refill"),
            snow=imagery_spec.get("snow"),
            steep_deg=float(imagery_spec.get("steep_deg", 40.0)),
            steep_cap=bool(imagery_spec.get("steep_cap", True)),
            steep_cap_lum=imagery_spec.get("steep_cap_lum"),
            steep_feather_deg=float(imagery_spec.get("steep_feather_deg", 0.0)),
            knee_lum=float(imagery_spec.get("knee_lum", 0.55)),
            # `delight`'s docstring offers a spec `highlight_ceiling`, and 0 to turn the
            # clamp off. This is the only call site and it was not passing the name, so
            # every de-lit map took the default and no spec could reach the lever.
            highlight_ceiling=float(imagery_spec.get("highlight_ceiling", 0.95)),
            cover_mask=(canopy_chm > 2.0)
            if canopy_chm is not None and imagery_spec.get("refill_by_cover")
            else (canopy_cover > 0.5)
            if canopy_cover is not None and imagery_spec.get("refill_by_cover")
            else None,
            match_ring=bool(imagery_spec.get("refill_match_ring", False)),
            shadow_dark_ratio=imagery_spec.get("shadow_dark_ratio"),
            exclude_sources=source_exclude,
        )
        stats = {"delight": True, "sun_fit": sun, **dstats, "source": source}
    return colour, stats


def source_colour_stats(colour: np.ndarray, stride: int = 4) -> dict:
    """What the photograph measures before any conditioning touches it.

    The shipped base's own luminance spread says nothing on its own: a flat pale basin
    and a mosaic the de-lighting flattened read the same number. Only the ratio of the
    two separates them, and this end of it was the end nobody recorded - every stat in
    the handoff describes the output. Factory Butte is the case that needs it: its base
    is the palest of the pack at 0.052 chroma under the mud flat, and whether that is
    the badlands or the correction is not answerable from the output alone.

    Taken on a stride, so the full mosaic is never copied to measure it.
    """

    sample = colour[::stride, ::stride].astype("float32") / 255.0
    lum = sample.mean(axis=-1)
    p05, p50, p95 = (float(v) for v in np.percentile(lum, [5, 50, 95]))
    brightest = sample.max(axis=-1)
    chroma = (brightest - sample.min(axis=-1)) / np.maximum(brightest, 1e-6)
    out = {
        "px": int(colour.shape[0]),
        "stride": int(stride),
        "lum_p05": round(p05, 4),
        "lum_p50": round(p50, 4),
        "lum_p95": round(p95, 4),
        "lum_spread": round(p95 - p05, 4),
        "chroma_mean": round(float(chroma.mean()), 4),
    }
    del sample, lum, brightest, chroma
    return out


def base_colour_stats(
    colour: np.ndarray,
    layer: np.ndarray,
    materials,
    *,
    before_ceiling: np.ndarray | None = None,
) -> dict:
    """The finished base's black-hole and per-layer numbers, measured on what ships.

    Every map reaches build_base_set, and only some reach the terrain stage's OBJECTS
    path, so this is where the base's own gate numbers are taken: measured here, they
    exist for all six maps and they describe the array that was written rather than an
    upstream one of a different size (the base is resized to base_px on its way out, and
    LANCZOS overshoot on a hard edge lands exactly in the clipped fraction).

    ``before_ceiling`` is the same base one step earlier, before the shipping clamp.
    The clamp caps every channel at 249 and ``clipped`` counts 250, so once a map runs
    the clamp its ``clipped`` is zero however the pipeline behaved - a true number that
    can no longer be a gate. Measured on the array handed in here instead, the per-layer
    share survives the fix that hid it, at the resolution the whole-base
    ``shipped_ceiling_fraction`` throws away: fb_caprock is 5.6% over the ceiling and
    0.13% of its base.
    """

    from PIL import Image

    layer_at_colour = layer
    if layer.shape[0] != colour.shape[0]:
        layer_at_colour = np.asarray(
            Image.fromarray(layer.astype("uint8")).resize(
                (colour.shape[0], colour.shape[0]), Image.NEAREST
            )
        )
    means = {}
    for index, name in enumerate(materials):
        where = layer_at_colour == index
        if where.sum() < 100:
            continue
        rgb = colour[where].reshape(-1, 3).mean(axis=0) / 255.0
        means[name] = {
            "rgb": [round(float(v), 4) for v in rgb],
            "luminance": round(float(rgb.mean()), 4),
            "cells": int(where.sum()),
            "clipped": round(float((colour[where].max(axis=-1) >= 250).mean()), 5),
        }
        if before_ceiling is not None:
            means[name]["clipped_before_ceiling"] = round(
                float((before_ceiling[where].max(axis=-1) >= 250).mean()), 5
            )
    return {
        "base_px": int(colour.shape[0]),
        "layer_mean_srgb": means,
        "near_black_fraction": round(float((colour.max(axis=-1) < 13).mean()), 6),
    }


def build_base_set(
    dem: np.ndarray,
    res: float,
    fp,
    naip_dir: Path,
    out_dir: Path,
    prefix: str,
    *,
    colour_full: np.ndarray | None = None,
    base_px: int = BASE_TEX_PX,
) -> dict[str, Path]:
    """t_base_{b,nm,r,h,ao}.png: the satellite-view base every terrain material shares.

    Written SOUTH-UP (row 0 = the level's south edge), the order the .ter heights are
    written in: the engine maps a base texture's first image row onto y = 0 of the
    terrain block, so a north-up image comes out mirrored against the heightmap (the
    visitor centre on the wrong rim). Every array here is north-up until the write.
    """

    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    if colour_full is None:
        colour = naip_mosaic(naip_dir, fp, base_px)
    elif colour_full.shape[0] != base_px:
        colour = np.asarray(Image.fromarray(colour_full).resize((base_px, base_px), Image.LANCZOS))
    else:
        colour = colour_full
    small = _resize_gray(dem, base_px)
    base_res = fp.size_m / base_px
    normal = hm.normal_map(small, base_res, strength=1.0)
    ao = hm.ambient_occlusion(small, base_res, radius_px=12)
    lo, hi = float(small.min()), float(small.max())
    height = ((small - lo) / max(hi - lo, 1e-6) * 255.0).round().astype("uint8")
    luminance = colour.astype("float32").mean(axis=-1) / 255.0
    rough = np.clip(0.9 - 0.15 * luminance, 0.55, 0.95)
    paths = {}
    for suffix, array in (
        ("b", colour),
        ("nm", normal),
        ("r", (rough * 255).round().astype("uint8")),
        ("h", height),
        ("ao", (ao * 255).round().astype("uint8")),
    ):
        path = out_dir / f"{prefix}_{suffix}.png"
        hm.write_png8(path, np.ascontiguousarray(array[::-1]))
        paths[suffix] = path
    return paths


def build_previews(
    dem: np.ndarray,
    res: float,
    fp,
    naip_dir: Path,
    frame: Frame,
    spawns: list[dict],
    level_root: Path,
    mod_id: str,
    *,
    colour_full: np.ndarray | None = None,
) -> dict:
    """Preview JPGs: colour orthoimagery lit by a DEM hillshade, whole map and per spawn."""

    from PIL import Image

    if colour_full is None:
        colour = naip_mosaic(naip_dir, fp, 2048).astype("float32") / 255.0
    else:
        colour = (
            np.asarray(Image.fromarray(colour_full).resize((2048, 2048), Image.LANCZOS)).astype(
                "float32"
            )
            / 255.0
        )
    shade = hm.hillshade(_resize_gray(dem, 2048), fp.size_m / 2048, 315.0, 40.0)
    lit = np.clip(colour * (0.55 + 0.6 * shade[..., None]), 0.0, 1.0)
    image = Image.fromarray((lit * 255).round().astype("uint8"))
    previews = {}
    main = level_root / f"{mod_id}_preview.jpg"
    image.resize((1024, 1024), Image.LANCZOS).save(main, format="JPEG", quality=88)
    previews["main"] = main.name
    for spawn in spawns:
        x, y = spawn["level_xy"]
        px = (x + fp.size_m / 2) / fp.size_m * 2048
        py = (fp.size_m / 2 - y) / fp.size_m * 2048
        half = 256
        box = (int(px - half), int(py - half), int(px + half), int(py + half))
        crop = image.crop(box)
        path = level_root / f"{spawn['objectname']}.jpg"
        crop.resize((512, 512), Image.LANCZOS).save(path, format="JPEG", quality=85)
        previews[spawn["objectname"]] = path.name
    return previews


# ---------------------------------------------------------------------------
# The level
# ---------------------------------------------------------------------------


def terrain_material(
    mod_id: str,
    internal: str,
    family: str,
    groundmodel: str,
    level_url: str,
    base_prefix: str,
    macro_prefix: str,
    footprint_m: float,
    *,
    square_size_m: float = 1.0,
    detail_tile_m: float = DETAIL_TILE_M,
    detail_strength: float = 0.35,
) -> dict:
    """One TerrainMaterial in the v1.5 (base + macro + detail) layout of shipped levels.

    ``*TexSize`` on a material is documented as WORLD metres for one tile of the map
    (Torque's diffuseSize lineage), and the shipped 2048 m level the pack was read
    against sets its base size to 2048 while its texture set declares 2048 PIXELS. That
    level is sampled at 1 m, where metres and terrain squares are the same number, and
    the two readings cannot be told apart. They can here: Meteor Crater is 2048 m across
    sampled at 0.5 m, was given 2048, and the game drew the orthoimagery tiled two by
    two (mirrored) over the level - the engine divides the terrain's SAMPLE count by
    this number, not its world width. So every size is authored in metres and converted
    to squares: a no-op on the four maps sampled at 1 m, the fix on the two that are not.
    """

    persistent = pid(mod_id, f"terrainmaterial:{internal}")
    squares_per_m = 1.0 / float(square_size_m)
    base_size = round(footprint_m * squares_per_m)
    detail_size = round(detail_tile_m * squares_per_m, 6)
    macro_size = round(MACRO_TILE_M * squares_per_m, 6)
    tex = f"{level_url}/art/terrains"
    entry = {
        "name": f"{internal}-{persistent}",
        "internalName": internal,
        "class": "TerrainMaterial",
        "persistentId": persistent,
        "groundmodelName": groundmodel,
        "detailDistances": [0, 0, 50, 100],
        "detailDistAtten": [1, 1],
        "macroDistances": [0, 10, 100, 3000],
        "macroDistAtten": [0, 1],
        "baseColorDetailStrength": [detail_strength, detail_strength],
        "normalDetailStrength": [0.7, 0.3],
        "roughnessDetailStrength": [0.3, 0.3],
        "aoDetailStrength": [1, 1],
        "baseColorMacroStrength": [0.1, 0.25],
        "normalMacroStrength": [0.4, 0.5],
        "roughnessMacroStrength": [0.15, 0.5],
    }
    for channel, suffix in (
        ("baseColor", "b"),
        ("normal", "nm"),
        ("roughness", "r"),
        ("height", "h"),
        ("ao", "ao"),
    ):
        entry[f"{channel}BaseTex"] = f"{tex}/{base_prefix}_{suffix}.png"
        entry[f"{channel}BaseTexSize"] = base_size
        entry[f"{channel}DetailTex"] = f"{tex}/t_{internal}_{suffix}.png"
        entry[f"{channel}DetailTexSize"] = detail_size
        entry[f"{channel}MacroTex"] = f"{tex}/{macro_prefix}_{suffix}.png"
        entry[f"{channel}MacroTexSize"] = macro_size
    return entry


def enforce_bed_contrast(
    colour,
    layer,
    materials,
    surfaces,
    texel_m: float,
    factor: float,
    margin_min: float = 0.55,
    ceiling: float = 0.60,
):
    """Where a 100 m stretch of bed is not ``factor`` lighter than the ground within
    6 m of it (the ground the eye compares the bed with, the band ``road_contrast``
    measures), the ground within 20 m is darkened by the missing amount, grain kept,
    down to ``margin_min`` of itself, and what the margin cannot give the bed takes
    as a floor: bed = max(bed, factor x near ground), per window."""

    names = {cfg.get("terrain_material") for cfg in surfaces.values()} & set(materials)
    if not names or colour is None:
        return colour
    from PIL import Image
    from scipy import ndimage

    n = colour.shape[0]
    layer_c = layer
    if layer.shape[0] != n:
        layer_c = np.asarray(Image.fromarray(layer.astype("uint8")).resize((n, n), Image.NEAREST))
    out = colour.astype("float32")
    bed = np.isin(layer_c, [materials.index(name) for name in names])
    if not bed.any():
        return colour
    near = _near_band(bed, texel_m)
    margin = ndimage.binary_dilation(bed, iterations=max(2, int(20.0 / texel_m))) & ~bed
    win = max(3, int(100.0 / texel_m))
    bed_f = bed.astype("float32")
    near_f = near.astype("float32")

    def local_mean(lum, weight):
        return ndimage.uniform_filter(lum * weight, size=win, mode="nearest") / np.maximum(
            ndimage.uniform_filter(weight, size=win, mode="nearest"), 1e-4
        )

    lum = out.mean(axis=-1) / 255.0
    near_mean0 = local_mean(lum, near_f)
    near_sq0 = local_mean(lum * lum, near_f)
    # The margin is judged by its pale side too (the same reference the lift below
    # and road_contrast use): a stippled fell-field whose mean the bed clears by
    # 14 % still hides the bed among its pale fines.
    pale0 = near_mean0 + 0.9 * np.sqrt(np.maximum(near_sq0 - near_mean0 * near_mean0, 0.0))
    bed0 = local_mean(lum, bed_f)
    ratio = np.minimum(bed0 / np.maximum(near_mean0, 1e-4), bed0 / np.maximum(pale0, 1e-4))
    del near_mean0, near_sq0, pale0, bed0
    needed = np.clip(ratio / factor, margin_min, 1.0).astype("float32")
    needed = ndimage.gaussian_filter(needed, max(1.0, 10.0 / texel_m))
    # The darkening tapers linearly from the bed's edge to nothing at 20 m (a
    # plateau of darkening with a step at its outer edge read as a dark corridor).
    dist = ndimage.distance_transform_edt(~bed) * texel_m
    fade = np.clip(1.0 - dist / 20.0, 0.0, 1.0).astype("float32") * margin
    scale = 1.0 - (1.0 - needed) * fade
    out = out * scale[..., None]
    # The floor on the bed: on pale ground (the plateau's fines, a lit fan, the
    # near-white rim) the darkened margin still leaves the bed short, so the bed
    # comes up to ``factor`` x the near ground, per window, re-measured after each
    # pass against the same band ``road_contrast`` reports (the window means are
    # already 100 m smooth, so the lift needs no blur of its own).
    # The reference is the margin's pale side (its mean plus two thirds of its
    # spread, about its upper quartile): a shelf road has an olive bank above and
    # pale scree below, and a bed lighter than their average vanished against the
    # scree. Nothing is lifted past ``ceiling`` (0.60 sRGB: the game's snow line).
    for _pass in range(5):
        lum2 = out.mean(axis=-1) / 255.0
        near_mean = local_mean(lum2, near_f)
        near_sq = local_mean(lum2 * lum2, near_f)
        near_pale = near_mean + 0.9 * np.sqrt(np.maximum(near_sq - near_mean * near_mean, 0.0))
        bed_now = np.maximum(local_mean(lum2, bed_f), 1e-4)
        lift = np.clip(factor * 1.01 * near_pale / bed_now, 1.0, 1.4)
        lift = np.minimum(lift, np.maximum(ceiling / bed_now, 1.0)).astype("float32")
        if float(lift.max()) <= 1.005:
            break
        out = np.clip(out * np.where(bed, lift, 1.0)[..., None], 0, 255)
    return np.clip(out, 0, 255).astype("uint8")


def _near_band(bed: np.ndarray, texel_m: float) -> np.ndarray:
    """The ground the eye compares a bed with: 2-8 m off it (the 2 m feather of the
    bed's paint excluded)."""

    from scipy import ndimage

    outer = ndimage.binary_dilation(bed, iterations=max(2, int(8.0 / texel_m)))
    inner = ndimage.binary_dilation(bed, iterations=max(1, int(2.0 / texel_m)))
    return outer & ~inner


def refill_match(
    colour_u8,
    refill: np.ndarray,
    texel_m: float,
    *,
    bed: np.ndarray | None = None,
    min_area_m2: float = 400.0,
    max_lum_dev: float = 0.05,
    max_chroma_dev: float = 0.02,
) -> np.ndarray:
    """Bring every refilled field on the finished base to its own ring of open ground:
    its mean luminance to within ``max_lum_dev`` and its mean on both chroma axes
    (excess green and blue-minus-red) to within ``max_chroma_dev``, feathered 3 m
    inside its edge.

    The de-lighting matches a field to its ring at the moment it fills it, but every
    later stage moves the two apart again: the incidence flat-field corrects the lit
    ring and (rightly) leaves the refilled cells alone, and the layer pulls work on
    layer means. This is the last word, on the pixels the game draws."""

    from scipy import ndimage

    n = colour_u8.shape[0]
    if refill.shape[0] != n:
        from PIL import Image

        refill = np.asarray(Image.fromarray(refill.astype("uint8")).resize((n, n), Image.NEAREST))
    fields = (refill == 1) | (refill == 2)
    if not fields.any():
        return colour_u8
    forest = (refill == 3) | (refill == 4)
    ring_ok = (refill == 0) & ~ndimage.binary_dilation(
        forest, iterations=max(1, int(10.0 / texel_m))
    )
    on_bed = None
    if bed is not None:
        if bed.shape[0] != n:
            from PIL import Image

            bed = (
                np.asarray(Image.fromarray(bed.astype("uint8") * 255).resize((n, n), Image.NEAREST))
                > 127
            )
        ring_ok &= ~ndimage.binary_dilation(bed, iterations=max(1, int(6.0 / texel_m)))
        # The painted bed keeps the contrast the stage before it just enforced.
        on_bed = bed
    del forest
    labels, count = ndimage.label(fields)
    if not count:
        return colour_u8
    out = colour_u8.astype("float32") / 255.0
    min_cells = max(16, int(min_area_m2 / (texel_m * texel_m)))
    pad = int(32.0 / texel_m)
    for sl, k in zip(ndimage.find_objects(labels), range(1, count + 1), strict=False):
        if sl is None:
            continue
        r0, r1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, n)
        c0, c1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, n)
        field = labels[r0:r1, c0:c1] == k
        if int(field.sum()) < min_cells:
            continue
        dist = ndimage.distance_transform_edt(~field) * texel_m
        ring = (dist > 10.0) & (dist <= 30.0) & ring_ok[r0:r1, c0:c1]
        if int(ring.sum()) < 50:
            continue
        inner = ndimage.binary_erosion(field, iterations=max(1, int(6.0 / texel_m)))
        interior = inner if inner.sum() >= 20 else field
        block = out[r0:r1, c0:c1]
        f_mean = block[interior].reshape(-1, 3).mean(axis=0)
        r_mean = block[ring].reshape(-1, 3).mean(axis=0)
        # Feathered 3 m inside the field's edge, so the correction has no step at it.
        inside_d = ndimage.distance_transform_edt(field) * texel_m
        w = np.clip(inside_d / 3.0, 0.0, 1.0).astype("float32")
        w = (w * w * (3.0 - 2.0 * w)) * field
        if on_bed is not None:
            w = w * ~on_bed[r0:r1, c0:c1]
        delta = np.zeros(3, dtype="float64")
        for axis in ("exg", "br"):
            if axis == "exg":
                own = 2 * f_mean[1] - f_mean[0] - f_mean[2]
                theirs = 2 * r_mean[1] - r_mean[0] - r_mean[2]
            else:
                own = f_mean[2] - f_mean[0]
                theirs = r_mean[2] - r_mean[0]
            excess = float(own - theirs)
            over = math.copysign(max(abs(excess) - max_chroma_dev, 0.0), excess)
            if over == 0.0:
                continue
            step = over / (3.0 if axis == "exg" else 1.0)
            step = float(np.clip(step, -0.08, 0.08))
            if axis == "exg":
                delta += np.array([step * 0.5, -step, step * 0.5])
            else:
                delta += np.array([step * 0.5, 0.0, -step * 0.5])
        ratio = float(f_mean.mean() / max(float(r_mean.mean()), 1e-4))
        want = float(np.clip(ratio, 1.0 - max_lum_dev, 1.0 + max_lum_dev))
        gain = float(np.clip(want / max(ratio, 1e-4), 0.7, 1.4))
        block += delta.astype("float32")[None, None, :] * w[..., None]
        out[r0:r1, c0:c1] = block * (1.0 + (gain - 1.0) * w)[..., None]
        del field, dist, ring, inner, block, w, inside_d
    return np.clip(out * 255.0, 0, 255).astype("uint8")


def refill_check(
    colour_u8,
    refill: np.ndarray,
    texel_m: float,
    *,
    min_area_m2: float = 1000.0,
    top: int = 25,
    bed: np.ndarray | None = None,
) -> dict | None:
    """Every refilled field (cast shadow or snow) on the shipped base against its own
    10-30 m ring of open, unrefilled ground: luminance ratio, blue-minus-red
    difference and the under-10 m grain ratio (the field's interior 6 m in over the
    ring), for the ``top`` largest fields over ``min_area_m2``. Measured last, after
    every pull and the bed paint, on the image the game draws."""

    from PIL import Image
    from scipy import ndimage

    n = colour_u8.shape[0]
    if refill.shape[0] != n:
        refill = np.asarray(Image.fromarray(refill.astype("uint8")).resize((n, n), Image.NEAREST))
    # The fields are the terrain's cast shadows (1) and the snow (2); a crown's
    # shadow in a forest gap (3) and the crowns themselves (4) are neither a field
    # nor open ground for a ring.
    filled = refill > 0
    # The ring is the open ground the refill borrowed from: unrefilled, and 10 m
    # clear of any crown or gap shadow (the forest floor between crowns is
    # neither the field's reference nor what the refill was matched to).
    forest = (refill == 3) | (refill == 4)
    ring_ok = ~filled & ~ndimage.binary_dilation(forest, iterations=max(1, int(10.0 / texel_m)))
    del forest
    if bed is not None:
        # Nor the painted road bed and its 6 m corridor (the ring is ground).
        if bed.shape[0] != n:
            bed = (
                np.asarray(Image.fromarray(bed.astype("uint8") * 255).resize((n, n), Image.NEAREST))
                > 127
            )
        ring_ok &= ~ndimage.binary_dilation(bed, iterations=max(1, int(6.0 / texel_m)))
    labels, count = ndimage.label((refill == 1) | (refill == 2))
    if not count:
        return None
    index = np.arange(1, count + 1)
    areas = ndimage.sum(filled.astype("float32"), labels, index) * texel_m * texel_m
    order = [int(i) for i in np.argsort(-areas)[:top] if areas[i] >= min_area_m2]
    if not order:
        return None
    rgb = colour_u8.astype("float32") / 255.0
    lum = rgb.mean(axis=-1)
    br = rgb[..., 2] - rgb[..., 0]
    # The green axis as well: a refill matched on luminance and blue-to-red still
    # came back a tenth greener than the meadow round it.
    exg = 2.0 * rgb[..., 1] - rgb[..., 0] - rgb[..., 2]
    fine = lum - ndimage.uniform_filter(lum, size=max(3, int(10.0 / texel_m)), mode="nearest")
    del rgb
    half = n * texel_m / 2.0
    pad = int(32.0 / texel_m)
    fields = []
    for i in order:
        lab = i + 1
        rows, cols = np.nonzero(labels == lab)
        r0, r1 = max(rows.min() - pad, 0), min(rows.max() + pad + 1, n)
        c0, c1 = max(cols.min() - pad, 0), min(cols.max() + pad + 1, n)
        field = labels[r0:r1, c0:c1] == lab
        interior = ndimage.binary_erosion(field, iterations=max(1, int(6.0 / texel_m)))
        # And the painted bed is not part of the field, for the same reason it is not
        # part of the ring. `refill_match` already refuses to correct a bed cell inside
        # a field - it zeroes its feather there, so the bed keeps the contrast the stage
        # before it just enforced - while this measured those same cells as if they were
        # ground. Whichever way the bed sits against the shadow, the match cannot move
        # those texels by design, so counting them here asks for something no fix can
        # deliver: the ratio barely moves however hard the ground around them is lifted,
        # and the gate reads that as the match having failed. Measured on the shipped
        # Meteor Crater level, the 2,973 m2 field this gate reports at (-35.3, 670.3) is
        # 84.4% road bed, on a level that is 1.16% road bed overall. It is a shadow on a
        # road, not an unlifted field.
        # The erosion runs first, and on an elongated field it can take everything: at
        # meteor_crater's 0.5 m texel this is twelve iterations, a 6 m band off every
        # boundary, and a road shadow at the 1000 m2 floor is about 12 m by 83 m. So
        # settle which population is in use BEFORE asking anything about the bed;
        # measuring the share on an interior the numbers do not rest on was how a field
        # the exclusion could not reach came to look like a field with no road near it.
        # Whether the numbers below rest on the eroded interior or on the whole
        # component. The fallback is not a failure - it is the old reading, deliberately
        # - but it is a different measurement and the handoff should say which.
        interior_eroded = bool(interior.sum() >= 20)
        if not interior_eroded:
            interior = field
        bed_share: float | None = None
        on_road_bed = False
        if bed is not None:
            not_bed = ~bed[r0:r1, c0:c1]
            bed_share = float((interior & ~not_bed).sum()) / int(interior.sum())
            # Below 20 cells the remainder is noise, so the field keeps its old reading.
            if (interior & not_bed).sum() >= 20:
                interior = interior & not_bed
            elif bed_share >= 0.5:
                # There is no ground left in this field: it IS a road. `refill_match`
                # refuses to correct a bed cell by design - it zeroes its feather there
                # - so every ratio below compares asphalt against a bed-free ring and
                # reports the match as having failed at something it is forbidden to
                # attempt. No fix moves those texels. It stays in `largest` with the
                # reason on it and comes out of the population the gates read.
                on_road_bed = True
            del not_bed
        dist = ndimage.distance_transform_edt(~field) * texel_m
        ring = (dist > 10.0) & (dist <= 30.0) & ring_ok[r0:r1, c0:c1]
        if ring.sum() < 50:
            continue
        l_in, l_ring = lum[r0:r1, c0:c1][interior], lum[r0:r1, c0:c1][ring]
        f_in, f_ring = fine[r0:r1, c0:c1][interior], fine[r0:r1, c0:c1][ring]
        fields.append(
            {
                "area_m2": round(float(areas[i]), 1),
                "center_xy": [
                    round(float(cols.mean() * texel_m - half), 1),
                    round(float(half - rows.mean() * texel_m), 1),
                ],
                "kind": "snow" if int(np.median(refill[rows, cols])) == 2 else "shadow",
                "lum_ratio": round(float(l_in.mean() / max(l_ring.mean(), 1e-4)), 3),
                "br_diff": round(
                    float(br[r0:r1, c0:c1][interior].mean() - br[r0:r1, c0:c1][ring].mean()), 3
                ),
                "exg_diff": round(
                    float(exg[r0:r1, c0:c1][interior].mean() - exg[r0:r1, c0:c1][ring].mean()), 3
                ),
                "grain_ratio": round(float(f_in.std() / max(f_ring.std(), 1e-4)), 3),
                # The population every ratio above rests on. `area_m2` is the component
                # BEFORE the erosion and the bed exclusion, so it is an upper bound and
                # not the sample size; `grain_ratio` in particular is a standard
                # deviation over exactly these texels.
                "interior_texels": int(interior.sum()),
                # False when the erosion left under 20 cells and the whole component was
                # used instead - bed included, so `bed_fraction` describes nothing that
                # was excluded.
                "interior_eroded": interior_eroded,
                # How much of the population above is road the match is not allowed to
                # touch, taken before the exclusion. None only when the caller passed no
                # bed at all, so 0.0 now means "no road here" and nothing else.
                "bed_fraction": None if bed_share is None else round(bed_share, 3),
                # True when that share left no ground to measure. Every ratio on this
                # field is asphalt against a bed-free ring, so the gates skip it.
                "on_road_bed": on_road_bed,
            }
        )
    if not fields:
        return None
    # The fields a match could have moved. A field that is all road bed is reported in
    # `largest` and counted here, but no summary statistic rests on it - see
    # `on_road_bed` above. `fields` is the size of the population the statistics come
    # from, so a build where the exclusion runs away leaves a number that says so
    # rather than a quietly smaller sample.
    measured = [f for f in fields if not f["on_road_bed"]]
    summary: dict = {
        "fields": len(measured),
        "fields_on_road_bed": len(fields) - len(measured),
        "largest": fields,
    }
    if not measured:
        return summary
    lum_r = np.array([f["lum_ratio"] for f in measured])
    grain = np.array([f["grain_ratio"] for f in measured])
    summary.update(
        {
            "lum_ratio_min": round(float(lum_r.min()), 3),
            "lum_ratio_max": round(float(lum_r.max()), 3),
            "lum_ratio_p10": round(float(np.percentile(lum_r, 10)), 3),
            "grain_ratio_p10": round(float(np.percentile(grain, 10)), 3),
            "br_diff_max_abs": round(float(np.abs([f["br_diff"] for f in measured]).max()), 3),
            "exg_diff_max_abs": round(float(np.abs([f["exg_diff"] for f in measured]).max()), 3),
        }
    )
    return summary


def road_contrast(colour, layer, materials, surfaces, texel_m: float) -> dict:
    """Bed luminance over the luminance of each layer within 6 m either side of it:
    the number that says whether the road reads on the ground at all."""

    names = {cfg.get("terrain_material") for cfg in surfaces.values()} & set(materials)
    if not names or colour is None:
        return {}
    from PIL import Image
    from scipy import ndimage

    n = colour.shape[0]
    layer_c = layer
    if layer.shape[0] != n:
        layer_c = np.asarray(Image.fromarray(layer.astype("uint8")).resize((n, n), Image.NEAREST))
    lum = colour.astype("float32").mean(axis=-1) / 255.0
    bed = np.isin(layer_c, [materials.index(name) for name in names])
    if not bed.any():
        return {}
    near = _near_band(bed, texel_m)
    bed_lum = float(lum[bed].mean())
    out = {"bed": round(bed_lum, 4)}
    # Along the road in 100 m windows: the local bed over the local margin, so a
    # pale summit is not hidden by a dark valley in the layer mean.
    win = max(3, int(100.0 / texel_m))
    bed_f = bed.astype("float32")
    near_f = near.astype("float32")
    bed_local = ndimage.uniform_filter(lum * bed_f, size=win, mode="nearest") / np.maximum(
        ndimage.uniform_filter(bed_f, size=win, mode="nearest"), 1e-4
    )
    near_local = ndimage.uniform_filter(lum * near_f, size=win, mode="nearest") / np.maximum(
        ndimage.uniform_filter(near_f, size=win, mode="nearest"), 1e-4
    )
    enough = (ndimage.uniform_filter(near_f, size=win, mode="nearest") > 0.01) & bed
    ratios = (bed_local / np.maximum(near_local, 1e-4))[enough]
    if ratios.size:
        out["windows"] = {
            "p05": round(float(np.percentile(ratios, 5)), 3),
            "p50": round(float(np.percentile(ratios, 50)), 3),
            "min": round(float(ratios.min()), 3),
        }
        # And against the margin's pale side (mean plus two thirds of its spread):
        # a bed the eye loses against pale scree scores under 1 here.
        near_sq = ndimage.uniform_filter(lum * lum * near_f, size=win, mode="nearest") / np.maximum(
            ndimage.uniform_filter(near_f, size=win, mode="nearest"), 1e-4
        )
        pale = near_local + 0.67 * np.sqrt(np.maximum(near_sq - near_local * near_local, 0.0))
        pale_ratios = (bed_local / np.maximum(pale, 1e-4))[enough]
        out["windows_vs_pale"] = {
            "p05": round(float(np.percentile(pale_ratios, 5)), 3),
            "min": round(float(pale_ratios.min()), 3),
        }
    for index, name in enumerate(materials):
        if name in names:
            continue
        cells = near & (layer_c == index)
        if cells.sum() < 2000:
            continue
        ground = float(lum[cells].mean())
        out[name] = {"margin": round(ground, 4), "ratio": round(bed_lum / max(ground, 1e-4), 3)}
    return out


def paint_road_beds(
    colour: np.ndarray, layer: np.ndarray, materials: list[str], palette: dict, surfaces: dict
) -> np.ndarray:
    """Paint the base colour under the carved road beds with the bed material's colour.

    The photograph shows cars, paint lines and shadows on the roads; the level shows a
    road. The bed's own colour (the palette base, in sRGB) with a little grain replaces
    the imagery there, feathered over two texels, so the decal and the ground agree.
    """

    names = {cfg.get("terrain_material") for cfg in surfaces.values()} & set(materials)
    if not names or colour is None:
        return colour
    from PIL import Image
    from scipy import ndimage

    n = colour.shape[0]
    out = colour.astype("float32")
    rng = np.random.default_rng(3)
    grain = None
    for name in sorted(names):
        mask = layer == materials.index(name)
        if not mask.any():
            continue
        if mask.shape[0] != n:
            mask = (
                np.asarray(
                    Image.fromarray(mask.astype("uint8") * 255).resize((n, n), Image.BILINEAR)
                )
                > 127
            )
        weight = ndimage.gaussian_filter(mask.astype("float32"), 1.0)[..., None]
        if grain is None:
            grain = rng.uniform(0.9, 1.1, size=(n, n, 1)).astype("float32")
        # The palette base is already sRGB (the tone contract): paint it as it is.
        base = np.asarray(palette[name]["base"], dtype="float64") * 255.0
        out = out * (1.0 - weight) + base.astype("float32")[None, None, :] * grain * weight
    return np.clip(out, 0, 255).astype("uint8")


def build_level(
    spec,
    example_root: Path,
    fp,
    dem: np.ndarray,
    layer: np.ndarray,
    encoded: hm.Encoded,
    terrain_stats: dict,
    *,
    detected_objects: list[dict] | None = None,
) -> dict:
    mod_id = spec.MOD_ID
    site = spec.SITE
    res = float(site["square_size_m"])
    size = int(site["size_px"])
    base_px = int(site.get("base_tex_px", BASE_TEX_PX))
    # One size for the whole detail array: the site's, else the largest tile any
    # palette entry asks for (the engine stacks the detail maps into one array).
    palette_sizes = [int(p.get("size", DETAIL_TEX_PX)) for p in spec.PALETTE.values()]
    detail_px = int(site.get("detail_tex_px", max([DETAIL_TEX_PX, *palette_sizes])))
    detail_tile_m = float(site.get("detail_tile_m", DETAIL_TILE_M))
    imagery_spec = getattr(spec, "IMAGERY", None)
    objects_spec = getattr(spec, "OBJECTS", None)
    forest_spec = getattr(spec, "FOREST", None)
    level_root = example_root / "mod" / "levels" / mod_id
    if level_root.exists():
        import shutil

        shutil.rmtree(level_root)
    level_root.mkdir(parents=True)
    level_url = f"/levels/{mod_id}"
    data_root = example_root / "data"
    frame = Frame(fp, dem, res, encoded.min_elevation_m)
    materials = list(spec.TERRAIN["materials"])
    report: dict = {"files": {}}

    # --- terrain binary + metadata + heightmap PNG ---------------------------------
    hm.write_ter(
        level_root / "theTerrain.ter",
        encoded.heights_u16_south_up,
        encoded.layer_u8_south_up,
        materials,
    )
    hm.write_png16(level_root / "theTerrain.terrainheightmap.png", encoded.heights_u16_north_up)
    write_json(
        level_root / "theTerrain.terrain.json",
        {
            "version": 9,
            "datafile": f"{level_url}/theTerrain.ter",
            "heightmapImage": f"{level_url}/theTerrain.terrainheightmap.png",
            "size": size,
            "binaryFormat": (
                "version(char), size(unsigned int), "
                "heightMap(heightMapSize * heightMapItemSize), "
                "layerMap(layerMapSize * layerMapItemSize), materialNames"
            ),
            "heightMapSize": size * size,
            "heightMapItemSize": 2,
            "layerMapSize": size * size,
            "layerMapItemSize": 1,
            "materials": materials,
        },
    )

    # --- textures ----------------------------------------------------------------
    terrains_dir = level_root / "art" / "terrains"
    base_prefix = "t_base"
    macro_prefix = "t_macro"
    cached = data_root / "terrain" / "colour.png"
    if cached.is_file() and (data_root / "terrain" / "imagery.json").is_file():
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None
        colour_full = np.asarray(Image.open(cached).convert("RGB"))
        imagery_stats = json.loads(
            (data_root / "terrain" / "imagery.json").read_text(encoding="utf-8")
        )
    else:
        colour_full, imagery_stats = conditioned_colour(
            dem, res, fp, data_root / "naip", imagery_spec
        )
        # Only the terrain stage's OBJECTS path caches a conditioned colour, so a map
        # that de-lights and has no OBJECTS spec lands here - and `delight` returns its
        # refilled-cell mask as the private `_refill_mask`, an ndarray the handoff JSON
        # cannot hold. The terrain stage pops it and saves it; do the same, so the
        # refill check below reads it from the same file either way.
        refill_mask = imagery_stats.pop("_refill_mask", None)
        if refill_mask is not None:
            terrain_dir = data_root / "terrain"
            terrain_dir.mkdir(parents=True, exist_ok=True)
            np.save(terrain_dir / "refill.npy", refill_mask.astype("uint8"))
            del refill_mask
    report["imagery"] = imagery_stats
    colour_full = paint_road_beds(
        colour_full, layer, materials, spec.PALETTE, getattr(spec, "ROADS", {}).get("surfaces", {})
    )
    pad_texture_file = data_root / "terrain" / "pad_texture.npy"
    if pad_texture_file.is_file():
        # A painted pad takes the flight's own grain back over its mean, so the lot
        # reads as asphalt with stall stripes rather than one flat fill.
        grain = np.load(pad_texture_file)
        if grain.shape[0] != colour_full.shape[0]:
            from PIL import Image

            grain = np.asarray(
                Image.fromarray(grain, mode="F").resize(
                    (colour_full.shape[1], colour_full.shape[0]), Image.BILINEAR
                )
            )
        colour_full = np.clip(colour_full.astype("float32") * grain[..., None], 0, 255).astype(
            "uint8"
        )
        del grain
    # The contract is one factor for every surface, or a factor per surface
    # ({"dirt": 1.06}: the two-tracks pale, the asphalt as dark as asphalt is).
    bed_factor = getattr(spec, "ROADS", {}).get("bed_lighter_than_ground") or 0.0
    all_surfaces = getattr(spec, "ROADS", {}).get("surfaces", {})
    by_surface = (
        {name: float(f) for name, f in bed_factor.items() if name in all_surfaces}
        if isinstance(bed_factor, dict)
        else {name: float(bed_factor) for name in all_surfaces}
        if float(bed_factor) > 0
        else {}
    )
    margin_min = float(getattr(spec, "ROADS", {}).get("bed_contrast_margin_min", 0.55))
    # The bed's ceiling in sRGB: the game's snow line on a grey alpine road (0.60),
    # higher on a desert plain whose ground already sits at 0.65.
    bed_ceiling = float(getattr(spec, "ROADS", {}).get("bed_ceiling", 0.60))

    def _enforce_beds(image):
        for name, factor in by_surface.items():
            image = enforce_bed_contrast(
                image,
                layer,
                materials,
                {name: all_surfaces[name]},
                fp.size_m / image.shape[0],
                factor,
                margin_min,
                bed_ceiling,
            )
        return image

    colour_full = _enforce_beds(colour_full)
    refill_file = data_root / "terrain" / "refill.npy"
    if refill_file.is_file() and colour_full is not None:
        # Every refilled field measured on the base the game draws, after every
        # later stage: the number that says whether a refill reads as its ground.
        bed_ids = [
            materials.index(cfg["terrain_material"])
            for cfg in all_surfaces.values()
            if cfg.get("terrain_material") in materials
        ]
        kinds = np.load(refill_file)
        bed_mask = np.isin(layer, bed_ids) if bed_ids else None
        texel = fp.size_m / colour_full.shape[0]
        colour_full = refill_match(colour_full, kinds, texel, bed=bed_mask)
        # A refilled field that touches a road takes the bed with it, which can put a
        # 100 m window back under contract after the enforcement already passed. The
        # contract is what ships, so it is enforced again here, last.
        colour_full = _enforce_beds(colour_full)
        check = refill_check(colour_full, kinds, texel, bed=bed_mask)
        del kinds
        if isinstance(report.get("imagery"), dict):
            report["imagery"]["refill_check"] = check
    if isinstance(bed_factor, dict):
        report["road_contrast"] = {
            name: road_contrast(
                colour_full,
                layer,
                materials,
                {name: all_surfaces[name]},
                fp.size_m / colour_full.shape[0],
            )
            for name in by_surface
        }
    else:
        report["road_contrast"] = road_contrast(
            colour_full, layer, materials, all_surfaces, fp.size_m / colour_full.shape[0]
        )
    # Resize to the base's own resolution HERE, so the numbers below are taken from the
    # same array build_base_set writes (it passes a matching array straight through).
    base_colour = colour_full
    if base_colour.shape[0] != base_px:
        from PIL import Image

        base_colour = np.asarray(
            Image.fromarray(colour_full).resize((base_px, base_px), Image.LANCZOS)
        )
    # Nothing reaches white, enforced on what SHIPS rather than in the middle of the
    # pipeline. `delight` already ends with this clamp, and it is not enough, for the
    # same reason the bed contract above is enforced twice: `delight` is not the last
    # writer of the base. `refill_match` lifts every refilled field toward its ring
    # after the clamp, `_enforce_beds` lifts a bed toward its margin, and the LANCZOS
    # resize overshoots on a hard edge - and the clamp leaves exactly one count of
    # margin (0.95 linear encodes to 249, the gate counts 250), so any of the three
    # re-breaks it. Measured on the shipped Factory Butte base, the resize alone puts
    # back 0.0016 on fb_caprock; the refill match put back far more than that, which is
    # how a map with an unconditional highlight ceiling shipped 5.6% of its caprock
    # blown out. The u8 -> linear -> u8 round trip is exactly lossless, so a texel under
    # the ceiling is not touched at all.
    # Scoped to the maps the gate scopes itself to: a level with no IMAGERY spec ships
    # the photograph as flown and nobody promised this of it.
    before_ceiling = None
    if getattr(spec, "IMAGERY", None):
        from . import imagery

        # Kept so the per-layer share below is measured on the array the clamp read.
        # Without it the clamp erases its own evidence: it caps every channel at 249
        # and the base's gate counts 250, so `clipped` reads zero on every map that
        # runs this, whatever the pipeline did upstream.
        # The cost is one more u8 base held alongside the clamped one and `_linear`,
        # about 50 MB at base_px 4096 against a peak near 250 MB. Freed with the stats
        # call below rather than held to the end of the stage, because the de-lighting
        # is where this pack meets its memory ceiling.
        before_ceiling = base_colour
        _linear, _over = imagery.clamp_highlights(imagery.srgb_to_linear(base_colour), 0.95)
        base_colour = imagery.linear_to_srgb_u8(_linear)
        del _linear
        if isinstance(report.get("imagery"), dict):
            # A large number here is not this clamp misbehaving, it is how much a later
            # stage lifted past the ceiling - which is worth seeing rather than silently
            # correcting.
            report["imagery"]["shipped_ceiling_fraction"] = round(_over, 6)
    build_base_set(
        dem,
        res,
        fp,
        data_root / "naip",
        terrains_dir,
        base_prefix,
        colour_full=base_colour,
        base_px=base_px,
    )
    report["base_colour"] = base_colour_stats(
        base_colour, layer, materials, before_ceiling=before_ceiling
    )
    del base_colour, before_ceiling
    texture_kit.build_set(
        terrains_dir,
        macro_prefix,
        "macro_clumpy",
        seed=7,
        size=MACRO_TEX_PX,
        base_rgb=[0.5, 0.5, 0.5],
    )
    tint_weight = float(imagery_spec.get("tint_from_imagery", 0.0)) if imagery_spec else 0.0
    layer_tints = {}
    if tint_weight > 0:
        from . import imagery

        layer_tints = imagery.layer_colour_stats(colour_full, layer, materials)
        report["layer_tints"] = layer_tints
    material_entries = {}
    texture_set_name = f"{mod_id}_TerrainTextureSet"
    material_entries[texture_set_name] = {
        "name": texture_set_name,
        "class": "TerrainMaterialTextureSet",
        "persistentId": pid(mod_id, "texture_set"),
        "baseTexSize": [base_px, base_px],
        "detailTexSize": [detail_px, detail_px],
        "macroTexSize": [MACRO_TEX_PX, MACRO_TEX_PX],
    }
    for internal in materials:
        palette = spec.PALETTE[internal]
        base_rgb = list(palette["base"])
        layer_weight = float(palette.get("tint_weight", tint_weight))
        if layer_weight > 0 and internal in layer_tints and not palette.get("keep_tint"):
            # The palette base is sRGB (the tone contract); the measured layer means
            # are linear light, so encode them before blending or the tint pulls every
            # material dark. A palette entry may set its own weight (a cliff whose
            # photograph is mostly shadow keeps more of its authored charcoal).
            measured = [max(float(m), 0.0) ** (1.0 / 2.2) for m in layer_tints[internal]]
            base_rgb = [
                round(b * (1 - layer_weight) + m * layer_weight, 4)
                for b, m in zip(base_rgb, measured, strict=True)
            ]
        texture_kit.build_set(
            terrains_dir,
            f"t_{internal}",
            palette["family"],
            seed=int(palette["seed"]),
            size=detail_px,
            rotate_deg=float(palette.get("rotate_deg", 0.0)),
            base_rgb=base_rgb,
        )
        groundmodel = palette.get("groundmodel") or GROUNDMODEL_BY_FAMILY[palette["family"]]
        entry = terrain_material(
            mod_id,
            internal,
            palette["family"],
            groundmodel,
            level_url,
            base_prefix,
            macro_prefix,
            fp.size_m,
            square_size_m=res,
            detail_tile_m=float(palette.get("tile_m", detail_tile_m)),
            detail_strength=float(palette.get("detail_strength", 0.35)),
        )
        material_entries[entry["name"]] = entry
    write_json(terrains_dir / "main.materials.json", material_entries)

    # --- road materials ------------------------------------------------------------
    road_dir = level_root / "art" / "road"
    surfaces = spec.ROADS.get("surfaces")
    road_specs = (
        {name: cfg["decal"] for name, cfg in surfaces.items()}
        if surfaces
        else {"legacy": spec.ROADS["material"]}
    )
    road_materials = {}
    for road_spec in road_specs.values():
        road_name = road_spec["name"]
        texture_kit.build_set(
            road_dir,
            road_name,
            road_spec["family"],
            seed=int(road_spec["seed"]),
            size=int(road_spec.get("size", 512)),
            base_rgb=road_spec["base"],
        )
        _feather_road_alpha(
            road_dir / f"{road_name}_b.png",
            edge_fraction=float(road_spec.get("edge_fraction", 0.18)),
        )
        road_materials[road_name] = {
            "name": road_name,
            "class": "Material",
            "mapTo": road_name,
            "persistentId": pid(mod_id, f"material:{road_name}"),
            "Stages": [
                {
                    "baseColorMap": f"{level_url}/art/road/{road_name}_b.png",
                    "normalMap": f"{level_url}/art/road/{road_name}_nm.png",
                    "roughnessMap": f"{level_url}/art/road/{road_name}_r.png",
                    "useAnisotropic": True,
                },
                {},
                {},
                {},
            ],
            "annotation": "DRIVABLE_ROAD",
            "materialTag0": "RoadAndPath",
            "materialTag1": "beamng",
            "translucent": True,
            "translucentBlendOp": "LerpAlpha",
            "translucentZWrite": False,
            "version": 1.5,
        }
    write_json(road_dir / "main.materials.json", road_materials)

    # --- spawns ------------------------------------------------------------------
    road_polylines = []
    # Gated on ROADS rather than on `surfaces`: a level whose roads are decals over
    # untouched ground paints no bed, so `ROADS["surfaces"]` is empty while the level
    # still has roads - Factory Butte writes 13 of them over 14.3 km. Gating on the bed
    # left `road_polylines` empty there, which silently disabled every consumer of it
    # (spawn snapping, trail features, and the stone clearance below) on exactly the
    # levels whose roads are not carved. Both consumers already test the list, so a
    # level with no ROADS at all is unaffected.
    _osm_roads = data_root / "osm" / "roads.json"
    if getattr(spec, "ROADS", None) and _osm_roads.is_file():
        from . import roads as road_tools

        road_polylines = road_tools.road_polylines(spec, fp, _osm_roads)
        if spec.ROADS.get("max_grade"):
            road_polylines, _cuts = road_tools.drop_cliff_segments(
                road_polylines,
                dem,
                res,
                fp.size_m,
                float(spec.ROADS["max_grade"]),
                min_length_m=float(spec.ROADS.get("cliff_cut_min_length_m", 100.0)),
            )
    features = []
    for entry in getattr(spec, "TRAIL_FEATURES", []) or []:
        fx, fy = frame.lonlat_to_level(entry["lon"], entry["lat"])
        inside = frame.inside(fx, fy, margin=0.0)
        nearest = None
        if inside and road_polylines:
            nearest = min(
                math.hypot(px - fx, py - fy)
                for road in road_polylines
                for px, py in _resample_polyline(road["points"], 2.0)
            )
        features.append(
            {
                "name": entry["name"],
                "source": entry.get("source", ""),
                "lat": entry["lat"],
                "lon": entry["lon"],
                "level_xy": [round(fx, 1), round(fy, 1)],
                "inside": bool(inside),
                "elevation_m": round(frame.height_at(fx, fy) + encoded.min_elevation_m, 1)
                if inside
                else None,
                "nearest_road_m": round(nearest, 1) if nearest is not None else None,
            }
        )
    report["trail_features"] = features
    spawns = []
    for entry in spec.SPAWNS:
        x, y = frame.lonlat_to_level(entry["lon"], entry["lat"])
        heading = float(entry.get("heading_deg", 0.0))
        snapped = False
        if entry.get("snap_to_road") and road_polylines:
            snap = snap_to_road(
                x,
                y,
                road_polylines,
                frame,
                float(entry.get("snap_radius_m", 60.0)),
                prefer_heading=float(entry["heading_deg"]) if "heading_deg" in entry else None,
            )
            if snap is not None:
                x, y, heading = snap
                snapped = True
        if not frame.inside(x, y, margin=20.0):
            raise ValueError(f"{mod_id}: spawn {entry['name']} lies outside the footprint")
        spawns.append(
            {
                "objectname": f"spawn_{entry['name']}",
                "label": entry.get("label") or entry["name"].replace("_", " ").title(),
                "level_xy": (round(x, 2), round(y, 2)),
                "z": round(frame.height_at(x, y) + 0.5, 2),
                "heading_deg": round(heading, 1),
                "default": bool(entry.get("default", False)),
                "lat": entry["lat"],
                "lon": entry["lon"],
                "snapped_to_road": snapped,
                # A staging spawn (the two ends of a climb) promises level ground;
                # a spawn at the Steps is on 20 % ledges because that is the place.
                "level_ground": bool(entry.get("level_ground", False)),
                # The ground the vehicle line rests on, not just the point under it.
                "apron": spawn_apron(frame, x, y, heading),
            }
        )
    default_spawn = next((s for s in spawns if s["default"]), spawns[0])
    spawn_clear = [(s["level_xy"][0], s["level_xy"][1]) for s in spawns]

    # --- roads -------------------------------------------------------------------
    if surfaces:
        roads, road_stats = build_surface_roads(spec, frame, data_root / "osm" / "roads.json", fp)
    else:
        roads, road_stats = build_roads(spec, frame, data_root / "osm" / "roads.json")

    # --- buildings ---------------------------------------------------------------
    # Before anything is scattered: the mask a roof makes is what keeps a boulder and
    # a spruce off it.
    built: dict = {"items": [], "materials": {}, "mask": None, "stats": {"count": 0}}
    if getattr(spec, "BUILDINGS", None):
        from . import buildings as bd

        canopy_file = data_root / "pointcloud" / "canopy.npz"
        if canopy_file.is_file():
            with np.load(canopy_file) as npz:
                built = bd.build(
                    spec,
                    fp,
                    level_root,
                    level_url,
                    lambda key: pid(mod_id, key),
                    dem=dem,
                    dsm=npz["dsm"],
                    ground=npz["ground"],
                    base_rgb=colour_full,
                    res=res,
                    data_root=data_root,
                    log=print,
                )

    # --- cliffs ---------------------------------------------------------------------
    # Modelled before anything is scattered, because the mask the walls return is what
    # keeps a stone from hovering on a face that is no longer where the terrain is.
    # This stage is NOT gated on OBJECTS: a map can have walls and no scatter, and the
    # whole point of the pass is that a map which declared nothing stops shipping empty.
    cliff: dict = {"items": [], "materials": {}, "mask": None, "stats": {"bands_modelled": 0}}
    if getattr(spec, "CLIFFS", None):
        from . import cliffs as cf

        cliff = cf.build(
            spec,
            fp,
            level_root,
            level_url,
            lambda key: pid(mod_id, key),
            dem=dem,
            res=res,
            min_elevation=encoded.min_elevation_m,
            layer=layer,
            materials=materials,
            log=print,
        )

    # --- placed objects: rocks, shrubs, the forest ------------------------------------
    placed: list[dict] = []
    trees: list[dict] = []
    forest_stats: dict = {}
    catalogue: dict = {}
    if objects_spec or forest_spec:
        from . import objects as ob
        from . import scene_objects, vegetation

        rock_materials: set[str] = set()
        rock_by_layer = (objects_spec or {}).get("rock_material_by_layer", {})
        size_rules = (objects_spec or {}).get("rock_material_by_size", {})
        if objects_spec and detected_objects:
            rock_layers = objects_spec.get("rock_layers")
            rock_layer_ids = {materials.index(n) for n in rock_layers} if rock_layers else None
            placed = ob.place_objects(
                detected_objects,
                dem,
                res,
                fp.size_m,
                encoded.min_elevation_m,
                seed=int(objects_spec.get("seed", 1)),
                max_rocks=int(objects_spec.get("max_rocks", 6000)),
                max_shrubs=int(objects_spec.get("max_shrubs", 6000)),
                layer=layer,
                rock_layers=rock_layer_ids,
            )
            default_rock = (
                next(iter(rock_by_layer.values()), "rock_talus") if rock_by_layer else "rock_talus"
            )
            size_cap = (objects_spec or {}).get("max_rock_size_by_layer", {})
            kept = []
            for obj in placed:
                if obj["kind"] == "rock":
                    r = int(min(max((fp.size_m / 2 - obj["y"]) / res, 0), size - 1))
                    c = int(min(max((obj["x"] + fp.size_m / 2) / res, 0), size - 1))
                    under = materials[int(layer[r, c])]
                    obj["material"] = rock_by_layer.get(under, default_rock)
                    # A block wider than a layer's threshold is another rock: the
                    # house-sized blocks on the Moenkopi crest are Kaibab.
                    for at_least, material in sorted(size_rules.get(under, []), key=lambda r: r[0]):
                        if max(obj["size"][:2]) >= float(at_least):
                            obj["material"] = material
                    # A bump wider than this layer carries as a rock (a hummock on the
                    # plain) is not placed: the photographs have house-sized blocks only
                    # on the rim.
                    if under in size_cap and max(obj["size"][:2]) > float(size_cap[under]):
                        continue
                    rock_materials.add(obj["material"])
                kept.append(obj)
            placed = kept
        scatter = (objects_spec or {}).get("scatter")
        if scatter:
            densities = {
                materials.index(name): float(per_ha)
                for name, per_ha in scatter.items()
                if name in materials
            }
            extra_rocks = ob.scatter_rocks(
                layer,
                dem,
                res,
                fp.size_m,
                encoded.min_elevation_m,
                densities,
                seed=int(objects_spec.get("seed", 1)) + 5,
                size_range=tuple(objects_spec.get("scatter_size_m", (0.3, 1.2))),
                toe_bias=float(objects_spec.get("toe_bias", 1.0)),
                toe_window_m=float(objects_spec.get("toe_window_m", 15.0)),
                toe_threshold_m=float(objects_spec.get("toe_threshold_m", 1.5)),
                max_count=int(objects_spec.get("scatter_max", 20000)),
                min_elevation_by_layer={
                    materials.index(name): float(elev)
                    for name, elev in (objects_spec.get("scatter_min_elevation") or {}).items()
                    if name in materials
                },
            )
            default_rock = (
                next(iter(rock_by_layer.values()), "rock_talus") if rock_by_layer else "rock_talus"
            )
            # The scattered stones of a layer may be another rock than its lidar
            # blocks (the summit's outcrop blocks are iron-stained, its scree is
            # not).
            scatter_rock = {**rock_by_layer, **objects_spec.get("scatter_rock_material", {})}
            for obj in extra_rocks:
                r = int(min(max((fp.size_m / 2 - obj["y"]) / res, 0), size - 1))
                c = int(min(max((obj["x"] + fp.size_m / 2) / res, 0), size - 1))
                obj["material"] = scatter_rock.get(materials[int(layer[r, c])], default_rock)
                rock_materials.add(obj["material"])
            placed += extra_rocks
        if cliff["mask"] is not None and cliff["mask"].any() and placed:
            # A stone placed from the DEM on a wall the cliff stage has just replaced
            # hangs in the air in front of the new rock, because the surface it was
            # seated on is no longer the surface. The toe keeps its talus: the mask is
            # the face itself, not the ground under it.
            face = cliff["mask"]
            before = len(placed)
            placed = [
                obj
                for obj in placed
                if not face[
                    int(min(max((fp.size_m / 2 - obj["y"]) / res, 0), size - 1)),
                    int(min(max((obj["x"] + fp.size_m / 2) / res, 0), size - 1)),
                ]
            ]
            report["objects_cleared_from_cliffs"] = before - len(placed)
        road_clear_m = float((objects_spec or {}).get("road_clear_m", 0.0))
        if road_clear_m > 0:
            from scipy import ndimage

            # The bed is the painted road surface, and a level whose roads are decals
            # over untouched ground has none - `ROADS["surfaces"]` is empty and no layer
            # carries a bed material. This used to be gated on `surfaces`, so on such a
            # level `road_clear_m` was accepted, reported nothing and removed nothing.
            # Measured on Factory Butte's terrain, that silently left 188 of its 54,040
            # scattered stones inside 3 m of a centreline, 62 of them 0.5 m or wider, on
            # 14.3 km of road the level exists to be driven. So where there is no bed,
            # clear against the centrelines themselves, which is what the spec key means
            # either way.
            bed_ids = [
                materials.index(cfg["terrain_material"])
                for cfg in (surfaces or {}).values()
                if cfg.get("terrain_material") in materials
            ]
            if bed_ids:
                bed = ndimage.binary_dilation(
                    np.isin(layer, bed_ids), iterations=max(1, round(road_clear_m / res))
                )
            elif road_polylines:
                from . import roads as _road_tools

                bed = _road_tools.centreline_mask(
                    road_polylines, res, fp.size_m, size, road_clear_m
                )
            else:
                # No bed and no centrelines: say so rather than reporting a clearance of
                # zero, which is what this whole change exists to stop happening.
                bed = None
            before = len(placed)
            if bed is not None:
                placed = [
                    obj
                    for obj in placed
                    if obj["kind"] != "rock"
                    or not bed[
                        int(min(max((fp.size_m / 2 - obj["y"]) / res, 0), size - 1)),
                        int(min(max((obj["x"] + fp.size_m / 2) / res, 0), size - 1)),
                    ]
                ]
            report["rocks_cleared_from_roads"] = before - len(placed)
            report["road_clearance_from"] = (
                "bed"
                if bed_ids
                else "centrelines"
                if bed is not None
                else "nothing to clear against"
            )
        shrub_from_imagery = (objects_spec or {}).get("shrubs_from_imagery")
        if shrub_from_imagery:
            extra = vegetation.shrubs_from_imagery(
                colour_full,
                dem,
                res,
                fp.size_m,
                encoded.min_elevation_m,
                shrub_from_imagery,
                seed=int(objects_spec.get("seed", 1)) + 3,
                exclude=placed,
                layer=layer,
                allowed_layers={
                    materials.index(name)
                    for name in shrub_from_imagery.get("layers", [])
                    if name in materials
                },
                max_slope_deg=shrub_from_imagery.get("max_slope_deg"),
                unplaced=(leftover := []),
            )
            placed += extra
            if shrub_from_imagery.get("erase_unplaced") and leftover:
                # A dark dot nothing stands on is a brown smear: repainted from the
                # ground round it.
                dots = leftover[0]
                if dots.shape[0] != colour_full.shape[0]:
                    from PIL import Image

                    dots = (
                        np.asarray(
                            Image.fromarray(dots.astype("uint8") * 255).resize(
                                (colour_full.shape[1], colour_full.shape[0]), Image.NEAREST
                            )
                        )
                        > 127
                    )
                colour_full = vegetation.erase_dots(
                    colour_full, dots, 10.0, fp.size_m / colour_full.shape[0]
                )
                report["imagery_dots_erased"] = int(dots.sum())
        shrub_scatter = (objects_spec or {}).get("shrub_scatter")
        if shrub_scatter:
            # The third way a bush can be placed, beside the lidar bump and the dark dot
            # in the photograph: a density per hectare on the layers named. It is the
            # only one that works on dry grass and knee-high scrub, which is what most
            # of Wallace Creek and the Factory Butte washes are.
            densities = {
                materials.index(name): float(per_ha)
                for name, per_ha in (shrub_scatter.get("density") or {}).items()
                if name in materials
            }
            if densities:
                block = None
                if cliff["mask"] is not None and cliff["mask"].any():
                    block = cliff["mask"]
                placed += ob.scatter_shrubs(
                    layer,
                    dem,
                    res,
                    fp.size_m,
                    encoded.min_elevation_m,
                    densities,
                    seed=int(objects_spec.get("seed", 1)) + 9,
                    height_range=tuple(shrub_scatter.get("height_m", (0.4, 1.2))),
                    width_ratio=tuple(shrub_scatter.get("width_ratio", (1.0, 1.8))),
                    max_slope_deg=float(shrub_scatter.get("max_slope_deg", 32.0)),
                    patch_m=float(shrub_scatter.get("patch_m", 60.0)),
                    patchiness=float(shrub_scatter.get("patchiness", 0.65)),
                    swale_bias=float(shrub_scatter.get("swale_bias", 0.0)),
                    swale_window_m=float(shrub_scatter.get("swale_window_m", 40.0)),
                    swale_threshold_m=float(shrub_scatter.get("swale_threshold_m", 1.0)),
                    max_count=int(shrub_scatter.get("max", 40000)),
                    exclude=block,
                )
        cover_colours: dict = {}
        if forest_spec:
            cover = vegetation.cover_maps(colour_full, dem, res, forest_spec)
            cover_colours = {
                "conifer": cover.get("conifer_colour"),
                "broadleaf": cover.get("broadleaf_colour"),
            }
            road_ids = [
                materials.index(cfg["terrain_material"])
                for cfg in (surfaces or {}).values()
                if cfg.get("terrain_material") in materials
            ]
            road_mask = np.isin(layer, road_ids) if surfaces else None
            spawn_exclusions = [
                (x, y, float(forest_spec.get("spawn_clear_m", 12.0))) for x, y in spawn_clear
            ]
            chm_file = data_root / "terrain" / "chm.npy"
            if forest_spec.get("source") == "chm" and chm_file.is_file():
                trees, forest_stats = vegetation.trees_from_chm(
                    np.load(chm_file),
                    dem,
                    colour_full,
                    res,
                    fp.size_m,
                    encoded.min_elevation_m,
                    forest_spec,
                    seed=int(forest_spec.get("seed", 7)),
                    road_mask=road_mask,
                    exclude_points=spawn_exclusions,
                )
            else:
                trees, forest_stats = vegetation.plant(
                    cover,
                    dem,
                    res,
                    fp.size_m,
                    encoded.min_elevation_m,
                    forest_spec,
                    seed=int(forest_spec.get("seed", 7)),
                    road_mask=road_mask,
                    exclude_points=spawn_exclusions,
                )
        # Nothing stands on a spawn.
        clear_r = float((objects_spec or {}).get("spawn_clear_m", 6.0))
        placed = [
            o
            for o in placed
            if all(
                (o["x"] - sx) ** 2 + (o["y"] - sy) ** 2 > clear_r * clear_r
                for sx, sy in spawn_clear
            )
        ]
        # Nothing stands on a building either: to the bump detector a roof is a
        # boulder, and to the canopy height model it is a nine metre tree.
        if built.get("mask") is not None:
            bmask = built["mask"]
            edge = bmask.shape[0] - 1

            def _on_building(x: float, y: float) -> bool:
                r = int(min(max((fp.size_m / 2 - y) / res, 0), edge))
                c = int(min(max((x + fp.size_m / 2) / res, 0), edge))
                return bool(bmask[r, c])

            before_objects, before_trees = len(placed), len(trees)
            placed = [o for o in placed if not _on_building(o["x"], o["y"])]
            trees = [t for t in trees if not _on_building(t["x"], t["y"])]
            built["stats"]["removed_objects"] = before_objects - len(placed)
            built["stats"]["removed_trees"] = before_trees - len(trees)

        tree_species = {t["species"] for t in trees}
        shrub_by_layer = (objects_spec or {}).get("shrub_material_by_layer", {})
        shrub_scatter_by_layer = ((objects_spec or {}).get("shrub_scatter") or {}).get(
            "material_by_layer"
        )
        shrub_families = (objects_spec or {}).get("shrub_materials") or {}
        default_shrub = next(iter(shrub_families), "shrub")
        shrub_materials: set[str] = set()
        # Species by size first (a bush the lidar measured at 2 m is a juniper on any
        # layer), then by layer.
        height_rules = (objects_spec or {}).get("shrub_material_by_height", [])
        by_height = sorted(((float(h), name) for h, name in height_rules), reverse=True)
        for obj in placed:
            if obj["kind"] != "shrub":
                continue
            r = int(min(max((fp.size_m / 2 - obj["y"]) / res, 0), size - 1))
            c = int(min(max((obj["x"] + fp.size_m / 2) / res, 0), size - 1))
            under = materials[int(layer[r, c])]
            obj["material"] = shrub_by_layer.get(under, default_shrub)
            for min_h, name in by_height:
                if float(obj["size"][2]) >= min_h:
                    obj["material"] = name
                    break
            if obj.get("source") == "scatter":
                # A plant the density scatter placed is a different plant from one the
                # lidar measured on the same ground: the layer's bush is the big one the
                # detector keeps, and what fills between them is grass and low scrub. A
                # spec that says so wins over the layer mapping and over the height
                # rules, which are cut for lidar heights and would call a 0.3 m tussock
                # by the name of the metre-and-a-half juniper beside it.
                obj["material"] = (shrub_scatter_by_layer or {}).get(under, obj["material"])
            family = shrub_families.get(obj["material"]) or {}
            cap = float(family.get("max_width_m", 0.0))
            if cap > 0 and max(obj["size"][:2]) > cap:
                obj["size"] = [min(obj["size"][0], cap), min(obj["size"][1], cap), obj["size"][2]]
            shrub_materials.add(obj["material"])
        has_shrubs = shrub_materials
        if not rock_materials and any(o["kind"] == "rock" for o in placed):
            rock_materials = {"rock_talus"}
        catalogue = scene_objects.build_shapes(
            spec,
            level_root,
            level_url,
            lambda key: pid(mod_id, key),
            tree_species=tree_species,
            rock_materials=rock_materials,
            shrub=has_shrubs,
            cover_colours=cover_colours,
        )
        forest_stats = {
            **forest_stats,
            **scene_objects.write_forest(
                spec,
                level_root,
                level_url,
                lambda key: pid(mod_id, key),
                catalogue,
                placed_objects=placed,
                trees=trees,
                seed=int((objects_spec or forest_spec).get("seed", 5)),
                dem=dem,
                res=res,
                fp_size_m=fp.size_m,
                min_elevation=encoded.min_elevation_m,
            ),
        }
        forest_stats["rocks"] = sum(1 for o in placed if o["kind"] == "rock")
        forest_stats["shrubs"] = sum(1 for o in placed if o["kind"] == "shrub")
    report["forest"] = forest_stats
    report["shapes"] = catalogue.get("shapes", [])
    report["buildings"] = built["stats"]
    report["cliffs"] = cliff["stats"]

    # --- previews + minimap --------------------------------------------------------
    previews = build_previews(
        dem, res, fp, data_root / "naip", frame, spawns, level_root, mod_id, colour_full=colour_full
    )
    from PIL import Image

    Image.fromarray(colour_full).resize((1024, 1024), Image.LANCZOS).save(
        level_root / f"{mod_id}_minimap.png", format="PNG", compress_level=6
    )

    lakes_file = data_root / "terrain" / "lakes.npy"
    water_objects = []
    if lakes_file.is_file():
        # One WaterBlock per painted body: its surface at the body's lowest ground
        # plus a hand, its box the body's bounds, four metres deep.
        from scipy import ndimage

        lake_mask = np.load(lakes_file)
        labels, _count = ndimage.label(lake_mask)
        half = fp.size_m / 2.0
        for k, sl in enumerate(ndimage.find_objects(labels), start=1):
            if sl is None:
                continue
            cells = labels[sl] == k
            if cells.sum() * res * res < 400.0:
                continue
            # The surface a hand over the body's 95th-percentile ground: a lidar-flat
            # lake is level to the centimetre, a settled pond's cells were cut under
            # its top by the terrain stage, so every cell is under water.
            surface = float(np.percentile(dem[sl][cells], 95)) + 0.15 - encoded.min_elevation_m
            r0, r1 = sl[0].start, sl[0].stop
            c0, c1 = sl[1].start, sl[1].stop
            cx = (c0 + c1) / 2.0 * res - half
            cy = half - (r0 + r1) / 2.0 * res
            depth = 4.0
            name = f"lake_{k:02d}"
            water_objects.append(
                {
                    "name": name,
                    "class": "WaterBlock",
                    "persistentId": pid(mod_id, name),
                    "__parent": "water",
                    "position": [round(cx, 2), round(cy, 2), round(surface - depth / 2.0, 2)],
                    "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                    "scale": [
                        round((c1 - c0) * res + 4.0, 1),
                        round((r1 - r0) * res + 4.0, 1),
                        depth,
                    ],
                    "liquidType": "Water",
                    "density": 1,
                    "viscosity": 1,
                    "baseColor": [0.2, 0.33, 0.31, 1],
                    "waterFogColor": [0.14, 0.24, 0.23, 1],
                    "fogDensity": 0.4,
                    "clarity": 0.3,
                }
            )
    report["water_objects"] = len(water_objects)

    # --- scene tree ---------------------------------------------------------------
    main = level_root / "main"
    footprint = float(fp.size_m)
    write_items(
        main / "items.level.json",
        [
            {
                "name": "MissionGroup",
                "class": "SimGroup",
                "enabled": "1",
                "persistentId": pid(mod_id, "MissionGroup"),
            }
        ],
    )
    write_items(
        main / "MissionGroup" / "items.level.json",
        [
            {
                "name": "Level_objects",
                "class": "SimGroup",
                "persistentId": pid(mod_id, "Level_objects"),
                "__parent": "MissionGroup",
            },
            {
                "name": "PlayerDropPoints",
                "class": "SimGroup",
                "persistentId": pid(mod_id, "PlayerDropPoints"),
                "__parent": "MissionGroup",
            },
            {
                "name": "roads",
                "class": "SimGroup",
                "persistentId": pid(mod_id, "roads"),
                "__parent": "MissionGroup",
            },
        ]
        + (
            # A water group only where a body was painted: an empty group would be
            # a folder with nothing in it.
            [
                {
                    "name": "water",
                    "class": "SimGroup",
                    "persistentId": pid(mod_id, "water"),
                    "__parent": "MissionGroup",
                }
            ]
            if water_objects
            else []
        )
        + (
            [
                {
                    "name": "forest",
                    "class": "SimGroup",
                    "persistentId": pid(mod_id, "forest"),
                    "__parent": "MissionGroup",
                }
            ]
            if catalogue
            else []
        )
        + (
            [
                {
                    "name": "buildings",
                    "class": "SimGroup",
                    "persistentId": pid(mod_id, "buildings"),
                    "__parent": "MissionGroup",
                }
            ]
            if built["items"]
            else []
        )
        + (
            [
                {
                    "name": "cliffs",
                    "class": "SimGroup",
                    "persistentId": pid(mod_id, "cliffs"),
                    "__parent": "MissionGroup",
                }
            ]
            if cliff["items"]
            else []
        ),
    )
    if built["items"]:
        write_items(main / "MissionGroup" / "buildings" / "items.level.json", built["items"])
    if cliff["items"]:
        write_items(main / "MissionGroup" / "cliffs" / "items.level.json", cliff["items"])
    if catalogue:
        from . import scene_objects

        write_items(
            main / "MissionGroup" / "forest" / "items.level.json",
            [scene_objects.forest_object(spec, level_url, lambda key: pid(mod_id, key))],
        )
    write_items(
        main / "MissionGroup" / "Level_objects" / "items.level.json",
        [
            {
                "name": "terrain",
                "class": "SimGroup",
                "persistentId": pid(mod_id, "terrain"),
                "__parent": "Level_objects",
            },
            {
                "name": "Sky",
                "class": "SimGroup",
                "persistentId": pid(mod_id, "Sky"),
                "__parent": "Level_objects",
            },
            {
                "name": "level_info",
                "class": "SimGroup",
                "persistentId": pid(mod_id, "level_info"),
                "__parent": "Level_objects",
            },
            {
                "name": "time",
                "class": "SimGroup",
                "persistentId": pid(mod_id, "time"),
                "__parent": "Level_objects",
            },
        ],
    )
    write_items(
        main / "MissionGroup" / "Level_objects" / "terrain" / "items.level.json",
        [
            {
                "name": "theTerrain",
                "class": "TerrainBlock",
                "persistentId": pid(mod_id, "theTerrain"),
                "__parent": "terrain",
                # Half a square in from the footprint corner: the game puts sample
                # (0, 0) at the block's position, the GIS grid holds the ground at each
                # cell's centre, so this lines the two up and every object, road and
                # spawn placed from the grid lands on the ground the game draws.
                "position": [-footprint / 2.0 + res / 2.0, -footprint / 2.0 + res / 2.0, 0],
                "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "terrainFile": f"{level_url}/theTerrain.ter",
                "materialTextureSet": texture_set_name,
                "minimapImage": f"levels/{mod_id}/{mod_id}_minimap.png",
                "squareSize": res,
                "maxHeight": encoded.max_height_m,
                # The resolution the engine bakes the far-field base map at. It has to
                # be the resolution of the base maps themselves, or the level draws a
                # 2048 px bake of a 4096 px orthophoto once the cells go out of detail
                # range - the whole map, from any ridge.
                "baseTexSize": base_px,
                "lightMapSize": 1024,
                "screenError": 16,
                "castShadows": True,
            }
        ],
    )
    write_items(
        main / "MissionGroup" / "Level_objects" / "Sky" / "items.level.json",
        [
            {
                "name": "sunsky",
                "class": "ScatterSky",
                "persistentId": pid(mod_id, "sunsky"),
                "__parent": "Sky",
                "position": [0, 0, 0],
                "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "scale": [1, 1, 1],
                "ambientScale": [1, 0.894117653, 0.78039217, 1],
                "ambientScaleGradientFile": "art/sky_gradients/default/gradient_ambient.png",
                "brightness": 0.9,
                "colorize": [0.215686277, 0.349019617, 0.603921592, 1],
                "colorizeGradientFile": "art/sky_gradients/default/gradient_colorize.png",
                "exposure": 1.4,
                "fadeStartDistance": 1000,
                "flareScale": 10,
                "flareType": "BNG_Sunflare_2",
                "fogScale": [0.396078438, 0.666666687, 1, 1],
                "fogScaleGradientFile": "art/sky_gradients/default/gradient_fog.png",
                "logWeight": 0.98,
                "mieScattering": 0.000401154364,
                "moonLightColor": [0.0980392024, 0.0980392024, 0.0980392024, 1],
                "moonMat": "Moon_Glow_Mat",
                "moonScale": 0.03,
                "nightColor": [1, 0.894117653, 0.78039217, 1],
                "nightCubemap": "nightCubemap",
                "nightFogColor": [0.396078438, 0.666666687, 1, 1],
                "nightFogGradientFile": "art/sky_gradients/default/gradient_fog.png",
                "nightGradientFile": "art/sky_gradients/default/gradient_ambient.png",
                "occlusionScale": 0.3,
                "shadowDistance": 1600,
                "shadowSoftness": 0.2,
                "skyBrightness": 42,
                "sunScale": [0.996078432, 0.831372559, 0.729411781, 1],
                "sunScaleGradientFile": "art/sky_gradients/default/gradient_sunscale.png",
                "texSize": 1024,
                "useNightCubemap": True,
            }
        ],
    )
    write_items(
        main / "MissionGroup" / "Level_objects" / "level_info" / "items.level.json",
        [
            {
                "name": "theLevelInfo",
                "class": "LevelInfo",
                "persistentId": pid(mod_id, "theLevelInfo"),
                "__parent": "level_info",
                "nearClip": 0.1,
                "visibleDistance": 9000,
                "decalBias": 0.0005,
                "fogDensity": 0.00015,
                "fogAtmosphereHeight": 1500,
                "canvasClearColor": [0, 0, 0, 255],
                "gravity": -9.80665,
                "levelName": spec.DISPLAY_NAME,
                "desc0": spec.FEATURES,
                "fogColor": [0.574180365, 0.77074331, 1, 1],
                "fogDensityOffset": 1,
                "temperatureCurveC": [0, 12, 0.25, 24, 0.5, 30, 0.75, 22, 1, 12],
                "ambientLightBlendPhase": 1,
                "advancedLightmapSupport": False,
                "globalEnviromentMap": "DefaultSkyCubemap",
                "soundAmbience": "AudioAmbienceDefault",
                "soundDistanceModel": "Logarithmic",
                "bigMapLevelBorderVisible": True,
            }
        ],
    )
    sky = spec.SKY
    write_items(
        main / "MissionGroup" / "Level_objects" / "time" / "items.level.json",
        [
            {
                "name": "tod",
                "class": "TimeOfDay",
                "persistentId": pid(mod_id, "tod"),
                "__parent": "time",
                "position": [0, 0, 0],
                "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "scale": [1, 1, 1],
                "axisTilt": 23.44,
                "dayLength": 1800,
                "startTime": float(sky["time"]),
                "time": float(sky["time"]),
                "play": False,
                "latitude": float(site["center_lat"]),
                "longitude": float(site["center_lon"]),
                "year": int(sky.get("year", 2026)),
                "month": int(sky.get("month", 6)),
                "day": int(sky.get("day", 20)),
                "utcOffset": str(sky.get("utc_offset", "-7")),
                "celestialProfile": "earth",
            }
        ],
    )
    spawn_objects = []
    for spawn in spawns:
        x, y = spawn["level_xy"]
        spawn_objects.append(
            {
                "name": spawn["objectname"],
                "class": "SpawnSphere",
                "persistentId": pid(mod_id, spawn["objectname"]),
                "__parent": "PlayerDropPoints",
                "position": [x, y, spawn["z"]],
                "rotationMatrix": yaw_matrix(spawn["heading_deg"]),
                "scale": [1, 1, 1],
                "dataBlock": "SpawnSphereMarker",
                "radius": 5,
                "autoplaceOnSpawn": "0",
                "homingCount": "0",
                "indoorWeight": "1",
                "outdoorWeight": "1",
                "lockCount": "0",
                "sphereWeight": "1",
            }
        )
    write_items(main / "MissionGroup" / "PlayerDropPoints" / "items.level.json", spawn_objects)
    write_items(main / "MissionGroup" / "roads" / "items.level.json", roads)
    if water_objects:
        write_items(main / "MissionGroup" / "water" / "items.level.json", water_objects)

    # --- info.json ---------------------------------------------------------------
    attribution = " ".join(
        f"{s['citation']}." for s in spec.SOURCES["elevation"] if s.get("citation")
    )
    description = (
        f"{spec.DESCRIPTION} Elevation: USGS 3DEP (public domain)"
        f"{'; ' + attribution if attribution else ''}"
        " Imagery: USGS/USDA NAIP (public domain). Roads: (c) OpenStreetMap contributors, ODbL."
    )
    write_json(
        level_root / "info.json",
        {
            "title": spec.DISPLAY_NAME,
            "description": description,
            "authors": spec.AUTHOR,
            "country": "levels.common.country.usa",
            "region": "northAmerica",
            "biome": spec.BIOME,
            "features": spec.FEATURES,
            "suitablefor": spec.SUITABLE_FOR,
            "roads": spec.ROADS_TEXT,
            "size": [int(footprint), int(footprint)],
            "supportsTraffic": False,
            "supportsTimeOfDay": True,
            "defaultDate": {
                "year": int(sky.get("year", 2026)),
                "month": int(sky.get("month", 6)),
                "day": int(sky.get("day", 20)),
            },
            "defaultSpawnPointName": default_spawn["objectname"],
            "previews": [previews["main"]],
            "spawnPoints": [
                {
                    "translationId": spawn["label"],
                    "description": f"{spawn['label']} ({spawn['lat']:.4f}, {spawn['lon']:.4f})",
                    "objectname": spawn["objectname"],
                    "preview": previews[spawn["objectname"]],
                }
                for spawn in spawns
            ],
        },
    )
    report.update(
        {
            "level_root": str(level_root),
            "spawns": spawns,
            "roads": road_stats,
            "materials": materials,
            "texture_set": texture_set_name,
            "terrain_block": {
                "position": [-footprint / 2.0 + res / 2.0, -footprint / 2.0 + res / 2.0, 0],
                "squareSize": res,
                "maxHeight": encoded.max_height_m,
                "size": size,
            },
        }
    )
    return report


def _feather_road_alpha(colour_path: Path, edge_fraction: float = 0.18) -> None:
    """Give the decal-road colour map a soft alpha edge across its width (U axis)."""

    from PIL import Image

    image = Image.open(colour_path).convert("RGBA")
    array = np.asarray(image).copy()
    width = array.shape[1]
    u = (np.arange(width) + 0.5) / width
    edge = np.clip(np.minimum(u, 1.0 - u) / edge_fraction, 0.0, 1.0)
    alpha = (edge * edge * (3 - 2 * edge) * 255).round().astype("uint8")
    array[..., 3] = alpha[None, :]
    Image.fromarray(array, mode="RGBA").save(colour_path, format="PNG", compress_level=6)
