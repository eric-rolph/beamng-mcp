"""Cook the forest's six-role PBR maps from the CC0 cache (design v4 §4.1, §4.5, §12).

    .\\.venv\\Scripts\\python.exe examples/hot_potato_arena/level/forest_textures.py \\
        --out examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena \\
        --cache examples/hot_potato_arena/cc0_cache \\
        --manifest authoring/ericrolph_hot_potato_arena_forest_textures.json

Every material of ``forest_spec.MATERIALS`` gets the level_facts six-role naming --
``*_b.color`` / ``*_nm.normal`` / ``*_r.data`` / ``*_ao.data`` / ``*_o.data`` -- at the size
design §12's "shipped as" column names.  Two families of recipe:

``tile``        a bark/ground texture resampled to size and tinted (no cut-out).
CUT-OUT STAMPS  **every** material that is not a tile -- all 22 of them, as of r3 -- is
                COMPOSED cell by cell from real islands of the CC0 photographs, taken with the
                source's own published alpha where it has one and with a measured segmentation
                where it does not, stamped in at their own rotation, scale, mirror and tint by
                :func:`compose_atlas`.  This replaced r1's "generated mask x source crop",
                which put a smooth blob where the needle silhouette should be (42 alpha islands
                against a stock conifer's 4,281-6,964 and a 134 mm mean needle against
                4.9-18.4 mm) and made all five ground covers one procedural grass sheet in five
                tints.  r2 converted eleven of them and left the four shrub sheets on the old
                path while its contact sheet said otherwise; r3 converts those four and
                **deletes** ``cook_atlas`` and the three mask functions, so there is no path
                left for a generated mask to reach a shipped atlas.

Matting (r3, D6).  A cut-out is only as good as its edge.  Three things had to be true and
were not: the island's colour is dilated out of its own core BEFORE the alpha is feathered
(``_dilate_colour``), a stamp is rotated into its own mean colour rather than into black, and
the cell composites in PREMULTIPLIED alpha and is divided out at the end instead of being
blended onto a black cell.  Without those, 12-21 % of four covers' opaque area was near-black
and 87-94 % of that sat within two texels of the cut edge -- a black rim on every grass blade,
which is why the meadow mipped down to dark lumps.

Rock and cover-shape materials take the model's packed ``arm`` map (R = AO, G = roughness,
B = metallic) apart into the two data maps.

Normal convention: the Poly Haven ``nor_gl`` map is written through unchanged, matching what
B1's ``cook_terrain_textures`` does for the terrain (``MAP_SUFFIX["nm"] = "nor_gl"``), so the
whole level is one convention.  PNG is deliberate: B6 pre-cooks every map to BC7/BC5/BC4 DDS
with full mip chains (design §10 B6 row, QB-11); shipping PNG here keeps the source lossless
and the intermediate reviewable.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from examples.hot_potato_arena.level import forest_spec as fs

Image.MAX_IMAGE_PIXELS = None

#: Poly Haven map names per role, tried in order; the first that exists on disk wins.
TEXTURE_SOURCES = {
    "base": ("diff",),
    "normal": ("nor_gl",),
    "roughness": ("rough", "arm"),
    "ao": ("ao", "arm"),
}
ARM_CHANNEL = {"roughness": 1, "ao": 0}


class TextureError(RuntimeError):
    """A CC0 source is missing or a recipe cannot be honoured."""


def _find(cache: Path, asset: str, names: tuple[str, ...]) -> Path:
    """Resolve one Poly Haven map: textures ship flat, models under ``textures/``.

    The resolution suffix is globbed rather than assumed -- B1 fetches some of the same ids at
    4k (``burned_ground_01``) and B3 at 2k, and both land in the shared cache.
    """
    for name in names:
        for directory in (cache / asset, cache / asset / "textures"):
            if not directory.is_dir():
                continue
            hits = sorted(
                p
                for p in directory.iterdir()
                if p.is_file()
                and p.suffix.lower() in (".png", ".jpg")
                and (
                    p.stem == f"{asset}_{name}"
                    or (
                        p.stem.startswith(f"{asset}_{name}_")
                        and p.stem[len(asset) + len(name) + 2 :].rstrip("k").isdigit()
                    )
                )
            )
            if hits:
                # prefer 2k (the design's fetch resolution), else the largest available
                exact = [p for p in hits if p.stem.endswith("_2k")]
                return exact[0] if exact else hits[-1]
    raise TextureError(f"{asset}: no source for {names} under {cache / asset}")


def _load(path: Path, size: int | None = None, mode: str = "RGB") -> np.ndarray:
    with Image.open(path) as image:
        image = image.convert(mode)
        if size is not None and image.size != (size, size):
            image = image.resize((size, size), Image.LANCZOS)
        return np.asarray(image, dtype=np.uint8)


def _png(array: np.ndarray) -> bytes:
    mode = "L" if array.ndim == 2 else "RGB"
    buffer = io.BytesIO()
    Image.fromarray(array, mode).save(buffer, format="PNG", optimize=False, compress_level=6)
    return buffer.getvalue()


def _rng(*parts) -> np.random.Generator:
    seed = hashlib.sha256((":".join(str(p) for p in (fs.TEXTURE_SEED, *parts))).encode()).digest()
    return np.random.default_rng(int.from_bytes(seed[:8], "little"))


# ------------------------------------------------------------------------------ cut-out masks
def _smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------- image primitives (numpy only)
# scipy is NOT a declared dependency of this repository, so everything the stamp cutter needs --
# box mean, dilation, connected components -- is implemented here on integral images and
# run-length union-find.  A gate that only runs where the author happens to have scipy is not a
# gate (pyproject's `dev` comment says the same thing about lupa).
def _box_mean(array: np.ndarray, radius: int) -> np.ndarray:
    """Mean over a (2r+1)^2 window, edge-extended, via an integral image."""
    if radius <= 0:
        return array.astype(np.float64)
    padded = np.pad(array.astype(np.float64), radius + 1, mode="edge")
    summed = np.pad(padded.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    side = 2 * radius + 1
    height, width = array.shape
    total = (
        summed[side : side + height, side : side + width]
        - summed[0:height, side : side + width]
        - summed[side : side + height, 0:width]
        + summed[0:height, 0:width]
    )
    return total / float(side * side)


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Box dilation: any set texel inside the (2r+1)^2 window."""
    if radius <= 0:
        return mask
    return _box_mean(mask.astype(np.float64), radius) > (0.5 / float((2 * radius + 1) ** 2))


