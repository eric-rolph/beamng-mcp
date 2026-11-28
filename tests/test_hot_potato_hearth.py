"""Static gates for B2's hearth (design v4 §3, §5.3, §7.3; §10's B2 row).

Every assertion here is a pure function of the frozen ``layout.json``, the two B2
authoring manifests and the level tree on disk -- no simulator.  The live gates that
repeat these readings by ray and by frame live in
``tests/test_hot_potato_hearth_live.py``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from examples.hot_potato_arena.level import hearth_build as hb
from examples.hot_potato_arena.level import hearth_spec as hs
from examples.hot_potato_arena.level import place_hearth as ph

#: The crust plate's UV contract, read from the shapes manifest the Blender run wrote.
bh_uv = hb.shapes_manifest()["crust"]["uv_tiles"]

LEVEL_ROOT = hb.LEVEL_ROOT
pytestmark = pytest.mark.skipif(
    not hb.available(), reason="the B2 hearth manifests are not built in this tree"
)


def test_layout_is_the_frozen_design_v4() -> None:
    """The layout B2 reads is the sha-locked v4 one, not a later edit."""

    lock = json.loads(hs.DESIGN_LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["source"].startswith("level_round/design")
    assert "layout.json" in lock["files"]
    payload = hs.LAYOUT_PATH.read_bytes()
    import hashlib

    digest = hashlib.sha256(payload).hexdigest()[:16]
    assert digest == lock["files"]["layout.json"], (
        "the vendored layout is not the frozen v4 one",
        digest,
        lock["files"]["layout.json"],
    )


def test_the_census_matches_the_design() -> None:
    census = hb.census()
    assert census["stones"] == 28
    assert census["crust_plates"] == hs.CRUST_COUNT == 24
    # Amendment A2 (2026-09-15/16, ``authoring/design_amendments.md``): the kindling logs,
    # the enamel pot, the lantern tripod and the lantern came off the map, then the leaner
    # log, the bench deck and the four lantern posts; with them the eight log-end
    # fire/smoke nodes (34 -> 26), the four kindling fire lights, the lantern's two lights
    # and the four track lanterns on the posts (36 -> 26), nine of which cast shadows
    # (23 -> 14).
    assert census["emitter_nodes"] == 26
    assert census["lights"] == 26
    # r3 DEVIATION, stated: 12 of the 24 ember-bed lights drop ``castShadows`` and
    # become the FILL half of the re-light (``hearth_spec.EMBER_FILL``).  35 -> 23 is a
    # frame-time REDUCTION taken while the pools got bigger; the deviation table is
    # ``hs.ember_light_deviations()`` and the gate below reads it.
    assert census["lights_shadowed"] == 14
    assert census["sfx_emitters"] == 18
    assert census["sfx_spaces"] == 13
    assert census["decals"]["rows"] == census["decals"]["written_rows"] == 619
    assert census["decals"]["keys"] == 12
    # QB-21 asks >= 300 rows and >= 3 families; the design names six hearth families
    assert census["decals"]["family_count"] >= 6
    assert census["shapes"] == 7
    assert not census["duplicate_names"]


def test_the_ember_relight_is_declared_and_halves_the_shadow_maps() -> None:
    """The bed lights the stones, and the deviation table IS the shipped record."""

    rows = hs.ember_light_deviations()
    assert len(rows) == 24
    assert [r["role"] for r in rows[:4]] == ["key", "fill", "key", "fill"]
    assert sum(1 for r in rows if r["castShadows"][1]) == 12
    for row in rows:
        assert row["radius"][0] == 34.0
        assert row["intensity"][0] == 12000.0
        assert row["castShadows"][0] is True
        assert 0.72 <= hs.ember_variance(f"{hs.LEVEL_ID}_{row['name']}") <= 1.28
    # r4: the radius is the ROLE's value exactly -- no per-light variance on it, so the
    # published table cannot drift from the geometry the way r3's did (critic r3 D1).
    assert {r["radius"][1] for r in rows} == {
        float(hs.EMBER_KEY["radius"]),
        float(hs.EMBER_FILL["radius"]),
    }
    for row in rows:
        base = hs.EMBER_KEY if row["role"] == "key" else hs.EMBER_FILL
        assert row["radius"][1] == float(base["radius"])
    # the ring must not be one even strip: >= 2x spread between its lights
    intensities = [r["intensity"][1] for r in rows]
    assert max(intensities) / min(intensities) >= 2.0
    records = {r["name"]: r for r in hs.light_records()}
    for row in rows:
        record = records[f"{hs.LEVEL_ID}_{row['name']}"]
        assert record["radius"] == row["radius"][1]
        assert record["intensity"] == row["intensity"][1]
        assert record["castShadows"] == row["castShadows"][1]


def test_the_ember_ring_has_a_thirty_degree_pool_pitch_and_no_dark_gap() -> None:
    """r4, and it is the gate r3 needed and did not have (critic r3, C3-1).

    r3 grew every ember pool from the design's 34 m to 54-66 m on a 49.077 m spacing and
    reported it as "the direct answer to ``lit_fraction 1.0, longest dark run 0.0 deg``".
    Re-running B2's own frame instrument on B2's own certified frame returned the
    identical reading with the band 25 % MORE even.  Nothing in the build could have
    caught that, because nothing modelled the ring between the light table and a boot.

    ``hs.ember_ring_profile()`` does.  Two things have to hold at once and they pull
    against each other, which is exactly why this is a gate:

    * the band must stay CONTINUOUS -- design section 8's S6 pass rule is "the ring
      reads as a continuous glow band", so a dark gap is a failure, not the fix;
    * it must be MODULATED at the KEY pitch -- 30 degrees, harmonic 12 -- rather than
      being a wash.
    """

    profile = hs.ember_ring_profile()
    assert profile["lights"] == 24
    assert profile["minimum_is_zero"] is False
    assert profile["trough_over_mean"] > 0.002, "the ring has a dark gap: section 8 S6 fails"
    # the pools alternate: the KEY bins must be several times the FILL bins
    assert profile["key_over_fill"] >= 3.0, profile["key_over_fill"]
    # and the 30 degree period must carry real amplitude against the 15 degree one.
    # r3's table scores 0.204 here and the design's own 24 identical lights score 0.046.
    assert profile["harmonic_12_over_24"] >= 0.50, profile["harmonic_12_over_24"]
    assert profile["coefficient_of_variation"] > 3.0
    # every giant stone must still stand inside a KEY pool, because "the stones are lit"
    # is the one thing critic r3 said it would ship out of r3
    key_radius = float(hs.EMBER_KEY["radius"])
    keys = [
        record
        for index, record in enumerate(
            r for r in hs.light_records() if r["name"].startswith(f"{hs.LEVEL_ID}_ember_light_")
        )
        if index % 2 == 0
    ]
    for stone in hs.stones():
        if not stone["name"].startswith("hearth_stone"):
            continue
        nearest = min(
            math.hypot(stone["x"] - record["position"][0], stone["y"] - record["position"][1])
            - float(stone["diam"]) / 2.0
            for record in keys
        )
        assert nearest < key_radius, (stone["name"], nearest, key_radius)


def test_the_crust_maps_u_axis_is_the_radius() -> None:
    """r3's cook banks the bed along u; if the exporter swapped u and v it would paint
    a bright stripe every 15 degrees instead.  Read out of the shipped DAE's bytes."""

    axes = hb.crust_uv_axes()
    assert axes["r"] == [hs.CRUST_R_INNER, hs.CRUST_R_OUTER]
    assert axes["u"] == [0.0, bh_uv["radial"]]
    assert axes["v"] == [0.0, bh_uv["tangential"]]
    # u IS the radius: perfectly correlated, and v carries none of it
    assert axes["corr_u_r"] == 1.0
    assert abs(axes["corr_v_r"]) < 0.01
    # and the density both ways stays inside design section 8's <= 15 mm/texel
    assert max(bh_uv["mm_per_texel"]) <= 15.0


