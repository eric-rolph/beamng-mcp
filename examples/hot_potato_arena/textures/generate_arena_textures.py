"""Deterministic PBR texture sets for the Gateway Skillet arena (v2).

Runs in the repo venv (numpy + Pillow), NOT inside Blender:

    .\\.venv\\Scripts\\python.exe examples/hot_potato_arena/textures/generate_arena_textures.py

Six families (design v3 SS7.1 as amended by v3.1 Item 5), every one emitted
through ``proplib.texture_kit`` so the map names, determinism law (_rng),
the blockiness-fixed noise basis and the transfer-function law (srgb=True
for new work) match the pack's proven conventions:

- ``ericrolph_hot_potato_arena_cast_iron``      seasoned sand-cast pan
- ``ericrolph_hot_potato_arena_butter``         melted butter (groundtype ICE)
- ``ericrolph_hot_potato_arena_salt``           coarse salt crust (SAND)
- ``ericrolph_hot_potato_arena_skillet_steel``  hardware steel (pillars, towers, lips)
- ``ericrolph_hot_potato_arena_handle_wood``    handle-deck planking, seams every 0.3 m
- ``ericrolph_hot_potato_arena_rim``            v3.1: rivet band + polished lip
                                                (V 0..0.5, tiles in U every 5.7 m,
                                                three rivets = 1.9 m pitch) and the
                                                baked name plate (V 0.5..1, one-shot,
                                                8 m x 4 m, "THE GATEWAY SKILLET")

The arena-only families are registered into ``texture_kit.FAMILIES`` at
runtime -- additive, the shared kit file is not touched -- and are built
from the kit's own primitives so they inherit its noise basis and its
byte-stable PNG writer. Rivets live in this MATERIAL because geometry
rivets cannot exist under the 20 mm drivable-relief cap (critique fix 5).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
GIANT_PROPS = EXAMPLE_ROOT.parent / "giant_props"
sys.path.insert(0, str(GIANT_PROPS))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402
from proplib import texture_kit as tk  # noqa: E402

ARENA_ID = "ericrolph_hot_potato_arena"
OUT_DIR = SCRIPT_PATH.parent
ARENA_NAME = ("THE GATEWAY", "SKILLET")

# Rim band layout constants -- shared with create_arena.py's UV mapping.
RIM_TILE_U_M = 5.7  # one U tile = 5.7 m of crest = 3 rivets at 1.9 m
RIM_BAND_R0 = 90.0  # band covers wall stations r 90..93 (V 0..0.5)
RIM_BAND_R1 = 93.0
RIM_CREST_R = 91.4
PLATE_W_M, PLATE_H_M = 8.0, 4.0  # name plate (V 0.5..1)


def arena_butter(size, rng, base=(0.93, 0.74, 0.25), rough=0.10):
    """Melted butter: golden, glossy, soft melt swirls and paler rivulets.

    Mechanically ICE (F7: sliding 0.20) -- the LOOK has to sell the
    physics, so the roughness floor is glassy and the swirl relief is soft
    and broad (no landmark a player could count at speed).
    """

    swirl = tk._fbm(size, rng, base_cells=3, octaves=4)
    melt = tk._fbm(size, rng, base_cells=8, octaves=3)
    streak = tk._streaks(size, rng, max(8, size // 4), length_frac=0.2)
    tone = 0.55 + (swirl - 0.5) * 0.35 + (melt - 0.5) * 0.15
    color = tk._colorize(base, tone, 0.12)
    color *= 0.94 + streak[..., None] * 0.12
    foam = np.clip((swirl - 0.72) * 4.0, 0.0, 1.0) ** 2
    color = color * (1 - foam[..., None] * 0.25) + foam[..., None] * np.array([0.98, 0.92, 0.62])
    height = (swirl - 0.5) * 0.10 + (melt - 0.5) * 0.03
    roughness = rough + (melt - 0.5) * 0.08 + foam * 0.30
    return color.clip(0, 1), height, roughness.clip(0.02, 1), None


def arena_salt(size, rng, base=(0.70, 0.69, 0.66)):
    """Coarse salt: off-white granular crust, sparse specular facets.

    v2: albedo pulled down from 0.92 to 0.80 (round-1 renders blew the
    arcs out to paper), crevice shadowing doubled so the grains read as
    grains at driving distance.
    """

    g1 = tk._value_noise(size, max(8, size // 4), rng)
    g2 = tk._value_noise(size, max(8, size // 2), rng)
    fine = tk._fbm(size, rng, base_cells=32, octaves=3)
    tone = 0.72 + (g1 - 0.5) * 0.34 + (g2 - 0.5) * 0.22 + (fine - 0.5) * 0.10
    color = tk._colorize(base, tone, 0.10)
    sparkle = np.clip((g2 - 0.82) * 5.0, 0.0, 1.0)
    color += sparkle[..., None] * 0.12
    crevice = np.clip((0.48 - g1) * 2.2, 0.0, 1.0)
    color *= 1.0 - crevice[..., None] * 0.28
    height = (g1 - 0.5) * 0.18 + (g2 - 0.5) * 0.07 + (fine - 0.5) * 0.03
    roughness = 0.86 - sparkle * 0.40 + (g1 - 0.5) * 0.10
    return color.clip(0, 1), height, roughness.clip(0, 1), None


def arena_handle_wood(size, rng, plank_m=0.3, tile_m=6.0, ends_per_plank=2.0, **kw):
    """wood_plank with real plank seams AND plank ends (round-2 fix 6).

    Grain runs along U (+X). Planks are ``plank_m`` wide across V over a
    ``tile_m`` metric tile (6 m: the 3 m repeat read as wallpaper). Each
    plank band gets its own grain phase (a wrapped roll along U, seamless),
    a per-plank tone jitter, a V-groove at every long seam, and 1-3 END
    seams at random positions along U so no two planks repeat in step.
    """

    color, height, rough, _ = tk.wood_plank(size, rng, **kw)
    planks = max(2, int(round(tile_m / plank_m)))
    band = size / planks
    rows = np.arange(size)
    cols = np.arange(size)
    end_mask = np.zeros((size, size))
    for p in range(planks):
        lo, hi = int(round(p * band)), int(round((p + 1) * band))
        shift = int(rng.integers(0, size))
        tone = 1.0 + float(rng.uniform(-0.09, 0.09))
        color[lo:hi] = np.roll(color[lo:hi], shift, axis=1) * tone
        height[lo:hi] = np.roll(height[lo:hi], shift, axis=1)
        rough[lo:hi] = np.roll(rough[lo:hi], shift, axis=1)
        n_ends = int(rng.integers(1, int(ends_per_plank) + 2))
        for _ in range(n_ends):
            c = float(rng.uniform(0, size))
            d = np.minimum(np.abs(cols - c), size - np.abs(cols - c))
            end_mask[lo:hi] = np.maximum(end_mask[lo:hi], np.clip(1.0 - d / 2.0, 0.0, 1.0)[None, :])
            # the board beyond the end gets a slightly different tone
            seg = (cols - c) % size < size / (n_ends + 1)
            color[lo:hi, seg] *= 1.0 + float(rng.uniform(-0.05, 0.05))
    seam = np.zeros(size)
    for p in range(planks):
        c = (p * band) % size
        d = np.minimum(np.abs(rows - c), size - np.abs(rows - c))
        seam = np.maximum(seam, np.clip(1.0 - d / 2.2, 0.0, 1.0))
    groove = np.maximum(seam[:, None], end_mask)
    height = height - groove * 0.35
    color *= (1.0 - groove * 0.45)[..., None]
    rough = np.clip(rough + groove * 0.25, 0, 1)
    return color.clip(0, 1), height, rough, None


def _font(px: int):
    path = tk._font_file()
    if path is None:
        return ImageFont.load_default()
    return ImageFont.truetype(path, px)


def arena_rim(
    size, rng, iron=(0.13, 0.12, 0.115), steel=(0.50, 0.51, 0.53), brass=(0.72, 0.56, 0.28)
):
    """Riveted rim band (bottom half) + baked name plate (top half).

    Bottom half (V 0..0.5): tiles in U every 5.7 m; V spans the band's
    3 m of radius (r 90..93, texel density ~170-180 px/m both axes). Three
    rivet domes at 1.9 m pitch sit on the crest row (r 91.4), a polished
    steel lip +/-0.6 m either side of the crest carries a low-roughness
    highlight, the rest is the seasoned-iron skin.

    Top half (V 0.5..1): one-shot 8 m x 4 m cast plate with a raised
    border and embossed brass lettering, "THE GATEWAY SKILLET".
    """

    half = size // 2
    yy, xx = np.mgrid[0:size, 0:size]
    color = np.zeros((size, size, 3))
    height = np.zeros((size, size))
    rough = np.full((size, size), 0.62)

    # ---- band (array rows half..size-1 = V 0..0.5, row size-1 is V=0) ----
    grain = tk._value_noise(size, max(8, size // 3), rng)
    mottle = tk._fbm(size, rng, base_cells=8, octaves=4)
    iron_tone = 0.42 + (mottle - 0.5) * 0.28 + (grain - 0.5) * 0.16
    band_color = tk._colorize(iron, iron_tone, 0.12)
    v = (size - 1 - yy) / size  # 0 at the bottom row
    r_of_row = RIM_BAND_R0 + (v / 0.5) * (RIM_BAND_R1 - RIM_BAND_R0)
    lip = np.clip(1.0 - np.abs(r_of_row - RIM_CREST_R) / 0.6, 0.0, 1.0)
    lip = lip * lip * (3 - 2 * lip)
    steel_tone = 0.50 + (grain - 0.5) * 0.20 + (mottle - 0.5) * 0.10
    steel_color = tk._colorize(steel, steel_tone, 0.06)
    band = band_color * (1 - lip[..., None]) + steel_color * lip[..., None]
    band_rough = 0.62 + (mottle - 0.5) * 0.12 - lip * 0.36
    band_height = (grain - 0.5) * 0.05 + (mottle - 0.5) * 0.03 + lip * 0.10
    # rivets: 3 per tile on the crest row
    px_per_m = size / RIM_TILE_U_M
    crest_row = size - 1 - int(round(((RIM_CREST_R - RIM_BAND_R0) / 3.0) * 0.5 * size))
    rivet_r = 0.21 * px_per_m
    dome = np.zeros((size, size))
    for k in range(3):
        cx = int(round((k + 0.5) / 3.0 * size))
        tk._stamp(dome, crest_row, cx, rivet_r, 1.0, falloff=0.55)
    dome_h = np.sqrt(np.clip(dome, 0, 1))  # spherical-ish cap
    band_height += dome_h * 0.9
    band = band * (1 - dome_h[..., None] * 0.6) + np.array(steel) * 1.15 * dome_h[..., None] * 0.6
    band_rough = band_rough - dome_h * 0.25
    mask = yy >= half
    color[mask] = band[mask]
    height[mask] = band_height[mask]
    rough[mask] = band_rough[mask]

    # ---- plate (array rows 0..half-1 = V 0.5..1) ----
    plate_tone = 0.40 + (mottle - 0.5) * 0.22 + (grain - 0.5) * 0.14
    plate = tk._colorize((0.10, 0.095, 0.09), plate_tone, 0.10)
    ph = (grain - 0.5) * 0.04 + (mottle - 0.5) * 0.02
    # raised border 0.25 m in from the plate edge
    bx = size / PLATE_W_M * 0.25
    by = half / PLATE_H_M * 0.25
    inner = ((xx > bx) & (xx < size - bx) & (yy > by) & (yy < half - by)).astype(float)
    border = 1.0 - inner
    plate = plate * (1 - border[..., None] * 0.3) + np.array(brass) * 0.55 * border[..., None] * 0.3
    ph += border * 0.35
    # lettering
    text = Image.new("L", (size, half), 0)
    draw = ImageDraw.Draw(text)
    line1 = _font(int(size * 0.135))
    line2 = _font(int(size * 0.215))
    w1 = draw.textbbox((0, 0), ARENA_NAME[0], font=line1)
    w2 = draw.textbbox((0, 0), ARENA_NAME[1], font=line2)
    draw.text(
        ((size - (w1[2] - w1[0])) / 2 - w1[0], half * 0.12 - w1[1]),
        ARENA_NAME[0],
        fill=255,
        font=line1,
    )
    draw.text(
        ((size - (w2[2] - w2[0])) / 2 - w2[0], half * 0.47 - w2[1]),
        ARENA_NAME[1],
        fill=255,
        font=line2,
    )
    letters = np.asarray(text.filter(ImageFilter.GaussianBlur(1.2)), dtype=float) / 255.0
    plate_top, ph_top = plate[:half], ph[:half]
    plate_top = plate_top * (1 - letters[..., None]) + np.array(brass) * letters[..., None]
    ph_top = ph_top + letters * 0.55
    prough = 0.60 + (mottle[:half] - 0.5) * 0.10 - letters * 0.30 - border[:half] * 0.15
    color[:half] = plate_top
    height[:half] = ph_top
    rough[:half] = prough
    return color.clip(0, 1), height, rough.clip(0.05, 1), None


tk.FAMILIES.setdefault("arena_butter", arena_butter)
tk.FAMILIES.setdefault("arena_salt", arena_salt)
tk.FAMILIES.setdefault("arena_handle_wood", arena_handle_wood)
tk.FAMILIES.setdefault("arena_rim", arena_rim)


SETS = [
    # (suffix, family, size, normal_strength, params)
    (
        "cast_iron",
        "cast_iron",
        1024,
        2.6,
        # v2: darker, warmer, higher contrast -- round-1 read as concrete.
        {"base": (0.095, 0.085, 0.078), "oxide": (0.30, 0.16, 0.09), "contrast": 1.5},
    ),
    ("butter", "arena_butter", 512, 2.2, {}),
    ("salt", "arena_salt", 512, 3.0, {}),
    (
        "skillet_steel",
        "steel_worn",
        1024,
        2.0,
        {"base": (0.46, 0.48, 0.51), "rough": 0.38},
    ),
    (
        "handle_wood",
        "arena_handle_wood",
        1024,
        2.6,
        {
            "early": (0.44, 0.27, 0.14),
            "late": (0.11, 0.055, 0.028),
            # Straighter, longer grain (round-2 fix 6: "maze-wallpaper").
            "rings": 7.0,
            "figure": 0.45,
            "sheen": 0.6,
            "tile_m": 6.0,
        },
    ),
    ("rim", "arena_rim", 1024, 3.2, {}),
]


def main() -> None:
    manifest: dict[str, dict] = {}
    for suffix, family, size, normal_strength, params in SETS:
        base_name = f"{ARENA_ID}_{suffix}"
        manifest[base_name] = tk.build_set(
            OUT_DIR,
            base_name,
            family,
            size=size,
            normal_strength=normal_strength,
            params=params,
            srgb=True,
        )
        print(f"texture set {base_name}: {manifest[base_name]}")
    manifest["_rim_layout"] = {
        "tile_u_m": RIM_TILE_U_M,
        "band_r0": RIM_BAND_R0,
        "band_r1": RIM_BAND_R1,
        "crest_r": RIM_CREST_R,
        "plate_w_m": PLATE_W_M,
        "plate_h_m": PLATE_H_M,
        "name": " ".join(ARENA_NAME),
    }
    with open(OUT_DIR / "arena_textures.manifest.json", "w", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main()
