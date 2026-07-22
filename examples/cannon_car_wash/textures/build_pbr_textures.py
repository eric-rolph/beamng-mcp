"""Build deterministic BeamNG-ready PBR textures for Cannon Car Wash.

The architectural tiles are drawn procedurally at true metric scale so the
generator's authored UV0 meters-per-tile mapping produces life-size blocks,
bricks, and panel ribs in game: the CMU tile covers exactly 0.8 x 0.4 m of two
390 x 190 mm blocks per course, the brick tile covers 1.2 x 0.6 m of six
modular bricks across eight courses, and the corrugated tile carries six
0.2 m-pitch trapezoidal ribs.  Every module is computed from wrapped per-pixel
cell coordinates, so tiles are seamless by construction rather than mirrored,
and a true metric height field drives each normal and ambient-occlusion map
instead of a luminance guess.  Only the wet-concrete floor still starts from a
photo source; its tile is made seamless with an offset cross-fade and broken up
with periodic value noise so no kaleidoscope symmetry survives.

BeamNG's texture cooker recognises ``.color.png`` as sRGB, ``.normal.png`` as
OpenGL Y+ tangent normals, and ``.data.png`` as linear scalar data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Final

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

SCRIPT_ROOT: Final = Path(__file__).resolve().parent
EXAMPLE_ROOT: Final = SCRIPT_ROOT.parent
SOURCE_ROOT: Final = SCRIPT_ROOT / "source"
DEFAULT_OUTPUT_ROOT: Final = SCRIPT_ROOT / "generated_png"
MOD_ID: Final = "ericrolph_cannon_car_wash"
DEFAULT_MANIFEST_PATH: Final = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}.textures.json"

TILE: Final = 1024


def _texture_name(stem: str, suffix: str) -> str:
    return f"{MOD_ID}_{stem}.{suffix}.png"


def _seal_edges(image: Image.Image) -> Image.Image:
    """Make the final opposing texel rows/columns exactly periodic."""

    pixels = np.asarray(image).copy()
    pixels[:, -1] = pixels[:, 0]
    pixels[-1, :] = pixels[0, :]
    return Image.fromarray(pixels)


def _dilate_alpha_colour(colour: Image.Image, opacity: Image.Image) -> Image.Image:
    """Pad opaque card colours beneath transparent texels for stable mip edges."""

    dilated = colour.filter(ImageFilter.MaxFilter(size=17))
    return Image.composite(colour, dilated, opacity)


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True, compress_level=9)


def _cell_hash(ix: np.ndarray, iy: np.ndarray, salt: int) -> np.ndarray:
    """Deterministic integer-lattice hash mapped into [0, 1).

    Plain integer mixing keeps per-block variation stable across numpy
    versions, unlike drawing per-cell values from a stateful RNG stream.
    """

    mask = np.uint64(0xFFFFFFFF)
    h = (
        ix.astype(np.uint64) * np.uint64(374761393)
        + iy.astype(np.uint64) * np.uint64(668265263)
        + np.uint64(salt) * np.uint64(2246822519)
    ) & mask
    h = ((h ^ (h >> np.uint64(13))) * np.uint64(1274126177)) & mask
    h ^= h >> np.uint64(16)
    return ((h & np.uint64(0xFFFFFF)).astype(np.float64) / float(0x1000000)).astype(np.float32)


def _smoothstep(value: np.ndarray) -> np.ndarray:
    clipped = np.clip(value, 0.0, 1.0)
    return clipped * clipped * (3.0 - 2.0 * clipped)


def _periodic_value_noise(size: tuple[int, int], cells: tuple[int, int], salt: int) -> np.ndarray:
    """Return a wrap-periodic value-noise field in [0, 1)."""

    height, width = size
    cells_y, cells_x = cells
    ys = np.arange(height, dtype=np.float32)[:, None] * (cells_y / height)
    xs = np.arange(width, dtype=np.float32)[None, :] * (cells_x / width)
    y0 = np.floor(ys).astype(np.int64)
    x0 = np.floor(xs).astype(np.int64)
    ty = _smoothstep(ys - y0)
    tx = _smoothstep(xs - x0)
    y0 %= cells_y
    x0 %= cells_x
    y1 = (y0 + 1) % cells_y
    x1 = (x0 + 1) % cells_x
    y0v = np.broadcast_to(y0, (height, width))
    y1v = np.broadcast_to(y1, (height, width))
    x0v = np.broadcast_to(x0, (height, width))
    x1v = np.broadcast_to(x1, (height, width))
    c00 = _cell_hash(x0v, y0v, salt)
    c10 = _cell_hash(x1v, y0v, salt)
    c01 = _cell_hash(x0v, y1v, salt)
    c11 = _cell_hash(x1v, y1v, salt)
    top = c00 + (c10 - c00) * tx
    bottom = c01 + (c11 - c01) * tx
    return top + (bottom - top) * ty


def _periodic_fbm(size: tuple[int, int], base_cells: int, octaves: int, salt: int) -> np.ndarray:
    """Sum wrap-periodic noise octaves, normalized into [0, 1]."""

    total = np.zeros(size, dtype=np.float32)
    amplitude = 1.0
    amplitude_sum = 0.0
    for octave in range(octaves):
        cells = base_cells * (2**octave)
        total += amplitude * _periodic_value_noise(size, (cells, cells), salt + octave * 101)
        amplitude_sum += amplitude
        amplitude *= 0.5
    return total / amplitude_sum


def _normal_from_metric_height(
    height_m: np.ndarray,
    tile_m: tuple[float, float],
) -> Image.Image:
    """Encode exact OpenGL Y+ tangent normals from a height field in meters."""

    rows, cols = height_m.shape
    px_x = tile_m[0] / cols
    px_y = tile_m[1] / rows
    dx = (np.roll(height_m, -1, axis=1) - np.roll(height_m, 1, axis=1)) / (2.0 * px_x)
    dy = (np.roll(height_m, -1, axis=0) - np.roll(height_m, 1, axis=0)) / (2.0 * px_y)
    # Image rows point down while the texture V axis points up.  Positive green
    # is therefore +dy here, producing BeamNG's required OpenGL Y+ normals.
    normal = np.dstack((-dx, dy, np.ones_like(height_m)))
    normal /= np.linalg.norm(normal, axis=2, keepdims=True).clip(min=1e-6)
    encoded = np.clip((normal * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(encoded)


def _ao_from_metric_height(height_m: np.ndarray, strength: float) -> Image.Image:
    """Derive small-scale cavity occlusion from the physical height field."""

    span = float(height_m.max() - height_m.min())
    normalized = (height_m - float(height_m.min())) / max(span, 1e-6)
    height_image = Image.fromarray((normalized * 255.0).astype(np.uint8))
    neighbourhood = (
        np.asarray(height_image.filter(ImageFilter.GaussianBlur(radius=6)), dtype=np.float32)
        / 255.0
    )
    cavities = np.maximum(neighbourhood - normalized, 0.0)
    ao = np.clip(1.0 - cavities * strength, 0.36, 1.0)
    return Image.fromarray((ao * 255.0).astype(np.uint8))


def _to_srgb_image(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(rgb * 255.0, 0, 255).astype(np.uint8))


def _to_data_image(scalar: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(scalar * 255.0, 0, 255).astype(np.uint8))


def _masonry_grid(
    tile_m: tuple[float, float],
    module_m: tuple[float, float],
    mortar_m: float,
    bond_offset_m: float,
) -> dict[str, np.ndarray]:
    """Compute wrapped per-pixel module data for a running-bond masonry tile."""

    xs = (np.arange(TILE, dtype=np.float32)[None, :] + 0.5) * (tile_m[0] / TILE)
    ys = (np.arange(TILE, dtype=np.float32)[:, None] + 0.5) * (tile_m[1] / TILE)
    course = np.floor(ys / module_m[1]).astype(np.int64)
    courses_per_tile = round(tile_m[1] / module_m[1])
    course %= courses_per_tile
    offset_x = (xs + course * bond_offset_m) % tile_m[0]
    column = np.floor(offset_x / module_m[0]).astype(np.int64)
    u = offset_x % module_m[0]
    v = ys % module_m[1]
    half_mortar = mortar_m / 2.0
    edge_u = np.minimum(u - half_mortar, module_m[0] - half_mortar - u)
    edge_v = np.minimum(v - half_mortar, module_m[1] - half_mortar - v)
    inside = (edge_u > 0.0) & (edge_v > 0.0)
    edge_distance = np.minimum(np.maximum(edge_u, 0.0), np.maximum(edge_v, 0.0))
    return {
        "course": np.broadcast_to(course, (TILE, TILE)),
        "column": column,
        "inside": inside,
        "edge_distance": edge_distance,
        "u": u,
        "v": v,
    }


def _build_cmu(output_root: Path) -> list[Path]:
    """Grey CMU running bond: tile 0.8 x 0.4 m = 2 blocks x 2 courses, life size."""

    tile_m = (0.8, 0.4)
    grid = _masonry_grid(tile_m, (0.4, 0.2), 0.010, 0.2)
    inside = grid["inside"]
    bevel = _smoothstep(grid["edge_distance"] / 0.006)

    block_value = _cell_hash(grid["column"], grid["course"], 11)
    block_tilt_u = _cell_hash(grid["column"], grid["course"], 12) - 0.5
    block_tilt_v = _cell_hash(grid["column"], grid["course"], 13) - 0.5

    pits = _periodic_fbm((TILE, TILE), 64, 3, 21)
    pit_depth = np.where(pits < 0.38, (0.38 - pits) * 0.012, 0.0)
    sand = _periodic_fbm((TILE, TILE), 128, 2, 22)

    face = 0.011 * bevel
    face += 0.0012 * (block_tilt_u * grid["u"] / 0.4 + block_tilt_v * grid["v"] / 0.2)
    face -= pit_depth
    height = np.where(inside, face, 0.0015 * (sand - 0.5))

    luminance = np.where(
        inside,
        0.635 + (block_value - 0.5) * 0.075 - pit_depth * 16.0,
        0.560 + (sand - 0.5) * 0.10,
    )
    mottle = _periodic_fbm((TILE, TILE), 6, 3, 23)
    luminance += (mottle - 0.5) * 0.045
    tint = np.array([1.02, 1.0, 0.965], dtype=np.float32)
    colour = luminance[..., None] * tint[None, None, :]

    roughness = np.where(inside, 0.84 + (block_value - 0.5) * 0.05, 0.92)
    roughness += pit_depth * 6.0 + (sand - 0.5) * 0.03

    paths = {
        _texture_name("cmu", "color"): _to_srgb_image(colour),
        _texture_name("cmu", "normal"): _normal_from_metric_height(height, tile_m),
        _texture_name("cmu_roughness", "data"): _to_data_image(roughness),
        _texture_name("cmu_ao", "data"): _ao_from_metric_height(height, 34.0),
    }
    outputs: list[Path] = []
    for name, image in paths.items():
        path = output_root / name
        _save(_seal_edges(image), path)
        outputs.append(path)
    return outputs


def _build_interior_brick(output_root: Path) -> list[Path]:
    """Red clay brick running bond: tile 1.2 x 0.6 m = 6 bricks x 8 courses."""

    tile_m = (1.2, 0.6)
    grid = _masonry_grid(tile_m, (0.2, 0.075), 0.010, 0.1)
    inside = grid["inside"]
    bevel = _smoothstep(grid["edge_distance"] / 0.0045)

    # Ivory-buff clay units with a sparse darker "flashed" population brighten
    # the tunnel interior far more than the previous deep-red bond.
    value_shift = (_cell_hash(grid["column"], grid["course"], 31) - 0.5) * 0.078
    warm_shift = (_cell_hash(grid["column"], grid["course"], 32) - 0.5) * 0.047
    brick_colour = np.stack(
        (
            0.776 + value_shift + warm_shift,
            0.714 + value_shift,
            0.620 + value_shift - warm_shift,
        ),
        axis=-1,
    ).astype(np.float32)
    flashed = _cell_hash(grid["column"], grid["course"], 37) < 0.12
    flash_tint = np.array([0.82, 0.78, 0.76], dtype=np.float32)
    brick_colour = np.where(
        flashed[..., None], brick_colour * flash_tint[None, None, :], brick_colour
    )

    kiln = _periodic_fbm((TILE, TILE), 12, 3, 33)
    brick_colour *= (0.92 + kiln * 0.16)[..., None]
    grain = _periodic_fbm((TILE, TILE), 192, 2, 36)
    brick_colour *= (0.96 + grain * 0.08)[..., None]
    specks = _periodic_value_noise((TILE, TILE), (512, 512), 38) > 0.93
    brick_colour = np.where((specks & inside)[..., None], brick_colour + 0.08, brick_colour)

    sand = _periodic_fbm((TILE, TILE), 128, 2, 34)
    mortar_colour = (0.65 + (sand - 0.5) * 0.12)[..., None] * np.array(
        [1.0, 0.978, 0.93], dtype=np.float32
    )[None, None, :]
    colour = np.where(inside[..., None], brick_colour, mortar_colour)

    wobble = _periodic_fbm((TILE, TILE), 48, 2, 35)
    height = np.where(
        inside,
        0.009 * bevel + 0.0018 * (wobble - 0.5),
        0.0012 * (sand - 0.5),
    )

    roughness = np.where(
        inside,
        0.62 + (kiln - 0.5) * 0.10 + np.where(flashed, 0.04, 0.0),
        0.88,
    )

    paths = {
        _texture_name("interior_brick", "color"): _to_srgb_image(colour),
        _texture_name("interior_brick", "normal"): _normal_from_metric_height(height, tile_m),
        _texture_name("interior_brick_roughness", "data"): _to_data_image(roughness),
        _texture_name("interior_brick_ao", "data"): _ao_from_metric_height(height, 30.0),
    }
    outputs: list[Path] = []
    for name, image in paths.items():
        path = output_root / name
        _save(_seal_edges(image), path)
        outputs.append(path)
    return outputs


def _build_corrugated_blue(output_root: Path) -> list[Path]:
    """Factory-blue trapezoidal cladding: tile 1.2 x 1.2 m = 6 ribs at 0.2 m pitch."""

    tile_m = (1.2, 1.2)
    pitch = 0.2
    xs = (np.arange(TILE, dtype=np.float32)[None, :] + 0.5) * (tile_m[0] / TILE)
    xs = np.broadcast_to(xs, (TILE, TILE))
    u = (xs % pitch) / pitch

    # Trapezoidal profile across one 200 mm module: valley, web, 60 mm crest,
    # web, valley.  30 mm physical rib depth drives the exact normal slopes.
    crest = 0.30
    web = 0.125
    ramp_up = _smoothstep((u - (0.5 - crest / 2 - web)) / web)
    ramp_down = 1.0 - _smoothstep((u - (0.5 + crest / 2)) / web)
    profile = np.minimum(ramp_up, ramp_down)
    height = profile * 0.030

    rib_index = np.floor((xs % tile_m[0]) / pitch).astype(np.int64)
    rib_shade = _cell_hash(rib_index, np.zeros_like(rib_index), 41)

    brushing = _periodic_value_noise((TILE, TILE), (7, 173), 42)
    dust = _periodic_fbm((TILE, TILE), 9, 3, 43)

    base = np.array([0.117, 0.302, 0.639], dtype=np.float32)
    shading = 0.86 + profile * 0.20
    luminance = shading * (0.97 + (rib_shade - 0.5) * 0.05 + (brushing - 0.5) * 0.035)
    colour = base[None, None, :] * luminance[..., None]
    valley_dust = np.clip((0.35 - profile), 0.0, 1.0) * (dust - 0.5) * 0.08
    colour += valley_dust[..., None]

    roughness = 0.40 - profile * 0.07 + (dust - 0.5) * 0.06 + (brushing - 0.5) * 0.03

    paths = {
        _texture_name("corrugated_blue", "color"): _to_srgb_image(colour),
        _texture_name("corrugated_blue", "normal"): _normal_from_metric_height(height, tile_m),
        _texture_name("corrugated_blue_roughness", "data"): _to_data_image(roughness),
        _texture_name("corrugated_blue_ao", "data"): _ao_from_metric_height(height, 18.0),
    }
    outputs: list[Path] = []
    for name, image in paths.items():
        path = output_root / name
        _save(_seal_edges(image), path)
        outputs.append(path)
    return outputs


def _offset_blend_seamless(source: Image.Image, size: int = TILE) -> np.ndarray:
    """Make a photo tile periodic without mirror kaleidoscope symmetry.

    The half-tile-offset copy is continuous across the tile border; a feathered
    center-weighted mask hides that copy's own seam, which lies mid-tile under
    fully opaque original content.
    """

    base = ImageOps.fit(source.convert("RGB"), (size, size), Image.Resampling.LANCZOS)
    arr = np.asarray(base, dtype=np.float32) / 255.0
    shifted = np.roll(arr, (size // 2, size // 2), axis=(0, 1))
    feather = size // 5
    edge = np.minimum(np.arange(size, dtype=np.float32), np.arange(size, dtype=np.float32)[::-1])
    weight = _smoothstep(edge / feather)
    mask = np.minimum(weight[:, None], weight[None, :])
    return arr * mask[..., None] + shifted * (1.0 - mask[..., None])


def _build_wet_concrete(output_root: Path) -> list[Path]:
    """Sealed wet concrete: tile 2 x 2 m with saw-cut joints on the tile grid."""

    tile_m = (2.0, 2.0)
    source_path = SOURCE_ROOT / "wet_concrete_source.png"
    if not source_path.is_file():
        raise FileNotFoundError(f"missing texture source: {source_path}")
    with Image.open(source_path) as source:
        colour = _offset_blend_seamless(source)

    mottle = _periodic_fbm((TILE, TILE), 4, 4, 51)
    colour *= (0.94 + (mottle - 0.5) * 0.14)[..., None]

    # A 2 x 2 m saw-cut joint grid lands exactly on the tile border, reading as
    # real slab control joints across the whole 18 m floor.
    joint_half_m = 0.004
    px_m = tile_m[0] / TILE
    axis_m = (np.arange(TILE, dtype=np.float32) + 0.5) * px_m
    distance_edge = np.minimum(axis_m, tile_m[0] - axis_m)
    joint_line = np.clip(1.0 - distance_edge / (joint_half_m + 2.0 * px_m), 0.0, 1.0)
    joint = np.maximum(joint_line[:, None], joint_line[None, :])
    colour *= (1.0 - joint * 0.42)[..., None]

    micro = _periodic_fbm((TILE, TILE), 96, 2, 52)
    height = 0.0012 * (micro - 0.5) - joint * 0.006

    wet = _smoothstep((mottle - 0.42) / 0.2)
    roughness = 0.46 - wet * 0.30 + (micro - 0.5) * 0.06 + joint * 0.18

    paths = {
        _texture_name("wet_concrete", "color"): _to_srgb_image(colour),
        _texture_name("wet_concrete", "normal"): _normal_from_metric_height(height, tile_m),
        _texture_name("wet_concrete_roughness", "data"): _to_data_image(roughness),
        _texture_name("wet_concrete_ao", "data"): _ao_from_metric_height(height, 22.0),
    }
    outputs: list[Path] = []
    for name, image in paths.items():
        path = output_root / name
        _save(_seal_edges(image), path)
        outputs.append(path)
    return outputs


def _build_tileables(output_root: Path) -> list[Path]:
    return (
        _build_cmu(output_root)
        + _build_interior_brick(output_root)
        + _build_corrugated_blue(output_root)
        + _build_wet_concrete(output_root)
    )


def _build_brush_cards(output_root: Path) -> list[Path]:
    size = 512
    colour = Image.new("RGB", (size, size), (7, 25, 68))
    opacity = Image.new("L", (size, size), 0)
    colour_draw = ImageDraw.Draw(colour)
    opacity_draw = ImageDraw.Draw(opacity)
    palette = ((4, 64, 178), (0, 125, 214), (0, 177, 204), (7, 44, 129))
    strip_height = 15
    gap = 7
    for index, y in enumerate(range(4, size - strip_height, strip_height + gap)):
        phase = index * 0.71
        points_top: list[tuple[int, int]] = []
        points_bottom: list[tuple[int, int]] = []
        for x in range(0, size + 1, 16):
            wave = round(math.sin(x * 0.045 + phase) * 2.0)
            points_top.append((x, y + wave))
            points_bottom.append((x, y + strip_height + wave))
        polygon = points_top + list(reversed(points_bottom))
        colour_draw.polygon(polygon, fill=palette[index % len(palette)])
        opacity_draw.polygon(polygon, fill=255)
        # A thin highlight and shadow give each EVA strip volume in the card.
        colour_draw.line(points_top, fill=(18, 194, 236), width=2)
        colour_draw.line(points_bottom, fill=(2, 19, 61), width=2)
    # Break up only the free outer edge of the cards; the hub edge remains
    # opaque so no radial holes appear around the rotating shaft.
    opacity_array = np.asarray(opacity, dtype=np.uint8).copy()
    yy, xx = np.indices(opacity_array.shape)
    fray = (xx > int(size * 0.82)) & (((xx * 17 + yy * 31) % 47) < 4)
    opacity_array[fray] = 0
    opacity = Image.fromarray(opacity_array)
    colour = _dilate_alpha_colour(colour, opacity)
    luminance = np.asarray(colour.convert("L"), dtype=np.float32) / 255.0
    dx = (np.roll(luminance, -1, axis=1) - np.roll(luminance, 1, axis=1)) * 0.5
    dy = (np.roll(luminance, -1, axis=0) - np.roll(luminance, 1, axis=0)) * 0.5
    normal_vectors = np.dstack((-dx * 1.1, dy * 1.1, np.ones_like(luminance)))
    normal_vectors /= np.linalg.norm(normal_vectors, axis=2, keepdims=True).clip(min=1e-6)
    normal = Image.fromarray(np.clip((normal_vectors * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8))
    roughness = Image.new("L", (size, size), round(0.72 * 255))
    outputs = {
        _texture_name("brush_cards", "color"): colour,
        _texture_name("brush_cards", "normal"): normal,
        _texture_name("brush_cards_roughness", "data"): roughness,
        _texture_name("brush_cards_opacity", "data"): opacity,
    }
    paths: list[Path] = []
    for name, image in outputs.items():
        path = output_root / name
        _save(image, path)
        paths.append(path)
    return paths


def _sign_font(variation: str, size: int, fallback: str) -> ImageFont.FreeTypeFont:
    """Return a Bahnschrift named instance with a deterministic Arial fallback."""

    bahnschrift = Path("C:/Windows/Fonts/bahnschrift.ttf")
    if bahnschrift.is_file():
        font = ImageFont.truetype(str(bahnschrift), size=size)
        try:
            font.set_variation_by_name(variation)
        except OSError:
            pass
        else:
            return font
    return ImageFont.truetype(f"C:/Windows/Fonts/{fallback}", size=round(size * 0.875))


def _tracked_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    tracking: float,
) -> float:
    widths = [draw.textlength(character, font=font) for character in text]
    return float(sum(widths)) + tracking * (len(text) - 1)


def _tracked_text(
    draws: list[tuple[ImageDraw.ImageDraw, tuple[int, int, int]]],
    origin_x: float,
    baseline_y: float,
    text: str,
    font: ImageFont.FreeTypeFont,
    tracking: float,
) -> None:
    x = origin_x
    for character in text:
        for draw, fill in draws:
            draw.text((x, baseline_y), character, font=font, fill=fill, anchor="ls")
        x += draws[0][0].textlength(character, font=font) + tracking


# Logo geometry shared by the colour and emissive layers: a launched cannonball
# with a comet tail and stray droplets, all inside the circular badge.
_SIGN_TAIL_C = ((282, 237), (272, 223), (216, 269), (220, 273))
_SIGN_TAIL_B = ((317, 303), (299, 279), (224, 346), (228, 351))
_SIGN_TAIL_A = ((319, 272), (289, 229), (178, 332), (184, 341))
_SIGN_DROPLETS = (((196, 368), 9), ((232, 390), 6), ((172, 340), 5))
_SIGN_TAGLINE = "WASH · WAX · LAUNCH"


def _sign_badge_disc(
    pixels: np.ndarray,
    inner: tuple[int, int, int],
    outer: tuple[int, int, int],
) -> None:
    ys = np.arange(pixels.shape[0], dtype=np.float32)[:, None]
    xs = np.arange(pixels.shape[1], dtype=np.float32)[None, :]
    radius = np.sqrt((xs - 296.0) ** 2 + (ys - 256.0) ** 2)
    t = np.clip(radius / 160.0, 0.0, 1.0)[..., None]
    disc = (1.0 - t) * np.array(inner, dtype=np.float32) + t * np.array(outer, dtype=np.float32)
    mask = radius <= 160.0
    pixels[mask] = disc[mask]


def _sign_logo(draw: ImageDraw.ImageDraw, *, emissive: bool) -> None:
    scale = 0.65 if emissive else 1.0

    def level(colour: tuple[int, int, int]) -> tuple[int, int, int]:
        return tuple(round(channel * scale) for channel in colour)

    draw.polygon(list(_SIGN_TAIL_C), fill=level((255, 196, 120)))
    draw.polygon(list(_SIGN_TAIL_B), fill=level((255, 168, 64)))
    draw.polygon(list(_SIGN_TAIL_A), fill=level((255, 120, 32)))
    ball_fill = (240, 248, 255) if emissive else (250, 252, 255)
    draw.ellipse((353 - 52, 216 - 52, 353 + 52, 216 + 52), fill=ball_fill)
    draw.ellipse((339 - 16, 202 - 16, 339 + 16, 202 + 16), fill=(255, 255, 255))
    droplet_fill = (170, 230, 255) if not emissive else (100, 180, 230)
    for (cx, cy), r in _SIGN_DROPLETS:
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=droplet_fill)


def _draw_sign_panel() -> tuple[Image.Image, Image.Image]:
    """Modern express-wash sign lockup: badge, DIN two-weight wordmark, tagline.

    The colour layer reads as a framed cabinet face by day; the emissive layer
    lights only the graphic elements so the night render looks channel-lit
    rather than a uniformly glowing panel.  The orange tagline pill survives
    the blue-leaning in-game emissiveFactor as the building's one warm accent.
    """

    width, height = 2048, 512

    # Background: vertical navy gradient, a diagonal sheen sweep, and an inner
    # shadow seating the face inside its retainer frame.
    ys = np.arange(height, dtype=np.float32)[:, None]
    xs = np.arange(width, dtype=np.float32)[None, :]
    t = np.broadcast_to(ys / (height - 1.0), (height, width))[..., None]
    top = np.array([14, 24, 52], dtype=np.float32)
    bottom = np.array([6, 12, 30], dtype=np.float32)
    pixels = (1.0 - t) * top + t * bottom
    sheen = 18.0 * np.exp(-((xs - 1.4 * ys - 300.0) ** 2) / (2.0 * 260.0**2))
    pixels += sheen[..., None]
    edge_x = np.minimum(xs, width - 1 - xs)
    edge_y = np.minimum(ys, height - 1 - ys)
    edge = np.minimum(
        np.broadcast_to(edge_x, (height, width)),
        np.broadcast_to(edge_y, (height, width)),
    )
    inner_shadow = 0.55 + 0.45 * np.clip(edge / 14.0, 0.0, 1.0)
    pixels *= inner_shadow[..., None]
    pixels = np.clip(pixels, 0.0, 255.0)

    colour = Image.fromarray(pixels.astype(np.uint8))
    shadow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    shadow_draw.ellipse((304 - 192, 264 - 192, 304 + 192, 264 + 192), fill=(2, 6, 18, 150))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=8))
    colour = Image.alpha_composite(colour.convert("RGBA"), shadow_layer).convert("RGB")

    pixels = np.asarray(colour, dtype=np.float32)
    _sign_badge_disc(pixels, (0, 178, 235), (0, 96, 176))
    colour = Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))
    colour_draw = ImageDraw.Draw(colour)

    colour_draw.ellipse((110, 70, 482, 442), outline=(238, 246, 252), width=16)
    colour_draw.ellipse((130, 90, 462, 422), outline=(0, 150, 220), width=4)
    _sign_logo(colour_draw, emissive=False)

    colour_draw.rounded_rectangle((820, 360, 1740, 448), radius=44, fill=(236, 98, 18))
    colour_draw.line((864, 368, 1696, 368), fill=(255, 150, 70), width=3)

    emissive = Image.new("RGB", (width, height), (0, 0, 0))
    emissive_draw = ImageDraw.Draw(emissive)
    emissive_draw.ellipse((296 - 160, 256 - 160, 296 + 160, 256 + 160), fill=(14, 60, 110))
    emissive_draw.ellipse((110, 70, 482, 442), outline=(215, 235, 250), width=16)
    emissive_draw.ellipse((130, 90, 462, 422), outline=(0, 140, 215), width=4)
    _sign_logo(emissive_draw, emissive=True)
    emissive_draw.rounded_rectangle((820, 360, 1740, 448), radius=44, fill=(150, 64, 14))
    emissive_draw.rounded_rectangle((10, 10, 2037, 501), radius=26, outline=(24, 48, 90), width=5)

    cannon_font = _sign_font("Bold Condensed", 288, "arialbd.ttf")
    wash_font = _sign_font("SemiLight Condensed", 288, "arial.ttf")
    tagline_font = _sign_font("SemiBold", 58, "arialbd.ttf")

    cannon_width = _tracked_width(colour_draw, "CANNON", cannon_font, 8.0)
    wash_width = _tracked_width(colour_draw, "WASH", wash_font, 8.0)
    total_width = cannon_width + 70.0 + wash_width
    if total_width > 1470.0:
        raise RuntimeError(f"sign lockup exceeds its safe zone: {total_width:.0f}px")
    left_x = 540.0 + (1470.0 - total_width) / 2.0
    _tracked_text(
        [(colour_draw, (245, 250, 255)), (emissive_draw, (238, 244, 255))],
        left_x,
        312.0,
        "CANNON",
        cannon_font,
        8.0,
    )
    _tracked_text(
        [(colour_draw, (0, 190, 255)), (emissive_draw, (90, 200, 255))],
        left_x + cannon_width + 70.0,
        312.0,
        "WASH",
        wash_font,
        8.0,
    )

    tagline_width = _tracked_width(colour_draw, _SIGN_TAGLINE, tagline_font, 6.0)
    if tagline_width > 860.0:
        raise RuntimeError(f"sign tagline exceeds its pill: {tagline_width:.0f}px")
    tagline_x = 1280.0 - tagline_width / 2.0
    _tracked_text([(colour_draw, (16, 20, 34))], tagline_x, 422.0, _SIGN_TAGLINE, tagline_font, 6.0)
    _tracked_text([(emissive_draw, (0, 0, 0))], tagline_x, 422.0, _SIGN_TAGLINE, tagline_font, 6.0)

    return colour, emissive


# FIRING TABLE menu copy: express-wash tier structure delivered in artillery
# deadpan. Lower tiers pointedly do not launch you; the flagship does, and it
# is of course the most popular. Written for a smart six-year-old and a wise
# fifty-one-year-old at the same time.
_MENU_TITLE = "FIRING TABLE"
_MENU_TIERS: Final = (
    ("THE DUD", "Soap, rinse, dry. Does not go off.", "$3", False),
    ("THE MISFIRE", "Wash & wax. Departure still voluntary.", "$6", False),
    ("HALF CHARGE", "Repairs your car, then gently fires it.", "$12", False),
    ("MUZZLE VELOCITY", "Full powder. Exit at 360 km/h. GO.", "$24", True),
)
_MENU_FINE_PRINT = (
    "Do not exit vehicle. The vehicle will exit.",
    "Landing is the customer's responsibility.",
)
_THANKS_LINE = "THANK YOU! COME BACK DOWN SOON."


def _draw_menu_panel() -> tuple[Image.Image, Image.Image]:
    """Backlit FIRING TABLE menu board for the entrance-lane monument."""

    width, height = 416, 512
    colour = Image.new("RGB", (width, height), (6, 14, 32))
    emissive = Image.new("RGB", (width, height), (0, 0, 0))
    colour_draw = ImageDraw.Draw(colour)
    emissive_draw = ImageDraw.Draw(emissive)

    colour_draw.rectangle((4, 4, width - 5, height - 5), outline=(0, 150, 220), width=3)
    emissive_draw.rectangle((4, 4, width - 5, height - 5), outline=(24, 60, 110), width=3)

    title_font = _sign_font("Bold Condensed", 44, "arialbd.ttf")
    name_font = _sign_font("Bold Condensed", 30, "arialbd.ttf")
    blurb_font = _sign_font("SemiLight", 18, "arial.ttf")
    tag_font = _sign_font("SemiBold", 13, "arialbd.ttf")
    fine_font = _sign_font("SemiLight", 13, "arial.ttf")

    title_width = _tracked_width(colour_draw, _MENU_TITLE, title_font, 2.0)
    title_x = (width - title_width) / 2.0
    _tracked_text(
        [(colour_draw, (240, 247, 255)), (emissive_draw, (225, 238, 252))],
        title_x,
        56.0,
        _MENU_TITLE,
        title_font,
        2.0,
    )
    colour_draw.line((24, 70, width - 24, 70), fill=(0, 150, 220), width=2)
    emissive_draw.line((24, 70, width - 24, 70), fill=(20, 70, 120), width=2)

    for index, (name, blurb, price, most_popular) in enumerate(_MENU_TIERS):
        row_top = 84 + index * 92
        if most_popular:
            colour_draw.rounded_rectangle(
                (8, row_top - 4, width - 9, row_top + 66), radius=10, fill=(236, 98, 18)
            )
            emissive_draw.rounded_rectangle(
                (8, row_top - 4, width - 9, row_top + 66), radius=10, fill=(150, 64, 14)
            )
            tag_width = _tracked_width(colour_draw, "MOST POPULAR", tag_font, 1.0)
            _tracked_text(
                [(colour_draw, (16, 20, 34)), (emissive_draw, (0, 0, 0))],
                width - 16 - tag_width,
                row_top + 62.0,
                "MOST POPULAR",
                tag_font,
                1.0,
            )
            name_fill = (16, 20, 34)
            price_fill = (16, 20, 34)
            blurb_fill = (52, 26, 8)
            name_glow = (0, 0, 0)
            price_glow = (0, 0, 0)
            blurb_glow = (0, 0, 0)
        else:
            name_fill = (235, 243, 252)
            price_fill = (0, 190, 255)
            blurb_fill = (150, 170, 195)
            name_glow = (205, 224, 240)
            price_glow = (70, 185, 250)
            blurb_glow = (90, 110, 140)
        _tracked_text(
            [(colour_draw, name_fill), (emissive_draw, name_glow)],
            16.0,
            row_top + 26.0,
            name,
            name_font,
            1.0,
        )
        price_width = _tracked_width(colour_draw, price, name_font, 1.0)
        _tracked_text(
            [(colour_draw, price_fill), (emissive_draw, price_glow)],
            width - 16 - price_width,
            row_top + 26.0,
            price,
            name_font,
            1.0,
        )
        _tracked_text(
            [(colour_draw, blurb_fill), (emissive_draw, blurb_glow)],
            16.0,
            row_top + 52.0,
            blurb,
            blurb_font,
            0.0,
        )

    for line_index, line in enumerate(_MENU_FINE_PRINT):
        line_width = _tracked_width(colour_draw, line, fine_font, 0.0)
        _tracked_text(
            [(colour_draw, (110, 130, 160)), (emissive_draw, (60, 80, 105))],
            (width - line_width) / 2.0,
            468.0 + line_index * 18.0,
            line,
            fine_font,
            0.0,
        )
    return colour, emissive


def _draw_thanks_strip() -> tuple[Image.Image, Image.Image]:
    """Exit strip; at 360 km/h the driver cannot read it, which is the joke."""

    width, height = 1600, 250
    colour = Image.new("RGB", (width, height), (6, 14, 32))
    emissive = Image.new("RGB", (width, height), (0, 0, 0))
    colour_draw = ImageDraw.Draw(colour)
    emissive_draw = ImageDraw.Draw(emissive)
    colour_draw.rectangle((6, 6, width - 7, height - 7), outline=(0, 150, 220), width=4)
    emissive_draw.rectangle((6, 6, width - 7, height - 7), outline=(24, 60, 110), width=4)

    font = _sign_font("Bold Condensed", 96, "arialbd.ttf")
    first, second = "THANK YOU! ", "COME BACK DOWN SOON."
    first_width = _tracked_width(colour_draw, first, font, 2.0)
    second_width = _tracked_width(colour_draw, second, font, 2.0)
    start_x = (width - (first_width + second_width)) / 2.0
    baseline = 158.0
    _tracked_text(
        [(colour_draw, (245, 250, 255)), (emissive_draw, (235, 244, 255))],
        start_x,
        baseline,
        first,
        font,
        2.0,
    )
    _tracked_text(
        [(colour_draw, (0, 190, 255)), (emissive_draw, (90, 200, 255))],
        start_x + first_width,
        baseline,
        second,
        font,
        2.0,
    )
    return colour, emissive


def _build_sign(output_root: Path) -> list[Path]:
    """Compose the 2048x1024 signage atlas: sign, menu board, thank-you strip.

    The entrance sign occupies the full top half (UV v 0.5..1); the menu board
    and exit strip live in the bottom half so the single emissive sign_face
    material can drive all three displays without adding a material slot.
    """

    width, height = 2048, 1024
    colour = Image.new("RGB", (width, height), (5, 9, 20))
    emissive = Image.new("RGB", (width, height), (0, 0, 0))

    sign_colour, sign_emissive = _draw_sign_panel()
    menu_colour, menu_emissive = _draw_menu_panel()
    thanks_colour, thanks_emissive = _draw_thanks_strip()
    colour.paste(sign_colour, (0, 0))
    emissive.paste(sign_emissive, (0, 0))
    colour.paste(menu_colour, (0, 512))
    emissive.paste(menu_emissive, (0, 512))
    colour.paste(thanks_colour, (448, 512))
    emissive.paste(thanks_emissive, (448, 512))

    # Tasteful bloom is baked only into the emissive mask; actual illumination
    # still comes from the namespaced scene lights.
    sharp = np.asarray(emissive, dtype=np.float32)
    blurred = np.asarray(emissive.filter(ImageFilter.GaussianBlur(radius=12)), dtype=np.float32)
    emissive = Image.fromarray(np.maximum(sharp, blurred * 0.6).astype(np.uint8))

    outputs = {
        _texture_name("sign", "color"): colour,
        _texture_name("sign_emissive", "data"): emissive,
    }
    paths: list[Path] = []
    for name, image in outputs.items():
        path = output_root / name
        _save(image, path)
        paths.append(path)
    return paths


def build(output_root: Path) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)
    expected = set()
    outputs = (
        _build_tileables(output_root) + _build_brush_cards(output_root) + _build_sign(output_root)
    )
    expected.update(path.name for path in outputs)
    for existing in output_root.glob("*.png"):
        if existing.name not in expected:
            existing.unlink()
    files = []
    for path in sorted(outputs):
        with Image.open(path) as image:
            files.append(
                {
                    "name": path.name,
                    "width": image.width,
                    "height": image.height,
                    "mode": image.mode,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return {
        "schema_version": 1,
        "texture_root": "textures/generated_png",
        "source_policy": "metric_procedural_seamless_power_of_two",
        "normal_convention": "OpenGL_Y_positive",
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()
    manifest = build(args.output_root.resolve())
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
