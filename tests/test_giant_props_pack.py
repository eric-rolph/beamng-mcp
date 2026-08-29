"""Static structural gates for the Giant Props pack examples.

These tests validate the Blender-handoff evidence chain for every mod under
``examples/giant_props``: handoff/DAE hash integrity, JBeam consistency with
the handoff, cage connectivity, materials coverage, runtime Lua boilerplate,
and the deterministic distribution ZIP. They are static gates only — live
BeamNG behaviour still requires the opt-in live suites.
"""

from __future__ import annotations

import ast
import hashlib
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import numpy
import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
HANDOFF_SCHEMA = "ericrolph-giant-props-handoff-v1"
HARVEST_SCHEMA = "ericrolph-giant-props-harvest-v1"
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
# The smallest Contains trigger must still fully hold a compact car.
# The toaster redesign uses deliberately snug 3.0 m slot triggers (2.0 m
# car + 0.5 m margin each side); 2.9 still catches never-containable boxes.
MIN_CONTAINS_DIMENSIONS = (2.9, 4.5, 3.0)

MOD_KEYS = sorted(
    child.name for child in PACK_ROOT.iterdir() if child.is_dir() and (child / "spec.py").is_file()
)


def load_spec(mod_key: str):
    import importlib.util

    spec_path = PACK_ROOT / mod_key / "spec.py"
    loader_spec = importlib.util.spec_from_file_location(
        f"giant_props_test_spec_{mod_key}", spec_path
    )
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)
    return module


def load_handoff(mod_key: str) -> dict:
    spec = load_spec(mod_key)
    path = PACK_ROOT / mod_key / "authoring" / f"{spec.MOD_ID}.handoff.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_proplib():
    """Import proplib the way build.py does (pack root on sys.path)."""

    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    from proplib import prop_builder, texture_kit

    return prop_builder, texture_kit


def reject_constants(value: str) -> None:
    raise AssertionError(f"non-finite JSON constant: {value}")


