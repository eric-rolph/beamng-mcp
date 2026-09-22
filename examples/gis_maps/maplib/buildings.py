"""Buildings from OpenStreetMap outlines at lidar-measured heights.

The pack's rule everywhere else is that the ground is measured and never invented, and
buildings are held to it. OSM gives the outline and nothing else: every height, every
roof shape and every roof colour here is read off the data the level is already built
from.

    outline      OSM ``building`` ways (ODbL), projected onto the level grid
    height       the 3DEP point cloud's highest-hit surface minus its classified
                 ground, inside the outline - the same two arrays the forest is
                 planted from, read over a different polygon
    roof shape   fitted to those returns: flat if the surface is level, gabled if it
                 rises to a line, hipped if it falls away at both ends, and the ridge
                 runs along the outline's own long axis
    roof colour  the median of the de-lit orthophoto inside the outline, snapped to
                 the nearest of eight roofing colours
    walls        procedural, from the family OSM's ``building`` and
                 ``building:material`` tags name, in a seeded colour per building

Nothing is read from a photograph of a facade and nothing is traced from a rendering.
A wall is a texture family the way a talus block is a texture family.

Two things the rest of the pipeline must know about, both returned as ``mask``: the
bump detector would read a roof as a boulder, and the canopy height model would plant
a 9 m spruce on one. Both take the building mask as an exclusion.

The terrain itself needs no healing. 3DEP's 1 m raster is a bare-earth DTM with no
buildings in it, so the ground under a footprint is already the ground; the building
stands on it. The orthophoto needs none either: the roof it photographed is exactly
where the roof mesh goes, and the de-lighting has already refilled the shadow the
building threw.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .meshgen import Mesh
from .stable_seed import stable_hash

# Roofing colours a building in the San Juans actually has, as linear sRGB 0-1. The
# measured median inside the outline is snapped to the nearest of these, so a red barn
# stays red and a galvanised shed stays grey without the orthophoto's noise coming
# through as a hundred slightly different greys.
ROOF_COLOURS = {
    "galv": (0.47, 0.48, 0.49),
    "grey": (0.30, 0.31, 0.32),
    "charcoal": (0.14, 0.14, 0.15),
    "rust": (0.38, 0.17, 0.11),
    "red": (0.44, 0.14, 0.11),
    "green": (0.18, 0.26, 0.19),
    "brown": (0.29, 0.22, 0.16),
    "tan": (0.50, 0.44, 0.35),
}

# Wall families, by what OSM says the building is. The San Juan mining towns are
# board-and-batten and clapboard with corrugated steel on the industrial sheds and
# stone on the older civic buildings.
WALL_FAMILIES = {
    "house": "clapboard",
    "residential": "clapboard",
    "detached": "clapboard",
    "apartments": "clapboard",
    "hotel": "clapboard",
    "cabin": "board",
    "hut": "board",
    "shed": "board",
    "barn": "board",
    "farm_auxiliary": "board",
    "industrial": "steel",
    "warehouse": "steel",
    "service": "steel",
    "garage": "steel",
    "garages": "steel",
    "commercial": "brick",
    "retail": "brick",
    "civic": "stone",
    "public": "stone",
    "church": "board",
    "school": "brick",
    "yes": "clapboard",
}
MATERIAL_TAG_FAMILIES = {
    "wood": "board",
    "timber_framing": "board",
    "metal": "steel",
    "metal_sheet": "steel",
    "brick": "brick",
    "stone": "stone",
    "concrete": "stone",
    "plaster": "clapboard",
}


# ---------------------------------------------------------------------------
# Outlines
# ---------------------------------------------------------------------------


def load_footprints(path: Path, fp, *, min_area_m2: float = 12.0) -> list[dict]:
    """Closed OSM building outlines as level-coordinate rings, biggest first.

    A ring is counter-clockwise with no repeated closing vertex, in metres from the
    footprint's centre. Anything smaller than ``min_area_m2`` is a bin store or a
    mapping artefact and is dropped.
    """

    from rasterio.warp import transform

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cx, cy = fp.center
    half = fp.size_m / 2.0
    out = []
    for way in data.get("elements", []):
        if way.get("type") != "way" or not way.get("geometry"):
            continue
        tags = way.get("tags") or {}
        if not tags.get("building"):
            continue
        geometry = way["geometry"]
        if len(geometry) < 4:
            continue
        lons = [float(g["lon"]) for g in geometry]
        lats = [float(g["lat"]) for g in geometry]
        xs, ys = transform("EPSG:4326", f"EPSG:{fp.epsg}", lons, lats)
        ring = [(x - cx, y - cy) for x, y in zip(xs, ys, strict=True)]
        if ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) < 3:
            continue
        area = _signed_area(ring)
        if abs(area) < min_area_m2:
            continue
        if area < 0:  # OSM rings come either way round; the mesher wants CCW
            ring = ring[::-1]
            area = -area
        # Wholly outside the level, including its own overhang, is not ours to draw.
        if min(abs(x) for x, _ in ring) > half or min(abs(y) for _, y in ring) > half:
            continue
        if all(abs(x) > half or abs(y) > half for x, y in ring):
            continue
        # An outline straddling the edge with its CENTRE outside would put its tile's
        # TSStatic origin outside the level, where the engine has no ground for it.
        # (Not cx/cy - those hold the footprint centre every ring is projected against.)
        mid_x = sum(px for px, _ in ring) / len(ring)
        mid_y = sum(py for _, py in ring) / len(ring)
        if abs(mid_x) > half or abs(mid_y) > half:
            continue
        out.append({"id": int(way["id"]), "tags": tags, "ring": ring, "area_m2": area})
    out.sort(key=lambda b: -b["area_m2"])
    return out


def _signed_area(ring: list[tuple[float, float]]) -> float:
    a = 0.0
    for i in range(len(ring)):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % len(ring)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out: list[tuple[float, float]] = []
        for p in seq:
            while len(out) >= 2:
                (x0, y0), (x1, y1) = out[-2], out[-1]
                if (x1 - x0) * (p[1] - y0) - (y1 - y0) * (p[0] - x0) > 0:
                    break
                out.pop()
            out.append(p)
        return out

    lower = half(pts)
    upper = half(reversed(pts))
    return lower[:-1] + upper[:-1]


def min_area_rect(ring: list[tuple[float, float]]) -> dict:
    """The smallest rectangle round the outline: centre, half-lengths, long-axis angle.

    Rotating calipers on the convex hull. A roof sits over this rectangle, not over the
    outline, which is what a roof does: it runs to the eaves in one direction and to
    the gable in the other whatever the wall below is doing.
    """

    hull = _convex_hull(ring)
    if len(hull) < 3:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return {
            "center": ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2),
            "half": (max(1e-3, (max(xs) - min(xs)) / 2), max(1e-3, (max(ys) - min(ys)) / 2)),
            "angle": 0.0,
        }
    pts = np.asarray(hull, dtype="float64")
    best = None
    for i in range(len(hull)):
        x0, y0 = hull[i]
        x1, y1 = hull[(i + 1) % len(hull)]
        theta = math.atan2(y1 - y0, x1 - x0)
        c, s = math.cos(-theta), math.sin(-theta)
        rx = pts[:, 0] * c - pts[:, 1] * s
        ry = pts[:, 0] * s + pts[:, 1] * c
        w = rx.max() - rx.min()
        h = ry.max() - ry.min()
        if best is None or w * h < best[0]:
            best = (w * h, theta, rx.min(), rx.max(), ry.min(), ry.max())
    _area, theta, rx0, rx1, ry0, ry1 = best
    c, s = math.cos(theta), math.sin(theta)
    mx, my = (rx0 + rx1) / 2, (ry0 + ry1) / 2
    a, b = (rx1 - rx0) / 2, (ry1 - ry0) / 2
    if b > a:  # the long axis is the ridge; keep it first
        a, b = b, a
        theta += math.pi / 2
        c, s = math.cos(theta), math.sin(theta)
        mx, my = my, -mx
    return {
        "center": (mx * c - my * s, mx * s + my * c),
        "half": (max(a, 1e-3), max(b, 1e-3)),
        "angle": theta,
    }


def earclip(ring: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """Triangulate a simple counter-clockwise polygon by ear clipping."""

    n = len(ring)
    if n < 3:
        return []
    idx = list(range(n))
    tris: list[tuple[int, int, int]] = []
    guard = 0
    while len(idx) > 3 and guard < 4 * n:
        guard += 1
        clipped = False
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            ax, ay = ring[i0]
            bx, by = ring[i1]
            cx, cy = ring[i2]
            cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            if cross <= 0:  # reflex corner, not an ear
                continue
            if any(
                _in_triangle(ring[j], (ax, ay), (bx, by), (cx, cy))
                for j in idx
                if j not in (i0, i1, i2)
            ):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            clipped = True
            break
        if not clipped:  # self-intersecting outline: fall back to a centroid fan
            return [(idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1)]
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def _in_triangle(p, a, b, c) -> bool:
    (px, py), (ax, ay), (bx, by), (cx, cy) = p, a, b, c
    d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by)
    d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy)
    d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


# ---------------------------------------------------------------------------
# Measuring
# ---------------------------------------------------------------------------


def rasterize_ring(ring, res: float, half: float, n: int, *, grow_m: float = 0.0):
    """Row/col index arrays of the grid cells inside an outline (row 0 is north)."""

    xs = [x for x, _ in ring]
    ys = [y for _, y in ring]
    c0 = max(0, int((min(xs) - grow_m + half) / res))
    c1 = min(n, int((max(xs) + grow_m + half) / res) + 1)
    r0 = max(0, int((half - (max(ys) + grow_m)) / res))
    r1 = min(n, int((half - (min(ys) - grow_m)) / res) + 1)
    if r1 <= r0 or c1 <= c0:
        return None
    cc, rr = np.meshgrid(np.arange(c0, c1), np.arange(r0, r1))
    px = (cc + 0.5) * res - half
    py = half - (rr + 0.5) * res
    inside = np.zeros(px.shape, dtype=bool)
    m = len(ring)
    for i in range(m):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % m]
        crosses = ((y0 > py) != (y1 > py)) & (
            px < (x1 - x0) * (py - y0) / np.where(y1 == y0, 1e-12, y1 - y0) + x0
        )
        inside ^= crosses
    if grow_m > 0:
        from scipy import ndimage

        inside = ndimage.binary_dilation(inside, iterations=max(1, int(grow_m / res)))
    return rr[inside], cc[inside]


def measure(
    building: dict,
    dsm: np.ndarray,
    ground: np.ndarray,
    dem: np.ndarray,
    res: float,
    half: float,
    *,
    min_height_m: float = 2.2,
    max_height_m: float = 40.0,
    roof_band_m: float = 3.0,
) -> dict | None:
    """Eaves, ridge, roof kind and ridge azimuth, read off the lidar surface.

    Returns None where the lidar says there is nothing standing: a footprint mapped
    over a slab, a building taken down since the flight, or a cell count too small to
    say anything with.
    """

    n = dsm.shape[0]
    hit = rasterize_ring(building["ring"], res, half, n)
    if hit is None or hit[0].size < 4:
        return None
    rr, cc = hit
    surface = dsm[rr, cc]
    floor = ground[rr, cc]
    floor = np.where(np.isfinite(floor), floor, dem[rr, cc])
    h = surface - floor
    h = h[np.isfinite(h)]
    if h.size < 4:
        return None
    # A roof is the dominant surface inside its own outline. A crown overhanging it is
    # a handful of returns several metres above, and a gap between two wings a handful
    # below - and a straight p90 takes the crown. Trim to the returns within a band of
    # the median first: in Telluride, where the cottages stand under big spruce, the
    # untrimmed median ridge came out at 16.8 m for a town of six to nine metre houses.
    median = float(np.median(h))
    body = h[np.abs(h - median) <= roof_band_m]
    if body.size < max(4, int(0.25 * h.size)):
        body = h  # no dominant surface: take what there is rather than invent one
    ridge = float(np.percentile(body, 90))
    if not (min_height_m <= ridge <= max_height_m):
        return None

    rect = min_area_rect(building["ring"])
    # Eaves: the low quartile of the roof surface. A roof's lowest quarter is its
    # eaves course whatever shape the rest of it is.
    eaves = float(np.percentile(body, 25))
    rise = max(0.0, ridge - eaves)
    # Where the outline is not a rectangle a fitted ridge is a guess, so those take a
    # flat roof with a parapet, which is what a flat-roofed main street has anyway.
    rectangularity = building["area_m2"] / (4.0 * rect["half"][0] * rect["half"][1])
    if rise < 0.8 or rectangularity < 0.82:
        kind = "flat"
        eaves = float(np.percentile(body, 60))
        rise = 0.0
    else:
        # Hipped or gabled: walk the long axis and see whether the surface falls away
        # at both ends. A gable stands full height to the wall; a hip does not.
        px = (cc + 0.5) * res - half
        py = half - (rr + 0.5) * res
        c, s = math.cos(-rect["angle"]), math.sin(-rect["angle"])
        u = (px - rect["center"][0]) * c - (py - rect["center"][1]) * s
        a = rect["half"][0]
        hh = dsm[rr, cc] - np.where(np.isfinite(ground[rr, cc]), ground[rr, cc], dem[rr, cc])
        ends = np.isfinite(hh) & (np.abs(u) > 0.75 * a)
        middle = np.isfinite(hh) & (np.abs(u) < 0.35 * a)
        kind = "gable"
        if ends.sum() >= 3 and middle.sum() >= 3:
            end_top = float(np.percentile(hh[ends], 90))
            mid_top = float(np.percentile(hh[middle], 90))
            if end_top < mid_top - 0.35 * rise:
                kind = "hip"
    floor_z = float(np.median(np.where(np.isfinite(dem[rr, cc]), dem[rr, cc], 0.0)))
    return {
        **building,
        "cells": int(rr.size),
        "floor_z": floor_z,
        "eaves_m": round(eaves, 2),
        "ridge_m": round(ridge, 2),
        "roof": kind,
        "rect": rect,
        "rectangularity": round(float(rectangularity), 3),
    }


def roof_colour(building: dict, base_rgb: np.ndarray, res: float, half: float) -> str:
    """The nearest roofing colour to the orthophoto's median inside the outline."""

    n = base_rgb.shape[0]
    hit = rasterize_ring(building["ring"], res, half, n)
    if hit is None or hit[0].size < 3:
        return "galv"
    rr, cc = hit
    px = base_rgb[rr, cc].astype("float32")
    if px.max() > 1.5:
        px = px / 255.0
    median = np.median(px[:, :3], axis=0)
    best, best_d = "galv", 1e9
    for name, rgb in ROOF_COLOURS.items():
        d = float(np.sum((median - np.asarray(rgb, dtype="float32")) ** 2))
        if d < best_d:
            best, best_d = name, d
    return best


