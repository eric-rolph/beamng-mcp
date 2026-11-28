"""Deterministic generator for every scene file of the Giant's Hearth level.

Round B1 (terrain, materials, water, roads, backdrop, sky records). Outputs live
under ``examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena/``:

- ``info.json`` (design v4 §11), ``main/items.level.json`` and the MissionGroup
  JSONL groups (template nesting plus ``level_objects/{backdrop, decal_road}``),
- the ``.ter`` v9 terrain + ``.terrain.json`` sidecar + ``.ter.depth.png``
  (``terrain_io``, whose height and paint law is the vendored design model),
- ``art/terrains/main.materials.json``: the TerrainMaterialTextureSet and the
  ELEVEN TerrainMaterials of design §2.4 in the johnson_valley recipe's field
  set, every one of the 15 ``<chan><Layer>Tex`` slots filled and sized,
- ``groundModels/<id>_groundmodels.json``: the four level-scoped ERHP_* models
  (B0's field set MINUS ``isAlias``, which logs an E line per model),
- ``art/decalroad/main.materials.json``: the eleven road materials (ten visible
  layers of the §2.3.1 stack + our own ``…_road_invisible``),
- the 112 DecalRoads of §2.3 (5 invisible + 28 track + 39 trail + 40 hearth skid
  arcs) built on the PINNED node lists in
  ``authoring/<id>.level_layout.json`` ``decal_roads``,
- the WaterPlane of §5.2, the backdrop ring TSStatic of §2.6, the TimeOfDay /
  ScatterSky / LevelInfo / CloudLayer records of §5.1 in B0's measured form,
  four SpawnSpheres, eleven CameraBookmarks (§8), minimap and two previews,
- ``scenarios/<id>_probe/`` (the pipeline probe scenario the live gate boots).

The COOKED terrain / road / backdrop textures are not rendered here: they are
``cook_terrain_textures.py``'s outputs, carried into the archive through its
manifest, because cooking 165 PNGs from 314 MB of CC0 source takes ~55 s and
must not run inside every test.

Every object/material/datablock name and file basename the engine does not
mandate carries ``ericrolph_hot_potato_arena_``. Names the engine looks up by
convention stay stock: ``MissionGroup`` and the template group names,
``theTerrain``, ``theForest``, ``tod``, ``sunsky``, ``theLevelInfo``, ``clouds``.
The ELEVEN terrain-material ``internalName``s are the design's bare layer names
(``hearth`` … ``alpine``): the ``.ter`` layer table, every ``GroundCover.layer``
B3 authors and the live readback all key off that exact list, and TerrainMaterial
SimObjects are unnamed in-engine (report_B surprise 6), so they never enter the
global name space. persistentIds are uuid5 of the object name; every text output
is strict JSON with LF newlines and sorted keys.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from examples.hot_potato_arena.level import blender_backdrop as backdrop
from examples.hot_potato_arena.level import cook_terrain_textures as cook
from examples.hot_potato_arena.level import forest_build, props_build, shelf_road
from examples.hot_potato_arena.level import terrain_io as terrain
from examples.hot_potato_arena.sync_scenario_outputs import engine_yaw_matrix

LEVEL_ID = terrain.LEVEL_ID
CENTER = terrain.CENTER
EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
MOD_ROOT = EXAMPLE_ROOT / "mod"
LEVEL_RELATIVE = f"levels/{LEVEL_ID}"
LEVEL_ROOT = MOD_ROOT / "levels" / LEVEL_ID
LAYOUT_PATH = EXAMPLE_ROOT / "authoring" / f"{LEVEL_ID}.level_layout.json"
DESIGN_LOCK_PATH = EXAMPLE_ROOT / "authoring" / "level_design_v4.lock.json"
BACKDROP_DIR = "art/shapes/hot_potato_arena_backdrop"
TERRAIN_STEM = f"{LEVEL_ID}_terrain"
TER_PATH = f"/{LEVEL_RELATIVE}/{TERRAIN_STEM}.ter"
TEXTURE_SET = f"{LEVEL_ID}_terrain_texture_set"
PROBE_ID = f"{LEVEL_ID}_probe"
PROBE_PLAYER = f"{PROBE_ID}_player"
PROBE_GROUP = f"{PROBE_ID}_group"
SPAWN_SOUTH = f"{LEVEL_ID}_spawn_south"
SPAWN_BEARING, SPAWN_R = 180.0, 40.0
SPAWN_Z_LIFT = 0.6
IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
ROAD_INVISIBLE = f"{LEVEL_ID}_road_invisible"

# --- sky / atmosphere (design v4 §5.1, B0's measured record) ----------------------
TOD_CLOCK = 0.30  # golden hour: sun 9.77 deg at azimuth 294.0 (B0 ephemeris)
TOD_NIGHT_CLOCK = 0.50  # the night round's clock (sun -19.74 deg)
SKY_GRADIENTS = "art/sky_gradients/default"
FOG_COLOR = [0.80, 0.70, 0.56, 1.0]
#: r6 (critic r5 N5-2, the player defect). Our day frames measure flatter than a stock
#: in-engine screenshot, and `b1/r6/probe/ground_shading.py` - the ground's analogue of
#: `backdrop_atlas.py`, which rebuilds what the terrain shader puts on screen at our own
#: camera, sun and fog and scores it with the frame instrument's own sigma_local8 - says
#: where. The macro strengths and the macro's own contrast are NOT where it is short:
#: at 250-900 m the 80 m macro tile is mipped to a few pixels, so `normalMacroStrength`
#: far 0.30 -> 0.60 buys +2.4 % and even trebling `MACRO_TARGET_SPREAD` buys +4.2 %.
#: The engine's own distance fog is: 0.00045 -> 0.00030 buys **+3.8 % at 250 m, +7.8 %
#: at 500 m and +14.4 % at 900 m**, and it is the one term that runs the full depth of
#: every frame. 0.00030 is the MEDIAN of the twenty stock `LevelInfo` records, and four
#: of the five design reference levels sit at or below it (east_coast_usa 0.0002, italy
#: 0.0002, small_island 0.000166, west_coast_usa 0.00035; johnson_valley's 0.0015 comes
#: with a 75.99 m atmosphere height, i.e. a shallow ground haze, not ours). At 1,200 m
#: the ring's transmittance goes 0.58 -> 0.70, so the "hazy sunlit playa" reading holds
#: and the backdrop is helped rather than hurt.
FOG_DENSITY = 0.00030
#: r5 (critic r4 B4-4, second half). The blank skyline had TWO causes and the atlas was
#: only one of them: the ring stands 1,180-1,382 m out, so the engine's own fog runs the
#: whole way to it, and a 220 m atmosphere height puts a ridge line whose summits are at
#: z 380-620 well inside the haze layer. Measured over the 20 stock ``LevelInfo``
#: records (``b1/r5/probe/stock_fog_band.py``): the band is 75.99-1600 m, median 261.8,
#: and EVERY stock level whose subject is a distant ridge line sits at the bottom of it
#: - johnson_valley (a desert basin ringed by ranges, the closest analogue there is)
#: **75.99**, small_island 97.23, east_coast_usa 182.17, west_coast_usa 192.79. 150 m
#: keeps the whole play area hazy - the basin floor is z 98-106 and its crest 143, so
#: every drivable metre is still inside the layer and the "hazy sunlit playa" reading is
#: unchanged - while the ridge summits stand 2.5-4x above it. Density is untouched
#: (0.00045, inside the stock band 0.00005-0.0015).
FOG_ATMOSPHERE_HEIGHT = 150.0
VISIBLE_DISTANCE = 12000.0
GRAVITY = -9.81
GLOBAL_CUBEMAP = "BNG_Sky_02_cubemap"  # B6 replaces this with the level's own capture
NIGHT_START = "0.29"
NIGHT_END = "0.79"

# --- water (design §5.2) -----------------------------------------------------------
WATER_NAME = f"{LEVEL_ID}_water"
WATER_Z = terrain.LAKE_LEVEL  # 98.0

# --- backdrop (design §2.6) ---------------------------------------------------------
BACKDROP_NAME = f"{LEVEL_ID}_backdrop_ring"

# --- hearth skid arcs (design §2.3.1, 40 arcs r 118-170 on the flat slab) -----------
SKID_ARC_COUNT = 40
SKID_ARC_SEED = 0x534B4944  # "SKID"
#: B4 A/B lever: put the improved spline BACK on the two dirt-surface families for a
#: diagnostic cut.  The shipped default draws them linear -- see visible_road_records.
SPLINE_SURFACE_ENV = "HOT_POTATO_B4_SPLINE_SURFACE"
SKID_R_MIN, SKID_R_MAX = 118.0, 170.0

#: Terrain material shared fields (design §2.4; JV recipe §7.1 field set).
#:
#: r3 (critic r2 B-4). The engine's terrain shader
#: (``shaders/common/terrain/terrain.h.hlsl``) composites
#: ``base + (macro*2-1)*macroFactor + (detail*2-1)*detailFactor``, and
#: ``blendDetailMacro`` + ``calculateStrenth`` saturate the middle factor at
#: ``distances[2]``, so past that distance the band is applied at exactly
#: ``strength[1]``. r2 read that correctly and answered it by taking every far strength
#: to ZERO - which, with ``detailDistances [0,0,50,80]`` and
#: ``macroDistances [0,10,200,3000]``, means **no detail albedo past 50 m and no macro
#: past 200 m**: the surface between the near field and the wall was the base set
#: alone. That is the smooth streaked mid-ground the critic found in eight of nine day
#: frames, and r2's report mis-attributed it to "raw terrain with nothing on it yet".
#:
#: r3 keeps the far field free of the macro's authored tile by DE-TILING the macro
#: itself (``cook_terrain_textures.MACRO_FLATTEN``, measured in
#: ``r3/probe/macro_lattice.json``) instead of by emptying it, and pushes the detail
#: out to where stock levels put it. Reference band, measured over the terrain
#: materials of eight stock levels (west_coast_usa, italy, johnson_valley,
#: east_coast_usa, small_island, utah, jungle_rock_island, derby):
#:
#:   detailDistances   [0,0,15,30] ... [0,0,100,200]   (small_island uses [0,0,100,200])
#:   macroDistances    [0,0,100,3000] ... [0,100,1000,9000]
#:   far MACRO strengths are usually NON-ZERO and often LARGER than near
#:                                             (roughnessMacro [0.15, 0.8] is stock)
#:
#: **r4 (critic r3 B3-3): the far DETAIL claim was wrong and is withdrawn.** r3 wrote
#: "far detail strengths are USUALLY 0" and kept all three at zero. Re-derived over
#: the same 104 stock materials (``r4/probe/stock_detail_band.json``), far detail is
#: non-zero on **51.9 %** (baseColorDetail), **51.9 %** (normalDetail) and **76.2 %**
#: (roughnessDetail) - so stock does the opposite more often than not, and the one
#: thing still emptying the surface past 100 m was justified by a false premise.
#:
#: r4 restores it at values that are not merely inside the band but shipped VERBATIM by
#: a stock material on OUR OWN ``detailDistances [0, 0, 100, 200]``:
#:
#:   small_island ``dirt_loose``        detailDistances [0,0,100,200]  baseColorDetail [0.35, 0.35]
#:   small_island ``Rock``              detailDistances [0,0,100,200]  roughnessDetail [0.3, 0.3]
#:   small_island ``dirt_rocky_large``  detailDistances [0,0,100,200]  roughnessDetail [0.3, 0.3]
#:
#: and normalDetail far at the stock non-zero MEDIAN, 0.15. With near == far on two of
#: the three, ``detailDistances`` stops gating them at all and the detail albedo is
#: applied at one strength everywhere - which is what "the far field is textured" has
#: to mean. What is measured, rather than asserted: ``r4/probe/farfield.json``.
#: QB-4 gates the far DETAIL strength at p90 <= 0.5 and ``macroDistances[3] >= 400``;
#: both still pass.
DETAIL_DISTANCES = [0, 0, 100, 200]
MACRO_DISTANCES = [0, 10, 200, 3000]
STRENGTHS = {
    "baseColorDetailStrength": [0.35, 0.35],
    "normalDetailStrength": [0.8, 0.15],
    "roughnessDetailStrength": [0.3, 0.3],
    "baseColorMacroStrength": [0.16, 0.20],
    # r6: 0.30 was the stock 25th percentile over 185 stock terrain materials (median
    # 0.50, p75 0.60, max 1.20) and the normal is the term a 9.77 deg sun reads hardest.
    # `b1/r6/probe/ground_shading.py` prices it honestly: +1.8 % of far-field
    # sigma_local8 at 900 m, +1.4 % at 500 m - the macro tile is mipped to a few pixels
    # out there, so this is a small term and is shipped as one. The far MACRO strength
    # is now the stock median rather than its lower quartile.
    "normalMacroStrength": [0.55, 0.50],
    "roughnessMacroStrength": [0.20, 0.45],
}
CHANNELS = ("b", "nm", "r", "ao", "h")
CHANNEL_FIELD = {"b": "baseColor", "nm": "normal", "r": "roughness", "ao": "ao", "h": "height"}
LAYER_ANNOTATION = {
    "hearth": "ASPHALT",
    "ash": "DIRT",
    "scorch": "DIRT",
    "trail": "DIRT",
    "meadow": "GRASS",
    "forest_floor": "GRASS",
    "scree": "GRAVEL",
    "rock": "ROCK",
    "shore": "SAND",
    "lakebed": "MUD",
    "alpine": "GRASS",
}

#: The four LEVEL-scoped ground models (design §2.4). B0 measured that the design's
#: original field set logs one E line per model for ``isAlias``; it is dropped.
LEVEL_GROUNDMODELS: dict[str, dict[str, Any]] = {
    "ERHP_ASH": {
        "staticFrictionCoefficient": 0.66,
        "slidingFrictionCoefficient": 0.66,
        "hydrodynamicFriction": 0,
        "stribeckVelocity": 4,
        "strength": 1,
        "roughnessCoefficient": 0.45,
        "collisiontype": "DIRT_DUSTY",
    },
    "ERHP_SCORCH": {
        "staticFrictionCoefficient": 0.68,
        "slidingFrictionCoefficient": 0.70,
        "hydrodynamicFriction": 0,
        "stribeckVelocity": 4,
        "strength": 1,
        "roughnessCoefficient": 0.42,
        "collisiontype": "DIRT_DUSTY",
    },
    "ERHP_TRAIL": {
        "staticFrictionCoefficient": 0.72,
        "slidingFrictionCoefficient": 0.74,
        "hydrodynamicFriction": 0,
        "stribeckVelocity": 4,
        "strength": 1,
        "roughnessCoefficient": 0.40,
        "collisiontype": "DIRT",
    },
    "ERHP_FOREST_FLOOR": {
        "staticFrictionCoefficient": 0.60,
        "slidingFrictionCoefficient": 0.63,
        "hydrodynamicFriction": 0,
        "stribeckVelocity": 4,
        "strength": 1,
        "roughnessCoefficient": 0.45,
        "collisiontype": "GRASS",
    },
}

#: The eight-layer dirt-road decal stack (design §2.3.1): material -> the record
#: fields every DecalRoad of that layer carries.
ROAD_LAYERS: dict[str, dict[str, Any]] = {
    "m_dirt_variation": {
        # r2/B4: 32, not the design table's 128.  128 on the 8 m track and the 6 m trail is a
        # 16:1 and a 21:1 stretch of a 2048 square, which is what the r1 critic saw smeared
        # along both trail frames.  Census of every visible DecalRoad in the 14 stock level
        # archives that carries nodes (b4/census_stock_texturelength.py, 39,251 records):
        # SURFACE-class roads run textureLength/width p05 2.0, MEDIAN 4.0, p95 15.0, and only
        # 227 of 10,905 exceed 16:1.  The 64-300 m figures the design took this from were
        # measured on variation OVERLAYS, whose stock median ratio really is 16:1.  32 puts
        # the track at 4.0:1 and the trail at 5.3:1 -- the stock surface median.
        "textureLength": 32,
        "startEndFade": [20, 20],
        "distanceFade": [250, 50],
        # r3: A LOWER renderPriority DRAWS ON TOP.  Study A r2 and r3 both left the ordering
        # semantics open; BeamNG's own authoring code settles it three ways:
        #   roadArchitect/decals.lua L95/L111: the base drivable road takes
        #     `#road.profile.layers + 3` and every overlay layer takes `i` (1..#layers) --
        #     the road is the HIGHEST number and the overlays painted on it are lower;
        #   procTrack.lua L878-882: `tread_marks_clean` 4, `road_orange_markings` 3 -- the
        #     painted markings, which must sit on the tread, take the LOWER number;
        #   client/postFx/turbulence.lua: `renderPriority = 0.5; --Render after the glows`
        #     against glow's 1, the same convention one system over.
        # So r2's stack was upside down.  With the surface at 8 the three families ABOVE it
        # -- mud cracks 9, puddles 10, needle litter 25 -- were painted and then buried, and
        # the pale `m_track_dust_overlay` at 4 (albedo luma 180.0, saturation 0.079, a 35 %
        # flat wash) was drawn OVER the road down the whole trail.  That is precisely what
        # critic pass 2 measured: luma 132.5 -> 161.1, saturation 0.262 -> 0.148, "a pale
        # limestone haul road rather than dirt".  Every other family in the stack is DARKER
        # than the surface, so simply putting them the right way up darkens and enriches it.
        # The direction is re-measured live in r3 anyway (report_B4 section 4.4's A/B).
        "renderPriority": 20,
    },
    "m_dirt_flows": {
        "textureLength": 8,
        "startEndFade": [5, 5],
        "distanceFade": [150, 50],
        "renderPriority": 14,
    },
    "m_dirt_gravel": {
        "textureLength": 12,
        "startEndFade": [5, 5],
        "distanceFade": [150, 50],
        "renderPriority": 10,
    },
    "m_dirt_tiretracks": {
        "textureLength": 16,
        "startEndFade": [20, 20],
        "distanceFade": [150, 50],
        # the ruts are the NEWEST wear on a dirt road, so they take a LOWER number than the
        # surface, the dust, the flows, the erosion, the gravel, the cracks and the water
        "renderPriority": 4,
    },
    "m_bank_erosion": {
        "textureLength": 16,
        "startEndFade": [5, 5],
        "distanceFade": [150, 50],
        "renderPriority": 12,
    },
    "m_mud_cracks": {
        "textureLength": 6,
        "startEndFade": [3, 3],
        "distanceFade": [120, 40],
        "renderPriority": 8,
    },
    "m_puddle_wet": {
        "textureLength": 5,
        "startEndFade": [2, 2],
        "distanceFade": [120, 40],
        "renderPriority": 6,
    },
    "m_track_dust_overlay": {
        "textureLength": 48,
        "startEndFade": [30, 30],
        "distanceFade": [200, 50],
        "renderPriority": 16,
    },
    "m_skid_arc": {
        "textureLength": 20,
        "startEndFade": [30, 30],
        "distanceFade": [150, 50],
        "renderPriority": 3,
    },
    "m_needle_litter": {
        "textureLength": 4,
        "startEndFade": [0.2, 0.2],
        "distanceFade": [80, 40],
        "renderPriority": 1,
    },
}
#: r3: the width of the ONE centred rut record per road.  The ruts mask paints its pair at
#: u 0.28 / 0.72, so a 3.6 m record lands them at +-0.79 m -- a car's own track width.
RUT_WIDTH_M = 3.6
#: r3: node spacing for the full-length overlays (ruts, verges, dust).  At 20-25 m a record
#: following the trail's R 40 corners chords them by 1.24 m and the "rut" leaves the road
#: where a player is most likely to be looking at it; 6 m puts the chord at 0.11 m.
OVERLAY_STEP_M = 6.0
ROAD_GROUND_TYPE = {
    "m_dirt_variation": "DIRT",
    "m_dirt_flows": "DIRT",
    "m_dirt_gravel": "GRAVEL",
    "m_dirt_tiretracks": "DIRT",
    "m_bank_erosion": "DIRT",
    "m_mud_cracks": "DIRT",
    "m_puddle_wet": "DIRT",
    "m_track_dust_overlay": "DIRT",
    "m_skid_arc": "ASPHALT",
    "m_needle_litter": "GRASS",
}


class LevelWriteError(RuntimeError):
    """The generated level would violate the package contract."""


def persistent_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:{LEVEL_ID}:level:{name}"))


def _r6(value: float) -> float:
    rounded = round(float(value), 6)
    return 0.0 if rounded == 0 else rounded


def _r3(value: float) -> float:
    rounded = round(float(value), 3)
    return 0.0 if rounded == 0 else rounded


def _json(value: Any) -> bytes:
    text = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if "NaN" in text or "Infinity" in text:
        raise LevelWriteError("non-finite number in generated JSON")
    return text.encode("utf-8")


def _jsonl(records: list[dict[str, Any]]) -> bytes:
    lines = []
    for record in records:
        line = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if "NaN" in line or "Infinity" in line:
            raise LevelWriteError("non-finite number in generated JSONL")
        lines.append(line + "\n")
    return "".join(lines).encode("utf-8")


# --- the frozen design layout -------------------------------------------------------


_LAYOUT: dict[str, Any] | None = None


def layout() -> dict[str, Any]:
    """The design's ``layout.json``, vendored byte-for-byte into ``authoring/``."""

    global _LAYOUT
    if _LAYOUT is None:
        _LAYOUT = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    return _LAYOUT