def _label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connected components, run-length + union-find.  Returns (labels, count).

    Rows are decomposed into runs with one vectorised diff, so the Python loop is over RUNS
    (thousands on a dilated clump mask) rather than texels (millions).
    """
    height, width = mask.shape
    flat = np.pad(mask, ((0, 0), (1, 1))).astype(np.int8)
    steps = np.diff(flat, axis=1)
    starts_r, starts_c = np.nonzero(steps == 1)
    _, ends_c = np.nonzero(steps == -1)
    if not len(starts_r):
        return np.zeros_like(mask, dtype=np.int32), 0
    runs = np.stack([starts_r, starts_c, ends_c], axis=1)  # row, start, end (exclusive)
    parent = list(range(len(runs)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    row_first = np.searchsorted(runs[:, 0], np.arange(height + 1))
    rows = runs[:, 0].tolist()
    lo = runs[:, 1].tolist()
    hi = runs[:, 2].tolist()
    for row in range(1, height):
        above_a, above_b = row_first[row - 1], row_first[row]
        here_a, here_b = row_first[row], row_first[row + 1]
        i, j = above_a, here_a
        while i < above_b and j < here_b:
            if hi[i] <= lo[j]:
                i += 1
            elif hi[j] <= lo[i]:
                j += 1
            else:
                union(i, j)
                if hi[i] < hi[j]:
                    i += 1
                else:
                    j += 1
    roots = np.array([find(i) for i in range(len(runs))], dtype=np.int64)
    unique, compact = np.unique(roots, return_inverse=True)
    labels = np.zeros((height, width), dtype=np.int32)
    for index in range(len(runs)):
        labels[rows[index], lo[index] : hi[index]] = compact[index] + 1
    return labels, len(unique)


def _feather(alpha: np.ndarray, radius: int = 2) -> np.ndarray:
    """Soften a hard cut-out edge so alphaTest does not shimmer and mips do not crawl."""
    return np.clip(_box_mean(alpha, radius) * 1.15, 0.0, 1.0)


def _dilate_colour(array: np.ndarray, core: np.ndarray, rounds: int = 6) -> np.ndarray:
    """Push the CORE's colour outward over everything that is not core.  2-D or 3-D.

    r3 (D6).  A cut-out island's bounding box still contains the source photograph's own dark
    backdrop, and ``_feather`` then widens the alpha OVER it -- so the shipped albedo grew a
    one-to-two-texel near-black rim around every blade.  Measured on the r2 zip: 17.1 % of
    ``gc_meadow``'s opaque area, 21.0 % of ``gc_alpine``'s and 21.1 % of ``gc_stubble``'s was
    near-black (max RGB < 0.10), and 87-94 % of that sat within 2 texels of the cut edge, so a
    grass blade 2-4 texels wide was mostly black and the meadow mipped down to dark lumps.
    Dilating the colour under the alpha is the standard fix and it is done HERE, on the island,
    before the feather and before any rotation can resample the backdrop back in.
    """
    if array.ndim == 2:
        return _bleed(array[..., None].astype(np.float64), core, rounds)[..., 0]
    return _bleed(array.astype(np.float64), core, rounds)


def _bleed(colour: np.ndarray, alpha: np.ndarray, rounds: int = 4) -> np.ndarray:
    """Push the cut-out's colour outward into the transparent texels.

    Without it the mip chain averages foliage against whatever the empty cell was cleared to
    and the card grows a halo two LODs down -- the classic alpha-fringe.  Each round replaces
    the still-empty texels with the alpha-weighted box mean of what is already covered.
    """
    filled = alpha > 0.02
    out = colour.astype(np.float64).copy()
    weight = filled.astype(np.float64)
    for _ in range(rounds):
        if filled.all():
            break
        weight_blur = _box_mean(weight, 2)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.stack(
                [
                    _box_mean(out[..., c] * weight, 2) / np.maximum(weight_blur, 1e-6)
                    for c in range(out.shape[2])
                ],
                axis=2,
            )
        grow = (~filled) & (weight_blur > 1e-6)
        out[grow] = mean[grow]
        filled = filled | grow
        weight = filled.astype(np.float64)
    return np.clip(out, 0, 255)


# ============================================================================================
# The CUT-OUT STAMP pipeline (r2) -- real photographed foliage instead of a generated mask
# ============================================================================================
# Round 1 built the twig and cover atlases as `generated_mask x source_alpha`, which put a
# smooth blob where the silhouette should be: 42 alpha islands against a stock conifer's
# 4,281-6,964, a mean needle 134 mm wide against 4.9-18.4 mm, and five "different" ground
# covers that were one procedural grass sheet in five tints.
#
# What the round-1 critique found in the sources, and what this pipeline does about it:
#
#   * `pine_tree_01`'s and `fir_tree_01`'s published twig alphas ARE needle-level -- but only
#     over the two (pine) and roughly seven (fir) real sprigs on a sheet that is otherwise
#     bark, UV junk and a colour-checker chart, whose alpha is fully OPAQUE.  Measured over
#     the whole sheet that reads as "66 islands, 342 px stroke"; measured over a sprig it is a
#     photograph of needles.  So the fix is not to abandon the alpha, it is to FIND the sprigs
#     and cut only those.
#   * `pine_sapling_medium` / `fir_sapling_medium` publish their bigger sibling's sheet byte
#     for byte (sha256[:16] 1e5a1fe741f4cb73 and 6eecd1cf1e059488 on both pairs), so the
#     "four distinct twig sources" of design §12 are two.  `pine_sapling_small` and
#     `fir_sapling` were fetched to test whether Poly Haven has more: they do not carry a
#     usable sprig (their twig regions are UV-atlas junk), which is MEASURED in
#     `SOURCE_NOTES` rather than assumed.  Variety therefore comes from cutting many
#     genuinely different stamps out of the two real scans and composing each cell from them
#     at its own rotation, scale, mirror and tint.
#   * the grass/fern/needle/twig cut-outs the ground covers want are all in the design's §12
#     list already, they were simply never cut: `grass_medium_01` / `_02` are blades and
#     seed-heads on BLACK, `fern_02` is five fronds on a flat backdrop, `forest_leaves_04` is
#     a needle-litter tile, `burned_ground_01` is charred stalks.
#
# One engine serves both: find the real islands in a source, cut them out with their own
# alpha, and stamp them into the atlas.
STAMP_MASKS = ("alpha", "bright", "carve", "offcolour")


def stamp_mask(recipe: str, base: np.ndarray, alpha: np.ndarray | None, params: dict) -> np.ndarray:
    """The 0..1 cut-out field of a source sheet, by recipe.

    ``alpha``  the published photogrammetry alpha (the conifer twig sheets) -- native detail,
               nothing generated, which is the whole point.
    ``bright`` a model atlas rendered on black (`grass_medium_01/_02`): the background is the
               only truly dark thing on the sheet.
    ``carve``  a full-bleed tile or a flat-backdrop atlas (`fern_02`, `forest_leaves_04`,
               `burned_ground_01`, `sparse_grass`): the plant is what stands out from its own
               local mean in luminance or in colour.  This is a real segmentation of a real
               photograph, not a drawn shape.
    """
    channels = base.astype(np.float64)
    luma = 0.299 * channels[..., 0] + 0.587 * channels[..., 1] + 0.114 * channels[..., 2]
    if recipe == "alpha":
        if alpha is None:
            raise TextureError("the 'alpha' stamp recipe needs a published alpha map")
        return np.clip(alpha.astype(np.float64) / 255.0, 0.0, 1.0)
    if recipe == "bright":
        floor = float(params.get("floor", 18.0))
        span = float(params.get("span", 26.0))
        return _smoothstep((luma - floor) / span)
    if recipe == "carve":
        # A ground tile has no background to key on, so the segmentation is by CONTRAST and
        # COLOUR against the tile's own local mean, and the threshold is set by the coverage
        # we want rather than by a magic level: `cover=0.10` means "keep the leafiest tenth of
        # this photograph".  That is what makes one recipe work on a needle-litter tile, a
        # burnt ground and a fern sheet without three sets of hand-tuned constants.
        radius = int(params.get("radius", 7))
        local = _box_mean(luma, radius)
        detail = np.abs(luma - local)
        detail = detail / max(float(np.percentile(detail, 99.0)), 1e-6)
        green = channels[..., 1] - 0.5 * (channels[..., 0] + channels[..., 2])
        bright = (luma - local) / np.maximum(local, 12.0)
        score = (
            float(params.get("w_detail", 1.0)) * np.clip(detail, 0.0, 1.5)
            + float(params.get("w_green", 0.0)) * np.clip(green / 20.0, 0.0, 1.5)
            + float(params.get("w_bright", 0.0)) * np.clip(bright / 0.25, -1.5, 1.5)
        )
        cover = float(params.get("cover", 0.10))
        level = float(np.percentile(score, 100.0 * (1.0 - cover)))
        span = max(0.25 * abs(level), 0.02)
        return _smoothstep((score - level) / span + 0.5)
    if recipe == "offcolour":
        # A Poly Haven MODEL atlas paints its unused UV space one flat colour (`fern_02`'s is
        # (76, 100, 44) over 30.8 % of the sheet).  The plant is then simply "everything far
        # from the modal colour" -- which pulls the six fern fronds out of that sheet with
        # their pinnae intact where a luminance or greenness test cannot.
        quantised = (channels // 8).astype(np.int64)
        key = quantised[..., 0] * 1024 + quantised[..., 1] * 32 + quantised[..., 2]
        values, counts = np.unique(key, return_counts=True)
        mode = int(values[counts.argmax()])
        background = np.array(
            [(mode // 1024) * 8 + 4, ((mode // 32) % 32) * 8 + 4, (mode % 32) * 8 + 4]
        )
        distance = np.sqrt(((channels - background) ** 2).sum(axis=2))
        cover = float(params.get("cover", 0.16))
        level = float(np.percentile(distance, 100.0 * (1.0 - cover)))
        return _smoothstep((distance - level) / max(0.18 * level, 1.0) + 0.5)
    raise TextureError(f"unknown stamp mask recipe {recipe!r}")


class Stamp:
    """One cut-out: a real island of foliage with its own six-role maps and its own alpha."""

    __slots__ = ("ao", "base", "normal", "opacity", "roughness", "score", "source")

    def __init__(self, base, opacity, normal, roughness, ao, score, source) -> None:
        self.base = base
        self.opacity = opacity
        self.normal = normal
        self.roughness = roughness
        self.ao = ao
        self.score = score
        self.source = source

    @property
    def size(self) -> tuple[int, int]:
        return self.opacity.shape[1], self.opacity.shape[0]


def _source_maps(cache: Path, asset: str, prefix: str) -> dict:
    """Load one source's five roles (base, normal, roughness, ao, published alpha)."""
    out = {
        "base": _load(_find(cache, asset, (f"{prefix}diff",)), mode="RGB"),
        "normal": _load(_find(cache, asset, (f"{prefix}nor_gl", "nor_gl")), mode="RGB"),
    }
    out["roughness"] = _channel(
        _find(cache, asset, (f"{prefix}rough", f"{prefix}arm", "rough", "arm")), "roughness"
    )
    ao_path = _optional(cache, asset, (f"{prefix}ao", f"{prefix}arm", "ao", "arm"))
    out["ao"] = _channel(ao_path, "ao") if ao_path is not None else derived_ao(out["normal"])
    try:
        out["alpha"] = _load(_find(cache, asset, (f"{prefix}alpha",)), mode="L")
    except TextureError:
        out["alpha"] = None
    size = out["base"].shape[0]
    for role in ("normal",):
        if out[role].shape[0] != size:
            out[role] = np.asarray(
                Image.fromarray(out[role], "RGB").resize((size, size), Image.LANCZOS),
                dtype=np.uint8,
            )
    for role in ("roughness", "ao"):
        out[role] = _resize_l(out[role], size)
    if out["alpha"] is not None and out["alpha"].shape[0] != size:
        out["alpha"] = _resize_l(out["alpha"], size)
    return out


#: r10 (critic B9-2).  A MODEL atlas -- `dry_branches_medium_01`, `bark_debris_01`, `fern_02`,
#: `grass_medium_*`, the four shrub sheets -- carries, beside its photographed foliage, large
#: FLAT UNTEXTURED FACETS: the scan's backdrop shards and the baker's UV padding.  They are
#: real islands with real alpha, so `cut_stamps`' island tests (fill, detail, achromatic mean)
#: cannot see them when they share an island with a twig, and r2-r9 shipped them.  Graded by
#: `gc_litter`'s own `grade` (sat 0.46 / luma 0.27) a pale beige facet becomes a pale GREY
#: bevelled slab, and the critic read a cluster of them on the forest floor as the capital
#: letter "A" beside "...ORTIN..." (`b3/critic_r9/atlases/LITTER_r0c1.png`).  There is no text
#: in any source and no bake scene: the letterforms are facet silhouettes.
#:
#: The filter is per-TEXEL and the same shape as r9's `texel_hue`: find the texels that sit at
#: the centre of a smooth patch at least `2*radius+1` across (photographed needles, blades,
#: bark and char have none at any scale -- measured over all thirteen pools in
#: `b3/r10/probe/flatness_L*.json`), take the whole connected smooth region each one belongs
#: to so the facet's bevel goes with its interior, add the bright-achromatic texels, grow the
#: rejection a little and cut them out of the island.
#
# r11 (critic B10-2).  THE OUTLINE CLAUSE, which r10 had in the gate and not in the cut.
# The audit below (`AUDIT`) has always needed BOTH halves -- flat shading AND a straight,
# chunky boundary -- for exactly the reason its own docstring gives: *a broad autumn leaf is
# flat but its outline is a leaf*.  The stamp-time cut had only the flatness half, so it ate
# laminae and left veins: measured on the certified cuts by `r11/facet_ledger.py`, r9 -> r10
# lost 64.7 % of `f_shrub_leaf_01`'s opaque texels at its own alphaRef against a foreign area
# of at most 12,635 (a factor of 15.8), 65.1 % of `_04` (34.0x), 61.0 % of `f_fern` (37.5x)
# and 45.2 % of `f_reed`, which never failed the gate at all.  `straight_share` and
# `compact_min` default to the GATE's own bars so the two cannot drift apart, and the outline is
# read through `_gate_view` at the scale the gate itself will see it -- these run on the SOURCE
# photograph, where an island is several hundred texels across and a ragged photographed edge
# scores as less straight than the same edge resampled into a 256 px cell.
FACET_DEFAULT = {
    "level": 8.0,
    "radius": 5,
    "grow": 3,
    "bright": 0.42,
    "sat": 0.20,
    "dark": 0.055,
    "straight_share": None,  # None -> AUDIT["straight_share"]
    "compact_min": None,  # None -> AUDIT["compact_min"]
    "straight_run": None,  # None -> AUDIT["straight_run"]
    "gate_view_px": 200,  # measure the outline at the gate's own scale, not the source's
    "min_region_px": 120,  # below this a smooth blob is leaf interior, never a facet
}


#: r11 (critic B10-2): what the facet cut did, per source -- how many smooth regions it looked
#: at, how many it cut for having a straight chunky outline, and the texels either way.  A
#: filter that deletes pixels has to be able to say what it deleted; `r11/facet_ledger.py`
#: publishes the atlas-level consequence and this is the same story at the source.
FACET_STATS: dict[str, dict] = {}


