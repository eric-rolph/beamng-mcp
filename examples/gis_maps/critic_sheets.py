"""Render the review sheets a critic looks at for one map, from the built level.

Usage (from the repository root):

    python examples/gis_maps/critic_sheets.py <map_key>

Writes ``<map>/authoring/critic/*``: an overview under the level's own sun, driver and
drone views from every spawn with every placed object drawn and the terrain's detail
textures tiled in the near field, texture swatches for every terrain, road and shape
material, the shapes rendered through their own textures, the placement map and the
road profiles. Nothing here ships; the sheets are what the critic ledger in DESIGN.md
refers to.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

PACK_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PACK_ROOT))

from maplib import heightmap as hm  # noqa: E402
from maplib import meshgen, pipeline, preview3d  # noqa: E402

DAE_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}


def load_spec(key: str):
    loader = importlib.util.spec_from_file_location(
        f"gis_maps_critic_spec_{key}", PACK_ROOT / key / "spec.py"
    )
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def _label(image, text: str):
    from PIL import ImageDraw

    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, min(image.width, 8 + 7 * len(text)), 16), fill=(0, 0, 0))
    draw.text((4, 2), text, fill=(255, 255, 255))
    return image


def load_shapes(level_root: Path, spec) -> dict[str, dict]:
    """Every shipped DAE as ``meshgen.Mesh`` lists (with UVs), its textures and extents."""

    import xml.etree.ElementTree as ET

    from PIL import Image

    shapes_dir = level_root / "art" / "shapes" / spec.MOD_ID
    if not shapes_dir.is_dir():
        return {}
    materials_file = shapes_dir / "main.materials.json"
    materials = (
        json.loads(materials_file.read_text(encoding="utf-8")) if materials_file.is_file() else {}
    )
    textures: dict[str, dict] = {}
    for name, mat in materials.items():
        stages = mat.get("Stages") or [{}]
        url = stages[0].get("baseColorMap")
        if not url:
            continue
        rel = url.split(f"/levels/{spec.MOD_ID}/", 1)[-1]
        path = level_root / rel
        if path.is_file():
            textures[name] = {"image": Image.open(path).convert("RGBA"), "colour": (0.6, 0.6, 0.6)}
    out = {}
    for p in sorted(shapes_dir.glob("*.dae")):
        tree = ET.parse(p)  # noqa: S314 - our own generated DAE
        meshes = []
        for geom in tree.getroot().findall(".//c:geometry", DAE_NS):
            name = geom.get("name", "")
            if name.startswith("Colmesh"):
                continue
            sources = geom.findall(".//c:source", DAE_NS)
            pos = np.fromstring(sources[0].find("c:float_array", DAE_NS).text, sep=" ").reshape(
                -1, 3
            )
            uv = (
                np.fromstring(sources[2].find("c:float_array", DAE_NS).text, sep=" ").reshape(-1, 2)
                if len(sources) > 2
                else np.zeros((pos.shape[0], 2))
            )
            tri_el = geom.find(".//c:triangles", DAE_NS)
            idx = np.fromstring(tri_el.find("c:p", DAE_NS).text, sep=" ", dtype=int).reshape(-1, 9)[
                :, [0, 3, 6]
            ]
            mat = (tri_el.get("material") or "").replace("-material", "")
            meshes.append(meshgen.Mesh(name, pos, np.zeros_like(pos), uv, idx, material=mat or "m"))
        if not meshes:
            continue
        allp = np.concatenate([m.positions for m in meshes])
        out[p.stem] = {
            "meshes": meshes,
            "extent": (allp.max(axis=0) - allp.min(axis=0)).tolist(),
            "textures": {m.material: textures.get(m.material, (0.6, 0.6, 0.6)) for m in meshes},
        }
    return out


def sprites_for(
    level_root: Path, spec, forest_lines: list[dict], shapes: dict[str, dict], out_dir: Path
) -> list[dict]:
    """Billboard sprites (RGBA) for every forest instance, sized by the shape's extents."""

    from PIL import Image

    mod_id = spec.MOD_ID
    tex_dir = level_root / "art" / "shapes" / mod_id / "textures"
    cache: dict[str, tuple[np.ndarray, float, float]] = {}
    out = []
    for line in forest_lines:
        item = line["type"]
        if item not in cache:
            short = item[len(mod_id) + 1 :]
            shape = shapes.get(short)
            if shape is None:
                continue
            ex, ey, ez = shape["extent"]
            if short.startswith("rock"):
                tmp = out_dir / f"sprite_{short}.png"
                preview3d.render_mesh(
                    shape["meshes"],
                    tmp,
                    size=(200, 150),
                    yaw_deg=30,
                    pitch_deg=8,
                    textures=shape["textures"],
                    transparent=True,
                )
                image = Image.open(tmp).convert("RGBA")
                image = image.crop(image.getbbox() or (0, 0, image.width, image.height))
                cache[item] = (np.asarray(image), max(ex, ey) * 1.1, ez)
            else:
                species = short.rsplit("_", 1)[0]
                card = tex_dir / f"{mod_id}_{species}_cards_b.png"
                if not card.is_file():
                    card = tex_dir / f"{mod_id}_shrub_cards_b.png"
                image = Image.open(card).convert("RGBA")
                image = image.crop(image.getbbox() or (0, 0, image.width, image.height))
                cache[item] = (np.asarray(image.resize((160, 160))), max(ex, ey), ez)
        rgba, base_w, base_h = cache[item]
        scale = float(line["scale"])
        out.append(
            {
                "x": line["pos"][0],
                "y": line["pos"][1],
                "z": line["pos"][2],
                "w": base_w * scale,
                "h": base_h * scale,
                "rgba": rgba,
            }
        )
    return out


