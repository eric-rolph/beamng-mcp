"""B2's cooked maps: the six rock heroes, the ember crust and the two decal sets.

Everything is a deterministic function of the CC0 sources in ``cc0_cache/`` and the
seeds in ``hearth_spec``.  Run::

    .\\.venv\\Scripts\\python.exe -m examples.hot_potato_arena.level.hearth_textures

Laws applied here:

* **every dimension is a power of two** or the engine silently never cooks the
  texture and draws missing-texture magenta (B1 r2).  ``_check_px`` refuses one.
* **PNG row 0 is v = 1**: a map whose content has a top-down meaning is flipped once
  at the end of the cook.  The rock heroes and the crust are tileable/UV-mapped so
  the orientation is carried by the source; the DECAL ATLAS is the one authored
  top-down here, and it is flipped once in :func:`_atlas`.
* the maps land in the slot names their material's ``version`` implies (1.5 / PBR).

The manifest lands in ``authoring/<id>_hearth_textures.json`` with every file's
sha256, pixel size and byte count, and the provenance row of each CC0 source.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from examples.hot_potato_arena.level import hearth_spec as hs

EXAMPLE_ROOT = hs.EXAMPLE_ROOT
CACHE = EXAMPLE_ROOT / "cc0_cache"
LEVEL_ROOT = EXAMPLE_ROOT / "mod" / "levels" / hs.LEVEL_ID
MANIFEST = hs.AUTHORING / f"{hs.LEVEL_ID}_hearth_textures.json"

#: CC0 sources this round consumes, beyond the six stone glTFs' own maps.
OVERLAY_SOURCES = {
    "burned_ground_01": "char / ash: the crust albedo's base and the soot overlays",
    "snow_02": "the crust's fine grain (inverted) and the salt scatter decal",
    "rock_face": "the hearth slab micro-structure under the soot and scorch decals",
    "dry_ground_rocks": "the ash-drift and scorch decal grain",
    # r7 (critic C6-1): the 36 m slot's DETAIL DONOR.  Only its high-frequency grain and
    # its roughness are read -- never its body, silhouette or colour.
    "namaqualand_boulder_06": (
        "the rock_face_01 slot's detail donor: high-frequency colour/normal/AO grain and "
        "the roughness channel, because rock_07's own is a constant 0.2979"
    ),
}


class HearthTextureError(RuntimeError):
    """A cook input is missing or a written map would not cook in the engine."""


def _check_px(px: int, label: str) -> int:
    if px < 16 or (px & (px - 1)) != 0:
        raise HearthTextureError(f"{label}: {px} px is not a power of two >= 16 and never cooks")
    return px


def _rng(*parts: Any) -> np.random.Generator:
    key = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()[:8]
    return np.random.default_rng(int.from_bytes(key, "big") ^ hs.TEXTURE_SEED)


def _load(path: Path, px: int, mode: str = "RGB") -> np.ndarray:
    with Image.open(path) as image:
        image = image.convert(mode).resize((px, px), Image.LANCZOS)
        return np.asarray(image).astype(np.float32) / 255.0


def _model_map(asset: str, role: str, px: int) -> np.ndarray | None:
    """One of a PolyHaven model's own 2k maps (``diff`` / ``nor_gl`` / ``arm``)."""

    folder = CACHE / asset / "textures"
    if not folder.is_dir():
        raise HearthTextureError(f"missing CC0 model textures for {asset} at {folder}")
    for candidate in sorted(folder.glob(f"{asset}_{role}_*.jpg")) + sorted(
        folder.glob(f"{asset}_{role}_*.png")
    ):
        return _load(candidate, px)
    return None


def _texture_map(asset: str, role: str, px: int) -> np.ndarray:
    folder = CACHE / asset
    for pattern in (f"*_{role}_*.jpg", f"*_{role}_*.png", f"*{role}*.jpg", f"*{role}*.png"):
        hits = sorted(folder.glob(pattern))
        if hits:
            return _load(hits[0], px)
    raise HearthTextureError(f"missing CC0 texture {asset}/{role}")


def _png(array: np.ndarray, mode: str = "RGB") -> bytes:
    data = np.clip(array * 255.0 + 0.5, 0, 255).astype(np.uint8)
    if mode == "L" and data.ndim == 3:
        data = data[:, :, 0]
    buffer = io.BytesIO()
    Image.fromarray(data, mode).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _luma(rgb: np.ndarray) -> np.ndarray:
    return rgb[:, :, 0] * 0.299 + rgb[:, :, 1] * 0.587 + rgb[:, :, 2] * 0.114


def _srgb_to_linear(x: np.ndarray) -> np.ndarray:
    """sRGB display values -> linear light.

    A ``baseColorMap`` byte MEANS an sRGB display value (critic r2, C2-2b), so any
    comparison of one plate's albedo against another's -- B0's probe plate against this
    crust, for instance -- has to happen here, not on the bytes.
    """

    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


#: **The two DATA maps cook at half the base colour's size, and this is a measurement.**
#:
#: r2 took all four maps of all six rocks to 2048 to close design section 8's texel
#: density.  Only ``_b.color`` carries that rule -- ``_r.data`` (roughness) and
#: ``_ao.data`` (occlusion) are low-frequency scalars, and at 1024 over a 20-36 m
#: boulder they still hold 20-36 mm per texel of DATA, which no player can resolve.
#:
#: Two things it buys, both measured this round:
#:
#: * **the engine stops refusing to stream in** (critic r2, C2-5).  Under the design's
#:   own byte model a source went 16.78 MB resident; the two BC4s at 1024 take it to
#:   12.58, i.e. **-4.19 MB per source, -25.2 MB over six**, which is 60 % of the
#:   +41.9 MB overrun r2 handed to B6 -- and it is the streaming pressure that was
#:   producing ``dds mip chain (12) does not match texture (11) ... skipping
#:   stream-in`` on ``namaqualand_boulder_02``'s maps in the control leg.
#: * design section 9's budget goes from 100.7 MB shipped to 75.5.
DATA_MAP_DIVISOR = 2


def _resize(field: np.ndarray, px: int) -> np.ndarray:
    """Area-average a single-channel field down to ``px`` (an exact integer factor)."""

    if field.shape[0] == px:
        return field
    factor = field.shape[0] // px
    if factor < 1 or px * factor != field.shape[0]:
        raise HearthTextureError(f"{field.shape[0]} does not divide down to {px}")
    return field.reshape(px, factor, px, factor).mean(axis=(1, 3))


def _tile(array: np.ndarray, times: int) -> np.ndarray:
    if times <= 1:
        return array
    reps = (times, times, 1) if array.ndim == 3 else (times, times)
    tiled = np.tile(array, reps)
    px = array.shape[0]
    return tiled[:px, :px] if array.ndim == 2 else tiled[:px, :px, :]


def _smooth_noise(px: int, cells: int, rng: np.random.Generator) -> np.ndarray:
    """A periodic value-noise field: bilinear upsample of a ``cells``-square lattice."""

    lattice = rng.random((cells, cells)).astype(np.float32)
    lattice = np.vstack([lattice, lattice[:1]])
    lattice = np.hstack([lattice, lattice[:, :1]])
    ys = np.linspace(0, cells, px, endpoint=False)
    xs = np.linspace(0, cells, px, endpoint=False)
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    ty = (ys - y0)[:, None]
    tx = (xs - x0)[None, :]
    ty = ty * ty * (3 - 2 * ty)
    tx = tx * tx * (3 - 2 * tx)
    a = lattice[np.ix_(y0, x0)]
    b = lattice[np.ix_(y0, x0 + 1)]
    c = lattice[np.ix_(y0 + 1, x0)]
    d = lattice[np.ix_(y0 + 1, x0 + 1)]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def _fbm(px: int, cells: int, octaves: int, rng: np.random.Generator) -> np.ndarray:
    total = np.zeros((px, px), np.float32)
    amplitude = 1.0
    norm = 0.0
    for octave in range(octaves):
        total += amplitude * _smooth_noise(px, cells * (2**octave), rng)
        norm += amplitude
        amplitude *= 0.5
    return total / norm


def _normal_from_height(height: np.ndarray, strength: float = 1.0) -> np.ndarray:
    dzdx = np.roll(height, -1, 1) - np.roll(height, 1, 1)
    dzdy = np.roll(height, -1, 0) - np.roll(height, 1, 0)
    nx = -dzdx * strength
    ny = -dzdy * strength
    nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / length, ny / length, nz / length], -1) * 0.5 + 0.5


