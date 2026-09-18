"""Objects the lidar surface contains: find them, take them out of the ground, place them.

A "highest hit" grid (Meteor Crater's NCALM product) still has every shrub, boulder,
fence post and building in it as a bump; a bare-earth grid (3DEP) keeps boulders and
rock outcrops because they are ground. Either way the sensible terrain is the
grey-opening of the surface (everything narrower than ``open_m`` removed), and each
removed bump is a candidate object. The imagery decides what it was: green and dark
under a bump is a shrub, pale is a rock, long and thin is a fence or wall, big and
rectangular is a building. Rocks and shrubs come back as placed meshes; fences and
buildings are simply gone (the pack avoids the built environment on purpose).
"""

from __future__ import annotations

import math

import numpy as np


def _disc(radius_px: int) -> np.ndarray:
    r = max(1, int(radius_px))
    y, x = np.mgrid[-r : r + 1, -r : r + 1]
    return (x * x + y * y) <= r * r


# What a `detect_objects` pass reports when it never ran. `pipeline` hands this back for a
# level whose spec sets `"detect": None`, so the handoff and the build log keep their shape
# and a reader sees the zeros rather than a missing section. Every count a real pass
# reports is here and zero; `open_m` and `min_height_m` are deliberately NOT, because no
# opening happened and a settings key present here would read as one that did.
def detect_off_stats() -> dict:
    return {
        "candidates": 0,
        "objects": 0,
        "rejected_cliff": 0,
        "berms_removed": 0,
        "structures_flattened": 0,
        "removed_volume_m3": 0.0,
        "detect": "off",
    }


