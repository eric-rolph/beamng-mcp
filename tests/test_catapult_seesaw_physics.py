"""Static contracts for Charlie's Catapult Seesaw's physical mechanism.

These checks deliberately cover both the Blender-authored handoff and the
generated mod.  A source-only assertion would allow stale JBeam/Lua artifacts
to keep shipping the old kinematic board and scripted vehicle velocity.
"""

from __future__ import annotations

import importlib.util
import json
import re
import zipfile
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_ROOT = PACK_ROOT / "catapult_seesaw"
MOD_ID = "ericrolph_catapult_seesaw"
HANDOFF_PATH = MOD_ROOT / "authoring" / f"{MOD_ID}.handoff.json"
JBEAM_PATH = MOD_ROOT / "mod" / "vehicles" / MOD_ID / f"{MOD_ID}.jbeam"
RUNTIME_PATH = MOD_ROOT / "mod" / "lua" / "ge" / "extensions" / MOD_ID / "runtime.lua"
DIST_ZIP_PATH = MOD_ROOT / "dist" / "catapult_seesaw_ericrolph.zip"
UPDATE_ZIP_PATH = MOD_ROOT / "dist" / "repo_update" / "catapult_seesaw_ericrolph.zip"
PHYSICS_DAE_NAME = f"{MOD_ID}_physics_v3.dae"
OBSOLETE_DAE_NAMES = (
    f"{MOD_ID}.dae",
    f"{MOD_ID}_physics_v2.dae",
)

PHYSICAL_GROUPS = ("plank", "weight")
RELEASE_BREAK_GROUP = "catapult_weight_release"
FORBIDDEN_SUBJECT_ACTUATORS = (
    "launchSubject",
    "addSubjectVelocity",
    "teleportSubject",
    "applyClusterVelocityScaleAdd",
)


def _load_spec():
    module_spec = importlib.util.spec_from_file_location(
        "catapult_seesaw_physics_contract_spec", MOD_ROOT / "spec.py"
    )
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _load_artifacts() -> tuple[dict, dict]:
    handoff = json.loads(HANDOFF_PATH.read_text(encoding="utf-8"))
    document = json.loads(JBEAM_PATH.read_text(encoding="utf-8"))
    return handoff, document[MOD_ID]


def _without_lua_comments(source: str) -> str:
    """Remove comments while retaining quoted vehicle-Lua command strings."""

    source = re.sub(r"--\[\[.*?\]\]", "", source, flags=re.DOTALL)
    return re.sub(r"--[^\r\n]*", "", source)


def _assert_no_subject_actuator(source: str, *, artifact: str) -> None:
    code = _without_lua_comments(source)
    offenders = [
        name
        for name in FORBIDDEN_SUBJECT_ACTUATORS
        if re.search(rf"\b{re.escape(name)}\s*\(", code)
    ]
    assert not offenders, (
        f"{artifact} still prescribes the subject's motion via {offenders}; "
        "the falling weight and hinged plank must provide the impulse"
    )


def _handoff_self_collision(node: dict) -> bool:
    # Handoff fields use snake_case, while their generated JBeam equivalents
    # use BeamNG's camelCase spelling.
    return bool(node.get("self_collision", node.get("selfCollision", False)))


def _handoff_group_nodes(handoff: dict, group: str) -> list[dict]:
    return [node for node in handoff["nodes"] if node.get("group") == group]


def _jbeam_group_nodes(part: dict, group: str) -> list[list]:
    full_group = f"{MOD_ID}_{group}"
    return [row for row in part["nodes"][1:] if row[-1].get("group") == full_group]


def _group_triangles(rows: list, node_ids: set[str]) -> list[list]:
    return [row for row in rows if set(row[:3]) <= node_ids]


def test_catapult_behavior_never_prescribes_subject_motion() -> None:
    """Only the prop release may be scripted; the car's trajectory may not be."""

    spec = _load_spec()
    _assert_no_subject_actuator(spec.LUA_BEHAVIOR, artifact="spec.LUA_BEHAVIOR")
    assert "launch_up_mps" not in spec.BEHAVIOR
    assert "launch_forward_mps" not in spec.BEHAVIOR

    runtime = RUNTIME_PATH.read_text(encoding="utf-8")
    behavior_source = spec.LUA_BEHAVIOR.strip("\n")
    assert runtime.count(behavior_source) == 1, (
        "generated runtime is stale: it does not contain the canonical "
        "catapult behavior exactly once"
    )
    behavior_start = runtime.index("local behavior = {}")
    behavior_end = runtime.index("local function synchronizeInstallation", behavior_start)
    _assert_no_subject_actuator(
        runtime[behavior_start:behavior_end], artifact="generated behavior section"
    )
    _assert_no_subject_actuator(runtime, artifact="generated runtime")


