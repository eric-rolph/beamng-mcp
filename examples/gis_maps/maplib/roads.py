"""Roads as terrain, not just decals.

OpenStreetMap gives centrelines; the lidar gives a surface that, at 0.5-1 m, still has
the road's crown, ruts, cut banks and every noise return on it, and the decal that
draws the road does nothing for the physics. ``carve`` smooths the profile along
each way, flattens the bed across its width, feathers into the banks, and returns a
mask the terrain stage paints with a road material whose ground model the tyres feel.
"""

from __future__ import annotations

import itertools
import json
import math

import numpy as np


def _lonlat_to_level(fp, lons, lats):
    from rasterio.warp import transform

    xs, ys = transform("EPSG:4326", f"EPSG:{fp.epsg}", list(lons), list(lats))
    cx, cy = fp.center
    return [(x - cx, y - cy) for x, y in zip(xs, ys, strict=True)]


def road_polylines(spec, fp, osm_path) -> list[dict]:
    """OSM ways in the spec's include list, as level-frame polylines with width/surface."""

    payload = json.loads(osm_path.read_text(encoding="utf-8"))
    include = set(spec.ROADS["include"])
    widths = spec.ROADS["widths"]
    surface_by_type = spec.ROADS.get("surface_by_type", {})
    exclude_ways = {int(v) for v in spec.ROADS.get("exclude_ways", [])}
    half = fp.size_m / 2.0 - 2.0
    out = []
    for element in payload.get("elements", []):
        if element.get("type") != "way" or int(element.get("id", -1)) in exclude_ways:
            continue
        tags = element.get("tags", {})
        highway = tags.get("highway")
        if highway not in include:
            continue
        geometry = element.get("geometry", [])
        if len(geometry) < 2:
            continue
        points = _lonlat_to_level(fp, [p["lon"] for p in geometry], [p["lat"] for p in geometry])
        runs: list[list[tuple[float, float]]] = [[]]
        for x, y in points:
            if -half <= x <= half and -half <= y <= half:
                runs[-1].append((x, y))
            elif runs[-1]:
                runs.append([])
        surface = tags.get("surface", "")
        kind = surface_by_type.get(highway, "dirt")
        if surface in ("asphalt", "paved", "concrete"):
            kind = "paved"
        elif surface in ("gravel", "dirt", "unpaved", "ground", "compacted", "fine_gravel"):
            kind = "dirt" if kind != "paved" or surface != "compacted" else kind
        for index, run in enumerate(r for r in runs if len(r) >= 2):
            out.append(
                {
                    "id": f"{element['id']}_{index}",
                    "highway": highway,
                    "surface": kind,
                    "width": float(widths.get(highway, 4.0)),
                    "points": run,
                    "name": tags.get("name", ""),
                }
            )
    return out


