"""Deterministic foliage, bark and rock textures for the procedural shapes.

Card atlases are RGBA (alpha-tested in the engine); bark and rock sets follow the same
``<name>_{b,nm,r}.png`` convention as the terrain kit so one material writer serves
both. Everything is periodic gradient noise from ``texture_kit`` composed in numpy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import texture_kit as tk


def _srgb(linear: np.ndarray) -> np.ndarray:
    return tk._srgb(linear)


def _lin(colour) -> np.ndarray:
    """Authored (sRGB) colour to linear light; every set is encoded back on save."""

    return np.power(np.asarray(colour, dtype="float64"), 2.2)


def _dilate_colour(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Give transparent texels the colour of the nearest opaque one (no pale halo)."""

    from scipy import ndimage

    opaque = alpha > 0.5
    if opaque.all() or not opaque.any():
        return rgb
    indices = ndimage.distance_transform_edt(~opaque, return_distances=False, return_indices=True)
    return rgb[tuple(indices)]


def _save_rgba(path: Path, rgb: np.ndarray, alpha: np.ndarray) -> Path:
    from PIL import Image

    rgb = _dilate_colour(rgb, alpha)

    rgba = np.concatenate(
        [
            (_srgb(np.clip(rgb, 0, 1)) * 255).round().astype("uint8"),
            (np.clip(alpha, 0, 1) * 255).round().astype("uint8")[..., None],
        ],
        axis=-1,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path, format="PNG", compress_level=6)
    return path


def _save_rgb(path: Path, rgb: np.ndarray, *, srgb: bool = True) -> Path:
    from PIL import Image

    arr = _srgb(np.clip(rgb, 0, 1)) if srgb else np.clip(rgb, 0, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((arr * 255).round().astype("uint8"), mode="RGB").save(
        path, format="PNG", compress_level=6
    )
    return path


def _save_gray(path: Path, gray: np.ndarray) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((np.clip(gray, 0, 1) * 255).round().astype("uint8"), mode="L").save(
        path, format="PNG", compress_level=6
    )
    return path


def _grid(size: int):
    v, u = np.mgrid[0:size, 0:size] / float(size)
    return u, 1.0 - v  # u across, v up (row 0 = top of the card)


def _normal_from_height(height: np.ndarray, strength: float) -> np.ndarray:
    gy, gx = np.gradient(height)
    nx = -gx * strength * height.shape[0]
    ny = gy * strength * height.shape[0]
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / length, ny / length, nz / length], axis=-1) * 0.5 + 0.5


# ---------------------------------------------------------------------------
# Conifer spire card
# ---------------------------------------------------------------------------


