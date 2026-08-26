"""Headless state-machine gate for the COLOSSUS runtime.

The pack's static gates prove the evidence chain and ``tests/
test_colossus_tire_geometry.py`` proves the cage. Neither can see this
runtime's actual mechanic, which is unusual for the pack: it drives nothing,
it MEASURES. Everything it says to the player is fitted, live, from three
cage nodes on the crown centre line, and every one of those steps is cheap to
get wrong in a way no static check notices:

- ``fitAxle`` is a three-point circumcentre. If it is wrong the prop is
  silent forever and nothing fails.
- the angle is unwrapped across +-pi every frame, and an off-by-one there
  either double-counts revolutions or never counts one.
- RELEASE is claimed from the tire having MOVED, not from the queued Lua
  command succeeding, because ``queueLuaCommand`` returns before the vehicle
  VM has done anything. The same path has to catch a strap that parts on its
  own before anyone boards.
- the dismount payoff follows vehicles geometrically once the tire has left
  the dock, because both triggers are anchored to the fixed dock and cannot
  follow it. The first cut of that read a ``state.subjects`` table the shared
  runtime does not have, so it iterated nothing and the payoff never fired -
  which is exactly the class of bug this file exists to catch.

This runs the REAL generated ``runtime.lua`` under lupa against stubbed engine
globals, following ``test_hot_potato_logic.py`` and
``test_spin_launch_sequence.py``. It cannot prove physics: no soft body, no
collision, no rendering is real here. It proves the logic those hang off. A
live gate on a sentinel-isolated profile is still required before shipping.

Run:  .venv\\Scripts\\python.exe -m pytest -q tests\\test_colossus_tire_sequence.py
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "colossus_tire"
PROP_ID = 1
SUBJECT_ID = 7


def load_spec():
    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader_spec = importlib.util.spec_from_file_location("colossus_seq_spec", spec_path)
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)
    return module


# The engine surface runtime.lua touches. The important stub here is the node
# one: `S.setTire` places the three marker nodes on a real circle so the
# runtime's own fit has something true to recover.
STUBS = r"""
-- BeamNG's GE Lua is LuaJIT 2.1, i.e. Lua 5.1 plus extras, and it HAS
-- math.atan2. Lua 5.3 removed it in favour of the two-argument math.atan, and
-- lupa here is built against 5.5 - so without this the harness reports a nil
-- call for code that is perfectly correct on the engine. Restoring it makes
-- the stub library match the one the runtime actually ships against.
if not math.atan2 then
  math.atan2 = function(y, x) return math.atan(y, x) end
end

local S = {}
S.messages = {}
S.events = {}
S.scene = {}
S.vehicles = {}
S.nodes = {}
S.queued = {}

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
function vecmt:squaredLength() return self.x^2 + self.y^2 + self.z^2 end
function vecmt:dot(o) return self.x * o.x + self.y * o.y + self.z * o.z end
function vecmt:cross(o)
  return vec3(self.y * o.z - self.z * o.y,
              self.z * o.x - self.x * o.z,
              self.x * o.y - self.y * o.x)
end
function vecmt:normalize()
  local l = self:length()
  if l > 0 then self.x, self.y, self.z = self.x / l, self.y / l, self.z / l end
  return self
end
function vecmt:normalized() return vec3(self.x, self.y, self.z):normalize() end
function vecmt:getRotationTo() return quat(0, 0, 0, 1) end
function vec3(x, y, z)
  if type(x) == "table" then x, y, z = x.x or x[1], x.y or x[2], x.z or x[3] end
  return setmetatable({x = x or 0, y = y or 0, z = z or 0}, vecmt)
end

local quatmt = {}
quatmt.__index = quatmt
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

local objmt = {}
objmt.__index = objmt
function objmt:setField(name, _i, value) self.fields[name] = value end
function objmt:getField(name) return self.fields[name] end
function objmt:getClassName() return self.class end
function objmt:getName() return self.name end
function objmt:getID() return self.id end
function objmt:setCanSave() end
function objmt:registerObject(name) self.name = name; S.scene[name] = self end
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
  return setmetatable({class = class, fields = {}, id = nextObjectId,
                       active = false}, objmt)
end

