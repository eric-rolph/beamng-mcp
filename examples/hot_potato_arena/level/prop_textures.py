"""Cook the B4 prop materials' five maps from the CC0 sources, deterministically.

One material -> five PNGs (``_b.color``, ``_nm.normal``, ``_r.data``, ``_ao.data``,
``_o.data``) under ``levels/<id>/art/shapes/props/``, plus a manifest with each file's
sha256 so ``props_build.verify`` can refuse a tree that drifted from its cook.

The CC0 tiles come through B3's ``forest_textures.cook_tile`` rather than a second copy of
that loader -- the same ``_find`` glob, the same ``arm`` unpacking, the same LANCZOS resize.
What B4 adds on top is small and named per material: the roughness remap into the range the
design gives each surface, the growth-ring end grain (``proplib.texture_kit.end_grain``, the
catapult round's crosscut recipe), the charred bands at the kindling logs' fire ends, the
rust overlay on the lantern metal, the emissive globe, and the routed sign face -- the
repo's panel-text recipe (``texture_kit._font_file`` + PIL, the way ``arena_rim`` bakes the
rim plate).

Every shipped square is a POWER OF TWO: a non-power-of-two texture is silently never cooked
and draws missing-texture magenta (level_facts, B1 r2).

    .\\.venv\\Scripts\\python.exe -m examples.hot_potato_arena.level.prop_textures \\
        --out examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena \\
        --cache examples/hot_potato_arena/cc0_cache \\
        --manifest examples/hot_potato_arena/authoring/ericrolph_hot_potato_arena_prop_textures.json
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "examples" / "giant_props"))

from proplib import texture_kit as tk  # noqa: E402

from examples.hot_potato_arena.level import forest_textures as ft  # noqa: E402
from examples.hot_potato_arena.level import props_spec as ps  # noqa: E402

TEXTURE_SEED = 0x50545853  # "PTXS"
ROLES = ("b", "nm", "r", "ao", "o")
ROLE_MAP = {"b": "base", "nm": "normal", "r": "roughness", "ao": "ao", "o": "opacity"}
SIGN_LINES = ("GIANT'S HEARTH", "HOT COALS")
#: the sign board face is 1.70 x 0.70 m (blender_props.build_sign)
SIGN_BOARD_ASPECT = 0.70 / 1.70


class PropTextureError(RuntimeError):
    """A CC0 source is missing or a recipe cannot be honoured."""


def _rng(*parts: Any) -> np.random.Generator:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big") ^ TEXTURE_SEED)


def _png(array: np.ndarray) -> bytes:
    mode = "L" if array.ndim == 2 else "RGB"
    buffer = io.BytesIO()
    Image.fromarray(array, mode).save(buffer, format="PNG", optimize=False, compress_level=6)
    return buffer.getvalue()


def _remap_roughness(rough: np.ndarray, low: float, high: float) -> np.ndarray:
    data = rough.astype(np.float64) / 255.0
    return np.clip((low + (high - low) * data) * 255.0, 0, 255).astype(np.uint8)


def _normal_from_height(height: np.ndarray, strength: float = 2.0) -> np.ndarray:
    return np.clip(tk._height_to_normal(height, strength) * 255.0, 0, 255).astype(np.uint8)


def _blend_normal(base: np.ndarray, extra: np.ndarray, amount: float) -> np.ndarray:
    """Blend a detail normal into a base normal in tangent space (linear, then renormalise)."""

    b = base.astype(np.float64) / 127.5 - 1.0
    e = extra.astype(np.float64) / 127.5 - 1.0
    mixed = b + np.stack([e[..., 0] * amount, e[..., 1] * amount, np.zeros_like(e[..., 2])], -1)
    length = np.linalg.norm(mixed, axis=-1, keepdims=True)
    length[length == 0] = 1.0
    return np.clip((mixed / length + 1.0) * 127.5, 0, 255).astype(np.uint8)


def _end_grain_layer(size: int, key: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    colour, height, rough, _ = tk.end_grain(size, _rng(key, "rings"), aspect=1.0, pith_drop=0.0)
    return (
        np.clip(colour * 255.0, 0, 255).astype(np.uint8),
        height,
        np.clip(rough * 255.0, 0, 255).astype(np.uint8),
    )


def _sign_letters(size: int, board_aspect: float) -> np.ndarray:
    """The two sign lines as a 0..1 coverage mask, PRE-DISTORTED for the board's aspect.

    The board face is 1.70 x 0.70 m and a square texture is stretched onto it, so letters
    drawn square on the map come out 2.4x too short in the world.  They are therefore drawn
    on a canvas with the BOARD's aspect and then resized to the square, which inverts the
    stretch exactly.  The point size is fitted to the longest line rather than guessed --
    "GIANT'S HEARTH" at a guessed 0.155 x 1024 px ran off both edges of the map.
    """

    path = tk._font_file()
    height = max(16, round(size * board_aspect))
    canvas = Image.new("L", (size, height), 0)
    draw = ImageDraw.Draw(canvas)
    rows = []
    for index, line in enumerate(SIGN_LINES):
        px = max(8, int(height * (0.34 if index == 0 else 0.27)))
        while px > 8:
            font = ImageFont.truetype(path, px) if path else ImageFont.load_default()
            box = draw.textbbox((0, 0), line, font=font)
            if (box[2] - box[0]) <= size * 0.88:
                break
            px = int(px * 0.94)
        rows.append((line, font, draw.textbbox((0, 0), line, font=font)))
    total = sum(box[3] - box[1] for _line, _font, box in rows) + int(height * 0.10)
    y = (height - total) // 2
    for line, font, box in rows:
        x = (size - (box[2] - box[0])) // 2 - box[0]
        draw.text((x, y - box[1]), line, fill=255, font=font)
        y += (box[3] - box[1]) + int(height * 0.10)
    stretched = canvas.resize((size, size), Image.LANCZOS)
    return np.asarray(stretched, dtype=np.float64) / 255.0


def _sign_face(size: int, plank: dict[str, np.ndarray], key: str) -> dict[str, np.ndarray]:
    """Burn the two sign lines into the plank: the repo's panel-text recipe."""

    letters = _sign_letters(size, SIGN_BOARD_ASPECT)
    # a routed groove: burnt-dark walls, a touch of AO, and a real normal step
    colour = plank["base"].astype(np.float64)
    colour *= (1.0 - letters * 0.78)[..., None]
    height = -letters * 0.55
    rough = np.clip(plank["roughness"].astype(np.float64) / 255.0 + letters * 0.22, 0, 1)
    ao = np.clip(plank["ao"].astype(np.float64) / 255.0 * (1.0 - letters * 0.45), 0, 1)
    return {
        "base": np.clip(colour, 0, 255).astype(np.uint8),
        "normal": _blend_normal(plank["normal"], _normal_from_height(height, 3.0), 1.0),
        "roughness": np.clip(rough * 255.0, 0, 255).astype(np.uint8),
        "ao": np.clip(ao * 255.0, 0, 255).astype(np.uint8),
        "opacity": np.full((size, size), 255, dtype=np.uint8),
    }