def spawn_xy() -> tuple[float, float]:
    x, y = terrain.bearing_point(SPAWN_BEARING, SPAWN_R)
    return _r6(x), _r6(y)


def spawn_position() -> list[float]:
    x, y = spawn_xy()
    return [x, y, _r6(CENTER[2] + SPAWN_Z_LIFT)]


# --- terrain materials ----------------------------------------------------------------


def material_object_name(layer: str) -> str:
    return f"{LEVEL_ID}_t_{layer}"


def terrain_materials_document() -> dict[str, Any]:
    document: dict[str, Any] = {
        TEXTURE_SET: {
            "name": TEXTURE_SET,
            "class": "TerrainMaterialTextureSet",
            "persistentId": persistent_id(f"texture_set:{TEXTURE_SET}"),
            "baseTexSize": [cook.BASE_PX, cook.BASE_PX],
            "detailTexSize": [cook.DETAIL_PX, cook.DETAIL_PX],
            "macroTexSize": [cook.MACRO_PX, cook.MACRO_PX],
        }
    }
    extent = float(terrain.DEFAULT_SPEC.extent_m)
    for layer in terrain.MATERIALS:
        name = material_object_name(layer)
        entry: dict[str, Any] = {
            "name": name,
            "internalName": layer,
            "class": "TerrainMaterial",
            "persistentId": persistent_id(f"terrain_material:{layer}"),
            "annotation": LAYER_ANNOTATION[layer],
            "groundmodelName": terrain.LAYER_GROUNDMODEL[layer],
            "detailDistances": list(DETAIL_DISTANCES),
            "macroDistances": list(MACRO_DISTANCES),
        }
        for channel in CHANNELS:
            field = CHANNEL_FIELD[channel]
            entry[f"{field}BaseTex"] = f"/{LEVEL_RELATIVE}/{cook.base_texture_relative(channel)}"
            # squareSize is exactly 1.0, so the extent in metres and the sample
            # count are the same number and study §5.4's unit question never arises.
            entry[f"{field}BaseTexSize"] = extent
            entry[f"{field}DetailTex"] = (
                f"/{LEVEL_RELATIVE}/{cook.terrain_texture_relative(layer, 'detail', channel)}"
            )
            entry[f"{field}DetailTexSize"] = float(cook.DETAIL_SOURCES[layer].tile_m)
            entry[f"{field}MacroTex"] = (
                f"/{LEVEL_RELATIVE}/{cook.terrain_texture_relative(layer, 'macro', channel)}"
            )
            entry[f"{field}MacroTexSize"] = float(cook.MACRO_SOURCES[layer].tile_m)
        entry.update({k: list(v) for k, v in STRENGTHS.items()})
        document[name] = entry
    return document