def detail_tiles(level_root: Path, root: Path, spec) -> dict | None:
    """The terrain's own detail textures, in colour, for the near field.

    These were luminance until now, so the near ground wore the material's brightness
    over the orthophoto's colour and a material's own hue never reached the sheet: four
    near-identical beiges and four well-separated rocks looked the same. Each tile is
    divided by its own mean luminance, which keeps its colour ratio and leaves its level
    to the base, so what the near field shows is the base tinted by the material."""

    from PIL import Image

    layer_file = root / "data" / "terrain" / "layer.npy"
    if not layer_file.is_file():
        return None
    terrains = level_root / "art" / "terrains"
    tiles = []
    for name in spec.TERRAIN["materials"]:
        p = terrains / f"t_{name}_b.png"
        if not p.is_file():
            tiles.append((np.ones((2, 2, 3), dtype="float32"), 2.0))
            continue
        rgb = np.asarray(Image.open(p).convert("RGB").resize((256, 256)), dtype="float32") / 255.0
        lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        rgb = np.clip(rgb / max(float(lum.mean()), 1e-3), 0.55, 1.6)
        tiles.append((rgb, float(spec.PALETTE.get(name, {}).get("tile_m", 2.0))))
    return {"layer": np.load(layer_file), "tiles": tiles, "fade_m": 120.0}


