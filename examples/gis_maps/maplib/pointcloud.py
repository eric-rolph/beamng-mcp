"""USGS 3DEP point clouds from the public Entwine (EPT) index, gridded for a canopy.

``fetch_canopy`` walks the EPT hierarchy for the footprint, streams every node's LAZ
through ``laspy`` and grids the returns in the level frame: the highest return per
cell (a digital surface model), the lowest ground-classified return per cell and the
return counts. Nothing point-shaped is kept; each LAZ file is deleted once gridded.
``canopy_height`` then turns those grids plus the bare-earth DEM into a canopy height
model, from which the forest is planted at measured tree tops with measured heights.

The index is https://s3-us-west-2.amazonaws.com/usgs-lidar-public/<resource>/ept.json
(public domain, USGS 3DEP). Node keys are ``D-X-Y-Z`` in an octree whose root cube is
``bounds``; the hierarchy is a tree of JSON files where a count of -1 marks a node
whose own file holds the next levels.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

EPT_BASE = "https://s3-us-west-2.amazonaws.com/usgs-lidar-public"
NOISE_CLASSES = (7, 18)
GROUND_CLASS = 2


def _get_json(session, url: str) -> dict:
    response = session.get(url, timeout=120)
    response.raise_for_status()
    return response.json()


def node_bounds_xy(root: list[float], key: str) -> tuple[float, float, float, float]:
    """(x0, y0, x1, y1) of an octree node in the index's own coordinates."""

    depth, ix, iy, _iz = (int(v) for v in key.split("-"))
    size = (root[3] - root[0]) / float(1 << depth)
    return (
        root[0] + ix * size,
        root[1] + iy * size,
        root[0] + (ix + 1) * size,
        root[1] + (iy + 1) * size,
    )


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def walk_hierarchy(
    session, resource: str, root: list[float], query: tuple[float, float, float, float]
) -> list[str]:
    """Every node key holding points that may fall inside ``query`` (index coordinates)."""

    nodes: list[str] = []
    stack = ["0-0-0-0"]
    seen: set[str] = set()
    while stack:
        key = stack.pop()
        if key in seen:
            continue
        seen.add(key)
        entries = _get_json(session, f"{EPT_BASE}/{resource}/ept-hierarchy/{key}.json")
        for child, count in entries.items():
            if not _overlaps(node_bounds_xy(root, child), query):
                continue
            if count == -1:
                stack.append(child)
            elif count > 0:
                nodes.append(child)
    return sorted(set(nodes))


def _reduce_cells(index: np.ndarray, z: np.ndarray, n_cells: int):
    """Per-cell max and min of ``z`` grouped by flat cell ``index`` (sorted reduction)."""

    order = np.lexsort((z, index))
    idx_sorted = index[order]
    z_sorted = z[order]
    unique, first = np.unique(idx_sorted, return_index=True)
    last = np.concatenate([first[1:], [idx_sorted.size]]) - 1
    return unique, z_sorted[last], z_sorted[first]