def wall_family(tags: dict) -> str:
    material = (tags.get("building:material") or "").lower()
    if material in MATERIAL_TAG_FAMILIES:
        return MATERIAL_TAG_FAMILIES[material]
    return WALL_FAMILIES.get((tags.get("building") or "yes").lower(), "clapboard")


# ---------------------------------------------------------------------------
# Meshing
# ---------------------------------------------------------------------------


def _quad(p0, p1, p2, p3, uvs, positions, normals, uv_out, tris):
    base = len(positions)
    normal = np.cross(np.asarray(p1) - np.asarray(p0), np.asarray(p3) - np.asarray(p0))
    length = float(np.linalg.norm(normal))
    normal = normal / length if length > 1e-9 else np.asarray([0.0, 0.0, 1.0])
    for p, uv in zip((p0, p1, p2, p3), uvs, strict=True):
        positions.append(p)
        normals.append(normal)
        uv_out.append(uv)
    tris.append((base, base + 1, base + 2))
    tris.append((base, base + 2, base + 3))


def _tri(p0, p1, p2, uvs, positions, normals, uv_out, tris):
    base = len(positions)
    normal = np.cross(np.asarray(p1) - np.asarray(p0), np.asarray(p2) - np.asarray(p0))
    length = float(np.linalg.norm(normal))
    normal = normal / length if length > 1e-9 else np.asarray([0.0, 0.0, 1.0])
    for p, uv in zip((p0, p1, p2), uvs, strict=True):
        positions.append(p)
        normals.append(normal)
        uv_out.append(uv)
    tris.append((base, base + 1, base + 2))


