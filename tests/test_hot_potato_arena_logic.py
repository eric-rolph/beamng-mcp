"""Headless (lupa) gate for the Gateway Skillet scenario extension.

Runs the REAL shipped scenario Lua against a stub engine and a stub Hot Potato
runtime. It cannot prove particles or physics; it proves the logic the arena
hangs off the runtime's hook surface (design v3 §5.4, §5.5, §6.3; critique
round 1 fixes 1-3, 5, 6, 8-10):

- boot retries until the runtime resolves, then applies exactly the five
  option calls in the design's order (serial 53 added oob_burn_multiplier,
  which ships at 1.0 = OFF, so the arena must switch it on) and never
  re-applies them - not after onClientStartMission, not after
  onScenarioRestarted, not after mission end,
- the player's values of the five keys are snapshotted before the writes and
  handed back at mission end (only the keys the arena changed; a valve radius
  left by a crash is never handed back), and the snapshot survives the
  engine's reload-on-restart,
- obstacle registration goes through hotPotatoRegisterObstacles when present,
  degrades to a logged warning when absent, and is re-done when the runtime
  module is a new instance, when the prop comes back, or when the runtime's
  count has dropped - exactly one extra call each time,
- geyser windows follow their cycles, keep the wisp on as the OFF tell, drive
  the curtain on the window, pop a vehicle inside the strip once per ON window
  with velocity scale 1 (an ADD), never during OFF, and never from a site
  whose emitters did not resolve,
- the decay valve steps 91.4 -> 75 at 120 s of live-round stall, -> 60 at
  180 s, restores on every round exit, spends at most three calls per stalled
  round, spends none when a decay was refused, resets its clock on a pass, and
  is disabled entirely in BeamMP,
- the watchdog keys on prop LIVENESS: a dead Dispenser restores once and
  disarms; a steady-tick stall (frozen stats payload, live prop) does NOT
  false-restore (critique erratum 5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

lupa = pytest.importorskip("lupa")

MOD_ID = "ericrolph_hot_potato_arena"
#: B5 (2026-09-10): the scenario moved off stock gridmap_v2 onto the round's own
#: level, whose id is the same string. The level binding is the PATH.
LEVEL_ID = MOD_ID
LUA_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "hot_potato_arena"
    / "mod"
    / "levels"
    / LEVEL_ID
    / "scenarios"
    / MOD_ID
    / f"{MOD_ID}.lua"
)
#: The engine hands `onClientStartMission` / `onClientEndMission` a level path.
#: The module never parses it - it only echoes it into the session events - so
#: this is an opaque token; it is written out of LEVEL_ID so the suite says
#: which level it is standing on.
MISSION_PATH = f"/levels/{LEVEL_ID}/main.level.json"
RUNTIME = "ericrolph__hot__potato_runtime"
DISPENSER = f"{MOD_ID}_dispenser"
GATE_STRIP = (850.0, -222.318, 100.3)
OUTSIDE = (850.0, -250.0, 100.3)
BOOT_KEYS = (
    "arena_radius_m",
    "arena_enabled",
    "ai_enabled",
    "arena_magnet_enabled",
    "oob_burn_multiplier",
)
ARENA_VALUES = {
    "arena_radius_m": 91.4,
    "arena_enabled": True,
    "ai_enabled": True,
    "arena_magnet_enabled": True,
    "oob_burn_multiplier": 3.0,
}
#: What a fresh profile has before the arena boots (the runtime's shipped
#: defaults): OOB burn is OFF, so the arena's 3.0 is always a write and always
#: a hand-back. The other three follow the runtime's own defaults.
PLAYER_DEFAULTS = {
    "arena_radius_m": 91.4,
    "arena_enabled": True,
    "ai_enabled": False,
    "arena_magnet_enabled": True,
    "oob_burn_multiplier": 1.0,
}
#: The hand-back a default profile is owed at every exit path.
OOB_HANDBACK = ("oob_burn_multiplier", 1.0)

STUBS = r"""
local S = {}
S.events = {}
S.calls = {}
S.obstacleCalls = {}
S.lastObstacles = {}
S.pops = {}
S.scene = {}
S.vehicles = {}
S.stats = {phase = "idle", carrier = -1, transfers = 0}
S.registered = true
S.hookPresent = true
S.getterPresent = true
S.setOptionResult = true
S.mp = false
-- The shipped defaults (spec.py OPTIONS): the player's settings before the arena.
S.options = {arena_radius_m = 91.4, arena_enabled = true, ai_enabled = false, arena_magnet_enabled = true, oob_burn_multiplier = 1.0}
S.generation = 0
S.hookResult = true
-- The user folder, as the engine's json helpers see it.
S.files = {}
S.fileWrites = 0
S.writeResult = true
function jsonReadFile(path) return S.files[path] end
function jsonWriteFile(path, payload, _pretty)
  S.fileWrites = S.fileWrites + 1
  if not S.writeResult then return false end
  S.files[path] = payload
  return true
end
FS = {removeFile = function(_self, path) S.files[path] = nil end}
function S.snapshotFile() return S.files["settings/ericrolph_hot_potato_arena.snapshot.json"] end
function S.plantSnapshotFile(options)
  S.files["settings/ericrolph_hot_potato_arena.snapshot.json"] = {schema = 1, mod = "ericrolph_hot_potato_arena", options = options}
end