def _rust_overlay(maps: dict[str, np.ndarray], cache: Path, asset: str, size: int, key: str):
    """Blotch a rust tile over the plate metal with a low-frequency mask."""

    rust = ft.cook_tile({"size": size, "cc0": asset}, cache)
    mask = tk._fbm(size, _rng(key, "rust"), base_cells=4, octaves=4)
    mask = np.clip((mask - 0.44) * 3.4, 0.0, 1.0)[..., None]
    maps["base"] = np.clip(
        maps["base"].astype(np.float64) * (1 - mask) + rust["base"].astype(np.float64) * mask,
        0,
        255,
    ).astype(np.uint8)
    maps["roughness"] = np.clip(
        maps["roughness"].astype(np.float64) * (1 - mask[..., 0])
        + rust["roughness"].astype(np.float64) * mask[..., 0],
        0,
        255,
    ).astype(np.uint8)
    maps["normal"] = _blend_normal(maps["normal"], rust["normal"], 0.55)
    return maps


def _weathering(
    maps: dict[str, np.ndarray], size: int, key: str, recipe: dict[str, Any]
) -> dict[str, np.ndarray]:
    """A LOW-FREQUENCY weathering macro: the thing that survives being mipped down.

    Critic pass 3's player judgement: the bench log is "genuinely good at the two distances
    that matter and weak at the third" -- at 60-130 m ``b4_bench_broadside``,
    ``b4_bench_approach`` and ``b4_bench_crown`` "flatten into pale timber slabs and the
    illusion thins".  The critic read it as a LOD or texture-scale question.  It is neither:
    the log is 100 m long, so at 130 m it still draws its a700, and its grain tile is ~6 m,
    which is 30 px at that range.

    What is actually missing is SCALE in the albedo.  Every feature the two bench materials
    carry lives at the grain's own frequency, and a mip chain averages exactly that away --
    so past the range where one tile covers a few pixels the whole flank converges on its own
    mean, which is a pale grey-brown, and 60 m of log becomes one flat value.  A pale slab is
    what a texture with no low-frequency content looks like from far enough away, by
    construction, whatever its resolution.

    So this adds content at a frequency the mips KEEP: ``cells`` blotches across the tile
    (two or three, not twenty), darkening the albedo by up to ``depth`` and roughening it by
    ``rough``, plus a matching AO dip.  At arm's length it reads as damp and dry patches on
    old timber; at 130 m it is the tonal break-up that stops the flank averaging flat.  It is
    deliberately NOT a normal-map change: relief at this scale would fight the log's own
    silhouette, and the silhouette is now doing its own work (the containment bolster gives
    the broadside two standing bark rails and a shadow line the whole 60 m).
    """

    cells = int(recipe.get("cells", 3))
    octaves = int(recipe.get("octaves", 3))
    depth = float(recipe.get("depth", 0.28))
    rough = float(recipe.get("rough", 0.10))
    mask = tk._fbm(size, _rng(key, "weather"), base_cells=cells, octaves=octaves)
    mask = np.clip((mask - mask.mean()) * 1.9 + 0.5, 0.0, 1.0)
    maps["base"] = np.clip(
        maps["base"].astype(np.float64) * (1.0 - depth * mask[..., None]), 0, 255
    ).astype(np.uint8)
    maps["roughness"] = np.clip(
        maps["roughness"].astype(np.float64) + rough * 255.0 * mask, 0, 255
    ).astype(np.uint8)
    maps["ao"] = np.clip(maps["ao"].astype(np.float64) * (1.0 - 0.5 * depth * mask), 0, 255).astype(
        np.uint8
    )
    return maps