def _voronoi_distance(px: int, cells: int, rng: np.random.Generator) -> np.ndarray:
    """Periodic nearest-feature distance in CELL units, 3 x 3 neighbourhood only.

    One jittered site per lattice cell means the nearest site is always in the 3 x 3
    block around a pixel's own cell, so the search is nine vectorised passes instead
    of ``cells**2`` -- the naive form took minutes per 2048-square map.
    """

    step = px / cells
    sites = (np.stack(np.mgrid[0:cells, 0:cells], -1).astype(np.float32) + 0.5) * step
    sites += (rng.random(sites.shape).astype(np.float32) - 0.5) * step * 0.8
    ys, xs = np.mgrid[0:px, 0:px].astype(np.float32)
    cy = np.minimum((ys / step).astype(np.int32), cells - 1)
    cx = np.minimum((xs / step).astype(np.int32), cells - 1)
    best = np.full((px, px), np.inf, np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            iy = (cy + dy) % cells
            ix = (cx + dx) % cells
            sy = sites[iy, ix, 0] + np.where(cy + dy < 0, -px, np.where(cy + dy >= cells, px, 0))
            sx = sites[iy, ix, 1] + np.where(cx + dx < 0, -px, np.where(cx + dx >= cells, px, 0))
            best = np.minimum(best, (ys - sy) ** 2 + (xs - sx) ** 2)
    return np.sqrt(best) / step


#: The largest domain warp, in CELL units, that :func:`_voronoi_two` may be given.
#:
#: **This is a periodicity law, measured.**  The search is a 3 x 3 block around the
#: sample's own lattice cell, so a warp of one cell or more can push the true nearest
#: site outside the block -- and it does so ONLY near the map's borders, where the
#: warp field and the wrap interact.  r3 warped by ``px / 22`` PIXELS for every layer,
#: which is 0.82 cells for the coarsest layer and **1.17 cells for the finest**, and
#: the finished map measured a v-axis wrap step 1.97x its own interior median on the
#: emissive channel: the "straight vertical v-tiling seam" critic r3 saw at 2 m.
#: A warp expressed in CELLS cannot do that, and 0.45 keeps the true site inside the
#: block with room to spare (the site jitter itself is +/- 0.475 of a cell).
WARP_CELL_LIMIT = 0.45


def _voronoi_two(px: int, cells: int, rng: np.random.Generator, warp=None):
    """(F1, F2) nearest and second-nearest site distances, in CELL units, periodic.

    ``warp`` is an optional ``(dy, dx)`` pair of periodic fields in **CELL** units
    (r3 passed pixels; see :data:`WARP_CELL_LIMIT` for why that seamed the map).
    Offsetting the sample point instead of the sites keeps the search local but bends
    every cell boundary, so the lattice stops reading as a lattice.  r2's crust used
    the unwarped form and critic r2's verdict on the night bed was "the cell size is
    close to uniform edge to edge, so it reads as a cracked lava crust".

    The lattice index is taken with ``floor`` and ``%``, never ``clip``: a warped
    sample that lands outside ``[0, px)`` belongs to the cell it actually lands in,
    wrapped, and clipping it to the border cell is what breaks the wrap.
    """

    step = px / cells
    sites = (np.stack(np.mgrid[0:cells, 0:cells], -1).astype(np.float32) + 0.5) * step
    sites += (rng.random(sites.shape).astype(np.float32) - 0.5) * step * 0.95
    # five independent per-SITE attributes, so every chunk can carry its own value, its
    # own tilt, its own ash cover, its own facet rotation and its own facet count --
    # see :func:`_cells`
    attrs = rng.random((cells, cells, 5)).astype(np.float32)
    ys, xs = np.mgrid[0:px, 0:px].astype(np.float32)
    if warp is not None:
        limit = float(max(np.abs(warp[0]).max(), np.abs(warp[1]).max()))
        if limit > WARP_CELL_LIMIT:
            raise HearthTextureError(
                f"domain warp of {limit:.3f} cells exceeds {WARP_CELL_LIMIT}: the nearest "
                "site can fall outside the 3 x 3 search block and the map stops being "
                "periodic (see WARP_CELL_LIMIT)"
            )
        ys = ys + warp[0] * step
        xs = xs + warp[1] * step
    # floor, then wrap: a negative sample belongs to cell -1, not to cell 0
    cy = np.floor(ys / step).astype(np.int64)
    cx = np.floor(xs / step).astype(np.int64)
    first = np.full((px, px), np.inf, np.float32)
    second = np.full((px, px), np.inf, np.float32)
    near = np.zeros((px, px, 5), np.float32)
    off = np.zeros((px, px, 2), np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            gy = cy + dy
            gx = cx + dx
            iy = gy % cells
            ix = gx % cells
            # the site's position in the sample's own (unwrapped) frame
            sy = sites[iy, ix, 0] + np.floor_divide(gy, cells).astype(np.float32) * px
            sx = sites[iy, ix, 1] + np.floor_divide(gx, cells).astype(np.float32) * px
            d = (ys - sy) ** 2 + (xs - sx) ** 2
            second = np.minimum(second, np.maximum(first, d))
            win = d < first
            near = np.where(win[:, :, None], attrs[iy, ix], near)
            off = np.where(win[:, :, None], np.stack([(ys - sy) / step, (xs - sx) / step], -1), off)
            first = np.minimum(first, d)
    return np.sqrt(first) / step, np.sqrt(second) / step, near, off


def _cells(px: int, cells: int, rng: np.random.Generator, warp=None) -> dict[str, np.ndarray]:
    """A cellular field with PER-CHUNK identity, which is what makes it read as coal.

    r3a and r3b both drew a correct Voronoi tessellation and both read as cracked dry
    mud, because every cell had the same albedo, the same height and the same tilt --
    only the boundaries differed.  A bed of charcoal is a PILE OF SEPARATE LUMPS: each
    one is its own value, sits at its own angle, and carries its own dusting of ash.
    Those three per-site attributes are what this returns alongside the distances.
    """

    f1, f2, near, off = _voronoi_two(px, cells, rng, warp)
    # --- the facet radius: a CHIP, not a pebble (critic r3, "Taste") ------------------
    # Critic r3 saw "several perfect circles -- un-eroded hemisphere footprints" at 2 m
    # and named the round silhouette as one of r4's three jobs.  Adding noise to a
    # circular distance field erodes its edge but leaves it a circle underneath; a lump
    # of charcoal is not an eroded ball, it is a FRACTURED SOLID with flat faces.
    #
    # The support function of a regular n-gon of inradius rho is rho / cos(a), where a
    # is the angle to the nearest facet normal.  So scaling the radial distance by
    # cos(a) / cos(pi/n) turns every level set of ``f1`` from a circle into a regular
    # n-gon inscribed in it -- exactly, with no extra sampling -- and the per-site
    # attributes give every chunk its own facet count (4-7) and its own rotation, so no
    # two lumps share an outline.  The noise that r3 added on top still ragged-edges it;
    # what changed is what it is raggeding.
    theta = np.arctan2(off[:, :, 0], off[:, :, 1])
    sides = np.floor(4.0 + near[:, :, 4] * 4.0)  # 4, 5, 6 or 7 facets
    sector = 6.283185307179586 / sides
    angle = np.mod(theta + near[:, :, 3] * 6.283185307179586, sector) - sector * 0.5
    facet = np.cos(angle) / np.cos(sector * 0.5)
    return {
        "f1": f1,
        "f2": f2,
        "gap": f2 - f1,
        "facet_r": f1 * facet,
        "sides": sides,
        "value": near[:, :, 0],
        "ash_bias": near[:, :, 1],
        # a plane across each cell, from its own third attribute: the chunk's tilt
        "tilt": (
            off[:, :, 0] * np.cos(near[:, :, 2] * 6.2832)
            + off[:, :, 1] * np.sin(near[:, :, 2] * 6.2832)
        ),
    }


def _smoothstep(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _blur(field: np.ndarray, sigma_px: float) -> np.ndarray:
    """Periodic Gaussian blur by FFT -- wraps exactly, so a tiling map stays tiling."""

    n = field.shape[0]
    freq = np.fft.fftfreq(n).astype(np.float32)
    kernel = np.exp(-2.0 * (np.pi * sigma_px) ** 2 * (freq[:, None] ** 2 + freq[None, :] ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(field) * kernel)).astype(np.float32)


def _tiled_model_map(asset: str, role: str, px: int, times: int) -> np.ndarray:
    """One PolyHaven MODEL's map, repeated ``times`` across a ``px`` map.

    :func:`_tiled_source` does this for the flat CC0 textures; the detail donor of a stone
    slot (r7, ``hearth_spec.STONE_DETAIL_DONOR``) is a MODEL folder, whose maps live under
    ``<asset>/textures/``.  Loading at ``px // times`` first is not a loss -- that is all
    the detail one tile of the finished map can hold.
    """

    if px % times:
        raise HearthTextureError(
            f"{asset}/{role}: {times} tiles does not divide {px}, so the detail layer "
            "would stop being periodic and the map would seam"
        )
    source = _model_map(asset, role, max(px // times, 16))
    if source is None:
        raise HearthTextureError(f"detail donor {asset} has no {role} map")
    return np.tile(source, (times, times, 1))


def _high_pass(field: np.ndarray, sigma_px: float) -> np.ndarray:
    """What is left of a field above ``sigma_px`` -- the grain, with the body removed."""

    return field - _blur_rgb(field, sigma_px)


def _blur_rgb(field: np.ndarray, sigma_px: float) -> np.ndarray:
    if field.ndim == 2:
        return _blur(field, sigma_px)
    return np.stack(
        [_blur(field[:, :, c], sigma_px) for c in range(field.shape[2])], axis=2
    ).astype(np.float32)


def _attenuate_low_frequency(field: np.ndarray, sigma_px: float, gain: float) -> np.ndarray:
    """Keep the mean, keep everything finer than ``sigma_px``, scale the rest by ``gain``.

    r7 (critic C6-1): the 36 m slot magnifies a 0.32 m scan 112x, so the scan's own colour
    variation arrives as blotches metres across.  This halves the part that magnification
    pushed past plausibility without touching the stone's own body or its mean colour.
    """

    low = _blur_rgb(field, sigma_px)
    mean = field.reshape(-1, field.shape[2]).mean(axis=0)[None, None, :]
    return np.clip(mean + gain * (low - mean) + (field - low), 0.0, 1.0)


def _graft_normal(base: np.ndarray, donor: np.ndarray, sigma_px: float, gain: float) -> np.ndarray:
    """Add the donor's high-frequency SLOPE to the body's own normal, then renormalise."""

    b = base * 2.0 - 1.0
    d = donor * 2.0 - 1.0
    xy = b[:, :, :2] + gain * _high_pass(d[:, :, :2], sigma_px)
    z = np.sqrt(np.clip(1.0 - np.clip(xy[:, :, 0] ** 2 + xy[:, :, 1] ** 2, 0.0, 0.998), 0.0, 1.0))
    return np.clip(np.dstack([xy, z]) * 0.5 + 0.5, 0.0, 1.0)


def _tiled_source(asset: str, role: str, px: int, times: int) -> np.ndarray:
    """A CC0 source repeated ``times`` across a ``px`` map at its own physical scale.

    :func:`_tile` crops back to its INPUT size (it raises a map's own frequency); this
    grows one to ``px``.  Loading the source at ``px // times`` first is not a loss --
    that is all the detail a tile of the finished map can hold.
    """

    if px % times:
        raise HearthTextureError(
            f"{asset}/{role}: {times} tiles does not divide {px}, so the "
            "map would stop being periodic and the plate would seam"
        )
    source = _texture_map(asset, role, max(px // times, 16))
    return np.tile(source, (times, times, 1))


# --- the six rock heroes -------------------------------------------------------------
def cook_rock(asset: str) -> dict[str, bytes]:
    """``diff`` -> baseColor, ``nor_gl`` -> normal, ``arm`` -> AO/roughness.

    PolyHaven models ship an ORM-style ``arm`` map (AO / Roughness / Metallic in
    R / G / B), which is exactly the two data maps a v1.5 material wants, so nothing
    is invented: the roughness is lifted a little where the model is darkest (soot
    is matte) and the albedo gets a slight desaturation toward granite.
    """

    px = _check_px(int(hs.STONE_SOURCES[asset]["map_px"]), f"{asset} rock hero")
    name = hs.stone_material(asset)
    # r6: the maps come from the SCAN the slot is derived from, the file names from the
    # slot itself (hearth_spec.stone_source_folder)
    folder = hs.stone_source_folder(asset)
    diffuse = _model_map(folder, "diff", px)
    normal = _model_map(folder, "nor_gl", px)
    arm = _model_map(folder, "arm", px)
    if diffuse is None:
        raise HearthTextureError(f"{asset}: no diffuse map in the CC0 cache")
    if normal is None:
        normal = _normal_from_height(_luma(diffuse), 4.0)
    if arm is None:
        occlusion = np.clip(_luma(diffuse) * 1.2, 0, 1)
        roughness = np.clip(1.0 - _luma(diffuse) * 0.5, 0.2, 1.0)
    else:
        occlusion = arm[:, :, 0]
        roughness = arm[:, :, 1]
    # r7 (critic C6-1): the detail graft.  Only a slot that DECLARES a donor takes it, so
    # the other five stones cook byte-for-byte as they did in r6.  Every constant, and the
    # measurement that set it, is in `hearth_spec.STONE_DETAIL_DONOR`'s docstring.
    donor_folder = hs.stone_detail_donor(asset)
    if donor_folder:
        tiles = int(hs.DETAIL_TILES)
        sigma = float(hs.DETAIL_SIGMA_PX)
        d_diff = _tiled_model_map(donor_folder, "diff", px, tiles)
        d_norm = _tiled_model_map(donor_folder, "nor_gl", px, tiles)
        d_arm = _tiled_model_map(donor_folder, "arm", px, tiles)
        # 1. the base colour's magnified low frequencies, halved
        diffuse = _attenuate_low_frequency(
            diffuse, float(hs.DETAIL_BASE_LF_SIGMA_PX), float(hs.DETAIL_BASE_LF_GAIN)
        )
        # 2. the donor's grain, multiplicatively -- hue and value stay the body's, and a
        #    dark part of the stone stays dark
        grain = _high_pass(_luma(d_diff), sigma)[:, :, None]
        diffuse = np.clip(diffuse * (1.0 + float(hs.DETAIL_COLOUR_GAIN) * grain), 0.0, 1.0)
        normal = _graft_normal(normal, d_norm, sigma, float(hs.DETAIL_NORMAL_GAIN))
        occlusion = np.clip(
            occlusion + float(hs.DETAIL_AO_GAIN) * _high_pass(d_arm[:, :, 0], sigma), 0.0, 1.0
        )
        # 3. a CONSTANT roughness is a placeholder, not a measurement: take the donor's,
        #    keeping ITS variation and placing it at the ring's own measured level so the
        #    darkness lift below cannot clip it into a uniform matte sheet
        if float(np.std(roughness)) < float(hs.ROUGHNESS_DEGENERATE_STD):
            donor_rough = d_arm[:, :, 1].astype(np.float32)
            spread = float(donor_rough.std()) or 1.0
            lift_mean = float(((1.0 - _luma(diffuse)) * 0.18).mean())
            roughness = (donor_rough - float(donor_rough.mean())) / spread * float(
                hs.DETAIL_ROUGHNESS_TARGET_STD
            ) + (float(hs.DETAIL_ROUGHNESS_TARGET_MEAN) - lift_mean)
    grey = _luma(diffuse)[:, :, None]
    albedo = np.clip(diffuse * 0.75 + grey * 0.25, 0, 1)
    matte = np.clip(roughness + (1.0 - grey[:, :, 0]) * 0.18, 0.05, 1.0)
    data_px = _check_px(px // DATA_MAP_DIVISOR, f"{asset} data maps")
    return {
        f"{name}_b.color.png": _png(albedo),
        f"{name}_nm.normal.png": _png(normal),
        f"{name}_r.data.png": _png(_resize(matte, data_px)[:, :, None].repeat(3, 2), "L"),
        f"{name}_ao.data.png": _png(_resize(occlusion, data_px)[:, :, None].repeat(3, 2), "L"),
    }


# --- the ember crust -----------------------------------------------------------------
#: sRGB display values, because that is what the byte in ``_b.color.png`` MEANS to the
#: engine: :func:`_png` writes ``array * 255`` and the engine decodes a ``baseColorMap``
#: as sRGB (critic r2, C2-2b).  r2 authored these as if they were linear, which is one of
#: the two reasons the day crust shipped as a saturated sheet.
#:
#: **r4 re-grade, and it is B0's own plate that sets these.**  Critic r3 read B0's probe
#: plate out of B0's shipped bytes: albedo **sRGB 0.0585** (range 0.041-0.081), linear
#: mean **0.00549**, carrying an emissive mask at **32.5 %** coverage.  That plate read
#: 2.9-3.1x red excess against itself with the emissive removed, AND it is what the
#: design's words describe -- "black-red coal", "red lumps, not a bright surface".  r3
#: shipped an albedo **7.24x brighter in linear light** (0.03972) with a 0.48 % emissive
#: mask and read 1.346, and the frames showed why: grey cobbles with glowing grout.
#:
#: **r4 booted three grades of these constants on the sentinel and kept every frame set**
#: (``b2/r4/albedo_trade.py``, which re-derives each one offline from its own archived
#: frames because the leg report is overwritten by the next boot).  Nothing else differed
#: between them -- same mask, same lights, same cut procedure:
#:
#: ==================  ==========  ==========  ==========  ==========
#: albedo linear mean  0.03972 r3  0.01303     0.01037     0.00805
#: section 8 crust/slab   1.0057   0.9465      SHIPPED     1.2524
#: B0's own instrument     1.346   1.8548      SHIPPED     6.7632
#: ==================  ==========  ==========  ==========  ==========
#:
#: Both readings move the SAME way as the char goes black, which is critic r3's C3-2
#: ruling measured rather than argued.  The trade that IS real is a different and smaller
#: one: below about 0.009 linear the bed stops being readable at the S4 driver's eye (its
#: near band fell to luma 11.3 against r3's 63.0).  These constants sit at the darkest
#: grade that still reads, and the numbers it buys are published beside the darker one.
#:
#: There was never a conflict between the ratio and the art direction; r3 moved away
#: from both at once.  These constants move back toward B0's plate.
CRUST_CHARCOAL_DARK = (0.038, 0.034, 0.0325)
CRUST_CHARCOAL_LIGHT = (0.122, 0.1075, 0.0985)
#: wood ash in shadow is a WARM MID GREY, not a highlight.  r3's 0.412 pale ash on the
#: lump tops is the "grey river cobbles" read, and it was 46 % of the plate.
CRUST_ASH = (0.2715, 0.255, 0.2395)
CRUST_ASH_WARM = (0.206, 0.175, 0.1485)
#: The SCORCH on the char around a live pocket -- a hint, not a colour.  B0's reference
#: plate carries no red in its albedo at all (0.041-0.081, flat): every bit of its
#: 2.9-3.1x red excess comes from the emissive stage.  r2 put red under the whole plate
#: and shipped a brick sheet; r3 kept a strong tint on a tiny mask.  r4 keeps the tint
#: small enough that the albedo stays black char and lets the emissive carry the red.
CRUST_HOT_TINT = (0.150, 0.040, 0.012)

#: **How much of the bed is open to its own heat.**  The midpoint of the ember mask's
#: threshold: LOWER lights more of the bed.  This is the one knob in the cook that was
#: chosen by a measured sweep rather than by taste, because it is the knob that decides
#: between the round's two failure modes -- r2's lava field at 0.338 coverage and r3's
#: glowing grout at 0.037.  ``b2/r4/coverage_sweep.py`` cooks the crust at five values,
#: renders the same driver's-eye frame from each, and publishes the panel and the
#: numbers; ``b2/r4/coverage_sweep.json`` is the record.
#:
#: The scale it is chosen on is the round's own history, measured off the shipped frames
#: (``b2/r4/frame_ember_fraction.json``): the fraction of the near bed whose red excess
#: clears 40/255 reads **0.777** in r2's judged S4 day frame (rejected: "a saturated
#: brick-red sheet") and **0.058** in r3's (rejected: "grey cobbles with orange grout").
#: The offline preview reproduces r3's day frame at 0.050 against its real 0.058, so it
#: predicts the real frame to about 16 %.
#:
#: 0.42 opens **28.2 %** of the plate above an emissive of 0.05, against r3's 3.7 % and
#: r2's 33.8 %, and the sentinel returns a day bed at 0.20 -- three and a half times r3
#: and nearly four times less than r2.  How BRIGHT that lit share is is a separate knob
#: (``CRUST_EMBER_PEAK`` / ``GAMMA``), which is the distinction r1 through r3 never made.
CRUST_EMBER_OPEN = 0.42

#: **How hot the lit part is**, as against how much of the bed is lit.
#:
#: These two are what the round has been missing.  Coverage and brightness were one
#: knob in r1, r2 and r3, so every attempt to make the bed read as coals moved both and
#: landed on lava or on gravel.  Measured across r3's and r4's first boots of the same
#: scene, the two effects separate cleanly:
#:
#:     night bed clipped to white  ~=  0.43 x frac(emissive > 0.5)
#:     day bed with red excess >40 ~=  0.71 x frac(emissive > 0.05)
#:
#: r4's first cook shipped ``frac > 0.5 = 0.143`` and burned **6.2 %** of the night bed
#: to white (r3: 0.5 %, r2: 0.7 %) -- the white-hot lava field this round has rejected
#: twice.  Dividing the heat field by ``PEAK`` rather than clipping it, then applying
#: ``GAMMA``, holds the day coverage and collapses the night's blown top.
#: ``FLOOR`` is what keeps the two knobs genuinely independent: every pixel the mask
#: opens glows at least this much, so the day coverage follows the MASK and the gamma is
#: free to collapse the night's top end without also switching the dull coals off.
CRUST_EMBER_FLOOR = 0.17
CRUST_EMBER_PEAK = 1.80
CRUST_EMBER_GAMMA = 3.00


def cook_crust() -> dict[str, bytes]:
    """Black-red coal: ``burned_ground_01`` luminance inverted + a Voronoi lump mask.

    The emissive map is the LUMP-CORE mask, not the whole plate: B0 measured that a
    2500-nit horizontal plate reads only 1.12-1.20x the control's luma at golden
    hour but 2.9-3.1x its red excess, so the crust must read as RED LUMPS.  Tuning
    happens on the mask's contrast and the emissive factor's red, never on the nits.

    **r3 re-cook: it was a lava field, and this makes it a coal bed.**  Critic pass 2's
    ruling on r2's map was that the night bed "reads as lava, not a campfire -- no ash,
    uniform cells, and it lights none of its own stones", and that by day it is "a
    saturated brick-red sheet with visible tiling and a hard cut edge".  Every one of
    those is a property of THIS function, so this is where they are fixed.

    Five changes, and each one answers a named defect:

    1. **The map's U axis is now the RADIUS.**  ``blender_hearth.CRUST_UV_TILES`` moved
       the plate to *one* radial tile and two tangential ones, so column ``x`` of every
       map is a fixed radius between 176 and 199 m.  ``bank`` is that profile: ash and
       cold at BOTH rims, hot in the middle.  This is what a banked bed of coals does,
       it is the only way a tiling map can know where the edge of the bed is, and it
       feathers the hard cut line the critic saw at r 199 -- from both sides, so it does
       not depend on which rim column 0 lands on.
    2. **Ash.**  ~40 % of the plate is now wood ash: pale warm grey, no ember under it,
       its own soft powder height.  It drifts at ~8 m, settles on the lump TOPS and out
       of the fissures, and thickens toward the rims.  r2 had none -- its 6 % "dead
       patches" were flat grey blobs with no structure, which is why they read as
       missing texture rather than as burnt-out crust.
    3. **Charcoal, not red.**  r2's albedo had ``coal * 0.235`` of RED under the whole
       plate, so every pixel was red before anything else happened.  The base is now
       black charcoal and the only red in the albedo is a warm tint ON the hot cracks.
    4. **The lattice is domain-warped and two-scale.**  Chunks (~0.9 m) and gravel
       (~0.4 m) with a low-frequency field deciding which is in charge, both warped, so
       the cell size stops being uniform edge to edge.
    5. **The glow lives or dies by region.**  ``heat`` is a 2-cell fBm -- ~12 m patches
       -- with real contrast, multiplied by ``bank`` and by ``1 - ash``.  Parts of the
       ring are properly out.

    **r4: the look and the number were never in conflict, and this cook chases both.**

    r3's docstring said "B0 measured the 2.5 on a fully emissive plate, not on an
    albedo", and used that to publish design section 8 as a miss it had chosen.  Critic
    r3 read B0's shipped bytes and the sentence is FALSE.  B0's probe plate is:

    ======================  ==============  ==============
    ..                      B0's plate      r3's crust
    ======================  ==============  ==============
    albedo, linear mean     0.00549         0.03972  (7.24x brighter)
    albedo, sRGB mean       0.0585          0.1932
    emissive map mean       0.3098          0.0076
    emissive > 0.5          32.50 %          0.48 %
    the control             the same quad, emissive stage removed
    ======================  ==============  ==============

    So B0's own reference is a **black char albedo carrying a strong, masked emissive**
    -- it satisfies the design's art direction ("black-red coal", "red lumps, not a
    bright surface") and the 2.9-3.1 ratio AT THE SAME TIME.  r3 moved away from both
    at once: it cut the emissive mask 9.3x and lifted the albedo, and the frames read as
    grey cobbles with glowing grout.  r4 rebuilds the plate B0's way -- albedo an order
    of magnitude darker, mask coverage back in B0's band -- and expects the ratio and
    the picture to move together, because they are the same lever.

    The real defect in section 8 is a different one, and it belongs to B6: its 2.5x is a
    threshold **transplanted** from an emissive-on/off comparison on ONE plate onto a
    crust-versus-hearth-slab comparison between two different surfaces, and that
    comparison was never validated at any value.  B2's like-for-like number -- the same
    instrument B0 used, this crust against itself with the emissive removed -- is the
    one to judge the cook by.
    """

    px = _check_px(hs.CRUST_MAP_PX, "ember crust")
    name = hs.crust_material()
    rng = _rng("crust", px)
    # The char and grain sources are TILED 8x inside the map, not stretched across it.
    # One 2048 tile is now 23 x 24.5 m of annulus (see the UV note above); burned ground
    # stretched over 24.5 m carries no structure at all, and a bed of charcoal whose
    # only structure is a Voronoi lattice reads as paving slabs -- which is exactly what
    # r3c rendered.  8 tiles puts the source back at its own ~3 m scale.
    char_tiles = 8
    char = _tiled_source("burned_ground_01", "diff", px, char_tiles)
    char_disp = _tiled_source("burned_ground_01", "disp", px, char_tiles)
    grain = _tiled_source("snow_02", "diff", px, 16)
    char_l = _luma(char)
    char_h = _luma(char_disp)

    # --- the radial profile: column x IS the radius, once across the plate ---------
    xs = np.mgrid[0:px, 0:px][1].astype(np.float32) / px
    # jitter the rim line so the bed's edge is not a machined circle
    rim_break = _fbm(px, 7, 3, _rng("crust", "rim", px)) - 0.5
    edge = np.minimum(xs, 1.0 - xs) * 2.0 + rim_break * 0.22
    bank = _smoothstep(edge, 0.02, 0.46)

    # --- the pile: four scales of faceted CHIP, composited by max -------------------
    # This is the change that stopped it reading as paving.  A Voronoi tessellation
    # partitions the plane -- every pixel belongs to exactly one cell and the cells
    # share a connected graph of boundaries, which is the visual signature of crazy
    # paving (r3a-r3d, all four rejected on this).  A bed of charcoal is a PILE:
    # lumps of four different sizes dropped on top of each other, the big ones
    # occluding the small ones, and the gaps between them irregular and DISCONNECTED.
    # Compositing them with ``max`` gives exactly that, and it gives occlusion
    # for free -- whichever lump is tallest here owns the pixel and its identity.
    #
    # r4 changes two things about the lumps themselves.  The warp is in CELL units
    # (see ``WARP_CELL_LIMIT``: r3's pixel warp was 1.17 cells at the finest layer and
    # it seamed the map).  And each lump's footprint is a FACET POLYGON, not a circle
    # (see ``_cells``): critic r3 counted "several perfect circles -- un-eroded
    # hemisphere footprints" at 2 m, and round outlines plus flat disc tops is the
    # other half of the cobble read.
    warp_y = (_fbm(px, 3, 3, _rng("crust", "wy", px)) - 0.5) * 0.80
    warp_x = (_fbm(px, 3, 3, _rng("crust", "wx", px)) - 0.5) * 0.80
    #: (cells, footprint radius in cell units, amplitude) -- one tile is 23.000 m in u
    #: (the radius) by 24.544 m in v, so 21 cells is a **1.169 m** chunk on its long
    #: axis and 76 cells a **0.303 m** cinder: inside the design's 0.3-1.2 m lump band
    #: on BOTH axes.  (r3 published 0.303-1.278 and called it inside the band; 1.278 is
    #: 6.5 % over, and it was over on the short axis too -- critic r3 D8.)
    layers = ((21, 0.56, 1.00), (32, 0.54, 0.88), (49, 0.52, 0.74), (76, 0.50, 0.58))
    pile = np.zeros((px, px), np.float32)
    chunk_val = np.zeros((px, px), np.float32)
    chunk_ash = np.zeros((px, px), np.float32)
    chunk_tilt = np.zeros((px, px), np.float32)
    lump_r = np.ones((px, px), np.float32)
    # charcoal breaks along the grain: a lump is angular and ragged, never a pebble.
    # This is added to each layer's facet field, so it eats into the silhouette.
    ragged = _fbm(px, 90, 3, _rng("crust", "ragged", px)) - 0.5
    chip = _fbm(px, 34, 4, _rng("crust", "chip", px)) - 0.5
    for index, (n, span, amp) in enumerate(layers):
        scale = 1.0 - index * 0.16
        layer = _cells(px, n, _rng("crust", "pile", index, px), (warp_y * scale, warp_x * scale))
        radius = layer["facet_r"] / span + ragged * (0.30 + 0.09 * index) + chip * 0.22
        # a faceted chunk, not a hemisphere: flat-ish top, steep flanks, hard rim.  The
        # exponent pair is what a fractured solid looks like in section -- ``sqrt`` (a
        # hemisphere) puts most of its height change at the RIM, which is what draws a
        # round outline in the normal map even after the footprint is a polygon.
        dome = np.clip(1.0 - np.clip(radius, 0, 4) ** 2.7, 0, 1) ** 0.55
        # every lump also gets its own HEIGHT, so some sit deep in the bed
        cand = dome * amp * (0.20 + 1.05 * layer["value"])
        win = cand > pile
        chunk_val = np.where(win, layer["value"], chunk_val)
        chunk_ash = np.where(win, layer["ash_bias"], chunk_ash)
        chunk_tilt = np.where(win, layer["tilt"] * (0.62 - index * 0.11), chunk_tilt)
        lump_r = np.where(win, radius, lump_r)
        pile = np.maximum(pile, cand)
    fine = _fbm(px, 16, 4, rng)
    grit = _fbm(px, 42, 3, _rng("crust", "grit", px))
    # the gaps are where NO lump reaches -- pockets, not a graph
    crack = _smoothstep(pile, 0.52, 0.10)
    # the lower FLANK of a chunk, just above the gap floor: a coal bed is red down the
    # sides of its lumps as well as between them, and confining the glow to the empty
    # gaps alone is half of what drew "glowing grout between cobbles" in r3.  Kept
    # narrow on purpose -- r4a opened it to (0.78, 0.16), 42 % of the plate lit, and the
    # preview went straight back to a connected lava net.
    flank = _smoothstep(pile, 0.62, 0.30)
    lump = np.clip(1.0 - lump_r, 0, 1)

    # --- ash: drifts and hollows, NOT a cap on every lump --------------------------
    lump_top = _smoothstep(pile, 0.30, 0.85)
    drift = _fbm(px, 3, 4, _rng("crust", "ash", px))
    # r3 put ``lump_top * 0.30`` INTO the ash mask, so the pale grey landed on the
    # rounded caps of the chunks -- pale rounded caps on dark ground is the definition
    # of a cobbled surface, and critic r3 called it the dominant read of the design's
    # own hero frame.  r4 inverts the term: the opaque ash sits in the HOLLOWS and
    # drifts and against the rims, where wind and gravity actually put it, and the lump
    # tops carry only the thin veil ``cover`` allows below.  Coverage falls with it.
    ash = _smoothstep(
        drift * 0.66
        + chunk_ash * 0.72
        + (1.0 - lump_top) * 0.26
        + grit * 0.18
        + (char_h - 0.5) * 0.34
        - crack * 0.55
        - bank * 0.30,
        0.66,
        1.06,
    )

    # --- heat: which parts of this bed are still alive -----------------------------
    # 2 cells over a 23 m tile is ~12 m, and the contrast is deliberately hard: a bed
    # this size is not uniformly alive, and r2's near-constant heat is what made the
    # 200 m ring read as one lit strip.  r4 widens the live share, because r3's 3.7 %
    # emissive coverage is what made the ring read as gravel at 100 m and what put the
    # like-for-like emissive ratio at 1.346 against B0's 2.9-3.1 on a 32.5 % mask.
    heat = _smoothstep(_fbm(px, 2, 3, _rng("crust", "heat", px)), 0.34, 0.70)
    heat = heat * bank * (1.0 - ash)

    # --- height: every chunk sits at its own level, its own angle, its own knobs ----
    coal_h = np.clip(
        pile * 0.58
        + chunk_tilt * 0.16
        + (char_h - 0.5) * 0.46
        + (grit - 0.5) * 0.16
        + fine * 0.10
        + 0.18,
        0,
        1,
    )
    ash_h = np.clip(0.36 + drift * 0.20 + grit * 0.12 + (char_h - 0.5) * 0.16, 0, 1)
    height = coal_h * (1.0 - ash * 0.70) + ash_h * (ash * 0.70)
    height = np.clip(height * (0.30 + 0.70 * bank) + (1.0 - bank) * 0.12, 0, 1)

    # --- albedo: black charcoal, dark ash, and red ONLY on what is glowing ----------
    # The whole plate now lives between sRGB 0.03 and 0.24 with a linear mean an order
    # of magnitude below r3's, because that is what B0's own reference plate is and
    # what the design's words ask for.  The char texture at its own scale carries the
    # value variation and the chunk id carries the chunk-to-chunk step.
    char_v = np.clip((char_l - 0.20) / 0.40, 0, 1)
    char_mix = np.clip(
        char_v * 0.64 + chunk_val * 0.42 + chunk_tilt * 0.14 + (char_h - 0.5) * 0.24 - 0.12, 0, 1
    )[:, :, None]
    dark = np.array(CRUST_CHARCOAL_DARK, np.float32)
    light = np.array(CRUST_CHARCOAL_LIGHT, np.float32)
    charcoal = dark + (light - dark) * char_mix**1.4
    ash_cold = np.array(CRUST_ASH, np.float32)
    ash_warm = np.array(CRUST_ASH_WARM, np.float32)
    ash_col = ash_cold + (ash_warm - ash_cold) * np.clip(1.0 - drift * 1.25, 0, 1)[:, :, None]
    ash_col = ash_col * (0.72 + 0.44 * _luma(grain)[:, :, None])
    # a DUSTING, not a coat: even the deepest drift lets some char through, and the
    # char texture's own grain breaks the ash up so it reads as powder
    cover = np.clip(ash * (0.70 + 0.26 * grit) * (0.76 + 0.26 * char_v), 0, 0.82)[:, :, None]
    albedo = charcoal * (1.0 - cover) + ash_col * cover

    # --- emissive: a hard MASK on the live part of the bed, not a wash --------------
    # Critic r3's decisive finding: B0's reference plate reads 2.9-3.1x with an
    # emissive mask at **32.5 % coverage, mean 0.3098**, over an albedo 7.2x darker
    # than r3 shipped -- so the ratio and the art direction were never in conflict, and
    # r3's 0.48 % mask was simply too small to be a campfire.  r4 rebuilds the mask the
    # way B0's is built: nearly binary, high value, and covering the low quarter of the
    # bed.  ``broken`` still decides which stretches have closed over, so the glow is
    # pockets and channels rather than a connected lava net.
    #
    # ``broken`` is also what keeps the glow DISCONNECTED, and r4's sweep is where that
    # became measurable.  The space between the lumps is by construction a connected
    # network -- it is the complement of the footprints -- so widening the mask along it
    # rebuilds r2's "fully connected orange cell network" no matter how black the char
    # is.  r3's answer was to light only the deepest holes (3.7 %).  r4's is to CHOP the
    # network: ``broken`` runs at ~0.9 m and ~0.4 m instead of r3's ~3 m, so every
    # channel is cut into pocket-length segments and the bed reads as separate coals at
    # four times r3's coverage.  ``b2/r4/pocket_stats.py`` counts the components.
    broken = _smoothstep(
        _fbm(px, 26, 3, _rng("crust", "break", px)) * 0.58
        + _fbm(px, 58, 2, _rng("crust", "break2", px)) * 0.26
        + fine * 0.16
        + chunk_val * 0.12,
        0.42,
        0.64,
    )
    # WHERE the bed is open to its own heat: the gaps, the lower flanks of the chunks
    # and the shoulders between them.  Wider than r3's gaps-only mask by design -- r3's
    # 3.7 % lit the joints and nothing else, which is what drew "glowing grout".
    open_bed = np.clip(
        crack * (0.30 + 1.20 * broken) + flank * (0.15 + 0.85 * broken) * 0.58 + lump**4.0 * 0.06,
        0,
        1,
    )
    # a hard edge, because a coal is lit or it is not and a soft ramp between the two
    # is what reads as molten rock
    mask = _smoothstep(open_bed, CRUST_EMBER_OPEN - 0.15, CRUST_EMBER_OPEN + 0.15)
    # HOW HOT it is there.  A bed of coals has an enormous value range -- a few pockets
    # white-orange, most a deep dull red, and whole stretches out.  B0's own mask has
    # the same shape (57 % over 0.1, 32.5 % over 0.5, mean 0.31), and a binary mask at
    # full value over the same area is a lava net instead -- which is what the r4a
    # preview drew.  ``ember`` is regional (``heat``, ~12 m) times a ~2.5 m field, so
    # the hot spots cluster the way a real fire's do.
    #
    # **The exponent and the divisor here were measured on the sentinel, not chosen.**
    # r4's first boot cooked this field with a hard ``clip(..., 0, 1)``, which parked a
    # large share of the lit bed at exactly 1.0.  The shipped map read ``frac > 0.5 =
    # 0.1434`` and the night frames came back with **6.2 % of the near bed clipped to
    # white** (r3: 0.5 %) -- a white-hot lava field, the exact failure the round has
    # twice rejected.  Two boots of the same scene give the transfer:
    #
    #     night pixels above luma 240  ~=  0.43 x frac(emissive > 0.5)
    #     day pixels with red excess > 40  ~=  0.71 x frac(emissive > 0.05)
    #
    # (r3: 0.00954 -> 0.005 clipped, 0.037 -> 0.058 red; r4a: 0.1434 -> 0.0618,
    # 0.311 -> 0.221.  Both fit to within a few per cent.)  So the two things the bed
    # needs are INDEPENDENT knobs on this one field: coverage above 0.05 sets how much
    # of the day bed reads red, and coverage above 0.5 sets how much of the night bed
    # burns out.  Dividing by ``CRUST_EMBER_PEAK`` instead of clipping, and raising the
    # result to ``CRUST_EMBER_GAMMA``, keeps the first and collapses the second.
    hotspot = _fbm(px, 9, 3, _rng("crust", "hotspot", px))
    raw = 0.16 + 1.35 * heat * (0.30 + 0.85 * hotspot)
    ember = CRUST_EMBER_FLOOR + (1.0 - CRUST_EMBER_FLOOR) * (
        np.clip(raw / CRUST_EMBER_PEAK, 0.0, 1.0) ** CRUST_EMBER_GAMMA
    )
    core = np.clip(mask * ember, 0.0, 1.0)

    # THE HALO -- a hot pocket throws warm light onto the coal faces around it, and an
    # emissive material lights nothing in this engine, so the near-field bounce has to
    # be BAKED.  It is a blurred copy of the core, weighted by how reflective the
    # surface is (ash picks up more of it than black char, exactly as a real bounce
    # would) and strongest low in the bed where the pockets are.  ~0.25 m at this UV.
    #
    # **What it is NOT** (critic r3, D5): it is not what lights the stones.  It is
    # baked into the bed's own albedo and cannot light anything off the bed at all --
    # the ember PointLights do that.  r3's change list credited it with answering "the
    # bed lights nothing" and that credit was wrong.  What it does is make the bed's
    # own surface read as lit BY the pockets rather than as a set of glowing decals.
    surface_l = _luma(albedo)
    halo = _blur(core, px * 0.011) * (0.22 + 1.05 * surface_l) * (0.45 + 0.75 * (1.0 - lump_top))
    emissive = np.clip(core + halo * 0.85, 0.0, 1.0)

    # the red in the ALBEDO belongs only on what is actually glowing, plus a short
    # scorch halo around it -- not under the whole plate the way r2 had it
    hot = np.clip(core * 1.1 + halo * 0.8, 0, 1)
    albedo = np.clip(albedo + np.array(CRUST_HOT_TINT, np.float32) * hot[:, :, None], 0, 1)
    # ash is a powder (very matte), cold char is matte, and the glassy floor of a live
    # pocket has real sheen -- critic r3's taste note was that 0.58-0.97 across the
    # whole map is uniformly matte and the material never reads
    roughness = np.clip(0.66 + ash * 0.28 - hot * 0.34 + (grit - 0.5) * 0.10, 0.30, 0.98)
    emissive_rgb = np.stack([emissive, emissive * 0.42, emissive * 0.10], -1)
    red_excess = albedo[:, :, 0] - (albedo[:, :, 1] + albedo[:, :, 2]) / 2.0
    # the crust's roughness map cooks at half size like every other data map (critic r3
    # D4: it was the one 2048 ``_r.data`` left in the hearth, ~2.1 MB that can never
    # stream past 1024 on either profile at ``GraphicTextureQuality: "Normal"``)
    rough_px = max(px // DATA_MAP_DIVISOR, 16)
    return {
        f"{name}_b.color.png": _png(albedo),
        f"{name}_nm.normal.png": _png(_normal_from_height(height, 5.0)),
        f"{name}_r.data.png": _png(_resize(roughness, rough_px)[:, :, None].repeat(3, 2), "L"),
        f"{name}_e.color.png": _png(emissive_rgb),
    }, {
        "pile_layers": [list(layer) for layer in layers],
        "lump_span_m": [
            round(hs.CRUST_TILE_V_M / layers[-1][0], 3),
            round(hs.CRUST_TILE_V_M / layers[0][0], 3),
        ],
        "lump_span_m_u_axis": [
            round(hs.CRUST_TILE_U_M / layers[-1][0], 3),
            round(hs.CRUST_TILE_U_M / layers[0][0], 3),
        ],
        "lump_span_convention": (
            "one tile is 23.000 m radially (u) by 24.544 m tangentially (v); the band "
            "published is the LONG axis, so the design's 0.3-1.2 m holds on both"
        ),
        "facet_sides": [4, 7],
        "warp_cells": round(0.80 * 0.5, 4),
        "warp_cell_limit": WARP_CELL_LIMIT,
        "domain_warped": True,
        "radial_axis": "u (image columns) = radius 176 -> 199 m, one tile across the plate",
        "roughness_px": rough_px,
        "ash_fraction": round(float((ash > 0.5).mean()), 5),
        "ash_mean": round(float(ash.mean()), 5),
        "bank_mean": round(float(bank.mean()), 5),
        "heat_mean": round(float(heat.mean()), 5),
        "dead_fraction": round(float((heat < 0.05).mean()), 5),
        "albedo_mean_rgb": [round(float(albedo[:, :, i].mean()), 5) for i in range(3)],
        "albedo_linear_mean": round(float(_srgb_to_linear(albedo).mean()), 6),
        "albedo_red_excess_mean": round(float(red_excess.mean()), 5),
        "emissive_core_fraction": round(float((emissive > 0.05).mean()), 5),
        "emissive_mask_fraction_over_half": round(float((emissive > 0.5).mean()), 5),
        "emissive_mean": round(float(emissive.mean()), 5),
        "emissive_p99": round(float(np.quantile(emissive, 0.99)), 5),
        "emissive_core_p99": round(float(np.quantile(core, 0.99)), 5),
        "halo_mean": round(float(halo.mean()), 5),
        "roughness_p05_p95": [
            round(float(np.quantile(roughness, 0.05)), 4),
            round(float(np.quantile(roughness, 0.95)), 4),
        ],
        "b0_reference_plate": {
            "albedo_linear_mean": 0.00549,
            "albedo_srgb_mean": 0.0585,
            "emissive_map_mean": 0.3098,
            "emissive_fraction_over_half": 0.325,
            "source": "critic r3 verify_b0_vs_b2_plate.json, from B0's own shipped bytes",
        },
    }


# --- the decal sets ------------------------------------------------------------------
def _radial_falloff(px: int, power: float = 2.0) -> np.ndarray:
    ys, xs = np.mgrid[0:px, 0:px].astype(np.float32)
    r = np.sqrt(((xs - px / 2) / (px / 2)) ** 2 + ((ys - px / 2) / (px / 2)) ** 2)
    return np.clip(1.0 - r, 0, 1) ** power


def _cell_art(key: str, cell_px: int) -> tuple[np.ndarray, np.ndarray]:
    """(albedo RGB, opacity L) for one decal family, in its own 512 px cell."""

    rng = _rng("decal", key)
    fine = _fbm(cell_px, 8, 4, rng)
    coarse = _fbm(cell_px, 3, 3, rng)
    disc = _radial_falloff(cell_px, 1.6)
    ys, xs = np.mgrid[0:cell_px, 0:cell_px].astype(np.float32)
    u = xs / cell_px
    v = ys / cell_px
    if key == "dcl_ash_drift":
        colour = np.stack([0.42 + fine * 0.22, 0.40 + fine * 0.20, 0.39 + fine * 0.19], -1)
        alpha = disc * np.clip(coarse * 1.5 - 0.15, 0, 1)
    elif key == "dcl_scorch_streak":
        streak = np.clip(1.0 - np.abs(v - 0.5) * 3.4, 0, 1) ** 1.4
        colour = np.stack([0.10 + fine * 0.07, 0.075 + fine * 0.05, 0.06 + fine * 0.04], -1)
        alpha = (
            streak * np.clip(0.35 + coarse * 0.9, 0, 1) * np.clip(1.2 - np.abs(u - 0.5) * 1.6, 0, 1)
        )
    elif key == "dcl_soot_splash":
        colour = np.stack([0.06 + fine * 0.05, 0.05 + fine * 0.04, 0.05 + fine * 0.04], -1)
        alpha = disc * np.clip(fine * 1.8 - 0.35, 0, 1)
    elif key == "dcl_skid_arc":
        band = np.clip(1.0 - np.abs(v - 0.5) * 5.0, 0, 1) ** 0.8
        twin = np.maximum(
            np.clip(1.0 - np.abs(v - 0.36) * 9.0, 0, 1), np.clip(1.0 - np.abs(v - 0.64) * 9.0, 0, 1)
        )
        colour = np.stack([0.045 + fine * 0.03] * 3, -1)
        alpha = np.clip(twin * 0.9 + band * 0.25, 0, 1) * np.clip(0.55 + fine * 0.8, 0, 1)
    elif key == "dcl_needle_litter":
        colour = np.stack([0.30 + fine * 0.16, 0.21 + fine * 0.12, 0.12 + fine * 0.07], -1)
        alpha = disc * np.clip(fine * 2.1 - 0.55, 0, 1)
    elif key == "dcl_grease_ring":
        ring = np.clip(1.0 - np.abs(v - 0.5) * 6.0, 0, 1) ** 1.2
        colour = np.stack([0.10 + fine * 0.05, 0.085 + fine * 0.04, 0.06 + fine * 0.03], -1)
        alpha = ring * np.clip(0.35 + coarse * 0.7, 0, 1)
    elif key == "dcl_scorch_bloom":
        colour = np.stack([0.09 + fine * 0.06, 0.07 + fine * 0.04, 0.06 + fine * 0.03], -1)
        alpha = _radial_falloff(cell_px, 2.6) * np.clip(0.5 + coarse * 0.9, 0, 1)
    elif key == "dcl_tyre_scuff":
        band = np.clip(1.0 - np.abs(v - 0.5) * 4.2, 0, 1)
        colour = np.stack([0.055 + fine * 0.03] * 3, -1)
        alpha = band * np.clip(fine * 1.6 - 0.25, 0, 1)
    elif key == "dcl_seasoning_flake":
        colour = np.stack([0.13 + fine * 0.09, 0.10 + fine * 0.06, 0.075 + fine * 0.04], -1)
        alpha = disc * np.clip(fine * 2.4 - 0.85, 0, 1)
    elif key == "dcl_salt_scatter":
        colour = np.stack([0.86 + fine * 0.12, 0.86 + fine * 0.12, 0.83 + fine * 0.12], -1)
        alpha = disc * np.clip(fine * 2.6 - 1.0, 0, 1)
    elif key == "dcl_butter_smear":
        colour = np.stack([0.86 + fine * 0.10, 0.68 + fine * 0.12, 0.26 + fine * 0.10], -1)
        alpha = disc * np.clip(0.35 + coarse * 0.85, 0, 1) * 0.8
    else:
        raise HearthTextureError(f"no cell art for {key}")
    return np.clip(colour, 0, 1), np.clip(alpha, 0, 1)


def cook_decals() -> tuple[dict[str, bytes], dict[str, Any]]:
    px = _check_px(hs.DECAL_ATLAS_PX, "decal atlas")
    grid = hs.DECAL_ATLAS_GRID
    cell = px // grid
    _check_px(cell, "decal atlas cell")
    albedo = np.zeros((px, px, 3), np.float32)
    opacity = np.zeros((px, px), np.float32)
    height = np.zeros((px, px), np.float32)
    used: dict[str, list[int]] = {}
    for key, spec in hs.DECAL_KEYS.items():
        if spec["material"] != "atlas":
            continue
        row, column = divmod(int(spec["cell"]), grid)
        art, alpha = _cell_art(key, cell)
        y0, x0 = row * cell, column * cell
        albedo[y0 : y0 + cell, x0 : x0 + cell] = art
        opacity[y0 : y0 + cell, x0 : x0 + cell] = alpha
        height[y0 : y0 + cell, x0 : x0 + cell] = alpha * 0.6
        used[key] = [column, row]
    roughness = np.clip(0.75 - _luma(albedo) * 0.15, 0.1, 1.0)
    # PNG row 0 is v = 1: the cells above are authored top-down, so flip ONCE here
    # and record the cell rects in the same (flipped) frame the DecalData names.
    flip = slice(None, None, -1)
    stem = f"{hs.LEVEL_ID}_t_dcl_atlas"
    files = {
        f"{stem}_b.color.png": _png(albedo[flip]),
        f"{stem}_nm.normal.png": _png(_normal_from_height(height, 3.0)[flip]),
        f"{stem}_r.data.png": _png(roughness[flip][:, :, None].repeat(3, 2), "L"),
        f"{stem}_o.data.png": _png(opacity[flip][:, :, None].repeat(3, 2), "L"),
    }
    # the emissive ember-pile decal on its own power-of-two set
    epx = _check_px(hs.DECAL_EMBER_PX, "ember decal")
    rng = _rng("decal", "dcl_ember_pile")
    lump = _fbm(epx, 7, 4, rng)
    disc = _radial_falloff(epx, 1.4)
    core = np.clip((lump - 0.52) / 0.48, 0, 1) ** 1.5
    ember_albedo = np.stack([0.16 + core * 0.62, 0.075 + core * 0.20, 0.055 + core * 0.04], -1)
    ember_alpha = disc * np.clip(lump * 1.9 - 0.45, 0, 1)
    ember_emissive = np.stack([core, core * 0.55, core * 0.2], -1)
    estem = f"{hs.LEVEL_ID}_t_dcl_ember"
    files.update(
        {
            f"{estem}_b.color.png": _png(np.clip(ember_albedo, 0, 1)),
            f"{estem}_nm.normal.png": _png(_normal_from_height(lump, 4.0)),
            f"{estem}_r.data.png": _png(
                np.clip(0.9 - core * 0.3, 0.1, 1)[:, :, None].repeat(3, 2), "L"
            ),
            f"{estem}_o.data.png": _png(ember_alpha[:, :, None].repeat(3, 2), "L"),
            f"{estem}_e.color.png": _png(np.clip(ember_emissive, 0, 1)),
        }
    )
    census = {
        "atlas_px": px,
        "cell_px": cell,
        "grid": grid,
        "cells_used": used,
        "flipped_once": True,
        "ember_px": epx,
        "ember_core_fraction": round(float((ember_emissive[:, :, 0] > 0.05).mean()), 5),
        "mean_opacity": {
            key: round(
                float(
                    opacity[
                        (int(spec["cell"]) // grid) * cell : (int(spec["cell"]) // grid) * cell
                        + cell,
                        (int(spec["cell"]) % grid) * cell : (int(spec["cell"]) % grid) * cell
                        + cell,
                    ].mean()
                ),
                5,
            )
            for key, spec in hs.DECAL_KEYS.items()
            if spec["material"] == "atlas"
        },
    }
    return files, census


# --- the ember particle sprites (r2, critic r1 D2) -------------------------------------
def cook_particles() -> tuple[dict[str, bytes], dict[str, Any]]:
    """Two RGBA sprites whose alpha reaches ZERO before the quad's edge.

    r1 named the stock ``art/shapes/particles/ember.png``, whose alpha never drops
    below 4/255 -- so under the additive stacking of ``hearth_spec.PARTICLE_TUNING``'s
    comment every texel of the quad clipped and the glow rendered as a white BOX.  A
    sprite that ends in alpha 0 cannot draw its own bounding box no matter what is
    stacked on it, which is why the shape is fixed here and the stacking is fixed in
    the datablock: either alone would leave the other free to come back.

    ``glow`` also carries a ragged rim (three angular cosine octaves keyed by
    ``TEXTURE_SEED``) so the bed's breath is not a machined circle.
    """

    files: dict[str, bytes] = {}
    census: dict[str, Any] = {}
    for kind, spec in hs.PARTICLE_SPRITES.items():
        px = _check_px(int(spec["px"]), f"particle sprite {kind}")
        core = float(spec["core"])
        falloff = float(spec["falloff"])
        axis = (np.arange(px, dtype=np.float64) + 0.5) / px * 2.0 - 1.0
        gx, gy = np.meshgrid(axis, axis)
        radius = np.sqrt(gx * gx + gy * gy)
        if kind in ("glow", "wisp"):
            theta = np.arctan2(gy, gx)
            rng = _rng("particle", kind, px, hs.TEXTURE_SEED)
            wobble = np.zeros_like(theta)
            for harmonic, weight in ((3.0, 0.55), (5.0, 0.30), (9.0, 0.15)):
                phase = float(rng.uniform(0.0, 2.0 * np.pi))
                wobble += weight * np.cos(harmonic * theta + phase)
            radius = radius / (1.0 - 0.13 * wobble)
        alpha = np.clip((1.0 - radius) / (1.0 - core), 0.0, 1.0) ** falloff
        # the outer two texels are hard zero: no filter ring, no quad edge, ever
        alpha[:2, :] = alpha[-2:, :] = alpha[:, :2] = alpha[:, -2:] = 0.0
        if kind == "wisp":
            # steam, not fire: a warm neutral grey, flat across the puff
            rgb = np.stack(
                [
                    np.full_like(alpha, 0.92),
                    np.full_like(alpha, 0.89),
                    np.full_like(alpha, 0.85),
                ],
                axis=2,
            )
        else:
            heat = np.clip(1.0 - radius / max(core * 3.0, 1e-6), 0.0, 1.0)
            rgb = np.stack(
                [
                    np.ones_like(alpha),
                    0.45 + 0.55 * heat,
                    0.10 + 0.90 * heat * heat,
                ],
                axis=2,
            )
        payload = _png(np.concatenate([rgb, alpha[:, :, None]], axis=2), "RGBA")
        files[f"{hs.LEVEL_ID}_particle_{kind}.png"] = payload
        opaque = alpha > 0.0
        rows = np.any(opaque, axis=1)
        columns = np.any(opaque, axis=0)
        bbox = int(rows.sum()) * int(columns.sum())
        census[kind] = {
            "px": px,
            "alpha_min": round(float(alpha.min()), 6),
            "alpha_max": round(float(alpha.max()), 6),
            "alpha_mean": round(float(alpha.mean()), 6),
            "border_alpha_max": round(
                float(
                    max(
                        alpha[0, :].max(),
                        alpha[-1, :].max(),
                        alpha[:, 0].max(),
                        alpha[:, -1].max(),
                    )
                ),
                6,
            ),
            # a filled square reads 1.0 here; a disc with a falloff reads ~0.8 or less
            "bbox_fill": round(float(opaque.sum()) / bbox, 4) if bbox else None,
            # the same statistic at the critic's blob threshold: r1's rendered sprites
            # read a median 0.875 because they WERE filled squares
            "bbox_fill_half": round(float((alpha >= 0.5).sum()) / bbox, 4) if bbox else None,
            "note": spec["note"],
        }
    return files, census


# --- driver ---------------------------------------------------------------------------
def cook_all() -> tuple[dict[str, bytes], dict[str, Any]]:
    outputs: dict[str, bytes] = {}
    notes: dict[str, Any] = {}
    for asset in hs.STONE_SOURCES:
        for name, payload in cook_rock(asset).items():
            outputs[f"{hs.SHAPE_DIR}/{name}"] = payload
    crust_files, crust_notes = cook_crust()
    for name, payload in crust_files.items():
        outputs[f"{hs.SHAPE_DIR}/{name}"] = payload
    notes["crust"] = crust_notes
    decal_files, decal_notes = cook_decals()
    for name, payload in decal_files.items():
        outputs[f"{hs.DECAL_DIR}/{name}"] = payload
    notes["decals"] = decal_notes
    particle_files, particle_notes = cook_particles()
    for name, payload in particle_files.items():
        outputs[f"{hs.PARTICLE_DIR}/{name}"] = payload
    notes["particles"] = particle_notes
    return outputs, notes


def cooked_members() -> tuple[str, ...]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return tuple(sorted(manifest["files"]))


def write(root: Path = LEVEL_ROOT) -> dict[str, Any]:
    outputs, notes = cook_all()
    files: dict[str, Any] = {}
    for relative, payload in sorted(outputs.items()):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != payload:
            target.write_bytes(payload)
        with Image.open(io.BytesIO(payload)) as image:
            size = image.size
        files[relative] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "px": list(size),
        }
        _check_px(size[0], relative)
        _check_px(size[1], relative)
    manifest = {
        "level_id": hs.LEVEL_ID,
        "seed": hs.TEXTURE_SEED,
        "notes": notes,
        "cc0_overlay_sources": OVERLAY_SOURCES,
        "files": files,
        "total_bytes": sum(int(v["bytes"]) for v in files.values()),
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main() -> int:
    manifest = write()
    print(
        json.dumps(
            {
                "files": len(manifest["files"]),
                "MB": round(manifest["total_bytes"] / 1e6, 1),
                "notes": manifest["notes"],
            },
            indent=1,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
