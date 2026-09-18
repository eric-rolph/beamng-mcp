"""Static structural gates for the BeamNG maps pack.

Every spec is validated on its own; the artefact gates (handoff hashes against the
generated level tree, the .ter binary, the scene files, the ZIP lock) run when the map
has been built and skip with a reason otherwise, because ``mod/`` and ``dist/`` are build
output the repository deliberately does not track.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "gis_maps"
HANDOFF_SCHEMA = "ericrolph-beamng-maps-handoff-v1"
APPROVED_ROOTS = {
    "vehicles",
    "levels",
    "art",
    "assets",
    "lua",
    "scripts",
    "ui",
    "gameplay",
    "settings",
    "trackEditor",
    "vehicleGroups",
}
MAP_KEYS = sorted(
    child.name for child in PACK_ROOT.iterdir() if child.is_dir() and (child / "spec.py").is_file()
)


def load_spec(map_key: str):
    spec_path = PACK_ROOT / map_key / "spec.py"
    loader = importlib.util.spec_from_file_location(f"gis_maps_test_spec_{map_key}", spec_path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def load_maplib():
    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    from maplib import gis_sources, heightmap, level_builder, packaging, pipeline, texture_kit

    return gis_sources, heightmap, level_builder, packaging, pipeline, texture_kit


def level_root(map_key: str) -> Path:
    spec = load_spec(map_key)
    return PACK_ROOT / map_key / "mod" / "levels" / spec.MOD_ID


def require_built(map_key: str) -> Path:
    root = level_root(map_key)
    if not (root / "info.json").is_file():
        pytest.skip(f"{map_key}: level not built (python examples/gis_maps/build.py {map_key} all)")
    return root


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_items(path: Path) -> list[dict]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    objects = [json.loads(line) for line in lines]
    assert path.read_text(encoding="utf-8").lstrip()[0] == "{", (
        f"{path}: items.level.json must not be a JSON array"
    )
    return objects


def all_items(main: Path) -> list[tuple[Path, dict]]:
    return [
        (path, obj) for path in sorted(main.rglob("items.level.json")) for obj in read_items(path)
    ]


# ---------------------------------------------------------------------------
# Spec gates
# ---------------------------------------------------------------------------


def test_pack_has_all_maps() -> None:
    # A literal, bumped by one for the map you add, so a spec silently dropping out of
    # discovery is a red suite and not a smaller green one.
    assert len(MAP_KEYS) == 6, MAP_KEYS


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_spec_identity(map_key: str) -> None:
    spec = load_spec(map_key)
    assert spec.MOD_ID == f"ericrolph_{map_key}"
    assert spec.ZIP_BASENAME == f"{map_key}_ericrolph.zip"
    assert spec.AUTHOR == "ericrolph"
    for field in ("DISPLAY_NAME", "DESCRIPTION", "BIOME", "FEATURES", "SUITABLE_FOR", "ROADS_TEXT"):
        assert isinstance(getattr(spec, field), str) and getattr(spec, field).strip(), field


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_spec_footprint_is_a_beamng_terrain(map_key: str) -> None:
    site = load_spec(map_key).SITE
    size = site["size_px"]
    assert size & (size - 1) == 0 and 1024 <= size <= 8192, "heightmap edge must be a power of two"
    assert site["square_size_m"] in (0.5, 1.0, 1.5, 2.0)
    assert size * site["square_size_m"] <= 8192
    assert 32601 <= site["epsg"] <= 32660, "sites are placed in WGS 84 UTM north zones"
    assert -90 < site["center_lat"] < 90 and -180 < site["center_lon"] < 180


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_spec_materials_and_rules_agree(map_key: str) -> None:
    spec = load_spec(map_key)
    materials = spec.TERRAIN["materials"]
    assert len(materials) == len(set(materials)) and 1 <= len(materials) <= 254
    assert spec.TERRAIN["classify"]["default"] in materials
    for rule in spec.TERRAIN["classify"]["rules"]:
        assert rule["material"] in materials, rule
        assert set(rule) - {"material"} <= {
            "min_slope",
            "max_slope",
            "min_elevation",
            "max_elevation",
            "min_exg",
            "max_exg",
            "min_canopy",
            "max_canopy",
            "ew_facing",
            "min_elevation_frac",
            "max_elevation_frac",
        }
    _, _, level_builder, _, _, texture_kit = load_maplib()
    for name in materials:
        palette = spec.PALETTE[name]
        assert palette["family"] in texture_kit.FAMILIES, palette["family"]
        assert palette["family"] in level_builder.GROUNDMODEL_BY_FAMILY or palette.get(
            "groundmodel"
        )
        assert len(palette["base"]) == 3 and all(0.0 <= c <= 1.0 for c in palette["base"])
    road = spec.ROADS["material"]
    assert road["family"] in texture_kit.FAMILIES
    assert set(spec.ROADS["include"]) <= set(spec.ROADS["widths"]), (
        "every included highway type needs a width"
    )


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_spec_spawns_lie_inside_the_footprint(map_key: str) -> None:
    spec = load_spec(map_key)
    _gis_sources, _, _, _, pipeline, _ = load_maplib()
    fp = pipeline.footprint_for(spec)
    from rasterio.warp import transform

    defaults = 0
    names = set()
    for spawn in spec.SPAWNS:
        xs, ys = transform("EPSG:4326", f"EPSG:{fp.epsg}", [spawn["lon"]], [spawn["lat"]])
        assert fp.west + 20 <= xs[0] <= fp.east - 20 and fp.south + 20 <= ys[0] <= fp.north - 20, (
            spawn["name"]
        )
        defaults += bool(spawn.get("default"))
        names.add(spawn["name"])
    assert defaults == 1, "exactly one default spawn"
    assert len(names) == len(spec.SPAWNS)
    assert 0.0 <= spec.SKY["time"] < 1.0


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_spec_sources_carry_citations(map_key: str) -> None:
    spec = load_spec(map_key)
    kinds = [s["kind"] for s in spec.SOURCES["elevation"]]
    assert kinds[0] == "usgs_3dep", "3DEP is the baseline every other source is levelled onto"
    for source in spec.SOURCES["elevation"][1:]:
        assert source.get("citation") and source.get("license"), source["name"]
        if source["kind"] == "ot_tiles":
            assert "(\\d+)" in source["pattern"] and source["tile_m"] > 0


# ---------------------------------------------------------------------------
# Toolkit gates (no data needed)
# ---------------------------------------------------------------------------


def test_ter_roundtrip(tmp_path: Path) -> None:
    _, hm, _, _, _, _ = load_maplib()
    dem = (np.random.default_rng(3).random((64, 64)) * 120.0 + 1500.0).astype("float32")
    layer = (np.arange(64 * 64).reshape(64, 64) % 3).astype("uint8")
    encoded = hm.encode(dem, layer)
    path = tmp_path / "t.ter"
    hm.write_ter(path, encoded.heights_u16_south_up, encoded.layer_u8_south_up, ["a", "bb", "ccc"])
    raw = path.read_bytes()
    version, size = struct.unpack("<BI", raw[:5])
    assert version == 9 and size == 64
    heights = np.frombuffer(raw[5 : 5 + 2 * 64 * 64], dtype="<u2").reshape(64, 64)
    layers = np.frombuffer(raw[5 + 2 * 64 * 64 : 5 + 3 * 64 * 64], dtype="u1").reshape(64, 64)
    assert raw[5 + 3 * 64 * 64 :] == b"\x03\x00\x00\x00" + b"\x01a" + b"\x02bb" + b"\x03ccc"
    assert np.array_equal(heights, encoded.heights_u16_north_up[::-1])
    assert np.array_equal(layers, layer[::-1])
    decoded = heights.astype("float64") * encoded.max_height_m / 65536.0 + encoded.min_elevation_m
    assert np.abs(decoded[::-1] - dem).max() < encoded.max_height_m / 65536.0 + 1e-3
    assert encoded.max_height_m >= float(dem.max() - dem.min())


def test_texture_kit_is_deterministic(tmp_path: Path) -> None:
    _, _, _, _, _, texture_kit = load_maplib()
    a = texture_kit.build_set(
        tmp_path / "a", "x", "gravel", seed=42, size=64, base_rgb=[0.5, 0.4, 0.3]
    )
    b = texture_kit.build_set(
        tmp_path / "b", "x", "gravel", seed=42, size=64, base_rgb=[0.5, 0.4, 0.3]
    )
    for suffix in ("b", "nm", "r", "h", "ao"):
        assert a[suffix].read_bytes() == b[suffix].read_bytes(), suffix
    c = texture_kit.build_set(
        tmp_path / "c", "x", "gravel", seed=43, size=64, base_rgb=[0.5, 0.4, 0.3]
    )
    assert a["b"].read_bytes() != c["b"].read_bytes(), "a different seed must change the map"


# The names the placed-object generators seed themselves from. A seed built on the
# builtin hash() of one of these is a different seed in every process, which is how two
# CI builds of the same commit shipped different rocks, different shrubs and a forest of
# 9032 instances against 9040.
_SEED_NAMES = ("rock_limestone", "rock_talus", "sage", "juniper", "aspen_sapling", "brick")

_SEED_PROBE = """
import json, sys
sys.path.insert(0, sys.argv[1])
from maplib.stable_seed import stable_hash
names = json.loads(sys.argv[2])
print(json.dumps({
    "stable": [stable_hash(n) for n in names],
    "builtin": [hash(n) for n in names],
}))
"""


def _seed_probe(hash_seed: str) -> dict:
    """Run the probe in a fresh interpreter with PYTHONHASHSEED set to ``hash_seed``."""

    import os
    import subprocess

    env = dict(os.environ, PYTHONHASHSEED=hash_seed)
    out = subprocess.run(  # noqa: S603 - this interpreter, a literal script, static arguments
        [sys.executable, "-c", _SEED_PROBE, str(PACK_ROOT), json.dumps(list(_SEED_NAMES))],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return json.loads(out.stdout)


def test_object_seeds_are_stable_across_processes() -> None:
    """``stable_hash`` gives the same number in a differently salted interpreter.

    This has to cross a process boundary: str hashing is salted once per process, so a
    single-process test passes with the defect present and proves nothing. The builtin
    is measured alongside as the control - if it ever stops differing here, the salt is
    pinned in the environment and this test has quietly stopped testing anything."""

    a, b = _seed_probe("1"), _seed_probe("2")
    assert a["stable"] == b["stable"], (a["stable"], b["stable"])
    assert a["builtin"] != b["builtin"], (
        "PYTHONHASHSEED appears to be pinned, so this test can no longer tell a stable "
        "seed from an unstable one"
    )


def test_no_generator_is_seeded_from_the_builtin_hash() -> None:
    """No module under ``maplib`` derives a seed or a shipped id from ``hash()``.

    Guards the spelling as well as the property: the test above cannot see a new call
    site that no map exercises yet, and a reviewer reading `hash(family) % 97` has no
    reason to suspect it."""

    offenders = []
    for path in sorted((PACK_ROOT / "maplib").glob("*.py")):
        # stable_seed.py names the builtin in its own docstring to explain what it
        # replaces; it is the one file that is allowed to say the word.
        if path.name == "stable_seed.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"(?<![\w.])hash\s*\(", code):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, "use maplib.stable_seed.stable_hash instead:\n" + "\n".join(offenders)


def test_texture_tiles_wrap() -> None:
    _, _, _, _, _, texture_kit = load_maplib()
    rng = np.random.default_rng(1)
    noise = texture_kit.fbm(128, 4, 3, rng)
    # Periodic noise: the step across the wrap edge is no larger than interior steps.
    interior = np.abs(np.diff(noise, axis=1)).max()
    wrap = np.abs(noise[:, 0] - noise[:, -1]).max()
    assert wrap <= interior * 1.5


def test_terrain_texture_sizes_are_terrain_squares() -> None:
    """A ``*TexSize`` is divided into the terrain's SAMPLE count, not its world width.

    Meteor Crater is 2048 m across sampled at 0.5 m; given its footprint in metres the
    game drew the orthoimagery tiled two by two over the level. Sizes are authored in
    metres and converted here, so a map sampled at 1 m is unchanged.
    """

    _, _, level_builder, _, _, _ = load_maplib()
    args = ("m", "rock_x", "rock", "gm", "/levels/m", "t_base", "t_macro")
    half = level_builder.terrain_material(*args, 2048.0, square_size_m=0.5, detail_tile_m=2.0)
    one = level_builder.terrain_material(*args, 4096.0, square_size_m=1.0, detail_tile_m=2.0)
    coarse = level_builder.terrain_material(*args, 6144.0, square_size_m=1.5, detail_tile_m=2.0)
    for entry in (half, one, coarse):
        # 4096 samples across, so the base map covers the terrain exactly once.
        assert entry["baseColorBaseTexSize"] == 4096
    assert one["baseColorDetailTexSize"] == 2.0 and one["baseColorMacroTexSize"] == 60.0
    # 4 squares at 0.5 m is the authored 2 m tile; 120 squares is the authored 60 m.
    assert half["baseColorDetailTexSize"] == 4.0 and half["baseColorMacroTexSize"] == 120.0
    assert coarse["baseColorMacroTexSize"] == 40.0


def test_delight_stats_survive_the_handoff_json() -> None:
    """`delight` returns one ndarray, and every stage that keeps it must pop it.

    It comes back as the private ``_refill_mask``, the refilled cells the level stage
    measures against their rings. The terrain stage pops it and saves it, but only maps
    with an OBJECTS spec condition their colour there; the four without one reach
    ``conditioned_colour`` from the level stage instead, where nothing did. The first
    release build after those four turned the de-lighting on died on
    ``TypeError: Object of type ndarray is not JSON serializable`` writing the handoff.

    So: every public stat survives ``json.dumps``, and the private key stays the only
    one that does not.
    """
    load_maplib()
    from maplib import imagery

    n, res = 128, 1.5
    yy, xx = np.mgrid[0:n, 0:n].astype("float32")
    dem = (120.0 * np.sin(xx / 30.0) * np.cos(yy / 30.0)).astype("float32")
    colour = np.random.default_rng(0).integers(40, 200, size=(n, n, 3), dtype=np.uint8)
    # Bingham Canyon's authored block, the one that hit this.
    _, stats = imagery.delight(
        colour,
        dem,
        res,
        azimuth_deg=180.0,
        altitude_deg=63.0,
        strength=1.0,
        max_gain=4.5,
        steep_deg=32.0,
        steep_cap=True,
        steep_feather_deg=8.0,
    )
    private = sorted(k for k in stats if k.startswith("_"))
    assert private == ["_refill_mask"], private
    assert isinstance(stats["_refill_mask"], np.ndarray)
    with pytest.raises(TypeError):
        json.dumps(stats)
    # The handoff takes the public view, whatever a stage forgot to pop.
    _, _, _, _, pipeline, _ = load_maplib()
    json.dumps(pipeline.public_stats(stats))
    stats.pop("_refill_mask")
    json.dumps(stats)


def test_delight_never_blows_a_channel() -> None:
    """No texel `delight` returns has a channel at or above 250, on warm ground.

    The soft knee compresses on the texel's MEAN luminance, but it is one CHANNEL that
    reaches the 8-bit wall, so a warm surface saturates its red while its mean sits
    under the knee and the knee does nothing about it. Measured on the shipped bases,
    every clipped texel of Factory Butte's caprock and Meteor Crater's east-facing
    limestone was clipped in red alone or in red and green, never in all three.
    """

    load_maplib()
    from maplib import imagery

    n, res = 128, 1.0
    yy, xx = np.mgrid[0:n, 0:n].astype("float32")
    dem = (80.0 * np.sin(xx / 24.0) * np.cos(yy / 24.0)).astype("float32")
    # Bright warm rock, the shape that clips: red near the wall, blue well under it.
    colour = np.dstack(
        [
            np.full((n, n), 250, dtype="uint8"),
            np.full((n, n), 214, dtype="uint8"),
            np.full((n, n), 156, dtype="uint8"),
        ]
    )
    out, stats = imagery.delight(
        colour, dem, res, azimuth_deg=160.0, altitude_deg=55.0, strength=1.0, max_gain=2.2
    )
    assert out.max() < 250, (out.max(), out.reshape(-1, 3)[out.max(axis=-1).ravel().argmax()])
    assert stats["highlight_ceiling_fraction"] > 0, "this fixture is meant to hit the ceiling"
    # And the ceiling is off when a spec turns it off, so it stays an authored choice.
    loose, loose_stats = imagery.delight(
        colour,
        dem,
        res,
        azimuth_deg=160.0,
        altitude_deg=55.0,
        strength=1.0,
        max_gain=2.2,
        highlight_ceiling=0.0,
    )
    assert loose.max() > out.max()
    assert loose_stats["highlight_ceiling_fraction"] == 0.0


def test_clamp_highlights_holds_hue() -> None:
    """The ceiling scales the whole texel, so only its brightness moves."""

    load_maplib()
    from maplib import imagery

    warm = np.array([[[1.30, 1.05, 0.62]]], dtype="float32")
    out, fraction = imagery.clamp_highlights(warm.copy(), 0.95)
    assert fraction == 1.0
    assert out.max() == pytest.approx(0.95, abs=1e-6)
    assert np.allclose(out[0, 0] / out[0, 0].max(), warm[0, 0] / warm[0, 0].max(), atol=1e-6)
    # 0.95 linear is the brightest value that still encodes under the gates' 250.
    assert imagery.linear_to_srgb_u8(out.copy()).max() == 249
    # Under the ceiling nothing moves, and a ceiling of 0 is a no-op.
    dim = np.array([[[0.40, 0.31, 0.22]]], dtype="float32")
    same, none = imagery.clamp_highlights(dim.copy(), 0.95)
    assert none == 0.0 and np.array_equal(same, dim)
    off, none_off = imagery.clamp_highlights(warm.copy(), 0.0)
    assert none_off == 0.0 and np.array_equal(off, warm)


def test_yaw_matrix_convention() -> None:
    _, _, level_builder, _, _, _ = load_maplib()
    north = level_builder.yaw_matrix(0.0)
    south = level_builder.yaw_matrix(180.0)
    assert south == [1.0, 0.0, 0.0, -0.0, 1.0, 0.0, 0.0, 0.0, 1.0] or south[0] == 1.0
    assert north[0] == -1.0 and north[4] == -1.0


def test_packaging_refuses_unapproved_roots(tmp_path: Path) -> None:
    _, _, _, packaging, _, _ = load_maplib()
    (tmp_path / "mod" / "README").parent.mkdir(parents=True)
    (tmp_path / "mod" / "README").write_text("no")
    with pytest.raises(ValueError):
        packaging.build_distribution(tmp_path, "x", "x.zip")


# ---------------------------------------------------------------------------
# Artefact gates (built maps only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_handoff_hashes_match_shipped_files(map_key: str) -> None:
    root = require_built(map_key)
    spec = load_spec(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    assert handoff["schema"] == HANDOFF_SCHEMA
    assert handoff["asset"]["id"] == spec.MOD_ID
    for name, record in handoff["shipped"].items():
        path = root / name
        assert path.stat().st_size == record["size"], name
        assert sha256_file(path) == record["sha256"], name
    assert (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}_thumbnail.jpg").is_file()


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_ter_binary_is_well_formed(map_key: str) -> None:
    root = require_built(map_key)
    spec = load_spec(map_key)
    size = spec.SITE["size_px"]
    raw = (root / "theTerrain.ter").read_bytes()
    version, stored_size = struct.unpack("<BI", raw[:5])
    assert version == 9 and stored_size == size
    materials = json.loads((root / "theTerrain.terrain.json").read_text(encoding="utf-8"))[
        "materials"
    ]
    assert materials == spec.TERRAIN["materials"]
    names = b"".join(struct.pack("<B", len(m)) + m.encode() for m in materials)
    assert len(raw) == 5 + 3 * size * size + 4 + len(names)
    assert raw[5 + 3 * size * size :] == struct.pack("<I", len(materials)) + names
    heights = np.frombuffer(raw[5 : 5 + 2 * size * size], dtype="<u2")
    layers = np.frombuffer(raw[5 + 2 * size * size : 5 + 3 * size * size], dtype="u1")
    assert heights.min() == 0, "heights are relative to the lowest sample"
    assert heights.max() > 1000, "the 16-bit ladder must actually be used"
    valid = (layers < len(materials)) | (layers == 255)
    assert valid.all()
    assert (layers == 255).mean() == 0.0, "no holes are authored in these maps"


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_heightmap_png_is_16_bit_and_row_consistent(map_key: str) -> None:
    from PIL import Image

    root = require_built(map_key)
    spec = load_spec(map_key)
    size = spec.SITE["size_px"]
    image = Image.open(root / "theTerrain.terrainheightmap.png")
    assert image.mode in ("I;16", "I") and image.size == (size, size)
    png = np.asarray(image).astype("uint16")
    raw = (root / "theTerrain.ter").read_bytes()
    ter = np.frombuffer(raw[5 : 5 + 2 * size * size], dtype="<u2").reshape(size, size)
    assert np.array_equal(png[::-1], ter), "PNG is north-up; .ter row 0 is the south edge"


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_scene_tree_parents_and_terrain_block(map_key: str) -> None:
    root = require_built(map_key)
    spec = load_spec(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    items = all_items(root / "main")
    names = {obj["name"] for _, obj in items}
    for path, obj in items:
        assert "class" in obj and "name" in obj, (path, obj)
        if obj["name"] != "MissionGroup":
            assert obj.get("__parent") in names, (path, obj["name"])
        if obj["class"] == "SimGroup" and obj["name"] != "MissionGroup":
            folder = path.parent / obj["name"]
            assert (folder / "items.level.json").is_file(), f"SimGroup {obj['name']} has no folder"
    terrain = [obj for _, obj in items if obj["class"] == "TerrainBlock"]
    assert len(terrain) == 1
    block = terrain[0]
    footprint = spec.SITE["size_px"] * spec.SITE["square_size_m"]
    # Half a square in: the game's sample (0, 0) sits on the GIS grid's first cell centre.
    res = spec.SITE["square_size_m"]
    assert block["position"] == [-footprint / 2 + res / 2, -footprint / 2 + res / 2, 0]
    assert block["squareSize"] == spec.SITE["square_size_m"]
    # The far-field bake has to be as big as the base maps it bakes, or the whole level
    # is drawn from a half-resolution copy of its orthoimagery.
    texture_set = next(
        m
        for m in json.loads(
            (root / "art" / "terrains" / "main.materials.json").read_text(encoding="utf-8")
        ).values()
        if m["class"] == "TerrainMaterialTextureSet"
    )
    assert block["baseTexSize"] == texture_set["baseTexSize"][0]
    assert block["maxHeight"] == handoff["terrain"]["max_height_m"]
    assert block["terrainFile"] == f"/levels/{spec.MOD_ID}/theTerrain.ter"
    assert (root / block["minimapImage"].split(f"{spec.MOD_ID}/", 1)[1]).is_file()
    for name in ("theLevelInfo", "tod", "sunsky"):
        assert name in names


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_info_json_spawns_resolve(map_key: str) -> None:
    root = require_built(map_key)
    info = json.loads((root / "info.json").read_text(encoding="utf-8"))
    items = all_items(root / "main")
    spawns = {obj["name"]: obj for _, obj in items if obj["class"] == "SpawnSphere"}
    listed = {s["objectname"] for s in info["spawnPoints"]}
    assert info["defaultSpawnPointName"] in listed
    assert listed == set(spawns), "info.json and PlayerDropPoints must agree"
    for entry in info["spawnPoints"]:
        assert (root / entry["preview"]).is_file()
    for preview in info["previews"]:
        assert (root / preview).is_file()
    assert (
        info["size"]
        == [int(load_spec(map_key).SITE["size_px"] * load_spec(map_key).SITE["square_size_m"])] * 2
    )
    assert "OpenStreetMap" in info["description"] and "3DEP" in info["description"]
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"ericrolph_{map_key}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    for spawn in spawns.values():
        assert 0.0 < spawn["position"][2] <= handoff["terrain"]["max_height_m"] + 1.0


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_terrain_materials_cover_every_layer(map_key: str) -> None:
    from PIL import Image

    root = require_built(map_key)
    spec = load_spec(map_key)
    footprint = spec.SITE["size_px"] * spec.SITE["square_size_m"]
    materials = json.loads(
        (root / "art" / "terrains" / "main.materials.json").read_text(encoding="utf-8")
    )
    sets = [m for m in materials.values() if m["class"] == "TerrainMaterialTextureSet"]
    assert len(sets) == 1
    texture_set = sets[0]
    by_internal = {
        m["internalName"]: m for m in materials.values() if m["class"] == "TerrainMaterial"
    }
    assert set(by_internal) == set(spec.TERRAIN["materials"])
    expected_px = {
        "Base": texture_set["baseTexSize"][0],
        "Detail": texture_set["detailTexSize"][0],
        "Macro": texture_set["macroTexSize"][0],
    }
    for internal, entry in by_internal.items():
        assert entry["name"] == f"{internal}-{entry['persistentId']}"
        assert entry["groundmodelName"]
        entry_detail_m = float(
            spec.PALETTE[internal].get("tile_m", spec.SITE.get("detail_tile_m", 2.0))
        )
        for key, value in entry.items():
            if key.endswith("Tex"):
                path = root / value.split(f"/levels/{spec.MOD_ID}/", 1)[1]
                assert path.is_file(), value
                slot = (
                    "Base"
                    if key.endswith("BaseTex")
                    else "Detail"
                    if key.endswith("DetailTex")
                    else "Macro"
                )
                assert Image.open(path).size == (expected_px[slot], expected_px[slot]), value
            # The engine divides the terrain's SAMPLE count by these, not its world
            # width, so every size is the authored metres expressed in terrain squares.
            # Meteor Crater proved it: 2048 m sampled at 0.5 m, given 2048, drew the
            # orthoimagery tiled two by two over the level.
            squares_per_m = 1.0 / spec.SITE["square_size_m"]
            if key.endswith("BaseTexSize"):
                assert value == spec.SITE["size_px"], (
                    "base texture must cover the whole terrain exactly once"
                )
                assert value == int(footprint * squares_per_m)
            if key.endswith("DetailTexSize"):
                assert value == pytest.approx(entry_detail_m * squares_per_m, abs=1e-5), key
            if key.endswith("MacroTexSize"):
                assert value == pytest.approx(60.0 * squares_per_m, abs=1e-5), key


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_roads_are_inside_and_draped(map_key: str) -> None:
    root = require_built(map_key)
    spec = load_spec(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    half = spec.SITE["size_px"] * spec.SITE["square_size_m"] / 2
    road_materials = json.loads(
        (root / "art" / "road" / "main.materials.json").read_text(encoding="utf-8")
    )
    roads = [obj for _, obj in all_items(root / "main") if obj["class"] == "DecalRoad"]
    assert len(roads) == handoff["roads"]["roads"]
    for road in roads:
        assert road["material"] in road_materials
        assert len(road["nodes"]) >= 2
        for x, y, z, width in road["nodes"]:
            assert -half <= x <= half and -half <= y <= half
            assert 0.0 <= z <= handoff["terrain"]["max_height_m"]
            assert 2.0 <= width <= 12.0
    # Every road material the level ships (the surface set, or the single default)
    # has its textures in the mod.
    used = {road["material"] for road in roads}
    assert used <= set(road_materials)
    for stage in [road_materials[name]["Stages"][0] for name in sorted(used)]:
        for value in stage.values():
            if isinstance(value, str) and value.startswith("/levels/"):
                assert (root / value.split(f"/levels/{spec.MOD_ID}/", 1)[1]).is_file(), value


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_distribution_zip_matches_lock(map_key: str) -> None:
    require_built(map_key)
    spec = load_spec(map_key)
    dist = PACK_ROOT / map_key / "dist"
    zip_path = dist / spec.ZIP_BASENAME
    lock_path = dist / f"{spec.MOD_ID}.lock.json"
    if not zip_path.is_file() or not lock_path.is_file():
        pytest.skip(f"{map_key}: dist not built")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert sha256_file(zip_path) == lock["sha256"]
    assert zip_path.stat().st_size == lock["size"]
    _, _, _, packaging, _, _ = load_maplib()
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.namelist()
        assert len(members) == lock["members"]
        assert all(m.split("/")[0] in APPROVED_ROOTS for m in members)
        assert f"levels/{spec.MOD_ID}/info.json" in members
        assert f"levels/{spec.MOD_ID}/theTerrain.ter" in members
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        assert packaging.future_dated_members(archive) == []


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_design_ledger_matches_handoff(map_key: str) -> None:
    """The DESIGN.md ledger is generated from the handoff; a stale one is a red gate."""

    require_built(map_key)
    _, _, _, _, pipeline, _ = load_maplib()
    spec = load_spec(map_key)
    design = (PACK_ROOT / map_key / "DESIGN.md").read_text(encoding="utf-8")
    assert pipeline.LEDGER_HEADING in design
    rendered = pipeline.render_ledger(spec, PACK_ROOT / map_key)
    assert design[design.index(pipeline.LEDGER_HEADING) :] == rendered


# ---------------------------------------------------------------------------
# Delivery and local deployment tools
# ---------------------------------------------------------------------------


def _load_script(name: str):
    path = PACK_ROOT / f"{name}.py"
    loader = importlib.util.spec_from_file_location(f"gis_maps_{name}", path)
    module = importlib.util.module_from_spec(loader)
    # dataclasses resolve string annotations through sys.modules[cls.__module__];
    # a module executed without being registered there breaks every @dataclass in it.
    sys.modules[loader.name] = module
    loader.loader.exec_module(module)
    return module


def _tiny_release(tmp_path: Path, key: str) -> Path:
    """A minimal but structurally valid level ZIP for the tooling gates."""

    zip_path = tmp_path / f"{key}_ericrolph.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(f"levels/ericrolph_{key}/info.json", json.dumps({"title": key}))
        archive.writestr(f"levels/ericrolph_{key}/theTerrain.ter", b"\x09" + b"\x00" * 64)
    return zip_path


def test_join_parts_rebuilds_zip_and_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    join_parts = _load_script("join_parts")
    pack = tmp_path / "pack"
    (pack / "meteor_crater").mkdir(parents=True)
    (pack / "meteor_crater" / "spec.py").write_text("MOD_ID='ericrolph_meteor_crater'\n")
    monkeypatch.setattr(join_parts, "PACK_ROOT", pack)
    original = _tiny_release(tmp_path, "meteor_crater")
    data = original.read_bytes()
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    chunks = [data[i : i + 40] for i in range(0, len(data), 40)]
    sums = []
    for index, chunk in enumerate(chunks):
        part = parts_dir / f"meteor_crater_ericrolph.zip.part{index}"
        part.write_bytes(chunk)
        sums.append(f"{hashlib.sha256(chunk).hexdigest()}  {part.name}")
    sums.append(f"{hashlib.sha256(data).hexdigest()}  meteor_crater_ericrolph.zip")
    (parts_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    assert join_parts.join(parts_dir) == 0
    rebuilt = pack / "meteor_crater" / "dist" / "meteor_crater_ericrolph.zip"
    assert rebuilt.read_bytes() == data
    lock = json.loads(
        (pack / "meteor_crater" / "dist" / "ericrolph_meteor_crater.lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock["sha256"] == hashlib.sha256(data).hexdigest() and lock["members"] == 2
    # A corrupted part is refused and nothing is left behind.
    (parts_dir / "meteor_crater_ericrolph.zip.part0").write_bytes(b"x" * 40)
    rebuilt.unlink()
    assert join_parts.join(parts_dir) == 1
    assert not rebuilt.exists()


def test_deploy_local_reports_and_deploys_into_a_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deploy_local = _load_script("deploy_local")
    pack = tmp_path / "pack"
    (pack / "meteor_crater" / "dist").mkdir(parents=True)
    (pack / "meteor_crater" / "spec.py").write_text(
        "MOD_ID='ericrolph_meteor_crater'\nDISPLAY_NAME='Crater'\nZIP_BASENAME='meteor_crater_ericrolph.zip'\n"
    )
    release = _tiny_release(pack / "meteor_crater" / "dist", "meteor_crater")
    lock = {"sha256": hashlib.sha256(release.read_bytes()).hexdigest()}
    (pack / "meteor_crater" / "dist" / "ericrolph_meteor_crater.lock.json").write_text(
        json.dumps(lock)
    )
    profile = tmp_path / "profile"
    (profile / "mods").mkdir(parents=True)
    monkeypatch.setattr(deploy_local, "PACK_ROOT", pack)
    monkeypatch.setenv("BEAMNG_MAPS_PROFILE", str(profile))
    monkeypatch.setenv("BEAMNG_MAPS_ALLOW_RUNNING", "1")
    assert deploy_local.main([]) == 1  # missing -> stale report exits 1
    assert deploy_local.main(["--deploy"]) == 0
    deployed = profile / "mods" / "meteor_crater_ericrolph.zip"
    assert deployed.read_bytes() == release.read_bytes()
    assert deploy_local.main([]) == 0  # current
    # A second copy of the namespace anywhere below mods/ is a conflict, by content.
    shadow = profile / "mods" / "repo" / "old_copy.zip"
    shadow.parent.mkdir()
    shutil.copyfile(release, shadow)
    assert deploy_local.main(["--deploy"]) == 1
    # A dist that disagrees with its lock is never deployed.
    shadow.unlink()
    release.write_bytes(release.read_bytes() + b"\x00")
    assert deploy_local.main(["--deploy"]) == 1


def _pack_with_one_map(tmp_path: Path, key: str = "meteor_crater") -> Path:
    pack = tmp_path / "pack"
    (pack / key / "dist").mkdir(parents=True)
    (pack / key / "spec.py").write_text(
        f"MOD_ID='ericrolph_{key}'\nDISPLAY_NAME='Crater'\nZIP_BASENAME='{key}_ericrolph.zip'\n"
    )
    return pack


def test_deploy_local_maps_filter_deploys_only_the_named_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--maps must narrow the deploy, or installing one map ships every ZIP in dist/."""

    deploy_local = _load_script("deploy_local")
    pack = tmp_path / "pack"
    for key in ("meteor_crater", "factory_butte"):
        (pack / key / "dist").mkdir(parents=True)
        (pack / key / "spec.py").write_text(
            f"MOD_ID='ericrolph_{key}'\nDISPLAY_NAME='{key}'\nZIP_BASENAME='{key}_ericrolph.zip'\n",
        )
        release = _tiny_release(pack / key / "dist", key)
        (pack / key / "dist" / f"ericrolph_{key}.lock.json").write_text(
            json.dumps({"sha256": hashlib.sha256(release.read_bytes()).hexdigest()})
        )
    profile = tmp_path / "profile"
    (profile / "mods").mkdir(parents=True)
    monkeypatch.setattr(deploy_local, "PACK_ROOT", pack)
    monkeypatch.setenv("BEAMNG_MAPS_PROFILE", str(profile))
    monkeypatch.setenv("BEAMNG_MAPS_ALLOW_RUNNING", "1")
    assert deploy_local.main(["--maps", "meteor_crater", "--deploy"]) == 0
    assert (profile / "mods" / "meteor_crater_ericrolph.zip").is_file()
    assert not (profile / "mods" / "factory_butte_ericrolph.zip").exists()
    with pytest.raises(SystemExit):
        deploy_local.main(["--maps", "no_such_map"])


