"""Gates for the authored-JBeam escape hatch in ``proplib.prop_builder``.

``JBEAM_SECTIONS`` exists so a prop can carry the mechanisms the cage
compiler deliberately does not synthesise — ``rotators``, ``powertrain``,
``controller``, ``hydros`` — the way stock BeamNG props do. It is the one
physics input that arrives as opaque JSON, so it is also the one that can
name a node the cage no longer has. The engine's failure mode for that is
silent: a rotator whose ``node1:`` does not resolve is dropped, and the mod
ships a fan that simply never turns, with nothing in the log.

These tests pin the two properties that make the hatch safe: it may only
ADD sections, and every node/group reference in it is checked against the
measured cage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"


def load_prop_builder():
    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    from proplib import prop_builder

    return prop_builder


NODE_IDS = {"m_hub_front", "m_hub_rear", "m_yoke_arm_r", "m_deck_00"}
NODE_GROUPS = {"m_rotor", "m_blade"}

# The shape a real prop ships: a stock-pattern rotator table (header row plus
# modifier dicts plus one data row) and a motor block with a node list.
ROTATORS = [
    ["name", "[group]:", "node1:", "node2:", "nodeArm:", "wheelDir"],
    {"radius": 15.39},
    {"brakeTorque": 340000, "brakeSpring": 3000},
    ["fan_rotor", ["m_rotor"], "m_hub_front", "m_hub_rear", "m_yoke_arm_r", -1],
]
MOTOR = {
    "torqueReactionNodes:": ["m_hub_front", "m_hub_rear", "m_yoke_arm_r"],
    "maxRPM": 1760,
}


def check(section, value):
    load_prop_builder().check_jbeam_section_refs(section, value, NODE_IDS, NODE_GROUPS)


def test_a_well_formed_rotator_table_passes() -> None:
    check("rotators", ROTATORS)
    check("motor", MOTOR)


def test_multiple_group_entries_all_resolve() -> None:
    check(
        "rotators",
        [
            ["name", "[group]:", "node1:", "node2:", "nodeArm:", "wheelDir"],
            ["fan_rotor", ["m_rotor", "m_blade"], "m_hub_front", "m_hub_rear", "m_yoke_arm_r", -1],
        ],
    )


def test_sections_with_no_node_references_are_left_alone() -> None:
    # `controller` and `powertrain` name lua files and devices, not nodes.
    check("controller", [["fileName"], ["giantFan", {}]])
    check(
        "powertrain",
        [
            ["type", "name", "inputName", "inputIndex"],
            ["shaft", "shaft", "motor", 1, {"gearRatio": 40, "connectedWheel": "fan_rotor"}],
        ],
    )


@pytest.mark.parametrize(
    "column",
    ["node1:", "node2:", "nodeArm:"],
)
def test_an_unknown_node_in_any_node_column_raises(column: str) -> None:
    header = ["name", "[group]:", "node1:", "node2:", "nodeArm:", "wheelDir"]
    row = ["fan_rotor", ["m_rotor"], "m_hub_front", "m_hub_rear", "m_yoke_arm_r", -1]
    row[header.index(column)] = "m_renamed_in_blender"
    with pytest.raises(ValueError, match="unknown cage node: m_renamed_in_blender"):
        check("rotators", [header, row])


def test_an_unknown_node_group_raises() -> None:
    with pytest.raises(ValueError, match="empty node group: m_typo"):
        check(
            "rotators",
            [
                ["name", "[group]:", "node1:", "node2:", "nodeArm:", "wheelDir"],
                ["fan_rotor", ["m_typo"], "m_hub_front", "m_hub_rear", "m_yoke_arm_r", -1],
            ],
        )


def test_an_unknown_node_in_a_node_LIST_raises() -> None:
    with pytest.raises(ValueError, match="unknown cage node: m_gone"):
        check("motor", {"torqueReactionNodes:": ["m_hub_front", "m_gone"]})


def test_an_empty_node_list_raises() -> None:
    with pytest.raises(ValueError, match="must be a non-empty list"):
        check("motor", {"torqueReactionNodes:": []})


def test_a_non_string_node_reference_raises() -> None:
    with pytest.raises(ValueError, match="is not a node name"):
        check(
            "rotators",
            [
                ["name", "[group]:", "node1:", "node2:", "nodeArm:", "wheelDir"],
                ["fan_rotor", ["m_rotor"], 119, "m_hub_rear", "m_yoke_arm_r", -1],
            ],
        )


def test_a_reference_nested_in_a_modifier_dict_is_still_checked() -> None:
    # JBeam modifier dicts can carry node columns too; a walk that only
    # understood the table form would miss this one.
    with pytest.raises(ValueError, match="unknown cage node: m_nope"):
        check("rotators", [{"node1:": "m_nope"}])


def test_the_hatch_cannot_overwrite_a_generated_section(tmp_path: Path) -> None:
    """The clobber guard is what stops authored JSON shadowing measured geometry."""

    prop_builder = load_prop_builder()
    source = (PACK_ROOT / "proplib" / "prop_builder.py").read_text(encoding="utf-8")
    assert "JBEAM_SECTIONS may not overwrite a generated section" in source
    # And the generated names it must protect are the ones build_jbeam writes.
    for generated in ("nodes", "beams", "triangles", "flexbodies", "refNodes"):
        assert f'"{generated}"' in source, generated
    assert prop_builder.NODE_REF_KEYS  # the column list is non-empty


def test_controller_names_must_be_bare_lua_identifiers() -> None:
    source = (PACK_ROOT / "proplib" / "prop_builder.py").read_text(encoding="utf-8")
    assert "controller name is not a bare lua identifier" in source


def test_props_rows_are_gated_like_every_other_node_reference() -> None:
    """`props` carries idRef:/idX:/idY:, so it goes through the same gate.

    A `props` row whose anchor node was renamed in Blender fails exactly the
    way a rotator's does — the mesh is silently never placed — so the two
    share one validator rather than `props` being written straight in.
    """

    good = [
        ["func", "mesh", "idRef:", "idX:", "idY:", "min", "max"],
        ["fanSweep", "m_pointer", "m_hub_front", "m_hub_rear", "m_yoke_arm_r", -360, 360],
    ]
    check("props", good)

    bad = [row[:] for row in good]
    bad[1][2] = "m_renamed"
    with pytest.raises(ValueError, match="unknown cage node: m_renamed"):
        check("props", bad)


def test_props_cannot_be_declared_twice() -> None:
    source = (PACK_ROOT / "proplib" / "prop_builder.py").read_text(encoding="utf-8")
    assert "JBEAM_PROPS and JBEAM_SECTIONS['props'] both define props" in source