# BeamNG resolves vehicle-to-mesh collision per triangle at 2000 Hz. A wall or a roof
# pitch emitted as one big quad gives the solver a 30 m triangle, which reads as a
# trampoline under a wheel and lights flat besides. Every face is laid out as a grid of
# quads no longer than this.
MAX_FACE_M = 2.5


def _grid_quad(corners, texcoords, positions, normals, uvs, tris, *, max_m: float = MAX_FACE_M):
    """A quad as a bilinear grid of sub-quads, wound like its corners.

    ``corners`` runs round the face; the normal comes out of the same cross product
    ``_quad`` uses, so a face that was wound outward stays wound outward.
    """

    p00, p10, p11, p01 = (np.asarray(c, dtype="float64") for c in corners)
    t00, t10, t11, t01 = (np.asarray(t, dtype="float64") for t in texcoords)
    nu = max(1, math.ceil(max(np.linalg.norm(p10 - p00), np.linalg.norm(p11 - p01)) / max_m))
    nv = max(1, math.ceil(max(np.linalg.norm(p01 - p00), np.linalg.norm(p11 - p10)) / max_m))
    if nu == 1 and nv == 1:
        _quad(p00, p10, p11, p01, [t00, t10, t11, t01], positions, normals, uvs, tris)
        return

    def at(u, v):
        p = (1 - v) * ((1 - u) * p00 + u * p10) + v * ((1 - u) * p01 + u * p11)
        t = (1 - v) * ((1 - u) * t00 + u * t10) + v * ((1 - u) * t01 + u * t11)
        return p, t

    for i in range(nu):
        for j in range(nv):
            u0, u1 = i / nu, (i + 1) / nu
            v0, v1 = j / nv, (j + 1) / nv
            (a, ta), (b, tb) = at(u0, v0), at(u1, v0)
            (c, tc), (d, td) = at(u1, v1), at(u0, v1)
            _quad(a, b, c, d, [ta, tb, tc, td], positions, normals, uvs, tris)