def test_deploy_local_remove_is_a_dry_run_until_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--remove reports, --remove --confirm deletes, by CONTENT and wherever the zip sits."""

    deploy_local = _load_script("deploy_local")
    pack = _pack_with_one_map(tmp_path)
    profile = tmp_path / "profile"
    mods = profile / "mods"
    mods.mkdir(parents=True)
    monkeypatch.setattr(deploy_local, "PACK_ROOT", pack)
    monkeypatch.setenv("BEAMNG_MAPS_PROFILE", str(profile))
    monkeypatch.setenv("BEAMNG_MAPS_ALLOW_RUNNING", "1")

    # Nothing installed: removal is a clean no-op, not an error.
    assert deploy_local.main(["--remove", "--confirm"]) == 0

    installed = _tiny_release(mods, "meteor_crater")
    stale_copy = mods / "unpacked" / "an_old_name.zip"
    stale_copy.parent.mkdir()
    shutil.copyfile(installed, stale_copy)
    unrelated = _tiny_release(mods, "somebody_elses_level")
    assert deploy_local.main(["--remove"]) == 1  # dry run exits non-zero, deletes nothing
    assert installed.is_file() and stale_copy.is_file()
    assert deploy_local.main(["--remove", "--confirm"]) == 0
    assert not installed.exists() and not stale_copy.exists()
    assert unrelated.is_file()  # a level this pack does not own is never touched


def test_deploy_local_remove_spares_a_zip_that_also_carries_an_unselected_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting a mixed zip would take a level nobody asked about, so it is reported."""

    deploy_local = _load_script("deploy_local")
    pack = _pack_with_one_map(tmp_path)
    profile = tmp_path / "profile"
    mods = profile / "mods"
    mods.mkdir(parents=True)
    monkeypatch.setattr(deploy_local, "PACK_ROOT", pack)
    monkeypatch.setenv("BEAMNG_MAPS_PROFILE", str(profile))
    monkeypatch.setenv("BEAMNG_MAPS_ALLOW_RUNNING", "1")
    mixed = mods / "someone_elses_pack.zip"
    with zipfile.ZipFile(mixed, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("levels/ericrolph_meteor_crater/info.json", "{}")
        archive.writestr("levels/their_level/info.json", "{}")
    assert deploy_local.main(["--remove", "--confirm"]) == 1
    assert mixed.is_file()

    # Same rule protects one of our own levels that --maps held back.
    (pack / "factory_butte").mkdir()
    (pack / "factory_butte" / "spec.py").write_text(
        "MOD_ID='ericrolph_factory_butte'\nDISPLAY_NAME='Butte'\n"
        "ZIP_BASENAME='factory_butte_ericrolph.zip'\n"
    )
    both = mods / "two_of_ours.zip"
    with zipfile.ZipFile(both, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("levels/ericrolph_meteor_crater/info.json", "{}")
        archive.writestr("levels/ericrolph_factory_butte/info.json", "{}")
    assert deploy_local.main(["--remove", "--confirm", "--maps", "meteor_crater"]) == 1
    assert both.is_file()
    assert (
        deploy_local.main(["--remove", "--confirm", "--maps", "meteor_crater", "factory_butte"])
        == 1
    )
    assert not both.exists()  # both named: the bundle goes


def test_deploy_local_remove_needs_no_local_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An uninstall has to work from spec.py alone: dist/ may have been deleted."""

    deploy_local = _load_script("deploy_local")
    pack = tmp_path / "pack"
    (pack / "meteor_crater").mkdir(parents=True)  # no dist/ at all
    (pack / "meteor_crater" / "spec.py").write_text(
        "MOD_ID='ericrolph_meteor_crater'\nDISPLAY_NAME='Crater'\n"
        "ZIP_BASENAME='meteor_crater_ericrolph.zip'\n"
    )
    profile = tmp_path / "profile"
    mods = profile / "mods"
    mods.mkdir(parents=True)
    monkeypatch.setattr(deploy_local, "PACK_ROOT", pack)
    monkeypatch.setenv("BEAMNG_MAPS_PROFILE", str(profile))
    monkeypatch.setenv("BEAMNG_MAPS_ALLOW_RUNNING", "1")
    installed = _tiny_release(mods, "meteor_crater")
    assert deploy_local.main(["--remove", "--confirm"]) == 0
    assert not installed.exists()


def test_deploy_local_remove_refuses_while_the_game_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deploy_local = _load_script("deploy_local")
    pack = _pack_with_one_map(tmp_path)
    profile = tmp_path / "profile"
    mods = profile / "mods"
    mods.mkdir(parents=True)
    monkeypatch.setattr(deploy_local, "PACK_ROOT", pack)
    monkeypatch.setattr(deploy_local, "beamng_running", lambda: True)
    monkeypatch.setenv("BEAMNG_MAPS_PROFILE", str(profile))
    installed = _tiny_release(mods, "meteor_crater")
    assert deploy_local.main(["--remove", "--confirm"]) == 1
    assert installed.is_file()


def test_install_local_passes_the_maps_filter_to_the_deploy_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_local = _load_script("install_local")
    pack = tmp_path / "pack"
    for key in ("meteor_crater", "factory_butte"):
        (pack / key).mkdir(parents=True)
        (pack / key / "spec.py").write_text(
            f"MOD_ID='ericrolph_{key}'\nDISPLAY_NAME='{key}'\nZIP_BASENAME='{key}_ericrolph.zip'\n",
        )
    for module in (install_local.build, install_local.join_parts, install_local.deploy_local):
        monkeypatch.setattr(module, "PACK_ROOT", pack)
    monkeypatch.setattr(install_local, "release_ok", lambda key: True)
    seen: list[list[str]] = []
    monkeypatch.setattr(install_local.deploy_local, "main", lambda argv: seen.append(argv) or 0)
    assert install_local.main(["--maps", "meteor_crater"]) == 0
    assert seen == [["--deploy", "--maps", "meteor_crater"]]
    seen.clear()
    assert install_local.main([]) == 0
    assert seen == [["--deploy"]]


def test_deploy_local_verify_reads_the_game_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--verify has to answer "did it load?" from the engine's own log, not from eyes."""

    deploy_local = _load_script("deploy_local")
    pack = _pack_with_one_map(tmp_path)
    profile = tmp_path / "profile"
    mods = profile / "mods"
    mods.mkdir(parents=True)
    monkeypatch.setattr(deploy_local, "PACK_ROOT", pack)
    monkeypatch.setenv("BEAMNG_MAPS_PROFILE", str(profile))

    # No log at all: the game has never run against this profile.
    assert deploy_local.main(["--verify"]) == 1

    log = profile / "beamng.log"
    log.write_text("mounted /mods/meteor_crater_ericrolph.zip\n", encoding="utf-8")
    assert deploy_local.main(["--verify"]) == 0

    # A line naming the namespace with an error word is a failure, not a pass.
    log.write_text(
        "mounted /mods/meteor_crater_ericrolph.zip\n"
        "failed to load levels/ericrolph_meteor_crater/info.json\n",
        encoding="utf-8",
    )
    assert deploy_local.main(["--verify"]) == 1

    # Deployed but never mentioned: the engine has not rescanned yet.
    log.write_text("nothing to see here\n", encoding="utf-8")
    _tiny_release(mods, "meteor_crater")
    assert deploy_local.main(["--verify"]) == 1


def test_install_local_rejoins_parts_and_deploys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install_local --parts must take a delivered build straight into the profile, no rebuild."""

    install_local = _load_script("install_local")
    pack = tmp_path / "pack"
    (pack / "meteor_crater").mkdir(parents=True)
    (pack / "meteor_crater" / "spec.py").write_text(
        "MOD_ID='ericrolph_meteor_crater'\nDISPLAY_NAME='Crater'\nZIP_BASENAME='meteor_crater_ericrolph.zip'\n"
    )
    for module in (install_local.build, install_local.join_parts, install_local.deploy_local):
        monkeypatch.setattr(module, "PACK_ROOT", pack)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        install_local.build, "run_stage", lambda key, stage, force=False: calls.append((key, stage))
    )
    data = _tiny_release(tmp_path, "meteor_crater").read_bytes()
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    (parts_dir / "meteor_crater_ericrolph.zip.part0").write_bytes(data)
    (parts_dir / "SHA256SUMS.txt").write_text(
        f"{hashlib.sha256(data).hexdigest()}  meteor_crater_ericrolph.zip\n"
    )
    profile = tmp_path / "profile"
    (profile / "mods").mkdir(parents=True)
    monkeypatch.setenv("BEAMNG_MAPS_PROFILE", str(profile))
    monkeypatch.setenv("BEAMNG_MAPS_ALLOW_RUNNING", "1")
    assert install_local.main(["--parts", str(parts_dir)]) == 0
    assert calls == [], "a verified delivered build must not trigger a rebuild"
    assert (profile / "mods" / "meteor_crater_ericrolph.zip").read_bytes() == data
    # Without parts and without a release, every stage runs (stubbed here) and the
    # missing lock is reported rather than silently deployed.
    (pack / "meteor_crater" / "dist" / "meteor_crater_ericrolph.zip").unlink()
    with pytest.raises(SystemExit):
        install_local.main(["--no-deploy"])
    assert [stage for _, stage in calls] == ["fetch", "terrain", "level", "dist"]


def test_install_local_release_download_verifies_and_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--release pulls each ZIP from the release, checks SHA256SUMS.txt and writes the lock."""

    install_local = _load_script("install_local")
    pack = tmp_path / "pack"
    (pack / "meteor_crater").mkdir(parents=True)
    (pack / "meteor_crater" / "spec.py").write_text(
        "MOD_ID='ericrolph_meteor_crater'\nDISPLAY_NAME='Crater'\nZIP_BASENAME='meteor_crater_ericrolph.zip'\n"
    )
    for module in (install_local.build, install_local.join_parts, install_local.deploy_local):
        monkeypatch.setattr(module, "PACK_ROOT", pack)
    data = _tiny_release(tmp_path, "meteor_crater").read_bytes()
    served = {
        "SHA256SUMS.txt": (
            f"{hashlib.sha256(data).hexdigest()}  meteor_crater_ericrolph.zip\n".encode()
        ),
        "meteor_crater_ericrolph.zip": data,
    }
    requested: list[str] = []

    def fake_download(url: str, path: Path) -> None:
        requested.append(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(served[url.rsplit("/", 1)[1]])

    install_local.fetch_release(
        "gis-maps-v1", ["meteor_crater"], repo="o/r", download=fake_download
    )
    assert requested == [
        "https://github.com/o/r/releases/download/gis-maps-v1/SHA256SUMS.txt",
        "https://github.com/o/r/releases/download/gis-maps-v1/meteor_crater_ericrolph.zip",
    ]
    dist = pack / "meteor_crater" / "dist"
    assert (dist / "meteor_crater_ericrolph.zip").read_bytes() == data
    lock = json.loads((dist / "ericrolph_meteor_crater.lock.json").read_text(encoding="utf-8"))
    assert lock["sha256"] == hashlib.sha256(data).hexdigest() and "gis-maps-v1" in lock["origin"]
    # A tampered asset is deleted, never locked.
    served["meteor_crater_ericrolph.zip"] = data + b"\x00"
    (dist / "meteor_crater_ericrolph.zip").unlink()
    with pytest.raises(SystemExit):
        install_local.fetch_release(
            "gis-maps-v1", ["meteor_crater"], repo="o/r", download=fake_download
        )
    assert not (dist / "meteor_crater_ericrolph.zip").exists()


# ---------------------------------------------------------------------------
# Art-pass toolkit gates (no build needed): meshes, shadows, road beds, objects, forest
# ---------------------------------------------------------------------------


def _load_art_modules():
    load_maplib()
    from maplib import imagery, meshgen, objects, roads, vegetation

    return imagery, meshgen, objects, roads, vegetation


def test_meshgen_writes_collada_beamng_can_read(tmp_path: Path) -> None:
    """A rock and a spruce: Z-up metres, one geometry per mesh, Colmesh-N collision only."""

    import xml.etree.ElementTree as ET

    _, meshgen, _, _, _ = _load_art_modules()
    ns = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
    rock = meshgen.write_dae(
        tmp_path / "rock.dae", meshgen.rock_meshes(3, (2.0, 1.5, 1.0), material="m_rock"), "rock"
    )
    spruce = meshgen.write_dae(
        tmp_path / "spruce.dae",
        meshgen.conifer_meshes(
            4, 12.0, 4.0, card_material="m_cards", bark_material="m_bark", name="spruce"
        ),
        "spruce",
    )
    assert rock["extent_m"] == [2.0, 1.5, 1.0] and rock["triangles"] > 1000
    assert spruce["extent_m"][2] == 12.0 and spruce["triangles"] < 120
    for name in ("rock", "spruce"):
        root = ET.parse(tmp_path / f"{name}.dae").getroot()
        assert root.find("c:asset/c:up_axis", ns).text == "Z_UP"
        assert root.find("c:asset/c:unit", ns).get("meter") == "1"
        nodes = root.findall("c:library_visual_scenes/c:visual_scene/c:node", ns)
        names = [n.get("name") for n in nodes]
        assert "Colmesh-1" in names, names
        for node in nodes:
            inst = node.find("c:instance_geometry", ns)
            has_material = inst.find("c:bind_material", ns) is not None
            assert has_material != node.get("name").startswith("Colmesh"), node.get("name")
        for tri in root.findall(".//c:triangles", ns):
            count = int(tri.get("count"))
            assert len(tri.find("c:p", ns).text.split()) == count * 9


def test_cast_shadows_fall_away_from_the_sun() -> None:
    imagery, _, _, _, _ = _load_art_modules()
    n = 400
    dem = np.zeros((n, n), dtype="float32")
    dem[190:210, 195:205] = 30.0  # a 30 m wall at the centre
    for azimuth, expect in ((90, "west"), (0, "south"), (180, "north"), (270, "east")):
        shadow = imagery.cast_shadows(dem, 1.0, azimuth, 30.0) < 0.5
        rows, cols = np.nonzero(shadow)
        assert rows.size, azimuth
        side = {
            "west": cols.max() < 195,
            "east": cols.min() > 204,
            "south": rows.min() > 209,
            "north": rows.max() < 190,
        }[expect]
        assert side, f"sun az {azimuth}: shadow should fall {expect}"
        length = (
            (cols.max() - cols.min()) if expect in ("west", "east") else (rows.max() - rows.min())
        )
        assert 40 <= length <= 60, f"30 m wall at 30 deg altitude throws ~52 m, got {length}"


def test_road_carve_flattens_the_bed_across_and_along(tmp_path: Path) -> None:
    _, _, _, roads, _ = _load_art_modules()
    n, res = 256, 1.0
    y, x = np.mgrid[0:n, 0:n].astype("float32")
    dem = 100.0 + 0.3 * x + 0.5 * np.sin(y / 3.0)  # cross-slope east-west, ripples north-south
    polyline = [
        {
            "id": "r",
            "highway": "track",
            "surface": "dirt",
            "width": 4.0,
            "points": [(0.0, -100.0), (0.0, 100.0)],
            "name": "",
        }
    ]
    carved, mask, surface, stats = roads.carve(
        dem, res, n * res, polyline, profile_window_m=20.0, feather_m=2.0, max_cut_fill_m=2.0
    )
    assert stats["roads"] == 1 and mask.sum() > 600 and set(np.unique(surface)) <= {0, 2}
    centre = n // 2
    bed = carved[40:-40, centre - 1 : centre + 2]
    assert np.abs(bed[:, 0] - bed[:, 2]).max() < 0.02, "no cross-slope left on the bed"
    assert (
        np.std(np.diff(carved[40:-40, centre], 2)) < np.std(np.diff(dem[40:-40, centre], 2)) * 0.5
    )
    assert np.array_equal(carved[:, : centre - 6], dem[:, : centre - 6]), (
        "outside the feather nothing moves"
    )


def test_detect_objects_lifts_a_boulder_and_leaves_the_ground() -> None:
    _, _, objects, _, _ = _load_art_modules()
    n, res = 200, 0.5
    y, x = np.mgrid[0:n, 0:n].astype("float32") * res
    dem = 10.0 + 0.02 * x
    # A boulder-shaped bump: steep sides, 3 m across, so the whole of it is narrower
    # than the 6 m opening (a Gaussian skirt wider than the footprint would survive it).
    bump = 1.2 * np.exp(-(((x - 50) ** 2 + (y - 50) ** 2) / (2 * 0.8**2)))
    ground, found, stats = objects.detect_objects(
        dem + bump, res, open_m=6.0, min_height_m=0.4, min_area_m2=1.0, max_area_m2=80.0
    )
    assert stats["objects"] == 1 and 1.0 <= found[0]["peak_m"] <= 1.25
    assert abs(found[0]["row"] - 100) < 1.5 and abs(found[0]["col"] - 100) < 1.5
    assert np.abs(ground - dem).max() < 0.06, "the ground under the boulder is the plane again"
    counts = objects.classify_objects(found, None, n, rock_only=True)
    assert counts == {"rock": 1, "shrub": 0, "linear": 0}
    placed = objects.place_objects(found, ground, res, n * res, 10.0)
    assert len(placed) == 1 and placed[0]["kind"] == "rock" and placed[0]["size"][2] >= 1.0


def test_ept_hierarchy_walk_visits_only_overlapping_nodes() -> None:
    """A fake Entwine index: the walker opens sub-hierarchies and skips distant nodes."""

    load_maplib()
    from maplib import pointcloud as pc

    root = [0.0, 0.0, 0.0, 1024.0, 1024.0, 1024.0]
    files = {
        "0-0-0-0": {"0-0-0-0": 10, "1-0-0-0": 20, "1-1-0-0": 30, "2-0-0-0": -1, "2-3-3-0": 5},
        "2-0-0-0": {"2-0-0-0": 7, "3-0-0-0": 3, "3-1-1-0": 4},
    }

    class Session:
        def get(self, url, timeout=0):
            key = url.rsplit("/", 1)[-1].replace(".json", "")

            class Response:
                def raise_for_status(self):
                    pass

                def json(self):
                    return files[key]

            return Response()

    nodes = pc.walk_hierarchy(Session(), "fake", root, (10.0, 10.0, 200.0, 200.0))
    assert "2-3-3-0" not in nodes, "a node in the far corner must not be visited"
    assert "1-1-0-0" not in nodes
    assert set(nodes) == {"0-0-0-0", "1-0-0-0", "2-0-0-0", "3-0-0-0", "3-1-1-0"}
    assert pc.node_bounds_xy(root, "2-3-3-0") == (768.0, 768.0, 1024.0, 1024.0)


def test_canopy_tops_and_heights_come_from_the_lidar(tmp_path: Path) -> None:
    """Synthetic returns: the canopy height model and the tree tops are measured."""

    import numpy as np

    load_maplib()
    from maplib import pointcloud as pc
    from maplib import vegetation as veg

    n = 128
    dem = np.zeros((n, n), dtype="float32") + 3000.0
    dsm = np.full((n, n), np.nan, dtype="float32")
    ground = np.full((n, n), np.nan, dtype="float32")
    counts = np.zeros((n, n), dtype="uint16")
    yy, xx = np.mgrid[0:n, 0:n]
    # bare ground everywhere with ground returns 0.4 m above the DEM datum
    ground[:] = 3000.4
    counts[:] = 2
    dsm[:] = 3000.4
    trees = [(30, 30, 14.0), (30, 60, 9.0), (90, 40, 3.0), (100, 100, 20.0)]
    for r, c, h in trees:
        crown = np.clip(h - 0.6 * np.hypot(yy - r, xx - c) * (h / 4.0) ** 0.5, 0, None)
        dsm = np.maximum(dsm, 3000.4 + crown)
    grid = tmp_path / "canopy.npz"
    np.savez(grid, dsm=dsm, ground=ground, counts=counts, ground_counts=counts)
    chm, stats = pc.canopy_height(grid, dem)
    assert abs(stats["ground_offset_m"] - 0.4) < 0.05, stats
    assert abs(float(chm[30, 30]) - 14.0) < 0.6 and abs(float(chm[100, 100]) - 20.0) < 0.6
    assert float(chm[5, 5]) < 0.1, "bare ground is not canopy"
    rows, cols, heights = pc.tree_tops(chm, 1.0, min_height_m=2.0)
    found = {(int(r), int(c)) for r, c in zip(rows, cols, strict=True)}
    assert found == {(r, c) for r, c, _ in trees}, found
    assert heights.max() > 19.0
    planted, pstats = veg.trees_from_chm(
        chm,
        dem,
        None,
        1.0,
        float(n),
        2990.0,
        {"treeline_m": 9999.0, "min_tree_height_m": 2.0, "max_trees": 100},
        seed=1,
    )
    assert pstats["trees"] == 4 and pstats["source"] == "lidar canopy"
    assert all(t["species"] in ("spruce", "fir") for t in planted)
    assert max(t["height_m"] for t in planted) > 19.0


def test_vegetation_plants_only_where_the_imagery_is_forest() -> None:
    _, _, _, _, vegetation = _load_art_modules()
    n = 256
    colour = np.full((n, n, 3), 170, dtype="uint8")  # bright bare ground
    rng = np.random.default_rng(1)
    patch = rng.integers(20, 60, size=(96, 96, 3), dtype="uint8")
    patch[..., 1] += 30  # dark, green, textured
    colour[40:136, 40:136] = patch
    dem = np.full((n, n), 3000.0, dtype="float32")
    spec = {"treeline_m": 3600.0, "spacing_m": 4.0, "max_trees": 5000, "krummholz_band_m": 100.0}
    maps = vegetation.cover_maps(colour, dem, 1.0, spec)
    assert 0.08 < maps["conifer"].mean() < 0.16
    trees, stats = vegetation.plant(maps, dem, 1.0, float(n), 3000.0, spec)
    assert stats["trees"] > 200
    half = n / 2
    for t in trees:
        col = t["x"] + half
        row = half - t["y"]
        assert 34 <= col <= 142 and 34 <= row <= 142, "a tree outside the forest patch"
        assert t["species"] in ("spruce", "fir")


# ---------------------------------------------------------------------------
# Art-pass artefact gates (built maps only)
# ---------------------------------------------------------------------------


def _terrain_height_lookup(map_key: str):
    """(z_at(x, y), max_height) from the shipped 16-bit heightmap PNG (north-up)."""

    from PIL import Image

    spec = load_spec(map_key)
    root = require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    max_height = float(handoff["terrain"]["max_height_m"])
    png = np.asarray(Image.open(root / "theTerrain.terrainheightmap.png"), dtype="float64")
    size = png.shape[0]
    res = float(spec.SITE["square_size_m"])
    half = size * res / 2.0

    def z_at(x: float, y: float) -> float:
        col = int(min(max((x + half) / res, 0), size - 1))
        row = int(min(max((half - y) / res, 0), size - 1))
        return float(png[row, col]) * max_height / 65536.0

    return z_at, half


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_flatfield_leaves_no_residual_sun(map_key: str) -> None:
    """After the flat-field every listed layer's brightness is within 10 % across its
    incidence (or aspect) bins: what the de-lighting left of the flight's sun is gone."""

    spec = load_spec(map_key)
    flatfield = (getattr(spec, "IMAGERY", None) or {}).get("aspect_flatfield")
    if not flatfield:
        pytest.skip(f"{map_key}: no flat-field")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    stats = handoff["terrain"]["stats"].get("aspect_flatfield", {})
    materials = list(spec.TERRAIN["materials"])
    checked = 0
    for name in flatfield["layers"]:
        entry = stats.get(str(materials.index(name)))
        if not entry:
            continue  # too small a layer to flat-field
        checked += 1
        gentle = entry.get("after_spread")
        steep = entry.get("after_spread_steep")
        assert gentle is not None or steep is not None, (map_key, name, entry)
        # Nothing the flat-field lifted ran to white.
        assert entry.get("clipped_fraction", 0.0) < 0.002, (map_key, name, entry)
        assert gentle is None or gentle <= 1.10, (map_key, name, entry)
        assert steep is None or steep <= 1.15, (map_key, name, entry)
    assert checked, f"{map_key}: the flat-field ran on none of its layers"


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_road_bed_reads_lighter_than_its_ground(map_key: str) -> None:
    """Where the spec says the bed is the pale ribbon of the photographs, the painted
    bed is at least that much lighter than every layer along it."""

    spec = load_spec(map_key)
    factor = (getattr(spec, "ROADS", None) or {}).get("bed_lighter_than_ground")
    if not factor:
        pytest.skip(f"{map_key}: no bed contrast contract")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    # One factor for every surface, or a factor per surface ({"dirt": 1.06}).
    contracts = (
        {name: (float(f), handoff["road_contrast"][name]) for name, f in factor.items()}
        if isinstance(factor, dict)
        else {"all": (float(factor), handoff["road_contrast"])}
    )
    for surface, (want, contrast) in contracts.items():
        layers = {
            k: v for k, v in contrast.items() if k not in ("bed", "windows", "windows_vs_pale")
        }
        assert layers, (surface, contrast)
        for name, entry in layers.items():
            # The per-layer ratio is a whole-road aggregate (the road's mean bed over
            # one layer's mean margin, mixing pale and dark stretches); the 100 m
            # windows below are the contract. In aggregate the bed is never darker
            # than any layer it crosses.
            assert entry["ratio"] >= 1.0, (map_key, surface, name, entry, contrast["bed"])
        # And along the road: 95 % of the bed's 100 m windows read at least 10 %
        # lighter than their own margins (a pale summit is not hidden by a dark
        # valley), or the contract's own factor where that is smaller.
        windows = contrast.get("windows")
        assert windows and windows["p05"] >= want * 0.98, (map_key, surface, windows)
        # And against the margin's pale side, the reference the enforcement uses.
        pale = contrast.get("windows_vs_pale")
        assert pale and pale["p05"] >= want * 0.97 and pale["min"] >= want * 0.93, (
            map_key,
            surface,
            pale,
        )
    # And the beds meet at their junctions in one surface: no seam steps.
    # (The step is read a cell apart on the raster: on a 25 % grade that is 0.25 m
    # of legitimate rise, so the gate is 0.4 m, not the 0.15 m a flat seam would show.)
    carved = handoff["terrain"]["stats"].get("road_carve") or {}
    seam = carved.get("max_seam_step_m")
    assert seam is not None and seam < 0.4, (map_key, carved)


def test_base_colour_stats_measures_each_layer() -> None:
    """The base's gate numbers: a near-black fraction over the whole image and a clipped
    fraction per layer, with a layer map resized to the colour rather than assumed equal.

    This runs without a built tree, so the arithmetic behind the gate below is checked
    even where the levels are not on disk."""

    _, _, level_builder, _, _, _ = load_maplib()

    colour = np.full((32, 32, 3), 128, dtype="uint8")
    colour[0, 0] = 0  # one near-black texel out of 1024
    colour[16:, :16] = 255  # a quarter of the image blown out
    layer = np.zeros((16, 16), dtype="uint8")
    layer[8:, :8] = 1  # at half resolution, the quarter that is white

    stats = level_builder.base_colour_stats(colour, layer, ["ground", "ledge"])
    assert stats["base_px"] == 32
    # Rounded to six places on the way into the handoff, two orders under the 1e-4 gate.
    assert stats["near_black_fraction"] == pytest.approx(1 / 1024, abs=1e-6)
    # The white quarter is layer 1 alone, so its clipping does not hide in the average:
    # over the whole image it is 0.25, which the per-layer number resolves to 1.0 and 0.0.
    assert stats["layer_mean_srgb"]["ledge"]["clipped"] == pytest.approx(1.0)
    assert stats["layer_mean_srgb"]["ground"]["clipped"] == pytest.approx(0.0)
    assert stats["layer_mean_srgb"]["ledge"]["cells"] == 256


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_base_colour_has_no_black_holes(map_key: str) -> None:
    """No in-paint, refill or gain leaves black ground: under a texel in ten thousand of
    the finished base is near black (the asphalt is dark, never black)."""

    spec = load_spec(map_key)
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    if not getattr(spec, "IMAGERY", None):
        pytest.skip(f"{map_key}: the base is not conditioned imagery")
    # Measured by the level stage on the base it wrote, so it is here for every map.
    # It used to be read from the terrain stage's stats, which only the OBJECTS path
    # fills - so four of the six maps skipped this gate silently and the two that ran
    # it were measured before the base was resized to its own resolution.
    stats = handoff.get("base_colour") or {}
    assert stats.get("near_black_fraction") is not None, (
        f"{map_key}: the level stage recorded no base colour statistics"
    )
    assert stats["near_black_fraction"] < 1e-4, stats["near_black_fraction"]
    means = stats.get("layer_mean_srgb", {})
    assert means, f"{map_key}: no layer was measured on the finished base"
    for name, entry in means.items():
        # And no layer of the finished base runs to white either.
        assert entry.get("clipped", 0.0) < 0.002, (map_key, name, entry)
    for name, lit in (getattr(spec, "IMAGERY", None) or {}).get("lighter_than", {}).items():
        # A layer the spec says reads lighter than another (the cream ledges over
        # the tan plain) does so in the finished base.
        assert means[name]["luminance"] >= float(lit["factor"]) * means[lit["than"]]["luminance"], (
            name,
            means[name],
            means[lit["than"]],
        )


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_refills_carry_their_rings_grain(map_key: str) -> None:
    """Where the spec matches every refilled field to its ring, the fields' 2-8 m grain
    is at least 80 % of the ring's (a refill is not a smooth oval in a mottled plain)."""

    spec = load_spec(map_key)
    if not (getattr(spec, "IMAGERY", None) or {}).get("refill_match_ring"):
        pytest.skip(f"{map_key}: refills are not ring-matched")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    ratio = handoff["imagery"].get("refill_grain_ratio")
    assert ratio and ratio["p10"] >= 0.8, (map_key, ratio)


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_refills_read_as_their_ground_on_the_shipped_base(map_key: str) -> None:
    """Every large refilled field (cast shadow or snow) measured on the base the game
    draws sits between 0.90 and 1.10 of its ring's luminance and within 0.04 of it on
    both chroma axes (the level stage matches every field to its ring as the last
    word on the shipped pixels), and carries at least 0.45 of its ring's under-10 m
    grain in the worst tenth of fields: a terrain shadow's fine grain is carried in
    from the ring, but its structure is its own and softer than a lit talus ring's."""

    spec = load_spec(map_key)
    if not (getattr(spec, "IMAGERY", None) or {}).get("refill_match_ring"):
        pytest.skip(f"{map_key}: no ring-matched refills")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    check = (handoff.get("imagery") or {}).get("refill_check")
    assert check, (map_key, "no refill_check in the handoff")
    assert check["lum_ratio_p10"] >= 0.90 and check["lum_ratio_max"] <= 1.10, (map_key, check)
    assert check["grain_ratio_p10"] >= 0.45, (map_key, check)
    assert check["br_diff_max_abs"] <= 0.04, (map_key, check)
    # And on the green axis: a refill matched on luminance alone came back as
    # dusty-rose banding through the tundra and mint patches in the meadows.
    assert check["exg_diff_max_abs"] <= 0.04, (map_key, check)


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_spawns_stand_on_ground_a_vehicle_fits_on(map_key: str) -> None:
    """A spawn the spec marks ``level_ground`` stands on ground a line of vehicles
    fits on: a 14 by 7 m rectangle at its heading, tilted no more than 8 degrees
    across the heading and with the ground within 0.6 m of the plane it sits on.

    Only the staging spawns promise this. A spawn at the Steps is on 20-25 % bedrock
    ledges because that is what the Steps are, and its apron is reported, not gated."""

    spec = load_spec(map_key)
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    spawns = handoff["level"]["spawns"] if "level" in handoff else handoff["spawns"]
    if not any("apron" in spawn for spawn in spawns):
        pytest.skip(f"{map_key}: built before the spawn apron was measured")
    staged = [spawn for spawn in spawns if spawn.get("level_ground")]
    if not staged:
        pytest.skip(f"{map_key}: no spawn declares level_ground")
    for spawn in staged:
        apron = spawn["apron"]
        assert apron["across_deg"] <= 8.0, (map_key, spawn["objectname"], apron)
        assert apron["roughness_m"] <= 0.6, (map_key, spawn["objectname"], apron)


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_decal_roads_have_no_node_steps(map_key: str) -> None:
    """A decal road never steps off the bed at an end (no grade change over 10 %
    within three nodes of either end), and nowhere changes grade by more than 25 %
    between two nodes (a kerb at a seam or a pad edge)."""

    spec = load_spec(map_key)
    if not (getattr(spec, "ROADS", None) or {}).get("surfaces"):
        pytest.skip(f"{map_key}: legacy single-material roads")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    roads = handoff["roads"]
    assert "max_end_grade_change" in roads, roads
    assert roads["max_end_grade_change"] <= 0.10, (map_key, roads["max_end_grade_change"])
    assert roads["max_grade_change"] <= 0.25, (map_key, roads["max_grade_change"])
    # A pad with a kerb rule ships no cut face round it steeper than the rule + 3.
    for pad in spec.ROADS.get("pads") or []:
        if not pad.get("kerb_max_slope_deg"):
            continue
        note = next(
            (
                p
                for p in handoff["terrain"]["stats"].get("pads", [])
                if p.get("center_xy") == pad["center_xy"]
            ),
            None,
        )
        assert note and note.get("kerb_slope_max_deg") is not None, (map_key, pad, note)
        # The lot adds no cut face: the inner half of the kerb band holds the rule
        # outright, and the whole band is no steeper on the whole than the flank
        # the lot is cut into was already (its own wall stays its own wall).
        cap = float(pad["kerb_max_slope_deg"])
        # The inner half of the band: the batter at the cap, and the lidar's own
        # retaining wall smoothed over 4 m, so nothing there stands over cap + 25
        # (the wall the lidar holds is 5 m tall; smoothed it lies under 40 degrees).
        assert note["kerb_inner_max_deg"] <= cap + 25.0, (map_key, note)
        assert note["kerb_slope_p95_deg"] <= max(cap + 3.0, note["kerb_natural_p95_deg"] + 2.0), (
            map_key,
            note,
        )
        assert note["kerb_slope_max_deg"] <= note["kerb_natural_max_deg"] + 10.0, (map_key, note)
    # A spec may cap the steepest 10 m of a surface (a paved road graded off a pad).
    for surface, cap in (spec.ROADS.get("max_grade_10m") or {}).items():
        steepest = roads["max_grade_10m"].get(surface, 0.0)
        assert steepest <= cap, (map_key, surface, steepest, cap)


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_forest_items_are_declared_draped_and_inside(map_key: str) -> None:
    spec = load_spec(map_key)
    root = require_built(map_key)
    forest_file = root / "forest" / f"{spec.MOD_ID}.forest4.json"
    has_objects = bool(getattr(spec, "OBJECTS", None) or getattr(spec, "FOREST", None))
    if not has_objects:
        assert not forest_file.exists(), (
            f"{map_key}: no OBJECTS/FOREST in the spec but a forest file shipped"
        )
        return
    assert forest_file.is_file(), f"{map_key}: OBJECTS/FOREST in the spec but no forest file"
    items = json.loads(
        (root / "art" / "forest" / "managedItemData.json").read_text(encoding="utf-8")
    )
    for name, item in items.items():
        assert item["class"] == "TSForestItemData" and item["internalName"] == name
        assert item["shapeFile"].startswith(f"/levels/{spec.MOD_ID}/art/shapes/{spec.MOD_ID}/")
        assert (root / item["shapeFile"][len(f"/levels/{spec.MOD_ID}/") :]).is_file(), item[
            "shapeFile"
        ]
    z_at, half = _terrain_height_lookup(map_key)
    lines = [
        json.loads(line)
        for line in forest_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines, "an empty forest is a broken detector"
    worst = 0.0
    for line in lines:
        assert set(line) == {"type", "pos", "rotationMatrix", "scale"} and line["type"] in items
        x, y, z = line["pos"]
        assert -half <= x <= half and -half <= y <= half
        assert len(line["rotationMatrix"]) == 9 and 0.2 <= line["scale"] <= 30.0
        worst = max(worst, abs(z - z_at(x, y)))
    assert worst < 3.5, f"{map_key}: a placed object floats or sinks {worst:.1f} m off the terrain"
    forest_objects = [o for _, o in all_items(root / "main") if o.get("class") == "Forest"]
    assert (
        len(forest_objects) == 1
        and forest_objects[0]["dataFile"] == f"/levels/{spec.MOD_ID}/forest/{forest_file.name}"
    )
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    assert handoff["forest"]["instances"] == len(lines)
    assert handoff["shipped"][f"forest/{forest_file.name}"]["sha256"] == sha256_file(forest_file)


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_shapes_parse_and_their_materials_exist(map_key: str) -> None:
    import xml.etree.ElementTree as ET

    spec = load_spec(map_key)
    root = require_built(map_key)
    shapes_dir = root / "art" / "shapes" / spec.MOD_ID
    if not shapes_dir.is_dir():
        pytest.skip(f"{map_key}: no shapes in this level")
    materials = json.loads((shapes_dir / "main.materials.json").read_text(encoding="utf-8"))
    ns = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
    daes = sorted(shapes_dir.glob("*.dae"))
    assert daes
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    for dae in daes:
        tree_root = ET.parse(dae).getroot()
        assert tree_root.find("c:asset/c:up_axis", ns).text == "Z_UP"
        for material in tree_root.findall("c:library_materials/c:material", ns):
            name = material.get("name")
            assert name in materials and materials[name]["mapTo"] == name, (dae.name, name)
            for stage in materials[name]["Stages"]:
                for key, value in stage.items():
                    if key.endswith("Map"):
                        assert (root / value[len(f"/levels/{spec.MOD_ID}/") :]).is_file(), value
        nodes = tree_root.findall("c:library_visual_scenes/c:visual_scene/c:node", ns)
        assert any(not n.get("name").startswith("Colmesh") for n in nodes), dae.name
        shipped = handoff["shipped"][f"art/shapes/{spec.MOD_ID}/{dae.name}"]
        assert shipped["sha256"] == sha256_file(dae)


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_road_surfaces_are_painted_and_decalled(map_key: str) -> None:
    spec = load_spec(map_key)
    root = require_built(map_key)
    surfaces = spec.ROADS.get("surfaces")
    if not surfaces:
        pytest.skip(f"{map_key}: legacy single-material roads")
    materials = spec.TERRAIN["materials"]
    raw = (root / "theTerrain.ter").read_bytes()
    size = struct.unpack_from("<I", raw, 1)[0]
    layer = np.frombuffer(raw, dtype="uint8", count=size * size, offset=5 + size * size * 2)
    road_materials = json.loads(
        (root / "art" / "road" / "main.materials.json").read_text(encoding="utf-8")
    )
    decal_names = {
        o["material"] for _, o in all_items(root / "main") if o.get("class") == "DecalRoad"
    }
    for surface, cfg in surfaces.items():
        index = materials.index(cfg["terrain_material"])
        painted = int((layer == index).sum())
        if cfg["decal"]["name"] in decal_names:
            assert painted > 500, (
                f"{map_key}: {surface} roads decalled but the bed is not painted ({painted} cells)"
            )
        assert cfg["decal"]["name"] in road_materials
    assert decal_names <= {cfg["decal"]["name"] for cfg in surfaces.values()}


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_imagery_delighting_is_recorded(map_key: str) -> None:
    spec = load_spec(map_key)
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    imagery_spec = getattr(spec, "IMAGERY", None)
    recorded = handoff.get("imagery", {})
    if not (imagery_spec and imagery_spec.get("delight")):
        assert not recorded.get("delight")
        return
    assert recorded["delight"] is True
    assert recorded["sun_fit"]["correlation"] > 0.3, "the fitted sun does not explain the shading"
    assert 0.0 <= recorded["cast_shadow_fraction"] < 0.3
    assert 0.5 <= recorded["minnaert_k"] <= 1.4 and recorded["gain_p95"] <= 4.0


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_buildings_are_measured_not_invented(map_key: str) -> None:
    """Every shipped building stands at a height the lidar returned, on its own ground.

    The outline is OSM's and nothing else is: the ridge came from the point cloud's
    highest hit inside that outline, so the ledger's spread has to look like a town's
    and not like a constant. A building is also the one thing in this pack that must
    not have a boulder or a spruce on top of it, so the mask that excludes them is
    gated here too.
    """

    spec = load_spec(map_key)
    if not getattr(spec, "BUILDINGS", None):
        pytest.skip(f"{map_key}: no buildings in this level")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    stats = handoff["buildings"]
    assert stats["count"] > 0, stats
    cfg = spec.BUILDINGS
    # Measured, so the spread is a town's: the median under the tallest, and nothing
    # outside the window the spec allows.
    assert cfg["min_height_m"] <= stats["ridge_p50_m"] <= stats["ridge_p95_m"], stats
    assert stats["ridge_p95_m"] <= stats["ridge_max_m"] <= cfg["max_height_m"], stats
    assert stats["ridge_p50_m"] < stats["ridge_max_m"] - 1.0, ("no spread: a constant?", stats)
    # Outlines the lidar found nothing standing on are dropped, not drawn at a guess.
    assert stats["count"] + stats["dropped_no_lidar"] == stats["outlines"], stats
    # Roofs are fitted, so more than one kind must come out of the fit.
    assert len(stats["roof_kinds"]) >= 2, stats
    assert sum(stats["roof_kinds"].values()) == stats["count"], stats
    assert sum(stats["roof_colours"].values()) == stats["count"], stats
    assert sum(stats["wall_families"].values()) == stats["count"], stats
    # The mask covers the footprints it was built from, and it took objects off them.
    assert stats["mask_cells"] > stats["count"] * 10, stats
    assert stats["removed_trees"] >= 0 and stats["removed_objects"] >= 0, stats


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_building_tiles_parse_and_stand_on_the_terrain(map_key: str) -> None:
    """Each tile DAE is Z-up, hashed in the handoff, and its statics sit on the level."""

    import xml.etree.ElementTree as ET

    spec = load_spec(map_key)
    if not getattr(spec, "BUILDINGS", None):
        pytest.skip(f"{map_key}: no buildings in this level")
    root = require_built(map_key)
    shapes_dir = root / "art" / "shapes" / f"{spec.MOD_ID}_buildings"
    assert shapes_dir.is_dir(), shapes_dir
    materials = json.loads((shapes_dir / "main.materials.json").read_text(encoding="utf-8"))
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    ns = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
    daes = sorted(shapes_dir.glob("*.dae"))
    assert daes
    for dae in daes:
        tree_root = ET.parse(dae).getroot()
        assert tree_root.find("c:asset/c:up_axis", ns).text == "Z_UP"
        for material in tree_root.findall("c:library_materials/c:material", ns):
            name = material.get("name")
            assert name in materials and materials[name]["mapTo"] == name, (dae.name, name)
            for stage in materials[name]["Stages"]:
                for key, value in stage.items():
                    if key.endswith("Map"):
                        assert (root / value[len(f"/levels/{spec.MOD_ID}/") :]).is_file(), value
        shipped = handoff["shipped"][f"art/shapes/{spec.MOD_ID}_buildings/{dae.name}"]
        assert shipped["sha256"] == sha256_file(dae)

    # items.level.json is line-delimited JSON, one object per line.
    items = [
        json.loads(line)
        for line in (root / "main" / "MissionGroup" / "buildings" / "items.level.json")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    half = spec.SITE["size_px"] * spec.SITE["square_size_m"] / 2.0
    assert len(items) == len(daes), (len(items), len(daes))
    for item in items:
        assert item["class"] == "TSStatic", item
        x, y, _z = item["position"]
        assert abs(x) <= half and abs(y) <= half, item
        assert (root / item["shapeName"][len(f"/levels/{spec.MOD_ID}/") :]).is_file(), item
        assert item["collisionType"] == "Visible Mesh Final", item