def main(argv: list[str]) -> int:
    key = argv[0]
    spec = load_spec(key)
    root = PACK_ROOT / key
    level_root = root / "mod" / "levels" / spec.MOD_ID
    out_dir = root / "authoring" / "critic"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*"):
        stale.unlink()
    fp = pipeline.footprint_for(spec)
    res = float(spec.SITE["square_size_m"])
    dem = np.load(root / "data" / "terrain" / "dem.npy")
    handoff = json.loads(
        (root / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(encoding="utf-8")
    )
    # Placed objects and spawns are relative to the terrain origin (the lowest sample).
    dem = dem - float(handoff["terrain"]["min_elevation_m"])
    from PIL import Image, ImageDraw

    Image.MAX_IMAGE_PIXELS = None
    # The shipped base is south-up (the engine's order); the sheets are north-up.
    colour = np.asarray(
        Image.open(level_root / "art" / "terrains" / "t_base_b.png").convert("RGB")
    )[::-1]
    if colour.shape[0] != dem.shape[0]:
        colour = np.asarray(
            Image.fromarray(colour).resize((dem.shape[0], dem.shape[0]), Image.LANCZOS)
        )
    # Sun from the level's TimeOfDay: time 0.25 = 18:00, 0.75 = 06:00; approximate az/alt.
    t = float(spec.SKY["time"])
    hour = (12.0 + (t if t <= 0.5 else t - 1.0) * 24.0) % 24.0
    alt = max(8.0, 65.0 * math.cos((hour - 12.0) / 12.0 * math.pi))
    az = (180.0 + (hour - 12.0) * 15.0) % 360.0

    # 1. overview
    shade = hm.hillshade(dem, res, az, alt)
    lit = np.clip(colour.astype("float32") / 255.0 * (0.4 + 0.8 * shade[..., None]), 0, 1)
    over = Image.fromarray((lit * 255).astype("uint8")).resize((1200, 1200), Image.LANCZOS)
    _label(
        over,
        f"{spec.DISPLAY_NAME}: de-lit base colour under the level sun (az {az:.0f} alt {alt:.0f})",
    ).save(out_dir / "01_overview.jpg", quality=90)

    # 2. ground views from the spawns
    shapes = load_shapes(level_root, spec)
    forest_file = level_root / "forest" / f"{spec.MOD_ID}.forest4.json"
    lines = (
        [
            json.loads(line)
            for line in forest_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if forest_file.is_file()
        else []
    )
    sprites = sprites_for(level_root, spec, lines, shapes, out_dir)
    detail = detail_tiles(level_root, root, spec)
    for i, spawn in enumerate(handoff["spawns"]):
        x, y = spawn["level_xy"]
        heading = spawn["heading_deg"]
        near = [s for s in sprites if abs(s["x"] - x) < 700 and abs(s["y"] - y) < 700]
        for tag, eye_h, fov in (("driver", 2.2, 75.0), ("drone", 35.0, 70.0)):
            path = out_dir / f"02_view_{i}_{spawn['objectname']}_{tag}.png"
            preview3d.render_terrain_view(
                dem,
                colour,
                res,
                eye_xy=(x, y),
                heading_deg=heading,
                path=path,
                size=(1200, 600),
                eye_height=eye_h,
                fov_deg=fov,
                max_distance=1800,
                sprites=near,
                sun_azimuth_deg=az,
                sun_altitude_deg=alt,
                detail=detail if tag == "driver" else None,
            )
            img = Image.open(path)
            _label(
                img,
                f"{spawn['label']} ({tag}, {eye_h:.0f} m up) looking {heading:.0f} deg, "
                f"{len(near)} objects in range",
            ).save(path)

    # 3. texture swatches
    terrains = level_root / "art" / "terrains"
    names = list(spec.TERRAIN["materials"])
    sw = 256
    sheet = Image.new("RGB", (sw * 4, sw * len(names)), (20, 20, 20))
    for r, name in enumerate(names):
        for c, suffix in enumerate(("b", "nm", "r", "h")):
            p = terrains / f"t_{name}_{suffix}.png"
            if p.is_file():
                sheet.paste(Image.open(p).convert("RGB").resize((sw, sw)), (c * sw, r * sw))
        palette = spec.PALETTE[name]
        ImageDraw.Draw(sheet).text(
            (4, r * sw + 2),
            f"{name} ({palette['family']}, {palette.get('tile_m', 2)} m tile)",
            fill=(255, 255, 0),
        )
    sheet.save(out_dir / "03_terrain_swatches.jpg", quality=88)
    shapes_tex = level_root / "art" / "shapes" / spec.MOD_ID / "textures"
    road_tex = level_root / "art" / "road"
    extras = (
        sorted(list(shapes_tex.glob("*_b.png")) + list(road_tex.glob("*_b.png")))
        if shapes_tex.is_dir()
        else sorted(road_tex.glob("*_b.png"))
    )
    if extras:
        cols = 4
        rows = math.ceil(len(extras) / cols)
        sheet = Image.new("RGB", (sw * cols, sw * rows), (100, 140, 190))
        for i, p in enumerate(extras):
            im = Image.open(p).convert("RGBA").resize((sw, sw))
            sheet.paste(im, ((i % cols) * sw, (i // cols) * sw), im)
            ImageDraw.Draw(sheet).text(
                ((i % cols) * sw + 4, (i // cols) * sw + 2), p.stem, fill=(255, 255, 0)
            )
        sheet.save(out_dir / "04_object_and_road_swatches.jpg", quality=88)

    # 4. shape geometry, rendered through the shapes' own textures
    if shapes:
        tiles = []
        for stem, shape in list(shapes.items())[:20]:
            tmp = out_dir / f"geo_{stem}.png"
            preview3d.render_mesh(
                shape["meshes"],
                tmp,
                size=(300, 300),
                yaw_deg=30,
                pitch_deg=12,
                textures=shape["textures"],
            )
            im = Image.open(tmp)
            ex, ey, ez = shape["extent"]
            ImageDraw.Draw(im).text(
                (4, 2),
                f"{stem} {sum(m.triangle_count for m in shape['meshes'])} tris, "
                f"{ex:.1f}x{ey:.1f}x{ez:.1f} m",
                fill=(255, 255, 0),
            )
            tiles.append(im)
            tmp.unlink()
        cols = 4
        rows = math.ceil(len(tiles) / cols)
        sheet = Image.new("RGB", (300 * cols, 300 * rows))
        for i, im in enumerate(tiles):
            sheet.paste(im, ((i % cols) * 300, (i // cols) * 300))
        sheet.save(out_dir / "05_shape_geometry.jpg", quality=88)

    # 5. placement map
    if lines:
        shade2 = hm.hillshade(dem, res, 315, 45)
        img = Image.fromarray((shade2 * 255).astype("uint8")).convert("RGB").resize((1600, 1600))
        d = ImageDraw.Draw(img)
        sc = 1600 / fp.size_m
        half = fp.size_m / 2
        for line in lines:
            short = line["type"][len(spec.MOD_ID) + 1 :]
            col = (
                (255, 70, 40)
                if short.startswith("rock")
                else (40, 200, 60)
                if short.startswith("shrub")
                else (20, 110, 40)
                if short.startswith(("spruce", "fir"))
                else (150, 170, 60)
                if short.startswith(("krummholz", "willow"))
                else (220, 200, 50)
            )
            px, py = (line["pos"][0] + half) * sc, (half - line["pos"][1]) * sc
            d.point((px, py), fill=col)
        for spawn in handoff["spawns"]:
            px, py = (spawn["level_xy"][0] + half) * sc, (half - spawn["level_xy"][1]) * sc
            d.ellipse((px - 6, py - 6, px + 6, py + 6), outline=(0, 120, 255), width=3)
        _label(
            img,
            f"placed objects: {len(lines)} (red rocks, green shrubs, dark green conifers, "
            "olive krummholz, yellow aspen, blue rings spawns)",
        ).save(out_dir / "06_placement_map.jpg", quality=88)

    # 6. road profiles: the road under the default spawn first, then the longest.
    # A critic stands at the default spawn, so profiling only the longest road
    # answered for a track nobody drives from there.
    roads_file = level_root / "main" / "MissionGroup" / "roads" / "items.level.json"
    roads = [
        json.loads(line)
        for line in roads_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if roads:
        spawn = handoff["spawns"][0]
        sx, sy = spawn["level_xy"]

        def _near(road) -> float:
            xy = np.array([n[:2] for n in road["nodes"]])
            return float(np.min(np.hypot(xy[:, 0] - sx, xy[:, 1] - sy)))

        picks = [(f"under {spawn['label']}", min(roads, key=_near))]
        longest = max(roads, key=lambda r: len(r["nodes"]))
        if longest is not picks[0][1]:
            picks.append(("longest road", longest))

        W, H = 1200, 300
        img = Image.new("RGB", (W, H * len(picks)), "white")
        dr = ImageDraw.Draw(img)
        for panel, (why, road) in enumerate(picks):
            top = panel * H
            nodes = np.array([n[:3] for n in road["nodes"]])
            d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(nodes[:, :2], axis=0).T))])
            lo, hi = nodes[:, 2].min(), nodes[:, 2].max()
            pts = [
                (x / max(d[-1], 1) * W, top + H - 10 - (z - lo) / max(hi - lo, 1e-6) * (H - 30))
                for x, z in zip(d, nodes[:, 2], strict=True)
            ]
            dr.line(pts, fill=(40, 40, 220), width=2)
            # The steepest 10 m is what a car feels; the sheet quoted no number at all.
            grade = 0.0
            if d[-1] >= 10.0:
                even = np.arange(0.0, d[-1], 1.0)
                z = np.interp(even, d, nodes[:, 2])
                if z.size > 10:
                    grade = float(np.max(np.abs(z[10:] - z[:-10])) / 10.0)
            dr.text(
                (10, top + 5),
                f"{road['name']} ({road['material']}, {why}): {d[-1]:.0f} m, "
                f"{lo:.0f}-{hi:.0f} m above terrain origin, {len(nodes)} nodes, "
                f"steepest 10 m {grade * 100:.1f}%",
                fill="black",
            )
            if panel:
                dr.line([(0, top), (W, top)], fill=(200, 200, 200), width=1)
        img.save(out_dir / "07_road_profile.png")
    print(f"critic sheets written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