def detect_objects(
    dsm: np.ndarray,
    res: float,
    *,
    open_m: float = 6.0,
    min_height_m: float = 0.5,
    min_area_m2: float = 1.0,
    max_area_m2: float = 80.0,
    structure_open_m: float = 40.0,
    structure_min_area_m2: float = 60.0,
    structure_min_height_m: float = 1.5,
    max_relief_m: float = 6.0,
    relief_per_peak: float = 2.5,
    max_height_m: float = 0.0,
    cliff_slope_deg: float = 0.0,
    cliff_buffer_m: float = 20.0,
    berm_min_elongation: float | None = None,
    berm_max_width_m: float = 12.0,
    berm_min_height_m: float | None = None,
) -> tuple[np.ndarray, list[dict], dict]:
    """Return (ground, objects, stats): the opened ground surface and every bump it removed.

    Small bumps (``open_m`` footprint) become candidate rocks/shrubs. Large tall bumps
    (buildings, parked vehicles in a lot) are found with the wider ``structure_open_m``
    opening and are flattened without becoming anything; ``structure_open_m`` 0 turns
    that pass off (a level whose only compound is an authored flatten box needs no
    rule that could take a ridge crest for a roof). A bump taller than
    ``max_height_m`` (when set) is landform and stays; so does any bump within
    ``cliff_buffer_m`` of ground steeper than ``cliff_slope_deg`` (when set): a ledge
    on a crater wall is the wall, not a boulder on it.
    """

    from scipy import ndimage

    surface = dsm.astype("float32")
    footprint = _disc(open_m / 2.0 / res)
    opened = ndimage.grey_opening(surface, footprint=footprint, mode="nearest")
    near_cliff = None
    local_slope = None
    if cliff_slope_deg > 0 or max_height_m > 0:
        smooth = ndimage.gaussian_filter(opened, 2.0)
        gy, gx = np.gradient(smooth, res)
        local_slope = np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")
        del smooth, gy, gx
    if cliff_slope_deg > 0:
        # The cliff band is read on a widely opened surface (a 24 m disc): a berm or
        # a wall is not a cliff, and its own flanks must not put it "within 10 m of
        # ground over 35 degrees" and keep it.
        wide = _coarse_opening(opened, 12.0 / res)
        gy_w, gx_w = np.gradient(ndimage.gaussian_filter(wide, 2.0), res)
        steep = np.degrees(np.arctan(np.hypot(gx_w, gy_w))) > cliff_slope_deg
        near_cliff = ndimage.binary_dilation(steep, iterations=max(1, int(cliff_buffer_m / res)))
        del steep, wide, gy_w, gx_w
    # An opening on a convex ridge also shaves the ridge crest: only keep residual where
    # the bump is isolated, i.e. its footprint area is bounded (blob filter below).
    residual = surface - opened
    candidate = residual > min_height_m
    labels, count = ndimage.label(candidate)
    index = np.arange(1, count + 1)
    areas = ndimage.sum(candidate, labels, index) * res * res
    peaks = ndimage.maximum(residual, labels, index)
    objs = ndimage.find_objects(labels)
    keep = np.zeros(count + 1, dtype=bool)
    objects: list[dict] = []
    rejected_cliff = 0
    berms = 0
    k = max(1, round(1.5 / res))
    for i, sl in enumerate(objs, start=1):
        area = float(areas[i - 1])
        h = (sl[0].stop - sl[0].start) * res
        w = (sl[1].stop - sl[1].start) * res
        bbox_area = max(h * w, 1e-6)
        compactness = area / bbox_area
        elongation = max(h, w) / max(min(h, w), res)
        # Wires, fences and walls: long thin blobs of any area (a power line is a
        # kilometre of raised surface) come out of the ground and nothing goes back.
        linear = elongation >= 6.0 and area <= 20000.0
        if area < min_area_m2 and not linear:
            # Too small to be anything: a post, a sign, a single return. It still
            # leaves the ground (nothing stands on a highest-hit spike), it just does
            # not come back as an object.
            keep[i] = True
            continue
        if not linear and area > max_area_m2:
            continue
        ys, xs = np.nonzero(labels[sl] == i)
        cy = sl[0].start + ys.mean()
        cx = sl[1].start + xs.mean()
        peak = float(peaks[i - 1])
        gentle_here = local_slope is not None and local_slope[int(cy), int(cx)] < 15.0
        if (
            berm_min_elongation is not None
            and peak > (berm_min_height_m if berm_min_height_m is not None else max_height_m)
            and gentle_here
            and min(h, w) <= berm_max_width_m
            and elongation >= berm_min_elongation
            and not (near_cliff is not None and near_cliff[int(cy), int(cx)])
        ):
            # A berm or a wall: tall, narrow and long on gentle ground away from
            # any cliff. It leaves the ground and nothing comes back (a dashed
            # berm across the ejecta stood as a row of ledge-textured walls).
            keep[i] = True
            berms += 1
            continue
        if max_height_m > 0 and peak > max_height_m and not linear:
            if area > 20.0 and not gentle_here:
                rejected_cliff += 1  # a bump that tall and that wide on a slope is landform
                continue
            if area > 20.0:
                # A tall wide bump on gentle ground is a big juniper or a shed: it
                # leaves the ground and the imagery says which (a pale one is never
                # placed on the plain, the layer caps see to that).
                pass
            else:
                # A pole, a mast, a lone post: too tall for its footprint to be
                # anything but built. It leaves the ground and nothing comes back.
                keep[i] = True
                continue
        if (
            near_cliff is not None
            and not linear
            and near_cliff[int(cy), int(cx)]
            and not gentle_here
        ):
            rejected_cliff += 1  # a ledge on the wall; a bush on a bench is not
            continue
        # A bump whose ground spans more relief than the bump itself is a cliff-edge
        # shaving of the opening, and a bump much taller than wide is a ridge crest:
        # neither comes out of the ground (nothing would go back in its place).
        r0, c0 = int(cy), int(cx)
        window = opened[max(0, r0 - k) : r0 + k + 1, max(0, c0 - k) : c0 + k + 1]
        relief = float(window.max() - window.min())
        # A post or a single juniper trunk is tall for its footprint too, so the
        # height-to-width test only applies once the footprint could be a ridge.
        spire = peak > 2.5 * math.sqrt(area) and area >= 4.0 and not linear
        if relief > max(max_relief_m, relief_per_peak * peak) or spire:
            rejected_cliff += 1
            continue
        keep[i] = True
        objects.append(
            {
                "row": float(cy),
                "col": float(cx),
                "area_m2": round(area, 2),
                "w_m": round(w, 2),
                "h_m": round(h, 2),
                "peak_m": round(float(peaks[i - 1]), 2),
                "compactness": round(compactness, 3),
                "elongation": round(float(elongation), 2),
                "kind": "linear" if linear else None,
            }
        )
    small_mask = keep[labels]
    # The threshold only outlines the top of a bump; grow the mask so the skirt goes too
    # (the opening already removed the whole bump, the mask just says where to use it).
    small_mask = ndimage.binary_dilation(small_mask, iterations=int(1.5 / res) + 1)
    # Blobs too big for the small pass but not structures are ridge shavings: keep the
    # original surface there. Structures: a wider opening restricted to tall, large blobs.
    ground = np.where(small_mask, opened, surface)
    structures = 0
    count_b = 0
    if structure_open_m > 0:
        big_footprint = _disc(structure_open_m / 2.0 / res)
        opened_big = ndimage.grey_opening(surface, footprint=big_footprint, mode="nearest")
        residual_big = surface - opened_big
        struct_candidate = residual_big > structure_min_height_m
        labels_b, count_b = ndimage.label(struct_candidate)
    if count_b:
        index_b = np.arange(1, count_b + 1)
        areas_b = ndimage.sum(struct_candidate, labels_b, index_b) * res * res
        objs_b = ndimage.find_objects(labels_b)
        struct_mask = np.zeros(surface.shape, dtype=bool)
        peaks_b = ndimage.maximum(residual_big, labels_b, index_b)
        for i, sl in enumerate(objs_b, start=1):
            area = float(areas_b[i - 1])
            tall = float(peaks_b[i - 1]) >= 3.0
            if (area < structure_min_area_m2 and not (tall and area >= 20.0)) or area > 40000.0:
                continue
            h = (sl[0].stop - sl[0].start) * res
            w = (sl[1].stop - sl[1].start) * res
            compactness = area / max(h * w, 1e-6)
            if compactness < 0.45 or max(h, w) / max(min(h, w), res) >= 6.0:
                continue  # ridges, rims, wires and fences are not buildings
            struct_mask[sl] |= labels_b[sl] == i
            structures += 1
        if structures:
            # The whole footprint goes, skirt included: grow the core through everything
            # that still stands 0.3 m proud of the wide opening and touches it, then fill
            # to that opening's floor and feather 4 m into the ground so no berm ring or
            # stepped wall marks where a building or a tree clump stood.
            skirt = residual_big > 0.3
            labels_s, _count_s = ndimage.label(skirt)
            touched = np.unique(labels_s[struct_mask])
            footprint = np.isin(labels_s, touched[touched > 0]) | struct_mask
            footprint = ndimage.binary_dilation(footprint, iterations=int(2 / res) + 1)
            dist = ndimage.distance_transform_edt(~footprint) * res
            w = np.clip(1.0 - dist / 4.0, 0.0, 1.0).astype("float32")
            ground = ground * (1 - w) + np.minimum(ground, opened_big) * w
    # Smooth the seam where small objects were removed.
    seam = ndimage.binary_dilation(small_mask, iterations=1) & ~small_mask
    blurred = ndimage.uniform_filter(ground, size=3, mode="nearest")
    ground = np.where(seam, blurred, ground).astype("float32")
    stats = {
        "candidates": int(count),
        "objects": len(objects),
        "rejected_cliff": int(rejected_cliff),
        "berms_removed": int(berms),
        "structures_flattened": int(structures),
        "removed_volume_m3": round(float(np.clip(surface - ground, 0, None).sum() * res * res), 1),
        "open_m": open_m,
        "min_height_m": min_height_m,
    }
    return ground, objects, stats


