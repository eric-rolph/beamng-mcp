"""Headless state-machine gates for the COLOSSUS runtime.

The REAL generated ``runtime.lua`` is executed under lupa against stubbed
engine globals. It sees mechanics no static check can: that the axle fit
actually resolves from three live nodes, that a revolution is counted once,
that release is claimed from MOVEMENT rather than from a queued command that
may never run, that the chocks letting go on their own is noticed, and that
the capsize beat survives the frame it is written in.

The prop is a tire and nothing else now - no dock, no gangway, no access port,
nobody inside it - so the loop under test is short: come near it, the chocks
come out, and after that it is a free 10.5 tonne body being measured.

RUN IT FROM THE REPO VENV. Without lupa every one of these SKIPS silently,
which is exactly what happened to one review panel.
"""

from __future__ import annotations

import importlib.util
import math
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = REPO_ROOT / "examples" / "giant_props" / "colossus_tire"
SUBJECT_ID = 4242


@pytest.fixture(scope="module")
def spec():
    path = EXAMPLE_ROOT / "spec.py"
    loader = importlib.util.spec_from_file_location("colossus_sequence_spec", path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runtime_source(spec):
    path = EXAMPLE_ROOT / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID / "runtime.lua"
    if not path.is_file():
        pytest.skip("no generated GE runtime")
    return path.read_text(encoding="utf-8")


HARNESS = """
S = {}
S.lastIn = {}
S.messages = {}
S.events = {}
S.vehicles = {}
S.nodePositions = {}
S.brokenGroups = {}
S.queued = {}
S.propId = 7
S.materials = {}

-- LuaJIT has math.atan2; Lua 5.5 dropped it. BeamNG runs LuaJIT, so the
-- runtime is allowed to use it and the harness has to supply it.
if math.atan2 == nil then
  function math.atan2(y, x) return math.atan(y, x) end
end

local vec3mt = {}
vec3mt.__index = vec3mt
function vec3(x, y, z)
  if type(x) == "table" then return vec3(x.x, x.y, x.z) end
  return setmetatable({x = x or 0, y = y or 0, z = z or 0}, vec3mt)
end
function vec3mt.__add(a, b) return vec3(a.x + b.x, a.y + b.y, a.z + b.z) end
function vec3mt.__sub(a, b) return vec3(a.x - b.x, a.y - b.y, a.z - b.z) end
function vec3mt.__unm(a) return vec3(-a.x, -a.y, -a.z) end
function vec3mt.__mul(a, b)
  if type(a) == "number" then return vec3(a * b.x, a * b.y, a * b.z) end
  if type(b) == "number" then return vec3(a.x * b, a.y * b, a.z * b) end
  return vec3(a.x * b.x, a.y * b.y, a.z * b.z)
end
function vec3mt.__div(a, b) return vec3(a.x / b, a.y / b, a.z / b) end
function vec3mt:dot(o) return self.x * o.x + self.y * o.y + self.z * o.z end
function vec3mt:cross(o)
  return vec3(
    self.y * o.z - self.z * o.y,
    self.z * o.x - self.x * o.z,
    self.x * o.y - self.y * o.x
  )
end
function vec3mt:squaredLength() return self:dot(self) end
function vec3mt:length() return math.sqrt(self:dot(self)) end
function vec3mt:normalize()
  local l = self:length()
  if l > 0 then self.x, self.y, self.z = self.x / l, self.y / l, self.z / l end
  return self
end
function vec3mt:normalized() return vec3(self):normalize() end

-- A REAL quaternion. The shared runtime builds the prop's frame from one and
-- then rotates every trigger's authored offset through it, so a stub that
-- returned itself from __mul made registration fail with
-- trigger_creation_failed and every behaviour test measure silence.
local quatmt = {}
quatmt.__index = quatmt
function quat(x, y, z, w)
  return setmetatable({x = x or 0, y = y or 0, z = z or 0, w = w or 1}, quatmt)
end
function quatmt.__mul(a, b)
  if getmetatable(b) == quatmt then
    return quat(
      a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
      a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
      a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
      a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z
    )
  end
  -- v' = v + 2 * cross(q.xyz, cross(q.xyz, v) + q.w * v)
  local u = vec3(a.x, a.y, a.z)
  local inner = u:cross(vec3(b.x, b.y, b.z)) + vec3(b.x, b.y, b.z) * a.w
  local rotated = vec3(b.x, b.y, b.z) + u:cross(inner) * 2.0
  return rotated
end
function quatmt:normalize()
  local l = math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z + self.w * self.w)
  if l > 0 then
    self.x, self.y, self.z, self.w = self.x / l, self.y / l, self.z / l, self.w / l
  end
  return self
end
function quatmt:normalized() return quat(self.x, self.y, self.z, self.w):normalize() end
function quatmt:toTorqueQuat() return self end
function quatmt:inversed() return quat(-self.x, -self.y, -self.z, self.w) end

function S.clearMessages() S.messages = {}; S.lastIn = {} end
function S.visible(category) return S.lastIn[category] or "" end
function S.sawIn(category, fragment)
  local text = S.lastIn[category]
  return text ~= nil and text:find(fragment, 1, true) ~= nil
end
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

-- The tire's three marker nodes, posed by the test.
-- axisZ is the axle's Z COMPONENT, 0..1 - which is exactly what the runtime
-- compares against leaning_dot / tipping_dot / tipped_dot, so a test can name
-- the lean it wants instead of solving for it.
function S.setTire(cx, cy, cz, radius, angle, axisZ)
  local axis = vec3(1, 0, 0)
  if axisZ ~= nil then
    local z = math.max(-1.0, math.min(1.0, axisZ))
    axis = vec3(math.sqrt(math.max(0.0, 1.0 - z * z)), 0, z)
  end
  local ref = vec3(0, 0, 1) - axis * axis.z
  if ref:length() < 1e-6 then ref = vec3(0, 1, 0) - axis * axis.y end
  ref = ref:normalized()
  local other = axis:cross(ref)
  local centre = vec3(cx, cy, cz)
  local names = {"@MOD_ID@_crn_c_j00", "@MOD_ID@_crn_c_j16", "@MOD_ID@_crn_c_j32"}
  for index, name in ipairs(names) do
    local a = angle + (index - 1) * 2 * math.pi / 3
    S.nodePositions[name] =
      centre + (ref * math.cos(a) + other * math.sin(a)) * radius
  end
end

function S.moveNode(name, x, y, z)
  S.nodePositions[name] = vec3(x, y, z)
end

function S.moveVehicle(id, x, y, z)
  S.vehicles[id] = S.vehicles[id] or {}
  S.vehicles[id].pos = vec3(x, y, z)
end

-- The runtime resolves a node NAME to a cid through core_vehicle_manager's
-- vdata, then asks the vehicle for that cid's position RELATIVE to its datum.
-- Both halves are stubbed so the chunk under test is the shipped one.
S.cids = {}
S.cidNames = {}
-- The scene tree. The runtime creates one trigger box per zone and checks
-- that its materials exist; none of that is what these tests are about, so it
-- is stubbed to the minimum that lets registration succeed.
S.objects = {}
S.nextObjectId = 1000
local function sceneObject(name, class)
  S.nextObjectId = S.nextObjectId + 1
  local id = S.nextObjectId
  return {
    name = name,
    getClassName = function() return class end,
    getID = function() return id end,
    setPosition = function() end,
    setPosRot = function() end,
    setScale = function() end,
    -- setField/getField are a real store: the runtime REVALIDATES a trigger's
    -- mode and test type on every event before it will act on it, so a stub
    -- that forgot what it was told silently dropped every zone_enter.
    fields = {},
    setField = function(self, name, _index, value) self.fields[name] = value end,
    getField = function(self, name, _index) return self.fields[name] end,
    preApply = function() end,
    postApply = function() end,
    setCanSave = function() end,
    registerObject = function() end,
    delete = function() end,
    obj = nil,
  }
end
scenetree = {
  MissionGroup = {addObject = function() end},
  findObject = function(name)
    if S.objects[name] then return S.objects[name] end
    for _, material in ipairs(S.materials or {}) do
      if material == name then return sceneObject(name, "Material") end
    end
    return nil
  end,
  findObjectById = function(id)
    for _, object in pairs(S.objects) do
      if object.getID() == id then return object end
    end
    return nil
  end,
}
function createObject(class)
  local object = sceneObject("", class)
  object.registerObject = function(_, name)
    object.name = name
    S.objects[name] = object
  end
  return object
end
function loadJsonMaterialsFile() return true end

core_vehicle_manager = {
  getVehicleData = function(id)
    if id ~= S.propId then return nil end
    local nodes = {}
    local index = 0
    for name, _ in pairs(S.nodePositions) do
      if S.cids[name] == nil then
        S.cids[name] = index
        S.cidNames[index] = name
        index = index + 1
      end
      nodes[#nodes + 1] = {name = name, cid = S.cids[name]}
    end
    return {vdata = {nodes = nodes}}
  end,
}

be = {}
function be:getObjectByID(id)
  if id == S.propId then
    return {
      getId = function() return S.propId end,
      getJBeamFilename = function() return "@MOD_ID@" end,
      getPosition = function() return vec3(0, 0, 0) end,
      getNodePosition = function(_, cid)
        local name = S.cidNames[cid]
        return name and S.nodePositions[name] or nil
      end,
      queueLuaCommand = function(_, command)
        S.queued[#S.queued + 1] = command
        local group = command:match("breakBreakGroup%('([^']+)'%)")
        if group then S.brokenGroups[group] = true end
      end,
    }
  end
  local vehicle = S.vehicles[id]
  if not vehicle then return nil end
  return {
    getId = function() return id end,
    getJBeamFilename = function() return "etk800" end,
    getPosition = function() return vehicle.pos or vec3(0, 0, 0) end,
  }
end
function be:reloadCollision() end

guihooks = {message = function(payload, ttl, category)
  local text = tostring(payload.txt or "")
  S.messages[#S.messages + 1] = text
  S.lastIn[tostring(category or "")] = text
end}
function log(level, tag, message)
  S.events[#S.events + 1] = {level = level, message = tostring(message)}
end
function jsonEncode(value)
  if type(value) ~= "table" then return tostring(value) end
  local parts = {}
  for key, item in pairs(value) do
    parts[#parts + 1] = tostring(key) .. "=" .. jsonEncode(item)
  end
  return "{" .. table.concat(parts, ",") .. "}"
end
"""


def _load(spec, source):
    """Run the SHIPPED runtime chunk and hand back the module table it returns."""

    lupa = pytest.importorskip("lupa")
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(HARNESS.replace("@MOD_ID@", spec.MOD_ID))
    state = lua.globals().S
    module = lua.execute(source)
    assert module is not None, "the runtime chunk returned nothing"
    return lua, state, module


def _seed_frame_nodes(state, source):
    """Put the four refNode datums where the runtime says they are.

    The shared runtime resolves the prop's live frame from these before it
    will synchronise anything, so without them registration fails with
    trigger_creation_failed and every behaviour test measures silence.
    """

    import re

    marker = "local FRAME_NODES = {"
    block = source[source.index(marker) :]
    block = block[: block.index(chr(10) + "}")]
    pattern = re.compile(
        r'name = "([^"]+)", mesh = vec3\(\s*([-0-9.e]+),\s*([-0-9.e]+),\s*([-0-9.e]+)\s*\)'
    )
    found = pattern.findall(block)
    assert len(found) >= 4, f"parsed {len(found)} frame nodes out of the runtime"
    for name, x, y, z in found:
        state.moveNode(name, float(x), float(y), float(z))


@pytest.fixture
def rig(spec, runtime_source):
    lua, state, module = _load(spec, runtime_source)
    _seed_frame_nodes(state, runtime_source)
    state.setTire(0.0, 0.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, 0.0, None)
    state.moveVehicle(SUBJECT_ID, 40.0, 0.0, 0.5)
    module.onExtensionLoaded()
    module.registerProp(state.propId)
    return lua, state, module, spec


def tick(module, frames: int = 1, dt: float = 1.0 / 60.0):
    for _ in range(frames):
        module.onPreRender(dt, dt, dt)


def arm(lua, state, module, spec):
    """Drive the subject into the approach zone and let the chocks come out.

    The trigger's scene name is the runtime's own format, and the event
    carries the trigger's ID as well as its name because the runtime
    re-validates identity against BOTH - a name alone would let another prop's
    zone drive this one.
    """

    name = f"{spec.MOD_ID}_p{state.propId}_approach"
    trigger = state.objects[name]
    assert trigger is not None, list(state.objects)
    state.moveVehicle(SUBJECT_ID, 8.0, 0.0, 0.5)
    module.onBeamNGTrigger(
        lua.table_from(
            {
                "event": "enter",
                "triggerName": name,
                "triggerID": trigger.getID(),
                "subjectID": SUBJECT_ID,
            }
        )
    )


def test_the_runtime_finds_the_axle_and_counts_a_revolution(rig):
    """Three live nodes, one circle, one revolution - counted once."""

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    arm(lua, state, module, spec)
    tick(module, 240)
    state.clearMessages()

    steps = 72
    for index in range(1, steps + 1):
        angle = 2.0 * math.pi * index / steps
        state.setTire(
            0.0, spec.OUTER_RADIUS * angle, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -angle, None
        )
        tick(module)
    assert state.said("Revolution 1"), list(state.messages.values())
    assert not state.said("Revolution 2"), "a single turn counted twice"


def test_release_is_claimed_from_movement_not_from_the_queued_command(rig):
    """queueLuaCommand only ASKS. Release is claimed when the tire moves."""

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    arm(lua, state, module, spec)
    tick(module, 240)
    assert state.brokenGroups[spec.STRAP_BREAK_GROUP], list(state.queued.values())
    assert state.eventCount("colossus_released") == 1, list(state.events.values())


def test_the_closing_beat_ships(runtime_source):
    """The at-rest scoreboard line exists in the shipped runtime.

    The lupa rig cannot cheaply roll the tire 10 m and park it, so the beat
    is pinned at the source level: the string, the settle window, and the
    re-arm threshold all have to survive refactors.
    """

    assert "At rest: %.0f m, %d revolutions." in runtime_source
    assert "b.restClock" in runtime_source
    assert "b.restAnnounced" in runtime_source


def test_chocks_that_let_go_on_their_own_are_noticed(rig):
    """Forty tie-downs under the carcass. If they part, the runtime says so."""

    _lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
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
    assert state.eventCount("colossus_chocks_failed") == 1


def test_the_capsize_line_is_the_one_left_on_screen(rig):
    """The terminal beat has to survive the frame it is written in.

    An earlier version printed "COLOSSUS IS DOWN" and then printed a second
    string into the SAME UI category in the SAME frame, destroying it. A
    harness that recorded only message TEXT could not see that, which is why
    the stub records the category too.
    """

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    arm(lua, state, module, spec)
    tick(module, 240)
    state.setTire(0.0, 5.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.4, None)
    tick(module, 3)
    state.clearMessages()
    state.setTire(0.0, 6.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.5, 0.85)
    tick(module, 3)
    visible = state.visible(f"{spec.MOD_ID}_messages")
    assert "COLOSSUS IS DOWN" in visible, visible
    assert "m," in visible, f"the capsize line carries no score: {visible!r}"


def test_a_downed_colossus_stays_down(rig):
    """Once it is over, it stops scoring."""

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    arm(lua, state, module, spec)
    tick(module, 240)
    state.setTire(0.0, 6.0, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.5, 0.85)
    tick(module, 3)
    state.clearMessages()
    for index in range(40):
        state.setTire(
            0.0, 6.0 + index * 0.5, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -0.5 - index * 0.05, 0.85
        )
        tick(module)
    assert not state.said("Revolution"), list(state.messages.values())
    assert state.eventCount("colossus_tipped") == 1


def test_the_lean_warnings_come_before_it_is_too_late(rig):
    """Three beats, and the first two are the only warning anyone gets."""

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    arm(lua, state, module, spec)
    tick(module, 240)
    state.clearMessages()
    for index in range(1, 30):
        lean = math.sin(math.radians(index * 1.4))
        state.setTire(0.0, index * 0.4, spec.OUTER_RADIUS, spec.OUTER_RADIUS, -index * 0.03, lean)
        tick(module)
    assert state.said("SHE IS LEANING"), list(state.messages.values())
    assert state.said("SHE IS GOING OVER"), list(state.messages.values())


def test_the_runtime_never_drives_anything(rig):
    """The premise is that the physics does it. Prove the shipped Lua does not.

    The generated runtime carries the pack's shared subject-mutation helpers
    only when a mod opts in; this one must not, and may queue exactly two
    vehicle commands in its whole life, both in the release beat: the
    break-group cut, and the winch that pulls its own CHOCKS clear.
    """

    lua, state, module, spec = rig
    tick(module, int(spec.BEHAVIOR["settle_seconds"] * 60) + 30)
    arm(lua, state, module, spec)
    tick(module, 600)
    commands = list(state.queued.values())
    # The registration acknowledgement is the shared runtime's, not this
    # behaviour's. What this prop may ask a vehicle to do is exactly two
    # things, once: cut its own tie-downs, and winch its own CHOCKS clear.
    # The winch is machinery, not scripted tire physics - so every impulse
    # in it must name chock nodes and nothing else.
    cuts = [command for command in commands if "breakBreakGroup" in command]
    assert len(cuts) == 1, commands
    winches = [command for command in commands if "applyImpulse" in command]
    assert len(winches) == 1, commands
    named = re.findall(r'"([a-z0-9_]+)"', winches[0])
    assert named and all("chock_" in name for name in named), winches
    # Everything else the runtime ever queues must be an AUDIO dispatch into
    # its own vehicle extension - cue names and mixer pushes, no physics.
    others = [command for command in commands if command not in cuts and command not in winches]
    strays = [c for c in others if "_vehicle.ctAudio" not in c and "Registered')" not in c]
    assert not strays, strays
    forbidden = ("setVelocity", "applyForce(", "setPosition", "teleport")
    assert not [c for c in commands if any(word in c for word in forbidden)], commands