def test_the_crust_tile_metres_agree_with_the_exporter() -> None:
    """``hearth_spec``'s copy of the tile count cannot drift from ``blender_hearth``'s.

    ``hearth_textures`` sizes its lumps in METRES against the design's 0.3-1.2 m band,
    and the metre depends on how many times the map tiles across a plate.  Two modules
    now hold that number, so one gate holds them together.
    """

    from examples.hot_potato_arena.level import blender_hearth as bh

    assert bh.CRUST_UV_TILES == hs.CRUST_TANGENTIAL_TILES == 2.0
    assert bh.CRUST_RADIAL_TILES == 1.0
    assert hs.CRUST_TILE_U_M == pytest.approx(23.0)
    assert hs.CRUST_TILE_V_M == pytest.approx(24.5437, abs=1e-4)
    # and the exporter's own manifest agrees, from the DAE it actually wrote
    assert bh_uv["tangential"] == hs.CRUST_TANGENTIAL_TILES
    assert bh_uv["radial"] == 1.0


def test_the_crust_lumps_are_inside_the_design_band_on_the_LONG_axis() -> None:
    """Critic r3 D8: r3's coarsest lump is 1.278 m against the design's 1.2 m ceiling.

    r3 published ``23.0 / cells`` and called it "inside the design's 0.3-1.2 m band".
    A tile is 23.000 m radially and **24.544 m** tangentially, so the honest number is
    the long axis, and on that axis r3's 18-cell layer is 1.363 m -- 14 % over, not
    "inside".  This gate is the long axis.
    """

    crust = hb.textures_manifest()["notes"]["crust"]
    layers = [int(row[0]) for row in crust["pile_layers"]]
    coarsest, finest = min(layers), max(layers)
    long_axis = max(hs.CRUST_TILE_U_M, hs.CRUST_TILE_V_M)
    assert long_axis / coarsest <= 1.2, (coarsest, long_axis / coarsest)
    assert long_axis / finest >= 0.3, (finest, long_axis / finest)
    # and the manifest publishes the long axis, not the flattering one
    assert crust["lump_span_m"] == [
        round(long_axis / finest, 3),
        round(long_axis / coarsest, 3),
    ]


def test_the_crust_maps_are_periodic_across_the_v_seam() -> None:
    """A tangential tile boundary must be invisible, and r3's was not.

    The plate's *v* axis tiles twice per 15 degree sector and abuts the next plate, so
    every crust map has to be periodic in v (image ROWS).  r3's domain warp was passed
    in PIXELS and reached 1.17 cells at the finest layer, which pushed the true nearest
    Voronoi site outside the 3 x 3 search block near the map border; the shipped
    emissive map's wrap step measured **1.97x** its own interior median and critic r3
    saw "at least two straight vertical v-tiling seams" in the 2 m frame.

    Seam energy is the mean absolute row step ACROSS the wrap over the median interior
    row step.  A periodic map reads about 1.0.  The *u* axis is the radius and is
    deliberately NOT periodic (it banks), so it is not judged here.
    """

    numpy = pytest.importorskip("numpy")
    image_module = pytest.importorskip("PIL.Image")
    stem = hs.crust_material()
    for role in ("_b.color.png", "_nm.normal.png", "_e.color.png", "_r.data.png"):
        path = LEVEL_ROOT / hs.SHAPE_DIR / f"{stem}{role}"
        assert path.is_file(), path
        with image_module.open(path) as image:
            data = numpy.asarray(image.convert("RGB"), numpy.float32).mean(axis=2) / 255.0
        interior = numpy.abs(numpy.diff(data, axis=0)).mean(axis=1)
        wrap = float(numpy.abs(data[0] - data[-1]).mean())
        ratio = wrap / max(float(numpy.median(interior)), 1e-9)
        assert ratio < 1.35, (role, ratio, "the v tile boundary is a visible seam")