def _grid_tri(points, texcoords, positions, normals, uvs, tris, *, max_m: float = MAX_FACE_M):
    """A triangle split four ways at its midpoints until no edge is longer than max_m.

    Midpoint subdivision keeps the winding of every child, so an outward face stays
    outward, and the flat roof deck of a 40 m mill shed stops being two triangles.
    """

    pts = [np.asarray(q, dtype="float64") for q in points]
    txs = [np.asarray(t, dtype="float64") for t in texcoords]
    stack = [(pts, txs)]
    guard = 0
    while stack and guard < 20000:
        guard += 1
        pp, tt = stack.pop()
        longest = max(float(np.linalg.norm(pp[i] - pp[(i + 1) % 3])) for i in range(3))
        if longest <= max_m:
            _tri(*pp, tt, positions, normals, uvs, tris)
            continue
        m = [(pp[i] + pp[(i + 1) % 3]) / 2 for i in range(3)]
        mt = [(tt[i] + tt[(i + 1) % 3]) / 2 for i in range(3)]
        stack += [
            ([pp[0], m[0], m[2]], [tt[0], mt[0], mt[2]]),
            ([m[0], pp[1], m[1]], [mt[0], tt[1], mt[1]]),
            ([m[2], m[1], pp[2]], [mt[2], mt[1], tt[2]]),
            ([m[0], m[1], m[2]], [mt[0], mt[1], mt[2]]),
        ]