local function encode(value, depth)
  depth = depth or 0
  local t = type(value)
  if t == "table" then
    if depth > 3 then return "{...}" end
    local parts = {}
    local keys = {}
    for k in pairs(value) do keys[#keys + 1] = tostring(k) end
    table.sort(keys)
    for _, k in ipairs(keys) do
      local v = value[k]
      if v == nil then v = value[tonumber(k)] end
      parts[#parts + 1] = '"' .. k .. '":' .. encode(v, depth + 1)
    end
    return "{" .. table.concat(parts, ",") .. "}"
  elseif t == "string" then
    return '"' .. value .. '"'
  else
    return tostring(value)
  end
end
function jsonEncode(value) return encode(value) end
function log(level, tag, message)
  S.events[#S.events + 1] = {level = level, tag = tag, message = message}
end

local objmt = {}
objmt.__index = objmt
function objmt:getID() return self.id end
function objmt:getClassName() return self.class end
function objmt:setActive(on) self.active = on and true or false end
function objmt:getName() return self.name end

local vehmt = {}
vehmt.__index = vehmt
function vehmt:getID() return self.id end
function vehmt:getName() return self.name end
function vehmt:getPosition() return {x = self.pos.x, y = self.pos.y, z = self.pos.z} end
function vehmt:getRefNodeId() return 0 end
function vehmt:applyClusterVelocityScaleAdd(_node, scale, x, y, z)
  S.pops[#S.pops + 1] = {id = self.id, scale = scale, x = x, y = y, z = z}
end

local nextEmitterId = 50000
function S.addEmitter(name, active)
  nextEmitterId = nextEmitterId + 1
  S.scene[name] = setmetatable({name = name, class = "ParticleEmitterNode", active = active == true, id = nextEmitterId}, objmt)
end
function S.removeEmitter(name) S.scene[name] = nil end
function S.addVehicle(id, name, x, y, z)
  local vehicle = setmetatable({id = id, name = name, pos = {x = x, y = y, z = z}}, vehmt)
  S.vehicles[id] = vehicle
  S.scene[name] = vehicle
  return vehicle
end
function S.moveVehicle(id, x, y, z)
  local vehicle = S.vehicles[id]
  vehicle.pos.x, vehicle.pos.y, vehicle.pos.z = x, y, z
end
function S.removeVehicle(id)
  local vehicle = S.vehicles[id]
  if vehicle then S.scene[vehicle.name] = nil end
  S.vehicles[id] = nil
end

scenetree = {}
function scenetree.findObject(name) return S.scene[name] end
function getAllVehicles()
  local list = {}
  for _, vehicle in pairs(S.vehicles) do list[#list + 1] = vehicle end
  table.sort(list, function(a, b) return a.id < b.id end)
  return list
end
be = {}
function be:getObjectByID(id) return S.vehicles[id] end

extensions = {}
function S.installRuntime()
  S.generation = S.generation + 1
  local module = {
    generation = S.generation,
    hotPotatoSetOption = function(key, value)
      S.calls[#S.calls + 1] = {key = key, value = value}
      if S.setOptionResult then S.options[key] = value end
      return S.setOptionResult
    end,
    hotPotatoGetOptions = function()
      local copy = {}
      for k, v in pairs(S.options) do copy[k] = v end
      return copy
    end,
    hotPotatoGetStats = function() return S.stats end,
    getSystemState = function(id) return {registered = S.registered, id = id} end,
  }
  if S.hookPresent then
    module.hotPotatoRegisterObstacles = function(list)
      local copy = {}
      for i, entry in ipairs(list) do
        -- Copy EVERY field the arena sent, so a gate can prove the payload
        -- carries exactly the contract's keys and nothing else.
        local one = {}
        for k, v in pairs(entry) do one[k] = v end
        copy[i] = one
      end
      S.obstacleCalls[#S.obstacleCalls + 1] = copy
      if S.hookResult then S.lastObstacles = copy end
      return S.hookResult
    end
    if S.getterPresent then
      module.hotPotatoGetObstacles = function()
        return {count = #S.lastObstacles, entries = S.lastObstacles}
      end
    end
  end
  extensions["@RUNTIME@"] = module
end
function S.removeRuntime() extensions["@RUNTIME@"] = nil end
function S.dropObstacles() S.lastObstacles = {} end
function S.setMP(active)
  if active then
    MPCoreNetwork = {isMPSession = function() return true end}
  else
    MPCoreNetwork = nil
  end
end
function S.clearCalls() S.calls = {} S.pops = {} end
function S.snapshotGlobal() return rawget(_G, "ericrolph_hot_potato_arena_option_snapshot") end
return S
""".replace("@RUNTIME@", RUNTIME)

GATE_WISP = (f"{MOD_ID}_geyser_gate_wisp_1",)
GATE_CURTAIN = (
    f"{MOD_ID}_geyser_gate_curtain_1",
    f"{MOD_ID}_geyser_gate_curtain_2",
    f"{MOD_ID}_geyser_gate_spatter",
)
SPOUT_EMITTERS = tuple(
    f"{MOD_ID}_geyser_{site}_{kind}"
    for site in ("spout_e", "spout_w")
    for kind in ("wisp_1", "curtain_1", "curtain_2", "curtain_3", "curtain_4", "spatter")
)
EMITTER_NAMES = (*GATE_WISP, *GATE_CURTAIN, *SPOUT_EMITTERS)


def _plant(state, options_dict: dict) -> None:
    """Leave a snapshot file behind, as a mission that died would have."""

    state.plantSnapshotFile(lua_table_from(state, options_dict))


def lua_table_from(state, values: dict):
    runtime = _RUNTIMES[id(state)]
    table = runtime.table()
    for key, value in values.items():
        table[key] = value
    return table


_RUNTIMES: dict[int, Any] = {}


def _make_rig(with_emitters: bool = True, lua_path: Path = LUA_PATH):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    state = lua.execute(STUBS)
    _RUNTIMES[id(state)] = lua
    if with_emitters:
        for name in EMITTER_NAMES:
            state.addEmitter(name, name.endswith("wisp_1"))
    state.addVehicle(7, DISPENSER, 850.0, -280.0, 100.1)
    module = lua.execute(lua_path.read_text(encoding="utf-8"))
    module.onExtensionLoaded()
    return lua, state, module


def _rig_for(lua_path: Path):
    """A rig over a DELIBERATELY DAMAGED copy of the shipped Lua.

    Used by the census gate to watch the boot assert fire; the shipped file on
    disk is never touched.
    """

    return _make_rig(lua_path=lua_path)


@pytest.fixture()
def rig():
    return _make_rig()


def tick(module, seconds=0.1, steps=1):
    for _ in range(steps):
        module.onPreRender(seconds, seconds, seconds)


def run(module, seconds, dt=0.5):
    tick(module, seconds=dt, steps=int(round(seconds / dt)))


def calls(state):
    return [(row.key, row.value) for row in state.calls.values()]


def events(state, event):
    return [e.message for e in state.events.values() if f'"event":"{event}"' in str(e.message)]


def system(module):
    return module.getSystemState()


def boot(state, module):
    state.installRuntime()
    module.onClientStartMission(MISSION_PATH)
    tick(module, 0.1, 2)
    assert system(module).booted is True
    state.clearCalls()


def start_round(state, carrier=11, transfers=0):
    state.stats.phase = "live"
    state.stats.carrier = carrier
    state.stats.transfers = transfers


def end_round(state, phase="boom"):
    state.stats.phase = phase
    state.stats.carrier = -1


def gate_active(state):
    return [state.scene[name].active for name in GATE_WISP], [
        state.scene[name].active for name in GATE_CURTAIN
    ]


def options(state):
    return {key: state.options[key] for key in BOOT_KEYS}


# --- boot -------------------------------------------------------------------


def test_boot_retries_until_the_runtime_resolves_then_applies_five_ordered_calls(rig):
    _, state, module = rig
    run(module, 40.0)
    assert calls(state) == []
    assert system(module).booted is False
    assert len(events(state, "boot_waiting")) == 1
    state.installRuntime()
    tick(module, 0.1, 1)
    # The order is the design's: self-heal radius first, then the arena
    # switches, with the OOB burn penalty alongside the magnet. A sixth key
    # added silently fails here and in the package gates.
    assert calls(state) == [
        ("arena_radius_m", 91.4),
        ("arena_enabled", True),
        ("ai_enabled", True),
        ("arena_magnet_enabled", True),
        ("oob_burn_multiplier", 3.0),
    ]
    assert [key for key, _ in calls(state)] == list(BOOT_KEYS)
    assert system(module).booted is True
    assert system(module).valve.enabled is True
    run(module, 30.0)
    assert len(calls(state)) == len(BOOT_KEYS), "boot options must be applied exactly once"


def test_boot_snapshots_the_players_values_before_writing_them(rig):
    _, state, module = rig
    state.options.ai_enabled = False
    state.options.arena_magnet_enabled = False
    boot(state, module)
    snapshot = system(module).snapshot
    assert snapshot.arena_radius_m == 91.4 and snapshot.arena_enabled is True
    assert snapshot.ai_enabled is False and snapshot.arena_magnet_enabled is False
    assert state.snapshotGlobal() is None, "nothing global besides the extension"
    assert options(state) == ARENA_VALUES
    # The disk-backed snapshot exists for the whole mission and carries the
    # player's values, written before the first option write.
    stored = state.snapshotFile()
    assert stored is not None and system(module).snapshot_file_written is True
    assert stored.options.ai_enabled is False and stored.options.arena_magnet_enabled is False
    assert stored.mod == MOD_ID


def test_snapshot_file_is_written_before_the_first_option_write(rig):
    _, state, module = rig
    state.installRuntime()
    tick(module, 0.1, 1)
    # The stub counts writes: the snapshot file (1) must precede the four
    # option calls, and nothing else writes files during a boot.
    assert state.fileWrites == 1 and len(calls(state)) == len(BOOT_KEYS)
    assert state.snapshotFile() is not None


def test_boot_registers_the_obstacle_table_through_the_hook(rig):
    _, state, module = rig
    boot(state, module)
    # B5 (2026-09-10): ONE call carries BOTH censuses. The runtime REPLACES its
    # whole set on every call, so a second call for the level's rows would leave
    # the arena's 46 unregistered. Design v4 §7.3 R9: 46 + 67 = 113, against the
    # cap ask #8 raised to 128 at Hot Potato serial 56.
    assert len(state.obstacleCalls) == 1
    registered = state.obstacleCalls[1]
    reported = system(module)
    assert len(registered) == reported.obstacle_count
    assert len(registered) == 113
    assert reported.obstacle_arena == 46
    assert reported.obstacle_level == 67
    assert reported.obstacle_expected == 113
    assert reported.obstacle_cap == 128
    assert reported.obstacle_census_ok is True
    assert len(registered) <= reported.obstacle_cap
    first = registered[1]
    # Exactly the runtime's contract: position, keep-out r, physical rp. The
    # table's local `name` and the authoring-only `rp_kind` never ship.
    assert set(dict(first).keys()) == {"x", "y", "r", "rp"}
    # The arena's own rows come FIRST and are unchanged by the level move.
    assert (
        first.x == pytest.approx(883.941) and first.y == pytest.approx(-246.059) and first.r == 6.5
    )
    assert first.rp == pytest.approx(1.2)
    # ... and the level's rows follow, starting at 47 with B2's first stone.
    level_first = registered[47]
    assert level_first.x == pytest.approx(794.872) and level_first.y == pytest.approx(-74.258)
    assert level_first.r == pytest.approx(15.0) and level_first.rp == pytest.approx(11.0)
    for index in range(1, len(registered) + 1):
        entry = registered[index]
        assert set(dict(entry).keys()) == {"x", "y", "r", "rp"}
        # The runtime refuses the WHOLE list on one bad row: r in [0.5, 30] and
        # 0.1 <= rp <= r (spec.py v26.OBSTACLE_R_MIN/MAX, OBSTACLE_RP_MIN).
        assert 0.1 <= entry.rp <= entry.r, (index, entry.rp, entry.r)
        assert 0.5 <= entry.r <= 30.0, (index, entry.r)
    assert system(module).obstacles == "registered"
    assert system(module).obstacle_reason == "boot"


def test_a_hand_edited_obstacle_table_fires_the_census_warning_and_still_registers(rig, tmp_path):
    """The boot census assert, shown FIRING - by deletion and by corruption.

    `OBSTACLE_COUNTS` is generated from the two handoffs in the same pass as
    `OBSTACLES`, so the only way they disagree is a hand edit of the shipped
    file. The check is deliberately a loud warning rather than a refusal: a
    short list still lets the pin reflex dodge the solids that ARE in it, and
    this module never stops play over bookkeeping.
    """

    import re

    source = LUA_PATH.read_text(encoding="utf-8")

    # (a) DELETION: drop the last twenty rows of the table, leave the counts.
    body = re.search(r"local OBSTACLES = \{\n(.*?)\n\}\n", source, re.DOTALL)
    assert body is not None
    rows = body.group(1).splitlines()
    assert len(rows) == 113
    short = source.replace(body.group(1), "\n".join(rows[:-20]), 1)
    short_path = tmp_path / "short.lua"
    short_path.write_text(short, encoding="utf-8", newline="\n")
    _, state, module = _rig_for(short_path)
    boot(state, module)
    reported = system(module)
    assert reported.obstacle_count == 93
    assert reported.obstacle_expected == 113
    assert reported.obstacle_census_ok is False
    assert len(state.obstacleCalls) == 1, "a miscount must never stop the registration"
    assert len(state.obstacleCalls[1]) == 93
    warnings = [
        e
        for e in state.events.values()
        if e.level == "W" and "obstacle_census_mismatch" in e.message
    ]
    assert len(warnings) == 1, "one warning, not one per frame"

    # (b) CORRUPTION: leave the rows, move the declared total.
    bent = source.replace("total = 113", "total = 999", 1)
    assert bent != source
    bent_path = tmp_path / "bent.lua"
    bent_path.write_text(bent, encoding="utf-8", newline="\n")
    _, state2, module2 = _rig_for(bent_path)
    boot(state2, module2)
    assert system(module2).obstacle_count == 113
    assert system(module2).obstacle_expected == 999
    assert system(module2).obstacle_census_ok is False
    assert any(
        e.level == "W" and "obstacle_census_mismatch" in e.message for e in state2.events.values()
    )

    # (c) CONTROL: the shipped file does not fire it.
    _, state3, module3 = _rig_for(LUA_PATH)
    boot(state3, module3)
    assert system(module3).obstacle_census_ok is True
    assert not any(
        e.level == "W" and "obstacle_census_mismatch" in e.message for e in state3.events.values()
    )


def test_missing_obstacle_hook_is_a_logged_warning_not_a_failure(rig):
    _, state, module = rig
    state.hookPresent = False
    state.installRuntime()
    tick(module, 0.1, 2)
    assert system(module).booted is True
    assert system(module).obstacles == "unavailable"
    run(module, 30.0)
    warnings = [
        e for e in state.events.values() if e.level == "W" and "obstacle_hook_missing" in e.message
    ]
    assert len(warnings) == 1, "the missing hook is logged once, not nagged"
    assert len(calls(state)) == len(BOOT_KEYS)


def test_beammp_session_writes_no_options_and_disables_the_valve(rig):
    _, state, module = rig
    state.setMP(True)
    state.installRuntime()
    tick(module, 0.1, 2)
    assert system(module).booted is True
    assert system(module).mp is True
    assert calls(state) == []
    assert system(module).valve.enabled is False
    start_round(state)
    run(module, 400.0)
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == []
    assert len(state.obstacleCalls) >= 1, "obstacle dodge coverage is local and still registers"


def test_refused_boot_option_fails_closed_and_keeps_the_valve_off(rig):
    _, state, module = rig
    state.setOptionResult = False
    state.installRuntime()
    tick(module, 0.1, 2)
    assert system(module).booted is True
    assert system(module).valve.enabled is False
    start_round(state)
    run(module, 400.0)
    assert len(calls(state)) == len(BOOT_KEYS)


def test_start_mission_after_boot_does_not_reboot(rig):
    _, state, module = rig
    boot(state, module)
    module.onClientStartMission(MISSION_PATH)
    run(module, 10.0)
    assert calls(state) == []
    assert system(module).booted is True


# --- restart (critique fix 2) --------------------------------------------------


def test_scenario_restart_keeps_the_boot_and_costs_no_option_calls(rig):
    _, state, module = rig
    boot(state, module)
    run(module, 20.0)
    obstacle_calls = len(state.obstacleCalls)
    module.onScenarioRestarted()
    run(module, 30.0)
    assert calls(state) == []
    assert len(state.obstacleCalls) == obstacle_calls
    assert system(module).booted is True
    assert len(events(state, "boot")) == 1


def test_scenario_restart_mid_decay_restores_once_and_resets_the_round(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    run(module, 121.0)
    assert calls(state) == [("arena_radius_m", 75.0)]
    module.onScenarioRestarted()
    assert calls(state) == [("arena_radius_m", 75.0), ("arena_radius_m", 91.4)]
    assert system(module).valve.stage == 0 and system(module).valve.in_round is False
    assert system(module).clock == 0
    end_round(state)
    run(module, 30.0)
    assert len(calls(state)) == 2


def test_engine_reload_on_restart_hands_back_then_the_fresh_instance_resnapshots(rig):
    """The engine unloads and reloads the scenario extension on restart. The
    unload hands the player's values back (2 calls here), the fresh instance
    boots on the restored values (5 calls) and snapshots them - never the
    arena's own values, and never anything global."""

    lua, state, module = rig
    state.options.ai_enabled = False
    boot(state, module)
    module.onExtensionUnloaded()
    assert calls(state) == [("ai_enabled", False), OOB_HANDBACK]
    assert state.snapshotGlobal() is None
    assert state.snapshotFile() is None
    fresh = lua.execute(LUA_PATH.read_text(encoding="utf-8"))
    fresh.onExtensionLoaded()
    state.clearCalls()
    tick(fresh, 0.1, 2)
    assert len(calls(state)) == len(BOOT_KEYS)
    assert fresh.getSystemState().snapshot.ai_enabled is False
    assert fresh.getSystemState().recovered_calls == 0
    state.clearCalls()
    fresh.onClientEndMission(MISSION_PATH)
    assert calls(state) == [("ai_enabled", False), OOB_HANDBACK]
    assert state.options.ai_enabled is False
    assert state.snapshotGlobal() is None and state.snapshotFile() is None


def test_the_next_mission_snapshots_the_players_current_values_not_stale_ones(rig):
    """The player flips ai_enabled on BETWEEN two arena visits; the second
    visit must hand back true, not the first visit's false."""

    lua, state, module = rig
    state.options.ai_enabled = False
    boot(state, module)
    module.onExtensionUnloaded()  # the pause menu's Exit scenario path
    state.options.ai_enabled = True  # the player's change between visits
    fresh = lua.execute(LUA_PATH.read_text(encoding="utf-8"))
    fresh.onExtensionLoaded()
    state.clearCalls()
    tick(fresh, 0.1, 2)
    assert fresh.getSystemState().snapshot.ai_enabled is True
    state.clearCalls()
    fresh.onExtensionUnloaded()
    assert calls(state) == [OOB_HANDBACK]
    assert state.options.ai_enabled is True


# --- option restore (critique fix 3) ------------------------------------------


def test_mission_end_hands_back_only_the_options_the_arena_changed(rig):
    _, state, module = rig
    state.options.ai_enabled = False
    state.options.arena_magnet_enabled = False
    before = options(state)
    boot(state, module)
    assert options(state) == ARENA_VALUES
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == [("ai_enabled", False), ("arena_magnet_enabled", False), OOB_HANDBACK]
    assert options(state) == before
    assert system(module).ended is True


def test_mission_end_hands_back_only_what_the_arena_changed(rig):
    _, state, module = rig
    # Everything the arena writes already matches the player EXCEPT the OOB
    # burn, which the runtime ships OFF - so exactly one hand-back is owed.
    state.options.ai_enabled = True
    boot(state, module)
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == [OOB_HANDBACK]


def test_a_custom_player_radius_is_handed_back_but_a_crashed_valve_radius_is_not(rig):
    lua, state, module = rig
    state.options.arena_radius_m = 120.0
    state.options.ai_enabled = True
    boot(state, module)
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == [("arena_radius_m", 120.0), OOB_HANDBACK]
    # A dirty 60 left by a session that died mid-decay: the boot self-heals
    # it to 91.4 and mission end must not put the dirt back.
    _, state2, module2 = _make_rig()
    state2.options.arena_radius_m = 60.0
    state2.options.ai_enabled = True
    boot(state2, module2)
    assert state2.options.arena_radius_m == 91.4
    module2.onClientEndMission(MISSION_PATH)
    assert calls(state2) == [OOB_HANDBACK]


def test_exit_scenario_unload_without_mission_end_hands_the_options_back(rig):
    """homeRail's "Exit scenario" calls scenario_scenarios.stop(), which
    unloads this extension BEFORE clientEndMission (critique r2, fix 1)."""

    _, state, module = rig
    state.options.ai_enabled = False
    state.options.arena_magnet_enabled = False
    before = options(state)
    boot(state, module)
    module.onExtensionUnloaded()
    assert calls(state) == [("ai_enabled", False), ("arena_magnet_enabled", False), OOB_HANDBACK]
    assert options(state) == before
    assert state.snapshotFile() is None and state.snapshotGlobal() is None
    # The level unload raises clientEndMission later (extension gone in the
    # engine; here the same instance): a second hand-back is a no-op.
    module.onClientEndMission(MISSION_PATH)
    assert len(calls(state)) == 3
    assert system(module).ended is True


def test_double_hand_back_is_a_no_op_in_either_order(rig):
    _, state, module = rig
    state.options.ai_enabled = False
    boot(state, module)
    module.onClientEndMission(MISSION_PATH)
    module.onExtensionUnloaded()
    assert calls(state) == [("ai_enabled", False), OOB_HANDBACK]


def test_crash_leftover_snapshot_is_handed_back_before_the_next_boot_writes(rig):
    """A mission that died (Alt-F4) left the snapshot file and the arena's
    values persisted. The next boot restores the file's values FIRST, then
    snapshots afresh, writes a fresh file, and only then writes its five."""

    _, state, module = rig
    # Persisted dirt from the dead session (the arena's own values), and its
    # leftover snapshot file (the player's).
    state.options.ai_enabled = True
    state.options.arena_magnet_enabled = True
    state.options.oob_burn_multiplier = 3.0
    _plant(
        state,
        {
            "arena_radius_m": 91.4,
            "arena_enabled": True,
            "ai_enabled": False,
            "arena_magnet_enabled": False,
            "oob_burn_multiplier": 1.0,
        },
    )
    state.installRuntime()
    tick(module, 0.1, 2)
    assert calls(state)[:3] == [
        ("ai_enabled", False),
        ("arena_magnet_enabled", False),
        OOB_HANDBACK,
    ]
    assert calls(state)[3:] == [
        ("arena_radius_m", 91.4),
        ("arena_enabled", True),
        ("ai_enabled", True),
        ("arena_magnet_enabled", True),
        ("oob_burn_multiplier", 3.0),
    ]
    assert system(module).recovered_calls == 3
    assert len(events(state, "snapshot_recovered")) == 1
    snapshot = system(module).snapshot
    assert snapshot.ai_enabled is False and snapshot.arena_magnet_enabled is False
    assert snapshot.oob_burn_multiplier == 1.0
    assert state.snapshotFile().options.ai_enabled is False
    state.clearCalls()
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == [("ai_enabled", False), ("arena_magnet_enabled", False), OOB_HANDBACK]
    assert state.snapshotFile() is None


def test_tuner_change_mid_mission_is_preserved_at_exit(rig):
    """Critic r3 fix 2: the HUD tuner exposes every boot key. A value the
    player set mid-mission is theirs; only the ARENA's own value is undone."""

    _, state, module = rig
    state.options.ai_enabled = True
    state.options.arena_magnet_enabled = False
    boot(state, module)
    # Tuner: ai off, radius 120 (both differ from what the arena wrote).
    state.options.ai_enabled = False
    state.options.arena_radius_m = 120.0
    module.onClientEndMission(MISSION_PATH)
    # magnet: current true == arena value, != snapshot false -> handed back.
    # ai: current false != arena value true -> the player's, preserved.
    # radius: current 120 != arena 91.4 -> preserved (no restoreRadius call
    # either: the valve never decayed).
    assert calls(state) == [("arena_magnet_enabled", False), OOB_HANDBACK]
    assert state.options.ai_enabled is False and state.options.arena_radius_m == 120.0


def test_tuner_change_mid_mission_survives_a_restart_unload(rig):
    lua, state, module = rig
    state.options.ai_enabled = True
    boot(state, module)
    state.options.ai_enabled = False  # tuner
    module.onExtensionUnloaded()
    assert calls(state) == [OOB_HANDBACK]
    assert state.options.ai_enabled is False
    fresh = lua.execute(LUA_PATH.read_text(encoding="utf-8"))
    fresh.onExtensionLoaded()
    state.clearCalls()
    tick(fresh, 0.1, 2)
    assert fresh.getSystemState().snapshot.ai_enabled is False, (
        "the fresh instance snapshots the tuner value"
    )


def test_crash_recovery_leaves_a_between_visit_change_alone(rig):
    """A dead visit left ai/magnet ON; the player then set radius 120 in
    freeroam. Recovery hands back only the arena's own dirt."""

    _, state, module = rig
    state.options.ai_enabled = True
    state.options.arena_magnet_enabled = True
    state.options.arena_radius_m = 120.0  # the player's freeroam change
    _plant(
        state,
        {
            "arena_radius_m": 91.4,
            "arena_enabled": True,
            "ai_enabled": False,
            "arena_magnet_enabled": False,
        },
    )
    state.installRuntime()
    tick(module, 0.1, 2)
    assert calls(state)[:2] == [("ai_enabled", False), ("arena_magnet_enabled", False)]
    assert system(module).recovered_calls == 2
    assert system(module).snapshot.arena_radius_m == 120.0, (
        "the fresh snapshot carries the player's 120 home"
    )
    module.onClientEndMission(MISSION_PATH)
    assert state.options.arena_radius_m == 120.0
    assert state.options.ai_enabled is False and state.options.arena_magnet_enabled is False


def test_accepted_edge_a_final_value_equal_to_the_arenas_is_handed_back(rig):
    """Critic r4 LOW 2, pinned as ACCEPTED behaviour: a player who toggles a
    key off then back ON (landing on the arena's own value), or types 91.4
    over a pre-mission 120, is indistinguishable from the arena's write and
    gets the pre-mission value back. Unobservable at exit; documented."""

    _, state, module = rig
    state.options.ai_enabled = False
    state.options.arena_radius_m = 120.0
    boot(state, module)
    state.options.ai_enabled = False  # tuner: off ...
    state.options.ai_enabled = True  # ... then on again == the arena's value
    state.options.arena_radius_m = 91.4  # tuner: typed the arena's value
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == [("arena_radius_m", 120.0), ("ai_enabled", False), OOB_HANDBACK]


def test_tuner_radius_set_during_a_decay_window_is_left_alone(rig):
    """Critic r4 LOW 3: the valve restores only while the runtime still holds
    the valve's own last-written step."""

    _, state, module = rig
    state.options.ai_enabled = True
    boot(state, module)
    start_round(state)
    run(module, 121.0)
    assert calls(state) == [("arena_radius_m", 75.0)]
    state.options.arena_radius_m = 120.0  # tuner, mid-decay
    end_round(state)
    tick(module, 0.5)
    assert calls(state) == [("arena_radius_m", 75.0)], "no 91.4 written over the player's 120"
    assert len(events(state, "valve_restore_skipped")) == 1
    assert system(module).valve.stage == 0 and system(module).valve.radius == 91.4
    run(module, 30.0)
    assert len(calls(state)) == 1, "nothing retried"
    # Mission end: current 120 != snapshot 91.4 but != the arena's 91.4 -> kept.
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == [("arena_radius_m", 75.0), OOB_HANDBACK], "the 120 is never written over"
    assert state.options.arena_radius_m == 120.0


def test_tuner_radius_during_a_decay_is_left_alone_by_the_watchdog_and_teardown(rig):
    _, state, module = rig
    state.options.ai_enabled = True
    boot(state, module)
    start_round(state)
    run(module, 181.0)
    assert len(calls(state)) == 2
    state.options.arena_radius_m = 60.5  # tuner, one tick off the valve's 60
    state.registered = False
    run(module, 6.0)
    assert len(calls(state)) == 2 and system(module).valve.disarmed is True
    module.onExtensionUnloaded()
    assert len(calls(state)) == 3 and calls(state)[-1] == OOB_HANDBACK
    assert state.options.arena_radius_m == 60.5


def test_valve_still_restores_when_the_runtime_holds_its_own_step(rig):
    _, state, module = rig
    state.options.ai_enabled = True
    boot(state, module)
    start_round(state)
    run(module, 181.0)
    end_round(state)
    tick(module, 0.5)
    assert calls(state) == [
        ("arena_radius_m", 75.0),
        ("arena_radius_m", 60.0),
        ("arena_radius_m", 91.4),
    ]
    assert events(state, "valve_restore_skipped") == []


def test_untouched_keys_still_restore_when_one_was_tuned(rig):
    _, state, module = rig
    state.options.ai_enabled = False
    state.options.arena_magnet_enabled = False
    boot(state, module)
    state.options.arena_magnet_enabled = False  # tuner turned the magnet back off
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == [("ai_enabled", False), OOB_HANDBACK]


def test_unwritable_snapshot_file_is_reported_and_the_mission_still_plays(rig):
    _, state, module = rig
    state.writeResult = False
    state.installRuntime()
    tick(module, 0.1, 2)
    assert system(module).booted is True
    assert system(module).snapshot_file_written is False
    assert len(events(state, "snapshot_file_unwritable")) == 1
    assert len(calls(state)) == len(BOOT_KEYS)
    assert state.snapshotFile() is None
    # Fail-open: the in-memory snapshot still hands back at exit.
    state.options.ai_enabled = True
    state.clearCalls()
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == [("ai_enabled", False), OOB_HANDBACK]


def test_a_clean_session_leaves_no_snapshot_file(rig):
    _, state, module = rig
    boot(state, module)
    assert state.snapshotFile() is not None
    module.onClientEndMission(MISSION_PATH)
    assert state.snapshotFile() is None
    assert not any(str(k).endswith(".snapshot.json") for k in dict(state.files).keys())


def test_crash_recovery_never_hands_back_a_valve_radius(rig):
    _, state, module = rig
    state.options.ai_enabled = True
    _plant(
        state,
        {
            "arena_radius_m": 60.0,
            "arena_enabled": True,
            "ai_enabled": True,
            "arena_magnet_enabled": True,
        },
    )
    state.installRuntime()
    tick(module, 0.1, 2)
    assert calls(state) == [
        ("arena_radius_m", 91.4),
        ("arena_enabled", True),
        ("ai_enabled", True),
        ("arena_magnet_enabled", True),
        ("oob_burn_multiplier", 3.0),
    ]
    assert system(module).recovered_calls == 0


# --- ended latch (critique fix 8) ---------------------------------------------


def test_no_reboot_after_mission_end_until_the_next_mission_starts(rig):
    _, state, module = rig
    boot(state, module)
    module.onClientEndMission(MISSION_PATH)
    state.clearCalls()
    run(module, 30.0)
    assert calls(state) == []
    assert system(module).booted is False and system(module).ended is True
    module.onClientStartMission(MISSION_PATH)
    tick(module, 0.1, 2)
    assert len(calls(state)) == len(BOOT_KEYS)
    assert system(module).booted is True


# --- obstacle upkeep (critique fix 6) -----------------------------------------


def test_obstacles_reregister_once_when_the_runtime_is_a_new_instance(rig):
    _, state, module = rig
    boot(state, module)
    run(module, 20.0)
    assert len(state.obstacleCalls) == 1
    state.removeRuntime()
    run(module, 10.0)
    state.installRuntime()
    state.dropObstacles()
    run(module, 1.0)
    assert len(state.obstacleCalls) == 2
    assert system(module).obstacle_reason == "runtime_reloaded"
    run(module, 60.0)
    assert len(state.obstacleCalls) == 2
    assert calls(state) == []


def test_obstacles_reregister_once_when_the_prop_comes_back(rig):
    _, state, module = rig
    boot(state, module)
    state.registered = False
    run(module, 10.0)
    assert len(state.obstacleCalls) == 1
    state.registered = True
    run(module, 1.0)
    assert len(state.obstacleCalls) == 2
    assert system(module).obstacle_reason == "prop_returned"
    run(module, 60.0)
    assert len(state.obstacleCalls) == 2


def test_obstacle_count_drift_is_repaired_within_the_check_cadence(rig):
    _, state, module = rig
    boot(state, module)
    run(module, 20.0)
    state.dropObstacles()
    run(module, 6.0)
    assert len(state.obstacleCalls) == 2
    assert system(module).obstacle_reason == "count_drift"
    run(module, 60.0)
    assert len(state.obstacleCalls) == 2


def test_without_the_count_getter_a_stable_runtime_is_never_reregistered(rig):
    _, state, module = rig
    state.getterPresent = False
    boot(state, module)
    run(module, 120.0)
    assert len(state.obstacleCalls) == 1


def test_a_refusing_hook_is_retried_with_capped_exponential_backoff(rig):
    """LOW fix 3: a hook that returns false must not be nagged every 5 s.
    The boot refusal doubles the interval, so retries land at 10, 30, 70,
    130, 190, 250 s -> exactly 7 calls (boot + 6) in the first 5 minutes
    (13 per minute before), one warning per call."""

    _, state, module = rig
    state.hookResult = False
    state.installRuntime()
    tick(module, 0.1, 2)
    assert system(module).obstacles == "refused"
    assert system(module).obstacle_interval == 10.0
    run(module, 300.0)
    total = len(state.obstacleCalls)
    assert total == 7, total
    warnings = [
        e for e in state.events.values() if e.level == "W" and '"event":"obstacles"' in e.message
    ]
    assert len(warnings) == total
    assert system(module).obstacle_interval == 60.0
    # A fresh runtime instance re-arms the cadence and the hook now accepts.
    state.hookResult = True
    state.installRuntime()
    run(module, 1.0)
    assert system(module).obstacles == "registered"
    assert system(module).obstacle_interval == 5.0
    run(module, 120.0)
    assert len(state.obstacleCalls) == total + 1


# --- geysers ----------------------------------------------------------------


def test_gate_geyser_keeps_the_wisp_on_and_cycles_the_curtain_8s_off_4s_on(rig):
    _, state, module = rig
    boot(state, module)
    assert gate_active(state) == ([True], [False, False, False])
    run(module, 7.5)
    assert gate_active(state) == ([True], [False, False, False])
    run(module, 1.0)
    assert gate_active(state) == ([True], [True, True, True])
    assert system(module).geysers[1].on is True
    run(module, 4.0)
    assert gate_active(state) == ([True], [False, False, False])
    assert system(module).geysers[1].windows == 1
    run(module, 12.0)
    assert system(module).geysers[1].windows == 2


def test_spout_geysers_are_phase_shifted_so_the_bowl_always_moves(rig):
    _, state, module = rig
    boot(state, module)
    all_on = 0
    any_on = 0
    total = 0
    for _ in range(int(84 / 0.5)):
        tick(module, 0.5)
        geysers = system(module).geysers
        states = [geysers[i].on for i in (1, 2, 3)]
        total += 1
        any_on += 1 if any(states) else 0
        all_on += 1 if all(states) else 0
    assert any_on / total > 0.75
    assert all_on < total / 4
    assert system(module).geysers[2].windows >= 5 and system(module).geysers[3].windows >= 5


def test_vehicle_inside_the_strip_pops_once_per_on_window_as_a_velocity_add(rig):
    _, state, module = rig
    boot(state, module)
    state.addVehicle(11, "car_in_strip", *GATE_STRIP)
    state.addVehicle(12, "car_outside", *OUTSIDE)
    run(module, 7.5)  # OFF window
    assert len(state.pops) == 0
    run(module, 4.5)  # through the first ON window
    pops = [(p.id, p.scale, p.x, p.y, p.z) for p in state.pops.values()]
    assert pops == [(11, 1, 0, 0, 5.5)], (
        "scale 1 is the ADD form; 0 would replace the car's velocity"
    )
    run(module, 12.0)  # next window
    assert [p.id for p in state.pops.values()] == [11, 11]
    assert system(module).geysers[1].pops == 2
    assert len(events(state, "geyser_pop")) == 2


def test_dispenser_and_airborne_vehicles_are_never_popped(rig):
    _, state, module = rig
    boot(state, module)
    state.moveVehicle(7, *GATE_STRIP)  # the dispenser parked in the strip
    state.addVehicle(13, "flying", GATE_STRIP[0], GATE_STRIP[1], 108.0)
    run(module, 30.0)
    assert len(state.pops) == 0


def test_a_site_whose_emitters_did_not_resolve_never_pops():
    _, state, module = _make_rig(with_emitters=False)
    boot(state, module)
    state.addVehicle(11, "car_in_strip", *GATE_STRIP)
    run(module, 40.0)
    assert len(state.pops) == 0
    assert system(module).geysers[1].blind is True
    assert len(events(state, "geyser_blind")) >= 1
    assert len([e for e in events(state, "geyser_blind") if '"site":"gate"' in e]) == 1
    # The emitters arrive late (a slow prefab): the site comes alive.
    for name in EMITTER_NAMES:
        state.addEmitter(name, name.endswith("wisp_1"))
    run(module, 13.0)
    assert len(state.pops) == 1
    assert system(module).geysers[1].blind is False


def test_a_partially_resolved_site_is_blind(rig):
    _, state, module = rig
    state.removeEmitter(GATE_CURTAIN[0])
    boot(state, module)
    state.addVehicle(11, "car_in_strip", *GATE_STRIP)
    run(module, 30.0)
    assert len(state.pops) == 0
    assert system(module).geysers[1].blind is True


def test_pop_state_is_bounded_across_many_windows_and_vehicles(rig):
    _, state, module = rig
    boot(state, module)
    for index in range(20):
        state.addVehicle(100 + index, f"car_{index}", *GATE_STRIP)
    run(module, 12.0 * 6)
    assert system(module).geysers[1].pops == 20 * 6
    run(module, 12.0)
    assert system(module).geysers[1].pops == 20 * 7


# --- decay valve --------------------------------------------------------------


def test_stalled_round_decays_in_two_steps_and_restores_on_round_end(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    run(module, 119.0)
    assert calls(state) == []
    run(module, 2.0)
    assert calls(state) == [("arena_radius_m", 75.0)]
    assert system(module).valve.stage == 1
    run(module, 58.0)
    assert calls(state) == [("arena_radius_m", 75.0)]
    run(module, 2.0)
    assert calls(state) == [("arena_radius_m", 75.0), ("arena_radius_m", 60.0)]
    run(module, 300.0)
    assert len(calls(state)) == 2, "no further steps below 60"
    end_round(state)
    tick(module, 0.5)
    assert calls(state)[-1] == ("arena_radius_m", 91.4)
    assert len(calls(state)) == 3
    assert system(module).valve.stage == 0
    assert system(module).valve.round_calls == 3
    run(module, 60.0)
    assert len(calls(state)) == 3


@pytest.mark.parametrize("exit_phase", ["boom", "return", "idle"])
def test_every_round_exit_path_restores_the_radius(rig, exit_phase):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    run(module, 121.0)
    assert calls(state) == [("arena_radius_m", 75.0)]
    end_round(state, exit_phase)
    tick(module, 0.5)
    assert calls(state) == [("arena_radius_m", 75.0), ("arena_radius_m", 91.4)]


def test_a_pass_resets_the_stall_clock(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    run(module, 100.0)
    state.stats.transfers = 1
    state.stats.carrier = 12
    run(module, 100.0)
    assert calls(state) == []
    run(module, 21.0)
    assert calls(state) == [("arena_radius_m", 75.0)]


def test_a_round_that_never_stalls_costs_zero_calls(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    for index in range(10):
        run(module, 60.0)
        state.stats.transfers = index + 1
    end_round(state)
    tick(module, 0.5)
    assert calls(state) == []


def test_watchdog_restores_once_and_disarms_when_the_prop_dies_mid_decay(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    run(module, 121.0)
    assert calls(state) == [("arena_radius_m", 75.0)]
    state.removeVehicle(7)
    state.registered = False
    run(module, 4.5)
    assert len(calls(state)) == 1
    run(module, 1.0)
    assert calls(state) == [("arena_radius_m", 75.0), ("arena_radius_m", 91.4)]
    assert system(module).valve.disarmed is True
    assert system(module).valve.stage == 0
    run(module, 400.0)
    assert len(calls(state)) == 2, "a dead prop must not be nagged"
    assert len(events(state, "valve_watchdog")) == 1


def test_watchdog_keys_on_registration_not_just_the_scene_object(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    run(module, 181.0)
    assert len(calls(state)) == 2
    state.registered = False
    run(module, 6.0)
    assert calls(state)[-1] == ("arena_radius_m", 91.4)
    assert len(calls(state)) == 3


def test_watchdog_rearms_when_the_prop_comes_back(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    run(module, 121.0)
    state.registered = False
    run(module, 6.0)
    assert system(module).valve.disarmed is True
    state.registered = True
    state.stats.phase = "idle"
    tick(module, 0.5)
    assert system(module).valve.disarmed is False
    start_round(state, carrier=21)
    run(module, 121.0)
    assert calls(state)[-1] == ("arena_radius_m", 75.0)


def test_steady_tick_stall_with_a_frozen_payload_does_not_false_restore(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    run(module, 121.0)
    assert calls(state) == [("arena_radius_m", 75.0)]
    run(module, 61.0)
    assert calls(state) == [("arena_radius_m", 75.0), ("arena_radius_m", 60.0)]
    run(module, 600.0)
    assert len(calls(state)) == 2
    assert system(module).valve.stage == 2
    assert system(module).valve.disarmed is False
    assert events(state, "valve_watchdog") == []


def test_refused_decay_is_not_retried_and_spends_no_restore_call(rig):
    _, state, module = rig
    boot(state, module)
    state.setOptionResult = False
    start_round(state)
    run(module, 125.0)
    assert len(calls(state)) == 1
    run(module, 300.0)
    assert len(calls(state)) == 2
    assert system(module).valve.failed is True
    end_round(state)
    run(module, 5.0)
    assert len(calls(state)) == 2, "the radius never moved, so nothing is restored"


# --- cleanup ------------------------------------------------------------------


def test_mission_end_restores_the_radius_clears_obstacles_and_douses_emitters(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    run(module, 121.0)
    assert calls(state) == [("arena_radius_m", 75.0)]
    run(module, 8.5)  # gate ON
    assert gate_active(state) == ([True], [True, True, True])
    module.onClientEndMission(MISSION_PATH)
    assert ("arena_radius_m", 91.4) in calls(state)
    assert len(state.obstacleCalls) == 2 and len(state.obstacleCalls[2]) == 0
    assert gate_active(state) == ([False], [False, False, False])
    assert system(module).booted is False and system(module).ended is True
    run(module, 5.0)
    assert len(calls(state)) == 4, "no re-boot after mission end"


def test_mission_end_without_a_decay_makes_no_radius_call(rig):
    _, state, module = rig
    state.options.ai_enabled = True  # nothing but the OOB switch to hand back
    boot(state, module)
    module.onClientEndMission(MISSION_PATH)
    assert calls(state) == [OOB_HANDBACK]
    assert "arena_radius_m" not in [key for key, _ in calls(state)]


def test_extension_unload_restores_the_radius_like_mission_end(rig):
    _, state, module = rig
    state.options.ai_enabled = True  # nothing else to hand back
    boot(state, module)
    start_round(state)
    run(module, 181.0)
    module.onExtensionUnloaded()
    # teardown order: the radius first, then the option hand-back.
    assert ("arena_radius_m", 91.4) in calls(state)
    assert calls(state)[-1] == OOB_HANDBACK
    assert len(calls(state)) == 4


def test_missing_runtime_after_boot_never_raises(rig):
    _, state, module = rig
    boot(state, module)
    start_round(state)
    state.removeRuntime()
    run(module, 200.0)
    assert calls(state) == []
    assert not [e for e in state.events.values() if e.level == "E"]
