"""Build deterministic BeamNG-ready PBR textures for Cannon Car Wash.

The four source base-colour images are deliberately kept outside the runtime
mod tree.  This script converts them to power-of-two, mirror-seamless maps and
derives conservative normal, roughness, and ambient-occlusion data maps.  It
also builds the alpha-tested brush-card atlas and the dual-layer emissive sign.

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

SOURCE_SPECS: Final = {
    "cmu": {
        "source": "cmu_source.png",
        "normal_strength": 3.2,
        "roughness": 0.78,
        "roughness_variation": 0.15,
        "ao_strength": 1.5,
    },
    "interior_brick": {
        "source": "interior_brick_source.png",
        "normal_strength": 3.0,
        "roughness": 0.68,
        "roughness_variation": 0.13,
        "ao_strength": 1.45,
    },
    "wet_concrete": {
        "source": "wet_concrete_source.png",
        "normal_strength": 1.35,
        "roughness": 0.31,
        "roughness_variation": 0.22,
        "ao_strength": 0.65,
    },
    "corrugated_blue": {
        "source": "corrugated_blue_source.png",
        "normal_strength": 2.4,
        "roughness": 0.42,
        "roughness_variation": 0.12,
        "ao_strength": 1.0,
    },
}


def _mirror_seamless(source: Image.Image, size: int = 1024) -> Image.Image:
    """Return a power-of-two texture with identical opposite boundaries."""

    half = size // 2
    base = ImageOps.fit(source.convert("RGB"), (half, half), Image.Resampling.LANCZOS)
    result = Image.new("RGB", (size, size))
    result.paste(base, (0, 0))
    result.paste(ImageOps.mirror(base), (half, 0))
    result.paste(ImageOps.flip(base), (0, half))
    result.paste(ImageOps.flip(ImageOps.mirror(base)), (half, half))
    return result


def _luminance(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32) / 255.0


def _normal_from_height(image: Image.Image, strength: float) -> Image.Image:
    height = _luminance(image)
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    # Image rows point down while the texture V axis points up.  Positive green
    # is therefore +dy here, producing BeamNG's required OpenGL Y+ normals.
    normal = np.dstack((-dx * strength, dy * strength, np.ones_like(height)))
    normal /= np.linalg.norm(normal, axis=2, keepdims=True).clip(min=1e-6)
    encoded = np.clip((normal * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(encoded)


def _roughness_from_colour(
    image: Image.Image,
    base: float,
    variation: float,
) -> Image.Image:
    luminance = _luminance(image)
    local = luminance - float(luminance.mean())
    roughness = np.clip(base + local * variation, 0.08, 0.96)
    return Image.fromarray((roughness * 255.0).astype(np.uint8))


def _ao_from_height(image: Image.Image, strength: float) -> Image.Image:
    height_image = image.convert("L")
    height = np.asarray(height_image, dtype=np.float32) / 255.0
    neighbourhood = (
        np.asarray(height_image.filter(ImageFilter.GaussianBlur(radius=6)), dtype=np.float32)
        / 255.0
    )
    cavities = np.maximum(neighbourhood - height, 0.0)
    ao = np.clip(1.0 - cavities * strength, 0.36, 1.0)
    return Image.fromarray((ao * 255.0).astype(np.uint8))


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


def _build_tileables(output_root: Path) -> list[Path]:
    outputs: list[Path] = []
    for stem, spec in SOURCE_SPECS.items():
        source_path = SOURCE_ROOT / str(spec["source"])
        if not source_path.is_file():
            raise FileNotFoundError(f"missing texture source: {source_path}")
        with Image.open(source_path) as source:
            colour = _mirror_seamless(source)
        maps = {
            _texture_name(stem, "color"): colour,
            _texture_name(stem, "normal"): _normal_from_height(
                colour, float(spec["normal_strength"])
            ),
            _texture_name(stem + "_roughness", "data"): _roughness_from_colour(
                colour,
                float(spec["roughness"]),
                float(spec["roughness_variation"]),
            ),
            _texture_name(stem + "_ao", "data"): _ao_from_height(
                colour, float(spec["ao_strength"])
            ),
        }
        for name, image in maps.items():
            path = output_root / name
            _save(_seal_edges(image), path)
            outputs.append(path)
    return outputs


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
    normal = _normal_from_height(colour, 1.1)
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


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _build_sign(output_root: Path) -> list[Path]:
    size = (1024, 256)
    colour = Image.new("RGB", size, (3, 15, 42))
    emissive = Image.new("RGB", size, (0, 0, 0))
    colour_draw = ImageDraw.Draw(colour)
    emissive_draw = ImageDraw.Draw(emissive)
    font = _font(122)
    label = "CANNON WASH"
    bounds = colour_draw.textbbox((0, 0), label, font=font, stroke_width=2)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    origin = ((size[0] - width) // 2, (size[1] - height) // 2 - bounds[1])
    colour_draw.rounded_rectangle((12, 12, 1011, 243), radius=20, outline=(0, 103, 187), width=8)
    colour_draw.text(
        origin,
        label,
        font=font,
        fill=(214, 245, 255),
        stroke_width=3,
        stroke_fill=(0, 89, 167),
    )
    emissive_draw.rounded_rectangle((12, 12, 1011, 243), radius=20, outline=(0, 76, 160), width=6)
    emissive_draw.text(
        origin,
        label,
        font=font,
        fill=(225, 255, 255),
        stroke_width=5,
        stroke_fill=(0, 105, 230),
    )
    # Small bloom is baked only into the emissive mask; actual illumination is
    # provided by namespaced scene lights rather than pretending albedo glows.
    glow = emissive.filter(ImageFilter.GaussianBlur(radius=8))
    emissive = Image.fromarray(np.maximum(np.asarray(emissive), np.asarray(glow)).astype(np.uint8))
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
        "source_policy": "mirror_seamless_power_of_two",
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