def groundmodels_document() -> dict[str, Any]:
    """Level-scoped ground models, loaded from ``levels/<id>/groundModels/*.json``.

    Proven live (report_B P2d/P2e): this file's coefficients are what the tires
    use, and ``collisiontype`` must name an engine-known particles material or the
    vehicle VM reports ``none``. B0 measured the decelerations these four produce:
    ASH 6.013, SCORCH 6.306, TRAIL 6.752, FOREST_FLOOR 5.572 m/s^2.
    """

    return {name: dict(fields) for name, fields in LEVEL_GROUNDMODELS.items()}


# --- road materials --------------------------------------------------------------------


def road_material_name(key: str) -> str:
    return f"{LEVEL_ID}_{key}"


def road_materials_document() -> dict[str, Any]:
    root = f"/{LEVEL_RELATIVE}/{cook.ROAD_DIR}"
    document: dict[str, Any] = {}
    for key in cook.ROAD_SOURCES:
        name = road_material_name(key)
        stage: dict[str, Any] = {
            "baseColorMap": f"{root}/{LEVEL_ID}_t_{key}_b.png",
            "normalMap": f"{root}/{LEVEL_ID}_t_{key}_nm.png",
            "roughnessMap": f"{root}/{LEVEL_ID}_t_{key}_r.png",
            "ambientOcclusionMap": f"{root}/{LEVEL_ID}_t_{key}_ao.png",
            "opacityMap": f"{root}/{LEVEL_ID}_t_{key}_o.png",
            "roughnessFactor": 1.0,
            "metallicFactor": 0.0,
        }
        document[name] = {
            "name": name,
            "mapTo": name,
            "class": "Material",
            "persistentId": persistent_id(f"material:{name}"),
            "Stages": [stage, {}, {}, {}],
            "alphaRef": 0,
            "annotation": "STREET",
            "castShadows": False,
            "groundType": ROAD_GROUND_TYPE[key],
            "materialTag0": "RoadAndPath",
            "materialTag1": LEVEL_ID,
            "translucent": True,
            "translucentZWrite": True,
            "version": 1.5,
        }
    # r4 (critic r3 B3-1). THIS MATERIAL WAS NOT INVISIBLE. `ai_connector_150` runs
    # from the AI ring (r 170) straight out along bearing 150 - which is exactly the
    # S2 camera's own bearing from C - and it drew the hard-edged dithered trapezoid
    # that has been in every S2 frame since r1 (`r4/probe/road_project.json`: it is
    # the ONLY DecalRoad with any geometry in the artefact window, its screen centre
    # is x 960.0 against the artefact's measured 960, and its far node at 92 m matches
    # the artefact's measured top edge at 90 m).
    #
    # The cause is the `version` key. Stock's own `road_invisible` (west_coast_usa
    # `art/road/main.materials.json`) carries NO version, i.e. it is a v1.0 material,
    # and on that path `colorMap` IS the albedo slot: a fully transparent map with
    # `alphaTest` + `alphaRef 127` discards every fragment. r1..r3 copied the stock
    # recipe's Stages verbatim and then added `"version": 1.5`, which routes the
    # material through the PBR path where the albedo slot is `baseColorMap` - so no
    # texture was bound at all, the material fell back to its default opaque base
    # colour, and the road rendered wherever the DecalRoad's own distance fade let it.
    # r4 ships the stock recipe EXACTLY: no version key, so `colorMap` is read.
    document[ROAD_INVISIBLE] = {
        "name": ROAD_INVISIBLE,
        "mapTo": ROAD_INVISIBLE,
        "class": "Material",
        "persistentId": persistent_id(f"material:{ROAD_INVISIBLE}"),
        # The stock recipe (study §7.5) with our own fully transparent 16x16 map, so
        # the AI ring never depends on another level's dds.
        "Stages": [
            {
                "colorMap": f"{root}/{LEVEL_ID}_t_road_invisible.color.png",
                "specularPower": 1,
                "useAnisotropic": True,
            },
            {},
            {},
            {},
        ],
        "alphaRef": 127,
        "alphaTest": True,
        "annotation": "STREET",
        "castShadows": False,
        "materialTag0": "RoadAndPath",
        "materialTag1": LEVEL_ID,
        "specularStrength0": "0",
    }
    return document


#: 16 is the engine's floor: boot 1 logged
#: "skip cooking, texture is smaller than 16x16 or not power of 2 ... 4x4" (E line).
ROAD_INVISIBLE_PX = 16


def road_invisible_png() -> bytes:
    """A fully transparent RGBA map for our own ``road_invisible``."""

    return cook.png_bytes(
        np.zeros((ROAD_INVISIBLE_PX, ROAD_INVISIBLE_PX, 4), dtype=np.uint8), "RGBA"
    )


# --- backdrop material -------------------------------------------------------------------


def backdrop_detail_scale() -> list[float]:
    """r13: the ``detailScale`` pair, DERIVED from the mesh's own UV metric.

    ``blender_backdrop`` maps ``u = column / COLUMN_SEGMENTS``, so one u unit spans the
    whole circumference; and ``v = (band + |z - Z_BASE| / (Z_TOP - Z_BASE)) / STRIP_BANDS``,
    so one v unit spans ``STRIP_BANDS`` times the z range. The two are therefore anisotropic
    by a factor of about five, and a single scalar ``detailScale`` would smear the rock into
    horizontal bands - which is N12-5's own complaint (*"the apron combed into radial
    streaks"*) arriving a second time from the other direction.

    The circumference is the NEAR ring's: the three rings share one material, and the near
    one is the ring a player can walk up to. The far ring's detail therefore reads about
    17 % larger, which is 1,382 / 1,180 and is invisible at 1.4 km.
    """

    near = backdrop.RINGS[0]
    circumference = 2.0 * math.pi * near.radius_m
    z_span = (backdrop.Z_TOP - backdrop.Z_BASE) * backdrop.STRIP_BANDS
    tile = cook.BACKDROP_DETAIL_TILE_M
    return [round(circumference / tile, 3), round(z_span / tile, 3)]


def backdrop_materials_document() -> dict[str, Any]:
    root = f"/{LEVEL_RELATIVE}/{BACKDROP_DIR}"
    name = backdrop.BACKDROP_MATERIAL
    detail = f"/{LEVEL_RELATIVE}/{cook.backdrop_detail_texture_relative('b')}"
    detail_nm = f"/{LEVEL_RELATIVE}/{cook.backdrop_detail_texture_relative('nm')}"
    return {
        name: {
            "name": name,
            "mapTo": name,
            "class": "Material",
            "persistentId": persistent_id(f"material:{name}"),
            "Stages": [
                {
                    "baseColorMap": f"{root}/{name}.color.png",
                    "normalMap": f"{root}/{name}.normal.png",
                    "roughnessMap": f"{root}/{name}_roughness.data.png",
                    "roughnessFactor": 1.0,
                    "metallicFactor": 0.0,
                    # --- r13: the near-field detail graft (critic r12, "the foot") -----
                    # The atlas is 0.905 m per texel on the near ring. At 10 m that is a
                    # beige blur and no atlas can fix it; these maps are the level's own
                    # rock tiled over the base at 0.715 cm per texel, 127x finer.
                    # The keys are the engine's own: 186 stock materials in west_coast_usa
                    # carry detailScale, 31 detailNormalMap, 30 detailMap.
                    # r15 (critic r14 B14-1): the AUTHORED TILE is now 29.28 m rather than
                    # 7.32, because one tile is a 4x4 grid of hash-offset, hash-flipped
                    # reads of the same scan. detailScale is derived from that number, so
                    # this pair moves 1012.863 / 209.016 -> 253.216 / 52.254 with no edit
                    # here: the material follows the cook, which is why the derivation
                    # lives in backdrop_detail_scale() and not in a literal.
                    "detailMap": detail,
                    "detailNormalMap": detail_nm,
                    "detailScale": backdrop_detail_scale(),
                    "detailBaseColorMapStrength": 0.55,
                    "detailNormalMapStrength": 1.35,
                    # NO ``roughnessDetailMap``, and the reason is measured. The graft's
                    # roughness map is centred on **0.8615** and the atlas's roughness at
                    # the foot is a near-constant **0.85**; under an overlay blend
                    # (``2d - 1``) the composite saturates to a clipped, flat **1.0**, so a
                    # roughness detail would have FLATTENED the wall - B2's "wax" defect
                    # arriving from the other side, in the revision that cites B2's lesson.
                    # Which blend the engine uses cannot be established without a boot that
                    # measures it, so the map is left off: the colour and normal detail
                    # carry the fix (high-frequency power x22.6, normal relief 0.0708 ->
                    # 0.4181) and neither can saturate. `b1/r13/foot/foot_detail_r13.json`
                    # publishes all three blend models.
                },
                {},
                {},
                {},
            ],
            "annotation": "ROCK",
            # r13 / N12-3: wheels on the mountain reported ASPHALT, because a TSStatic
            # material with no ``groundType`` falls back to the engine's default. 52 stock
            # materials use "ROCK" (automation_test_track's ``rockwall`` among them), and
            # johnson_valley's own ``backdrop`` material carries "DIRT_LOOSE" - a backdrop
            # with a ground model is stock practice, not an invention.
            "groundType": "ROCK",
            "castShadows": False,
            "materialTag0": LEVEL_ID,
            "translucentBlendOp": "None",
            "version": 1.5,
        }
    }


# --- scene records ------------------------------------------------------------------------


def _group(name: str, parent: str | None, **extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "name": name,
        "class": "SimGroup",
        "persistentId": persistent_id(f"group:{name}"),
    }
    if parent is not None:
        record["__parent"] = parent
    record.update(extra)
    return record