def classify_objects(
    objects: list[dict],
    colour_u8: np.ndarray | None,
    grid_size: int,
    *,
    green_threshold: float = 0.045,
    dark_threshold: float = 0.33,
    rock_only: bool = False,
    dark_ratio: float | None = None,
) -> dict:
    """Assign ``kind`` (rock, shrub, linear) to each object from shape and imagery colour.

    A bump is a shrub when its pixels are green, darker than ``dark_threshold``, or
    (with ``dark_ratio``) darker than that share of the ground within 30 m of it: a
    juniper on a pale crest is dark against its ground, not against the map."""

    counts = {"rock": 0, "shrub": 0, "linear": 0}
    scale = (colour_u8.shape[0] / grid_size) if colour_u8 is not None else 1.0
    local = None
    if dark_ratio is not None and colour_u8 is not None:
        from scipy import ndimage

        lum = colour_u8.astype("float32").mean(axis=-1) / 255.0
        local = ndimage.uniform_filter(lum, size=max(3, int(30.0 * scale)), mode="nearest")
        del lum
    for obj in objects:
        if obj["kind"] == "linear" or obj["elongation"] > 4.0 or obj["compactness"] < 0.28:
            obj["kind"] = "linear"
        elif rock_only or colour_u8 is None:
            obj["kind"] = "rock"
        else:
            r = int(obj["row"] * scale)
            c = int(obj["col"] * scale)
            rad = max(1, int(math.sqrt(obj["area_m2"]) * scale / 2))
            patch = (
                colour_u8[max(0, r - rad) : r + rad + 1, max(0, c - rad) : c + rad + 1].astype(
                    "float32"
                )
                / 255.0
            )
            if patch.size == 0:
                obj["kind"] = "rock"
            else:
                mean = patch.reshape(-1, 3).mean(axis=0)
                green = 2 * mean[1] - mean[0] - mean[2]
                dark = mean.mean()
                obj["colour"] = [round(float(v), 3) for v in mean]
                relative_dark = local is not None and dark < float(dark_ratio) * float(
                    local[min(r, local.shape[0] - 1), min(c, local.shape[1] - 1)]
                )
                obj["kind"] = (
                    "shrub"
                    if (green > green_threshold or dark < dark_threshold or relative_dark)
                    else "rock"
                )
        counts[obj["kind"]] += 1
    return counts


def place_objects(
    objects: list[dict],
    ground: np.ndarray,
    res: float,
    fp_size_m: float,
    min_elevation: float,
    *,
    seed: int = 1,
    max_rocks: int = 6000,
    max_shrubs: int = 8000,
    layer: np.ndarray | None = None,
    rock_layers: set[int] | None = None,
    max_rock_height_m: float = 6.0,
) -> list[dict]:
    """Level-frame placements (x, y east/north of centre; z above terrain origin).

    Objects sit at the centre of their detection cell so the height they are given is
    the height the engine's terrain has there. A bump whose 3 m neighbourhood spans more
    relief than the bump itself is a cliff-edge artefact of the opening, not a rock.
    """

    rng = np.random.default_rng(seed)
    half = fp_size_m / 2.0
    out = []
    rocks = [o for o in objects if o["kind"] == "rock"]
    shrubs = [o for o in objects if o["kind"] == "shrub"]
    if layer is not None and rock_layers is not None:
        rocks = [o for o in rocks if int(layer[int(o["row"]), int(o["col"])]) in rock_layers]
    k = max(1, round(1.5 / res))

    def on_a_cliff(o: dict) -> bool:
        r, c = int(o["row"]), int(o["col"])
        window = ground[max(0, r - k) : r + k + 1, max(0, c - k) : c + k + 1]
        relief = float(window.max() - window.min())
        # A 45 degree talus slope spans ~3 m of relief across the window; a knife edge
        # spans tens. A boulder is also never much taller than it is wide.
        too_steep = relief > max(6.0, 2.5 * float(o["peak_m"]))
        too_tall = float(o["peak_m"]) > 2.5 * math.sqrt(float(o["area_m2"]))
        return too_steep or too_tall

    rocks = [o for o in rocks if not on_a_cliff(o)]
    # Prefer the tallest / most compact when over budget.
    rocks.sort(key=lambda o: -(o["peak_m"] * o["compactness"]))
    shrubs.sort(key=lambda o: -o["area_m2"])
    for kind, items, cap in (("rock", rocks, max_rocks), ("shrub", shrubs, max_shrubs)):
        for o in items[:cap]:
            r, c = int(o["row"]), int(o["col"])
            x = c * res - half + res / 2.0
            y = half - r * res - res / 2.0
            z = float(ground[r, c] - min_elevation)
            if kind == "rock":
                # A boulder is never much wider than it is tall: a 12 m bump half a
                # metre high is a mound, not a rock, so its footprint is trimmed to
                # what its height can carry (and 8 m at most).
                max_w = min(8.0, 1.0 + 2.5 * float(o["peak_m"]))
                size = (
                    max(0.6, min(o["w_m"], max_w)) * rng.uniform(0.9, 1.05),
                    max(0.6, min(o["h_m"], max_w)) * rng.uniform(0.9, 1.05),
                    max(0.5, min(o["peak_m"] * 1.25, max_rock_height_m)),
                )
                sink = 0.18 * size[2]
            else:
                w = max(0.8, min(math.sqrt(o["area_m2"]) * 1.15, 6.0))
                size = (w, w, max(0.6, min(o["peak_m"] * 1.1, 6.0)))  # a big juniper is 6 m
                sink = 0.05
            out.append(
                {
                    "kind": kind,
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "z": round(z - sink, 2),
                    "size": [round(v, 2) for v in size],
                    "yaw_deg": round(float(rng.uniform(0, 360)), 1),
                    "peak_m": o["peak_m"],
                }
            )
    return out


def drop_fence_lines(
    objects: list[dict],
    res: float,
    *,
    max_area_m2: float = 3.0,
    line_m: float = 40.0,
    cell_m: float = 2.0,
    post_gap_m: float = 8.0,
) -> int:
    """Mark small objects that stand in straight rows (fence posts, wall stubs) as linear.

    Post centroids are rasterised on a ``cell_m`` grid, dilated so posts up to
    ``post_gap_m`` apart touch, and opened with straight-line structuring elements at
    twelve angles; anything on a surviving ``line_m`` line is a row, not a rock.
    """

    from scipy import ndimage

    small = [o for o in objects if o["kind"] in ("rock", "shrub") and o["area_m2"] <= max_area_m2]
    if len(small) < 6:
        return 0
    cell = max(res, cell_m)
    rows = np.array([int(o["row"] * res / cell) for o in small])
    cols = np.array([int(o["col"] * res / cell) for o in small])
    n = int(max(rows.max(), cols.max())) + 4
    grid = np.zeros((n, n), dtype=bool)
    grid[rows, cols] = True
    grid = ndimage.binary_dilation(grid, iterations=max(1, int(post_gap_m / cell / 2)))
    length = max(5, int(line_m / cell))
    lines = np.zeros_like(grid)
    for angle in np.arange(0, 180, 15):
        t = np.radians(angle)
        se = np.zeros((length, length), dtype=bool)
        centre = length // 2
        for k in range(-centre, centre + 1):
            r = round(centre + k * np.sin(t))
            c = round(centre + k * np.cos(t))
            if 0 <= r < length and 0 <= c < length:
                se[r, c] = True
        lines |= ndimage.binary_opening(grid, structure=se)
    dropped = 0
    for o, r, c in zip(small, rows, cols, strict=True):
        if lines[r, c]:
            o["kind"] = "linear"
            dropped += 1
    return dropped