@pytest.mark.parametrize("group", PHYSICAL_GROUPS)
def test_handoff_authors_dynamic_collision_cages(group: str) -> None:
    handoff, _ = _load_artifacts()
    nodes = _handoff_group_nodes(handoff, group)
    assert len(nodes) >= 4, f"{group} needs a real multi-node soft-body cage"

    contact_nodes = [node for node in nodes if node["collision"]]
    assert len(contact_nodes) >= 4, f"{group} has no usable collision surface"
    assert all(not node["fixed"] for node in contact_nodes)
    if group == "plank":
        assert all(not _handoff_self_collision(node) for node in contact_nodes), (
            "the wide plank must not collide with its own adjacent triangle nodes; "
            "that feedback made the unloaded lever bounce"
        )
    else:
        assert any(_handoff_self_collision(node) for node in contact_nodes), (
            "the counterweight's rubber impact face still needs self contact"
        )

    node_ids = {node["id"] for node in nodes}
    triangles = [
        triangle for triangle in handoff["triangles"] if set(triangle["nodes"]) <= node_ids
    ]
    assert len(triangles) >= 2, f"{group} needs node-contacting collision triangles"


def test_handoff_authors_dense_ten_short_ton_guided_counterweight() -> None:
    handoff, _ = _load_artifacts()
    weight_nodes = _handoff_group_nodes(handoff, "weight")
    total_weight = sum(float(node["weight"]) for node in weight_nodes)
    assert total_weight == pytest.approx(9_070.0, rel=0.005), (
        "the visual 10-short-ton casting must also be a 9,070 kg physical cage"
    )
    assert len(weight_nodes) >= 75, "the impact load must be spread over a dense cage"
    assert max(float(node["weight"]) for node in weight_nodes) < 200.0, (
        "multi-ton corner nodes behave like spring-loaded point hammers"
    )

    release_beams = [
        beam
        for beam in handoff["beams"]
        if beam.get("extra", {}).get("breakGroup") == RELEASE_BREAK_GROUP
    ]
    assert len(release_beams) == 17
    assert sum(beam["spec"] == "release_latch" for beam in release_beams) == 2
    assert sum(beam["spec"] == "rest_hold" for beam in release_beams) == 15
    assert all(
        float(handoff["beam_specs"][beam["spec"]]["beamSpring"]) > 0 for beam in release_beams
    )

    weight_ids = {node["id"] for node in weight_nodes}
    permanent_weight_beams = [beam for beam in handoff["beams"] if set(beam["nodes"]) <= weight_ids]
    assert permanent_weight_beams, "releasing the supports must not dissolve the weight cage"
    assert not [node for node in handoff["nodes"] if node.get("extra", {}).get("couplerTag")]


@pytest.mark.parametrize("group", PHYSICAL_GROUPS)
def test_generated_jbeam_preserves_physical_collision_groups(group: str) -> None:
    handoff, part = _load_artifacts()
    source_nodes = _handoff_group_nodes(handoff, group)
    generated_nodes = _jbeam_group_nodes(part, group)
    assert {row[0] for row in generated_nodes} == {node["id"] for node in source_nodes}

    contact_rows = [row for row in generated_nodes if row[-1]["collision"]]
    assert len(contact_rows) >= 4
    assert all(not row[-1]["fixed"] for row in contact_rows)
    if group == "plank":
        assert all(not row[-1]["selfCollision"] for row in contact_rows)
    else:
        assert any(row[-1]["selfCollision"] for row in contact_rows)

    node_ids = {row[0] for row in generated_nodes}
    assert len(_group_triangles(part["triangles"][1:], node_ids)) >= 2


