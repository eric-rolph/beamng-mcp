"""Static gates for the Giant's Hearth level (terrain, materials, roads, packaging).

No simulator. The live proof is tests/test_hot_potato_level_scaffold_live.py.

Everything here is measured against the FROZEN design (v4): the height and paint
law is ``examples/hot_potato_arena/level/terrain_model.py``, vendored byte for
byte from the design spec and locked in ``authoring/level_design_v4.lock.json``,
and the road node lists / cameras / spawns come from the equally vendored
``authoring/<id>.level_layout.json``. The relief law is re-measured from the
SHIPPED ``.ter`` bytes, not from the model in memory.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import uuid
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from examples.hot_potato_arena.level import blender_backdrop as backdrop
from examples.hot_potato_arena.level import brink, forest_build, hearth_build, terrain_model
from examples.hot_potato_arena.level import cook_terrain_textures as cook
from examples.hot_potato_arena.level import level_writer as writer
from examples.hot_potato_arena.level import terrain_io as terrain

LEVEL_ROOT = writer.LEVEL_ROOT
NAMESPACE = writer.LEVEL_ID
STOCK_NAMES = {
    "MissionGroup",
    "level_objects",
    "terrain",
    "vegetation",
    "Water",
    "sky_and_sun",
    "backdrop",
    "decal_road",
    "PlayerDropPoints",
    "CameraBookmarks",
    "AIWaypointsGroup",
    "AIDecalWaypointsGroup",
    "theTerrain",
    "theForest",
    "tod",
    "sunsky",
    "theLevelInfo",
    "clouds",
}
#: design v4 §2.7: |z[i-1] - 2 z[i] + z[i+1]| <= 20 mm on every drivable line.
RELIEF_LAW_M = terrain_model.RELIEF_LAW_M


@pytest.fixture(scope="module")
def spec() -> terrain.TerrainSpec:
    return terrain.TerrainSpec()


@pytest.fixture(scope="module")
def heightmap(spec):
    return terrain.build_heightmap(spec)


@pytest.fixture(scope="module")
def rendered():
    return writer.render_level()


@pytest.fixture(scope="module")
def shipped_ter(spec):
    """The heightmap read back OUT of the shipped .ter bytes (not the model in memory)."""

    path = LEVEL_ROOT / f"{writer.TERRAIN_STEM}.ter"
    if not path.is_file():
        pytest.skip("level tree not generated yet")
    size, heights, layers, materials = terrain.read_ter(path)
    return size, heights, layers, materials


def _records(payload: bytes) -> list[dict]:
    return [json.loads(line) for line in payload.decode("utf-8").splitlines()]


# --- the frozen design is the source ---------------------------------------------------


def test_terrain_model_is_the_frozen_design_byte_for_byte() -> None:
    lock = json.loads(writer.DESIGN_LOCK_PATH.read_text(encoding="utf-8"))
    model = Path(terrain_model.__file__)
    layout = writer.LAYOUT_PATH
    assert hashlib.sha256(model.read_bytes()).hexdigest()[:16] == lock["files"]["terrain_model.py"]
    assert hashlib.sha256(layout.read_bytes()).hexdigest()[:16] == lock["files"]["layout.json"]
    summary = writer.EXAMPLE_ROOT / "authoring" / f"{NAMESPACE}.terrain_summary.json"
    assert (
        hashlib.sha256(summary.read_bytes()).hexdigest()[:16]
        == lock["files"]["terrain_summary.json"]
    )
    assert b"\r" not in model.read_bytes()
    assert b"\r" not in layout.read_bytes()


def test_the_shipped_ter_is_what_the_frozen_design_derives(spec, heightmap, shipped_ter) -> None:
    """critic r10 N10-5: the named assurance was not the one that held.

    Three revisions have written "``theTerrain.ter`` ships the design's map and
    ``test_terrain_model_is_the_frozen_design_byte_for_byte`` still asserts it", and B1 r10's
    Kettle Lake argument - that the waterline can only move if the BASIN moves - leans on
    the phrase "byte-for-byte". That test hashes ``terrain_model.py``, ``layout.json`` and
    ``terrain_summary.json``. **No test hashed the shipped ``.ter`` against anything.** The
    chain was frozen source plus deterministic derivation plus four structural tests, which
    is a good chain and is not the named one.

    This is the named one: re-derive the heightmap and the layer map from the frozen model
    and require the SHIPPED bytes to equal them, element for element.
    """

    derived_heights, derived_layers = heightmap
    size, heights, layers, _materials = shipped_ter
    assert size == spec.size
    assert heights.shape == derived_heights.shape
    assert layers.shape == derived_layers.shape
    assert int((heights != derived_heights).sum()) == 0
    assert int((layers != derived_layers).sum()) == 0


def test_world_frame_matches_the_design(spec) -> None:
    assert spec.size == 2048
    assert spec.square_size == 1.0
    assert spec.position == (-174.0, -1304.0, 0.0)
    assert spec.max_height == 320.0
    # 5/1024 m exactly, binary-exact in float32, and 100.000 = u 20480 exactly.
    assert spec.unit_m == 5.0 / 1024.0
    assert float(spec.units_to_height(terrain.U_FLOOR)) == 100.0
    assert int(spec.height_to_units(100.0)) == 20480
    assert terrain.CENTER == (850.0, -280.0, 100.0)
    # QB-1b: the step is <= 5 mm.
    assert spec.unit_m * 1000.0 == pytest.approx(4.8828125)


# --- .ter format and exactness --------------------------------------------------------


def test_ter_round_trip_is_byte_exact(tmp_path: Path, spec, heightmap) -> None:
    heights, layers = heightmap
    payload = terrain.write_ter_bytes(heights, layers, spec.materials)
    path = tmp_path / "round.ter"
    path.write_bytes(payload)
    size, back_heights, back_layers, materials = terrain.read_ter(path)
    assert size == spec.size
    assert materials == list(spec.materials)
    assert np.array_equal(back_heights, heights)
    assert np.array_equal(back_layers, layers)
    assert len(payload) == terrain.ter_member_size(spec)
    assert len(payload) == 5 + 3 * spec.size**2 + 4 + sum(1 + len(n) for n in spec.materials)


def test_shipped_ter_carries_the_design_grid(shipped_ter, spec) -> None:
    size, heights, _layers, materials = shipped_ter
    assert size == 2048
    assert materials == list(terrain.MATERIALS) == list(terrain_model.LAYERS)
    assert int(heights.min()) == 17604 and int(heights.max()) == 56726  # design §2.7
    assert int((heights == 65535).sum()) == 0  # the 319.995 ceiling is never reached


def test_flat_disc_is_exactly_100_000_out_to_r_210(shipped_ter, spec) -> None:
    """Design §2.7: 138,505 nodes at exactly u 20480 inside r 210."""

    _, heights, _, _ = shipped_ter
    index = np.arange(spec.size, dtype=np.float64)
    xs = spec.position[0] + index
    ys = spec.position[1] + index
    grid_x, grid_y = np.meshgrid(xs, ys)
    r, _ = terrain.polar(grid_x, grid_y)
    disc = r <= terrain.FLAT_RADIUS_M
    assert int(disc.sum()) == 138505
    assert np.unique(heights[disc]).tolist() == [terrain.U_FLOOR]
    assert float(spec.units_to_height(terrain.U_FLOOR)) == 100.0


def _second_difference_report(z: np.ndarray, mask: np.ndarray) -> dict[str, float]:
    diffs = terrain.second_differences(z)
    with np.errstate(all="ignore"):
        both = np.where(np.isnan(diffs).all(axis=0), 0.0, np.nan_to_num(diffs, nan=0.0).max(axis=0))
    values = both[mask & np.isfinite(both)]
    return {
        "cells": int(values.size),
        "max_mm": float(values.max() * 1000.0) if values.size else 0.0,
        "over_law": int((values > RELIEF_LAW_M).sum()),
    }


def test_relief_law_holds_on_every_drivable_line(shipped_ter, spec) -> None:
    """Design §2.7: second differences <= 20 mm on the apron, track, trail and runouts."""

    _, heights, _, _ = shipped_ter
    z = np.asarray(spec.units_to_height(heights.astype(np.int64)), dtype=np.float64)
    grid = terrain.grid()
    index = np.arange(spec.size, dtype=np.float64)
    grid_x, grid_y = np.meshgrid(spec.position[0] + index, spec.position[1] + index)
    r, theta = terrain.polar(grid_x, grid_y)
    trail_d = np.asarray(grid["trail_d"], dtype=np.float64)
    lane = np.zeros_like(r, dtype=bool)
    for centre in terrain_model.LANE_CENTRES:
        lane |= np.abs((theta - centre + 180.0) % 360.0 - 180.0) <= terrain_model.LANE_HALF
    zones = {
        "graded_apron_210_350": (r > 210.0) & (r <= 350.0),
        "track_band_248_pm4": np.abs(r - terrain_model.TRACK_R) <= 4.0,
        "trail_corridor_3m": trail_d <= 3.0,
        "trail_corridor_4m": trail_d <= 4.0,
        "trail_corridor_6m": trail_d <= 6.0,
        "everything_inside_350": r <= 350.0,
        "lane_runouts_350_420": (r > 350.0) & (r <= 420.0) & lane,
    }
    report = {name: _second_difference_report(z, mask) for name, mask in zones.items()}
    for name, row in report.items():
        assert row["cells"] > 0, (name, row)
        assert row["over_law"] == 0, (name, row, report)
        assert row["max_mm"] <= RELIEF_LAW_M * 1000.0, (name, row)
    # the residual is the 4.88 mm quantisation: two units = 9.77 mm
    assert report["everything_inside_350"]["max_mm"] == pytest.approx(9.7656, abs=0.01)


def test_depth_png_is_a_real_map_at_terrain_resolution(rendered, spec) -> None:
    payload = rendered[f"{writer.TERRAIN_STEM}.ter.depth.png"]
    with Image.open(io.BytesIO(payload)) as image:
        assert image.size == (spec.size, spec.size)
        assert image.mode == "L"
        array = np.asarray(image)
    # 255 everywhere dry (B0: that alone removes the D line), a gradient on the lake bed
    assert int(array.max()) == 255
    assert int(array.min()) < 255
    assert float((array == 255).mean()) > 0.9


# --- terrain materials and ground models -----------------------------------------------


def test_eleven_terrain_materials_carry_every_tex_slot(rendered) -> None:
    document = json.loads(rendered["art/terrains/main.materials.json"])
    sets = [v for v in document.values() if v["class"] == "TerrainMaterialTextureSet"]
    assert len(sets) == 1 and sets[0]["name"] == writer.TEXTURE_SET
    assert sets[0]["baseTexSize"] == [4096, 4096]
    assert sets[0]["detailTexSize"] == [1024, 1024]
    assert sets[0]["macroTexSize"] == [1024, 1024]
    by_layer = {v["internalName"]: v for v in document.values() if v["class"] == "TerrainMaterial"}
    assert len(by_layer) == 11
    # the .ter layer table's order IS the design's; the JSON document is sorted by key
    assert set(by_layer) == set(terrain.MATERIALS)
    materials = [by_layer[layer] for layer in terrain.MATERIALS]
    # QB-5: >= 8 materials, >= 5 distinct ground models (the design ships 10 of them).
    models = {m["groundmodelName"] for m in materials}
    assert len(models) == 10
    assert models == {
        "ASPHALT",
        "ERHP_ASH",
        "ERHP_SCORCH",
        "ERHP_TRAIL",
        "GRASS",
        "ERHP_FOREST_FLOOR",
        "GRAVEL",
        "ROCK",
        "SAND",
        "MUD",
    }
    for entry in materials:
        layer = entry["internalName"]
        # r3 (critic r2 B-4): the far bands are no longer zeroed, so the gate is the
        # STOCK band measured over eight reference levels' terrain materials rather
        # than a literal - detail out to [0, 0, 100, 200] (small_island ships exactly
        # that), macro saturating between 50 and 1000 m, far DETAIL strength usually 0
        # and far MACRO strength non-zero (roughnessMacro [0.15, 0.8] is stock).
        assert entry["detailDistances"] == list(writer.DETAIL_DISTANCES)
        assert entry["macroDistances"] == list(writer.MACRO_DISTANCES)
        assert entry["detailDistances"][:2] == [0, 0]
        assert 15 <= entry["detailDistances"][2] <= 100
        assert entry["detailDistances"][2] < entry["detailDistances"][3] <= 3000
        assert 50 <= entry["macroDistances"][2] <= 1000
        assert entry["macroDistances"][3] >= 400
        for field in ("baseColorMacroStrength", "normalMacroStrength", "roughnessMacroStrength"):
            assert entry[field][1] > 0.0, (field, entry[field])
            assert entry[field][1] <= 1.2, (field, entry[field])
        # r4 (critic r3 B3-3): far DETAIL is non-zero too, and the r3 claim that stock
        # "usually" zeroes it was false - re-derived over the same 104 stock materials it
        # is non-zero on 51.9 % (baseColor), 51.9 % (normal) and 76.2 % (roughness).
        # These three values are shipped VERBATIM by small_island materials that also
        # ship our exact detailDistances [0, 0, 100, 200]: dirt_loose baseColorDetail
        # [0.35, 0.35], Rock and dirt_rocky_large roughnessDetail [0.3, 0.3]; normal's
        # far is the stock non-zero median 0.15.
        for field in (
            "baseColorDetailStrength",
            "normalDetailStrength",
            "roughnessDetailStrength",
        ):
            assert entry[field][1] > 0.0, (field, entry[field])
        assert entry["baseColorDetailStrength"] == [0.35, 0.35]
        assert entry["roughnessDetailStrength"] == [0.3, 0.3]
        assert entry["normalDetailStrength"][1] == 0.15
        for channel in ("baseColor", "normal", "roughness", "ao", "height"):
            for band in ("Base", "Detail", "Macro"):
                relative = entry[f"{channel}{band}Tex"].removeprefix(f"/levels/{NAMESPACE}/")
                assert relative in cook.load_manifest()["files"], relative
                assert (LEVEL_ROOT / relative).is_file(), relative
            # QB-3 / QB-4b: every slot is SIZED, and the detail tile is 2-4 m.
            assert entry[f"{channel}BaseTexSize"] == 2048.0
            assert entry[f"{channel}DetailTexSize"] == cook.DETAIL_SOURCES[layer].tile_m
            assert entry[f"{channel}MacroTexSize"] == cook.MACRO_SOURCES[layer].tile_m
        # QB-4: far detail strength p90 <= 0.5, macro tile 20-100 m
        assert entry["baseColorDetailStrength"][1] <= 0.5
        assert 2.0 <= cook.DETAIL_SOURCES[layer].tile_m <= 4.0
        assert 20.0 <= cook.MACRO_SOURCES[layer].tile_m <= 100.0


def test_level_ground_models_have_no_isalias_and_the_measured_coefficients(rendered) -> None:
    document = json.loads(rendered[f"groundModels/{NAMESPACE}_groundmodels.json"])
    assert set(document) == {"ERHP_ASH", "ERHP_SCORCH", "ERHP_TRAIL", "ERHP_FOREST_FLOOR"}
    for name, fields in document.items():
        # B0: "isAlias" logs an E line per model; it is dropped from the field set.
        assert "isAlias" not in fields, name
        assert len(name) <= 31, name
        assert fields["collisiontype"] in {"DIRT", "DIRT_DUSTY", "GRASS"}
    assert document["ERHP_ASH"]["staticFrictionCoefficient"] == 0.66
    assert document["ERHP_SCORCH"]["slidingFrictionCoefficient"] == 0.70
    assert document["ERHP_TRAIL"]["collisiontype"] == "DIRT"
    assert document["ERHP_FOREST_FLOOR"]["staticFrictionCoefficient"] == 0.60


def test_layer_coverage_matches_the_design_table(shipped_ter) -> None:
    """Design §2.4/§2.7: eleven layers, each >= 0.5 % of the block (min trail 0.70 %).

    Amendment A1 (2026-09-15, ``authoring/design_amendments.md``): the r16 brink repaint
    moves 118,014 nodes ``forest_floor`` -> ``scree`` / ``rock`` at the block's edge, so the
    table now reads forest_floor 66.14, scree 4.03, rock 10.29 (was 69.0 / 2.16 / 9.35). The
    tolerances are the ORIGINAL ones - the numbers changed, not the gate's width - and the
    eight untouched layers keep their design values to the same +-0.02.
    """

    _, _, layers, _ = shipped_ter
    total = layers.size
    percent = {
        name: float((layers == index).sum()) / total * 100.0
        for index, name in enumerate(terrain.MATERIALS)
    }
    assert min(percent.values()) >= 0.5, percent
    assert percent["trail"] == pytest.approx(0.70, abs=0.02), percent
    assert percent["forest_floor"] == pytest.approx(66.14, abs=0.1), percent
    assert percent["scree"] == pytest.approx(4.03, abs=0.02), percent
    assert percent["hearth"] == pytest.approx(2.29, abs=0.02), percent
    assert percent["ash"] == pytest.approx(0.90, abs=0.02), percent
    assert percent["scorch"] == pytest.approx(1.42, abs=0.02), percent
    assert percent["meadow"] == pytest.approx(8.73, abs=0.02), percent
    assert percent["rock"] == pytest.approx(10.29, abs=0.02), percent
    assert percent["lakebed"] == pytest.approx(2.97, abs=0.02), percent


# --- the cooked CC0 art ------------------------------------------------------------------


def test_base_set_is_4096_at_half_a_metre_per_texel(spec) -> None:
    manifest = cook.load_manifest()
    for role, mode in (("b", "RGB"), ("nm", "RGB"), ("r", "L"), ("ao", "L"), ("h", "L")):
        relative = cook.base_texture_relative(role)
        assert relative in manifest["files"]
        path = LEVEL_ROOT / relative
        with Image.open(path) as image:
            assert image.size == (4096, 4096), relative
            assert image.mode == mode, relative
    # 2,048 m over 4,096 texels = 0.5 m/texel (the WCUSA / small_island class).
    assert spec.extent_m / 4096.0 == 0.5


def test_base_set_carries_real_information_at_all_4096_rows() -> None:
    """critic r1 D-6: r1's ``np.repeat`` made every odd row equal its even neighbour.

    The map was a 2048^2 image stored at 4096^2, so its real density was 1.0 m/texel,
    not the 0.5 the header claims. Every role is now resampled or sampled at the true
    grid, so no row pair is identical anywhere in the set.
    """

    for role in cook.ROLES:
        with Image.open(LEVEL_ROOT / cook.base_texture_relative(role)) as image:
            data = np.asarray(image, dtype=np.float32)
        rows = np.abs(data[0::2] - data[1::2]).mean()
        cols = np.abs(data[:, 0::2] - data[:, 1::2]).mean()
        assert rows > 0.05, (role, float(rows))
        assert cols > 0.05, (role, float(cols))


#: Measured on the five reference maps' own ``t_terrain_base_b.png`` by the round-1
#: critic's ``base_entropy.py`` (2048^2 centre crop, luma): west_coast_usa / italy /
#: johnson_valley / east_coast_usa / small_island. The gate is the reference BAND.
REFERENCE_BASE_SIGMA_LOCAL8 = (0.01588, 0.02997)
REFERENCE_BASE_SIGMA_GLOBAL = (0.03685, 0.07988)
REFERENCE_BASE_COLOURS = (5559, 34361)


def test_base_albedo_detail_lands_in_the_reference_band() -> None:
    """critic r1 D-2: r1 was 11 flat colours x a hillshade.

    sigma_local(8x8) was 0.0022 against the references' 0.0159-0.0300 and the
    high-frequency share 0.00098 against 0.092-0.483, while sigma_global was the
    HIGHEST of the six. The composite must stay inside the band on all three.
    """

    payload = (LEVEL_ROOT / cook.base_texture_relative("b")).read_bytes()
    with Image.open(io.BytesIO(payload)) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    crop = 2048
    y0 = x0 = (rgb.shape[0] - crop) // 2
    sub = rgb[y0 : y0 + crop, x0 : x0 + crop]
    luma = (0.2126 * sub[..., 0] + 0.7152 * sub[..., 1] + 0.0722 * sub[..., 2]) / 255.0
    blocks = luma.reshape(crop // 8, 8, crop // 8, 8)
    sigma_local8 = float(blocks.std(axis=(1, 3)).mean())
    sigma_global = float(luma.std())
    flat = sub.astype(np.uint8).reshape(-1, 3)
    packed = (flat[:, 0].astype(np.uint32) << 16) | (flat[:, 1].astype(np.uint32) << 8) | flat[:, 2]
    colours = int(np.unique(packed).size)

    assert REFERENCE_BASE_SIGMA_LOCAL8[0] <= sigma_local8 <= REFERENCE_BASE_SIGMA_LOCAL8[1], (
        sigma_local8
    )
    assert REFERENCE_BASE_SIGMA_GLOBAL[0] <= sigma_global <= REFERENCE_BASE_SIGMA_GLOBAL[1], (
        sigma_global
    )
    assert REFERENCE_BASE_COLOURS[0] <= colours <= REFERENCE_BASE_COLOURS[1], colours
    # the whole set against the design's ~69 MB budget (r1 shipped 9.6 MB)
    total = sum(
        (LEVEL_ROOT / cook.base_texture_relative(role)).stat().st_size for role in cook.ROLES
    )
    assert 55_000_000 <= total <= 85_000_000, total


def test_crevice_warmth_is_luma_neutral_and_only_touches_crevices() -> None:
    """r5 / critic r4 N4-1: the burnt disc's blue veins, and the shape of the fix.

    The certified r4 AERIAL rendered the hearth/scorch crack network as indigo filaments
    (b* < 0 on 3.72 % of the inner disc, min -8.62, against r3's 0.00 % / -0.30) while
    the shipped ALBEDO has 0.00 % negative b* and a min of +0.84 in every round - so the
    hue is the shading's, not the paint's, and no albedo instrument in r1-r4 could see
    it (``b1/r5/probe/hue_in_frame.py`` carries both halves).

    The counter is a luma-NEUTRAL warm chroma added in proportion to how far the
    composite's own modulation has fallen below 1, i.e. in the cracks and nowhere else.
    Two properties have to hold or the fix becomes a tint: the warm axis must carry no
    luma of its own (the cook subtracts it, this pins the intent), and the amount must
    stay small enough that the burnt layers keep the neutral ground N3-4 asked for.
    """

    direction = np.array(cook.BASE_CREVICE_WARM_DIR, dtype=np.float64)
    # warm means red up and blue down, and the two must be able to cancel in luma
    assert direction[0] > 0.0 > direction[2]
    shift = direction - cook._luma(direction)
    assert abs(float(cook._luma(shift))) < 1e-12, shift
    assert 0.0 < cook.BASE_CREVICE_WARMTH <= 0.15
    assert 0.10 <= cook.BASE_CREVICE_KNEE <= 1.0


def test_base_albedo_is_the_right_way_up(shipped_ter) -> None:
    """critic r1 U3: the base map's ORIENTATION, measured instead of argued.

    Builds the expected tone field straight from the shipped layer map and the
    per-layer palette, then correlates it against the shipped albedo under all eight
    dihedral transforms. The identity must win outright: a flip or a transpose would
    move the lake's pale bed out of the WNW quadrant.
    """

    _size, _heights, layers, _materials = shipped_ter
    palette = cook.layer_albedo(
        {
            cook.terrain_texture_relative(name, "detail", "b"): (
                LEVEL_ROOT / cook.terrain_texture_relative(name, "detail", "b")
            ).read_bytes()
            for name in terrain.MATERIALS
        }
    )
    stacked = np.stack([palette[name] for name in terrain.MATERIALS], axis=0)
    expected = np.asarray(
        Image.fromarray(np.clip(stacked[layers] * 255.0, 0, 255).astype(np.uint8)[::-1]).resize(
            (256, 256), Image.BOX
        ),
        dtype=np.float32,
    )
    expected = 0.2126 * expected[..., 0] + 0.7152 * expected[..., 1] + 0.0722 * expected[..., 2]
    with Image.open(LEVEL_ROOT / cook.base_texture_relative("b")) as image:
        actual = np.asarray(image.convert("RGB").resize((256, 256), Image.BOX), dtype=np.float32)
    actual = 0.2126 * actual[..., 0] + 0.7152 * actual[..., 1] + 0.0722 * actual[..., 2]

    def score(candidate: np.ndarray) -> float:
        a = candidate - candidate.mean()
        b = actual - actual.mean()
        return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum()))

    scores = {
        "identity": score(expected),
        "flip_rows": score(expected[::-1]),
        "flip_cols": score(expected[:, ::-1]),
        "rot180": score(expected[::-1, ::-1]),
        "transpose": score(expected.T),
        "transpose_flip_rows": score(expected.T[::-1]),
        "transpose_flip_cols": score(expected.T[:, ::-1]),
        "rot180_transpose": score(expected.T[::-1, ::-1]),
    }
    best = max(scores, key=scores.get)
    runner_up = max(k for k in scores if k != "identity")
    assert best == "identity", scores
    # r4: the floor moves 0.70 -> 0.60 and the reason is stated rather than absorbed.
    # This correlation is between the shipped albedo and the PURE TONE FIELD, so it falls
    # as the map gains texture on top of that tone - which is the whole direction of the
    # round. Measured on the three certified cuts with this exact code: r2 0.7914 /
    # margin 0.2403, r3 0.7486 / 0.2188, r4 0.6996 / 0.2003. The ORIENTATION evidence is
    # the ranking and the margin, and both still hold with room; the absolute number is a
    # "the tone field is still recognisable in there" check and 0.60 keeps it meaningful
    # (a wrong orientation scores 0.50 at best on this map).
    assert scores["identity"] > 0.60, scores
    assert scores["identity"] - max(v for k, v in scores.items() if k != "identity") > 0.15, (
        scores,
        runner_up,
    )


def test_detail_and_macro_maps_are_1024_with_the_design_texel_density() -> None:
    manifest = cook.load_manifest()
    for layer in terrain.MATERIALS:
        for band, table in (("detail", cook.DETAIL_SOURCES), ("macro", cook.MACRO_SOURCES)):
            for role in cook.ROLES:
                relative = cook.terrain_texture_relative(layer, band, role)
                assert relative in manifest["files"], relative
                with Image.open(LEVEL_ROOT / relative) as image:
                    assert image.size == (1024, 1024), relative
            tile = table[layer].tile_m
            mm_per_texel = tile / 1024.0 * 1000.0
            if band == "detail":
                assert 1.9 <= mm_per_texel <= 4.0, (layer, mm_per_texel)


def test_every_cc0_derived_png_is_in_the_provenance_ledger() -> None:
    manifest = cook.load_manifest()
    ledger = json.loads(cook.PROVENANCE_PATH.read_text(encoding="utf-8"))
    assert "CC0" in ledger["license"]
    missing: list[str] = []
    for relative, row in manifest["files"].items():
        for source in row["cc0_files"]:
            if source not in ledger["files"]:
                missing.append(f"{relative} <- {source}")
    assert not missing, missing[:10]
    # every source the cook names is on disk with the ledger's byte count
    for row in manifest["files"].values():
        for source in row["cc0_files"]:
            entry = ledger["files"][source]
            assert entry["license"].startswith("CC0")
            assert entry["md5_published"]
            path = cook.CC0_CACHE / source
            if path.is_file():
                assert path.stat().st_size == entry["bytes"], source


def test_cooked_tree_matches_the_manifest_sha256() -> None:
    assert cook.verify_tree(LEVEL_ROOT) == []


def test_the_cook_is_deterministic() -> None:
    """Re-cook two representative maps and compare bytes against the shipped ones."""

    manifest = cook.load_manifest()
    again = cook.cook_source(cook.DETAIL_SOURCES["ash"], "detail:ash")
    payload = cook._encode("b", again["b"])
    relative = cook.terrain_texture_relative("ash", "detail", "b")
    assert hashlib.sha256(payload).hexdigest() == manifest["files"][relative]["sha256"]
    roads = cook.cook_roads()
    relative = cook.road_texture_relative("m_dirt_variation", "o")
    assert hashlib.sha256(roads[relative]).hexdigest() == manifest["files"][relative]["sha256"]


# --- roads --------------------------------------------------------------------------------


def test_decal_road_census_is_the_designs_112_as_r3_ships_it(rendered) -> None:
    """Design §2.3's 112, plus the SIX records B4 r2's single-variable A/B added.

    r2 closed ``KNOWN_DECAL_BATCHER_LINE`` by cutting every visible road that repeated its
    first node into two OPEN halves.  The track surface became ``_a`` + ``_b``, and the four
    overlay families that ran the whole loop with it had to be cut at the same station:
    variation 2 -> 3, bank erosion 4 -> 6, dust 2 -> 3.  This gate asserted 112 and failed
    from r2 until r3, so the per-family counts below have been unenforced for a revision.

    r3 then took two families the OTHER way.  The two offset 3.5 m tiretrack records per
    road became ONE centred 3.6 m record (the mask already paints a pair inside it), so
    tiretracks go 6 -> 3; and the pale ``m_track_dust_overlay`` came OFF the forest trail,
    where it was most of the "pale limestone haul road" critic pass 2 measured, so dust goes
    3 -> 2.  112 + 6 - 3 - 1 = 114, which is the 109 in ``decal_road/`` plus the 5 invisible
    AI roads in ``AIDecalWaypointsGroup/`` -- the split critic B4 pass 2 reconciled by hand.
    """

    census = writer.decal_road_census()
    assert census["total"] == 114
    assert census[writer.ROAD_INVISIBLE] == 5
    for key, count in (
        ("m_dirt_variation", 3),
        ("m_dirt_flows", 14),
        ("m_dirt_gravel", 9),
        ("m_dirt_tiretracks", 3),
        ("m_bank_erosion", 6),
        ("m_mud_cracks", 12),
        ("m_puddle_wet", 10),
        ("m_track_dust_overlay", 2),
        ("m_skid_arc", 40),
        ("m_needle_litter", 10),
    ):
        assert census[writer.road_material_name(key)] == count, key
    # the six extra records are SPLITS, not new content: the four overlay families and the
    # track surface each gained exactly one record, and nothing else moved
    assert (
        sum(
            census[writer.road_material_name(k)]
            for k in ("m_dirt_variation", "m_bank_erosion", "m_track_dust_overlay")
        )
        == 11
    )
    # QB-14: >= 10 road materials, all ours.
    materials = json.loads(rendered[f"{cook.ROAD_DIR}/main.materials.json"])
    assert len(materials) == 11
    for name, entry in materials.items():
        assert name.startswith(f"{NAMESPACE}_"), name
        assert entry["annotation"] == "STREET"
        assert entry["materialTag0"] == "RoadAndPath"
        assert entry["castShadows"] is False
    for key in cook.ROAD_SOURCES:
        stage = materials[writer.road_material_name(key)]["Stages"][0]
        # QB-14b: base + normal + roughness + ao + opacity on every visible layer.
        for field in (
            "baseColorMap",
            "normalMap",
            "roughnessMap",
            "ambientOcclusionMap",
            "opacityMap",
        ):
            relative = stage[field].removeprefix(f"/levels/{NAMESPACE}/")
            assert (LEVEL_ROOT / relative).is_file(), relative


def test_invisible_road_material_is_the_stock_recipe_exactly(rendered) -> None:
    """r4 / critic r3 B3-1: the "invisible" AI road material was NOT invisible.

    ``ai_connector_150`` runs out from the AI ring along bearing 150 - the S2 camera's
    own bearing from C - and drew the hard-edged dithered trapezoid that sat on the pan
    in every S2 frame from r1 to r3 (``b1/r4/probe/road_project.json`` attributes it by
    projecting all 112 roads through the exact shot pose; it is the only road with any
    geometry in the artefact's measured window, its screen centre matches to the pixel,
    and its far node's distance matches the artefact's top edge).

    The cause was one key. Stock's ``road_invisible`` is a v1.0 material, where
    ``colorMap`` IS the albedo slot, so a fully transparent map plus ``alphaTest`` /
    ``alphaRef 127`` discards every fragment. r1..r3 copied those Stages and added
    ``"version": 1.5``, which routes the material through the PBR path where the albedo
    slot is ``baseColorMap`` - no texture bound, default opaque base colour, a road that
    draws. This gate pins the recipe: transparent map on ``colorMap``, alpha test on,
    and NO version key.
    """

    materials = json.loads(rendered[f"{cook.ROAD_DIR}/main.materials.json"])
    entry = materials[writer.ROAD_INVISIBLE]
    assert "version" not in entry, "a v1.5 material ignores colorMap and renders opaque"
    stage = entry["Stages"][0]
    assert "colorMap" in stage and "baseColorMap" not in stage
    assert entry["alphaTest"] is True
    assert entry["alphaRef"] == 127
    relative = stage["colorMap"].removeprefix(f"/levels/{NAMESPACE}/")
    assert (LEVEL_ROOT / relative).is_file(), relative
    with Image.open(LEVEL_ROOT / relative) as image:
        pixels = np.asarray(image.convert("RGBA"))
    assert pixels.shape[:2] == (writer.ROAD_INVISIBLE_PX, writer.ROAD_INVISIBLE_PX)
    assert int(pixels[..., 3].max()) == 0, "the map must be fully transparent"
    # and the five roads that use it are still there, still drivable: the navgraph reads
    # them, the renderer must not.
    ai = _records(rendered["main/MissionGroup/AIDecalWaypointsGroup/items.level.json"])
    assert len(ai) == 5
    for record in ai:
        assert record["material"] == writer.ROAD_INVISIBLE
        assert record["drivability"] == 1.0
        assert record.get("gatedRoad") is True


def test_every_copied_stock_recipe_is_still_the_stock_recipe(rendered) -> None:
    """r5: the ROOT enabling condition of B-5, gated for EVERY material and not one.

    The r4 critic's finding on ``b1/r4/why_b5_was_misread.md``: the post-mortem names
    four failures and misses the one that enabled all of them - *a stock recipe was
    copied verbatim, then modified, and nothing in the round checked that a copied stock
    recipe was still the stock recipe*. ``"version": 1.5`` is carried by 61.4 % of stock
    ``Material`` records, so "is this key stock?" was never the question; "is this key
    stock FOR THIS RECIPE?" was, and 0 of the 15 stock invisible-road materials carry
    it.

    The key sets below are read off the shipped stock levels by
    ``b1/r5/probe/stock_recipe_sweep.py``, which prints the full diff and the share of
    stock materials of each class carrying each key. They are declared here rather than
    read at test time so the static suite stays hermetic (no game install required).

    The law: a copied recipe may DROP keys - a dropped key is the engine's own default -
    and may never ADD one. Every deletion is declared with its reason, and the single
    ADDITION the round makes on purpose (``castShadows`` on the backdrop) is declared
    with its reason too, so the gate passes because it looked and not because it did not.

    r6 (critic r5 B5-3): the sweep's one remaining flag was the backdrop, whose material
    does not live in either ``main.materials.json`` this gate used to open. Its own
    recipe family is covered below.
    """

    stock_keys = {
        # hirochi_raceway art/road/main.materials.json :: road_invisible (italy and
        # johnson_valley are identical; west_coast_usa adds dynamicCubemap/materialTag2)
        "road_invisible": {
            "Stages",
            "alphaRef",
            "alphaTest",
            "annotation",
            "castShadows",
            "class",
            "mapTo",
            "materialTag0",
            "materialTag1",
            "name",
            "persistentId",
            "specularStrength0",
        },
        # johnson_valley art/decalroad/main.materials.json :: m_asphalt_decayed
        "decal_road": {
            "Stages",
            "alphaRef",
            "annotation",
            "castShadows",
            "class",
            "groundType",
            "mapTo",
            "materialTag0",
            "materialTag1",
            "name",
            "persistentId",
            "specularStrength0",
            "translucent",
            "translucentZWrite",
            "version",
        },
        # west_coast_usa art/terrains/main.materials.json :: <level>TerrainMaterialTextureSet
        "terrain_texture_set": {
            "baseTexSize",
            "class",
            "detailTexSize",
            "macroTexSize",
            "name",
            "persistentId",
        },
        # west_coast_usa art/shapes/buildings/main.materials.json :: brick_herringbone,
        # the nearest stock Material to our backdrop over all eight stock levels
        # (jaccard 0.750 - it is the only stock level that ships this recipe).
        "backdrop": {
            "Stages",
            "alphaRef",
            "annotation",
            "class",
            "mapTo",
            "materialTag0",
            "materialTag1",
            "name",
            "persistentId",
            "translucentBlendOp",
            "version",
        },
    }
    # every key we deliberately do not carry, with the reason
    dropped = {
        # our decal roads are unlit dirt overlays: the stock v1.5 specular slot is left
        # at the engine default rather than pinned to asphalt's value
        "decal_road": {"specularStrength0"},
        "road_invisible": set(),
        "terrain_texture_set": set(),
        # the backdrop atlas is fully opaque, so there is no alpha cutoff to set; and
        # one materialTag (the level id) is all the ring needs - the stock recipe's
        # second tag is west_coast's own building group, which we have no analogue of.
        "backdrop": {"alphaRef", "materialTag1"},
    }
    # every key we deliberately ADD to a stock recipe, with the reason. B-5 was an
    # undeclared addition, so an addition is a defect unless it is named right here.
    added_with_a_reason = {
        "road_invisible": set(),
        "decal_road": set(),
        "terrain_texture_set": set(),
        # castShadows False. The backdrop is a 1,150-1,400 m radius ring, 320-640 m
        # tall, standing entirely outside the 2,047 m play block: as a shadow caster it
        # would occupy a whole cascade every frame and could only ever shade ground the
        # player can never reach. The TSStatic record already declares castShadows False
        # (test_backdrop_ring_closes_the_world); the material states the same intent so
        # the ring cannot cast from the shape's other draw path. The key is ordinary on
        # the class - 15.0 % of the 1,670 stock Material records carry it, 3.1 % of the
        # 1,110 in art/shapes - it is simply absent from THIS nearest stock recipe.
        # r13 / N12-3: groundType "ROCK". Critic r12 drove onto the range and the wheels
        # reported ASPHALT - a TSStatic material with no ``groundType`` falls back to the
        # engine's default, so a 1.2 km wall of granite sounded and gripped like a road.
        # The key is ordinary on the class (52 stock materials across the shipped levels
        # carry "ROCK", `automation_test_track`'s `rockwall` among them) and ordinary on
        # THIS OBJECT in particular: `johnson_valley`'s own material named `backdrop`
        # carries "DIRT_LOOSE" and `driver_training`'s `eca_backdrop` carries "GRAVEL".
        # A backdrop with a ground model is stock practice; it is absent from the nearest
        # stock recipe only because that recipe is one level's and this is another's.
        "backdrop": {"castShadows", "groundType"},
    }

    materials = json.loads(rendered[f"{cook.ROAD_DIR}/main.materials.json"])
    for name, entry in materials.items():
        recipe = "road_invisible" if name == writer.ROAD_INVISIBLE else "decal_road"
        keys = set(entry)
        added = keys - stock_keys[recipe]
        assert added == added_with_a_reason[recipe], (
            f"{name} adds {sorted(added)} to the stock {recipe} recipe"
        )
        assert stock_keys[recipe] - keys == dropped[recipe], (name, sorted(keys))

    terrains = json.loads(rendered[f"{cook.TERRAIN_DIR}/main.materials.json"])
    for name, entry in terrains.items():
        if entry.get("class") != "TerrainMaterialTextureSet":
            continue
        keys = set(entry)
        assert keys == stock_keys["terrain_texture_set"], (name, sorted(keys))

    # the backdrop keeps its material in its own shape folder, which is why the r5 sweep
    # still flagged it after this gate shipped: it is a THIRD materials document.
    backdrop_document = json.loads(
        rendered[f"{writer.BACKDROP_DIR}/{backdrop.BACKDROP_MATERIAL}.materials.json"]
    )
    assert set(backdrop_document) == {backdrop.BACKDROP_MATERIAL}
    for name, entry in backdrop_document.items():
        assert entry["class"] == "Material"
        keys = set(entry)
        added = keys - stock_keys["backdrop"]
        assert added == added_with_a_reason["backdrop"], (
            f"{name} adds {sorted(added)} to the stock backdrop recipe"
        )
        assert stock_keys["backdrop"] - keys == dropped["backdrop"], (name, sorted(keys))
        assert entry["castShadows"] is False  # the declared addition, at its declared value
        assert entry["groundType"] == "ROCK", entry.get("groundType")
        # r13: the near-field detail graft lives INSIDE Stage 0, so it does not touch the
        # top-level recipe above - but it must be complete, or the engine silently draws
        # the base alone and the foot is a beige blur again with nothing to show for it.
        stage = entry["Stages"][0]
        for key in (
            "detailMap",
            "detailNormalMap",
            "detailScale",
            "detailBaseColorMapStrength",
            "detailNormalMapStrength",
        ):
            assert key in stage, key
        # and NOT a roughness detail: the graft's roughness map is centred on 0.8615 and
        # the atlas's foot roughness is a near-constant 0.85, so an overlay blend saturates
        # to a flat 1.0 and the wall goes waxy - B2's own defect, from the other side.
        assert "roughnessDetailMap" not in stage, stage.get("roughnessDetailMap")
        assert "detailRoughnessMapStrength" not in stage
        # the scale is DERIVED from the mesh's own UV metric, never typed: u spans the
        # circumference and v spans STRIP_BANDS times the z range, so the pair must be
        # anisotropic by that ratio or the rock renders as horizontal streaks - which is
        # N12-5's complaint arriving a second time from the other direction.
        assert stage["detailScale"] == writer.backdrop_detail_scale()
        assert stage["detailScale"][0] / stage["detailScale"][1] == pytest.approx(
            (2.0 * math.pi * backdrop.RINGS[0].radius_m)
            / ((backdrop.Z_TOP - backdrop.Z_BASE) * backdrop.STRIP_BANDS),
            rel=1e-3,
        )
        # r14 / critic r13 B13-3: the two files it names are the graft's OWN, in the
        # backdrop's folder, and they are NO LONGER the terrain's rock layer. r13 pointed
        # the material at the ground's own files because the two were byte-identical - the
        # only difference being a declared tile size, which does not touch a pixel. r14
        # takes the tile-scale energy out of the wall's copy so 460 m of it stops reading
        # as courses of masonry, and the ground must not have that filter: it is tiled at
        # 1.83 m under a macro map at a grazing angle and would only lose bedding. Same
        # stone, filtered - so the assertion is now that they DIFFER.
        for key, role in (("detailMap", "b"), ("detailNormalMap", "nm")):
            assert stage[key].endswith(cook.backdrop_detail_texture_relative(role)), stage[key]
            assert cook.BACKDROP_DIR in stage[key], stage[key]
            graft = LEVEL_ROOT / cook.backdrop_detail_texture_relative(role)
            ground = LEVEL_ROOT / cook.terrain_texture_relative("rock", "detail", role)
            assert graft.is_file() and ground.is_file()
            assert graft.read_bytes() != ground.read_bytes()
        # and no third member: the material declares no roughnessDetailMap, so a cooked
        # roughness would be a file nothing reads - which is what the orphan-member audit
        # exists to catch.
        assert cook.BACKDROP_DETAIL_ROLES == ("b", "nm")
        assert not (
            LEVEL_ROOT / f"{cook.BACKDROP_DIR}/{cook.LEVEL_ID}_backdrop_detail_r.png"
        ).exists()


def test_road_nodes_are_the_pinned_lists_and_sit_on_the_terrain(rendered) -> None:
    layout = writer.layout()["decal_roads"]
    ai = _records(rendered["main/MissionGroup/AIDecalWaypointsGroup/items.level.json"])
    assert [r["name"] for r in ai] == [
        f"{NAMESPACE}_ai_ring",
        f"{NAMESPACE}_ai_connector_60",
        f"{NAMESPACE}_ai_connector_150",
        f"{NAMESPACE}_ai_connector_240",
        f"{NAMESPACE}_ai_connector_330",
    ]
    ring = ai[0]
    assert ring["material"] == writer.ROAD_INVISIBLE
    assert ring["drivability"] == 1.0 and ring["gatedRoad"] is True
    # 25 pinned nodes plus a 26th repeating node 0: a `closedLoop` field made the
    # engine's static decal batcher build an infinite AABB (boot 1 run 1).
    assert len(ring["nodes"]) == 26
    assert ring["nodes"][-1][:2] == ring["nodes"][0][:2]
    assert "closedLoop" not in ring
    keys = ["ai_ring", *(f"ai_connector_{b}" for b in (60, 150, 240, 330))]
    for record, key in zip(ai, keys, strict=True):
        pinned = layout[key]["nodes"]
        closed = layout[key].get("closed", False)
        assert len(record["nodes"]) == len(pinned) + (1 if closed else 0)
        for node, expected in zip(record["nodes"], pinned, strict=False):
            assert node[0] == pytest.approx(expected["x"], abs=1e-6)
            assert node[1] == pytest.approx(expected["y"], abs=1e-6)
            assert node[3] == expected["width"]

    visible = _records(rendered["main/MissionGroup/decal_road/items.level.json"])
    by_name = {r["name"]: r for r in visible}
    # B4 r2 split the track surface into two OPEN halves so the visible track carries no
    # repeated first node at all (the r1 batcher line).  This gate went looking for the old
    # single record and died on a KeyError from r2 until r3 taught it the split -- so the
    # node pinning below has been unasserted for a revision.  Rebuild the 48-node loop from
    # the halves and pin it exactly as before.
    track_a = by_name[f"{NAMESPACE}_track_surface_a"]
    track_b = by_name[f"{NAMESPACE}_track_surface_b"]
    trail = by_name[f"{NAMESPACE}_trail_surface"]
    assert f"{NAMESPACE}_track_surface" not in by_name, "the split halves are the track now"
    for half in (track_a, track_b):
        assert len(half["nodes"]) == 25 and half["drivability"] == 0.5
        assert half["nodes"][-1][:2] != half["nodes"][0][:2], "a half must not close on itself"
        assert "closedLoop" not in half
    # the halves meet end to end and together walk the pinned loop once
    assert track_a["nodes"][-1][:2] == track_b["nodes"][0][:2]
    assert track_b["nodes"][-1][:2] == track_a["nodes"][0][:2]
    track_nodes = track_a["nodes"] + track_b["nodes"][1:]
    assert len(track_nodes) == 49  # 48 pinned + the closer
    for node, expected in zip(track_nodes, layout["track_surface"]["nodes"], strict=False):
        assert node[0] == pytest.approx(expected["x"], abs=1e-6)
        assert node[1] == pytest.approx(expected["y"], abs=1e-6)
    assert len(trail["nodes"]) == 71 and trail["drivability"] == 0.3  # the PINNED 71-node list
    for node, expected in zip(trail["nodes"], layout["trail_surface"]["nodes"], strict=True):
        assert node[0] == pytest.approx(expected["x"], abs=1e-6)
        assert node[1] == pytest.approx(expected["y"], abs=1e-6)
        assert node[2] == pytest.approx(expected["z"], abs=1e-3)
        assert node[3] == 6.0
    # exactly ONE navgraph layer per road (study §5.12): every cosmetic record is -1.
    drivable = [r["name"] for r in visible if r["drivability"] != -1]
    assert drivable == [
        f"{NAMESPACE}_track_surface_a",
        f"{NAMESPACE}_track_surface_b",
        f"{NAMESPACE}_trail_surface",
        # amendment A6: the approach from the trail's end to the road up the canyon wall --
        # a real road, so a navgraph layer of its own, and still exactly one per road
        f"{NAMESPACE}_shelf_approach",
    ]
    # every node of every road stands on the shipped collision surface
    worst = 0.0
    for record in ai + visible:
        for x, y, z, _width in record["nodes"]:
            worst = max(worst, abs(z - terrain.surface_z(x, y)))
    assert worst <= 0.006, worst  # one quantisation unit is 4.88 mm


def test_hearth_skid_arcs_lie_on_the_flat_slab() -> None:
    records = writer.hearth_skid_records()
    assert len(records) == 40
    for record in records:
        for x, y, z, width in record["nodes"]:
            r, _ = terrain.polar(x, y)
            assert writer.SKID_R_MIN - 1.0 <= float(r) <= writer.SKID_R_MAX + 1.0
            assert z == 100.0  # the slab is exactly the datum out to r 210
            assert width == 4.0


# --- sky, water, backdrop, spawns, cameras ---------------------------------------------


def test_time_of_day_record_is_b0s_measured_form(rendered) -> None:
    payload = rendered["main/MissionGroup/level_objects/sky_and_sun/items.level.json"]
    records = {r["name"]: r for r in _records(payload)}
    tod = records["tod"]
    assert tod["version"] == 2  # the CLOCK-LAW switch: without it the clock is startTime - 0.25
    assert tod["startTime"] == 0.30 and tod["time"] == 0.30
    assert (tod["year"], tod["month"], tod["day"]) == (2026, 6, 20)  # day of the MONTH
    assert tod["latitude"] == 46.55 and tod["longitude"] == 8.45
    # keys the class does not own must be STRINGS or the loader drops them (B0)
    assert tod["utcOffset"] == "1" and isinstance(tod["utcOffset"], str)
    assert tod["dstRule"] == "eu" and isinstance(tod["dstRule"], str)
    assert tod["animate"] == "0" and tod["play"] is False
    info = records["theLevelInfo"]
    assert info["nightLightsNightStart"] == "0.29" and isinstance(
        info["nightLightsNightStart"], str
    )
    assert info["nightLightsNightEnd"] == "0.79" and isinstance(info["nightLightsNightEnd"], str)
    assert info["visibleDistance"] == 12000.0  # QB-22: >= 8000
    # r5 (critic r4 B4-4): the atmosphere height came down 220 -> 150 so the ridge
    # ring stands above the haze layer. r6 (critic r5 N5-2): the density came down
    # 0.00045 -> 0.00030, the MEDIAN of the twenty stock LevelInfo records, because it
    # is the one term that runs the full depth of every frame and the frames measured
    # flatter than a stock screenshot. Both are pinned against the stock band in
    # test_backdrop_haze_grades_the_tone_... and in test_the_sky_stack_is_inside_...
    assert info["fogDensity"] == writer.FOG_DENSITY == 0.00030
    assert info["fogAtmosphereHeight"] == writer.FOG_ATMOSPHERE_HEIGHT == 150.0
    sky = records["sunsky"]
    assert sky["azimuth"] == 294.0  # B0's measured sunset azimuth at clock 0.30
    assert "moonMat" not in sky  # B0 measured it is not a field
    for gradient in (
        "ambientScaleGradientFile",
        "colorizeGradientFile",
        "fogScaleGradientFile",
        "nightFogGradientFile",
        "nightGradientFile",
    ):
        assert sky[gradient].startswith("art/sky_gradients/default/")
    clouds = records["clouds"]
    assert clouds["texture"] == "levels/Utah/art/skies/clouds_fluffy.dds"
    assert len(clouds["Textures"]) == 3


def test_the_sky_stack_is_inside_the_stock_band_and_carries_a_stock_sky(rendered) -> None:
    """r6 / critic r5 N5-2: the frames were flatter than a stock in-engine screenshot.

    The r5 critic named the ScatterSky and the fog as the most plausible cause and
    recorded that **no round had measured them against stock**.
    ``b1/r6/probe/stock_sky_band.py`` does, over every ``ScatterSky``, ``CloudLayer`` and
    ``LevelInfo`` in the twenty-one shipped levels; ``b1/r6/probe/frame_contrast.py``
    splits our own frames at the horizon and says which half is short.

    Two things came out of it and both are pinned here.

    * **The sky half.** Our sky's own ``sigma_local8`` was 0.0021-0.0096 (median 0.0044)
      against a stock preview band of 0.0048-0.0446 (median 0.0134) - three times less
      structure over a quarter to two fifths of every frame. ``coverage`` 0.55 was below
      EVERY outdoor natural stock level: johnson_valley 1.23, italy 1.23, east_coast_usa
      1.234, Utah 1.23, small_island 1.2, west_coast_usa 1.0, and only the indoor and
      test maps sit at 0.08-0.30.
    * **The light half.** ``ambientScale`` and ``sunScale`` are now johnson_valley's own
      bytes - the closest stock analogue there is - so the shadows are as deep and the
      sun as warm as the reference desert basin's.

    The band literals below are declared rather than read at test time so the static
    suite stays hermetic; the probe re-derives them from the game install.
    """

    sky = _records(rendered["main/MissionGroup/level_objects/sky_and_sun/items.level.json"])
    records = {r["name"]: r for r in sky}
    scatter, clouds = records["sunsky"], records["clouds"]

    # johnson_valley (and derby) ship exactly these, as 132/255, 130/255, 144/255
    assert scatter["ambientScale"] == [0.517647, 0.509804, 0.564706, 1.0]
    # ...and 255/255, 167/255, 42/255
    assert scatter["sunScale"] == [1.0, 0.654902, 0.164706, 1.0]
    # the nineteen stock ScatterSky records, per component (min, max)
    ambient_band = ((0.298, 1.0), (0.337, 0.895), (0.368, 0.910))
    sun_band = ((0.898, 1.0), (0.545, 0.903), (0.086, 0.832))
    for value, (low, high) in zip(scatter["ambientScale"][:3], ambient_band, strict=True):
        assert low <= value <= high, (value, low, high)
    for value, (low, high) in zip(scatter["sunScale"][:3], sun_band, strict=True):
        assert low <= value <= high, (value, low, high)
    # the ambient must never again be brighter in luma than the reference basin's
    luma = (0.2126, 0.7152, 0.0722)
    ours = sum(w * v for w, v in zip(luma, scatter["ambientScale"][:3], strict=True))
    assert ours <= 0.517, ours  # johnson_valley's own ambient luma, 0.5165
    # skyBrightness stays at the stock MEDIAN (band 11-350)
    assert scatter["skyBrightness"] == 40.0

    # the cloud deck: at an outdoor stock level's own coverage, on Utah's own texture
    assert clouds["coverage"] == 1.23  # Utah's and johnson_valley's value
    assert 1.0 <= clouds["coverage"] <= 1.2345  # every outdoor natural stock level
    assert 0.0 <= clouds["exposure"] <= 1.7  # stock band, median 1.3
    assert 0.0 <= clouds["height"] <= 8.0  # stock band, median 3.0

    # ScatterSky.elevation is OUT of the stock band (10.0 against 15.51-270) and stays
    # there: core_celestial positions the sun every frame from lat/lon + date +
    # utcOffset, so the static field is never read. Declared, not gamed.
    assert scatter["elevation"] == 10.0


def test_water_plane_is_the_design_lake(rendered) -> None:
    water = _records(rendered["main/MissionGroup/level_objects/Water/items.level.json"])[0]
    assert water["name"] == writer.WATER_NAME
    assert water["position"][2] == 98.0
    centre = terrain.bearing_point(terrain_model.LAKE_BEARING, terrain_model.LAKE_R)
    assert water["position"][0] == pytest.approx(centre[0], abs=0.01)
    assert water["position"][1] == pytest.approx(centre[1], abs=0.01)
    # QB-24: the full field set is present
    for field in (
        "baseColor",
        "clarity",
        "depthGradientMax",
        "depthGradientTex",
        "rippleTex",
        "foamTex",
        "cubemap",
        "Ripples (texture animation)",
        "Waves (vertex undulation)",
        "Foam",
        "overallWaveMagnitude",
        "reflectivity",
        "underwaterColor",
        "waterFogDensity",
        "gridSize",
    ):
        assert field in water, field
    assert water["foamTex"].endswith("foam2_b.color.dds")  # A11: italy's exact reference
    depth = water["depthGradientTex"].removeprefix(f"/levels/{NAMESPACE}/")
    assert depth in rendered
    # A level-wide plane at 98.0 must wet nothing but the lake: the design's margin.
    grid = terrain.grid()
    index = np.arange(2048, dtype=np.float64)
    gx, gy = np.meshgrid(-174.0 + index, -1304.0 + index)
    e = terrain_model.lake_e(gx, gy)
    outside = np.asarray(grid["zq"])[e > 1.25]
    assert float(outside.min()) >= 98.5, float(outside.min())
    # r5 / critic r4 N4-6: the lake's HARD RIM and NEAR-UNIFORM FILL are texture-side.
    # `b1/r5/probe/paint_edges.py` shows the rim is not a paint boundary at all - the
    # base albedo's bearing-mean luma is flat to +-0.01 across the shoreline in every
    # round - so it is this record. The band below is measured over the **60 WaterPlane
    # and River records of the shipped stock levels** by `b1/r5/probe/stock_water_band.py`
    # (declared here so the static suite needs no game install), and r1-r4 shipped
    # `clarity` 0.55 against a stock band that tops out at 0.25: our water was more than
    # twice as clear as the clearest water any stock level ships, which is why the bed
    # read as one flat pale ellipse from the crest.
    stock_band = {
        "clarity": (0.0, 0.25),
        "foamMaxDepth": (0.2, 6.0),
        "foamRippleInfluence": (0.005, 2.0),
        "overallFoamOpacity": (0.4, 5.5),
        "overallRippleMagnitude": (0.15, 20.0),
        "overallWaveMagnitude": (0.0, 0.5),
        "depthGradientMax": (5.0, 200.0),
        "reflectivity": (0.0, 1.0),
        "fresnelBias": (-0.5, 1.0),
        "fresnelPower": (0.1, 5.0),
        "distortEndDist": (1.0, 30.0),
        "distortFullDepth": (5.0, 7.0),
    }
    for field, (low, high) in stock_band.items():
        assert low <= water[field] <= high, (field, water[field], low, high)
    # r11 / critic r10 B10-3. r5 moved three fields and STOPPED at the stock median, and
    # `clarity` 0.25 is the band's MAXIMUM - the clearest water any stock level ships - so
    # the bed still read as a flat pale ellipse from the crest, and r10 then handed the
    # whole symptom to the design as a basin move without mentioning that this record
    # exists. It is B1's. r11 sweeps the six fields LIVE in one boot, on one camera, with a
    # water-off projection mask and a repeat-shot noise floor, and ships the row the sweep
    # picks (`b1/r11/probe/water_material.py`).
    #
    # This is the gate on the link between the sweep and the record: the shipped record
    # must BE the shipped leg, field for field, so a value can never be retyped beside the
    # table that chose it.
    for field, value in writer.WATER_SWEEP[writer.WATER_RECIPE].items():
        assert water[field] == value, (field, water[field], value)
    # every leg of the sweep must be a COMPLETE recipe: the first cut of the table held
    # deltas and gave the control an empty dict, so five of the seven legs set nothing at
    # all and the boot rendered the previous leg's water. The readback control caught it.
    fields = set(writer.WATER_R10_BASELINE)
    for leg, recipe in writer.WATER_SWEEP.items():
        assert set(recipe) == fields, (leg, sorted(set(recipe) ^ fields))
        for field, value in recipe.items():
            low, high = stock_band[field]
            assert low <= value <= high, (leg, field, value, low, high)


def test_backdrop_ring_closes_the_world(rendered) -> None:
    record = _records(rendered["main/MissionGroup/level_objects/backdrop/items.level.json"])[0]
    assert record["class"] == "TSStatic"
    # r12 (critic r11 B11-3): the range is a closed solid with a Colmesh, and the record
    # says so. Through r11 this read "None" and a car drove through the ring onto grass.
    assert record["collisionType"] == "Collision Mesh"
    assert record["castShadows"] is False
    assert record["position"] == [850.0, -280.0, 0.0]
    summary = backdrop.silhouette_summary()
    # design §2.6: 24 silhouette peaks on the primary ring. r7 (critic r6 B6-1) gave each
    # of those 24 massifs spurs, a ridged crest and cols of its own, so the number of
    # MEASURED prominent maxima is no longer the number of AUTHORED summits - the second
    # is what the design fixes, and it is still exactly 24. Both are asserted, and the
    # measured count must exceed the authored one or the sub-structure is not there.
    assert summary["primary_summits"] == 24
    if backdrop.GIS_ENABLED:
        # B7 / amendment A4 (2026-09-16): the crest is no longer 24 authored massifs with
        # authored sub-structure -- it is the ground elevation of a real canyon rim, so
        # "more measured maxima than authored summits" is a question about a generator that
        # no longer drives the shape.  What the clause was defending is that the skyline is
        # not a paper crown of a few domes, and that survives as a floor on the measured
        # count.  MEASURED on the shipped mapping: 14 prominent maxima, against 12 for a
        # profile that would read as a plain wall.  The rest of the defence moved to the
        # provenance gate below and to the relief-coverage invariant, both of which bite
        # harder on real data than a peak count does.
        assert summary["peaks"] >= 12, summary["peaks"]
    else:
        assert summary["peaks"] > 24, summary["peaks"]
    assert summary["control_columns"] == 48
    assert 320.0 <= summary["height_min"] and summary["height_max"] <= 640.0
    assert 1150.0 <= summary["radius_min"] and summary["radius_max"] <= 1400.0
    # the ring stands entirely beyond the 2,047 m terrain block's play area
    assert summary["radius_min"] > terrain_model.CLEAR_R
    path = LEVEL_ROOT / record["shapeName"].removeprefix(f"/levels/{NAMESPACE}/")
    if not path.is_file():
        pytest.skip("backdrop DAE not exported yet")
    assert b"\r" not in path.read_bytes()
    assert backdrop.dae_node_parents(path) == backdrop.EXPECTED_TREE
    # r12: two geometries - the visual solid and its Colmesh - counted apart. A single sum
    # over every <triangles> would count the collision mesh as if it were drawn.
    assert summary["mesh_kind"] == "solid"
    assert backdrop.dae_tri_counts(path) == {
        f"{backdrop.BACKDROP_NODE}-mesh": summary["triangles"],
        f"{backdrop.COLMESH_NODE}-mesh": summary["colmesh_triangles"],
    }
    assert backdrop.dae_tri_count(path) == summary["triangles"] + summary["colmesh_triangles"]
    assert re.search(r'name="[^"]*_a\d+"', path.read_text(encoding="utf-8"))
    assert backdrop.BACKDROP_MATERIAL in backdrop.dae_material_names(path)
    # QB-7: the stock nulldetail node (critic r1 D-9)
    assert backdrop.NULLDETAIL_NODE in backdrop.dae_node_parents(path)
    assert backdrop.COLMESH_NODE in backdrop.dae_node_parents(path)


def test_the_backdrop_crest_is_the_lidar_profile_it_claims_to_be() -> None:
    """B7 / amendment A4: the skyline is real ground, and this is what says so.

    The ring's crest comes from `authoring/<level>_backdrop_gis.json`: the elevation of the
    Island in the Sky rim above the Shafer benches (USGS 3DEP 1 m lidar, public domain),
    sampled on three circles at this level's ring radii.  A generator can be re-tuned and a
    picture can be re-shot, but a borrowed landscape has to keep saying WHERE it came from
    and stay the shape that was borrowed, so this gate reads the shipped module against the
    shipped file, point for point, and checks the provenance the file carries.

    It also re-measures the two invariants the mapping was CHOSEN to satisfy (`b7/
    choose_mapping.py`), because they are properties of the data and not of the code:
    the world is shut on every bearing, and no crest height is a clamp.
    """

    if not backdrop.GIS_ENABLED:
        pytest.skip("the backdrop is on its synthetic generator")
    document = backdrop.gis_document()
    provenance = document["provenance"]
    assert provenance["crs"].startswith("EPSG:26912")
    assert "3DEP" in provenance["source"] and "public domain" in provenance["source"]
    assert provenance["product"] == "USGS_1M_12_x60y426_UT_WestEast_B22.tif"
    assert len(provenance["sha256"]) == 64
    assert provenance["centre_lat_lon"] == [38.45242, -109.83511]
    assert document["columns"] == backdrop.COLUMN_SEGMENTS
    assert set(document["crest_m"]) == {spec.name for spec in backdrop.RINGS}

    # every sample of every ring, straight out of the file, through the shipped mapping
    for spec in backdrop.RINGS:
        assert document["ring_radius_m"][spec.name] == spec.radius_m
        series = document["crest_m"][spec.name]
        shift = round(backdrop.GIS_ROTATION_DEG[spec.name] / 360.0 * len(series))
        for index in range(0, len(series), 97):  # a stride that is coprime with 1,536
            metres = series[(index - shift) % len(series)]
            expected = backdrop.GIS_OFFSET_M + backdrop.GIS_VERTICAL_SCALE * metres
            got = backdrop.ring_profile(spec, index * 360.0 / len(series))[0]
            # The softplus floor guard never returns exactly the mapped height: it adds
            # `knee * log1p(exp(-(z - floor) / knee))`, which is 11 mm at 100 m above the
            # floor and 5 microns at 200 m. Bound the sample by that quantity rather than
            # by a round number, so the gate stays a statement about the DATA.
            knee = backdrop.GIS_FLOOR_KNEE_M
            guard = knee * math.log1p(math.exp(-(expected - backdrop.RING_FLOOR_Z) / knee))
            assert got == pytest.approx(expected + guard, abs=1e-6), (spec.name, index)
            assert got >= backdrop.RING_FLOOR_Z

    # the two properties the mapping was chosen for, re-measured here
    columns = backdrop.COLUMN_SEGMENTS
    bearings = [360.0 * i / columns for i in range(columns)]
    visible = [backdrop.ridge_profile(b)[0] for b in bearings]
    centre_x, centre_y = backdrop.CENTER_XY
    shut = 0
    for bearing, top in zip(bearings, visible, strict=True):
        edge_r = float(backdrop.block_edge_radius(bearing))
        radians = math.radians(bearing)
        ground = float(
            backdrop.terrain_z_world(
                np.array([centre_x + (edge_r - 3.0) * math.sin(radians)]),
                np.array([centre_y + (edge_r - 3.0) * math.cos(radians)]),
            )[0]
        )
        need = max(
            backdrop.EYE_Z + (ground - backdrop.EYE_Z) * (spec.radius_m / edge_r)
            for spec in backdrop.RINGS
        )
        shut += top >= need
    assert shut == columns, f"{columns - shut} bearings let the eye out of the world"
    assert min(visible) > backdrop.RING_FLOOR_Z + 50.0, min(visible)


def test_the_brink_band_marks_the_fall_the_backdrop_actually_has() -> None:
    """r16 / critic pass 15 B15-2: the paint's threshold is the mesh's own gutter floor.

    ``terrain_model.BACKDROP_GUTTER_Z`` is the height the brink band measures a fall
    against, and it is ``blender_backdrop.Z_BASE`` written a second time because
    ``blender_backdrop`` imports the terrain and the cycle is not worth breaking for one
    float. If the two ever drift the band would mark the wrong columns and say nothing
    about it, so they are asserted equal here, and the band's own widths are asserted to be
    ordered and small enough to be a shoulder rather than a ring of gravel round the world.
    """

    # r17: the band lives in B1's own `brink.py`, not in the vendored frozen model.
    assert brink.BACKDROP_GUTTER_Z == backdrop.Z_BASE
    assert 0.0 < brink.BRINK_ROCK_M < brink.BRINK_SCREE_M
    assert brink.BRINK_SCREE_M <= 30.0
    assert brink.BRINK_FALL_M > 0.0
    # the band is painted from LAYERS that already exist and already have ground models;
    # a band on a layer the .ter has no material for would not load at all.
    assert {"scree", "rock"} <= set(terrain_model.LAYERS)


def test_the_apron_row_floors_the_gutter_without_a_degenerate_quad() -> None:
    """r16 / B15-2: the extra polygon row, and the two things it must never do.

    ``POLYGON_ROWS`` 15 -> 16 puts the apron's TOE at ``foot_r - w`` on ``Z_BASE``. The row
    may not close to nothing (a zero-width quad is a degenerate triangle - the same reason
    ``APRON_MIN_LIP_M`` exists), and the front face's seven rows must still start where
    ``FRONT_POINT_0`` says, because every index map in the module is written against that
    number and the last time it moved it moved in four places.
    """

    assert backdrop.POLYGON_ROWS == backdrop.SEGMENTS_V + 1 + backdrop.EXTRA_ROWS
    assert len(backdrop.EXTRA_POINTS) == backdrop.EXTRA_ROWS
    assert len(backdrop.EXTRA_EDGES) == backdrop.POLYGON_ROWS - backdrop.SEGMENTS_V
    assert 0.0 < backdrop.GUTTER_FLOOR_MIN_M <= backdrop.GUTTER_FLOOR_M
    for band in range(len(backdrop.RINGS)):
        for column in (0, 197, 811, 1535):
            polygon = backdrop.column_polygon(band, column)
            assert len(polygon) == backdrop.POLYGON_ROWS
            toe = polygon[backdrop.FRONT_POINT_0 - 1]
            foot = polygon[backdrop.FRONT_POINT_0]
            assert toe[1] == backdrop.Z_BASE and foot[1] == backdrop.Z_BASE
            width = foot[0] - toe[0]
            assert backdrop.GUTTER_FLOOR_MIN_M - 1e-6 <= width <= backdrop.GUTTER_FLOOR_M + 1e-6


def test_backdrop_is_a_skyline_not_a_paper_crown() -> None:
    """critic r1 D-1, measured with the critic's own instrument.

    r1: one quad strip, 384 triangles, 0 ridgelines that could occlude another,
    circular autocorrelation 0.926 at lag 30 deg (the silhouette repeated 12x),
    peak-height stdev 32.6 m on a 577 m mean (+-5.6 %), strip magnified 1.87x
    on screen at FOV 60.
    """

    summary = backdrop.silhouette_summary()
    assert summary["rings"] >= 3
    assert summary["vertical_segments"] >= 4
    assert summary["triangles"] >= 8000
    # a near ridge stands in front of a farther one on a real share of the horizon
    assert summary["bearings_with_a_far_ridge_behind_the_near_one"] >= 96

    samples = 3600
    heights = [backdrop.ridge_profile(360.0 * i / samples)[0] for i in range(samples)]
    mean = sum(heights) / samples
    deviations = [h - mean for h in heights]
    denominator = sum(d * d for d in deviations)

    def autocorrelation(lag_deg: float) -> float:
        k = round(lag_deg / 360.0 * samples)
        return sum(deviations[i] * deviations[(i + k) % samples] for i in range(samples)) / (
            denominator
        )

    # r13: the lag-7.5 clause was BACKWARDS and it rewarded the defect r13 exists to fix.
    #
    # Autocorrelation at a lag far SHORTER than any real feature is a measure of
    # smoothness, not of repetition: rotate a massif by 7.5 deg and most of it still lies
    # on itself. Rotate a picket of 15 deg teeth by 7.5 deg and every tooth lands in a
    # gap, which scores ZERO - and passed. `b1/r13/probe/autocorrelation_band.py` runs
    # this exact statistic, unchanged, over the seven stock BeamNG ranges
    # `ridge_shape.py` scores: **all seven fail `< 0.30` at lag 7.5, scoring 0.8430 to
    # 0.9618.** Six of seven fail at 15 and at 30 and at 180; three of seven at 45. A gate
    # that rejects every real range in the game while passing a comb is not measuring what
    # its own docstring says, and r12 passed lag 7.5 with **0.0018** for exactly the
    # reason the user's footage looked wrong.
    #
    # So the SHORT lag keeps the same constant, turned around: a range must be CORRELATED
    # with itself at 7.5 deg. r12 scores 0.0018 and fails this; r13 scores 0.4144 and
    # passes; stock scores 0.84-0.96 and the gap is honest - our crest carries a 0.234 deg
    # multifractal that a stock skyline 1.2 km away does not resolve, so we sit between
    # the comb and the mountain and the floor is set where a comb cannot reach it.
    # The LONG lags keep the anti-periodicity bound unchanged: r1's own failure was 0.926
    # at lag 30, and that is what those clauses were written for.
    short = autocorrelation(7.5)
    assert short > 0.30, ("a crest uncorrelated at 7.5 deg is a comb, not a range", short)
    for lag in (15.0, 30.0, 45.0, 90.0, 180.0):
        # B7 / amendment A4 (2026-09-16): bound the POSITIVE side only, and floor the
        # negative.  The failure this clause was written for is REPETITION -- r1 scored
        # +0.926 at lag 30 because its silhouette repeated every 30 deg -- and `abs()`
        # conflates that with its opposite.  A real rim is ANTI-correlated at the width of
        # its own massif: the lidar crest scores -0.3035 at 45 deg because the wall stands
        # high on one side of the bowl and is cut by canyons 45 deg away, which is
        # large-scale structure and the very thing that makes it read as landscape.  The
        # floor keeps the clause's teeth: a crest that is one hill and one hole scores
        # about -1.0 and still fails.
        value = autocorrelation(lag)
        assert value < 0.30, ("repetition", lag, value)
        assert value > -0.60, ("a single lobe is not a range", lag, value)

    # r13: the massif-group tier and the coverage invariant it makes necessary.
    # A 360 deg ring is not a landscape: a stock level may be flat over a quadrant because
    # the player can look elsewhere, and a ring that is flat over a quadrant has a hole in
    # the world. Clustering makes a dead arc reachable for the first time and the first
    # clustered draft produced one over the `f10` bearing of the user's own footage.
    assert summary["shoulders"] >= 3 * len(backdrop.RINGS), summary["shoulders_per_ring"]
    assert 2.0 <= summary["summits_per_group"] <= 5.0, summary["summits_per_group"]
    assert summary["relief_repair_passes"] < backdrop.RELIEF_MAX_PASSES, summary
    assert summary["worst_visible_span_in_a_window_m"] >= backdrop.RELIEF_MIN_SPAN_M, summary[
        "worst_visible_span_in_a_window_m"
    ]

    peaks = [
        heights[i]
        for i in range(samples)
        if heights[i] > heights[i - 1] and heights[i] >= heights[(i + 1) % samples]
    ]
    peak_mean = sum(peaks) / len(peaks)
    stdev = (sum((p - peak_mean) ** 2 for p in peaks) / len(peaks)) ** 0.5
    assert stdev / peak_mean > 0.09, (stdev, peak_mean)
    assert max(peaks) / min(peaks) > 1.4, (min(peaks), max(peaks))

    # the strip must MINIFY on screen: 1920 px over a 91.53 deg horizontal FOV
    # (vertical 60, 16:9) is 20.98 screen px per degree.
    assert cook.BACKDROP_STRIP[0] / 360.0 >= 20.98
    with Image.open(LEVEL_ROOT / cook.backdrop_texture_relative("b")) as image:
        assert image.size == tuple(cook.BACKDROP_STRIP)
    assert cook.BACKDROP_BANDS == len(backdrop.RINGS)
    # critic r2 N-1: the mesh module writes the UVs and cannot import the cook (it has
    # to stay importable inside Blender, which has no Pillow), so the two declarations
    # are gated against each other here - and both dimensions must be powers of two or
    # the engine silently never cooks the atlas and the ring renders untextured.
    assert (backdrop.STRIP_W, backdrop.STRIP_H) == tuple(cook.BACKDROP_STRIP)
    # r15: the roughness strip got its own constant when the normal strip was doubled, and
    # the detail graft's size is now DERIVED (source px x cells) rather than typed - both
    # are new ways for a non-power-of-two to reach the engine, so both are gated here.
    for size in (
        *cook.BACKDROP_STRIP,
        *cook.BACKDROP_NORMAL_STRIP,
        *cook.BACKDROP_ROUGH_STRIP,
        cook.BACKDROP_DETAIL_PX,
    ):
        assert size & (size - 1) == 0, size


def test_backdrop_summits_are_mountains_and_not_domes() -> None:
    """r7 / critic r6 B6-1, said by four consecutive critics before it was fixed.

    r2 closed REPETITION (autocorrelation 0.926 -> 0.072, peak spread +-5.6 % -> +-13 %)
    and never touched SHAPE, so every one of the 54 summits was the same object at a
    different scale: ``exp(-(d/w)^2)``, symmetric about its apex, zero slope AT the apex,
    an infinite smooth tail. r3, r4, r5 and r6 all wrote that the skyline reads as domes.

    This gate pins the four properties that separate rock from a dune, each of which is
    zero or absent in r2-r6 and none of which any earlier gate could see:

    1. a NON-ZERO apex slope on a real share of the summits, which for ``(1 - t**a)**b``
       means ``a <= 1`` on at least one side (r2: 0 of 54, because a was 2 everywhere);
    2. ASYMMETRY - a summit whose two half-widths differ (r2: exactly 0.0 on all 54);
    3. more than one archetype in play, so summits differ in outline and not only in
       height;
    4. cols cut THROUGH the crest, and a column pitch fine enough to render one: a notch
       0.30 deg wide cannot exist in a mesh whose columns are 0.9375 deg apart.

    The world-closure floor moves with it and gets STRONGER, not weaker: an individual
    ring may now cut below design §2.6's z 320 (that is what a col is) while the VISIBLE
    silhouette - the max apparent elevation over the three rings, which is what a player
    sees - may not, and ``_close_the_world`` shallows notches until that holds on a
    4x-oversampled grid rather than hoping it does.
    """

    summary = backdrop.silhouette_summary()

    # 1. sharp apexes
    assert summary["sharp_apex_summits"] >= summary["massifs"] // 2, summary
    # 2. asymmetry: not one summit may be a mirror of itself
    assert summary["symmetric_summits"] == 0, summary
    assert summary["median_flank_asymmetry"] > 0.15, summary
    # 3. shape variety
    used = {name for name, count in summary["archetypes"].items() if count}
    assert len(used) >= 4, summary["archetypes"]
    assert max(summary["archetypes"].values()) <= 0.55 * summary["massifs"], summary
    # 4. cols, and a mesh fine enough to draw one
    assert summary["notches"] >= 3 * len(backdrop.RINGS), summary
    assert summary["column_degrees"] <= 0.30, summary
    narrowest = min(n.half_width_deg for rows in backdrop._NOTCHES.values() for n in rows)
    assert narrowest >= summary["column_degrees"], (narrowest, summary["column_degrees"])
    # ...and the notch is worth cutting: at the ring's own radius it must read on screen.
    # 1920 px over a 91.53 deg horizontal FOV is 20.98 px per degree.
    assert 2.0 * narrowest * 20.98 >= 5.0, narrowest

    # the world stays closed, on a grid four times finer than the mesh's own columns
    fine = 4 * backdrop.COLUMN_SEGMENTS
    visible = [backdrop.ridge_profile(360.0 * i / fine)[0] for i in range(fine)]
    assert min(visible) >= backdrop.H_MIN, min(visible)
    # and a single ring really does dip below it, or the notches are cosmetic
    per_ring = [
        min(backdrop.ring_profile(spec, 360.0 * i / fine)[0] for i in range(fine))
        for spec in backdrop.RINGS
    ]
    assert min(per_ring) < backdrop.H_MIN, per_ring
    assert min(per_ring) >= backdrop.RING_FLOOR_Z, per_ring
    # no summit is cut off flat by the ceiling clamp
    tops = [
        max(backdrop.ring_profile(spec, 360.0 * i / fine)[0] for i in range(fine))
        for spec in backdrop.RINGS
    ]
    assert max(tops) < backdrop.H_MAX, tops


def test_backdrop_haze_grades_the_tone_and_not_the_ridges_own_contrast() -> None:
    """r5 / critic r4 B4-4: the aerial perspective was applied TWICE.

    The ring stands 1,180-1,382 m out and the level's own ``LevelInfo`` fogs it again at
    render (r5's ``fogDensity 0.00045`` was a transmittance of 0.54-0.59 over that
    distance; r6's 0.00030 is 0.66-0.70, so the second attenuation is lighter still),
    so an atlas that had ALSO pre-multiplied the ridge's local contrast by 0.45 left a
    row of blank domes on five of eight bearings. The band haze now grades the band's
    TONE only; the ridge's own contrast keeps a much smaller per-band loss and a much
    shorter foot ramp. This gate pins the split so it cannot quietly come back.
    """

    assert len(cook.BACKDROP_BAND_DETAIL) == cook.BACKDROP_BANDS
    assert len(cook.BACKDROP_BAND_HAZE) == cook.BACKDROP_BANDS
    for band in range(cook.BACKDROP_BANDS):
        tone_loss = cook.BACKDROP_BAND_HAZE[band]
        detail_loss = cook.BACKDROP_BAND_DETAIL[band]
        # the detail must never be attenuated as hard as the tone: the engine's own
        # distance fog is the second attenuation and it is per pixel, by true distance.
        assert 0.0 <= detail_loss <= tone_loss, (band, detail_loss, tone_loss)
        assert detail_loss <= 0.25, (band, detail_loss)
    # monotone with distance, and the far band still reads as farther than the near one
    assert list(cook.BACKDROP_BAND_DETAIL) == sorted(cook.BACKDROP_BAND_DETAIL)
    assert cook.BACKDROP_BAND_DETAIL[-1] > 0.0
    # the detail's ramp only has to hide the mesh's bottom edge, not 220 m of ridge
    assert 20.0 <= cook.BACKDROP_FOOT_FADE_M <= 120.0
    assert cook.BACKDROP_FOOT_FADE_M < 220.0
    # ...and the SECOND attenuation, the engine's own. The ring's summits are at
    # z 380-620 and the fog layer must not swallow them: the stock band over the 20
    # shipped LevelInfo records is 75.99-1600 m (median 261.8), and every stock level
    # whose subject is a distant ridge line is at the bottom of it - johnson_valley
    # 75.99, small_island 97.23, east_coast_usa 182.17, west_coast_usa 192.79. Ours must
    # stay above the basin's own crest (every drivable metre stays hazy) and well under
    # the ridge line. b1/r5/probe/stock_fog_band.py re-derives the band.
    assert 75.99 <= writer.FOG_ATMOSPHERE_HEIGHT <= 200.0, writer.FOG_ATMOSPHERE_HEIGHT
    assert writer.FOG_ATMOSPHERE_HEIGHT > terrain_model.MAX_HEIGHT * 0.0 + 143.0
    assert writer.FOG_ATMOSPHERE_HEIGHT < min(spec.base_z for spec in backdrop.RINGS) * 0.5
    assert 0.00005 <= writer.FOG_DENSITY <= 0.0015, writer.FOG_DENSITY


def test_four_spawns_stand_on_the_terrain_where_the_design_derived_them(rendered) -> None:
    records = _records(rendered["main/MissionGroup/PlayerDropPoints/items.level.json"])
    assert [r["name"] for r in records] == [
        f"{NAMESPACE}_spawn_south",
        f"{NAMESPACE}_spawn_trailhead",
        f"{NAMESPACE}_spawn_lakeshore",
        f"{NAMESPACE}_spawn_firewood_gap",
    ]
    design = {row["name"]: row for row in writer.layout()["spawns"]}
    for record in records[1:]:
        row = design[record["name"].removeprefix(NAMESPACE)]
        assert record["position"][0] == pytest.approx(row["x"], abs=1e-6)
        assert record["position"][1] == pytest.approx(row["y"], abs=1e-6)
        surface = terrain.surface_z(row["x"], row["y"])
        assert record["position"][2] == pytest.approx(surface + writer.SPAWN_Z_LIFT, abs=0.01)
        assert record["dataBlock"] == "SpawnSphereMarker"
        assert record["spawnClass"] == "Player"
    info = json.loads(rendered["info.json"])
    assert len(info["spawnPoints"]) == 4  # design §11: 4 >= 3
    assert info["defaultSpawnPointName"] == writer.SPAWN_SOUTH
    assert info["size"] == [2048, 2048]
    assert info["minimap"][0]["offset"] == [-174.0, 744.0]
    assert info["supportsTraffic"] is True
    assert info["defaultDate"] == {"year": 2026, "month": 6, "day": 20}
    assert len(info["previews"]) == 2
    for preview in info["previews"]:
        assert preview in rendered
        with Image.open(io.BytesIO(rendered[preview])) as image:
            assert image.size == (800, 600)
    with Image.open(io.BytesIO(rendered[f"minimap/{NAMESPACE}_minimap.png"])) as image:
        assert image.size == (2048, 2048)


def test_eleven_camera_bookmarks_carry_the_truth_plan(rendered) -> None:
    records = _records(rendered["main/MissionGroup/CameraBookmarks/items.level.json"])
    cameras = writer.layout()["cameras"]
    assert len(records) == len(cameras) == 11
    for record, camera in zip(records, cameras, strict=True):
        assert record["name"].endswith(camera["name"])
        assert record["position"] == [round(float(v), 6) for v in camera["position"]]
        matrix = record["rotationMatrix"]
        assert len(matrix) == 9
        rows = [matrix[0:3], matrix[3:6], matrix[6:9]]
        for row in rows:  # every row is a unit vector (a proper rotation)
            assert sum(v * v for v in row) == pytest.approx(1.0, abs=1e-5)
        forward = rows[1]
        eye = camera["position"]
        aim = camera["look_at"]
        delta = [aim[i] - eye[i] for i in range(3)]
        norm = sum(v * v for v in delta) ** 0.5
        for i in range(3):
            assert forward[i] == pytest.approx(delta[i] / norm, abs=1e-5)


# --- packaging ------------------------------------------------------------------------------


def test_render_is_deterministic(rendered) -> None:
    again = writer.render_level()
    assert set(again) == set(rendered)
    assert all(again[k] == rendered[k] for k in rendered)


def test_text_outputs_are_strict_json_with_lf(rendered) -> None:
    for path, payload in rendered.items():
        if not path.endswith(".json"):
            continue
        assert b"\r" not in payload, path
        text = payload.decode("utf-8")
        if path.endswith(("items.level.json", ".forest4.json", ".prefab.json")):
            for line in text.splitlines():
                assert isinstance(json.loads(line), dict)
        else:
            json.loads(text)


def test_every_new_name_is_namespaced_and_every_id_is_uuid5(rendered) -> None:
    names: list[str] = []
    ids: list[str] = []
    for path, payload in rendered.items():
        if path.endswith(("items.level.json", ".prefab.json")):
            for record in _records(payload):
                if "name" in record:
                    names.append(record["name"])
                    if "persistentId" in record:
                        identifier = uuid.UUID(record["persistentId"])
                        assert identifier.version == 5, record["name"]
                        ids.append(record["persistentId"])
    # every persistentId is a uuid5, no two collide, and the ids ARE derived from
    # the object names (spot-checked on the two records whose key is the name).
    assert len(ids) == len(set(ids))
    terrain_record = _records(rendered["main/MissionGroup/level_objects/terrain/items.level.json"])[
        0
    ]
    assert terrain_record["persistentId"] == writer.persistent_id("theTerrain")
    water_record = _records(rendered["main/MissionGroup/level_objects/Water/items.level.json"])[0]
    assert water_record["persistentId"] == writer.persistent_id("water")
    assert names
    for name in names:
        assert name in STOCK_NAMES or name.startswith(f"{NAMESPACE}_"), name
    material_docs = (
        "art/terrains/main.materials.json",
        f"{cook.ROAD_DIR}/main.materials.json",
    )
    for document_path in material_docs:
        for key, entry in json.loads(rendered[document_path]).items():
            assert key.startswith(f"{NAMESPACE}_"), key
            if entry["class"] == "TerrainMaterial":
                # design §2.4 pins the BARE layer names as internalName; the object
                # name is namespaced and TerrainMaterials are unnamed SimObjects live.
                assert entry["internalName"] in terrain.MATERIALS
                assert entry["name"] == f"{NAMESPACE}_t_{entry['internalName']}"
    for path in rendered:
        base = Path(path).name
        if base in {
            "info.json",
            "items.level.json",
            "main.materials.json",
            "main.decals.json",
            # engine-mandated basenames (the forest datablock file B3 owns)
            "managedItemData.json",
        }:
            continue
        assert base.startswith(NAMESPACE), path


def test_checked_in_level_tree_matches_the_render(rendered) -> None:
    if not LEVEL_ROOT.is_dir():
        pytest.skip("level tree not generated yet")
    stale = [
        p
        for p, payload in rendered.items()
        if not (LEVEL_ROOT / p).is_file() or (LEVEL_ROOT / p).read_bytes() != payload
    ]
    assert not stale, stale


#: Groups this writer does not author, keyed by the round that does. A render that drops
#: one of these loads clean and censuses ZERO of that round's objects, with no error line
#: anywhere - it happened four times during the parallel build, once between a cut and the
#: boot that used it. `mission_group_records()` must declare every one.
FOREIGN_GROUPS = {
    f"{NAMESPACE}_props": "B4",
    f"{NAMESPACE}_hearth": "B2",
    f"{NAMESPACE}_night_light": "B2",
    f"{NAMESPACE}_audio": "B2",
}


def test_mission_group_records_declare_every_foreign_group() -> None:
    declared = {
        record["name"] for records in writer.mission_group_records().values() for record in records
    }
    missing = {name: owner for name, owner in FOREIGN_GROUPS.items() if name not in declared}
    assert not missing, f"mission_group_records() would delete: {missing}"


def test_a_render_never_drops_a_foreign_group_or_a_foreign_decal_key(rendered) -> None:
    """The render may not lose a SimGroup or a decal key the checked-in tree carries.

    B1 authors no static decals and only five of the ten scene groups, but it rewrites
    both files wholesale. This gate reads what is on disk - whoever wrote it - and asserts
    the fresh render still carries every group NAME and every decal KEY, with at least as
    many rows under each key. It is deliberately one-directional: adding is fine, losing
    is not.
    """

    if not LEVEL_ROOT.is_dir():
        pytest.skip("level tree not generated yet")

    group_file = "main/MissionGroup/items.level.json"
    on_disk = LEVEL_ROOT / group_file
    if on_disk.is_file():
        disk_groups = {r["name"] for r in _records(on_disk.read_bytes()) if "name" in r}
        render_groups = {r["name"] for r in _records(rendered[group_file]) if "name" in r}
        assert disk_groups <= render_groups, sorted(disk_groups - render_groups)

    disk_decals = LEVEL_ROOT / "main.decals.json"
    if disk_decals.is_file():
        before = json.loads(disk_decals.read_text(encoding="utf-8")).get("instances", {})
        after = json.loads(rendered["main.decals.json"])["instances"]
        assert set(before) <= set(after), sorted(set(before) - set(after))
        thinned = {
            k: (len(before[k]), len(after[k])) for k in before if len(after[k]) < len(before[k])
        }
        assert not thinned, thinned


def test_the_decal_carry_forward_reads_a_foreign_key_and_survives_a_bad_file(
    tmp_path: Path,
) -> None:
    """The mechanism itself, on a tree this test owns - not on the shipped one."""

    assert writer._existing_decal_instances(tmp_path) == {}
    (tmp_path / "main.decals.json").write_text("{ not json", encoding="utf-8")
    assert writer._existing_decal_instances(tmp_path) == {}
    foreign = {"someone_elses_key": [[0, 1.0, 0, 1.0, 2.0, 3.0, 0, 0, 1.0, 1.0, 0, 0, "u"]]}
    (tmp_path / "main.decals.json").write_text(
        json.dumps({"header": {"version": 2}, "instances": foreign}), encoding="utf-8"
    )
    assert writer._existing_decal_instances(tmp_path) == foreign


def test_level_lock_matches_the_archive() -> None:
    from examples.hot_potato_arena.level import build_level_zip as dist

    archive = dist.DEFAULT_OUTPUT_DIR / dist.ZIP_NAME
    lock_path = dist.DEFAULT_OUTPUT_DIR / dist.LOCK_NAME
    if not archive.is_file() or not lock_path.is_file():
        pytest.skip("level dist not built")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert lock["sha256"] == dist._sha256(archive)
    # `dist_level/` holds whichever cut was taken last, and there are two kinds.
    #
    # A ROUND'S OWN cut is a SUBSET of the level allowlist, because another round is
    # still building its members into the shared tree (see build_level_zip's
    # --members-file / stage_level_tree). Every member is on the allowlist.
    #
    # A FULL-LEVEL DELIVERY is a SUPERSET, because `expected_level_members()` composes
    # `forest_build` and `props_build` but NOT `hearth_build` - so 76 members the shared
    # tree really carries (66 of them exactly `hearth_build.bulk_members()` +
    # `dae_members()`, the other 10 registered by no round at all) are invisible to the
    # allowlist. That is the same family as the two foreign-ownership bugs gated above,
    # one layer out, and it is NOT fixed here: `expected_members()` also drives B1's live
    # install gate, and the rounds that own those members are the ones that must register
    # them.
    #
    # r9 (critic r8 N8-6). What this gate USED to say it asserted was "nothing B1 AUTHORS
    # may be missing from a cut". What it actually did, for the only kind of cut B1 takes,
    # was `pass`. Two things were wrong:
    #
    #   1. the subset branch asserted nothing at all;
    #   2. `b1_authored` was `render_level() | cooked_members() | dae_members()`, and
    #      `dae_members()` is the backdrop shape PLUS B3's 63 forest shapes, while
    #      `render_level()` composes every round's records. So of the 87 "B1-authored"
    #      members critic r8 found missing from `recut_r8`, 63 are B3's forest, 12 are
    #      B4's props and the rest are other rounds' group files. None of them is B1's,
    #      and a B1 subset cut is CORRECT to omit them.
    #
    # WHAT THIS GATE COVERS, said out loud: every member B1 itself renders into the tree -
    # the 168 cooked textures and the six-file backdrop shape folder, 171 in all - must be
    # in the lock, for a subset cut and for a delivery alike. Measured over recut_r6, r7
    # and r8: 0 absent (`b1/r9/probe/lock_gate_coverage.json`).
    #
    # WHAT THIS GATE DOES NOT COVER, said equally out loud: it says NOTHING about B2's 66
    # hearth members, B3's 371 forest members or B4's 67 prop members. A B1 subset cut
    # carries none of them by design, and the level B1's live install gate boots is
    # therefore a level with no hearth, no forest and no props. That is a deliberate
    # subject isolation, not an accident - and it is stated here rather than left for a
    # critic to discover, which is the whole of N8-6.
    allowlist = set(dist.expected_members())
    # B6 (2026-09-15): a cut taken with `--cooked-dir` ships the engine's cooked DDS in
    # place of a PNG member and records the pair in `lock["cooked"]`; for every
    # membership question below the PNG the tree renders counts as present when its cooked
    # stand-in is in the lock. The archive itself is verified against the SHIPPED names.
    cooked = lock.get("cooked", {})
    for shipped, row in cooked.items():
        assert shipped in lock["members"], shipped
        assert shipped.endswith(".dds") and row["source"].endswith(".png"), (shipped, row)
        assert lock["member_sha256"][shipped] == row["cooked_sha256"], shipped
    locked = set(lock["members"]) | {row["source"] for row in cooked.values()}
    b1_renders = {
        f"{writer.LEVEL_RELATIVE}/{path}"
        for path in (
            *cook.cooked_members(),
            *(
                f"{writer.BACKDROP_DIR}/{name}"
                for name in (
                    "ericrolph_hot_potato_arena_backdrop_ring.dae",
                    "ericrolph_hot_potato_arena_backdrop_ring.cdae",
                    "ericrolph_hot_potato_arena_backdrop.materials.json",
                )
            ),
        )
    }
    # not B1's, and named so the next reader does not have to re-derive it
    not_b1s = {
        f"{writer.LEVEL_RELATIVE}/{path}"
        for path in (
            *forest_build.bulk_members(LEVEL_ROOT),
            *hearth_build.bulk_members(),
        )
    }
    assert not (b1_renders & not_b1s), sorted(b1_renders & not_b1s)[:5]
    missing_b1 = sorted(b1_renders - locked)
    assert not missing_b1, (
        f"{len(missing_b1)} member(s) B1 renders are absent from the lock: {missing_b1[:5]}"
    )
    if locked <= allowlist:
        # a round's own subset cut: it is allowed to omit every other round's members and
        # it does. The count is asserted so it cannot drift silently in either direction.
        assert not (locked & not_b1s), sorted(locked & not_b1s)[:5]
    else:
        assert allowlist <= locked, sorted(allowlist - locked)[:5]
        assert not (locked - allowlist) & b1_renders, sorted((locked - allowlist) & b1_renders)[:5]
    assert lock["members"] == sorted(lock["members"])
    assert set(lock["member_sha256"]) == set(lock["members"])
    assert not (set(cooked) & {row["source"] for row in cooked.values()})
    dist.verify_archive(archive, lock["members"])
    # QB-28: the zip stays under 1 GB -- amended A3 (2026-09-15, `design_amendments.md`) to
    # 1.1 GB: shipping the engine's cooked DDS in place of the PNGs it proves (B6) removes the
    # first-load texture cook and costs +35.8 MB over the raw-PNG cut (242 maps: 346.3 MB of
    # PNG -> 382.1 MB of DDS at the profile's GraphicTextureQuality "Normal").
    assert archive.stat().st_size < 1_100_000_000
    # The shipped arena dist is untouched by this round: its lock still matches its zip.
    arena_dir = writer.EXAMPLE_ROOT / "dist"
    arena_lock = json.loads(
        (arena_dir / "ericrolph_hot_potato_arena.lock.json").read_text(encoding="utf-8")
    )
    assert arena_lock["sha256"] == dist._sha256(arena_dir / "hot_potato_arena_ericrolph.zip")