def mission_group_records() -> dict[str, list[dict[str, Any]]]:
    return {
        "main/items.level.json": [_group("MissionGroup", None, enabled="1")],
        "main/MissionGroup/items.level.json": [
            _group("level_objects", "MissionGroup"),
            _group("CameraBookmarks", "MissionGroup"),
            _group("PlayerDropPoints", "MissionGroup", enabled="1"),
            _group("AIWaypointsGroup", "MissionGroup"),
            _group("AIDecalWaypointsGroup", "MissionGroup"),
            _group("decal_road", "MissionGroup"),
            # B4 owns this group: the logs, the bench deck, the giant props, the trail
            # dressing and the four prefab clusters (place_props.rendered_outputs).
            _group(f"{LEVEL_ID}_props", "MissionGroup"),
            # B2 owns these three: the 28 hearth stones + 24 crust plates + 34 particle
            # emitter nodes; the 36 night lights; the 18 SFXEmitters + 13 SFXSpaces
            # (place_hearth.rendered_outputs).
            #
            # THEY MUST BE DECLARED HERE, NOT MERGED IN AFTERWARDS. This file is written
            # by three rounds, and whichever writer runs last wins: B4's writer silently
            # dropped B2's rows FOUR times during the parallel build, and one of those
            # times it happened between a cut and the boot that used it — the level loaded
            # clean and the scene census read 0 of 153 hearth objects, with no error
            # anywhere. Every group any round adds belongs in this list.
            _group(f"{LEVEL_ID}_hearth", "MissionGroup"),
            _group(f"{LEVEL_ID}_night_light", "MissionGroup"),
            _group(f"{LEVEL_ID}_audio", "MissionGroup"),
        ],
        "main/MissionGroup/level_objects/items.level.json": [
            _group("terrain", "level_objects"),
            _group("vegetation", "level_objects"),
            _group("Water", "level_objects"),
            _group("sky_and_sun", "level_objects"),
            _group("backdrop", "level_objects"),
            # B7b owns this one: the shelf road cut into the near ring's face
            # (`shelf_road`, a native MeshRoad), plus nothing else. Same law as above --
            # every group any round adds belongs in this list, or the next writer to
            # run drops it and the scene loads clean and empty.
            _group(shelf_road.GROUP_NAME, "level_objects"),
        ],
    }


def terrain_records(spec: terrain.TerrainSpec) -> list[dict[str, Any]]:
    return [terrain.terrain_block_record(spec, TER_PATH, TEXTURE_SET, persistent_id("theTerrain"))]


def sky_records() -> list[dict[str, Any]]:
    """The §5.1 records in B0's MEASURED form.

    ``version 2`` is the clock-law switch (with it the level loads at
    ``startTime`` itself; without it at ``startTime - 0.25``). ``day`` is the day
    of the MONTH. Any key the class does not own must be a STRING to survive the
    loader (``utcOffset``, ``dstRule``, the night-window fields); numbers vanish
    silently. The sun, moon and stars are positioned every frame by the Lua
    ``core_celestial`` extension from lat/lon + date + ``utcOffset``; its
    ``enableChrome`` overrides the authored night keys, which therefore describe
    only the ``core_celestial.setEnabled(false)`` fallback (B0 r3).
    """

    return [
        {
            "name": "tod",
            "class": "TimeOfDay",
            "persistentId": persistent_id("tod"),
            "__parent": "sky_and_sun",
            "animate": "0",
            "axisTilt": -20,
            "day": 20,
            "dayLength": 1800,
            "dstRule": "eu",
            "latitude": 46.55,
            "longitude": 8.45,
            "month": 6,
            "play": False,
            "startTime": TOD_CLOCK,
            "time": TOD_CLOCK,
            "utcOffset": "1",
            "version": 2,
            "year": 2026,
        },
        {
            "name": "sunsky",
            "class": "ScatterSky",
            "persistentId": persistent_id("sunsky"),
            "__parent": "sky_and_sun",
            # r6 (critic r5 N5-2). johnson_valley's own ambient, byte for byte
            # (132/255, 130/255, 144/255) - the closest stock analogue there is, a
            # desert basin ringed by ranges under a low warm sun, and derby ships the
            # identical vector. Ours was 16 % brighter in luma and carried a blue cast
            # (0.72 against 0.565 in B) that lifted every shadow: our day frames'
            # `shadow_share_lt_0p10` was 0.00-2.53 % against a stock band of
            # 0.17-10.78 %, and the two NATIVE 1920x1080 stock in-engine renders are at
            # 6.71 % and 8.83 %. Measured in `b1/r6/probe/frame_contrast.py`.
            "ambientScale": [0.517647, 0.509804, 0.564706, 1.0],
            "ambientScaleGradientFile": f"{SKY_GRADIENTS}/gradient_ambient.png",
            "azimuth": 294.0,
            "colorize": [0.30, 0.24, 0.55, 1.0],
            "colorizeGradientFile": f"{SKY_GRADIENTS}/gradient_colorize.png",
            "elevation": 10.0,
            "enableFogFallBack": False,
            "flareScale": 5.0,
            "flareType": "BNG_Sunflare_3",
            "fogScale": [0.62, 0.50, 0.34, 1.0],
            "fogScaleGradientFile": f"{SKY_GRADIENTS}/gradient_fog.png",
            "meteorRate": 0.15,
            "mieScattering": 0.00055,
            "moonAzimuth": 130.0,
            "moonElevation": 35.0,
            "moonIllumination": 0.7,
            "moonScale": 0.05,
            "moonEnabled": True,
            "nightColor": [0.0, 0.0, 0.0, 1.0],
            "nightCubemap": "nightCubemap",
            "nightFogColor": [0.0, 0.0, 0.0, 1.0],
            "nightFogGradientFile": f"{SKY_GRADIENTS}/gradient_fog.png",
            "nightGradientFile": f"{SKY_GRADIENTS}/gradient_ambient.png",
            "occlusionScale": 0.025,
            "shadowDarkenColor": [0.0, 0.0, 0.0, 0.0],
            "skyBrightness": 40.0,
            "starVisibility": 1.0,
            # r6: johnson_valley's own sun, byte for byte (255/255, 167/255, 42/255).
            # Ours carried more blue (0.30 against 0.165), which at a 9.77 deg sun -
            # where the sky is already the larger term on flat ground - is what made
            # "golden hour" read as a uniform wash. The stock B component runs
            # 0.086-0.831 over the nineteen `ScatterSky` records; Utah, the other desert
            # level, is lower still at 0.086.
            "sunScale": [1.0, 0.654902, 0.164706, 1.0],
            "sunScaleGradientFile": f"{SKY_GRADIENTS}/gradient_sunscale.png",
            "useNightCubemap": True,
        },
        {
            "name": "theLevelInfo",
            "class": "LevelInfo",
            "persistentId": persistent_id("theLevelInfo"),
            "__parent": "sky_and_sun",
            "canvasClearColor": [1, 1, 1, 255],
            "enabled": "1",
            "fogAtmosphereHeight": FOG_ATMOSPHERE_HEIGHT,
            "fogColor": FOG_COLOR,
            "fogDensity": FOG_DENSITY,
            "globalEnviromentMap": GLOBAL_CUBEMAP,
            "gravity": GRAVITY,
            # Dynamic fields the class does not own: STRINGS, or they are dropped (B0 A3).
            "nightLightsNightEnd": NIGHT_END,
            "nightLightsNightStart": NIGHT_START,
            "temperatureCurveC": [0, 14, 0.25, 9, 0.5, 4, 0.75, 8, 1, 14],
            "visibleDistance": VISIBLE_DISTANCE,
        },
        {
            "name": "clouds",
            "class": "CloudLayer",
            "persistentId": persistent_id("clouds"),
            "__parent": "sky_and_sun",
            # r6. Three cloud decks were booted and only `coverage` is kept; the two that
            # are not are declared here because the null is the useful part.
            #   leg A (CERTIFIED - this cut, `b1/r6/evidence/`): coverage 0.55 -> 1.23 on
            #     this level's own deck. One cumulus enters frame; the sky's own
            #     sigma_local8 on s7 goes 0.00214 -> 0.00312.
            #   leg B (`b1/r6/leg_utah_deck/`): + Utah's tex scales and its 7 km height,
            #     the deck that goes with this texture. The cloud LEAVES the frame
            #     (0.00312 -> 0.00281): our nine shot cameras look at the horizon, where a
            #     7 km deck is overhead and out of a 60 deg vertical FOV.
            #   leg C (`b1/r6/leg_jv_deck/`): johnson_valley's ENTIRE deck - its texture,
            #     scales, speeds, height 3, exposure 1.3, windSpeed 0.2. This one is
            #     visible: low haze bands along the ridge line. It is also the worst of
            #     the three, because that haze sits IN FRONT of the backdrop - the frames'
            #     sigma_local8 median falls 0.03291 -> 0.02683, below the stock band's own
            #     minimum, and the ring's own band falls with it.
            # All three zips and all 81 frames are kept. The deck below is r5's, unchanged.
            "Textures": [
                {"texDirection": [1.0, 0.0], "texScale": 1.5, "texSpeed": 0.002},
                {"texDirection": [0.8, 0.2], "texScale": 3.0, "texSpeed": 0.02},
                {"texDirection": [0.2, 0.5], "texScale": 4.0, "texSpeed": 0.03},
            ],
            "baseColor": [0.996, 0.996, 0.996, 0.996],
            # r6 (critic r5 N5-2). Split every frame at the horizon and the sky is where
            # the flatness lives: over our eight day bearings the sky's own sigma_local8
            # is 0.0021-0.0096 (median 0.0044) against a stock preview band of
            # 0.0048-0.0446 (median 0.0134) - THREE TIMES less structure across a
            # quarter to two fifths of every frame - and its highlight share is ~0
            # where a stock frame's clouds carry the top of the histogram. Coverage is
            # why: 0.55 is below EVERY outdoor natural stock level. The six the design
            # references and Utah run 1.0-1.234 (johnson_valley 1.23, italy 1.23,
            # east_coast_usa 1.234, Utah 1.23, small_island 1.2, west_coast_usa 1.0);
            # only the indoor and test maps sit at 0.08-0.30. 1.23 is Utah's and
            # johnson_valley's own value, and the texture below is already Utah's.
            "coverage": 1.23,
            "exposure": 1.4,  # the stock band is 0.0-1.7, median 1.3
            "height": 4.5,  # the stock band is 0.0-8.0, median 3.0
            "texture": "levels/Utah/art/skies/clouds_fluffy.dds",
            "windSpeed": 0.15,
        },
    ]


def vegetation_records() -> list[dict[str, Any]]:
    """The empty vegetation scaffolding B3 fills (this round ships no forest items)."""

    wind_xy = terrain.bearing_point(90.0, 380.0)
    return [
        {
            "name": f"{LEVEL_ID}_wind",
            "class": "ForestWindEmitter",
            "persistentId": persistent_id("wind"),
            "__parent": "vegetation",
            "position": [
                _r6(wind_xy[0]),
                _r6(wind_xy[1]),
                _r3(terrain.surface_z(*wind_xy) + 20.0),
            ],
            "gustFrequency": 2,
            "gustStrength": 3,
            "gustWobbleStrength": 3,
            "gustYawAngle": 50,
            "hasMount": "0",
            "strength": 0.5,
            "turbulenceStrength": 5.25,
        },
        {
            "name": "theForest",
            "class": "Forest",
            "persistentId": persistent_id("theForest"),
            "__parent": "vegetation",
            "lodReflectScalar": 0,
        },
    ]