def fetch_canopy(
    fp,
    out_dir: Path,
    resource: str,
    *,
    res: float = 1.0,
    margin_m: float = 30.0,
    force: bool = False,
    workers: int = 8,
    log=print,
) -> dict:
    """Grid the 3DEP returns over the footprint; returns the metadata written next to them.

    Writes ``canopy.npz`` (dsm: highest return, ground: lowest ground return, counts,
    ground_counts; NaN where a cell saw nothing) and ``canopy.json``.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    grid_file = out_dir / "canopy.npz"
    meta_file = out_dir / "canopy.json"
    if grid_file.is_file() and meta_file.is_file() and not force:
        return json.loads(meta_file.read_text(encoding="utf-8"))

    import laspy
    import requests
    from rasterio.warp import transform as warp_transform

    started = time.time()
    session = requests.Session()
    info = _get_json(session, f"{EPT_BASE}/{resource}/ept.json")
    epsg = int(info["srs"]["horizontal"])
    root = info["bounds"]
    index_crs, level_crs = f"EPSG:{epsg}", f"EPSG:{fp.epsg}"
    cx, cy = fp.center
    corners_x, corners_y = warp_transform(
        level_crs,
        index_crs,
        [fp.west, fp.east, fp.west, fp.east],
        [fp.south, fp.south, fp.north, fp.north],
    )
    query = (
        min(corners_x) - margin_m,
        min(corners_y) - margin_m,
        max(corners_x) + margin_m,
        max(corners_y) + margin_m,
    )
    nodes = walk_hierarchy(session, resource, root, query)
    log(f"  point cloud {resource}: {len(nodes)} octree nodes over the footprint")

    n = round(fp.size_m / res)
    half = fp.size_m / 2.0
    dsm = np.full(n * n, -np.inf, dtype="float32")
    ground = np.full(n * n, np.inf, dtype="float32")
    counts = np.zeros(n * n, dtype="uint32")
    ground_counts = np.zeros(n * n, dtype="uint32")
    laz_dir = out_dir / "laz"
    laz_dir.mkdir(exist_ok=True)
    points_read = 0
    points_used = 0

    def download(key: str) -> tuple[str, Path]:
        path = laz_dir / f"{key}.laz"
        if not path.is_file():
            with session.get(
                f"{EPT_BASE}/{resource}/ept-data/{key}.laz", stream=True, timeout=300
            ) as r:
                r.raise_for_status()
                tmp = path.with_suffix(".part")
                with tmp.open("wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                tmp.replace(path)
        return key, path

    def in_batches(pool, keys: list[str], batch: int):
        """``pool.map`` over ``keys``, but never more than ``batch`` downloads ahead.

        ``Executor.map`` submits every item up front, so the whole node set would land
        in ``laz_dir`` while the gridding loop below consumes it one at a time and the
        downloads - being the faster half - run away from it. On Black Bear Pass that is
        10,755 nodes, about 2.35 GB, held on disk instead of the few MB the delete-as-you-go
        contract implies. Batching keeps the pool saturated and the disk bounded.
        """

        for start in range(0, len(keys), batch):
            yield from pool.map(download, keys[start : start + batch])

    with ThreadPoolExecutor(max_workers=workers) as pool:
        ahead = max(workers * 4, 1)
        for done, (_key, path) in enumerate(in_batches(pool, nodes, ahead), start=1):
            las = laspy.read(path)
            x = np.asarray(las.x, dtype="float64")
            y = np.asarray(las.y, dtype="float64")
            z = np.asarray(las.z, dtype="float32")
            cls = np.asarray(las.classification, dtype="uint8")
            del las
            points_read += x.size
            keep = ~np.isin(cls, NOISE_CLASSES)
            lx, ly = warp_transform(index_crs, level_crs, x[keep], y[keep])
            z, cls = z[keep], cls[keep]
            cols = np.floor((np.asarray(lx) - cx + half) / res).astype("int64")
            rows = np.floor((half - (np.asarray(ly) - cy)) / res).astype("int64")
            inside = (cols >= 0) & (cols < n) & (rows >= 0) & (rows < n)
            if inside.any():
                index = rows[inside] * n + cols[inside]
                zi, ci = z[inside], cls[inside]
                points_used += int(inside.sum())
                unique, zmax, _zmin = _reduce_cells(index, zi, n * n)
                dsm[unique] = np.maximum(dsm[unique], zmax)
                counts += np.bincount(index, minlength=n * n).astype("uint32")
                is_ground = ci == GROUND_CLASS
                if is_ground.any():
                    gu, _gmax, gmin = _reduce_cells(index[is_ground], zi[is_ground], n * n)
                    ground[gu] = np.minimum(ground[gu], gmin)
                    ground_counts += np.bincount(index[is_ground], minlength=n * n).astype("uint32")
            path.unlink(missing_ok=True)
            if done % 100 == 0 or done == len(nodes):
                log(f"    {done}/{len(nodes)} nodes, {points_read / 1e6:.1f} M points read")

    dsm = np.where(np.isfinite(dsm), dsm, np.nan).reshape(n, n)
    ground = np.where(np.isfinite(ground), ground, np.nan).reshape(n, n)
    np.savez_compressed(
        grid_file,
        dsm=dsm.astype("float32"),
        ground=ground.astype("float32"),
        counts=np.minimum(counts, 65535).astype("uint16").reshape(n, n),
        ground_counts=np.minimum(ground_counts, 65535).astype("uint16").reshape(n, n),
    )
    meta = {
        "kind": "usgs_ept",
        "resource": resource,
        "index_epsg": epsg,
        "nodes": len(nodes),
        "points_read": int(points_read),
        "points_in_footprint": int(points_used),
        "density_per_m2": round(points_used / (fp.size_m * fp.size_m), 2),
        "grid_res_m": res,
        "grid_size": n,
        "cells_with_returns": round(float((counts > 0).mean()), 4),
        "cells_with_ground": round(float((ground_counts > 0).mean()), 4),
        "elapsed_s": round(time.time() - started, 1),
        "citation": (
            f"USGS 3DEP lidar point cloud {resource} via the public Entwine index "
            "(usgs-lidar-public)"
        ),
    }
    meta_file.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")
    try:
        laz_dir.rmdir()
    except OSError:
        pass
    return meta


def _regrid_canopy(dsm, ground, counts, shape):
    """Put a canopy grid on the DEM's grid when the two were gridded at different steps.

    The cloud is gridded once at fetch time and the level's sample count can change
    afterwards, so the two need not agree. Block-reducing by an integer factor is exact
    for what each array means: the surface takes the block MAXIMUM, because a tree top
    is the highest return over the ground it shades and averaging would shave it; the
    ground takes the block MINIMUM, because bare earth under a canopy is the lowest
    return; counts add. Anything else falls back to an area resample.
    """

    import numpy as np

    n, m = dsm.shape[0], shape[0]
    if n % m == 0:
        f = n // m
        blocks = (m, f, m, f)
        import warnings

        with warnings.catch_warnings():
            # A block with no return at all is legitimate over water and rock faces;
            # nanmax of nothing is NaN, which is exactly what the caller wants.
            warnings.simplefilter("ignore", RuntimeWarning)
            dsm = np.nanmax(dsm.reshape(blocks).transpose(0, 2, 1, 3).reshape(m, m, f * f), -1)
            ground = np.nanmin(
                ground.reshape(blocks).transpose(0, 2, 1, 3).reshape(m, m, f * f), -1
            )
        counts = counts.reshape(blocks).sum(axis=(1, 3), dtype="int64")
        return (
            dsm.astype("float32"),
            ground.astype("float32"),
            np.minimum(counts, 65535).astype("uint16"),
        )
    from PIL import Image

    def _rs(a, mode):
        return np.asarray(
            Image.fromarray(a.astype("float32"), mode="F").resize((m, m), Image.BOX)
        ).astype("float32")

    return _rs(dsm, "F"), _rs(ground, "F"), _rs(counts.astype("float32"), "F").astype("uint16")


def canopy_height(grid_file: Path, dem: np.ndarray, *, max_height_m: float = 60.0):
    """Canopy height model on the DEM grid from the gridded returns.

    Ground is the lowest ground return where the cloud has one, else the DEM; the
    cloud's vertical datum is levelled onto the DEM by the median ground offset. Cells
    without a return are 0 (nothing stands there). Returns (chm, stats).
    """

    from scipy import ndimage

    data = np.load(grid_file)
    dsm = data["dsm"].astype("float32")
    ground = data["ground"].astype("float32")
    counts = data["counts"]
    if dsm.shape != dem.shape:
        dsm, ground, counts = _regrid_canopy(dsm, ground, counts, dem.shape)
    has_ground = np.isfinite(ground)
    offset = float(np.nanmedian((ground - dem)[has_ground])) if has_ground.any() else 0.0
    base = np.where(has_ground, ground, dem + offset)
    # Ground returns under a canopy are sparse and noisy: take the local minimum of the
    # base over 3 m so a mis-classified branch never lowers a tree. On a slope that
    # minimum sits below the cell by about 1.5 m times the gradient, and the highest
    # return in the cell sits above it by half as much again; take that expected
    # relief out so a bare 40 degree scree is not two metres of "canopy".
    base = ndimage.minimum_filter(base, size=3, mode="nearest")
    gy, gx = np.gradient(ndimage.gaussian_filter(dem.astype("float64"), 1.0))
    relief = (2.0 * np.hypot(gx, gy)).astype("float32")
    chm = dsm - base - relief
    chm = np.where(np.isfinite(chm), chm, 0.0)
    chm = np.clip(chm, 0.0, max_height_m).astype("float32")
    chm[counts == 0] = 0.0
    stats = {
        "ground_offset_m": round(offset, 3),
        "cells_with_returns": round(float((counts > 0).mean()), 4),
        "canopy_over_2m": round(float((chm > 2.0).mean()), 4),
        "canopy_over_5m": round(float((chm > 5.0).mean()), 4),
        "height_p95_m": round(
            float(np.percentile(chm[chm > 2.0], 95)) if (chm > 2.0).any() else 0.0, 2
        ),
        "height_max_m": round(float(chm.max()), 2),
    }
    return chm, stats


def tree_tops(chm: np.ndarray, res: float, *, min_height_m: float = 2.0, smooth_px: float = 0.6):
    """Local maxima of the canopy with a height-dependent metric exclusion radius.

    Returns (rows, cols, heights) in descending height. A top is accepted only if no
    taller accepted top lies within ``max(1.5, 0.5 + 0.12 h)`` metres of it, which is
    the crown radius of a spruce or fir of height ``h``; the search is a KD-tree in
    metres, so nothing snaps to the raster's cell block.
    """

    from scipy import ndimage
    from scipy.spatial import cKDTree

    smooth = ndimage.gaussian_filter(chm, smooth_px) if smooth_px > 0 else chm
    peaks = (smooth >= ndimage.maximum_filter(smooth, size=3, mode="nearest")) & (
        smooth >= min_height_m
    )
    rows, cols = np.nonzero(peaks)
    heights = smooth[rows, cols]
    order = np.argsort(-heights, kind="stable")
    rows, cols, heights = rows[order], cols[order], heights[order]
    if rows.size == 0:
        return rows, cols, heights
    points = np.column_stack([cols * res, rows * res])
    radii = np.maximum(1.5, 0.5 + 0.12 * heights)
    tree = cKDTree(points)
    neighbours = tree.query_ball_point(points, r=radii)
    suppressed = np.zeros(rows.size, dtype=bool)
    keep = np.zeros(rows.size, dtype=bool)
    for i in range(rows.size):
        if suppressed[i]:
            continue
        keep[i] = True
        for j in neighbours[i]:
            if j > i:  # lower or equal height, later in the order
                suppressed[j] = True
    return rows[keep], cols[keep], heights[keep]