def drop_cliff_segments(
    polylines: list[dict],
    dem: np.ndarray,
    res: float,
    fp_size_m: float,
    max_grade: float,
    *,
    min_length_m: float = 20.0,
    join_radius_m: float = 8.0,
) -> tuple[list[dict], int]:
    """Cut every polyline where the ground steps more steeply than ``max_grade``.

    An OSM way drawn across a cliff (a stub that ends at a waterfall, a track that
    the mapper continued over a ledge) would otherwise become a decal road with a
    20 m drop in one segment. The pieces on either side survive if they are at least
    ``min_length_m`` long, or, whatever their length, if both their ends lie within
    ``join_radius_m`` of a surviving piece (a 70 m OSM way that links two long ways
    is the road, not a stub). Returns the new list and the number of cuts made.
    """

    n = dem.shape[0]
    half = fp_size_m / 2.0

    def height(x: float, y: float) -> float:
        col = int(min(max((x + half) / res, 0), n - 1))
        row = int(min(max((half - y) / res, 0), n - 1))
        return float(dem[row, col])

    out: list[dict] = []
    short: list[dict] = []
    cuts = 0
    for road in polylines:
        dense = densify(road["points"], 4.0)
        pieces: list[list[tuple[float, float]]] = [[tuple(dense[0])]]
        for a, b in itertools.pairwise(dense):
            run = math.hypot(b[0] - a[0], b[1] - a[1])
            grade = abs(height(*b) - height(*a)) / max(run, 1e-6)
            if grade > max_grade:
                cuts += 1
                pieces.append([])
            pieces[-1].append(tuple(b))
        for index, piece in enumerate(pieces):
            if len(piece) < 2:
                continue
            length = sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in itertools.pairwise(piece))
            entry = dict(road)
            entry["points"] = [(float(x), float(y)) for x, y in piece]
            if index:
                entry["id"] = f"{road['id']}_{index}"
            (out if length >= min_length_m else short).append(entry)
    if short and out:
        kept_points = np.concatenate([densify(r["points"], 2.0) for r in out])
        kept_z = np.array([height(x, y) for x, y in kept_points])
        for entry in short:
            ends = np.array([entry["points"][0], entry["points"][-1]])
            gaps = ((ends[:, None, :] - kept_points[None, :, :]) ** 2).sum(axis=-1)
            nearest = gaps.argmin(axis=1)
            d = np.sqrt(gaps[np.arange(2), nearest])
            dz = np.abs(np.array([height(*e) for e in ends]) - kept_z[nearest])
            # A short link between two surviving ways, at their height: a stub that
            # meets a way 7 m below it is the mapper's line over a ledge.
            if (d <= join_radius_m).all() and (dz <= 1.0).all():
                out.append(entry)
    return out, cuts


def clear_corridor(
    dem: np.ndarray,
    res: float,
    fp_size_m: float,
    polylines: list[dict],
    *,
    open_m: float = 6.0,
    extra_m: float = 3.0,
    min_bump_m: float = 0.3,
) -> tuple[np.ndarray, int]:
    """Take every bump over ``min_bump_m`` out of the road corridors before carving.

    A juniper the detector let through, a kerb, a sign: anything the carve would have
    to climb inside width/2 + ``extra_m`` of a centreline is opened away first, so the
    bed and the decal nodes never meet a residual bump. Returns (dem, cells lowered).
    """

    from scipy import ndimage

    n = dem.shape[0]
    half = fp_size_m / 2.0
    corridor = np.zeros((n, n), dtype=bool)
    widest = 0.0
    for road in polylines:
        dense = densify(road["points"], res)
        cols = np.clip(((dense[:, 0] + half) / res).astype(int), 0, n - 1)
        rows = np.clip(((half - dense[:, 1]) / res).astype(int), 0, n - 1)
        corridor[rows, cols] = True
        widest = max(widest, float(road["width"]))
    if not corridor.any():
        return dem, 0
    corridor = ndimage.binary_dilation(corridor, iterations=int((widest / 2.0 + extra_m) / res) + 1)
    radius = int(open_m / 2.0 / res)
    yy, xx = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    disc = (xx * xx + yy * yy) <= radius * radius
    opened = ndimage.grey_opening(dem, footprint=disc, mode="nearest")
    bump = corridor & ((dem - opened) > min_bump_m)
    bump = ndimage.binary_dilation(bump, iterations=1)
    out = np.where(bump, opened, dem).astype("float32")
    return out, int(bump.sum())


def densify(points: list[tuple[float, float]], step: float) -> np.ndarray:
    pts = np.asarray(points, dtype="float64")
    out = [pts[0]]
    for a, b in itertools.pairwise(pts):
        length = float(np.hypot(*(b - a)))
        n = max(1, math.ceil(length / step))
        for i in range(1, n + 1):
            out.append(a + (b - a) * (i / n))
    return np.asarray(out)


