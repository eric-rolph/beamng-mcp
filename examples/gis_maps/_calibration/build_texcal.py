"""A throwaway level that measures how BeamNG maps a terrain base texture.

The six GIS maps ship one orthophoto meant to cover the level exactly once, and
Meteor Crater draws it four times. The pack's reading of ``*BaseTexSize`` was
inferred from a level sampled at 1 m, where world metres and terrain squares are
the same number, so the inference was never tested. This level tests it.

512 m square at 0.5 m per sample - Meteor Crater's sampling, the case that fails.
Dead flat, so nothing but the base texture is on screen. One base map: an 8 x 8
grid of identifiable cells with a red ramp east, a green ramp north and a white
L in the south-west cell. Four terrain materials, one per quadrant, each given a
DIFFERENT ``*BaseTexSize``:

    south-west  512   the footprint in metres      (the documented reading)
    south-east  1024  the terrain's sample count   (what the pack ships now)
    north-west  256   half the footprint
    north-east  2048  double the sample count

Whichever quadrant shows the grid exactly once, at one cell per 64 m, names the
rule. The L and the ramps say whether it wraps, mirrors, or clamps, and where
texel (0, 0) lands.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PACK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PACK_ROOT))

from maplib import heightmap as hm  # noqa: E402
from maplib.level_builder import pid, write_items, write_json  # noqa: E402

MOD_ID = "ericrolph_texcal"
SIZE_PX = 1024
SQUARE_M = 0.5
FOOTPRINT_M = SIZE_PX * SQUARE_M  # 512 m
BASE_PX = 1024
CELLS = 8

# internal name -> the *BaseTexSize it is given, and the quadrant it paints
QUADRANTS = {
    "cal_sw_512": (512, "west", "south"),
    "cal_se_1024": (1024, "east", "south"),
    "cal_nw_256": (256, "west", "north"),
    "cal_ne_2048": (2048, "east", "north"),
}
MATERIALS = list(QUADRANTS)

root = Path(__file__).resolve().parent
level = root / "mod" / "levels" / MOD_ID
if level.exists():
    import shutil

    shutil.rmtree(level)
terrains = level / "art" / "terrains"
terrains.mkdir(parents=True)
level_url = f"/levels/{MOD_ID}"

# --- terrain: dead flat, painted by quadrant ------------------------------------
dem = np.zeros((SIZE_PX, SIZE_PX), dtype="float32")
layer = np.zeros((SIZE_PX, SIZE_PX), dtype="uint8")
half = SIZE_PX // 2
# rows are north-up here: row 0 = north.
for name, (_size, ew, ns) in QUADRANTS.items():
    idx = MATERIALS.index(name)
    rows = slice(0, half) if ns == "north" else slice(half, SIZE_PX)
    cols = slice(0, half) if ew == "west" else slice(half, SIZE_PX)
    layer[rows, cols] = idx
encoded = hm.encode(dem, layer)
hm.write_ter(
    level / "theTerrain.ter",
    encoded.heights_u16_south_up,
    encoded.layer_u8_south_up,
    MATERIALS,
)

# --- the base map: a grid you can read off a screenshot -------------------------
cell = BASE_PX // CELLS
img = Image.new("RGB", (BASE_PX, BASE_PX), (128, 128, 128))
draw = ImageDraw.Draw(img)
# Row 0 of this image is the SOUTH edge, like the shipped base maps, so +y in the
# image is north and the ramps below read the same way in game.
for row in range(CELLS):
    for col in range(CELLS):
        # red rises east, green rises north, blue alternates so neighbours differ.
        r = 40 + int(215 * col / (CELLS - 1))
        g = 40 + int(215 * row / (CELLS - 1))
        b = 60 if (row + col) % 2 == 0 else 190
        draw.rectangle(
            [col * cell, row * cell, (col + 1) * cell - 1, (row + 1) * cell - 1], fill=(r, g, b)
        )
for i in range(CELLS + 1):
    p = min(i * cell, BASE_PX - 3)
    draw.rectangle([p, 0, p + 2, BASE_PX], fill=(0, 0, 0))
    draw.rectangle([0, p, BASE_PX, p + 2], fill=(0, 0, 0))
# A white L in the south-west cell: the long arm points north, the foot points east.
draw.rectangle(
    [int(cell * 0.25), int(cell * 0.15), int(cell * 0.40), int(cell * 0.85)], fill=(255, 255, 255)
)
draw.rectangle(
    [int(cell * 0.25), int(cell * 0.15), int(cell * 0.80), int(cell * 0.30)], fill=(255, 255, 255)
)
# A black disc in the north-east cell, so the opposite corner is unmistakable.
draw.ellipse(
    [
        BASE_PX - int(cell * 0.75),
        BASE_PX - int(cell * 0.75),
        BASE_PX - int(cell * 0.25),
        BASE_PX - int(cell * 0.25),
    ],
    fill=(0, 0, 0),
)
# write south-up, exactly as the pack writes its shipped base maps
Image.fromarray(np.asarray(img)[::-1]).save(terrains / "t_cal_b.png", compress_level=6)

flat = {
    "nm": (128, 128, 255),
    "r": (160, 160, 160),
    "h": (128, 128, 128),
    "ao": (255, 255, 255),
}
for suffix, colour in flat.items():
    Image.new("RGB", (BASE_PX, BASE_PX), colour).save(
        terrains / f"t_cal_{suffix}.png", compress_level=9
    )
# detail and macro exist only because the material slots want a file; both are
# switched off by their strengths, so nothing but the base map is on screen.
for prefix, px in (("t_detail", 64), ("t_macro", 64)):
    for suffix, colour in (("b", (128, 128, 128)), *flat.items()):
        Image.new("RGB", (px, px), colour).save(
            terrains / f"{prefix}_{suffix}.png", compress_level=9
        )

# --- materials ------------------------------------------------------------------
texture_set = f"{MOD_ID}_TerrainTextureSet"
entries = {
    texture_set: {
        "name": texture_set,
        "class": "TerrainMaterialTextureSet",
        "persistentId": pid(MOD_ID, "texture_set"),
        "baseTexSize": [BASE_PX, BASE_PX],
        "detailTexSize": [64, 64],
        "macroTexSize": [64, 64],
    }
}
for internal, (size, _ew, _ns) in QUADRANTS.items():
    persistent = pid(MOD_ID, f"terrainmaterial:{internal}")
    entry = {
        "name": f"{internal}-{persistent}",
        "internalName": internal,
        "class": "TerrainMaterial",
        "persistentId": persistent,
        "groundmodelName": "DIRT",
        "detailDistances": [0, 0, 50, 100],
        "detailDistAtten": [1, 1],
        "macroDistances": [0, 10, 100, 3000],
        "macroDistAtten": [0, 1],
        # everything off but the base map
        "baseColorDetailStrength": [0, 0],
        "normalDetailStrength": [0, 0],
        "roughnessDetailStrength": [0, 0],
        "aoDetailStrength": [0, 0],
        "baseColorMacroStrength": [0, 0],
        "normalMacroStrength": [0, 0],
        "roughnessMacroStrength": [0, 0],
    }
    for channel, suffix in (
        ("baseColor", "b"),
        ("normal", "nm"),
        ("roughness", "r"),
        ("height", "h"),
        ("ao", "ao"),
    ):
        entry[f"{channel}BaseTex"] = f"{level_url}/art/terrains/t_cal_{suffix}.png"
        entry[f"{channel}BaseTexSize"] = size
        entry[f"{channel}DetailTex"] = f"{level_url}/art/terrains/t_detail_{suffix}.png"
        entry[f"{channel}DetailTexSize"] = 4
        entry[f"{channel}MacroTex"] = f"{level_url}/art/terrains/t_macro_{suffix}.png"
        entry[f"{channel}MacroTexSize"] = 60
    entries[entry["name"]] = entry
write_json(terrains / "main.materials.json", entries)

# --- scene tree -----------------------------------------------------------------
main = level / "main"
write_items(
    main / "items.level.json",
    [
        {
            "name": "MissionGroup",
            "class": "SimGroup",
            "enabled": "1",
            "persistentId": pid(MOD_ID, "MissionGroup"),
        }
    ],
)
write_items(
    main / "MissionGroup" / "items.level.json",
    [
        {
            "name": "Level_objects",
            "class": "SimGroup",
            "persistentId": pid(MOD_ID, "Level_objects"),
            "__parent": "MissionGroup",
        },
        {
            "name": "PlayerDropPoints",
            "class": "SimGroup",
            "persistentId": pid(MOD_ID, "drops"),
            "__parent": "MissionGroup",
        },
    ],
)
write_items(
    main / "MissionGroup" / "Level_objects" / "items.level.json",
    [
        {
            "name": "terrain",
            "class": "SimGroup",
            "persistentId": pid(MOD_ID, "terrain"),
            "__parent": "Level_objects",
        },
        {
            "name": "Sky",
            "class": "SimGroup",
            "persistentId": pid(MOD_ID, "Sky"),
            "__parent": "Level_objects",
        },
        {
            "name": "level_info",
            "class": "SimGroup",
            "persistentId": pid(MOD_ID, "level_info"),
            "__parent": "Level_objects",
        },
        {
            "name": "time",
            "class": "SimGroup",
            "persistentId": pid(MOD_ID, "time"),
            "__parent": "Level_objects",
        },
    ],
)
write_items(
    main / "MissionGroup" / "Level_objects" / "terrain" / "items.level.json",
    [
        {
            "name": "theTerrain",
            "class": "TerrainBlock",
            "persistentId": pid(MOD_ID, "theTerrain"),
            "__parent": "terrain",
            "position": [-FOOTPRINT_M / 2 + SQUARE_M / 2, -FOOTPRINT_M / 2 + SQUARE_M / 2, 0],
            "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
            "terrainFile": f"{level_url}/theTerrain.ter",
            "materialTextureSet": texture_set,
            "minimapImage": f"levels/{MOD_ID}/{MOD_ID}_minimap.png",
            "squareSize": SQUARE_M,
            "maxHeight": encoded.max_height_m,
            "baseTexSize": BASE_PX,
            "lightMapSize": 1024,
            "screenError": 16,
            "castShadows": True,
        }
    ],
)
write_items(
    main / "MissionGroup" / "Level_objects" / "Sky" / "items.level.json",
    [
        {
            "name": "sunsky",
            "class": "ScatterSky",
            "persistentId": pid(MOD_ID, "sunsky"),
            "__parent": "Sky",
            "position": [0, 0, 0],
            "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
            "scale": [1, 1, 1],
            "azimuth": 0,
            "elevation": 89.0,
            "brightness": 1.0,
            "exposure": 1.0,
            "sunSize": 1.0,
            "skyBrightness": 25.0,
            "castShadows": True,
        }
    ],
)
write_items(
    main / "MissionGroup" / "Level_objects" / "level_info" / "items.level.json",
    [
        {
            "name": "theLevelInfo",
            "class": "LevelInfo",
            "persistentId": pid(MOD_ID, "theLevelInfo"),
            "__parent": "level_info",
            "nearClip": 0.1,
            "visibleDistance": 4000,
            "fogDensity": 0.0,
            "gravity": -9.80665,
            "levelName": "Terrain texture calibration",
            "globalEnviromentMap": "DefaultSkyCubemap",
        }
    ],
)
write_items(
    main / "MissionGroup" / "Level_objects" / "time" / "items.level.json",
    [
        {
            "name": "tod",
            "class": "TimeOfDay",
            "persistentId": pid(MOD_ID, "tod"),
            "__parent": "time",
            "position": [0, 0, 0],
            "rotationMatrix": [1, 0, 0, 0, 1, 0, 0, 0, 1],
            "scale": [1, 1, 1],
            "axisTilt": 23.44,
            "dayLength": 1800,
            "startTime": 0.5,
            "time": 0.5,
            "play": False,
            "latitude": 0.0,
            "longitude": 0.0,
            "year": 2026,
            "month": 6,
            "day": 20,
            "utcOffset": "0",
            "celestialProfile": "earth",
        }
    ],
)
# One spawn at the middle of the level, facing north.
write_items(
    main / "MissionGroup" / "PlayerDropPoints" / "items.level.json",
    [
        {
            "name": "spawn_centre",
            "class": "SpawnSphere",
            "persistentId": pid(MOD_ID, "spawn_centre"),
            "__parent": "PlayerDropPoints",
            "position": [0.0, 0.0, 1.0],
            "rotationMatrix": [-1.0, 0.0, 0.0, -0.0, -1.0, 0.0, 0.0, 0.0, 1.0],
            "scale": [1, 1, 1],
            "dataBlock": "SpawnSphereMarker",
            "radius": 5,
            "autoplaceOnSpawn": "0",
            "homingCount": "0",
            "indoorWeight": "1",
            "outdoorWeight": "1",
            "lockCount": "0",
            "sphereWeight": "1",
        }
    ],
)

# --- previews and info ----------------------------------------------------------
preview = Image.fromarray(np.asarray(img.resize((512, 512), Image.NEAREST)))
preview.save(level / f"{MOD_ID}_preview.jpg", quality=88)
preview.save(level / "spawn_centre.jpg", quality=88)
img.resize((512, 512), Image.NEAREST).save(level / f"{MOD_ID}_minimap.png", compress_level=6)
write_json(
    level / "info.json",
    {
        "title": "Terrain texture calibration",
        "authors": "ericrolph",
        "description": (
            "A 512 m square at 0.5 m per terrain sample, dead flat, painted with one 8 x 8 "
            "grid base map. Each quadrant gives that map a different *BaseTexSize: 512 in the "
            "south-west, 1024 in the south-east, 256 in the north-west, 2048 in the north-east. "
            "The quadrant that shows the grid exactly once, at one cell per 64 m, names the rule. "
            "Not a playable level - delete it when the answer is in."
        ),
        "previews": [f"{MOD_ID}_preview.jpg"],
        "size": [int(FOOTPRINT_M), int(FOOTPRINT_M)],
        "defaultSpawnPointName": "spawn_centre",
        "spawnPoints": [
            {
                "translationId": "Centre",
                "description": "Centre of the level",
                "objectname": "spawn_centre",
                "preview": "spawn_centre.jpg",
            }
        ],
    },
)
print(f"level written: {level}")
print(f"  terrain {SIZE_PX} samples at {SQUARE_M} m = {FOOTPRINT_M:.0f} m, flat")
print(
    f"  base map {BASE_PX} px, {CELLS}x{CELLS} cells = {FOOTPRINT_M / CELLS:.0f} m per cell "
    f"if it covers the level once"
)
for _internal, (size, ew, ns) in QUADRANTS.items():
    print(f"  {ns}-{ew}: BaseTexSize {size}")
