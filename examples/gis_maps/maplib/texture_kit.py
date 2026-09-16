"""Deterministic, tileable PBR texture sets for terrain materials.

The giant props pack seeds every material by name; this does the same by ``seed`` so
a rebuild on any machine writes pixel-identical maps. Everything is periodic gradient
noise and periodic Worley (cell) noise composed in numpy: no external assets, no
licences to carry.

Each family writes five maps at ``size`` px, named the way BeamNG's v1.5 terrain
materials expect them: ``<name>_b.png`` (base colour, sRGB), ``<name>_nm.png``
(tangent normal), ``<name>_r.png`` (roughness), ``<name>_h.png`` (height) and
``<name>_ao.png`` (ambient occlusion).

Families are named for what they are on the ground. A rock family is built from
cells (each block or cobble is one Worley cell with its own height and tint and a
crack where it meets the next), bedded rock from bands of random thickness, shale
from small plates and downslope streaks, tundra from tussocks, roads from ruts.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

FAMILIES = {
    # name: base frequency (fbm lattice cells across the tile), octaves, roughness,
    # height gain, the feature function, and whether cells carry their own tint.
    "desert_floor": {"freq": 6, "octaves": 5, "rough": 0.86, "gain": 0.55, "feature": "pebbles"},
    "gravel": {"freq": 10, "octaves": 5, "rough": 0.82, "gain": 0.9, "feature": "pebbles"},
    "rock_strata": {"freq": 3, "octaves": 6, "rough": 0.72, "gain": 1.0, "feature": "strata"},
    "scree": {"freq": 12, "octaves": 5, "rough": 0.78, "gain": 1.0, "feature": "blocks"},
    "dry_grass": {"freq": 8, "octaves": 5, "rough": 0.90, "gain": 0.5, "feature": "tufts"},
    "clay_pan": {"freq": 4, "octaves": 4, "rough": 0.70, "gain": 0.35, "feature": "cracks"},
    "shale": {"freq": 7, "octaves": 6, "rough": 0.76, "gain": 0.8, "feature": "rills"},
    "volcanic_ash": {"freq": 5, "octaves": 5, "rough": 0.92, "gain": 0.45, "feature": "pebbles"},
    "snow": {"freq": 3, "octaves": 4, "rough": 0.35, "gain": 0.3, "feature": "none"},
    # Alpine tundra in the photographs: grey-tan rubble with olive turf, the turf
    # darker than the ground between (cushions 0.39, bare ground 0.46, straw 0.55).
    "alpine_tundra": {
        "freq": 9,
        "octaves": 5,
        "rough": 0.88,
        "gain": 1.2,
        "feature": "tufts",
        "cushion_rgb": [0.38, 0.40, 0.22],
        "ground_rgb": [0.53, 0.51, 0.44],
        "straw_rgb": [0.60, 0.55, 0.36],
        "shade_by_height": 0.25,
        "cushion_profile": 0.6,  # a soft rim, not a sticker's wall
    },
    # Still water: a flat dark tile with a faint ripple, for the cells under a lake.
    "water": {"freq": 3, "octaves": 3, "rough": 0.15, "gain": 0.08, "feature": "none"},
    "macro_clumpy": {"freq": 4, "octaves": 4, "rough": 0.80, "gain": 0.4, "feature": "none"},
    # Texture-pass families (Meteor Crater / Black Bear Pass rework).
    "limestone": {"freq": 3, "octaves": 6, "rough": 0.70, "gain": 1.1, "feature": "ledges"},
    "talus_blocks": {"freq": 8, "octaves": 5, "rough": 0.80, "gain": 1.0, "feature": "boulders"},
    # The Moenkopi crest: red-brown blocks on tan-grey dust with cream Kaibab pieces.
    "rim_rubble": {
        "freq": 8,
        "octaves": 5,
        "rough": 0.80,
        "gain": 1.0,
        "feature": "boulders",
        "pale_share": 0.25,
        "pale_rgb": [0.78, 0.72, 0.62],
        "matrix_rgb": [0.62, 0.56, 0.48],
    },
    # Ejecta: cream-grey Kaibab chunks (an absolute tone, not the soil's) domed
    # in the height map, on rust-brown soil.
    "ejecta": {
        "freq": 7,
        "octaves": 5,
        "rough": 0.84,
        "gain": 0.8,
        "feature": "cobbles",
        "chunk_rgb": [0.50, 0.47, 0.41],
        "shade_by_height": 0.5,
    },
    # The decal: a 0.4 m tan shoulder inside the soft edge and wheel-track wear at
    # 18 %; the slab is the base (the tone is set by the median, not a mean the
    # shoulder would lift). The terrain bed under it carries no shoulder.
    "asphalt": {
        "freq": 12,
        "octaves": 4,
        "rough": 0.72,
        "gain": 0.25,
        "feature": "asphalt",
        "shoulder_rgb": [0.56, 0.49, 0.39],
        "shoulder_span": [0.03, 0.10],
        "wear_contrast": 0.30,
        "tone_by": "median",
    },
    "asphalt_bed": {
        "freq": 12,
        "octaves": 4,
        "rough": 0.72,
        "gain": 0.25,
        "feature": "asphalt",
        "shoulder": False,
        "wear_contrast": 0.18,
    },
    # A desert two-track: the ruts are the palest part (dust-polished), so the
    # tile is barely shaded by its height and the ruts carry a +10 % tint.
    "dirt_track": {
        "freq": 8,
        "octaves": 5,
        "rough": 0.88,
        "gain": 0.6,
        "feature": "ruts",
        "shade_by_height": 0.15,
        "rut_tint": 0.35,
    },
    "gravel_track": {
        "freq": 10,
        "octaves": 5,
        "rough": 0.84,
        "gain": 0.8,
        "feature": "ruts_gravel",
    },
    # Road beds under the decals: terrain materials tile in world space, so the bed
    # itself is isotropic compacted gravel or dirt; the ruts live on the decal.
    "gravel_bed": {"freq": 10, "octaves": 5, "rough": 0.84, "gain": 0.8, "feature": "gravel"},
    "dirt_bed": {"freq": 8, "octaves": 5, "rough": 0.9, "gain": 0.35, "feature": "pebbles"},
    "shale_plates": {"freq": 6, "octaves": 5, "rough": 0.78, "gain": 1.6, "feature": "shale"},
    "cliff_beds": {"freq": 3, "octaves": 6, "rough": 0.74, "gain": 1.0, "feature": "cliff"},
    "tussock": {"freq": 9, "octaves": 5, "rough": 0.90, "gain": 0.7, "feature": "tussocks"},
    "dark_strata": {"freq": 3, "octaves": 6, "rough": 0.72, "gain": 1.0, "feature": "dark_strata"},
    "forest_floor": {"freq": 7, "octaves": 5, "rough": 0.92, "gain": 0.9, "feature": "duff"},
}


# ---------------------------------------------------------------------------
# Noise primitives (all periodic over the tile)
# ---------------------------------------------------------------------------


def _tileable_noise(size: int, period, rng: np.random.Generator) -> np.ndarray:
    """Periodic gradient (Perlin-style) noise; ``period`` lattice cells across the tile.

    ``period`` may be an int or an (x, y) pair for anisotropic (streaked) noise.
    """

    px, py = (period, period) if isinstance(period, int | float) else period
    px, py = max(1, int(px)), max(1, int(py))
    angles = rng.uniform(0.0, 2.0 * np.pi, size=(py, px))
    gx = np.cos(angles)
    gy = np.sin(angles)
    cx = np.arange(size, dtype="float64") * px / size
    cy = np.arange(size, dtype="float64") * py / size
    xi = np.floor(cx).astype(int) % px
    yi = np.floor(cy).astype(int) % py
    xf = cx - np.floor(cx)
    yf = cy - np.floor(cy)
    xi1 = (xi + 1) % px
    yi1 = (yi + 1) % py

    def fade(t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    u = fade(xf)[None, :]
    v = fade(yf)[:, None]
    X, Y = np.meshgrid(xf, yf)
    n00 = gx[yi[:, None], xi[None, :]] * X + gy[yi[:, None], xi[None, :]] * Y
    n10 = gx[yi[:, None], xi1[None, :]] * (X - 1) + gy[yi[:, None], xi1[None, :]] * Y
    n01 = gx[yi1[:, None], xi[None, :]] * X + gy[yi1[:, None], xi[None, :]] * (Y - 1)
    n11 = gx[yi1[:, None], xi1[None, :]] * (X - 1) + gy[yi1[:, None], xi1[None, :]] * (Y - 1)
    nx0 = n00 * (1 - u) + n10 * u
    nx1 = n01 * (1 - u) + n11 * u
    return (nx0 * (1 - v) + nx1 * v) * 1.4142


def fbm(
    size: int, base_period, octaves: int, rng: np.random.Generator, persistence: float = 0.5
) -> np.ndarray:
    total = np.zeros((size, size))
    amplitude = 1.0
    norm = 0.0
    for octave in range(octaves):
        if isinstance(base_period, int | float):
            period = base_period * (2**octave)
        else:
            period = (base_period[0] * (2**octave), base_period[1] * (2**octave))
        total += amplitude * _tileable_noise(size, period, rng)
        norm += amplitude
        amplitude *= persistence
    return total / norm


def worley(
    size: int,
    cells,
    rng: np.random.Generator,
    jitter: float = 0.85,
    warp: float = 0.0,
    return_offset: bool = False,
):
    """Periodic Worley noise: (F1, F2, cell_id) with distances in cell units.

    With ``return_offset`` a fourth item, the (dx, dy) offset from the nearest feature
    point in cell units, lets a caller give every cell its own tilted plane.

    ``cells`` may be an int or an (x, y) pair for elongated cells. F1 is the distance to
    the nearest feature point, F2 to the second nearest; ``F2 - F1`` is small on cell
    boundaries (cracks) and ``cell_id`` picks a per-cell random value.
    """

    cx, cy = (cells, cells) if isinstance(cells, int | float) else cells
    cx, cy = max(1, int(cx)), max(1, int(cy))
    offsets = rng.uniform(0.5 - jitter / 2, 0.5 + jitter / 2, size=(cy, cx, 2))
    ids = rng.integers(0, 1 << 30, size=(cy, cx))
    px = np.arange(size, dtype="float64") * cx / size
    py = np.arange(size, dtype="float64") * cy / size
    X, Y = np.meshgrid(px, py)
    if warp > 0:
        # Periodic domain warp: straight cell edges become the outlines of real blocks.
        X = X + warp * fbm(size, 4, 2, rng)
        Y = Y + warp * fbm(size, 4, 2, rng)
    ix = np.floor(X).astype(int)
    iy = np.floor(Y).astype(int)
    f1 = np.full((size, size), np.inf)
    f2 = np.full((size, size), np.inf)
    best = np.zeros((size, size), dtype="int64")
    ox = np.zeros((size, size))
    oy = np.zeros((size, size))
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            nx = (ix + dx) % cx
            ny = (iy + dy) % cy
            fx = ix + dx + offsets[ny, nx, 0]
            fy = iy + dy + offsets[ny, nx, 1]
            d = np.hypot(X - fx, Y - fy)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            best = np.where(closer, ids[ny, nx], best)
            ox = np.where(closer, X - fx, ox)
            oy = np.where(closer, Y - fy, oy)
            f1 = np.where(closer, d, f1)
    if return_offset:
        return f1, f2, best, (ox, oy)
    return f1, f2, best


def _cell_value(cell_id: np.ndarray, salt: int) -> np.ndarray:
    """Deterministic 0..1 per cell id."""

    h = (cell_id.astype(np.int64) * 2654435761 + salt * 97) & 0x7FFFFFFF
    h = (h ^ (h >> 15)) * 1274126177 & 0x7FFFFFFF
    return ((h ^ (h >> 13)) & 0xFFFFFF) / float(0xFFFFFF)


def _smooth(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------
# Features: height detail in -1..1 (and an optional per-pixel tint multiplier)
# ---------------------------------------------------------------------------


def _block_pile(
    size: int,
    rng: np.random.Generator,
    count: int,
    radius_range: tuple[float, float],
    amplitude: float,
    salt: int,
    *,
    elongation: tuple[float, float] = (1.0, 1.0),
    tilt: float = 0.9,
    facet: float = 0.3,
    bevel: float = 0.06,
) -> tuple[np.ndarray, np.ndarray]:
    """Drop ``count`` convex blocks on a periodic tile; nearest top wins.

    Each block's top is two facets meeting at a ridge (``facet`` is the drop across the
    block at its ends, in amplitudes) on top of its own tilt, and its edges are
    chamfered over the outer ``bevel`` of the radius so no block has a razor rim.
    Returns (height, owner): height is -inf where no block landed, owner the block id
    (``salt`` + index) so a caller can tint each block on its own.
    """

    height = np.full((size, size), -np.inf)
    owner = np.full((size, size), -1, dtype="int64")
    lo, hi = radius_range
    for i in range(count):
        cx, cy = rng.uniform(0, 1, 2)
        r = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
        w = int(r * 1.15 * max(elongation) * size) + 1
        rows = (np.arange(-w, w + 1) + round(cy * size)) % size
        cols = (np.arange(-w, w + 1) + round(cx * size)) % size
        dy = (np.arange(-w, w + 1) + round(cy * size)) / size - cy
        dx = (np.arange(-w, w + 1) + round(cx * size)) / size - cx
        DX, DY = np.meshgrid(dx, dy)
        # An elongated block: squeeze one axis at a random heading (chips, twigs).
        stretch = float(np.exp(rng.uniform(np.log(elongation[0]), np.log(elongation[1]))))
        heading = rng.uniform(0, np.pi)
        ax = (DX * np.cos(heading) + DY * np.sin(heading)) / stretch
        ay = -DX * np.sin(heading) + DY * np.cos(heading)
        inside = np.ones(DX.shape, dtype=bool)
        margin = np.full(DX.shape, np.inf)
        for angle in np.sort(rng.uniform(0, 2 * np.pi, int(rng.integers(5, 8)))):
            proj = ax * np.cos(angle) + ay * np.sin(angle)
            limit = r * rng.uniform(0.7, 1.0)
            inside &= proj <= limit
            margin = np.minimum(margin, limit - proj)
        # Bigger blocks stand taller, every block has its own tilt.
        top = (rng.uniform(0.25, 0.75) + 0.3 * (r - lo) / max(hi - lo, 1e-6)) * amplitude
        grad = rng.uniform(-tilt, tilt, 2) * amplitude
        z = top + (grad[0] * DX + grad[1] * DY) / max(r, 1e-4) * 0.5
        # A ridge across the top: two facets falling away either side of a random line.
        ridge = rng.uniform(0, np.pi)
        across = np.abs(DX * np.cos(ridge) + DY * np.sin(ridge)) / max(r, 1e-4)
        z = z - rng.uniform(0.3, 1.0) * facet * amplitude * across
        # The chamfer: the outer part of the block drops to the neighbour's level.
        if bevel > 0:
            chamfer = np.clip(1.0 - margin / (bevel * r), 0.0, 1.0)
            z = z - chamfer * 0.25 * amplitude
        sub = np.ix_(rows, cols)
        better = inside & (z > height[sub])
        height[sub] = np.where(better, z, height[sub])
        owner[sub] = np.where(better, salt + i, owner[sub])
    return height, owner


def _dome_pile(
    size: int,
    rng: np.random.Generator,
    count: int,
    radius_range: tuple[float, float],
    *,
    elongation: tuple[float, float] = (1.0, 1.0),
    salt: int = 0,
    presence: np.ndarray | None = None,
    presence_min: float = 0.0,
    heading_field: np.ndarray | None = None,
    ragged: float = 0.0,
    profile: float = 0.35,
) -> tuple[np.ndarray, np.ndarray]:
    """Drop ``count`` domed cushions (log-uniform radius, elliptical at a random heading)
    on a periodic tile; the tallest wins. Heights are 0..1 (the crown of the largest).
    A cushion is skipped where ``presence`` (a tile-sized field sampled at its centre)
    is below ``presence_min``, so gaps are where the sward is open, never a hole cut
    out of a finished pile; ``heading_field`` (radians) gives each cushion the lie of
    its clump. Returns (height, owner); height is -inf where no cushion landed."""

    height = np.full((size, size), -np.inf)
    owner = np.full((size, size), -1, dtype="int64")
    lo, hi = radius_range
    for i in range(count):
        cx, cy = rng.uniform(0, 1, 2)
        r = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
        stretch = float(np.exp(rng.uniform(np.log(elongation[0]), np.log(elongation[1]))))
        py, px = int(cy * size) % size, int(cx * size) % size
        if presence is not None and presence[py, px] < presence_min:
            continue
        w = int(r * stretch * size) + 2
        rows = (np.arange(-w, w + 1) + round(cy * size)) % size
        cols = (np.arange(-w, w + 1) + round(cx * size)) % size
        dy = (np.arange(-w, w + 1) + round(cy * size)) / size - cy
        dx = (np.arange(-w, w + 1) + round(cx * size)) / size - cx
        DX, DY = np.meshgrid(dx, dy)
        heading = rng.uniform(0, np.pi)
        if heading_field is not None:
            heading = float(heading_field[py, px]) + rng.uniform(-0.25, 0.25)
        ax = (DX * np.cos(heading) + DY * np.sin(heading)) / stretch
        ay = -DX * np.sin(heading) + DY * np.cos(heading)
        d2 = (ax * ax + ay * ay) / (r * r)
        if ragged > 0:
            # A lobed outline: the radius wanders round the cushion, so no two
            # neighbours meet along a straight cell edge.
            theta = np.arctan2(ay, ax)
            wobble = 1.0 + ragged * (
                0.6 * np.sin(2 * theta + rng.uniform(0, 6.3))
                + 0.4 * np.sin(3 * theta + rng.uniform(0, 6.3))
            )
            d2 = d2 / (wobble * wobble)
        crown = (0.55 + 0.45 * (r - lo) / max(hi - lo, 1e-6)) * rng.uniform(0.85, 1.0)
        z = np.clip(1.0 - d2, 0.0, 1.0) ** profile * crown  # 0.35 a firm rim, 0.6 a soft one
        sub = np.ix_(rows, cols)
        better = (d2 < 1.0) & (z > height[sub])
        height[sub] = np.where(better, z, height[sub])
        owner[sub] = np.where(better, salt + i, owner[sub])
    return height, owner


def _bedded(
    size: int,
    rng: np.random.Generator,
    *,
    bands: int,
    red_share: float,
    lip: float,
    sigma: float = 0.55,
    joint_share: float = 1.0,
    chip_cells: tuple[int, int] = (9, 5),
    chip_share: float = 0.28,
    rubble_share: float = 0.28,
):
    """Bedded rock: log-normal beds, hard beds proud with chipped lips and a few leaning
    joints, soft beds recessed and rubbly (``red_share`` of them red-brown interbeds),
    desert varnish streaking down across all of them."""
    # Bedded rock: log-normal bed thickness, hard beds standing proud with chipped
    # lips and a few leaning, wavering joints each, soft beds recessed and rubbly
    # and warmer, desert varnish streaking down across all of them.
    y = np.linspace(0, 1, size, endpoint=False)[:, None]
    u = np.linspace(0, 1, size, endpoint=False)[None, :]
    thick = np.exp(rng.normal(0.0, sigma, bands))
    thick /= thick.sum()
    edges = np.concatenate([[0.0], np.cumsum(thick)])
    warp = fbm(size, (2, 6), 3, rng) * 0.035
    # Start half a bed in so the tile's wrap falls mid-bed: the beds are periodic,
    # so the tile edge is then no different from any other row.
    yy = (y + warp + 0.5 * thick[0]) % 1.0
    band_index = np.clip(np.searchsorted(edges, yy, side="right") - 1, 0, bands - 1)
    phase = (yy - edges[band_index]) / thick[band_index]
    hard = rng.uniform(0, 1, bands) > 0.35
    amplitude = np.where(hard, rng.uniform(0.75, 1.0, bands), rng.uniform(0.3, 0.55, bands))[
        band_index
    ]
    profile = np.where(phase < lip, phase / lip, 1.0 - 0.2 * (phase - lip) / (1 - lip))
    f1, _f2, cid = worley(size, chip_cells, rng, jitter=0.95)
    broken = (_cell_value(cid, 21) > 1.0 - chip_share) & (phase > 0.75)
    # A notch is an open wedge at the lip: widest at the bed's top edge, closing
    # down into the bed, the lip taken out where it is, not a plug hung from it.
    wedge = np.clip((phase - 0.75) / 0.25, 0, 1)
    missing = _smooth((0.5 - f1) / 0.15) * broken * wedge
    r1, _, rid = worley(size, 36, rng, jitter=1.0)
    # Rubble at the foot of a soft bed only: sparse, and gone by mid-bed.
    rubble = (
        _smooth(1.0 - r1 / (0.25 + 0.25 * _cell_value(rid, 22)))
        * (_cell_value(rid, 23) > 1.0 - rubble_share)
        * _smooth((0.5 - phase) / 0.25)
    )
    soft_here = ~hard[band_index]
    grain = fbm(size, 30, 3, rng) * 0.08 + fbm(size, (8, 60), 2, rng) * 0.05
    joints = np.zeros((size, size))
    wobble = fbm(size, (3, 12), 2, rng) * 0.004
    for b_index in range(bands):
        if not hard[b_index]:
            continue
        in_band = band_index == b_index
        if _cell_value(np.array([b_index]), 5)[0] > joint_share:
            continue  # this bed is unjointed
        count = int(_cell_value(np.array([b_index]), 4)[0] * 4)
        line = np.zeros((size, size))
        for k in range(count):
            pos = _cell_value(np.array([b_index * 13 + k]), 6)[0]
            lean = (_cell_value(np.array([b_index * 17 + k]), 8)[0] - 0.5) * 0.08
            width = 0.003 + 0.004 * _cell_value(np.array([b_index * 19 + k]), 9)[0]
            d = np.abs(((u - pos - lean * (yy - edges[b_index]) + wobble + 0.5) % 1.0) - 0.5)
            line = np.maximum(line, np.exp(-((d / width) ** 2)))
        joints[in_band] = line[in_band]
    # Desert varnish: four to six streaks a tile, 5-8 % of it wide (0.15-0.25 m on
    # a 3 m tile), soft-edged, each starting under a hard bed's lip and fading
    # linearly to nothing over a quarter to a half of the tile down the face
    # (hairlines ruled through the beds read as pencil, not varnish), at a
    # darkening the eye reads on a cream face.
    varnish = np.zeros((size, size))
    hard_ids = [b for b in range(bands) if hard[b]] or [0]
    soft_edge = 0.75 + 0.25 * fbm(size, (8, 30), 2, rng)
    for _k in range(int(rng.integers(5, 8))):
        pos, width = rng.uniform(0, 1), rng.uniform(0.05, 0.08)
        length, start = rng.uniform(0.3, 0.5), edges[int(rng.choice(hard_ids))]
        d = np.abs(((u - pos + 0.5) % 1.0) - 0.5) / (width / 2.0)
        across = np.clip(1.0 - d, 0, 1) ** 0.5 * soft_edge
        along = np.clip(((yy - start) % 1.0) / length, 0, 1)
        fade = np.where(along < 1.0, 1.0 - 0.6 * along, 0.0) * np.clip((1.0 - along) / 0.15, 0, 1)
        varnish = np.maximum(varnish, across * fade * rng.uniform(0.7, 0.9))
    from scipy import ndimage as _ndi

    varnish = _ndi.gaussian_filter(varnish, max(1.0, size / 60.0))  # edges blurred 5 cm
    hard_grain = fbm(size, 90, 3, rng) * 0.05 * hard[band_index]
    h = profile * amplitude * (1.0 - 0.7 * missing) + rubble * soft_here * 0.25 + grain + hard_grain
    h -= joints * 0.3
    # Hard beds cream (capped so nothing blooms white under the sun), soft beds a
    # step darker: the contrast lives in the soft beds.
    lum = np.where(
        hard, 0.80 + 0.10 * rng.uniform(0, 1, bands), 0.45 + 0.15 * rng.uniform(0, 1, bands)
    )[band_index]
    # The shadow line under every harder bed: the recessed bed is darkest right under
    # the lip above it.
    from scipy import ndimage

    occlusion = np.clip((ndimage.maximum_filter(h, size=9, mode="wrap") - h) / 0.5, 0, 1)
    lum = lum * (0.96 + 0.08 * _cell_value(cid, 10)) * (1.0 - 0.35 * joints)
    lum = lum * (1.0 - 0.3 * occlusion) * (1.0 - 0.12 * missing * (1.0 - wedge * 0.6))
    # Soft beds are warm; half of them are the red-brown siltstone interbeds that
    # stripe the Kaibab in the crater's rim photographs.
    red_bed = (rng.uniform(0, 1, bands) < red_share)[band_index] & soft_here
    bed_rgb = np.where(
        red_bed[..., None],
        _rgb(0.92, 0.62, 0.46),
        np.where(soft_here[..., None], _rgb(1.0, 0.94, 0.86), _rgb(1, 1, 1)),
    )
    tint = lum[..., None] * bed_rgb
    # The varnish is a dark red-brown stain, not a shadow: it takes the face to
    # a third of its tone at full strength and browns it on the way.
    stain = _rgb(0.36, 0.28, 0.24)
    tint = tint * (1.0 - varnish[..., None] * (1.0 - stain))
    return np.clip(h * 2.0 - 1.0, -1, 1), tint


def _tilt(cid: np.ndarray, offset, salt: int, amount: float) -> np.ndarray:
    """A plane through each cell's feature point with a random per-cell gradient."""

    ox, oy = offset
    return amount * ((_cell_value(cid, salt) - 0.5) * ox + (_cell_value(cid, salt + 1) - 0.5) * oy)


