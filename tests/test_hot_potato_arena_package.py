"""Static gates for the Gateway Skillet arena package (examples/hot_potato_arena).

Every count here is read from the two reviewed authoring files - the geometry
handoff (statics, obstacles, shapes) and the scenario layout table (spawns,
pantry stacks, barrels, geyser sites) - never typed in: a geometry re-cut or a
layout amendment must only require re-running sync_scenario_outputs.py, and
these gates then re-derive their expectations.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

import pytest

import examples.hot_potato_arena.build_distribution as distribution
import examples.hot_potato_arena.sync_scenario_outputs as sync
from examples.hot_potato_arena.build_distribution import (
    ALLOWED_TOP_LEVEL_ROOTS,
    ZIP_EPOCH,
    ZIP_NAME,
    DistributionError,
    build_distribution,
    expected_members,
    validate_mod_tree,
)
from examples.hot_potato_arena.sync_scenario_outputs import (
    DISPENSER_NAME,
    EXAMPLE_ROOT,
    GROUP_NAME,
    HOT_POTATO_JBEAM,
    LEVEL_ID,
    LUA_PATH,
    MOD_ID,
    MOD_ROOT,
    PLAYER_NAME,
    PREFAB_PATH,
    PROP_ROLE_FIELD,
    SCENARIO_PATH,
    SCENARIO_RELATIVE,
    SHAPES_RELATIVE,
    THUMBNAIL_PATH,
    read_handoff,
    read_layout,
)

STOCK_JBEAMS = {"etk800", "covet", "bx", "barstow", "bluebuck", "cardboard_box", "barrels"}
STOCK_EMITTERS = {"BNGP_waterfallsteam", "BNGP_34"}
EMITTER_DATABLOCK = "lightExampleEmitterNodeData1"
TEXT_SUFFIXES = {".json", ".lua", ".dae"}


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json_loads(source: str) -> Any:
    return json.loads(source, parse_constant=_reject_non_finite, object_pairs_hook=_unique_object)


def _prefab_records() -> list[dict[str, Any]]:
    records = [
        _strict_json_loads(line)
        for line in PREFAB_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records and all(isinstance(record, dict) for record in records)
    return records


def _is_namespaced(value: str) -> bool:
    return value == MOD_ID or value.startswith(f"{MOD_ID}_")


def _lua_source() -> str:
    return LUA_PATH.read_text(encoding="utf-8")


def _lua_table_rows(source: str, name: str) -> str:
    match = re.search(rf"^local {name} = \{{\n(?P<body>.*?)^\}}", source, re.MULTILINE | re.DOTALL)
    assert match is not None, f"generated Lua table {name} is missing"
    return match.group("body")


def _lua_obstacles(source: str) -> list[dict[str, Any]]:
    body = _lua_table_rows(source, "OBSTACLES")
    rows = re.findall(
        r'\{name = "(?P<name>[^"]+)", x = (?P<x>-?[\d.]+), y = (?P<y>-?[\d.]+), '
        r"r = (?P<r>[\d.]+), rp = (?P<rp>[\d.]+)\}",
        body,
    )
    return [
        {"name": n, "x": float(x), "y": float(y), "r": float(r), "rp": float(rp)}
        for n, x, y, r, rp in rows
    ]


def _lua_strings(source: str, name: str) -> list[str]:
    return re.findall(r'"([^"]+)"', _lua_table_rows(source, name))


@pytest.fixture(scope="module")
def handoff() -> dict[str, Any]:
    return read_handoff()


@pytest.fixture(scope="module")
def layout(handoff: dict[str, Any]) -> dict[str, Any]:
    return read_layout(handoff)


# --- generator ------------------------------------------------------------


def test_generated_outputs_are_synchronized_with_the_authoring_files() -> None:
    outputs = sync.render_outputs()
    for path, payload in outputs.items():
        assert path.is_file(), path
        assert path.read_bytes() == payload, f"stale generated output: {path.name}"


def test_generator_rejects_a_handoff_that_breaks_the_contract(handoff: dict[str, Any]) -> None:
    too_many = dict(handoff)
    too_many["obstacles"] = handoff["obstacles"] * 5
    assert len(too_many["obstacles"]) > sync.OBSTACLE_HOOK_CAP
    with pytest.raises(sync.SyncError, match="obstacle"):
        sync.generated_lua_block(too_many)
    broken = EXAMPLE_ROOT / "authoring" / "broken.handoff.json"
    try:
        broken.write_text(json.dumps(too_many), encoding="utf-8")
        with pytest.raises(sync.SyncError):
            read_handoff(broken)
    finally:
        broken.unlink(missing_ok=True)


def test_generator_refuses_a_handoff_matrix_that_contradicts_its_declared_convention(
    handoff: dict[str, Any],
) -> None:
    wrong = json.loads(json.dumps(handoff))
    victim = next(
        i for i in wrong["instances"] if abs(float(i["rotation_ccw_deg_z"])) not in (0.0, 180.0)
    )
    victim["rotationMatrix"] = sync.standard_yaw_matrix(float(victim["rotation_ccw_deg_z"]))
    broken = EXAMPLE_ROOT / "authoring" / "broken.handoff.json"
    try:
        broken.write_text(json.dumps(wrong), encoding="utf-8")
        with pytest.raises(sync.SyncError, match="engine encoding"):
            read_handoff(broken)
    finally:
        broken.unlink(missing_ok=True)


def test_layout_refuses_a_pop_strip_wider_than_its_steam(
    handoff: dict[str, Any], layout: dict[str, Any]
) -> None:
    wide = json.loads(json.dumps({k: v for k, v in layout.items() if not k.startswith("_")}))
    wide["geysers"][1]["half_len"] = 40.0
    broken = EXAMPLE_ROOT / "authoring" / "broken.layout.json"
    try:
        broken.write_text(json.dumps(wide), encoding="utf-8")
        with pytest.raises(sync.SyncError, match="wider than its steam"):
            read_layout(handoff, broken)
    finally:
        broken.unlink(missing_ok=True)


# --- prefab -----------------------------------------------------------------


def test_prefab_is_strict_jsonl_with_deterministic_namespaced_records(
    handoff: dict[str, Any], layout: dict[str, Any]
) -> None:
    records = _prefab_records()
    names = [record["name"] for record in records]
    assert len(names) == len(set(names))
    assert all(_is_namespaced(name) for name in names)
    for record in records:
        identifier = record["persistentId"]
        assert str(UUID(identifier)) == identifier
        assert identifier == sync.persistent_id(record["name"]), record["name"]
        if record["class"] != "SimGroup":
            assert record["__parent"] == GROUP_NAME
        for key in ("position", "rotationMatrix", "scale"):
            if key in record:
                assert all(math.isfinite(float(value)) for value in record[key])
    identifiers = [record["persistentId"] for record in records]
    assert len(identifiers) == len(set(identifiers))

    classes = Counter(record["class"] for record in records)
    assert classes["TSStatic"] == len(handoff["instances"])
    assert classes["BeamNGVehicle"] == len(sync.vehicle_layout(handoff, layout))
    assert classes["SimGroup"] == 1
    assert classes["ParticleEmitterNode"] == sum(
        len(site["emitters"]) for site in sync.geyser_layout(handoff, layout)
    )
    assert records[-1]["class"] == "SimGroup" and records[-1]["name"] == GROUP_NAME


def test_prefab_statics_mirror_the_handoff_and_honour_collision_flags(
    handoff: dict[str, Any],
) -> None:
    statics = {r["name"]: r for r in _prefab_records() if r["class"] == "TSStatic"}
    assert set(statics) == {str(i["name"]) for i in handoff["instances"]}
    for instance in handoff["instances"]:
        record = statics[str(instance["name"])]
        assert record["shapeName"] == "/" + instance["dae"]
        assert (MOD_ROOT / instance["dae"]).is_file()
        assert record["position"] == [round(float(v), 6) for v in instance["position"]]
        angle = float(instance["rotation_ccw_deg_z"])
        # Engine convention (rows = local axes in world), measured live; the
        # v2 handoff declares the same convention and carries the same matrix.
        assert record["rotationMatrix"] == pytest.approx(sync.engine_yaw_matrix(angle), abs=1e-9)
        assert record["rotationMatrix"] == pytest.approx(
            [float(v) for v in instance["rotationMatrix"]], abs=1e-6
        )
        assert record["scale"] == [float(v) for v in instance["scale"]]
        if instance["collision"] == "none":
            assert record["collisionType"] == "None" and record["decalType"] == "None"
        else:
            assert record["collisionType"] == "Visible Mesh Final"
            assert record["decalType"] == "Visible Mesh Final"
    floor_skins = [name for name in statics if "_floor_" in name]
    assert len(floor_skins) == 4, "the four floor-skin quadrants are missing"
    # Design change 2026-09-02 (geometry v3.2): the floor skin is a DRIVEN,
    # COLLIDING surface at +50 mm (the far-field depth fight was
    # boot-dependent and the DAE LOD never engaged - critic r4 negative
    # control, G1 banding on 2 of 3 boots). The handoff flips the four
    # quadrants to visible-mesh and lifts the hazard plates to z 100.05;
    # the LOD blocks are kept as keys but null.
    assert all(statics[name]["collisionType"] == "Visible Mesh Final" for name in floor_skins)
    assert all(statics[name]["decalType"] == "Visible Mesh Final" for name in floor_skins)
    assert all(statics[name]["prebuildCollisionData"] == "1" for name in floor_skins)
    assert handoff["shapes"]["floor_skin_quadrant"].get("lod") is None
    assert handoff.get("floor_skin_lod") is None
    assert isinstance(handoff.get("floor_skin"), dict)
    plates = [name for name in statics if "_butter_pool_" in name or "_salt_arc_" in name]
    assert len(plates) == 5
    assert all(statics[name]["position"][2] == 100.05 for name in plates), {
        name: statics[name]["position"][2] for name in plates
    }
    # No forceDetail / meshCulling / originSort on any record: the JSON
    # prefab loader leaves those string-typed S32 slots uninitialised (critic
    # r3 read 12589 and four large integers back), while the class default
    # reads -1 / 0. Stock gridmap_v2 and CCW emit none of them either.
    for record in statics.values():
        for field in ("forceDetail", "meshCulling", "originSort"):
            assert field not in record, (record["name"], field)
    assert len(handoff["instances"]) == len(statics) == 32


def test_prefab_vehicle_census_follows_the_layout_with_stock_jbeams_referenced(
    handoff: dict[str, Any], layout: dict[str, Any]
) -> None:
    vehicles = [r for r in _prefab_records() if r["class"] == "BeamNGVehicle"]
    by_name = {record["name"]: record for record in vehicles}
    expected = sync.vehicle_layout(handoff, layout)
    assert [v["name"] for v in vehicles] == [e["name"] for e in expected]
    assert all(record["autoEnterVehicle"] == "false" for record in vehicles)
    assert all(record["dataBlock"] == "default_vehicle" for record in vehicles)
    jbeams = Counter(record["jBeam"] for record in vehicles)
    assert jbeams[HOT_POTATO_JBEAM] == 1
    box_count = sum(int(g["count"]) for g in layout["box_walls"])
    barrel_count = sum(int(g["count"]) for g in layout["barrel_clusters"])
    assert jbeams["cardboard_box"] == box_count
    assert jbeams["barrels"] == barrel_count
    assert sum(jbeams[str(c["jbeam"])] for c in layout["cars"]) >= len(layout["cars"])
    assert set(jbeams) - {HOT_POTATO_JBEAM} <= STOCK_JBEAMS
    assert len(vehicles) == 1 + len(layout["cars"]) + box_count + barrel_count
    dispenser = by_name[DISPENSER_NAME]
    assert dispenser["position"] == [850.0, -280.0, float(layout["dispenser_z"])]
    player = by_name[PLAYER_NAME]
    player_spec = next(c for c in layout["cars"] if c["role"] == "player")
    assert player["jBeam"] == player_spec["jbeam"]
    assert player["position"][:2] == pytest.approx(
        list(sync.bearing_point(float(player_spec["bearing"]), float(layout["spawn_ring_r"]))),
        abs=1e-5,
    )
    # Every car faces the pad: engine convention, row 1 of the matrix IS the
    # local +Y axis in world and a BeamNG vehicle's nose is local -Y.
    for record in vehicles:
        if record["jBeam"] in ("cardboard_box", "barrels", HOT_POTATO_JBEAM):
            continue
        m = record["rotationMatrix"]
        nose = (-m[3], -m[4])
        to_centre = (850.0 - record["position"][0], -280.0 - record["position"][1])
        norm = math.hypot(*to_centre)
        assert nose[0] * to_centre[0] / norm + nose[1] * to_centre[1] / norm > 0.999
    # Breakable props carry the role stamp; nothing else does.
    for record in vehicles:
        if record["jBeam"] in ("cardboard_box", "barrels"):
            assert record[PROP_ROLE_FIELD] == "prop" and record["canSaveDynamicFields"] == "1"
        else:
            assert PROP_ROLE_FIELD not in record
    # v3.1 amendment: the centre pantry stacks sit at 20/200.
    centre_walls = sorted(float(g["bearing"]) for g in layout["box_walls"] if float(g["r"]) < 40)
    assert centre_walls == [20.0, 200.0]
    # Stock content is referenced, never copied.
    assert not (MOD_ROOT / "vehicles").exists()
    assert not any(MOD_ROOT.rglob("*.jbeam"))


def test_prefab_emitters_are_stock_particles_with_wisps_on_and_curtains_off(
    handoff: dict[str, Any], layout: dict[str, Any]
) -> None:
    emitters = {r["name"]: r for r in _prefab_records() if r["class"] == "ParticleEmitterNode"}
    sites = sync.geyser_layout(handoff, layout)
    site_names = {e["name"] for site in sites for e in site["emitters"]}
    assert set(emitters) == site_names
    for site in sites:
        for emitter in site["wisp"]:
            assert emitters[emitter["name"]]["active"] is True
        for emitter in site["curtain"]:
            assert emitters[emitter["name"]]["active"] is False
        assert len(site["wisp"]) >= 1 and len(site["curtain"]) >= 2
    for record in emitters.values():
        assert record["dataBlock"] == EMITTER_DATABLOCK
        assert record["emitter"] in STOCK_EMITTERS
    source = _lua_source()
    lua_wisp = set(re.findall(r'"([^"]+)"', " ".join(re.findall(r"wisp = \{([^}]*)\}", source))))
    lua_curtain = set(
        re.findall(r'"([^"]+)"', " ".join(re.findall(r"curtain = \{([^}]*)\}", source)))
    )
    assert lua_wisp == {e["name"] for s in sites for e in s["wisp"]}
    assert lua_curtain == {e["name"] for s in sites for e in s["curtain"]}
    # Spout sites sit at the design table's r = 90 (build round 1 used 91.4).
    for spec in layout["geysers"]:
        if spec["name"].startswith("spout"):
            assert float(spec["r"]) == 90.0


# --- scenario json + lua ----------------------------------------------------


def test_scenario_json_declares_the_scenario_owned_extension_and_player_focus() -> None:
    scenario = _strict_json_loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    assert isinstance(scenario, list) and len(scenario) == 1
    entry = scenario[0]
    assert entry["extensions"] == [{"name": MOD_ID}]
    assert entry["vehicles"] == {PLAYER_NAME: {"playerUsable": True, "startFocus": True}}
    assert entry["forceNoCountDown"] is True
    assert "Gateway Skillet" in entry["name"]
    assert THUMBNAIL_PATH.is_file() and THUMBNAIL_PATH.read_bytes()[:3] == b"\xff\xd8\xff"
    assert not (MOD_ROOT / "lua").exists()
    assert not (MOD_ROOT / "scripts").exists()


def test_lua_generated_block_matches_the_authoring_files(
    handoff: dict[str, Any], layout: dict[str, Any]
) -> None:
    source = _lua_source()
    assert source.count(sync.GENERATED_BEGIN) == 1 and source.count(sync.GENERATED_END) == 1
    obstacles = _lua_obstacles(source)
    # B5 (2026-09-10): the registration is now the arena's 46 rows PLUS the
    # level's 67 (B2's 28 stones + B4's 39 props), in ONE call - the runtime
    # REPLACES its set on every call, so a second call would unregister the
    # first list. Design v4 §7.3 R9; cap 128 via runtime ask #8, Hot Potato
    # build serial 56.
    level_rows = sync.read_level_obstacles()
    assert len(level_rows) == 67
    arena = obstacles[: len(handoff["obstacles"])]
    level = obstacles[len(handoff["obstacles"]) :]
    # Two-radius contract (geometry v3.5 / runtime serial 55): r is the dodge
    # keep-out, rp the measured physical radius of the solid.
    expected = [
        {
            "name": str(o["name"]),
            "x": float(o["x"]),
            "y": float(o["y"]),
            "r": float(o["r_keepout"]),
            "rp": float(o["rp"]),
        }
        for o in handoff["obstacles"]
    ]
    # The arena's own rows come FIRST and are BYTE-IDENTICAL to the gridmap_v2
    # build: nothing inside r 113 changed shape, position or registry.
    assert arena == expected
    assert level == [{k: v for k, v in row.items() if k != "source"} for row in level_rows]
    # v3.6 closed the handle nose (a 14 m wall previously registered only at
    # its two end corners - where G13's remaining pin happened) with four
    # face points at 2.8 m pitch: 42 -> 46.
    assert len(arena) == len(handoff["obstacles"]) == 46
    assert len(obstacles) == 113
    assert sync.OBSTACLE_HOOK_CAP == 128
    assert len(obstacles) <= sync.OBSTACLE_HOOK_CAP
    assert re.search(
        r"local OBSTACLE_COUNTS = \{arena = 46, level = 67, total = 113, cap = 128\}", source
    )
    # The runtime REFUSES the whole registration if any rp is non-finite,
    # below its 0.1 floor, or larger than its own r, or any r is outside
    # [0.5, 30] - caught here, before a boot.
    assert all(sync.OBSTACLE_RP_FLOOR <= o["rp"] <= o["r"] for o in obstacles), [
        o for o in obstacles if not (sync.OBSTACLE_RP_FLOOR <= o["rp"] <= o["r"])
    ]
    assert all(sync.OBSTACLE_R_MIN <= o["r"] <= sync.OBSTACLE_R_MAX for o in obstacles), [
        o for o in obstacles if not (sync.OBSTACLE_R_MIN <= o["r"] <= sync.OBSTACLE_R_MAX)
    ]
    assert all(math.isfinite(o["rp"]) for o in obstacles)
    assert len({o["name"] for o in obstacles}) == len(obstacles)
    # Nothing the level registers may sit inside the arena's own crest: the
    # registry is a dodge census of the SITE, and a level row inside r 113
    # would mean the level round put a solid in the pan.
    for row in level:
        assert math.hypot(row["x"] - 850.0, row["y"] + 280.0) > 113.0, row
    # The posts are the arena's real cylinders; everything else sits at or
    # near the contract floor (24 points are physically 0.0 - they lie ON the
    # solid's surface - and ship the 0.1 floor rather than defaulting to r).
    posts = {o["rp"] for o in arena if o["rp"] > sync.OBSTACLE_RP_FLOOR}
    assert posts == {1.2, 1.5, 2.121, 2.321}, posts
    assert sum(1 for o in arena if o["rp"] == sync.OBSTACLE_RP_FLOOR) == 28
    nose = [o for o in obstacles if o["name"].startswith("handle_nose_face_")]
    assert len(nose) == 4 and all(o["rp"] == sync.OBSTACLE_RP_FLOOR for o in nose)
    assert [o["x"] for o in nose] == sorted(o["x"] for o in nose), "nose points run along the wall"
    # rp_kind is authoring metadata: it must never reach a shipped field.
    assert "rp_kind =" not in source
    assert _lua_strings(source, "STATIC_NAMES") == [str(i["name"]) for i in handoff["instances"]]
    assert _lua_strings(source, "VEHICLE_NAMES") == [
        e["name"] for e in sync.vehicle_layout(handoff, layout)
    ]
    # The generated key list is pinned literally: a sixth key added silently
    # (or a reordering) fails here and in the BOOT_CALLS gate below.
    assert re.search(
        r'local BOOT_OPTION_KEYS = \{"arena_radius_m", "arena_enabled", "ai_enabled", '
        r'"arena_magnet_enabled", "oob_burn_multiplier"\}',
        source,
    )
    assert tuple(sync.BOOT_OPTION_KEYS) == (
        "arena_radius_m",
        "arena_enabled",
        "ai_enabled",
        "arena_magnet_enabled",
        "oob_burn_multiplier",
    )
    statics = {r["name"]: r for r in _prefab_records() if r["class"] == "TSStatic"}
    for obstacle in obstacles:
        static = statics.get(f"{MOD_ID}_{obstacle['name']}")
        if static is not None:
            assert static["position"][0] == pytest.approx(obstacle["x"], abs=1e-6)
            assert static["position"][1] == pytest.approx(obstacle["y"], abs=1e-6)


def test_lua_contract_boot_order_pop_add_hook_tolerance_and_mp_guard() -> None:
    source = _lua_source()
    boot = re.search(r"local BOOT_CALLS = \{(?P<body>.*?)\n\}", source, re.DOTALL)
    assert boot is not None
    keys = re.findall(r'\{"([a-z_]+)",', boot.group("body"))
    # Serial 53's OOB burn ships at 1.0 = OFF, so the arena must switch it on
    # or perimeter looping costs the carrier nothing. 3.0 is the player's
    # figure and is inside the runtime's {1, 5} clamp.
    assert keys == [
        "arena_radius_m",
        "arena_enabled",
        "ai_enabled",
        "arena_magnet_enabled",
        "oob_burn_multiplier",
    ]
    assert keys == list(sync.BOOT_OPTION_KEYS), "BOOT_CALLS and BOOT_OPTION_KEYS must agree"
    assert '{"arena_radius_m", ARENA_RADIUS_M}' in boot.group("body")
    assert '{"oob_burn_multiplier", 3.0}' in boot.group("body")
    assert "local ARENA_RADIUS_M = 91.4" in source
    # The pop is an ADD (scale 1); scale 0 is CCW's stop/launch form.
    assert "local POP_VELOCITY_SCALE = 1" in source
    assert re.search(
        r"applyClusterVelocityScaleAdd\(\s*vehicle:getRefNodeId\(\), "
        r"POP_VELOCITY_SCALE, 0, 0, GEYSER_POP_MPS\)",
        source,
    )
    assert "hotPotatoRegisterObstacles" in source and "hotPotatoGetObstacles" in source
    # B5: the boot census assert, and exactly ONE registration call site.
    assert "obstacle_census_mismatch" in source
    assert source.count("pcall(module.hotPotatoRegisterObstacles, list)") == 1
    assert "hotPotatoGetOptions" in source
    assert "obstacle_hook_missing" in source and "geyser_blind" in source
    assert "isMPSession" in source and "MPCoreNetwork" in source
    # Nothing global besides the extension (AGENTS.md L75-88): the option
    # snapshot is extension-local plus the scenario-owned file.
    assert "rawset(_G" not in source and "_G[" not in source
    assert 'local SNAPSHOT_PATH = "settings/ericrolph_hot_potato_arena.snapshot.json"' in source
    assert "snapshot_recovered" in source
    assert "local OBSTACLE_BACKOFF_CAP_SECONDS = 60.0" in source
    for constant in (
        "local STALL_STEP1_SECONDS = 120.0",
        "local STALL_STEP2_SECONDS = 180.0",
        "local STALL_STEP1_RADIUS = 75.0",
        "local STALL_STEP2_RADIUS = 60.0",
        "local WATCHDOG_STALE_SECONDS = 5.0",
    ):
        assert constant in source
    assert "modScript" not in source
    for export in (
        "M.onPreRender",
        "M.onClientStartMission",
        "M.onClientEndMission",
        "M.onScenarioRestarted",
        "M.onExtensionUnloaded",
        "M.getSystemState",
    ):
        assert export in source


# --- text laws --------------------------------------------------------------


def test_every_shipped_text_member_is_lf_and_strict_json() -> None:
    files = validate_mod_tree()
    for relative, path in files.items():
        if path.suffix not in TEXT_SUFFIXES:
            continue
        payload = path.read_bytes()
        assert b"\r" not in payload, f"CR bytes in {relative}"
        if relative.endswith(".prefab.json"):
            _prefab_records()
        elif path.suffix == ".json":
            assert _strict_json_loads(payload.decode("utf-8")) is not None


def test_materials_are_namespaced_level_scoped_and_carry_groundtypes(
    handoff: dict[str, Any],
) -> None:
    materials_path = MOD_ROOT / handoff["materials_json"]
    assert materials_path.name == f"{MOD_ID}.materials.json"
    # B5 (2026-09-10): the groundtype binding law (AGENTS.md) is the reason this
    # assertion exists at all - a mod material binds a ground type ONLY under
    # `levels/<id>/art/shapes/...`. The move to the round's own level keeps it
    # satisfied, and now by the level that actually owns the site.
    assert materials_path.parent == MOD_ROOT / Path(SHAPES_RELATIVE)
    assert SHAPES_RELATIVE == f"levels/{LEVEL_ID}/art/shapes/hot_potato_arena"
    assert "gridmap_v2" not in handoff["materials_json"]
    materials = _strict_json_loads(materials_path.read_text(encoding="utf-8"))
    assert {f"{MOD_ID}_butter", f"{MOD_ID}_salt", f"{MOD_ID}_cast_iron"} <= set(materials)
    for name, definition in materials.items():
        assert _is_namespaced(name)
        assert definition["name"] == name and definition["mapTo"] == name
        assert _is_namespaced(definition["materialTag0"])
        assert str(UUID(definition["persistentId"])) == definition["persistentId"]
        for stage in definition["Stages"]:
            for field, value in stage.items():
                if field.endswith("Map"):
                    assert value.startswith(f"/{SHAPES_RELATIVE}/textures/")
                    assert (MOD_ROOT / value.removeprefix("/")).is_file()
    assert materials[f"{MOD_ID}_butter"]["groundtype"] == "ICE"
    assert materials[f"{MOD_ID}_salt"]["groundtype"] == "SAND"
    assert "groundtype" not in materials[f"{MOD_ID}_cast_iron"]
    shape_materials = {m for shape in handoff["shapes"].values() for m in shape["materials"]}
    assert shape_materials <= set(materials)

    # Shadow casting (geometry v3.3 + v3.4, materials-only): the far-field
    # striping was re-diagnosed as shadow acne, first on the driven floor skin
    # (v3.3) and then on the glacis it migrated to (v3.4). This is a MATERIAL
    # field - zero of gridmap_v2's 7,167 stock TSStatic records carry any
    # shadow field, so no prefab record changes. The disabled set is exactly
    # what the handoff declares, and that must be the floor skin's own
    # materials plus the glacis material - nothing wider.
    shadows = (handoff.get("floor_skin") or {}).get("shadows") or {}
    disabled = set(shadows.get("disabled_materials") or [])
    assert disabled, "the handoff must declare which materials stop casting"
    glacis = {f"{MOD_ID}_cast_iron_glacis"}
    assert disabled == set(handoff["shapes"]["floor_skin_quadrant"]["materials"]) | glacis
    assert {
        name for name, spec in materials.items() if spec.get("castShadows") is False
    } == disabled
    assert all("castShadows" not in materials[name] for name in set(materials) - disabled)
    # Mirrors geometry's A22: the bank keeps casting. Both wall shapes still
    # carry the matte iron and the rim, and neither is in the disabled set -
    # only bands lying entirely beyond the crest went to the glacis material.
    matte, rim = f"{MOD_ID}_cast_iron_matte", f"{MOD_ID}_rim"
    assert not ({matte, rim} & disabled)
    for wall in ("wall_arc_45", "wall_arc_spout"):
        wall_materials = set(handoff["shapes"][wall]["materials"])
        assert {matte, rim} <= wall_materials, wall
        assert glacis <= wall_materials, wall
    # The glacis copy differs from the matte ONLY by the shadow flag.
    ignored = {"castShadows", "name", "mapTo", "persistentId"}
    assert {
        k: v for k, v in materials[f"{MOD_ID}_cast_iron_glacis"].items() if k not in ignored
    } == {k: v for k, v in materials[matte].items() if k not in ignored}


def test_no_source_artifacts_or_stock_copies_in_the_mod_tree() -> None:
    forbidden = (".py", ".blend", ".handoff.json", ".layout.json", ".md", ".txt")
    # `mod/` holds two products, and since B5 they share ONE level directory:
    # the arena owns `.../art/shapes/hot_potato_arena/` and
    # `.../scenarios/<MOD_ID>/`, and everything else under
    # `mod/levels/<LEVEL_ID>/` belongs to level/build_level_zip.py and is gated
    # by tests/test_hot_potato_level_scaffold.py. See LEVEL_SUBTREE in
    # build_distribution.py for why this scan must skip the rest: a BeamNG level
    # namespaces by DIRECTORY, so it legitimately ships main.materials.json.
    #
    # Before B5 "ours" meant "outside mod/levels/<MOD_ID>/", which after the move
    # would have matched NOTHING and quietly asserted over an empty list. It is
    # now the two subtrees the archive actually ships.
    ours = [
        path
        for path in MOD_ROOT.rglob("*")
        if path.is_file()
        and not distribution._is_foreign_level_file(
            PurePosixPath(path.relative_to(MOD_ROOT).as_posix())
        )
    ]
    assert len(ours) == len(expected_members()) == 36, len(ours)
    for path in ours:
        assert not path.name.casefold().endswith(forbidden), path
        assert path.name != "main.materials.json", path
    shapes = [p for p in ours if p.suffix == ".dae"]
    assert shapes and all(p.name.startswith(f"{MOD_ID}_") for p in shapes)
    assert all("hot_potato_arena" in p.parts for p in shapes)
    # Stock content is referenced by path, never copied: nothing of ours may sit
    # in another level's tree, and no stock level directory may exist here.
    assert all(p.relative_to(MOD_ROOT).parts[1] == LEVEL_ID for p in ours), ours
    assert not (MOD_ROOT / "levels" / "gridmap_v2").exists()
    assert sorted(p.name for p in (MOD_ROOT / "levels").iterdir()) == [LEVEL_ID]


# --- distribution -----------------------------------------------------------


def test_expected_members_are_derived_and_exactly_cover_the_mod_tree(
    handoff: dict[str, Any],
) -> None:
    members = expected_members()
    assert set(validate_mod_tree()) == set(members)
    assert {PurePosixPath(m).parts[0] for m in members} == ALLOWED_TOP_LEVEL_ROOTS == {"levels"}
    assert sum(1 for m in members if m.endswith(".dae")) == len(handoff["shapes"])
    # B5: every member is now under the round's own level, and none under stock.
    assert all(PurePosixPath(m).parts[1] == LEVEL_ID for m in members), members
    assert not any("gridmap_v2" in m for m in members)
    for suffix in (".lua", ".prefab.json", ".json", ".jpg"):
        assert f"{SCENARIO_RELATIVE}/{MOD_ID}{suffix}" in members
    assert handoff["materials_json"] in members
    assert tuple(sorted(members)) == members


def test_distribution_archive_is_deterministic_stored_and_locked(tmp_path: Path) -> None:
    first = build_distribution(tmp_path / "first")
    second = build_distribution(tmp_path / "second")
    first_archive = Path(str(first["archive"]))
    assert first_archive.name == ZIP_NAME
    assert first_archive.read_bytes() == Path(str(second["archive"])).read_bytes()
    assert first["sha256"] == second["sha256"]
    lock = _strict_json_loads(Path(str(first["lock"])).read_text(encoding="utf-8"))
    assert lock["sha256"] == first["sha256"] and lock["size"] == first["size"]
    assert lock["members"] == list(expected_members())
    with pytest.raises(DistributionError, match="--overwrite"):
        build_distribution(tmp_path / "first")
    with zipfile.ZipFile(first_archive) as archive:
        names = archive.namelist()
        assert names == list(expected_members())
        assert archive.testzip() is None
        infos = archive.infolist()
        assert all(member.compress_type == zipfile.ZIP_STORED for member in infos)
        assert all(member.date_time == ZIP_EPOCH for member in infos)
        assert all((member.external_attr >> 16) & 0o777 == 0o644 for member in infos)
        assert {PurePosixPath(name).parts[0] for name in names} == {"levels"}


def test_distribution_builder_refuses_an_unexpected_mod_file(tmp_path: Path) -> None:
    staged = tmp_path / "mod"
    for relative in expected_members():
        destination = staged / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MOD_ROOT / Path(relative), destination)
    (staged / Path(SCENARIO_RELATIVE) / "notes.txt").write_text(
        "must not ship\n", encoding="utf-8"
    )
    with pytest.raises(DistributionError, match=r"notes\.txt"):
        build_distribution(tmp_path / "out", mod_root=staged)
    assert not (tmp_path / "out" / ZIP_NAME).exists()


def test_the_level_subtree_skip_is_scoped_to_the_level_rounds_own_files(tmp_path: Path) -> None:
    """B5: the arena now lives INSIDE the level directory, so the skip that hides
    the level round's 800 files must not also hide a stray file of ours.

    Shown firing three ways: a stray beside the scenario, a stray beside the
    shapes, and - as the negative control - a file in the level round's own part
    of the tree, which must still be skipped silently.
    """

    staged = tmp_path / "mod"
    for relative in expected_members():
        destination = staged / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MOD_ROOT / Path(relative), destination)

    # Control: the level round's own member is skipped, so the tree validates.
    foreign = staged / "levels" / LEVEL_ID / "main" / "items.level.json"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("{}\n", encoding="utf-8")
    assert set(validate_mod_tree(staged)) == set(expected_members())
    assert distribution._is_foreign_level_file(
        PurePosixPath(f"levels/{LEVEL_ID}/main/items.level.json")
    )

    # ... and a stray in either of OUR two subtrees is still refused.
    for stray in (
        staged / Path(SCENARIO_RELATIVE) / "stray.json",
        staged / Path(SHAPES_RELATIVE) / "stray.json",
    ):
        stray.write_text("{}\n", encoding="utf-8")
        relative = stray.relative_to(staged).as_posix()
        assert not distribution._is_foreign_level_file(PurePosixPath(relative))
        with pytest.raises(DistributionError, match=r"stray\.json"):
            validate_mod_tree(staged)
        stray.unlink()
    assert set(validate_mod_tree(staged)) == set(expected_members())


def test_distribution_builder_refuses_crlf_text_members(tmp_path: Path) -> None:
    staged = tmp_path / "mod"
    for relative in expected_members():
        destination = staged / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(MOD_ROOT / Path(relative), destination)
    victim = staged / Path(SCENARIO_RELATIVE) / f"{MOD_ID}.lua"
    victim.write_bytes(victim.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(DistributionError, match="LF law"):
        build_distribution(tmp_path / "out", mod_root=staged)


def test_dist_art_members_are_pinned_to_the_geometry_hashes_manifest(
    handoff: dict[str, Any],
) -> None:
    """Every DAE, texture and materials member in the dist zip must be the
    exact bytes the geometry worker's hashes manifest measured (critic r3 /
    geometry v3.1 errata): a stale re-cut can never ship again."""

    manifest_path = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}.hashes.json"
    assert manifest_path.is_file(), "the geometry hashes manifest is missing"
    manifest = _strict_json_loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "ericrolph-hot-potato-arena-hashes-v1"
    # Pinned to the geometry round the package was cut against: v3.8. v3.5
    # and v3.6 were handoff-only (the two-radius table, then the four
    # handle-nose points); v3.7 was a RETRACTION - the reported 145 mm
    # deck-rear step did not exist, the edge was always on the bank arc - and
    # shipped only assert A26. v3.8 is the one real finding: the handle's tuck
    # strip stood +4.741 mm proud, fixed structurally by making the skirt
    # DESCEND 50 mm from the deck edge, so it is under the bank by
    # construction rather than by tessellation. A newer manifest means the
    # generator must be re-run on purpose.
    assert manifest["round"] == "v3.8", manifest["round"]
    # The handle is the ONLY member that moved - the first deliberate handle
    # change since round 2, and the one intended exception to the
    # do-not-regress manifest. 12 vertices moved; no geometry added.
    assert manifest["dae"]["handle"]["sha256"] == (
        "88cbb1c5971887af27a435f1cd4432e4f2d9f7ce613a48394e382d0c3470667a"
    )
    assert manifest["dae"]["handle"]["tris"] == 2022
    assert manifest["dae"]["wall_arc_45"]["sha256"] == (
        "3af9f916a2a6db3350e9cd6a1cc6f695d32fea838131e774a28da3165cd3cb7b"
    )
    assert manifest["dae"]["wall_arc_spout"]["sha256"] == (
        "cb0bc02d6d63950288677b567d43cac0e28504dfb6d6d178b1f32b5cdb024709"
    )
    # B5 (2026-09-10): the ONE art member the level move rewrote. Its 27 texture
    # map paths went from `/levels/gridmap_v2/...` to
    # `/levels/ericrolph_hot_potato_arena/...`; no map, factor or flag changed.
    # Old digest 70de26ae4615246956141b3ddfdce83af490eb2d449e9f759b10bc476d9b914f.
    assert manifest["materials_json"]["sha256"] == (
        "adf0464c7046cec7da940c741dcf4e0bbaa669d15ef0fa8e200f1ca5ea93e45a"
    )
    # ... and the thirteen DAEs did NOT move a byte. The whole point of the
    # geometry manifest is that a level move cannot become a silent re-cut.
    assert manifest["dae"]["handle"]["sha256"] == handoff["shapes"]["handle"]["sha256"]
    assert all(entry["file"].startswith(SHAPES_RELATIVE) for entry in manifest["dae"].values())
    assert manifest["materials_json"]["file"].startswith(SHAPES_RELATIVE)
    # The floor skin is untouched since v3.3.
    assert manifest["dae"]["floor_skin_quadrant"]["sha256"].startswith("1ca6b37e")
    assert handoff.get("hash_manifest", {}).get("file") == manifest_path.name
    expected: dict[str, str] = {}
    for entry in manifest["dae"].values():
        expected[entry["file"]] = entry["sha256"]
    # Textures are keyed by basename under the shapes' textures/ folder.
    texture_root = str(PurePosixPath(manifest["materials_json"]["file"]).parent / "textures")
    for basename, entry in manifest["textures"].items():
        expected[f"{texture_root}/{basename}"] = entry["sha256"]
    expected[manifest["materials_json"]["file"]] = manifest["materials_json"]["sha256"]
    # The handoff's shape table cites the same digests.
    for key, shape in handoff["shapes"].items():
        assert manifest["dae"][key]["sha256"] == shape["sha256"], key
    art_members = [m for m in expected_members() if "/scenarios/" not in m]
    assert set(art_members) == set(expected), {
        "missing_from_manifest": sorted(set(art_members) - set(expected)),
        "not_shipped": sorted(set(expected) - set(art_members)),
    }
    import hashlib

    for member in art_members:
        actual = hashlib.sha256((MOD_ROOT / member).read_bytes()).hexdigest()
        assert actual == expected[member], (
            f"{member}: tree {actual[:12]} != manifest {expected[member][:12]}"
        )
    dist = EXAMPLE_ROOT / "dist"
    archive = dist / ZIP_NAME
    if not archive.is_file():
        pytest.skip("no dist archive built on this tree")
    with zipfile.ZipFile(archive) as zf:
        for member in art_members:
            actual = hashlib.sha256(zf.read(member)).hexdigest()
            assert actual == expected[member], (
                f"dist {member}: {actual[:12]} != manifest {expected[member][:12]}"
            )


def test_checked_in_lock_matches_the_dist_archive_and_the_hot_potato_lock() -> None:
    dist = EXAMPLE_ROOT / "dist"
    archive = dist / ZIP_NAME
    lock_path = dist / distribution.LOCK_NAME
    if not archive.is_file() or not lock_path.is_file():
        pytest.skip("no dist archive built on this tree")
    lock = _strict_json_loads(lock_path.read_text(encoding="utf-8"))
    assert distribution._sha256(archive) == lock["sha256"]
    assert lock["members"] == list(expected_members())
    distribution.verify_archive(archive)
    if distribution.HOT_POTATO_LOCK.is_file():
        hot_potato = _strict_json_loads(distribution.HOT_POTATO_LOCK.read_text(encoding="utf-8"))
        assert lock["depends_on"]["sha256"] == hot_potato["sha256"], (
            "the arena dist was cut against an older Hot Potato zip; rebuild it"
        )