def test_the_crust_is_built_the_way_b0s_reference_plate_is() -> None:
    """A dark albedo carrying a masked, strong emissive -- critic r3's C3-2 ruling.

    B0's probe plate, read from B0's own shipped bytes by critic r3, is albedo **linear
    mean 0.00549** (sRGB 0.0585) under an emissive mask at **32.5 %** coverage, mean
    0.3098, and it read 2.9-3.1x red excess against itself with the emissive removed.
    r3 shipped an albedo **7.24x brighter** with a 0.48 % mask and read 1.346, and then
    argued the design's art direction made the ratio unreachable.  It does not: B0's own
    reference satisfies both at once.

    The bands here are deliberately wide.  The point is not to copy B0's plate -- it is
    a 3.2 m quad, this is a 23 m banked bed with ash drifts and dead stretches -- but
    to make the SHAPE of the build a gate, so no future revision can quietly go back to
    a pale albedo with a hairline mask.
    """

    numpy = pytest.importorskip("numpy")
    image_module = pytest.importorskip("PIL.Image")
    stem = hs.crust_material()
    with image_module.open(LEVEL_ROOT / hs.SHAPE_DIR / f"{stem}_b.color.png") as image:
        albedo = numpy.asarray(image.convert("RGB"), numpy.float32) / 255.0
    with image_module.open(LEVEL_ROOT / hs.SHAPE_DIR / f"{stem}_e.color.png") as image:
        emissive = numpy.asarray(image.convert("RGB"), numpy.float32)[:, :, 0] / 255.0
    linear = numpy.where(albedo <= 0.04045, albedo / 12.92, ((albedo + 0.055) / 1.055) ** 2.4)
    linear_mean = float(linear.mean())
    lit = float((emissive > 0.05).mean())
    bright = float((emissive > 0.5).mean())
    # black-red coal: within 3x of B0's plate in linear light, and never r3's 7.24x
    assert 0.0030 <= linear_mean <= 0.0165, linear_mean
    # A REAL MASK, not a hairline.  r3 shipped 0.037 here and the 100 m ring read as a
    # strip of gravel; r2 and B0 both sat near 0.33.
    assert lit >= 0.20, lit
    # and it must stay a MASK: most of the bed is black char, or it is a lava field
    assert lit <= 0.45, lit
    # **The BRIGHT share is a separate, opposite bound, and it is the one r4's first
    # boot got wrong.**  Two boots of the same scene give the transfer ``night pixels
    # above luma 240 ~= 0.43 x frac(emissive > 0.5)``; at 0.143 the night bed came back
    # 6.2 % burned to white and read as molten rock.  r3 and r2 both sat near 0.5-0.7 %
    # clipped, so the ceiling here is the night frame's, not a taste call.
    assert bright <= 0.035, (bright, "the night bed will clip to white: this is lava")
    # the manifest publishes the same numbers the gate reads
    crust = hb.textures_manifest()["notes"]["crust"]
    assert crust["albedo_linear_mean"] == pytest.approx(linear_mean, abs=5e-4)
    assert crust["emissive_mask_fraction_over_half"] == pytest.approx(bright, abs=5e-3)


def test_stone_faces_clear_the_design_radius() -> None:
    """R1: nothing hittable inside r 200; the design puts the inner faces at 202.0."""

    gate = ph.gate_clearance()
    assert gate["min_inner_face_r"] == pytest.approx(202.0, abs=0.01)
    for face in gate["faces"]:
        assert face["r_inner_face"] >= 200.0, face


def test_the_four_lanes_are_at_least_thirty_five_metres() -> None:
    """R2: four lanes at 60/150/240/330, any left/right pair, chocks included."""

    gate = ph.gate_clearance()
    assert set(gate["lanes"]) == {"lane_60", "lane_150", "lane_240", "lane_330"}
    for name, row in gate["lanes"].items():
        assert row is not None, name
        assert row["width"] >= 35.0, (name, row)
    assert gate["lane_min"] == pytest.approx(89.0, abs=0.1)


def test_fire_sites_clear_their_logs_and_every_stone() -> None:
    gate = ph.gate_fire_sites()
    assert len(gate["fires"]) == 4
    assert gate["min_log_clearance_m"] >= 1.5
    assert gate["min_stone_face_m"] >= 30.0


def test_every_placed_object_sits_on_or_above_the_terrain() -> None:
    """R8: statics at their authored offset, everything else >= 0 above the ground."""

    gate = ph.gate_z()
    assert gate["count"] >= 130
    assert gate["non_static_min_delta"] >= 0.0
    assert gate["static_offset_max_error"] <= 0.01


def test_no_name_collides_with_anything_the_level_already_ships() -> None:
    """SimObject names are global across classes -- one collision blanks a whole item."""

    gate = ph.gate_names()
    assert gate["collisions_with_the_tree"] == []
    assert gate["unnamespaced"] == []
    assert gate["b2_names"] >= 150
    assert gate["foreign_names_scanned"] > 50


def test_every_datablock_reference_resolves() -> None:
    """R10, and the two forms B0 measured: no EmberEmitter, no one-shot fire profile."""

    gate = ph.gate_datablock_resolution()
    assert gate["problems"] == []
    assert set(gate["level_particles"]) == {
        f"{hs.LEVEL_ID}_pd_ember",
        f"{hs.LEVEL_ID}_pd_ember_glow",
        # r2: the six heat wisps left BNGP_24 behind -- the stock steam set rendered as
        # six blown white eggs at golden hour and the design asks for "low-alpha"
        f"{hs.LEVEL_ID}_pd_heat_wisp",
    }
    assert set(gate["level_nodes"]) == {f"{hs.LEVEL_ID}_pen_ember"}
    assert set(gate["level_sfx_profiles"]) == {
        f"{hs.LEVEL_ID}_sfx_fireloop1",
        f"{hs.LEVEL_ID}_sfx_fireloop2",
    }
    text = json.dumps(hb.rendered_outputs(), default=str)
    for missing in ("EmberEmitter", "EmberNode", "EmberParticle", "FireLoopSound"):
        assert missing not in text, missing