def building_meshes(
    b: dict,
    terrain_z,
    *,
    wall_material: str,
    roof_material: str,
    wall_tile_m: float = 4.0,
    roof_tile_m: float = 2.0,
    overhang_m: float = 0.35,
    origin=(0.0, 0.0, 0.0),
) -> list[Mesh]:
    """Walls extruded to a level eaves line, and the fitted roof over them."""

    ring = b["ring"]
    ox, oy, oz = origin
    floor_z = b["floor_z"]
    eaves_z = floor_z + b["eaves_m"]
    # The wall foot follows the ground and is buried 0.35 m, so nothing floats on a
    # slope and no gap opens under a sill; the eaves line stays level, as a building's
    # does. On ground steeper than the wall is tall the foot is clamped.
    feet = []
    for x, y in ring:
        z = float(terrain_z(x, y)) - 0.35
        feet.append(min(z, eaves_z - 2.0))

    positions: list = []
    normals: list = []
    uvs: list = []
    tris: list = []
    perim = 0.0
    m = len(ring)
    for i in range(m):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % m]
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg < 1e-6:
            continue
        u0, u1 = perim / wall_tile_m, (perim + seg) / wall_tile_m
        perim += seg
        z0, z1 = feet[i], feet[(i + 1) % m]
        _grid_quad(
            (
                (x0 - ox, y0 - oy, z0 - oz),
                (x1 - ox, y1 - oy, z1 - oz),
                (x1 - ox, y1 - oy, eaves_z - oz),
                (x0 - ox, y0 - oy, eaves_z - oz),
            ),
            (
                (u0, 0.0),
                (u1, 0.0),
                (u1, (eaves_z - z1) / wall_tile_m),
                (u0, (eaves_z - z0) / wall_tile_m),
            ),
            positions,
            normals,
            uvs,
            tris,
        )
    walls = Mesh(
        name=f"b{b['id']}_wall",
        positions=np.asarray(positions, dtype="float32"),
        normals=np.asarray(normals, dtype="float32"),
        uvs=np.asarray(uvs, dtype="float32"),
        triangles=np.asarray(tris, dtype="int32"),
        material=wall_material,
    )

    positions, normals, uvs, tris = [], [], [], []
    if b["roof"] == "flat":
        # A parapet band round the edge and the deck just inside it.
        top = eaves_z + 0.35
        for i in range(m):
            x0, y0 = ring[i]
            x1, y1 = ring[(i + 1) % m]
            seg = math.hypot(x1 - x0, y1 - y0)
            if seg < 1e-6:
                continue
            _grid_quad(
                (
                    (x0 - ox, y0 - oy, eaves_z - oz),
                    (x1 - ox, y1 - oy, eaves_z - oz),
                    (x1 - ox, y1 - oy, top - oz),
                    (x0 - ox, y0 - oy, top - oz),
                ),
                ((0, 0), (seg / roof_tile_m, 0), (seg / roof_tile_m, 0.35), (0, 0.35)),
                positions,
                normals,
                uvs,
                tris,
            )
        deck = eaves_z + 0.2
        for i0, i1, i2 in earclip(ring):
            _grid_tri(
                (
                    (ring[i0][0] - ox, ring[i0][1] - oy, deck - oz),
                    (ring[i1][0] - ox, ring[i1][1] - oy, deck - oz),
                    (ring[i2][0] - ox, ring[i2][1] - oy, deck - oz),
                ),
                [(ring[i][0] / roof_tile_m, ring[i][1] / roof_tile_m) for i in (i0, i1, i2)],
                positions,
                normals,
                uvs,
                tris,
            )
    else:
        rect = b["rect"]
        a = rect["half"][0] + overhang_m
        bb = rect["half"][1] + overhang_m
        theta = rect["angle"]
        c, s = math.cos(theta), math.sin(theta)
        rise = max(0.4, b["ridge_m"] - b["eaves_m"])
        ridge_z = eaves_z + rise
        hip = bb if b["roof"] == "hip" else 0.0

        def world(u, v, z):
            return (
                rect["center"][0] + u * c - v * s - ox,
                rect["center"][1] + u * s + v * c - oy,
                z - oz,
            )

        slope_len = math.hypot(bb, rise)

        def face(points, texcoords, flip):
            pts = list(points)
            uvw = list(texcoords)
            if flip:
                pts.reverse()
                uvw.reverse()
            if len(pts) == 4:
                _grid_quad(pts, uvw, positions, normals, uvs, tris)
            else:
                _grid_tri(pts, uvw, positions, normals, uvs, tris)

        # The two pitches, eaves to ridge.
        for sign in (1.0, -1.0):
            face(
                (
                    world(-a, sign * bb, eaves_z),
                    world(a, sign * bb, eaves_z),
                    world(a - hip, 0.0, ridge_z),
                    world(-a + hip, 0.0, ridge_z),
                ),
                (
                    (-a / roof_tile_m, 0.0),
                    (a / roof_tile_m, 0.0),
                    ((a - hip) / roof_tile_m, slope_len / roof_tile_m),
                    ((-a + hip) / roof_tile_m, slope_len / roof_tile_m),
                ),
                # The far pitch is already wound outward; the near one is wound into
                # the roof and has to be turned over.
                sign > 0,
            )
        # The ends: a hip slopes in to the ridge, a gable stands up to it.
        for sign in (1.0, -1.0):
            if hip > 0.0:
                face(
                    (
                        world(sign * a, -bb, eaves_z),
                        world(sign * a, bb, eaves_z),
                        world(sign * (a - hip), 0.0, ridge_z),
                    ),
                    (
                        (-bb / roof_tile_m, 0.0),
                        (bb / roof_tile_m, 0.0),
                        (0.0, math.hypot(hip, rise) / roof_tile_m),
                    ),
                    sign < 0,
                )
            else:
                face(
                    (
                        world(sign * a, -bb, eaves_z),
                        world(sign * a, bb, eaves_z),
                        world(sign * a, 0.0, ridge_z),
                    ),
                    (
                        (0.0, 0.0),
                        (2 * bb / roof_tile_m, 0.0),
                        (bb / roof_tile_m, rise / roof_tile_m),
                    ),
                    sign < 0,
                )
    roof = Mesh(
        name=f"b{b['id']}_roof",
        positions=np.asarray(positions, dtype="float32"),
        normals=np.asarray(normals, dtype="float32"),
        uvs=np.asarray(uvs, dtype="float32"),
        triangles=np.asarray(tris, dtype="int32"),
        material=roof_material,
    )
    return [walls, roof]


