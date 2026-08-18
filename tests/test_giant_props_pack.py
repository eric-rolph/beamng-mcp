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
import json
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
    # football_goal_post. 18 -> 19 (2026-08-14): hot_potato. A tripwire for a
    # mod silently dropping out of discovery, so it is deliberately a literal.
    assert len(MOD_KEYS) == 19, MOD_KEYS


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
        PACK_ROOT / mod_key / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID
        / "runtime.lua"
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
                offenders.append(f"{name}() called at line {number + 1}, "
                                 f"defined at line {definition + 1}")
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
        PACK_ROOT / mod_key / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID
        / "runtime.lua"
    )
    if not runtime.is_file():
        pytest.skip("no generated GE runtime")
    text = runtime.read_text(encoding="utf-8")
    if "local REQUIRED = {" not in text:
        pytest.skip("mod declares no REQUIRED tunables")

    def _block(marker: str) -> str:
        start = text.index(marker)
        return text[start:text.index("}", start)]

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
    reencoded.write_bytes(reencoded.read_bytes() + b"\x00")   # bytes move
    with Image.open(reencoded) as image:
        assert image.tobytes() == pixels_before                # pixels do not
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
        assert (
            int.from_bytes(blob[4:8], "little") == 124
        ), f"harvested DDS has a malformed header: {cooked_name}"
        assert len(blob) != 1398281, (
            f"harvested DDS is the engine's IMPORTING TEXTURE placeholder: {cooked_name}"
        )
        assert (example_root / "textures" / record["source"]).is_file()
        assert len(record["source_sha256"]) == 64


@pytest.mark.parametrize("mod_key", MOD_KEYS)
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

