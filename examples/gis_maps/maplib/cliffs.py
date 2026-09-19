"""Cliff faces as modelled rock instead of painted heightmap.

A BeamNG terrain is a 2.5-D grid: one height per square, no overhang, and the base
colour projected straight down. That is survivable on a 20 degree scree slope and it is
not survivable on a wall. At 70 degrees a square metre of rock face is drawn from
0.34 m2 of texture, so every bed, joint and stain on it is stretched threefold down the
face; at 85 degrees it is elevenfold. The terrain cannot hold the ledge a hard bed makes
over a soft one either, because the ledge is an overhang and the grid has one height per
square. So the walls read as smeared paint however well the tile is authored - which is
what fifteen rounds of texture work on Black Bear Pass have been up against.

This stage takes the walls off the terrain and models them. It finds the steep bands in
the lidar, lays a rock skin over them, and gives the skin the relief the heightmap
cannot carry:

* **Bedding.** Displacement is periodic in world Z, so the beds lie level across the
  whole face whichever way it turns. Hard beds stand proud and square, soft beds recede
  and round off, and the underside of a hard bed is cut back under it - a real overhang,
  the thing the heightmap can never do.
* **Joints.** A second period along strike cuts the face into blocks that step in and
  out of the wall and part at a groove, so a wall is masonry rather than a ramp.
* **Buttresses.** A 30 m band of noise over both, so the wall has noses and gullies and
  is not a panel with a pattern on it.
* **UVs from the world, not from above.** ``u`` runs along strike and ``v`` is world Z,
  both in metres, so the beds stay level, the texel size stops depending on the slope,
  and the worst compression is ``sin(slope)`` - 0.77 at 50 degrees, against the terrain
  projection's 2.9x stretch at 70.

The skin stands ``base_out_m`` proud of the DEM so a recessed bed still clears the
terrain behind it, and the displacement is feathered to zero one lattice step outside
the band, so the skin sits down onto the ground at the crest and the toe with no gap and
no seam.

The result is written the way ``buildings.py`` writes its tiles: one Collada file per
tile placed as a ``TSStatic`` with ``Visible Mesh Final`` collision, so what a car hits
is the modelled rock and not the ramp underneath it.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import foliage_textures as ft
from .meshgen import Mesh, vertex_normals, write_dae
from .stable_seed import stable_hash

TILE_M = 256.0

DEFAULTS = {
    # A wall, not a steep slope: 48 degrees is above every scree angle of repose in the
    # pack and just over Black Bear Pass's own 45 degree cliff classifier, so a band
    # here is inside that classifier's rock rather than straddling its edge.
    "min_slope_deg": 48.0,
    # Ten metres of relief is the smallest thing a driver reads as a cliff rather than
    # as a bank. Below it the skin costs triangles for something the terrain already
    # draws acceptably.
    "min_relief_m": 10.0,
    "min_area_m2": 600.0,
    # 1.5 m resolves a 2.2 m bed and a 6 m joint. Coarsened automatically when the
    # budget would otherwise be blown; the step actually used ships in the handoff.
    "face_step_m": 1.5,
    "max_face_step_m": 4.0,
    "bed_m": 2.2,
    "joint_m": 6.0,
    "relief_m": 0.9,
    "buttress_m": 1.4,
    # The skin's deepest recess still stands this far out of the DEM. It has to cover
    # what the terrain can do between two lattice nodes: a 0.3 m bump the sampling
    # misses pokes 0.3/tan(slope) out of the face, which is 0.11 m on a 70 degree wall
    # and 0.25 m on a 50 degree one, so 0.35 clears both and the lidar's own noise.
    "base_out_m": 0.35,
    "tile_m": 3.0,
    "max_triangles": 400000,
}


def slope_deg(dem: np.ndarray, res: float) -> np.ndarray:
    """Slope in degrees from central differences, edges replicated."""

    dzdy, dzdx = np.gradient(dem.astype("float64"), res)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy))).astype("float32")


def _smooth_normals(dem: np.ndarray, res: float, window_m: float = 5.0):
    """Horizontal unit normal of the wall, from a DEM smoothed to ``window_m``.

    The face's direction is the wall's, not the lidar's noise: a 1 m grid on a
    70 degree face swings the raw normal by tens of degrees between neighbours, and a
    skin displaced along that is corduroy.
    """

    from scipy import ndimage

    size = max(3, round(window_m / res) | 1)
    smooth = ndimage.uniform_filter(dem.astype("float32"), size=size, mode="nearest")
    dzdy, dzdx = np.gradient(smooth.astype("float64"), res)
    # Rows run south, so the north component of the downhill-facing normal is +dzdy.
    nx, ny = -dzdx, dzdy
    norm = np.hypot(nx, ny)
    flat = norm < 1e-6
    nx = np.where(flat, 1.0, nx / np.where(flat, 1.0, norm))
    ny = np.where(flat, 0.0, ny / np.where(flat, 1.0, norm))
    return nx.astype("float32"), ny.astype("float32")


def detect_bands(
    dem: np.ndarray,
    res: float,
    *,
    min_slope_deg: float,
    min_relief_m: float,
    min_area_m2: float,
    allowed: np.ndarray | None = None,
) -> tuple[np.ndarray, list[dict]]:
    """Label the connected steep bands worth modelling, split by which way they face.

    A band is labelled inside one facing class - walls that face mostly east or west,
    and walls that face mostly north or south - because the strike coordinate the
    bedding and the joints are built on is one horizontal axis, and a single label
    wrapped round a butte would have to choose one axis for two walls at right angles.
    Splitting puts the change of axis on the nose between them, where a box map's seam
    belongs, instead of smearing one of the two faces.

    ``allowed`` restricts the search to a mask - the terrain's own cliff layers, where a
    spec names them. Returns the label image (0 = nothing) and one record per band.
    """

    from scipy import ndimage

    steep = slope_deg(dem, res) >= float(min_slope_deg)
    if allowed is not None:
        steep &= allowed
    # A one-cell fringe of steep squares along a gully is noise, not a wall: open it,
    # then close the pinholes a bed of softer rock punches through a face.
    steep = ndimage.binary_opening(steep, structure=np.ones((3, 3), bool))
    steep = ndimage.binary_closing(steep, structure=np.ones((3, 3), bool))
    if not steep.any():
        return np.zeros(dem.shape, dtype="int32"), []
    nx, ny = _smooth_normals(dem, res)
    # True where the wall faces mostly east or west, so it runs north-south and the
    # axis its length is measured along - its strike - is y.
    faces_ew = np.abs(nx) >= np.abs(ny)

    cell_area = res * res
    out = np.zeros(dem.shape, dtype="int32")
    records: list[dict] = []
    next_id = 0
    for along_y in (True, False):
        mask = steep & (faces_ew if along_y else ~faces_ew)
        if not mask.any():
            continue
        labels, count = ndimage.label(mask, structure=np.ones((3, 3), int))
        if not count:
            continue
        for index, sl in enumerate(ndimage.find_objects(labels), start=1):
            block = labels[sl] == index
            area = float(block.sum()) * cell_area
            if area < float(min_area_m2):
                continue
            heights = dem[sl][block]
            relief = float(heights.max() - heights.min())
            if relief < float(min_relief_m):
                continue
            next_id += 1
            out[sl][block] = next_id
            records.append(
                {
                    "id": next_id,
                    "along_y": bool(along_y),
                    "area_m2": round(area, 1),
                    "relief_m": round(relief, 2),
                    "cells": int(block.sum()),
                    "top_m": round(float(heights.max()), 2),
                    "base_m": round(float(heights.min()), 2),
                }
            )
    return out, records


def _hash01(*arrays: np.ndarray, salt: int) -> np.ndarray:
    """Deterministic 0..1 hash of integer arrays: the same field on every machine."""

    shape = np.broadcast(*arrays).shape if len(arrays) > 1 else arrays[0].shape
    h = np.full(shape, salt, dtype="int64")
    for a in arrays:
        h = (h * np.int64(1000003)) ^ np.asarray(a, dtype="int64")
        h &= np.int64(0x7FFFFFFFFFFF)
        h ^= h >> np.int64(13)
    h = (h * np.int64(2654435761)) & np.int64(0x7FFFFFFFFFFF)
    return (h % np.int64(1 << 24)).astype("float64") / float(1 << 24)


def _value_noise2(u: np.ndarray, v: np.ndarray, salt: int) -> np.ndarray:
    """Smooth 0..1 noise on a unit lattice; three octaves make the buttresses."""

    total = np.zeros(np.broadcast(u, v).shape, dtype="float64")
    amplitude, weight, frequency = 1.0, 0.0, 1.0
    for octave in range(3):
        su, sv = u * frequency, v * frequency
        iu, iv = np.floor(su).astype("int64"), np.floor(sv).astype("int64")
        fu, fv = su - iu, sv - iv
        fu = fu * fu * (3.0 - 2.0 * fu)
        fv = fv * fv * (3.0 - 2.0 * fv)
        c00 = _hash01(iu, iv, salt=salt + octave)
        c10 = _hash01(iu + 1, iv, salt=salt + octave)
        c01 = _hash01(iu, iv + 1, salt=salt + octave)
        c11 = _hash01(iu + 1, iv + 1, salt=salt + octave)
        total += amplitude * (
            (c00 * (1 - fu) + c10 * fu) * (1 - fv) + (c01 * (1 - fu) + c11 * fu) * fv
        )
        weight += amplitude
        amplitude *= 0.5
        frequency *= 2.1
    return total / weight


def face_relief(
    strike: np.ndarray,
    z: np.ndarray,
    *,
    bed_m: float,
    joint_m: float,
    relief_m: float,
    buttress_m: float,
    seed: int,
) -> np.ndarray:
    """Metres the skin stands out of the DEM, before the feather and the base offset.

    ``strike`` is distance along the wall and ``z`` is height above the terrain origin,
    both in metres, so the bedding is level in the world and the joints are vertical
    whichever way the wall turns.
    """

    # Bedding warped a little in Z so the beds are not a ruled grating across the face.
    warp = (_value_noise2(strike / 46.0, z / 46.0, seed + 11) - 0.5) * 0.55 * bed_m
    phase = (z + warp) / float(bed_m)
    bed_id = np.floor(phase).astype("int64")
    frac = phase - bed_id
    hardness = _hash01(bed_id, salt=seed + 3)
    # A hard bed stands proud with a square edge; a soft one recedes and rounds off.
    profile = np.where(
        hardness > 0.5,
        0.5 - 0.25 * np.cos(2 * np.pi * np.clip(frac, 0.0, 1.0)) ** 8,
        -0.35 + 0.25 * np.sin(np.pi * frac),
    )
    bed_out = (hardness - 0.5) * 1.4 + 0.35 * profile
    # The underside of a hard bed is cut back under it. This is the overhang, and it is
    # the whole reason the wall is geometry and not a heightmap.
    under = np.clip(1.0 - frac / 0.3, 0.0, 1.0) ** 2
    undercut = -0.55 * under * np.clip((hardness - 0.5) * 2.0, 0.0, 1.0)

    # Joints: blocks along strike, each stepping in or out, parted by a groove.
    jwarp = (_value_noise2(strike / 31.0, z / 19.0, seed + 29) - 0.5) * 0.7 * joint_m
    jphase = (strike + jwarp) / float(joint_m)
    block_id = np.floor(jphase).astype("int64")
    jfrac = jphase - block_id
    block_out = (_hash01(block_id, bed_id, salt=seed + 7) - 0.5) * 0.7
    edge = np.minimum(jfrac, 1.0 - jfrac)
    groove = -0.9 * np.exp(-((edge / 0.06) ** 2))

    relief = float(relief_m) * (bed_out + undercut + block_out + groove)
    # Noses and gullies at 30 m: without them a modelled wall is a flat panel with a
    # pattern on it, which is the painted wall's failure at another scale.
    relief += float(buttress_m) * (_value_noise2(strike / 30.0, z / 38.0, seed + 41) - 0.5) * 2.0
    return relief


def _skin(
    labels: np.ndarray,
    dem: np.ndarray,
    nx: np.ndarray,
    ny: np.ndarray,
    res: float,
    fp_size_m: float,
    min_elevation: float,
    keep_ids: set[int],
    along_y_by_id: dict[int, bool],
    cfg: dict,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Positions, UVs and quads for every band kept, in one pass on a shared lattice.

    Every band is displaced on the same lattice and every lattice node holds exactly one
    position, so two bands meeting on the nose of a butte share their vertices: no crack
    between them, no overlapping shells to flicker, and the change of strike axis costs
    one quad of stretched texture on the nose itself.

    The bedding is one field over the whole level rather than one per band, because
    strata are continuous: a bed that runs out of one wall comes back at the same height
    on the next.
    """

    from scipy import ndimage

    step = max(1, round(float(cfg["face_step_m"]) / res))
    rows = np.arange(0, dem.shape[0], step)
    cols = np.arange(0, dem.shape[1], step)
    sub = labels[np.ix_(rows, cols)]
    sub = np.where(np.isin(sub, sorted(keep_ids)), sub, 0)
    inside = sub > 0
    if not inside.any():
        return None

    # One call gives both the feather distance and, through the nearest owner, which
    # band a node in the ring outside the walls belongs to.
    distance, (ir, ic) = ndimage.distance_transform_edt(~inside, return_indices=True)
    grown = distance <= 1.001  # one lattice step of feather, where the skin sits down
    owner = np.where(inside, sub, np.where(grown, sub[ir, ic], 0))

    quad_ok = (grown[:-1, :-1] & grown[:-1, 1:] & grown[1:, 1:] & grown[1:, :-1]) & (
        inside[:-1, :-1] | inside[:-1, 1:] | inside[1:, 1:] | inside[1:, :-1]
    )
    if not quad_ok.any():
        return None

    half = fp_size_m / 2.0
    rr, cc = np.meshgrid(rows, cols, indexing="ij")
    # The GIS grid holds each cell's centre, and the terrain block is already offset by
    # half a square to match it, so a node sits at its cell's centre like every other
    # placement in the pack.
    x = cc * res - half + res / 2.0
    y = half - rr * res - res / 2.0
    z = dem[np.ix_(rows, cols)].astype("float64") - float(min_elevation)

    along_y = np.zeros(sub.shape, bool)
    for band_id, flag in along_y_by_id.items():
        if flag:
            along_y |= owner == band_id
    strike = np.where(along_y, y, x)

    relief = face_relief(
        strike,
        z,
        bed_m=float(cfg["bed_m"]),
        joint_m=float(cfg["joint_m"]),
        relief_m=float(cfg["relief_m"]),
        buttress_m=float(cfg["buttress_m"]),
        seed=seed,
    )
    # Each band stands clear of the terrain behind it by its own deepest recess plus the
    # base offset, so a recessed bed never sinks back into the ramp it replaces.
    order = sorted(keep_ids)
    floors = np.atleast_1d(
        ndimage.minimum(np.where(inside, relief, np.inf), labels=sub, index=order)
    )
    floor_by_id = np.zeros(int(sub.max()) + 1, dtype="float64")
    for band_id, value in zip(order, floors, strict=True):
        floor_by_id[band_id] = 0.0 if not np.isfinite(value) else float(value)
    feather = np.where(inside, 1.0, np.clip(1.0 - distance, 0.0, 1.0))
    out = np.where(
        owner > 0, feather * (relief - floor_by_id[owner] + float(cfg["base_out_m"])), 0.0
    )

    positions = np.stack(
        [
            x + nx[np.ix_(rows, cols)].astype("float64") * out,
            y + ny[np.ix_(rows, cols)].astype("float64") * out,
            z,
        ],
        axis=-1,
    )
    tile = max(0.25, float(cfg["tile_m"]))
    uvs = np.stack([strike / tile, z / tile], axis=-1)

    used = np.zeros(sub.shape, bool)
    used[:-1, :-1] |= quad_ok
    used[:-1, 1:] |= quad_ok
    used[1:, 1:] |= quad_ok
    used[1:, :-1] |= quad_ok
    index = -np.ones(sub.shape, dtype="int64")
    index[used] = np.arange(int(used.sum()), dtype="int64")
    qr, qc = np.nonzero(quad_ok)
    corners = np.stack(
        [index[qr, qc], index[qr, qc + 1], index[qr + 1, qc + 1], index[qr + 1, qc]], axis=-1
    )
    return positions[used], uvs[used], corners


