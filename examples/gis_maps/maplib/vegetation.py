"""Tree cover from the orthoimagery, and a forest planted from it.

NAIP at 0.6-1 m shows every conifer crown as a dark green blob with its own shadow, an
aspen grove as a lighter yellow-green mass, and a meadow as smooth bright green. The
classifier here uses exactly those three cues (green excess, darkness, local texture)
and the DEM (treeline, aspect) to decide where trees stand, which species, and how tall.
Placement is a jittered grid thinned by local cover, so the forest edge follows the
photograph rather than a painted polygon.
"""

from __future__ import annotations

import math

import numpy as np

from . import heightmap as hm


def cover_maps(
    colour_u8: np.ndarray, dem: np.ndarray, res: float, forest_spec: dict
) -> dict[str, np.ndarray]:
    """Per-cell class maps at the colour grid: conifer, broadleaf, meadow (0..1 soft masks)."""

    from scipy import ndimage

    c = colour_u8.astype("float32") / 255.0
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    green = 2 * g - r - b
    bright = c.mean(axis=-1)
    # Local texture: crowns and their shadows make the 5x5 std high; meadows are smooth.
    mean = ndimage.uniform_filter(bright, size=5)
    sq = ndimage.uniform_filter(bright * bright, size=5)
    texture = np.sqrt(np.clip(sq - mean * mean, 0, None))
    green_s = ndimage.uniform_filter(green, size=3)
    conifer = (
        (green_s > forest_spec.get("green_min", 0.03))
        & (bright < forest_spec.get("conifer_max_brightness", 0.36))
        & (texture > forest_spec.get("texture_min", 0.025))
    )
    broadleaf = (
        (green_s > forest_spec.get("green_min", 0.03) + 0.04)
        & (bright >= forest_spec.get("conifer_max_brightness", 0.36))
        & (bright < 0.55)
        & (r > b + 0.02)
    )
    meadow = (green_s > forest_spec.get("green_min", 0.03)) & ~conifer & ~broadleaf
    if dem.shape[0] != colour_u8.shape[0]:
        from PIL import Image

        dem = np.asarray(
            Image.fromarray(dem.astype("float32"), mode="F").resize(
                (colour_u8.shape[1], colour_u8.shape[0]), Image.BILINEAR
            )
        )
    treeline = float(forest_spec.get("treeline_m", 3600.0))
    krummholz_band = float(forest_spec.get("krummholz_band_m", 120.0))
    conifer &= dem < treeline
    broadleaf &= dem < float(forest_spec.get("broadleaf_max_m", treeline - 400.0))
    # Cover density: fraction of forest cells in a ~12 m window, so the sampler can thin.
    win = max(3, int(12.0 / (res * dem.shape[0] / colour_u8.shape[0])))
    conifer_density = ndimage.uniform_filter(conifer.astype("float32"), size=win)
    broadleaf_density = ndimage.uniform_filter(broadleaf.astype("float32"), size=win)
    lin = (colour_u8.astype("float32") / 255.0) ** 2.2
    return {
        "conifer": conifer,
        "broadleaf": broadleaf,
        "meadow": meadow,
        "conifer_colour": [float(v) for v in lin[conifer].mean(axis=0)] if conifer.any() else None,
        "broadleaf_colour": [float(v) for v in lin[broadleaf].mean(axis=0)]
        if broadleaf.any()
        else None,
        "conifer_density": conifer_density,
        "broadleaf_density": broadleaf_density,
        "krummholz": conifer & (dem >= treeline - krummholz_band),
    }