def conifer_card(
    out_dir: Path,
    name: str,
    seed: int,
    size: int = 1024,
    *,
    kind: str = "spruce",
    colour=(0.10, 0.20, 0.12),
) -> dict[str, Path]:
    """A whole spire on one card: whorled silhouette, clustered needle mass, lit tips."""

    rng = np.random.default_rng(seed)
    u, v = _grid(size)
    x = (u - 0.5) * 2.0  # -1..1 across
    whorls = {"spruce": 9, "fir": 11, "krummholz": 4, "sapling": 6, "willow": 4}[kind]
    fullness = {"spruce": 0.85, "fir": 0.62, "krummholz": 1.0, "sapling": 0.95, "willow": 1.0}[kind]
    # Silhouette half-width: spruce a full spire with drooping whorls, fir a narrow
    # spire of flat layered tiers, krummholz a wind-flagged mat leaning leeward with
    # its crown on the ground.
    taper = np.power(
        np.clip(1.0 - v, 0, 1), {"krummholz": 0.5, "sapling": 0.6, "willow": 0.5}.get(kind, 0.85)
    )
    scallop = 0.82 + 0.18 * np.abs(np.sin(v * whorls * np.pi + 0.3))
    if kind == "fir":
        scallop = 0.75 + 0.25 * np.abs(np.sin(v * whorls * np.pi + 0.3)) ** 0.5
    half_width = fullness * taper * scallop
    # The lowest whorls are shorter than the ones above them (snow load, shade), so
    # the crown never ends in a straight hem wider than itself.
    half_width = half_width * np.where(v < 0.15, 0.6 + 0.4 * v / 0.15, 1.0)
    if kind == "krummholz":
        # A wind-pruned mat with a broad rounded top, leaning a little leeward.
        x = x - 0.15 * v
        # A dome (widest at the ground, rounded over the top), ragged all round.
        half_width = (
            fullness * np.sqrt(np.clip(1.0 - v**2, 0, 1)) * (0.86 + 0.14 * tk.fbm(size, 10, 2, rng))
        )
    if kind == "willow":
        # A carr: a flat-topped dome, upright, its top a ragged run of shoots.
        half_width = (
            fullness * np.sqrt(np.clip(1.0 - v**3, 0, 1)) * (0.84 + 0.16 * tk.fbm(size, 14, 2, rng))
        )
    inside = np.abs(x) < half_width
    # Needle mass: several octaves of tileable noise, thresholded into clumps.
    clumps = tk.fbm(size, 18, 4, rng) * 0.6 + tk.fbm(size, 48, 2, rng) * 0.4
    density = np.clip((half_width - np.abs(x)) / np.maximum(half_width, 1e-3), 0, 1)
    mass = clumps + 0.55 * density + 0.25 * (v < 0.04)
    # Dense enough to survive the game's alpha test (alphaRef 96) without going wispy.
    alpha = np.clip((mass - 0.12) * 7.0, 0, 1) * inside
    # Trunk column near the axis so the card never reads hollow.
    alpha = np.maximum(alpha, inside * np.clip(1.0 - np.abs(x) / 0.06, 0, 1) * (v < 0.92))
    # Ragged branch tips at the bottom instead of a flat bar.
    ragged = tk.fbm(size, 24, 2, rng) * 0.5 + 0.5
    hem = np.clip(
        (v - 0.02 - 0.06 * ragged) / (0.08 if kind not in ("krummholz", "willow") else 0.03), 0, 1
    )
    alpha = alpha * hem
    # Keep the very base clear above ground level (v < 0 handled by geometry).
    # Colour: dark blue-green mass, lighter yellow-green tips at the outside and top.
    base = _lin(colour)
    tip = (
        _lin([0.34, 0.46, 0.20])
        if kind not in ("krummholz", "willow")
        else _lin([0.30, 0.40, 0.20])
        if kind == "krummholz"
        else _lin([0.52, 0.56, 0.36])
    )
    edge = np.clip((np.abs(x) / np.maximum(half_width, 1e-3) - 0.55) / 0.45, 0, 1)
    light = 0.35 * edge + 0.25 * np.clip(v - 0.6, 0, 1) / 0.4 + 0.15 * np.clip(clumps, 0, 1)
    light = np.clip(light + 0.08 * tk.fbm(size, 6, 2, rng), 0, 1)
    rgb = base[None, None, :] * (1.0 - light[..., None]) + tip[None, None, :] * light[..., None]
    rgb *= (0.75 + 0.5 * np.clip(clumps + 0.3, 0, 1))[..., None]
    rgb = np.clip(rgb, 0, 1)
    paths = {"b": _save_rgba(out_dir / f"{name}_b.png", rgb, alpha)}
    # A soft "puffy" normal so the card catches light like a volume.
    puff = np.clip(alpha, 0, 1) * (0.5 + 0.5 * np.clip(clumps + 0.5, 0, 1))
    paths["nm"] = _save_rgb(
        out_dir / f"{name}_nm.png", _normal_from_height(puff * 0.02, 1.5), srgb=False
    )
    return paths


def broadleaf_card(
    out_dir: Path, name: str, seed: int, size: int = 1024, *, colour=(0.22, 0.38, 0.12)
) -> dict[str, Path]:
    """Rounded aspen crown: many overlapping leaf clusters with sky showing through."""

    rng = np.random.default_rng(seed)
    u, v = _grid(size)
    x = (u - 0.5) * 2.0
    cy = 0.62
    ry, rx = 0.38, 0.62
    lobes = 1.0 + 0.18 * tk.fbm(size, 5, 2, rng)
    ellipse = ((x / rx) ** 2 + ((v - cy) / ry) ** 2) * lobes
    clusters = tk.fbm(size, 14, 4, rng) * 0.6 + tk.fbm(size, 40, 2, rng) * 0.4
    mass = clusters + 0.7 * np.clip(1.0 - ellipse, 0, 1)
    alpha = np.clip((mass - 0.22) * 4.0, 0, 1) * (ellipse < 1.15)
    alpha = np.maximum(alpha, np.clip(1.0 - np.abs(x) / 0.05, 0, 1) * (v < cy))
    base = _lin(colour)
    light_col = _lin([0.55, 0.66, 0.22])
    light = np.clip(0.5 * np.clip(clusters + 0.2, 0, 1) + 0.35 * np.clip(v - 0.5, 0, 1) / 0.5, 0, 1)
    rgb = base[None, None, :] * (1 - light[..., None]) + light_col[None, None, :] * light[..., None]
    rgb *= (0.7 + 0.5 * np.clip(clusters + 0.4, 0, 1))[..., None]
    paths = {"b": _save_rgba(out_dir / f"{name}_b.png", np.clip(rgb, 0, 1), alpha)}
    puff = alpha * (0.5 + 0.5 * np.clip(clusters + 0.5, 0, 1))
    paths["nm"] = _save_rgb(
        out_dir / f"{name}_nm.png", _normal_from_height(puff * 0.02, 1.5), srgb=False
    )
    return paths