def _gate_view(region: np.ndarray, target: int) -> np.ndarray:
    """One region's mask, cropped and resampled to the scale the audit gate reads it at.

    r11 (critic B10-2).  The gate measures a shape after the stamp has been rotated and
    resampled into a 256 px atlas cell; the stamp-time cut sees the same shape at several
    hundred source texels, where a photographed edge is ragged and a straight one is not
    obviously straighter.  Comparing the two at different scales is comparing two different
    statistics.  Bilinear down to `target` and re-threshold is what the cook itself does to
    the stamp, so the outline this measures is the outline that will ship.
    """
    ys, xs = np.nonzero(region)
    if not len(ys):
        return region
    crop = region[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    longest = max(crop.shape)
    if longest <= target:
        return crop
    scale = target / float(longest)
    height = max(2, round(crop.shape[0] * scale))
    width = max(2, round(crop.shape[1] * scale))
    with Image.fromarray((crop.astype(np.uint8) * 255), "L") as image:
        small = np.asarray(image.resize((width, height), Image.BILINEAR))
    return small >= 128


def _local_std(luma: np.ndarray, radius: int = 3) -> np.ndarray:
    mean = _box_mean(luma, radius)
    return np.sqrt(np.maximum(_box_mean(luma * luma, radius) - mean * mean, 0.0))


def facet_texels(patch: np.ndarray, cut: np.ndarray, spec: dict) -> np.ndarray | None:
    """The texels of one island that belong to a flat model-atlas facet, or ``None``.

    ``patch`` is the island's RGB window as float, ``cut`` its 0..1 mask.  Opt in per source
    with ``facet_reject=True`` (or a dict overriding :data:`FACET_DEFAULT`); a source that is a
    photograph rather than a model atlas leaves it off and pays nothing.
    """
    setting = spec.get("facet_reject")
    if not setting:
        return None
    params = dict(FACET_DEFAULT)
    if isinstance(setting, dict):
        params.update(setting)
    covered = cut >= 0.5
    if not covered.any():
        return None
    luma = 0.299 * patch[..., 0] + 0.587 * patch[..., 1] + 0.114 * patch[..., 2]
    smooth = (_local_std(luma) < float(params["level"])) & covered
    seeds = _box_mean(smooth.astype(np.float64), int(params["radius"])) > 0.985
    reject = np.zeros(cut.shape, dtype=bool)
    stats = FACET_STATS.setdefault(
        f"{spec.get('cc0')}:{spec.get('prefix', '')}{spec.get('mask')}",
        {"regions": 0, "cut": 0, "kept": 0, "cut_texels": 0, "kept_texels": 0},
    )
    if seeds.any():
        labels, count = _label(smooth)
        if count:
            share_bar = params["straight_share"]
            share_bar = AUDIT["straight_share"] if share_bar is None else float(share_bar)
            fat_bar = params["compact_min"]
            fat_bar = AUDIT["compact_min"] if fat_bar is None else float(fat_bar)
            run_floor = params["straight_run"]
            run_floor = AUDIT["straight_run"] if run_floor is None else int(run_floor)
            min_px = int(params["min_region_px"])
            for tag in np.unique(labels[seeds & (labels > 0)]).tolist():
                region = labels == tag
                area = int(region.sum())
                stats["regions"] += 1
                if area < min_px:
                    stats["kept"] += 1
                    stats["kept_texels"] += area
                    continue
                # Measure the OUTLINE at the resolution the gate will see it in.  A stamp is
                # rotated and resampled down into an atlas cell, and a photographed edge that
                # is ragged at 800 source texels is a clean line at 200 -- so straightness
                # read on the raw source is systematically lower than the gate's own reading
                # of the same shape, and a facet slips through.  `_gate_view` crops the region
                # and resamples it to the gate's own scale before `straight_share` runs.
                small = _gate_view(region, int(params["gate_view_px"]))
                share = straight_share(small, run_floor)
                ys, xs = np.nonzero(small)
                extent = max(int(ys.max() - ys.min()) + 1, int(xs.max() - xs.min()) + 1)
                fat = int(small.sum()) / float(extent * extent)
                if share >= share_bar and fat >= fat_bar:
                    reject |= region
                    stats["cut"] += 1
                    stats["cut_texels"] += area
                else:
                    stats["kept"] += 1
                    stats["kept_texels"] += area
    high, low = patch.max(axis=2), patch.min(axis=2)
    with np.errstate(invalid="ignore", divide="ignore"):
        saturation = np.where(high > 1.0, (high - low) / np.maximum(high, 1e-6), 0.0)
    reject |= covered & (high > 255.0 * float(params["bright"])) & (
        saturation < float(params["sat"])
    )
    # The same scan's BACKDROP: near-black shards that the `offcolour` cut keeps because they
    # are off-colour.  r3 already dilates foliage colour over the feathered rim; these are
    # whole islands' worth of it, and they read on the forest floor as holes.
    reject |= covered & (high < 255.0 * float(params.get("dark", 0.0)))
    if not reject.any():
        return None
    return _dilate(reject, int(params["grow"]))


def cut_stamps(cache: Path, spec: dict) -> list[Stamp]:
    """Every usable cut-out island of one CC0 source, largest/leafiest first.

    ``spec`` names the asset, the map prefix, the mask recipe, how far apart two islands have
    to be to count as two (``clump_px``), the accepted island size in source texels and the
    colour test that keeps foliage and rejects bark.
    """
    maps = _source_maps(cache, spec["cc0"], spec.get("prefix", ""))
    fine = stamp_mask(spec.get("mask", "alpha"), maps["base"], maps["alpha"], spec)
    seeds = fine >= float(spec.get("seed_level", 0.5))
    if not seeds.any():
        raise TextureError(f"{spec['cc0']}: the {spec.get('mask')} recipe found nothing")
    labels, count = _label(_dilate(seeds, int(spec.get("clump_px", 6))))
    channels = maps["base"].astype(np.float64)
    green = channels[..., 1] - 0.5 * (channels[..., 0] + channels[..., 2])
    luma = 0.299 * channels[..., 0] + 0.587 * channels[..., 1] + 0.114 * channels[..., 2]
    min_px, max_px = int(spec.get("min_px", 48)), int(spec.get("max_px", 1400))
    fill_range = spec.get("fill", (0.02, 0.92))
    green_min = float(spec.get("green_min", -1e9))
    stamps: list[Stamp] = []
    if count:
        flat = labels.ravel()
        order = np.argsort(flat, kind="stable")
        sorted_labels = flat[order]
        bounds = np.searchsorted(sorted_labels, np.arange(count + 2))
        rows, cols = np.divmod(order, labels.shape[1])
        for tag in range(1, count + 1):
            lo, hi = bounds[tag], bounds[tag + 1]
            if hi - lo < min_px * min_px // 12:
                continue
            ys, xs = rows[lo:hi], cols[lo:hi]
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            x0, x1 = int(xs.min()), int(xs.max()) + 1
            side = max(y1 - y0, x1 - x0)
            if side < min_px or side > max_px:
                continue
            window = (slice(y0, y1), slice(x0, x1))
            cut = fine[window] * (labels[window] == tag)
            fill = float((cut >= 0.5).mean())
            if not (fill_range[0] <= fill <= fill_range[1]):
                continue
            covered = cut >= 0.5
            if covered.sum() < min_px * 4:
                continue
            if float(green[window][covered].mean()) < green_min:
                continue
            hue_band = spec.get("texel_hue")
            if hue_band is not None:
                # r9: a PER-TEXEL hue window.  `fern_02`'s fronds share their islands with the
                # model atlas's tan UV-padding facets (hue 30-45, rgb ~ 105/84/44 against the
                # fronds' 56/71/20; 41-64 % of two of the five islands), which shipped as the
                # "hay-coloured" plates under every fern in r2-r8.  The island filter above
                # cannot separate them because they are the SAME island; this keeps only the
                # texels whose hue is foliage and lets the feather re-soften the cut.
                hue = _hue_degrees(channels[window])
                inside = (hue >= float(hue_band[0])) & (hue <= float(hue_band[1]))
                cut = cut * np.where(inside, 1.0, 0.0)
                covered = cut >= 0.5
                if covered.sum() < min_px * 4:
                    continue
            facet = facet_texels(channels[window], cut, spec)
            if facet is not None:
                cut = cut * np.where(facet, 0.0, 1.0)
                covered = cut >= 0.5
                if covered.sum() < min_px * 4:
                    continue
                if not (fill_range[0] <= float((cut >= 0.5).mean()) <= fill_range[1]):
                    continue
            # r3 (D6): reject a BRIGHT ACHROMATIC island.  `forest_leaves_04` is photographed
            # with a scale/calibration block in frame, and r2 cut a 10,721-texel flat pale-grey
            # box out of it and shipped it as forest litter -- visible as flat pale chips on
            # the S7 forest floor.  Nothing in a forest is both bright and colourless; needles,
            # bark, char and dead leaves all carry chroma.  Same filter class as the fill and
            # detail tests above, applied to every source rather than patched onto one.
            patch = channels[window]
            high = patch.max(axis=2)
            low = patch.min(axis=2)
            with np.errstate(invalid="ignore", divide="ignore"):
                saturation = np.where(high > 1.0, (high - low) / np.maximum(high, 1e-6), 0.0)
            value_mean = float(high[covered].mean()) / 255.0
            sat_mean = float(saturation[covered].mean())
            bright_v, min_s = spec.get("achromatic_reject", (0.45, 0.18))
            achromatic = covered & (saturation < float(min_s)) & (high > 255.0 * float(bright_v))
            achromatic_share = float(achromatic.sum()) / float(covered.sum())
            # The island MEAN test is what catches a photographic calibration block (it is
            # bright and colourless from edge to edge).  The TEXEL-SHARE test is a second,
            # opt-in filter for a source whose junk is mixed INTO a real island -- the shrub
            # model atlases pad their UV space with flat khaki facets that hang off the
            # leaves.  It is off by default because pale organic litter (char straw, dry
            # branches) is legitimately low-saturation and a blanket cap eats it: measured, a
            # global 0.10 cap took `burned_ground_01` from 16 usable stamps to 3.
            share_cap = float(spec.get("achromatic_texel_max", 1.0))
            whole = value_mean > float(bright_v) and sat_mean < float(min_s)
            if whole or achromatic_share > share_cap:
                REJECTED_ISLANDS.append(
                    {
                        "source": f"{spec['cc0']}:{spec.get('prefix', '')}{spec.get('mask')}",
                        "texels": int(covered.sum()),
                        "box": [x0, y0, x1 - x0, y1 - y0],
                        "mean_value": round(value_mean, 4),
                        "mean_saturation": round(sat_mean, 4),
                        "achromatic_texel_share": round(achromatic_share, 4),
                        "why": "the whole island is bright achromatic"
                        if whole
                        else "too much bright achromatic texel area",
                    }
                )
                continue
            # Detail measured ON THE CUT-OUT, not on its bounding box.  It is what separates a
            # photographed sprig from the smooth UV-atlas junk that shares `pine_tree_01`'s
            # cut-out region: the junk is flat bars of colour, the sprig is needles.
            step = np.abs(np.diff(luma[window], axis=1, prepend=luma[window][:, :1]))
            detail = float(step[covered].mean())
            if detail < float(spec.get("detail_min", 0.0)):
                continue
            # r3 (D6): the colour under the alpha is dilated out of the island's own CORE
            # before the feather widens the cut, so the feathered rim carries foliage colour
            # instead of the photograph's backdrop.
            core = (cut >= float(spec.get("core_level", 0.6))).astype(np.float64)
            if not core.any():
                core = covered.astype(np.float64)
            rounds = int(spec.get("dilate_rounds", 6))
            stamps.append(
                Stamp(
                    base=_dilate_colour(maps["base"][window], core, rounds).astype(np.uint8),
                    opacity=_feather(cut, int(spec.get("feather_px", 1))),
                    normal=_dilate_colour(maps["normal"][window], core, rounds).astype(np.uint8),
                    roughness=_dilate_colour(maps["roughness"][window], core, rounds).astype(
                        np.uint8
                    ),
                    ao=_dilate_colour(maps["ao"][window], core, rounds).astype(np.uint8),
                    score=float(covered.sum()) ** 0.5 * (0.4 + detail),
                    source=f"{spec['cc0']}:{spec.get('prefix', '')}{spec.get('mask', 'alpha')}",
                )
            )
    stamps.sort(key=lambda s: -s.score)
    limit = int(spec.get("limit", 24))
    if not stamps:
        raise TextureError(f"{spec['cc0']}: no island survived the {spec.get('mask')} filters")
    stamps = stamps[:limit]
    pieces = spec.get("subdivide")
    if pieces:
        # `pine_tree_01` carries exactly TWO real sprigs on a sheet of bark and UV junk (the
        # rest of its cut-out region is flat colour bars, which is why the round-1 window
        # search kept landing on them).  Two stamps is not variety, so each sprig is also cut
        # into overlapping sub-patches: still the same photographed needles at the same
        # scale, but a different arrangement in every cell.
        count, fraction = int(pieces[0]), float(pieces[1])
        extra: list[Stamp] = []
        for order, stamp in enumerate(stamps):
            height, width = stamp.opacity.shape
            side_h = max(24, int(height * fraction))
            side_w = max(24, int(width * fraction))
            for step in range(count):
                phi = ((step + 1) * 0.6180339887) % 1.0
                psi = ((step + 1) * 0.7548776662) % 1.0
                y0 = int((height - side_h) * phi)
                x0 = int((width - side_w) * psi)
                window = (slice(y0, y0 + side_h), slice(x0, x0 + side_w))
                cut = stamp.opacity[window]
                if float((cut >= 0.5).mean()) < 0.02:
                    continue
                extra.append(
                    Stamp(
                        base=stamp.base[window].copy(),
                        opacity=cut.copy(),
                        normal=stamp.normal[window].copy(),
                        roughness=stamp.roughness[window].copy(),
                        ao=stamp.ao[window].copy(),
                        score=stamp.score * (0.9 ** (order + 1)),
                        source=f"{stamp.source}#sub{step}",
                    )
                )
        # r3 (M8): `subdivide_only` drops the PARENT stamps and keeps their sub-patches.
        # PINE_SPRIGS and PINE_NEEDLES are two different subdivisions of the SAME two sprigs,
        # so both pools begin with those two identical stamps -- and `stride`/`phase` only
        # separate WITHIN one pool.  That is why critic r2 found `f_pine_twig_a` and
        # `f_sapling_twig` sharing one stamp and `f_fir_twig_b` and `f_dwarf_pine` sharing
        # three, while DEV-10 claimed no two atlases carry the same stamp.  With the parents
        # dropped from the NEEDLES pools the two families cannot intersect at all.
        stamps = extra if spec.get("subdivide_only") else stamps + extra
        if not stamps:
            raise TextureError(f"{spec['cc0']}: subdivide_only left no stamps")
    stride = int(spec.get("stride", 1))
    if stride > 1:
        # Deal the pool out so two atlases off the same scan never carry the same stamps.
        stamps = stamps[int(spec.get("phase", 0)) % stride :: stride]
        if not stamps:
            raise TextureError(f"{spec['cc0']}: stride {stride} left no stamps")
    return stamps


#: r3 (D6): every island the achromatic filter threw away, for the texture manifest.
REJECTED_ISLANDS: list[dict] = []

_STAMP_CACHE: dict[tuple, list[Stamp]] = {}


def stamps_for(cache: Path, spec: dict) -> list[Stamp]:
    key = tuple(sorted((k, str(v)) for k, v in spec.items()))
    if key not in _STAMP_CACHE:
        _STAMP_CACHE[key] = cut_stamps(cache, spec)
    return _STAMP_CACHE[key]


def _rotate_stamp(stamp: Stamp, degrees: float, scale: float, mirror: bool) -> dict:
    """Rotate/scale/mirror one stamp, rotating the NORMAL's tangent frame with it."""
    width, height = stamp.size
    target = (max(4, round(width * scale)), max(4, round(height * scale)))
    out: dict[str, np.ndarray] = {}
    for role, array, mode in (
        ("base", stamp.base, "RGB"),
        ("normal", stamp.normal, "RGB"),
        ("roughness", stamp.roughness, "L"),
        ("ao", stamp.ao, "L"),
        ("opacity", np.clip(stamp.opacity * 255.0, 0, 255).astype(np.uint8), "L"),
    ):
        if mirror:
            array = np.ascontiguousarray(array[:, ::-1])
        image = Image.fromarray(array, mode).resize(target, Image.LANCZOS)
        # r3 (D6): rotate the DATA maps into their own mean, never into black.  `expand=True`
        # fills the new corners with `fillcolor` and the bicubic resample blends that colour
        # across the patch's outer border -- with black, that is a second source of the
        # near-black rim, on top of the compositing one.  Only the opacity map may go to 0.
        if role == "opacity":
            fill = 0
        elif role == "normal":
            fill = (128, 128, 255)
        elif mode == "L":
            fill = int(array.mean())
        else:
            fill = tuple(int(v) for v in array.reshape(-1, 3).mean(axis=0))
        out[role] = np.asarray(
            image.rotate(degrees, resample=Image.BICUBIC, expand=True, fillcolor=fill),
            dtype=np.uint8,
        )
    normal = out["normal"].astype(np.float64)
    nx = normal[..., 0] / 127.5 - 1.0
    ny = normal[..., 1] / 127.5 - 1.0
    if mirror:
        nx = -nx
    theta = math.radians(degrees)
    rx = nx * math.cos(theta) - ny * math.sin(theta)
    ry = nx * math.sin(theta) + ny * math.cos(theta)
    normal[..., 0] = np.clip((rx + 1.0) * 127.5, 0, 255)
    normal[..., 1] = np.clip((ry + 1.0) * 127.5, 0, 255)
    out["normal"] = normal.astype(np.uint8)
    return out


def _hue_degrees(rgb: np.ndarray) -> np.ndarray:
    """Hue in degrees (0..360) of an (..., 3) array, 0 where the texel is grey."""
    channels = rgb.astype(np.float64)
    r, g, b = channels[..., 0], channels[..., 1], channels[..., 2]
    high, low = channels.max(axis=-1), channels.min(axis=-1)
    delta = high - low
    safe = np.where(delta > 1e-6, delta, 1.0)
    hue = np.where(
        high == r,
        (g - b) / safe,
        np.where(high == g, (b - r) / safe + 2.0, (r - g) / safe + 4.0),
    )
    return np.where(delta > 1e-6, (hue * 60.0) % 360.0, 0.0)


def _rgb_to_hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high, low = rgb.max(axis=-1), rgb.min(axis=-1)
    saturation = np.where(high > 1e-6, (high - low) / np.maximum(high, 1e-6), 0.0)
    return _hue_degrees(rgb), saturation, high


def _hsv_to_rgb(hue: np.ndarray, saturation: np.ndarray, value: np.ndarray) -> np.ndarray:
    h = (hue % 360.0) / 60.0
    i = np.floor(h).astype(np.int64) % 6
    f = h - np.floor(h)
    p = value * (1.0 - saturation)
    q = value * (1.0 - saturation * f)
    t = value * (1.0 - saturation * (1.0 - f))
    r = np.choose(i, [value, q, p, p, t, value])
    g = np.choose(i, [t, value, value, q, p, p])
    b = np.choose(i, [p, p, t, value, value, q])
    return np.stack([r, g, b], axis=-1)


def albedo_stats(base: np.ndarray, opacity: np.ndarray, alpha_ref: int) -> dict:
    """Alpha-weighted albedo of the texels the alphaTest keeps: the census's own numbers."""
    rgb = np.clip(base.astype(np.float64) / 255.0, 0.0, 1.0)
    mask = opacity.astype(np.float64) >= float(alpha_ref)
    if mask.sum() < 16:
        return {"coverage": 0.0}
    hue, saturation, _value = _rgb_to_hsv(rgb)
    luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    radians = np.radians(hue[mask])
    mean_hue = math.degrees(
        math.atan2(float(np.sin(radians).mean()), float(np.cos(radians).mean()))
    )
    return {
        "coverage": round(float(mask.mean()), 4),
        "luma_srgb_mean": round(float(luma[mask].mean()), 4),
        "saturation_mean": round(float(saturation[mask].mean()), 4),
        "hue_deg_mean": round(mean_hue % 360.0, 1),
        "mean_rgb": [round(float(v), 4) for v in rgb[mask].mean(axis=0)],
        "green_minus_red_mean": round(float((rgb[mask][:, 1] - rgb[mask][:, 0]).mean()), 4),
    }


def grade_cell(
    base: np.ndarray, opacity01: np.ndarray, alpha_ref: int, target: dict, rounds: int = 3
) -> np.ndarray:
    """Move a cell's alpha-weighted albedo onto a MEASURED stock band (r9).

    The bar: ECUSA's douglas-fir card reads sRGB luma 0.218, saturation 0.539, hue 84.5;
    italy's scots pine 0.220 / 0.617 / 73.6; WCUSA's radiata 0.308 / 0.483 / 70.4
    (``b3/r9/stock_census.json``).  r8's twig atlases read 0.32-0.34 / 0.41-0.55 / 68-88 with
    red >= green on the pines -- the "bright yellow-green" every frame showed.  The grade is
    three passes of hue shift, saturation scale and luma scale on the texels the alphaTest
    keeps, measured the way the census measured stock, so the shipped number can be quoted
    against the stock number in the same units.
    """
    rgb = np.clip(base.astype(np.float64) / 255.0, 0.0, 1.0)
    mask = opacity01 * 255.0 >= float(alpha_ref)
    if mask.sum() < 16:
        return base
    for _ in range(rounds):
        hue, saturation, value = _rgb_to_hsv(rgb)
        radians = np.radians(hue[mask])
        mean_hue = math.degrees(
            math.atan2(float(np.sin(radians).mean()), float(np.cos(radians).mean()))
        )
        if "hue" in target:
            hue = (hue + (float(target["hue"]) - mean_hue)) % 360.0
        if "sat" in target:
            saturation = np.clip(
                saturation * float(target["sat"]) / max(float(saturation[mask].mean()), 1e-3),
                0.0,
                1.0,
            )
        rgb = _hsv_to_rgb(hue, saturation, value)
        if "luma" in target:
            luma = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
            rgb = np.clip(
                rgb * (float(target["luma"]) / max(float(luma[mask].mean()), 1e-3)), 0.0, 1.0
            )
    return np.clip(rgb * 255.0, 0, 255)


def _stamp_axis(stamp: Stamp) -> tuple[float, float, float]:
    """(direction of base -> tip in image degrees, length px along it, width px across it).

    A sprig's tip is the narrow end: the principal axis of the alpha, and the end that holds
    fewer texels in its outer 35 % is the tip.
    """
    mask = stamp.opacity >= 0.5
    ys, xs = np.nonzero(mask)
    if len(xs) < 8:
        return -90.0, float(max(stamp.size)), float(min(stamp.size))
    cx, cy = float(xs.mean()), float(ys.mean())
    cov = np.cov(np.stack([xs - cx, ys - cy]).astype(np.float64))
    eigen, vectors = np.linalg.eigh(cov)
    axis = vectors[:, int(np.argmax(eigen))]
    along = (xs - cx) * axis[0] + (ys - cy) * axis[1]
    across = -(xs - cx) * axis[1] + (ys - cy) * axis[0]
    low, high = float(along.min()), float(along.max())
    span = high - low
    n_low = int((along < low + 0.35 * span).sum())
    n_high = int((along > high - 0.35 * span).sum())
    if n_high > n_low:
        axis = -axis
    return (
        math.degrees(math.atan2(float(axis[1]), float(axis[0]))),
        span,
        float(across.max() - across.min()),
    )


def _paste_under(
    acc: dict, cell_op: np.ndarray, piece: dict, top_left: tuple[int, int], tint
) -> None:
    """Composite one rotated piece UNDER what the cell already holds (premultiplied)."""
    cell_h, cell_w = cell_op.shape
    ph, pw = piece["opacity"].shape
    ox, oy = top_left
    x0, y0 = max(0, ox), max(0, oy)
    x1, y1 = min(cell_w, ox + pw), min(cell_h, oy + ph)
    if x1 <= x0 or y1 <= y0:
        return
    src = (slice(y0 - oy, y1 - oy), slice(x0 - ox, x1 - ox))
    dst = (slice(y0, y1), slice(x0, x1))
    base = piece["base"][src].astype(np.float64)
    if tuple(tint) != (1.0, 1.0, 1.0):
        base = np.clip(base * np.asarray(tint, dtype=np.float64).reshape(1, 1, 3), 0, 255)
    flat = np.clip(piece["opacity"][src].astype(np.float64) / 255.0, 0.0, 1.0)
    contribution = flat * (1.0 - cell_op[dst])
    weight = contribution[..., None]
    acc["rgb"][dst] += base * weight
    acc["nrm"][dst] += piece["normal"][src].astype(np.float64) * weight
    acc["rgh"][dst] += piece["roughness"][src].astype(np.float64) * contribution
    acc["ao"][dst] += piece["ao"][src].astype(np.float64) * contribution
    cell_op[dst] += contribution


#: r9 spray cell defaults: a stem with herringbone sprigs, base at the cell's bottom
SPRAY_DEFAULT = dict(
    pairs=(4, 7),  # sprig pairs along the stem
    angle_deg=(30.0, 58.0),  # a sprig's angle off the stem
    scale=(0.30, 0.44),  # a base sprig's length, share of the cell's height
    taper=0.55,  # the tip sprig's length relative to a base sprig's
    stem_width=(0.014, 0.024),  # stem width at the base, share of the cell's width
    stem_colour=(86, 68, 50),
    tip_stamps=(1, 2),
    lean_deg=12.0,  # the stem's lean off vertical
    spread=(0.08, 0.90),  # where along the stem the pairs sit (0 = base)
    centroid_at=0.45,  # a sprig's alpha centroid sits this far out along its own axis
)


def compose_spray_atlas(material: dict, cache: Path) -> dict[str, np.ndarray]:
    """One atlas of SPRAY cells: a twig with herringbone sprigs, base down (r9).

    r2-r8 stamped 16-34 sub-patches of the two pine sprigs into each cell at free
    rotations -- confetti, which the orchestrator read on the r8 frames as "broadleaf
    speckle".  A conifer's foliage unit is a spray: a shoot with sprigs left and right,
    shorter toward the tip.  Every cell here is one such spray built from the WHOLE
    photographed sprigs, oriented along their own principal axis with the tip outward, the
    stem drawn under them, and the card hangs by its base (v = 0) on the branch it grows
    from (``blender_forest._spray_card``).
    """
    size = material["size"]
    cols, rows = material["grid"]
    cell_w, cell_h = size // cols, size // rows
    params = dict(SPRAY_DEFAULT, **material.get("spray", {}))
    pool: list[tuple[Stamp, float, tuple[float, float, float]]] = []
    for spec in material["sources"]:
        weight = float(spec.get("weight", 1.0))
        tint = tuple(float(v) for v in spec.get("stamp_tint", (1.0, 1.0, 1.0)))
        cut = stamps_for(cache, spec)
        for stamp in cut:
            pool.append((stamp, weight / len(cut), tint))
    if not pool:
        raise TextureError(f"{material['key']}: no stamps")
    weights = np.array([w for _, w, _ in pool], dtype=np.float64)
    weights = weights / weights.sum()
    axes = [_stamp_axis(stamp) for stamp, _, _ in pool]
    out = {
        "base": np.zeros((size, size, 3), dtype=np.float64),
        "normal": np.tile(np.array([128.0, 128.0, 255.0]), (size, size, 1)),
        "roughness": np.full((size, size), 170.0),
        "ao": np.full((size, size), 255.0),
        "opacity": np.zeros((size, size), dtype=np.float64),
    }
    grade = material.get("grade")
    alpha_ref = int(material.get("alphaRef", 64))
    flat_normal = np.array([128.0, 128.0, 255.0])
    for index in range(cols * rows):
        col, row = index % cols, index // cols
        x0, y0 = col * cell_w, row * cell_h
        rng = _rng(material["key"], "spray", index)
        acc = {
            "rgb": np.zeros((cell_h, cell_w, 3)),
            "nrm": np.zeros((cell_h, cell_w, 3)),
            "rgh": np.zeros((cell_h, cell_w)),
            "ao": np.zeros((cell_h, cell_w)),
        }
        cell_op = np.zeros((cell_h, cell_w))
        # the stem: base at the bottom centre, tip near the top, leaning a little
        lean = math.radians(float(rng.uniform(-params["lean_deg"], params["lean_deg"])))
        base_pt = np.array([cell_w * 0.5 + rng.uniform(-0.06, 0.06) * cell_w, cell_h * 0.97])
        length = cell_h * 0.90
        tip_pt = base_pt + length * np.array([math.sin(lean), -math.cos(lean)])
        stem_dir = (tip_pt - base_pt) / max(float(np.linalg.norm(tip_pt - base_pt)), 1e-6)
        stem_deg = math.degrees(math.atan2(float(stem_dir[1]), float(stem_dir[0])))
        placements: list[tuple[float, float, float]] = []  # (t along the stem, side, size)
        pairs = rng.integers(params["pairs"][0], params["pairs"][1] + 1)
        lo, hi = params["spread"]
        for k in range(pairs):
            t = lo + (hi - lo) * (k + 0.5) / pairs
            for side in (-1.0, 1.0):
                placements.append((t + rng.uniform(-0.03, 0.03), side, rng.uniform(0.85, 1.15)))
        tips = rng.integers(params["tip_stamps"][0], params["tip_stamps"][1] + 1)
        for _ in range(tips):
            placements.append((rng.uniform(0.93, 1.0), 0.0, rng.uniform(0.6, 0.85)))
        # tip first, base last: the base sprigs go UNDER the tip ones
        placements.sort(key=lambda entry: -entry[0])
        for t, side, jitter in placements:
            choice = int(rng.choice(len(pool), p=weights))
            stamp, _, tint = pool[choice]
            axis_deg, span_px, _width = axes[choice]
            angle = float(rng.uniform(*params["angle_deg"])) * side
            theta = stem_deg + angle + float(rng.uniform(-6.0, 6.0))
            scale_share = float(rng.uniform(*params["scale"])) * jitter
            scale_share *= 1.0 - (1.0 - params["taper"]) * max(0.0, min(1.0, t))
            scale = float(np.clip(scale_share * cell_h / max(span_px, 1.0), 0.05, 1.5))
            mirror = bool(rng.integers(0, 2))
            # a mirror flips the image left-right, so the axis angle a -> 180 - a
            axis_here = (180.0 - axis_deg) if mirror else axis_deg
            # PIL rotates counter-clockwise on screen, which in y-down image coordinates
            # turns a direction of angle a into a - degrees: rotate by (axis - target)
            piece = _rotate_stamp(stamp, axis_here - theta, scale, mirror)
            flat = piece["opacity"].astype(np.float64)
            ys, xs = np.nonzero(flat >= 128)
            if not len(xs):
                continue
            centroid = np.array([xs.mean(), ys.mean()])
            direction = np.array([math.cos(math.radians(theta)), math.sin(math.radians(theta))])
            anchor = base_pt + (tip_pt - base_pt) * max(0.0, min(1.0, t))
            wanted = anchor + direction * (params["centroid_at"] * span_px * scale)
            top_left = (round(wanted[0] - centroid[0]), round(wanted[1] - centroid[1]))
            _paste_under(acc, cell_op, piece, top_left, tint)
        # the stem, under everything: a tapered brown line with a little colour noise
        stem_mask = Image.new("L", (cell_w, cell_h), 0)
        draw = ImageDraw.Draw(stem_mask)
        width0 = max(2, round(float(rng.uniform(*params["stem_width"])) * cell_w))
        segments = 6
        for s in range(segments):
            a = base_pt + (tip_pt - base_pt) * (s / segments)
            b = base_pt + (tip_pt - base_pt) * ((s + 1) / segments)
            width = max(1, round(width0 * (1.0 - 0.7 * (s + 0.5) / segments)))
            draw.line(
                [(float(a[0]), float(a[1])), (float(b[0]), float(b[1]))], fill=255, width=width
            )
        stem_alpha = np.asarray(stem_mask, dtype=np.float64) / 255.0
        noise = 1.0 + 0.10 * rng.standard_normal((cell_h, cell_w, 1))
        stem_rgb = np.clip(
            np.asarray(params["stem_colour"], dtype=np.float64).reshape(1, 1, 3) * noise, 0, 255
        )
        stem_piece = {
            "base": stem_rgb,
            "opacity": np.clip(stem_alpha * 255.0, 0, 255),
            "normal": np.tile(flat_normal, (cell_h, cell_w, 1)),
            "roughness": np.full((cell_h, cell_w), 215.0),
            "ao": np.full((cell_h, cell_w), 230.0),
        }
        _paste_under(acc, cell_op, stem_piece, (0, 0), (1.0, 1.0, 1.0))
        covered = cell_op > 1e-3
        denominator = np.maximum(cell_op, 1e-6)
        cell_rgb = np.where(covered[..., None], acc["rgb"] / denominator[..., None], 0.0)
        cell_nrm = np.where(covered[..., None], acc["nrm"] / denominator[..., None], flat_normal)
        cell_rgh = np.where(covered, acc["rgh"] / denominator, 170.0)
        cell_ao = np.where(covered, acc["ao"] / denominator, 255.0)
        cell_rgb = _bleed(cell_rgb, cell_op)
        if grade:
            cell_rgb = grade_cell(cell_rgb, np.clip(cell_op, 0.0, 1.0), alpha_ref, grade)
        out["base"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_rgb
        out["normal"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_nrm
        out["roughness"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_rgh
        out["ao"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_ao
        out["opacity"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_op * 255.0
    return {
        "base": np.clip(out["base"], 0, 255).astype(np.uint8),
        "normal": np.clip(out["normal"], 0, 255).astype(np.uint8),
        "roughness": np.clip(out["roughness"], 0, 255).astype(np.uint8),
        "ao": np.clip(out["ao"], 0, 255).astype(np.uint8),
        "opacity": np.clip(out["opacity"], 0, 255).astype(np.uint8),
    }


def compose_atlas(material: dict, cache: Path) -> dict[str, np.ndarray]:
    """One atlas whose every cell is real photographed foliage, stamped in.

    Each cell takes ``per_cell`` stamps drawn from the material's own weighted source list at
    its own rotation, scale, mirror and tint, so sixteen cells of one atlas -- and six atlases
    off two scans -- are all genuinely different arrangements of real needles.
    """
    size = material["size"]
    cols, rows = material["grid"]
    cell_w, cell_h = size // cols, size // rows

    def _pool(sources):
        pool: list[tuple[Stamp, float]] = []
        tints: list[tuple[float, float, float]] = []
        for spec in sources:
            weight = float(spec.get("weight", 1.0))
            # A PER-SOURCE tint, so one atlas can carry green fern fronds and BROWN
            # fallen-needle clumps side by side: `gc_litter` is design §4.5's "fern fronds,
            # needle clumps, twig bundles", and a needle clump on the forest floor is dead,
            # not live.
            tint = tuple(float(v) for v in spec.get("stamp_tint", (1.0, 1.0, 1.0)))
            cut = stamps_for(cache, spec)
            # The weight is the SOURCE's share of the cell, split over its stamps.  Weighting
            # per stamp instead makes the share proportional to how many islands a source
            # happens to yield: `fern_02` cuts 5 fronds and `fir_tree_01` 42 needle patches,
            # so a nominal 0.24 / 0.10 split came out 1.2 / 4.2 and the litter atlas had no
            # ferns in it at all.
            for stamp in cut:
                pool.append((stamp, weight / len(cut)))
                tints.append(tint)
        if not pool:
            raise TextureError(f"{material['key']}: no stamps")
        weights = np.array([w for _, w in pool], dtype=np.float64)
        return pool, tints, weights / weights.sum()

    # r9: `cell_sources` gives each RANGE of cells its own pool, so the three covers that
    # share one atlas (litter cells 0-5, ferns 6-10, needle mat 11-15) are three different
    # things instead of one mixture drawn three times -- r8's "fern" cover was the litter
    # mixture with the rust-tinted needle clumps in it, which is the hay-coloured carpet.
    ranges = []
    for start, stop, sources in material.get("cell_sources", ()):
        ranges.append((int(start), int(stop), _pool(sources)))
    default_pool = _pool(material["sources"]) if material.get("sources") else None
    if default_pool is None and not ranges:
        raise TextureError(f"{material['key']}: no stamps")
    grade = material.get("grade")
    alpha_ref = int(material.get("alphaRef", 64))
    out = {
        "base": np.zeros((size, size, 3), dtype=np.float64),
        "normal": np.tile(np.array([128.0, 128.0, 255.0]), (size, size, 1)),
        "roughness": np.full((size, size), 170.0),
        "ao": np.full((size, size), 255.0),
        "opacity": np.zeros((size, size), dtype=np.float64),
    }
    per_cell = material.get("per_cell", (2, 4))
    span = material.get("stamp_span", (0.55, 0.95))  # long side, as a fraction of the cell
    upright = float(material.get("upright_deg", 180.0))
    root = bool(material.get("rooted", False))
    for index in range(cols * rows):
        col, row = index % cols, index // cols
        x0, y0 = col * cell_w, row * cell_h
        rng = _rng(material["key"], "cell", index)
        chosen = next(
            (entry for start, stop, entry in ranges if start <= index < stop), default_pool
        )
        if chosen is None:
            raise TextureError(f"{material['key']}: cell {index} has no source pool")
        pool, tints, weights = chosen
        # r3 (D6): the cell accumulates in PREMULTIPLIED alpha and is divided out at the end.
        # r2 composited straight `src*a + dst*(1-a)` onto a cell cleared to BLACK, so every
        # partially transparent texel -- which is every texel of the feathered cut edge -- came
        # out multiplied by its own alpha.  That, not the source photographs, is where the
        # near-black rim measured on four covers came from.
        acc_rgb = np.zeros((cell_h, cell_w, 3))
        acc_nrm = np.zeros((cell_h, cell_w, 3))
        acc_rgh = np.zeros((cell_h, cell_w))
        acc_ao = np.zeros((cell_h, cell_w))
        cell_op = np.zeros((cell_h, cell_w))
        for _ in range(int(rng.integers(per_cell[0], per_cell[1] + 1))):
            choice = int(rng.choice(len(pool), p=weights))
            stamp = pool[choice][0]
            stamp_tint = tints[choice]
            width, height = stamp.size
            want = rng.uniform(*span) * max(cell_w, cell_h)
            scale = float(np.clip(want / max(width, height), 0.10, 1.30))
            degrees = float(rng.uniform(-upright, upright))
            piece = _rotate_stamp(stamp, degrees, scale, bool(rng.integers(0, 2)))
            ph, pw = piece["opacity"].shape
            if ph >= cell_h or pw >= cell_w:
                crop_y = max(0, (ph - cell_h) // 2 + 1)
                crop_x = max(0, (pw - cell_w) // 2 + 1)
                keep_h, keep_w = min(ph, cell_h - 1), min(pw, cell_w - 1)
                piece = {
                    k: v[crop_y : crop_y + keep_h, crop_x : crop_x + keep_w]
                    for k, v in piece.items()
                }
                ph, pw = piece["opacity"].shape
            ox = int(rng.integers(0, max(1, cell_w - pw)))
            oy = (
                int(cell_h - ph - rng.integers(0, max(1, int(cell_h * 0.08))))
                if root
                else int(rng.integers(0, max(1, cell_h - ph)))
            )
            oy = max(0, min(oy, cell_h - ph))
            if stamp_tint != (1.0, 1.0, 1.0):
                piece["base"] = apply_tint(piece["base"], stamp_tint)
            flat = np.clip(piece["opacity"].astype(np.float64) / 255.0, 0.0, 1.0)
            window = (slice(oy, oy + ph), slice(ox, ox + pw))
            # "over" in premultiplied space: the new stamp goes UNDER what is already there
            contribution = flat * (1.0 - cell_op[window])
            weight = contribution[..., None]
            acc_rgb[window] += piece["base"] * weight
            acc_nrm[window] += piece["normal"] * weight
            acc_rgh[window] += piece["roughness"] * contribution
            acc_ao[window] += piece["ao"] * contribution
            cell_op[window] += contribution
        covered = cell_op > 1e-3
        denominator = np.maximum(cell_op, 1e-6)
        cell_rgb = np.where(covered[..., None], acc_rgb / denominator[..., None], 0.0)
        cell_nrm = np.where(
            covered[..., None],
            acc_nrm / denominator[..., None],
            np.array([128.0, 128.0, 255.0]),
        )
        cell_rgh = np.where(covered, acc_rgh / denominator, 170.0)
        cell_ao = np.where(covered, acc_ao / denominator, 255.0)
        cell_rgb = _bleed(cell_rgb, cell_op)
        if grade:
            cell_rgb = grade_cell(cell_rgb, np.clip(cell_op, 0.0, 1.0), alpha_ref, grade)
        out["base"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_rgb
        out["normal"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_nrm
        out["roughness"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_rgh
        out["ao"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_ao
        out["opacity"][y0 : y0 + cell_h, x0 : x0 + cell_w] = cell_op * 255.0
    return {
        "base": np.clip(out["base"], 0, 255).astype(np.uint8),
        "normal": np.clip(out["normal"], 0, 255).astype(np.uint8),
        "roughness": np.clip(out["roughness"], 0, 255).astype(np.uint8),
        "ao": np.clip(out["ao"], 0, 255).astype(np.uint8),
        "opacity": np.clip(out["opacity"], 0, 255).astype(np.uint8),
    }


def _channel(path: Path, role: str) -> np.ndarray:
    """A single-channel data map: a dedicated map, or the right slice of a packed `arm`."""
    if "_arm" in path.name:
        return _load(path, mode="RGB")[..., ARM_CHANNEL[role]]
    return _load(path, mode="L")


def derived_ao(normal: np.ndarray) -> np.ndarray:
    """AO from the normal map's Z when Poly Haven ships neither an ``ao`` nor an ``arm`` map.

    ``rock_moss_set_01/_02`` publish diff / nor_gl / rough only.  The blue channel of a
    tangent-space normal is cos(slope), so ``0.55 + 0.45 cos(slope)`` darkens creases and
    leaves flats untouched -- a cavity proxy, recorded as such rather than a measured bake.
    """
    nz = normal[..., 2].astype(np.float64) / 255.0
    return np.clip((0.55 + 0.45 * nz) * 255.0, 0, 255).astype(np.uint8)


def _optional(cache: Path, asset: str, names: tuple[str, ...]) -> Path | None:
    try:
        return _find(cache, asset, names)
    except TextureError:
        return None


def cook_tile(material: dict, cache: Path) -> dict[str, np.ndarray]:
    """A plain tiling surface (bark, rock): resample every role to the shipped size."""
    size = material["size"]
    asset = material["cc0"]
    out = {
        "base": _load(_find(cache, asset, TEXTURE_SOURCES["base"]), size, "RGB"),
        "normal": _load(_find(cache, asset, TEXTURE_SOURCES["normal"]), size, "RGB"),
    }
    out["roughness"] = _resize_l(
        _channel(_find(cache, asset, TEXTURE_SOURCES["roughness"]), "roughness"), size
    )
    ao_path = _optional(cache, asset, TEXTURE_SOURCES["ao"])
    out["ao"] = (
        _resize_l(_channel(ao_path, "ao"), size)
        if ao_path is not None
        else derived_ao(out["normal"])
    )
    # a fully opaque cut-out: see forest_spec.MATERIAL_ROLES -- alphaTest without an
    # opacityMap renders the engine's placeholder material (measured live)
    out["opacity"] = np.full((size, size), 255, dtype=np.uint8)
    return out


def _resize_l(array: np.ndarray, size: int) -> np.ndarray:
    if array.shape[0] == size and array.shape[1] == size:
        return array
    with Image.fromarray(array, "L") as image:
        return np.asarray(image.resize((size, size), Image.LANCZOS), dtype=np.uint8)


def apply_tint(base: np.ndarray, tint) -> np.ndarray:
    factors = np.asarray(tint, dtype=np.float64).reshape(1, 1, 3)
    return np.clip(base.astype(np.float64) * factors, 0, 255).astype(np.uint8)


#: r9: every cut-out foliage map ships at least this rough.  r8's twig atlases carried the
#: scans' own roughness (0.63-0.70) and the imposter bake lit them like satin; stock foliage
#: is matte, and the dense-alpha sapling that baked right was the roughest of the set.
FOLIAGE_ROUGHNESS_FLOOR = 0.82

#: r9: what the last cook measured, per material -- written into the textures manifest so
#: the report quotes a shipped number, not a target.
COOK_STATS: dict[str, dict] = {}


def cook_material(material: dict, cache: Path) -> dict[str, bytes]:
    kind = material.get("kind", "rock")
    if material.get("compose") == "spray":
        maps = compose_spray_atlas(material, cache)  # r9: one spray per cell
    elif material.get("sources") or material.get("cell_sources"):
        maps = compose_atlas(material, cache)  # the cut-out pipeline: real photographed islands
    elif kind in ("tile", "rock"):
        maps = cook_tile(material, cache)
    else:
        # r3: there is no third path any more.  Every cut-out material names its sources and
        # the generated-mask cook is deleted, so this cannot silently fall back to a drawn mask.
        raise TextureError(f"{material['key']}: a {kind!r} material must name its `sources`")
    maps["base"] = apply_tint(maps["base"], material.get("tint", (1.0, 1.0, 1.0)))
    if "alphaRef" in material and kind not in ("tile", "rock"):
        # r11 (critic B10-2): what the source filter's outline clause deliberately let through
        # is removed HERE, by the gate's own test, at the cell -- the foreign area itself and
        # not a multiple of it.  Runs on the tinted albedo, i.e. on the bytes that ship.
        maps = scrub_foreign(maps, material)
        floor = round(255 * float(material.get("roughness_floor", FOLIAGE_ROUGHNESS_FLOOR)))
        covered = maps["opacity"] > 0
        maps["roughness"] = np.where(
            covered, np.maximum(maps["roughness"], floor), maps["roughness"]
        ).astype(np.uint8)
        if material.get("ao_floor") is not None:
            # r12 (critic B11-5): a model atlas's AO is black in its UV padding, and a leaf
            # island cut with `offcolour` carries some of that padding under its alpha --
            # `f_shrub_leaf_03` shipped 6.0 % of its opaque texels at AO < 0.05, black under
            # any light.  Floored on the covered texels only, like the roughness above.
            ao_floor = round(255 * float(material["ao_floor"]))
            maps["ao"] = np.where(covered, np.maximum(maps["ao"], ao_floor), maps["ao"]).astype(
                np.uint8
            )
        COOK_STATS[material["key"]] = {
            **albedo_stats(maps["base"], maps["opacity"], int(material["alphaRef"])),
            "roughness_mean": (
                round(float(maps["roughness"][covered].mean()) / 255.0, 4)
                if covered.any()
                else None
            ),
            "ao_p05": (
                round(float(np.percentile(maps["ao"][covered], 5)) / 255.0, 4)
                if covered.any()
                else None
            ),
            "alphaRef": int(material["alphaRef"]),
        }
    roles = fs.MATERIAL_ROLES[kind]
    return {fs.texture_relative(material["key"], role): _png(maps[role]) for role in roles}


# ============================================================================================
# r10 (critic B9-2): the FOREIGN-GEOMETRY audit -- every cell of every atlas we ship
# ============================================================================================
# The r9 cut shipped, on `gc_litter` cell (0,1), a pale grey bevelled shape a player reads as
# a capital "A", drawn by three GroundCover layers at probability 0.92 out to 50 m.  It was not
# text: it was a cluster of `dry_branches_medium_01`'s flat scan-backdrop facets, desaturated
# by the litter grade.  Nothing in the r9 gate looked at a cell as a PICTURE, so it shipped.
#
# What a facet, a letterform and a UV-padding tab all are, and a photographed needle, blade,
# frond, leaf or bark chip is not, is a piece of FLAT SHADING BOUNDED BY STRAIGHT EDGES.  Both
# halves are needed: a broad autumn leaf is flat but its outline is a leaf (measured:
# `f_shrub_leaf_01` cell 7 carries 665 flat texels at straight-share 0.05-0.21), and a stem is
# straight but not flat.  The audit therefore reports, per cell, the largest connected region
# that is BOTH, and the gate fails a cell that carries one bigger than the cap.
AUDIT = {
    "flat_level": 4.0,  # local luma std below this is "flat shading"
    "flat_radius": 6,  # ...over a patch at least 2r+1 texels wide
    "straight_share": 0.34,  # ...whose boundary is at least this straight
    "straight_run": 10,  # a straight run is this many boundary texels on one line
    # ...and is CHUNKY rather than blade-shaped: area over the square of its longest side.  A
    # reed blade and a grass stem are flat and straight and legitimate; measured on the r9
    # tree they sit at 0.05-0.09 while the facet slabs sit at 0.16-0.52.
    "compact_min": 0.12,
    "max_texels": 96,  # per cell, at 256 square: 0.15 % of the cell
    # r11 (critic N-4): THE GATE'S OWN FOUNDING CASE did not fire.  On r9's shipped bytes the
    # `gc_litter` cell (0,1) slab -- the shape a person read as a capital "A", the reason this
    # gate exists -- measures `straight_share` 0.2276 against the 0.34 bar, and 0.3103 at the
    # most favourable run length there is (`r11/n4_calibrate.json`): r9's `gc_litter` failed
    # through cells 4 and 5, not through the letter.  `straight_share` asks for long straight
    # RUNS, and a small bevelled glyph has six or seven SHORT edges, none of them long enough.
    #
    # A polygon has few EDGE DIRECTIONS whatever the length of its edges.  `polygonality`
    # measures that -- the boundary's tangent-angle histogram, share carried by the strongest
    # four bins -- and it separates cleanly (`r11/polygonality.json`): the "A" reads **0.465**,
    # every chunky flat region of the r11 shipped atlases reads **at most 0.452**, and r9's
    # worst reads 0.846.  A region is foreign if it is flat, chunky, over the cap, and EITHER
    # long-edged or few-directioned.  The compactness clause still protects a reed blade and a
    # grass stem, which are legitimately straight AND few-directioned.
    "polygon_share": 0.45,
}


def _boundary(mask: np.ndarray) -> np.ndarray:
    inner = mask & np.roll(mask, 1, 0) & np.roll(mask, -1, 0)
    inner &= np.roll(mask, 1, 1) & np.roll(mask, -1, 1)
    return mask & ~inner


def straight_share(mask: np.ndarray, run: int = 10, angles: int = 36) -> float:
    """Share of one region's boundary texels that lie on a long straight line.

    For each of ``angles`` orientations the boundary is projected onto the line's normal and
    binned at one texel; a bin holding ``run`` or more texels that are contiguous along the
    line (span within 1.6x their count) is a straight edge, and its texels are marked.  A
    polygon facet is fenced by a handful of such lines; an organic outline is fenced by none.
    """
    edge = _boundary(mask)
    ys, xs = np.nonzero(edge)
    if len(ys) < run:
        return 0.0
    on_line = np.zeros(len(ys), dtype=bool)
    for step in range(angles):
        theta = np.pi * step / angles
        cos, sin = float(np.cos(theta)), float(np.sin(theta))
        normal = np.round(xs * -sin + ys * cos).astype(np.int64)
        along = xs * cos + ys * sin
        order = np.lexsort((along, normal))
        keys = normal[order]
        starts = np.flatnonzero(np.r_[True, keys[1:] != keys[:-1]])
        stops = np.r_[starts[1:], len(keys)]
        for lo, hi in zip(starts.tolist(), stops.tolist(), strict=True):
            if hi - lo < run:
                continue
            block = order[lo:hi]
            span = float(along[block].max() - along[block].min()) + 1.0
            if span <= 1.6 * (hi - lo):
                on_line[block] = True
    return float(on_line.mean())


def polygonality(mask: np.ndarray, bins: int = 36, top: int = 4) -> float:
    """Share of one region's boundary tangent-angle weight carried by the strongest bins.

    r11 (critic N-4).  `straight_share` asks how much of a boundary lies on long straight runs;
    this asks how FEW DIRECTIONS the boundary uses, which is what a polygon has whether its
    edges are long or short.  The gradient is box-smoothed first so a stair-stepped diagonal
    reads as one direction rather than as a mixture of horizontal and vertical steps, and the
    histogram is blurred by one bin so a straight edge that falls between two bins is not
    penalised for it.
    """
    field = mask.astype(np.float64)
    gy = np.zeros_like(field)
    gx = np.zeros_like(field)
    gy[1:-1, :] = field[2:, :] - field[:-2, :]
    gx[:, 1:-1] = field[:, 2:] - field[:, :-2]
    gy, gx = _box_mean(gy, 2), _box_mean(gx, 2)
    edge = _boundary(mask)
    weight = np.hypot(gx, gy)[edge]
    if weight.sum() <= 0:
        return 0.0
    angle = (np.arctan2(gy[edge], gx[edge]) % np.pi) / np.pi * bins
    hist = np.zeros(bins)
    np.add.at(hist, np.clip(angle.astype(int), 0, bins - 1), weight)
    hist = hist / hist.sum()
    blurred = hist + 0.5 * (np.roll(hist, 1) + np.roll(hist, -1))
    return float(np.sort(blurred)[-top:].sum() / blurred.sum())


def _is_foreign(region: np.ndarray, cfg: dict) -> tuple[int, float, float, float]:
    """(foreign texels, straight share, polygonality, compactness) of one flat region."""
    area = int(region.sum())
    share = straight_share(region, int(cfg["straight_run"]))
    ys, xs = np.nonzero(region)
    extent = max(int(ys.max() - ys.min()) + 1, int(xs.max() - xs.min()) + 1)
    fat = area / float(extent * extent)
    poly = polygonality(region) if share < float(cfg["straight_share"]) else 1.0
    edged = share >= float(cfg["straight_share"]) or poly >= float(cfg["polygon_share"])
    return (area if edged and fat >= float(cfg["compact_min"]) else 0), share, poly, fat


def audit_cells(
    colour: np.ndarray, opacity: np.ndarray, grid, alpha_ref: int, settings: dict | None = None
) -> list[dict]:
    """Per cell of one atlas: the worst flat-and-straight region in it.

    ``colour`` is the cooked albedo, ``opacity`` the cooked opacity map, both at ship
    resolution; ``grid`` is the material's own (cols, rows).
    """
    cfg = dict(AUDIT)
    cfg.update(settings or {})
    size = colour.shape[0]
    cols, rows = int(grid[0]), int(grid[1])
    cell_w, cell_h = size // cols, size // rows
    rgb = colour.astype(np.float64)
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    covered = opacity >= alpha_ref
    flat = (_local_std(luma) < float(cfg["flat_level"])) & covered
    seeds = _box_mean(flat.astype(np.float64), int(cfg["flat_radius"])) > 0.985
    out: list[dict] = []
    for index in range(cols * rows):
        col, row = index % cols, index // cols
        win = (slice(row * cell_h, (row + 1) * cell_h), slice(col * cell_w, (col + 1) * cell_w))
        cell_flat, cell_seed = flat[win], seeds[win]
        worst = {
            "cell": index,
            "covered_texels": int(covered[win].sum()),
            "flat_texels": 0,
            "straight_share": 0.0,
            "polygonality": 0.0,
            "compactness": 0.0,
            "foreign_texels": 0,
        }
        if cell_seed.any():
            labels, _count = _label(cell_flat)
            for tag in np.unique(labels[cell_seed & (labels > 0)]).tolist():
                region = labels == tag
                area = int(region.sum())
                foreign, share, poly, fat = _is_foreign(region, cfg)
                if (foreign, area) > (worst["foreign_texels"], worst["flat_texels"]):
                    worst["flat_texels"] = area
                    worst["straight_share"] = round(share, 4)
                    worst["polygonality"] = round(poly, 4)
                    worst["compactness"] = round(fat, 4)
                    worst["foreign_texels"] = foreign
        out.append(worst)
    return out


#: r11 (critic B10-2): what `scrub_foreign` took out of each atlas, per material.
SCRUB_STATS: dict[str, dict] = {}


def foreign_regions(colour, opacity, grid, alpha_ref: int, settings: dict | None = None):
    """Every region of an atlas the audit gate calls foreign, as one boolean mask.

    Same test as :func:`audit_cells`, but it returns the pixels rather than a count, so what
    the gate objects to can be REMOVED instead of merely reported.
    """
    cfg = dict(AUDIT)
    cfg.update(settings or {})
    size = colour.shape[0]
    cols, rows = int(grid[0]), int(grid[1])
    cell_w, cell_h = size // cols, size // rows
    rgb = colour.astype(np.float64)
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    covered = opacity >= alpha_ref
    flat = (_local_std(luma) < float(cfg["flat_level"])) & covered
    seeds = _box_mean(flat.astype(np.float64), int(cfg["flat_radius"])) > 0.985
    mask = np.zeros(covered.shape, dtype=bool)
    found = 0
    for index in range(cols * rows):
        col, row = index % cols, index // cols
        win = (slice(row * cell_h, (row + 1) * cell_h), slice(col * cell_w, (col + 1) * cell_w))
        cell_flat, cell_seed = flat[win], seeds[win]
        if not cell_seed.any():
            continue
        labels, _count = _label(cell_flat)
        cell_mask = np.zeros(cell_flat.shape, dtype=bool)
        for tag in np.unique(labels[cell_seed & (labels > 0)]).tolist():
            region = labels == tag
            area = int(region.sum())
            if area <= int(cfg["max_texels"]):
                continue
            foreign, _share, _poly, _fat = _is_foreign(region, cfg)
            if foreign:
                cell_mask |= region
                found += area
        if cell_mask.any():
            mask[win] |= cell_mask
    return mask, found


def scrub_foreign(maps: dict, material: dict, rounds: int = 3) -> dict:
    """Erase from an atlas exactly what the audit gate calls foreign, and say how much.

    r11 (critic B10-2).  r10 tried to stop foreign geometry reaching the atlas by filtering the
    SOURCE, and the filter it used -- flat shading, with no outline clause -- could not tell a
    model-atlas facet from a leaf lamina at source resolution: it removed 34-65 % of the opaque
    art from seven understory atlases, 19-43x the area it was aiming at, and `f_reed` lost
    45 % without ever having failed the gate.

    The source filter now carries the gate's own outline clause and takes 0.2-1.4 % of the
    texels of a photographed leaf source (`r11/facet_probe.json`), which is what restores the
    leaf.  What survives that is removed HERE, at the cell, by the gate's own test -- so the
    collateral is the foreign area itself rather than a multiple of it, and the number is
    published per atlas in :data:`SCRUB_STATS`.
    """
    grid = material.get("grid")
    if not grid or "alphaRef" not in material:
        return maps
    ref = int(material["alphaRef"])
    removed_total = 0
    passes = 0
    for _ in range(rounds):
        mask, found = foreign_regions(maps["base"], maps["opacity"], grid, ref)
        if not found:
            break
        passes += 1
        before = int((maps["opacity"] >= ref).sum())
        # a LOCAL erase: solid over the region, ramped over ~2 texels at its rim, so the cut
        # does not shimmer under alphaTest and nothing outside the region is touched
        soft = _box_mean(_dilate(mask, 2).astype(np.float64), 2)
        maps["opacity"] = np.clip(
            maps["opacity"].astype(np.float64) * (1.0 - np.clip(soft * 1.6, 0.0, 1.0)), 0, 255
        ).astype(np.uint8)
        removed_total += before - int((maps["opacity"] >= ref).sum())
    SCRUB_STATS[material["key"]] = {
        "passes": passes,
        "opaque_texels_removed": int(removed_total),
        "opaque_texels_after": int((maps["opacity"] >= ref).sum()),
        "alphaRef": ref,
    }
    return maps


def audit_tree(level_root: Path, settings: dict | None = None) -> dict:
    """Run :func:`audit_cells` over every cut-out atlas in a built level tree.

    Returns ``{"materials": [...], "worst": int, "sources": {...}}``.  ``sources`` is the
    provenance half of the gate: every CC0 asset any shipped atlas cuts from, so a source that
    is not on the declared list is a failure by name rather than by picture.
    """
    materials = []
    sources: dict[str, list[str]] = {}
    for material in fs.MATERIALS:
        kind = material.get("kind", "rock")
        if kind in ("tile", "rock") or "alphaRef" not in material:
            continue
        key = material["key"]
        declared = {material["cc0"]}
        for spec in material.get("sources", ()) or ():
            declared.add(spec["cc0"])
        for _, _, specs in material.get("cell_sources", ()) or ():
            for spec in specs:
                declared.add(spec["cc0"])
        sources[key] = sorted(declared)
        colour_rel = fs.texture_relative(key, "base")
        opacity_rel = fs.texture_relative(key, "opacity")
        colour_path, opacity_path = level_root / colour_rel, level_root / opacity_rel
        if not (colour_path.is_file() and opacity_path.is_file()):
            raise TextureError(f"{key}: the tree is missing {colour_rel} or {opacity_rel}")
        colour = np.asarray(Image.open(colour_path).convert("RGB"))
        opacity = np.asarray(Image.open(opacity_path).convert("L"))
        cells = audit_cells(
            colour, opacity, material["grid"], int(material["alphaRef"]), settings
        )
        materials.append(
            {
                "key": key,
                "grid": list(material["grid"]),
                "size": int(colour.shape[0]),
                "worst_foreign_texels": max(c["foreign_texels"] for c in cells),
                "cells_with_foreign": sum(1 for c in cells if c["foreign_texels"]),
                "cells": cells,
            }
        )
    return {
        "materials": materials,
        "worst": max((m["worst_foreign_texels"] for m in materials), default=0),
        "cap": int(dict(AUDIT, **(settings or {}))["max_texels"]),
        "sources": sources,
    }


def cook(
    cache: Path, out_root: Path, only: set[str] | None = None, existing: Path | None = None
) -> dict[str, dict]:
    """Cook every material -- or, with ``only``, just those keys MERGED into ``existing``.

    r12: the same rule `build_forest_shapes.build` adopted in r10 -- a partial run merges into
    the manifest on disk instead of replacing it, so re-cooking three shrub sheets cannot leave
    a three-row manifest for the static gates to measure almost nothing against.  The merged
    rows for the un-cooked materials are carried over verbatim (files, albedo and the rejected
    islands of the sources they cut from); a full run still replaces every row.
    """
    manifest: dict[str, dict] = {}
    prior: dict | None = None
    if only and existing and existing.is_file():
        prior = json.loads(existing.read_text(encoding="utf-8"))
        manifest.update(prior.get("files", {}))
    started = time.time()
    for material in fs.MATERIALS:
        if only and material["key"] not in only:
            continue
        material = dict(material)
        material.setdefault("kind", "rock")
        payloads = cook_material(material, cache)
        for relative, payload in payloads.items():
            target = out_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            with Image.open(io.BytesIO(payload)) as image:
                resolution = list(image.size)
            manifest[relative] = {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
                "resolution": resolution,
                "material": fs.material_name(material["key"]),
            }
        print(
            f"[textures] {material['key']:20s} {len(payloads)} maps "
            f"{sum(len(p) for p in payloads.values()) / 1e6:6.1f} MB",
            flush=True,
        )
    rejected = list(REJECTED_ISLANDS)
    albedo = dict(COOK_STATS)
    if prior is not None:
        # carry the un-cooked materials' rows over: their albedo, and the rejected islands of
        # the sources they cut from (a source shared with a re-cooked material is re-cut here
        # and reported fresh)
        cooked_sources = set()
        for material in fs.MATERIALS:
            if material["key"] not in (only or ()):
                continue
            specs = list(material.get("sources", ()) or ())
            for _, _, more in material.get("cell_sources", ()) or ():
                specs.extend(more)
            for spec in specs:
                cooked_sources.add(f"{spec['cc0']}:{spec.get('prefix', '')}{spec.get('mask')}")
        rejected = [
            row for row in prior.get("rejected_islands", []) if row.get("source") not in cooked_sources
        ] + rejected
        albedo = {**prior.get("albedo", {}), **albedo}
    out = {
        "level_id": fs.LEVEL_ID,
        "texture_seed": fs.TEXTURE_SEED,
        "seconds": round(time.time() - started, 1),
        "files": manifest,
        "bytes": sum(v["size"] for v in manifest.values()),
        # r3 (D6): every island the achromatic filter refused, named, so "no calibration block
        # ships" is a reading rather than an assertion.
        "rejected_islands": rejected,
        # r9: the alpha-weighted albedo of every cut-out at its own alphaRef, in the census's
        # units, beside the stock bar it was graded to
        "albedo": dict(sorted(albedo.items())),
    }
    if prior is not None:
        out["merged_into_an_existing_manifest"] = sorted(only or ())
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--only", default=None, help="comma-separated material keys (merged)")
    arguments = parser.parse_args(argv)
    only = set(arguments.only.split(",")) if arguments.only else None
    manifest = cook(arguments.cache, arguments.out, only, existing=arguments.manifest)
    text = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_text(text, encoding="utf-8", newline="\n")
    print(
        f"[textures] {len(manifest['files'])} maps, "
        f"{manifest['bytes'] / 1e6:.1f} MB in {manifest['seconds']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
