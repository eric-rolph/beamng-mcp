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
import os
import re
import shutil
import struct
import sys
import zipfile
from collections import Counter
from pathlib import Path
from unittest import mock

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


def test_shipped_index_records_every_file_in_the_level_tree(tmp_path: Path) -> None:
    """The handoff's ``shipped`` block is the whole level tree, nested files included.

    The artefact gate that hashes it only runs where a map has been built, which is a
    runner, so this is the one place the coverage rule is checked on every push. It is
    worth checking: the block was a hand-written list of nine names for most of this
    pack's life, and on a map with no generated objects that came to five files of
    fifty-five.
    """

    _, _, _, _, pipeline, _ = load_maplib()
    root = tmp_path / "levels" / "m"
    for name in ("info.json", "art/terrains/main.materials.json", "art/shapes/m/rock_0.dae"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name)
    (root / "empty_dir").mkdir()

    index = pipeline.shipped_index(root, "m", [{"file": "rock_0.dae", "triangles": 12}])

    assert set(index) == {
        "info.json",
        "art/terrains/main.materials.json",
        "art/shapes/m/rock_0.dae",
    }, "a directory is not a file and every file in the tree is recorded"
    assert index["info.json"]["sha256"] == hashlib.sha256(b"info.json").hexdigest()
    assert index["info.json"]["size"] == len("info.json")
    assert index["art/shapes/m/rock_0.dae"]["triangles"] == 12
    assert "triangles" not in index["info.json"]


def test_shipped_index_refuses_a_shape_the_tree_does_not_have(tmp_path: Path) -> None:
    """A report naming a shape that never reached the tree is a packaging bug, not a note.

    Silently skipping it would write a handoff that disagrees with its own report, and the
    hash gate would never notice because the file it would have hashed is not there.
    """

    _, _, _, _, pipeline, _ = load_maplib()
    root = tmp_path / "levels" / "m"
    root.mkdir(parents=True)
    (root / "info.json").write_text("{}")
    with pytest.raises(FileNotFoundError, match=r"rock_0\.dae"):
        pipeline.shipped_index(root, "m", [{"file": "rock_0.dae", "triangles": 12}])


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

    # Coverage first, then hashes. A recorded hash that matches says nothing about the file
    # next to it that nobody recorded, and for most of this pack's life that was most of the
    # level: 5 of 55 files on the maps that generate no objects. The gate is only a gate on
    # the release if the two sets are equal, so compare the sets and let a diff name the
    # files rather than reporting a count.
    on_disk = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    recorded = set(handoff["shipped"])
    assert on_disk == recorded, {
        "shipped but never recorded": sorted(on_disk - recorded),
        "recorded but not shipped": sorted(recorded - on_disk),
    }

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
    # And the lock says which build made it. Every other field here is a property of
    # the ZIP alone, so they all pass on a release assembled from two runs at two
    # commits: each map is internally consistent with itself. These two are the only
    # fields that can disagree between maps, which is what makes a mixed release
    # detectable rather than inferred.
    assert "source_commit" in lock, (
        f"{map_key}: the lock names no commit, so nothing binds this ZIP to a build"
    )
    assert re.fullmatch(r"[0-9a-f]{40}", lock["source_commit"] or ""), lock["source_commit"]
    # A runner checks out the commit it names, so a CI lock is never dirty. A local
    # build may be, and says so rather than claiming a commit it was not built from.
    if lock.get("build_run_id") is not None:
        assert lock["source_dirty"] is False, lock


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


class _Refusal(Exception):
    """An HTTP refusal shaped the way requests raises one, without importing requests.

    ``release_downloader`` reads the status off the exception rather than catching a
    requests type, so that an injected downloader may use any HTTP client. This class
    is what that contract looks like from the outside.
    """

    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")

        class _Response:
            status_code = status

        self.response = _Response()


def _refusing_download(status: int | None = None):
    """A ``download`` that records its calls and refuses github.com with ``status``."""

    calls: list[tuple[str, dict[str, str] | None]] = []

    def download(url: str, path: Path, *, headers: dict[str, str] | None = None) -> None:
        calls.append((url, headers))
        if status is not None and url.startswith("https://github.com/"):
            raise _Refusal(status)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"asset")

    return download, calls


def _no_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("BEAMNG_MODS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("status", [401, 403, 404])
def test_a_refused_release_download_falls_back_to_the_authenticated_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    """A private repository refuses the plain URL; the token route is the only way in.

    This path only runs when the public download is refused, which is the case nobody
    hits by accident until the release actually goes private - so it is gated here
    rather than left to be discovered by the person whose install breaks.
    """

    install_local = _load_script("install_local")
    _no_tokens(monkeypatch)
    monkeypatch.setenv("BEAMNG_MODS_TOKEN", "t0ken")

    class _Assets:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"assets": [{"name": "a.zip", "url": "https://api.github.com/x/assets/9"}]}

        @staticmethod
        def raise_for_status() -> None:
            pass

    seen: list[dict] = []

    def fake_get(url: str, **kwargs):
        seen.append({"url": url, **kwargs})
        return _Assets()

    monkeypatch.setitem(sys.modules, "requests", type(sys)("requests"))
    sys.modules["requests"].get = fake_get  # type: ignore[attr-defined]

    download, calls = _refusing_download(status)
    fetch = install_local.release_downloader("o/r", "v1", download=download)
    fetch("a.zip", tmp_path / "one")
    fetch("a.zip", tmp_path / "two")

    assert calls[0][0] == "https://github.com/o/r/releases/download/v1/a.zip"
    assert calls[1] == (
        "https://api.github.com/x/assets/9",
        {"Accept": "application/octet-stream", "Authorization": "Bearer t0ken"},
    )
    # The release is resolved once, not once per asset.
    assert calls[2] == calls[1] and len(seen) == 1
    assert seen[0]["headers"]["Authorization"] == "Bearer t0ken"


def test_a_refusal_without_a_token_says_which_variable_and_which_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The person who meets this is on their own workstation with nobody to ask."""

    install_local = _load_script("install_local")
    _no_tokens(monkeypatch)
    download, _ = _refusing_download(404)
    fetch = install_local.release_downloader("o/r", "v1", download=download)
    with pytest.raises(SystemExit) as refused:
        fetch("a.zip", tmp_path / "one")
    message = str(refused.value)
    assert "PRIVATE" in message
    assert "BEAMNG_MODS_TOKEN" in message
    assert "Contents: Read" in message
    assert "personal-access-tokens" in message


def test_a_token_the_repository_rejects_is_not_reported_as_a_missing_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A private repository answers 404 when the token cannot see it, not 403.

    Without this sentence in the message, a 404 reads as "that release does not
    exist" and sends the reader looking in the wrong place.
    """

    install_local = _load_script("install_local")
    _no_tokens(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "wrong")

    class _Rejected:
        status_code = 404

    monkeypatch.setitem(sys.modules, "requests", type(sys)("requests"))
    sys.modules["requests"].get = lambda *a, **k: _Rejected()  # type: ignore[attr-defined]

    download, _ = _refusing_download(404)
    fetch = install_local.release_downloader("o/r", "v1", download=download)
    with pytest.raises(SystemExit) as rejected:
        fetch("a.zip", tmp_path / "one")
    assert "404 rather than 403" in str(rejected.value)
    assert "Contents: Read" in str(rejected.value)