def _hewn_relief(
    maps: dict[str, np.ndarray], size: int, key: str, recipe: dict[str, Any]
) -> dict[str, np.ndarray]:
    """Adze scallops, the hewer's wander and saw chatter: the RELIEF a hewn face is made of.

    r5, and it is a measurement that asked for it rather than a frame.  ``t1_detail.py``
    reads ``normal_relief_p50`` (median |xy| of the normal map) off the SHIPPED bytes:

        bench_hewn 0.090   bench_bark 0.271   B4 kindling bark 0.350
        B3 forest knotted bark 0.332          B1 terrain rock detail 0.332

    The deck is three to four times flatter than every surface it is seen beside, so at any
    distance where the grain has mipped away there is nothing left for the light to shade --
    which is the other half of critic pass 3's "flattens into pale timber slabs".  The r4
    weathering macro fixed the ALBEDO half (measured: 1.30x the no-treatment control's
    residual contrast at 100 m on this material, 2.14x on the bark); this fixes the other.

    Three layers, all of them things a tool actually does to timber, and all sized against
    the tile's own measured world extent (5.57 m in u by 1.91 m in v, off the shipped DAE):

    * **scallops** -- ``-|sin|``, a dished cut rather than a sine wave, repeating along the
      log at ``stroke_cycles`` per tile.  Two cycles is a 0.95 m stroke, which is 7.5 screen
      pixels at 100 m and therefore survives the mip chain that removes the grain.
    * **wander** -- the depth of the cut varying around the girth, so the strokes are not a
      ruled grating.
    * **chatter** -- the fine ripple a saw leaves across the cut.

    ``jitter`` displaces the scallop's phase with fbm.  A strictly periodic stroke is a comb,
    and a comb at the mid field is precisely the defect that cost B1 r13 and r14 two
    revisions (``level_facts`` 2026-09-10: "break a tile with genuine aperiodicity, never by
    filtering harmonics out of the tile itself").  ``t1_detail.py`` measures the periodicity
    at 10 / 20 / 60 / 100 m and publishes it beside the relief, with the no-treatment control
    carried in every row.

    Deliberately NOT touched: roughness.  B1 r13 found a graft's roughness detail saturated
    its wall flat and dropped it -- "a graft is per-channel; do not assume all four maps want
    it".  The albedo is modulated only slightly (``albedo``), because the scallop has to read
    when the light is flat as well as when it rakes.
    """

    stroke = float(recipe.get("stroke_cycles", 2.0))
    across = float(recipe.get("across_cycles", 3.0))
    chatter = float(recipe.get("chatter_cycles", 13.0))
    jitter = float(recipe.get("jitter", 0.10))
    slope = float(recipe.get("slope", 0.25))
    ao = float(recipe.get("ao", 0.22))
    albedo = float(recipe.get("albedo", 0.10))

    v = np.arange(size, dtype=np.float64)[:, None] / size
    u = np.arange(size, dtype=np.float64)[None, :] / size
    wobble = tk._fbm(size, _rng(key, "adze"), base_cells=6, octaves=3) - 0.5
    # a scallop is a DISH, not a wave: the adze leaves concave cuts with sharp arrises
    dish = -np.abs(np.sin(np.pi * (stroke * v + jitter * wobble)))
    wander = 0.5 + 0.5 * np.sin(2.0 * np.pi * across * u)
    chat = np.sin(2.0 * np.pi * chatter * v + 1.7) * np.cos(2.0 * np.pi * (across * 2.0) * u)
    height = dish * (0.65 + 0.35 * wander) + 0.10 * chat
    height -= height.mean()

    # THE NORMAL IS BUILT FROM THE FIELD'S OWN GRADIENT AND SCALED TO A DECLARED SLOPE.
    #
    # `tk._height_to_normal` takes a per-TEXEL finite difference, so a feature 1,024 texels
    # long produces a gradient of order 1e-3 whatever amplitude it is given: a first sweep of
    # this graft at depths 0.0 -> 1.3 moved `normal_relief_p50` from 0.1246 to 0.1266, i.e.
    # the treatment was doing nothing and the height amplitude was an unusable knob.  So the
    # graft declares the thing the gate measures -- the tangent-space SLOPE at the 90th
    # percentile -- and the field is scaled to it.  ``slope`` 0.25 means "the steepest tenth
    # of this surface leans a quarter of a unit", which is a number a reader can check
    # against `normal_relief_p50` directly.
    gx = -(np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1))
    gy = np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)
    reference = float(np.percentile(np.hypot(gx, gy), 90)) or 1.0
    scale = slope / reference
    stack = np.stack([gx * scale, gy * scale, np.ones_like(gx)], -1)
    stack /= np.linalg.norm(stack, axis=-1, keepdims=True)
    detail = np.clip((stack * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)
    maps["normal"] = _blend_normal(maps["normal"], detail, 1.0)
    # the dish is a hollow: darker in the trough, in ambient occlusion and a little in colour
    hollow = np.clip(-height / max(float(np.abs(height).max()), 1e-6), 0.0, 1.0)
    maps["ao"] = np.clip(maps["ao"].astype(np.float64) * (1.0 - ao * hollow), 0, 255).astype(
        np.uint8
    )
    maps["base"] = np.clip(
        maps["base"].astype(np.float64) * (1.0 - albedo * hollow[..., None]), 0, 255
    ).astype(np.uint8)
    return maps


def _char_bands(maps: dict[str, np.ndarray], size: int, key: str) -> dict[str, np.ndarray]:
    """Charcoal crust: crazed alligator cracks over a near-black base."""

    crack = tk._fbm(size, _rng(key, "char"), base_cells=10, octaves=5)
    ridge = 1.0 - np.abs(crack - 0.5) * 2.0
    cell = np.clip((ridge - 0.62) * 6.0, 0.0, 1.0)
    glow = np.clip((crack - 0.70) * 4.0, 0.0, 1.0)
    colour = maps["base"].astype(np.float64) * 0.30
    colour += cell[..., None] * np.array([26.0, 22.0, 20.0])
    colour += glow[..., None] * np.array([46.0, 12.0, 3.0])
    maps["base"] = np.clip(colour, 0, 255).astype(np.uint8)
    maps["roughness"] = np.clip(maps["roughness"].astype(np.float64) * 0.5 + 210.0, 0, 255).astype(
        np.uint8
    )
    maps["normal"] = _blend_normal(maps["normal"], _normal_from_height(-cell * 0.35, 2.5), 1.0)
    maps["ao"] = np.clip(maps["ao"].astype(np.float64) * (1.0 - cell * 0.35), 0, 255).astype(
        np.uint8
    )
    return maps


def _emissive_globe(maps: dict[str, np.ndarray], size: int, key: str) -> dict[str, np.ndarray]:
    """A soot-streaked glass globe lit from inside: a bright, warm, near-flat albedo.

    B0 measured the emissive read: 2500 nits on a backlit VERTICAL plate with its control in
    shadow is 6.9x the control's luma at golden hour, 1.27x at noon.  The globe is that
    vertical case, so the albedo carries the colour and the material's ``emissive`` flag
    carries the light; the map itself stays a texture, not a claim.
    """

    streak = tk._value_noise(size, max(8, size // 6), _rng(key, "soot"))
    soot = np.clip((streak - 0.55) * 2.2, 0.0, 1.0)
    warm = np.stack(
        [
            np.full((size, size), 252.0),
            np.full((size, size), 222.0),
            np.full((size, size), 158.0),
        ],
        -1,
    )
    maps["base"] = np.clip(warm * (1.0 - soot[..., None] * 0.55), 0, 255).astype(np.uint8)
    maps["roughness"] = np.clip(30.0 + soot * 120.0, 0, 255).astype(np.uint8)
    maps["ao"] = np.full((size, size), 255, dtype=np.uint8)
    return maps


def cook_material(key: str, recipe: dict[str, Any], cache: Path) -> dict[str, np.ndarray]:
    size = int(recipe["size"])
    if size & (size - 1):
        raise PropTextureError(f"{key}: {size} is not a power of two and would never cook")
    asset = recipe["source"]
    maps = ft.cook_tile({"size": size, "cc0": asset}, cache)
    if recipe.get("rings"):
        rings_colour, rings_height, rings_rough = _end_grain_layer(size, key)
        maps["base"] = np.clip(
            maps["base"].astype(np.float64) * 0.35 + rings_colour.astype(np.float64) * 0.65,
            0,
            255,
        ).astype(np.uint8)
        maps["normal"] = _blend_normal(maps["normal"], _normal_from_height(rings_height, 2.2), 1.0)
        maps["roughness"] = np.clip(
            maps["roughness"].astype(np.float64) * 0.4 + rings_rough.astype(np.float64) * 0.6,
            0,
            255,
        ).astype(np.uint8)
    if recipe.get("overlay"):
        maps = _rust_overlay(maps, cache, recipe["overlay"], size, key)
    if key == "kindling_char":
        maps = _char_bands(maps, size, key)
    if recipe.get("emissive"):
        maps = _emissive_globe(maps, size, key)
    if recipe.get("text"):
        maps = _sign_face(size, maps, key)
    if recipe.get("relief"):
        maps = _hewn_relief(maps, size, key, recipe["relief"])
    if recipe.get("weather"):
        maps = _weathering(maps, size, key, recipe["weather"])
    maps["base"] = ft.apply_tint(maps["base"], recipe.get("tint", (1.0, 1.0, 1.0)))
    low, high = recipe.get("rough", (0.35, 0.9))
    maps["roughness"] = _remap_roughness(maps["roughness"], low, high)
    return maps


def cook(cache: Path, out_root: Path) -> dict[str, Any]:
    started = time.time()
    files: dict[str, dict[str, Any]] = {}
    for key, recipe in ps.MATERIALS.items():
        maps = cook_material(key, recipe, cache)
        for role in ROLES:
            relative = ps.texture_relative(key, role)
            payload = _png(maps[ROLE_MAP[role]])
            target = out_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            files[relative] = {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
                "px": int(recipe["size"]),
                "material": ps.material_name(key),
                "role": role,
            }
    return {
        "level_id": ps.LEVEL_ID,
        "seed": TEXTURE_SEED,
        "materials": len(ps.MATERIALS),
        "files": dict(sorted(files.items())),
        "seconds": round(time.time() - started, 1),
    }


def material_document() -> dict[str, Any]:
    """``art/shapes/props/<id>_props.materials.json``: one Material per B4 surface."""

    document: dict[str, Any] = {}
    for key, recipe in ps.MATERIALS.items():
        name = ps.material_name(key)
        stage: dict[str, str] = {}
        for role, field in (
            ("b", "baseColorMap"),
            ("nm", "normalMap"),
            ("r", "roughnessMap"),
            ("ao", "ambientOcclusionMap"),
            ("o", "opacityMap"),
        ):
            stage[field] = f"/levels/{ps.LEVEL_ID}/{ps.texture_relative(key, role)}"
        record: dict[str, Any] = {
            "name": name,
            "class": "Material",
            "persistentId": _persistent_id(name),
            "mapTo": name,
            "Stages": [stage, {}, {}, {}],
            # v1.5 is the PBR path and every map above is authored in a v1.5 slot.
            # B1 r4's law: declaring 1.5 on a v1.0 recipe routes the maps nowhere and the
            # surface renders wrong; the version and the slots agree here by construction.
            "version": 1.5,
            "materialTag0": "beamng",
            "materialTag1": "Natural",
            "groundType": recipe["ground"],
            "annotation": "OBJECTS",
            "translucent": False,
            "castShadows": True,
            "alphaTest": False,
            "alphaRef": 0,
            "doubleSided": False,
        }
        if recipe.get("emissive"):
            # The v1.5 emissive recipe is PER STAGE, not per material, and it needs its own
            # map bound: stock's glow_city ``powerglow_gridmap_a`` and east_coast_usa's
            # ``trafficLight`` both write {emissive, emissiveFactor, emissiveIntensityNits,
            # emissiveMap = the same file as baseColorMap, pixelSpecular} INSIDE Stages[0].
            # B4 boot 1 wrote emissive/glow/emissiveIntensity at material level with array
            # values -- the right numbers in slots nothing reads, the same class of mistake as
            # B1 r4's material-version trap -- and the lantern's globe was black at clock 0.50.
            stage["emissive"] = True
            stage["emissiveFactor"] = [1, 1, 1]
            stage["emissiveIntensityNits"] = float(recipe["emissive"])
            stage["emissiveMap"] = stage["baseColorMap"]
            stage["pixelSpecular"] = True
            # the globe must not shadow the SpotLight B2 hangs inside it
            record["castShadows"] = False
        document[name] = record
    return document


def _persistent_id(name: str) -> str:
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp/{ps.LEVEL_ID}/{name}"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    arguments = parser.parse_args(argv)
    manifest = cook(arguments.cache, arguments.out)
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"[prop-textures] {len(manifest['files'])} maps in {manifest['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
