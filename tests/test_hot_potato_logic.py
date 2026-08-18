"""Headless state-machine gate for Hot Potato's generated GE runtime.

Every other prop in the pack is a fixed machine exercised with ONE subject, so
the pack's existing gates cannot see this mod's actual mechanic at all: the
potato only means anything with several vehicles in play, and its failure
modes (a pass that ping-pongs every tick, a fuse that never fires, a carrier
that vanishes and takes the round with it) are all multi-vehicle.

This runs the REAL generated ``runtime.lua`` under lupa against stubbed engine
globals. It cannot prove physics - no deformation, no particles, no lights are
real here - but it proves the logic those things hang off:

- driving through the gate starts a round and gives the potato to that car,
- contact passes it to the nearest eligible car,
- the previous carrier is immune for the cooldown, so it cannot bounce back,
- the fuse runs on the wall clock and detonates the CURRENT carrier,
- detonation issues the vehicle-side break/crush/fire commands,
- a carrier that despawns sends the potato home instead of picking a victim.

The live gate on a sentinel-isolated profile is still required before shipping;
this is the cheap half that runs on every commit.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "hot_potato"


def load_spec():
    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader_spec = importlib.util.spec_from_file_location("hot_potato_spec", spec_path)
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)
    return module


# The engine surface runtime.lua actually touches. Everything is the smallest
# stub that behaves like the real thing for the paths under test.
STUBS = r"""
local S = {}
S.messages = {}
S.events = {}
S.commands = {}
S.velocities = {}
S.clockMs = 0
S.scene = {}
S.vehicles = {}

-- vec3 / quat ------------------------------------------------------------
local vecmt = {}
vecmt.__index = vecmt
function vecmt.__add(a, b) return vec3(a.x + b.x, a.y + b.y, a.z + b.z) end
function vecmt.__sub(a, b) return vec3(a.x - b.x, a.y - b.y, a.z - b.z) end
function vecmt.__mul(a, b)
  if type(a) == "number" then return vec3(a * b.x, a * b.y, a * b.z) end
  if type(b) == "number" then return vec3(a.x * b, a.y * b, a.z * b) end
  return vec3(a.x * b.x, a.y * b.y, a.z * b.z)
end
function vecmt.__unm(a) return vec3(-a.x, -a.y, -a.z) end
function vecmt:length() return math.sqrt(self.x^2 + self.y^2 + self.z^2) end
function vecmt:dot(o) return self.x * o.x + self.y * o.y + self.z * o.z end
function vecmt:normalize()
  local l = self:length()
  if l > 0 then self.x, self.y, self.z = self.x / l, self.y / l, self.z / l end
  return self
end
function vecmt:normalized()
  return vec3(self.x, self.y, self.z):normalize()
end
function vecmt:getRotationTo() return quat(0, 0, 0, 1) end
function vecmt:toTable() return {self.x, self.y, self.z} end
function vec3(x, y, z)
  if type(x) == "table" then x, y, z = x.x or x[1], x.y or x[2], x.z or x[3] end
  return setmetatable({x = x or 0, y = y or 0, z = z or 0}, vecmt)
end

local quatmt = {}
quatmt.__index = quatmt
-- Identity-only composition is enough: this harness never yaws the prop, and
-- rotation correctness is a live-render question, not a logic one.
function quatmt.__mul(a, b)
  if getmetatable(b) == vecmt then return vec3(b.x, b.y, b.z) end
  return quat(0, 0, 0, 1)
end
function quatmt:toTorqueQuat() return self end
function quat(x, y, z, w)
  if type(x) == "table" then x, y, z, w = x[1] or 0, x[2] or 0, x[3] or 0, x[4] or 1 end
  return setmetatable({x = x or 0, y = y or 0, z = z or 0, w = w or 1}, quatmt)
end
function quatFromDir() return quat(0, 0, 0, 1) end