def test_pack_has_all_mods() -> None:
    # 13 -> 17 (2026-08-10): pachinko_tower, belt_sander_trap,
    # sumo_gyro_platform and junk_chute_grinder. 17 -> 18 (2026-08-13):
    # football_goal_post. 18 -> 19 (2026-08-14): hot_potato. 19 -> 20
    # (2026-08-24): spin_launch. 20 -> 21 (2026-08-24): colossus_tire.
    # 21 -> 22 (2026-08-25): high_five - which first landed WITHOUT its bump,
    # so the tripwire fired in reverse: the suite was red for a mod ARRIVING.
    # 22 -> 23 (2026-08-25): giant_fan.
    # A tripwire for a mod silently dropping out of discovery, so it is
    # deliberately a literal - bump it by ONE for the mod you added, never to
    # whatever discovery happens to return.
    assert len(MOD_KEYS) == 23, MOD_KEYS


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_handoff_hashes_match_daes(mod_key: str) -> None:
    spec = load_spec(mod_key)
    handoff = load_handoff(mod_key)
    assert handoff["schema"] == HANDOFF_SCHEMA
    assert handoff["asset"]["id"] == spec.MOD_ID
    mod_root = PACK_ROOT / mod_key / "mod"
    visual_path = mod_root / handoff["visual"]["path"]
    digest = hashlib.sha256(visual_path.read_bytes()).hexdigest()
    assert handoff["visual"]["sha256"] == digest
    assert handoff["visual"]["size"] == visual_path.stat().st_size
    for part in handoff["parts"]:
        part_path = mod_root / part["path"]
        part_digest = hashlib.sha256(part_path.read_bytes()).hexdigest()
        assert part["sha256"] == part_digest, part["name"]


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_local_helpers_defined_before_use(mod_key: str) -> None:
    """No `local function` may be CALLED above its own definition.

    A Lua local binds at its definition point, so a helper placed above the
    function it calls resolves that name as a GLOBAL - nil - and blows up the
    first time that path actually runs, not at load. Nothing catches it
    earlier: the chunk compiles clean, and a lupa syntax gate passes.

    It has now cost two live rounds (sumo 2026-08-13 and again 2026-08-14,
    where a misplaced playCall took out both corner registration and the
    whole win path with "attempt to call global 'queueVehicleFx'"), so the
    ordering is checked here instead of remembered.
    """

    spec = load_spec(mod_key)
    runtime = (
        PACK_ROOT / mod_key / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID / "runtime.lua"
    )
    if not runtime.is_file():
        pytest.skip("no generated GE runtime")

    lines = runtime.read_text(encoding="utf-8").splitlines()
    # Comments and string bodies are not code; a name mentioned there is not
    # a call. Strip line comments, then blank out quoted spans.
    code = []
    for line in lines:
        line = re.sub(r"--.*$", "", line)
        line = re.sub(r'"[^"]*"', '""', line)
        code.append(line)

    defined_at: dict[str, int] = {}
    for number, line in enumerate(code):
        match = re.match(r"\s*local function (\w+)", line)
        if match and match.group(1) not in defined_at:
            defined_at[match.group(1)] = number

    offenders = []
    for name, definition in defined_at.items():
        for number in range(definition):
            if re.search(rf"(?<![\w.:]){re.escape(name)}\s*\(", code[number]):
                offenders.append(
                    f"{name}() called at line {number + 1}, defined at line {definition + 1}"
                )
                break
    assert not offenders, (
        f"{mod_key}: local helpers used before definition (nil at runtime): "
        + "; ".join(sorted(offenders))
    )


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_required_tunables_all_ship(mod_key: str) -> None:
    """Every key a mod's Lua declares REQUIRED must be in the shipped table.

    Behaviour CODE is read fresh from spec.py at build.py time, but behaviour
    PARAMS reach the runtime through the handoff, which only the BLENDER stage
    rewrites. So adding a tunable and rebuilding with build.py alone ships Lua
    that demands a key the table does not have - and a mod whose tunable check
    fails holds every part at its authored pose and never bakes its collision.

    That is not a subtle failure: it shipped once (sumo serial 30, 2026-08-14)
    and the player found cars falling THROUGH the arena and cloth hanging dead
    still, because the fault path had skipped both the collision bake and the
    wind seeding. Nothing downstream of the build can catch it, so it is
    caught here.
    """

    spec = load_spec(mod_key)
    runtime = (
        PACK_ROOT / mod_key / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID / "runtime.lua"
    )
    if not runtime.is_file():
        pytest.skip("no generated GE runtime")
    text = runtime.read_text(encoding="utf-8")
    if "local REQUIRED = {" not in text:
        pytest.skip("mod declares no REQUIRED tunables")

    def _block(marker: str) -> str:
        """The whole brace-balanced table, not up to the first close.

        colossus_tire is the first mod whose tunable table holds NESTED
        tables - a node-name list and a station triple - and stopping at the
        first `}` cut the block off after six of its twenty-three keys, so
        the gate reported fourteen tunables missing that were shipped three
        lines further down.
        """

        start = text.index(marker)
        depth = 0
        for offset in range(start + len(marker) - 1, len(text)):
            if text[offset] == "{":
                depth += 1
            elif text[offset] == "}":
                depth -= 1
                if depth == 0:
                    return text[start:offset]
        raise AssertionError(f"unterminated table after {marker!r}")

    required = set(re.findall(r'"(\w+)"', _block("local REQUIRED = {")))
    shipped = set(re.findall(r"(\w+) =", _block("local B = {")))
    missing = sorted(required - shipped)
    assert not missing, (
        f"{mod_key}: Lua requires tunables the shipped table lacks: {missing}. "
        "Re-run the Blender generator - a build.py-only rebuild cannot update "
        "the handoff."
    )


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_jbeam_matches_handoff(mod_key: str) -> None:
    spec = load_spec(mod_key)
    handoff = load_handoff(mod_key)
    jbeam_path = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID / f"{spec.MOD_ID}.jbeam"
    jbeam = json.loads(jbeam_path.read_text(encoding="utf-8"), parse_constant=reject_constants)
    part = jbeam[spec.MOD_ID]

    node_rows = part["nodes"][1:]
    handoff_nodes = {node["id"]: node for node in handoff["nodes"]}
    assert len(node_rows) == len(handoff_nodes)
    positions: dict[str, tuple[float, float, float]] = {}
    fixed_flags: dict[str, bool] = {}
    collision_flags: dict[str, bool] = {}
    node_options: dict[str, dict] = {}
    for row in node_rows:
        identifier, x, y, z, options = row
        source = handoff_nodes[identifier]
        assert [x, y, z] == source["position"]
        assert options["fixed"] == source["fixed"]
        assert options["collision"] == source["collision"]
        assert options["selfCollision"] is bool(source.get("self_collision", False))
        assert options["nodeWeight"] > 0
        positions[identifier] = (x, y, z)
        fixed_flags[identifier] = options["fixed"]
        collision_flags[identifier] = options["collision"]
        node_options[identifier] = options

    adjacency: dict[str, set[str]] = {identifier: set() for identifier in positions}
    for row in part["beams"][1:]:
        first, second, options = row
        assert first in positions and second in positions
        ax, ay, az = positions[first]
        bx, by, bz = positions[second]
        length = ((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2) ** 0.5
        assert length > 0.01, (first, second)
        if options.get("beamType") == "|BOUNDED":
            assert options["beamSpring"] >= 0
            assert options.get("beamLimitSpring", 0) > 0
            assert options.get("beamLimitDamp", 0) > 0
        else:
            assert options["beamSpring"] > 0
        adjacency[first].add(second)
        adjacency[second].add(first)

    # A locked coupler is a real graph edge even though JBeam represents it
    # as matching node options rather than a row in the beams section.
    tagged_nodes: dict[str, list[str]] = {}
    for identifier, options in node_options.items():
        tag = options.get("tag")
        if tag:
            tagged_nodes.setdefault(str(tag), []).append(identifier)
    for identifier, options in node_options.items():
        coupler_tag = options.get("couplerTag")
        if not coupler_tag or options.get("couplerLock") is not True:
            continue
        for target in tagged_nodes.get(str(coupler_tag), []):
            adjacency[identifier].add(target)
            adjacency[target].add(identifier)

    seen: set[str] = set()
    frontier = [next(iter(positions))]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(adjacency[current] - seen)
    assert seen == set(positions), "cage graph is disconnected"

    for row in part["triangles"][1:]:
        a, b, c, options = row
        assert len({a, b, c}) == 3
        assert {a, b, c} <= set(positions)
        assert options["groundModel"]

    refnodes = part["refNodes"][1]
    assert set(refnodes) <= set(positions)
    ref_position = positions[refnodes[0]]
    back_position = positions[refnodes[1]]
    assert back_position[1] > ref_position[1], "back refnode must sit at +Y"

    # AND THE TRIAD MUST BE RIGHT-HANDED, the same way for every prop. BeamNG
    # builds the spawn basis from this table, so a mirrored triad spawns the
    # prop flipped about its fore-aft axis with everything the player
    # approaches - ramps, doors, docks - on the wrong side. Twenty-two of the
    # twenty-three props agreed; colossus_tire alone came out mirrored, and
    # nothing downstream reported it because a runtime that maps authored
    # baselines onto live ones uses the same roles on both sides.
    left_position = positions[refnodes[2]]
    up_position = positions[refnodes[3]]
    to_back = [back_position[i] - ref_position[i] for i in range(3)]
    to_left = [left_position[i] - ref_position[i] for i in range(3)]
    to_up = [up_position[i] - ref_position[i] for i in range(3)]
    cross = [
        to_left[1] * to_back[2] - to_left[2] * to_back[1],
        to_left[2] * to_back[0] - to_left[0] * to_back[2],
        to_left[0] * to_back[1] - to_left[1] * to_back[0],
    ]
    handedness = sum(cross[i] * to_up[i] for i in range(3))
    assert handedness > 0.0, (
        f"{mod_key}: refNode triad is mirrored (cross(left-ref, back-ref) . (up-ref) "
        f"= {handedness:.2f}); every other prop in the pack is right-handed"
    )

    base_ids = handoff["base_nodes"]
    assert len(base_ids) >= 3
    min_z = min(z for (_x, _y, z) in positions.values())
    for identifier in base_ids:
        assert fixed_flags[identifier]
        assert positions[identifier][2] <= min_z + 0.06

    envelope = handoff["spawn_envelope_nodes"]
    assert len(envelope) == 8
    for identifier in envelope:
        assert collision_flags[identifier]

    flex_mesh, groups = part["flexbodies"][1]
    assert flex_mesh == handoff["asset"]["visual_mesh"]
    # The visual flexbody binds the handoff's authored visual_groups
    # (mod-prefixed) when a spec declares them, else the default physics
    # group - the same contract prop_builder implements. colossus_tire binds
    # its chock visual to four per-wedge groups so the skin never references
    # a fixed anchor.
    declared = handoff["asset"].get("visual_groups") or []
    expected = [f"{spec.MOD_ID}_{g}" for g in declared] if declared else [f"{spec.MOD_ID}_physics"]
    assert groups == expected


# The ref node IS the spawn datum. BeamNG places a vehicle by its BASE
# ORIGIN - the LOWEST node in the cage - and then reports ``origin`` from
# the REF node, so authoring the two at different heights lifts the entire
# prop by the difference. spin_launch shipped with its ref at the ramp foot
# (authored z 0) and its plinth deliberately "buried" at z -3.0; a prop
# cannot bury anything, so the plinth landed on the terrain and the approach
# ramp started 3 m in the air. Measured live 2026-08-24: origin.z == 3.0 for
# a prop spawned at surface z = 0, and a player could not drive onto the
# machine at all. Both refnode docstrings in proplib/blender_kit.py state
# this rule; nothing enforced it until now.
#
# 0.05 m is not arbitrary slop: it is the same window ``auto_base_nodes``
# uses to decide which nodes are ground ballast, so this asserts precisely
# "the ref node would qualify as a base node".
SPAWN_DATUM_TOLERANCE = 0.05

# Tombstones, deliberately NOT a widened tolerance. A tolerance big enough
# to admit a known 0.75 m failure cannot catch a 0.75 m regression, which is
# the whole class of bug this gate exists for. strict=True keeps the defect
# named in the code and turns the eventual fix into a FAILURE that forces
# the tombstone out.
SPAWN_DATUM_XFAIL = {
    "sumo_gyro_platform": (
        "datum_ref sits at z 0 (the arena floor) while the drain moat floor "
        "is MOAT_FLOOR_Z = -0.75, so the prop spawns 0.75 m in the air. The "
        "moat depth is itself derived - it clears the rim girder's lowest "
        "swept point at -0.554 m by 0.196 - so the fix is the same "
        "whole-machine re-datum spin_launch needed (+0.75 on every authored "
        "z), which means its own Blender run, its own hashes, its own zip "
        "lock and its own live gate. That belongs in its own change."
    ),
}


def _spawn_datum_params():
    return [
        pytest.param(
            key,
            marks=pytest.mark.xfail(strict=True, reason=SPAWN_DATUM_XFAIL[key]),
        )
        if key in SPAWN_DATUM_XFAIL
        else key
        for key in MOD_KEYS
    ]


@pytest.mark.parametrize("mod_key", _spawn_datum_params())
def test_reference_node_is_the_lowest_node(mod_key: str) -> None:
    """The ref node is the spawn datum, so it must be the lowest node.

    Read out of the SHIPPED jbeam rather than the handoff, because the jbeam
    is what BeamNG places the prop from; the handoff's own refnodes table is
    cross-checked against it here so the authoring evidence and the artifact
    cannot disagree about which node is the datum.
    """

    spec = load_spec(mod_key)
    handoff = load_handoff(mod_key)
    jbeam_path = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID / f"{spec.MOD_ID}.jbeam"
    jbeam = json.loads(jbeam_path.read_text(encoding="utf-8"), parse_constant=reject_constants)
    part = jbeam[spec.MOD_ID]

    positions = {row[0]: (row[1], row[2], row[3]) for row in part["nodes"][1:]}
    # A mod may AUTHOR an allowance for nodes that are buried below its
    # datum by design: colossus_tire's strap anchors are fixed, collisionless
    # tie-down points 0.6 m under grade that the release cuts away from.
    # The allowance is a named spec constant, not a flag heuristic, because
    # collision-false alone does not prove a node cannot matter to placement
    # (sumo_gyro_platform's moat floor is collision-false and still the
    # subject of a strict xfail about exactly that).
    buried_ok = tuple(getattr(spec, "SPAWN_DATUM_BURIED_OK", ()))
    if buried_ok:
        positions = {
            identifier: position
            for identifier, position in positions.items()
            if not any(marker in identifier for marker in buried_ok)
        }
    ref = part["refNodes"][1][0]
    assert ref == handoff["refnodes"]["ref"], (
        f"{mod_key}: shipped jbeam refNodes[0] is {ref!r} but the handoff "
        f"names {handoff['refnodes']['ref']!r}"
    )

    ref_z = positions[ref][2]
    min_z = min(z for (_x, _y, z) in positions.values())
    lift = ref_z - min_z
    lowest = sorted(
        identifier for identifier, (_x, _y, z) in positions.items() if z <= min_z + 1e-6
    )
    assert lift <= SPAWN_DATUM_TOLERANCE, (
        f"{mod_key}: ref node {ref!r} is authored {lift:.3f} m above the "
        f"lowest node (ref z {ref_z:.3f}, min z {min_z:.3f}). BeamNG places "
        f"by base origin, so this prop spawns {lift:.3f} m in the air and "
        f"nothing on it lands where it was authored. Lowest nodes: "
        f"{lowest[:4]}"
    )


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_panel_button_chain_is_wired_end_to_end(mod_key: str) -> None:
    """A console button is FOUR agreements, and nothing checked any of them.

    A press travels spec.PANEL_BUTTONS -> jbeam `triggers2` (the click box, on
    three named cage nodes) -> `triggerEventLinks2` (box id to input action) ->
    `actionsEnabled` -> the interaction json's `onDown`, which finally calls
    `pressPanelButtonByVehicle` on the doubled-underscore extension name. Break
    any single link and the cap is dead in the game.

    No gate could see that. The live gates call `pressPanelButtonByVehicle`
    directly - a mouse ray is not scriptable - so they prove what the button
    calls and never that anything calls the button. Six props ship a console.
    """

    spec = load_spec(mod_key)
    buttons = getattr(spec, "PANEL_BUTTONS", ())
    vehicle_root = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID
    interaction_path = vehicle_root / f"{spec.MOD_ID}_default.interaction.json"
    if not buttons:
        assert not interaction_path.is_file(), "interaction map with no PANEL_BUTTONS"
        pytest.skip("no console panel")
    if not vehicle_root.is_dir():
        pytest.skip("generated vehicle tree absent; run build.py <mod_key> all")
    assert interaction_path.is_file(), "PANEL_BUTTONS with no interaction map"

    part = json.loads(
        (vehicle_root / f"{spec.MOD_ID}.jbeam").read_text(encoding="utf-8"),
        parse_constant=reject_constants,
    )[spec.MOD_ID]
    node_ids = {row[0] for row in part["nodes"][1:]}
    boxes = {row[0]: row for row in part["triggers2"][1:]}
    links = {row[0]: row[2] for row in part["triggerEventLinks2"][1:]}
    enabled = {row[0] for row in part["actionsEnabled"][1:]}
    actions = json.loads(interaction_path.read_text(encoding="utf-8"))["actions"]
    # BeamNG doubles literal underscores before replacing the path separator.
    extension = f"{spec.MOD_ID}/runtime".replace("_", "__").replace("/", "_")

    expected_actions = set()
    for button in buttons:
        key = button["id"]
        box_id = f"panel_{key}"
        action_id = f"{spec.MOD_ID}_{key}"
        expected_actions.add(action_id)
        assert box_id in boxes, (mod_key, box_id, sorted(boxes))
        box = boxes[box_id]
        assert box[4] == "box", (mod_key, box_id, box[4])
        # idRef / idX / idY: a click box hangs off three real cage nodes.
        for column in (1, 2, 3):
            assert box[column] in node_ids, (mod_key, box_id, box[column])
        assert links.get(box_id) == action_id, (mod_key, box_id, links.get(box_id))
        assert box_id in enabled, (mod_key, box_id)
        action = actions.get(action_id)
        assert action is not None, (mod_key, action_id, sorted(actions))
        on_down = str(action["onDown"])
        assert f"extensions.{extension}.pressPanelButtonByVehicle" in on_down, (
            mod_key,
            action_id,
            on_down,
        )
        assert f"'{key}'" in on_down, (mod_key, action_id, on_down)
        assert action["title"] == button["title"], (mod_key, action_id)
    assert set(actions) == expected_actions, (mod_key, sorted(set(actions) ^ expected_actions))


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_materials_cover_all_referenced(mod_key: str) -> None:
    spec = load_spec(mod_key)
    handoff = load_handoff(mod_key)
    materials_path = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID / "main.materials.json"
    materials = json.loads(
        materials_path.read_text(encoding="utf-8"), parse_constant=reject_constants
    )
    referenced = set(handoff["visual"]["materials"])
    for part in handoff["parts"]:
        referenced.update(part["materials"])
    assert referenced <= set(materials)
    for name, definition in materials.items():
        assert definition["name"] == name
        assert definition["mapTo"] == name
        assert name.startswith(spec.MOD_ID)
        assert definition["version"] == 1.5
        stage0 = definition["Stages"][0]
        assert len(stage0["baseColorFactor"]) == 4
        for map_key in ("baseColorMap", "normalMap", "roughnessMap", "opacityMap"):
            game_path = stage0.get(map_key)
            if game_path is None:
                continue
            prefix = f"/vehicles/{spec.MOD_ID}/"
            assert game_path.startswith(prefix), (name, map_key, game_path)
            shipped = (
                PACK_ROOT
                / mod_key
                / "mod"
                / "vehicles"
                / spec.MOD_ID
                / game_path.removeprefix(prefix)
            )
            cooked = shipped.with_name(shipped.name.rsplit(".png", 1)[0] + ".dds")
            assert shipped.is_file() or cooked.is_file(), (name, map_key, str(shipped))
            if cooked.is_file():
                # Engine placeholder size = an unfinished cook was shipped.
                assert cooked.stat().st_size != 1398281, (name, map_key, "poisoned DDS")


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_translucent_palette_entries_emit_an_opacity_factor(mod_key: str) -> None:
    """THE OPACITY LAW, on every palette in the pack.

    ``baseColorFactor[3]`` is not read as opacity by BeamNG's v1.5 PBR
    material. The emitter declared ``translucent`` and left the number
    there, so ELEVEN materials across SIX props shipped fully opaque -
    including both panes of glass_atrium, a mod whose entire concept is
    glass. Proven live 2026-08-25 on spin_launch's velocity dial: as
    shipped it was a blank pale-blue disc; adding ``opacityFactor 0.12`` to
    stage 0 - and nothing else - made it a legible instrument.

    This gate reads the PALETTES and runs the emitter's own helper, not the
    shipped materials.json, and that is deliberate: an emitter fix reaches a
    prop only when that prop is next rebuilt, so a shipped-file gate would
    be answering "has this prop been rebuilt yet" instead of "is the law
    kept". The law is the emitter's, so it is tested where it lives - the
    same shape as test_builder_refuses_a_four_component_emissive_factor.
    """

    prop_builder, _ = load_proplib()
    spec = load_spec(mod_key)
    checked = 0
    for name, entry in spec.PALETTE.items():
        color = entry["color"]
        if float(color[3]) >= 1.0:
            continue
        checked += 1
        # The two branches build_materials picks between: a textured entry
        # tints its maps, an untextured one uses the colour outright. Both
        # carry the alpha, and both go through the same helper.
        if "texture" in entry:
            factor = list(entry.get("tint", [1.0, 1.0, 1.0, color[3]]))
        else:
            factor = list(color)
        stage0 = {"baseColorFactor": factor}
        prop_builder.move_alpha_to_opacity(stage0)
        # The raw passthrough is merged after the derived fields, so an entry
        # that states its own opacity still wins - and still satisfies this.
        stage0.update(entry.get("stage") or {})
        opacity = stage0.get("opacityFactor")
        assert opacity is not None, (
            f"{mod_key}: {name} is translucent (alpha {color[3]}) and emits no"
            " opacityFactor; baseColorFactor alpha is INERT for opacity and the"
            " material will render fully opaque in game"
        )
        assert 0.0 < float(opacity) <= 1.0, (mod_key, name, opacity)
        assert stage0["baseColorFactor"][3] == 1.0, (
            f"{mod_key}: {name} still carries its transparency in"
            f" baseColorFactor[3] ({stage0['baseColorFactor'][3]}), where"
            " nothing reads it"
        )
    if checked:
        print(f"{mod_key}: {checked} translucent material(s) checked")


def test_builder_moves_the_alpha_where_the_engine_reads_it() -> None:
    """The gate above is retroactive; this one pins the helper's behaviour."""

    prop_builder, _ = load_proplib()
    stage0 = {"baseColorFactor": [0.62, 0.70, 0.74, 0.12]}
    prop_builder.move_alpha_to_opacity(stage0)
    assert stage0 == {"baseColorFactor": [0.62, 0.70, 0.74, 1.0], "opacityFactor": 0.12}
    # IDEMPOTENT. Once the alpha is 1.0 there is nothing left to move, so a
    # second pass must not overwrite an opacity that is already correct.
    prop_builder.move_alpha_to_opacity(stage0)
    assert stage0["opacityFactor"] == 0.12
    # An opaque material is left completely alone - no stray opacityFactor 1.0
    # on the 200-odd materials in this pack that are not glass.
    opaque = {"baseColorFactor": [0.5, 0.5, 0.5, 1.0]}
    prop_builder.move_alpha_to_opacity(opaque)
    assert opaque == {"baseColorFactor": [0.5, 0.5, 0.5, 1.0]}
    # A stage that has no colour factor yet (never happens in build_materials,
    # but the helper must not invent one) is untouched.
    empty: dict = {}
    prop_builder.move_alpha_to_opacity(empty)
    assert empty == {}


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_emissive_factors_have_three_components(mod_key: str) -> None:
    """THE THREE-COMPONENT LAW: a 4-element ``emissiveFactor`` renders INERT.

    Measured 2026-08-15 on a calibration strip (AGENTS.md, "Round-16/17: the
    photometric ledger"): two cells differing ONLY in whether a fourth element
    is appended to ``[1, 1, 1]`` read sRGB 255.0 and sRGB 0.0 at midnight, and
    nothing rescues four - a 4-component cell carrying ``emissive: true`` AND
    ``emissiveIntensityNits: 1800`` still reads 0.0. All 486 emissiveFactor
    arrays in the shipped game write three.

    The pack wrote four by analogy with ``color``, which really is RGBA, and
    eight materials across four mods shipped dark for months while the pack's
    own documentation recorded the wrong law ("emissive is inert on this
    pipeline"). This gate reads the SHIPPED materials.json rather than the
    palette, so it also covers the ``stage`` raw-key passthrough - the door
    prop_builder.check_emissive_factor closes at build time.
    """

    spec = load_spec(mod_key)
    materials_path = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID / "main.materials.json"
    materials = json.loads(
        materials_path.read_text(encoding="utf-8"), parse_constant=reject_constants
    )
    for name, definition in materials.items():
        for index, stage in enumerate(definition["Stages"]):
            factor = stage.get("emissiveFactor")
            if factor is None:
                continue
            assert isinstance(factor, list), (name, index, factor)
            assert len(factor) == 3, (
                f"{name} stage {index}: emissiveFactor {factor} has {len(factor)}"
                " components; only three emit"
            )


def test_builder_refuses_a_four_component_emissive_factor() -> None:
    """The gate above is retroactive; this one stops the bug being re-authored."""

    prop_builder, _ = load_proplib()
    stages = [{"emissiveFactor": [1.0, 0.55, 0.08, 1.0]}, {}, {}, {}]
    with pytest.raises(ValueError, match="only THREE emit"):
        prop_builder.check_emissive_factor("mod", "beacon_amber", stages)
    # Three passes, and a runtime dynamic-texture reference is not an array.
    prop_builder.check_emissive_factor("mod", "ok", [{"emissiveFactor": [1.0, 0.55, 0.08]}, {}])
    prop_builder.check_emissive_factor("mod", "no_emissive", [{"metallicFactor": 0.0}, {}])


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_runtime_lua_boilerplate(mod_key: str) -> None:
    spec = load_spec(mod_key)
    runtime_path = (
        PACK_ROOT / mod_key / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID / "runtime.lua"
    )
    source = runtime_path.read_text(encoding="utf-8")
    for required in (
        "M.registerProp = registerProp",
        "M.onBeamNGTrigger = onBeamNGTrigger",
        "M.onPreRender = onPreRender",
        "M.onVehicleResetted = onVehicleResetted",
        "M.onClientEndMission = onClientEndMission",
        'triggerTestType", 0, "Bounding box"',
        "behavior.update",
    ):
        assert required in source, required
    assert "modScript" not in source
    # Balanced long-string/function structure smoke: equal counts of
    # ``function`` keywords and closing ``end`` keywords is necessary (not
    # sufficient) for well-formed Lua.
    functions = len(re.findall(r"\bfunction\b", source))
    ends = len(re.findall(r"\bend\b", source))
    assert ends >= functions

    bootstrap_path = (
        PACK_ROOT
        / mod_key
        / "mod"
        / "vehicles"
        / spec.MOD_ID
        / "lua"
        / f"{spec.MOD_ID}_vehicle.lua"
    )
    bootstrap = bootstrap_path.read_text(encoding="utf-8")
    expected_extension = f"{spec.MOD_ID}/runtime".replace("_", "__").replace("/", "_")
    assert expected_extension in bootstrap


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_trigger_specs_are_sane(mod_key: str) -> None:
    handoff = load_handoff(mod_key)
    triggers = handoff["behavior"]["triggers"]
    assert triggers, "every contraption declares at least one trigger"
    for name, trigger in triggers.items():
        assert trigger["mode"] in ("Contains", "Overlaps"), name
        dimensions = trigger["dimensions"]
        assert all(value > 0 for value in dimensions), name
        if trigger["mode"] == "Contains":
            for actual, minimum in zip(dimensions, MIN_CONTAINS_DIMENSIONS, strict=True):
                assert actual >= minimum, (name, dimensions)


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_distribution_zip_matches_lock(mod_key: str) -> None:
    spec = load_spec(mod_key)
    dist_root = PACK_ROOT / mod_key / "dist"
    zip_path = dist_root / spec.ZIP_BASENAME
    lock_path = dist_root / f"{spec.MOD_ID}.lock.json"
    if not zip_path.is_file():
        pytest.skip("distribution ZIP absent (gitignored); run build.py <mod_key> dist")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    payload = zip_path.read_bytes()
    assert lock["sha256"] == hashlib.sha256(payload).hexdigest()
    assert lock["size"] == len(payload)
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        assert len(names) == lock["members"]
        for name in names:
            root = name.split("/", 1)[0]
            assert root in APPROVED_ROOTS, name
            assert "README" not in name
            assert not name.endswith((".py", ".json.bak"))
        infos = archive.infolist()
        assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_only_declared_assets_ship(mod_key: str) -> None:
    """assets/ is build inputs + a declared few runtime files, never a blind copy.

    A blind rglob once shipped boot_of_doom's 3.6 MB hero .glb and a second,
    unreferenced copy of its three baked maps (~11 MB of a 42 MB zip). Build
    inputs must never reach a player's disk: the spec declares exactly what
    ships via SHIP_ASSETS, and .glb is not a runtime format at all.
    """

    spec = load_spec(mod_key)
    assets_root = PACK_ROOT / mod_key / "assets"
    vehicle_root = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID
    declared = {rel.replace("\\", "/") for rel in getattr(spec, "SHIP_ASSETS", ())}
    if not vehicle_root.is_dir():
        pytest.skip("generated vehicle tree absent; run build.py <mod_key> all")
    if assets_root.is_dir():
        for source in assets_root.rglob("*"):
            if not source.is_file():
                continue
            rel = source.relative_to(assets_root).as_posix()
            staged = (vehicle_root / rel).is_file()
            if rel in declared:
                assert staged, f"declared asset never staged: {rel}"
            else:
                assert not staged, f"undeclared asset shipped: {rel}"
    for rel in declared:
        assert (assets_root / rel).is_file(), f"SHIP_ASSETS entry missing: {rel}"
    zip_path = PACK_ROOT / mod_key / "dist" / spec.ZIP_BASENAME
    if zip_path.is_file():
        with zipfile.ZipFile(zip_path) as archive:
            assert not [n for n in archive.namelist() if n.endswith((".glb", ".gltf", ".blend"))]


def test_texture_seeds_are_stable_across_processes() -> None:
    """The pack's procedural families must be reproducible between builds.

    ``_rng`` used to seed from ``hash(("giant_props", name))``, and Python
    randomizes str hashing per process, so every ``build.py <key> textures``
    drew a different noise instance for every texture in the pack. That is
    the root of the cooked-DDS harvest trap: a harvested DDS is a bake of
    one specific PNG, and NO staleness check — mtime or content hash — can
    preserve a bake whose source never reproduces.

    This assertion has to cross a PROCESS boundary. Within a single
    interpreter ``hash()`` is perfectly stable, so an in-process version of
    this test passed happily all the way through the bug.
    """

    program = (
        f"import sys; sys.path.insert(0, {str(PACK_ROOT)!r})\n"
        "from proplib.texture_kit import _rng\n"
        "print(_rng('ericrolph_probe').integers(0, 2**31, size=4).tolist())\n"
    )
    draws = {
        subprocess.run(  # noqa: S603 - fixed program text, this interpreter
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for _ in range(3)
    }
    assert len(draws) == 1, f"seed varies between processes: {draws}"


def test_cooked_harvest_survives_a_texture_rebuild(tmp_path: Path) -> None:
    """A certified cooked DDS must still ship after the textures are rebuilt.

    THE TRAP (observed 2026-08-13). The staleness guard compared mtimes,
    but ``ensure_textures`` re-saved every PNG on every run, so any build
    after a harvest made every cooked DDS look stale forever and the mod
    silently reverted to shipping raw PNGs — rebuilding whale_geyser swapped
    all 12 .dds for .png and dropped its zip from 7,230,941 to 4,816,662
    bytes. Two other mods had already lost their harvests the same way with
    no diagnostic on any build.

    Both halves of the intent are pinned here: a regenerated-but-identical
    source keeps its bake, and an actually-edited source loses it (the
    centrifuge bug, where a July bake shadowed three rounds of later texture
    work and the player kept re-reporting the same "digital camo").
    """

    prop_builder, texture_kit = load_proplib()
    mod_id = "harvest_probe"
    textures = tmp_path / "textures"
    cooked_dir = tmp_path / "textures_cooked"
    cooked_dir.mkdir()

    manifest = texture_kit.build_set(textures, mod_id, "concrete", size=64)
    map_names = [manifest[key] for key in ("baseColorMap", "normalMap", "roughnessMap")]
    # Stand-ins for the engine's bake: content is irrelevant to the guard,
    # only the recorded correspondence to a source PNG is.
    for name in map_names:
        (cooked_dir / (name.rsplit(".png", 1)[0] + ".dds")).write_bytes(b"DDS " + name.encode())
    prop_builder.write_harvest_manifest(tmp_path, mod_id)

    def still_cooked(name: str) -> bool:
        cooked = cooked_dir / (name.rsplit(".png", 1)[0] + ".dds")
        record = prop_builder.load_harvest_manifest(tmp_path, mod_id).get(cooked.name)
        return prop_builder.cooked_is_current(cooked, textures / name, record)

    assert all(still_cooked(name) for name in map_names)

    # A texture rebuild — the exact operation that used to invalidate
    # everything — must be a no-op for the harvest.
    texture_kit.build_set(textures, mod_id, "concrete", size=64)
    for name in map_names:
        assert still_cooked(name), f"harvest invalidated by a plain rebuild: {name}"

    # Validity must be indifferent to MTIME specifically, not merely
    # protected by writes that happen to leave it alone. Moving every source
    # timestamp past its bake is precisely what an unconditional re-save did,
    # and it must not retire a single DDS.
    future = time.time() + 3600
    for name in map_names:
        os.utime(textures / name, (future, future))
    for name in map_names:
        assert still_cooked(name), f"harvest invalidated by an mtime bump alone: {name}"

    # Nor may a RE-ENCODE retire one, and this used to be the whole of the
    # "a real edit" case - which it never was: appending a null byte moves the
    # file bytes and stops at IEND, so not one pixel changes. MEASURED
    # 2026-08-15: this box carries four Python installations with different
    # Pillow builds, and running the suite under a second one re-encoded 145 of
    # pachinko_tower's PNGs to different bytes with max |pixel delta| 0. That
    # retired all 130 of its harvest records in one step, and no harvest run
    # could repair it because the re-harvest would have been re-encoded again.
    # A generated texture's identity is its DECODED IMAGE.
    from PIL import Image

    reencoded = textures / map_names[0]
    with Image.open(reencoded) as image:
        pixels_before = image.tobytes()
    reencoded.write_bytes(reencoded.read_bytes() + b"\x00")  # bytes move
    with Image.open(reencoded) as image:
        assert image.tobytes() == pixels_before  # pixels do not
    assert still_cooked(map_names[0]), "a re-encode retired a valid bake"

    # ...but a real edit to the source - one that moves a PIXEL - must still
    # retire its bake. This is the centrifuge bug, and it is the half of the
    # guard that has teeth.
    edited = textures / map_names[0]
    with Image.open(edited) as image:
        array = numpy.asarray(image.convert("RGB")).copy()
    array[0, 0] = 255 - array[0, 0]
    Image.fromarray(array).save(edited)
    assert not still_cooked(map_names[0]), "edited source kept its stale bake"
    assert all(still_cooked(name) for name in map_names[1:])


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_shipped_cooked_dds_comes_from_the_harvest(mod_key: str) -> None:
    """Every .dds in a shipped tree is a byte copy of a textures_cooked/ file.

    Keeps the shipped bakes traceable: a DDS with no counterpart in the
    example's harvest folder came from somewhere nobody can re-derive.
    """

    spec = load_spec(mod_key)
    shipped_dir = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID / "textures"
    cooked_dir = PACK_ROOT / mod_key / "textures_cooked"
    for shipped in sorted(shipped_dir.glob("*.dds")):
        source = cooked_dir / shipped.name
        assert source.is_file(), f"shipped DDS is not in the harvest: {shipped.name}"
        assert source.read_bytes() == shipped.read_bytes(), shipped.name


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_distribution_has_no_future_dated_member(mod_key: str) -> None:
    """No shipped ZIP member may be stamped later than now.

    THE FUTURE-DATE TRAP (2026-08-14, pachinko_tower build 34). BeamNG
    re-cooks a source whose timestamp is newer than its cooked cache entry,
    and binds ``core/art/importingMat.dds`` — the green "IMPORTING TEXTURE"
    checkerboard — while that cook is in flight. ``_serial_timestamp`` used
    to stamp members ``2026-08-01 + serial DAYS``, which overtakes the
    calendar for any mod past roughly a serial a day: pachinko at serial 34
    was stamped three weeks ahead, the published centrifuge at serial 147 was
    stamped four months ahead. A future-dated source is newer than a cache
    the engine writes NOW and stays newer forever, so the cook never
    converges.

    Proven live, cold isolated profile, dx11 windowed, texture bytes held
    fixed and only the member date changed:

        dated 2026-09-04 -> 267 cook starts rising to 652 across 85
                            textures, ``steel.color`` re-imported 37x,
                            the whole prop on IMPORTING TEXTURE
        dated 2026-08-01 -> 84 cook starts, exactly one per texture,
                            every surface correct

    This is the gate that would have caught it without a human looking at
    the game. It replaces ``test_built_tree_ships_no_uncooked_texture``,
    which enforced the falsified "raw PNGs are the problem" theory and cost
    3x the download for nothing.
    """

    spec = load_spec(mod_key)
    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    from proplib import packaging

    zip_path = PACK_ROOT / mod_key / "dist" / spec.ZIP_BASENAME
    if not zip_path.is_file():
        pytest.skip("no built distribution")
    with zipfile.ZipFile(zip_path) as archive:
        late = packaging.future_dated_members(archive)
    assert not late, (
        f"{mod_key}: {len(late)} ZIP member(s) dated in the future; BeamNG will "
        f"re-cook them forever and the player sees IMPORTING TEXTURE. {late[:4]}"
    )


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_harvest_manifest_is_well_formed(mod_key: str) -> None:
    """If a harvest manifest exists it must describe the files that are there.

    A sha256 certifies IDENTITY, not usefulness: an empty file has a perfectly
    valid digest, so ``steel.normal.dds`` was once harvested at ZERO BYTES (a
    live session whose log ends mid-import on exactly that texture) and the
    manifest certified it. Every harvested DDS is therefore also checked for
    the ``DDS `` magic, a 124-byte header, real surface data behind it, and
    for not being the engine's 1,398,281-byte IMPORTING TEXTURE placeholder.
    """

    prop_builder, _ = load_proplib()
    example_root = PACK_ROOT / mod_key
    spec = load_spec(mod_key)
    path = prop_builder.harvest_manifest_path(example_root, spec.MOD_ID)
    if not path.is_file():
        pytest.skip("no cooked-DDS harvest manifest")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema"] == HARVEST_SCHEMA
    assert document["mod_id"] == spec.MOD_ID
    for cooked_name, record in document["textures"].items():
        cooked = example_root / "textures_cooked" / cooked_name
        assert cooked.is_file(), f"manifest records a missing DDS: {cooked_name}"
        blob = cooked.read_bytes()
        assert record["dds_sha256"] == hashlib.sha256(blob).hexdigest()
        assert len(blob) > 148, f"harvested DDS has no surface data: {cooked_name}"
        assert blob[:4] == b"DDS ", f"harvested DDS has no DDS magic: {cooked_name}"
        assert int.from_bytes(blob[4:8], "little") == 124, (
            f"harvested DDS has a malformed header: {cooked_name}"
        )
        assert len(blob) != 1398281, (
            f"harvested DDS is the engine's IMPORTING TEXTURE placeholder: {cooked_name}"
        )
        assert (example_root / "textures" / record["source"]).is_file()
        assert len(record["source_sha256"]) == 64


# Tombstone, same discipline as SPAWN_DATUM_XFAIL: strict=True keeps the
# defect named in the code until the re-harvest forces it out.
HARVEST_DRIFT_XFAIL = {
    "pachinko_tower": (
        "The harvest was certified 2026-08-15; the shared texture_kit "
        "primitives changed underneath it on 2026-08-25 (a7592a1: _blur, "
        "_streaks, stamped_mark and friends reworked for Spin Launch) and "
        "2026-08-26 (b6524dc, High Five), so the sandboxed rebuild "
        "regenerates at least plate_maker.color.png (family panel_legend) "
        "with a different source hash and cooked_is_current() correctly "
        "refuses the DDS. The certified cook is STALE, not wrong: the "
        "shipped zip still carries exactly the DDS bytes the manifest "
        "records. The fix is a re-harvest and re-cut of pachinko_tower - "
        "its own textures run, its own manifest, its own zip lock - not a "
        "wider gate. Found 2026-08-29 by the washer-merge gate sweep."
    ),
}


def _harvest_drift_params():
    return [
        pytest.param(
            key,
            marks=pytest.mark.xfail(strict=True, reason=HARVEST_DRIFT_XFAIL[key]),
        )
        if key in HARVEST_DRIFT_XFAIL
        else key
        for key in MOD_KEYS
    ]


@pytest.mark.parametrize("mod_key", _harvest_drift_params())
def test_certified_harvest_still_ships_dds(mod_key: str, tmp_path) -> None:
    """A mod whose harvest validates must still select DDS after a rebuild.

    The live counterpart of ``test_cooked_harvest_survives_a_texture_rebuild``.
    ``ensure_textures`` is the mutating half of a ``build.py <key> textures``
    run.

    IT RUNS IN A COPY NOW, and until round 3 it ran ON THE CHECKED-IN TREE.
    The justification for that was that the generators are seed-stable and
    the writes are byte-compared, so the call is a proven no-op - which is
    the *property this test exists to verify*. It is not available as a
    premise. And it is not even true unconditionally: the 145-PNG incident
    was this exact call, on this exact tree, under a different Pillow build,
    rewriting 145 files and invalidating all 130 harvest records. A test
    that can destroy the artefact it is checking has to be sandboxed, and
    the sandbox costs one directory copy.
    Skips until a mod has a certified harvest — a re-harvest in game arms
    this gate automatically.
    """

    prop_builder, _ = load_proplib()
    live_root = PACK_ROOT / mod_key
    spec = load_spec(mod_key)
    harvest = prop_builder.load_harvest_manifest(live_root, spec.MOD_ID)
    if not harvest:
        pytest.skip("no certified cooked-DDS harvest")

    example_root = tmp_path / "tree"
    example_root.mkdir()
    # `assets` is an INPUT here, not an output: an "external" palette family
    # (boot_of_doom's baked hero maps) stages checked-in files from it, so a
    # sandbox without it makes ensure_textures raise instead of rebuilding.
    for sub_dir in ("textures", "textures_cooked", "assets"):
        if (live_root / sub_dir).is_dir():
            shutil.copytree(live_root / sub_dir, example_root / sub_dir)
    before = {
        p.name: prop_builder.sha256_pixels(p)
        for p in sorted((live_root / "textures").glob("*.png"))
    }

    prop_builder.ensure_textures(example_root, spec)

    # The live tree must be byte-identical afterwards. Stated as a distinct
    # assertion rather than as a premise in the docstring.
    after = {
        p.name: prop_builder.sha256_pixels(p)
        for p in sorted((live_root / "textures").glob("*.png"))
    }
    assert before == after, "the sandboxed rebuild reached the live tree"

    for cooked_name, record in harvest.items():
        cooked = example_root / "textures_cooked" / cooked_name
        fresh = example_root / "textures" / record["source"]
        assert prop_builder.cooked_is_current(cooked, fresh, record), (
            f"{cooked_name} was invalidated by a texture rebuild"
        )


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_vehicle_metadata(mod_key: str) -> None:
    spec = load_spec(mod_key)
    vehicle_root = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID
    info = json.loads((vehicle_root / "info.json").read_text(encoding="utf-8"))
    assert info["Type"] == "Prop"
    assert info["Name"] == spec.DISPLAY_NAME
    pc = json.loads((vehicle_root / "standard.pc").read_text(encoding="utf-8"))
    assert pc["mainPartName"] == spec.MOD_ID
    assert (vehicle_root / "default.jpg").is_file()


# ---------------------------------------------------------------------------
# THE TEXTURE WRITER ITSELF.
#
# Round 3 found that ZERO tests touched `_save_stable`, `_same_pixels` or
# `sha256_pixels`. The law they implement was covered - a fixture wrote two
# PNGs with PIL directly and checked that the harvest survived - but the
# functions that enforce it were not, so the fixture exercised PIL and the
# guard went untested. These four are the guard.
# ---------------------------------------------------------------------------


def _png(pixels, compress_level: int = 6) -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG", compress_level=compress_level)
    return buffer.getvalue()


def test_save_stable_leaves_a_re_encoded_identical_image_alone(tmp_path: Path) -> None:
    """THE 145-PNG INCIDENT, in one test.

    Two encodings of the SAME pixels at different compression levels differ in
    file bytes and not at all in image. `_save_stable` must not write, must not
    move the mtime, and must not invalidate a bake.
    """

    _, texture_kit = load_proplib()
    from PIL import Image

    pixels = numpy.zeros((32, 32, 3), dtype=numpy.uint8)
    pixels[8:24, 8:24] = (200, 30, 40)
    target = tmp_path / "t.png"
    target.write_bytes(_png(pixels, compress_level=1))
    before_bytes = target.read_bytes()
    before_mtime = target.stat().st_mtime_ns

    # compress_level 9 encodes the same image to different bytes.
    assert _png(pixels, 9) != before_bytes
    texture_kit._save_stable(Image.fromarray(pixels), target)

    assert target.read_bytes() == before_bytes, "an identical image was rewritten"
    assert target.stat().st_mtime_ns == before_mtime, "mtime moved on a no-op write"


def test_save_stable_does_write_a_one_bit_change(tmp_path: Path) -> None:
    """The other half. A guard that never writes is not a guard."""

    _, texture_kit = load_proplib()
    from PIL import Image

    pixels = numpy.zeros((32, 32, 3), dtype=numpy.uint8)
    target = tmp_path / "t.png"
    target.write_bytes(_png(pixels))
    pixels[0, 0, 0] = 1
    texture_kit._save_stable(Image.fromarray(pixels), target)
    with Image.open(target) as got:
        assert numpy.asarray(got)[0, 0, 0] == 1


def test_same_pixels_separates_image_identity_from_byte_identity() -> None:
    _, texture_kit = load_proplib()

    a = numpy.zeros((16, 16, 3), dtype=numpy.uint8)
    b = a.copy()
    b[3, 3, 1] = 255
    assert texture_kit._same_pixels(_png(a, 1), _png(a, 9)) is True
    assert texture_kit._same_pixels(_png(a), _png(b)) is False
    # Size and mode are part of identity.
    wide = numpy.zeros((16, 32, 3), dtype=numpy.uint8)
    assert texture_kit._same_pixels(_png(a), _png(wide)) is False
    grey = numpy.zeros((16, 16), dtype=numpy.uint8)
    assert texture_kit._same_pixels(_png(a), _png(grey)) is False


def test_sha256_pixels_does_not_degrade_into_the_law_it_guards(tmp_path: Path) -> None:
    """THE INVERTED GUARD.

    `sha256_pixels` used to answer any exception at all with `sha256_file`,
    which is the *byte* identity the whole law exists to reject. So a Pillow
    that could open a file but not decode it would silently put the harvest
    back on file bytes and invalidate every bake - reporting success. The
    fallback is now narrow: a genuine non-image falls back, a broken image
    raises.
    """

    prop_builder, _ = load_proplib()

    pixels = numpy.zeros((16, 16, 3), dtype=numpy.uint8)
    pixels[4:12, 4:12] = 77
    one = tmp_path / "one.png"
    two = tmp_path / "two.png"
    one.write_bytes(_png(pixels, 1))
    two.write_bytes(_png(pixels, 9))
    assert one.read_bytes() != two.read_bytes()
    assert prop_builder.sha256_pixels(one) == prop_builder.sha256_pixels(two)
    assert prop_builder.sha256_file(one) != prop_builder.sha256_file(two)

    # A genuine non-image: fall back, that is the right answer for it.
    plain = tmp_path / "notes.txt"
    plain.write_bytes(b"not an image")
    assert prop_builder.sha256_pixels(plain) == prop_builder.sha256_file(plain)

    # A PNG whose header parses and whose data does not. This MUST raise.
    broken = tmp_path / "broken.png"
    broken.write_bytes(one.read_bytes()[:60])
    with pytest.raises(Exception) as caught:
        prop_builder.sha256_pixels(broken)
    assert not isinstance(caught.value, AssertionError)


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_generator_is_import_safe(mod_key: str) -> None:
    """Every generator's ``main()`` must stay behind an ``__main__`` guard.

    All 19 generators used to end in a bare, unguarded ``main()``, so merely
    IMPORTING one ran a full build. That is not hypothetical: on 2026-08-18 a
    read-only inspection script did ``spec_from_file_location`` + ``exec_module``
    on the pachinko generator to dump bounding boxes and silently rewrote 8
    .dae files, the handoff and the thumbnail. This tree has no version
    control, so there was nothing to revert to.

    The guard costs nothing on the build path - Blender sets ``__name__`` to
    ``"__main__"`` for ``--python`` scripts - but it is one line, and one line
    is exactly what a future edit drops without noticing. This test is the
    tripwire, so the next regression is caught here instead of by another
    destroyed baseline.
    """

    generator = PACK_ROOT / mod_key / "blender" / f"create_{mod_key}.py"
    assert generator.is_file(), generator
    tree = ast.parse(generator.read_text(encoding="utf-8"))

    bare = [
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "main"
    ]
    assert not bare, f"unguarded module-level main() in {generator.name} at line(s) {bare}"

    guarded = [
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        and any(
            isinstance(inner, ast.Expr)
            and isinstance(inner.value, ast.Call)
            and isinstance(inner.value.func, ast.Name)
            and inner.value.func.id == "main"
            for inner in node.body
        )
    ]
    assert guarded, f'{generator.name} has no `if __name__ == "__main__":` calling main()'


# ---------------------------------------------------------------------------
# Gates added 2026-08-25 after the colossus_tire critic round. Every one of
# these exists because something shipped past the other 26 checks.
# ---------------------------------------------------------------------------
def _triangle_normal(points):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_fixed_surfaces_are_not_one_way_floors(mod_key: str) -> None:
    """A fixed horizontal surface must have at least as much UP area as DOWN.

    jbeam collision triangles are one-sided. A deck whose corner order happens
    to wind the other way is an invisible floor that only collides from
    underneath, and a car drives straight through it - which is exactly what
    colossus_tire's 13 m loading ramp did, past every other gate here,
    because nothing downstream of the generator looks at winding.

    Down-facing fixed geometry is perfectly legitimate: undersides, soffits,
    and the lower half of every ``add_quad_both`` pair. What is never
    legitimate is down-facing horizontal area with no up-facing area to match
    it. Measured over the whole pack the ratio runs from 1.00 (pachinko_tower,
    sumo_gyro_platform - both entirely double-sided) to 12.1, so 0.9 leaves
    real headroom while a one-way floor scores 0.
    """

    handoff = load_handoff(mod_key)
    positions = {node["id"]: node["source_world_position"] for node in handoff["nodes"]}
    fixed = {node["id"]: node["fixed"] for node in handoff["nodes"]}

    up_area = down_area = 0.0
    for triangle in handoff["triangles"]:
        identifiers = triangle["nodes"]
        if not all(fixed.get(i) for i in identifiers):
            continue
        normal = _triangle_normal([positions[i] for i in identifiers])
        length = math.sqrt(sum(component * component for component in normal))
        if length < 1e-9:
            continue
        vertical = normal[2] / length
        if vertical > 0.7:
            up_area += 0.5 * length
        elif vertical < -0.7:
            down_area += 0.5 * length

    if down_area <= 0.5:
        return
    assert up_area >= 0.9 * down_area, (
        f"{mod_key}: {down_area:.1f} m2 of DOWN-facing fixed horizontal collision "
        f"against only {up_area:.1f} m2 facing up - a car falls through it"
    )


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_selector_thumbnails_are_the_authored_render(mod_key: str) -> None:
    """default.jpg and standard.jpg must BE the authored thumbnail.

    prop_builder copies authoring/<mod_id>_thumbnail.jpg to both, so they are
    derived files - but nothing checked that the copy in mod/ is still a copy
    of the current render. A Blender re-run that rewrites the thumbnail after
    the last build.py leaves the shipped pair stale and the ZIP lock pinned to
    an image no longer in the tree, silently.
    """

    spec = load_spec(mod_key)
    authored = PACK_ROOT / mod_key / "authoring" / f"{spec.MOD_ID}_thumbnail.jpg"
    if not authored.is_file():
        pytest.skip("no authored thumbnail")
    vehicle = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID
    source = hashlib.sha256(authored.read_bytes()).hexdigest()
    for name in ("default.jpg", "standard.jpg"):
        shipped = vehicle / name
        if not shipped.is_file():
            continue
        assert hashlib.sha256(shipped.read_bytes()).hexdigest() == source, (
            f"{mod_key}: {name} is not the current authored thumbnail; "
            "re-run build.py <mod> prop then dist"
        )


@pytest.mark.parametrize("mod_key", MOD_KEYS)
def test_behaviour_node_names_resolve_in_the_jbeam(mod_key: str) -> None:
    """Every node id the runtime is handed must exist in the shipped cage.

    A mod whose runtime measures live geometry hangs its whole measurement
    layer off string literals. Rename a cage column and the lookup returns nil
    forever: the update path returns early, no message ever fires, and NOTHING
    fails - the jbeam still matches the handoff, connectivity still passes,
    the ZIP still matches its lock. Same for a breakGroup the runtime asks the
    vehicle VM to break.
    """

    spec = load_spec(mod_key)
    handoff = load_handoff(mod_key)
    node_ids = {node["id"] for node in handoff["nodes"]}

    def walk(value):
        if isinstance(value, str):
            if value.startswith(f"{spec.MOD_ID}_"):
                yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from walk(item)

    missing = sorted({name for name in walk(handoff.get("behavior")) if name not in node_ids})
    assert not missing, f"{mod_key}: behaviour references node ids the cage lacks: {missing}"

    groups = {
        beam.get("extra", {}).get("breakGroup")
        for beam in handoff["beams"]
        if beam.get("extra", {}).get("breakGroup")
    }
    runtime = (
        PACK_ROOT / mod_key / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID / "runtime.lua"
    )
    if runtime.is_file():
        text = runtime.read_text(encoding="utf-8")
        # The runtime usually builds the group name by concatenating a
        # tunable, so the literal is in the B table rather than at the call
        # site. Read it from there; skip any capture that is itself Lua
        # concatenation.
        for key, name in re.findall(r'(\w*break_group\w*) = "([^"]*)"', text):
            if ".." in name or not name:
                continue
            assert name in groups, (
                f"{mod_key}: {key} names breakGroup {name!r}, which no beam "
                f"carries (cage has {sorted(groups)})"
            )


# ---------------------------------------------------------------------------
# SAME-WINDING COPLANAR DOUBLE COVER.
#
# planar_folds' `sum|area| - |sum area|` invariant (football goal post, THE
# FOLD LAW in AGENTS.md) is blind BY CONSTRUCTION to two coplanar layers
# wound the SAME way: both layers add to the vector sum and the scalar sum
# alike, so the difference is exactly zero — its own docstring records this
# as blind spot #1. It is the worse defect of the two, because a same-winding
# layer is not backface-culled: it draws on top of the surface it duplicates
# and z-fights in the open. spin_cycle_washer shipped 0.083380 m^2 of it on
# the front panel (triangles 8139/8140, `enamel_white`, plane y=+6.5) from
# the proplib `cut_openings` pending-bevel bug, fixed 2026-08-26 by applying
# the body's bevel in stack order (`apply_pending_bevels`).
#
# Detection needs actual coplanar polygon clipping, and the grouping must NOT
# reuse planar_folds' fixed 2 um offset lattice (its blind spot #2): the
# washer panel's vertices export at y = 6.499999 / 6.5 / 6.500001, and a
# fixed lattice splits that one plane into three buckets and hides the
# defect. Plane offsets are single-linkage CLUSTERED with a 50 um gap
# instead — far above exporter/float32 noise inside one plane, far below the
# >= 1 mm rebates this pack designs against z-fighting.
#
# Scope mirrors THE FOLD LAW's discipline: one index-connected body at a
# time, because two different solids may legitimately share a plane (the
# weld / Z-FIGHT LAW contacts have OPPOSING normals and are invisible here
# anyway; same-side cross-body overlaps are not gated until someone measures
# a legitimate one). Calibrated 2026-08-26 over every shipped DAE of every
# mod on this branch: the washer defect was the only finding, and the floors
# below produced ZERO noise findings anywhere else. (Heads-up for a mod not
# yet on this branch: the main-checkout work-in-progress `colossus_tire`
# measured 20 chock_paint clusters of 0.0009-0.0018 m^2 — its landing round
# will trip this gate and should re-cut, not widen the floor.)
# ---------------------------------------------------------------------------

# Two parallel planes closer than this are one plane (single-linkage gap).
_PLANE_GAP = 5e-5
# A pair must overlap by more than this to count: well above float noise on
# shared-edge neighbours, four orders of magnitude under any visible membrane.
_PAIR_OVERLAP_FLOOR = 1e-9
_DEGENERATE_AREA = 1e-12


def _dae_triangle_soup(path: Path) -> tuple:
    """Positions + per-<triangles>-block vertex indices from a shipped DAE.

    The DAE is the observation; an in-Blender measurement is only a
    prediction (AGENTS.md, "the exporter is part of the geometry"). Raises
    on non-triangle primitives so a scope hole cannot open silently.
    """

    text = path.read_text(encoding="utf-8")
    assert "<polylist" not in text and "<polygons" not in text, (
        f"{path.name}: non-triangulated primitives; this gate only reads <triangles>"
    )
    arrays = {
        match.group(1): numpy.array(match.group(2).split(), dtype=numpy.float64)
        for match in re.finditer(
            r'<float_array id="([^"]+)" count="\d+">([^<]*)</float_array>', text
        )
    }
    vertices_to_positions = {
        match.group(1): match.group(2)
        for match in re.finditer(
            r'<vertices id="([^"]+)">\s*<input semantic="POSITION" source="#([^"]+)"/>',
            text,
        )
    }
    position_chunks: list = []
    chunk_base: dict[str, int] = {}
    blocks: list[tuple[str, numpy.ndarray]] = []
    for match in re.finditer(
        r'<triangles(?: material="([^"]*)")? count="(\d+)">(.*?)</triangles>', text, re.S
    ):
        material, count, body = match.group(1) or "", int(match.group(2)), match.group(3)
        inputs = re.findall(r'<input semantic="([^"]+)" source="#([^"]+)" offset="(\d+)"', body)
        stride = max(int(offset) for _semantic, _source, offset in inputs) + 1
        vertex_inputs = [
            (source, int(offset))
            for semantic, source, offset in inputs
            if semantic == "VERTEX"
        ]
        assert len(vertex_inputs) == 1, (path.name, material)
        source_id, offset = vertex_inputs[0]
        positions_id = vertices_to_positions[source_id] + "-array"
        if positions_id not in chunk_base:
            chunk_base[positions_id] = sum(len(chunk) for chunk in position_chunks)
            position_chunks.append(arrays[positions_id].reshape(-1, 3))
        raw = numpy.array(re.search(r"<p>([^<]*)</p>", body).group(1).split(), dtype=numpy.int64)
        assert raw.size == count * 3 * stride, (path.name, material)
        blocks.append(
            (material, raw.reshape(-1, stride)[:, offset].reshape(-1, 3) + chunk_base[positions_id])
        )
    if not blocks:
        return numpy.zeros((0, 3)), []
    return numpy.vstack(position_chunks), blocks


def _connected_labels(vertex_count: int, triangles: numpy.ndarray) -> numpy.ndarray:
    """Union-find vertex labels: one index-connected body per root."""

    parent = numpy.arange(vertex_count, dtype=numpy.int64)

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for a, b, c in triangles:
        root = find(a)
        for other in (b, c):
            other_root = find(other)
            if other_root != root:
                parent[other_root] = root
    return numpy.fromiter(
        (find(index) for index in range(vertex_count)), dtype=numpy.int64, count=vertex_count
    )


def _clip_overlap_area(subject: numpy.ndarray, clipper: numpy.ndarray) -> float:
    """Intersection area of two CCW 2D triangles (Sutherland-Hodgman)."""

    output = [tuple(point) for point in subject]
    for index in range(3):
        ax, ay = clipper[index]
        bx, by = clipper[(index + 1) % 3]
        ex, ey = bx - ax, by - ay
        if not output:
            return 0.0
        clipped: list[tuple[float, float]] = []
        previous = output[-1]
        previous_side = ex * (previous[1] - ay) - ey * (previous[0] - ax)
        for point in output:
            side = ex * (point[1] - ay) - ey * (point[0] - ax)
            if side >= 0.0:
                if previous_side < 0.0:
                    t = previous_side / (previous_side - side)
                    clipped.append(
                        (
                            previous[0] + t * (point[0] - previous[0]),
                            previous[1] + t * (point[1] - previous[1]),
                        )
                    )
                clipped.append(point)
            elif previous_side >= 0.0:
                t = previous_side / (previous_side - side)
                clipped.append(
                    (
                        previous[0] + t * (point[0] - previous[0]),
                        previous[1] + t * (point[1] - previous[1]),
                    )
                )
            previous, previous_side = point, side
        output = clipped
    if len(output) < 3:
        return 0.0
    area = 0.0
    origin_x, origin_y = output[0]
    for (first_x, first_y), (second_x, second_y) in itertools.pairwise(output[1:]):
        area += (first_x - origin_x) * (second_y - origin_y) - (second_x - origin_x) * (
            first_y - origin_y
        )
    return abs(area) / 2.0


def _same_winding_double_cover(positions: numpy.ndarray, blocks: list) -> list[dict]:
    """Overlap findings per (body, plane cluster, winding side)."""

    if not blocks:
        return []
    triangles = numpy.vstack([indices for _material, indices in blocks])
    materials: list[str] = []
    for material, indices in blocks:
        materials.extend([material] * len(indices))
    labels = _connected_labels(len(positions), triangles)

    corners = positions[triangles]
    cross = numpy.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0]) / 2.0
    area = numpy.linalg.norm(cross, axis=1)
    live = area > _DEGENERATE_AREA
    live_index = numpy.nonzero(live)[0]
    units = cross[live] / area[live, None]
    # Canonical side = sign of the LARGEST |component|. planar_folds picks
    # the FIRST component above 1e-9 instead, and this gate's own synthetic
    # teeth test caught that inheriting it loses the defect: 1 um exporter
    # noise on an axis-aligned normal makes the noise component the lead,
    # flips the canonical sign, and files the two layers of a double cover
    # in different buckets where they are never compared.
    lead = numpy.argmax(numpy.abs(units), axis=1)
    side = numpy.where(units[numpy.arange(len(units)), lead] > 0.0, 1, -1)
    canon = units * side[:, None]
    offsets = numpy.einsum("ij,ij->i", canon, corners[live].mean(axis=1))
    # `+ 0.0` folds IEEE -0.0 into +0.0 so a rounded-away noise component
    # cannot split a bucket on the sign of zero.
    group_rows = numpy.column_stack(
        (labels[triangles[live, 0]].astype(numpy.float64), numpy.round(canon, 4) + 0.0)
    )
    _uniques, group_of = numpy.unique(group_rows, axis=0, return_inverse=True)

    findings: list[dict] = []
    order = numpy.lexsort((offsets, group_of))
    boundaries = numpy.nonzero(
        (numpy.diff(group_of[order]) != 0) | (numpy.diff(offsets[order]) > _PLANE_GAP)
    )[0]
    for cluster in numpy.split(order, boundaries + 1):
        if len(cluster) < 2:
            continue
        for winding in (1, -1):
            members = cluster[side[cluster] == winding]
            if len(members) < 2:
                continue
            normal = canon[members[0]]
            axis = numpy.zeros(3)
            axis[int(numpy.argmin(numpy.abs(normal)))] = 1.0
            u_axis = numpy.cross(normal, axis)
            u_axis /= numpy.linalg.norm(u_axis)
            basis = numpy.column_stack((u_axis, numpy.cross(normal, u_axis)))
            flat = {}
            for member in members:
                points = corners[live_index[member]] @ basis
                doubled = (points[1, 0] - points[0, 0]) * (points[2, 1] - points[0, 1]) - (
                    points[2, 0] - points[0, 0]
                ) * (points[1, 1] - points[0, 1])
                flat[member] = points if doubled >= 0.0 else points[::-1]
            boxes = {
                member: (
                    points[:, 0].min(),
                    points[:, 0].max(),
                    points[:, 1].min(),
                    points[:, 1].max(),
                )
                for member, points in flat.items()
            }
            scan = sorted(flat, key=lambda member: boxes[member][0])
            total = 0.0
            pairs: list[tuple[int, int, float]] = []
            for position_index, first in enumerate(scan):
                _fx0, fx1, fy0, fy1 = boxes[first]
                for second in scan[position_index + 1 :]:
                    sx0, _sx1, sy0, sy1 = boxes[second]
                    if sx0 > fx1:
                        break
                    if sy0 > fy1 or fy0 > sy1:
                        continue
                    overlap = _clip_overlap_area(flat[second], flat[first])
                    if overlap > _PAIR_OVERLAP_FLOOR:
                        total += overlap
                        pairs.append(
                            (int(live_index[first]), int(live_index[second]), overlap)
                        )
            if pairs:
                findings.append(
                    {
                        "overlap_m2": total,
                        "plane_normal": [round(float(value), 4) for value in normal],
                        "plane_offset": float(offsets[members[0]]),
                        "pairs": sorted(pairs, key=lambda item: -item[2])[:6],
                        "materials": sorted(
                            {materials[index] for a, b, _o in pairs for index in (a, b)}
                        ),
                    }
                )
    return findings