def scatter_rocks(
    layer: np.ndarray,
    ground: np.ndarray,
    res: float,
    fp_size_m: float,
    min_elevation: float,
    densities_per_ha: dict[int, float],
    *,
    seed: int = 11,
    size_range: tuple[float, float] = (0.3, 1.2),
    toe_bias: float = 1.0,
    toe_window_m: float = 15.0,
    toe_threshold_m: float = 1.5,
    max_count: int = 20000,
    min_elevation_by_layer: dict[int, float] | None = None,
) -> list[dict]:
    """Small rocks scattered on the layers the lidar-scale detector cannot see.

    The 1 m grid keeps boulders; the 0.3-1 m stones that make a talus field read as
    talus are below its resolution, so they are sampled by density per hectare on the
    layers named, biased toward concave toes (where scree actually collects).
    """

    from scipy import ndimage

    rng = np.random.default_rng(seed)
    half = fp_size_m / 2.0
    n = layer.shape[0]
    spacing = 4.0
    count = int(fp_size_m / spacing)
    gx, gy = np.meshgrid(np.arange(count), np.arange(count))
    xs = (gx.ravel() + rng.uniform(0.1, 0.9, gx.size)) * spacing - half
    ys = half - (gy.ravel() + rng.uniform(0.1, 0.9, gy.size)) * spacing
    cols = np.clip(((xs + half) / res).astype(int), 0, n - 1)
    rows = np.clip(((half - ys) / res).astype(int), 0, n - 1)
    smooth = ndimage.uniform_filter(
        ground.astype("float32"), size=max(3, int(toe_window_m / res)), mode="nearest"
    )
    concave = np.clip((smooth - ground) / toe_threshold_m, 0.0, 1.0)
    # A density raster, ramped 40 m across every class line and 80 m of elevation
    # up to a layer's floor, so the stones never stop dead on a contour.
    field = np.zeros(layer.shape, dtype="float32")
    for index, per_ha in densities_per_ha.items():
        on_layer = layer == index
        floor = (min_elevation_by_layer or {}).get(index)
        if floor is not None:  # the benches' rubble, not the low meadows
            ramp = np.clip((ground - (floor - 80.0)) / 80.0, 0.0, 1.0)
            field += on_layer * per_ha * ramp
        else:
            field += on_layer * per_ha
    own = field.copy()
    field = ndimage.gaussian_filter(field, max(1.0, 40.0 / res))
    # The ramp runs between the scatter layers only (never onto a cliff face or a
    # road bed, which have no density of their own), and never lifts a class past
    # three times its own density: the benches take a few of the talus's stones,
    # not the talus's field.
    field = np.minimum(field, 3.0 * own) * np.isin(layer, list(densities_per_ha.keys()))
    density = field[rows, cols]
    probability = density * (spacing * spacing / 1e4) * (1.0 + toe_bias * concave[rows, cols])
    # The toe bias moves a class's stones to its toes, it does not add stones; and
    # the ramps move them across the class lines without changing the count: each
    # class is renormalised so its expected count is its density x its area (the
    # area weighted by the elevation ramp), whatever the blur and the toes did.
    layer_at = layer[rows, cols]
    cell_ha = res * res / 1e4
    for index, per_ha in densities_per_ha.items():
        on_points = layer_at == index
        expected = float(probability[on_points].sum())
        if expected <= 0:
            continue
        on_layer = layer == index
        floor = (min_elevation_by_layer or {}).get(index)
        if floor is not None:
            area = float((np.clip((ground - (floor - 80.0)) / 80.0, 0.0, 1.0) * on_layer).sum())
        else:
            area = float(on_layer.sum())
        probability[on_points] *= per_ha * area * cell_ha / expected
    probability = np.minimum(probability, 1.0)
    keep = rng.uniform(0, 1, xs.size) < probability
    idx = np.nonzero(keep)[0]
    if idx.size > max_count:
        idx = rng.choice(idx, size=max_count, replace=False)
    lo, hi = size_range
    out = []
    for i in idx:
        size = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
        r, c = int(rows[i]), int(cols[i])
        # The three aspect draws, in the order they have always been consumed, so the
        # stream is unchanged. `size` is then the stone's LONGEST horizontal extent,
        # because that is what `scatter_size_m` declares and what scene_objects turns
        # into the forest item's scale, which for a stone is metres and not a
        # multiplier. Jittering one horizontal axis up and the other down left the
        # declared range approximate at both ends, so a declared 0.2 m floor shipped
        # 0.18 m plates. Renormalising the aspect here rather than clamping the result
        # at the bound keeps the size gate able to fail.
        ax = rng.uniform(0.9, 1.1)
        ay = rng.uniform(0.7, 1.0)
        az = rng.uniform(0.55, 0.85)
        aspect = size / max(ax, ay)
        out.append(
            {
                "kind": "rock",
                "x": round(float(xs[i]), 2),
                "y": round(float(ys[i]), 2),
                "z": round(float(ground[r, c] - min_elevation) - 0.2 * size, 2),
                "size": [
                    round(aspect * ax, 2),
                    round(aspect * ay, 2),
                    round(aspect * az, 2),
                ],
                "yaw_deg": round(float(rng.uniform(0, 360)), 1),
                "peak_m": None,
                "source": "scatter",
            }
        )
    return out