-- scene objects ----------------------------------------------------------
local objmt = {}
objmt.__index = objmt
function objmt:setField(name, _i, value) self.fields[name] = value end
function objmt:getField(name) return self.fields[name] end
function objmt:getClassName() return self.class end
function objmt:getName() return self.name end
function objmt:getID() return self.id end
function objmt:setCanSave() end
function objmt:registerObject(name)
  self.name = name
  S.scene[name] = self
end
function objmt:addObject() end
function objmt:setPosRot() end
function objmt:setPosition() end
function objmt:setScale() end
function objmt:setEmitterDataBlock() end
function objmt:setActive(on) self.active = on and true or false end
function objmt:delete() if self.name then S.scene[self.name] = nil end end

local nextObjectId = 1000
function createObject(class)
  nextObjectId = nextObjectId + 1
  return setmetatable(
    {class = class, fields = {}, id = nextObjectId, active = false}, objmt)
end

scenetree = {}
scenetree.MissionGroup = setmetatable({class = "SimGroup", fields = {}}, objmt)
function scenetree.findObject(name)
  if S.scene[name] then return S.scene[name] end
  -- Materials and stock particle datablocks resolve by name.
  if type(name) == "string" and (name:find("BNGP_") == 1) then
    return setmetatable({class = "ParticleEmitterData", fields = {}}, objmt)
  end
  -- Palette materials resolve by name, but a runtime scene object is named
  -- <mod>_p<propId>_<slot> and must NOT: registerInMission refuses a name
  -- that already resolves, so a greedy match here made every part, trigger
  -- and effect fail to register with "scene name is already in use".
  if type(name) == "string" and name:find("ericrolph_") == 1
    and not name:find("_p%d+_") then
    return setmetatable({class = "Material", fields = {}}, objmt)
  end
  return nil
end
function scenetree.findObjectById(id)
  for _, object in pairs(S.scene) do
    if object.id == id then return object end
  end
  return nil
end

-- vehicles ---------------------------------------------------------------
local vehmt = {}
vehmt.__index = vehmt
function vehmt:getId() return self.id end
function vehmt:getPosition() return vec3(self.pos.x, self.pos.y, self.pos.z) end
function vehmt:getRotation() return {0, 0, 0, 1} end
function vehmt:getJBeamFilename() return self.model end
function vehmt:getRefNodeId() return 0 end
function vehmt:getSpawnWorldOOBB()
  local half = self.half
  return {getHalfExtents = function() return vec3(half.x, half.y, half.z) end}