def _rgb(*values: float) -> np.ndarray:
    return np.array(values, dtype="float64")


def _feature(kind: str, size: int, rng: np.random.Generator, params: dict | None = None):
    """Return (detail, tint) for a family; ``tint`` is None or a 0.6..1.4 multiplier map.

    ``params`` is the family's own entry, for the few kinds that take options."""

    params = params or {}

    if kind == "pebbles":
        # Desert floor: sparse pebbles over fine grit, darker cryptobiotic crust in patches.
        f1, _, cid = worley(size, 40, rng)
        radius = 0.18 + 0.16 * _cell_value(cid, 1)
        pebble = _smooth(1.0 - f1 / radius) * (0.4 + 0.6 * _cell_value(cid, 2))
        sparse = _cell_value(cid, 3) > 0.45
        g1, _, gid = worley(size, 90, rng)
        grit = _smooth(1.0 - g1 / 0.35) * (_cell_value(gid, 4) > 0.5) * 0.3
        crust = _smooth((fbm(size, 4, 3, rng) - 0.05) / 0.15)
        h = pebble * sparse * 1.6 + grit - 0.35 + fbm(size, 18, 3, rng) * 0.25
        tint = (1.0 - crust[..., None] * _rgb(0.16, 0.18, 0.21)) * (1.0 + 0.25 * pebble * sparse)[
            ..., None
        ]
        return np.clip(h, -1, 1), tint
    if kind == "gravel":
        # Compacted road gravel on a 2 m tile: crushed stone from 5 to 60 mm (log-uniform,
        # so most of it is small), the coarse pieces sitting proud in a bed of fines,
        # with the fines packed flat by the traffic and a little dust between.
        stones, s_owner = _block_pile(
            size, rng, 320, (0.003, 0.025), 0.5, 0, elongation=(1.0, 1.7), tilt=0.5
        )
        fines, f_owner = _block_pile(
            size, rng, 22000, (0.002, 0.006), 0.3, 10000, elongation=(1.0, 1.4), tilt=0.4
        )
        # Fines fill the bed, packed nearly flat; stones stand a little proud of them.
        # Anything neither reached is dust at the bed level.
        bed = np.where(np.isfinite(fines), 0.2 + 0.5 * fines, 0.18)
        height = np.where(np.isfinite(stones), 0.15 + stones, bed)
        owner = np.where(np.isfinite(stones), s_owner, np.where(np.isfinite(fines), f_owner, -1))
        height = height + fbm(size, 20, 3, rng) * 0.1
        lum = np.where(owner >= 0, 0.8 + 0.4 * _cell_value(np.maximum(owner, 0), 4), 0.85)
        # The coarse pieces are the road's own rock, broken fresh: paler than the dust.
        lum = np.where(np.isfinite(stones), lum * 1.1, lum)
        return np.clip(height * 1.6 - 0.6, -1, 1), lum
    if kind == "blocks":
        return _feature("boulders", size, rng)
    if kind == "boulders":
        # A talus pile, not a pavement: convex blocks at three sizes dropped onto the
        # tile with overlap allowed (the nearest top wins), gravel where none landed,
        # shadow under every upper block's edge, lichen on a third of the big ones.
        from scipy import ndimage

        large, l_owner = _block_pile(size, rng, 48, (0.05, 0.1), 1.0, 0)
        medium, m_owner = _block_pile(size, rng, 160, (0.025, 0.06), 0.72, 1000)
        small, s_owner = _block_pile(size, rng, 700, (0.009, 0.024), 0.4, 5000)
        height = np.maximum(np.maximum(large, medium), small)
        owner = np.where(large >= height, l_owner, np.where(medium >= height, m_owner, s_owner))
        present = np.isfinite(height)
        gravel = fbm(size, 60, 3, rng) * 0.12 + 0.12
        height = np.where(present, height, gravel)
        own = np.maximum(owner, 0)
        # Face grain: pits a few centimetres across in every face, and a crack
        # through one block in ten, so no face is one flat tone.
        p1, _p2, pid = worley(size, 150, rng, jitter=1.0)
        pits = _smooth(1.0 - p1 / 0.35) * (_cell_value(pid, 38) > 0.6) * present
        c1, c2, _cid = worley(size, 5, rng, jitter=1.0)
        crack = (1.0 - _smooth((c2 - c1) / 0.02)) * (_cell_value(own, 39) > 0.9) * present
        height = height - 0.05 * pits - 0.25 * crack
        occlusion = np.clip(
            (ndimage.maximum_filter(height, size=7, mode="wrap") - height) / 0.35, 0, 1
        )
        lum = np.where(present, 0.62 + 0.7 * _cell_value(own, 34), 0.85 + 0.2 * gravel)
        lum = lum * (1.0 - 0.45 * occlusion) * (1.0 - 0.08 * pits) * (1.0 - 0.35 * crack)
        patch = fbm(size, 24, 3, rng)
        big = present & (owner < 1000)
        # Lichen on a few of the big blocks only, in small patches that never cross a
        # block's edge (the gate is the block's own id).
        lichen = (big & (_cell_value(np.maximum(owner, 0), 36) > 0.8)) * _smooth(
            (patch - 0.12) / 0.1
        )
        orange = (_cell_value(np.maximum(owner, 0), 37) > 0.75)[..., None]
        lichen_rgb = np.where(orange, _rgb(1.25, 0.95, 0.55), _rgb(1.0, 1.12, 0.62))
        tint = lum[..., None] * (1.0 + (lichen_rgb - 1.0) * lichen[..., None])
        # Options: a share of the blocks in another rock (cream Kaibab among the red
        # Moenkopi), and the dust between the blocks its own colour.
        # Both are absolute sRGB colours: the multiplier that turns the family's
        # base into them, so a cream block is cream whatever the base is.
        base_lin = np.power(np.asarray(params.get("base_rgb", [0.5, 0.5, 0.5]), "float64"), 2.2)
        pale_share = float(params.get("pale_share", 0.0))
        if pale_share > 0:
            pale = (present & (_cell_value(own, 42) < pale_share))[..., None]
            pale_lin = np.power(np.asarray(params.get("pale_rgb", [0.78, 0.72, 0.62])), 2.2)
            tint = np.where(pale, lum[..., None] * (pale_lin / np.maximum(base_lin, 1e-3)), tint)
        if params.get("matrix_rgb"):
            matrix_lin = np.power(np.asarray(params["matrix_rgb"], "float64"), 2.2)
            tint = np.where(
                (~present)[..., None],
                lum[..., None] * (matrix_lin / np.maximum(base_lin, 1e-3)),
                tint,
            )
        height = height + fbm(size, 90, 2, rng) * 0.03
        return np.clip(height * 1.7 - 0.9, -1, 1), tint
    if kind == "cobbles":
        # Ejecta: angular blocks at two sizes half-buried in sand, only some cells
        # carry one; the blocks are rust-brown Kaibab and Coconino, the sand is pale.
        def blocks(cells, salt, presence, amplitude):
            f1, f2, cid, off = worley(size, cells, rng, jitter=1.0, warp=0.06, return_offset=True)
            radius = 0.3 + 0.3 * _cell_value(cid, salt)
            present = _cell_value(cid, salt + 1) > presence
            facet = _smooth((f2 - f1) / 0.14)
            # A chunk is its Worley cell cut back to a rough radius: straight edges
            # where the cell boundary cuts it, rounded where the radius does.
            body = _smooth((f2 - f1) / 0.12) * _smooth((radius * 1.4 - f1) / 0.2) * present
            top = 0.5 + 0.5 * _cell_value(cid, salt + 4) + _tilt(cid, off, salt + 2, 0.5)
            return body * top * (0.6 + 0.4 * facet) * amplitude, body, cid

        # Both sizes as cut blocks (piles of convex polygons with a ridge and a
        # chamfer), never discs.
        from scipy import ndimage

        big_h, b_owner = _block_pile(
            size, rng, 8, (0.035, 0.08), 1.0, 3000, elongation=(1.0, 1.7), tilt=0.5
        )
        big_body = np.isfinite(big_h).astype("float64")
        bid = np.maximum(b_owner, 0)
        small_h, s_owner = _block_pile(
            size, rng, 70, (0.012, 0.03), 0.5, 7000, elongation=(1.0, 1.6), tilt=0.5
        )
        small_body = np.isfinite(small_h).astype("float64")

        def domed(pile_h, owner):
            # A chunk is a dome, not a plateau: its height rises as the square root
            # of the distance in from its edge, to its own top, so the normal map
            # carries a top and a rolled edge instead of one shadow line.
            body = np.isfinite(pile_h)
            flat = np.where(body, pile_h, 0.0)
            if not body.any():
                return flat
            own = np.where(body, owner, 0)
            index = np.arange(int(own.max()) + 1)
            d = ndimage.distance_transform_edt(body)
            d_max = ndimage.maximum(d, own, index)[own]
            h_max = ndimage.maximum(flat, own, index)[own]
            dome = np.sqrt(np.clip(d / np.maximum(d_max, 1.0), 0, 1))
            return np.where(body, h_max * (0.1 + 1.3 * dome) + 0.2 * (flat - h_max), 0.0)

        big = domed(big_h, bid)
        small = domed(small_h, np.maximum(s_owner, 0))
        h = np.maximum(big, small) + fbm(size, 36, 2, rng) * 0.08
        body = np.clip(big_body + small_body, 0, 1)
        block_lum = 0.92 + 0.16 * np.where(
            big_body > 0, _cell_value(bid, 75), _cell_value(np.maximum(s_owner, 0), 85)
        )
        # Shadow on the down-light side of every chunk only (the height stepped
        # three texels), a third of the chunks dusted to the soil, a slight gradient
        # across each face; the soil between is the rust-brown of the hummocks.
        shadow = np.clip((np.roll(h, 3, axis=0) - h) / 0.35, 0, 1) * (1 - body)
        owner_all = np.where(big_body > 0, bid, np.maximum(s_owner, 0))
        dusted = (_cell_value(owner_all, 88) < 0.3)[..., None]
        grade = 1.0 + 0.03 * fbm(size, (2, 60), 1, rng)
        chunk = _rgb(1.15, 1.02, 0.88)
        if params.get("chunk_rgb"):
            # Kaibab chunks are cream-grey whatever the soil: an absolute tone.
            base_lin = np.power(np.asarray(params.get("base_rgb", [0.5, 0.5, 0.5]), "float64"), 2.2)
            chunk = np.power(np.asarray(params["chunk_rgb"], "float64"), 2.2) / base_lin
        # Fine speckle inside every chunk and a darker line on its down-light edges,
        # so a chunk is a stone and not a paper cut-out.
        speckle = 1.0 + 0.06 * fbm(size, 120, 2, rng)
        edge_line = np.clip((ndimage.maximum_filter(h, size=5, mode="wrap") - h) / 0.12, 0, 1)
        rock_rgb = chunk * (block_lum * grade * speckle * (1.0 - 0.45 * edge_line))[..., None]
        soil_rgb = _rgb(1.0, 0.82, 0.66) * (0.9 + 0.2 * fbm(size, 8, 2, rng))[..., None]
        rock_rgb = np.where(dusted, rock_rgb * 0.6 + soil_rgb * 0.4, rock_rgb)
        tint = (rock_rgb * body[..., None] + soil_rgb * (1 - body[..., None])) * (
            1.0 - 0.45 * shadow
        )[..., None]
        return np.clip(h * 2.0 - 0.9, -1, 1), tint
    if kind == "cliff":
        # A blocky tuff face: a tight pile of large plates at their own heights and
        # tilts, shattered into smaller blocks in a few clusters, cut by one or two
        # master partings, water-stained, lichen on the old faces.
        from scipy import ndimage

        large, l_owner = _block_pile(size, rng, 60, (0.06, 0.16), 1.0, 0, tilt=0.7)
        medium, m_owner = _block_pile(size, rng, 140, (0.03, 0.07), 0.8, 1000, tilt=0.7)
        small, s_owner = _block_pile(size, rng, 900, (0.01, 0.028), 0.55, 5000, tilt=0.5)
        # Shatter clusters: inside two or three random ellipses the small blocks win.
        U, V = np.meshgrid(
            np.linspace(0, 1, size, endpoint=False), np.linspace(0, 1, size, endpoint=False)
        )
        shatter = np.zeros((size, size), dtype=bool)
        ragged = fbm(size, 6, 3, rng)
        for _ in range(int(rng.integers(2, 4))):
            cx, cy = rng.uniform(0, 1, 2)
            rx, ry = rng.uniform(0.1, 0.24, 2)
            du = ((U - cx + 0.5) % 1.0) - 0.5
            dv = ((V - cy + 0.5) % 1.0) - 0.5
            shatter |= (du / rx) ** 2 + (dv / ry) ** 2 + 0.8 * ragged < 0.8
        height = np.where(shatter, small, np.maximum(np.maximum(large, medium), small))
        owner = np.where(
            shatter,
            s_owner,
            np.where(large >= height, l_owner, np.where(medium >= height, m_owner, s_owner)),
        )
        present = np.isfinite(height)
        height = np.where(present, height, 0.2)
        # Master partings: one or two straight deep joints across the tile.
        # Their headings are integer windings of the tile so they close on themselves
        # at the wrap instead of jumping at the tile edge.
        windings = [(1, 0), (0, 1), (1, 1), (1, -1), (2, 1), (1, 2), (2, -1), (1, -2)]
        for _ in range(int(rng.integers(1, 3))):
            a, b = windings[int(rng.integers(0, len(windings)))]
            offset = rng.uniform(0, 1)
            d = np.abs(((a * U + b * V - offset + 0.5) % 1.0) - 0.5) / math.hypot(a, b)
            height = height - 0.5 * np.exp(-((d / 0.006) ** 2))
        occlusion = np.clip(
            (ndimage.maximum_filter(height, size=7, mode="wrap") - height) / 0.3, 0, 1
        )
        stain = np.clip(fbm(size, (36, 2), 3, rng) * 1.6, 0, 1) ** 2
        lum = 0.6 + 0.75 * _cell_value(np.maximum(owner, 0), 68)
        lum = lum * (1.0 - 0.45 * occlusion) * (1.0 - 0.4 * stain)
        patch = fbm(size, 20, 3, rng)
        old_face = present & (owner < 1000) & (_cell_value(np.maximum(owner, 0), 69) > 0.55)
        lichen = old_face * _smooth((patch - 0.08) / 0.1)
        orange = (_cell_value(np.maximum(owner, 0), 70) > 0.5)[..., None]
        lichen_rgb = np.where(orange, _rgb(1.2, 0.9, 0.5), _rgb(0.95, 1.1, 0.7))
        tint = lum[..., None] * (1.0 + (lichen_rgb - 1.0) * lichen[..., None])
        height = height + fbm(size, 34, 3, rng) * 0.06
        return np.clip(height * 1.7 - 0.9, -1, 1), tint
    if kind == "dark_strata":
        # Thin-bedded dark rock (the Telluride cliffs): forty log-normal beds to the
        # tile (a 12 m tile puts the median at 0.3 m), no red interbeds, water stains
        # and lichen, joints in six beds of ten and never lined up bed to bed.
        return _bedded(size, rng, bands=40, red_share=0.0, lip=0.08, sigma=0.6, joint_share=0.6)
    if kind in ("ledges", "strata"):
        return _bedded(
            size,
            rng,
            bands=8 if kind == "ledges" else 11,
            red_share=0.5,
            lip=0.12,
            chip_cells=(24, 8),
            chip_share=0.3,
            rubble_share=0.3,
        )
    if kind == "shale":
        # Scree of loose plates: elongated chips at every heading and log-normal sizes,
        # piled with overlap, fine grit where no chip landed.
        from scipy import ndimage

        chips, c_owner = _block_pile(
            size, rng, 700, (0.012, 0.045), 0.6, 0, elongation=(1.6, 3.0), tilt=0.6
        )
        fine, f_owner = _block_pile(
            size, rng, 1600, (0.005, 0.014), 0.3, 3000, elongation=(1.3, 2.2), tilt=0.4
        )
        height = np.maximum(chips, fine)
        owner = np.where(chips >= height, c_owner, f_owner)
        present = np.isfinite(height)
        grit = fbm(size, 90, 3, rng) * 0.08 + 0.1
        height = np.where(present, height, grit)
        occlusion = np.clip(
            (ndimage.maximum_filter(height, size=5, mode="wrap") - height) / 0.25, 0, 1
        )
        lum = np.where(present, 0.7 + 0.5 * _cell_value(np.maximum(owner, 0), 12), 0.85)
        lum = lum * (1.0 - 0.4 * occlusion)
        return np.clip(height * 1.8 - 0.8, -1, 1), lum
    if kind in ("tufts", "tussocks"):
        # Tussock tundra: sedge cushions of log-normal size (10-45 cm on the 2 m tile),
        # up to two and a half times as long as wide and lying the same way within a
        # clump, run together where a slow noise says the sward is closed and absent
        # where it says bare; the bare ground is fine gravel, not flakes; blade-scale
        # streaks on every cushion and straw-yellow dead crowns on a third of them.
        sward = fbm(size, 3, 2, rng) + 0.5 * fbm(size, 7, 2, rng)
        lie = np.pi * (fbm(size, 2, 2, rng) + 0.5)  # one heading per clump
        cushion, owner = _dome_pile(
            size,
            rng,
            650,
            (0.03, 0.07),
            elongation=(1.3, 1.8),
            presence=sward,
            presence_min=0.2,
            heading_field=lie,
            ragged=0.2,
            profile=float(params.get("cushion_profile", 0.35)),
        )
        cushion = np.where(np.isfinite(cushion), cushion, 0.0)
        # The bare ground between the clumps: packed fines with a scatter of grit.
        fines, f_owner = _block_pile(
            size, rng, 6000, (0.003, 0.008), 0.3, 10000, elongation=(1.0, 1.5), tilt=0.4
        )
        grit = np.where(np.isfinite(fines), 0.12 + 0.5 * fines, 0.1)
        p1, _, pid = worley(size, 70, rng, jitter=1.0)
        stones = (
            _smooth(1.0 - p1 / (0.2 + 0.15 * _cell_value(pid, 18)))
            * (_cell_value(pid, 19) > 0.7)
            * 0.25
        )
        own = np.maximum(owner, 0)
        # Blades: fine streaks along each clump's lie.
        # Blades at 3-8 mm on the 2 m tile: one direction per cushion, never a weave.
        along = fbm(size, (400, 100), 2, rng)
        across = fbm(size, (100, 400), 2, rng)
        blades = np.where(_cell_value(own, 25) > 0.5, along, across) * 0.5
        blades = blades * (0.5 + _cell_value(own, 21))
        # Tan grass tufts, 2-5 cm, on the bare ground between the cushions.
        tuft_h, _tuft_owner = _dome_pile(size, rng, 500, (0.005, 0.012), elongation=(1.0, 2.0))
        tufts = np.where(np.isfinite(tuft_h), tuft_h, 0.0) * (cushion < 0.05)
        h = cushion + (grit + stones + tufts * 0.4) * (1 - cushion) + blades * cushion
        h = h + fbm(size, 30, 3, rng) * 0.1
        veg = np.clip(cushion * 1.4, 0, 1)
        # Dead straw on a fifth of the cushions, over the whole cushion and most on
        # its crown.
        crowned = (_cell_value(own, 22) > 0.8).astype("float64")
        crown = (0.5 + 0.5 * np.clip((cushion - 0.4) / 0.6, 0, 1)) * crowned
        # Late-summer olive, no more saturated than the palette base; the blades
        # carry 15 % of the tone so the cushions are not smooth. A family may name
        # the cushion, ground and straw colours outright (sRGB): they are taken as
        # tints on the material's base, so the tonal order is the authored one.
        green_t, soil_t, straw_t = _rgb(0.82, 0.92, 0.64), _rgb(0.8, 0.69, 0.58), None
        if params.get("cushion_rgb"):
            base_lin = np.power(np.asarray(params.get("base_rgb", [0.5, 0.5, 0.5]), "float64"), 2.2)
            green_t = np.power(np.asarray(params["cushion_rgb"], "float64"), 2.2) / base_lin
            soil_t = np.power(np.asarray(params["ground_rgb"], "float64"), 2.2) / base_lin
            straw_t = np.power(np.asarray(params["straw_rgb"], "float64"), 2.2) / base_lin
        green = green_t * (0.76 + 0.48 * _cell_value(own, 20))[..., None]
        green = green * (1.0 + 0.6 * blades)[..., None]
        straw = straw_t if straw_t is not None else _rgb(1.12, 0.98, 0.58)
        veg_rgb = green * (1 - crown[..., None]) + straw * crown[..., None]
        soil = soil_t * (0.9 + 0.3 * np.clip(grit, 0, 1))[..., None]
        soil = (
            soil
            * (1.0 + 0.35 * tufts)[..., None]
            * np.where((tufts > 0.2)[..., None], _rgb(1.05, 1.0, 0.85), _rgb(1.0, 1.0, 1.0))
        )
        tint = (veg_rgb * veg[..., None] + soil * (1 - veg)[..., None]) * (1.0 + 0.5 * stones)[
            ..., None
        ]
        return np.clip(h * 1.8 - 0.7, -1, 1), tint
    if kind == "duff":
        # Conifer floor: needle clumps at two scales, fallen twigs at every heading,
        # a few cones, damp dark patches; isotropic and with real relief.
        # Twigs 5-30 cm long on the 2 m tile (a floor is needles and cones with a few
        # short twigs, not pick-up sticks).
        twigs, _t = _block_pile(
            size, rng, 110, (0.003, 0.008), 0.35, 0, elongation=(3.0, 6.0), tilt=0.2
        )
        cones, c_owner = _block_pile(size, rng, 40, (0.008, 0.014), 0.7, 500, tilt=0.3)
        n1, _, nid = worley(size, 26, rng, jitter=1.0)
        clumps = _smooth(1.0 - n1 / (0.5 + 0.3 * _cell_value(nid, 3))) * (
            0.3 + 0.5 * _cell_value(nid, 4)
        )
        needles = fbm(size, 70, 3, rng) * 0.3 + clumps * 0.5
        litter = np.maximum(
            np.where(np.isfinite(twigs), twigs, -1.0), np.where(np.isfinite(cones), cones, -1.0)
        )
        h = np.where(litter > needles, litter, needles)
        damp = _smooth((fbm(size, 4, 3, rng) - 0.05) / 0.2)
        # Twigs are pale, opaque wood with a shadow along their lower edge, not
        # dark slivers.
        from scipy import ndimage

        twig_here = np.isfinite(twigs)
        edge = ndimage.binary_dilation(twig_here, iterations=2) & ~twig_here
        tint = (
            (1.0 - 0.3 * damp)[..., None]
            * _rgb(1.0, 0.92, 0.8)
            * (1.0 + 0.15 * twig_here - 0.3 * edge - 0.25 * np.isfinite(cones))[..., None]
        )
        return np.clip(h * 1.8 - 0.7, -1, 1), tint
    if kind == "cracks":
        f1, f2, cid = worley(size, 7, rng, jitter=0.7)
        crack = 1.0 - _smooth((f2 - f1) / 0.08)
        curl = _smooth(f1 / 0.9) * 0.3
        return np.clip(0.3 - crack * 1.4 - curl + fbm(size, 24, 2, rng) * 0.1, -1, 1), None
    if kind == "rills":
        ridges = np.abs(fbm(size, (22, 3), 3, rng)) * 2 - 1
        return ridges * 0.6 + fbm(size, 18, 3, rng) * 0.4, None
    if kind == "asphalt":
        grain = fbm(size, 64, 2, rng) * 0.5 + fbm(size, 128, 1, rng) * 0.5
        # Cracks: cells of 0.3-0.5 m (a 6 m tile), their edges displaced by noise
        # and only three in ten drawn, so no paving tessellation shows.
        f1, f2, cid_c = worley(size, 16, rng, jitter=1.0, warp=0.05)
        # A crack is a line three or four texels wide (30 mm on an 8 m tile), two
        # fifths darker than the slab, on three edges in ten: at a fifth over one
        # texel it was under threshold at every distance.
        cracks = (1.0 - _smooth((f2 - f1) / 0.006)) * (_cell_value(cid_c, 61) > 0.7)
        patches = fbm(size, 3, 2, rng) * 0.15
        # Across the road (u): a pale gravel shoulder each side and a darker wear
        # band down the middle of each lane.
        x = np.linspace(0, 1, size, endpoint=False)[None, :]
        # A 0.4 m tan gravel shoulder each side of a 6 m road (7 % of the width)
        # inside the decal's opaque part, and a 0.6 m wheel-track wear band in each
        # lane a tenth paler than the slab.
        shoulder = np.zeros((size, size))
        if params.get("shoulder", True):
            s_in, s_out = params.get("shoulder_span", (0.0, 0.07))
            # The shoulder's inner edge wanders +-0.15 m (a 6 m road) at a 2-4 m
            # wavelength and its tone carries the gravel grain, so it is not a
            # painted line.
            # 1/f wander at 2-8 m wavelengths (0.1 m on a 6 m road) plus 5 cm jitter:
            # a gravel edge, not rick-rack.
            wander = (
                fbm(size, (1, 3), 3, rng)[:, :1] * 0.03 + fbm(size, (1, 40), 1, rng)[:, :1] * 0.008
            )
            xj = x + wander
            band = _smooth((s_out - xj) / 0.01) * _smooth((xj - s_in) / 0.01)
            band = band + _smooth((xj - (1.0 - s_out)) / 0.01) * _smooth(((1.0 - s_in) - xj) / 0.01)
            shoulder = np.clip(band, 0, 1) * (0.85 + 0.3 * np.clip(grain + 0.5, 0, 1))
        wear = np.exp(-((x - 0.23) ** 2) / 0.0018) + np.exp(-((x - 0.77) ** 2) / 0.0018)
        wear = np.clip(wear, 0, 1) * np.ones((size, 1))
        tint = ((1.0 + float(params.get("wear_contrast", 0.1)) * wear) * (1.0 - 0.4 * cracks))[
            ..., None
        ]
        if params.get("shoulder_rgb"):
            base_lin = np.power(np.asarray(params.get("base_rgb", [0.5, 0.5, 0.5]), "float64"), 2.2)
            ratio = np.power(np.asarray(params["shoulder_rgb"], "float64"), 2.2) / base_lin
            tint = tint * (1.0 + (ratio - 1.0) * shoulder[..., None])
        else:
            tint = tint * (1.0 + 1.2 * shoulder)[..., None]
            tint = tint * np.where(
                shoulder[..., None] > 0.5, _rgb(1.0, 0.94, 0.86), _rgb(1.0, 1.0, 1.0)
            )
        # And deep enough that the normal tilts at the lip rather than lying flat.
        h = grain * 0.5 - cracks * 2.2 + patches + shoulder * 0.3
        return np.clip(h, -1, 1), tint
    if kind in ("ruts", "ruts_gravel"):
        # Across the road (u): two compacted wheel ruts and a raised, rougher centre.
        x = np.linspace(0, 1, size, endpoint=False)[None, :]
        # Flat-bottomed ruts with a real wall (2 % of the width, a hand on a 4 m road).
        rut = _smooth((0.07 - np.abs(x - 0.30)) / 0.008) + _smooth(
            (0.07 - np.abs(x - 0.70)) / 0.008
        )
        rut = np.clip(rut, 0, 1)
        crown = 0.45 * np.exp(-((x - 0.5) ** 2) / 0.015)
        # Stones as on the bed: log-uniform 5-60 mm on a 2 m tile, most of them small.
        stones, s_owner = _block_pile(
            size, rng, 400, (0.003, 0.025), 1.0, 0, elongation=(1.0, 1.7), tilt=0.5
        )
        pebbles = np.where(np.isfinite(stones), np.clip(stones, 0, 1), 0.0)
        cid = np.maximum(s_owner, 0)
        # Washboard in the wheel tracks at the 0.4-0.7 m pitch braking traffic makes:
        # three pitches whose phases wander with a slow noise, so the eye never
        # counts a period, at a third of the rut depth.
        v = np.linspace(0, 1, size, endpoint=False)[:, None]
        wander = [fbm(size, (1, 3), 2, rng)[:, :1] * 0.6 for _ in range(3)]
        tread = (
            np.sin(2 * np.pi * (7 * v + wander[0]))
            + 0.7 * np.sin(2 * np.pi * (9 * v + wander[1]))
            + 0.5 * np.sin(2 * np.pi * (12 * v + wander[2]))
        ) / 2.2
        tread = tread * 0.3 * 0.9  # a third of the 0.9 rut depth
        wear = fbm(size, (2, 8), 2, rng) * 0.2
        base = (-0.9 * rut + crown) * np.ones((size, 1)) + wear + tread * rut
        weight = 0.25 if kind == "ruts" else 0.6
        h = base + pebbles * weight * (1.0 - 0.5 * rut)  # stones on through the rut floor
        # A desert two-track has pale, dust-polished ruts and a darker crown of
        # crust; a gravel track's ruts are compacted and darker.
        if kind == "ruts":
            wheel = (1.0 + float(params.get("rut_tint", 0.12)) * rut) * (1.0 - 0.14 * crown)
            # Pebble speckle at a readable amplitude, so the track is not a blur.
            wheel = wheel * (1.0 + 0.15 * fbm(size, 100, 2, rng))
        else:
            wheel = (1.0 - 0.18 * rut) * (1.0 + 0.08 * crown)
        tint = wheel * (0.9 + 0.2 * _cell_value(cid, 19) * pebbles)
        return np.clip(h, -1, 1), tint
    return fbm(size, 6, 4, rng), None