def scatter_shrubs(
    layer: np.ndarray,
    ground: np.ndarray,
    res: float,
    fp_size_m: float,
    min_elevation: float,
    densities_per_ha: dict[int, float],
    *,
    seed: int = 21,
    height_range: tuple[float, float] = (0.4, 1.2),
    width_ratio: tuple[float, float] = (1.0, 1.8),
    max_slope_deg: float = 32.0,
    patch_m: float = 60.0,
    patchiness: float = 0.65,
    swale_bias: float = 0.0,
    swale_window_m: float = 40.0,
    swale_threshold_m: float = 1.0,
    material_by_layer: dict[int, str] | None = None,
    max_count: int = 40000,
    exclude: np.ndarray | None = None,
) -> list[dict]:
    """Bushes and tussocks sampled by density per hectare on the layers named.

    The pack could only put a bush somewhere two ways: lift it out of the lidar as a
    bump, or find its shadow in the photograph. Both need the plant to be big enough and
    dark enough to have been measured, so a map of dry grass and knee-high saltbush -
    the Carrizo Plain, the Factory Butte washes - came out with nothing on it at all,
    and that is most of why four of the six levels ship bare. This is the third way, and
    it is the same instrument ``scatter_rocks`` already uses for the stones below the
    lidar's resolution.

    Two things separate it from scattering stones. Vegetation is patchy rather than
    Poisson - a plain of evenly spaced bushes reads as a dot screen - so the density is
    multiplied by a normalised noise field at ``patch_m`` and renormalised afterwards,
    which moves the plants into clumps without changing how many there are. And a bush
    grows where the water is, so ``swale_bias`` gathers them into the hollows exactly as
    the stones' toe bias gathers scree into the concavities.
    """

    from scipy import ndimage

    rng = np.random.default_rng(seed)
    half = fp_size_m / 2.0
    n = layer.shape[0]
    # One candidate per 2 m square, so a density up to 2,500 a hectare is reachable and
    # two bushes never land inside one another.
    spacing = 2.0
    count = int(fp_size_m / spacing)
    gx, gy = np.meshgrid(np.arange(count), np.arange(count))
    xs = (gx.ravel() + rng.uniform(0.1, 0.9, gx.size)) * spacing - half
    ys = half - (gy.ravel() + rng.uniform(0.1, 0.9, gy.size)) * spacing
    cols = np.clip(((xs + half) / res).astype(int), 0, n - 1)
    rows = np.clip(((half - ys) / res).astype(int), 0, n - 1)

    dzdy, dzdx = np.gradient(ground.astype("float32"), res)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    # Nothing grows on a wall, and the last few degrees ramp rather than stop dead, so
    # a hillside does not end in a line of bushes along a contour.
    grows = np.clip((float(max_slope_deg) - slope) / 6.0, 0.0, 1.0)
    if exclude is not None:
        grows = grows * ~exclude

    field = np.zeros(layer.shape, dtype="float32")
    for index, per_ha in densities_per_ha.items():
        field += (layer == index) * float(per_ha)
    own = field.copy()
    # Ramped 20 m across every class line: a wash's saltbush does not stop on the
    # classifier's contour, it thins out over the bank.
    field = ndimage.gaussian_filter(field, max(1.0, 20.0 / res))
    field = np.minimum(field, 3.0 * own) * np.isin(layer, list(densities_per_ha.keys()))

    probability = field[rows, cols] * (spacing * spacing / 1e4) * grows[rows, cols]
    if patchiness > 0.0:
        # Patchiness is one smoothed white-noise field normalised to a mean of 1, so it
        # redistributes plants and never invents them.
        noise = rng.uniform(0.0, 1.0, layer.shape).astype("float32")
        noise = ndimage.gaussian_filter(noise, max(1.0, float(patch_m) / res / 2.0))
        lo, hi = float(noise.min()), float(noise.max())
        noise = (noise - lo) / max(hi - lo, 1e-6)
        patch = 1.0 + float(patchiness) * (2.0 * noise - 1.0)
        probability = probability * patch[rows, cols]
    if swale_bias > 0.0:
        smooth = ndimage.uniform_filter(
            ground.astype("float32"), size=max(3, int(swale_window_m / res)), mode="nearest"
        )
        concave = np.clip((smooth - ground) / max(swale_threshold_m, 1e-3), 0.0, 1.0)
        probability = probability * (1.0 + float(swale_bias) * concave[rows, cols])

    # Each class is renormalised to density x area after the ramp, the patches and the
    # swales, so what those three do is move plants about and never change the count.
    layer_at = layer[rows, cols]
    cell_ha = res * res / 1e4
    for index, per_ha in densities_per_ha.items():
        on_points = layer_at == index
        expected = float(probability[on_points].sum())
        if expected <= 0:
            continue
        area = float((layer == index).sum())
        probability[on_points] *= per_ha * area * cell_ha / expected
    probability = np.minimum(probability, 1.0)
    keep = rng.uniform(0, 1, xs.size) < probability
    idx = np.nonzero(keep)[0]
    if idx.size > max_count:
        idx = rng.choice(idx, size=max_count, replace=False)

    lo_h, hi_h = height_range
    lo_w, hi_w = width_ratio
    out = []
    for i in idx:
        r, c = int(rows[i]), int(cols[i])
        # Log-normal heights: a stand of one-size bushes is a crop, not scrub.
        height = float(np.exp(rng.uniform(np.log(lo_h), np.log(hi_h))))
        width = height * float(rng.uniform(lo_w, hi_w))
        entry = {
            "kind": "shrub",
            "x": round(float(xs[i]), 2),
            "y": round(float(ys[i]), 2),
            # 3 cm in, the seating the pack already uses for a mat or a sapling.
            "z": round(float(ground[r, c] - min_elevation) - 0.03, 2),
            "size": [
                round(width, 2),
                round(width * float(rng.uniform(0.8, 1.0)), 2),
                round(height, 2),
            ],
            "yaw_deg": round(float(rng.uniform(0, 360)), 1),
            "peak_m": None,
            "source": "scatter",
        }
        if material_by_layer:
            family = material_by_layer.get(int(layer[r, c]))
            if family:
                entry["material"] = family
        out.append(entry)
    return out