end
function vehmt:queueLuaCommand(command)
  S.commands[#S.commands + 1] = {id = self.id, command = command}
end
function vehmt:applyClusterVelocityScaleAdd(_node, _scale, x, y, z)
  S.velocities[#S.velocities + 1] = {id = self.id, x = x, y = y, z = z}
end
function vehmt:setPositionRotation() end

function S.addVehicle(id, model, x, y, z, hx, hy, hz)
  local vehicle = setmetatable({
    id = id, model = model,
    pos = {x = x, y = y, z = z},
    half = {x = hx or 0.95, y = hy or 2.3, z = hz or 0.75},
  }, vehmt)
  S.vehicles[id] = vehicle
  return vehicle
end

function S.moveVehicle(id, x, y, z)
  local vehicle = S.vehicles[id]
  vehicle.pos.x, vehicle.pos.y, vehicle.pos.z = x, y, z
end

function S.removeVehicle(id) S.vehicles[id] = nil end

function S.clear()
  S.commands = {}
  S.velocities = {}
  S.messages = {}
end

function getAllVehicles()
  local list = {}
  for _, vehicle in pairs(S.vehicles) do list[#list + 1] = vehicle end
  table.sort(list, function(a, b) return a.id < b.id end)
  return list
end

be = {}
function be:getObjectByID(id) return S.vehicles[id] end
function be:reloadCollision() end

-- misc engine surface ----------------------------------------------------
Engine = {Platform = {getSystemTimeMS = function() return S.clockMs end}}
guihooks = {message = function(payload, ttl, category)
  S.messages[#S.messages + 1] = tostring(payload.txt or "")
end}
function log(level, tag, message)
  S.events[#S.events + 1] = {level = level, message = message}
end
function jsonEncode(value) return tostring(value) end
core_vehicle_manager = {getVehicleData = function() return nil end}
function loadJsonMaterialsFile() return true end

return S
"""


@pytest.fixture()
def rig():
    spec = load_spec()
    runtime_path = (
        PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID
        / "runtime.lua"
    )
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    state = lua.execute(STUBS)
    module = lua.execute(runtime_path.read_text(encoding="utf-8"))
    return lua, state, module, spec


PROP_ID = 1


def register_prop(state, module):
    state.addVehicle(PROP_ID, "ericrolph_hot_potato", 0.0, 0.0, 0.0, 5.6, 7.0, 3.1)
    module.registerProp(PROP_ID)


def tick(state, module, seconds=0.05, steps=1):
    for _ in range(steps):
        state.clockMs = state.clockMs + seconds * 1000.0
        module.onPreRender(seconds, seconds, seconds)


def drive_through_gate(lua, state, module, vehicle_id):
    """Deliver the Contains enter event the way the engine would."""

    trigger_name = f"ericrolph_hot_potato_p{PROP_ID}_start_gate"
    trigger = state.scene[trigger_name]
    # A Python dict crosses as an opaque object; the runtime's first guard is
    # `type(data) ~= "table"`, so the event has to be a real Lua table.
    module.onBeamNGTrigger(lua.table_from({
        "event": "enter",
        "triggerID": trigger.id,
        "triggerName": trigger_name,
        "subjectID": vehicle_id,
    }))


def test_registers_with_triggers_effects_and_the_potato(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    system = module.getSystemState(PROP_ID)
    assert system.registered is True
    assert system.part_count == 1
    assert system.trigger_count == 1
    assert system.triggers.start_gate.mode == "Contains"
    assert system.triggers.start_gate.test_type == "Bounding box"
    # Three declared particle emitters plus the three beacon light objects the
    # behaviour makes itself and parks in state.effects for teardown.
    assert system.effect_count == 6


def test_gate_entry_starts_a_round(rig):
    lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    tick(state, module)
    drive_through_gate(lua, state, module, 2)
    tick(state, module)
    assert module.getSystemState(PROP_ID).behavior_phase == "live"
    assert any("GOT IT" in message for message in state.messages.values())


def test_contact_passes_the_potato_and_the_cooldown_stops_the_bounce_back(rig):
    lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    drive_through_gate(lua, state, module, 2)
    # Everyone on the field at round start carries the join-immunity grace,
    # so wait it out before testing the pass itself.
    tick(state, module, seconds=0.1,
         steps=int(spec.BEHAVIOR["join_immunity_seconds"] / 0.1) + 4)

    # Well apart: no pass.
    tick(state, module, steps=3)
    assert _carrier_of(module) == 2

    # Bumper to bumper: the pass lands on the next tick.
    state.moveVehicle(3, 2.0, 0.0, 0.0)
    tick(state, module)
    assert _carrier_of(module) == 3
    assert any("PASSED" in message for message in state.messages.values())

    # Still touching. The immunity window on vehicle 2 is what has to stop the
    # potato returning; without it this ping-pongs every single tick.
    cooldown = spec.BEHAVIOR["cooldown_seconds"]
    tick(state, module, seconds=0.05, steps=int(cooldown / 0.05) - 4)
    assert _carrier_of(module) == 3, "potato bounced back inside the cooldown"

    # Once the window expires it may legitimately come back.
    tick(state, module, seconds=0.05, steps=12)
    assert _carrier_of(module) == 2


def test_join_immunity_protects_a_car_that_just_appeared(rig):
    lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    tick(state, module)
    drive_through_gate(lua, state, module, 2)
    tick(state, module)

    # Spawning right on top of the carrier must not be instant death.
    state.addVehicle(3, "etk800", 1.5, 0.0, 0.0)
    tick(state, module)
    assert _carrier_of(module) == 2
    tick(state, module, seconds=0.05,
         steps=int(spec.BEHAVIOR["join_immunity_seconds"] / 0.05) + 4)
    assert _carrier_of(module) == 3


def test_fuse_detonates_the_current_carrier(rig):
    lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 80.0, 0.0, 0.0)
    tick(state, module)
    drive_through_gate(lua, state, module, 2)
    # Drop the prop's own registration acknowledgement so what is left is
    # exactly what the detonation sent.
    state.clear()

    # The fuse is randomised per round, so watch for the transition rather
    # than ticking a fixed count: a short draw plus a fixed count runs clean
    # past the whole boom sequence and lands back in idle.
    elapsed = 0.0
    deadline = spec.BEHAVIOR["fuse_max_seconds"] + 5.0
    while elapsed < deadline and module.getSystemState(PROP_ID).behavior_phase != "boom":
        tick(state, module, seconds=0.2)
        elapsed += 0.2
    assert module.getSystemState(PROP_ID).behavior_phase == "boom"
    assert elapsed >= spec.BEHAVIOR["fuse_min_seconds"] - 0.5, "fuse fired early"
    assert elapsed <= spec.BEHAVIOR["fuse_max_seconds"] + 0.5, "fuse overran"

    commands = [entry for entry in state.commands.values()]
    victims = {entry.id for entry in commands}
    assert victims == {2}, "detonation hit the wrong vehicle"
    joined = " ".join(entry.command for entry in commands)
    assert "breakAllBreakgroups" in joined
    assert "applyForceVector" in joined
    assert "explodeVehicle" in joined

    # The launch lands a tick behind the press.
    tick(state, module, seconds=0.2, steps=2)
    launches = [entry for entry in state.velocities.values() if entry.id == 2]
    assert launches, "carrier was never launched"
    assert launches[0].z == pytest.approx(spec.BEHAVIOR["detonate_launch_mps"])


def test_countdown_is_wall_clock_not_dtsim(rig):
    """The fuse must agree with the player's own clock.

    dtSim inside a prop's behavior.update is NOT wall seconds (measured ~3x
    fast), so a fuse accumulating dtSim would fire roughly three times early.
    Feeding a dtSim three times larger than the wall step must not move the
    detonation.
    """

    lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    tick(state, module)
    drive_through_gate(lua, state, module, 2)

    # 3x dtSim per 0.1 s of wall clock, run to just under the shortest fuse.
    elapsed = 0.0
    while elapsed < spec.BEHAVIOR["fuse_min_seconds"] - 1.0:
        state.clockMs = state.clockMs + 100.0
        module.onPreRender(0.1, 0.3, 0.3)
        elapsed += 0.1
    assert module.getSystemState(PROP_ID).behavior_phase == "live", (
        "fuse fired early - it is counting dtSim, not wall seconds"
    )


def test_losing_the_carrier_sends_the_potato_home(rig):
    lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 3.0, 0.0, 0.0)
    tick(state, module)
    drive_through_gate(lua, state, module, 2)
    tick(state, module)
    carrier = _carrier_of(module)

    state.removeVehicle(carrier)
    module.onVehicleDestroyed(carrier)
    tick(state, module)
    assert module.getSystemState(PROP_ID).behavior_phase == "idle"
    # The survivor must NOT have silently inherited the potato.
    assert _carrier_of(module) is None


def test_teardown_removes_every_scene_object(rig):
    lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    tick(state, module)
    drive_through_gate(lua, state, module, 2)
    tick(state, module)
    assert any(name.find("ericrolph_hot_potato_p1") == 0 for name in state.scene)

    module.onClientEndMission("/levels/gridmap_v2/main")
    leftovers = [name for name in state.scene if name.find("ericrolph_hot_potato_p1") == 0]
    assert not leftovers, f"scene objects survived mission end: {leftovers}"


def _carrier_of(module):
    """The carrier id, read back through the runtime's own telemetry.

    behavior.stats is the only generic channel getSystemState exposes, and
    -1 is the runtime's "nobody" (a nil field would vanish from the table).
    """

    stats = module.getSystemState(PROP_ID).behavior_stats
    carrier = int(stats.carrier)
    return None if carrier < 0 else carrier
