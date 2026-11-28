"""Static gates for the Giant's Hearth forest (build round B3, design v4 §4).

Everything here is measured on the SHIPPED tree
(``examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena/``), never on the
generators' return values, so a stale or hand-edited file fails the gate.  The quality-bar
thresholds are the design's own §13 lines; where the design states a number
(``top LOD p50 1,300``, ``154,686 instances``, ``1.41 M cover elements``) the test asserts
that number, not a range.

The suite SKIPS wholesale when the forest has not been built yet -- the three authoring
manifests are the witness -- so a checkout that only ran B0/B1 still collects.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from examples.hot_potato_arena.level import blender_forest as bf
from examples.hot_potato_arena.level import forest_build, mesh_audit
from examples.hot_potato_arena.level import forest_spec as fs
from examples.hot_potato_arena.level import plant_forest as pf

LEVEL_ROOT = (
    Path(__file__).resolve().parents[1] / "examples/hot_potato_arena/mod/levels" / fs.LEVEL_ID
)
AUTHORING = Path(__file__).resolve().parents[1] / "examples/hot_potato_arena/authoring"
PROVENANCE = AUTHORING / "cc0_provenance.json"

pytestmark = pytest.mark.skipif(
    not forest_build.available(), reason="B3 forest not built (no authoring manifests)"
)


def percentile(values: list[float], fraction: float) -> float:
    """numpy's linear percentile -- the one ``study/census.py`` reports its p50s with."""
    ordered = sorted(values)
    k = (len(ordered) - 1) * fraction
    low, high = math.floor(k), math.ceil(k)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (k - low))


@pytest.fixture(scope="module")
def shapes() -> dict:
    return forest_build.shapes_manifest()


@pytest.fixture(scope="module")
def textures() -> dict:
    return forest_build.textures_manifest()


@pytest.fixture(scope="module")
def plant() -> dict:
    return forest_build.plant_manifest()


