"""Static structural gates for the Giant Props pack examples.

These tests validate the Blender-handoff evidence chain for every mod under
``examples/giant_props``: handoff/DAE hash integrity, JBeam consistency with
the handoff, cage connectivity, materials coverage, runtime Lua boilerplate,
and the deterministic distribution ZIP. They are static gates only — live
BeamNG behaviour still requires the opt-in live suites.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
HANDOFF_SCHEMA = "ericrolph-giant-props-handoff-v1"
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


def reject_constants(value: str) -> None:
    raise AssertionError(f"non-finite JSON constant: {value}")


def test_pack_has_all_mods() -> None:
    assert len(MOD_KEYS) == 13, MOD_KEYS


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
    for row in node_rows:
        identifier, x, y, z, options = row
        source = handoff_nodes[identifier]
        assert [x, y, z] == source["position"]
        assert options["fixed"] == source["fixed"]
        assert options["collision"] == source["collision"]
        assert options["selfCollision"] is False
        assert options["nodeWeight"] > 0
        positions[identifier] = (x, y, z)
        fixed_flags[identifier] = options["fixed"]
        collision_flags[identifier] = options["collision"]

    adjacency: dict[str, set[str]] = {identifier: set() for identifier in positions}
    for row in part["beams"][1:]:
        first, second, options = row
        assert first in positions and second in positions
        ax, ay, az = positions[first]
        bx, by, bz = positions[second]
        length = ((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2) ** 0.5
        assert length > 0.01, (first, second)
        assert options["beamSpring"] > 0
        adjacency[first].add(second)
        adjacency[second].add(first)

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
    assert groups == [f"{spec.MOD_ID}_physics"]


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
    assert zip_path.is_file(), "distribution ZIP is missing; run build.py <mod> dist"
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
def test_vehicle_metadata(mod_key: str) -> None:
    spec = load_spec(mod_key)
    vehicle_root = PACK_ROOT / mod_key / "mod" / "vehicles" / spec.MOD_ID
    info = json.loads((vehicle_root / "info.json").read_text(encoding="utf-8"))
    assert info["Type"] == "Prop"
    assert info["Name"] == spec.DISPLAY_NAME
    pc = json.loads((vehicle_root / "standard.pc").read_text(encoding="utf-8"))
    assert pc["mainPartName"] == spec.MOD_ID
    assert (vehicle_root / "default.jpg").is_file()