def conifer_tier_card(
    out_dir: Path,
    name: str,
    seed: int,
    size: int = 512,
    *,
    kind: str = "spruce",
    colour=(0.12, 0.20, 0.11),
) -> dict[str, Path]:
    """A whorl of branches seen from above: needles radiating from the trunk, alpha
    dying to nothing at the rim so the square tier card never shows a corner."""

    rng = np.random.default_rng(seed)
    u, v = _grid(size)
    x, y = (u - 0.5) * 2.0, (v - 0.5) * 2.0
    r = np.sqrt(x * x + y * y)
    theta = np.arctan2(y, x)
    branches = {"spruce": 7, "fir": 9, "krummholz": 5, "sapling": 6, "willow": 5}[kind]
    spokes = 0.5 + 0.5 * np.cos(theta * branches + tk.fbm(size, 6, 2, rng) * 2.5)
    needles = tk.fbm(size, 40, 3, rng) * 0.5 + tk.fbm(size, 14, 3, rng) * 0.5
    mass = spokes * 0.45 + needles * 0.6 + (1.0 - r) * 0.45
    rim = np.clip((0.95 - r) / 0.3, 0, 1)
    alpha = np.clip((mass - 0.3) * 5.0, 0, 1) * rim * (r < 0.97)
    base = _lin(colour)
    tip = _lin([0.30, 0.42, 0.20])
    light = np.clip(0.6 * np.clip(needles + 0.3, 0, 1) + 0.3 * r, 0, 1)
    rgb = base[None, None, :] * (1 - light[..., None]) + tip[None, None, :] * light[..., None]
    rgb *= (0.65 + 0.4 * np.clip(needles + 0.4, 0, 1))[..., None]
    paths = {"b": _save_rgba(out_dir / f"{name}_b.png", np.clip(rgb, 0, 1), alpha)}
    paths["nm"] = _save_rgb(
        out_dir / f"{name}_nm.png", _normal_from_height(alpha * 0.03, 1.2), srgb=False
    )
    return paths


def shrub_card(
    out_dir: Path,
    name: str,
    seed: int,
    size: int = 512,
    *,
    colour=(0.18, 0.24, 0.12),
    light_colour=(0.30, 0.37, 0.19),
) -> dict[str, Path]:
    """Low rounded juniper / saltbush mound; ``light_colour`` is the sunlit tip colour."""

    rng = np.random.default_rng(seed)
    u, v = _grid(size)
    x = (u - 0.5) * 2.0
    ellipse = (x / 0.95) ** 2 + ((v - 0.35) / 0.62) ** 2
    clusters = tk.fbm(size, 16, 4, rng) * 0.6 + tk.fbm(size, 44, 2, rng) * 0.4
    mass = clusters + 0.8 * np.clip(1.0 - ellipse, 0, 1)
    alpha = np.clip((mass - 0.22) * 5.0, 0, 1) * (ellipse < 1.1) * (v > 0.02)
    base = _lin(colour)
    # Juniper: dense blue-green mass, only the sunlit tips go yellow-green.
    light_col = _lin(light_colour)
    light = np.clip(0.4 * np.clip(clusters + 0.2, 0, 1) + 0.3 * np.clip(v - 0.4, 0, 1), 0, 1)
    rgb = base[None, None, :] * (1 - light[..., None]) + light_col[None, None, :] * light[..., None]
    rgb *= (0.6 + 0.45 * np.clip(clusters + 0.4, 0, 1))[..., None]
    paths = {"b": _save_rgba(out_dir / f"{name}_b.png", np.clip(rgb, 0, 1), alpha)}
    paths["nm"] = _save_rgb(
        out_dir / f"{name}_nm.png", _normal_from_height(alpha * 0.02, 1.2), srgb=False
    )
    return paths


# ---------------------------------------------------------------------------
# Bark and rock
# ---------------------------------------------------------------------------