def test_particle_file_sorts_before_its_emitter_file() -> None:
    """server.lua walks the level directory in sorted order: particles must land first."""

    names = sorted(hs.particle_datablock_files())
    assert names[0].endswith("_embers_particle.datablocks.json")
    assert names[1].endswith("_embers_particleemitter.datablocks.json")


def test_generated_json_is_strict_lf_and_uuid5() -> None:
    gate = ph.gate_json()
    assert gate["problems"] == []
    assert gate["files"] >= 9


def test_night_lights_carry_the_string_fields_the_engine_reads() -> None:
    for record in hs.light_records():
        assert record["nightLight"] == "1", record["name"]
        assert isinstance(record["nightLight"], str)
        assert record["isEnabled"] is False, record["name"]
        assert record["texSize"] in {256, 512}, record["name"]
        assert record["flareType"] == "vehicleReverseLightFlare"
        assert record["attenuationRatio"] == [1.0, 0.0, 0.0]


def test_the_level_info_night_window_is_authored_as_strings() -> None:
    """B1 owns the LevelInfo; B2's lights are useless without its two string fields."""

    path = LEVEL_ROOT / "main/MissionGroup/level_objects/sky_and_sun/items.level.json"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    info = [r for r in records if r.get("class") == "LevelInfo"]
    assert info, "no LevelInfo in the sky group"
    assert info[0].get("nightLightsNightStart") == "0.29"
    assert info[0].get("nightLightsNightEnd") == "0.79"


def test_crust_plates_are_light_only_and_tightly_bounded() -> None:
    for record in hs.crust_records():
        assert record["collisionType"] == "None"
        assert record["castShadows"] is False
    plates = hs.crust_plates()
    assert len({tuple(p["position"][:2]) for p in plates}) == 24
    for plate in plates:
        r, bearing = hs.polar(plate["position"][0], plate["position"][1])
        assert r == pytest.approx(hs.CRUST_R_MID, abs=0.01)
        assert min(abs(bearing - plate["yaw"]), 360 - abs(bearing - plate["yaw"])) < 0.01


def test_stone_shapes_carry_their_lods_colmesh_and_soot() -> None:
    manifest = hb.shapes_manifest()
    assert set(manifest["stones"]) == set(hs.STONE_SOURCES)
    for asset, info in manifest["stones"].items():
        tris = info["node_tris"]
        for pixel, budget in hs.STONE_DETAILS:
            node = f"{hs.stone_stem(asset)}_a{pixel}"
            assert node in tris, (asset, node)
            assert 0 < tris[node] <= budget, (asset, node, tris[node], budget)
        colmesh = f"Colmesh_{hs.stone_stem(asset)}-1"
        # r6: the collider is a DECIMATED COPY of the visual, not a convex hull, so its
        # budget is per source (hearth_spec.STONE_COLMESH_BUDGET) -- see the DEVIATION
        # note there.  240 stays the default for anything without a row.
        budget = hs.stone_colmesh_budget(asset)
        assert 0 < tris[colmesh] <= budget, (asset, tris[colmesh], budget)
        assert info["colmesh_budget"] == budget, asset
        assert info["colmesh_kind"] in ("decimated_solid", "convex_hull_fallback"), asset
        assert f"nulldetail{hs.STONE_NULLDETAIL}" in tris
        assert "bb_autobillboard25" in tris
        # the soot bake: one COLOR input per detail node, floor at 0.45
        assert info["vertex_colour_semantic"] == len(hs.STONE_DETAILS)
        for node_soot in info["soot"].values():
            assert node_soot["min"] == pytest.approx(hs.SOOT_FLOOR, abs=1e-3)
            assert node_soot["max"] <= 1.0


def test_stone_shapes_stand_at_the_designs_height() -> None:
    """The scans do not come in the design's height/diameter ratio; the mesh is stretched."""

    manifest = hb.shapes_manifest()
    for asset, info in manifest["stones"].items():
        assert info["world_height_m"] == pytest.approx(info["design_height_m"], abs=0.05), asset
        assert 0.5 <= info["height_stretch"]["factor"] <= 2.5, asset


def test_the_rock_material_declares_the_soot_channel_on_a_v15_recipe() -> None:
    document = hs.rock_materials_document()
    for asset in hs.STONE_SOURCES:
        material = document[hs.stone_material(asset)]
        assert material["version"] == 1.5
        assert material["Stages"][0]["vertColor"] is True
        assert material["Stages"][0]["baseColorMap"].endswith("_b.color.png")
        assert material["groundType"] == "ROCK"


def test_the_crust_material_is_emissive_at_the_measured_recipe() -> None:
    material = hs.rock_materials_document()[hs.crust_material()]
    assert material["emissive"] is True
    assert material["emissiveIntensityNits"] == 2500
    assert material["emissiveFactor"] == [1.0, 0.36, 0.08]
    assert material["castShadows"] is False
    assert material["Stages"][0]["emissiveMap"].endswith("_e.color.png")


def test_every_cooked_map_is_a_power_of_two() -> None:
    """A non-power-of-two texture is silently never cooked and draws magenta."""

    for relative, info in hb.textures_manifest()["files"].items():
        for side in info["px"]:
            assert side >= 16 and (side & (side - 1)) == 0, (relative, info["px"])