#: r11, critic r10 B10-3. The pale ellipse a crest camera sees is the water's SURFACE, and
#: r10 handed the whole of it to the design as "moving the basin". The outline is the
#: heightmap's and that half is right; the FLAT PALE FILL and the RAZOR RIM are this
#: material's, they are B1's, and r5 already moved three of these fields for exactly this
#: symptom (see the comment on `clarity` below). r11 sweeps the levers B1 owns in ONE boot -
#: same weather, same camera, same sun - with the WaterPlane hidden once to give an exact
#: pixel mask of the water, and ships the row the sweep picks. Legs, and why each exists:
#:
#: * `depth_to_the_lakes_own_depth` - the lake is at most **12.043 m** deep (measured off
#:   the shipped `.ter`: 124,593 wet nodes, p50 8.640 m, floor at LAKE_FLOOR 86.0 under a
#:   98.0 surface). At `depthGradientMax` 18.0 the depth ramp's coordinate never exceeds
#:   0.669, so the ramp's darkest third is NEVER REACHED and every deep pixel holds one
#:   tone. Setting it to the depth the lake actually has is not a taste move.
#: * `clarity_to_the_band_floor` - r5 took `clarity` 0.55 -> 0.25, which is the stock
#:   band's MAXIMUM (13 stock records, min 0.00, median 0.25, max 0.25). The bed still
#:   shows through, and 92.96 % of the painted lakebed is under water, so paint can never
#:   reach it and this is the only lever that can.
#: * `surface_structure` - `overallWaveMagnitude` 0.05 against a stock median of 0.10, on
#:   water read at 1.2 km from the crest: the fill has half the vertex undulation stock
#:   ships, which is what "flat slab" is at that distance.
#: * `foam_band_wider` - `foamMaxDepth` 1.0 puts the foam where the water is under 1 m
#:   deep, and the lake's p10 depth is 1.203 m on a shelf that falls away fast: a thin
#:   even ring, i.e. the conic rim r5 was already attacking.
#: * `all_four` - the combination, which is the one that ships if it wins.
#: * `over_the_top` - a deliberate overshoot (clarity 0, ramp at half the depth, foam to
#:   the stock maximum, waves at 6x). It is here so the choice is a MEASURED optimum and
#:   not "more is better"; if it wins the rule was wrong and the report says so.
#:
#: Every value is inside the stock band measured over the 60 WaterPlane/River records of
#: the shipped stock levels (`b1/r5/probe/stock_water_band.json`, re-measured and pinned by
#: `b1/r11/probe/water_material.py`), and the sweep is run against the record that ships.
#: **Every leg carries the COMPLETE field set, not a delta.** The first cut of this table
#: held deltas from the r10 baseline and gave ``r10_shipped`` an EMPTY dict, so five of the
#: seven legs set nothing at all and rendered whatever the previous leg had left on the
#: object. The instrument's own field READBACK caught it - every leg came back identical,
#: and the "repeat" came back holding `over_the_top`'s values - which is what a readback
#: control is for and why every leg publishes one.
WATER_R10_BASELINE: dict[str, float] = {
    "clarity": 0.25,
    "depthGradientMax": 18.0,
    "foamMaxDepth": 1.0,
    "foamRippleInfluence": 0.075,
    "overallRippleMagnitude": 0.8,
    "overallWaveMagnitude": 0.05,
}
WATER_SWEEP: dict[str, dict[str, float]] = {
    "r10_shipped": dict(WATER_R10_BASELINE),
    "depth_to_the_lakes_own_depth": WATER_R10_BASELINE | {"depthGradientMax": 12.0},
    "clarity_to_the_band_floor": WATER_R10_BASELINE | {"clarity": 0.05},
    "surface_structure": WATER_R10_BASELINE
    | {"overallWaveMagnitude": 0.1, "overallRippleMagnitude": 1.2},
    "foam_band_wider": WATER_R10_BASELINE | {"foamMaxDepth": 2.5, "foamRippleInfluence": 0.35},
    "all_four": WATER_R10_BASELINE
    | {
        "depthGradientMax": 12.0,
        "clarity": 0.05,
        "overallWaveMagnitude": 0.1,
        "overallRippleMagnitude": 1.2,
        "foamMaxDepth": 2.5,
        "foamRippleInfluence": 0.35,
    },
    "over_the_top": {
        "depthGradientMax": 6.0,
        "clarity": 0.0,
        "overallWaveMagnitude": 0.3,
        "overallRippleMagnitude": 2.0,
        "foamMaxDepth": 6.0,
        "foamRippleInfluence": 1.0,
    },
}
#: The row the sweep picked, and the row this level ships. `water_records()` builds the
#: record by applying it to the r10 base, so the shipped record IS the swept leg and the
#: two cannot drift; `r11/probe/water_material.py` asserts the winner is this key.
WATER_RECIPE = "all_four"


def water_records() -> list[dict[str, Any]]:
    """The lake (design §5.2). Every field of the QB-24 set is present.

    The five swept fields come from ``WATER_SWEEP[WATER_RECIPE]``, so what ships is the
    leg the live sweep measured rather than a number retyped beside it.
    """

    centre = terrain.bearing_point(terrain.terrain_model.LAKE_BEARING, terrain.terrain_model.LAKE_R)
    swept = WATER_SWEEP[WATER_RECIPE]
    return [
        {
            "name": WATER_NAME,
            "class": "WaterPlane",
            "persistentId": persistent_id("water"),
            "__parent": "Water",
            "position": [_r3(centre[0]), _r3(centre[1]), WATER_Z],
            "Foam": [
                {
                    "foamDir": [0.0, 1.0],
                    "foamOpacity": 1.0,
                    "foamSpeed": 0.01,
                    "foamTexScale": [4.0, 4.0],
                },
                {
                    "foamDir": [0.0, -1.0],
                    "foamOpacity": 1.5,
                    "foamSpeed": 0.01,
                    "foamTexScale": [4.0, 4.0],
                },
            ],
            "Ripples (texture animation)": [
                {
                    "rippleDir": [0.0, -1.0],
                    "rippleMagnitude": 0.25,
                    "rippleSpeed": 0.008,
                    "rippleTexScale": [12.0, 12.0],
                },
                {
                    "rippleDir": [0.707, 0.707],
                    "rippleMagnitude": 0.25,
                    "rippleSpeed": 0.03,
                    "rippleTexScale": [3.0, 3.0],
                },
                {
                    "rippleDir": [-0.5, 0.86],
                    "rippleMagnitude": 0.18,
                    "rippleSpeed": 0.003,
                    "rippleTexScale": [90.0, 90.0],
                },
            ],
            "Waves (vertex undulation)": [
                {"waveDir": [0.0, -1.0], "waveMagnitude": 0.06, "waveSpeed": 1.0},
                {"waveDir": [0.25, 0.2], "waveMagnitude": 0.03, "waveSpeed": 2.0},
                {"waveDir": [0.1, -0.7], "waveMagnitude": 0.03, "waveSpeed": 3.0},
            ],
            "baseColor": [30, 62, 66, 60],
            # r5 (critic r4 N4-6: "what reads as artificial is not only the ellipse: it
            # is the HARD RIM and the NEAR-UNIFORM FILL, and those are texture-side").
            # Measured first, over the 60 WaterPlane/River records of the shipped stock
            # levels (b1/r5/probe/stock_water_band.py): `clarity` ours 0.55 against a
            # stock band of 0.00-0.25 - OUTSIDE it, and more than twice the clearest
            # water any stock level ships, which is why the bed shows through as one
            # flat pale ellipse from the crest; `foamMaxDepth` ours 0.35 against
            # 0.20-6.00 median 1.00 - a foam band 35 cm deep on a shelf that falls away
            # fast is a razor line, and a razor line at the waterline IS the hard rim;
            # `foamRippleInfluence` ours 0.005 was the stock MINIMUM (median 0.075), so
            # that razor line was also a perfect conic. All three move to a stock value
            # and nothing else about the water changes.
            #
            # r11 (critic r10 B10-3): r5 moved these three and STOPPED at the stock
            # median, and `clarity` 0.25 is the band's MAXIMUM - the clearest water any
            # stock level ships - so the bed still showed through as a flat pale ellipse
            # from the crest. r10 then handed the whole symptom upward as a design change
            # without mentioning that this record exists. It is B1's. The five swept
            # fields below now come from WATER_SWEEP, measured live in one boot.
            "clarity": swept["clarity"],
            "cubemap": GLOBAL_CUBEMAP,
            "depthGradientMax": swept["depthGradientMax"],
            "depthGradientTex": f"/{LEVEL_RELATIVE}/art/water/{LEVEL_ID}_depth_ramp.png",
            "distortEndDist": 10.0,
            "distortFullDepth": 5.5,
            "distortStartDist": 0.0,
            # italy's exact reference; a verified member of content/assets/materials/tileable.zip
            "foamTex": "/assets/materials/tileable/water/water_effects/foam2_b.color.dds",
            "foamAmbientLerp": 1.0,
            "foamMaxDepth": swept["foamMaxDepth"],
            "foamRippleInfluence": swept["foamRippleInfluence"],
            "fresnelBias": -0.1,
            "fresnelPower": 0.8,
            "gridSize": 100,
            "overallFoamOpacity": 1.5,
            "overallRippleMagnitude": swept["overallRippleMagnitude"],
            "overallWaveMagnitude": swept["overallWaveMagnitude"],
            "reflectDetailAdjust": 0.0,
            "reflectMaxRateMs": 20,
            "reflectivity": 0.35,
            "rippleTex": "/levels/jungle_rock_island/art/water/ripple4.png",
            "specularPower": 210.0,
            "underwaterColor": [40, 90, 80, 253],
            "viscosity": 0.001,
            "waterFogDensity": 0.35,
            "waterFogDensityOffset": 0.1,
            "wetDarkening": 0.3,
            "wetDepth": 0.5,
        }
    ]


def backdrop_records() -> list[dict[str, Any]]:
    """The backdrop range (design §2.6): one TSStatic on its Colmesh, no shadows.

    r12 (critic r11 B11-3): ``collisionType "Collision Mesh"`` - the DAE now carries a
    closed ``Colmesh_<name>-1`` node, so the wheels meet the range instead of driving
    through it onto the terrain behind. ``decalType`` stays ``None``.
    """

    return [
        {
            "name": BACKDROP_NAME,
            "class": "TSStatic",
            "persistentId": persistent_id(BACKDROP_NAME),
            "__parent": "backdrop",
            "position": [CENTER[0], CENTER[1], 0.0],
            "rotationMatrix": list(IDENTITY),
            "scale": [1.0, 1.0, 1.0],
            "shapeName": f"/{LEVEL_RELATIVE}/{BACKDROP_DIR}/{backdrop.BACKDROP_DAE_NAME}",
            "collisionType": "Collision Mesh",
            "decalType": "None",
            "castShadows": False,
            "useInstanceRenderData": True,
        }
    ]


def shelf_road_records() -> list[dict[str, Any]]:
    """B7b: the road up the canyon wall, as ONE native ``MeshRoad``.

    The engine's own class for a drivable road that is not draped on terrain: a spline of
    nodes, each with position, width, depth and a normal, collision built by the engine.
    It opens in the World Editor's Mesh Road Editor like a hand-laid road. The survey that
    places the nodes is ``shelf_road``'s; the record layout is the engine's own
    ``serialize()`` output (see ``shelf_road.meshroad_record``).
    """

    return [shelf_road.meshroad_record()]


def shelf_approach_records() -> list[dict[str, Any]]:
    """B7b: the DecalRoad from the trail's end to the foot of the shelf road.

    The nodes come from ``shelf_road.approach_nodes()``, not from ``layout.json``: that
    file is one of the nine the design lock hashes and is never edited. Both ends are
    derived anyway -- the trail's last waypoint from the terrain model, the far end from the
    road's own landing -- so the approach follows the road wherever the survey puts it.
    """

    record = _decal_road(
        shelf_road.APPROACH_NAME,
        "decal_road",
        shelf_road.approach_nodes(),
        road_material_name("m_dirt_variation"),
        drivability=0.3,
        layer="m_dirt_variation",
    )
    # The same measured fix as the track and trail surfaces of this family (B4's single-
    # variable A/B, `visible_road_records`): an improved spline on an `m_dirt_variation` road
    # is what makes the static decal batcher log an infinite AABB. The approach's nodes are
    # 4 m apart, so round its 17 m loop a linear chord sags 0.12 m.
    record["improvedSpline"] = False
    return [record]