def _shingles(
    size: int, rng: np.random.Generator, count: int, radius_range: tuple[float, float]
) -> tuple[np.ndarray, np.ndarray]:
    """A shingle pile: convex scales whose lower edge stands proud (a fixed tilt down
    the tile), the higher one winning where they overlap. Returns (height, owner)."""

    height = np.full((size, size), -np.inf)
    owner = np.full((size, size), -1, dtype="int64")
    lo, hi = radius_range
    for i in range(count):
        cx, cy = rng.uniform(0, 1, 2)
        r = float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
        stretch = rng.uniform(1.2, 1.8)  # taller than wide
        w = int(r * stretch * size) + 2
        rows = (np.arange(-w, w + 1) + round(cy * size)) % size
        cols = (np.arange(-w, w + 1) + round(cx * size)) % size
        dy = (np.arange(-w, w + 1) + round(cy * size)) / size - cy
        dx = (np.arange(-w, w + 1) + round(cx * size)) / size - cx
        DX, DY = np.meshgrid(dx, dy)
        ax, ay = DX, DY / stretch
        inside = np.ones(DX.shape, dtype=bool)
        for angle in np.sort(rng.uniform(0, 2 * np.pi, int(rng.integers(5, 8)))):
            inside &= (ax * np.cos(angle) + ay * np.sin(angle)) <= r * rng.uniform(0.75, 1.0)
        z = rng.uniform(0.2, 0.6) + 0.5 * (DY / (r * stretch)) + 0.1 * (DX / r) * rng.uniform(-1, 1)
        sub = np.ix_(rows, cols)
        better = inside & (z > height[sub])
        height[sub] = np.where(better, z, height[sub])
        owner[sub] = np.where(better, i, owner[sub])
    return height, owner


def bark_set(
    out_dir: Path, name: str, seed: int, size: int = 512, *, kind: str = "spruce"
) -> dict[str, Path]:
    """Bark tiles at one tile per 0.5 m of trunk (see ``meshgen.BARK_TILE_M``).

    Spruce: shingled scales, log-normal 3-8 cm, each overlapping the ones below it
    with a shadow only along its lower edge (no outline round the scale), and short
    vertical fissures between scale groups. Aspen: chalky bark with sharp-edged
    black lens scars, short horizontal lenticel dashes and faint tone banding.
    """

    rng = np.random.default_rng(seed)
    if kind == "aspen":
        plates = tk.fbm(size, 4, 3, rng)  # periods that divide the tile: no seam
        v = np.linspace(0, 1, size, endpoint=False)[:, None]
        level = np.zeros((size, size))
        # Lens scars: sharp ellipses 3-6 cm wide at 2:1, a dark core and a thin grey rim.
        scar_h, _scar_owner = tk._dome_pile(
            size, rng, 4, (0.025, 0.05), elongation=(1.8, 2.2), heading_field=level
        )
        scar = np.isfinite(scar_h)
        ragged = tk.fbm(size, 40, 2, rng) * 0.25
        core = scar & (scar_h + ragged > 0.2)
        rim = scar & ~core & (scar_h + ragged > 0.05)  # a thin pale rim round the scar
        # Lenticels: short horizontal dashes, 0.5-2 cm long, of varied weight.
        dash_h, dash_owner = tk._dome_pile(
            size, rng, 140, (0.003, 0.008), elongation=(3.0, 7.0), heading_field=level
        )
        dash_cut = 0.25 + 0.4 * tk._cell_value(np.maximum(dash_owner, 0), 3)
        dash = np.isfinite(dash_h) & (dash_h > dash_cut)
        band = 0.04 * np.sin(v * 2 * np.pi * 3) + 0.03 * tk.fbm(size, (1, 6), 2, rng)
        relief = 0.55 + 0.1 * plates - 0.3 * core - 0.1 * rim - 0.06 * dash
        height = np.clip(relief + tk.fbm(size, 40, 2, rng) * 0.04, 0, 1)
        pale = _lin([0.80, 0.80, 0.72])
        grey = _lin([0.50, 0.50, 0.46])
        dark = _lin([0.22, 0.18, 0.14])
        rgb = pale[None, None, :] * (0.85 + 0.25 * plates[..., None] + band[..., None])
        rgb = np.where(rim[..., None], pale[None, None, :] * 1.08, rgb)
        rgb = np.where(core[..., None], dark[None, None, :] * (0.8 + 0.4 * plates[..., None]), rgb)
        dash_tone = (0.55 + 0.3 * tk._cell_value(np.maximum(dash_owner, 0), 4))[..., None]
        rgb = np.where(dash[..., None], grey[None, None, :] * dash_tone, rgb)
        rough = np.clip(0.55 + 0.25 * (core | rim), 0, 1)
    else:
        # Engelmann spruce: scales dropped as a shingle pile, the higher one wins where
        # they overlap, so every scale's proud lower edge casts a shadow line on the
        # scale below it and nothing draws its top or side edges.
        scale_h, owner = _shingles(size, rng, 700, (0.03, 0.08))
        present = np.isfinite(scale_h)
        scale_h = np.where(present, scale_h, 0.0)
        # A pixel is in shadow where the pixel just above it (up the tile) is higher.
        above = np.roll(scale_h, -3, axis=0)
        shadow = np.clip((above - scale_h) / 0.35, 0, 1)
        # Short vertical fissures between scale groups: 2-6 cm long, half a
        # centimetre wide, straight up the trunk (cell boundaries branched into
        # Y shapes that read as twigs drawn on the plates).
        upright = np.full((size, size), np.pi / 2)
        fis_h, _fis_owner = tk._dome_pile(
            size, rng, 70, (0.004, 0.006), elongation=(4.0, 10.0), heading_field=upright
        )
        fissure = np.where(np.isfinite(fis_h), np.clip((fis_h - 0.15) / 0.3, 0, 1), 0.0)
        grain = tk.fbm(size, 40, 3, rng) * 0.06
        height = np.clip(0.3 + 0.45 * scale_h - 0.45 * fissure + grain, 0, 1)
        base = _lin([0.34, 0.30, 0.27])
        flake = 0.8 + 0.4 * tk._cell_value(np.maximum(owner, 0), 6)
        tint = (flake * (1.0 - 0.5 * shadow) * (1.0 - 0.5 * fissure))[..., None]
        rgb = base[None, None, :] * (0.7 + 0.5 * height[..., None]) * tint
        rough = np.clip(0.9 - 0.15 * height, 0, 1)
    paths = {
        "b": _save_rgb(out_dir / f"{name}_b.png", np.clip(rgb, 0, 1)),
        "nm": _save_rgb(
            out_dir / f"{name}_nm.png",
            _normal_from_height(height, 0.06 if kind != "aspen" else 0.05),
            srgb=False,
        ),
        "r": _save_gray(out_dir / f"{name}_r.png", rough),
    }
    return paths