def test_the_shipped_bulk_members_match_their_manifests() -> None:
    result = hb.verify()
    assert result == {"missing": [], "stale": []}


def test_the_tree_matches_the_render() -> None:
    result = ph.write(check_only=True)
    assert result["stale"] == []
    assert result["groups"]["added"] == []
    assert result["decals"]["stale"] is False


def test_the_decal_rows_land_where_the_design_puts_them() -> None:
    rows = hb.decal_instances()
    assert set(rows) == {hs.decal_datablock(key) for key in hs.DECAL_KEYS}
    for key, spec in hs.DECAL_KEYS.items():
        instances = rows[hs.decal_datablock(key)]
        assert len(instances) == spec["rows"], key
        for row in instances:
            size = row[1]
            assert spec["size"][0] - 1e-6 <= size <= spec["size"][1] + 1e-6, (key, size)
            normal = row[6:9]
            assert abs(math.sqrt(sum(v * v for v in normal)) - 1.0) < 1e-3, key
            tangent = row[9:12]
            assert abs(sum(a * b for a, b in zip(normal, tangent, strict=True))) < 1e-3, key
        uids = [row[12] for row in instances]
        assert len(set(uids)) == len(uids), key
    everything = [row[12] for key in rows for row in rows[key]]
    assert len(set(everything)) == len(everything), "uid collision across keys"


def test_the_obstacle_handoff_fits_the_runtime_contract() -> None:
    handoff = hb.obstacle_handoff()
    assert handoff["runtime_contract"]["total"] == 113
    assert handoff["owners"] == {"B2": 28, "B4": 39}
    for row in handoff["rows"]:
        assert 0.5 <= row["r"] <= 30.0, row
        assert row["rp"] <= row["r"], row
    assert len(handoff["fallback_rows"]) == 18
    assert hb.OBSTACLES_HANDOFF.is_file()


def test_the_audio_forest_meta_names_the_stock_events() -> None:
    rows = hb.audio_forest_document()
    assert rows[0]["type"] == "meta"
    assert rows[0]["mainEvent"].startswith("event:>Ambient>Wind>")
    assert rows[0]["roomtoneEnabled"] == 1
    assert all(row.get("include") == 1 for row in rows[1:])


def test_every_sfx_emitter_names_a_looping_profile() -> None:
    level_profiles = set(hs.sfx_datablock_file()[1])
    proven_stock = {"amb_windtrees_01"}
    inferred_stock = {"amb_birds_01"}
    tracks = [r["track"] for r in hs.audio_records() if r["class"] == "SFXEmitter"]
    assert len(tracks) == 18
    for track in tracks:
        assert track in level_profiles | proven_stock | inferred_stock, track
    for record in hs.sfx_datablock_file()[1].values():
        assert record["description"] == "AudioDefaultLoop3D"
        assert record["fileName"].startswith("art/sound/fireloop")


def test_release_text_members_are_lf_only() -> None:
    for relative in hb.rendered_outputs():
        payload = (LEVEL_ROOT / relative).read_bytes()
        assert b"\r" not in payload, relative
    for shared in (hb.DECALS_MEMBER, hb.GROUPS_MEMBER):
        assert b"\r" not in (LEVEL_ROOT / shared).read_bytes(), shared


def test_provenance_covers_every_cc0_source_the_hearth_uses() -> None:
    ledger = Path(hs.AUTHORING / "cc0_provenance.json")
    assert ledger.is_file()
    text = ledger.read_text(encoding="utf-8")
    # r6: a SLOT may be sourced from a differently-named scan (hearth_spec.stone_source_folder),
    # and the ledger has to cover the bytes actually read, not the slot's label
    used = {hs.stone_source_folder(asset) for asset in hs.STONE_SOURCES}
    for asset in (*used, *hb.ht.OVERLAY_SOURCES):
        assert f'"{asset}"' in text or f"/{asset}/" in text, asset


# --- r2 gates: every defect the critic found, made structural -------------------------
def test_the_dae_carries_the_designs_soot_multiplier() -> None:
    """r1 asked for 0.45 and shipped 0.70196, and no gate noticed.

    Blender's ``BYTE_COLOR`` attribute stores an sRGB byte and the COLLADA exporter
    writes that byte, so an un-compensated write ships the sRGB encoding of the
    multiplier as the multiplier.  The manifest now records what the FILE says, and
    this reads it back out of the shipped DAE bytes as well, because a manifest that
    describes an intention is exactly what let r1 through.
    """

    import re

    quantised = round(hs.SOOT_FLOOR * 255.0) / 255.0
    for asset, info in hb.shapes_manifest()["stones"].items():
        recorded = info["soot_in_the_dae"]
        assert recorded["arrays"] == 6, (asset, recorded)
        assert abs(recorded["min"] - quantised) <= 1.0 / 255.0, (asset, recorded, quantised)
        assert recorded["max"] >= 0.99, (asset, recorded)
        text = (LEVEL_ROOT / info["relative"]).read_text(encoding="utf-8")
        values: list[float] = []
        for match in re.finditer(r'id="[^"]*colors-soot-array"[^>]*>([^<]*)<', text):
            values.extend(float(v) for v in match.group(1).split()[0::4])
        assert values, asset
        assert abs(min(values) - quantised) <= 1.0 / 255.0, (asset, min(values))
        # the design's number, not its sRGB encoding: 0.70196 must NOT come back
        assert abs(min(values) - 0.70196) > 0.05, (asset, "the r1 sRGB round trip is back")