# ---------------------------------------------------------------------------
# Building the lot
# ---------------------------------------------------------------------------

# Wall colours per family: a small painted palette so a street is varied without any
# one house being invented. Which one a building gets is a hash of its OSM id, so it
# is the same colour on every rebuild and on every machine.
WALL_COLOURS = {
    "clapboard": [
        (0.62, 0.58, 0.52),
        (0.70, 0.67, 0.60),
        (0.46, 0.44, 0.41),
        (0.55, 0.36, 0.30),
        (0.36, 0.40, 0.42),
        (0.68, 0.62, 0.45),
    ],
    "board": [
        (0.40, 0.31, 0.24),
        (0.32, 0.25, 0.19),
        (0.48, 0.38, 0.28),
        (0.45, 0.22, 0.17),
    ],
    "steel": [(0.55, 0.56, 0.56), (0.44, 0.45, 0.46), (0.40, 0.42, 0.40)],
    "brick": [(0.42, 0.24, 0.18), (0.36, 0.22, 0.18), (0.48, 0.32, 0.24)],
    "stone": [(0.46, 0.44, 0.40), (0.40, 0.38, 0.35)],
}
TILE_M = 512.0


def _variant(osm_id: int, count: int) -> int:
    h = (osm_id * 2654435761) & 0xFFFFFFFF
    h ^= h >> 15
    return int(h % max(1, count))