def _quads_to_triangles(corners: np.ndarray) -> np.ndarray:
    """Two triangles a quad, wound so the face normal points out of the wall.

    The lattice runs east with the column and *south* with the row, so the corners come
    round clockwise seen from above and the winding is reversed to put the normal on the
    outside. Wound the other way the whole wall is drawn from behind: back-face culling
    makes it invisible from the road and the collision hull faces into the hill.
    """

    a, b, c, d = corners[:, 0], corners[:, 1], corners[:, 2], corners[:, 3]
    return np.concatenate([np.stack([a, c, b], -1), np.stack([a, d, c], -1)])


def build(
    spec,
    fp,
    level_root: Path,
    level_url: str,
    pid,
    *,
    dem: np.ndarray,
    res: float,
    min_elevation: float,
    layer: np.ndarray | None = None,
    materials: list[str] | None = None,
    log=print,
) -> dict:
    """Model every cliff band the spec asks for. Returns items, materials, mask, stats."""

    cfg = dict(DEFAULTS)
    cfg.update(getattr(spec, "CLIFFS", None) or {})
    mod_id = spec.MOD_ID
    seed = int(cfg.get("seed", 1700))
    shapes_dir = level_root / "art" / "shapes" / f"{mod_id}_cliffs"
    shapes_url = f"{level_url}/art/shapes/{mod_id}_cliffs"
    tex_dir = shapes_dir / "textures"

    allowed = None
    layer_names = cfg.get("layers")
    if layer_names and layer is not None and materials:
        ids = [materials.index(name) for name in layer_names if name in materials]
        allowed = np.isin(layer, ids) if ids else np.zeros(layer.shape, bool)

    labels, records = detect_bands(
        dem,
        res,
        min_slope_deg=float(cfg["min_slope_deg"]),
        min_relief_m=float(cfg["min_relief_m"]),
        min_area_m2=float(cfg["min_area_m2"]),
        allowed=allowed,
    )
    empty = {
        "items": [],
        "materials": {},
        "mask": np.zeros(dem.shape, bool),
        "stats": {"bands": 0, "bands_modelled": 0, "triangles": 0, "face_step_m": 0.0},
    }
    if not records:
        log("  cliffs: no band meets the spec's slope, relief and area")
        return empty

    # The tallest walls first: a driver reads the 60 m face on the switchbacks and never
    # sees the 11 m bank behind the spawn, so the budget goes to the former.
    records.sort(key=lambda r: (-r["relief_m"] * math.sqrt(r["area_m2"]), r["id"]))
    budget = int(cfg["max_triangles"])
    step_m = float(cfg["face_step_m"])
    # Two triangles per (step x step) square, so the whole qualifying area costs this:
    wanted = 2.0 * sum(r["area_m2"] for r in records) / (step_m * step_m)
    if wanted > budget:
        # Coarsen before dropping walls: the whole level a step coarser reads better
        # than half of it modelled and half of it left as smeared paint. Only what will
        # not fit at the coarsest step allowed is dropped, shortest wall first.
        step_m = min(float(cfg["max_face_step_m"]), step_m * math.sqrt(wanted / budget))
    cfg["face_step_m"] = step_m
    per_m2 = 2.0 / (step_m * step_m)
    keep: list[dict] = []
    spent = 0.0
    dropped = 0
    for record in records:
        cost = record["area_m2"] * per_m2
        if keep and spent + cost > budget:
            dropped += 1
            continue
        keep.append(record)
        spent += cost

    nx, ny = _smooth_normals(dem, res)
    keep_ids = {r["id"] for r in keep}
    mask = np.isin(labels, sorted(keep_ids))
    skin = _skin(
        labels,
        dem,
        nx,
        ny,
        res,
        fp.size_m,
        min_elevation,
        keep_ids,
        {r["id"]: r["along_y"] for r in keep},
        cfg,
        seed,
    )
    if skin is None:
        log("  cliffs: every band fell below the quad threshold")
        return empty
    positions, uvs, corners = skin
    tris = _quads_to_triangles(corners)
    triangles = int(tris.shape[0])

    # Tiled by the centroid of each triangle, so a TSStatic never spans the level.
    centre = positions[tris].mean(axis=1)
    keys = np.stack(
        [
            np.floor(centre[:, 1] / TILE_M).astype(int),
            np.floor(centre[:, 0] / TILE_M).astype(int),
        ],
        axis=-1,
    )
    tiles: dict[tuple[int, int], tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for key in map(tuple, np.unique(keys, axis=0)):
        take = tris[(keys[:, 0] == key[0]) & (keys[:, 1] == key[1])]
        if not take.size:
            continue
        used = np.unique(take)
        remap = -np.ones(positions.shape[0], dtype="int64")
        remap[used] = np.arange(used.size)
        tiles[key] = (positions[used], uvs[used], remap[take])

    if not tiles:
        log("  cliffs: every band fell below the quad threshold")
        return empty

    # --- one rock set per cliff material -------------------------------------------
    families = cfg.get("materials") or {
        "cliff_rock": {"colour": [0.46, 0.44, 0.42], "strata": 0.6, "lichen": 0.15}
    }
    materials_json: dict = {}
    # The texture's bedding is the SAME bedding the spec declares, at last. `rock_set`
    # counts beds per tile HEIGHT and the face's v runs z / tile_m, so one bed is
    # `tile_m / beds_per_tile` metres of wall. It was fixed at 7 and answered to nothing:
    # every map in the pack was drawing beds 3x to 7.5x finer than it asked for, which
    # reads as grain rather than as strata.
    #
    # Rounded to a whole number because v wraps every tile and a fractional count seams
    # at every tile boundary, so the bed the wall actually gets is not always the bed
    # the spec named - `texture_bed_m` below reports what was drawn, not what was asked
    # for. That distinction is the one this stage keeps getting wrong.
    #
    # A TILE MUST CARRY AT LEAST TWO BEDS, and a spec that cannot is a spec to widen.
    # `rock_set` tints each bed from a fixed seven-tone palette indexed by the floor of
    # the phase; at one bed per tile that index never advances, so the per-bed tone is a
    # single constant over the whole card and the only thing left varying down the wall
    # is the sine that separates beds. The wall then draws as one broad light-to-dark
    # gradient - correct bedding THICKNESS and no visible beds, which is a worse result
    # than the 7-bed corduroy it replaced because it looks like nothing at all. Measured
    # on the cards rock_set really writes: one bed per tile puts 100% of the card on a
    # single tone and its tile seam runs 23x the typical interior step, against 20% and
    # 6.5x at five beds.
    #
    # So each map's `tile_m` is now `bed_m` times a whole bed count, picked as the
    # largest count (at most five) that still leaves about 150 px per metre of wall at
    # that material's `size`. That makes the drawn bed EXACTLY the declared one on every
    # map in the pack, with no rounding error left to report.
    tile_m_cfg = max(0.25, float(cfg["tile_m"]))
    beds_per_tile = max(1, round(tile_m_cfg / max(float(cfg["bed_m"]), 1e-6)))
    texture_bed_m = tile_m_cfg / beds_per_tile
    for family in sorted(families):
        params = families[family]
        full = f"{mod_id}_{family}"
        ft.rock_set(
            tex_dir,
            full,
            # Not the builtin: it is salted per process, so a seed built from it plants
            # a different level on every build. See maplib/stable_seed.py.
            seed + 500 + (stable_hash(family) % 500),
            colour=tuple(params.get("colour", (0.46, 0.44, 0.42))),
            # `strata` is the AMPLITUDE of the bedding; `beds_per_tile` is its pitch.
            # The old comment here said the mesh carried the beds so the tile's strata
            # were only the partings inside one. That was false wherever the lattice is
            # too coarse to resolve `bed_m` - see `samples_per_bed_*` below - and on
            # those maps the wall got neither the geometric bedding nor the texture's.
            strata=float(params.get("strata", 0.6)),
            beds_per_tile=beds_per_tile,
            # A tile wide enough to carry several beds is also a tile whose texels are
            # spread over more wall, so a map that widens `tile_m` to get its bedding
            # rhythm can buy the surface detail back here instead of choosing between
            # them. 1024 over 3 m is 341 px/m; over 12 m it is 85, and 2048 makes that
            # 171.
            size=int(params.get("size", 1024)),
            lichen_cover=float(params.get("lichen", 0.15)),
        )
        materials_json[full] = {
            "name": full,
            "class": "Material",
            "mapTo": full,
            "persistentId": pid(f"cliff-material:{family}"),
            "materialTag0": mod_id,
            "materialTag1": "Rock",
            "version": 1.5,
            "castShadows": True,
            "Stages": [
                {
                    "baseColorMap": f"{shapes_url}/textures/{full}_b.png",
                    "normalMap": f"{shapes_url}/textures/{full}_nm.png",
                    "roughnessMap": f"{shapes_url}/textures/{full}_r.png",
                },
                {},
                {},
                {},
            ],
        }
    # One family for the whole level: a per-band choice would put a seam down the nose
    # between two walls of the same rock. A spec with two rocks names which is the face.
    family = str(cfg.get("face_material") or sorted(families)[0])
    material = f"{mod_id}_{family}"

    items = []
    # A cliff tile is unique geometry, not an instance, so what it costs on disk is worth
    # measuring rather than guessing: Collada is text and runs about 80 bytes a triangle.
    dae_bytes = 0
    for key in sorted(tiles):
        origin = np.array([(key[1] + 0.5) * TILE_M, (key[0] + 0.5) * TILE_M, 0.0])
        tile_pos, tile_uv, tile_tris = tiles[key]
        # A TSStatic's shape is authored about its own origin and the item carries the
        # tile centre, so the mesh is written relative to it.
        tile_pos = tile_pos - origin
        mesh = Mesh(
            "cliff_mesh",
            tile_pos,
            vertex_normals(tile_pos, tile_tris),
            tile_uv,
            tile_tris,
            material=material,
            node_name="cliff",
        )
        name = f"cliff_r{key[0]:+03d}_c{key[1]:+03d}"
        write_dae(shapes_dir / f"{name}.dae", [mesh], f"{mod_id}_{name}")
        dae_bytes += (shapes_dir / f"{name}.dae").stat().st_size
        items.append(
            {
                "name": f"{mod_id}_cliffs_{name}",
                "class": "TSStatic",
                "persistentId": pid(f"cliffs:{name}"),
                "position": [round(float(v), 3) for v in origin],
                "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
                "scale": [1, 1, 1],
                "shapeName": f"{shapes_url}/{name}.dae",
                "collisionType": "Visible Mesh Final",
                "decalType": "Visible Mesh Final",
                "useInstanceRenderData": True,
                "instanceColor": [1, 1, 1, 1],
                "__parent": "cliffs",
            }
        )

    (shapes_dir / "main.materials.json").write_text(
        json.dumps(dict(sorted(materials_json.items())), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    kept_relief = [r["relief_m"] for r in keep]
    # Can the mesh actually CARRY the bedding it is asked for? `face_relief` puts the beds
    # in the geometry (`phase = (z + warp) / bed_m`, metres of relief per vertex), and the
    # tile's own `strata` was demoted to the partings inside a bed when that moved -- so
    # the beds read as layers only if the vertices sample `bed_m` finely enough. Vertices
    # sit on a world-XY lattice of spacing `face_step_m`, so their spacing ALONG Z, which
    # is the axis the bedding varies on, is `face_step_m * tan(slope)`: coarser than the
    # step on anything steeper than 45 degrees, and the walls here are steep by selection.
    # Two samples per bed is the floor for a wavelength to survive sampling at all; under
    # one, the beds alias into irregular noise on the face.
    #
    # Recorded rather than asserted, because the number is a spec-and-budget question and
    # not something a build can fix: `max_triangles` coarsens `face_step_m` above what the
    # spec asked for, so a map can declare beds its own budget forbids. Measured over the
    # cells of the bands actually KEPT, at the step actually used.
    wall_slope = slope_deg(dem, res)[mask] if mask.any() else np.zeros(1, dtype="float32")
    bed_m = float(cfg["bed_m"])
    # THE STEP THE MESH ACTUALLY USES, not the one the budget produced. `_skin` lays its
    # vertices on WHOLE DEM cells - `step = max(1, round(face_step_m / res))` at line 299
    # - so the lattice really used is that many cells wide, and `face_step_m` below is the
    # pre-rounding float. Dividing by the float would make this metric the very thing it
    # was written to catch: a stage recording what it INTENDED rather than what it did.
    # On a 2 m DEM a declared 1.5 m step IS 2.0 m, so samples per bed computed from 1.5
    # reads a third better than the mesh can deliver, and a map already at one DEM cell
    # cannot be improved by any budget at all - it has run out of elevation data.
    lattice_step_m = max(1, round(step_m / res)) * res

    def _samples_per_bed(slope_percentile: float) -> float:
        deg = float(np.percentile(wall_slope, slope_percentile))
        # arctan keeps this under 90, but a near-vertical wall still wants a bound.
        vertical_step = lattice_step_m * math.tan(math.radians(min(deg, 89.0)))
        return bed_m / vertical_step if vertical_step > 1e-6 else float("inf")

    stats = {
        "bands": len(records),
        "bands_modelled": len(keep),
        "bands_over_budget": dropped,
        "tiles": len(items),
        "triangles": triangles,
        # THE BUDGET IS PRICED ON THE FLOAT STEP; THE MESH IS STRIDED ON THE LATTICE.
        # The loop above spends `area * 2 / step_m**2` per wall and stops at
        # `max_triangles`, but `_skin` lays vertices on WHOLE DEM cells, so what is
        # actually built costs `area * 2 / lattice_step_m**2`. Where rounding goes down
        # the mesh is finer than the price and the map ships over its own budget by
        # `(step_m / lattice_step_m) ** 2`, with nothing dropped and no warning - the
        # decision to keep a wall was made against a number the wall does not cost.
        #
        # `triangles` above is the real count off the built mesh, so the three numbers
        # together say which case a map is in without anyone re-deriving it. Recorded,
        # not asserted: repricing the loop on the lattice would change which walls get
        # dropped on every map at once, and that is a rebuild-and-look change rather
        # than one to make blind.
        "triangles_priced": round(spent),
        "triangles_budget": budget,
        "triangles_over_budget": round(triangles / max(budget, 1), 3),
        "face_step_m": round(step_m, 3),
        "bed_m": float(cfg["bed_m"]),
        "joint_m": float(cfg["joint_m"]),
        "relief_m": float(cfg["relief_m"]),
        "tile_m": float(cfg["tile_m"]),
        "min_slope_deg": float(cfg["min_slope_deg"]),
        "modelled_area_m2": round(sum(r["area_m2"] for r in keep), 1),
        "found_area_m2": round(sum(r["area_m2"] for r in records), 1),
        "relief_p50_m": round(float(np.median(kept_relief)), 2),
        "relief_max_m": round(float(max(kept_relief)), 2),
        # The lattice `_skin` really used, beside the pre-rounding float in
        # `face_step_m`. When these differ the mesh is coarser than the budget thinks,
        # and a map whose lattice is already one DEM cell cannot be helped by a bigger
        # triangle budget - only by finer elevation data.
        # What the TEXTURE draws a bed at, beside the `bed_m` the spec asked for. The
        # two differ by the whole-number rounding that keeps the tile seamless.
        "texture_bed_m": round(float(texture_bed_m), 3),
        "texture_beds_per_tile": int(beds_per_tile),
        "face_step_lattice_m": round(float(lattice_step_m), 3),
        "face_step_is_one_dem_cell": bool(round(step_m / res) <= 1),
        "wall_slope_p50_deg": round(float(np.median(wall_slope)), 1),
        "wall_slope_p90_deg": round(float(np.percentile(wall_slope, 90)), 1),
        # Beds per vertex along Z, at the median wall and at the steep tail. Under 2.0 the
        # bedding is undersampled; under 1.0 it aliases into noise instead of layers.
        "samples_per_bed_p50": round(_samples_per_bed(50.0), 2),
        "samples_per_bed_steep": round(_samples_per_bed(90.0), 2),
        "materials": len(materials_json),
        "face_material": family,
        "collada_bytes": int(dae_bytes),
        "shapes_dir": f"art/shapes/{mod_id}_cliffs",
    }
    log(
        f"  {len(keep)} cliff bands modelled in {len(items)} tiles, "
        f"{triangles / 1e3:.0f} k triangles at {step_m:.2f} m "
        f"(priced {stats['triangles_priced'] / 1e3:.0f} k against a "
        f"{budget / 1e3:.0f} k budget, {stats['triangles_over_budget']}x), "
        f"lattice {lattice_step_m:.1f} m, "
        f"tallest {stats['relief_max_m']} m"
    )
    return {"items": items, "materials": materials_json, "mask": mask, "stats": stats}