def test_the_particle_sprites_are_ours_and_end_in_alpha_zero() -> None:
    """A sprite whose alpha never reaches 0 draws its own bounding box when it stacks.

    That is what put a hard-edged saturated white rectangle in every frame the ember
    glow appeared in: ~21 live sprites per node, ADDITIVE at colour alpha 0.35, over a
    stock texture whose alpha floor is 4/255.  Both halves are gated -- the sprite ends
    at zero, and the datablock's summed peak stays under 1.
    """

    from PIL import Image

    notes = hb.textures_manifest()["notes"]["particles"]
    assert set(notes) == set(hs.PARTICLE_SPRITES)
    for kind, reading in notes.items():
        assert reading["border_alpha_max"] == 0.0, kind
        assert reading["alpha_min"] == 0.0, kind
        assert reading["alpha_max"] >= 0.99, kind
        # a filled square reads 1.0; r1's RENDERED sprites had a median fill of 0.875
        assert reading["bbox_fill_half"] < 0.35, (kind, reading["bbox_fill_half"])
        relative = hs.particle_texture(kind).removeprefix(f"{hs.LEVEL_RELATIVE}/")
        target = LEVEL_ROOT / relative
        assert target.is_file(), relative
        with Image.open(target) as image:
            assert image.mode == "RGBA", relative
            assert image.size == (reading["px"], reading["px"]), relative
        assert Path(relative).name.startswith(hs.LEVEL_ID), relative

    documents = hs.particle_datablock_files()
    particles = {
        name: record
        for document in documents.values()
        for name, record in document.items()
        if record["class"] == "ParticleData"
    }
    emitters = {
        name: record
        for document in documents.values()
        for name, record in document.items()
        if record["class"] == "ParticleEmitterData"
    }
    for name, emitter in emitters.items():
        particle = particles[str(emitter["particles"])]
        assert str(particle["textureName"]).startswith(hs.LEVEL_RELATIVE), name
        live = float(particle["lifetimeMS"]) / float(emitter["ejectionPeriodMS"])
        peak_alpha = max(colour[3] for colour in particle["colors"])
        assert 0.0 < peak_alpha <= 1.0, name
        travel = float(emitter["ejectionVelocity"]) * float(particle["lifetimeMS"]) / 1000.0
        size = max(float(s) for s in particle["sizes"])
        # The stacking rule applies to a sprite that never leaves its own footprint --
        # the glow drifts 0.5 m in 2.5 s and is 1.5 m across, so all ~10 live sprites
        # occupy the same pixels and their alphas ADD.  A spark travels 3.75 m and is
        # 0.1 m across, so it does not stack with itself and its own alpha is the peak.
        if str(emitter["blendStyle"]) == "ADDITIVE" and travel <= size:
            assert live * peak_alpha <= 1.0, (name, live, peak_alpha, travel, size)


def test_the_flare_census_is_a_count_not_a_claim() -> None:
    """r1's report said 10 flares remain; the records said 12.  Count them."""

    census = hs.flare_census()
    # A2 (2026-09-15): the four kindling fire lights and the lantern's two lights went with
    # the props they lit; the two spout keys are the flares that remain.
    assert census["lights"] == 26
    assert census["with_flare"] == 2, census["kept_names"]
    assert census["flareless"] == 24
    # every remaining flare belongs to an object some round actually builds
    assert set(census["kept_names"]) == {"spout_key_0", "spout_key_1"}
    for record in hs.light_records():
        if record["name"].startswith(hs.FLARELESS_LIGHT_PREFIXES):
            assert record["flareScale"] == 0.0, record["name"]