# Tombstone: this gate was calibrated 2026-08-26 on the washer branch, whose
# base predates the colossus_tire chock work, so the first pack-wide run
# (2026-08-29) was the first time the gate met colossus geometry.
DOUBLE_COVER_XFAIL = {
    "colossus_tire": (
        "~0.029 m^2 of same-winding coplanar double cover on the wheel "
        "chocks: 20 plane clusters (4 chocks x 5 planes - tops at z 0.480 "
        "and 0.510, both side planes), every triangle pair in "
        "ericrolph_colossus_tire_chock_paint, largest single strip "
        "0.00074 m^2. The chocks carry coincident same-winding faces that "
        "z-fight in the open exactly as this gate's docstring describes. "
        "The fix is a chock re-cut in colossus's next Blender run with its "
        "own hashes, zip lock and live gate - its own change, same law as "
        "sumo_gyro_platform's re-datum."
    ),
}


def _double_cover_params():
    return [
        pytest.param(
            key,
            marks=pytest.mark.xfail(strict=True, reason=DOUBLE_COVER_XFAIL[key]),
        )
        if key in DOUBLE_COVER_XFAIL
        else key
        for key in MOD_KEYS
    ]


@pytest.mark.parametrize("mod_key", _double_cover_params())
def test_no_same_winding_coplanar_double_cover(mod_key: str) -> None:
    spec = load_spec(mod_key)
    shipped_dir = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID
    daes = sorted(shipped_dir.glob("*.dae")) if shipped_dir.is_dir() else []
    if not daes:
        pytest.skip("no built mod tree")
    report = []
    for dae in daes:
        positions, blocks = _dae_triangle_soup(dae)
        for finding in _same_winding_double_cover(positions, blocks):
            report.append(
                f"{dae.name}: {finding['overlap_m2']:.6f} m^2 on plane "
                f"n={finding['plane_normal']} d={finding['plane_offset']:.6f} "
                f"materials {finding['materials']} pairs {finding['pairs'][:3]}"
            )
    assert not report, (
        f"{mod_key}: same-winding coplanar double cover in shipped DAEs — surfaces "
        "that z-fight in the open and that planar_folds cannot see (blind spot #1). "
        "If a Boolean target carried a pending bevel, see proplib "
        "apply_pending_bevels / cut_openings.\n" + "\n".join(report)
    )