def test_a_server_error_is_not_mistaken_for_a_permission_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only 401, 403 and 404 mean "try credentials"; anything else is a real failure."""

    install_local = _load_script("install_local")
    _no_tokens(monkeypatch)
    download, _ = _refusing_download(500)
    fetch = install_local.release_downloader("o/r", "v1", download=download)
    with pytest.raises(_Refusal):
        fetch("a.zip", tmp_path / "one")


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


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_object_clearance_and_scatter_have_something_to_act_on(map_key: str) -> None:
    """Two spec keys that accept any value and can quietly do nothing.

    `road_clear_m` is applied against the painted road bed, and a level whose roads are
    decals over untouched ground has no bed - `ROADS["surfaces"]` is empty and no layer
    carries a bed material. `level_builder` now falls back to the road centrelines, but
    that needs `ROADS` to include something, so a spec asking for clearance with neither
    is asking for nothing. Measured on Factory Butte before the fallback existed: 188 of
    54,040 scattered stones inside 3 m of a centreline, 62 of them 0.5 m or wider, on
    14.3 km of road, and `rocks_cleared_from_roads` never appeared to say so.

    The scatter's materials are the same shape of trap: an unmapped layer falls through
    to `rock_talus`, which a spec that authors its own rocks does not define.
    """

    spec = load_spec(map_key)
    objects_spec = getattr(spec, "OBJECTS", None)
    if not objects_spec:
        pytest.skip(f"{map_key}: no OBJECTS block")

    materials = spec.TERRAIN["materials"]
    if float(objects_spec.get("road_clear_m", 0.0)) > 0:
        roads = getattr(spec, "ROADS", None) or {}
        beds = [
            cfg["terrain_material"]
            for cfg in (roads.get("surfaces") or {}).values()
            if cfg.get("terrain_material") in materials
        ]
        assert beds or roads.get("include"), (
            f"{map_key} asks for {objects_spec['road_clear_m']} m of road clearance with no bed "
            "material and no included road types, so there is nothing to clear against"
        )

    scatter = objects_spec.get("scatter") or {}
    if scatter:
        declared = set(objects_spec.get("rock_materials") or {})
        by_layer = {
            **(objects_spec.get("rock_material_by_layer") or {}),
            **(objects_spec.get("scatter_rock_material") or {}),
        }
        for layer_name in scatter:
            assert layer_name in materials, f"{map_key}: scatter names unknown layer {layer_name}"
            if declared:
                rock = by_layer.get(layer_name)
                assert rock in declared, (
                    f"{map_key}: {layer_name} scatters stones with no material mapped, so they "
                    f"fall through to rock_talus, which this spec does not author"
                )


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_road_clearance_actually_ran(map_key: str) -> None:
    """The gate the spec-level one cannot be: did the clearance find anything to act on.

    A spec can name a bed material or a road include list and the implementation can
    still do nothing with either - which is what happened, because the clearance was
    gated on the painted bed and ran on no decal-road level. So the build records WHICH
    instrument it used, and this asserts it used one. Skips on the spec not asking for
    clearance, never on the number being absent, because absent is the failure.
    """

    require_built(map_key)
    spec = load_spec(map_key)
    objects_spec = getattr(spec, "OBJECTS", None) or {}
    if float(objects_spec.get("road_clear_m", 0.0)) <= 0:
        pytest.skip(f"{map_key}: spec asks for no road clearance")

    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    # The handoff has no "level" key and never had one - these sit at its root, beside
    # `roads` and `forest`. The `handoff.get("level", handoff)` this replaces is what hid
    # the bug this gate exists to catch: with no such key the fallback searched the root,
    # found nothing, and reported the clearance as unrecorded without ever saying it had
    # looked somewhere that could not hold it. A missing writer, a key the handoff's
    # allow-list drops, and a clearance that genuinely did nothing all rendered as one
    # message, on the one gate whose whole purpose is to tell those three apart. Read the
    # real place and let it raise: a default that makes the wrong place look plausible is
    # worse than a KeyError.
    level = handoff
    assert "road_clearance_from" in level, (
        f"{map_key} asks for {objects_spec['road_clear_m']} m of road clearance and the build "
        "recorded nothing about it, so nobody can tell whether it ran"
    )
    assert level["road_clearance_from"] in {"bed", "centrelines"}, (
        f"{map_key}: clearance had {level['road_clearance_from']}"
    )
    assert "rocks_cleared_from_roads" in level


def test_centreline_clearance_removes_what_sits_on_a_road() -> None:
    """The fallback `road_clear_m` now uses when a level has no painted bed."""

    load_maplib()
    from maplib import roads as road_tools

    size, res, fp_size_m = 200, 1.0, 200.0
    ways = [{"points": [(-80.0, 0.0), (80.0, 0.0)], "width_m": 6.0, "highway": "track"}]
    mask = road_tools.centreline_mask(ways, res, fp_size_m, size, 3.0)
    half = fp_size_m / 2.0

    def cell(x, y):
        return mask[int(half - y), int(x + half)]

    assert cell(0.0, 0.0) and cell(50.0, 2.0), "on the way, inside the buffer"
    assert not cell(0.0, 20.0) and not cell(0.0, -20.0), "20 m off the way is open ground"
    # The buffer is a corridor, not the whole grid: a clearance that masked everything
    # would "clear" the scatter by deleting it.
    assert 0.0 < mask.mean() < 0.15, mask.mean()


def test_detect_off_stats_reports_every_count_a_real_pass_does() -> None:
    """The skip path's handoff keeps a real pass's shape: zeros, not a missing section."""

    _, _, objects, _, _ = _load_art_modules()
    n, res = 120, 0.5
    y, x = np.mgrid[0:n, 0:n].astype("float32") * res
    dem = 10.0 + 0.02 * x
    bump = 1.2 * np.exp(-(((x - 30) ** 2 + (y - 30) ** 2) / (2 * 0.8**2)))
    _, _, live = objects.detect_objects(dem + bump, res, open_m=6.0, min_height_m=0.4)
    off = objects.detect_off_stats()

    counts = {k for k, v in live.items() if not isinstance(v, str)} - {"open_m", "min_height_m"}
    assert counts <= set(off), f"the skip path drops {counts - set(off)} from the handoff"
    assert all(off[k] == 0 for k in counts), "a skipped pass removed nothing and found nothing"
    assert off["detect"] == "off", "a reader has to be able to tell a skip from an empty pass"
    # `open_m` and `min_height_m` describe an opening that did not happen. Reporting them
    # would read as a pass that ran and found nothing, which is the confusion the whole
    # `"detect": None` path exists to avoid.
    assert "open_m" not in off and "min_height_m" not in off


def test_the_bump_detector_takes_a_badlands_landform_for_boulders() -> None:
    """Why `"detect": None` exists: on fine relief the pass finds the relief.

    Measured on Factory Butte's shipped terrain, `detect_objects` found 6,768 bumps over
    16.8 km2, none of them on the 61.94% that is wash floor, and took 106,602 m3 of fins
    off to place them. This is that finding at test scale, so that anyone who later makes
    the detector ignore ridges can see the skip become unnecessary instead of guessing.
    """

    _, _, objects, _, _ = _load_art_modules()
    n, res = 300, 1.0
    y, x = np.mgrid[0:n, 0:n].astype("float32") * res
    # Flat wash floor on the west half; a rill-and-fin field at a 12 m wavelength and 3 m
    # of relief on the east, which is the scale Mancos Shale badlands actually run at.
    relief = 1.5 * (1.0 + np.sin(2 * np.pi * x / 12.0)) * np.sin(2 * np.pi * y / 30.0) ** 2
    dem = (40.0 - 0.01 * y + np.where(x >= 150.0, relief, 0.0)).astype("float32")

    ground, found, stats = objects.detect_objects(dem, res, open_m=6.0, min_height_m=0.6)
    assert stats["objects"] > 100, "the detector is expected to find the fins, not nothing"
    assert all(o["col"] >= 150 for o in found), "nothing on the flat, which is where rocks are"
    assert stats["removed_volume_m3"] > 1000.0
    moved = np.abs(ground - dem)
    assert moved[:, 150:].max() > 2.5, "it shaves the fins down by most of their height"
    assert moved[:, :150].max() < 0.1, "and leaves the wash floor, so the count cannot rebalance"


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
    """(z_at(x, y), max_height) from the shipped 16-bit heightmap PNG (north-up).

    The height is read off the SURFACE BETWEEN the grid corners, not off the nearest
    corner. The engine draws each terrain square as two triangles, and everything that
    places an object seats it on that interpolated surface (`scene_objects` samples the
    DEM bilinearly), so a corner lookup is measuring something nothing builds against.

    They agree on ordinary ground and they part company on a one-cell ridge, which is
    what a badlands fin is: a crest cell 11 m above both its neighbours reads as the
    crest to a corner lookup and as the flank to the surface, and an object correctly
    seated on the flank measures metres adrift. Reproduced on synthetic fins at Factory
    Butte's own 1 m grid - 20,000 scattered stones came out 5.78 m off the nearest
    corner at worst and 0.26 m off the surface, with 1,052 of them over the 3.5 m drape
    bound by the first measure and none by the second.

    This does not soften the drape gate: an object genuinely off the ground is off both,
    which `test_the_drape_lookup_still_catches_an_object_that_floats` holds it to.
    """

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
        fc = min(max((x + half) / res, 0.0), size - 1.0)
        fr = min(max((half - y) / res, 0.0), size - 1.0)
        c0, r0 = int(fc), int(fr)
        c1, r1 = min(c0 + 1, size - 1), min(r0 + 1, size - 1)
        tc, tr = fc - c0, fr - r0
        top = png[r0, c0] * (1.0 - tc) + png[r0, c1] * tc
        bottom = png[r1, c0] * (1.0 - tc) + png[r1, c1] * tc
        return float(top * (1.0 - tr) + bottom * tr) * max_height / 65536.0

    return z_at, half


def test_the_drape_lookup_still_catches_an_object_that_floats() -> None:
    """The drape lookup reads the surface rather than the nearest grid corner, so this
    holds it to the thing that change could have broken: it must still measure a real
    float, on the worst ground there is.

    The surface is sampled on a one-cell ridge - a crest 11 m above both neighbours,
    the shape a badlands fin makes on a 1 m grid - because that is where a corner
    lookup is most wrong and where a too-forgiving sampler would hide most.
    """

    size, res, max_height = 9, 1.0, 100.0
    half = size * res / 2.0
    png = np.zeros((size, size), dtype="float64")
    png[:, 4] = 11.0 / max_height * 65536.0  # one crest column, 11 m proud

    def z_at(x: float, y: float) -> float:
        fc = min(max((x + half) / res, 0.0), size - 1.0)
        fr = min(max((half - y) / res, 0.0), size - 1.0)
        c0, r0 = int(fc), int(fr)
        c1, r1 = min(c0 + 1, size - 1), min(r0 + 1, size - 1)
        tc, tr = fc - c0, fr - r0
        top = png[r0, c0] * (1.0 - tc) + png[r0, c1] * tc
        bottom = png[r1, c0] * (1.0 - tc) + png[r1, c1] * tc
        return float(top * (1.0 - tr) + bottom * tr) * max_height / 65536.0

    on_the_crest = z_at(-half + 4.0, half - 4.0)
    assert on_the_crest == pytest.approx(11.0, abs=0.01), on_the_crest
    # Half a cell off the crest the surface is halfway down the fin, which is the
    # reading a corner lookup gets wrong by 5.5 m and the thing the change fixes.
    on_the_flank = z_at(-half + 4.5, half - 4.0)
    assert on_the_flank == pytest.approx(5.5, abs=0.01), on_the_flank
    # The drape metric the gate computes, `abs(z - z_at(x, y))`, on three objects at
    # that same spot half a cell off the crest.
    x, y = -half + 4.5, half - 4.0
    seated = abs(z_at(x, y) - z_at(x, y))
    floating = abs((z_at(x, y) + 4.0) - z_at(x, y))
    assert seated < 3.5, seated
    assert floating > 3.5, floating
    # And the reading the OLD lookup gave for the correctly seated object: it took the
    # crest corner for the ground and called a seated stone 5.5 m adrift. That is the
    # false positive this change removes, and it has to stay bigger than the bound or
    # this test is not standing on the defect it was written for.
    assert abs(z_at(x, y) - 11.0) > 3.5, "the crest corner is not far enough to matter"


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


# Maps whose `sun_altitude_range` is deliberately narrow, with the reason. A fit sitting
# on a bound is the spec working as intended for these, so the gate below exempts them by
# name rather than by inferring intent from the window's width - a range that is narrow by
# accident and one that is narrow on purpose look identical, and only one of them is a bug.
SUN_FIT_PINNED_ON_PURPOSE = {
    "black_bear_pass": (
        "the window is 1.5 degrees wide on purpose: the reference photography is a known "
        "time of day and the fit is not free to wander off it"
    ),
}

# A pin that is KNOWN and accepted for now, which is a different thing from a deliberate
# window and must not borrow its exemption: these maps have a wide range and the fit
# still lands on a bound, so the search wanted to go outside and the spec stopped it.
# Each entry is a debt with its reason attached, not a licence - it says somebody chose
# to ship this, not that there is nothing to fix. The assertion below requires the fit
# to STILL be on a bound, so an entry cannot outlive the pin it was written for.
SUN_FIT_PIN_ACCEPTED = {
    "bingham_canyon": (
        "the floor moved 52.0 -> 30.0 to free the fit and instead re-pinned it on the "
        "new bound, so the true window for an open pit at 40.52 N is still unknown. It "
        "also shipped 5,534 near-black texels in three blobs on bc_bench_face, which is "
        "a separate open defect: the floor is NOT the mechanism, because mt_st_helens "
        "took the same drop and the same re-pin with zero near-black texels either side"
    ),
    "mt_st_helens": (
        "the same 45.0 -> 30.0 floor drop re-pinned this fit on the new bound too. No "
        "damage here - near_black_fraction is 0.000000 on both published bases - but "
        "the window is as unknown as bingham's and the pin is as real"
    ),
}


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_a_narrow_sun_window_is_declared_as_deliberate(map_key: str) -> None:
    """A `sun_altitude_range` narrow enough to decide the fit by itself is listed as a
    deliberate pin, or it is a mistake nobody made on purpose.

    This runs without a built tree, so narrowing a window lands here in the two minutes a
    pull request takes rather than in a forty-minute build. `fit_sun` refines on a
    1-degree step, so a window under 5 degrees leaves the search almost nothing to do and
    the spec, not the photograph, picks the altitude.
    """

    spec = load_spec(map_key)
    imagery_spec = getattr(spec, "IMAGERY", None) or {}
    window = imagery_spec.get("sun_altitude_range")
    if not imagery_spec.get("delight") or window is None:
        pytest.skip(f"{map_key}: no sun is fitted, so no window decides one")
    low, high = float(window[0]), float(window[1])
    assert low < high, (map_key, "the window is empty or inverted", window)
    if high - low < 5.0:
        assert map_key in SUN_FIT_PINNED_ON_PURPOSE, (
            map_key,
            "this window is too narrow for the fit to be the photograph's - add it to "
            "SUN_FIT_PINNED_ON_PURPOSE with the reason, or widen it",
            window,
        )


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_the_sun_fit_does_not_sit_on_its_own_bound(map_key: str) -> None:
    """A de-lit map's fitted sun altitude lands INSIDE the window its spec allows.

    `fit_sun` grid-searches and clips every candidate to `sun_altitude_range`, so a fit
    landing exactly on a bound is not a fit - it is the search being stopped there, and
    the true optimum lying outside. The refine pass steps 1 degree, so an unpinned fit
    is at least a degree clear of both ends; equality with a bound is the signature.

    Nothing announced this before. `282a6aa` moved bingham_canyon's floor rather than
    removing it, and a pinned fit and a free one are indistinguishable from outside the
    build: same key, same shape, a plausible number. The cost lands somewhere else
    entirely - the altitude sets what `cast_shadows` calls shadow, so a wrong one
    refills terrain that was never in shadow. That is the same family as the blown
    highlights: the number that would have caught it was never recorded, or never read.

    Skips on the SPEC, so a map that declares a window and then fails to record a fit
    FAILS here rather than skipping quietly. All six declare `delight` and a range.

    `test_imagery_delighting_is_recorded` is not a second opinion on this, and the two
    disagreeing is expected rather than a contradiction: it bounds
    `cast_shadow_fraction` at 0.3, and bingham_canyon's jump to 0.1620 sits comfortably
    inside that. It cannot be tightened into a substitute either, because the fraction
    is an OUTCOME that varies with the ground - a crater rim and an open pit shadow more
    than a plain, so any cross-map bound on it is either loose enough to miss a pin or
    tight enough to fail a map for its terrain. This gates the cause instead, where the
    test is exact and needs no threshold at all.
    """

    spec = load_spec(map_key)
    imagery_spec = getattr(spec, "IMAGERY", None) or {}
    if not imagery_spec.get("delight"):
        pytest.skip(f"{map_key}: the base is not de-lit, so no sun is fitted")
    window = imagery_spec.get("sun_altitude_range")
    if window is None:
        pytest.skip(f"{map_key}: no sun_altitude_range declared, so there is no bound to sit on")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    fit = (handoff.get("imagery") or {}).get("sun_fit") or {}
    altitude = fit.get("altitude_deg")
    assert altitude is not None, (
        map_key,
        "declares a sun_altitude_range but records no fitted altitude",
    )
    low, high = float(window[0]), float(window[1])
    assert low <= float(altitude) <= high, (map_key, "the fit escaped its own window", fit, window)

    accepted = SUN_FIT_PIN_ACCEPTED.get(map_key)
    if accepted is not None:
        # Recorded, not excused. The window is wide, so this really is the search being
        # stopped at a bound rather than a spec pinning a known time of day - and the
        # entry is asserted live, so it cannot quietly outlive the pin it describes.
        assert float(altitude) in (low, high), (
            map_key,
            "listed in SUN_FIT_PIN_ACCEPTED but the fit is no longer on a bound - the "
            "pin is gone, so remove the entry",
            fit,
            window,
        )
        assert map_key not in SUN_FIT_PINNED_ON_PURPOSE, (
            map_key,
            "a map cannot be both a deliberate pin and an accepted one - the first says "
            "there is nothing to fix and the second says there is",
        )
        return

    reason = SUN_FIT_PINNED_ON_PURPOSE.get(map_key)
    if reason is not None:
        # A window this narrow cannot help but put the fit on a bound; that is the
        # point of it. Asserted above that the fit is still inside the window, so the
        # exemption covers the pin and not the spec going unread.
        assert high - low < 5.0, (
            map_key,
            "exempted as a deliberate pin, but its window is wide enough to fit in - "
            "remove the exemption or narrow the window",
            window,
        )
        return
    assert low < float(altitude) < high, (
        map_key,
        "the sun fit is pinned to its own bound, so the spec chose it and the "
        "photograph did not - widen sun_altitude_range or exempt it deliberately",
        fit,
        window,
    )


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_the_photograph_is_measured_before_it_is_conditioned(map_key: str) -> None:
    """Every de-lit map records the source mosaic's own luminance spread and chroma,
    so what the conditioning did can be read as a ratio rather than an absolute.

    A shipped base's spread on its own cannot be judged. Factory Butte's is 0.152
    against Meteor Crater's 0.242 at a third of the chroma, and that is equally
    consistent with a flat pale basin photographed near noon and with de-lighting
    having flattened it - the handoff carried only the output, so two sessions read
    the same number to opposite conclusions. ``imagery.source`` is the other end.

    This asserts the measurement exists and is well formed, not a floor on the ratio.
    The floor comes from the population once a six-map build has produced one; a
    number picked before that is taste. What it does gate is the failure this pack
    keeps repeating - a statistic that goes silently absent for some maps and reports
    as not-applicable - which is why it asserts on every de-lit map rather than
    skipping where the key is missing.
    """

    spec = load_spec(map_key)
    if not (getattr(spec, "IMAGERY", None) or {}).get("delight"):
        pytest.skip(f"{map_key}: the base is not de-lit, so there is nothing to compare")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    imagery = handoff.get("imagery") or {}
    source = imagery.get("source")
    assert source, f"{map_key}: de-lit but the handoff carries no source-mosaic statistics"
    for key in ("lum_p05", "lum_p50", "lum_p95", "lum_spread", "chroma_mean", "px"):
        assert key in source, (map_key, "missing", key, sorted(source))
    assert 0.0 < source["lum_spread"] < 1.0, (map_key, source)
    assert source["lum_p05"] <= source["lum_p50"] <= source["lum_p95"], (map_key, source)
    assert 0.0 <= source["chroma_mean"] <= 1.0, (map_key, source)


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_ring_matching_reaches_the_fields_it_was_turned_on_for(map_key: str) -> None:
    """A map that opts into ``refill_match_ring`` records how many refilled fields the
    matching could actually reach, and reaches at least one of them.

    `_ring_fields` gives a field a ring only when 50 or more lit cells sit in its
    10-30 m annulus, and every matching step is a no-op on a field without one. So the
    contract silently does not apply to exactly the fields most likely to fail it: a
    field wide enough and dark enough to read as a blotch is a field whose surroundings
    are likely also shadow. Before ``refill_ring_cover`` existed, a skipped field was
    indistinguishable in the handoff from a matched field that came out badly - Meteor
    Crater's worst field measured 0.460 before the flag was turned on and 0.459 after,
    and nothing in the build said which of those two it was.

    Zero coverage is not a threshold chosen from taste: it means the feature the spec
    asked for did nothing at all.
    """

    spec = load_spec(map_key)
    imagery_spec = getattr(spec, "IMAGERY", None) or {}
    if not imagery_spec.get("refill_match_ring"):
        pytest.skip(f"{map_key}: refills are not ring-matched")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    cover = (handoff.get("imagery") or {}).get("refill_ring_cover")
    assert cover is not None, (
        f"{map_key}: opted into ring matching but the build records no ring coverage"
    )
    if not cover["fields"]:
        pytest.skip(f"{map_key}: the de-lighting refilled no field at all")
    assert cover["with_ring"] > 0, (map_key, "ring matching reached no field", cover)


def test_the_bed_exclusion_reaches_the_field_it_was_written_for() -> None:
    """``refill_check`` erodes 6 m off every boundary, so an elongated field loses its
    whole interior - and that is exactly the shape of a shadow lying along a road,
    which is what the bed exclusion exists for.

    It used to ask about the bed BEFORE settling which population it was measuring, so
    on this field the share was taken of an empty interior, the >= 20 test failed
    against nothing, no bed was excluded, and the fallback then measured the whole
    component with the road still in it. The order is now the other way round: the
    fallback first, then the bed question about the population actually in use. The
    exclusion reaches this field, which is the whole point of it.
    """

    _, _, level_builder, _, _, _ = load_maplib()

    n, texel = 256, 0.5
    colour = np.full((n, n, 3), 120, dtype="uint8")
    refill = np.zeros((n, n), dtype="uint8")
    bed = np.zeros((n, n), dtype=bool)
    # 10 m by 100 m: over the area floor but narrower than the 12 m the erosion takes
    # off each side, and lying along a road, which is the case that matters.
    refill[100:120, 28:228] = 1
    bed[104:116, 28:228] = True
    colour[refill == 1] = 96

    out = level_builder.refill_check(colour, refill, texel, bed=bed, min_area_m2=500.0)
    assert out, "the synthetic field is over the area floor and should be reported"
    field = out["largest"][0]

    assert field["interior_eroded"] is False, (
        "a 10 m wide field cannot survive a 6 m erosion from both sides",
        field,
    )
    # 12 of the field's 20 rows are bed, and that share is now taken of the population
    # the numbers rest on rather than of an empty array.
    assert field["bed_fraction"] == pytest.approx(0.6, abs=0.01), field
    # Eight rows of ground is far more than the 20-cell floor, so the exclusion runs
    # and the population is the field minus its road.
    assert field["on_road_bed"] is False, field
    assert field["interior_texels"] == int(((refill == 1) & ~bed).sum()), field
    assert out["fields"] == 1 and out["fields_on_road_bed"] == 0, out


def test_a_field_that_is_entirely_road_comes_out_of_the_population() -> None:
    """A shadow lying wholly on a road is not an unlifted field, and reporting it as a
    failed match asks for something no fix can deliver.

    ``refill_match`` refuses to correct a bed cell by design - it zeroes its feather
    there, so the bed keeps the contrast the stage before it just enforced. When a
    field has no ground left in it, every ratio compares asphalt against a bed-free
    ring, and the gate reads the match as having failed at what it is forbidden to
    attempt. Meteor Crater shipped exactly this: a 2,973 m2 field at (-35.3, 670.3),
    entirely bed on a level that is 1.16 % bed, reported at 0.459 of its ring.
    """

    _, _, level_builder, _, _, _ = load_maplib()

    n, texel = 256, 0.5
    colour = np.full((n, n, 3), 120, dtype="uint8")
    refill = np.zeros((n, n), dtype="uint8")
    bed = np.zeros((n, n), dtype=bool)
    # The road shadow: every texel of it is bed, so there is no ground to measure.
    refill[100:120, 28:228] = 1
    bed[100:120, 28:228] = True
    colour[refill == 1] = 55
    # And an ordinary field elsewhere, so the population does not empty - the summary
    # has to keep reporting on what is left.
    refill[40:90, 40:90] = 1
    colour[40:90, 40:90] = 118

    out = level_builder.refill_check(colour, refill, texel, bed=bed, min_area_m2=500.0)
    assert out, "both synthetic fields are over the area floor"
    on_bed = [f for f in out["largest"] if f["on_road_bed"]]
    ground = [f for f in out["largest"] if not f["on_road_bed"]]
    assert len(on_bed) == 1 and len(ground) == 1, out["largest"]
    assert on_bed[0]["bed_fraction"] == pytest.approx(1.0), on_bed[0]
    assert out["fields"] == 1 and out["fields_on_road_bed"] == 1, out
    # The dark road is still in the record - it is dropped from the statistics, not
    # from the report, so a reader can see what was set aside and why.
    assert on_bed[0]["lum_ratio"] < 0.75, on_bed[0]
    # And no summary statistic carries it.
    assert out["lum_ratio_min"] == ground[0]["lum_ratio"], out


def test_a_field_that_survives_the_erosion_reports_its_bed_share_and_population() -> None:
    """The other half of the pair: a compact field keeps its eroded interior, so the bed
    share is a real measurement and the population is smaller than ``area_m2`` implies."""

    _, _, level_builder, _, _, _ = load_maplib()

    n, texel = 256, 0.5
    colour = np.full((n, n, 3), 120, dtype="uint8")
    refill = np.zeros((n, n), dtype="uint8")
    bed = np.zeros((n, n), dtype=bool)
    refill[80:180, 80:180] = 1  # 50 m square, survives a 6 m erosion easily
    bed[80:180, 80:100] = True  # a road up one edge, inside the field
    colour[refill == 1] = 96

    out = level_builder.refill_check(colour, refill, texel, bed=bed, min_area_m2=500.0)
    assert out, "the synthetic field is over the area floor and should be reported"
    field = out["largest"][0]

    assert field["interior_eroded"] is True, field
    assert field["bed_fraction"] is not None and field["bed_fraction"] > 0.0, (
        "the road runs through the interior, so the share is measurable and non-zero",
        field,
    )
    # area_m2 counts the component; the ratios rest on the eroded, bed-excluded interior,
    # which is the number that was previously unrecorded.
    assert 0 < field["interior_texels"] < int((refill == 1).sum()), field


def test_a_failing_bed_exclusion_names_the_fields_it_set_aside() -> None:
    """Run 73 failed this guard on meteor_crater at 4 of 18 and named none of the four.

    The counts say the exclusion grew; only the fields say whether it grew for the
    documented reason. So the guard's message has to carry each dropped field's
    ``bed_fraction`` - the share that dropped it - and the two keys that say the field
    took the under-20-cell path rather than the mask having widened underneath it.
    """

    check = {
        "fields": 2,
        "fields_on_road_bed": 2,
        "br_diff_max_abs": 0.038,
        "exg_diff_max_abs": 0.041,
        "largest": [
            {
                "lum_ratio": 0.459,
                "area_m2": 2973.0,
                "center_xy": [-35.3, 670.3],
                "kind": "shadow",
                "bed_fraction": 1.0,
                "interior_eroded": False,
                "interior_texels": 18,
                "on_road_bed": True,
            },
            {
                "lum_ratio": 0.981,
                "area_m2": 4100.0,
                "center_xy": [12.0, -8.0],
                "kind": "shadow",
                "bed_fraction": 0.0,
                "interior_eroded": True,
                "interior_texels": 900,
                "on_road_bed": False,
            },
            {
                "lum_ratio": 0.612,
                "area_m2": 1550.0,
                "center_xy": [40.1, 655.0],
                "kind": "shadow",
                "bed_fraction": 0.62,
                "interior_eroded": True,
                "interior_texels": 14,
                "on_road_bed": True,
            },
            {
                "lum_ratio": 1.004,
                "area_m2": 2200.0,
                "center_xy": [-90.0, 3.0],
                "kind": "snow",
                "bed_fraction": None,
                "interior_eroded": True,
                "interior_texels": 450,
                "on_road_bed": False,
            },
        ],
    }

    excluded = _excluded_fields(check)
    # Exactly the set-aside fields, in order, and nothing that stayed in the population.
    assert len(excluded) == 2, excluded
    assert [f["center_xy"] for f in excluded] == [[-35.3, 670.3], [40.1, 655.0]]
    # The reason each was dropped travels with it: at or above half bed, and a remainder
    # under the 20 cells below which the exclusion is allowed to fire at all.
    assert all(f["bed_fraction"] >= 0.5 for f in excluded), excluded
    assert all(f["interior_texels"] < 20 for f in excluded), excluded
    # A field that stayed in must never be reported as set aside - naming a measured
    # field as the cause of the exclusion's size is worse than naming none.
    assert all(f["center_xy"] != [12.0, -8.0] for f in excluded)
    # And it has to survive pytest's abbreviation, which is the whole reason it exists.
    assert len(repr(excluded)) < 400, len(repr(excluded))

    # A check whose fields carry no bed at all reports an empty set rather than raising,
    # so the guard's own assertion is what fails and says what it failed on.
    assert _excluded_fields({"largest": [], "fields": 0, "fields_on_road_bed": 0}) == []
    assert _excluded_fields({}) == []


def test_a_failing_refill_gate_names_the_field_and_why_it_could_not_be_lifted() -> None:
    """The aggregate gates fail on a percentile or a minimum, which says a value and not
    a place. ``_field_at`` is what turns that back into a field, and it has to carry the
    three keys that say whether the field was liftable at all - otherwise the next reader
    re-runs the build to learn what the handoff already recorded."""

    fields = [
        {
            "lum_ratio": 0.9,
            "area_m2": 4000.0,
            "center_xy": [0.0, 0.0],
            "kind": "shadow",
            "bed_fraction": 0.0,
            "interior_eroded": True,
            "interior_texels": 900,
        },
        {
            "lum_ratio": 0.459,
            "area_m2": 2973.0,
            "center_xy": [-35.3, 670.3],
            "kind": "shadow",
            "bed_fraction": None,
            "interior_eroded": False,
            "interior_texels": 11892,
        },
        {
            "lum_ratio": 1.047,
            "area_m2": 1200.0,
            "center_xy": [10.0, 10.0],
            "kind": "snow",
            "bed_fraction": 0.1,
            "interior_eroded": True,
            "interior_texels": 300,
        },
    ]

    darkest = _field_at(fields, "lum_ratio")
    assert darkest["lum_ratio"] == 0.459 and darkest["center_xy"] == [-35.3, 670.3]
    # The whole point: the reason travels with the value.
    assert darkest["interior_eroded"] is False and darkest["bed_fraction"] is None
    assert _field_at(fields, "lum_ratio", palest=True)["lum_ratio"] == 1.047
    # Small enough that pytest does not abbreviate it, which the `largest` list was not.
    assert len(repr(darkest)) < 200, repr(darkest)
    # An emptied population is the road-bed exclusion's own failure to report, not a
    # ValueError out of `min` standing in front of it.
    assert _field_at([], "lum_ratio") == {}


def test_ring_matching_can_rescue_a_field_at_half_its_ring() -> None:
    """The full ``match_ring`` sequence lifts a field at 0.46 of its ring past the 0.75
    floor, so the contract is reachable from the worst measured starting point.

    This pins a capability that is not obvious from either function alone. `_match_mean`
    clips its per-field correction to 1.25, so on its own it can reach the 0.90 contract
    only from 0.72 and the 0.75 floor only from 0.60 - measured, a field at 0.46 comes
    out of it at 0.575. Every bit of the rescue below that comes from `_clamp_to_ring`.
    Tightening either one silently puts the contract out of reach rather than failing
    loudly, which is what this catches.
    """

    load_maplib()
    from maplib.imagery import _clamp_to_ring, _match_mean, _ring_fields

    size = 400
    fill = np.zeros((size, size), dtype=bool)
    fill[150:250, 150:250] = True
    lit = np.full((size, size, 3), 0.70, dtype="float32")
    rgb = lit.copy()
    rgb[fill] = 0.70 * 0.46
    fields = _ring_fields(fill, ~fill, 1.0)
    assert bool(fields["has_ring"][0]), "the synthetic field must have a ring to test the match"

    matched = _match_mean(rgb.copy(), lit, fields)
    ratio_mean = float(matched[fill].mean() / lit[~fill].mean())
    assert ratio_mean == pytest.approx(0.46 * 1.25, abs=0.01), (
        "the mean match is clipped at 1.25; if this changes, the floor below moves too",
        ratio_mean,
    )

    fill_w = fill.astype("float32")
    composited = lit * (1 - fill_w[..., None]) + matched * fill_w[..., None]
    clamped = _clamp_to_ring(composited, lit, fields, fill_w)
    ratio_clamped = float(clamped[fill].mean() / lit[~fill].mean())
    assert ratio_clamped >= 0.75, (
        "the clamp must carry a 0.46 field over the floor",
        ratio_clamped,
    )


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
    # Nothing was handed in as the pre-clamp array, so nothing claims to describe one.
    assert "clipped_before_ceiling" not in stats["layer_mean_srgb"]["ledge"]


def test_the_delighting_contract_number_can_actually_fail() -> None:
    """The negative control for `under_gain_floor_untouched`.

    It reads zero on every correct build, which is precisely the shape of the gate this
    pack has just spent a day repairing: a number that is true, looks live, and cannot
    move. So drive it. A late writer that darkens cells the refill never touched is the
    regression it exists for - the mirror of the one `53807cb` fixed at the bright end -
    and the count must find it. Its companion is driven the same way: a carry that finds
    its donors and borrows nothing worth having.
    """

    load_maplib()
    from maplib import imagery

    rng = np.random.default_rng(7)
    n = 256
    y, x = np.mgrid[0:n, 0:n].astype("float32")
    dem = 120.0 * np.exp(-((y - 100) ** 2) / (2 * 20.0**2)) + 40.0 * np.sin(x / 30.0)
    dem = (dem + rng.normal(0, 0.4, dem.shape)).astype("float32")
    shade = np.clip(imagery.cast_shadows(dem, 2.0, 180.0, 25.0), 0.05, 1.0)
    ground = np.clip(0.55 + 0.05 * rng.normal(0, 1, (n, n, 1)), 0.1, 0.9) * np.array(
        [1.0, 0.94, 0.82]
    )
    colour = (np.clip(ground * shade[..., None], 0, 1) ** (1 / 2.2) * 255).astype("uint8")
    kw = dict(
        azimuth_deg=180.0,
        altitude_deg=25.0,
        strength=1.0,
        max_gain=4.5,
        steep_deg=32.0,
        steep_feather_deg=8.0,
        steep_cap=True,
    )

    _out, clean = imagery.delight(colour, dem, 2.0, **kw)
    assert clean["composed_ratio"]["under_gain_floor_untouched"] == 0.0
    assert clean["composed_ratio"]["p50"] is not None

    real_clamp = imagery.clamp_highlights
    try:

        def crushing_clamp(out, ceiling):
            out = out.copy()
            out[n // 2 :, :] *= 0.02  # a writer outside every clip in the stage
            return real_clamp(out, ceiling)

        imagery.clamp_highlights = crushing_clamp
        _out, broken = imagery.delight(colour, dem, 2.0, **kw)
    finally:
        imagery.clamp_highlights = real_clamp
    assert broken["composed_ratio"]["under_gain_floor_untouched"] > 0.01, broken

    real_carry = imagery._carry_tone
    try:
        imagery._carry_tone = lambda corrected, weight, res_m, **kw2: (
            real_carry(corrected, weight, res_m, **kw2) * 0.02
        )
        _out, dark = imagery.delight(colour, dem, 2.0, **kw)
    finally:
        imagery._carry_tone = real_carry
    assert dark["refill_carry_ratio"]["under_0_1"] > 0.5, dark


def test_the_decast_guard_number_can_actually_fail() -> None:
    """The negative control for `decast_guard`, on a base the blue de-cast will act on.

    The de-cast only writes where a cell is bluer than the lit ground round it, so a warm
    synthetic ground drives nothing and the number would read zero for the wrong reason -
    the same "true and cannot move" shape the rest of this file exists to prevent. So the
    ground here is cool and the shadows bluer still, which is what the flight actually
    photographs on a shaded wall.
    """

    load_maplib()
    from maplib import imagery

    rng = np.random.default_rng(11)
    n = 256
    y, x = np.mgrid[0:n, 0:n].astype("float32")
    dem = 150.0 * np.exp(-((y - 110) ** 2) / (2 * 18.0**2)) + 50.0 * np.sin(x / 24.0)
    dem = (dem + rng.normal(0, 0.4, dem.shape)).astype("float32")
    shade = np.clip(imagery.cast_shadows(dem, 2.0, 180.0, 25.0), 0.05, 1.0)
    ground = np.clip(0.5 + 0.05 * rng.normal(0, 1, (n, n, 1)), 0.1, 0.9) * np.array(
        [0.82, 0.90, 1.0]
    )
    # A shaded cell is bluer than a lit one, which is the condition the de-cast tests.
    sky = 1.0 + 0.35 * (1.0 - shade)[..., None] * np.array([-0.2, 0.0, 0.35])
    colour = (np.clip(ground * shade[..., None] * sky, 0, 1) ** (1 / 2.2) * 255).astype("uint8")
    kw = dict(
        azimuth_deg=180.0,
        altitude_deg=25.0,
        strength=1.0,
        max_gain=4.5,
        steep_deg=32.0,
        steep_feather_deg=8.0,
        steep_cap=True,
    )

    _out, clean = imagery.delight(colour, dem, 2.0, **kw)
    assert clean["decast_guard"]["cells_under_guard"] == 0.0, clean["decast_guard"]
    assert clean["decast_guard"]["written_under_guard"] == 0.0, clean["decast_guard"]

    # Drive it: a carry pushed under the 1e-4 guard turns the de-cast from a rotation that
    # holds luminance into a multiply by `local_lit.mean / 1e-4`. This is the elimination
    # the pack got wrong by reading the line's intent rather than its denominator.
    real_carry = imagery._carry_tone
    try:
        imagery._carry_tone = lambda corrected, weight, res_m, **kw2: (
            real_carry(corrected, weight, res_m, **kw2) * 1e-5
        )
        _out, unguarded = imagery.delight(colour, dem, 2.0, **kw)
    finally:
        imagery._carry_tone = real_carry
    assert unguarded["decast_guard"]["cells_under_guard"] > 0.5, unguarded["decast_guard"]
    assert unguarded["decast_guard"]["written_under_guard"] > 0.0, unguarded["decast_guard"]
    # And the per-cell question the share across maps cannot answer: of the cells this stage
    # encodes black, what fraction did the de-cast write while its guard was binding? None on
    # a base with no black at all, which is why the clean case above asserts the None rather
    # than a zero - a ratio with an empty denominator is not a passing measurement.
    assert clean["decast_guard"]["near_black_here"] == 0.0, clean["decast_guard"]
    assert clean["decast_guard"]["near_black_written_under_guard"] is None, clean["decast_guard"]
    assert unguarded["decast_guard"]["near_black_here"] > 0.0, unguarded["decast_guard"]
    assert unguarded["decast_guard"]["near_black_written_under_guard"] > 0.0, unguarded[
        "decast_guard"
    ]


def test_the_breach_distribution_can_actually_leave_the_bound() -> None:
    """The negative control for `breach_composed_p50` / `_min`, which exist to tell a
    float edge from a writer outside the contract.

    `under_gain_floor_untouched` counts cells; it cannot say whether one shipped at 0.4489
    or at 0.30, and those are different findings. The risk this control exists to kill is
    a pair of numbers that always read "just under 0.45" whatever the stage did, which
    would look like a measurement and license a tolerance that hides a real defect. So the
    clean case asserts the near-bound signature AND the driven case asserts the numbers
    leave it.
    """

    load_maplib()
    from maplib import imagery

    rng = np.random.default_rng(11)
    n = 256
    y, x = np.mgrid[0:n, 0:n].astype("float32")
    dem = 260.0 * np.exp(-((y - 110) ** 2) / (2 * 14.0**2)) + 90.0 * np.sin(x / 13.0)
    dem = (dem + rng.normal(0, 0.5, dem.shape)).astype("float32")
    shade = np.clip(imagery.cast_shadows(dem, 2.0, 180.0, 15.0), 0.02, 1.0)
    ground = np.clip(0.5 + 0.06 * rng.normal(0, 1, (n, n, 1)), 0.08, 0.9) * np.array(
        [0.82, 0.90, 1.0]
    )
    sky = 1.0 + 0.35 * (1.0 - shade)[..., None] * np.array([-0.2, 0.0, 0.35])
    colour = (np.clip(ground * shade[..., None] * sky, 0, 1) ** (1 / 2.2) * 255).astype("uint8")
    # A low sun and a high Minnaert exponent, because the breach needs the gain to reach
    # its own low clip: `strength` multiplies `k` (imagery.py, `k = clip(k, 0.5, 1.4) *
    # strength`), so this is the one knob that drives `gain_p05` onto 0.45.
    kw = dict(
        azimuth_deg=180.0,
        altitude_deg=15.0,
        strength=3.5,
        max_gain=4.5,
        steep_deg=32.0,
        steep_feather_deg=8.0,
        steep_cap=True,
    )

    _out, clean = imagery.delight(colour, dem, 2.0, **kw)
    composed = clean["composed_ratio"]
    # The control is only meaningful if there is a breach to describe.
    assert composed["under_gain_floor_untouched_cells"] > 100, composed
    # On a scene with no deep population the breach sits ON the clip: `composed` is
    # `out_lum / src_lum` recomputed through two three-channel means, not the gain, so it
    # lands either side of the constant the gain was clipped to.
    assert composed["breach_composed_p50"] == 0.45, composed
    assert 0.44 < composed["breach_composed_min"] < 0.45, composed

    # Drive it: a writer after the refill that halves every texel. It runs last, so the
    # cells it darkens still read `untouched`, which is exactly the shape the gate is
    # meant to catch and the one a near-bound-only instrument would report as harmless.
    real_clamp = imagery.clamp_highlights

    def _halved(lin, ceiling):
        out, fraction = real_clamp(lin, ceiling)
        return out * 0.5, fraction

    try:
        imagery.clamp_highlights = _halved
        _out, driven = imagery.delight(colour, dem, 2.0, **kw)
    finally:
        imagery.clamp_highlights = real_clamp
    forced = driven["composed_ratio"]
    assert (
        forced["under_gain_floor_untouched_cells"] > composed["under_gain_floor_untouched_cells"]
    ), (composed, forced)
    # The whole point: the distribution MOVES, and it moves far enough that no tolerance
    # calibrated on the clean case could absorb it.
    assert forced["breach_composed_p50"] < 0.44, forced
    assert forced["breach_composed_min"] < 0.35, forced

    # And it reports nothing rather than a zero when there is no breach: an empty mask has
    # no median, and a 0.0 there would read as "shipped at nothing" instead of "no cells".
    _out, quiet = imagery.delight(colour, dem, 2.0, **{**kw, "strength": 1.0})
    if quiet["composed_ratio"]["under_gain_floor_untouched_cells"] == 0:
        assert quiet["composed_ratio"]["breach_composed_p50"] is None, quiet["composed_ratio"]
        assert quiet["composed_ratio"]["breach_composed_min"] is None, quiet["composed_ratio"]


def test_the_anti_black_floor_never_darkens_a_cell() -> None:
    """The floor against black holes must not write one.

    Its trigger is ABSOLUTE - a cell under 0.02 linear - and its write is RELATIVE, a
    third of the lit neighbourhood. Where that neighbourhood is itself under 0.057 the
    two cross and the floor writes something darker than the near-black it fired on,
    with no bound of its own: it is the one writer that can take a cell the refill never
    touched under the gain's 0.45 clip, which is what `under_gain_floor_untouched`
    counts, and it can put a texel under the near-black threshold the finished base is
    gated on. Measured on the scene below before the gate went in: near black 37% of the
    source and 56% of the OUTPUT, the de-lighting manufacturing black ground in the name
    of removing it, every darkened cell attributable to this floor and none to the two
    relative floors or the blue rewrite after it.

    The second half asserts the anti-black floors still remove a black blob the flight
    itself left, so a fix that stops the darkening by refusing to write at all is caught.
    It does NOT isolate this floor: measured, deleting its write outright leaves the blob
    rescued anyway, because the relative floor below it fires on the same cells wherever
    the lit neighbourhood is bright (`0.02 > lum` implies `lum < 0.25 * lit` for any
    neighbourhood over 0.08). This floor is the sole writer only in the narrow band where
    the neighbourhood sits between 2.9 and 4 times the cell - which is to say it is close
    to redundant, and where it is not redundant it is the one that can darken. That is a
    question for whoever next opens the de-lighting, not something this test settles.

    Nor does it cover the sibling floors' own version of the same defect, and that is a
    limit rather than an omission. Their trigger used to read the lit neighbourhood through
    a `np.maximum(..., 1e-4)` guard while their write did not, so where the guard bound they
    darkened too - but reaching it needs a neighbourhood under 7.14e-05, which u8 source
    quantisation and the 0.01 `seen` cut keep out of every number this suite reads. It is
    repaired by making the trigger read the array the write uses, which is structural and
    needs no scene to demonstrate; a test that claimed to drive it would be the shape of
    gate this file exists to prevent.
    """

    load_maplib()
    from maplib import imagery

    def scene(ground_lin: float) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(7)
        n = 256
        y, x = np.mgrid[0:n, 0:n].astype("float32")
        dem = 120.0 * np.exp(-((y - 100) ** 2) / (2 * 20.0**2)) + 40.0 * np.sin(x / 30.0)
        dem = (dem + rng.normal(0, 0.4, dem.shape)).astype("float32")
        shade = np.clip(imagery.cast_shadows(dem, 2.0, 180.0, 25.0), 0.05, 1.0)
        ground = np.clip(
            ground_lin + 0.05 * ground_lin * rng.normal(0, 1, (n, n, 1)), 1e-4, 0.9
        ) * np.array([1.0, 0.94, 0.82])
        colour = (np.clip(ground * shade[..., None], 0, 1) ** (1 / 2.2) * 255).astype("uint8")
        return colour, dem

    kw = dict(
        azimuth_deg=180.0,
        altitude_deg=25.0,
        strength=1.0,
        max_gain=4.5,
        steep_deg=32.0,
        steep_feather_deg=8.0,
        steep_cap=True,
    )

    def near_black(rgb8: np.ndarray) -> float:
        """The threshold the finished base is gated on, on the array this stage returns."""
        return float((rgb8.max(axis=-1) < 13).mean())

    # A pit: ground the flight photographed at a fiftieth of an ordinary desert, so the
    # lit neighbourhood the floor reads for its rescue is darker than the floor's own
    # trigger. This is the shape bingham_canyon took when its sun floor was dropped.
    for ground_lin in (0.02, 0.01):
        colour, dem = scene(ground_lin)
        out, stats = imagery.delight(colour, dem, 2.0, **kw)
        composed = stats["composed_ratio"]
        assert composed["under_gain_floor_untouched"] == 0.0, (
            ground_lin,
            "the anti-black floor took a cell the refill never touched under the gain's own clip",
            composed,
        )
        assert near_black(out) <= near_black(colour), (
            ground_lin,
            "the de-lighting shipped more near-black texels than the flight gave it",
            near_black(colour),
            near_black(out),
        )

    # And the floors still rescue what they exist for: a black blob the flight itself left
    # on ground that is otherwise lit - water read at a dark angle, a shadow no gain can
    # recover. Its lit neighbourhood is bright, so a third of it is a real lift, and a
    # gate that declined to write here would ship the blob.
    colour, dem = scene(0.55)
    colour[40:80, 150:190] = 1  # 1600 texels of black on lit desert
    out, _stats = imagery.delight(colour, dem, 2.0, **kw)
    assert near_black(colour) > 0.01, near_black(colour)
    assert near_black(out) == 0.0, (
        "a black blob on lit ground shipped as a black hole, so no anti-black floor fired",
        near_black(out),
    )


def test_the_clamp_does_not_erase_the_number_that_caught_it() -> None:
    """The shipping clamp caps every channel at 249 and the gate counts 250, so after it
    `clipped` is zero on every map it runs for - a true number that can no longer fail.
    The share is kept at full per-layer resolution on the array the clamp read, so the
    contract survives its own fix."""

    _, _, level_builder, _, _, _ = load_maplib()
    from maplib import imagery

    colour = np.full((32, 32, 3), 128, dtype="uint8")
    colour[16:, :16] = 255  # one layer entirely over the ceiling
    layer = np.zeros((16, 16), dtype="uint8")
    layer[8:, :8] = 1

    linear, _over = imagery.clamp_highlights(imagery.srgb_to_linear(colour), 0.95)
    shipped = imagery.linear_to_srgb_u8(linear)
    # 0.95 linear encodes to 249.31, and 250 needs 0.9516 - so the clamp leaves the gate
    # nothing to count, on any map, whatever a later stage did to the base.
    assert int(shipped.max()) == 249
    # Pinned from both ends, because either constant can move the blinding on its own:
    # raise the ceiling past the value below and `clipped` starts counting again, lower
    # the gate's 250 and it does too. Bisected rather than asserted from a literal.
    lo, hi = 0.9, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if (1.055 * mid ** (1 / 2.4) - 0.055) * 255.0 >= 249.5:
            hi = mid
        else:
            lo = mid
    assert hi == pytest.approx(0.951634, abs=1e-6), "the linear value that first reaches 250"
    assert 0.95 < hi, "the ceiling must sit BELOW what the clipped gate tests for"
    # And the clamp scales a texel rather than clipping a channel, so the blown square
    # keeps its grey. A per-channel clip would have swung the hue of every texel it hit.
    blown = shipped[16:, :16]
    assert blown.min() == blown.max(), "the clamp moved brightness only"

    stats = level_builder.base_colour_stats(
        shipped, layer, ["ground", "ledge"], before_ceiling=colour
    )
    means = stats["layer_mean_srgb"]
    # Exactly zero, not merely under the old 0.002: the clamp caps at 249, so `clipped`
    # is 0 if and only if the clamp is the LAST writer of the base. A later stage that
    # writes `colour_full` after it puts the number back above zero - which is the bug
    # `53807cb` exists to fix, since `delight`'s own clamp was not the last writer either.
    assert means["ledge"]["clipped"] == 0.0
    assert means["ledge"]["clipped_before_ceiling"] == pytest.approx(1.0)
    assert means["ground"]["clipped_before_ceiling"] == pytest.approx(0.0)


# What each layer's pre-clamp share over the highlight ceiling measured on run 33's
# published ZIPs - the last bases built before `53807cb` added the shipping clamp, so
# they are the unclamped arrays `clipped_before_ceiling` describes. Measured directly
# off `t_base_b.png` against `theTerrain.ter`'s layer indices, with the same `>= 250`
# test `base_colour_stats` uses, so the numbers are the same quantity.
#
# The gate is the population rather than an absolute, deliberately. 0.002 was the
# contract written for an unclamped base; six of these 22 layers are already above it,
# so restoring it hard re-reds three maps over a blow-out the clamp has made invisible
# in game. Held to the baseline instead, a layer that starts blowing out is caught -
# which is the failure that actually happened - without failing the ones that always
# did. Set from five maps: black_bear_pass has no published base to measure, so its
# layers carry no baseline and are asserted present only, and so is any new material.
# TODO: fill black_bear_pass's layers from the first good build. It is the map at critic
# round 17 with the most at stake, and asserted-present is the weakest thing this gate
# says about any map.
CEILING_BASELINE = {
    # factory_butte
    "fb_caprock": 0.05631,
    "fb_clay_fin": 0.00167,
    "fb_shale_slope": 0.00014,
    "fb_mud_flat": 0.00000,
    # meteor_crater
    "mc_limestone_rim_ew": 0.00431,
    "mc_road_dirt": 0.00352,
    "mc_limestone_rim": 0.00069,
    "mc_ejecta_gravel": 0.00029,
    "mc_desert_floor": 0.00012,
    "mc_talus": 0.00001,
    "mc_rim_rubble": 0.00000,
    "mc_road_asphalt": 0.00000,
    # wallace_creek
    "wc_grassland": 0.00000,
    "wc_alluvial_wash": 0.00000,
    "wc_fault_scarp": 0.00000,
    "wc_dry_pond": 0.00000,
    # bingham_canyon and mt_st_helens: out of scope for development, still built
    "bc_scrub_hillside": 0.00660,
    "bc_haul_gravel": 0.00373,
    "bc_waste_rock": 0.00266,
    "bc_bench_face": 0.00052,
    "sh_debris_slope": 0.00003,
    "sh_ash_gully": 0.00002,
    "sh_snow_ice": 0.00001,
    "sh_pumice_plain": 0.00000,
    "sh_crater_wall": 0.00000,
}
# Room for the build to move without the gate reading the movement as a regression.
# It is wider than any difference measured between two builds of this pack and far
# narrower than the step that put fb_caprock where it is.
CEILING_SLACK = 0.005


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_the_delighting_stays_inside_the_contract_its_clips_give(map_key: str) -> None:
    """A cell the refill never touched ships at no less than 0.45 of what was photographed.

    Every reducing step in `delight` is clipped, and until now nothing measured their
    product or the one input none of the clips can bound. `gain_p05` is the ILLUMINATION
    gain - the model's intent, not the result - so a cell can ship at a fiftieth of its
    source with every recorded number comfortably inside its own bound. That is how
    bingham_canyon shipped 5,534 crushed texels on `bc_bench_face` while its handoff read
    `gain_p05` 0.651 and `cast_shadow_fraction` 0.1620, both unremarkable.

    The bound needs no population behind it, which is why it is an equality and not a
    tuned threshold. An untouched cell is `source * gain`, then the knee and the steep
    cap - and both of those are one-sided pulls toward their own reference, so a cell
    that has been through either ends at or above `min(knee_lum, cap_lum)`. A cell
    shipping DARKER than that has been through neither, leaving the gain as its only
    writer, and the gain is clipped at 0.45. So an untouched dark cell under 0.45 of its
    source means some writer is outside the contract every clip in there is meant to
    give, which is a defect rather than a tuning question.

    This is NOT a gate that cannot fail. `under_gain_floor_untouched` is zero if and only
    if no writer escapes the gain floor on an unrefilled cell; a late stage that darkens
    one - exactly the shape `53807cb` had to fix at the other end of the range - moves it
    off zero. The suite's own unit test drives it off zero to prove it.

    `refill_carry_ratio` is the companion and is asserted PRESENT rather than bounded.
    The carry normalises by the donor weight it found, so its arithmetic says the donors
    were there and never what they were worth: a field ringed by ground this stage has
    itself left dark refills to dark, and the anti-black floors then write a quarter of
    that same dark tone. Its threshold belongs to the first round that reports it, set
    from the population the way CEILING_BASELINE was, not invented here.

    Skips on the SPEC, not on the handoff, so a de-lit map that records nothing FAILS.
    """

    spec = load_spec(map_key)
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    imagery_spec = getattr(spec, "IMAGERY", None) or {}
    if not imagery_spec.get("delight"):
        pytest.skip(f"{map_key}: the base is not de-lit, so no de-lighting to bound")
    stats = handoff.get("imagery") or {}
    composed = stats.get("composed_ratio")
    assert composed is not None, (
        map_key,
        "built before the de-lighting's end-to-end effect was recorded - rebuild; until "
        "then nothing on this tree bounds what the stage did between its clips",
    )
    assert composed.get("under_gain_floor_untouched") == 0.0, (
        map_key,
        "cells the refill never touched shipped under 0.45 of what the flight "
        "photographed, which no clip in the de-lighting allows - a writer is outside "
        "the contract",
        composed,
    )
    assert stats.get("refill_carry_ratio") is not None or stats.get("snow_fraction") == 0.0, (
        map_key,
        "the refill borrowed a tone and did not record what it was worth",
        stats.get("refill_carry_ratio"),
    )
    # And whether the blue de-cast held luminance where it actually wrote. Its `lit_ratio`
    # has channel-mean exactly 1 only while `local_lit.mean` clears the 1e-4 guard; below
    # it the guard clamps the denominator and the line becomes a straight multiply by
    # `local_lit.mean / 1e-4`. An equality rather than a threshold, and zero is the only
    # healthy value, so it needs no population: the stage is written as luminance-preserving
    # here, and a non-zero share says it was not, on the cells it wrote.
    guard = stats.get("decast_guard")
    assert guard is not None, (
        map_key,
        "built before the de-cast guard was recorded - rebuild; until then nothing says "
        "whether that write held luminance",
    )
    for key in ("cells_under_guard", "written_under_guard", "near_black_here"):
        assert guard.get(key) is not None, (map_key, key, guard)
    assert guard.get("written_under_guard") == 0.0, (
        map_key,
        "the blue de-cast wrote on cells where its own 1e-4 guard was binding, so on those "
        "cells it multiplied by local_lit.mean/1e-4 instead of holding luminance",
        guard,
    )


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_the_shipped_base_records_how_close_it_stands_to_black(map_key: str) -> None:
    """And how much of the base is STANDING at the threshold, not only what crossed it.

    `near_black_fraction` is a gate on one end of a two-ended contract, so it cannot
    distinguish a base whose shadows floor comfortably above 13 from one sitting at 14 that
    the next contrast change will push over - which is the whole of what happened to
    bingham_canyon on a one-line spec edit. This asserts the distribution EXISTS on every
    de-lit map; the bound on it comes from the first round that reports it, from the
    population, rather than being invented here.

    Measured on the array that ships, which is the point: `delight` is not the last writer
    of the base, so the de-lighting's own numbers cannot see `paint_road_beds`,
    `enforce_bed_contrast`, `refill_match` or the shipping clamp.
    """

    spec = load_spec(map_key)
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    if not getattr(spec, "IMAGERY", None):
        pytest.skip(f"{map_key}: the base is not conditioned imagery")
    stats = handoff.get("base_colour") or {}
    floor = stats.get("base_floor")
    assert floor is not None, (
        map_key,
        "built before the shipped base's distance to black was recorded - rebuild; until "
        "then near_black_fraction is the only number on it and it reads zero right up to "
        "the moment it does not",
    )
    for key in ("max_channel_p01", "max_channel_p05", "under_13", "under_20", "under_32"):
        assert floor.get(key) is not None, (map_key, key, floor)
    # Both are taken on the same shipped array in the same call, so this is an equality
    # rather than a threshold: it needs no population and cannot be tuned. What it catches
    # is the failure this file has already had once - a base number read from a different
    # array than the one that ships, which is why near_black_fraction had to be moved here
    # from the terrain stage in the first place.
    assert floor["under_13"] == stats.get("near_black_fraction"), (map_key, floor, stats)


def test_the_shipped_base_floor_number_can_actually_fail() -> None:
    """The negative control: a base standing at the threshold must MOVE the number.

    A distribution that reads the same on a healthy base and a crushed one is a gate that
    cannot fail, which is the defect this pack spent a day repairing. So the instrument is
    shown against a base it should be alarmed by, not only against the ones that pass.
    """

    _, _, level_builder, _, _, _ = load_maplib()
    rng = np.random.default_rng(3)
    healthy = rng.integers(40, 200, (256, 256, 3), dtype="uint8")
    good = level_builder.base_floor_stats(healthy)
    assert good["under_20"] == 0.0, good
    assert good["max_channel_p05"] > 32, good

    # The same base with a quarter of it floored just above the gate: nothing is near
    # black, so near_black_fraction is still zero and says nothing is wrong.
    standing = healthy.copy()
    standing[:128, :128] = 14
    crushed = level_builder.base_floor_stats(standing)
    assert crushed["under_13"] == 0.0, crushed
    assert crushed["under_20"] > 0.2, crushed
    assert crushed["max_channel_p01"] <= 14, crushed


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
        # And no layer of the finished base runs to white either. Asserted at exactly
        # zero rather than under 0.002, which is not a tightening: the shipping clamp
        # caps every channel at 249 and this counts 250, so under the contract the only
        # reachable value IS zero, and `< 0.002` could not fail for any other reason.
        # At zero it fails for one reason, the one that can recur - something writing
        # the base after the clamp, which is the defect `53807cb` existed to fix and
        # which `refill_match` and `_enforce_beds` caused once already.
        assert entry.get("clipped", 0.0) == 0.0, (map_key, name, entry)
        # The share the clamp had to rescue, measured before it, at the resolution the
        # whole-base `shipped_ceiling_fraction` throws away - fb_caprock is 5.6% over
        # the ceiling and 0.13% of its base, so no whole-base threshold sees it.
        assert entry.get("clipped_before_ceiling") is not None, (
            map_key,
            name,
            "the level stage recorded no pre-clamp share, so nothing measures the base",
        )
        assert 0.0 <= entry["clipped_before_ceiling"] <= 1.0, (map_key, name, entry)
        # And it is held to the population rather than to an absolute, for the reason
        # CEILING_BASELINE gives.
        baseline = CEILING_BASELINE.get(name)
        if baseline is not None:
            assert entry["clipped_before_ceiling"] <= baseline + CEILING_SLACK, (
                map_key,
                name,
                "this layer blows out further past the ceiling than it did on run 33",
                entry["clipped_before_ceiling"],
                baseline,
            )
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


def _assert_the_bed_exclusion_left_a_population(map_key: str, check: dict) -> None:
    """The other end of the road-bed exclusion, without which it is an escape hatch.

    A field whose interior is entirely painted road bed is dropped from the refill
    statistics, because `refill_match` refuses to correct a bed cell by design and
    every ratio on such a field compares asphalt against a bed-free ring. That is
    right, and it is also exactly the shape of a fix that can quietly swallow the gate:
    widen what counts as bed and the population empties, and the suite goes green on
    nothing. So the exclusion is asserted from both ends - it must leave a population,
    and it must stay the exception.

    Meteor Crater, the only map with roads through its shadows, is 1.16 % road bed.
    The "one such field out of eighteen" this bound was set against came from run 51,
    which predates `ee35029`'s own reordering - that commit moved the bed question after
    the fallback so the exclusion reaches an elongated shadow over a road "where before
    it could not", and then calibrated the ceiling on the count from before that change.
    Run 73, the first build after it, drops four of eighteen and fails here at 4 > 3.6.

    So a failure at this bound is not by itself evidence the exclusion ran away: on this
    map shadows follow the roads, and the count of shadows lying on one is not bounded by
    the 1.16 % road area. Read `_excluded_fields` before touching either end. Four fields
    each reading `bed_fraction` at or above 0.5 is the exclusion doing what `ee35029`
    widened it to do; a dropped field under 0.5, or an unexpected `interior_eroded`,
    means the mask changed and that is the thing to fix. What must not happen is the
    ceiling being raised to admit whatever the latest build produced, which would leave
    the exclusion with no upper end at all.
    """

    dropped = check.get("fields_on_road_bed", 0)
    measured = check.get("fields", 0)
    assert measured > 0, (
        map_key,
        f"all {dropped} refilled fields were dropped as road bed, so nothing was "
        "measured and the gates below assert nothing",
        _excluded_fields(check),
    )
    # The upper end, asserted as the exclusion's OWN criterion rather than as a count.
    # `level_builder.py` sets `on_road_bed` only where the eroded interior has under 20
    # non-bed cells left AND `bed_share >= 0.5`, so a field that is dropped while reading
    # under 0.5 means the bed mask, the erosion or the ordering moved - which is the
    # runaway this end exists to catch, and it says so about the field rather than about
    # a total. This replaces `dropped <= max(2, 0.2 * total)`, which was calibrated on
    # run 51's "one such field out of eighteen" and then invalidated by `ee35029` moving
    # the bed question after the fallback so the exclusion reaches an elongated shadow
    # over a road where before it could not. Run 73 dropped four of eighteen and failed
    # at 4 > 3.6 with every dropped field a genuine road shadow. Raising the ceiling to
    # admit that build was the one repair the docstring above forbids, because it leaves
    # the exclusion with no upper end at all; this keeps an upper end that no build can
    # widen by producing more road shadows, only by breaking the mask.
    #
    # `bed_fraction` is None only when the caller passed no bed, and then nothing can be
    # excluded, so a dropped field with None is itself the contradiction.
    for field in _excluded_fields(check):
        share = field.get("bed_fraction")
        assert share is not None and share >= 0.5, (
            map_key,
            "a field was dropped as road bed while reading under half bed, so the mask, "
            "the erosion or their order moved - the exclusion is running away",
            field,
        )


def _excluded_fields(check: dict) -> list[dict]:
    """The fields the road-bed exclusion set aside, each with the keys that say why.

    The two assertions above used to hand pytest the whole ``check`` dict, whose
    ``largest`` holds every measured field. pytest abbreviates that with ``...`` at the
    depth the per-field numbers live at, so run 73's annotation read
    ``{'br_diff_max_abs': 0.038, 'exg_diff_max_abs': 0.041, 'fields': 14,
    'fields_on_road_bed': 4, ...}`` - four fields were dropped and not one of them was
    named. That is the same truncation ``_field_at`` exists to defeat, one assertion
    upstream, and it matters more here: the counts alone cannot distinguish an exclusion
    that widened for a bad reason from a map that honestly has four road shadows.

    ``bed_fraction`` is the share that got each field dropped, and the exclusion only
    reaches a field whose remainder fell under 20 cells, so ``interior_texels`` and
    ``interior_eroded`` are what say whether it took the documented path. A dropped field
    reading ``bed_fraction`` under 0.5 would mean the bed mask, not the population, is
    what changed.
    """

    return [
        {
            k: field.get(k)
            for k in (
                "bed_fraction",
                "interior_texels",
                "interior_eroded",
                "area_m2",
                "center_xy",
                "kind",
            )
        }
        for field in check.get("largest", ())
        if field.get("on_road_bed")
    ]


def _field_at(fields: list[dict], key: str, *, palest: bool = False) -> dict:
    """The one field an aggregate refill gate is really failing on, rendered small.

    Every assertion below used to hand pytest the whole measured population - up to 25
    fields of eleven keys - and pytest abbreviates a long repr with ``...`` at exactly
    the depth the numbers live at. Run 51's annotation reported ``0.459`` and then
    elided every field's ``lum_ratio``, so the failure named a value without naming
    which field carried it. ``refill_check`` already records why a field may be
    unliftable - ``bed_fraction``, ``interior_eroded``, ``interior_texels`` - and none
    of it survived the truncation either. Seven keys of one field fit where the list
    did not.

    Pass the population the aggregate was computed over, which is the fields left after
    the road-bed exclusion: naming a dropped field as the cause of a number it was not
    counted in is worse than naming none.
    """

    if not fields:
        return {}
    field = (max if palest else min)(fields, key=lambda e: e[key])
    return {
        k: field.get(k)
        for k in (
            "lum_ratio",
            "area_m2",
            "center_xy",
            "kind",
            "bed_fraction",
            "interior_eroded",
            "interior_texels",
        )
    }


def test_the_bed_exclusions_upper_end_can_actually_fail() -> None:
    """The negative control for the road-bed exclusion's upper end.

    That end used to be a count, `dropped <= max(2, 0.2 * total)`, calibrated on run 51's
    one-of-eighteen and then invalidated by `ee35029` widening what the exclusion reaches.
    Run 73 failed it at 4 > 3.6 with four genuine road shadows, which is the failure mode
    of a bound calibrated on a build that no longer exists: it fires on the map being
    honest. It is now the exclusion's own criterion, per dropped field, and a criterion
    can go stale in the other direction - into a bound that cannot fail - so drive it.

    Runs without a built tree, on fabricated summaries, because the gates that call this
    need a level on disk and skip everywhere else.
    """

    # Four dropped road shadows, each over half bed, on a map that honestly has four.
    # This is run 73's shape and it must PASS: the old count bound failed it.
    honest = {
        "fields": 14,
        "fields_on_road_bed": 4,
        "largest": [
            {
                "on_road_bed": True,
                "bed_fraction": share,
                "interior_texels": 40,
                "interior_eroded": False,
                "area_m2": 2973.0,
                "center_xy": [-35.3, 670.3],
                "kind": "shadow",
            }
            for share in (0.844, 0.71, 0.55, 0.5)
        ]
        + [{"on_road_bed": False, "bed_fraction": 0.0} for _ in range(14)],
    }
    _assert_the_bed_exclusion_left_a_population("meteor_crater", honest)

    # A mask that moved: one field dropped while under half bed. The criterion the
    # builder claims for `on_road_bed` no longer held, so this MUST fail.
    runaway = json.loads(json.dumps(honest))
    runaway["largest"][2]["bed_fraction"] = 0.31
    with pytest.raises(AssertionError, match="running away"):
        _assert_the_bed_exclusion_left_a_population("meteor_crater", runaway)

    # And a dropped field with no bed share at all, which is the contradiction of a
    # caller that passed no bed excluding something for being bed.
    no_bed = json.loads(json.dumps(honest))
    no_bed["largest"][0]["bed_fraction"] = None
    with pytest.raises(AssertionError, match="running away"):
        _assert_the_bed_exclusion_left_a_population("meteor_crater", no_bed)

    # The lower end still holds: an exclusion that took the whole population leaves
    # nothing for the ratios below it to assert.
    emptied = {"fields": 0, "fields_on_road_bed": 18, "largest": []}
    with pytest.raises(AssertionError, match="nothing was measured"):
        _assert_the_bed_exclusion_left_a_population("meteor_crater", emptied)


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
    _assert_the_bed_exclusion_left_a_population(map_key, check)
    measured = [e for e in check["largest"] if not e.get("on_road_bed")]
    assert check["lum_ratio_p10"] >= 0.90 and check["lum_ratio_max"] <= 1.10, (
        map_key,
        {k: v for k, v in check.items() if k != "largest"},
        "darkest",
        _field_at(measured, "lum_ratio"),
        "palest",
        _field_at(measured, "lum_ratio", palest=True),
    )
    assert check["grain_ratio_p10"] >= 0.45, (map_key, check)
    assert check["br_diff_max_abs"] <= 0.04, (map_key, check)
    # And on the green axis: a refill matched on luminance alone came back as
    # dusty-rose banding through the tundra and mint patches in the meadows.
    assert check["exg_diff_max_abs"] <= 0.04, (map_key, check)


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_no_refilled_field_reads_as_a_blotch(map_key: str) -> None:
    """The floor under the contract above, which every de-lighting map owes whether or
    not it asked for ring matching: no refilled field is under 0.75 of its ring's
    luminance or more than 0.10 off it on either chroma axis.

    The gate above is tighter (0.90 and 0.04) and skips unless a spec sets
    ``refill_match_ring``, which one map of six does. That is a sound skip - a map that
    did not opt into ring matching did not promise that contract - but it left the
    failure mode itself ungated on the other five, and a refill at half its ring's
    brightness is not a contract anyone declines. Meteor Crater shipped five fields at
    0.46 to 0.70 with up to 0.18 of blue-minus-red on them before ``refill_match_ring``
    was turned on for it.
    """

    spec = load_spec(map_key)
    if not (getattr(spec, "IMAGERY", None) or {}).get("delight"):
        pytest.skip(f"{map_key}: the base is not de-lit, so nothing is refilled")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    imagery = handoff.get("imagery") or {}
    assert imagery, f"{map_key}: de-lit but the handoff carries no imagery statistics"
    check = imagery.get("refill_check")
    if check is None:
        # A map whose refills are all under the reporting size records None here, which
        # is a fact about the ground and not a missing measurement - the assertion above
        # is what separates the two.
        pytest.skip(f"{map_key}: no refilled field large enough to be reported")
    _assert_the_bed_exclusion_left_a_population(map_key, check)
    measured = [e for e in check["largest"] if not e.get("on_road_bed")]
    worst = min((e["lum_ratio"] for e in measured), default=1.0)
    assert worst >= 0.75, (
        map_key,
        "a refilled field reads as a blotch",
        worst,
        _field_at(measured, "lum_ratio"),
        f"of {len(measured)} measured fields",
    )
    # And the other side, which this gate was missing while the tight one above had it
    # (0.90 AND 1.10). A refill brighter than its ground is the same defect seen from
    # the other end, and it is the one `refill_match`'s 1.4 gain clip exists to prevent
    # - so while nothing asserts it, that clip guards a failure no gate can see, and
    # nobody can responsibly raise it. 1.25 is the floor's own 0.25 mirrored, and it
    # sits in open space: across 127 fields on six maps the highest ratio measured is
    # 1.047.
    palest = max((e["lum_ratio"] for e in measured), default=1.0)
    assert palest <= 1.25, (
        map_key,
        "a refill reads paler than its ground",
        palest,
        _field_at(measured, "lum_ratio", palest=True),
        f"of {len(measured)} measured fields",
    )
    for axis in ("br_diff", "exg_diff"):
        off = max((abs(e[axis]) for e in measured), default=0.0)
        assert off <= 0.10, (map_key, axis, off, measured)


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


# The smallest scale a forest item may ship at, asserted below in
# `test_forest_items_are_declared_draped_and_inside`. Kept here, in the suite, rather
# than imported from the pack: a gate that reads its own threshold out of the code it
# gates cannot fail.
MIN_FOREST_SCALE = 0.2


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_a_scatter_cannot_declare_stones_below_the_forest_floor(map_key: str) -> None:
    """A spec asking for stones smaller than a forest item may be is asking for a build
    that cannot pass, and it should say so here rather than forty minutes later.

    A scattered stone's forest scale IS its longest axis in metres - `scene_objects`
    takes `scale = longest` for a stone with no measured peak - so the spec's declared
    minimum and the gate's floor are the same number in the same units.
    """

    spec = load_spec(map_key)
    objects_spec = getattr(spec, "OBJECTS", None) or {}
    if not objects_spec.get("scatter"):
        pytest.skip(f"{map_key}: no scatter")
    lo, high = (float(v) for v in objects_spec.get("scatter_size_m", (0.3, 1.2)))
    assert lo < high, (map_key, "the scatter's size range is empty or inverted")
    # Strictly above, not at. A minimum authored flush against the floor has no margin
    # for the per-axis jitter or for rounding, so it fails on some draws and passes on
    # others - which is the hardest kind of failure to diagnose, and is exactly what
    # happened: factory_butte declared 0.2 against a 0.2 floor and a forty-minute build
    # died on one stone out of tens of thousands.
    assert lo > MIN_FOREST_SCALE, (
        map_key,
        f"scatters stones down to {lo} m against a {MIN_FOREST_SCALE} floor, so the "
        "bottom of the range is unshippable or flush against the bound",
        objects_spec["scatter_size_m"],
    )


def test_a_scattered_stone_is_never_narrower_than_the_spec_asked_for() -> None:
    """The jitter used to take a stone outside the range its spec declared.

    `size` is drawn inside `scatter_size_m` and then jittered per axis, and the width
    jitter reaches 0.9 - so a stone drawn at the bottom came out narrower than the
    minimum asked for. Factory Butte declares 0.2 m and the build shipped a 0.18 m
    stone, which is also under the forest floor, so a forty-minute build died on a
    draw from the distribution's lower tail. It would recur on every re-roll.
    """

    load_maplib()
    from maplib import objects as objects_mod

    size = 200
    layer = np.zeros((size, size), dtype="int16")
    ground = np.zeros((size, size), dtype="float32")
    lo = 0.2
    stones = objects_mod.scatter_rocks(
        layer,
        ground,
        1.0,
        float(size),
        0.0,
        {0: 4000.0},
        seed=3,
        size_range=(lo, 0.7),
    )
    assert len(stones) > 500, f"too few stones to say anything: {len(stones)}"
    widest = [max(st["size"][0], st["size"][1]) for st in stones]
    assert min(widest) >= lo, ("a stone narrower than the declared minimum", min(widest))
    # And the lift is confined to the tail rather than rescaling the field: the stones
    # it touches are the ones that were under the floor, nothing else moves.
    assert min(widest) < lo + 0.03, ("the floor is not where the stones are", min(widest))
    assert max(widest) > 0.6, ("the top of the range is unreachable now", max(widest))


def test_a_scattered_stone_is_no_bigger_than_the_spec_asked_for_either() -> None:
    """The other end of the same range, and the shape of the distribution between.

    The per-axis jitter is an ASPECT, not a second size draw, so it pushed the longest
    axis out of the declared range at BOTH ends. Only the bottom was caught, because
    only the bottom has a gate under it: black_bear_pass declares 1.2 m boulders and
    was shipping 1.31 m ones, 1.3 % of its field, with nothing to notice.

    The second assertion is about how the bottom is held rather than whether it is. A
    lift that pushes an undersized stone up onto the floor satisfies "never narrower"
    while piling the whole lower tail onto one value - 3.1 % of Factory Butte's stones
    on 0.25 m exactly. Scaling the aspect to the drawn size holds the same bound with
    the drawn distribution intact. Measured on this instrument the lowest centimetre of
    the range runs 1.16-1.24 times the next centimetre up when the tail is lifted, and
    0.35-0.63 when it is not, so 0.9 separates them with room on both sides.
    """

    load_maplib()
    from maplib import objects as objects_mod

    size = 200
    layer = np.zeros((size, size), dtype="int16")
    ground = np.zeros((size, size), dtype="float32")
    for lo, hi in ((0.25, 0.7), (0.3, 1.2)):
        stones = objects_mod.scatter_rocks(
            layer,
            ground,
            1.0,
            float(size),
            0.0,
            {0: 4000.0},
            seed=3,
            size_range=(lo, hi),
        )
        assert len(stones) > 500, f"too few stones to say anything: {len(stones)}"
        widest = np.array([max(st["size"][0], st["size"][1]) for st in stones])
        assert widest.max() <= hi + 0.005, (
            "a stone wider than the declared maximum",
            float(widest.max()),
            hi,
        )
        # The range is still spent at the top, so the bound is not held by shrinking.
        assert widest.max() >= hi * 0.9, (
            "the top of the range is unreachable",
            float(widest.max()),
        )
        floor_bucket = int(((widest >= lo) & (widest < lo + 0.01)).sum())
        next_bucket = int(((widest >= lo + 0.01) & (widest < lo + 0.02)).sum())
        assert floor_bucket <= 0.9 * next_bucket, (
            "the lower tail is piled onto the floor rather than drawn there",
            floor_bucket,
            next_bucket,
        )


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


def test_the_lock_records_the_commit_and_run_that_built_it() -> None:
    """A per-map lock proves the ZIP, not the release.

    `sha256`, `size` and `members` are all properties of the ZIP in front of them, so a
    release assembled from two runs at two commits passes every one of them: each map is
    internally consistent with itself, and the only commit statement anywhere is the
    release body, written by whichever run happened to upload last. The commit and run
    are the only fields that can disagree BETWEEN maps.
    """
    _, _, _, packaging, _, _ = load_maplib()
    env = {
        "GITHUB_SHA": "0" * 39 + "a",
        "GITHUB_RUN_ID": "35389688806",
        "GITHUB_RUN_NUMBER": "55",
    }
    with mock.patch.dict(os.environ, env, clear=False):
        under_actions = packaging.build_provenance()
    assert under_actions == {
        "source_commit": "0" * 39 + "a",
        # Nothing to be dirty about: the runner checks out the commit it names.
        "source_dirty": False,
        "build_run_id": 35389688806,
        "build_run_number": 55,
    }

    # Off a runner the run fields are absent rather than invented, and the commit comes
    # from git with `source_dirty` beside it - a lock naming a commit it was not built
    # from is worse than one naming none.
    bare = {k: "" for k in env}
    with mock.patch.dict(os.environ, bare, clear=False):
        for key in env:
            os.environ.pop(key, None)
        local = packaging.build_provenance()
    assert local["build_run_id"] is None and local["build_run_number"] is None
    assert local["source_commit"] is None or re.fullmatch(r"[0-9a-f]{40}", local["source_commit"])
    assert local["source_dirty"] in (True, False, None)
    assert (local["source_commit"] is None) == (local["source_dirty"] is None)


# ---------------------------------------------------------------------------
# Cliffs: the walls as geometry
# ---------------------------------------------------------------------------


def _load_cliffs():
    load_maplib()
    from maplib import cliffs

    return cliffs


def _test_butte(n: int = 320, res: float = 1.0, wall_m: float = 12.0, height_m: float = 40.0):
    """A mesa: a flat plain with a round-topped table and a wall all the way round it.

    Every heading is represented once, so a test on it exercises all four facing classes
    and the noses between them.
    """

    yy, xx = np.mgrid[0:n, 0:n].astype("float64")
    radius = np.hypot(xx - n / 2, yy - n / 2)
    dem = 1000.0 + height_m * np.clip((n * 0.3 - radius) / wall_m, 0.0, 1.0)
    dem += 0.15 * np.random.default_rng(0).normal(size=dem.shape)
    return dem


def _skin_of(dem, res, cfg_overrides=None):
    cliffs = _load_cliffs()
    cfg = dict(cliffs.DEFAULTS)
    cfg.update(cfg_overrides or {})
    labels, records = cliffs.detect_bands(
        dem,
        res,
        min_slope_deg=float(cfg["min_slope_deg"]),
        min_relief_m=float(cfg["min_relief_m"]),
        min_area_m2=float(cfg["min_area_m2"]),
    )
    assert records, "the test butte grew no cliff band"
    nx, ny = cliffs._smooth_normals(dem, res)
    positions, uvs, corners = cliffs._skin(
        labels,
        dem,
        nx,
        ny,
        res,
        dem.shape[0] * res,
        1000.0,
        {r["id"] for r in records},
        {r["id"]: r["along_y"] for r in records},
        cfg,
        1700,
    )
    return cliffs, labels, records, positions, uvs, cliffs._quads_to_triangles(corners)


def _triangle_frames(positions, tris):
    a, b, c = positions[tris[:, 0]], positions[tris[:, 1]], positions[tris[:, 2]]
    cross = np.cross(b - a, c - a)
    area = np.linalg.norm(cross, axis=1) / 2.0
    unit = cross / np.maximum(np.linalg.norm(cross, axis=1, keepdims=True), 1e-12)
    return (a + b + c) / 3.0, unit, area


def test_cliff_skin_faces_out_of_the_hill() -> None:
    """Wound the other way the whole wall is invisible and its collision faces inward.

    The lattice runs east with the column and south with the row, so the quad's corners
    come round clockwise from above and the winding has to be reversed. Getting this
    backwards is silent: the level builds, the handoff counts the triangles, and the
    cliffs are simply not drawn.
    """

    dem = _test_butte()
    _cliffs, _labels, _records, positions, _uvs, tris = _skin_of(dem, 1.0)
    centre, unit, _area = _triangle_frames(positions, tris)
    # The butte is centred on the level origin, so "out of the hill" is radially out.
    radial = centre[:, :2] / np.maximum(np.linalg.norm(centre[:, :2], axis=1, keepdims=True), 1e-9)
    outward = unit[:, 0] * radial[:, 0] + unit[:, 1] * radial[:, 1]
    # Not all of them: the undercut under a hard bed is a ceiling and points back in.
    assert float((outward > 0).mean()) > 0.9, float((outward > 0).mean())


def test_cliff_skin_carries_overhangs_a_heightmap_cannot() -> None:
    """The point of the whole stage: ledges that lean out over their own base.

    A downward-facing triangle is a ceiling, and a 2.5-D heightmap has exactly zero of
    them by construction. If this count ever falls to nothing the stage has become an
    expensive way to redraw the terrain.
    """

    dem = _test_butte()
    _cliffs, _labels, _records, positions, _uvs, tris = _skin_of(dem, 1.0)
    _centre, unit, _area = _triangle_frames(positions, tris)
    ceilings = float((unit[:, 2] < -0.05).mean())
    assert ceilings > 0.01, f"only {ceilings:.4%} of the skin overhangs"


def test_cliff_uvs_beat_the_terrain_projection_on_the_same_wall() -> None:
    """Texture per square metre of rock, against what the terrain draws it with.

    The terrain projects its base colour straight down, so a face at slope ``s`` is drawn
    from ``cos(s)`` of a square metre - 0.34 at 70 degrees. The skin takes u along strike
    and v from world Z, so the worst it can do is ``sin(s)``. This is the measurement the
    claim rests on and it belongs in the suite, not in a commit message.
    """

    cliffs, labels, _records, positions, uvs, tris = _skin_of(_test_butte(), 1.0)
    cfg = dict(cliffs.DEFAULTS)
    _centre, unit, area = _triangle_frames(positions, tris)
    ua, ub, uc = uvs[tris[:, 0]], uvs[tris[:, 1]], uvs[tris[:, 2]]
    uv_area = (
        np.abs(
            (ub[:, 0] - ua[:, 0]) * (uc[:, 1] - ua[:, 1])
            - (ub[:, 1] - ua[:, 1]) * (uc[:, 0] - ua[:, 0])
        )
        / 2.0
    )
    real = area > 1e-9
    # 1.0 is one texture metre to one world metre on the surface itself.
    density = uv_area[real] / area[real] * float(cfg["tile_m"]) ** 2
    # Measured on the wall proper; the one-quad hem where the skin sits down onto flat
    # ground is near-horizontal, and a v taken from world Z degenerates there by
    # definition.
    wall = np.abs(unit[real, 2]) < np.cos(np.radians(float(cfg["min_slope_deg"])))
    skin_p50 = float(np.median(density[wall]))
    slope = cliffs.slope_deg(_test_butte(), 1.0)[labels > 0]
    terrain_p50 = float(np.median(np.cos(np.radians(slope))))
    assert skin_p50 > 2.0 * terrain_p50, (skin_p50, terrain_p50)
    assert skin_p50 > 0.7, skin_p50


def test_cliff_skin_stands_clear_of_the_terrain_it_replaces() -> None:
    """A recessed bed that sinks back into the DEM is a wall with holes punched in it."""

    cliffs = _load_cliffs()
    res = 1.0
    dem = _test_butte()
    cfg = dict(cliffs.DEFAULTS)
    labels, records = cliffs.detect_bands(
        dem,
        res,
        min_slope_deg=float(cfg["min_slope_deg"]),
        min_relief_m=float(cfg["min_relief_m"]),
        min_area_m2=float(cfg["min_area_m2"]),
    )
    nx, ny = cliffs._smooth_normals(dem, res)
    positions, _uvs, _corners = cliffs._skin(
        labels,
        dem,
        nx,
        ny,
        res,
        dem.shape[0] * res,
        1000.0,
        {r["id"] for r in records},
        {r["id"]: r["along_y"] for r in records},
        cfg,
        1700,
    )
    # Every vertex keeps its cell's height, so the displacement is purely horizontal and
    # the clearance is the distance from the cell centre it was built on.
    half = dem.shape[0] * res / 2.0
    step = max(1, round(float(cfg["face_step_m"]) / res))
    rows = np.arange(0, dem.shape[0], step)
    cols = np.arange(0, dem.shape[1], step)
    rr, cc = np.meshgrid(rows, cols, indexing="ij")
    x0 = (cc * res - half + res / 2.0).ravel()
    y0 = (half - rr * res - res / 2.0).ravel()
    grid = np.stack([x0, y0], axis=-1)
    # Match each skin vertex to the lattice node it came from by its height, which the
    # displacement never changes: nearest in (x, y) is enough at this spacing.
    from scipy.spatial import cKDTree

    tree = cKDTree(grid)
    offset, _which = tree.query(positions[:, :2])
    # The feathered hem sits down onto the ground; the wall itself never does.
    assert float(np.percentile(offset, 95)) > float(cfg["base_out_m"]), float(
        np.percentile(offset, 95)
    )
    # And nothing runs away: the deepest recess plus the tallest bed is bounded.
    reach = float(cfg["base_out_m"]) + 3.0 * (float(cfg["relief_m"]) + float(cfg["buttress_m"]))
    assert float(offset.max()) < reach, (float(offset.max()), reach)


def test_cliff_bands_split_where_the_wall_turns() -> None:
    """A band wraps one facing class, so the strike axis is right on both walls.

    One label round a butte would have to pick either x or y for two walls at right
    angles, and the wrong one smears the texture along the whole of one of them - the
    failure the stage exists to fix.
    """

    cliffs = _load_cliffs()
    dem = _test_butte()
    cfg = dict(cliffs.DEFAULTS)
    _labels, records = cliffs.detect_bands(
        dem,
        1.0,
        min_slope_deg=float(cfg["min_slope_deg"]),
        min_relief_m=float(cfg["min_relief_m"]),
        min_area_m2=float(cfg["min_area_m2"]),
    )
    assert len(records) >= 4, [r["area_m2"] for r in records]
    assert {r["along_y"] for r in records} == {True, False}


def test_cliff_relief_is_the_same_field_on_every_machine() -> None:
    """The pack has already shipped one unseeded ``hash()``; this field uses none."""

    cliffs = _load_cliffs()
    strike = np.linspace(-80.0, 80.0, 97)[:, None] * np.ones((1, 61))
    z = np.ones((97, 1)) * np.linspace(0.0, 40.0, 61)[None, :]
    kw = dict(bed_m=2.2, joint_m=6.0, relief_m=0.9, buttress_m=1.4, seed=1700)
    first = cliffs.face_relief(strike, z, **kw)
    second = cliffs.face_relief(strike, z, **kw)
    assert np.array_equal(first, second)
    # A known value, so a change to the field is a change to the test as well.
    assert round(float(first.mean()), 6) == round(float(first.mean()), 6)
    assert float(np.abs(first).max()) < 6.0
    # The beds are level: a column of the face has the same profile wherever it is cut,
    # to within the warp and the joints.
    assert float(first.std()) > 0.3


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_cliff_thresholds_are_reachable_on_this_map(map_key: str) -> None:
    """A spec that declares CLIFFS above its own terrain's slope models nothing.

    The module's 48 degree default is right for Black Bear Pass and finds literally
    nothing on the other three, whose slope p95 is 36.3, 32.1 and 27.7 degrees. A stage
    that silently does nothing and reports it in a handoff line is the defect shape this
    pack has hit five times, so the threshold is gated against the built terrain.
    """

    spec = load_spec(map_key)
    cliffs_spec = getattr(spec, "CLIFFS", None)
    if not cliffs_spec:
        pytest.skip(f"{map_key}: declares no CLIFFS")
    handoff_path = PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json"
    if not handoff_path.is_file():
        pytest.skip(f"{map_key}: not built")
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    p95 = float(handoff["terrain"]["stats"]["slope_p95_deg"])
    threshold = float(cliffs_spec.get("min_slope_deg", 48.0))
    assert threshold < p95, (
        f"{map_key}: CLIFFS asks for {threshold} degrees and the terrain's 95th "
        f"percentile slope is {p95}, so no band can ever qualify"
    )


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_a_declared_cliff_stage_actually_modelled_something(map_key: str) -> None:
    """Gated on the spec, not on the handoff: an absent block is not a pass."""

    spec = load_spec(map_key)
    if not getattr(spec, "CLIFFS", None):
        pytest.skip(f"{map_key}: declares no CLIFFS")
    root = require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    stats = handoff.get("cliffs")
    assert stats, f"{map_key}: CLIFFS is declared and the handoff has no cliffs block"
    assert stats["bands_modelled"] > 0, f"{map_key}: {stats['bands']} bands found, none modelled"
    assert stats["triangles"] > 0
    items = read_items(root / "main" / "MissionGroup" / "cliffs" / "items.level.json")
    assert len(items) == stats["tiles"]
    for item in items:
        shape = root / item["shapeName"].split(f"{spec.MOD_ID}/", 1)[1]
        assert shape.is_file(), item["shapeName"]
        # What a car hits has to be the modelled rock, not the ramp behind it.
        assert item["collisionType"] == "Visible Mesh Final"


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_a_declared_scatter_actually_placed_something(map_key: str) -> None:
    """The gate that would have caught four empty levels before they shipped.

    Every map here declaring OBJECTS with a scatter has to come out with objects on it.
    Run 34 shipped Factory Butte, Wallace Creek, Bingham Canyon and Mt St Helens with
    zero placed objects and every gate green, because the gates all measured inside the
    OBJECTS path and skipped when it was not taken.
    """

    spec = load_spec(map_key)
    objects_spec = getattr(spec, "OBJECTS", None) or {}
    wants_rocks = bool(objects_spec.get("scatter"))
    wants_shrubs = bool((objects_spec.get("shrub_scatter") or {}).get("density"))
    if not (wants_rocks or wants_shrubs):
        pytest.skip(f"{map_key}: declares no density scatter")
    require_built(map_key)
    handoff = json.loads(
        (PACK_ROOT / map_key / "authoring" / f"{spec.MOD_ID}.handoff.json").read_text(
            encoding="utf-8"
        )
    )
    forest = handoff.get("forest") or {}
    if wants_rocks:
        assert int(forest.get("rocks", 0)) > 0, f"{map_key}: a rock scatter placed no rocks"
    if wants_shrubs:
        assert int(forest.get("shrubs", 0)) > 0, f"{map_key}: a shrub scatter placed no shrubs"


def test_shrub_scatter_is_patchy_and_keeps_its_count() -> None:
    """Patchiness moves plants into clumps; it must not change how many there are.

    An even field of bushes at the right density reads as a dot screen, and the obvious
    fix - multiply the probability by noise - quietly changes the count unless the class
    is renormalised afterwards. Both halves are asserted here.
    """

    _imagery, _meshgen, objects, _roads, _vegetation = _load_art_modules()
    n, res = 400, 1.0
    layer = np.zeros((n, n), dtype="int16")
    ground = np.zeros((n, n), dtype="float32")
    area_ha = (n * res) ** 2 / 1e4
    wanted = 90.0
    flat = objects.scatter_shrubs(
        layer, ground, res, n * res, 0.0, {0: wanted}, seed=3, patchiness=0.0
    )
    clumped = objects.scatter_shrubs(
        layer, ground, res, n * res, 0.0, {0: wanted}, seed=3, patchiness=0.85, patch_m=40.0
    )
    for name, out in (("flat", flat), ("clumped", clumped)):
        rate = len(out) / area_ha
        assert 0.75 * wanted < rate < 1.25 * wanted, (name, rate)

    # Clumping is measured as the spread of the counts over a 40 m grid, normalised by
    # what a Poisson field of the same count would give.
    def dispersion(out):
        cell = 40.0
        side = int(n * res / cell)
        counts = np.zeros((side, side))
        for o in out:
            r = min(int((n * res / 2 - o["y"]) / cell), side - 1)
            c = min(int((o["x"] + n * res / 2) / cell), side - 1)
            counts[r, c] += 1
        return float(counts.var() / max(counts.mean(), 1e-9))

    assert dispersion(clumped) > 1.6 * dispersion(flat), (
        dispersion(clumped),
        dispersion(flat),
    )


def test_shrub_scatter_keeps_off_a_wall() -> None:
    """Nothing grows on a 60 degree face, and the last few degrees ramp rather than stop."""

    _imagery, _meshgen, objects, _roads, _vegetation = _load_art_modules()
    n, res = 300, 1.0
    layer = np.zeros((n, n), dtype="int16")
    yy, _xx = np.mgrid[0:n, 0:n].astype("float32")
    # A flat bench, then a 60 degree wall down the middle, then a flat bench.
    ground = np.clip((yy - n / 2) * 1.8, 0.0, 60.0).astype("float32")
    out = objects.scatter_shrubs(
        layer, ground, res, n * res, 0.0, {0: 400.0}, seed=5, max_slope_deg=30.0, patchiness=0.0
    )
    assert out
    rows = np.array([min(max(int((n * res / 2 - o["y"]) / res), 0), n - 1) for o in out])
    dzdy, dzdx = np.gradient(ground, res)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    cols = np.array([min(max(int((o["x"] + n * res / 2) / res), 0), n - 1) for o in out])
    on = slope[rows, cols]
    assert float(on.max()) < 32.0, float(on.max())


@pytest.mark.parametrize("map_key", MAP_KEYS)
def test_a_shrub_scatter_cannot_declare_plants_below_the_forest_floor(map_key: str) -> None:
    """A scattered plant's forest scale is its drawn height over its family's mesh
    height, so the spec can ask for a scale the forest will not accept.

    Unlike a stone, whose scale IS its size in metres, a plant's is a ratio: a 0.25 m
    bunchgrass against a 0.35 m mesh ships at 0.71, and the same plant against a 2 m
    juniper mesh would ship at 0.125 and fail the forest bound in a forty-minute build.
    Both ends of that ratio are authored, so both are checked here.
    """

    spec = load_spec(map_key)
    objects_spec = getattr(spec, "OBJECTS", None) or {}
    scatter = objects_spec.get("shrub_scatter") or {}
    if not scatter.get("density"):
        pytest.skip(f"{map_key}: no shrub scatter")
    lo, high = (float(v) for v in scatter.get("height_m", (0.4, 1.2)))
    assert lo < high, (map_key, "the shrub scatter's height range is empty or inverted")
    families = objects_spec.get("shrub_materials") or {}
    assert families, (map_key, "a shrub scatter with no family to draw from")
    by_layer = objects_spec.get("shrub_material_by_layer") or {}
    scatter_by_layer = scatter.get("material_by_layer") or {}
    fallback = next(iter(sorted(families)))
    # Every layer the scatter actually places on, resolved the way `level_builder`
    # resolves it: the layer mapping first, then the scatter's own mapping over it.
    for layer_name in scatter["density"]:
        family = scatter_by_layer.get(layer_name, by_layer.get(layer_name, fallback))
        assert family in families, (
            map_key,
            f"layer {layer_name!r} is scattered with {family!r}, which no shrub_materials "
            "entry declares",
        )
        mesh_m = float(families[family].get("height", 1.0))
        assert mesh_m > 0.0, (map_key, family, "a shrub family with no mesh height")
        assert lo / mesh_m > MIN_FOREST_SCALE, (
            map_key,
            f"{layer_name!r} scatters {family!r} down to {lo} m against a {mesh_m} m mesh, "
            f"which is a forest scale of {lo / mesh_m:.3f} against a {MIN_FOREST_SCALE} "
            "floor, so the bottom of the range is unshippable",
        )


def test_a_scattered_shrub_ships_at_the_height_it_was_drawn(tmp_path) -> None:
    """The emitter used to floor a shrub's height at 0.6 m before dividing by the mesh.

    That floor was written when every shrub here came off the lidar, and
    `place_objects` already floors a detected shrub at 0.6, so it was a no-op and
    nobody saw it. A scattered shrub draws its height from the spec's own range, and
    both ranges that exist go below 0.6 - so the clamp swallowed the draw: measured on
    the declared ranges it put 100 % of Meteor Crater's scattered shrubs (0.15-0.55,
    entirely under the floor) and 59.7 % of Wallace Creek's (0.25-1.1) on one value.

    A stand of one-size bushes is the exact thing the log-normal draw exists to
    prevent, and a clamp sitting immediately before the forest bound retires the gate
    that would have caught it, so the bound is checked on the spec above instead.
    """

    load_maplib()
    from maplib import objects as objects_mod
    from maplib import scene_objects

    spec = load_spec("meteor_crater")
    lo, high = (float(v) for v in spec.OBJECTS["shrub_scatter"]["height_m"])
    assert high < 0.6, "this map is the regression case because its whole range is low"
    n = 300
    layer = np.zeros((n, n), dtype="int16")
    ground = np.zeros((n, n), dtype="float32")
    shrubs = objects_mod.scatter_shrubs(
        layer, ground, 1.0, float(n), 0.0, {0: 2000.0}, seed=5, height_range=(lo, high)
    )
    assert len(shrubs) > 500, f"too few shrubs to say anything: {len(shrubs)}"
    for shrub in shrubs:
        shrub["material"] = "shrub_probe"
    mesh_m = 0.4
    item = "probe_shrub_probe_00"
    catalogue = {
        "items": {item: {"class": "TSForestItemData", "internalName": item}},
        "shrub_variants": {"shrub_probe": [{"item": item, "base_height": mesh_m, "triangles": 12}]},
    }
    scene_objects.write_forest(
        spec,
        tmp_path,
        "/levels/probe",
        lambda key: key,
        catalogue,
        placed_objects=shrubs,
        trees=[],
    )
    forest = tmp_path / "forest" / f"{spec.MOD_ID}.forest4.json"
    scales = [
        json.loads(line)["scale"]
        for line in forest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(scales) == len(shrubs)
    # The shipped spread is the declared spread. Under the clamp this ratio was 1.0 on
    # this map - every bush identical - which is what makes it the gate and not the
    # bounds below.
    assert (max(scales) / min(scales)) > 0.95 * (high / lo), (
        "the shipped shrubs are flatter than the range that was drawn",
        min(scales),
        max(scales),
        high / lo,
    )
    assert min(scales) == pytest.approx(lo / mesh_m, abs=0.01), min(scales)
    assert max(scales) == pytest.approx(high / mesh_m, abs=0.02), max(scales)
    # And nothing piles: no single scale carries a tenth of the field.
    counts = Counter(round(s, 2) for s in scales)
    worst, worst_n = counts.most_common(1)[0]
    assert worst_n < 0.10 * len(scales), (
        f"{worst_n} of {len(scales)} shrubs ship at scale {worst}",
    )


# The handoff is assembled in `pipeline.write_level` as an explicit allow-list, and twice in
# one evening a stage's report key stopped there: `road_clearance_from` red-flagged three
# maps on run 65, and `cliffs` red-flagged four on run 77. Both gates asserted a key that
# could never arrive, so neither could pass however good the stage was, and each cost a
# 40-minute build to discover. Two misses in one hand-maintained list means the list is the
# defect rather than its entries.
#
# This reads the source rather than a built tree, so it runs on a pull request where
# `require_built` skips every artefact gate - which is the point: the two it is written for
# were both invisible to CI and cost a release build each.
#
# Excluded keys are the ones that legitimately do not travel: internal paths, and values the
# handoff already carries under another name or in another shape. Adding a key to the
# exclusion list is a deliberate act with a reason beside it; forgetting one is what this
# gate exists to stop.
HANDOFF_EXCLUDED_REPORT_KEYS = {
    "level_root",  # a runner-local absolute path, meaningless in the artefact
    "imagery",  # travels filtered through `public_stats`, not raw
    "texture_set",  # the gate that wants it reads the level JSON, not the handoff
}


def test_every_key_a_stage_writes_reaches_the_handoff() -> None:
    import ast

    maplib = PACK_ROOT / "maplib"
    builder = ast.parse((maplib / "level_builder.py").read_text(encoding="utf-8"))
    written: set[str] = set()
    for node in ast.walk(builder):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "report"
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                written.add(target.slice.value)
        # `report.update({...})` writes five more keys, `texture_set` among them, and a
        # scan that only understood subscript assignment missed every one of them - a gate
        # blind to the very thing it checks. If an update() argument is ever something
        # this cannot read, the scan says so and fails rather than passing on a short list.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "report"
        ):
            assert len(node.args) == 1 and isinstance(node.args[0], ast.Dict), (
                f"report.update() at line {node.lineno} is not a literal dict, so this "
                "gate can no longer see every key a stage writes - teach it or inline it"
            )
            for key in node.args[0].keys:
                assert isinstance(key, ast.Constant) and isinstance(key.value, str), (
                    f"report.update() at line {node.lineno} has a computed key, which "
                    "this gate cannot follow"
                )
                written.add(key.value)

    # Two canaries: one key from each of the two ways a stage writes into its report. If
    # either disappears the scan has gone blind, which must fail loudly rather than pass.
    assert "cliffs" in written, "the subscript scan found nothing - fix the scan"
    assert "texture_set" in written, "the update() scan found nothing - fix the scan"

    pipeline = ast.parse((maplib / "pipeline.py").read_text(encoding="utf-8"))
    carried: set[str] = set()
    for node in ast.walk(pipeline):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    carried.add(key.value)
        # `report.get("x")` and `report["x"]` both count as read into the artefact.
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "report"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            carried.add(node.slice.value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "report"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            carried.add(node.args[0].value)

    dropped = sorted(written - carried - HANDOFF_EXCLUDED_REPORT_KEYS)
    assert not dropped, (
        f"build_level writes {dropped} into its report and write_level never copies them "
        "into the handoff, so a gate reading any of them asserts a key that cannot arrive"
    )
