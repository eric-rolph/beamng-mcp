"""B7b gates: the Shafer Bench, a native MeshRoad up the canyon wall.

Every gate measures the SHIPPED module or the SHIPPED scene files. Nothing re-derives the
survey: ``shelf_road`` computes it from the ring and the terrain, and these assert the
properties a road needs for a car to use it. Design amendment A6 records the addition.
"""

from __future__ import annotations

import json
import math

import pytest

from examples.hot_potato_arena.level import blender_backdrop as backdrop
from examples.hot_potato_arena.level import level_writer as writer
from examples.hot_potato_arena.level import shelf_road as shelf
from examples.hot_potato_arena.level import terrain_model as terrain

#: A dirt mountain road. The level's trail is gated at 12 %; the bench is laid at 10 % and
#: only the 30 m runout, which is the hillside's own grade, goes past that. The approach's
#: limit is the module's own (`shelf.APPROACH_GRADE_MAX`, judged over 25 m), because its last
#: pitch comes down onto the road's foot where the hillside falls toward the wall.
BENCH_GRADE_MAX = 0.105
RUNOUT_GRADE_MAX = 0.18
#: Wider than the trail's 6 m: this one has a 200 m drop on one side.
WIDTH_MIN_M = 9.0
RISE_MIN_M = 200.0


@pytest.fixture(scope="module")
def report() -> dict:
    return shelf.audit()


def test_the_road_climbs_at_a_drivable_grade(report: dict) -> None:
    assert report["grade_max_on_the_bench"] <= BENCH_GRADE_MAX, report
    assert report["grade_max_on_the_runout"] <= RUNOUT_GRADE_MAX, report
    assert report["rise_m"] >= RISE_MIN_M, report
    assert report["approach"]["grade_max_sustained"] <= shelf.APPROACH_GRADE_MAX, report["approach"]


def test_the_road_never_leaves_the_wall_it_is_cut_along(report: dict) -> None:
    """Off the face there is no rock beside the deck, and the road is a ribbon in the sky."""

    assert report["samples_off_the_face"] == 0, report


def test_the_road_is_never_inside_the_terrain(report: dict) -> None:
    """A road cannot cut into a BeamNG heightfield: the terrain renders over it.

    The runout is counted apart: it is laid ON the ground by construction.
    """

    assert report["samples_buried_in_terrain"] == 0, report
    assert report["runout_stations"] > 0, report


def test_no_two_stretches_of_road_share_a_column_of_the_wall(report: dict) -> None:
    """Why this is a traverse and not switchbacks, asserted rather than asserted-about.

    A bench cut into a face of angle `a` does not daylight until `cut x tan(a)` higher up;
    this face reaches 88 deg, so any two legs stacked in one column overhang. The survey
    crosses each column once and the question cannot arise -- while that stays true.
    """

    assert report["columns_used_twice"] == 0, report
    assert report["steepest_face_deg"] > 85.0, (
        "the face got gentler; switchbacks may now fit and this is no longer why the road "
        f"is a traverse: {report}"
    )


def test_there_is_wall_above_the_road_for_its_whole_length(report: dict) -> None:
    assert report["worst_crest_gap_m"] >= shelf.CREST_CLEARANCE_M, report