def test_generated_jbeam_preserves_dense_weight_mass_release_and_vertical_guide() -> None:
    _, part = _load_artifacts()
    weight_rows = _jbeam_group_nodes(part, "weight")
    assert sum(float(row[-1]["nodeWeight"]) for row in weight_rows) == pytest.approx(
        9_070.0, rel=0.005
    )
    assert len(weight_rows) >= 75
    assert max(float(row[-1]["nodeWeight"]) for row in weight_rows) < 200.0

    release_rows = [
        row for row in part["beams"][1:] if row[-1].get("breakGroup") == RELEASE_BREAK_GROUP
    ]
    assert len(release_rows) == 17
    assert all(float(row[-1]["beamSpring"]) > 0 for row in release_rows)
    assert not [row for row in part["nodes"][1:] if row[-1].get("couplerTag")]

    rail_name = f"{MOD_ID}_weight_guide"
    assert part["rails"][rail_name]["links:"] == [f"{rail_name}_{index}" for index in range(5)]
    slider_rows = part["slidenodes"][1:]
    assert {row[0] for row in slider_rows} == {
        f"{MOD_ID}_weight_2_2_0",
        f"{MOD_ID}_weight_hook",
    }
    assert all(row[1] == rail_name and row[2] is True and row[3] is True for row in slider_rows)


def test_asymmetric_lever_authors_six_metre_drop_and_departure_geometry() -> None:
    spec = _load_spec()
    assert spec.COUNTERWEIGHT_MASS_KG == pytest.approx(9_070.0)
    assert spec.FREE_FALL_DISTANCE == pytest.approx(6.0, abs=0.02)
    assert spec.WEIGHT_BOTTOM_REST_Z - spec.SURFACE_REST_AT_WEIGHT == pytest.approx(6.0, abs=0.02)
    assert spec.PLANK_CAR_ARM + spec.PLANK_WEIGHT_ARM == pytest.approx(spec.PLANK_LENGTH)
    assert spec.PLANK_CAR_ARM / spec.PLANK_WEIGHT_ARM >= 1.5
    assert 0.0 < spec.GANTRY_Y < spec.PLANK_WEIGHT_ARM

    # A -32 degree plank is moving tangent to its circular arc, so the car
    # end's instantaneous departure vector is 58 degrees above horizontal.
    departure_angle_deg = 90.0 - abs(float(spec.FLING_STOP_ANGLE_DEG))
    assert 50.0 <= departure_angle_deg <= 65.0


def test_five_collinear_hinge_pins_are_preserved_in_handoff_and_jbeam() -> None:
    handoff, part = _load_artifacts()
    expected_ids = {f"{MOD_ID}_plank_hinge_{index}" for index in range(5)}
    pins = [node for node in handoff["nodes"] if node["id"] in expected_ids]
    assert {node["id"] for node in pins} == expected_ids
    assert all(node["fixed"] and not node["collision"] for node in pins)
    assert len({round(float(node["position"][1]), 5) for node in pins}) == 1
    assert len({round(float(node["position"][2]), 5) for node in pins}) == 1
    assert len({round(float(node["position"][0]), 5) for node in pins}) == 5

    generated = [row for row in part["nodes"][1:] if row[0] in expected_ids]
    assert {row[0] for row in generated} == expected_ids
    assert all(row[-1]["fixed"] and not row[-1]["collision"] for row in generated)


def test_direct_full_width_impact_bank_matches_the_structural_plank_rib() -> None:
    handoff, part = _load_artifacts()
    impact_spec = handoff["beam_specs"]["impact_transfer"]
    assert impact_spec["beamType"] == "|BOUNDED"
    assert impact_spec["beamLimitSpring"] == pytest.approx(1_000_000.0)
    assert impact_spec["beamLimitDamp"] == pytest.approx(12_000.0)
    assert impact_spec["beamLimitDampRebound"] == pytest.approx(30_000.0)

    expected_pairs = {
        frozenset(
            {
                f"{MOD_ID}_plank_{index}_6_bottom",
                f"{MOD_ID}_weight_striker_{index}",
            }
        )
        for index in range(5)
    }
    impact_beams = [beam for beam in handoff["beams"] if beam["spec"] == "impact_transfer"]
    assert {frozenset(beam["nodes"]) for beam in impact_beams} == expected_pairs
    assert all(
        float(beam["extra"]["shortBoundRange"]) == pytest.approx(5.70553778)
        for beam in impact_beams
    )

    node_by_id = {node["id"]: node for node in handoff["nodes"]}
    for pair in expected_pairs:
        plank_id = next(node_id for node_id in pair if "_plank_" in node_id)
        striker_id = next(node_id for node_id in pair if "_weight_striker_" in node_id)
        plank_node = node_by_id[plank_id]
        striker_node = node_by_id[striker_id]
        assert plank_node["weight"] == pytest.approx(80.0)
        assert striker_node["weight"] == pytest.approx(80.0)
        assert plank_node["position"][0] == pytest.approx(striker_node["position"][0])
        assert not plank_node["fixed"] and not striker_node["fixed"]

    generated_pairs = {
        frozenset(row[:2])
        for row in part["beams"][1:]
        if row[-1].get("beamType") == "|BOUNDED" and frozenset(row[:2]) in expected_pairs
    }
    assert generated_pairs == expected_pairs