def rock_set(
    out_dir: Path,
    name: str,
    seed: int,
    size: int = 1024,
    *,
    colour=(0.52, 0.46, 0.40),
    strata: float = 0.4,
    beds_per_tile: int = 7,
    lichen_cover: float = 0.3,
) -> dict[str, Path]:
    """Weathered rock: fractures, lichen blotches, optional bedding strata.

    ``lichen_cover`` is the share of the face under lichen (a third for the alpine
    talus, a hundredth for desert rock)."""

    rng = np.random.default_rng(seed)
    _u, v = _grid(size)
    grain = tk.fbm(size, 14, 5, rng)
    f1, f2, cid = tk.worley(size, 6, rng, jitter=0.9)
    # Fractures are fragments of cell boundaries, not a network: gate them with noise.
    fractures = (1.0 - tk._smooth((f2 - f1) / 0.015)) * (tk.fbm(size, 5, 2, rng) > 0.3)
    pits_f1, _, pits_id = tk.worley(size, 40, rng)
    pits = tk._smooth(1.0 - pits_f1 / 0.3) * (tk._cell_value(pits_id, 9) > 0.7)
    # Each facet its own tone, +-6 %: a block is several faces, not one skin.
    facet = 0.94 + 0.12 * tk._cell_value(cid, 7)
    # ``beds_per_tile`` is how many beds fit in one tile HEIGHT, so the caller sets it
    # from the bed thickness the map declares and the metres a tile covers. It was
    # hardcoded at 7, which on a 3 m tile draws a bed every 0.43 m whatever the spec
    # asked for - 5.6x too fine on Black Bear Pass's 2.4 m beds and 7.5x on Meteor
    # Crater's 3.2 m. Bedding that fine reads as grain rather than as layers, which is
    # half of why these walls do not look like sedimentary rock.
    #
    # It must stay a whole number: v repeats every 1.0 across a tile, so a fractional
    # count puts a visible discontinuity at every tile boundary up the wall.
    bed_phase = v * max(1, int(beds_per_tile)) + 0.15 * tk.fbm(size, 2, 3, rng)
    # Bedding as bands with edges (a soft sine never read as strata): the tone
    # steps 10-20 % from bed to bed at ``strata`` 0.45 and the relief follows it.
    bands = np.tanh(2.5 * np.sin(bed_phase * 2 * np.pi))
    beds = bands * strata
    bed_id = np.floor(bed_phase).astype(int) % 7
    bed_tone = 1.0 + 0.15 * strata * (rng.uniform(-1, 1, 7)[bed_id])
    height = 0.55 + 0.18 * grain + 0.12 * beds - 0.4 * fractures - 0.2 * pits + 0.1 * (facet - 1.0)
    height = np.clip(height, 0, 1)
    # Lichen as two or three colonies a tile: log-normal blotches, 1-25 cm at unit
    # scale, thick at the colony's heart and thinning out, yellow-green; black
    # rock-tripe apart under 2 % of the face. An even field of same-size blotches
    # read as camouflage.
    _yy, _xx = np.mgrid[0:size, 0:size] / size
    colony = np.zeros((size, size))
    for _c in range(int(rng.integers(2, 4))):
        cy, cx = rng.uniform(0, 1, 2)
        dy = (_yy - cy + 0.5) % 1.0 - 0.5
        dx = (_xx - cx + 0.5) % 1.0 - 0.5
        colony += np.exp(-(dx * dx + dy * dy) / (2 * rng.uniform(0.08, 0.16) ** 2))
    colony = colony + 0.15 * tk.fbm(size, 4, 2, rng)
    blotch, _b_owner = tk._dome_pile(
        size,
        rng,
        900,
        (0.005, 0.125),
        elongation=(1.0, 1.6),
        presence=colony,
        presence_min=0.45,
        ragged=0.6,
    )
    blotch = np.where(np.isfinite(blotch), blotch, 0.0)
    target = min(max(lichen_cover, 0.001), 0.6)
    if float((blotch > 0.15).mean()) > target:
        cut = float(np.quantile(blotch, 1.0 - target))
    else:
        cut = 0.15
    lichen = np.clip((blotch - cut) / 0.15, 0, 1)
    tripe, _t_owner = tk._dome_pile(size, rng, 60, (0.01, 0.06), elongation=(1.0, 1.4), ragged=0.5)
    tripe = np.where(np.isfinite(tripe), tripe, 0.0)
    tripe_target = min(0.02, 0.2 * lichen_cover)
    t_cut = (
        float(np.quantile(tripe, 1.0 - tripe_target))
        if float((tripe > 0.2).mean()) > tripe_target
        else 0.2
    )
    black_lichen = (np.clip((tripe - t_cut) / 0.1, 0, 1) > 0.5)[..., None]
    lichen = np.maximum(lichen, np.clip((tripe - t_cut) / 0.1, 0, 1))
    base = _lin(colour)
    lichen_col = np.where(black_lichen, _lin([0.12, 0.12, 0.11]), _lin([0.50, 0.53, 0.40]))
    # Weathering: stains at a tenth to a third of the face and dark water streaks
    # down it, so the tone spans a real range rather than one putty grey.
    stains = tk.fbm(size, 6, 3, rng) * 0.32
    streaks = np.clip(tk.fbm(size, (24, 3), 3, rng) * 1.4, 0, 1) ** 2 * 0.3
    weather = np.clip(
        0.75 + 0.6 * (height - 0.5) + 0.12 * tk.fbm(size, 3, 2, rng) + stains - streaks, 0.3, 1.4
    )
    weather = weather * facet * bed_tone
    rgb = base[None, None, :] * weather[..., None]
    # Dust in the hollows and pale specks (calcite, grit) so a face is never one
    # flat tone, and the beds read in the colour as well as the relief.
    dust = np.clip((tk.fbm(size, 5, 3, rng) - 0.05) * 3.0, 0, 1) * (1.0 - height) * 0.8
    dust_col = _lin([0.62, 0.58, 0.50])
    rgb = rgb * (1 - 0.5 * dust[..., None]) + dust_col[None, None, :] * 0.5 * dust[..., None]
    sp_f1, _sp, sp_id = tk.worley(size, 90, rng, jitter=1.0)
    specks = tk._smooth(1.0 - sp_f1 / 0.25) * (tk._cell_value(sp_id, 11) > 0.93)
    rgb = rgb * (1.0 + 0.35 * specks[..., None])
    rgb = rgb * (1.0 + 0.22 * beds)[..., None]
    rgb = rgb * (1 - 0.7 * lichen[..., None]) + lichen_col * 0.7 * lichen[..., None]
    rgb *= (1.0 - 0.5 * fractures)[..., None]
    # Tone contract: the set's mean albedo is the authored colour, so a boulder is
    # neither paler nor darker than the ground it sits on.
    rgb = rgb * (float(base.mean()) / max(float(rgb.mean()), 1e-4))
    rough = np.clip(0.78 - 0.15 * (height - 0.5) + 0.1 * lichen, 0.4, 1)
    return {
        "b": _save_rgb(out_dir / f"{name}_b.png", np.clip(rgb, 0, 1)),
        # A rock face tilts ten to fifteen degrees per texel on average (the cracks
        # and stains, not sandpaper), or the mesh's own shape vanishes under
        # lighting noise.
        "nm": _save_rgb(out_dir / f"{name}_nm.png", _normal_from_height(height, 0.06), srgb=False),
        "r": _save_gray(out_dir / f"{name}_r.png", rough),
    }