def _coarse_opening(window: np.ndarray, radius_px: float) -> np.ndarray:
    """A grey opening with a very wide disc, done on a block-minimum pyramid.

    A 120 m disc at 0.5 m is 240 samples across; scipy would build a footprint of
    45,000 taps per output sample. Block-minimum the window so the disc is about 40
    taps across, open there, and bring the floor back up smoothly. The floor is a
    little lower than the exact opening, which for a compound to remove is fine.
    """

    from scipy import ndimage

    f = max(1, int(radius_px // 20))
    if f == 1:
        return ndimage.grey_opening(window, footprint=_disc(radius_px), mode="nearest")
    h, w = window.shape
    ph, pw = (-h) % f, (-w) % f
    padded = np.pad(window, ((0, ph), (0, pw)), mode="edge")
    coarse = padded.reshape((h + ph) // f, f, (w + pw) // f, f).min(axis=(1, 3))
    opened = ndimage.grey_opening(coarse, footprint=_disc(radius_px / f), mode="nearest")
    up = np.kron(opened, np.ones((f, f), dtype=opened.dtype))[:h, :w]
    return ndimage.gaussian_filter(up.astype("float32"), f)


def inside_boxes(objects: list[dict], res: float, fp_size_m: float, boxes: list[dict]):
    """Split ``objects`` into (outside, inside) an authored flatten box: what stood in
    a flattened compound (cars, sheds, planted trees) does not come back as a rock."""

    half = fp_size_m / 2.0
    outside, inside = [], []
    for o in objects:
        x = o["col"] * res - half
        y = half - o["row"] * res
        hit = next(
            (
                b
                for b in boxes
                if abs(x - b["center_xy"][0]) <= float(b.get("size_m", 200.0)) / 2.0
                and abs(y - b["center_xy"][1]) <= float(b.get("size_m", 200.0)) / 2.0
            ),
            None,
        )
        if hit is None:
            outside.append(o)
        elif hit.get("keep_objects_on_layers"):
            # A box that reaches over a crest keeps the crest's blocks: the drop
            # is decided once the layers are classified (``drop_box_objects``).
            o["box_layers"] = list(hit["keep_objects_on_layers"])
            outside.append(o)
        else:
            inside.append(o)
    return outside, inside


def drop_box_objects(objects: list[dict], layer: np.ndarray, materials: list[str]):
    """Drop the objects a keep-layers box deferred whose cell is not on one of its
    named layers (the compound's furniture), keep the ones on the crest."""

    kept, dropped = [], 0
    for o in objects:
        allowed = o.pop("box_layers", None)
        if allowed is not None and o.get("kind") != "shrub":
            # A bush stays on any layer (the flank between the lot and the crest
            # has them); a rock off the kept layers was the compound's furniture.
            under = materials[int(layer[int(o["row"]), int(o["col"])])]
            if under not in allowed:
                dropped += 1
                continue
        kept.append(o)
    return kept, dropped


def inpaint_boxes(
    colour_u8: np.ndarray,
    res: float,
    fp_size_m: float,
    boxes: list[dict],
    *,
    ring_m: float = 30.0,
    keep_mask: np.ndarray | None = None,
    exclude_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Repaint the imagery inside the flatten boxes from the ring of ground around them.

    A flattened compound keeps its roofs, car-park stripes and parked cars in the
    photograph; the level has none of them. The boxes are taken as one mask (two
    that overlap share a ring), the low pass of the fill is a normalised Gaussian
    pyramid over the ring, and the grain is the ring's own high-pass laid in as 16 m
    patches at random quarter turns with 3 m feathered overlaps, each cut from the
    ring arc nearest to it (no mirroring, so nothing radiates from a box centre; no
    far source, so the grain beside a smooth side is smooth), feathered over the
    ring's width at the box sides. ``keep_mask`` cells (the crest and walls) keep their
    photograph.
    """

    from scipy import ndimage

    n = colour_u8.shape[0]
    half = fp_size_m / 2.0
    active = [b for b in boxes if float(b.get("inpaint_ring_m", ring_m)) > 0]
    if not active:
        return colour_u8
    ring = max(float(b.get("inpaint_ring_m", ring_m)) for b in active)
    inside_all = np.zeros((n, n), dtype=bool)
    for box in active:
        cx, cy = box["center_xy"]
        size = float(box.get("size_m", 200.0))
        c0 = int(max(0, (cx - size / 2 + half) / res))
        c1 = int(min(n, (cx + size / 2 + half) / res))
        r0 = int(max(0, (half - (cy + size / 2)) / res))
        r1 = int(min(n, (half - (cy - size / 2)) / res))
        inside_all[r0:r1, c0:c1] = True
    rr, cc = np.nonzero(inside_all)
    pad = int(ring / res) + int(20 / res) + 2
    rr0, rr1 = max(0, rr.min() - pad), min(n, rr.max() + pad + 1)
    cc0, cc1 = max(0, cc.min() - pad), min(n, cc.max() + pad + 1)
    window = colour_u8[rr0:rr1, cc0:cc1].astype("float32")
    inside = inside_all[rr0:rr1, cc0:cc1]
    band = ndimage.binary_dilation(inside, iterations=int(ring / res)) & ~inside
    if keep_mask is not None:
        band &= ~keep_mask[rr0:rr1, cc0:cc1]  # a wall in the ring is not plain
    if not band.any():
        return colour_u8
    weight = band.astype("float32")
    # Low pass: a normalised Gaussian pyramid over the ring, the ring's mean last.
    ring_mean = window[band].reshape(-1, 3).mean(axis=0)
    fill = np.tile(ring_mean.astype("float32"), (*window.shape[:2], 1))
    cover = np.zeros(window.shape[:2], dtype="float32")
    for sigma in (ring / res / 2.0, ring / res, ring / res * 2.0, ring / res * 4.0):
        num = ndimage.gaussian_filter(window * weight[..., None], (sigma, sigma, 0))
        den = ndimage.gaussian_filter(weight, sigma)
        level = num / np.maximum(den, 1e-4)[..., None]
        take = (den > 0.02) & (cover < 0.02)
        fill = np.where(take[..., None], level, fill)
        cover = np.where(take, den, cover)
    # Grain: the ring's high-pass ratio, quilted in as random patches.
    lum_w = window.mean(axis=-1)
    low = ndimage.gaussian_filter(lum_w, 4.0)
    hp = np.clip(lum_w / np.maximum(low, 1e-3), 0.7, 1.4)
    patch_px = max(4, int(16.0 / res))
    feather_px = max(2, int(4.0 / res))
    step = patch_px - feather_px
    rng = np.random.default_rng(11)
    # Ring cells whose whole patch lies in the ring are the sources.
    core = ndimage.binary_erosion(band, iterations=patch_px // 2 + 1)
    if exclude_mask is not None:
        core &= ~exclude_mask[rr0:rr1, cc0:cc1]  # no road fragment is a source
    # No source patch touches the level's edge (a box near the footprint's edge
    # would otherwise quilt the padding's reflections into itself).
    guard = np.zeros(core.shape, dtype=bool)
    m = patch_px // 2 + 1
    if rr0 == 0:
        guard[:m, :] = True
    if rr1 == n:
        guard[-m:, :] = True
    if cc0 == 0:
        guard[:, :m] = True
    if cc1 == n:
        guard[:, -m:] = True
    core &= ~guard
    src_r, src_c = np.nonzero(core)
    quilt = np.ones(window.shape[:2], dtype="float32")
    if src_r.size:
        from scipy.spatial import cKDTree

        # Each patch is cut from the ring arc nearest to it (within 60 m along the
        # ring), so the grain inside a box is the grain of the ground beside that
        # side of it, not one amplitude drawn from the whole ring.
        tree = cKDTree(np.stack([src_r, src_c], axis=1))
        arc_px = 60.0 / res
        # A patch busier than the ring (a track fragment, a bump's shadow) is not
        # laid: its high-pass rms must stay under 1.5x the ring's median.
        hp_sq = ndimage.uniform_filter((hp - 1.0) ** 2, size=patch_px, mode="nearest")
        ring_rms = float(np.median(np.sqrt(hp_sq[core])))
        # A single pale stripe (a track) passes the rms test: a patch whose
        # high-pass runs over 1.12 or under 0.88 anywhere is not laid either.
        hp_max = ndimage.maximum_filter(hp, size=patch_px, mode="nearest")
        hp_min = ndimage.minimum_filter(hp, size=patch_px, mode="nearest")
        calm = (hp_max <= 1.12) & (hp_min >= 0.88)
        # Nor a patch holding a dark dot (a bush, a pole's shadow) over 2 m2: a
        # juniper quilted four times in a column is a juniper too many (0.8 of the
        # 30 m mean: 0.72 missed the junipers on the crest's dark ground).
        around = ndimage.uniform_filter(lum_w, size=max(3, int(30.0 / res)), mode="nearest")
        dot = ndimage.binary_opening(lum_w < 0.8 * around, iterations=1)
        calm &= ~ndimage.maximum_filter(dot, size=patch_px, mode="nearest")
        del around, dot
        # Nor a patch whose grain runs one way (a track fragment, a fence's shadow,
        # a row of bays): the structure tensor's coherence over the patch must stay
        # under 0.5, so nothing oriented is stamped in a row.
        gy_h = ndimage.gaussian_filter(hp, 1.0, order=(1, 0))
        gx_h = ndimage.gaussian_filter(hp, 1.0, order=(0, 1))
        jxx = ndimage.uniform_filter(gx_h * gx_h, size=patch_px, mode="nearest")
        jyy = ndimage.uniform_filter(gy_h * gy_h, size=patch_px, mode="nearest")
        jxy = ndimage.uniform_filter(gx_h * gy_h, size=patch_px, mode="nearest")
        coherence = np.sqrt((jxx - jyy) ** 2 + 4.0 * jxy * jxy) / np.maximum(jxx + jyy, 1e-9)
        calm &= coherence < 0.5
        del gy_h, gx_h, jxx, jyy, jxy, coherence
        good = calm & (np.sqrt(hp_sq) <= 1.5 * ring_rms)
        good_idx = np.nonzero(good[src_r, src_c])[0]
        # The nearest good sources, for an arc with none: still the ground beside
        # that side of the box, never a source drawn from the whole ring (a far
        # arc's pale plain quilted onto a wall clipped white).
        good_tree = (
            cKDTree(np.stack([src_r[good_idx], src_c[good_idx]], axis=1)) if good_idx.size else None
        )
        acc = np.zeros(window.shape[:2], dtype="float32")
        wsum = np.zeros(window.shape[:2], dtype="float32")
        ramp = np.linspace(0.0, 1.0, feather_px, endpoint=False)
        edge = np.ones(patch_px, dtype="float32")
        edge[:feather_px] = ramp
        edge[-feather_px:] = ramp[::-1]
        win2d = edge[:, None] * edge[None, :]
        rows_i, cols_i = np.nonzero(inside)
        # A source is not cut again within 10 m of a source already laid, and the
        # patch pitch is jittered +-4 m: patches cut in step from the nearest arc
        # stamped whatever that arc held in a row every 12 m.
        used = np.zeros(window.shape[:2], dtype=bool)
        reuse_px = max(2, int(10.0 / res))
        jitter_px = max(1, int(4.0 / res))
        step = max(2, patch_px - feather_px - jitter_px)
        for r_grid in range(rows_i.min() - patch_px, rows_i.max() + 1, step):
            for c_grid in range(cols_i.min() - patch_px, cols_i.max() + 1, step):
                r_start = r_grid + int(rng.integers(-jitter_px, jitter_px + 1))
                c_start = c_grid + int(rng.integers(-jitter_px, jitter_px + 1))
                r_a, c_a = max(0, r_start), max(0, c_start)
                r_b = min(window.shape[0], r_start + patch_px)
                c_b = min(window.shape[1], c_start + patch_px)
                if r_b <= r_a or c_b <= c_a or not inside[r_a:r_b, c_a:c_b].any():
                    continue
                centre = ((r_a + r_b) / 2.0, (c_a + c_b) / 2.0)
                nearest = int(tree.query(centre)[1])
                arc = tree.query_ball_point((src_r[nearest], src_c[nearest]), arc_px)
                arc = [int(a) for a in arc if good[src_r[a], src_c[a]]]
                if not arc and good_tree is not None:
                    near_k = min(20, good_idx.size)
                    _d, near_i = good_tree.query((src_r[nearest], src_c[nearest]), k=near_k)
                    arc = [int(good_idx[j]) for j in np.atleast_1d(near_i)]
                k = None
                for _try in range(16):
                    if not arc:
                        break
                    cand = arc[int(rng.integers(0, len(arc)))]
                    if not used[src_r[cand], src_c[cand]]:
                        k = cand
                        break
                if k is None:
                    k = arc[int(rng.integers(0, len(arc)))] if arc else nearest
                ur0, ur1 = max(0, int(src_r[k]) - reuse_px), int(src_r[k]) + reuse_px + 1
                uc0, uc1 = max(0, int(src_c[k]) - reuse_px), int(src_c[k]) + reuse_px + 1
                used[ur0:ur1, uc0:uc1] = True
                sr, sc = int(src_r[k]) - patch_px // 2, int(src_c[k]) - patch_px // 2
                sr = min(max(sr, 0), window.shape[0] - patch_px)
                sc = min(max(sc, 0), window.shape[1] - patch_px)
                tile = np.rot90(hp[sr : sr + patch_px, sc : sc + patch_px], int(rng.integers(0, 4)))
                w2 = win2d
                tile = tile[: r_b - r_start, : c_b - c_start]
                w2 = w2[: r_b - r_start, : c_b - c_start]
                tile = tile[r_a - r_start :, c_a - c_start :]
                w2 = w2[r_a - r_start :, c_a - c_start :]
                acc[r_a:r_b, c_a:c_b] += tile * w2
                wsum[r_a:r_b, c_a:c_b] += w2
        quilt = np.where(wsum > 1e-3, acc / np.maximum(wsum, 1e-3), 1.0)
    # The ring keeps its own grain: the feather blends only the low pass, and the
    # quilted grain inside meets the ring's at the edge (a grainless ring under
    # the feather was a seam).
    quilt = np.where(inside, quilt, hp)
    fill = fill * quilt[..., None]
    # The box's mean is the ring's mean, channel by channel (the pyramid's low
    # pass drifts a few per cent from it inside a wide box).
    ring_now = fill[band].reshape(-1, 3).mean(axis=0)
    inside_now = fill[inside].reshape(-1, 3).mean(axis=0)
    fill = fill * np.clip(ring_now / np.maximum(inside_now, 1e-3), 0.8, 1.25)[None, None, :]
    # Feather the fill over the ring's width at the box sides.
    dist = ndimage.distance_transform_edt(~inside) * res
    w = np.clip(1.0 - dist / ring, 0.0, 1.0).astype("float32")
    w = w * w * (3.0 - 2.0 * w)
    w = np.where(inside, 1.0, w)
    if keep_mask is not None:
        w = np.where(keep_mask[rr0:rr1, cc0:cc1], 0.0, w)
    out = colour_u8.astype("float32")
    out[rr0:rr1, cc0:cc1] = window * (1 - w[..., None]) + fill * w[..., None]
    return np.clip(out, 0, 255).astype("uint8")


def flatten_boxes(
    ground: np.ndarray,
    res: float,
    fp_size_m: float,
    boxes: list[dict],
    *,
    baseline: np.ndarray | None = None,
) -> tuple[np.ndarray, list[dict]]:
    """Authored boxes where a known compound is taken out of the ground.

    A visitor centre with its car parks, sheds and planted trees is a hundred metres
    of built ground; no blob rule tells it from a hummock, so the spec names the box
    (``center_xy``, ``size_m``). With ``use_baseline`` and a bare-earth ``baseline``
    (the 3DEP DTM, which has no buildings), the box takes the baseline's ground,
    feathered ``feather_m`` (20 m) at its edge, and the compound is gone whatever
    shape it had. Otherwise a wide opening (``open_m``) lowers what stands wholly
    inside the box by more than 0.3 m, feathered 6 m. Returns (ground, notes).
    """

    from scipy import ndimage

    n = ground.shape[0]
    half = fp_size_m / 2.0
    out = ground.copy()
    notes = []
    for box in boxes:
        cx, cy = box["center_xy"]
        size = float(box.get("size_m", 200.0))
        open_m = float(box.get("open_m", 100.0))
        c0 = int(max(0, (cx - size / 2 + half) / res))
        c1 = int(min(n, (cx + size / 2 + half) / res))
        r0 = int(max(0, (half - (cy + size / 2)) / res))
        r1 = int(min(n, (half - (cy - size / 2)) / res))
        if box.get("use_baseline") and baseline is not None:
            feather = float(box.get("feather_m", 20.0))
            pad = int(feather / res) + 2
            rr0, rr1 = max(0, r0 - pad), min(n, r1 + pad)
            cc0, cc1 = max(0, c0 - pad), min(n, c1 + pad)
            inside = np.zeros((rr1 - rr0, cc1 - cc0), dtype=bool)
            inside[r0 - rr0 : r1 - rr0, c0 - cc0 : c1 - cc0] = True
            dist = ndimage.distance_transform_edt(~inside) * res
            w = np.clip(1.0 - dist / feather, 0.0, 1.0).astype("float32")
            w = w * w * (3.0 - 2.0 * w)
            window = out[rr0:rr1, cc0:cc1]
            bare = baseline[rr0:rr1, cc0:cc1]
            bare = np.where(np.isfinite(bare), bare, window)
            lowered = np.clip(window - bare, 0, None)
            out[rr0:rr1, cc0:cc1] = window * (1 - w) + bare * w
            notes.append(
                {
                    "why": box.get("why", ""),
                    "center_xy": [cx, cy],
                    "size_m": size,
                    "source": "baseline",
                    "max_lowered_m": round(float(lowered[inside].max()), 2),
                    "volume_m3": round(float(lowered[inside].sum() * res * res), 1),
                }
            )
            continue
        pad = int(open_m / res) + 2
        rr0, rr1 = max(0, r0 - pad), min(n, r1 + pad)
        cc0, cc1 = max(0, c0 - pad), min(n, c1 + pad)
        window = out[rr0:rr1, cc0:cc1]
        opened = _coarse_opening(window, open_m / 2.0 / res)
        lowered = np.clip(window - opened, 0, None)
        inside = np.zeros_like(window, dtype=bool)
        inside[r0 - rr0 : r1 - rr0, c0 - cc0 : c1 - cc0] = True
        # Only what the opening lowers AND what sits wholly inside the box goes: a
        # crater rim or a hummock that runs on past the box edge is landscape, the
        # compound in the middle is not.
        raised = (lowered > 0.3) & inside
        labels, count = ndimage.label(raised)
        if count:
            edge = np.zeros_like(inside)
            edge[r0 - rr0, :] = edge[r1 - rr0 - 1, :] = True
            edge[:, c0 - cc0] = edge[:, c1 - cc0 - 1] = True
            touching = np.unique(labels[edge & raised])
            raised &= ~np.isin(labels, touching[touching > 0])
        dist = ndimage.distance_transform_edt(~raised) * res
        w = np.clip(1.0 - dist / 6.0, 0.0, 1.0).astype("float32")
        w = ndimage.gaussian_filter(w, 1.0)
        out[rr0:rr1, cc0:cc1] = window * (1 - w) + opened * w
        notes.append(
            {
                "why": box.get("why", ""),
                "center_xy": [cx, cy],
                "size_m": size,
                "open_m": open_m,
                "lowered_m3": round(float((lowered * (w > 0.5)).sum() * res * res), 1),
                "max_lowered_m": round(float((lowered * (w > 0.5)).max()), 2),
            }
        )
    return out, notes