def test_five_bounded_hydraulic_catchers_and_snubbers_arrest_rebound() -> None:
    handoff, part = _load_artifacts()
    spec = handoff["beam_specs"]["hydraulic_catcher"]
    assert spec["beamType"] == "|BOUNDED"
    assert spec["beamSpring"] == pytest.approx(0.0)
    assert float(spec["beamLimitSpring"]) > 0.0
    assert float(spec["beamLimitDamp"]) > 0.0
    assert float(spec["beamLimitDampRebound"]) >= float(spec["beamLimitDamp"])

    authored = [beam for beam in handoff["beams"] if beam.get("spec") == "hydraulic_catcher"]
    assert len(authored) == 5
    assert all("fling_catcher_anchor" in " ".join(beam["nodes"]) for beam in authored)

    snubbers = [beam for beam in handoff["beams"] if beam.get("spec") == "rebound_snubber"]
    assert len(snubbers) == 5
    snubber_spec = handoff["beam_specs"]["rebound_snubber"]
    assert snubber_spec["beamType"] == "|BOUNDED"
    assert float(snubber_spec["beamLimitDamp"]) > float(snubber_spec["beamLimitDampRebound"])
    assert all(beam["extra"]["longBoundRange"] == pytest.approx(6.5) for beam in snubbers)

    generated = [row for row in part["beams"][1:] if row[-1].get("beamType") == "|BOUNDED"]
    assert len(generated) == 15
    assert all(float(row[-1]["beamLimitSpring"]) > 0.0 for row in generated)
    assert all(float(row[-1]["beamLimitDampRebound"]) > 0.0 for row in generated)


def test_plank_and_weight_ship_as_separate_physical_flexbodies() -> None:
    handoff, part = _load_artifacts()
    expected = {
        f"{MOD_ID}_plank_mesh": ["plank"],
        f"{MOD_ID}_weight_mesh": ["weight"],
    }
    authored = {
        entry["mesh"]: entry["groups"] for entry in handoff["asset"].get("flexbodies_extra", [])
    }
    assert {name: authored.get(name) for name in expected} == expected

    generated = {row[0]: row[1] for row in part["flexbodies"][1:]}
    for mesh, groups in expected.items():
        assert generated.get(mesh) == [f"{MOD_ID}_{group}" for group in groups]

    # The moving components must not also spawn as disconnected TSStatic
    # parts over the node-bound flexbodies.
    static_part_names = {entry["name"] for entry in handoff.get("parts", [])}
    assert not ({"plank", "weight"} & static_part_names)


def test_repo_update_stages_the_exact_certified_release_archive() -> None:
    assert UPDATE_ZIP_PATH.read_bytes() == DIST_ZIP_PATH.read_bytes(), (
        "dist/repo_update is stale; upload the same certified archive that "
        "the lockfile and live test validated"
    )


def test_physics_flexbodies_use_a_cache_busted_collada_path() -> None:
    handoff, _ = _load_artifacts()
    expected_member = f"vehicles/{MOD_ID}/{PHYSICS_DAE_NAME}"
    assert handoff["visual"]["path"] == expected_member

    vehicle_root = MOD_ROOT / "mod" / "vehicles" / MOD_ID
    assert (vehicle_root / PHYSICS_DAE_NAME).is_file()
    for obsolete_name in OBSOLETE_DAE_NAMES:
        assert not (vehicle_root / obsolete_name).exists(), (
            f"obsolete Collada path {obsolete_name} can reuse a stale .cdae"
        )

    with zipfile.ZipFile(DIST_ZIP_PATH) as archive:
        members = set(archive.namelist())
    assert expected_member in members
    for obsolete_name in OBSOLETE_DAE_NAMES:
        assert f"vehicles/{MOD_ID}/{obsolete_name}" not in members