def carve(
    dem: np.ndarray,
    res: float,
    fp_size_m: float,
    polylines: list[dict],
    *,
    profile_window_m: float = 30.0,
    feather_m: float = 2.5,
    junction_snap_m: float = 0.0,
    bridge_m: float = 20.0,
    end_feather_m: float = 10.0,
    max_profile_grade: float = 0.0,
    max_cut_fill_m: float = 2.0,
    crossfall: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Return (dem, road_mask, surface_index, stats).

    ``road_mask`` is True on the bed (within half the width); ``surface_index`` holds
    0 = none, 1 = paved, 2 = dirt per cell so the layer painter can pick a material.
    """

    from scipy import ndimage

    n = dem.shape[0]
    half = fp_size_m / 2.0
    target = np.full((n, n), np.nan, dtype="float32")
    halfwidth = np.zeros((n, n), dtype="float32")
    surface = np.zeros((n, n), dtype="uint8")
    stamped = np.zeros((n, n), dtype=bool)
    stats = {"roads": 0, "length_m": 0.0, "max_cut_m": 0.0, "max_fill_m": 0.0}

    def sample(xs, ys):
        cols = np.clip((xs + half) / res, 0, n - 1.001)
        rows = np.clip((half - ys) / res, 0, n - 1.001)
        c0, r0 = cols.astype(int), rows.astype(int)
        fc, fr = cols - c0, rows - r0
        return (
            dem[r0, c0] * (1 - fc) * (1 - fr)
            + dem[r0, np.minimum(c0 + 1, n - 1)] * fc * (1 - fr)
            + dem[np.minimum(r0 + 1, n - 1), c0] * (1 - fc) * fr
            + dem[np.minimum(r0 + 1, n - 1), np.minimum(c0 + 1, n - 1)] * fc * fr
        )

    strength = np.zeros((n, n), dtype="float32")
    way_of = np.full((n, n), -1, dtype="int64")  # which way stamped a cell
    # Every way's endpoints: an end within reach of another way's line is a
    # junction whatever the carving order, and is never cut back.
    all_points = [densify(r["points"], 2.0) for r in polylines if len(r["points"]) >= 2]
    ends_of: dict[int, list[np.ndarray]] = {}
    for index, pts in enumerate(all_points):
        others = [q for j, q in enumerate(all_points) if j != index]
        if not others:
            ends_of[index] = [pts[0], pts[-1]]
            continue
        other_pts = np.concatenate(others)
        junction_ends = []
        for end_pt in (pts[0], pts[-1]):
            if np.sqrt(((other_pts - end_pt) ** 2).sum(axis=1)).min() <= max(junction_snap_m, 8.0):
                junction_ends.append(end_pt)
        ends_of[index] = junction_ends
    stats["rejected_steep"] = 0
    # Longest ways first, so a spur meets the main road's bed and not the other way round.
    ordered = sorted(polylines, key=lambda r: -len(densify(r["points"], 4.0)))
    ramp_m = 30.0

    def ramp_to(profile: dict, index: int, z_join: float) -> None:
        # A smoothstep ramp onto the join height over 30 m: the grade is continuous
        # where the ramp ends, not a kink of the whole offset.
        along_p = profile["along"]
        dist = along_p if index == 0 else along_p[-1] - along_p
        t = np.clip(dist / ramp_m, 0.0, 1.0)
        pull = 1.0 - t * t * (3.0 - 2.0 * t)
        profile["smooth"] = profile["smooth"] + (z_join - profile["smooth"][index]) * pull

    # Pass 1: every way's grade line on its own.
    profiles: list[dict] = []
    for road in ordered:
        dense = densify(road["points"], res * 0.5)
        if dense.shape[0] < 4:
            continue
        # A free end on a gorge lip (a cut fragment whose next 5 m of ground is a
        # metre or more off its own bed) is cut back to where the ground goes on.
        step_px = res * 0.5
        road_index = next(
            (k for k, r in enumerate(polylines) if r is road or r["id"] == road["id"]), None
        )
        junction_pts = ends_of.get(road_index, []) if road_index is not None else []
        for end in ("start", "end"):
            end_pt = dense[0] if end == "start" else dense[-1]
            if any(np.hypot(*(end_pt - jp)) <= 1.0 for jp in junction_pts):
                continue  # this end meets another way: a junction, never a lip
            for _trim in range(int(30.0 / max(step_px, 1e-6)) // 10 + 1):
                if dense.shape[0] < 12:
                    break
                p = dense[0] if end == "start" else dense[-1]
                q = dense[4] if end == "start" else dense[-5]
                direction = p - q
                norm = float(np.hypot(*direction))
                if norm < 1e-6:
                    break
                beyond = p + direction / norm * 5.0
                r_b = int(min(max((half - beyond[1]) / res, 0), n - 1))
                c_b = int(min(max((beyond[0] + half) / res, 0), n - 1))
                z_p = float(sample(np.array([p[0]]), np.array([p[1]]))[0])
                if abs(float(dem[r_b, c_b]) - z_p) <= 1.0:
                    break
                dense = dense[10:] if end == "start" else dense[:-10]
        if dense.shape[0] < 4:
            continue
        z = sample(dense[:, 0], dense[:, 1]).astype("float64")
        seg = np.hypot(*np.diff(dense, axis=0).T)
        length = float(seg.sum())
        along = np.concatenate([[0.0], np.cumsum(seg)])
        # Bounded along-path smoothing: successively shorter moving averages, each
        # clamped to the cut/fill budget, so the bed follows a smooth grade line where
        # the terrain allows it and never digs a trench or builds a causeway where a
        # cliff-edge centreline would ask for one.
        smooth = z.copy()
        for window_m in (profile_window_m, profile_window_m / 2.0, profile_window_m / 4.0, 4.0):
            window = max(3, int(window_m / (res * 0.5)))
            kernel = np.ones(window) / window
            padded = np.pad(smooth, window, mode="reflect")
            smooth = np.convolve(padded, kernel, mode="same")[window:-window]
            smooth = np.clip(smooth, z - max_cut_fill_m, z + max_cut_fill_m)
        if max_profile_grade > 0:
            # A bed the smoothing could not bring under the grade limit over a metre
            # is a mine track up a cliff, not a road: it stays terrain.
            metre = max(2, round(1.0 / (res * 0.5)))
            rise = np.abs(smooth[metre:] - smooth[:-metre])
            run = along[metre:] - along[:-metre]
            if rise.size and float((rise / np.maximum(run, 1e-6)).max()) > max_profile_grade:
                stats["rejected_steep"] += 1
                continue
        profiles.append(
            {
                "road": road,
                "dense": dense,
                "z": z,
                "smooth": smooth,
                "along": along,
                "length": length,
                "way_id": hash(str(road["id"]).split("_")[0]) & 0x7FFFFFFF,
                "joined": [False, False],
            }
        )

    # Pass 2: junctions solved jointly, before any bed is carved. An end within
    # ``junction_snap_m`` of another way takes that way's grade line there (the
    # shorter way defers; two ends meeting take their mean) and ramps onto it; two
    # free ends within ``bridge_m`` and 3 m of height are joined by a straight
    # bridge at their shared height, so no gap is left for the ground to hump.
    snap_m = max(junction_snap_m, 0.0)
    seam_steps: list[float] = []
    for i, pi in enumerate(profiles):
        for end_idx in (0, 1):
            index = 0 if end_idx == 0 else pi["dense"].shape[0] - 1
            p = pi["dense"][index]
            best = None
            if snap_m > 0:
                for j, pj in enumerate(profiles):
                    if j == i or pj["way_id"] == pi["way_id"]:
                        continue
                    d = np.hypot(*(pj["dense"] - p).T)
                    k = int(np.argmin(d))
                    if d[k] <= snap_m and (best is None or d[k] < best[0]):
                        best = (float(d[k]), j, k)
            if best is not None:
                _d, j, k = best
                pj = profiles[j]
                interior = 3 < k < pj["dense"].shape[0] - 4
                if interior or pj["length"] >= pi["length"]:
                    z_join = float(pj["smooth"][k])
                else:
                    z_join = 0.5 * (float(pj["smooth"][k]) + float(pi["smooth"][index]))
                    ramp_to(pj, k, z_join)
                    pj["joined"][0 if k < pj["dense"].shape[0] // 2 else 1] = True
                ramp_to(pi, index, z_join)
                pi["joined"][end_idx] = True
                continue
            # A gap bridge to another way's free end.
            for j, pj in enumerate(profiles):
                if j == i or pj["way_id"] == pi["way_id"]:
                    continue
                for kj in (0, pj["dense"].shape[0] - 1):
                    q = pj["dense"][kj]
                    gap = float(np.hypot(*(q - p)))
                    if gap <= snap_m or gap > bridge_m:
                        continue
                    if abs(float(pj["smooth"][kj]) - float(pi["smooth"][index])) > 3.0:
                        continue
                    z_join = 0.5 * (float(pj["smooth"][kj]) + float(pi["smooth"][index]))
                    ramp_to(pi, index, z_join)
                    ramp_to(pj, kj, z_join)
                    count = max(2, int(gap / (res * 0.5)))
                    bridge = np.linspace(p, q, count + 1)[1:]
                    if end_idx == 0:
                        pi["dense"] = np.concatenate([bridge[::-1], pi["dense"]])
                        pi["smooth"] = np.concatenate([np.full(count, z_join), pi["smooth"]])
                        pi["z"] = np.concatenate(
                            [sample(bridge[::-1, 0], bridge[::-1, 1]).astype("float64"), pi["z"]]
                        )
                    else:
                        pi["dense"] = np.concatenate([pi["dense"], bridge])
                        pi["smooth"] = np.concatenate([pi["smooth"], np.full(count, z_join)])
                        pi["z"] = np.concatenate(
                            [pi["z"], sample(bridge[:, 0], bridge[:, 1]).astype("float64")]
                        )
                    seg = np.hypot(*np.diff(pi["dense"], axis=0).T)
                    pi["along"] = np.concatenate([[0.0], np.cumsum(seg)])
                    pi["length"] = float(seg.sum())
                    pi["joined"][end_idx] = True
                    pj["joined"][0 if kj == 0 else 1] = True
                    stats["bridges"] = stats.get("bridges", 0) + 1
                    break
                if pi["joined"][end_idx]:
                    break

    # Pass 3: stamp, longest first; a spur never overwrites the bed it joins.
    for pi in profiles:
        road, dense, z, smooth, along = pi["road"], pi["dense"], pi["z"], pi["smooth"], pi["along"]
        cols = np.clip(((dense[:, 0] + half) / res).astype(int), 0, n - 1)
        rows = np.clip(((half - dense[:, 1]) / res).astype(int), 0, n - 1)
        way_id = pi["way_id"]
        end_weight = np.ones(dense.shape[0])
        for end_idx, index in ((0, 0), (1, dense.shape[0] - 1)):
            if pi["joined"][end_idx]:
                r0, c0 = int(rows[index]), int(cols[index])
                if stamped[r0, c0] and way_of[r0, c0] != way_id:
                    seam_steps.append(abs(float(target[r0, c0]) - float(smooth[index])))
                continue
            if end_feather_m > 0:
                dist = along if index == 0 else along[-1] - along
                end_weight = np.minimum(end_weight, np.clip(dist / end_feather_m, 0.0, 1.0))
        stats["max_cut_m"] = max(stats["max_cut_m"], float((z - smooth).max()))
        stats["max_fill_m"] = max(stats["max_fill_m"], float((smooth - z).max()))
        fresh = ~stamped[rows, cols]
        target[rows[fresh], cols[fresh]] = smooth[fresh]
        strength[rows[fresh], cols[fresh]] = end_weight[fresh]
        way_of[rows[fresh], cols[fresh]] = way_id
        halfwidth[rows[fresh], cols[fresh]] = road["width"] / 2.0
        surface[rows[fresh], cols[fresh]] = 1 if road["surface"] == "paved" else 2
        stamped[rows, cols] = True
        stats["roads"] += 1
        stats["length_m"] += pi["length"]
    stats["max_seam_step_m"] = round(max(seam_steps), 3) if seam_steps else 0.0
    stats["junctions"] = len(seam_steps)
    if not stamped.any():
        return dem, np.zeros((n, n), dtype=bool), surface, stats
    distance, indices = ndimage.distance_transform_edt(~stamped, return_indices=True)
    near_r, near_c = indices[0], indices[1]
    distance_m = distance * res
    hw = halfwidth[near_r, near_c]
    tz = target[near_r, near_c]
    # The nearest-cell height steps from cell to cell along a diagonal line and
    # ribs the banks: smooth the bed height field a couple of cells so the bank
    # follows the grade line, not the raster.
    tz = ndimage.gaussian_filter(tz.astype("float32"), 2.0)
    surf = surface[near_r, near_c]
    inside = distance_m <= hw
    ramp = np.clip((distance_m - hw) / feather_m, 0.0, 1.0)
    weight = np.where(inside, 1.0, 1.0 - (ramp * ramp * (3 - 2 * ramp)))
    weight = np.where(distance_m <= hw + feather_m, weight, 0.0).astype("float32")
    weight = weight * strength[near_r, near_c]
    carved = dem * (1 - weight) + tz * weight
    carved = np.where(np.isfinite(carved), carved, dem).astype("float32")
    road_mask = inside
    surface_index = np.where(road_mask, surf, 0).astype("uint8")
    stats["length_m"] = round(stats["length_m"], 1)
    stats["bed_cells"] = int(road_mask.sum())
    stats["max_cut_m"] = round(stats["max_cut_m"], 2)
    stats["max_fill_m"] = round(stats["max_fill_m"], 2)
    return carved, road_mask, surface_index, stats


def trim_free_ends(
    polylines: list[dict], trim_m: float, junction_snap_m: float = 8.0
) -> list[dict]:
    """Shorten every unjoined end of every way by ``trim_m``: the carve feathers the
    bed out over that length, so a decal drawn to the way's end would step off the
    bed onto the natural ground at its first node. An end within ``junction_snap_m``
    of another way is a junction and keeps its length."""

    if trim_m <= 0:
        return polylines
    dense_all = [densify(r["points"], 2.0) for r in polylines if len(r["points"]) >= 2]
    out = []
    for index, road in enumerate(polylines):
        if len(road["points"]) < 2:
            continue
        pts = dense_all[index]
        others = [q for j, q in enumerate(dense_all) if j != index]
        other_pts = np.concatenate(others) if others else None

        def joined(end_pt, others_pts=other_pts):
            if others_pts is None:
                return False
            return float(np.sqrt(((others_pts - end_pt) ** 2).sum(axis=1)).min()) <= max(
                junction_snap_m, 8.0
            )

        seg = np.sqrt((np.diff(pts, axis=0) ** 2).sum(axis=1))
        along = np.concatenate([[0.0], np.cumsum(seg)])
        lo = 0.0 if joined(pts[0]) else trim_m
        hi = along[-1] if joined(pts[-1]) else along[-1] - trim_m
        if hi - lo < 15.0:
            continue
        keep = (along >= lo) & (along <= hi)
        kept = pts[keep]
        if kept.shape[0] < 2:
            continue
        out.append({**road, "points": [(float(x), float(y)) for x, y in kept]})
    return out