def build(
    spec,
    fp,
    level_root: Path,
    level_url: str,
    pid,
    *,
    dem: np.ndarray,
    dsm: np.ndarray,
    ground: np.ndarray,
    base_rgb: np.ndarray | None,
    res: float,
    data_root: Path,
    log=lambda msg: None,
) -> dict:
    """Measure, mesh and place every OSM building inside the level.

    Returns the TSStatic items, the materials they need, the mask the bump detector
    and the forest must not plant in, and the numbers for the build ledger.
    """

    from scipy import ndimage

    from . import foliage_textures as ft
    from .meshgen import write_dae
    from .scene_objects import _bilinear, _material

    cfg = getattr(spec, "BUILDINGS", {}) or {}
    # The cloud is gridded once at fetch time and the level's sample count can differ.
    # Without this the outlines were rasterised with the LEVEL's geometry into the
    # CLOUD's array: every height came from a quarter of the map at half scale, which
    # is how a town of six to nine metre cottages measured a 17 m median ridge.
    if dsm.shape != dem.shape:
        from .pointcloud import _regrid_canopy

        counts = np.ones(dsm.shape, dtype="uint16")
        dsm, ground, _counts = _regrid_canopy(dsm, ground, counts, dem.shape)
        log(f"  canopy grid regridded {counts.shape[0]} -> {dem.shape[0]} for the outlines")
    path = data_root / "osm" / "buildings.json"
    if not cfg or not path.is_file():
        return {"items": [], "materials": {}, "mask": None, "stats": {"count": 0}}

    mod_id = spec.MOD_ID
    half = fp.size_m / 2.0
    n = dem.shape[0]
    seed = int(cfg.get("seed", 41))
    wall_tile_m = float(cfg.get("wall_tile_m", 4.0))
    roof_tile_m = float(cfg.get("roof_tile_m", 2.0))

    outlines = load_footprints(path, fp, min_area_m2=float(cfg.get("min_area_m2", 12.0)))
    log(f"  {len(outlines)} OSM outlines inside the level")

    shapes_dir = level_root / "art" / "shapes" / f"{mod_id}_buildings"
    tex_dir = shapes_dir / "textures"
    shapes_url = f"{level_url}/art/shapes/{mod_id}_buildings"
    tex_url = f"{shapes_url}/textures"
    shapes_dir.mkdir(parents=True, exist_ok=True)
    tex_dir.mkdir(parents=True, exist_ok=True)

    materials: dict = {}
    written: set[str] = set()

    def wall_material(family: str, variant: int) -> str:
        name = f"{mod_id}_wall_{family}_{variant}"
        if name not in written:
            ft.facade_set(
                tex_dir,
                name,
                seed + 17 * variant + (stable_hash(family) % 997),
                int(cfg.get("facade_px", 1024)),
                family=family,
                colour=WALL_COLOURS[family][variant],
            )
            materials[name] = _material(mod_id, name, tex_url, kind="rock", pid=pid)
            written.add(name)
        return name

    def roof_material(colour: str) -> str:
        name = f"{mod_id}_roof_{colour}"
        if name not in written:
            ft.roof_set(
                tex_dir,
                name,
                seed + 101 + (stable_hash(colour) % 997),
                int(cfg.get("roof_px", 512)),
                colour=ROOF_COLOURS[colour],
            )
            materials[name] = _material(mod_id, name, tex_url, kind="rock", pid=pid)
            written.add(name)
        return name

    def terrain_z(x: float, y: float) -> float:
        return _bilinear(dem, res, fp.size_m, x, y)

    mask = np.zeros((n, n), dtype=bool)
    tiles: dict[tuple[int, int], list] = {}
    kept: list[dict] = []
    dropped = {"no_lidar": 0, "too_short": 0}
    reasons: dict[str, int] = {}
    for outline in outlines:
        measured = measure(
            outline,
            dsm,
            ground,
            dem,
            res,
            half,
            min_height_m=float(cfg.get("min_height_m", 2.2)),
            max_height_m=float(cfg.get("max_height_m", 40.0)),
            roof_band_m=float(cfg.get("roof_band_m", 3.0)),
        )
        if measured is None:
            dropped["no_lidar"] += 1
            hit = rasterize_ring(outline["ring"], res, half, n)
            why = "too_few_cells" if hit is None or hit[0].size < 4 else "height_out_of_range"
            reasons[why] = reasons.get(why, 0) + 1
            continue
        hit = rasterize_ring(outline["ring"], res, half, n)
        if hit is not None:
            mask[hit] = True
        family = wall_family(outline["tags"])
        variant = _variant(outline["id"], len(WALL_COLOURS[family]))
        colour = roof_colour(outline, base_rgb, res, half) if base_rgb is not None else "galv"
        measured["wall"] = f"{family}_{variant}"
        measured["roof_colour"] = colour
        cx = sum(x for x, _ in outline["ring"]) / len(outline["ring"])
        cy = sum(y for _, y in outline["ring"]) / len(outline["ring"])
        key = (math.floor(cy / TILE_M), math.floor(cx / TILE_M))
        origin = ((key[1] + 0.5) * TILE_M, (key[0] + 0.5) * TILE_M, 0.0)
        tiles.setdefault(key, []).append(
            building_meshes(
                measured,
                terrain_z,
                wall_material=wall_material(family, variant),
                roof_material=roof_material(colour),
                wall_tile_m=wall_tile_m,
                roof_tile_m=roof_tile_m,
                origin=origin,
            )
        )
        kept.append(measured)

    # A roof is a bump and a bump is a boulder; a roof is also 6 m above the ground and
    # the canopy model would call it a tree. Grow the mask 2 m so an eaves overhang and
    # a porch go with the building.
    if kept:
        mask = ndimage.binary_dilation(mask, iterations=max(1, int(2.0 / res)))

    items = []
    triangles = 0
    for key in sorted(tiles):
        meshes = [m for group in tiles[key] for m in group]
        triangles += sum(m.triangle_count for m in meshes)
        name = f"tile_r{key[0]:+03d}_c{key[1]:+03d}"
        write_dae(shapes_dir / f"{name}.dae", meshes, f"{mod_id}_{name}")
        items.append(
            {
                "name": f"{mod_id}_buildings_{name}",
                "class": "TSStatic",
                "persistentId": pid(f"buildings:{name}"),
                "position": [(key[1] + 0.5) * TILE_M, (key[0] + 0.5) * TILE_M, 0.0],
                "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "scale": [1, 1, 1],
                "shapeName": f"{shapes_url}/{name}.dae",
                "collisionType": "Visible Mesh Final",
                "decalType": "Visible Mesh Final",
                "useInstanceRenderData": True,
                "instanceColor": [1, 1, 1, 1],
                "__parent": "buildings",
            }
        )

    roofs: dict[str, int] = {}
    walls: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for b in kept:
        roofs[b["roof_colour"]] = roofs.get(b["roof_colour"], 0) + 1
        walls[b["wall"].split("_")[0]] = walls.get(b["wall"].split("_")[0], 0) + 1
        kinds[b["roof"]] = kinds.get(b["roof"], 0) + 1
    heights = [b["ridge_m"] for b in kept]
    stats = {
        "outlines": len(outlines),
        "count": len(kept),
        "dropped_no_lidar": dropped["no_lidar"],
        "dropped_why": dict(sorted(reasons.items())),
        "roof_band_m": float(cfg.get("roof_band_m", 3.0)),
        "tiles": len(tiles),
        "triangles": int(triangles),
        "roof_kinds": dict(sorted(kinds.items())),
        "roof_colours": dict(sorted(roofs.items())),
        "wall_families": dict(sorted(walls.items())),
        "ridge_p50_m": round(float(np.percentile(heights, 50)), 2) if heights else 0.0,
        "ridge_p95_m": round(float(np.percentile(heights, 95)), 2) if heights else 0.0,
        "ridge_max_m": round(float(max(heights)), 2) if heights else 0.0,
        "mask_cells": int(mask.sum()),
    }
    if materials:
        (shapes_dir / "main.materials.json").write_text(
            json.dumps(dict(sorted(materials.items())), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    stats["materials"] = len(materials)
    stats["shapes_dir"] = f"art/shapes/{mod_id}_buildings"
    log(
        f"  {stats['count']} buildings in {stats['tiles']} tiles, "
        f"{stats['triangles'] / 1e3:.0f} k triangles, ridge p50 {stats['ridge_p50_m']} m"
    )
    return {"items": items, "materials": materials, "mask": mask, "stats": stats, "kept": kept}