scenetree = {}
scenetree.MissionGroup = setmetatable({class = "SimGroup", fields = {}}, objmt)
function scenetree.findObject(name)
  if S.scene[name] then return S.scene[name] end
  if type(name) == "string" and name:find("BNGP_") == 1 then
    return setmetatable({class = "ParticleEmitterData", fields = {}}, objmt)
  end
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
  S.queued[#S.queued + 1] = command
end
function vehmt:getNodePosition(cid)
  local point = S.nodes[cid]
  if not point then return nil end
  return vec3(point.x - self.pos.x, point.y - self.pos.y, point.z - self.pos.z)
end
function vehmt:applyClusterVelocityScaleAdd() end
function vehmt:setPositionRotation() end

map = {objects = {}}

function S.addVehicle(id, model, x, y, z, hx, hy, hz)
  local vehicle = setmetatable({
    id = id, model = model,
    pos = {x = x, y = y, z = z},
    half = {x = hx or 0.95, y = hy or 2.3, z = hz or 0.75},
  }, vehmt)
  S.vehicles[id] = vehicle
  map.objects[id] = {vel = vec3(0, 0, 0), damage = 0}
  return vehicle
end

function S.moveVehicle(id, x, y, z)
  S.vehicles[id].pos = {x = x, y = y, z = z}
end

-- Place the three crown markers on a genuine circle: axle centre (cx, cy, cz),
-- radius r, rotation `angle`, plane normal along X (upright) unless `tipZ` is
-- given, in which case the axle is tilted toward world up so the runtime's
-- tipped-over test can be exercised.
function S.setTire(cx, cy, cz, r, angle, tipZ)
  local ax, az = 1.0, 0.0
  if tipZ then
    local l = math.sqrt(1 + tipZ * tipZ)
    ax, az = 1.0 / l, tipZ / l
  end
  -- Two in-plane baselines orthogonal to the axle.
  local e1 = vec3(-az, 0, ax)
  local e2 = vec3(0, 1, 0)
  for index = 1, 3 do
    local theta = angle + (index - 1) * (2 * math.pi / 3)
    local ox = math.cos(theta) * r
    local oy = math.sin(theta) * r
    S.nodes[index - 1] = {
      x = cx + e1.x * ox + e2.x * oy,
      y = cy + e1.y * ox + e2.y * oy,
      z = cz + e1.z * ox + e2.z * oy,
    }
  end
end

function S.clearMessages() S.messages = {} end
function S.said(fragment)
  for _, text in ipairs(S.messages) do
    if text:find(fragment, 1, true) then return true end
  end
  return false
end
function S.eventCount(name)
  local count = 0
  for _, entry in ipairs(S.events) do
    if entry.message:find(name, 1, true) then count = count + 1 end
  end
  return count
end
function S.queuedCount() return #S.queued end
function S.lastQueued() return S.queued[#S.queued] end

be = {}
function be:getObjectByID(id) return S.vehicles[id] end
function be:reloadCollision() end

guihooks = {message = function(payload)
  S.messages[#S.messages + 1] = tostring(payload.txt or "")
end}
function log(level, tag, message)
  S.events[#S.events + 1] = {level = level, message = tostring(message)}
end
-- The runtime logs structured events as tables; a tostring() of the table is
-- an address, which no assertion can read. Flatten it so the harness can see
-- what the runtime actually emitted.
function jsonEncode(value)
  if type(value) ~= "table" then return tostring(value) end
  local parts = {}
  for key, item in pairs(value) do
    parts[#parts + 1] = tostring(key) .. "=" .. tostring(item)
  end
  table.sort(parts)
  return "{" .. table.concat(parts, ", ") .. "}"
end

-- vdata: the three marker node names mapped to the cids S.nodes uses.
core_vehicle_manager = {
  getVehicleData = function()
    return {vdata = {nodes = S.markerNodes}}
  end,
}
function loadJsonMaterialsFile() return true end

return S
"""


@pytest.fixture()
def rig():
    spec = load_spec()
    runtime_path = (
        PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID / "runtime.lua"
    )
    if not runtime_path.is_file():
        pytest.skip("no generated GE runtime")
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    state = lua.execute(STUBS)
    # Marker node table, in the order the runtime asks for them.
    state.markerNodes = lua.table_from(
        {
            index + 1: lua.table_from({"name": name, "cid": index})
            for index, name in enumerate(spec.BEHAVIOR["marker_nodes"])
        }
    )
    module = lua.execute(runtime_path.read_text(encoding="utf-8"))
    state.addVehicle(PROP_ID, spec.MOD_ID, 0.0, 0.0, 0.0, 6.0, 15.0, 15.0)
    state.setTire(0.0, 0.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, 0.0, None)
    module.registerProp(PROP_ID)
    return lua, state, module, spec


def tick(module, count=1, dt=1.0 / 60.0):
    for _ in range(count):
        module.onPreRender(dt, dt, dt)


def fire_trigger(lua, state, module, spec, zone, vehicle_id, event="enter"):
    """Fire the shared runtime's trigger path for one zone.

    ``triggerID`` is mandatory and is re-validated against the live scene
    object, so the harness has to look the real trigger up rather than invent
    an id - the runtime is deliberately strict about trigger identity.
    """

    name = f"{spec.MOD_ID}_p{PROP_ID}_{zone}"
    trigger = state.scene[name]
    assert trigger is not None, f"trigger {name} was never created"
    module.onBeamNGTrigger(
        lua.table_from(
            {
                "event": event,
                "triggerName": name,
                "triggerID": trigger.id,
                "subjectID": vehicle_id,
                "subjectName": "etk800",
            }
        )
    )


def board(lua, state, module, spec, zone="cabin", vehicle_id=SUBJECT_ID):
    state.addVehicle(vehicle_id, "etk800", 0.0, 0.0, spec.CAVITY_FLOOR_Z + 0.5)
    fire_trigger(lua, state, module, spec, zone, vehicle_id)


# ---------------------------------------------------------------------------
# The measurement layer
# ---------------------------------------------------------------------------
def test_the_runtime_finds_the_axle_and_counts_a_revolution(rig):
    """A full synthetic turn must count exactly one revolution, not two.

    The angle is unwrapped across +-pi every frame; a sign slip there shows up
    as a revolution counted twice per turn, or never.
    """

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    board(lua, state, module, spec)
    tick(module, 240)  # let the countdown run and cut
    state.clearMessages()

    steps = 72
    for index in range(1, steps + 1):
        angle = 2.0 * math.pi * index / steps
        # Roll without slipping: the axle advances r * angle.
        state.setTire(
            0.0, spec.OUTER_RADIUS * angle, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -angle, None
        )
        tick(module)
    assert state.said("Revolution 1"), list(state.messages.values())
    assert not state.said("Revolution 2"), "a single turn counted twice"


def test_release_is_claimed_from_movement_not_from_the_queued_command(rig):
    """queueLuaCommand returns before the vehicle VM has done anything.

    Claiming release on a successful pcall would mark the prop free while the
    straps were still holding, and would leave the runtime permanently silent
    if the command never landed.
    """

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    board(lua, state, module, spec)
    tick(module, 240)

    assert state.queuedCount() >= 1
    assert "breakBreakGroup" in state.lastQueued()
    assert spec.STRAP_BREAK_GROUP in state.lastQueued()
    assert state.eventCount("colossus_released") == 0, "release was claimed before the tire moved"

    # Now let it actually roll away.
    state.setTire(0.0, 3.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.2, None)
    tick(module, 2)
    assert state.eventCount("colossus_released") == 1


def test_a_strap_that_parts_on_its_own_is_noticed(rig):
    """Two 95 kN beams under a 103 kN body can part before anyone boards.

    If release were only ever claimed inside the boarding path, that would
    leave the runtime silent for the rest of the session.

    The drift is measured HORIZONTALLY and only after the settle window,
    because the first live run showed a 28 m carcass drops 0.36 m onto its
    own contact patch and a 3D test against the spawn centre trips on gravity
    alone - which fired this event before anyone boarded and suppressed the
    whole boarding beat.
    """

    _lua, state, module, spec = rig
    settle = int(spec.BEHAVIOR["settle_seconds"] * 60) + 30
    tick(module, settle)
    state.clearMessages()
    # Sinking alone must NOT count, however far it sinks.
    state.setTire(0.0, 0.0, spec.OUTER_RADIUS - 2.0, spec.OUTER_RADIUS, 0.0, None)
    tick(module, 5)
    assert not state.said("parted"), (
        "settling onto the contact patch was mistaken for the tire escaping"
    )
    # Rolling away must.
    state.setTire(0.0, 4.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.3, None)
    tick(module, 5)
    assert state.said("parted"), list(state.messages.values())
    assert state.eventCount("colossus_strap_parted") == 1


def _ride(state, module, spec, metres=19.5):
    """Roll the tire, with the subject riding the cavity floor."""

    steps = 39
    for index in range(1, steps + 1):
        centre_y = metres * index / steps
        state.setTire(
            0.0, centre_y, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -centre_y / spec.OUTER_RADIUS, None
        )
        state.moveVehicle(SUBJECT_ID, 0.0, centre_y, spec.CAVITY_FLOOR_Z + 0.5)
        tick(module)
    return metres


def test_threading_the_port_is_the_payoff(rig):
    """Leaving through the open door is the climax beat, and it has to fire.

    This is the one that was silently dead twice over: the rider walk first
    read a table the shared runtime does not maintain, so it iterated nothing
    forever, and then it paid out for ANY exit including going over the side.
    """

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    board(lua, state, module, spec)
    tick(module, 240)
    _ride(state, module, spec)
    # Bring the port back round to the bottom: the door is open.
    state.setTire(0.0, 19.5, spec.OUTER_RADIUS, spec.OUTER_RADIUS, 0.0, None)
    state.moveVehicle(SUBJECT_ID, 0.0, 19.5, spec.CAVITY_FLOOR_Z + 0.5)
    tick(module, 3)
    state.clearMessages()
    # ...and out through it.
    state.moveVehicle(SUBJECT_ID, 0.0, -60.0, 0.5)
    tick(module, 3)
    assert state.said("threaded the port"), list(state.messages.values())
    assert state.eventCount("colossus_dismounted") == 1


def test_going_out_through_the_wall_pays_nothing(rig):
    """A capsize is not a dismount, and it used to score identically.

    insideTire rejects at |axial| > liner_half + 0.6, which a car on the
    cavity floor crosses at about 20 degrees of lean - a full 24 degrees
    before "COLOSSUS IS DOWN" - so rolling the Colossus over printed
    "CLEAR. NEW BEST." and then stomped it with the tipped message in the same
    UI category. Credit is now gated on the door actually being there.
    """

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    board(lua, state, module, spec)
    tick(module, 240)
    _ride(state, module, spec)
    state.clearMessages()
    # The port is 79 degrees round from the bottom; the subject leaves anyway.
    state.moveVehicle(SUBJECT_ID, 0.0, -60.0, 0.5)
    tick(module, 3)
    assert state.said("OUT THROUGH THE WALL"), list(state.messages.values())
    assert not state.said("NEW BEST"), "a wall exit set a record"


def test_a_downed_colossus_stays_down(rig):
    """Once it is over, the ride is over - it does not keep scoring.

    Round 3 ran updateRiders BEFORE updateTipped and never stopped either, so
    a downed tire rocking back across the rider threshold re-fired "Back
    aboard. Go again." forever and the HUD kept counting revolutions of a tire
    lying on its side.
    """

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    board(lua, state, module, spec)
    tick(module, 240)
    state.setTire(0.0, 5.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.4, None)
    tick(module, 3)
    # Lay the axle over until it points at the sky.
    state.setTire(0.0, 6.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.5, 4.0)
    tick(module, 3)
    state.clearMessages()
    # Rock it back and forth across the rider threshold for a while.
    for index in range(30):
        state.moveVehicle(SUBJECT_ID, 0.0, 6.0 + (index % 2) * 40.0, spec.CAVITY_FLOOR_Z + 0.5)
        tick(module)
    assert not state.said("Back aboard"), list(state.messages.values())
    assert not state.said("threaded the port"), list(state.messages.values())


def test_going_over_is_detected(rig):
    """A 28 m tire on a 10 m base is a coin. Falling is honest; silence is not."""

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    board(lua, state, module, spec)
    tick(module, 240)
    state.setTire(0.0, 5.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.4, None)
    tick(module, 3)
    state.clearMessages()
    # Lay the axle over until it points at the sky.
    state.setTire(0.0, 6.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.5, 4.0)
    tick(module, 3)
    assert state.said("COLOSSUS IS DOWN"), list(state.messages.values())


def test_the_runtime_never_drives_anything(rig):
    """The premise is that the physics does it. Prove the shipped Lua does not.

    The generated runtime carries the pack's shared subject-mutation helpers
    only when a mod opts in; this one must not, and must issue exactly one
    command into the vehicle VM - the strap cut.
    """

    _, _, _, spec = rig
    runtime = (
        PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID / "runtime.lua"
    )
    text = runtime.read_text(encoding="utf-8")
    for forbidden in (
        "applyClusterVelocityScaleAdd",
        "setPositionRotation",
        "launchSubject",
        "addSubjectVelocity",
        "teleportSubject",
    ):
        assert forbidden not in text, f"the Colossus runtime moves things: {forbidden}"
    assert "local function launchSubject" not in text, (
        "the shared subject-mutation helpers are compiled in; this mod sets "
        "ALLOW_SUBJECT_MUTATION = False precisely so they are not"
    )
    assert text.count("queueLuaCommand") == 2, (
        "exactly two queueLuaCommand call sites are expected: the shared "
        "registration acknowledgement and the strap cut"
    )