def facade_set(
    out_dir: Path,
    name: str,
    seed: int,
    size: int = 1024,
    *,
    family: str = "clapboard",
    colour=(0.55, 0.52, 0.47),
) -> dict[str, Path]:
    """A 4 m square of wall: boards, battens, corrugation, brick or rubble, with a window.

    The tile is 4 m across and the wall UVs run a tile every 4 m of perimeter and every
    4 m of height, so one window lands on each 4 m of frontage with its sill 0.6 m up
    and its head at 2.2 m. That is a window every four metres at the height windows
    are, which is what a street reads as from the pass; it is not a survey of anyone's
    house.
    """

    rng = np.random.default_rng(seed)
    u, v = _grid(size)
    base = _lin(colour)
    grain = tk.fbm(size, 24, 5, rng)
    height = np.zeros((size, size), dtype="float32")
    tone = np.ones((size, size), dtype="float32")

    if family in ("clapboard", "board"):
        # 200 mm laps across a 4 m tile is 20 courses; board-and-batten runs the other
        # way, 300 mm boards with a 50 mm batten proud of every joint.
        if family == "clapboard":
            phase = v * 20.0
            lap = phase - np.floor(phase)
            height = (0.25 + 0.75 * lap).astype("float32")
            height -= 0.55 * _smoothstep_band(lap, 0.0, 0.06)
            board_id = np.floor(phase).astype("int64")
        else:
            phase = u * 13.0
            lap = phase - np.floor(phase)
            board_id = np.floor(phase).astype("int64")
            height = 0.2 + 0.1 * np.cos(2 * np.pi * lap)
            batten = _smoothstep_band(lap, 0.0, 0.085)
            height = height + 0.8 * batten
        tone = 0.90 + 0.20 * tk._cell_value(board_id % 97, 11)
        # Sawn timber: fine lengthwise grain, and a weathered wash down the wall.
        grain_axis = tk.fbm(size, 80, 3, rng) if family == "clapboard" else tk.fbm(size, 3, 3, rng)
        tone *= 0.96 + 0.08 * grain_axis
        rough = 0.72 + 0.16 * grain
    elif family == "steel":
        # Corrugated sheet: a 76 mm pitch is 52 ribs across 4 m, with a lap seam every
        # 0.9 m and rust creeping up from the bottom edge.
        rib = np.cos(2 * np.pi * u * 52.0)
        height = (0.5 + 0.5 * rib).astype("float32")
        seam = _smoothstep_band(u * 4.4 - np.floor(u * 4.4), 0.0, 0.03)
        height = height * (1.0 - 0.5 * seam) + 0.6 * seam
        rust = np.clip(tk.fbm(size, 6, 4, rng) * 1.4 + (0.72 - v) * 1.6, 0.0, 1.0) ** 2
        base = (
            base[None, None, :] * (1 - rust[..., None]) + _lin((0.36, 0.17, 0.10)) * rust[..., None]
        )
        tone = 0.95 + 0.10 * grain
        rough = 0.35 + 0.45 * rust
    elif family == "brick":
        # 215 x 65 with a 10 mm joint: 17.8 bricks across and 47 courses up a 4 m tile.
        course = v * 47.0
        row = np.floor(course).astype("int64")
        stagger = 0.5 * (row % 2)
        along = u * 17.8 + stagger
        col = np.floor(along).astype("int64")
        joint = np.maximum(
            _smoothstep_band(course - row, 0.0, 0.13), _smoothstep_band(along - col, 0.0, 0.05)
        )
        height = (1.0 - joint).astype("float32")
        tone = 0.86 + 0.28 * tk._cell_value((row * 131 + col) % 211, 5)
        tone = tone * (1 - joint) + 1.35 * joint  # lime mortar is paler than the brick
        rough = 0.78 + 0.14 * grain
    else:  # stone: coursed rubble, the blocks themselves from a stretched Worley cell
        f1, f2, cid = tk.worley(size, 11, rng, jitter=0.85)
        joint = 1.0 - tk._smooth((f2 - f1) / 0.02)
        height = (1.0 - joint).astype("float32")
        tone = 0.82 + 0.34 * tk._cell_value(cid, 13)
        tone = tone * (1 - joint) + 1.25 * joint
        rough = 0.82 + 0.12 * grain

    rgb = (base[None, None, :] if base.ndim == 1 else base) * tone[..., None]

    # One window per tile: sill 0.6 m, head 2.2 m, 1.2 m wide, with a frame and a
    # reveal. Glass is dark and smooth; the frame stands proud.
    wx0, wx1 = 0.35, 0.65
    wy0, wy1 = 0.15, 0.55
    inside = (u > wx0) & (u < wx1) & (v > wy0) & (v < wy1)
    frame = (
        (u > wx0 - 0.022) & (u < wx1 + 0.022) & (v > wy0 - 0.022) & (v < wy1 + 0.022)
    ) & ~inside
    mullion = inside & (np.abs(u - 0.5) < 0.008)
    transom = inside & (np.abs(v - (wy0 + wy1) / 2) < 0.008)
    glass = inside & ~mullion & ~transom
    # Glass carries the sky it would reflect, darker at the bottom of the pane.
    sky = _lin((0.24, 0.29, 0.36))[None, None, :] * (0.45 + 0.9 * (v[..., None] - wy0))
    rgb = np.where(glass[..., None], sky, rgb)
    rgb = np.where((frame | mullion | transom)[..., None], _lin((0.74, 0.73, 0.70)), rgb)
    height = np.where(glass, 0.15, height)
    height = np.where(frame | mullion | transom, 1.0, height)
    rough = np.where(glass, 0.08, rough)
    rough = np.where(frame | mullion | transom, 0.45, rough)

    normal = _normal_from_height(height.astype("float32"), 0.8)
    return {
        "b": _save_rgb(out_dir / f"{name}_b.png", np.clip(rgb, 0.0, 1.0)),
        "nm": _save_rgb(out_dir / f"{name}_nm.png", normal, srgb=False),
        "r": _save_gray(out_dir / f"{name}_r.png", np.clip(rough, 0.0, 1.0)),
    }