def test_double_cover_scanner_sees_the_washer_defect() -> None:
    """The gate's teeth, proven on synthetic geometry.

    A detector asserted only against clean trees is unfalsifiable — this
    builds the defect class in miniature (two same-winding layers over the
    same plane region, exporter-noise offsets of ~1 um between them) plus
    the two legitimate shapes nearest to it, and checks each side of the
    line. The synthetic overlap reproduces the washer's shipped defect
    geometry: same winding, near-coincident plane, real shared area.
    """

    plane = [
        # A clean 2x2 tiling of one plane: four triangles, no overlap.
        ([(0, 0, 0), (1, 0, 0), (0, 1, 0)], 0.0),
        ([(1, 0, 0), (1, 1, 0), (0, 1, 0)], 0.0),
        ([(1, 0, 0), (2, 0, 0), (1, 1, 0)], 0.0),
        ([(2, 0, 0), (2, 1, 0), (1, 1, 0)], 0.0),
    ]
    positions = []
    triangles = []
    for corners, lift in plane:
        base = len(positions)
        positions.extend([(x, y, z + lift) for x, y, z in corners])
        triangles.append((base, base + 1, base + 2))
    # Weld the tiling into one body via shared coordinates? No — the scanner
    # groups by INDEX connectivity, so link the fan through shared indices.
    triangles = numpy.array(triangles)
    positions = numpy.array(positions, dtype=numpy.float64)
    triangles[1] = (1, 4, 2)
    triangles[2] = (1, 7, 4)
    triangles[3] = (7, 10, 4)
    clean = _same_winding_double_cover(positions[:12], [("tile", triangles)])
    assert clean == [], clean

    # Same-winding double cover with the washer's exporter-noise offsets:
    # a fifth triangle re-covers half of the first tile, 1 um off-plane.
    covered_positions = numpy.vstack(
        [positions[:12], numpy.array([(0, 0, 1e-6), (1, 0, 1e-6), (0, 1, 1e-6)])]
    )
    covered = _same_winding_double_cover(
        covered_positions, [("tile", numpy.vstack([triangles, [(0, 13, 14)]]))]
    )
    # (0, 13, 14) shares index 0 with the body, keeps the winding of the
    # plane, and duplicates the full first tile's half-square: 0.5 m^2.
    assert len(covered) == 1, covered
    assert abs(covered[0]["overlap_m2"] - 0.5) < 1e-9, covered

    # OPPOSING winding at the same coordinates is planar_folds' territory
    # (a fold), not this gate's: same triangle flipped must NOT fire here.
    folded = _same_winding_double_cover(
        covered_positions, [("tile", numpy.vstack([triangles, [(0, 14, 13)]]))]
    )
    assert folded == [], folded

    # A genuinely separate parallel plane 1 mm away (a designed rebate) in
    # the SAME body must stay a separate cluster: no finding.
    rebate_positions = numpy.vstack(
        [positions[:12], numpy.array([(0, 0, 1e-3), (1, 0, 1e-3), (0, 1, 1e-3)])]
    )
    rebated = _same_winding_double_cover(
        rebate_positions, [("tile", numpy.vstack([triangles, [(0, 13, 14)]]))]
    )
    assert rebated == [], rebated