def test_the_survey_follows_the_ring_it_claims_to_follow(report: dict) -> None:
    """The survey reads the SHIPPED crest and terrain, so a re-mapped rim moves the road."""

    assert backdrop.GIS_ENABLED, "the ring is no longer the lidar crest; re-survey the road"
    assert report["terrain_ter_sha256"] == backdrop.terrain_grid()["sha256"]
    bench = [s for s in shelf.alignment() if not s.get("on_the_ground")]
    assert len(bench) > 400, len(bench)
    for station in bench[:: max(1, len(bench) // 40)]:
        rows = shelf.face_rows(station["bearing"])
        assert rows[0][1] - 0.01 <= station["z"] <= rows[-1][1] + 0.01, station
        assert station["radius"] == pytest.approx(
            shelf.face_radius(station["bearing"], station["z"]), abs=1e-6
        ), station


def test_the_meshroad_nodes_are_a_road_a_car_fits_on(report: dict) -> None:
    nodes = shelf.meshroad_nodes()
    meshroad = report["meshroad"]
    assert meshroad["nodes"] == len(nodes) >= 50, meshroad
    assert meshroad["width_min_m"] >= WIDTH_MIN_M, meshroad
    # the pass widens into a pad a car can turn round on
    assert nodes[-1]["width"] >= shelf.SUMMIT_WIDTH_M - 0.01, nodes[-1]
    # nodes close enough that the spline between them hugs the survey
    assert meshroad["node_spacing_max_m"] <= shelf.NODE_SPACING_M * 1.25, meshroad
    for node in nodes:
        assert node["depth"] > 0.0, node
        assert math.isclose(math.hypot(*node["normal"]), 1.0, abs_tol=1e-6), node
        assert node["normal"][2] > 0.99, node  # banked a few percent, never tipped


def test_the_lane_is_never_narrower_than_designed_anywhere_along_the_spline(report: dict) -> None:
    """Measured at EVERY survey station against the rock exactly there, as the spline lays it.

    r1 set each node's wall edge against the nearest mesh column and nothing between nodes;
    rays across the first boot's deck met rock standing 7.5-14.3 m tall 4 m from the lane's
    centre. The node stations are one in four, and the spline runs straight between them.
    """

    assert report["meshroad"]["lane_width_min_m"] >= shelf.DECK_WIDTH_M - 0.05, report["meshroad"]


def test_there_is_no_slot_between_the_road_and_the_wall(report: dict) -> None:
    """The wall-side edge is inside the rock at every station, so no wheel can drop past it."""

    assert report["meshroad"]["wall_gap_max_m"] <= 0.0, report["meshroad"]


def test_the_bank_leans_into_the_wall_not_toward_the_drop() -> None:
    """A car that slides should slide into the rock, not off the edge."""

    for station, node in zip(
        [
            s
            for s in shelf.alignment()
            if s["index"] in {n["station"] for n in shelf.meshroad_nodes()}
        ],
        shelf.meshroad_nodes(),
        strict=True,
    ):
        if station.get("on_the_ground"):
            assert node["normal"] == (0.0, 0.0, 1.0), node
            continue
        theta = math.radians(station["bearing"])
        outward = (math.sin(theta), math.cos(theta))
        lean = node["normal"][0] * outward[0] + node["normal"][1] * outward[1]
        assert lean > 0.0, (station["index"], node)


def test_the_gate_on_the_lane_can_fail() -> None:
    """A gate never shown to fire has not been tested (round rule 6).

    Squeeze the drivable width the edges are built from and the as-built lane measurement
    must drop under the designed width -- proving the audit reads the rock, not the constant.
    """

    original = shelf.DECK_WIDTH_M
    try:
        shelf._EDGES = None
        shelf.DECK_WIDTH_M = original - 3.0
        squeezed = shelf.audit()["meshroad"]["lane_width_min_m"]
    finally:
        shelf.DECK_WIDTH_M = original
        shelf._EDGES = None
    assert squeezed < original - 0.05, squeezed


def test_the_approach_reaches_the_road_from_the_trail_the_level_already_has(report: dict) -> None:
    """The road is only a road if a car can get to it from where the player starts."""

    approach = report["approach"]
    nodes = shelf.approach_nodes()
    assert approach["nodes_off_the_terrain_block"] == 0, approach
    assert approach["joins_the_road_within_m"] <= 0.5, approach
    assert abs(approach["step_up_to_the_road_m"]) <= 0.35, approach
    # r2's AI car met the road head-on and stopped: the approach must ARRIVE pointing uphill
    assert approach["arrival_heading_off_the_road_deg"] <= 10.0, approach
    assert approach["grade_max_sustained"] <= shelf.APPROACH_GRADE_MAX, approach
    trail_x, trail_y = terrain.bearing_point(terrain.TRAIL_BEARING, terrain.TRAIL_WAYPOINTS[-1][1])
    assert math.hypot(nodes[0][0] - trail_x, nodes[0][1] - trail_y) <= 0.5, nodes[0]


def test_the_scene_carries_the_meshroad_and_its_approach() -> None:
    """The group, the MeshRoad and the DecalRoad, in the files the level actually writes."""

    outputs = writer.render_level()
    group_path = f"main/MissionGroup/level_objects/{shelf.GROUP_NAME}/items.level.json"
    records = [
        json.loads(line)
        for line in outputs[group_path].decode("utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1, records
    road = records[0]
    assert road["class"] == "MeshRoad", road["class"]
    assert road["name"] == shelf.ROAD_NAME
    assert road["topMaterial"] == shelf.ROAD_MATERIAL
    assert len(road["nodes"]) == len(shelf.meshroad_nodes())
    assert all(len(node) == 8 for node in road["nodes"]), road["nodes"][:2]
    # the group must be DECLARED, or the next round's writer drops it silently
    groups = writer.mission_group_records()["main/MissionGroup/level_objects/items.level.json"]
    assert any(row["name"] == shelf.GROUP_NAME for row in groups), [row["name"] for row in groups]

    roads = [
        json.loads(line)
        for line in outputs["main/MissionGroup/decal_road/items.level.json"]
        .decode("utf-8")
        .splitlines()
        if line.strip()
    ]
    approach = [row for row in roads if row["name"] == shelf.APPROACH_NAME]
    assert len(approach) == 1, [row["name"] for row in roads if "shelf" in row["name"]]
    assert approach[0]["nodes"] == shelf.approach_nodes()


def test_the_road_ships_no_texture_and_no_mesh_of_its_own() -> None:
    """Native object, the ring's own maps: nothing new cooks, no DAE, no .cdae to harvest.

    Every map the materials name must already be a level member, or the road renders with
    the placeholder the user caught in delivery 2.
    """

    document = shelf.materials_document()
    assert set(document) == {shelf.ROAD_MATERIAL, shelf.ROAD_SIDE_MATERIAL}
    members = set(writer.expected_level_members())
    for material in document.values():
        for key, value in material["Stages"][0].items():
            if not key.endswith("Map"):
                continue
            member = f"levels/{value.split('/levels/', 1)[1]}"
            assert member in members, (key, member)
            assert (writer.MOD_ROOT / member).is_file(), member
    assert not [m for m in members if "shelf" in m and m.endswith((".dae", ".cdae"))]


def test_no_tree_stands_in_the_road() -> None:
    """The corridor is clear, and the plant manifest says exactly what was taken out of it.

    The first road boot drove a car into a pine 18 m up the runout: the forest was planted
    before the road existed. Re-running the clearance plan on the shipped tree must find
    nothing left to remove, and the manifest's own record must match the census.
    """

    from examples.hot_potato_arena.level import forest_build

    level_root = writer.MOD_ROOT / writer.LEVEL_RELATIVE
    plan = shelf.forest_clearance_plan(level_root)
    still_there = {name: len(entry["removed"]) for name, entry in plan.items() if entry["removed"]}
    assert not still_there, still_there
    plant = forest_build.plant_manifest()
    record = plant["shelf_road_clearance"]
    assert record["removed_total"] == sum(record["by_species"].values()) == 565, record
    assert plant["instances_total"] == sum(plant["per_species"].values()) == 154686 - 565
    assert record["rule"]["amendment"] == "A6"
    # every species keeps instances: the clearance took a strip, not a species
    assert all(count > 0 for count in plant["per_species"].values())
    # and the bulk files still match the manifest that now describes them
    assert forest_build.verify(level_root) == {"missing": [], "changed": []}


def test_no_two_engine_objects_in_the_level_share_a_name_or_a_persistent_id() -> None:
    """Materials and scene objects share ONE global name and persistentId space.

    The level's own uniqueness gate compares scene records with each other and never with
    materials, and the first boot of this road fell straight through that hole: the road's
    deck material was called exactly what the MeshRoad is called, both ids were uuid5 of the
    same string, and the loader refused the road -- *"There is another object ... with either
    an identical name ... or identical persistentId (object has classname: 'material',
    expected classname: 'MeshRoad')"* -- in a level that otherwise loaded clean. This gate
    reads every materials file on disk and every scene record the writer renders, together.
    """

    level_root = writer.MOD_ROOT / writer.LEVEL_RELATIVE
    owners: dict[str, list[str]] = {}
    ids: dict[str, list[str]] = {}

    def claim(name: str | None, pid: str | None, where: str) -> None:
        if name:
            owners.setdefault(name, []).append(where)
        if pid:
            ids.setdefault(pid, []).append(where)

    for path in sorted(level_root.rglob("*.materials.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for key, entry in document.items():
            if isinstance(entry, dict):
                claim(
                    entry.get("name", key),
                    entry.get("persistentId"),
                    str(path.relative_to(level_root)),
                )
    for path, payload in writer.render_level().items():
        if not path.endswith(("items.level.json", ".prefab.json")):
            continue
        for line in payload.decode("utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                claim(record.get("name"), record.get("persistentId"), path)

    names_twice = {name: where for name, where in owners.items() if len(where) > 1}
    ids_twice = {pid: where for pid, where in ids.items() if len(where) > 1}
    assert not names_twice, sorted(names_twice.items())[:10]
    assert not ids_twice, sorted(ids_twice.items())[:10]