def roof_set(
    out_dir: Path, name: str, seed: int, size: int = 512, *, colour=(0.62, 0.63, 0.64)
) -> dict[str, Path]:
    """Standing-seam metal on a 2 m tile: what nearly every roof in the San Juans is.

    Seams every 0.45 m, screw lines across, and the panels each a shade off one
    another the way a roof replaced in pieces is.
    """

    rng = np.random.default_rng(seed)
    u, v = _grid(size)
    base = _lin(colour)
    pitch = 2.0 / 0.45  # seams across a 2 m tile
    phase = u * pitch
    panel = np.floor(phase).astype("int64")
    seam = _smoothstep_band(phase - panel, 0.0, 0.045)
    height = (0.15 + 0.85 * seam).astype("float32")
    # Screws every 0.6 m down the seam, and the shallow oil-canning of a long panel.
    screw_phase = v * (2.0 / 0.6)
    screws = seam * _smoothstep_band(screw_phase - np.floor(screw_phase), 0.0, 0.07)
    height += 0.45 * screws
    height += 0.06 * np.cos(2 * np.pi * (phase - panel) - np.pi) * tk.fbm(size, 3, 2, rng)
    tone = 0.88 + 0.24 * tk._cell_value(panel % 89, 17)
    weather = tk.fbm(size, 9, 4, rng)
    tone *= 0.92 + 0.16 * weather
    # The seam itself is a fold of the same sheet standing 25 mm proud: it reads as a
    # dark line at any distance because it is always in its own shadow on one side.
    tone *= 1.0 - 0.45 * seam
    # Dirt runs down the pitch and collects against the seams.
    streak = np.clip(tk.fbm(size, 4, 3, rng) * 0.5 + 0.5, 0.0, 1.0) * v
    tone *= 1.0 - 0.18 * streak * (0.4 + 0.6 * seam)
    # A little rust in the laps, more where the noise pools.
    rust = np.clip(weather * 1.3 - 0.55, 0.0, 1.0) ** 2 * (0.4 + 0.6 * seam)
    rgb = base[None, None, :] * tone[..., None]
    rgb = rgb * (1 - rust[..., None]) + _lin((0.34, 0.16, 0.09)) * rust[..., None]
    rough = np.clip(0.30 + 0.35 * weather + 0.35 * rust, 0.0, 1.0)
    normal = _normal_from_height(height, 1.1)
    return {
        "b": _save_rgb(out_dir / f"{name}_b.png", np.clip(rgb, 0.0, 1.0)),
        "nm": _save_rgb(out_dir / f"{name}_nm.png", normal, srgb=False),
        "r": _save_gray(out_dir / f"{name}_r.png", rough),
    }


def _smoothstep_band(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """1 inside a band that wraps at 0, falling off smoothly at its edge."""

    d = np.minimum(np.abs(x - lo), np.abs(x - 1.0 - lo))
    return np.clip(1.0 - d / max(hi - lo, 1e-6), 0.0, 1.0) ** 2