def test_the_shared_files_reconcile_in_both_directions() -> None:
    """The gate the critic asked B6 for, built here because B2 has the race scars.

    ``main/MissionGroup/items.level.json`` and ``main.decals.json`` are written by
    three workers.  Declaring B2's rows in one writer was necessary and NOT sufficient:
    the listing was overwritten without them anyway.  What catches every version of
    that bug is a TWO-WAY reconciliation -- every SimGroup row has a directory and
    every directory has a row; every decal key in the scene has a datablock and every
    datablock has rows -- so an orphan in either direction fails, whoever wrote it.
    """

    groups_path = LEVEL_ROOT / hb.GROUPS_MEMBER
    rows = [
        json.loads(line)
        for line in groups_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    listed = {str(row["name"]) for row in rows}
    directories = {
        path.name
        for path in (LEVEL_ROOT / "main" / "MissionGroup").iterdir()
        if path.is_dir() and (path / "items.level.json").is_file()
    }
    assert listed - directories == set(), ("SimGroup rows with no items file", listed - directories)
    assert directories - listed == set(), ("group directories nobody lists", directories - listed)
    for group in (hs.GROUP_HEARTH, hs.GROUP_NIGHT, hs.GROUP_AUDIO):
        assert group in listed, group

    decals = json.loads((LEVEL_ROOT / hb.DECALS_MEMBER).read_text(encoding="utf-8"))
    instances = decals.get("instances", {})
    mine = {hs.decal_datablock(key) for key in hs.DECAL_KEYS}
    assert mine <= set(instances), ("B2 decal keys are gone", mine - set(instances))
    assert sum(len(instances[key]) for key in mine) == 619
    datablocks = set(hs.decal_datablock_file()[1])
    assert mine <= datablocks, mine - datablocks
    for key in set(instances) & datablocks:
        assert instances[key], f"{key} has a datablock and no rows"


def test_qb8_every_dae_ships_its_sibling_cdae() -> None:
    """A ``stock`` item design section 13 says the level MEETS.

    The ``.cdae`` is the engine's own compile of the DAE, so the only way to ship one
    is to harvest it from a boot -- r1 generated seven and deleted them unread.
    """

    harvested = set(hb.harvest_members())
    if not harvested:
        pytest.skip("no engine-bake harvest staged in this tree yet (run the live main leg)")
    for relative in hb.dae_members():
        assert relative.removesuffix(".dae") + ".cdae" in harvested, relative
    manifest = hb.harvest_manifest()["files"]
    for relative in harvested:
        assert relative in manifest, relative
        assert manifest[relative]["bytes"] > 0, relative
    for row in manifest.values():
        atlas = row.get("atlas")
        if not atlas:
            continue
        # BB::DIM=128 / EQUATOR_STEPS=32 / INCLUDE_POLES=0 -> 8 x 4 cells of 128 px
        assert (atlas["width"], atlas["height"]) == (1024, 512), row["name"]
        assert atlas["cells_used"] == 32, row["name"]


# ---------------------------------------------------------------------------------------
# r6: the thin-shell gate (level_facts 2026-09-07, critic B2 pass 5's C5-2), the hearth's own
# ---------------------------------------------------------------------------------------


def test_no_hearth_stone_is_a_facade_inside_its_own_collider() -> None:
    """G-B2-01. Every one of the 28 placed stones, in the frame a car actually meets.

    The law, adopted from critic B2 pass 5 and recorded in ``level_facts`` on 2026-09-07:
    *a photogrammetry "face" scan wrapped on a proxy is a facade even when watertight* --
    ``h_rock_face_01`` shipped through r5 as a closed shell a median 0.75 m thick enclosing
    2-5 % of the volume of its own collision mesh, and that collision mesh was the shell's
    own convex hull, so a car stopped on an invisible wall before the rock it could see.
    Four of the 28 stones were that shape, two of them edge-on to the arena.

    The gate the law asks for, and the bars, pre-registered in ``b2/r6/GATE_PREREG.md``
    BEFORE the rebuild: visual / Colmesh volume >= 0.5 at every LOD, LOD parity spread
    <= 0.30, and a published car-band phantom-gap statistic whose ceilings are the WORST
    reading of each over the five stones the critic ruled solid, measured on the r5 shipped
    bytes in this same world frame (``hearth_build.STONE_COLLIDER_BARS``).

    **The frame is the point.** ``collider_probe.CAR_BAND_HEIGHTS_M`` are absolute metres
    (0.30-1.50 m: bumper, sill, bonnet, roof) but ``blender_hearth`` authors every stone at
    unit size and the TSStatic ``scale`` IS the design's footprint diameter, so probing the
    ``.dae`` as it lies casts the car band 10-22 m up a 26 m stone.
    ``hearth_build.stone_collider_report`` scales the geometry by the design diameter first
    and then calls B4's shared instrument, unmodified.

    What SHIPS reads, against what r5 shipped -- r7, correcting critic B2 pass 6's N2 and
    N3.  The figures here were ``build_out2``'s, which is the ``solid="face"`` build this
    round REFUSED and never shipped, and the BEFORE ray count was wrong by 351:

    ==================================  ==================  ==================
    ..                                  r5 shipped bytes    shipped now
    ==================================  ==================  ==================
    visual / Colmesh volume ratio       0.021 - 0.895       0.978 - 1.006
    car-band phantom p50                0.139 - 0.579 m     0.006 - 0.041 m
    car-band phantom max                0.580 - 3.872 m     0.058 - 0.172 m
    collider-only rays over the six     **2,196**           **83**
    ==================================  ==================  ==================

    ``b2/r7/stone_gate_AFTER_r7.json`` and
    ``b2/r7/stone_gate_BEFORE_r5_bytes_corrected.json`` -- the BEFORE re-taken at the bars
    ``GATE_PREREG.md`` ADOPTED (0.579 / 1.544 / 1.757) rather than the transcription-error
    ceilings the first run used, which is critic B2 pass 6's C6-3: **8 of r5's 28 stones
    fail the adopted gate** -- 4 on the collider bars (``rock_face_01``) and 4 more on the
    mesh audit (``namaqualand_boulder_03``) -- not the 16 the withdrawn ceilings gave.
    """

    assert hb.STONE_COLLIDER_BARS["ratio_min"] == 0.5, hb.STONE_COLLIDER_BARS
    placed = hs.layout()["stones"]
    assert len(placed) == 28, len(placed)
    rows = {asset: hb.stone_collider_report(asset) for asset in sorted(hs.STONE_SOURCES)}
    failures: dict[str, list[str]] = {}
    for name, row in rows.items():
        problems = hb.stone_collider_problems(row)
        if problems:
            failures[name] = problems
    assert not failures, failures
    # and every PLACED stone is gated through the source it draws, not just every source
    gated = {stone["name"]: str(stone["asset"]) for stone in placed}
    assert set(gated.values()) == set(rows), (sorted(set(gated.values())), sorted(rows))
    assert len(gated) == 28

    # the instrument can fail: push one stone's collider 1.0 m out on every horizontal side
    # and the phantom must read about a metre, not zero
    from examples.hot_potato_arena.level import collider_probe, mesh_audit

    asset = "namaqualand_boulder_05"
    scale = hb.stone_world_scale()[asset]
    path = LEVEL_ROOT / hs.SHAPE_DIR / f"{hs.stone_stem(asset)}.dae"
    geoms = mesh_audit.geometries(path.read_bytes())
    col_name = next(g for g in geoms if g.startswith("Colmesh_"))
    vis_name = max((g for g in geoms if g != col_name), key=lambda g: len(geoms[g][1]))
    col_verts, col_faces = collider_probe._arrays(*geoms[col_name])
    vis_verts, vis_faces = collider_probe._arrays(*geoms[vis_name])
    col_verts, vis_verts = col_verts * scale, vis_verts * scale
    proud = col_verts.copy()
    centre = (proud.min(axis=0) + proud.max(axis=0)) / 2.0
    offset = proud[:, :2] - centre[:2]
    norm = (offset**2).sum(axis=1) ** 0.5
    proud[:, :2] += offset / norm[:, None].clip(1e-9) * 1.0
    origins, directions, _meta = collider_probe.car_band_rays(proud)
    pushed = collider_probe.gap_statistics(
        origins, directions, (vis_verts, vis_faces), (proud, col_faces)
    )
    # a 1 m RADIAL push reads a 0.63 m median PERPENDICULAR gap, not 1.00: the nearest
    # point of a lumpy surface is closer than the direction the vertices were moved in,
    # and grazing rays land on the parts of the stone that moved least.  What the control
    # proves is that the instrument responds -- 0.63 m against the 0.025 m the shipped
    # collider reads on the same stone, twenty-five times over.
    assert pushed["phantom_p50_m"] > 0.5, pushed
    shipped = rows[asset]["details"][rows[asset]["finest_detail"]]["car_band"]
    assert pushed["phantom_p50_m"] > 10.0 * (shipped["phantom_p50_m"] or 0.0), (pushed, shipped)
    # r7 (critic B2 pass 6's N8): the two lines above prove the INSTRUMENT responds, and
    # stop there -- the code path that turns a bad measurement into a test FAILURE was
    # never exercised.  Feed the doctored reading to the gate itself and require it to
    # object, so the negative control tests the gate and not only the probe.
    doctored = json.loads(json.dumps(rows[asset]))
    doctored["details"][doctored["finest_detail"]]["car_band"] = dict(pushed)
    assert hb.stone_collider_problems(doctored), doctored["details"][doctored["finest_detail"]]


# ---------------------------------------------------------------------------------------
# r7: the HUSK gate (level_facts 2026-09-09 CORRECTION, critic B2 pass 6's ruling)
# ---------------------------------------------------------------------------------------


def test_no_hearth_stone_is_a_spiky_husk() -> None:
    """G-B2-06. The second half of the rock law: is this a boulder, or a hollow rind?

    The collider gate above answers "is there collision where nothing is drawn".  It cannot
    answer "is this body a rock", and the user's video is about the second question: the
    boulders read as "a single flake, not actual multi-faceted 3D rocks".  A wafer whose
    collision mesh hugs the wafer scores ~1.0 on the volume ratio and passes.

    **The bar implemented here is NOT the one first adopted.**  ``fill >= 0.30 AND
    solidity >= 0.65`` is withdrawn: critic B2 pass 6 calibrated both statistics against
    solids whose answer is known and found that a **sphere caps fill at 0.523** while **any
    convex body reads solidity 1.000**, so fill is a SHAPE statistic and solidity is the
    husk statistic -- and that bar fails 4 of the 13 stock BeamNG rocks it was calibrated
    on.  The replacement, adopted in ``level_facts``: hard-fail at solidity < 0.54 (below
    every stock rock), and fail the husk SIGNATURE, solidity < 0.67 AND fill < 0.28
    together.  It clears 6 of 6 hearth stones, clears 10 of 13 stock, and fails exactly the
    seven forest shapes the user's video identified.

    The three hearth stones that "narrowly missed" the withdrawn bar --
    ``h_namaqualand_boulder_03`` (fill 0.272 / solidity 0.872, 87 % of its own hull),
    ``h_boulder_01`` (0.293 / 0.718, on stock's own p25 to three decimals) and
    ``h_namaqualand_boulder_02`` (0.339 / 0.644) -- are inside stock's range on both
    statistics and are NOT defects.  This gate does not re-litigate them.
    """

    assert hb.STONE_HUSK_BARS == {
        "solidity_hard_min": 0.54,
        "solidity_signature_max": 0.67,
        "fill_signature_max": 0.28,
    }, hb.STONE_HUSK_BARS
    rows = {asset: hb.stone_husk_report(asset) for asset in sorted(hs.STONE_SOURCES)}
    failures = {a: hb.stone_husk_problems(r) for a, r in rows.items() if hb.stone_husk_problems(r)}
    assert not failures, {a: (rows[a], p) for a, p in failures.items()}
    # every placed stone draws one of these six sources, so 6 shapes gate 28 instances
    assert {str(s["asset"]) for s in hs.layout()["stones"]} == set(rows), sorted(rows)

    # NEGATIVE CONTROL, because a gate that has never been shown to fire has not been
    # tested (level_facts 2026-09-09, rule 2).  A spiky husk: nine flat sheets radiating
    # from a hollow core, which is the shape the user's video shows and the shape
    # `rock_solid.solid_from_face_scan` produces.
    import math

    positions: list[tuple[float, float, float]] = []
    tris: list[tuple[int, int, int]] = []
    for blade in range(9):
        angle = 2.0 * math.pi * blade / 9.0
        dx, dy = math.cos(angle), math.sin(angle)
        nx, ny = -dy * 0.01, dx * 0.01
        base = len(positions)
        for far, high in ((0.25, -1.0), (1.0, -0.4), (1.0, 0.4), (0.25, 1.0)):
            positions.append((dx * far + nx, dy * far + ny, high))
            positions.append((dx * far - nx, dy * far - ny, high))
        for i in range(3):
            a, b = base + i * 2, base + i * 2 + 2
            tris += [(a, a + 1, b), (a + 1, b + 1, b)]
        tris += [(base, base + 6, base + 1), (base + 1, base + 6, base + 7)]
    husk = hb.husk_statistics(positions, tris)
    assert husk["solidity_V_over_hull"] < hb.STONE_HUSK_BARS["solidity_hard_min"], husk
    assert hb.stone_husk_problems(husk), husk

    # ...and the SECOND rule fires on its own: a body that clears the hard floor but
    # carries the signature (not solid enough AND not boxy enough) must still fail.
    signature = {"solidity_V_over_hull": 0.60, "fill_V_over_box": 0.20}
    assert hb.stone_husk_problems(signature), signature
    # while a tapered clast at stock's own numbers passes both rules
    assert not hb.stone_husk_problems({"solidity_V_over_hull": 0.785, "fill_V_over_box": 0.279})