def _srgb(linear: np.ndarray) -> np.ndarray:
    linear = np.clip(linear, 0.0, 1.0)
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055)


def build_set(
    out_dir: Path,
    name: str,
    family: str,
    seed: int,
    size: int,
    base_rgb,
    rotate_deg: float = 0.0,
) -> dict[str, Path]:
    """Write the five maps for one material and return their paths keyed by suffix."""

    from PIL import Image

    params = FAMILIES[family]
    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    low = fbm(size, params["freq"], params["octaves"], rng)
    detail, tint = _feature(params["feature"], size, rng, {**params, "base_rgb": list(base_rgb)})
    if int(rotate_deg) % 180 == 90:
        # The same family turned a quarter: bedding that runs the other way for the
        # walls a top-down projection would otherwise stripe.
        low = low.T
        detail = detail.T
        tint = None if tint is None else (tint.T if tint.ndim == 2 else np.swapaxes(tint, 0, 1))
    height = np.clip(0.5 + 0.14 * low + 0.36 * params["gain"] * detail, 0.0, 1.0)

    # Colour: the authored base, shaded by the height field (dirt gathers in the lows),
    # tinted per cell where the family has cells, with a slow warm/cool drift.
    # Authored colours are what the screen should show (sRGB); the shading happens in
    # linear light and the result is encoded back, so the mean pixel equals the spec.
    base = np.power(np.asarray(base_rgb, dtype="float64"), 2.2)
    drift = fbm(size, 2, 2, rng)
    # A family whose relief is turf over gravel is not shaded by its height (the
    # cushions would come out paler than the ground between them, the wrong way
    # round for tundra): ``shade_by_height`` scales the shading and the gap darkening.
    by_h = float(params.get("shade_by_height", 1.0))
    shade = 0.72 + 0.85 * by_h * (height - 0.5) + 0.08 * drift
    shade *= 1.0 - 0.28 * by_h * (1.0 - _smooth((height - 0.15) / 0.35))  # cracks go dark
    if tint is not None and tint.ndim == 2:
        shade = shade * tint
    warm = np.stack([1.0 + 0.06 * drift, np.ones_like(drift), 1.0 - 0.06 * drift], axis=-1)
    colour = base[None, None, :] * shade[..., None] * warm
    if tint is not None and tint.ndim == 3:
        colour = colour * tint  # per-channel: lichen, soil between cushions, rust blocks
    # Tone contract: whatever the shading and tints did, the set's mean albedo is the
    # authored base, so a spec value reaches the screen as written.
    if params.get("tone_by") == "median":
        # The typical cell is the base (a decal whose shoulder would lift the mean).
        level = float(np.median(colour.mean(axis=-1)))
    else:
        level = float(colour.mean())
    colour = colour * (float(base.mean()) / max(level, 1e-4))
    # A soft knee on the brightest channel instead of a hard clip: the mean-albedo
    # scaling pinned a sixth of the limestone tile's texels at 255 in red, so the
    # hard beds had no colour left and the wall went chalk white under the sun.
    cap = float(params.get("albedo_max", 1.0))
    knee = cap * 0.8
    peak = colour.max(axis=-1, keepdims=True)
    rolled = knee + (peak - knee) / (1.0 + (peak - knee) / max(cap - knee, 1e-4))
    colour = colour * np.where(peak > knee, rolled / np.maximum(peak, 1e-4), 1.0)
    colour = np.clip(colour, 0.0, cap)
    colour_u8 = (_srgb(colour) * 255.0).round().astype("uint8")

    # Normal from the height field (tangent space, +Y up in texture space).
    scale = 6.0 * params["gain"]
    gy, gx = np.gradient(height)
    nx = -gx * scale * size / 256.0
    ny = gy * scale * size / 256.0
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack([nx / length, ny / length, nz / length], axis=-1)
    normal_u8 = np.clip((normal * 0.5 + 0.5) * 255.0, 0, 255).astype("uint8")

    rough = np.clip(params["rough"] + 0.12 * (0.5 - height) + 0.05 * drift, 0.05, 1.0)
    rough_u8 = (rough * 255.0).round().astype("uint8")
    height_u8 = (height * 255.0).round().astype("uint8")
    ao = np.clip(1.0 - 0.9 * (0.5 - height).clip(0, None) * 2.0, 0.25, 1.0)
    ao_u8 = (ao * 255.0).round().astype("uint8")

    paths = {}
    for suffix, array, mode in (
        ("b", colour_u8, "RGB"),
        ("nm", normal_u8, "RGB"),
        ("r", rough_u8, "L"),
        ("h", height_u8, "L"),
        ("ao", ao_u8, "L"),
    ):
        path = out_dir / f"{name}_{suffix}.png"
        Image.fromarray(array, mode=mode).save(path, format="PNG", compress_level=6)
        paths[suffix] = path
    return paths
