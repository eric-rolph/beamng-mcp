"""Stage implementations behind ``build.py``: fetch -> terrain -> level -> dist.

Each stage reads only what the previous one cached on disk, so a rebuild of any one
stage is reproducible on its own, and ``dist`` is a re-zip of ``mod/`` - never a rebuild.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import time
from pathlib import Path

import numpy as np

from . import gis_sources
from . import heightmap as hm

HANDOFF_SCHEMA = "ericrolph-beamng-maps-handoff-v1"


def _log(message: str) -> None:
    print(message, flush=True)


def footprint_for(spec) -> gis_sources.Footprint:
    site = spec.SITE
    size_m = site["size_px"] * site["square_size_m"]
    return gis_sources.Footprint.from_center(
        site["center_lat"], site["center_lon"], site["epsg"], size_m
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


def fetch(spec, example_root: Path, *, force: bool = False) -> dict:
    """Pull every public source the spec names into ``<map>/data/`` (cached, verified)."""

    data_root = example_root / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    fp = footprint_for(spec)
    _log(f"  footprint EPSG:{fp.epsg} W={fp.west:.0f} S={fp.south:.0f} size={fp.size_m:.0f} m")
    manifest: dict = {"footprint": fp.to_json(), "elevation": [], "imagery": None, "roads": None}
    for source in spec.SOURCES["elevation"]:
        kind = source["kind"]
        if kind == "usgs_3dep":
            paths = gis_sources.fetch_3dep_tiles(
                fp,
                data_root / "3dep",
                resolution=source.get("resolution", 1.0),
                force=force,
                log=_log,
            )
            manifest["elevation"].append({"kind": kind, "files": [p.name for p in paths]})
        elif kind == "ot_tiles":
            paths = gis_sources.fetch_ot_tiles(
                source["prefix"],
                fp,
                data_root / "ot" / source["name"],
                pattern=source["pattern"],
                tile_m=source["tile_m"],
                force=force,
                log=_log,
            )
            manifest["elevation"].append(
                {"kind": kind, "name": source["name"], "files": [p.name for p in paths]}
            )
        elif kind == "ot_grid":
            path = gis_sources.fetch_ot_grid_window(
                source["prefix"],
                source["open_name"],
                fp,
                data_root / "ot" / f"{source['name']}_window.tif",
                cache_dir=data_root / "ot" / "_grid_cache",
                force=force,
                log=_log,
            )
            manifest["elevation"].append(
                {"kind": kind, "name": source["name"], "files": [path.name]}
            )
        else:
            raise ValueError(f"unknown elevation source kind: {kind}")
    imagery = spec.SOURCES.get("imagery")
    if imagery:
        paths = gis_sources.fetch_naip_tiles(
            fp, data_root / "naip", resolution=imagery.get("resolution", 1.0), force=force, log=_log
        )
        manifest["imagery"] = {"kind": imagery["kind"], "files": [p.name for p in paths]}
    cloud = spec.SOURCES.get("pointcloud")
    if cloud:
        from . import pointcloud

        meta = pointcloud.fetch_canopy(
            fp,
            data_root / "pointcloud",
            cloud["resource"],
            res=float(cloud.get("grid_res_m", spec.SITE["square_size_m"])),
            force=force,
            log=_log,
        )
        manifest["pointcloud"] = meta
        _log(
            f"  canopy grid: {meta['points_in_footprint'] / 1e6:.1f} M returns in the footprint, "
            f"{meta['density_per_m2']} per m2, {meta['elapsed_s']} s"
        )
    roads = spec.SOURCES.get("roads")
    if roads:
        path = gis_sources.fetch_osm_roads(
            fp, data_root / "osm" / "roads.json", force=force, log=_log
        )
        manifest["roads"] = {"kind": roads["kind"], "files": [path.name]}
    if spec.SOURCES.get("buildings"):
        path = gis_sources.fetch_osm_buildings(
            fp, data_root / "osm" / "buildings.json", force=force, log=_log
        )
        manifest["buildings"] = {"kind": "osm_overpass", "files": [path.name]}
    (data_root / "fetch.manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


# ---------------------------------------------------------------------------
# terrain
# ---------------------------------------------------------------------------


def _source_resolution(path: Path) -> float:
    import rasterio

    with rasterio.open(path) as dataset:
        return float(dataset.res[0])


def _refilled_cells(terrain_dir: Path, size: int) -> np.ndarray | None:
    """The cells the de-lighting refilled (any kind), on a ``size`` grid, or None."""

    path = terrain_dir / "refill.npy"
    if not path.is_file():
        return None
    kinds = np.load(path)
    if kinds.shape[0] != size:
        from PIL import Image

        kinds = np.asarray(Image.fromarray(kinds).resize((size, size), Image.NEAREST))
    return kinds > 0


def _disc(radius_px: float) -> np.ndarray:
    """A disc structuring element (a cross kernel iterated makes a diamond)."""

    r = max(1, round(radius_px))
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    return (xx * xx + yy * yy) <= r * r + 0.5


def pad_center_xy(fp, pad) -> tuple[float, float]:
    """Where a pad sits on the level, in metres from the footprint's centre.

    A pad pinned by ``center_xy`` moves with the footprint; one pinned by ``lat``
    and ``lon`` stays on the ground it was measured from, which is what a turnout
    at a named place wants when the level around it grows.
    """

    if pad.get("lat") is not None and pad.get("lon") is not None:
        from rasterio.warp import transform

        xs, ys = transform("EPSG:4326", f"EPSG:{fp.epsg}", [float(pad["lon"])], [float(pad["lat"])])
        cx, cy = fp.center
        return (xs[0] - cx, ys[0] - cy)
    return (float(pad["center_xy"][0]), float(pad["center_xy"][1]))


def terrain(spec, example_root: Path) -> dict:
    """Composite every elevation source onto the level grid; write dem/layer arrays + stats."""

    started = time.time()
    fp = footprint_for(spec)
    site = spec.SITE
    size = int(site["size_px"])
    res = float(site["square_size_m"])
    data_root = example_root / "data"
    out = data_root / "terrain"
    out.mkdir(parents=True, exist_ok=True)
    grid = hm.target_grid(fp, size, res)
    stats: dict = {"size_px": size, "square_size_m": res, "footprint": fp.to_json(), "sources": []}

    baseline_paths = sorted((data_root / "3dep").glob("3dep_*.tif"))
    if not baseline_paths:
        raise FileNotFoundError("run the fetch stage first: no 3DEP tiles cached")
    base_res = _source_resolution(baseline_paths[0])
    _log(f"  baseline: {len(baseline_paths)} 3DEP tiles @ {base_res:g} m -> {size}px @ {res:g} m")
    dem = hm.resample_sources(baseline_paths, grid, downsample=base_res < res)
    baseline_dem = dem.copy()  # bare earth: what an authored flatten box falls back to
    stats["sources"].append(
        {
            "kind": "usgs_3dep",
            "tiles": len(baseline_paths),
            "valid_fraction": float(np.isfinite(dem).mean()),
        }
    )

    for source in spec.SOURCES["elevation"]:
        if source["kind"] == "usgs_3dep":
            continue
        if source["kind"] == "ot_tiles":
            paths = sorted((data_root / "ot" / source["name"]).glob("*.tif"))
        else:
            paths = [data_root / "ot" / f"{source['name']}_window.tif"]
        paths = [p for p in paths if p.is_file()]
        if not paths:
            raise FileNotFoundError(f"run the fetch stage first: no files for {source['name']}")
        src_res = _source_resolution(paths[0])
        _log(f"  overlay {source['name']}: {len(paths)} file(s) @ {src_res:g} m")
        overlay = hm.resample_sources(paths, grid, downsample=src_res < res)
        dem, composite_stats = hm.feathered_composite(
            dem, overlay, feather_px=max(8, int(24 / res))
        )
        stats["sources"].append(
            {"kind": source["kind"], "name": source["name"], "files": len(paths), **composite_stats}
        )
        _log(
            f"    covers {composite_stats['overlay_valid_fraction']:.1%} of the level, "
            f"datum shift {composite_stats['datum_shift_m']:+.2f} m"
        )

    dem, holes = hm.fill_holes(dem)
    stats["holes_filled"] = holes
    max_step = min(10.0, max(3.0, 8.0 * res))
    dem, spikes = hm.despike(dem, res, max_step_m=max_step)
    stats["spikes_clamped"] = spikes
    stats["despike_threshold_m"] = max_step
    pits_cfg = spec.TERRAIN.get("fill_pits")
    if pits_cfg:
        dem, pits = hm.fill_pits(
            dem, res, float(pits_cfg.get("close_m", 8.0)), float(pits_cfg.get("depth_m", 2.0))
        )
        stats["pits_filled"] = pits
        _log(f"  pits filled: {pits} cells")
    sigma = float(spec.TERRAIN.get("smooth_sigma_px", 0.0))
    if sigma > 0:
        from scipy import ndimage

        dem = ndimage.gaussian_filter(dem, sigma=sigma).astype("float32")
    stats["smooth_sigma_px"] = sigma

    canopy_file = example_root / "data" / "pointcloud" / "canopy.npz"
    canopy_cover = None
    canopy_chm = None
    if canopy_file.is_file():
        from scipy import ndimage

        from . import pointcloud

        chm, canopy_stats = pointcloud.canopy_height(canopy_file, dem)
        np.save(out / "chm.npy", chm)
        canopy_chm = chm
        stats["canopy"] = canopy_stats
        _log(f"  canopy height model: {canopy_stats}")
        # Canopy cover: the share of ground under a crown over 2 m within 15 m.
        canopy_cover = ndimage.uniform_filter(
            (chm > 2.0).astype("float32"), size=max(3, int(15.0 / res)), mode="nearest"
        )
    colour = None
    imagery_stats: dict = {}
    # Objects in the surface (shrubs, boulders, fences, buildings) come out of the ground
    # here and are recorded for the level stage to put back as placed meshes.
    objects_spec = getattr(spec, "OBJECTS", None)
    detected: list[dict] = []
    if objects_spec:
        from . import level_builder
        from . import objects as ob

        dem, detected, ostats = ob.detect_objects(dem, res, **objects_spec.get("detect", {}))
        if objects_spec.get("flatten_boxes"):
            dem, box_notes = ob.flatten_boxes(
                dem, res, fp.size_m, objects_spec["flatten_boxes"], baseline=baseline_dem
            )
            stats["flatten_boxes"] = box_notes
            _log(f"  flattened boxes: {box_notes}")
            detected, in_boxes = ob.inside_boxes(
                detected, res, fp.size_m, objects_spec["flatten_boxes"]
            )
            stats["objects_dropped_in_boxes"] = len(in_boxes)
        # Classify on the de-lit imagery (a shaded crater wall is not a shrub); the
        # conditioned colour is cached for the level stage so both see the same pixels.
        # The flight's road corridor (12 m either side of every OSM centreline) is
        # no source for a refill and no seed for snow: the beds are repainted later
        # anyway, and a switchback stack put the next bed up inside a 6 m ring.
        road_corridor = None
        if hasattr(spec, "ROADS") and (data_root / "osm" / "roads.json").is_file():
            from . import roads as road_tools

            lines = road_tools.road_polylines(spec, fp, data_root / "osm" / "roads.json")
            road_corridor = road_tools.centreline_mask(lines, res, fp.size_m, dem.shape[0], 12.0)
            del lines
        colour, imagery_stats = level_builder.conditioned_colour(
            dem,
            res,
            fp,
            data_root / "naip",
            getattr(spec, "IMAGERY", None),
            canopy_cover=canopy_cover,
            canopy_chm=canopy_chm,
            source_exclude=road_corridor,
        )
        del road_corridor
        # The refilled cells (1 cast shadow, 2 snow) ship for the level stage's
        # check of every field against its ring on the finished base.
        refill_mask = imagery_stats.pop("_refill_mask", None)
        if refill_mask is not None:
            np.save(out / "refill.npy", refill_mask.astype("uint8"))
            del refill_mask
        if objects_spec.get("flatten_boxes") and colour is not None:
            # The crest and the walls inside a box keep their photograph: only the
            # compound ground is repainted, whatever layer its terrace edges wear.
            # "Wall" is the 10 m-smoothed bare-earth slope over 28 degrees.
            from PIL import Image
            from scipy import ndimage

            keep = (
                hm.slope_degrees(
                    ndimage.gaussian_filter(baseline_dem.astype("float32"), 10.0 / res), res
                )
                > 28.0
            )
            if keep.shape[0] != colour.shape[0]:
                keep = (
                    np.asarray(
                        Image.fromarray(keep.astype("uint8") * 255).resize(
                            (colour.shape[1], colour.shape[0]), Image.NEAREST
                        )
                    )
                    > 127
                )
            # The ring's road fragments must not be quilted into a box: every ring
            # cell within 8 m of an OSM centreline is not a source.
            road_mask = None
            if hasattr(spec, "ROADS"):
                from . import roads as road_tools

                lines = road_tools.road_polylines(spec, fp, data_root / "osm" / "roads.json")
                road_mask = road_tools.centreline_mask(
                    lines, fp.size_m / colour.shape[0], fp.size_m, colour.shape[0], 8.0
                )
            colour = ob.inpaint_boxes(
                colour,
                fp.size_m / colour.shape[0],
                fp.size_m,
                objects_spec["flatten_boxes"],
                keep_mask=keep,
                exclude_mask=road_mask,
            )
            del road_mask
            for box in objects_spec["flatten_boxes"]:
                lo_hi = box.get("repaint_extremes")
                if not lo_hi:
                    continue
                # A box that keeps its photograph still loses the roof and its
                # shadow: cells far outside the box's own tone range are repainted
                # from the ground within 10 m of them.
                from . import vegetation

                texel = fp.size_m / colour.shape[0]
                bx, by = box["center_xy"]
                bs = float(box.get("size_m", 200.0))
                hf = fp.size_m / 2.0
                bc0 = int(max(0, (bx - bs / 2 + hf) / texel))
                bc1 = int(min(colour.shape[0], (bx + bs / 2 + hf) / texel))
                br0 = int(max(0, (hf - (by + bs / 2)) / texel))
                br1 = int(min(colour.shape[0], (hf - (by - bs / 2)) / texel))
                lum_b = colour.astype("float32").mean(axis=-1) / 255.0
                extreme = np.zeros(lum_b.shape, dtype=bool)
                extreme[br0:br1, bc0:bc1] = (lum_b[br0:br1, bc0:bc1] < float(lo_hi[0])) | (
                    lum_b[br0:br1, bc0:bc1] > float(lo_hi[1])
                )
                if extreme.any():
                    colour = vegetation.erase_dots(colour, extreme, 10.0, texel)
                del lum_b, extreme
            del keep
            _log("  base colour in-painted inside the flatten boxes")
        from PIL import Image

        Image.fromarray(colour).save(out / "colour.png", format="PNG", compress_level=3)
        (out / "imagery.json").write_text(
            json.dumps(imagery_stats, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        counts = ob.classify_objects(detected, colour, size, **objects_spec.get("classify", {}))
        dropped = ob.drop_fence_lines(
            detected,
            res,
            max_area_m2=12.0,
            post_gap_m=float(objects_spec.get("fence_post_gap_m", 8.0)),
        )
        stats["objects"] = {**ostats, "kinds": counts, "fence_posts_dropped": dropped}
        _log(
            f"  objects: {ostats['objects']} bumps removed ({counts}), "
            f"{ostats['structures_flattened']} structures flattened, {dropped} fence posts dropped"
        )

    # Roads are carved into the terrain before classification so the bed is flat and
    # the banks are real slopes.
    # Authored pads (a car park, a yard) are outlined and carved BEFORE the roads,
    # so every road's profile starts on the pad's plane instead of plunging off a
    # kerb: the lot's own outline from the flight (the dark cells inside the
    # authored rectangle, the hedge's green cells left out, closed and filled, the
    # largest piece kept) or the rectangle itself, carved as a fitted plane with its
    # grade and its cut/fill bounded, feathered into the ground.
    pad_outlines: list[dict] = []
    pads = (getattr(spec, "ROADS", None) or {}).get("pads") or []
    if pads:
        from scipy import ndimage

        from . import level_builder

        half_fp = fp.size_m / 2.0
        raw = None
        pad_notes = []
        for pad in pads:
            px, py = pad_center_xy(fp, pad)
            sx, sy = pad["size_m"]
            c0 = int(max(0, (px - sx / 2 + half_fp) / res))
            c1 = int(min(dem.shape[0], (px + sx / 2 + half_fp) / res))
            r0 = int(max(0, (half_fp - (py + sy / 2)) / res))
            r1 = int(min(dem.shape[0], (half_fp - (py - sy / 2)) / res))
            if r1 <= r0 or c1 <= c0:
                continue
            feather = float(pad.get("feather_m", 12.0))
            kerb_m = float(pad.get("kerb_m", 0.0))
            pad_px = int(max(feather, kerb_m) / res) + 2
            rr0, rr1 = max(0, r0 - pad_px), min(dem.shape[0], r1 + pad_px)
            cc0, cc1 = max(0, c0 - pad_px), min(dem.shape[0], c1 + pad_px)
            inside = np.zeros((rr1 - rr0, cc1 - cc0), dtype=bool)
            inside[r0 - rr0 : r1 - rr0, c0 - cc0 : c1 - cc0] = True
            outline = pad.get("from_imagery")
            if outline:
                if raw is None:
                    raw = level_builder.naip_mosaic(data_root / "naip", fp, dem.shape[0])
                block = raw[rr0:rr1, cc0:cc1].astype("float32") / 255.0
                lum = block.mean(axis=-1)
                dark = (lum < float(outline.get("max_lum", 0.42))) & inside
                green_cut = outline.get("exclude_green")
                if green_cut is not None:
                    # The hedge along the kerb is dark too, and it is not the lot.
                    exg = 2.0 * block[..., 1] - block[..., 0] - block[..., 2]
                    dark &= exg <= float(green_cut)
                    del exg
                # Disc kernels, then a 2 m smooth: the cross kernel's iterations
                # closed and opened the lot into a diamond and its kerb into a
                # sawtooth of 45-degree teeth.
                dark = ndimage.binary_closing(
                    dark, structure=_disc(float(outline.get("close_m", 12.0)) / 2.0 / res)
                )
                dark = ndimage.binary_opening(
                    dark, structure=_disc(float(outline.get("open_m", 4.0)) / 2.0 / res)
                )
                labels, count = ndimage.label(dark)
                if count:
                    areas = ndimage.sum(dark, labels, np.arange(1, count + 1))
                    dark = labels == (int(np.argmax(areas)) + 1)  # the lot is one piece
                    dark = ndimage.binary_fill_holes(dark)
                    # A single texel of smoothing: the disc kernels already take the
                    # sawtooth out, and 2 m of it rounded every straight kerb into
                    # lobes (the outline's shape index went to 2.1 against a real
                    # lot's 1.15).
                    dark = (
                        ndimage.gaussian_filter(dark.astype("float32"), max(0.6, 0.8 / res)) > 0.5
                    )
                if dark.sum() * res * res < float(outline.get("min_area_m2", 200.0)):
                    _log(f"  pad at {pad['center_xy']} skipped: no dark lot in the flight")
                    del block, lum, dark
                    continue
                inside = dark
                del block, lum, dark
            window = dem[rr0:rr1, cc0:cc1]
            if pad.get("flatten", True):
                rr, cc = np.nonzero(inside)
                xs, ys = cc * res, rr * res
                a = np.stack([xs - xs.mean(), ys - ys.mean(), np.ones_like(xs)], axis=1)
                coef, *_ = np.linalg.lstsq(a, window[rr, cc].astype("float64"), rcond=None)
                grade = float(np.hypot(coef[0], coef[1]))
                max_grade = float(pad.get("max_grade", 0.03))
                if grade > max_grade:
                    coef[:2] *= max_grade / grade
                gy_i, gx_i = np.mgrid[0 : window.shape[0], 0 : window.shape[1]]
                plane = (
                    coef[0] * (gx_i * res - xs.mean())
                    + coef[1] * (gy_i * res - ys.mean())
                    + coef[2]
                ).astype("float32")
                budget = float(pad.get("max_cut_fill_m", 1.5))
                target = np.clip(plane, window - budget, window + budget)
                dist = ndimage.distance_transform_edt(~inside) * res
                w = np.clip(1.0 - dist / feather, 0.0, 1.0).astype("float32")
                w = w * w * (3.0 - 2.0 * w)
                carved = window * (1 - w) + target * w
                kerb_slope = float(pad.get("kerb_max_slope_deg", 15.0))
                kerb_stats = None
                if kerb_m > 0 and kerb_slope > 0:
                    # The kerb: the lidar's retaining wall and the batter's toe
                    # within ``kerb_m`` of the lot are held under ``kerb_slope``
                    # (the steepest surface under the ground and the gentlest over
                    # it that hold it, averaged), so nothing round the lot is a
                    # cut face the classifier paints as talus.
                    band = (dist > 0) & (dist <= kerb_m)
                    band[:3, :] = band[-3:, :] = False
                    band[:, :3] = band[:, -3:] = False
                    # The lidar's own retaining wall inside the inner band is
                    # smoothed over 4 m before the batter (a 4 m wall comes down to
                    # 22 degrees), the smoothing feathered 4 m across the band's
                    # edges and never touching the lot: a wall the level cannot
                    # build is not left as a cut face in plain texture by the kerb.
                    inner_band = (dist > 0) & (dist <= kerb_m / 2.0)
                    w_s = ndimage.gaussian_filter(inner_band.astype("float32"), max(1.0, 2.0 / res))
                    w_s = np.where(inside, 0.0, w_s).astype("float32")
                    smooth_c = ndimage.gaussian_filter(carved, max(1.0, 4.0 / res))
                    carved = (carved * (1.0 - w_s) + smooth_c * w_s).astype("float32")
                    del inner_band, w_s, smooth_c
                    limited = hm.batter(
                        carved, inside, band, math.tan(math.radians(kerb_slope)), res
                    )
                    # The batter holds over the inner half of the band and gives way
                    # to the carved ground over the outer half, so a flank steeper
                    # than the cap is not re-graded 30 m out.
                    give = np.clip((dist - kerb_m / 2.0) / (kerb_m / 2.0), 0.0, 1.0).astype(
                        "float32"
                    )
                    carved = np.where(band, limited * (1.0 - give) + carved * give, carved).astype(
                        "float32"
                    )
                    del limited, give
                    zone = dist <= kerb_m

                    def _slope_deg(z):
                        gy_k, gx_k = np.gradient(z.astype("float64"), res)
                        return np.degrees(np.arctan(np.hypot(gx_k, gy_k)))

                    slope_all = _slope_deg(carved)
                    inner = (dist > 0) & (dist <= kerb_m / 2.0)
                    slope_k = slope_all[zone]
                    inner_k = slope_all[inner]
                    del slope_all
                    natural_all = _slope_deg(window)
                    natural_k = natural_all[zone]
                    natural_inner = natural_all[inner]
                    del natural_all, inner
                    kerb_stats = {
                        "kerb_slope_max_deg": round(float(slope_k.max()), 1),
                        "kerb_slope_p95_deg": round(float(np.percentile(slope_k, 95)), 1),
                        # The inner half of the band, where the limit holds outright.
                        "kerb_inner_max_deg": round(float(inner_k.max()), 1),
                        "kerb_natural_inner_max_deg": round(float(natural_inner.max()), 1),
                        # The ground's own steepness there before the lot was cut.
                        "kerb_natural_max_deg": round(float(natural_k.max()), 1),
                        "kerb_natural_p95_deg": round(float(np.percentile(natural_k, 95)), 1),
                    }
                    del slope_k, inner_k, natural_k, natural_inner, band, zone
                dem[rr0:rr1, cc0:cc1] = carved
                pad_notes.append(
                    {
                        "center_xy": [px, py],
                        "area_m2": round(float(inside.sum() * res * res), 1),
                        "grade": round(min(grade, max_grade), 4),
                        "grade_fitted": round(grade, 4),
                        "max_cut_m": round(float(np.clip(window - target, 0, None).max()), 2),
                        "max_fill_m": round(float(np.clip(target - window, 0, None).max()), 2),
                        **(kerb_stats or {}),
                    }
                )
            pad_outlines.append(
                {"pad": pad, "inside": inside, "rr0": rr0, "rr1": rr1, "cc0": cc0, "cc1": cc1}
            )
        stats["pads"] = pad_notes if pad_notes else len(pads)
        del raw

    carve_spec = spec.ROADS.get("carve") if hasattr(spec, "ROADS") else None
    surface_index = None
    if carve_spec:
        from . import roads as road_tools

        polylines = road_tools.road_polylines(spec, fp, data_root / "osm" / "roads.json")
        dem, lowered = road_tools.clear_corridor(dem, res, fp.size_m, polylines)
        stats["road_corridor_cells_cleared"] = lowered
        if spec.ROADS.get("max_grade"):
            polylines, cuts = road_tools.drop_cliff_segments(
                polylines,
                dem,
                res,
                fp.size_m,
                float(spec.ROADS["max_grade"]),
                min_length_m=float(spec.ROADS.get("cliff_cut_min_length_m", 100.0)),
            )
            stats["road_cliff_cuts"] = cuts
        dem, _road_mask, surface_index, rstats = road_tools.carve(
            dem, res, fp.size_m, polylines, **carve_spec
        )
        stats["road_carve"] = rstats
        _log(f"  roads carved: {rstats}")

    exg = None
    green_hue = None
    if any("exg" in key for rule in spec.TERRAIN["classify"]["rules"] for key in rule):
        # Excess green of the de-lit imagery on the DEM grid: turf is not rock.
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None
        rgb = (
            colour
            if colour.shape[0] == dem.shape[0]
            else np.asarray(
                Image.fromarray(colour).resize((dem.shape[0], dem.shape[0]), Image.BILINEAR)
            )
        )
        rgb = rgb.astype("float32") / 255.0
        exg = (2.0 * rgb[..., 1] - rgb[..., 0] - rgb[..., 2]).astype("float32")
        green_hue = (rgb[..., 1] - rgb[..., 0]).astype("float32")
        del rgb
    layer, fractions = hm.classify(
        dem, res, spec.TERRAIN, exg=exg, canopy=canopy_cover, green_hue=green_hue
    )
    if detected and any("box_layers" in o for o in detected):
        from . import objects as ob

        detected, dropped_by_layer = ob.drop_box_objects(
            detected, layer, list(spec.TERRAIN["materials"])
        )
        stats["objects_dropped_in_boxes"] = (
            stats.get("objects_dropped_in_boxes", 0) + dropped_by_layer
        )
        _log(f"  objects dropped off the kept layers in boxes: {dropped_by_layer}")
    flatfield = (getattr(spec, "IMAGERY", None) or {}).get("aspect_flatfield")
    if flatfield and colour is not None:
        from PIL import Image

        from . import imagery as imagery_tools

        Image.MAX_IMAGE_PIXELS = None
        ids = [
            list(spec.TERRAIN["materials"]).index(name)
            for name in flatfield.get("layers", [])
            if name in spec.TERRAIN["materials"]
        ]
        layer_at_colour = layer
        if layer.shape[0] != colour.shape[0]:
            layer_at_colour = np.asarray(
                Image.fromarray(layer).resize((colour.shape[0], colour.shape[0]), Image.NEAREST)
            )
        dem_at_colour = dem
        if dem.shape[0] != colour.shape[0]:
            dem_at_colour = np.asarray(
                Image.fromarray(dem).resize((colour.shape[0], colour.shape[0]), Image.BILINEAR)
            )
        colour, ff_stats = imagery_tools.aspect_flatfield(
            colour,
            dem_at_colour,
            fp.size_m / colour.shape[0],
            layer_at_colour,
            ids,
            strength=float(flatfield.get("strength", 1.0)),
            bins=int(flatfield.get("bins", 8)),
            min_slope_deg=float(flatfield.get("min_slope_deg", 8.0)),
            mode=str(flatfield.get("mode", "aspect")),
            target=str(flatfield.get("target", "mean")),
            max_factor=float(flatfield.get("max_factor", 1.8)),
            aspect_pass=float(flatfield.get("aspect_pass", 0.0)),
            chroma=bool(flatfield.get("chroma", False)),
            exclude=_refilled_cells(out, colour.shape[0]),
            sun=(
                (
                    float(imagery_stats["sun_fit"]["azimuth_deg"]),
                    float(imagery_stats["sun_fit"]["altitude_deg"]),
                )
                if imagery_stats.get("sun_fit")
                else None
            ),
        )
        Image.fromarray(colour).save(out / "colour.png", format="PNG", compress_level=3)
        stats["aspect_flatfield"] = ff_stats
        _log(f"  aspect flat-field on {len(ids)} layers")
    # A layer's base colour is pulled toward its palette base, or toward its own
    # ``base_pull_target`` where the tile's mean (the palette base) is not the tone
    # the base should carry (the limestone's tile is capped under the sun, its base
    # stays the cream the plain is measured against).
    pulls = {
        list(spec.TERRAIN["materials"]).index(name): (
            entry.get("base_pull_target", entry["base"]),
            float(entry["base_pull"]),
        )
        for name, entry in getattr(spec, "PALETTE", {}).items()
        if entry.get("base_pull") and name in spec.TERRAIN["materials"]
    }
    pull_tapers = {
        list(spec.TERRAIN["materials"]).index(name): float(entry["base_pull_taper_m"])
        for name, entry in getattr(spec, "PALETTE", {}).items()
        if entry.get("base_pull_taper_m") and name in spec.TERRAIN["materials"]
    }
    pull_windows = {
        list(spec.TERRAIN["materials"]).index(name): float(entry["base_pull_window_m"])
        for name, entry in getattr(spec, "PALETTE", {}).items()
        if entry.get("base_pull_window_m") and name in spec.TERRAIN["materials"]
    }
    pull_lum_gates = {
        list(spec.TERRAIN["materials"]).index(name): tuple(entry["base_pull_lum_gate"])
        for name, entry in getattr(spec, "PALETTE", {}).items()
        if entry.get("base_pull_lum_gate") and name in spec.TERRAIN["materials"]
    }
    pull_max_br = {
        list(spec.TERRAIN["materials"]).index(name): float(entry["base_pull_max_br"])
        for name, entry in getattr(spec, "PALETTE", {}).items()
        if entry.get("base_pull_max_br") and name in spec.TERRAIN["materials"]
    }
    if pulls and colour is not None:
        from PIL import Image

        from . import imagery as imagery_tools

        Image.MAX_IMAGE_PIXELS = None
        layer_at_colour = layer
        if layer.shape[0] != colour.shape[0]:
            layer_at_colour = np.asarray(
                Image.fromarray(layer.astype("uint8")).resize(
                    (colour.shape[0], colour.shape[0]), Image.NEAREST
                )
            )
        colour, pull_stats = imagery_tools.pull_layers(
            colour,
            layer_at_colour,
            pulls,
            texel_m=fp.size_m / colour.shape[0],
            tapers=pull_tapers,
            windows=pull_windows,
            max_br=pull_max_br,
            lum_gates=pull_lum_gates,
        )
        Image.fromarray(colour).save(out / "colour.png", format="PNG", compress_level=3)
        stats["base_pull"] = pull_stats
        _log(f"  base colour pulled toward the palette on {len(pulls)} layers")
    chroma = (getattr(spec, "IMAGERY", None) or {}).get("chroma_pull")
    if chroma and colour is not None:
        from PIL import Image

        from . import imagery as imagery_tools

        Image.MAX_IMAGE_PIXELS = None
        layer_at_colour = layer
        if layer.shape[0] != colour.shape[0]:
            layer_at_colour = np.asarray(
                Image.fromarray(layer).resize((colour.shape[0], colour.shape[0]), Image.NEAREST)
            )
        ids = [
            list(spec.TERRAIN["materials"]).index(name)
            for name in chroma.get("layers", [])
            if name in spec.TERRAIN["materials"]
        ]
        near = chroma.get("near_layer")
        colour, pulled = imagery_tools.pull_chroma(
            colour,
            layer_at_colour,
            ids,
            float(chroma["target_br"]),
            float(chroma.get("window_m", 100.0)),
            fp.size_m / colour.shape[0],
            tolerance=float(chroma.get("tolerance", 1.05)),
            near_layer=list(spec.TERRAIN["materials"]).index(near)
            if near in spec.TERRAIN["materials"]
            else None,
            within_m=float(chroma.get("within_m", 120.0)),
            saturation_gain=float(chroma.get("saturation_gain", 1.0)),
        )
        Image.fromarray(colour).save(out / "colour.png", format="PNG", compress_level=3)
        stats["chroma_pull_cells"] = pulled
        _log(f"  chroma pulled on {pulled} cells")
    lakes = (getattr(spec, "IMAGERY", None) or {}).get("lakes")
    if lakes and colour is not None:
        from PIL import Image
        from scipy import ndimage

        from . import imagery as imagery_tools

        Image.MAX_IMAGE_PIXELS = None
        dem_at_colour = dem
        if dem.shape[0] != colour.shape[0]:
            dem_at_colour = np.asarray(
                Image.fromarray(dem.astype("float32"), mode="F").resize(
                    (colour.shape[0], colour.shape[0]), Image.BILINEAR
                )
            )
        snow_refilled = None
        if (out / "refill.npy").is_file():
            # The snow the de-lighting refilled: lidar-flat, but not water.
            kinds = np.load(out / "refill.npy")
            if kinds.shape[0] != colour.shape[0]:
                kinds = np.asarray(
                    Image.fromarray(kinds).resize((colour.shape[0], colour.shape[0]), Image.NEAREST)
                )
            snow_refilled = ndimage.binary_dilation(
                kinds == 2, iterations=max(1, int(4.0 / (fp.size_m / colour.shape[0])))
            )
            del kinds
        colour, lake_cells, lake_mask = imagery_tools.paint_lakes(
            colour,
            dem_at_colour,
            fp.size_m / colour.shape[0],
            rgb=lakes["rgb"],
            max_lum=float(lakes.get("max_lum", 0.1)),
            min_area_m2=float(lakes.get("min_area_m2", 400.0)),
            cyan_excess=lakes.get("cyan_excess"),
            cyan_min_lum=float(lakes.get("cyan_min_lum", 0.35)),
            cyan_max_slope_deg=lakes.get("cyan_max_slope_deg"),
            flat_rms_m=lakes.get("flat_rms_m"),
            cyan_grow_m=float(lakes.get("cyan_grow_m", 0.0)),
            cyan_edge_m=float(lakes.get("cyan_edge_m", 0.0)),
            exclude=snow_refilled,
        )
        Image.fromarray(colour).save(out / "colour.png", format="PNG", compress_level=3)
        if lakes.get("material") and lake_mask.any():
            # Water gets its own layer (a flat dark tile, no cushions on it) and the
            # mask ships for the level stage's water objects.
            mask_dem = lake_mask
            if lake_mask.shape[0] != layer.shape[0]:
                mask_dem = (
                    np.asarray(
                        Image.fromarray(lake_mask.astype("uint8") * 255).resize(
                            (layer.shape[0], layer.shape[0]), Image.NEAREST
                        )
                    )
                    > 127
                )
            layer[mask_dem] = list(spec.TERRAIN["materials"]).index(lakes["material"])
            # A body whose lidar ground is not flat (settled tailings, a berm's toe)
            # is cut half a metre under its 90th-percentile ground, so the level's
            # water surface, set a hand over the body's ground, covers every cell.
            lab_l, _n_l = ndimage.label(mask_dem)
            cut = 0
            for k, sl in enumerate(ndimage.find_objects(lab_l), start=1):
                if sl is None:
                    continue
                cells = lab_l[sl] == k
                z = dem[sl][cells]
                top = float(np.percentile(z, 90))
                if top - float(z.min()) > 0.3:
                    lowered = np.minimum(z, top - 0.5)
                    cut += int((lowered < z).sum())
                    block = dem[sl]
                    block[cells] = lowered
            stats["lake_cells_cut"] = cut
            del lab_l
            np.save(out / "lakes.npy", mask_dem)
        stats["lake_cells_painted"] = lake_cells
        _log(f"  lakes painted: {lake_cells} cells")
    regions = (getattr(spec, "IMAGERY", None) or {}).get("base_pull_regions")
    if regions and colour is not None:
        from PIL import Image

        from . import imagery as imagery_tools

        Image.MAX_IMAGE_PIXELS = None
        dem_at_colour = dem
        if dem.shape[0] != colour.shape[0]:
            dem_at_colour = np.asarray(
                Image.fromarray(dem.astype("float32"), mode="F").resize(
                    (colour.shape[0], colour.shape[0]), Image.BILINEAR
                )
            )
        colour, region_stats = imagery_tools.pull_regions(
            colour, dem_at_colour, regions, fp.size_m / colour.shape[0]
        )
        Image.fromarray(colour).save(out / "colour.png", format="PNG", compress_level=3)
        stats["base_pull_regions"] = region_stats
        _log(f"  base colour pulled by elevation band on {len(region_stats)} regions")
    if colour is not None:
        # The mean sRGB colour and luminance of the finished base under each layer.
        from PIL import Image

        layer_at_colour = layer
        if layer.shape[0] != colour.shape[0]:
            layer_at_colour = np.asarray(
                Image.fromarray(layer.astype("uint8")).resize(
                    (colour.shape[0], colour.shape[0]), Image.NEAREST
                )
            )
        means = {}
        for index, name in enumerate(spec.TERRAIN["materials"]):
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
        stats["layer_mean_srgb"] = means
        stats["near_black_fraction"] = round(float((colour.max(axis=-1) < 13).mean()), 6)
    if pad_outlines and surface_index is not None:
        from scipy import ndimage

        # A painted pad keeps the flight's own grain: the level stage fills its mean
        # and multiplies this map back over it, so a car park is stall stripes, kerb
        # islands and patched asphalt rather than 14,000 m2 of even grey. What the
        # flight has that the level does not (a parked car, a roof) is repainted
        # from its own ring first, so the grain carries none of it.
        pad_texture = np.ones((colour.shape[0], colour.shape[1]), dtype="float32")
        pad_scale = colour.shape[0] / dem.shape[0]
        for entry in pad_outlines:
            pad, inside = entry["pad"], entry["inside"]
            rr0, rr1, cc0, cc1 = entry["rr0"], entry["rr1"], entry["cc0"], entry["cc1"]
            keep = pad.get("keep_flight_grain") and pad.get("paint", True)
            if keep and colour is not None:
                from PIL import Image

                from . import vegetation

                cr0, cr1 = int(rr0 * pad_scale), int(rr1 * pad_scale)
                ccl0, ccl1 = int(cc0 * pad_scale), int(cc1 * pad_scale)
                inside_c = (
                    np.asarray(
                        Image.fromarray(inside.astype("uint8") * 255).resize(
                            (ccl1 - ccl0, cr1 - cr0), Image.NEAREST
                        )
                    )
                    > 127
                )
                texel = fp.size_m / colour.shape[0]
                block = colour[cr0:cr1, ccl0:ccl1].astype("float32")
                lum_b = block.mean(axis=-1) / 255.0
                med = float(np.median(lum_b[inside_c])) if inside_c.any() else 1.0
                lo, hi = pad.get("repaint_outside", (0.6, 1.6))
                odd = inside_c & ((lum_b < lo * med) | (lum_b > hi * med))
                if odd.any():
                    full = np.zeros(colour.shape[:2], dtype=bool)
                    full[cr0:cr1, ccl0:ccl1] = odd
                    colour = vegetation.erase_dots(colour, full, 6.0, texel)
                    block = colour[cr0:cr1, ccl0:ccl1].astype("float32")
                    lum_b = block.mean(axis=-1) / 255.0
                    del full
                # The grain is the lot's luminance over its own 6 m mean.
                low = ndimage.uniform_filter(lum_b, size=max(3, int(6.0 / texel)), mode="nearest")
                grain = np.clip(lum_b / np.maximum(low, 1e-4), 0.55, 1.6).astype("float32")
                pad_texture[cr0:cr1, ccl0:ccl1] = np.where(inside_c, grain, 1.0)
                del block, lum_b, low, grain, odd, inside_c
            pin = pad.get("pin_layer")
            if pin and pin in spec.TERRAIN["materials"]:
                # The ground round a lot is the plain it was built on, whatever
                # slope its kerb wears: the layer within ``pin_layer_m`` of the
                # outline is pinned to it (a cut face painted talus and limestone
                # was the first thing the default spawn showed).
                pin_m = float(pad.get("pin_layer_m", 15.0))
                near_pad = ndimage.distance_transform_edt(~inside) * res <= pin_m
                near_pad &= ~inside
                if surface_index is not None:
                    near_pad &= surface_index[rr0:rr1, cc0:cc1] == 0
                block_l = layer[rr0:rr1, cc0:cc1]
                block_l[near_pad] = list(spec.TERRAIN["materials"]).index(pin)
                del near_pad, block_l
            if not pad.get("paint", True):
                continue  # a gravel lot keeps the flight's own colour
            surface_index[rr0:rr1, cc0:cc1] = np.where(
                inside,
                1 if pad.get("surface", "paved") == "paved" else 2,
                surface_index[rr0:rr1, cc0:cc1],
            )
            shoulder_m = float(pad.get("shoulder_m", 1.5))
            if colour is not None and shoulder_m > 0:
                # A car park has a crisp kerb: outside it a gravel shoulder in the
                # dirt bed's own tone, feathered a metre outward.
                dirt = spec.ROADS["surfaces"].get("dirt", {}).get("terrain_material")
                shoulder_rgb = pad.get(
                    "shoulder_rgb", (spec.PALETTE.get(dirt) or {}).get("base", [0.74, 0.67, 0.56])
                )
                scale = colour.shape[0] / dem.shape[0]
                cr0, cr1 = int(rr0 * scale), int(rr1 * scale)
                cc0c, cc1c = int(cc0 * scale), int(cc1 * scale)
                from PIL import Image

                inside_c = (
                    np.asarray(
                        Image.fromarray(inside.astype("uint8") * 255).resize(
                            (cc1c - cc0c, cr1 - cr0), Image.NEAREST
                        )
                    )
                    > 127
                )
                dist_c = ndimage.distance_transform_edt(~inside_c) * (res / scale)
                wc = np.where(
                    dist_c <= shoulder_m,
                    1.0,
                    np.clip(1.0 - (dist_c - shoulder_m) / 1.0, 0.0, 1.0),
                ).astype("float32") * (~inside_c)
                tone = np.asarray(shoulder_rgb, dtype="float32") * 255.0
                block = colour[cr0:cr1, cc0c:cc1c].astype("float32")
                colour[cr0:cr1, cc0c:cc1c] = np.clip(
                    block * (1 - wc[..., None]) + tone[None, None, :] * wc[..., None], 0, 255
                ).astype("uint8")
        if bool((pad_texture != 1.0).any()):
            np.save(out / "pad_texture.npy", pad_texture)
        del pad_texture
        if colour is not None:
            from PIL import Image

            Image.fromarray(colour).save(out / "colour.png", format="PNG", compress_level=3)
    if surface_index is not None:
        materials = list(spec.TERRAIN["materials"])
        for surface_name, index in (("paved", 1), ("dirt", 2)):
            cfg = spec.ROADS["surfaces"].get(surface_name)
            if cfg and cfg.get("terrain_material") in materials:
                layer[surface_index == index] = materials.index(cfg["terrain_material"])
        fractions = {name: float((layer == i).mean()) for i, name in enumerate(materials)}
    slope = hm.slope_degrees(dem, res)
    stats.update(
        {
            "min_elevation_m": float(dem.min()),
            "max_elevation_m": float(dem.max()),
            "mean_elevation_m": float(dem.mean()),
            "relief_m": float(dem.max() - dem.min()),
            "slope_mean_deg": float(slope.mean()),
            "slope_p95_deg": float(np.percentile(slope, 95)),
            "slope_over_30_fraction": float((slope > 30).mean()),
            "layer_fractions": fractions,
        }
    )
    np.save(out / "dem.npy", dem.astype("float32"))
    np.save(out / "layer.npy", layer.astype("uint8"))
    if objects_spec:
        (out / "objects.json").write_text(
            json.dumps(detected, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n"
        )
    (out / "terrain.stats.json").write_text(
        json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    _log(
        f"  elevation {stats['min_elevation_m']:.1f}..{stats['max_elevation_m']:.1f} m"
        f" (relief {stats['relief_m']:.0f} m), holes {holes}, spikes {spikes}, "
        f"{time.time() - started:.0f} s"
    )
    return stats


# ---------------------------------------------------------------------------
# level
# ---------------------------------------------------------------------------


def level(spec, example_root: Path) -> dict:
    """Terrain arrays -> the complete mod/levels/<mod_id>/ tree + authoring evidence."""

    from . import level_builder

    started = time.time()
    fp = footprint_for(spec)
    data_root = example_root / "data"
    terrain_dir = data_root / "terrain"
    if not (terrain_dir / "dem.npy").is_file():
        raise FileNotFoundError("run the terrain stage first")
    dem = np.load(terrain_dir / "dem.npy")
    layer = np.load(terrain_dir / "layer.npy")
    terrain_stats = json.loads((terrain_dir / "terrain.stats.json").read_text(encoding="utf-8"))
    encoded = hm.encode(dem, layer)
    _log(
        f"  maxHeight {encoded.max_height_m:.0f} m over "
        f"{encoded.min_elevation_m:.1f}..{encoded.max_elevation_m:.1f} m"
    )
    detected = None
    if (terrain_dir / "objects.json").is_file():
        detected = json.loads((terrain_dir / "objects.json").read_text(encoding="utf-8"))
    report = level_builder.build_level(
        spec, example_root, fp, dem, layer, encoded, terrain_stats, detected_objects=detected
    )
    level_root = Path(report["level_root"])
    if report.get("forest"):
        forest = report["forest"]
        _log(
            f"  forest: {forest.get('instances', 0)} instances ({forest.get('rocks', 0)} rocks, "
            f"{forest.get('shrubs', 0)} shrubs, {forest.get('trees', 0)} trees)"
        )
    _log(
        f"  roads: {report['roads']['roads']} decal roads, "
        f"{report['roads']['length_m'] / 1000:.1f} km"
    )

    # Authoring evidence: the handoff is the single source of truth the tests hash against.
    authoring = example_root / "authoring"
    authoring.mkdir(parents=True, exist_ok=True)
    shipped = {}
    for name in (
        "theTerrain.ter",
        "theTerrain.terrainheightmap.png",
        "theTerrain.terrain.json",
        "info.json",
        "art/terrains/main.materials.json",
        f"forest/{spec.MOD_ID}.forest4.json",
        "art/forest/managedItemData.json",
        f"art/shapes/{spec.MOD_ID}/main.materials.json",
        f"art/shapes/{spec.MOD_ID}_buildings/main.materials.json",
    ):
        path = level_root / name
        if not path.is_file():
            continue
        shipped[name] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    buildings_dir = level_root / "art" / "shapes" / f"{spec.MOD_ID}_buildings"
    for path in sorted(buildings_dir.glob("*.dae")) if buildings_dir.is_dir() else []:
        shipped[f"art/shapes/{spec.MOD_ID}_buildings/{path.name}"] = {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
    for summary in report.get("shapes", []):
        path = level_root / "art" / "shapes" / spec.MOD_ID / summary["file"]
        shipped[f"art/shapes/{spec.MOD_ID}/{summary['file']}"] = {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "triangles": summary["triangles"],
        }
    handoff = {
        "schema": HANDOFF_SCHEMA,
        "asset": {"id": spec.MOD_ID, "display_name": spec.DISPLAY_NAME, "zip": spec.ZIP_BASENAME},
        "site": dict(spec.SITE),
        "footprint": {
            **fp.to_json(),
            "bounds": list(fp.bounds),
            "wgs84_bbox_swne": list(fp.wgs84_bbox()),
        },
        "sources": {
            "elevation": [
                {
                    k: v
                    for k, v in s.items()
                    if k in ("kind", "name", "prefix", "resolution", "citation", "license")
                }
                for s in spec.SOURCES["elevation"]
            ],
            "imagery": "USGS/USDA NAIP orthoimagery via The National Map (public domain)",
            "roads": "OpenStreetMap contributors, ODbL 1.0",
            "pointcloud": (spec.SOURCES.get("pointcloud") or {}).get("citation"),
        },
        "terrain": {
            "size_px": int(spec.SITE["size_px"]),
            "square_size_m": float(spec.SITE["square_size_m"]),
            "max_height_m": encoded.max_height_m,
            "min_elevation_m": encoded.min_elevation_m,
            "max_elevation_m": encoded.max_elevation_m,
            "terrain_block": report["terrain_block"],
            "materials": report["materials"],
            "stats": terrain_stats,
        },
        "roads": report["roads"],
        "spawns": report["spawns"],
        "imagery": report.get("imagery", {}),
        "layer_tints": report.get("layer_tints", {}),
        "forest": report.get("forest", {}),
        "trail_features": report.get("trail_features", []),
        "road_contrast": report.get("road_contrast", {}),
        "shipped": shipped,
    }
    (authoring / f"{spec.MOD_ID}.handoff.json").write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    shutil.copyfile(
        level_root / f"{spec.MOD_ID}_preview.jpg", authoring / f"{spec.MOD_ID}_thumbnail.jpg"
    )
    _log(f"  level tree written in {time.time() - started:.0f} s")
    return handoff


# ---------------------------------------------------------------------------
# dist
# ---------------------------------------------------------------------------


def dist(spec, example_root: Path) -> dict:
    from . import packaging

    level_root = example_root / "mod" / "levels" / spec.MOD_ID
    for required in (
        "info.json",
        "theTerrain.ter",
        "main/items.level.json",
        "art/terrains/main.materials.json",
    ):
        if not (level_root / required).is_file():
            raise FileNotFoundError(
                f"{spec.MOD_ID}: {required} missing - run the level stage before dist"
            )
    return packaging.build_distribution(example_root, spec.MOD_ID, spec.ZIP_BASENAME)


# ---------------------------------------------------------------------------
# ledger: the DESIGN.md build ledger is generated from the handoff, never typed
# ---------------------------------------------------------------------------

LEDGER_HEADING = "## Build ledger"


def render_ledger(spec, example_root: Path) -> str:
    """Markdown for the DESIGN.md build ledger, from the handoff and the dist lock."""

    handoff = json.loads(
        (example_root / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(encoding="utf-8")
    )
    terrain = handoff["terrain"]
    stats = terrain["stats"]
    rows = [
        (
            "Elevation range",
            f"{stats['min_elevation_m']:.1f} - {stats['max_elevation_m']:.1f} m "
            f"(relief {stats['relief_m']:.0f} m)",
        ),
        (
            "Terrain block",
            f"{terrain['size_px']} samples @ {terrain['square_size_m']:g} m, "
            f"maxHeight {terrain['max_height_m']:.0f} m",
        ),
    ]
    for source in stats["sources"]:
        if source["kind"] == "usgs_3dep":
            rows.append(
                (
                    "3DEP baseline coverage",
                    f"{source['valid_fraction']:.1%} of the level before compositing",
                )
            )
        else:
            rows.append(
                (
                    f"Lidar overlay `{source['name']}`",
                    f"covers {source['overlay_valid_fraction']:.1%}, "
                    f"levelled by {source['datum_shift_m']:+.2f} m onto 3DEP",
                )
            )
    rows += [
        (
            "Holes filled / spikes clamped",
            f"{stats['holes_filled']} / {stats['spikes_clamped']} "
            f"(spike threshold {stats['despike_threshold_m']:g} m)",
        ),
        (
            "Slope mean / p95 / over 30 deg",
            f"{stats['slope_mean_deg']:.1f} / {stats['slope_p95_deg']:.1f} deg / "
            f"{stats['slope_over_30_fraction']:.1%}",
        ),
        (
            "Layer split",
            ", ".join(
                f"{name} {fraction:.0%}"
                for name, fraction in sorted(
                    stats["layer_fractions"].items(), key=lambda kv: -kv[1]
                )
            ),
        ),
        (
            "Roads",
            f"{handoff['roads']['roads']} decal roads, "
            f"{handoff['roads']['length_m'] / 1000:.1f} km ("
            + ", ".join(f"{k} {v}" for k, v in sorted(handoff["roads"]["by_type"].items()))
            + ")",
        ),
        (
            "Spawns",
            "; ".join(
                f"{s['objectname']} at ({s['level_xy'][0]:.0f}, {s['level_xy'][1]:.0f}), "
                f"{s['z'] + terrain['min_elevation_m']:.0f} m"
                for s in handoff["spawns"]
            ),
        ),
    ]
    imagery_h = handoff.get("imagery") or {}
    if imagery_h.get("delight"):
        rows.append(
            (
                "Imagery de-lighting",
                f"sun az {imagery_h['sun_azimuth_deg']:.0f} / "
                f"alt {imagery_h['sun_altitude_deg']:.0f} deg "
                f"(fit r={imagery_h['sun_fit']['correlation']:.2f}), "
                f"Minnaert k {imagery_h['minnaert_k']:.2f}, "
                f"cast shadow {imagery_h['cast_shadow_fraction']:.1%}, gain p05-p95 "
                f"{imagery_h['gain_p05']:.2f}-{imagery_h['gain_p95']:.2f}",
            )
        )
    if "objects" in stats:
        o = stats["objects"]
        rows.append(
            (
                "Surface objects removed",
                f"{o['objects']} bumps "
                + "("
                + ", ".join(f"{k} {v}" for k, v in sorted(o["kinds"].items()))
                + "), "
                f"{o['structures_flattened']} structures, {o['removed_volume_m3']:.0f} m3 lowered",
            )
        )
    if "canopy" in stats:
        c = stats["canopy"]
        rows.append(
            (
                "Canopy height model",
                f"lidar returns on {c['cells_with_returns']:.1%} of cells, ground datum offset "
                f"{c['ground_offset_m']:+.2f} m, canopy over 2 m on {c['canopy_over_2m']:.1%}, "
                f"heights p95 {c['height_p95_m']:.1f} m, max {c['height_max_m']:.1f} m",
            )
        )
    if "road_carve" in stats:
        rc = stats["road_carve"]
        rows.append(
            (
                "Road beds carved",
                f"{rc['roads']} ways, {rc['length_m'] / 1000:.1f} km, cut/fill up to "
                f"{rc['max_cut_m']:.1f}/{rc['max_fill_m']:.1f} m, "
                f"{rc.get('bed_cells', 0)} bed cells",
            )
        )
    forest_h = handoff.get("forest") or {}
    if forest_h.get("instances"):
        rows.append(
            (
                "Placed objects",
                f"{forest_h['instances']} forest items: {forest_h.get('rocks', 0)} rocks, "
                f"{forest_h.get('shrubs', 0)} shrubs, {forest_h.get('trees', 0)} trees "
                + "("
                + ", ".join(f"{k} {v}" for k, v in sorted((forest_h.get("species") or {}).items()))
                + "); "
                f"{forest_h['triangles_if_all_drawn'] / 1e6:.1f} M triangles if all drawn"
                + (
                    f"; trees at the lidar's tops, heights p50 {forest_h['height_p50_m']:.1f} / "
                    f"p95 {forest_h['height_p95_m']:.1f} m"
                    if forest_h.get("source") == "lidar canopy"
                    else ""
                ),
            )
        )
    features = handoff.get("trail_features") or []
    if features:
        inside = [f for f in features if f["inside"]]
        outside = [f["name"] for f in features if not f["inside"]]
        rows.append(
            (
                "Trail features",
                "; ".join(
                    f"{f['name']} at ({f['level_xy'][0]:.0f}, {f['level_xy'][1]:.0f}), "
                    f"{f['elevation_m']:.0f} m"
                    + (
                        f", {f['nearest_road_m']:.0f} m from the road"
                        if f["nearest_road_m"] is not None
                        else ""
                    )
                    for f in inside
                )
                + (f"; outside the footprint: {', '.join(outside)}" if outside else ""),
            )
        )
    lock_path = example_root / "dist" / f"{spec.MOD_ID}.lock.json"
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        rows.append(
            (
                "Distribution",
                f"`{lock['zip']}`, {lock['members']} members, {lock['size'] / 1e6:.1f} MB, "
                f"sha256 `{lock['sha256'][:16]}...`, build serial {lock['build_serial']}",
            )
        )
    lines = [
        LEDGER_HEADING,
        "",
        f"Generated by `build.py {example_root.name} ledger` from "
        f"`authoring/{spec.MOD_ID}.handoff.json`; the handoff is authoritative.",
        "",
        "| Measured | Value |",
        "| --- | --- |",
    ]
    lines += [f"| {key} | {value} |" for key, value in rows]
    return "\n".join(lines) + "\n"


def ledger(spec, example_root: Path) -> str:
    """Rewrite the ``## Build ledger`` section (through end of file) of DESIGN.md."""

    design_path = example_root / "DESIGN.md"
    text = design_path.read_text(encoding="utf-8")
    rendered = render_ledger(spec, example_root)
    index = text.find(LEDGER_HEADING)
    head = text[:index].rstrip("\n") + "\n\n" if index >= 0 else text.rstrip("\n") + "\n\n"
    design_path.write_text(head + rendered, encoding="utf-8", newline="\n")
    _log(f"  ledger rewritten in {design_path.name}")
    return rendered