def spawn_records() -> list[dict[str, Any]]:
    """Four SpawnSpheres: the arena's south apron plus the design's three derived ones."""

    records = [
        {
            "name": SPAWN_SOUTH,
            "class": "SpawnSphere",
            "persistentId": persistent_id(SPAWN_SOUTH),
            "__parent": "PlayerDropPoints",
            "position": spawn_position(),
            "dataBlock": "SpawnSphereMarker",
            "enabled": "1",
            "radius": 1.0,
            # spawn.lua multiplies the sphere rotation by a 180 deg yaw, so an
            # identity sphere spawns the nose toward +Y = north = toward C.
            "rotationMatrix": list(IDENTITY),
            "spawnClass": "Player",
            "sphereWeight": "1",
        }
    ]
    for row in layout()["spawns"]:
        name = f"{LEVEL_ID}{row['name']}"
        records.append(
            {
                "name": name,
                "class": "SpawnSphere",
                "persistentId": persistent_id(name),
                "__parent": "PlayerDropPoints",
                # z from the terrain model, lifted clear of the surface
                "position": [_r6(row["x"]), _r6(row["y"]), _r3(float(row["z"]) + SPAWN_Z_LIFT)],
                "dataBlock": "SpawnSphereMarker",
                "enabled": "1",
                "radius": 1.0,
                # The sphere's own yaw plus spawn.lua's 180 deg gives the design's facing.
                "rotationMatrix": engine_yaw_matrix((float(row["facing_deg"]) + 180.0) % 360.0),
                "spawnClass": "Player",
                "sphereWeight": "1",
            }
        )
    return records


def look_at_matrix(eye: tuple[float, float, float], aim: tuple[float, float, float]) -> list[float]:
    """Rotation matrix ROWS = the local axes (AGENTS arena law): x right, y forward, z up."""

    fx, fy, fz = (aim[0] - eye[0], aim[1] - eye[1], aim[2] - eye[2])
    length = math.sqrt(fx * fx + fy * fy + fz * fz)
    if length < 1e-9:
        raise LevelWriteError("camera eye and aim coincide")
    fx, fy, fz = fx / length, fy / length, fz / length
    rx, ry, rz = fy, -fx, 0.0
    rlen = math.hypot(rx, ry)
    if rlen < 1e-9:  # looking straight down: fall back to world east
        rx, ry, rlen = 1.0, 0.0, 1.0
    rx, ry = rx / rlen, ry / rlen
    ux = ry * fz - rz * fy
    uy = rz * fx - rx * fz
    uz = rx * fy - ry * fx
    return [_r6(v) for v in (rx, ry, rz, fx, fy, fz, ux, uy, uz)]


def camera_records() -> list[dict[str, Any]]:
    """The eleven truth-plan frames of §8 as CameraBookmarks."""

    records = []
    for camera in layout()["cameras"]:
        name = f"{LEVEL_ID}_cam_{camera['name']}"
        eye = tuple(float(v) for v in camera["position"])
        aim = tuple(float(v) for v in camera["look_at"])
        records.append(
            {
                "name": name,
                "internalName": name,
                "class": "CameraBookmark",
                "persistentId": persistent_id(name),
                "__parent": "CameraBookmarks",
                "position": [_r6(v) for v in eye],
                "dataBlock": "CameraBookmarkMarker",
                "rotationMatrix": look_at_matrix(eye, aim),
            }
        )
    return records


# --- DecalRoads ----------------------------------------------------------------------------


def _nodes(entry: dict[str, Any]) -> list[list[float]]:
    return [[_r6(n["x"]), _r6(n["y"]), _r3(n["z"]), float(n["width"])] for n in entry["nodes"]]


def _resample(nodes: list[list[float]], closed: bool) -> tuple[np.ndarray, np.ndarray]:
    """(points [n, 3], cumulative arc length) of a node list, closed if asked."""

    points = np.array([[n[0], n[1], n[2]] for n in nodes], dtype=np.float64)
    if closed:
        points = np.vstack([points, points[:1]])
    steps = np.linalg.norm(np.diff(points[:, :2], axis=0), axis=1)
    return points, np.concatenate([[0.0], np.cumsum(steps)])


def _point_at(points: np.ndarray, arc: np.ndarray, distance: float) -> tuple[float, float, float]:
    distance = float(np.clip(distance, 0.0, arc[-1]))
    index = int(np.searchsorted(arc, distance, side="right")) - 1
    index = min(max(index, 0), len(arc) - 2)
    span = arc[index + 1] - arc[index]
    t = 0.0 if span <= 0 else (distance - arc[index]) / span
    a, b = points[index], points[index + 1]
    return tuple(a + (b - a) * t)


def _sub_range(
    nodes: list[list[float]],
    closed: bool,
    start_m: float,
    length_m: float,
    width: float,
    step_m: float = 8.0,
    offset_m: float = 0.0,
) -> list[list[float]]:
    """A segment of a pinned centreline, optionally offset sideways by ``offset_m``."""

    points, arc = _resample(nodes, closed)
    total = float(arc[-1])
    count = max(2, round(length_m / step_m) + 1)
    out: list[list[float]] = []
    for index in range(count):
        distance = start_m + length_m * index / (count - 1)
        distance = distance % total if closed else min(distance, total)
        x, y, _z = _point_at(points, arc, distance)
        if offset_m:
            ahead = _point_at(points, arc, (distance + 1.0) % total if closed else distance + 1.0)
            dx, dy = ahead[0] - x, ahead[1] - y
            norm = math.hypot(dx, dy) or 1.0
            x += offset_m * (dy / norm)
            y += offset_m * (-dx / norm)
        # Cosmetic layers hug the SURFACE, not the chord between two pinned nodes:
        # a linear z between 12.5 m nodes on the trail's 11 % grade floats 38 mm.
        out.append([_r6(x), _r6(y), _r3(terrain.surface_z(x, y)), float(width)])
    return out


def _decal_road(
    name: str,
    parent: str,
    nodes: list[list[float]],
    material: str,
    *,
    closed: bool = False,
    drivability: float | None = None,
    gated: bool = False,
    improved: bool = True,
    layer: str | None = None,
    detail: float = 0.25,
) -> dict[str, Any]:
    if closed and nodes[0][:2] != nodes[-1][:2]:
        # Close the loop by REPEATING node 0 - the shape the scaffold's proven AI ring
        # used. A `closedLoop` field instead made the engine's static decal batcher
        # build an infinite AABB ("packed position exceeded supported local range of
        # 2048 meters ... by inf m", boot 1 run 1), so the flag is not authored.
        nodes = [*nodes, list(nodes[0])]
    record: dict[str, Any] = {
        "name": name,
        "class": "DecalRoad",
        "persistentId": persistent_id(name),
        "__parent": parent,
        "position": nodes[0][:3],
        "detail": detail,
        "material": material,
        "nodes": nodes,
        "improvedSpline": improved,
        # The track turns 7.5 deg per node on its r 248 circle; stock visible roads
        # carry an explicit breakAngle (italy 5-6, WCUSA 1) and the default is
        # smaller than our corner, which made the static decal batcher build a
        # leaf with an inverted-infinite AABB (boot 1: "packed position exceeded
        # supported local range of 2048 meters ... by inf m").
        "breakAngle": 8,
    }
    if layer is not None:
        record.update(
            {
                "textureLength": ROAD_LAYERS[layer]["textureLength"],
                "startEndFade": list(ROAD_LAYERS[layer]["startEndFade"]),
                "distanceFade": list(ROAD_LAYERS[layer]["distanceFade"]),
                "renderPriority": ROAD_LAYERS[layer]["renderPriority"],
            }
        )
    else:
        record.update(
            {
                "textureLength": 300.0,
                "startEndFade": [50.0, 50.0],
                "distanceFade": [150.0, 50.0],
                "renderPriority": 2,
            }
        )
    # Exactly ONE navgraph layer per road (study §5.12): every cosmetic layer is -1.
    record["drivability"] = -1 if drivability is None else drivability
    if gated:
        record["gatedRoad"] = True
    return record


def _split_closed_loop(record: dict[str, Any]) -> list[dict[str, Any]]:
    """B4: turn one loop closed by repeating node 0 into two open arcs meeting end to end.

    Why every closed VISIBLE road on the track goes through here, not just the surface: a
    census of the 44,521 DecalRoads in the shipped stock levels finds seven whose first node
    equals their last and every one is a degenerate 2-node record, so stock never closes a
    loop this way -- while johnson_valley ships a 3,610.8 m OPEN VISIBLE road, which is why
    the batcher's "supported local range of 2048 meters" is not about our 1,166 m span.  The
    engine's ``SceneStaticDecalRoadManager`` reported an INFINITE node AABB (``leaf
    origin=(-inf, -inf, -inf)``, overflow ``inf`` m) for the closed, visible track surface.
    The arcs share their end nodes exactly and carry ``startEndFade [0, 0]``, which also
    removes the fade a loop used to draw into itself at its own seam.
    """

    nodes = [list(n) for n in record["nodes"]]
    half = len(nodes) // 2
    out = []
    # ``nodes`` ALREADY ends on a repeat of node 0 (that is what made it a loop), so arc b is
    # nodes[half:] and nothing is appended.  B4's first split re-appended node 0 and gave arc
    # b two identical nodes in a row -- a ZERO-LENGTH final segment, which is the same
    # degenerate the engine's own wrap makes on a first == last road, and the batcher's
    # infinite-AABB line moved from `track_surface` to `track_surface_b` at the same world
    # vertex instead of going away (B4 boots 1 and 2).
    for suffix, arc in (("a", nodes[: half + 1]), ("b", nodes[half:])):
        clone = dict(record)
        clone["name"] = f"{record['name']}_{suffix}"
        clone["persistentId"] = persistent_id(clone["name"])
        clone["nodes"] = arc
        clone["position"] = arc[0][:3]
        clone["startEndFade"] = [0.0, 0.0]
        out.append(clone)
    return out


#: (name suffix, layer material key, count, width, segment length m, offset m)
TRACK_STACK = (
    ("flows", "m_dirt_flows", 6, 2.5, 45.0, -2.2),
    ("gravel", "m_dirt_gravel", 4, 3.0, 60.0, 0.0),
    ("cracks", "m_mud_cracks", 6, 4.0, 10.0, 2.6),
    ("puddle", "m_puddle_wet", 6, 3.0, 4.5, -1.6),
)
TRAIL_STACK = (
    ("flows", "m_dirt_flows", 8, 2.5, 37.5, -2.0),
    ("gravel", "m_dirt_gravel", 5, 3.0, 50.0, 0.0),
    ("cracks", "m_mud_cracks", 6, 4.0, 10.0, 2.0),
    ("puddle", "m_puddle_wet", 4, 3.0, 4.5, -1.2),
    ("litter", "m_needle_litter", 10, 2.5, 25.0, 3.2),
)


def ai_road_records() -> list[dict[str, Any]]:
    """The five invisible navgraph roads: the r 170 ring and the four lane connectors."""

    roads = layout()["decal_roads"]
    records = [
        _decal_road(
            f"{LEVEL_ID}_ai_ring",
            "AIDecalWaypointsGroup",
            _nodes(roads["ai_ring"]),
            ROAD_INVISIBLE,
            closed=True,
            drivability=1.0,
            gated=True,
        )
    ]
    for lane in (60, 150, 240, 330):
        key = f"ai_connector_{lane}"
        records.append(
            _decal_road(
                f"{LEVEL_ID}_{key}",
                "AIDecalWaypointsGroup",
                _nodes(roads[key]),
                ROAD_INVISIBLE,
                drivability=1.0,
                gated=True,
            )
        )
    return records