@pytest.fixture(scope="module")
def datablocks() -> dict:
    return json.loads((LEVEL_ROOT / "art/forest/managedItemData.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def materials() -> dict:
    out: dict[str, dict] = {}
    for family, directory in {
        "trees": fs.TREES_DIR,
        "deadwood": fs.DEADWOOD_DIR,
        "undergrowth": fs.CARDS_DIR,
        "rocks": fs.ROCKS_DIR,
        "groundcover": fs.COVER_DIR,
    }.items():
        path = LEVEL_ROOT / directory / f"{fs.LEVEL_ID}_{family}.materials.json"
        out.update(json.loads(path.read_text("utf-8")))
    return out


@pytest.fixture(scope="module")
def vegetation() -> list[dict]:
    path = LEVEL_ROOT / "main/MissionGroup/level_objects/vegetation/items.level.json"
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------------ the tree matches the build
def test_every_bulk_member_is_present_and_unmodified() -> None:
    problems = forest_build.verify(LEVEL_ROOT)
    assert problems == {"missing": [], "changed": []}


def test_the_level_allowlist_carries_the_whole_forest() -> None:
    from examples.hot_potato_arena.level import level_writer

    members = set(level_writer.expected_level_members())
    for relative in forest_build.bulk_members(LEVEL_ROOT):
        assert f"levels/{fs.LEVEL_ID}/{relative}" in members
    for relative in forest_build.rendered_outputs():
        assert f"levels/{fs.LEVEL_ID}/{relative}" in members


#: The SHIPPED instance count. The design plants 154,686 (`fs.TOTAL_INSTANCES`, asserted below
#: as the design's own number) and amendment A6 removes the ones standing in the corridor of
#: the road up the canyon wall (`shelf_road.apply_forest_clearance`: every other instance is
#: byte-identical). A gate that measures what ships reads this; a gate that reads the design
#: table reads the design. Same exactness either way.
#:
#: D7 (amendment A7): 515 -> 565. The three cliff shapes changed, so the planter re-ran and
#: re-seated 16,156 instances out of the solid bodies they had ended up inside; 50 more of them
#: landed in the road corridor and the clearance took them. The clearance is a filter over the
#: plant, so this number moves whenever a shape near the road moves -- it is not a constant of
#: the road.
SHIPPED_INSTANCES = 154686 - 565


# --------------------------------------------------------------------------- shapes: QB-6/7/9
def test_the_species_table_is_the_design_table() -> None:
    assert len(fs.SPECIES) == 54, "design §4.2 ships 54 TSForestItemData"
    assert len(fs.TREE_SPECIES) == 18, "18 of them are the generated conifers QB-6 measures"
    assert len({s["key"] for s in fs.SPECIES}) == 54
    assert fs.TOTAL_INSTANCES == 154686, "design §13 QB-16 asserts 154,686 instances"
    # r9 (DEV-22): the fern carpet 100,000 -> 40,000; the design's own sum was 1.41 M
    assert fs.TOTAL_COVER_ELEMENTS == 1_350_000, "design §4.5's 1.41 M less DEV-22's 60,000"
    assert len(fs.GROUND_COVERS) == 17, "DEV-12: 12 billboard records + 5 shape records"


def test_qb6_tree_daes_reproduce_the_design_line(shapes: dict) -> None:
    trees = [row for row in shapes["species"].values() if row["relative"].startswith(fs.TREES_DIR)]
    assert len(trees) == 18
    details = [
        sorted(((int(k), v) for k, v in row["details"].items()), reverse=True) for row in trees
    ]
    tops = [d[0][1] for d in details]
    lows = [d[-1][1] for d in details]
    # QB-6's window is on the p50, not on every shape: "top LOD p50 600-2,500 tris"
    assert percentile([len(d) for d in details], 0.5) == 3.0
    # DEV-9 (r2): the design's §4.2 canopy budgets buy 836 cards on a 28 m pine where three
    # stock conifers carry 2,037-2,697, and their top LODs carry 4,034-5,599 FOLIAGE triangles
    # against our 1,800 total.  r2-r8 raised the ten tall/mid conifers' top budgets so a pine
    # hung 2,086 stock-sized cards, inside QB-6's window at a p50 of 2,400.
    # DEV-28 (r9): measured SIDE BY SIDE with stock in one boot, the r9 crown (1,546 cards on
    # 28 m, 55 per metre) baked at an equator fill of 0.14-0.25 against stock's 0.35-0.40 --
    # stock hangs 142 cards per metre.  Every detail of the ten now carries 2.1-2.5x the
    # cards; the p50 is 4,820, INSIDE stock's own 4,034-5,599 foliage triangles, and QB-6's
    # design window (written for the 836-card canopy) is re-based on that census.
    # DEV-31 (r10): the three TALL PINES went 8,940 / 6,610 / 4,664 -> 13,000 / 9,600 / 6,800.
    # Measured in the r10 boot's own imposter bake (`b3/r10/imposter_luma_r10.json`), the
    # firs came out at an equator bbox fill of 0.356-0.363 against stock douglas fir's
    # 0.221-0.349 -- denser than stock -- while the tall pines sat at 0.177-0.201, BELOW the
    # stock floor of 0.221 and far below italy's scots pine at 0.403.  A pine's foliage is a
    # tuft at the end of each branch (`foliage_from` 0.34), so the same card count spreads
    # over far less silhouette than a fir's full-length sprays, and the imposter is what a
    # player sees for most of the forest.  The p50 is untouched at 4,820, inside stock's own
    # 4,034-5,599 foliage triangles; only the three pines that measured short moved.
    assert 4034 <= percentile(tops, 0.5) <= 5599, "DEV-28: the p50 inside stock's top LODs"
    assert percentile(tops, 0.5) == 4820.0, "DEV-28: the r9 canopy budget"
    assert max(tops) == 13_000 and min(tops) == 700
    ratio = percentile([low / top for low, top in zip(lows, tops, strict=True)], 0.5)
    # r3 (DEV-14): the low/top p50 was 0.100 in r2 and QB-6's own window "<= 0.6" REWARDED
    # that -- a ratio that gets better the thinner the distance mesh gets is the wrong way
    # round, and it is why nothing in r2 measured the defect a driver actually sees.  Three
    # stock conifers sit at 0.46-0.50; the ladder gate below is the real one.
    assert 0.35 <= ratio <= 0.6, "the lowest LOD is a stock-comparable share of its top"
    assert percentile([row["colmesh_tris"] for row in trees], 0.5) == 20.0
    assert all(row["colmesh_tris"] <= 60 for row in trees)
    assert all(row["bb_dim"] == fs.BB_DIM for row in trees), "bb_autobillboard25 on 100 %"


def test_qb7_nulldetail_and_colmesh_coverage(shapes: dict) -> None:
    rows = list(shapes["species"].values()) + list(shapes["covers"].values())
    assert len(rows) == 63, "54 forest species + 9 GroundCover shapes"
    assert all(row["nulldetail"] for row in rows), "every forest DAE ships a nulldetail"
    drive_through = {
        "bark_debris",
        "branch_pile",
        "shrub_01",
        "shrub_02",
        "shrub_03",
        "shrub_04",
        "fern_a",
        "fern_b",
        "reed_clump",
    }
    for key, row in shapes["species"].items():
        if key in drive_through:
            assert row["colmesh_tris"] == 0, f"{key} is drive-through by design"
        else:
            assert row["colmesh_tris"] > 0, f"{key} must ship a non-empty Colmesh"
    for row in shapes["covers"].values():
        assert row["colmesh_tris"] > 0
    heaviest = max(sum(row["details"].values()) for row in rows)
    assert heaviest <= 130_000, "QB-7 hero ceiling"


def test_no_detail_exceeds_its_authored_budget(shapes: dict) -> None:
    for key, row in {**shapes["species"], **shapes["covers"]}.items():
        for pixel, budget in row["budgets"].items():
            assert row["details"][pixel] <= budget, f"{key} _a{pixel} over budget"


def test_every_shipped_dae_has_the_stock_node_tree(shapes: dict) -> None:
    for key, row in shapes["species"].items():
        species = fs.SPECIES_BY_KEY[key]
        stem = bf.dae_stem(key)
        expected = bf.expected_tree(
            stem,
            tuple(pixel for pixel, _ in species["details"]),
            bb=species["bb"],
            null=species["null"],
            colmesh=bool(species["colmesh"]),
        )
        assert bf.dae_node_parents(LEVEL_ROOT / row["relative"]) == expected
    for key, row in shapes["covers"].items():
        cover = next(c for c in fs.COVER_SHAPES if c["key"] == key)
        stem = bf.dae_stem(key, cover=True)
        expected = bf.expected_tree(
            stem, (cover["detail_px"],), bb=False, null=cover["null"], colmesh=True
        )
        assert bf.dae_node_parents(LEVEL_ROOT / row["relative"]) == expected


def test_qb9_bb_dim_128_is_written_into_every_billboarded_shape(shapes: dict) -> None:
    billboarded = [row for key, row in shapes["species"].items() if fs.SPECIES_BY_KEY[key]["bb"]]
    assert len(billboarded) == 54, "design §4.3 counts all 54 forest items among the 68 pairs"
    # r4 (DEV-20): the block carries three lines now -- BB::DIM plus the equator and polar
    # step counts that take the atlas from 6 views to 26.
    pattern = re.compile(
        r'<node id="bb_autobillboard25".*?<technique profile="OpenCOLLADA"><user_properties>'
        + re.escape(fs.BB_PROPERTY)
        + r"</user_properties>",
        re.S,
    )
    for row in billboarded:
        text = (LEVEL_ROOT / row["relative"]).read_text("utf-8")
        assert pattern.search(text), f"{row['file']} lost its BB:: user properties"


def test_daes_are_quantised_and_lf(shapes: dict) -> None:
    for row in {**shapes["species"], **shapes["covers"]}.values():
        raw = (LEVEL_ROOT / row["relative"]).read_bytes()
        assert b"\r" not in raw, f"{row['file']} carries CR bytes"
        text = raw.decode("utf-8")
        assert bf.COLLADA_EPOCH in text, "the Collada timestamps must be pinned (AGENTS.md L710)"
        assert bf.quantise_collada(text) == text, "float arrays are not at five decimals"


# ------------------------------------------------------------------- datablocks: QB-16 / 16b
def test_qb16_datablocks_and_instances(datablocks: dict, plant: dict) -> None:
    assert len(datablocks) == 54
    assert plant["instances_total"] == SHIPPED_INSTANCES
    assert plant["datablocks"] == 54
    per_species = plant["per_species"]
    assert sum(per_species.values()) == SHIPPED_INSTANCES
    assert all(count > 0 for count in per_species.values()), "no species ships zero instances"


def test_qb16b_every_wind_and_physics_field_on_every_datablock(datablocks: dict) -> None:
    required = (
        "windScale",
        "branchAmp",
        "detailAmp",
        "detailFreq",
        "trunkBendScale",
        "mass",
        "radius",
        "rigidity",
        "dampingCoefficient",
        "tightnessCoefficient",
        "shadowNullDetailSize",
    )
    for name, record in datablocks.items():
        for field in required:
            assert field in record, f"{name} is missing {field}"
        assert record["class"] == "TSForestItemData"
        assert record["annotation"] in ("NATURE", "ROCK"), "level_facts: TREE is not a known one"
        assert record["shapeFile"].startswith(f"/levels/{fs.LEVEL_ID}/")


def test_every_datablock_points_at_a_shipped_dae(datablocks: dict) -> None:
    for record in datablocks.values():
        relative = record["shapeFile"].split(f"/levels/{fs.LEVEL_ID}/", 1)[1]
        assert (LEVEL_ROOT / relative).is_file(), record["shapeFile"]


# ------------------------------------------------------------------------------ forest4 files
def test_forest4_schema_and_counts(plant: dict) -> None:
    for name, count in plant["per_species"].items():
        path = LEVEL_ROOT / f"forest/{name}.forest4.json"
        lines = path.read_text("utf-8").splitlines()
        assert len(lines) == count, f"{name}: {len(lines)} rows, census says {count}"
        for line in lines[:64]:
            record = json.loads(line)
            assert set(record) == {"ctxid", "pos", "rotationMatrix", "scale", "type"}
            assert record["type"] == name
            assert len(record["pos"]) == 3
            assert len(record["rotationMatrix"]) == 9
            assert fs.SCALE_MIN - 1e-9 <= record["scale"] <= fs.SCALE_MAX + 1e-9


def _strict_loads(text: str, what: str):
    """``json.loads`` with the leniency switched OFF, the way a conforming reader parses.

    CPython accepts the bare tokens ``NaN`` / ``Infinity`` / ``-Infinity`` by default; RFC 8259
    has no such literals, so a file carrying one is not JSON even though ``json.loads`` reads
    it.  195 shipped instances carried ``"pos": [x, y, NaN]`` and every gate in this suite
    passed over them: the height check samples, the keep-out reductions are over x/y, and the
    live count never looks at a position.  This is the gate that could have seen it.
    """

    def refuse(token: str):
        raise AssertionError(f"{what}: the non-JSON literal {token!r} is in the file")

    return json.loads(text, parse_constant=refuse)


def _walk_numbers(node, path: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_numbers(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_numbers(value, f"{path}[{index}]")
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield path, node


def _generated_json_files() -> list[Path]:
    """Every release-bound JSON B3 writes: the forest4 JSONL, the datablocks, the materials,
    the vegetation group and the four authoring manifests."""
    files = sorted((LEVEL_ROOT / "forest").glob("*.forest4.json"))
    files.append(LEVEL_ROOT / "art/forest/managedItemData.json")
    files.append(LEVEL_ROOT / "main/MissionGroup/level_objects/vegetation/items.level.json")
    for family, directory in {
        "trees": fs.TREES_DIR,
        "deadwood": fs.DEADWOOD_DIR,
        "undergrowth": fs.CARDS_DIR,
        "rocks": fs.ROCKS_DIR,
        "groundcover": fs.COVER_DIR,
    }.items():
        files.append(LEVEL_ROOT / directory / f"{fs.LEVEL_ID}_{family}.materials.json")
    files += [
        forest_build.SHAPES_MANIFEST,
        forest_build.TEXTURES_MANIFEST,
        forest_build.PLANT_MANIFEST,
        forest_build.KEEPOUT_PROOF,
    ]
    return [path for path in files if path.is_file()]


def test_every_generated_json_is_strict_json_and_every_number_is_finite() -> None:
    """The gate D1 was missing: strict RFC-8259 parse + isfinite on EVERY number we ship.

    Not a sample and not one file family -- every JSON this worker generates, line by line for
    the JSONL ones, with ``parse_constant`` raising and an explicit ``math.isfinite`` on each
    scalar.  The bug it exists for wrote 195 ``NaN`` z values that read back fine through the
    default decoder.
    """
    checked_files = 0
    checked_numbers = 0
    for path in _generated_json_files():
        text = path.read_text("utf-8")
        jsonl = path.name.endswith(".forest4.json") or path.name.endswith("items.level.json")
        lines = enumerate(text.splitlines(), 1)
        chunks = (
            [(f"{path.name}:{n}", line) for n, line in lines if line.strip()]
            if jsonl
            else [(path.name, text)]
        )
        for what, chunk in chunks:
            document = _strict_loads(chunk, what)
            for where, value in _walk_numbers(document, what):
                assert math.isfinite(value), f"{where} = {value!r} is not finite"
                checked_numbers += 1
        checked_files += 1
    assert checked_files >= 54 + 6, f"only {checked_files} generated JSON files were parsed"
    assert checked_numbers > 2_000_000, checked_numbers


def test_no_instance_stands_outside_the_samplable_terrain_block(plant: dict) -> None:
    """Every instance is inside the HALF-OPEN block the bilinear surface is defined on.

    The coverage law: ``z_at_arr`` needs the ``i+1`` / ``j+1`` neighbours, so index ``N-1`` is
    an edge plane and is NOT samplable; the usable domain is ``[xs[0], xs[-1]) x [ys[0],
    ys[-1])``.  195 instances sat in the <= 1 m strip outside it.
    """
    from examples.hot_potato_arena.level import plant_forest, terrain_model

    grid = terrain_model.get_grid()
    xs, ys = grid["xs"], grid["ys"]
    outside = 0
    total = 0
    for name in sorted(plant["per_species"]):
        path = LEVEL_ROOT / f"forest/{name}.forest4.json"
        for line in path.read_text("utf-8").splitlines():
            x, y, z = json.loads(line)["pos"]
            total += 1
            if not (xs[0] <= x < xs[-1] and ys[0] <= y < ys[-1]):
                outside += 1
            assert math.isfinite(z)
    assert total == SHIPPED_INSTANCES
    assert outside == 0, f"{outside} instances are off the samplable block"
    assert not plant_forest.samplable(
        __import__("numpy").array([float(xs[-1])]), __import__("numpy").array([0.0])
    )[0], "the edge plane must not be samplable -- that is the law the fix encodes"


def test_the_keep_out_proof_has_no_violations() -> None:
    proof = json.loads(forest_build.KEEPOUT_PROOF.read_text("utf-8"))
    assert proof["instances"] == SHIPPED_INSTANCES
    for rule, value in proof.items():
        if isinstance(value, dict) and "violations" in value:
            assert value["violations"] == 0, f"{rule}: {value}"
    assert proof["min_radius_from_C_m"] >= fs.EVERYTHING_KEEPOUT_R
    assert proof["rule_road_corridor_9m"]["min_distance_to_either_m"] > fs.ROAD_KEEPOUT_M


def test_instance_heights_sit_on_the_design_surface(plant: dict) -> None:
    """A sample of instances is re-sampled against terrain_model's bilinear surface."""
    from examples.hot_potato_arena.level import terrain_io as terrain

    worst = 0.0
    for name in sorted(plant["per_species"])[:6]:
        path = LEVEL_ROOT / f"forest/{name}.forest4.json"
        for line in path.read_text("utf-8").splitlines()[::997]:
            record = json.loads(line)
            x, y, z = record["pos"]
            worst = max(worst, abs(terrain.surface_z(x, y) - z))
    assert worst <= 1e-3, f"an instance is {worst:.4f} m off the modelled surface"


# ------------------------------------------------------------- materials: QB-13 / QB-10 / 10b
def test_qb13_foliage_materials(materials: dict) -> None:
    foliage = {
        name: record
        for name, record in materials.items()
        if str(record.get("annotation", "")).upper() == "NATURE"
        and str(record.get("alphaTest", "0")).lower() in ("1", "true", "True")
    }
    assert len(foliage) == 23, "design §4.5 ships 22 foliage materials, + `f_branches` (r11, B10-1)"
    refs = [record["alphaRef"] for record in foliage.values()]
    # r4 (DEV-21): the design states alphaRef 84/110 and QB-13's own window is "p50 50-100,
    # max <= 150".  Every cut-out reference is now 255 x its own measured opaque coverage,
    # capped at the design's value, because a reference above the atlas's mip-averaged alpha
    # dissolves the card at distance (see the mip-chain gate).  p50 84 -> 57.5, max 110 -> 98.
    assert 50 <= percentile(refs, 0.5) <= 100, "QB-13's own window on the alphaRef p50"
    assert max(refs) <= 150
    for name, record in foliage.items():
        assert record["subSurface"] is True, name
        assert record["subSurfaceIntensity"] == 1, name
        assert record["doubleSided"] is True, name
        assert record["invertBackFaceNormals"] is True, name
        assert record["groundType"] in ("LEAVES_STRONG", "LEAVES_THIN", "GRASS", "WOOD"), name


def test_qb10_every_material_ships_the_pbr_roles(materials: dict) -> None:
    for name, record in materials.items():
        stage = record["Stages"][0]
        for field in ("baseColorMap", "normalMap", "roughnessMap", "ambientOcclusionMap"):
            assert field in stage, f"{name} has no {field}"
        for field, value in stage.items():
            relative = value.split(f"/levels/{fs.LEVEL_ID}/", 1)[1]
            assert (LEVEL_ROOT / relative).is_file(), f"{name}.{field} -> {value} is dangling"


def test_cut_out_materials_ship_an_opacity_map(materials: dict) -> None:
    for material in fs.MATERIALS:
        if "opacity" not in fs.MATERIAL_ROLES[material.get("kind", "rock")]:
            continue
        stage = materials[fs.material_name(material["key"])]["Stages"][0]
        assert "opacityMap" in stage, material["key"]


def test_qb12_texture_resolutions(textures: dict) -> None:
    """QB-12's floor holds; its 2048 clause is REVERSED by an engine law (r9, DEV-26).

    level_facts 2026-09-06 (PROVEN): at `GraphicTextureQuality` "Normal" -- the setting on
    the sentinel AND the real profile, which nobody may change -- the engine allocates an
    11-level texture object, a 2048 source renders at 1024 and a 12-level DDS chain is
    refused and never streams in.  So a 2048 map buys nothing visible and can cost the map;
    every B3 map ships at or under 1024 and the atlases are composed at that size.
    """
    sizes = [max(row["resolution"]) for row in textures["files"].values()]
    # r11 (B10-1): + the branch material's five 512 maps
    assert len(sizes) == 151
    assert sum(1 for s in sizes if s >= 1024) / len(sizes) >= 0.25
    assert max(sizes) <= 1024, "DEV-26: no B3 map may exceed the Normal texture object"


# ------------------------------------------------------------------- covers: QB-17 / 18 / 18b
def test_qb17_exactly_one_wind_emitter(vegetation: list[dict]) -> None:
    emitters = [r for r in vegetation if r["class"] == "ForestWindEmitter"]
    assert len(emitters) == 1
    record = emitters[0]
    assert record["strength"] == 0.5 and record["gustFrequency"] == 2
    assert record["gustStrength"] == 3 and record["gustWobbleStrength"] == 3
    assert record["gustYawAngle"] == 50 and record["turbulenceStrength"] == 5.25


def test_qb18_ground_covers(vegetation: list[dict]) -> None:
    covers = [r for r in vegetation if r["class"] == "GroundCover"]
    assert len(covers) == 17, "DEV-12 stacks the five billboard covers into twelve records"
    assert sum(r["maxElements"] for r in covers) == 1_350_000  # DEV-22 (r9)
    billboard = [r for r in covers if "material" in r]
    assert percentile([len(r["Types"]) for r in billboard], 0.5) == 5.0
    for record in covers:
        assert 50 <= record["radius"] <= 70, record["name"]
        assert record["maxBillboardTiltAngle"] == 40
        assert record["shapesCastShadows"] is False
        for field in (
            "windGustFrequency",
            "windGustLength",
            "windGustStrength",
            "windTurbulenceFrequency",
            "windTurbulenceStrength",
        ):
            assert field in record, f"{record['name']} missing {field}"
        if "dissolveRadius" in record:
            assert 30 <= record["dissolveRadius"] <= 100


def test_qb18b_shape_covers_on_every_dirt_layer(vegetation: list[dict]) -> None:
    layers = set()
    for record in (r for r in vegetation if r["class"] == "GroundCover"):
        if any("shapeFilename" in t for t in record["Types"]):
            layers.update(t["layer"] for t in record["Types"])
    assert {"ash", "scree", "rock", "forest_floor", "trail", "hearth"} <= layers


def test_cover_layers_are_real_terrain_materials(vegetation: list[dict]) -> None:
    from examples.hot_potato_arena.level import terrain_io as terrain

    for record in (r for r in vegetation if r["class"] == "GroundCover"):
        for entry in record["Types"]:
            assert entry["layer"] in terrain.MATERIALS, entry["layer"]


def test_cover_shapes_and_materials_resolve(vegetation: list[dict], materials: dict) -> None:
    for record in (r for r in vegetation if r["class"] == "GroundCover"):
        if "material" in record:
            assert record["material"] in materials
        for entry in record["Types"]:
            if "shapeFilename" in entry:
                relative = entry["shapeFilename"].split(f"/levels/{fs.LEVEL_ID}/", 1)[1]
                assert (LEVEL_ROOT / relative).is_file(), entry["shapeFilename"]
            if "billboardUVs" in entry:
                u, v, w, h = entry["billboardUVs"]
                assert 0.0 <= u < 1.0 and 0.0 <= v < 1.0 and 0 < w <= 1 and 0 < h <= 1
                assert u + w <= 1.0 + 1e-9 and v + h <= 1.0 + 1e-9


# ------------------------------------------------------ the global SimObject name space (law)
def test_no_name_is_declared_twice_across_classes(
    datablocks: dict, materials: dict, vegetation: list[dict]
) -> None:
    """level_facts: 'SimObject names are global across classes'.

    A Material named like a TSForestItemData is refused with "Cannot re-declare object ...
    with a different class" and EVERY instance of that item then vanishes -- boot 1 run 1 of
    the scaffold lost its whole rock population that way.  The frozen design's own foliage
    list collides with species 28-31 on four names; DEV-3 renames the materials.
    """
    buckets = {
        "TSForestItemData": set(datablocks),
        "Material": set(materials),
        "scene object": {r["name"] for r in vegetation if "name" in r},
    }
    seen: dict[str, str] = {}
    for kind, names in buckets.items():
        for name in names:
            assert name not in seen, f"{name} declared as both {seen[name]} and {kind}"
            seen[name] = kind


def test_every_forest_name_is_namespaced(datablocks: dict, materials: dict) -> None:
    for name in list(datablocks) + list(materials):
        assert name.startswith(f"{fs.LEVEL_ID}_"), name


def test_every_shipped_basename_is_namespaced(shapes: dict, textures: dict) -> None:
    rows = list(shapes["species"].values()) + list(shapes["covers"].values())
    for row in rows:
        assert row["file"].startswith(f"{fs.LEVEL_ID}_"), row["file"]
    for relative in textures["files"]:
        assert Path(relative).name.startswith(f"{fs.LEVEL_ID}_"), relative


# --------------------------------------------------------------------------------- provenance
def _cc0_ids_b3_uses() -> set[str]:
    """Every CC0 id the build reads, INCLUDING the r2 cut-out ``sources`` lists.

    r1's version read only ``material["cc0"]``.  An atlas composed from five sources would have
    had four of them unchecked, which is a provenance claim that is not tested -- so the set is
    built from the source lists too.
    """
    used = {material["cc0"] for material in fs.MATERIALS}
    for material in fs.MATERIALS:
        used |= {spec["cc0"] for spec in material.get("sources", ())}
    used |= {s["source"][0] for s in fs.SPECIES if "source" in s}
    used |= {c["source"][0] for c in fs.COVER_SHAPES if "source" in c}
    return used


def test_every_cut_out_source_resolves_and_is_covered_by_the_gates() -> None:
    """Every ``sources`` entry names a real recipe and a cache asset the cook can open."""
    from examples.hot_potato_arena.level import forest_textures as ft

    cache = Path(__file__).resolve().parents[1] / "examples/hot_potato_arena/cc0_cache"
    seen = 0
    for material in fs.MATERIALS:
        for spec in material.get("sources", ()):
            assert spec.get("mask", "alpha") in ft.STAMP_MASKS, spec
            assert (cache / spec["cc0"]).is_dir(), spec["cc0"]
            seen += 1
    assert seen >= 20, f"only {seen} cut-out sources declared"


def test_every_cc0_source_is_in_the_provenance_ledger() -> None:
    ledger = json.loads(PROVENANCE.read_text("utf-8"))
    recorded = {row["asset"] for row in ledger["files"].values()}
    used = _cc0_ids_b3_uses()
    missing = sorted(used - recorded)
    assert not missing, f"CC0 ids used by B3 with no provenance row: {missing}"
    assert ledger["license"].startswith("CC0 1.0")


def test_the_manifest_of_the_b3_fetch_matches_what_the_spec_uses() -> None:
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "examples/hot_potato_arena/cc0/manifests/b3_vegetation.json"
        ).read_text("utf-8")
    )
    fetched = {row["asset"] for row in manifest}
    used = _cc0_ids_b3_uses()
    # burned_ground_01 is B1's fetch (the ash detail); B3 reuses it for the cinder cover and,
    # in r2, for the scorch-stubble cut-outs
    assert used - fetched <= {"burned_ground_01"}


# ------------------------------------------------------------------- the design's own numbers
def test_zone_density_table_is_the_design_table() -> None:
    counts = fs.zone_category_counts()
    assert counts[("forest_core", "trees")] == 262 * 160
    assert counts[("forest_edge", "shrubs_ferns")] == 24 * 200
    assert counts[("scree_rock", "rocks")] == 78 * 300
    assert counts[("alpine", "rocks")] == 10 * 144
    assert sum(counts.values()) == 154686


def test_every_deviation_from_the_frozen_design_is_recorded() -> None:
    ids = [row["id"] for row in fs.DEVIATIONS]
    assert ids == sorted(ids, key=lambda i: int(i.split("-")[1]))
    assert len(set(ids)) == len(ids) == 29, (
        "r4 adds DEV-19..DEV-21, r9 DEV-22..DEV-28, r12 DEV-29 (the three shrub imposters: "
        "graded sheets, AO floor, dome cards wound outward -- critic B11-5)"
    )
    for row in fs.DEVIATIONS:
        assert row["design"] and row["built"] and row["reason"]


# ==================================================================== r3: the distance LOD (D4)
# Nothing in r1 or r2 measured the DISTANCE LOD or the crown's SHAPE, and both are what a driver
# sees: design 4.3's own arithmetic (935 px per unit of height/distance at 1080p) puts a 28 m
# tree's lowest mesh LOD in charge from 87 m to 262 m.  r2 shipped 296 foliage triangles there
# against three stock conifers' 1,886-2,643, a last ladder step of 5.61x against their <= 1.50x,
# and a crown that collapsed to 24 % of its own top-LOD width.  These gates are the ladder.
import collections  # noqa: E402
import itertools  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402

COLLADA = "{http://www.collada.org/2005/11/COLLADASchema}"


def _positions(mesh) -> list[float]:
    source_ids = {
        inp.get("source", "").lstrip("#")
        for vert in mesh.findall(f"{COLLADA}vertices")
        for inp in vert.findall(f"{COLLADA}input")
        if inp.get("semantic") == "POSITION"
    }
    for source in mesh.findall(f"{COLLADA}source"):
        if source.get("id") in source_ids:
            return [float(v) for v in source.find(f"{COLLADA}float_array").text.split()]
    return []


def _prims(mesh) -> list[tuple[str, list[int]]]:
    """[(material symbol, flat vertex index list), ...] for every <triangles> of one mesh."""
    rows = []
    for prim in mesh.findall(f"{COLLADA}triangles"):
        inputs = prim.findall(f"{COLLADA}input")
        stride = max(int(i.get("offset", "0")) for i in inputs) + 1
        offset = next(int(i.get("offset", "0")) for i in inputs if i.get("semantic") == "VERTEX")
        flat = [int(v) for v in prim.find(f"{COLLADA}p").text.split()][offset::stride]
        rows.append((prim.get("material") or "", flat))
    return rows


def _detail_geometry(path: Path, node_name: str):
    """(positions, [(material symbol, indices), ...]) of one _a<px> detail node."""
    root = ET.parse(path).getroot()  # a DAE this repository wrote itself
    meshes = {
        geometry.get("id"): (
            _positions(geometry.find(f"{COLLADA}mesh")),
            _prims(geometry.find(f"{COLLADA}mesh")),
        )
        for geometry in root.iter(f"{COLLADA}geometry")
        if geometry.find(f"{COLLADA}mesh") is not None
    }
    coordinates: list[float] = []
    prims: list[tuple[str, list[int]]] = []
    for node in root.iter(f"{COLLADA}node"):
        if (node.get("name") or node.get("id")) != node_name:
            continue
        for instance in node.findall(f"{COLLADA}instance_geometry"):
            flat, rows = meshes[instance.get("url", "").lstrip("#")]
            base = len(coordinates) // 3
            coordinates.extend(flat)
            prims.extend((symbol, [i + base for i in idx]) for symbol, idx in rows)
    return coordinates, prims


def _foliage_ladder_from_the_shipped_dae(species: dict) -> list[int]:
    """Foliage triangles per detail, highest pixel size first, MEASURED on the file."""
    path = LEVEL_ROOT / fs.species_dae_relative(species)
    ladder = []
    for pixel, _ in species["details"]:
        node = bf.detail_node(bf.dae_stem(species["key"]), pixel)
        _, prims = _detail_geometry(path, node)
        wanted = _foliage_symbols(species)
        ladder.append(sum(len(idx) // 3 for symbol, idx in prims if symbol in wanted))
    return ladder


#: the SLOT a foliage card is bound to; the trunk tube takes "bark"
FOLIAGE_SLOTS = ("twig", "leaf")


def _foliage_symbols(species: dict) -> set[str]:
    """The DAE <triangles material="..."> symbols that carry foliage, not bark.

    Blender's Collada exporter writes the MATERIAL's name with a "-material" suffix, not the
    slot name, so this resolves the slot through forest_spec.material_name.
    """
    return {
        f"{fs.material_name(key)}-material"
        for slot, key in species["materials"]
        if slot in FOLIAGE_SLOTS
    }


def test_the_lod_ladder_steps_like_a_stock_conifer() -> None:
    """Every foliage step <= 1.5x and the lowest LOD >= 35 % of its top, on the shipped DAEs.

    Stock, measured by critic r2 out of the game's own zips: ECUSA tree_douglasfir_large_a
    5,395 -> 3,776 -> 2,643 (1.43, 1.43, low/top 0.49), italy scots_pine 4,074 -> 2,795 ->
    1,886 (1.46, 1.48, 0.46), WCUSA pine_radiata_large 5,140 -> 3,855 -> 2,570 (1.33, 1.50,
    0.50).  r2's f_pine_tall_a was 4,172 -> 1,660 -> 296: steps 2.51 and 5.61, low/top 0.071,
    and that 296-triangle mesh drew every tree from 87 m to 262 m.
    """
    checked = 0
    for species in fs.SPECIES:
        if species["build"] not in ("conifer", "card"):
            continue
        ladder = _foliage_ladder_from_the_shipped_dae(species)
        assert ladder == list(fs.foliage_ladder(species)), (
            f"{species['key']}: the shipped DAE does not carry the authored foliage ladder"
        )
        for near, far in itertools.pairwise(ladder):
            assert near / far <= fs.LOD_STEP_MAX + 1e-9, (
                f"{species['key']}: an LOD step of {near / far:.2f}x, stock's worst is 1.50x"
            )
        assert ladder[-1] / ladder[0] >= fs.LOD_LOW_TOP_MIN, (
            f"{species['key']}: the lowest LOD keeps {ladder[-1] / ladder[0]:.3f} of its top, "
            "stock keeps 0.46-0.50"
        )
        checked += 1
    assert checked == 23, "10 tall/mid conifers + 6 saplings/dwarf + 7 card shapes"


def _triangle_area(coordinates: list[float], a: int, b: int, c: int) -> float:
    pa = coordinates[3 * a : 3 * a + 3]
    pb = coordinates[3 * b : 3 * b + 3]
    pc = coordinates[3 * c : 3 * c + 3]
    u = [pb[i] - pa[i] for i in range(3)]
    v = [pc[i] - pa[i] for i in range(3)]
    cross = (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )
    return 0.5 * math.sqrt(sum(t * t for t in cross))


#: r4 (critic r3 M14): MEASURED on the shipped opacity map at the material's own alphaRef,
#: not copied from critic r2's table.  r3 hard-coded `f_dwarf_pine: 0.233` where the shipped
#: atlas reads 0.332, so the gate rendered that species' silhouette ~30 % too thin -- a gate
#: measuring a constant instead of the artefact.
_COVERAGE_CACHE: dict[str, float] = {}


def foliage_coverage(key: str) -> float:
    """Alpha coverage of one cut-out atlas at its own alphaRef, read off the shipped PNG."""
    if key not in _COVERAGE_CACHE:
        import numpy as np
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = None
        material = next((m for m in fs.MATERIALS if m["key"] == key), None)
        if material is None or "alphaRef" not in material:
            return 0.22
        with Image.open(LEVEL_ROOT / fs.texture_relative(key, "opacity")) as image:
            opacity = np.asarray(image.convert("L"))
        _COVERAGE_CACHE[key] = float((opacity >= material["alphaRef"]).mean())
    return _COVERAGE_CACHE[key]


SIDE_VIEW_MPP = 0.05


def _side_view(species: dict, pixel: int):
    """Orthographic side view of one detail's FOLIAGE, as an opacity image at 0.05 m/px.

    This is critic r2's `crown_profile.render`: every foliage triangle is rasterised into its
    bounding box and multiplied into the running transmittance with its own material's alpha
    coverage, so a sparse atlas contributes less per card exactly as it does on screen.
    """
    import numpy as np

    path = LEVEL_ROOT / fs.species_dae_relative(species)
    coordinates, prims = _detail_geometry(path, bf.detail_node(bf.dae_stem(species["key"]), pixel))
    wanted = {
        f"{fs.material_name(key)}-material": foliage_coverage(key)
        for slot, key in species["materials"]
        if slot in FOLIAGE_SLOTS
    }
    tris = [
        (idx[i], idx[i + 1], idx[i + 2], wanted[symbol])
        for symbol, idx in prims
        if symbol in wanted
        for i in range(0, len(idx) - 2, 3)
    ]
    assert tris, f"{species['key']} _a{pixel}: no foliage"
    xs = [coordinates[3 * v] for a, b, c, _ in tris for v in (a, b, c)]
    zs = [coordinates[3 * v + 2] for a, b, c, _ in tris for v in (a, b, c)]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    nx = max(4, int((x1 - x0) / SIDE_VIEW_MPP) + 8)
    nz = max(4, int((z1 - z0) / SIDE_VIEW_MPP) + 8)
    keep = np.ones((nz, nx))
    for a, b, c, coverage in tris:
        px = [(coordinates[3 * v] - x0) / SIDE_VIEW_MPP + 4 for v in (a, b, c)]
        pz = [(z1 - coordinates[3 * v + 2]) / SIDE_VIEW_MPP + 4 for v in (a, b, c)]
        cx0, cx1 = int(max(0, min(px))), int(min(nx - 1, max(px)))
        cz0, cz1 = int(max(0, min(pz))), int(min(nz - 1, max(pz)))
        if cx1 < cx0 or cz1 < cz0:
            continue
        keep[cz0 : cz1 + 1, cx0 : cx1 + 1] *= 1.0 - coverage
    return 1.0 - keep, (z1 - z0)


def _opaque_width(opacity) -> float:
    """The widest 1 m height band of opaque crown, in metres.

    critic r2's `crown_profile.render` measures exactly this -- "per 1 m height band: the
    OPAQUE WIDTH (columns with opacity >= 0.5)" -- and reports its maximum.  Its readings on
    the r2 tree were 7.15 m at pine_tall_a's top LOD and 1.70 m at its lowest (24 %), against
    ECUSA's lowest 8.3 m (94 % of its own top) and italy's 11.35 m (104 %).
    """
    import numpy as np

    band = max(1, round(1.0 / SIDE_VIEW_MPP))
    widest = 0.0
    for row in range(0, opacity.shape[0], band):
        columns = np.nonzero((opacity[row : row + band] >= 0.5).any(axis=0))[0]
        if len(columns):
            widest = max(widest, (columns[-1] - columns[0] + 1) * SIDE_VIEW_MPP)
    return float(widest)


def _banding(opacity) -> dict:
    """The crown's vertical banding, on critic r2's own side-view statistic.

    `critic_r2/crown_banding.py` exactly: the mean opacity per 0.05 m row of crown, detrended
    with a 41-row moving average, Hann-windowed, and the strongest vertical period expressed
    as a share of the whole spectrum (`band_strength`).  r2 read 0.332 on `f_pine_tall_a` and
    0.320 on `f_pine_mid_a` against three stock conifers' 0.0505 / 0.1028 / 0.0894.

    `band_strength` is NOT scale free: a 2 m sapling crown has 20 FFT bins and a 23 m pine
    227, so the same relative comb takes ten times the share on the sapling and its dominant
    "period" comes out LONGER than its own crown -- the cone's taper, not a ladder.  The
    scale-free form divides by the mean bin instead (`prominence`; a flat spectrum reads 1.0
    at any height).  Measured on the shipped tree: B3's six saplings read 0.25-0.46 on
    band_strength and 7.99-12.03 on prominence, where the three stock conifers read
    9.13 / 14.08 / 10.99.  Both are returned so the gate can use the right one per shape.
    """
    import numpy as np

    profile = opacity.mean(axis=1)
    crown = np.nonzero(profile > 0.02 * profile.max())[0]
    raw = profile[crown[0] : crown[-1] + 1]
    p = raw - np.convolve(raw, np.ones(41) / 41, mode="same")
    p = p - p.mean()
    spectrum = np.abs(np.fft.rfft(p * np.hanning(len(p))))
    spectrum[0] = 0.0
    total = float(spectrum.sum()) + 1e-9
    k = int(np.argmax(spectrum))
    whorl = spectrum[3:] if len(spectrum) > 3 else spectrum[1:]
    bins = max(1, len(spectrum) - 1)
    return {
        "band_strength": float(spectrum[k] / total),
        "band_strength_whorl": float(whorl.max() / total) if len(whorl) else 0.0,
        "prominence": float(spectrum[k] / (total / bins)),
        "prominence_whorl": float(whorl.max() / (total / bins)) if len(whorl) else 0.0,
        "period_m": float((len(p) / k) * SIDE_VIEW_MPP) if k else float("nan"),
        "trough_pct": float((raw < 0.25 * raw.mean()).mean() * 100.0),
    }


def test_the_lod_ladder_conserves_the_crown_area() -> None:
    """Fewer cards at distance, but BIGGER, so the crown keeps its width instead of dissolving.

    The card half-side is multiplied by sqrt(cards_top / cards_here) (forest_spec.lod_card_scale),
    which holds the total card AREA constant down the ladder.  Measured on the shipped DAE: the
    lowest LOD's card area within 15 % of the top LOD's, and its OPAQUE crown width -- rendered
    the way critic r2 rendered it, alpha-weighted at 0.05 m/px -- at least 90 % of the top LOD's.
    r2's lowest LOD carried 7 % of the top's triangles at the SAME card size and the critic
    measured its crown at 1.70 m against its own top LOD's 7.15 m: 24 %, where three stock
    conifers' lowest LODs keep 94-104 %.
    """
    ratios = []
    for species in fs.SPECIES:
        if species["build"] not in ("conifer", "card"):
            continue
        key = species["key"]
        path = LEVEL_ROOT / fs.species_dae_relative(species)
        areas, widths = [], []
        for pixel, _ in species["details"]:
            coordinates, prims = _detail_geometry(path, bf.detail_node(bf.dae_stem(key), pixel))
            wanted = _foliage_symbols(species)
            total = 0.0
            for symbol, idx in prims:
                if symbol not in wanted:
                    continue
                for i in range(0, len(idx) - 2, 3):
                    total += _triangle_area(coordinates, idx[i], idx[i + 1], idx[i + 2])
            areas.append(total)
            widths.append(_opaque_width(_side_view(species, pixel)[0]))
        assert abs(areas[-1] / areas[0] - 1.0) <= 0.15, (
            f"{key}: the lowest LOD carries {areas[-1] / areas[0]:.2f} of the top LOD's card area"
        )
        ratios.append(widths[-1] / widths[0])
        assert ratios[-1] >= 0.75, (
            f"{key}: the crown narrows to {ratios[-1]:.2f} of its top-LOD opaque width "
            f"({widths[0]:.2f} m -> {widths[-1]:.2f} m)"
        )
    # The per-species floor is 0.75 because the measure is a THRESHOLD on a rendered
    # silhouette and a seeded card scatter moves it a few per cent either way; the population
    # is what the frames show.  Measured over all 23 card-bearing shapes: mean 0.97, worst
    # 0.77.  r2's pine_tall_a was 0.24 by critic r2's own render of the same statistic, and
    # the two stock lowest LODs it measured are 0.94 and 1.04.
    assert sum(ratios) / len(ratios) >= 0.90, (
        f"the population mean crown width at the lowest LOD is {sum(ratios) / len(ratios):.3f}"
    )
    assert len(ratios) == 23


def test_the_crown_is_not_a_stack_of_plates() -> None:
    """No dominant vertical period in the crown, on critic r2's OWN statistic (D5).

    r2 put every card of a whorl at exactly the whorl's z: 8-12 whorls over an 18 m crown is a
    1.5-1.6 m comb, and critic r2 measured the banding energy at 0.332 (f_pine_tall_a) and
    0.320 (f_pine_mid_a) against three stock conifers' 0.051 / 0.103 / 0.089, with 24.1 % and
    29.7 % of the crown's rows near-empty sky.  This gate is that instrument, reimplemented on
    the shipped DAE, and the WHORL-BAND reading (periods shorter than a third of the crown) has
    to hold for every conifer including the 2-4 m saplings, whose short crowns make the raw
    statistic read the cone's own taper as a period.

    r9 re-based the raw ceiling from 0.12 to 0.17 on a STOCK measurement by this same
    `_banding` (b3/r9/stock_banding.py -> stock_banding.json, 2026-09-08): italy's maritime
    pine reads 0.167, its scots pine 0.13-0.16 by view, ECUSA's douglas firs 0.039-0.15 and
    Utah's juniper 0.199 -- a real conifer's tiered whorls ARE a vertical period, and r9's
    rebuilt crowns (conical, tiered whorls, tufted pines) read 0.042-0.155 on the >= 8 m
    crowns, inside stock's own band.  Prominence (<= 18, stock max 16.2) and trough
    (<= 12.1 %, stock 3.8-18.3 %) stay where they were.
    """
    for species in fs.SPECIES:
        if species["build"] != "conifer":
            continue
        opacity, crown_m = _side_view(species, species["details"][0][0])
        band = _banding(opacity)
        assert band["prominence"] <= 18.0, (
            f"{species['key']}: banding prominence {band['prominence']:.2f} at a period of "
            f"{band['period_m']:.2f} m -- a ladder of plates on a pole"
        )
        assert band["trough_pct"] <= 12.1, (
            f"{species['key']}: {band['trough_pct']:.1f} % of the crown's rows are near-empty "
            "sky (ECUSA's douglasfir, the worst of the three stock conifers, is 12.1 %)"
        )
        if crown_m >= 8.0:
            # the 41-row detrend is 2.05 m, so on a crown of 8 m or more critic r2's raw
            # statistic is meaningful and is directly the number it published; 0.17 is
            # italy's maritime pine by this instrument (r9, stock_banding.json)
            assert band["band_strength"] <= 0.17, (
                f"{species['key']}: banding energy {band['band_strength']:.4f} at "
                f"{band['period_m']:.2f} m"
            )


def test_no_shipped_model_detail_is_an_open_shell(shapes: dict) -> None:
    """A photogrammetry shell seen from behind silhouettes as ribbons (D7).

    f_cliff_outcrop_a's top LOD shipped in r2 with 535 boundary edges and 90.6 m of open
    perimeter on a 21 m span -- and the camera at design 8's crest eye stands 10.8 m from one
    and looks straight through it.  blender_forest.close_shell caps every loop at import and
    seal_to re-caps after each decimation; what is left is measured HERE, on the shipped file.
    """
    for key, row in shapes["species"].items():
        species = fs.SPECIES_BY_KEY[key]
        if species["build"] != "model":
            continue
        for pixel, _ in species["details"]:
            coordinates, prims = _detail_geometry(
                LEVEL_ROOT / row["relative"], bf.detail_node(bf.dae_stem(key), pixel)
            )
            if not coordinates:
                continue
            edges: collections.Counter = collections.Counter()
            for _, idx in prims:
                for i in range(0, len(idx) - 2, 3):
                    tri = idx[i : i + 3]
                    for j in range(3):
                        a, b = tri[j], tri[(j + 1) % 3]
                        edges[(a, b) if a <= b else (b, a)] += 1
            span = max(max(coordinates[axis::3]) - min(coordinates[axis::3]) for axis in range(3))
            perimeter = sum(
                math.dist(coordinates[3 * a : 3 * a + 3], coordinates[3 * b : 3 * b + 3])
                for (a, b), n in edges.items()
                if n == 1
            )
            assert perimeter / max(span, 1e-6) <= 0.5, (
                f"{key} _a{pixel}: {perimeter:.1f} m of open boundary on a {span:.1f} m shape"
            )


def test_the_size_aware_camera_clearance_holds() -> None:
    """No solid model stands inside its own footprint of a truth-frame eye (D7)."""
    proof = json.loads(
        (AUTHORING / f"{fs.LEVEL_ID}_forest_keepout.json").read_text(encoding="utf-8")
    )
    rule = proof["rule_camera_clearance_size_aware"]
    assert rule["violations"] == 0
    assert rule["k"] == fs.CAMERA_CLEAR_HEIGHT_K
    assert rule["min_margin_m"] > 0.0
    assert rule["instances_with_a_radius_over_6m"] > 0, "the rule has a population"
    # f_cliff_outcrop_a stood 10.8 m from the crest eye in r2: height/distance 1.94
    assert rule["worst_solid_height_over_distance"] <= 1.0 / fs.CAMERA_CLEAR_HEIGHT_K + 1e-6


# ============================================================= r3: the cut-out edge (D6 and M2)
def test_no_material_can_take_a_generated_mask() -> None:
    """Every cut-out material names its sources, and the generated-mask cook is DELETED."""
    from examples.hot_potato_arena.level import forest_textures as ft

    for material in fs.MATERIALS:
        if material.get("kind", "rock") in ("tile", "rock"):
            continue
        assert material.get("sources"), f"{material['key']} has no cut-out sources"
    for gone in ("cook_atlas", "MASK_FUNCTIONS", "leaf_mask", "blade_mask", "sprig_mask"):
        assert not hasattr(ft, gone), f"forest_textures still carries {gone}"


def test_no_cut_out_atlas_ships_a_black_matting_halo(textures: dict) -> None:
    """The albedo under the alpha is foliage, not the source photograph's backdrop (D6).

    Critic r2, per texel over the shipped maps at each material's own alphaRef: gc_meadow
    17.06 % near-black, gc_alpine 20.98 %, gc_stubble 21.12 %, gc_reeds 11.98 %, with 87-94 %
    of it within two texels of the cut edge -- a black rim on every grass blade.  The two
    covers cut from fern and needle sources were 0.79 % and 0.35 %.  gc_litter separately
    shipped a 10,721-texel photographic calibration block, which is the last assertion.
    """
    import numpy as np
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    from examples.hot_potato_arena.level import forest_textures as ft

    checked = 0
    for material in fs.MATERIALS:
        if material.get("kind", "rock") in ("tile", "rock"):
            continue
        key, reference = material["key"], material["alphaRef"]
        with Image.open(LEVEL_ROOT / fs.texture_relative(key, "base")) as image:
            base = np.asarray(image.convert("RGB")).astype(np.float64) / 255.0
        with Image.open(LEVEL_ROOT / fs.texture_relative(key, "opacity")) as image:
            opacity = np.asarray(image.convert("L"))
        mask = opacity >= reference
        assert mask.any(), f"{key}: nothing is opaque at alphaRef {reference}"
        high, low = base.max(axis=2), base.min(axis=2)
        saturation = np.where(high > 0, (high - low) / np.maximum(high, 1e-9), 0.0)
        near_black = float((mask & (high < 0.10)).sum()) / float(mask.sum())
        achromatic = mask & (saturation < 0.18) & (high > 0.45)
        share = float(achromatic.sum()) / float(mask.sum())
        assert near_black <= 0.08, f"{key}: {near_black:.1%} of its opaque area is near-black"
        assert share <= 0.03, f"{key}: {share:.1%} of its opaque area is bright and colourless"
        labels, count = ft._label(achromatic)
        if count:
            biggest = int(np.bincount(labels.ravel())[1:].max())
            assert biggest < 4000, f"{key}: a {biggest}-texel achromatic block ships in it"
        checked += 1
    assert checked == 17, "every cut-out material (QB-13's 22 counts the 5 opaque bark tiles)"
    # r11 (B10-1): + the branch material's five 512 maps
    assert len(textures["files"]) == 151


# ================================================ r4: the baked billboard, and the shell caps
def _billboarded_species() -> list[dict]:
    return [s for s in fs.SPECIES if s["bb"]]


def _imposters_or_skip() -> dict:
    """The bake manifest -- required the moment an atlas ships, absent only before the bake."""
    if not forest_build.imposter_members(LEVEL_ROOT):
        pytest.skip("no imposter atlas in the tree yet; run the live re-bake boot")
    assert forest_build.IMPOSTERS_MANIFEST.is_file(), (
        "the tree ships imposter atlases with no bake manifest: re-run the live re-bake boot "
        "(HOT_POTATO_FOREST_REBAKE=1) so what each atlas is a bake OF is on the record"
    )
    return forest_build.imposters_manifest()


def test_every_shipped_imposter_was_baked_from_the_shipped_dae() -> None:
    """No atlas may be older than the geometry it depicts (critic r3 D8).

    All 54 shipped ``*.dae.imposter.dds`` were byte-identical across r1, r2 AND r3 while the
    round rebuilt every conifer twice -- tripled the top-LOD foliage, rebuilt the whorl
    architecture, moved the canopy start and rebuilt the whole LOD ladder.  The forest past
    262 m, which design 4.3 says is the whole forest as seen from the arena, was still drawn
    with r1's billboard.  Nothing could catch it because the bake recorded nothing about what
    it was a bake OF; ``authoring/<level>_forest_imposters.json`` now does, and this is the
    gate that reads it.
    """
    import hashlib

    manifest = _imposters_or_skip()
    assert manifest["bb_property"] == fs.BB_PROPERTY, (
        "the atlases were baked under a different BB:: recipe than the shapes now declare"
    )
    atlases = manifest["atlases"]
    wanted = {
        fs.species_dae_relative(species) + suffix
        for species in _billboarded_species()
        for suffix in (".imposter.dds", ".imposter_normals.dds")
    }
    assert set(atlases) == wanted, sorted(wanted.symmetric_difference(atlases))[:4]
    stale, missing = [], []
    for relative, row in sorted(atlases.items()):
        shipped = LEVEL_ROOT / relative
        if not shipped.is_file():
            missing.append(relative)
            continue
        if hashlib.sha256(shipped.read_bytes()).hexdigest() != row["sha256"]:
            stale.append(f"{relative}: the shipped atlas is not the one the manifest records")
            continue
        dae = LEVEL_ROOT / row["dae"]
        assert dae.is_file(), row["dae"]
        if hashlib.sha256(dae.read_bytes()).hexdigest() != row["dae_sha256"]:
            stale.append(f"{relative}: baked from a DIFFERENT {row['dae']} than the one shipped")
    assert not missing, missing[:4]
    assert not stale, stale[:4]


#: The billboard's silhouette may not be thinner than this share of its own tree's.  r1's
#: bake, still shipping in r3, read 0.126 bbox fill on `f_pine_tall_a` against 0.260 for the
#: r3 mesh at the same texel height -- 0.48, and visibly a stipple where the mesh is a tree.
IMPOSTER_FILL_OF_MESH_MIN = 0.70


def _shape_silhouette(species: dict, pixel: int, rows: int):
    """The WHOLE shape's side-view opacity at `rows` texels tall, TRIANGLE-rasterised.

    `_side_view` (critic r2's instrument, kept byte-for-byte for the crown gates) fills each
    triangle's BOUNDING BOX, which is honest enough for a scatter of small cards and wildly
    generous for a solid log.  The imposter comparison needs the real silhouette, so this
    rasterises the triangle itself, at exactly the texel height the atlas drew the shape at --
    which is also where a card's own alpha coverage decides whether it survives the alpha test.
    """
    import numpy as np

    path = LEVEL_ROOT / fs.species_dae_relative(species)
    coordinates, prims = _detail_geometry(path, bf.detail_node(bf.dae_stem(species["key"]), pixel))
    by_material = {}
    for _slot, key in species["materials"]:
        material = next((m for m in fs.MATERIALS if m["key"] == key), None)
        opaque = material is None or "alphaRef" not in material
        by_material[f"{fs.material_name(key)}-material"] = 1.0 if opaque else foliage_coverage(key)
    tris = [
        (idx[i], idx[i + 1], idx[i + 2], by_material.get(symbol, 1.0))
        for symbol, idx in prims
        for i in range(0, len(idx) - 2, 3)
    ]
    assert tris, f"{species['key']} _a{pixel}: no geometry"
    xs = [coordinates[3 * v] for a, b, c, _ in tris for v in (a, b, c)]
    zs = [coordinates[3 * v + 2] for a, b, c, _ in tris for v in (a, b, c)]
    x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
    scale = (rows - 1) / max(z1 - z0, 1e-6)
    nz = rows
    nx = max(4, int((x1 - x0) * scale) + 2)
    keep = np.ones((nz, nx))
    grid_x = np.arange(nx)[None, :]
    grid_z = np.arange(nz)[:, None]
    for a, b, c, coverage in tris:
        px = [(coordinates[3 * v] - x0) * scale for v in (a, b, c)]
        pz = [(z1 - coordinates[3 * v + 2]) * scale for v in (a, b, c)]
        lo_x, hi_x = int(max(0, math.floor(min(px)))), int(min(nx - 1, math.ceil(max(px))))
        lo_z, hi_z = int(max(0, math.floor(min(pz)))), int(min(nz - 1, math.ceil(max(pz))))
        if hi_x < lo_x or hi_z < lo_z:
            continue
        gx = grid_x[:, lo_x : hi_x + 1] + 0.5
        gz = grid_z[lo_z : hi_z + 1] + 0.5
        d = (px[1] - px[0]) * (pz[2] - pz[0]) - (px[2] - px[0]) * (pz[1] - pz[0])
        if abs(d) < 1e-9:
            keep[lo_z : hi_z + 1, lo_x : hi_x + 1] *= 1.0 - coverage
            continue
        u = ((gx - px[0]) * (pz[2] - pz[0]) - (gz - pz[0]) * (px[2] - px[0])) / d
        v = ((gz - pz[0]) * (px[1] - px[0]) - (gx - px[0]) * (pz[1] - pz[0])) / d
        inside = (u >= 0) & (v >= 0) & (u + v <= 1)
        block = keep[lo_z : hi_z + 1, lo_x : hi_x + 1]
        keep[lo_z : hi_z + 1, lo_x : hi_x + 1] = np.where(inside, block * (1.0 - coverage), block)
    return 1.0 - keep


def _bbox_fill(opacity) -> float:
    """Bbox fill of a rendered silhouette -- the atlas's own measure, on the mesh."""
    import numpy as np

    solid = opacity >= 0.5
    if not solid.any():
        return 0.0
    ys, xs = np.nonzero(solid)
    box = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
    return float(solid.sum()) / float(box)


def test_every_shipped_imposter_looks_like_its_own_tree() -> None:
    """View cells used, and bbox fill against the shape's OWN silhouette (critic r3 D8).

    Nothing in three rounds had looked at an imposter.  Measured on the 128 px cell grid the
    atlas is packed into: r1's bake filled 0.054-0.138 of its bounding box where five stock
    maps fill 0.40-0.66 and where the r3 MESH it stands in for fills 0.23-0.35, and it used
    4-6 of its 8 cells against stock's 32-64 of 32-64.
    """
    manifest = _imposters_or_skip()
    thin, blind, checked = [], [], 0
    for species in _billboarded_species():
        relative = fs.species_dae_relative(species) + ".imposter.dds"
        reading = forest_build.imposter_reading((LEVEL_ROOT / relative).read_bytes())
        assert reading == manifest["atlases"][relative]["reading"], (
            f"{species['key']}: the atlas no longer reads as the manifest recorded it"
        )
        if reading["cells_touched"] < fs.BB_VIEWS:
            blind.append(
                f"{species['key']}: {reading['cells_touched']} of {reading['cells']} view "
                f"cells rendered anything, for {fs.BB_VIEWS} declared views"
            )
        # The fill comparison is made where the stipple failure mode lives: shapes whose
        # silhouette is alpha-tested CARDS.  For the 36 CC0 model shapes an orthographic
        # projection of the mesh is not a fair reference (it ignores self-occlusion and the
        # imposter's own view directions), so those are gated on view coverage alone and
        # their fills are recorded in the evidence instead.
        if species["build"] not in ("conifer", "snag", "card"):
            continue
        top = species["details"][0][0]
        rows = max(8, reading["subject_height_px_max"])
        mesh = _bbox_fill(_shape_silhouette(species, top, rows))
        if mesh > 0 and reading["bbox_fill_max"] < IMPOSTER_FILL_OF_MESH_MIN * mesh:
            thin.append(
                f"{species['key']}: the billboard fills {reading['bbox_fill_max']:.3f} of its "
                f"bbox where its own _a{top} mesh fills {mesh:.3f} at the same texel height"
            )
        checked += 1
    assert not blind, blind[:4]
    assert not thin, thin[:4]
    assert checked == 25, "18 generated conifers and snags + 7 card shapes"


#: A shipped detail's largest face, as a multiple of its own median face.  r3 closed the
#: cliff shells with a flat n-gon fan and `f_cliff_outcrop_a`'s top LOD came out at 3,025x
#: (106.15 m2 against a 0.035 m2 median), 40.2 % of its area in faces over 1 m2 and 39.9 % of
#: the near rock the crest frame shows.  A decimated photogrammetry rock that was never
#: capped sits at 11-35x.
CAP_LARGEST_OVER_MEDIAN_MAX = 120.0
#: ...and this much of its area may sit in faces above 16x its own median.
CAP_COARSE_AREA_SHARE_MAX = 0.30
#: r5 (critic r4 B3): the two numbers above score FACES, and a cap does not have to be one
#: face.  r4 closed `f_crag`'s non-manifold back with `bpy.ops.mesh.fill`, which triangulated
#: a 35 x 7 x 21 m membrane across it; the second decimation pass in `seal_to` collapsed that
#: into 142 slivers holding 340.1 m2 of ONE PLANE on the 150 px detail (r2 32.2, r3 38.9) --
#: and the gate scored it 11.6x largest-over-median and 0.0 % above 16x, a comfortable pass.
#: So the third clause is the plane itself: the largest set of triangles whose normals agree
#: within `PLANE_TOLERANCE_DEG` and whose centres sit within `PLANE_TOLERANCE_M` of one plane.
#: MEASURED over all 77 model details in four cuts.  The worst plane AREA and the worst plane
#: SHARE are DIFFERENT DETAILS in every one of the four, so the pair below is two readings and
#: not one shape's (CORRECTED IN r7, critic r6 M34; b3/r5/planes.json, §R5.3's table):
#:     cut  worst plane area              worst plane share
#:     r2    32.2 m2  f_crag _a150          22.5 %  f_pebble_cluster _a150
#:     r3   120.8 m2  f_cliff_outcrop_a _a100   37.1 %  f_stump_a _a400
#:     r4   340.1 m2  f_crag _a150          30.2 %  f_windthrow_roots _a200
#:     r5    71.4 m2  f_crag _a150          20.5 %  f_windthrow_roots _a200
#: The
#: ceiling is under the 106.15 m2 cap D9 was originally about, so r3 fails on the shape D9
#: named as well as on the one r4 introduced.
PLANE_TOLERANCE_DEG = 4.0
PLANE_TOLERANCE_M = 0.25
CAP_PLANE_AREA_MAX_M2 = 100.0
CAP_PLANE_AREA_SHARE_MAX = 0.30


def _largest_plane(coordinates: list[float], prims) -> tuple[float, int, float, float]:
    """(plane m2, its triangles, plane share of the surface, surface m2) of one detail.

    The plane is grown from every face bigger than the detail's own median, which is where a
    cap always is: a cap is coarse relative to what it replaced, whether it is one n-gon, a
    beauty-fill fan of slivers, or a decimated membrane.
    """
    import numpy as np

    points = np.asarray(coordinates, dtype=np.float64).reshape(-1, 3)
    index = np.asarray(
        [idx[i : i + 3] for _symbol, idx in prims for i in range(0, len(idx) - 2, 3)],
        dtype=np.int64,
    )
    triangles = points[index]
    raw = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    area = 0.5 * np.linalg.norm(raw, axis=1)
    surface = float(area.sum()) or 1e-9
    unit = raw / np.maximum(np.linalg.norm(raw, axis=1, keepdims=True), 1e-12)
    centre = triangles.mean(axis=1)
    median = float(np.median(area)) or 1e-12
    cosine = math.cos(math.radians(PLANE_TOLERANCE_DEG))
    best, count = 0.0, 0
    for seed in np.argsort(-area, kind="stable")[:120]:
        if area[seed] <= median:
            continue
        normal = unit[seed]
        mask = (np.abs(unit @ normal) > cosine) & (
            np.abs(centre @ normal - normal @ centre[seed]) < PLANE_TOLERANCE_M
        )
        total = float(area[mask].sum())
        if total > best:
            best, count = total, int(mask.sum())
    return best, count, best / surface, surface


def test_no_shipped_model_detail_is_capped_with_a_plate(shapes: dict) -> None:
    """The open perimeter may not be paid for with a flat plate (critic r3 D9, r4 B3).

    r3's `close_shell` hung one n-gon fan on each boundary loop.  It closed the shell and it
    put 6,608 m2 of 16,545 m2 -- 39.9 % of the near rock surface the crest frame shows,
    largest visible face 140.4 m2 -- into smeared flat caps, against 4.2 % and 7.49 m2 in r2.
    The open-perimeter gate could not see it because the triangle COUNT barely moved: the
    caps replaced decimated detail.  This is the gate on the shape of that geometry.

    Three clauses, because a plate has three disguises: ONE big face (r3), a FAN of slivers
    over one plane (r4's `mesh.fill` membrane -- invisible to the first two clauses, which is
    why the third exists), and a large share of the surface in coarse faces.
    """
    worst_ratio, worst_share, worst_plane, worst_plane_share = 0.0, 0.0, 0.0, 0.0
    offenders, checked = [], 0
    for key, row in shapes["species"].items():
        species = fs.SPECIES_BY_KEY[key]
        if species["build"] != "model":
            continue
        for pixel, _ in species["details"]:
            coordinates, prims = _detail_geometry(
                LEVEL_ROOT / row["relative"], bf.detail_node(bf.dae_stem(key), pixel)
            )
            if not coordinates:
                continue
            areas = sorted(
                _triangle_area(coordinates, idx[i], idx[i + 1], idx[i + 2])
                for _symbol, idx in prims
                for i in range(0, len(idx) - 2, 3)
            )
            if len(areas) < 8:
                continue
            checked += 1
            median = areas[len(areas) // 2] or 1e-9
            total = sum(areas) or 1e-9
            ratio = areas[-1] / median
            share = sum(a for a in areas if a > 16 * median) / total
            plane, plane_tris, plane_share, _surface = _largest_plane(coordinates, prims)
            worst_ratio, worst_share = max(worst_ratio, ratio), max(worst_share, share)
            worst_plane = max(worst_plane, plane)
            worst_plane_share = max(worst_plane_share, plane_share)
            if ratio > CAP_LARGEST_OVER_MEDIAN_MAX or share > CAP_COARSE_AREA_SHARE_MAX:
                offenders.append(
                    f"{key} _a{pixel}: largest face {areas[-1]:.2f} m2 = {ratio:.0f}x its own "
                    f"median, {share:.1%} of its area above 16x the median"
                )
            if plane > CAP_PLANE_AREA_MAX_M2 or plane_share > CAP_PLANE_AREA_SHARE_MAX:
                offenders.append(
                    f"{key} _a{pixel}: {plane:.2f} m2 of it -- {plane_share:.1%}, in "
                    f"{plane_tris} triangles -- lies in ONE plane; that is a cap, not a rock"
                )
    assert not offenders, offenders[:4]
    assert checked == 77, "every model detail"
    assert worst_ratio > 0 and worst_share > 0 and worst_plane > 0 and worst_plane_share > 0


def test_every_alpha_test_reference_survives_its_own_mip_chain(materials: dict) -> None:
    """A cut-out atlas must keep its coverage at the mip a distant card samples (r4).

    An alpha-tested texture is opaque only while the mip it is sampled at still has texels
    above `alphaRef`, and a mip texel is the AVERAGE alpha of its block.  MEASURED on the
    shipped `f_pine_twig_a` cell at r3's alphaRef 110: coverage holds at 0.25-0.28 from 512 px
    down to 8 px and then collapses to 0.062 at 4 px and 0.000 at 2 px -- because 0.24 x 255 =
    61 is under 110.  A 28 m pine baked into a 128 px imposter cell draws its 0.60 m cards at
    2.7 px, which is exactly that mip, so the billboard came out a string of specks.

    READS THE TREE, not the module (critic r4 B4-i).  The r4 cut of this gate took `alphaRef`
    from `fs.MATERIALS`, so with only `LEVEL_ROOT` re-pointed it PASSED on the r3 tree -- it
    could only ever fail on r3's *code*, which is exactly the confusion critic r3 charged the
    r3 report with.  The reference now comes out of the shipped `*.materials.json` beside the
    map, and the module constant is checked against it separately, so the gate fails on ten of
    the seventeen cut-outs when it is pointed at the r3 tree.

    The comparison is against the **4-pixel mip** -- ten halvings from a 4,096 px atlas, seven
    from a 512 px cell -- not "four mips down"; that is the size a card 2.7 px across samples.
    """
    import numpy as np
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    checked, thin = 0, []
    for material in fs.MATERIALS:
        if "alphaRef" not in material or material.get("kind", "rock") in ("tile", "rock"):
            continue
        name = fs.material_name(material["key"])
        shipped = materials[name]
        reference = shipped["alphaRef"]
        assert shipped.get("alphaTest") is True, f"{name}: alphaRef without alphaTest"
        assert reference == material["alphaRef"], (
            f"{name}: the tree ships alphaRef {reference}, forest_spec says {material['alphaRef']}"
        )
        path = LEVEL_ROOT / fs.texture_relative(material["key"], "opacity")
        with Image.open(path) as image:
            atlas = np.asarray(image.convert("L")).astype(np.float32)
        columns, rows = material.get("grid") or (1, 1)
        current = atlas[: atlas.shape[0] // rows, : atlas.shape[1] // columns]
        mips = {}
        while True:
            mips[current.shape[1]] = current
            if current.shape[0] < 2 or current.shape[1] < 2:
                break
            high, wide = current.shape[0] // 2 * 2, current.shape[1] // 2 * 2
            current = current[:high, :wide].reshape(high // 2, 2, wide // 2, 2).mean(axis=(1, 3))
        full, deep = max(mips), min(s for s in mips if s >= 4)
        near = float((mips[full] >= reference).mean())
        far = float((mips[deep] >= reference).mean())
        assert near > 0.02, f"{name}: nothing is opaque at alphaRef {reference}"
        if far < 0.8 * near:
            thin.append(
                f"{name}: alphaRef {reference} keeps {near:.3f} of the atlas at {full} px and "
                f"only {far:.3f} at the {deep} px mip -- a card drawn that small dissolves"
            )
        checked += 1
    assert not thin, thin[:4]
    assert checked == 17, "every cut-out material"


# ============================================ r9: the rock gate (DEV-27, the user requirement)
#: The bars adopted from critic B2 pass 5 (level_facts 2026-09-07) and B4 r4's G-B4-17: the
#: five solid hearth stones read 0.52-0.89 on the volume ratio, so 0.5; the car-band phantom
#: gap is what a player meets, so it is bounded in absolute metres.
ROCK_GATE_BARS = {"ratio_min": 0.5, "parity_max": 0.30, "p50": 0.06, "p90": 0.12, "max": 0.25}


def test_every_forest_rock_is_a_solid_body_and_its_collider_is_the_rock(shapes: dict) -> None:
    """The user's r9 requirement, as a gate that cannot regress (DEV-27).

    Every shipped MODEL shape with a Colmesh -- the 20 rocks and the 7 solid deadwood pieces --
    must be SOLID at every detail and in its Colmesh by ``mesh_audit`` (closed, manifold,
    outward, with a bottom), and its Colmesh must be the rock the player sees by
    ``collider_probe``: visual / Colmesh volume >= 0.5 at every LOD, LOD parity spread <= 0.30,
    car-band phantom gap p50 / p90 / max <= 0.06 / 0.12 / 0.25 m.  r8 read -0.17 / 0.05 /
    0.06 on cliff_outcrop_a with a 1.54 m p90 gap and 2-4 open edges at every LOD of every
    mossy rock (``b3/r9/rock_probe_r8.json``, ``mesh_audit_r8.json``).  Reads the shipped DAE.
    """
    from examples.hot_potato_arena.level import collider_probe, mesh_audit

    problems, checked = [], 0
    for key, row in shapes["species"].items():
        species = fs.SPECIES_BY_KEY[key]
        # r11 (critic N-2): the scope is "a closed body the car can hit", not "built by the
        # model path".  `snag_a` and `snag_b` are closed, manifold, SOLID and carry a Colmesh,
        # and they held 22 of the 25 instances the critic still found rooted inside a body --
        # yet neither this gate nor the husk gate nor the keep-out list had ever looked at
        # them.  `plant_forest.is_keep_out_body` is the one definition all three now share.
        if not pf.is_keep_out_body(species) or not species["colmesh"]:
            continue
        payload = (LEVEL_ROOT / row["relative"]).read_bytes()
        audit = mesh_audit.audit_dae(Path(row["relative"]).name, payload)
        if not audit["all_solid"]:
            problems.append(f"{key}: not solid at {audit['open']}")
        if species["family"] == "rock":
            # a boulder is a ball: chi 2 - 2g, and a handle is a tunnel the decimator cannot
            # remove (the first voxel cut gave lichen_boulder genus 11, mossy_rock_b genus 6).
            # A row may DECLARE a genus it has MEASURED as real, closed, manifold topology
            # (only `mossy_rock_c`, chi -2 at every detail and in its Colmesh); anything else
            # is a defect.  r9 justified that declaration by arguing the handles were arches
            # wider than 0.8 m -- a logic error the critic caught (N-2): the closing only adds
            # material, and no direction of 80 shows a hole above 7 cm.  The declaration
            # stands on the measured topology alone; see the row's own comment.
            allowed = 2 - 2 * int(species.get("solid_genus", 0))
            handles = {
                g.rsplit("_", 1)[-1]: [(2 - s["chi"]) // 2 for s in r["shells"]]
                for g, r in audit["meshes"].items()
                if any(s["chi"] not in (2, allowed) for s in r["shells"])
            }
            if handles:
                problems.append(f"{key}: handles (genus by shell) {handles}")
        probe = collider_probe.probe_dae(Path(row["relative"]).name, payload)
        assert probe["has_colmesh"], key
        ratios = [d["volume_ratio_visual_over_colmesh"] for d in probe["details"].values()]
        if min(ratios) < ROCK_GATE_BARS["ratio_min"]:
            problems.append(f"{key}: visual/Colmesh volume {min(ratios):.2f}")
        if probe["lod_parity_ratio_spread"] > ROCK_GATE_BARS["parity_max"]:
            problems.append(f"{key}: LOD parity spread {probe['lod_parity_ratio_spread']:.2f}")
        band = probe["details"][probe["finest_detail"]]["car_band"]
        for stat in ("p50", "p90", "max"):
            value = band[f"phantom_{stat}_m"] or 0.0
            if value > ROCK_GATE_BARS[stat]:
                problems.append(f"{key}: car-band phantom gap {stat} {value:.3f} m")
        checked += 1
    assert checked == 29, "20 rocks + 7 solid deadwood pieces + 2 snags carry a Colmesh"
    assert not problems, problems[:8]


# ---------------------------------------------------------- r10: the two gates critic r9 asked for
#: every CC0 asset any shipped cut-out atlas is allowed to cut a stamp from.  It is the
#: `cc0` of each material plus every `cc0` named in its `sources` / `cell_sources`, and it is
#: written out here so a source that appears in an atlas without appearing in the design's
#: ledger fails by NAME, not only by picture.
DECLARED_ATLAS_SOURCES = {
    "bark_debris_01",
    "burned_ground_01",
    "dry_branches_medium_01",
    "fern_02",
    "fir_sapling_medium",
    "fir_tree_01",
    "forest_leaves_04",
    "grass_medium_01",
    "grass_medium_02",
    "leafy_grass",
    "pine_sapling_medium",
    "pine_tree_01",
    "shrub_01",
    "shrub_02",
    "shrub_03",
    "shrub_04",
    "sparse_grass",
}


def test_no_shipped_atlas_cell_carries_foreign_geometry() -> None:
    """There are no letters on the forest floor -- and nothing else that is not foliage.

    r9 shipped a pale grey bevelled shape on `gc_litter` cell (0,1) that reads as a capital
    "A", with more glyph-like fragments beside it, drawn by three GroundCover layers at
    probability 0.92 out to 50 m across the whole forest (critic B9-2,
    `b3/critic_r9/atlases/LITTER_r0c1.png`).  It was not text and there is no bake scene:
    these atlases are stamp composites, and the shapes were `dry_branches_medium_01`'s flat
    scan-backdrop facets, desaturated to grey by the litter grade.

    Foreign geometry is defined here as a connected region that is BOTH flat-shaded AND
    straight-edged -- `forest_textures.audit_cells`.  Both halves are load-bearing: a broad
    autumn leaf is flat but its outline is a leaf (measured straight-share 0.05-0.21), a stem
    is straight but not flat.  Run over the r9 SHIPPED tree this fails 10 of the 17 atlases
    (`gc_litter` 795 texels, `f_shrub_leaf_02` 10,326, `gc_stubble` 1,652), so it reproduces
    the defect a person found by eye.  The second clause is provenance: every source any atlas
    cuts from has to be on the declared list.
    """
    from examples.hot_potato_arena.level import forest_textures as ft

    report = ft.audit_tree(LEVEL_ROOT)
    cap = report["cap"]
    assert len(report["materials"]) == 17, "17 cut-out atlases ship"
    for key, sources in sorted(report["sources"].items()):
        unknown = set(sources) - DECLARED_ATLAS_SOURCES
        assert not unknown, f"{key} cuts from undeclared source(s) {sorted(unknown)}"
    problems = []
    for material in report["materials"]:
        if material["worst_foreign_texels"] > cap:
            worst = max(material["cells"], key=lambda c: c["foreign_texels"])
            problems.append(
                f"{material['key']} cell {worst['cell']}: {worst['foreign_texels']} texels "
                f"flat and straight-edged (flat {worst['flat_texels']}, "
                f"straightness {worst['straight_share']}) -- cap {cap}"
            )
    assert not problems, problems


def test_no_instance_is_rooted_inside_a_solid_body() -> None:
    """26.2 % of the r9 forest grew out of solid rock.  Re-measured on the shipped rows.

    r9 filled `cliff_outcrop_a/b` and `crag` into closed solids and nobody re-ran the planter,
    so 40,452 of 154,686 instances -- 1,251 full-size firs and pines, 1,880 saplings, 1,938
    shrubs and ferns, 1,093 snags and ~33 k of rock inside rock -- ended up rooted inside a
    rock body with collision (critic B9-1, `b3/critic_r9/interpenetration.json`).  Every
    keep-out the planter had was a 2-D field; a rock is a volume.

    This does not trust the plant manifest: it rebuilds the occupancy of all 29 solid species
    from the DAEs in the tree and re-tests every shipped `forest4` row, with the critic's own
    convention (the root point lifted 0.3 m, so litter under an overhang does not count).
    """
    from examples.hot_potato_arena.level import plant_forest as pf

    shapes = pf.solid_shapes(LEVEL_ROOT)
    # r11 (critic N-2): + `snag_a` and `snag_b`, which held 22 of the 25 residual hits
    assert len(shapes) == 29, "20 rocks + 7 solid deadwood pieces + 2 snags are keep-out volumes"
    rows: dict[str, list[dict]] = {}
    points: list[tuple[float, float, float]] = []
    owners: list[tuple[str, int]] = []
    for path in sorted((LEVEL_ROOT / "forest").glob("*.forest4.json")):
        name = path.stem.replace(".forest4", "")
        parsed = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
        rows[name] = parsed
        for order, row in enumerate(parsed):
            points.append((row["pos"][0], row["pos"][1], row["pos"][2] + pf.SOLID_LIFT_M))
            owners.append((name, order))

    class _Field(pf.SolidField):
        def __init__(self, rows: dict, shapes: dict) -> None:
            import numpy as np

            self.bodies, self.buckets = [], {}
            for name, shape in shapes.items():
                lo, span = shape["lo"], shape["span"]
                corners = np.array(
                    [
                        [lo[0] + span[0] * i, lo[1] + span[1] * j, lo[2] + span[2] * k]
                        for i in (0, 1)
                        for j in (0, 1)
                        for k in (0, 1)
                    ]
                )
                for order, row in enumerate(rows.get(name, ())):
                    rotation = np.asarray(row["rotationMatrix"], dtype=float).reshape(3, 3)
                    position = np.asarray(row["pos"], dtype=float)
                    scale = float(row["scale"])
                    world = (corners * scale) @ rotation + position
                    self.bodies.append(
                        {
                            "name": name,
                            "index": order,
                            "position": position,
                            "rotation": rotation,
                            "scale": scale,
                            "shape": shape,
                            "min": world.min(axis=0),
                            "max": world.max(axis=0),
                        }
                    )
            for tag, body in enumerate(self.bodies):
                for cx in range(
                    int(body["min"][0] // pf.SOLID_CELL_M),
                    int(body["max"][0] // pf.SOLID_CELL_M) + 1,
                ):
                    for cy in range(
                        int(body["min"][1] // pf.SOLID_CELL_M),
                        int(body["max"][1] // pf.SOLID_CELL_M) + 1,
                    ):
                        self.buckets.setdefault((cx, cy), []).append(tag)

    import numpy as np

    field = _Field(rows, shapes)
    hits, _hosts = field.inside(np.asarray(points, dtype=float), owners)
    inside = int(hits.sum())
    if inside:
        worst = collections.Counter(owners[i][0] for i in np.nonzero(hits)[0].tolist())
        raise AssertionError(
            f"{inside} of {len(points)} instances are rooted inside a solid body: "
            f"{worst.most_common(8)}"
        )
    proof = json.loads(forest_build.KEEPOUT_PROOF.read_text("utf-8"))
    rule = proof["rule_no_instance_inside_a_solid_body"]
    assert rule, "the plant ran without a level root, so the volume keep-out never ran"
    assert rule["rooted_inside_after"] == 0, rule
    # r11 (critic N-2): 27 + `snag_a` + `snag_b`
    assert rule["solid_species"] == 29, rule


# --- the husk gate (r10) --------------------------------------------------------------------
# `level_facts` 2026-09-09, from the user's own video ("the boulders are just a single flake"),
# as re-calibrated by critic B2 r6 against 13 stock BeamNG rocks and 6 hearth stones:
#
#     HARD FAIL   solidity < 0.54                   (below EVERY stock rock)
#     ALSO FAIL   solidity < 0.67  AND  fill < 0.28
#
# solidity = V / V(hull) is the HUSK statistic (any convex body reads 1.000); fill = V / (e1 e2
# e3) on the PCA axes is a SHAPE statistic (a sphere caps at 0.523), which is why the first bar,
# `fill >= 0.30 AND solidity >= 0.65`, failed 4 of the 13 stock rocks it was calibrated on.
HUSK_HARD_SOLIDITY = 0.54
HUSK_SOFT_SOLIDITY = 0.67
HUSK_SOFT_FILL = 0.28
#: DEADWOOD is a different class and the rock bars are a category error on it: a pile of loose
#: sticks has a convex hull the size of the pile.  Its reference is the CC0 scan it is cut from,
#: measured through this same code path, and the shipped manifest carries that reading
#: (`import_part.source_fill` / `source_solidity`).  Everything on the import route -- island
#: weld, shell seal, voxel remesh -- only ever FILLS, so "at least as solid as the scan" is a
#: real bar: five of the shapes clear it by 0.15-0.31 of solidity, and `windthrow_roots` only
#: reached it after its top detail went 1,200 -> 3,000 triangles.
HUSK_SOURCE_TOLERANCE = 0.02


def _principal_extents(positions: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """e1 >= e2 >= e3 of the vertex cloud on its OWN principal axes.

    An axis-aligned bounding box cannot see a blade lying diagonally, which is the whole point
    of the statistic.  Pure standard library: the 3x3 covariance's eigenvectors by Jacobi
    rotation (three symmetric sweeps converge to machine precision on a 3x3).
    """

    n = len(positions)
    mean = [sum(p[i] for p in positions) / n for i in range(3)]
    cov = [[0.0] * 3 for _ in range(3)]
    for p in positions:
        d = (p[0] - mean[0], p[1] - mean[1], p[2] - mean[2])
        for i in range(3):
            for j in range(3):
                cov[i][j] += d[i] * d[j]
    axes = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    for _ in range(24):
        p, q = max(
            ((i, j) for i in range(3) for j in range(i + 1, 3)),
            key=lambda ij: abs(cov[ij[0]][ij[1]]),
        )
        if abs(cov[p][q]) < 1e-18:
            break
        theta = 0.5 * math.atan2(2.0 * cov[p][q], cov[q][q] - cov[p][p])
        c, s = math.cos(theta), math.sin(theta)
        for k in range(3):
            kp, kq = cov[k][p], cov[k][q]
            cov[k][p], cov[k][q] = c * kp - s * kq, s * kp + c * kq
        for k in range(3):
            pk, qk = cov[p][k], cov[q][k]
            cov[p][k], cov[q][k] = c * pk - s * qk, s * pk + c * qk
        for k in range(3):
            kp, kq = axes[k][p], axes[k][q]
            axes[k][p], axes[k][q] = c * kp - s * kq, s * kp + c * kq
    spans = []
    for axis in range(3):
        direction = (axes[0][axis], axes[1][axis], axes[2][axis])
        values = [
            p[0] * direction[0] + p[1] * direction[1] + p[2] * direction[2] for p in positions
        ]
        spans.append(max(values) - min(values))
    spans.sort(reverse=True)
    return spans[0], spans[1], spans[2]


def husk_reading(positions: list, tris: list) -> dict:
    """flatness / blade / fill / solidity of one closed mesh, in its own frame."""

    e1, e2, e3 = _principal_extents(positions)
    volume = 0.0
    for a, b, c in tris:
        pa, pb, pc = positions[a], positions[b], positions[c]
        volume += (
            pa[0] * (pb[1] * pc[2] - pb[2] * pc[1])
            + pa[1] * (pb[2] * pc[0] - pb[0] * pc[2])
            + pa[2] * (pb[0] * pc[1] - pb[1] * pc[0])
        )
    volume = abs(volume) / 6.0
    box = e1 * e2 * e3
    hull = mesh_audit.hull_volume(positions)
    return {
        "flatness": e3 / e1 if e1 else 0.0,
        "blade": e2 / e1 if e1 else 0.0,
        "fill": volume / box if box else 0.0,
        "solidity": volume / hull if hull else 0.0,
        "volume_m3": volume,
    }


def _finest_visual(geoms: dict) -> str:
    best, best_n = None, -1
    for name in geoms:
        if name.startswith("Colmesh_"):
            continue
        head, _, tail = name.rpartition("_a")
        if head and tail.isdigit() and int(tail) > best_n:
            best, best_n = name, int(tail)
    if best is None:
        best = max(
            (g for g in geoms if not g.startswith("Colmesh_")),
            key=lambda g: len(geoms[g][1]),
        )
    return best


def test_the_convex_hull_this_gate_stands_on_is_correct():
    """NEGATIVE CONTROL, part 1: the hull itself, on bodies whose volume is known exactly."""

    cube = [(x, y, z) for x in (0.0, 1.0) for y in (0.0, 1.0) for z in (0.0, 1.0)]
    assert abs(mesh_audit.hull_volume(cube) - 1.0) < 1e-12
    # interior points must not change the hull
    padded = [*cube, (0.5, 0.5, 0.5), (0.25, 0.6, 0.4)]
    assert abs(mesh_audit.hull_volume(padded) - 1.0) < 1e-12
    # a regular octahedron of circumradius 1 has volume 4/3
    octa = (
        [(s * 1.0, 0.0, 0.0) for s in (-1, 1)]
        + [(0.0, s * 1.0, 0.0) for s in (-1, 1)]
        + [(0.0, 0.0, s * 1.0) for s in (-1, 1)]
    )
    assert abs(mesh_audit.hull_volume(octa) - 4.0 / 3.0) < 1e-12
    # degenerate input is 0, never an exception
    assert mesh_audit.hull_volume([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]) == 0.0
    assert mesh_audit.hull_volume([(0.0, 0.0, 0.0)] * 8) == 0.0


def test_the_husk_gate_fires_on_a_husk():
    """NEGATIVE CONTROL, part 2: a gate that has never been SHOWN TO FIRE is not tested.

    A SPIKY HUSK, built to the diagnosis in `level_facts`: thin sheets radiating from a hollow
    core.  Twelve wedges of a unit sphere, each 1 % of the sphere's radius thick.  Its hull is
    the sphere, its volume is almost nothing -- and the adopted bars must reject it while
    accepting a plain box, which is what a boulder is a rounded version of.
    """

    positions: list[tuple[float, float, float]] = []
    tris: list[tuple[int, int, int]] = []
    for k in range(12):
        angle = 2.0 * math.pi * k / 12.0
        dx, dy = math.cos(angle), math.sin(angle)
        base = len(positions)
        for z in (-0.01, 0.01):
            tip = z + (1.0 if z > 0 else -1.0)
            positions += [(0.0, 0.0, z), (dx, dy, z), (dx * 0.5, dy * 0.5, tip)]
        tris += [
            (base, base + 1, base + 2),
            (base + 3, base + 5, base + 4),
            (base, base + 3, base + 4),
            (base, base + 4, base + 1),
            (base + 1, base + 4, base + 5),
            (base + 1, base + 5, base + 2),
            (base + 2, base + 5, base + 3),
            (base + 2, base + 3, base),
        ]
    husk = husk_reading(positions, tris)
    assert husk["solidity"] < HUSK_HARD_SOLIDITY, husk
    box_positions = [(x, y, z) for x in (0.0, 1.0) for y in (0.0, 0.8) for z in (0.0, 0.6)]
    box_tris = [
        (0, 2, 3),
        (0, 3, 1),
        (4, 5, 7),
        (4, 7, 6),
        (0, 1, 5),
        (0, 5, 4),
        (2, 6, 7),
        (2, 7, 3),
        (0, 4, 6),
        (0, 6, 2),
        (1, 3, 7),
        (1, 7, 5),
    ]
    box = husk_reading(box_positions, box_tris)
    assert box["solidity"] > 0.99 and box["fill"] > 0.99, box


def test_no_rock_class_body_is_a_husk(shapes):
    """The user's "single flake", measured on the SHIPPED bytes at the finest visual LOD.

    Scope: every ``build="model"`` shape that carries a Colmesh.  ``colmesh=0`` is litter the
    car never touches (`bark_debris`, `branch_pile`), and the husk question is about what the
    car hits -- exactly how the rock gate above already scopes litter.
    """

    rows = shapes["species"]
    problems: list[str] = []
    readings: dict[str, dict] = {}
    for species in fs.SPECIES:
        # r11 (critic N-2 and N-3): the scope is a closed body with collision, ROCK OR
        # DEADWOOD.  The bar below is derived from stock ROCKS (`b3/r10/husk_*.json`), and a
        # standing broken trunk is not a rock: `snag_a` reads solidity 0.286 and `snag_b`
        # 0.327 against a HARD bar of 0.54, because a slender tapered pole with two stubs
        # fills very little of its own convex hull however solid it is.  That is a category
        # error, not a husk -- exactly R10.2's own argument for the DEADWOOD class -- so the
        # snags are excluded HERE, by class and with their measurement published
        # (`b3/r11/snag_gate_probe.json`), and are inside the keep-out and the rock gate,
        # which they pass with room.  N-3's complaint was that the reason given for an
        # exclusion was the wrong reason; this is the right one, and it is measured.
        if species["family"] not in ("rock", "deadwood") or not species["colmesh"]:
            continue
        if not pf.is_keep_out_body(species):
            continue
        key = species["key"]
        row = rows.get(key)
        if row is None:
            continue
        payload = (LEVEL_ROOT / row["relative"]).read_bytes()
        geoms = mesh_audit.geometries(payload)
        reading = husk_reading(*geoms[_finest_visual(geoms)])
        readings[key] = reading
        fill, solidity = reading["fill"], reading["solidity"]
        if species["family"] == "deadwood":
            source = (row.get("import_part") or {}).get("source_reading")
            assert source, f"{key}: the build manifest carries no source-scan reading"
            if solidity < source["solidity"] - HUSK_SOURCE_TOLERANCE:
                problems.append(
                    f"{key}: solidity {solidity:.3f} is below its own CC0 scan "
                    f"{source['asset']} at {source['solidity']:.3f}"
                )
            if fill < source["fill"] - HUSK_SOURCE_TOLERANCE:
                problems.append(
                    f"{key}: fill {fill:.3f} is below its own CC0 scan "
                    f"{source['asset']} at {source['fill']:.3f}"
                )
            continue
        if solidity < HUSK_HARD_SOLIDITY:
            problems.append(
                f"{key}: solidity {solidity:.3f} < {HUSK_HARD_SOLIDITY} (below every stock rock)"
            )
        elif solidity < HUSK_SOFT_SOLIDITY and fill < HUSK_SOFT_FILL:
            problems.append(
                f"{key}: solidity {solidity:.3f} < {HUSK_SOFT_SOLIDITY} AND "
                f"fill {fill:.3f} < {HUSK_SOFT_FILL}"
            )
    assert readings, "no model shape carried a Colmesh -- the gate measured nothing"
    assert not problems, "husk gate:\n  " + "\n  ".join(problems)


def test_every_part_index_selects_a_whole_scanned_rock(shapes):
    """`part` must index the glTF's own meshes, never loose geometry (r10).

    A glTF splits its vertex buffer at every UV/normal seam and Blender's importer does not
    weld, so joining the file and separating LOOSE parts cuts it into UV CHARTS:
    `rock_moss_set_01` holds 6 meshes and 71 loose pieces.  r9 shipped the loose ordering, so
    `mossy_rock_c`'s `part=2` was a 4,044-poly fragment of the 10,996-poly rock -- genus 2,
    24 components at 2 cm, fill 0.188 / solidity 0.489, and the user's "single flake".
    """

    rows = shapes["species"]
    problems = []
    checked = 0
    for species in fs.SPECIES:
        if species["build"] != "model" or species["source"][1] is None:
            continue
        row = rows.get(species["key"])
        if row is None:
            continue
        part = row.get("import_part") or {}
        assert part, f"{species['key']}: the build manifest carries no import_part record"
        checked += 1
        if part.get("imported_objects", 1) > 1 and part.get("part_source") != "objects":
            problems.append(
                f"{species['key']}: part {part.get('part_index')} came from "
                f"{part.get('part_source')!r} over {part.get('imported_objects')} imported "
                "objects -- that is a UV chart, not a rock"
            )
    assert checked, "no species uses a part index -- this gate measured nothing"
    assert not problems, "part selection:\n  " + "\n  ".join(problems)