def plant(
    maps: dict[str, np.ndarray],
    dem: np.ndarray,
    res: float,
    fp_size_m: float,
    min_elevation: float,
    forest_spec: dict,
    *,
    seed: int = 7,
    road_mask: np.ndarray | None = None,
    exclude_points: list[tuple[float, float, float]] | None = None,
) -> tuple[list[dict], dict]:
    """Jittered-grid planting thinned by cover. Returns (trees, stats).

    Each tree: species, x, y (level frame), z (terrain-relative), height_m, scale, yaw.
    """

    from scipy import ndimage

    rng = np.random.default_rng(seed)
    n_c = maps["conifer"].shape[0]
    n_d = dem.shape[0]
    grid_res = fp_size_m / n_c
    spacing = float(forest_spec.get("spacing_m", 6.0))
    treeline = float(forest_spec.get("treeline_m", 3600.0))
    krummholz_band = float(forest_spec.get("krummholz_band_m", 120.0))
    max_trees = int(forest_spec.get("max_trees", 80000))
    half = fp_size_m / 2.0
    # Candidate points on a jittered grid.
    count = int(fp_size_m / spacing)
    gx, gy = np.meshgrid(np.arange(count), np.arange(count))
    # jitter_cells 1 keeps every tree inside its own cell (an even stipple); 1.5 lets
    # them cross into the neighbours' cells so stands clump and open like a real wood.
    jitter = float(forest_spec.get("jitter_cells", 1.0))
    lo, hi = 0.5 - 0.35 * jitter, 0.5 + 0.35 * jitter
    xs = (gx.ravel() + rng.uniform(lo, hi, gx.size)) * spacing - half
    ys = half - (gy.ravel() + rng.uniform(lo, hi, gy.size)) * spacing
    cols = np.clip(((xs + half) / grid_res).astype(int), 0, n_c - 1)
    rows = np.clip(((half - ys) / grid_res).astype(int), 0, n_c - 1)
    dcols = np.clip(((xs + half) / res).astype(int), 0, n_d - 1)
    drows = np.clip(((half - ys) / res).astype(int), 0, n_d - 1)
    conifer_d = maps["conifer_density"][rows, cols]
    broadleaf_d = maps["broadleaf_density"][rows, cols]
    # Slope: nothing grows on cliffs.
    gyd, gxd = np.gradient(ndimage.gaussian_filter(dem.astype("float64"), 1.0), res)
    slope = np.degrees(np.arctan(np.hypot(gxd, gyd)))[drows, dcols]
    # Canopy gaps at 30-60 m so the stand is not a uniform stipple.
    coarse = max(4, n_c // 16)
    gaps = ndimage.gaussian_filter(rng.uniform(0, 1, (coarse, coarse)), 1.2)
    gaps = (gaps - gaps.min()) / max(gaps.max() - gaps.min(), 1e-6)
    gap_rows = np.minimum(rows * coarse // n_c, coarse - 1)
    gap_cols = np.minimum(cols * coarse // n_c, coarse - 1)
    gap_strength = float(forest_spec.get("gap_strength", 0.45))
    gap_factor = (1.0 - gap_strength) + gap_strength * gaps[gap_rows, gap_cols]
    keep_conifer = rng.uniform(0, 1, xs.size) < np.clip(conifer_d * 1.15, 0, 1) ** 1.3 * gap_factor
    keep_broadleaf = (~keep_conifer) & (
        rng.uniform(0, 1, xs.size) < np.clip(broadleaf_d * 1.1, 0, 1) ** 1.3 * gap_factor
    )
    keep = (keep_conifer | keep_broadleaf) & (slope < float(forest_spec.get("max_slope_deg", 42.0)))
    if road_mask is not None:
        rmask = ndimage.binary_dilation(road_mask, iterations=int(4 / res) + 1)
        keep &= ~rmask[drows, dcols]
    for ex, ey, radius in exclude_points or []:
        keep &= (xs - ex) ** 2 + (ys - ey) ** 2 > radius * radius
    idx = np.nonzero(keep)[0]
    if idx.size > max_trees:
        idx = rng.choice(idx, size=max_trees, replace=False)
    trees = []
    species_counts: dict[str, int] = {}
    bands = forest_spec.get(
        "height_bands", [[0, 3300, 12, 22], [3300, 3480, 7, 14], [3480, 9999, 4, 9]]
    )
    ground = hm.sample_bilinear(dem, res, fp_size_m, xs, ys)
    for i in idx:
        z = float(ground[i])
        if keep_conifer[i]:
            if z >= treeline - krummholz_band:
                if rng.uniform() > float(forest_spec.get("krummholz_keep", 0.6)):
                    continue
                species = "krummholz"
                height = rng.uniform(1.4, 3.2) * (
                    1.0 - 0.5 * (z - (treeline - krummholz_band)) / krummholz_band
                )
            else:
                lo_h, hi_h = 8.0, 18.0
                for lo, hi, h0, h1 in bands:
                    if lo <= z < hi:
                        lo_h, hi_h = h0, h1
                        break
                species = "spruce" if rng.uniform() < 0.65 else "fir"
                height = rng.uniform(lo_h, hi_h) * rng.uniform(0.8, 1.2)
        else:
            species = "aspen"
            height = rng.uniform(7.0, 14.0) * rng.uniform(0.8, 1.2)
        species_counts[species] = species_counts.get(species, 0) + 1
        trees.append(
            {
                "species": species,
                "x": round(float(xs[i]), 2),
                "y": round(float(ys[i]), 2),
                "z": round(z - min_elevation - 0.1, 2),
                "height_m": round(float(height), 2),
                "yaw_deg": round(float(rng.uniform(0, 360)), 1),
            }
        )
    stats = {
        "candidates": int(xs.size),
        "trees": len(trees),
        "species": species_counts,
        "conifer_cover_fraction": round(float(maps["conifer"].mean()), 4),
        "broadleaf_cover_fraction": round(float(maps["broadleaf"].mean()), 4),
        "spacing_m": spacing,
        "treeline_m": treeline,
    }
    return trees, stats


def shrubs_from_imagery(
    colour_u8: np.ndarray,
    dem: np.ndarray,
    res: float,
    fp_size_m: float,
    min_elevation: float,
    cfg: dict,
    *,
    seed: int = 3,
    exclude: list[dict] | None = None,
    layer: np.ndarray | None = None,
    allowed_layers: set[int] | None = None,
    max_slope_deg: float | None = None,
    unplaced: list | None = None,
) -> list[dict]:
    """Dark compact dots in the imagery (junipers, saltbush) that the lidar did not keep.

    A bump-less shrub still darkens its pixels against the plain: find blobs darker than
    the local ground by ``contrast`` with a plausible crown area, skip anything already
    placed within 2 m, and return shrub placements sized from the blob.
    """

    from scipy import ndimage

    rng = np.random.default_rng(seed)
    grid_res = fp_size_m / colour_u8.shape[0]
    bright = colour_u8.astype("float32").mean(axis=-1) / 255.0
    # Darkness against the local ground (a 20 m median), never an absolute level: a
    # shaded wall is dark everywhere and holds no dots.
    local = ndimage.median_filter(bright, size=max(9, int(20.0 / grid_res)), mode="nearest")
    dark = (local - bright) > float(cfg.get("contrast", 0.12))
    dark &= bright < float(cfg.get("max_brightness", 0.45))
    if layer is not None and allowed_layers:
        allowed = np.isin(layer, list(allowed_layers))
        if allowed.shape != dark.shape:
            from PIL import Image

            allowed = (
                np.asarray(
                    Image.fromarray(allowed.astype("uint8") * 255).resize(
                        dark.shape[::-1], Image.NEAREST
                    )
                )
                > 127
            )
        dark &= allowed
    if max_slope_deg is not None:
        gyd, gxd = np.gradient(ndimage.gaussian_filter(dem.astype("float64"), 1.0), res)
        steep = np.degrees(np.arctan(np.hypot(gxd, gyd))) > float(max_slope_deg)
        if steep.shape != dark.shape:
            from PIL import Image

            steep = (
                np.asarray(
                    Image.fromarray(steep.astype("uint8") * 255).resize(
                        dark.shape[::-1], Image.NEAREST
                    )
                )
                > 127
            )
        dark &= ~steep
    labels, count = ndimage.label(dark)
    if count == 0:
        return []
    index = np.arange(1, count + 1)
    areas = ndimage.sum(dark, labels, index) * grid_res * grid_res
    centroids = ndimage.center_of_mass(dark, labels, index)
    placed_labels: set[int] = set()
    lo, hi = float(cfg.get("min_area_m2", 1.0)), float(cfg.get("max_area_m2", 25.0))
    half = fp_size_m / 2.0
    taken = np.zeros(dem.shape, dtype=bool)
    for o in exclude or []:
        r = int(min(max((half - o["y"]) / res, 0), dem.shape[0] - 1))
        c = int(min(max((o["x"] + half) / res, 0), dem.shape[0] - 1))
        taken[max(0, r - 2) : r + 3, max(0, c - 2) : c + 3] = True
    out = []
    order = np.argsort(-areas)
    cap = int(cfg.get("max", 5000))
    for i in order:
        area = float(areas[i])
        if not (lo <= area <= hi):
            continue
        cy, cx = centroids[i]
        x = cx * grid_res - half
        y = half - cy * grid_res
        r = int(min(max((half - y) / res, 0), dem.shape[0] - 1))
        c = int(min(max((x + half) / res, 0), dem.shape[0] - 1))
        if taken[r, c]:
            continue
        taken[max(0, r - 2) : r + 3, max(0, c - 2) : c + 3] = True
        placed_labels.add(int(i) + 1)
        w = max(0.8, min(math.sqrt(area) * 1.1, 5.0))
        out.append(
            {
                "kind": "shrub",
                "x": round(float(x), 2),
                "y": round(float(y), 2),
                "z": round(float(dem[r, c] - min_elevation) - 0.05, 2),
                "size": [round(w, 2), round(w, 2), round(w * float(rng.uniform(0.45, 0.7)), 2)],
                "yaw_deg": round(float(rng.uniform(0, 360)), 1),
                "peak_m": None,
                "source": "imagery",
            }
        )
        if len(out) >= cap:
            break
    if unplaced is not None:
        # The dots nothing was placed on (too small, too big, taken, over the cap):
        # the caller repaints them, or they stay as brown smears with nothing on.
        keep = np.ones(count + 1, dtype=bool)
        keep[0] = False
        for lab in placed_labels:
            keep[lab] = False
        unplaced.append(keep[labels])
    return out


def erase_dots(colour_u8: np.ndarray, dots: np.ndarray, window_m: float, texel_m: float):
    """Repaint ``dots`` with the mean colour of the ground within ``window_m`` round
    them (the dots themselves left out)."""

    from scipy import ndimage

    if not dots.any():
        return colour_u8
    win = max(3, int(window_m / texel_m))
    out = colour_u8.astype("float32")
    keep = (~dots).astype("float32")
    den = np.maximum(ndimage.uniform_filter(keep, size=win, mode="nearest"), 1e-3)
    ring = np.stack(
        [
            ndimage.uniform_filter(out[..., ch] * keep, size=win, mode="nearest") / den
            for ch in range(3)
        ],
        axis=-1,
    )
    out = np.where(dots[..., None], ring, out)
    return np.clip(out, 0, 255).astype("uint8")


def trees_from_chm(
    chm: np.ndarray,
    dem: np.ndarray,
    colour_u8: np.ndarray | None,
    res: float,
    fp_size_m: float,
    min_elevation: float,
    forest_spec: dict,
    *,
    seed: int = 7,
    road_mask: np.ndarray | None = None,
    exclude_points: list[tuple[float, float, float]] | None = None,
) -> tuple[list[dict], dict]:
    """Plant the forest at the lidar's own tree tops with the lidar's own heights.

    Every local maximum of the canopy height model above ``min_tree_height_m`` is a
    tree; its height is measured, not drawn. Species still follow elevation (fir
    gaining on spruce toward the tree line, krummholz for the stunted tops in the band
    below it) and the imagery (bright green, below ``broadleaf_max_m``: aspen).
    """

    from scipy import ndimage

    from . import pointcloud

    rng = np.random.default_rng(seed)
    n = dem.shape[0]
    half = fp_size_m / 2.0
    treeline = float(forest_spec.get("treeline_m", 9999.0))
    band = float(forest_spec.get("krummholz_band_m", 100.0))
    broadleaf_max = float(forest_spec.get("broadleaf_max_m", 0.0))
    max_slope = float(forest_spec.get("max_slope_deg", 45.0))
    min_height = float(forest_spec.get("min_tree_height_m", 2.0))
    max_trees = int(forest_spec.get("max_trees", 120000))
    rows, cols, heights = pointcloud.tree_tops(chm, res, min_height_m=min_height)
    elevation = dem[rows, cols]
    gyd, gxd = np.gradient(ndimage.gaussian_filter(dem.astype("float64"), 1.0), res)
    slope = np.degrees(np.arctan(np.hypot(gxd, gyd)))[rows, cols]
    keep = (slope <= max_slope) & (elevation <= treeline + 5.0)
    if road_mask is not None:
        clear = ndimage.binary_dilation(road_mask, iterations=max(1, int(4.0 / res)))
        keep &= ~clear[rows, cols]
    # Off the cell centres: a top is somewhere in its metre, not on a lattice.
    jitter = float(forest_spec.get("top_jitter_m", 0.4))
    xs = cols * res - half + res / 2.0 + rng.uniform(-jitter, jitter, rows.size)
    ys = half - rows * res - res / 2.0 + rng.uniform(-jitter, jitter, rows.size)
    for ex, ey, radius in exclude_points or []:
        keep &= np.hypot(xs - ex, ys - ey) > radius
    rows, cols, heights = rows[keep], cols[keep], heights[keep]
    xs, ys, elevation = xs[keep], ys[keep], elevation[keep]
    if rows.size > max_trees:  # keep the tallest: the understory goes, the canopy stays
        order = np.argsort(-heights)[:max_trees]
        rows, cols, heights = rows[order], cols[order], heights[order]
        xs, ys, elevation = xs[order], ys[order], elevation[order]
    # Broadleaf where the de-lit imagery is bright green under the top.
    broadleaf = np.zeros(rows.size, dtype=bool)
    if colour_u8 is not None and broadleaf_max > 0:
        scale = colour_u8.shape[0] / n
        rgb = (
            colour_u8[
                np.clip((rows * scale).astype(int), 0, colour_u8.shape[0] - 1),
                np.clip((cols * scale).astype(int), 0, colour_u8.shape[1] - 1),
            ].astype("float32")
            / 255.0
        )
        exg = 2 * rgb[:, 1] - rgb[:, 0] - rgb[:, 2]
        bright = rgb.mean(axis=1)
        # A bright green top under 3 m is a willow, not an aspen.
        broadleaf = (exg > 0.12) & (bright > 0.30) & (elevation < broadleaf_max) & (heights >= 3.0)
    trees: list[dict] = []
    species_counts: dict[str, int] = {}
    # The ground under the jittered top, not the cell's value: on a 40 degree slope
    # the metre of jitter is a metre of height.
    ground = hm.sample_bilinear(dem, res, fp_size_m, xs, ys)
    aspen_sapling_max = float(forest_spec.get("aspen_sapling_max_height_m", 0.0))
    for i in range(rows.size):
        z = float(ground[i])
        h = float(heights[i])
        e = float(elevation[i])
        if broadleaf[i]:
            # A bright green top under the sapling height is an aspen sucker clump.
            species = "aspen_sapling" if h < aspen_sapling_max else "aspen"
        elif e >= treeline - band and h < 3.5:
            species = "krummholz"  # wind-pruned mats in the band below the tree line
        elif h < float(forest_spec.get("mat_max_height_m", 0.0)) and e >= float(
            forest_spec.get("mat_min_elevation_m", 9999.0)
        ):
            species = "willow"  # the light-green carrs of the subalpine meadows
        elif h < float(forest_spec.get("sapling_max_height_m", 0.0)):
            species = "sapling"  # a young conifer is bushy, not a scaled-down spire
        else:
            fir_share = float(np.clip((e - (treeline - 600.0)) / 600.0, 0.15, 0.6))
            species = "fir" if rng.uniform() < fir_share else "spruce"
        species_counts[species] = species_counts.get(species, 0) + 1
        # Mats, saplings and sucker clumps sit on the ground; a trunk is sunk a hand's
        # width so no root plate floats on a bump the metre grid missed.
        sink = 0.03 if species in ("krummholz", "willow", "sapling", "aspen_sapling") else 0.1
        trees.append(
            {
                "species": species,
                "x": round(float(xs[i]), 2),
                "y": round(float(ys[i]), 2),
                "z": round(z - min_elevation - sink, 2),
                "height_m": round(h, 2),
                "yaw_deg": round(float(rng.uniform(0, 360)), 1),
            }
        )
    heights_kept = np.array([t["height_m"] for t in trees]) if trees else np.zeros(1)
    stats = {
        "source": "lidar canopy",
        "tops": int(rows.size),
        "trees": len(trees),
        "species": species_counts,
        "height_p50_m": round(float(np.median(heights_kept)), 2),
        "height_p95_m": round(float(np.percentile(heights_kept, 95)), 2),
        "treeline_m": treeline,
        "min_tree_height_m": min_height,
    }
    return trees, stats