def visible_road_records() -> list[dict[str, Any]]:
    """The 28 track + 39 trail + 40 hearth-skid DecalRoads of §2.3 / §2.3.1."""

    roads = layout()["decal_roads"]
    records: list[dict[str, Any]] = []
    for key, closed, drivability, stack in (
        ("track_surface", True, 0.5, TRACK_STACK),
        ("trail_surface", False, 0.3, TRAIL_STACK),
    ):
        entry = roads[key]
        nodes = _nodes(entry)
        base = key.removesuffix("_surface")
        width = float(entry["width"])
        surface = _decal_road(
            f"{LEVEL_ID}_{key}",
            "decal_road",
            nodes,
            road_material_name("m_dirt_variation"),
            closed=closed,
            drivability=drivability,
            layer="m_dirt_variation",
        )
        # B4 CLOSES B1's decal-batcher line here, with a single-variable A/B: two cuts of the
        # SAME tree differing only in this field, booted back to back on the sentinel.
        #   improvedSpline true  -> known_decal_batcher_errors 1, 18 E lines  (cut 3d956607)
        #   improvedSpline false -> known_decal_batcher_errors 0, 16 E lines  (cut cb4e807d)
        # The line reads `packed position exceeded supported local range ... by inf m` with
        # `leaf origin=(-inf, -inf, -inf)` -- an INFINITE batch box, not an oversized road:
        # johnson_valley ships a 3,610 m open VISIBLE road and never logs it, and the two
        # earlier hypotheses (a loop closed by a repeated node; the zero-length segment that
        # closure makes) were each built, cut and booted, and each left the line in place.
        # What the A/B shows is that improvedSpline is NECESSARY for the line on these three
        # roads; it is not sufficient in general -- the other 115 DecalRoads keep it and stay
        # quiet.  The cost of drawing these two families linearly is bounded by the design's
        # own geometry check: a linear road through the trail's 71 pinned nodes stays within
        # 0.489 m of the modelled centreline (`layout.json` trail_surface.geometry_check
        # node_polyline_dev_max_m) against the spline's 0.167 m, and on the r 248 track the
        # chord sagitta between 7.5-degree nodes is 0.53 m -- 6.6 % of an 8 m painted width.
        surface["improvedSpline"] = bool(os.getenv(SPLINE_SURFACE_ENV))
        records.append(surface)
        _, arc = _resample(nodes, closed)
        total = float(arc[-1])
        for suffix, layer, count, layer_width, length, offset in stack:
            for index in range(count):
                start = total * (index + 0.5) / count - length / 2.0
                if not closed:
                    start = max(0.0, min(start, total - length))
                if suffix == "litter":
                    # needle litter only where the trail is inside the forest (r > 350)
                    start = total * 0.42 + (total * 0.55) * index / max(count - 1, 1)
                    start = min(start, total - length)
                records.append(
                    _decal_road(
                        f"{LEVEL_ID}_{base}_{suffix}_{index}",
                        "decal_road",
                        _sub_range(
                            nodes,
                            closed,
                            start,
                            length,
                            layer_width,
                            step_m=max(length / 6.0, 1.5),
                            offset_m=offset,
                        ),
                        road_material_name(layer),
                        layer=layer,
                    )
                )
        # ONE centred rut record per road, not two offset ones (r3).  The tiretracks
        # opacity mask (`cook_terrain_textures._road_opacity`, kind "ruts") already paints a
        # PAIR of wheel paths inside the record, at u 0.28 and 0.72 with sigma 0.09.  r2 laid
        # two 3.5 m records at +-1.2 m, so FOUR ruts covered y -2.95 .. +2.95 of a 6.0 m
        # trail: a wash over the whole surface with no wheel path anywhere in it, which is
        # exactly what critic pass 2 reported ("still no ruts").  One 3.6 m record centred on
        # the road puts the pair at +-0.79 m with a 0.32 m sigma -- a car's own track width.
        records.append(
            _decal_road(
                f"{LEVEL_ID}_{base}_rut",
                "decal_road",
                _sub_range(nodes, closed, 0.0, total, RUT_WIDTH_M, step_m=OVERLAY_STEP_M),
                road_material_name("m_dirt_tiretracks"),
                layer="m_dirt_tiretracks",
            )
        )
        for side, offset in (
            ("in", -(width / 2.0 + 0.5)),
            ("out", width / 2.0 + 0.5),
        ):
            records.append(
                _decal_road(
                    f"{LEVEL_ID}_{base}_verge_{side}",
                    "decal_road",
                    _sub_range(
                        nodes, closed, 0.0, total, 4.0, step_m=OVERLAY_STEP_M, offset_m=offset
                    ),
                    road_material_name("m_bank_erosion"),
                    layer="m_bank_erosion",
                )
            )
        if closed:
            # r3: the TRACK dust overlay is a track overlay.  r2 painted it down the forest
            # trail as well -- a 5.0 m wash of a luma-180.0, saturation-0.079 texture at 35 %
            # over a 6.0 m road -- and with the stack the right way up that wash is most of
            # what critic pass 2 measured as "a pale limestone haul road rather than dirt".
            # A rally loop raises dust; a forest track under a canopy does not.
            records.append(
                _decal_road(
                    f"{LEVEL_ID}_{base}_dust",
                    "decal_road",
                    _sub_range(nodes, closed, 0.0, total, 5.0, step_m=OVERLAY_STEP_M),
                    road_material_name("m_track_dust_overlay"),
                    layer="m_track_dust_overlay",
                )
            )
    records.extend(hearth_skid_records())
    # B4: no VISIBLE road ships closed by a repeated node (see _split_closed_loop).  The five
    # invisible AI roads keep their proven closed form -- they are not in the static decal
    # batcher that reports the line, and the r 170 ring's navgraph is measured (span 1.21 m).
    split: list[dict[str, Any]] = []
    for record in records:
        nodes = record["nodes"]
        if len(nodes) > 4 and nodes[0][:3] == nodes[-1][:3]:
            split.extend(_split_closed_loop(record))
        else:
            split.append(record)
    return split


def hearth_skid_records() -> list[dict[str, Any]]:
    """40 rubber arcs on the flat hearth slab (design §2.3.1; r 118-170, width 4).

    The slab is exactly 100.000 out to r 210, so every node sits on the datum.
    """

    rng = np.random.default_rng(SKID_ARC_SEED)
    records = []
    for index in range(SKID_ARC_COUNT):
        radius = float(SKID_R_MIN + (SKID_R_MAX - SKID_R_MIN) * rng.random())
        start = float(rng.random() * 360.0)
        span = float(18.0 + rng.random() * 42.0) * (1.0 if rng.random() < 0.5 else -1.0)
        steps = max(3, int(abs(span) / 6.0))
        nodes = []
        for step in range(steps + 1):
            bearing = start + span * step / steps
            x, y = terrain.bearing_point(bearing, radius)
            nodes.append([_r6(x), _r6(y), _r3(CENTER[2]), 4.0])
        records.append(
            _decal_road(
                f"{LEVEL_ID}_hearth_skid_{index}",
                "decal_road",
                nodes,
                road_material_name("m_skid_arc"),
                layer="m_skid_arc",
            )
        )
    return records


# --- minimap / previews ------------------------------------------------------------------


def shaded_relief(size: int = 2048) -> np.ndarray:
    """Top-down RGB (north up) straight from the shipped base albedo map."""

    payload = (LEVEL_ROOT / cook.base_texture_relative("b")).read_bytes()
    with Image.open(io.BytesIO(payload)) as image:
        return np.asarray(
            image.convert("RGB").resize((size, size), Image.Resampling.LANCZOS), dtype=np.uint8
        )


def minimap_png() -> bytes:
    return cook.png_bytes(shaded_relief(2048), "RGB")


def _preview(label: str, crop_m: float, note: str) -> bytes:
    """An 800x600 preview cut out of the base albedo, with a caption bar."""

    full = Image.fromarray(shaded_relief(2048))
    spec = terrain.DEFAULT_SPEC
    scale = 2048.0 / spec.extent_m
    cx = (CENTER[0] - spec.position[0]) * scale
    cy = 2048.0 - (CENTER[1] - spec.position[1]) * scale
    half_w = crop_m * scale / 2.0
    half_h = half_w * 600.0 / 800.0
    crop = full.crop(
        (int(cx - half_w), int(cy - half_h), int(cx + half_w), int(cy + half_h))
    ).resize((800, 600), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(crop)
    draw.rectangle((0, 566, 800, 600), fill=(18, 14, 12))
    draw.text((12, 576), label, fill=(255, 196, 64))
    draw.text((12, 588), note, fill=(200, 180, 150))
    buffer = io.BytesIO()
    crop.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def preview_pngs() -> dict[str, bytes]:
    return {
        f"{LEVEL_ID}_preview.png": _preview(
            "GIANT'S HEARTH - the Kettle Basin",
            1400.0,
            "Kettle Lake WNW, the campsite loop, the trail over the Firewood Gap",
        ),
        f"{LEVEL_ID}_preview_hearth.png": _preview(
            "GIANT'S HEARTH - the coals",
            700.0,
            "the Gateway Skillet bedded in a ring of coals, ash bed and stone ring",
        ),
    }


def probe_thumbnail_jpg(preview: bytes) -> bytes:
    with Image.open(io.BytesIO(preview)) as source:
        image = source.convert("RGB").resize((640, 360), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 330, 640, 360), fill=(18, 14, 12))
    draw.text((12, 338), "GIANT'S HEARTH - LEVEL PROBE", fill=(255, 196, 64))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def water_depth_ramp_png() -> bytes:
    """256 x 1 teal -> deep green-black ramp (design §5.2), stored 4 px tall."""

    width = 256
    t = np.linspace(0.0, 1.0, width)
    r = (34 + 26 * (1 - t)).astype(np.uint8)
    g = (86 + 62 * (1 - t)).astype(np.uint8)
    b = (84 + 54 * (1 - t)).astype(np.uint8)
    a = (70 + 185 * t).astype(np.uint8)
    rgba = np.stack([r, g, b, a], axis=-1)[None, :, :]
    return cook.png_bytes(np.repeat(rgba, 4, axis=0), "RGBA")


# --- info / scenario -------------------------------------------------------------------------


def info_document(spec: terrain.TerrainSpec) -> dict[str, Any]:
    extent = round(spec.extent_m)
    spawn_names = [SPAWN_SOUTH] + [f"{LEVEL_ID}{row['name']}" for row in layout()["spawns"]]
    labels = {
        SPAWN_SOUTH: "South apron",
        f"{LEVEL_ID}_spawn_trailhead": "Trailhead",
        f"{LEVEL_ID}_spawn_lakeshore": "Kettle Lake shore",
        f"{LEVEL_ID}_spawn_firewood_gap": "Firewood Gap",
    }
    previews = sorted(preview_pngs())
    return {
        "title": "Giant's Hearth",
        "description": (
            "A giant's campfire in a granite basin at the last light of the day: the Gateway "
            "Skillet sits bedded in a ring of coals the size of a village, with a trail that "
            "climbs out over the Firewood Gap. Drive the hearth, race the ember ring, or "
            "leave the coals for Kettle Lake - the fire is going out and the potato is still "
            "hot."
        ),
        "previews": previews,
        "size": [extent, extent],
        "biome": "alpine basin, conifer forest, lake",
        "roads": "campsite loop, one trail out",
        "suitablefor": "Hot Potato rounds, hillclimb, photo mode",
        "features": "giant campfire, night lights, lake",
        "authors": "Eric Rolph",
        "defaultSpawnPointName": SPAWN_SOUTH,
        "spawnPoints": [
            {
                "objectname": name,
                "preview": previews[0],
                "translationId": labels[name],
            }
            for name in spawn_names
        ],
        "minimap": [
            {
                "file": f"minimap/{LEVEL_ID}_minimap.png",
                "size": [extent, extent],
                "offset": [spec.position[0], spec.position[1] + spec.extent_m],
            }
        ],
        "supportsTraffic": True,
        "supportsTimeOfDay": True,
        "defaultDate": {"year": 2026, "month": 6, "day": 20},
    }


def probe_scenario_document() -> list[dict[str, Any]]:
    return [
        {
            "name": "Giant's Hearth: level probe",
            "description": (
                "One car on the hearth slab's south spawn. Pipeline probe; not the "
                "Hot Potato scenario."
            ),
            "difficulty": 0,
            "authors": "Eric Rolph",
            "lapConfig": [],
            "forceNoCountDown": True,
            "vehicles": {PROBE_PLAYER: {"playerUsable": True, "startFocus": True}},
            "prefabs": [],
        }
    ]


def probe_prefab_records() -> list[dict[str, Any]]:
    return [
        {
            "name": PROBE_PLAYER,
            "class": "BeamNGVehicle",
            "persistentId": persistent_id(PROBE_PLAYER),
            "__parent": PROBE_GROUP,
            "position": spawn_position(),
            "dataBlock": "default_vehicle",
            "jBeam": "etk800",
            "licenseText": "PROBE",
            "rotationMatrix": engine_yaw_matrix(180.0),
            "autoEnterVehicle": "false",
        },
        {
            "name": PROBE_GROUP,
            "class": "SimGroup",
            "persistentId": persistent_id(PROBE_GROUP),
            "groupPosition": "0.000000 0.000000 0.000000",
        },
    ]


# --- render everything ---------------------------------------------------------------------------


def dae_members() -> tuple[str, ...]:
    """Shapes produced by Blender (not by this module): the backdrop + B3's forest.

    A sibling ``.cdae`` rides along when one is staged in the tree. QB-8 ("every DAE
    ships a sibling .cdae") is a stock item that all twelve stock levels pass, and the
    engine cooks the file itself into ``temp/levels/<id>/`` on first load - so the way
    to ship one is to HARVEST it from a boot, exactly as design §4.3 harvests imposters.
    B1's live gate copies it out (``cdae_harvest`` in the boot evidence) and it is
    checked into the tree next to the DAE it was cooked from.
    """

    members = [f"{BACKDROP_DIR}/{backdrop.BACKDROP_DAE_NAME}"]
    cooked = LEVEL_ROOT / BACKDROP_DIR / f"{backdrop.BACKDROP_DAE_NAME.removesuffix('.dae')}.cdae"
    if cooked.is_file():
        members.append(f"{BACKDROP_DIR}/{cooked.name}")
    if forest_build.available():
        members.extend(forest_build.dae_members())
    if props_build.available():
        members.extend(props_build.dae_members())
    return tuple(sorted(members))


def _existing_decal_instances(root: Path = LEVEL_ROOT) -> dict[str, Any]:
    """Every decal key already on disk, so this writer never destroys a foreign round's.

    B1 authors no static decals. Returning `{}` unconditionally — which is what this
    writer did through r7 — deletes B2's 619 hearth rows and B4's trail dressing every
    time the level is re-rendered, silently: the level loads, nothing errors, the ground
    is simply bare. Missing or unreadable file means there is nothing to carry.
    """
    target = root / "main.decals.json"
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    instances = document.get("instances")
    return instances if isinstance(instances, dict) else {}


def render_level(spec: terrain.TerrainSpec = terrain.DEFAULT_SPEC) -> dict[str, bytes]:
    """Every SCENE file as bytes keyed by path relative to the level root.

    The cooked CC0 textures and the Blender DAE are NOT here; they are carried
    into the archive through ``cook_terrain_textures``'s manifest and
    ``dae_members()``.
    """

    heights, layers = terrain.build_heightmap(spec)
    previews = preview_pngs()
    groups = mission_group_records()
    outputs: dict[str, bytes] = {
        "info.json": _json(info_document(spec)),
        f"{TERRAIN_STEM}.ter": terrain.write_ter_bytes(heights, layers, spec.materials),
        f"{TERRAIN_STEM}.terrain.json": _json(terrain.terrain_sidecar(spec, TER_PATH)),
        f"{TERRAIN_STEM}.ter.depth.png": cook.png_bytes(terrain.depth_map_png_array(spec), "L"),
        "main.decals.json": _json(
            {
                "header": {
                    "name": "DecalData File",
                    "comments": (
                        "Instances format: rectIdx, size, renderPriority, position.x, "
                        "position.y, position.z, normal.x, normal.y, normal.z, tangent.x, "
                        "tangent.y, tangent.z, uid"
                    ),
                    "version": 2,
                },
                # B1 authors NO static decals, so this writer must never destroy the ones
                # other rounds author. `main.decals.json` is shared: B2 owns 12 keys / 619
                # rows (hearth soot, skids, oil, ash drift), B4 owns the trail dressing.
                # Emitting a bare `{}` here silently wiped all 619 of B2's rows out of the
                # working tree at 12:26 today — the level still loads, nothing errors, and
                # the ground is simply clean. Carry every existing key forward instead; a
                # round that owns keys replaces only its own (see place_hearth._merge).
                "instances": _existing_decal_instances(),
            }
        ),
        "art/terrains/main.materials.json": _json(terrain_materials_document()),
        f"{cook.ROAD_DIR}/main.materials.json": _json(road_materials_document()),
        f"{cook.ROAD_DIR}/{LEVEL_ID}_t_road_invisible.color.png": road_invisible_png(),
        f"{BACKDROP_DIR}/{LEVEL_ID}_backdrop.materials.json": _json(backdrop_materials_document()),
        f"groundModels/{LEVEL_ID}_groundmodels.json": _json(groundmodels_document()),
        f"art/water/{LEVEL_ID}_depth_ramp.png": water_depth_ramp_png(),
        f"minimap/{LEVEL_ID}_minimap.png": minimap_png(),
        f"scenarios/{PROBE_ID}/{PROBE_ID}.json": _json(probe_scenario_document()),
        f"scenarios/{PROBE_ID}/{PROBE_ID}.prefab.json": _jsonl(probe_prefab_records()),
        f"scenarios/{PROBE_ID}/{PROBE_ID}.jpg": probe_thumbnail_jpg(
            previews[f"{LEVEL_ID}_preview.png"]
        ),
        "main/MissionGroup/level_objects/terrain/items.level.json": _jsonl(terrain_records(spec)),
        "main/MissionGroup/level_objects/sky_and_sun/items.level.json": _jsonl(sky_records()),
        "main/MissionGroup/level_objects/vegetation/items.level.json": _jsonl(vegetation_records()),
        "main/MissionGroup/level_objects/Water/items.level.json": _jsonl(water_records()),
        "main/MissionGroup/level_objects/backdrop/items.level.json": _jsonl(backdrop_records()),
        f"main/MissionGroup/level_objects/{shelf_road.GROUP_NAME}/items.level.json": _jsonl(
            shelf_road_records()
        ),
        f"{BACKDROP_DIR}/{shelf_road.ROAD_NAME}.materials.json": _json(
            shelf_road.materials_document()
        ),
        "main/MissionGroup/PlayerDropPoints/items.level.json": _jsonl(spawn_records()),
        "main/MissionGroup/CameraBookmarks/items.level.json": _jsonl(camera_records()),
        "main/MissionGroup/AIWaypointsGroup/items.level.json": b"",
        "main/MissionGroup/AIDecalWaypointsGroup/items.level.json": _jsonl(ai_road_records()),
        "main/MissionGroup/decal_road/items.level.json": _jsonl(
            [*visible_road_records(), *shelf_approach_records()]
        ),
    }
    outputs.update(previews)
    if forest_build.available():
        # B3 owns art/forest, the vegetation group and the forest's shape materials; its DAEs,
        # cooked maps and forest4 instance files ride in through expected_level_members().
        outputs.update(forest_build.rendered_outputs())
    if props_build.available():
        # B4 owns the props group, the four .prefab cluster files and the props materials;
        # its DAEs and cooked maps ride in through expected_level_members().
        outputs.update(props_build.rendered_outputs())
    for path, records in groups.items():
        outputs[path] = _jsonl(records)
    for path, payload in outputs.items():
        if path.endswith(".json") and b"\r" in payload:
            raise LevelWriteError(f"CR byte in generated text output: {path}")
        if (
            not path.startswith(
                ("main/", "art/", "forest/", "minimap/", "scenarios/", "groundModels/")
            )
            and "/" in path
        ):
            raise LevelWriteError(f"unexpected output directory: {path}")
    return outputs


def expected_level_members() -> tuple[str, ...]:
    """Archive members (relative to the mod root): scene files + cooked art + the DAE."""

    rendered = [f"{LEVEL_RELATIVE}/{path}" for path in render_level()]
    cooked = [f"{LEVEL_RELATIVE}/{path}" for path in cook.cooked_members()]
    daes = [f"{LEVEL_RELATIVE}/{path}" for path in dae_members()]
    forest = (
        [f"{LEVEL_RELATIVE}/{path}" for path in forest_build.bulk_members(LEVEL_ROOT)]
        if forest_build.available()
        else []
    )
    props = (
        [f"{LEVEL_RELATIVE}/{path}" for path in props_build.bulk_members(LEVEL_ROOT)]
        if props_build.available()
        else []
    )
    members = sorted({*rendered, *cooked, *daes, *forest, *props})
    overlap = set(rendered) & set(cooked)
    if overlap:
        raise LevelWriteError(f"a cooked texture collides with a scene file: {sorted(overlap)}")
    return tuple(members)


def decal_road_census() -> dict[str, int]:
    census: dict[str, int] = {}
    for record in ai_road_records() + visible_road_records():
        census[str(record["material"])] = census.get(str(record["material"]), 0) + 1
    census["total"] = sum(census.values())
    return census


def level_manifest(outputs: dict[str, bytes]) -> dict[str, Any]:
    spec = terrain.TerrainSpec()
    heights, layers = terrain.build_heightmap(spec)
    design_lock = json.loads(DESIGN_LOCK_PATH.read_text(encoding="utf-8"))
    return {
        "level_id": LEVEL_ID,
        "design_lock": design_lock,
        "terrain": terrain.heightmap_summary(spec, heights, layers),
        "ter_bytes": terrain.ter_member_size(spec),
        "decal_roads": decal_road_census(),
        "spawns": [record["name"] for record in spawn_records()],
        "cameras": [record["name"] for record in camera_records()],
        "tod_clock": TOD_CLOCK,
        "fog_density": FOG_DENSITY,
        "water_z": WATER_Z,
        "files": len(outputs),
        "bytes": sum(len(v) for v in outputs.values()),
        "sha256": {
            path: hashlib.sha256(payload).hexdigest() for path, payload in sorted(outputs.items())
        },
    }


def write_level(root: Path = LEVEL_ROOT, *, check_only: bool = False) -> dict[str, Any]:
    outputs = render_level()
    written: list[str] = []
    stale: list[str] = []
    for relative, payload in sorted(outputs.items()):
        target = root / relative
        if target.exists() and target.read_bytes() == payload:
            continue
        if check_only:
            stale.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        written.append(relative)
    missing_daes = [path for path in dae_members() if not (root / path).is_file()]
    manifest = level_manifest(outputs)
    manifest["written"] = written
    manifest["stale"] = stale
    manifest["missing_daes"] = missing_daes
    manifest["stale_textures"] = cook.verify_tree(root)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="verify the tree matches the render; write nothing"
    )
    parser.add_argument("--root", type=Path, default=LEVEL_ROOT)
    arguments = parser.parse_args(argv)
    manifest = write_level(arguments.root, check_only=arguments.check)
    summary = {k: v for k, v in manifest.items() if k not in {"sha256", "terrain", "design_lock"}}
    print(json.dumps(summary, sort_keys=True))
    if arguments.check and (manifest["stale"] or manifest["stale_textures"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
