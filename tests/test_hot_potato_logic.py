"""Headless state-machine gate for Hot Potato's generated GE runtime.

Every other prop in the pack is a fixed machine exercised with ONE subject, so
the pack's existing gates cannot see this mod's actual mechanic at all: the
potato only means anything with several vehicles in play, and its failure
modes (a pass that ping-pongs every tick, a fuse that never fires, a carrier
that vanishes and takes the round with it) are all multi-vehicle.

This runs the REAL generated ``runtime.lua`` under lupa against stubbed engine
globals. It cannot prove physics - no deformation, no particles, no lights are
real here - but it proves the logic those things hang off:

- driving onto the medallion picks the potato up (a POSITIONAL sweep, after a
  Contains trigger shipped in v1 and never fired once in a real session),
- a hard enough tap passes it, and a gentle brush does not,
- a tag-back needs immunity, minimum hold AND a foot of real separation,
- the fuse runs on the wall clock and detonates the CURRENT carrier,
- detonation issues the vehicle-side break/crush/fire commands,
- a carrier that despawns sends the potato home instead of picking a victim.

The live gate on a sentinel-isolated profile is still required before shipping;
this is the cheap half that runs on every commit.
"""

from __future__ import annotations

import importlib.util
import re
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
-- Every setPosRot per scene object, in order: the v2.4 gates read part
-- flight paths (the return flight, the mash arcs) from these.
S.poses = {}

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
function objmt:setPosRot(x, y, z)
  if self.name then
    local track = S.poses[self.name]
    if not track then track = {} S.poses[self.name] = track end
    track[#track + 1] = {x = x, y = y, z = z}
  end
end
function objmt:setPosition(position)
  if self.name and position then
    local track = S.poses[self.name]
    if not track then track = {} S.poses[self.name] = track end
    track[#track + 1] = {x = position.x, y = position.y, z = position.z}
  end
end
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
function vehmt:getVelocity() return vec3(self.vel.x, self.vel.y, self.vel.z) end
function vehmt:getDirectionVector() return vec3(0, 1, 0) end
function vehmt:getDirectionVectorUp() return vec3(0, 0, 1) end

function S.addVehicle(id, model, x, y, z, hx, hy, hz)
  local vehicle = setmetatable({
    id = id, model = model,
    pos = {x = x, y = y, z = z},
    vel = {x = 0, y = 0, z = 0},
    half = {x = hx or 0.95, y = hy or 2.3, z = hz or 0.75},
  }, vehmt)
  S.vehicles[id] = vehicle
  return vehicle
end

function S.moveVehicle(id, x, y, z)
  local vehicle = S.vehicles[id]
  vehicle.pos.x, vehicle.pos.y, vehicle.pos.z = x, y, z
end

function S.setVelocity(id, x, y, z)
  local vehicle = S.vehicles[id]
  vehicle.vel.x, vehicle.vel.y, vehicle.vel.z = x, y, z
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

-- v2.11: the ground probe the slope-aware tip limit reads. A plane tilted
-- S.groundGrade along +x; castRayStatic returns the DISTANCE to it (the
-- engine's own contract, and the repo's proven idiom). S.groundRays counts
-- the probes so a gate can price them.
S.groundGrade = 0.0
S.groundRays = 0
S.groundSolid = true
function castRayStatic(start, direction, maxDistance)
  S.groundRays = S.groundRays + 1
  if not S.groundSolid then return maxDistance end
  local groundZ = S.groundGrade * start.x
  local distance = start.z - groundZ
  if distance < 0 or distance > maxDistance then return maxDistance end
  return distance
end

be = {}
function be:getObjectByID(id) return S.vehicles[id] end
function be:reloadCollision() end
-- v2.5: the AI sweep skips the player's own vehicle; tests set S.playerId.
S.playerId = nil
function be:getPlayerVehicleID() return S.playerId end

-- misc engine surface ----------------------------------------------------
Engine = {Platform = {getSystemTimeMS = function() return S.clockMs end}}
guihooks = {message = function(payload, ttl, category)
  S.messages[#S.messages + 1] = tostring(payload.txt or "")
end}
function log(level, tag, message)
  S.events[#S.events + 1] = {level = level, message = message}
end
-- Render event records as "key=value" text: the tick() crash guard looks
-- for "behavior_update_failed" in the logged message, and a bare
-- tostring(table) printed "table: 0x..." — so for every gate before v2.8
-- the guard was dead code and a throwing behaviour frame passed silently
-- (critic round, 2026-09-01).
function jsonEncode(value)
  if type(value) ~= "table" then return tostring(value) end
  local out = {}
  for key, item in pairs(value) do
    out[#out + 1] = tostring(key) .. "=" .. tostring(item)
  end
  table.sort(out)
  return table.concat(out, " ")
end
core_vehicle_manager = {getVehicleData = function() return nil end}
-- v2.8: the model registry the subject filter reads. Mirrors the real
-- core_vehicles.getModel: {model = {Type = ...}} for a known jbeam, and a
-- bare {} for one it does not know (core/vehicles.lua:759-764). Tests
-- extend S.modelTypes to stage a model.
S.modelTypes = {
  etk800 = "Car", pickup = "Truck",
  cardboard_box = "Prop", barrels = "Prop",
  unicycle = "Prop",  -- the on-foot player ships as a Prop in stock
  dryvan = "Trailer",
  unknown_kit = "Unknown",
}
core_vehicles = {
  getModel = function(name)
    local kind = S.modelTypes[name]
    if kind == nil then return {} end
    return {model = {Type = kind}, configs = {}}
  end,
}
function loadJsonMaterialsFile() return true end
S.sounds = {}
Engine.Audio = {playOnce = function(_channel, event, opts)
  S.sounds[#S.sounds + 1] = {
    event = event,
    pitch = opts and opts.pitch or 1,
    volume = opts and opts.volume or 1,
    positional = (opts and opts.position) and true or false,
  }
end}
Steam = {playerName = "ARCH KING 7"}
-- No settings file in the harness: options fall back to the shipped table.
S.settings = nil
function jsonReadFile() return S.settings end
function jsonWriteFile(_path, payload) S.settings = payload return true end

-- v2.6: the arena halo is immediate-mode debug-drawer geometry redrawn per
-- frame; the stub records every solid tri so the gates can see the wall
-- appear with a live round and vanish without one.
S.halo = {}
-- v2.7: the fireworks draw their shell, stars and finale rain with the
-- same immediate-mode drawer (a point light against open sky renders
-- NOTHING — the whole v2.7 fireworks bug); the stub records every sphere
-- so the gates can see the sky light up, and stay dark when the option
-- says so.
S.stars = {}
function color(r, g, b, a) return {r = r, g = g, b = b, a = a} end
function ColorF(r, g, b, a) return {r = r, g = g, b = b, a = a} end
debugDrawer = {
  drawTriSolid = function(_self, a, b, c) S.halo[#S.halo + 1] = {a = a, b = b, c = c} end,
  drawCylinder = function() end,
  drawSphere = function(_self, position, radius, colorf)
    S.stars[#S.stars + 1] = {position = position, radius = radius, color = colorf}
  end,
  drawLine = function() end,
}

return S
"""


@pytest.fixture()
def rig():
    spec = load_spec()
    runtime_path = (
        PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID / "runtime.lua"
    )
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    state = lua.execute(STUBS)
    module = lua.execute(runtime_path.read_text(encoding="utf-8"))
    return lua, state, module, spec


PROP_ID = 1


def register_prop(state, module):
    state.addVehicle(PROP_ID, "ericrolph_hot_potato", 0.0, 0.0, 0.0, 15.0, 2.0, 15.6)
    module.registerProp(PROP_ID)


def tick(state, module, seconds=0.05, steps=1):
    for _ in range(steps):
        state.clockMs = state.clockMs + seconds * 1000.0
        module.onPreRender(seconds, seconds, seconds)
    failures = [
        entry.message
        for entry in state.events.values()
        if entry.level == "E" and "behavior_update_failed" in str(entry.message)
    ]
    assert not failures, f"behaviour raised during update: {failures[:2]}"


def run_until(state, module, predicate, *, limit_seconds, seconds=0.2):
    """Step until `predicate` holds, and FAIL rather than spin forever.

    An unbounded `while True` turns a behaviour bug into a hung test run
    instead of a message - which is exactly what a missing vec3:cross() in
    these stubs did, once.
    """

    elapsed = 0.0
    while elapsed < limit_seconds:
        if predicate():
            return elapsed
        tick(state, module, seconds=seconds)
        elapsed += seconds
    raise AssertionError(f"condition never held within {limit_seconds}s of simulated play")


def _carrier_of(module):
    """The carrier id, read back through the runtime's own telemetry.

    behavior.stats is the only generic channel getSystemState exposes, and -1
    is the runtime's "nobody" (a nil field would vanish from the table).
    """

    stats = module.getSystemState(PROP_ID).behavior_stats
    carrier = int(stats.carrier)
    return None if carrier < 0 else carrier


def _remaining(module):
    return float(module.getSystemState(PROP_ID).behavior_stats.fuse_remaining)


def start_round(state, module, vehicle_id, x=0.0, y=0.0):
    """Drive onto the medallion; the idle sweep hands the potato over.

    Pickup respects the join-immunity window (a reset carrier standing on
    the pad must not re-arm instantly), so park on the pad and wait it out.
    """

    state.moveVehicle(vehicle_id, x, y, 0.0)
    tick(state, module, seconds=0.1, steps=24)  # 2.4 s > join_immunity 2.0 s
    return _carrier_of(module)


def close_in(state, module, mover, target, speed_mps, gap=2.0, axis="x"):
    """Put `mover` next to `target` and actually closing on it.

    Stub vehicles face +Y, so `axis="x"` is a side-swipe and `axis="y"` is
    nose-to-tail. Contact range differs by a factor of ~2.5 between them,
    which is exactly what the support-radius model exists to express.
    """

    tpos = state.vehicles[target].pos
    if axis == "y":
        state.moveVehicle(mover, tpos.x, tpos.y + gap, tpos.z)
        state.setVelocity(mover, 0.0, -speed_mps, 0.0)
    else:
        state.moveVehicle(mover, tpos.x + gap, tpos.y, tpos.z)
        state.setVelocity(mover, -speed_mps, 0.0, 0.0)
    state.setVelocity(target, 0.0, 0.0, 0.0)


TICK_WRITE = re.compile(r"setVolumePitch\(S\.id, ([0-9.]+), ([0-9.]+)\)")
PHYSICS_VERBS = ("breakAllBreakgroups", "applyForceVector", "explodeVehicle", "deflate")


def _physics_commands(state):
    """Vehicle commands that touch the physics — the ones "harmless" bans.

    The fuse tick legitimately rides the carrier's own VM now (audio
    mechanism v3: createSFXSource/setVolumePitch/playSFX/stopSFX pushed via
    queueLuaCommand), so "no commands at all" stopped being the right
    predicate the day the tick stopped leaking playOnce loop instances.

    v2.6: the damage-armor command PROTECTS a car (setBeamStrength to
    math.huge, deflateTire patched out) — it mentions "deflate" only to
    disarm it, so it is excluded the same way the audio writes are.
    """

    return [
        entry
        for entry in state.commands.values()
        if "ericrolph_hot_potato_armor" not in entry.command
        and any(verb in entry.command for verb in PHYSICS_VERBS)
    ]


def _tick_writes(state, vehicle_id):
    """(volume, pitch) of every TICK write sent to `vehicle_id`, in order.

    v2.5: the whistle rides the same VM with its own setVolumePitch writes
    (its steady pitch 1.0 is a feature, not an escalation leak), so this
    filters on the tick's own _G key rather than the write verb alone.
    """

    writes = []
    for entry in state.commands.values():
        if entry.id != vehicle_id:
            continue
        if "ericrolph_hot_potato_tick" not in entry.command:
            continue
        found = TICK_WRITE.search(entry.command)
        if found:
            writes.append((float(found.group(1)), float(found.group(2))))
    return writes


def test_registers_with_trigger_effects_and_the_potato(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    system = module.getSystemState(PROP_ID)
    assert system.registered is True
    # v2.4: the tuber plus its six mash chunks parked under the plaza.
    assert system.part_count == 7
    assert system.trigger_count == 1
    assert system.triggers.pad.mode == "Overlaps"
    # Nine declared particle emitters (fuse, blast, cheer, and v2.7's six
    # mash-steam wisps — briefly pairs for the critic's 85 m screenshot,
    # back to one per chunk when the player asked to "tone down the steam",
    # v2.7.1) plus the THREE light objects the behaviour makes itself and
    # parks in state.effects for teardown: the round-gated beacons. (v2.3
    # removed the wick and its ember lamp — the smoke wisp off the crown is
    # the idle invitation now.)
    assert system.effect_count == 12


def test_driving_onto_the_pad_picks_the_potato_up(rig):
    """The v1 regression, pinned.

    v1 gated pickup on a Contains BeamNGTrigger. The player's beamng.log
    recorded prop_registered and then not one zone_enter across a whole
    session of driving through it, so the potato just bobbed. A position test
    cannot miss, and this asserts it without any trigger event at all.
    """

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 60.0, 0.0)
    tick(state, module)
    assert _carrier_of(module) is None, "picked up from 85 m away"

    assert start_round(state, module, 2) == 2
    assert module.getSystemState(PROP_ID).behavior_phase == "live"
    assert any("GOT IT" in message for message in state.messages.values())


def test_a_hard_tap_passes_and_a_gentle_brush_does_not(rig):
    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 90.0, 0.0, 0.0)
    tick(state, module)
    start_round(state, module, 2)
    tick(state, module, seconds=0.1, steps=int(spec.BEHAVIOR["join_immunity_seconds"] / 0.1) + 4)

    # Touching, but crawling: below the impact threshold nothing happens.
    close_in(state, module, 3, 2, speed_mps=1.0)
    tick(state, module, steps=4)
    assert _carrier_of(module) == 2, "a fender brush should not transfer"

    # Same geometry, a real hit.
    close_in(state, module, 3, 2, speed_mps=spec.BEHAVIOR["impact_kmh"] / 3.6 + 2.0)
    tick(state, module)
    assert _carrier_of(module) == 3
    assert any("PASSED" in message for message in state.messages.values())


def test_a_rear_end_tap_at_real_car_spacing_registers(rig):
    """The geometry the live gate caught and this harness had been missing.

    Two etk800s bumper to bumper have their CENTRES about 4.7 m apart, because
    each is ~4.8 m long. The first contact model used one averaged radius per
    car - 1.68 m for an etk800 - so "contact" was 3.9 m and a rear-end tap
    could never transfer the potato, while a side-swipe would fire early. Every
    headless test passed anyway, because they all placed cars 2 m apart, which
    is inside even the wrong range. This one uses real spacing, and it also
    checks the other side: cars a clear two lengths apart must NOT transfer.
    """

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 200.0, 0.0, 0.0)
    tick(state, module)
    start_round(state, module, 2)
    tick(state, module, seconds=0.1, steps=int(spec.BEHAVIOR["join_immunity_seconds"] / 0.1) + 4)

    fast = spec.BEHAVIOR["impact_kmh"] / 3.6 + 2.0

    # Two car lengths clear, nose to tail: no transfer, however fast.
    close_in(state, module, 3, 2, speed_mps=fast, gap=11.0, axis="y")
    tick(state, module, steps=4)
    assert _carrier_of(module) == 2, "transferred from 11 m away"

    # A side-swipe at rear-end spacing must also miss: 4.7 m apart abreast is
    # two lanes of clear air, and the old averaged-radius model could not tell
    # these two cases apart at all.
    close_in(state, module, 3, 2, speed_mps=fast, gap=4.7, axis="x")
    tick(state, module, steps=4)
    assert _carrier_of(module) == 2, "transferred from 4.7 m abreast"

    # Nose to tail with centres 4.7 m apart - two etk800s touching bumpers.
    # This MUST register.
    close_in(state, module, 3, 2, speed_mps=fast, gap=4.7, axis="y")
    tick(state, module, steps=2)
    assert _carrier_of(module) == 3, (
        "a bumper-to-bumper rear-end tap did not transfer - contact range is "
        "smaller than two cars parked touching"
    )


def test_tag_back_needs_immunity_hold_and_a_foot_of_separation(rig):
    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 90.0, 0.0, 0.0)
    tick(state, module)
    start_round(state, module, 2)
    tick(state, module, seconds=0.1, steps=int(spec.BEHAVIOR["join_immunity_seconds"] / 0.1) + 4)

    fast = spec.BEHAVIOR["impact_kmh"] / 3.6 + 2.0
    close_in(state, module, 3, 2, speed_mps=fast)
    tick(state, module)
    assert _carrier_of(module) == 3

    # Locked together at speed for well past the immunity window. The
    # separation latch is what has to hold it on 3.
    for _ in range(80):
        close_in(state, module, 2, 3, speed_mps=fast)
        tick(state, module, seconds=0.1)
        if _carrier_of(module) != 3:
            break
    assert _carrier_of(module) == 3, (
        "potato tagged back while the pair never separated - the separation "
        "latch is what stops a locked-bumper pair trading it forever"
    )

    # Part them by more than a foot beyond contact, then come back hard.
    state.moveVehicle(2, 200.0, 0.0, 0.0)
    state.setVelocity(2, 0.0, 0.0, 0.0)
    tick(
        state, module, seconds=0.1, steps=int(spec.BEHAVIOR["tagback_min_hold_seconds"] / 0.1) + 40
    )
    close_in(state, module, 2, 3, speed_mps=fast)
    tick(state, module, steps=3)
    assert _carrier_of(module) == 2, "a properly separated tag-back was refused"


def test_radius_mode_transfers_without_contact(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 10.0) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    start_round(state, module, 2)
    tick(state, module, seconds=0.1, steps=30)

    # Eight metres apart and stationary: no contact and no closing speed, but
    # inside the bubble.
    carrier = state.vehicles[_carrier_of(module)].pos
    state.moveVehicle(3, carrier.x + 8.0, carrier.y, carrier.z)
    tick(state, module, steps=2)
    assert _carrier_of(module) == 3


def test_mod_controls_clamp_and_reject(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    tick(state, module)
    assert module.hotPotatoSetOption("radius_m", 1000.0) is True
    assert module.hotPotatoGetOptions().radius_m == 60.0, "out-of-range not clamped"
    assert module.hotPotatoSetOption("transfer_mode", "banana") is False
    assert module.hotPotatoSetOption("not_an_option", 1) is False
    assert module.hotPotatoSetOption("audio_enabled", False) is True
    assert module.hotPotatoGetOptions().audio_enabled is False


def test_fuse_is_gaussian_inside_its_clamp(rig):
    """Every draw must land in [min, max], and they must not all be equal."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    tick(state, module)
    draws = []
    for _ in range(40):
        state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
        tick(state, module, seconds=0.1, steps=24)  # wait out join immunity
        draws.append(_remaining(module))
        state.removeVehicle(2)
        module.onVehicleDestroyed(2)
        # v2.4: losing the carrier starts the return flight; the next draw
        # can only happen once the potato is back on its perch.
        run_until(
            state,
            module,
            lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
            limit_seconds=15.0,
        )
    low = spec.BEHAVIOR["fuse_min_seconds"] - 0.5
    high = spec.BEHAVIOR["fuse_max_seconds"] + 0.5
    assert all(low <= draw <= high for draw in draws), (
        f"fuse escaped its clamp: {min(draws)}..{max(draws)}"
    )
    assert len(set(round(draw, 3) for draw in draws)) > 5, "fuse is not varying"


def test_fuse_detonates_the_carrier_and_carrying_is_harmless(rig):
    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    start_round(state, module, 2)
    state.clear()

    elapsed = 0.0
    deadline = spec.BEHAVIOR["fuse_max_seconds"] + 5.0
    while elapsed < deadline and module.getSystemState(PROP_ID).behavior_phase != "boom":
        tick(state, module, seconds=0.2)
        elapsed += 0.2
        if elapsed < spec.BEHAVIOR["fuse_min_seconds"] - 1.0:
            # While merely carrying, the car must receive no PHYSICS command:
            # no crush, no breakgroups, no fire. The tick's audio writes are
            # expected — they are the cue riding the carrier's VM.
            assert not _physics_commands(state), (
                "a carrying vehicle was sent a physics command before detonation"
            )
    assert module.getSystemState(PROP_ID).behavior_phase == "boom"
    assert elapsed >= spec.BEHAVIOR["fuse_min_seconds"] - 0.5, "fuse fired early"
    assert _tick_writes(state, 2), "the carrier never received the fuse tick"

    commands = _physics_commands(state)
    assert {entry.id for entry in commands} == {2}, "detonation hit the wrong vehicle"
    joined = " ".join(entry.command for entry in commands)
    assert "breakAllBreakgroups" in joined
    assert "applyForceVector" in joined
    assert "explodeVehicle" in joined

    tick(state, module, seconds=0.2, steps=2)
    launches = [entry for entry in state.velocities.values() if entry.id == 2]
    assert launches, "carrier was never launched"


def test_a_late_transfer_still_grants_the_hot_window(rig):
    """Being tagged with a second left is a scare, not an execution."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    start_round(state, module, 2)

    run_until(
        state,
        module,
        lambda: _remaining(module) <= 1.0,
        limit_seconds=spec.BEHAVIOR["fuse_max_seconds"] + 10.0,
    )
    close_in(state, module, 3, 2, speed_mps=spec.BEHAVIOR["impact_kmh"] / 3.6 + 2.0)
    tick(state, module)
    assert _carrier_of(module) == 3
    remaining = _remaining(module)
    assert remaining >= spec.BEHAVIOR["grace_seconds"] - 0.5, (
        f"receiver got only {remaining:.2f}s, below the guaranteed hot window"
    )


def test_the_tick_accelerates_and_rises_in_pitch(rig):
    """No numeric countdown: urgency rides the cue, so the cue must move.

    The cue is ONE looping source in the carrier's VM whose pitch scales
    playback rate and tone together, so "faster" and "higher" are the same
    number: the pitch of the setVolumePitch writes the GE side pushes across
    the VM boundary. The volume swells with urgency too.
    """

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    start_round(state, module, 2)

    run_until(
        state,
        module,
        lambda: 0.0 < _remaining(module) < 2.0,
        limit_seconds=spec.BEHAVIOR["fuse_max_seconds"] + 10.0,
    )
    writes = _tick_writes(state, 2)
    assert len(writes) >= 3, "the tick was never driven across the cue window"
    volumes = [write[0] for write in writes]
    pitches = [write[1] for write in writes]
    assert pitches[-1] > pitches[0] + 0.5, "the tick did not accelerate and rise"
    assert volumes[-1] > volumes[0] + 0.2, "the tick did not swell"
    # The writes are throttled to audible steps, not streamed every frame.
    assert len(writes) < 200, f"{len(writes)} tick writes — the throttle is gone"


def test_countdown_is_wall_clock_not_dtsim(rig):
    """dtSim is NOT wall seconds (measured ~3x fast); the fuse must not use it."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    tick(state, module)

    elapsed = 0.0
    while elapsed < spec.BEHAVIOR["fuse_min_seconds"] - 1.0:
        state.clockMs = state.clockMs + 100.0
        module.onPreRender(0.1, 0.3, 0.3)
        elapsed += 0.1
    assert module.getSystemState(PROP_ID).behavior_phase == "live", (
        "fuse fired early - it is counting dtSim, not wall seconds"
    )


def test_resetting_a_sweep_discovered_carrier_sends_the_potato_home(rig):
    """Review finding (PR #87): the framework reset path only fires for
    vehicles it finds in state.zones, and a sweep-discovered carrier - the
    normal case, since the pad trigger is only a secondary path - was in no
    zone. Resetting it left the potato riding the reset car with the fuse
    still burning. The carrier now registers itself in a synthetic zone."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    carrier = start_round(state, module, 2)
    assert carrier == 2

    # The reset arrives through the FRAMEWORK hook, exactly as the engine
    # delivers it - no trigger event was ever involved for this carrier.
    module.onVehicleResetted(2)
    tick(state, module)
    # v2.4: the round is over instantly, and the potato takes the flight home.
    assert module.getSystemState(PROP_ID).behavior_phase in ("return", "idle")
    assert _carrier_of(module) is None, "potato kept riding a reset carrier"
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
        limit_seconds=20.0,
    )


def test_sole_survivor_wins_instead_of_detonating(rig):
    """Review finding (PR #87): when every non-carrier despawned mid-round,
    the fuse kept burning and detonated the last car standing. The round now
    ends as a win the moment the field collapses to one."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    # Drop the prop's own registration acknowledgement so the only commands
    # left to see would be a wrongful detonation.
    state.clear()

    # The other car despawns mid-round.
    state.removeVehicle(3)
    module.onVehicleDestroyed(3)
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
        # v2.4: the win is instant but the potato flies home before idle.
        limit_seconds=20.0,
    )
    assert _carrier_of(module) is None
    assert any("LAST CAR STANDING" in m for m in state.messages.values()), (
        "field collapse must end as a win"
    )
    # And above all: nobody was detonated. (Audio stop commands are fine —
    # the round ending is exactly when the tick must be silenced.)
    assert not _physics_commands(state), "the sole survivor received a detonation command"


def test_losing_the_carrier_sends_the_potato_home(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    carrier = start_round(state, module, 2)

    state.removeVehicle(carrier)
    module.onVehicleDestroyed(carrier)
    tick(state, module)
    # v2.4: the potato flies home rather than teleporting — the round is
    # over the moment the flight starts, and idle follows at touchdown.
    assert module.getSystemState(PROP_ID).behavior_phase == "return"
    assert _carrier_of(module) is None
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
        limit_seconds=20.0,
    )
    # The survivor is 300 m away and must NOT have inherited the potato.
    assert _carrier_of(module) is None


def test_detonated_carrier_can_start_the_next_round(rig):
    """The single-player lockout, pinned (player's 2026-08-28 beamng.log).

    v2.0 marked a detonated car in b.out and never cleared it, so after the
    first boom the pad was dead: the log shows four pad crossings after the
    detonation with zero pickups, because roster() reported an empty field
    every time. Eliminations are per-round; a finished round clears them.
    """

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2, x=0.0, y=0.0) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)

    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "boom",
        limit_seconds=spec.BEHAVIOR["fuse_max_seconds"] + 5.0,
    )
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
        # v2.4: the fire, then the whole return flight home.
        limit_seconds=spec.BEHAVIOR["fire_seconds"] + 25.0,
    )
    # The victim's join immunity is stamped past the boom AND the flight
    # (the wreck-on-the-medallion re-arm guard); wait it out.
    tick(state, module, seconds=0.2, steps=60)

    # The same car drives back onto the medallion. It must get the potato.
    assert start_round(state, module, 2, x=0.0, y=0.0) == 2, (
        "a detonated car stayed banned after the round ended"
    )


def test_prop_teardown_silences_the_carrier_tick(rig):
    """The 2026-08-29 recording, pinned: sound must not outlive the mod.

    The tick loop lives in the CARRIER's VM, which the framework's scene
    sweep cannot see — cleanupInstallation calls behavior.cleanup first so
    the loop is stopped through the same queueLuaCommand channel that
    started it. Without this, deleting the prop mid-round leaves the
    carrier beeping forever.
    """

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    assert _tick_writes(state, 2), "round started without a tick"

    state.clear()
    module.unregisterProp(PROP_ID, "player_deleted_prop")
    stops = [
        entry for entry in state.commands.values() if entry.id == 2 and "stopSFX" in entry.command
    ]
    assert stops, "prop teardown never told the carrier to stop the tick"


def test_transfer_moves_the_tick_to_the_new_carrier(rig):
    """A pass is audible as a handoff: old VM stops, new VM starts."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.1, steps=25)  # clear join immunity for 3

    state.clear()
    close_in(state, module, 3, 2, speed_mps=spec.BEHAVIOR["impact_kmh"] / 3.6 + 2.0)
    tick(state, module)
    assert _carrier_of(module) == 3
    old_stops = [
        entry for entry in state.commands.values() if entry.id == 2 and "stopSFX" in entry.command
    ]
    new_starts = [
        entry
        for entry in state.commands.values()
        if entry.id == 3 and "createSFXSource" in entry.command
    ]
    assert old_stops, "the passer kept ticking after the handoff"
    assert new_starts, "the receiver never started ticking"


def test_detonation_resends_the_tick_stop_during_the_boom(rig):
    """The 2026-08-29 player report, pinned: sizzle persisting past the boom.

    The one TICK_STOP detonate() queues crosses the GE->vehicle boundary in
    the same frame the victim's VM is being fed break, crush and fire
    commands. The boom phase now re-sends the stop over its first second —
    an already-silent VM no-ops, a missed stop gets caught. The stop itself
    is also belt-and-braces now: volume 0 first (the only write PROVEN
    audible on this raw-ogg source), then stopSFX, then cutSFX.
    """

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "boom",
        limit_seconds=spec.BEHAVIOR["fuse_max_seconds"] + 5.0,
    )
    state.clear()
    tick(state, module, seconds=0.2, steps=6)  # 1.2 s of boom phase
    stops = [
        entry for entry in state.commands.values() if entry.id == 2 and "stopSFX" in entry.command
    ]
    assert len(stops) >= 2, "the boom phase does not re-send the tick stop"
    assert all("setVolume(S.id, 0)" in entry.command for entry in stops), (
        "the stop no longer mutes before stopping — the raw-ogg guarantee"
    )
    assert all("cutSFX" in entry.command for entry in stops)


def test_camping_burns_the_fuse_faster(rig):
    """Anti-camping: parked below camp_speed_kmh, the fuse drains at the
    multiplier; at speed it drains in real time."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    for key, value in (
        ("fuse_base_seconds", 60.0),
        ("fuse_sigma_seconds", 0.0),
        ("fuse_min_seconds", 60.0),
        ("fuse_max_seconds", 60.0),
        ("camp_burn_multiplier", 3.0),
        ("camp_speed_kmh", 20.0),
    ):
        assert module.hotPotatoSetOption(key, value) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2

    # Parked (stub velocity is zero): 10 wall seconds must cost ~30.
    before = _remaining(module)
    tick(state, module, seconds=0.1, steps=100)
    drained_parked = before - _remaining(module)
    assert 25.0 < drained_parked < 35.0, (
        f"parked carrier drained {drained_parked:.1f}s over 10s at 3x"
    )

    # Moving over the threshold: real time only.
    state.setVelocity(2, 10.0, 0.0, 0.0)  # 36 km/h
    before = _remaining(module)
    tick(state, module, seconds=0.1, steps=100)
    drained_moving = before - _remaining(module)
    assert 8.0 < drained_moving < 12.0, f"moving carrier drained {drained_moving:.1f}s over 10s"


def test_pass_knockback_shoves_the_receiver(rig):
    _lua, state, module, spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("pass_knockback_mps", 10.0) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 90.0, 0.0, 0.0)
    tick(state, module)
    start_round(state, module, 2)
    tick(state, module, seconds=0.1, steps=int(spec.BEHAVIOR["join_immunity_seconds"] / 0.1) + 4)

    state.clear()
    # Receiver approaches from +x, so the knockback axis (carrier -> receiver)
    # is +x too: the hit sends it flying onward, with a little lift.
    close_in(state, module, 3, 2, speed_mps=spec.BEHAVIOR["impact_kmh"] / 3.6 + 2.0)
    tick(state, module)
    assert _carrier_of(module) == 3
    shoves = [
        entry
        for entry in state.velocities.values()
        if entry.id == 3 and entry.x > 5.0 and entry.z > 0.5
    ]
    assert shoves, "the impact pass never shoved the receiver"


def test_detonation_shockwave_pushes_bystanders_not_the_distant(rig):
    _lua, state, module, spec = rig
    register_prop(state, module)
    for key, value in (
        ("fuse_min_seconds", 5.0),
        ("fuse_max_seconds", 6.0),
        ("fuse_sigma_seconds", 0.0),
    ):
        assert module.hotPotatoSetOption(key, value) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    # Inside blast_radius_m (22) but outside pickup_radius (7.5); the third
    # car is far outside the wave.
    state.addVehicle(3, "etk800", 10.0, 0.0, 0.0)
    state.addVehicle(4, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.clear()
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "boom",
        limit_seconds=10.0,
    )
    tick(state, module, seconds=0.2)
    bystander = [entry for entry in state.velocities.values() if entry.id == 3]
    distant = [entry for entry in state.velocities.values() if entry.id == 4]
    assert bystander, "a car 10 m from the blast never felt the shockwave"
    assert any(entry.x > 1.0 for entry in bystander), (
        "the shockwave should push the bystander radially outward (+x)"
    )
    assert not distant, "a car 300 m away was pushed by a 22 m shockwave"


def test_champion_is_crowned_after_enough_wins(rig):
    """The wins ledger outlives rounds; wins_to_champion crowns and resets."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("wins_to_champion", 2) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)

    for round_index in range(2):
        state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
        tick(state, module)
        assert start_round(state, module, 2) == 2
        # The field collapses: the sole survivor wins the round.
        state.removeVehicle(3)
        module.onVehicleDestroyed(3)
        run_until(
            state,
            module,
            lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
            # v2.4: the potato flies home between rounds.
            limit_seconds=20.0,
        )
        state.moveVehicle(2, 60.0, 0.0, 0.0)
        tick(state, module)

    assert any("CHAMPION" in message for message in state.messages.values()), (
        "two wins at wins_to_champion=2 never crowned a champion"
    )
    # The ledger reset with the crown.
    stats = module.hotPotatoGetStats()
    assert len(list(stats.wins or [])) == 0, "the ledger did not reset after the crown"


def test_stats_hook_gates_the_countdown_behind_its_option(rig):
    """The HUD reads hotPotatoGetStats; the numeric fuse is opt-in."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2

    stats = module.hotPotatoGetStats()
    assert stats.phase == "live"
    assert int(stats.carrier) == 2
    assert stats.carrier_name == "etk800"
    assert float(stats.countdown) == -1, "the hidden fuse leaked to the HUD"

    assert module.hotPotatoSetOption("show_countdown", True) is True
    tick(state, module)
    stats = module.hotPotatoGetStats()
    assert float(stats.countdown) > 0, "show_countdown=true published nothing"


def test_negative_carrier_boost_drags_instead_of_boosting(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("carrier_boost_mps2", -3.0) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2

    state.clear()
    state.setVelocity(2, 10.0, 0.0, 0.0)
    tick(state, module, steps=4)
    drags = [entry for entry in state.velocities.values() if entry.id == 2]
    assert drags, "the handicap never touched the carrier"
    assert all(entry.x < 0 for entry in drags), (
        "a negative boost must drag AGAINST the motion, not along it"
    )


def test_smoke_option_gates_the_wisp(rig):
    """v2.3: the idle potato smokes — unless the option turns the wisp off."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module, steps=2)
    wisps = [
        obj
        for name, obj in state.scene.items()
        if name.find("ericrolph_hot_potato_p1") == 0 and name.endswith("_fuse")
    ]
    assert wisps, "the smoke effect object is missing from the scene"
    assert wisps[0].active is True, "the idle potato is not smoking"

    assert module.hotPotatoSetOption("smoke_enabled", False) is True
    tick(state, module, steps=2)
    assert wisps[0].active is False, "smoke_enabled=false did not stop the wisp"


def _poses_of(state, suffix):
    """Recorded setPosRot/setPosition track for the scene object ending in
    `suffix` (part_potato, part_mash_1, fw_px_1, ...)."""

    for name, track in state.poses.items():
        if name.startswith("ericrolph_hot_potato_p1") and name.endswith(suffix):
            return [(float(p.x), float(p.y), float(p.z)) for p in track.values()]
    return []


def _detonate_carrier(state, module, spec, carrier_id=2):
    """Park the carrier away from the pad and burn the fuse down to boom."""

    state.moveVehicle(carrier_id, 60.0, 0.0, 0.0)
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "boom",
        limit_seconds=spec.BEHAVIOR["fuse_max_seconds"] + 5.0,
    )


def test_boom_settles_into_a_return_flight_not_a_respawn(rig):
    """THE v2.4 ROUND-FLOW FIX, pinned. The player's report: "after the game
    started, the hot potato spawned onto another car. The game should only
    restart once someone passes over the hot potato."

    The old settle path handed the potato to the NEAREST car ("STILL IN
    PLAY!"). Now the boom always ends in a return flight, nobody inherits
    the potato — not even a car parked on the medallion mid-flight — and
    the next round arms only from idle, at the pad.
    """

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 20.0, 0.0, 0.0)  # close — the old victim
    tick(state, module)
    assert start_round(state, module, 2) == 2
    _detonate_carrier(state, module, spec)

    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "return",
        limit_seconds=spec.BEHAVIOR["fire_seconds"] + 5.0,
    )
    assert _carrier_of(module) is None, "the boom handed the potato to a car"
    assert not any("STILL IN PLAY" in m for m in state.messages.values())

    # A car parked on the medallion during the flight must NOT arm a round.
    state.moveVehicle(3, 0.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=5)
    assert module.getSystemState(PROP_ID).behavior_phase == "return"
    assert _carrier_of(module) is None

    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
        limit_seconds=25.0,
    )
    # Once the potato is back on its perch, the same car claims it AT the
    # pad — the only way a round may ever start.
    assert start_round(state, module, 3, x=0.0, y=0.0) == 3


def test_return_flight_climbs_cruises_and_settles_on_the_perch(rig):
    """The alien hover: straight up, drift over, ease down onto the perch."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    _detonate_carrier(state, module, spec)
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "return",
        limit_seconds=spec.BEHAVIOR["fire_seconds"] + 5.0,
    )
    state.poses = _fresh_pose_table(state)
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
        limit_seconds=25.0,
        seconds=0.1,
    )
    track = _poses_of(state, "part_potato")
    assert len(track) > 20, "the flight posed almost nothing"
    home_z = float(spec.POTATO_HOME[2])
    peak = max(z for _x, _y, z in track)
    assert peak > home_z + 8.0, f"the flight never climbed (peak {peak:.1f})"
    final = track[-1]
    assert abs(final[0]) < 1.0 and abs(final[1]) < 1.0, f"the potato settled off its perch: {final}"
    assert abs(final[2] - home_z) < 1.5, f"wrong settle height: {final[2]:.2f}"
    # And it came down from above the pad, not sideways through the arch:
    # the last leg is monotonically descending (small hover jitter allowed).
    tail = [z for _x, _y, z in track[-12:]]
    assert all(later <= earlier + 0.3 for earlier, later in zip(tail, tail[1:])), (
        "the descent was not a descent"
    )


def test_carry_clearance_lifts_the_potato_off_the_roof(rig):
    """v2.4, the player's report: "it collides with the vehicle mesh"."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)

    assert module.hotPotatoSetOption("carry_clearance_m", 0.0) is True
    tick(state, module, steps=3)
    low = _poses_of(state, "part_potato")[-1][2]
    assert module.hotPotatoSetOption("carry_clearance_m", 1.2) is True
    tick(state, module, steps=3)
    high = _poses_of(state, "part_potato")[-1][2]
    assert high > low + 0.7, (
        f"carry_clearance_m did not lift the carried potato ({low:.2f} -> {high:.2f})"
    )


def test_the_potato_bounces_on_the_beat_and_never_into_the_roof(rig):
    """v2.4: the carried potato hops a parabola launched on each tick beat;
    every hop is UPWARD from the clearance baseline."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)

    state.poses = _fresh_pose_table(state)
    tick(state, module, seconds=0.05, steps=40)  # two slow beats
    bouncing = [z for _x, _y, z in _poses_of(state, "part_potato")]
    assert max(bouncing) - min(bouncing) > 0.05, "the beat hop never moved it"

    assert module.hotPotatoSetOption("bounce_enabled", False) is True
    state.poses = _fresh_pose_table(state)
    tick(state, module, seconds=0.05, steps=40)
    still = [z for _x, _y, z in _poses_of(state, "part_potato")]
    wobble_cap = spec.BEHAVIOR["attach_wobble"] * 2.0 + 0.02
    assert max(still) - min(still) <= wobble_cap, "bounce_enabled=false still hopped"
    # The hop rides ABOVE the still baseline — never sinks into the roof.
    assert min(bouncing) >= min(still) - 0.02


def test_steady_tick_style_hides_every_escalation_channel(rig):
    """The hardcore ask: "only the hot potato song, no indication ... like a
    bomb is about to go off". Frozen pitch alone would ship a lie, so the
    volume, the HUD urgency AND the countdown gate all pin to flat here.
    """

    _lua, state, module, spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("tick_style", "steady") is True
    assert module.hotPotatoSetOption("show_countdown", True) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)

    run_until(
        state,
        module,
        lambda: 0.0 < _remaining(module) < 2.0,
        limit_seconds=spec.BEHAVIOR["fuse_max_seconds"] + 10.0,
    )
    writes = _tick_writes(state, 2)
    assert writes, "steady style silenced the tick entirely"
    # writes[0] is the pickup handoff (giveTo's initial drive); everything
    # after it must be dead flat.
    pitches = {round(pitch, 2) for _volume, pitch in writes}
    volumes = {round(volume, 2) for volume, _pitch in writes[1:]}
    assert len(pitches) == 1, f"steady tick still changed pitch: {sorted(pitches)}"
    assert len(volumes) <= 1, f"steady tick still swelled: {sorted(volumes)}"
    stats = module.hotPotatoGetStats()
    assert float(stats.urgency) == 0.0, "the HUD urgency bar leaked the fuse"
    assert float(stats.countdown) == -1, (
        "steady style must override show_countdown — the number IS the tell"
    )


def test_the_tick_falls_silent_just_before_the_boom(rig):
    """The horror cut (v2.4 audio critic rank 1): in escalating style the
    last silence_gap_seconds before the boom are dead air and darkness."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)

    run_until(
        state,
        module,
        lambda: 0.0 < _remaining(module) <= spec.BEHAVIOR["silence_gap_seconds"] - 0.1,
        limit_seconds=spec.BEHAVIOR["fuse_max_seconds"] + 10.0,
        seconds=0.05,
    )
    before = len(_tick_writes(state, 2))
    stops_before = sum(
        1 for entry in state.commands.values() if entry.id == 2 and "stopSFX" in entry.command
    )
    tick(state, module, seconds=0.05, steps=4)
    assert module.getSystemState(PROP_ID).behavior_phase == "live"
    assert len(_tick_writes(state, 2)) == before, "the tick kept driving inside the silence gap"
    stops_after = sum(
        1 for entry in state.commands.values() if entry.id == 2 and "stopSFX" in entry.command
    )
    assert stops_after > 0 and stops_after >= stops_before, (
        "entering the silence gap never stopped the loop"
    )


def test_fizzle_mode_cooks_the_holder_without_carnage(rig):
    """v2.4: detonate_enabled=false — elimination without a scratch."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("detonate_enabled", False) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 40.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.clear()
    _detonate_carrier(state, module, spec)
    tick(state, module, seconds=0.2, steps=5)

    assert not _physics_commands(state), "a fizzle broke something"
    assert not [entry for entry in state.velocities.values()], (
        "a fizzle launched or shoved somebody"
    )
    assert any("COOKED" in m for m in state.messages.values())
    # And the potato still takes the flight home.
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
        limit_seconds=25.0,
    )


def test_detonation_stacks_three_boom_layers(rig):
    """v2.4 audio critic: crack + body + debris ring — the proven one-shot
    at 0.85 / 0.55 / 1.6, the copies landing a beat behind."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    _detonate_carrier(state, module, spec)
    tick(state, module, seconds=0.1, steps=8)

    booms = [
        round(float(entry.pitch), 2)
        for entry in state.sounds.values()
        if "engine_explode" in str(entry.event)
    ]
    assert len(booms) >= 3, f"expected the layered boom, got {booms}"
    assert 0.55 in booms and 1.6 in booms, f"missing stack layers: {booms}"


def test_mash_flies_lands_and_melts_back_under_the_plaza(rig):
    """v2.4: six chunks out of the fireball, then re-parked below grade."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    _detonate_carrier(state, module, spec)
    tick(state, module, seconds=0.1, steps=10)

    airborne = _poses_of(state, "part_mash_1")
    assert airborne, "the mash never flew"
    assert max(z for _x, _y, z in airborne) > 0.0, "mash chunk 1 never rose above grade"
    # Outlives the boom phase, then melts back under and re-parks at its
    # authored home (z -30).
    run_until(
        state,
        module,
        lambda: (_poses_of(state, "part_mash_1") or [(0, 0, 0)])[-1][2] < -25.0,
        limit_seconds=spec.BEHAVIOR["mash_seconds"] + 40.0,
    )

    # And the whole show is optional.
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
        limit_seconds=30.0,
    )
    assert module.hotPotatoSetOption("mash_enabled", False) is True


def test_champion_fireworks_spell_the_name_over_the_arch(rig):
    """v2.4: the crown writes the champion's name in firework bursts."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("wins_to_champion", 1) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.removeVehicle(3)
    module.onVehicleDestroyed(3)
    run_until(
        state,
        module,
        lambda: any("CHAMPION" in m for m in state.messages.values()),
        limit_seconds=20.0,
    )
    # Let a few letters burst.
    tick(state, module, seconds=0.1, steps=60)
    assert any(name.endswith("fw_px_1") for name in state.scene), (
        "no firework light pool was created for the champion"
    )
    assert _poses_of(state, "fw_px_1"), "the firework lights never moved"
    # The per-letter arpeggio: pass stingers at more than one pitch.
    arpeggio = {
        round(float(entry.pitch), 2)
        for entry in state.sounds.values()
        if "Drift_Combo" in str(entry.event) and float(entry.pitch) > 1.001
    }
    assert arpeggio, "the letter bursts never played their rising stingers"


def test_fireworks_option_gates_the_whole_show(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("wins_to_champion", 1) is True
    assert module.hotPotatoSetOption("fireworks_enabled", False) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.removeVehicle(3)
    module.onVehicleDestroyed(3)
    run_until(
        state,
        module,
        lambda: any("CHAMPION" in m for m in state.messages.values()),
        limit_seconds=20.0,
    )
    tick(state, module, seconds=0.1, steps=30)
    assert not any(name.endswith("fw_px_1") for name in state.scene), (
        "fireworks_enabled=false still built the light pool"
    )


def test_hoarder_mode_scores_the_holder_and_crowns_at_target(rig):
    """v2.4 game mode: holding the potato EARNS — first to target is
    champion, and the round ends with the crown."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("game_mode", "hoarder") is True
    assert module.hotPotatoSetOption("hoard_target_points", 10) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)

    tick(state, module, seconds=0.2, steps=25)  # ~5 held seconds
    stats = module.hotPotatoGetStats()
    scores = list((stats.scores or {}).values())
    assert scores and int(scores[0].points) >= 4, (
        "holding the potato earned nothing in hoarder mode"
    )

    run_until(
        state,
        module,
        lambda: any("CHAMPION" in m for m in state.messages.values()),
        limit_seconds=15.0,
    )
    # The crown ends the round: the potato heads home, the board resets.
    assert module.getSystemState(PROP_ID).behavior_phase in ("return", "idle")
    stats = module.hotPotatoGetStats()
    assert len(list(stats.scores or [])) == 0, "the hoard did not reset"


def test_pinball_mode_passes_on_any_touch_with_a_shove(rig):
    """v2.4 game mode: a gentle brush — far below impact_kmh — passes, and
    the receiver gets a guaranteed hearty knockback."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("game_mode", "pinball") is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=12)  # past join immunity
    state.clear()

    close_in(state, module, 3, 2, speed_mps=1.0)  # a nudge, not a hit
    tick(state, module, steps=2)
    assert _carrier_of(module) == 3, "pinball mode refused a gentle touch"
    shoves = [entry for entry in state.velocities.values() if entry.id == 3]
    assert shoves and abs(shoves[0].x) >= 5.0, "pinball pass came without its bumper shove"


def test_steam_hiss_vents_while_idle_and_respects_its_option(rig):
    """v2.4: the idle potato periodically lets off a pitched-up air hiss —
    stock one-shot events only, positional, jittered."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.25, steps=48)  # ~12 idle seconds

    def hisses():
        return [entry for entry in state.sounds.values() if "Pneumatics" in str(entry.event)]

    vented = hisses()
    assert len(vented) >= 2, "the idle potato never vented"
    assert all(entry.positional for entry in vented), (
        "the hiss must be positional — it belongs to the potato, not the UI"
    )
    assert all(float(entry.pitch) >= 1.4 for entry in vented), (
        "the vent must be pitched UP into a potato-sized whistle"
    )

    assert module.hotPotatoSetOption("steam_hiss_enabled", False) is True
    before = len(hisses())
    tick(state, module, seconds=0.25, steps=48)
    assert len(hisses()) == before, "steam_hiss_enabled=false kept venting"


def test_glow_ramp_heats_the_carrier_light(rig):
    """v2.4: "like it glows hotter and hotter" — the carrier glow whitens
    and brightens with urgency, blackbody-style, and the option gates it."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)

    glow = state.scene["ericrolph_hot_potato_p1_beacon_glow"]
    tick(state, module, steps=3)
    early = str(glow.fields.color)
    run_until(
        state,
        module,
        lambda: 0.0 < _remaining(module) < 3.0,
        limit_seconds=spec.BEHAVIOR["fuse_max_seconds"] + 10.0,
    )
    late = str(glow.fields.color)
    early_green = float(early.split()[1])
    late_green = float(late.split()[1])
    assert late_green > early_green + 0.3, f"the glow never heated: {early!r} -> {late!r}"
    late_bright = float(str(glow.fields.brightness))
    assert late_bright > spec.BEHAVIOR["beacon_brightness"] * 1.5, (
        "the glow never brightened toward the boom"
    )


def test_beacon_master_switch_keeps_every_ray_dark(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("beacon_enabled", False) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.1, steps=30)
    for slot in ("beacon_glow", "beacon_ray_a", "beacon_ray_b"):
        light = state.scene["ericrolph_hot_potato_p1_" + slot]
        assert str(light.fields.isEnabled) == "0", f"{slot} lit with the beacon disabled"


def _fresh_pose_table(state):
    """Empty S.poses in place (lupa tables have no clear); returns it."""

    for key in [key for key in state.poses]:
        state.poses[key] = None
    return state.poses


def test_teardown_removes_every_scene_object(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    tick(state, module)
    assert any(name.find("ericrolph_hot_potato_p1") == 0 for name in state.scene)

    module.onClientEndMission("/levels/gridmap_v2/main")
    leftovers = [n for n in state.scene if n.find("ericrolph_hot_potato_p1") == 0]
    assert not leftovers, f"scene objects survived mission end: {leftovers}"


# --------------------------------------------------------------------------
# v2.5 (2026-08-30): the steam whistle, the AI drivers, and fireworks for
# any round winner.


def _commands_to(state, vehicle_id, needle):
    return [
        entry.command
        for entry in state.commands.values()
        if entry.id == vehicle_id and needle in entry.command
    ]


def _shrink_fuse(module, seconds=10):
    """Pin the Gaussian fuse to an exact length (sigma 0, min == max)."""

    assert module.hotPotatoSetOption("fuse_base_seconds", seconds) is True
    assert module.hotPotatoSetOption("fuse_sigma_seconds", 0) is True
    assert module.hotPotatoSetOption("fuse_min_seconds", seconds) is True
    assert module.hotPotatoSetOption("fuse_max_seconds", seconds) is True


def test_whistle_rides_the_carrier_and_sputters_before_the_boom(rig):
    """v2.5, the acoustic brief: the carried potato whistles (a raw-ogg loop
    in the carrier's VM, the tick's proven channel), the pitch glides DOWN
    as the pressure runs out, and the loop breaks into the baked staccato
    sputter one-shot as the fuse enters its final seconds."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 10)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=5)

    starts = _commands_to(state, 2, "ericrolph_hot_potato_whistle")
    assert starts, "the whistle loop never reached the carrier's VM"
    assert any("ericrolph_hot_potato_whistle.ogg" in c for c in starts)
    assert any("AudioDefaultLoop3D" in c for c in starts)

    # The downward glissando: whistle pitch writes strictly below 1.0 while
    # the tick's own pitch rises - two channels, opposite gestures.
    pitches = [
        float(found.group(2))
        for command in starts
        for found in [TICK_WRITE.search(command)]
        if found
    ]
    assert pitches and min(pitches) < 0.95, f"the whistle never glided down: {pitches}"

    run_until(
        state,
        module,
        lambda: _commands_to(state, 2, "erhp_sputter"),
        limit_seconds=12.0,
    )
    sputters = _commands_to(state, 2, "erhp_sputter")
    assert any("ericrolph_hot_potato_sputter.ogg" in c for c in sputters)
    assert any("AudioDefault3D" in c for c in sputters), (
        "the sputter must ride the stock NON-looping description"
    )
    # And the loop was stopped for it: the sputter is the finish, not a
    # layer over a still-running whistle.
    stops = [c for c in _commands_to(state, 2, "ericrolph_hot_potato_whistle") if "stopSFX" in c]
    assert stops, "the whistle loop was never stopped for the sputter"


def test_steady_tick_style_keeps_the_whistle_flat(rig):
    """Hardcore's contract, extended to the whistle: steady style holds
    constant pitch and never sputters - no audio tell that the end is
    near."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 8)
    assert module.hotPotatoSetOption("tick_style", "steady") is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase == "boom",
        limit_seconds=12.0,
    )
    whistle_writes = _commands_to(state, 2, "ericrolph_hot_potato_whistle")
    pitches = {
        round(float(found.group(2)), 3)
        for command in whistle_writes
        for found in [TICK_WRITE.search(command)]
        if found
    }
    assert pitches <= {1.0}, f"steady style leaked a pitch tell: {pitches}"
    assert not _commands_to(state, 2, "erhp_sputter"), (
        "steady style must not sputter - silence about the end IS the mode"
    )


def test_whistle_option_gates_the_whole_voice(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("whistle_enabled", False) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    assert not [
        c for c in _commands_to(state, 2, "ericrolph_hot_potato_whistle") if "playSFX(" in c
    ], "whistle_enabled=false still started the loop"


def test_ai_drivers_chase_flee_and_release(rig):
    """v2.5, "this game is meant to be multiplayer": with ai_enabled on, the
    AI carrier CHASES its nearest target, every other AI car FLEES the
    carrier, the player is never commanded, and flipping the option off
    hands every car back to its user."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 80.0, 0.0, 0.0)
    # Inside the default arena (v2.6): a car beyond 91.4 m is no longer
    # conscripted at all — that gate has its own test now.
    state.addVehicle(4, "etk800", -60.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=8)

    # Idle phase: the AI cars hold position; the player is untouched.
    assert any("ai.setMode('stop')" in c for c in _commands_to(state, 3, "ai.setMode"))
    assert any("ai.setMode('stop')" in c for c in _commands_to(state, 4, "ai.setMode"))
    assert not _commands_to(state, 2, "ai.setMode"), "the AI sweep commanded the PLAYER'S vehicle"

    # Vehicle 3 takes the potato: it hunts, 4 flees it, 2 stays untouched.
    assert start_round(state, module, 3) == 3
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=8)
    hunts = [c for c in _commands_to(state, 3, "ai.setMode") if "'chase'" in c]
    assert hunts, "the AI carrier never went hunting"
    assert any("setTargetObjectID(" in c for c in hunts)
    flees = [c for c in _commands_to(state, 4, "ai.setMode") if "'flee'" in c]
    assert flees, "the AI field never fled the carrier"
    assert any("setTargetObjectID(3)" in c for c in flees), "the fleeing car must flee the CARRIER"
    assert not _commands_to(state, 2, "ai.setMode")

    # The release: ai_enabled off returns every commanded car to its user.
    state.clear()
    assert module.hotPotatoSetOption("ai_enabled", False) is True
    tick(state, module, seconds=0.2, steps=8)
    for vehicle_id in (3, 4):
        assert any(
            "ai.setMode('disabled')" in c for c in _commands_to(state, vehicle_id, "ai.setMode")
        ), f"vehicle {vehicle_id} was never released"


def test_fireworks_for_any_round_winner_not_only_the_champion(rig):
    """v2.5 ("Champion fireworks should be for any winner"): the FIRST round
    win - far short of wins_to_champion - already writes the winner's name
    across the sky."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    assert int(spec.BEHAVIOR["wins_to_champion"]) > 1, (
        "this test needs a first win that is NOT the crowning"
    )
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.removeVehicle(3)
    module.onVehicleDestroyed(3)
    run_until(
        state,
        module,
        lambda: any("LAST CAR STANDING" in m for m in state.messages.values()),
        limit_seconds=20.0,
    )
    assert not any("CHAMPION" in m for m in state.messages.values()), (
        "one win must not crown - the show under test is the ROUND win's"
    )
    # Let a few letters burst.
    tick(state, module, seconds=0.1, steps=60)
    assert any(name.endswith("fw_px_1") for name in state.scene), (
        "no firework light pool for a round winner"
    )
    assert _poses_of(state, "fw_px_1"), "the winner's fireworks never moved"


# --------------------------------------------------------------------------
# v2.6 (2026-08-30): the arena, protect mode, damage armor, and the halo.


def test_the_arena_gates_who_can_receive_the_potato(rig):
    """v2.6 ("any AI vehicle within the game radius becomes part of the hot
    potato game"): a car outside the arena circle cannot receive the potato,
    however close the transfer rules say it is."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 60) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 30.0, 0.0, 0.0)  # in pass range, OUT of arena
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=10)
    assert _carrier_of(module) == 2, "a car outside the arena received the potato"
    # The same car one step inside the circle is a legal receiver at once.
    state.moveVehicle(3, 12.0, 0.0, 0.0)
    run_until(state, module, lambda: _carrier_of(module) == 3, limit_seconds=5.0)


def test_arena_off_restores_the_open_field(rig):
    """The circle is an option: with arena_enabled off the same faraway car
    is a legal receiver again."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_enabled", False) is True
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 60) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 30.0, 0.0, 0.0)
    tick(state, module)
    # With the circle off the faraway car is a legal receiver the moment
    # the round arms - the pass can land inside start_round itself.
    start_round(state, module, 2)
    run_until(state, module, lambda: _carrier_of(module) == 3, limit_seconds=5.0)


def test_arena_conscription_and_containment_herd_the_ai(rig):
    """v2.6: only cars INSIDE the circle are conscripted, and a conscripted
    car that strays out is steered straight back at the arch with the
    raw-coordinate slotTraffic target (ai.lua:5833), refreshed faster than
    its 0.5 s watchdog, until it is well inside again."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    # x=12: inside the 20 m arena but OUTSIDE the 7.5 m pickup radius, so
    # no round arms and the idle role stays under test.
    state.addVehicle(2, "etk800", 12.0, 0.0, 0.0)  # inside: conscripted
    state.addVehicle(3, "etk800", 100.0, 0.0, 0.0)  # outside: left alone
    tick(state, module, seconds=0.2, steps=10)
    assert _commands_to(state, 2, "ai.setMode"), "the car inside the arena was never conscripted"
    assert not _commands_to(state, 3, "ai."), "a car outside the arena must never be commandeered"
    # The conscripted car strays out: containment takes over.
    state.clear()
    state.moveVehicle(2, 40.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=12)
    herds = _commands_to(state, 2, "ai.setSlotTrafficTarget")
    assert len(herds) >= 4, f"containment must outpace the 0.5 s watchdog, saw {len(herds)} writes"
    # Home again, well inside the 80% hysteresis line (16 m) but clear of
    # the pickup radius: the role comes back and the herding stops.
    state.moveVehicle(2, 12.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    assert _commands_to(state, 2, "ai.setMode('stop')"), "a returned car never got its role back"
    state.clear()
    tick(state, module, seconds=0.2, steps=10)
    assert not _commands_to(state, 2, "ai.setSlotTrafficTarget"), (
        "containment kept herding a car that is already home"
    )


def test_protect_mode_inverts_the_hunt_and_scores_the_holder(rig):
    """v2.6, the reverse game: in protect mode the AI mob hunts the carrier,
    an AI carrier runs for its life, and held seconds score toward the same
    target the hoarder race uses."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.playerId = 2
    assert module.hotPotatoSetOption("game_mode", "protect") is True
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    state.addVehicle(2, "etk800", 40.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(4, "etk800", -40.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 3) == 3
    state.moveVehicle(3, 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    hunts = [c for c in _commands_to(state, 4, "ai.setMode") if "'chase'" in c]
    assert hunts, "the mob never hunted the carrier"
    assert any("ai.setTargetObjectID(3)" in c for c in hunts), "the hunt must target the carrier"
    flees = [c for c in _commands_to(state, 3, "ai.setMode") if "'flee'" in c]
    assert flees, "the AI carrier should flee its pursuers in protect mode"
    stats = module.hotPotatoGetStats()
    assert stats.scores and stats.scores[1] is not None, "no protect scoreboard"
    assert float(stats.scores[1].points) >= 1, "held seconds never scored"


def test_ai_role_commands_tune_after_the_mode_switch(rig):
    """v2.6, measured: ai.setMode -> resetMapAndRoute -> resetAggression /
    resetParameters (ai.lua:5780), so aggression and the speed cap sent
    BEFORE setMode are silently wiped by it. The role command must open
    with setMode. (The v2.5 order shipped exactly that bug.)"""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    state.playerId = 2
    state.addVehicle(2, "etk800", 40.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 3) == 3
    state.moveVehicle(3, 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    roles = [c for c in _commands_to(state, 3, "ai.setMode") if "ai.setAggression" in c]
    assert roles, "no tuned role command reached the AI carrier"
    for command in roles:
        assert command.index("ai.setMode") < command.index("ai.setAggression"), (
            f"tuning sent before setMode is wiped by it: {command}"
        )


def test_no_damage_mode_armors_the_field_but_never_the_boom(rig):
    """v2.6 damage options: no_damage armors every participant's beams to
    math.huge (the jbeam loader's own unbreakable semantic), and the
    detonation VICTIM has armor stripped before the break commands queue
    behind it in the same VM."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 8)
    assert module.hotPotatoSetOption("damage_mode", "no_damage") is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 40.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=8)
    for vehicle_id in (2, 3):
        armors = _commands_to(state, vehicle_id, "ericrolph_hot_potato_armor")
        assert any('"full"' in c for c in armors), f"vehicle {vehicle_id} was never armored"
        assert any("setBeamStrength" in c and "math.huge" in c for c in armors)
    assert start_round(state, module, 2) == 2
    _detonate_carrier(state, module, spec)
    ordered = [e.command for e in state.commands.values() if e.id == 2]
    strip = next(
        i for i, c in enumerate(ordered) if "ericrolph_hot_potato_armor" in c and '"none"' in c
    )
    smash = next(i for i, c in enumerate(ordered) if "breakAllBreakgroups" in c)
    assert strip < smash, "the boom hit a still-armored car"


def test_transfer_shield_armors_the_pair_then_lets_go(rig):
    """v2.6 ("vehicles transferring the potato are temporarily invincible
    when they collide"): an impact pass full-armors both cars at once, and
    the armor sweep hands stock damage back after the window."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 40.0, 0.0, 0.0)
    close_in(state, module, 3, 2, 10.0)
    run_until(state, module, lambda: _carrier_of(module) == 3, limit_seconds=6.0)
    for vehicle_id in (2, 3):
        assert any(
            '"full"' in c for c in _commands_to(state, vehicle_id, "ericrolph_hot_potato_armor")
        ), f"vehicle {vehicle_id} was not shielded through the pass"
    state.clear()
    tick(state, module, seconds=0.2, steps=30)  # 6 s > the 3 s default window
    for vehicle_id in (2, 3):
        assert any(
            '"none"' in c for c in _commands_to(state, vehicle_id, "ericrolph_hot_potato_armor")
        ), f"vehicle {vehicle_id} kept its shield past the window"


def test_the_halo_walls_the_arena_only_while_a_round_runs(rig):
    """v2.6 ("a see through halo ... when the game starts that goes away
    when the game ends"): the immediate-mode wall exists on live frames,
    never between rounds, and the option kills it entirely."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=5)
    assert len(state.halo) == 0, "the halo must not exist between rounds"
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=3)
    assert len(state.halo) > 0, "no halo while the round is live"
    assert module.hotPotatoSetOption("arena_halo_enabled", False) is True
    before = len(state.halo)
    tick(state, module, seconds=0.2, steps=3)
    assert len(state.halo) == before, "the halo option did not kill the wall"


# --------------------------------------------------------------------------
# v2.7 (2026-09-01): the arena magnet, the fireworks that actually render,
# and very light steam off the landed mash.
# --------------------------------------------------------------------------

MAGNET_G = 6.674e-11


def _well_masses(state, vehicle_id):
    """The mass of every gravity well placed on `vehicle_id`, in order.

    The runtime writes obj:setPlanets({x, y, z, 10, mass}); a clear is
    setPlanets({}) and parses to nothing here.
    """

    masses = []
    for command in _commands_to(state, vehicle_id, "obj:setPlanets({"):
        found = re.search(r"10, ([0-9.eE+-]+)\}\)", command)
        if found:
            masses.append(float(found.group(1)))
    return masses


def _well_heights(state, vehicle_id):
    """The z of every gravity well placed on `vehicle_id`, in order."""

    heights = []
    for command in _commands_to(state, vehicle_id, "obj:setPlanets({"):
        found = re.search(r"obj:setPlanets\(\{[-0-9.]+, [-0-9.]+, ([-0-9.]+), 10,", command)
        if found:
            heights.append(float(found.group(1)))
    return heights


MAGNET_LIFT_CAP_G = 0.65


def _expected_hoist(gees, speed=0.0):
    """The v2.9 hoist: the v2.7.1 0.6 while the car is slow, tapered to 25 %
    of it by ram speed, then lowered further if it would lift more than the
    cap at these gees."""

    share = (speed - 10.0) / (28.0 - 10.0)
    taper = min(max(share, 0.0), 1.0)
    hoist = 0.6 * (1.0 - taper * (1.0 - 0.25))
    lift_share = MAGNET_LIFT_CAP_G / max(gees, 1e-4)
    if lift_share < 1.0:
        hoist = min(hoist, lift_share / (1.0 - lift_share * lift_share) ** 0.5)
    return hoist


def _magnet_mass(gees, distance, speed=0.0):
    """The well law: the well hangs `hoist`*d above the pad, and the mass
    makes the requested gees at the true 3D reach to that hoisted point."""

    lift = distance * _expected_hoist(gees, speed)
    return gees * 9.81 * (distance * distance + lift * lift) / MAGNET_G


def _well_components(state, vehicle_id, distance):
    """(lift g, horizontal g) the last well on `vehicle_id` actually applies
    to a car at `distance` — read back from the command the runtime sent."""

    mass = _well_masses(state, vehicle_id)[-1]
    lift = _well_heights(state, vehicle_id)[-1]
    reach2 = distance * distance + lift * lift
    accel = MAGNET_G * mass / reach2
    reach = reach2**0.5
    return accel * lift / reach / 9.81, accel * distance / reach / 9.81


def test_the_magnet_tethers_a_strayed_member_and_lets_go_inside(rig):
    """v2.7 ("a magnetic force that pulls vehicles back into the center"):
    a round member — the PLAYER included, which the AI steering can never
    touch — who drives out of the ring gets a standing gravity well at the
    pad (obj:setPlanets, the engine's own attractor), with its mass
    recomputed from the car's current range so the pull is a constant
    arena_magnet_g anywhere outside. Bystanders never inside the ring are
    never touched, and the well lifts once the car is well inside again."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.playerId = 3
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)  # inside: a member
    state.addVehicle(4, "etk800", 200.0, 0.0, 0.0)  # bystander: never inside
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)  # the sweep drafts 3 inside
    state.clear()
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=12)
    masses = _well_masses(state, 3)
    assert len(masses) >= 3, (
        f"the well must refresh with the 0.25 s sweep, saw {len(masses)} writes"
    )
    # Constant-force tether at d = 40 m, at the shipped default of 1.2 g.
    expected = _magnet_mass(1.2, 40.0)
    assert abs(masses[-1] - expected) / expected < 0.05, (
        f"well mass {masses[-1]:g} is not the constant-force tether {expected:g}"
    )
    # The well hangs above the pad (v2.7.1): 0.6 * 40 = 24 m up, so the
    # pull lifts as it drags — a flat pull lost to tire grip in live play.
    heights = _well_heights(state, 3)
    assert heights and abs(heights[-1] - 24.0) < 1.0, (
        f"the well must hang ~24 m over the pad, sat at {heights and heights[-1]}"
    )
    assert not _commands_to(state, 4, "obj:setPlanets"), (
        "a bystander that was never inside the ring got a gravity well"
    )
    # Home again, inside the 90% release line (18 m): the well lifts.
    state.clear()
    state.moveVehicle(3, 12.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=6)
    assert any("obj:setPlanets({})" in c for c in _commands_to(state, 3, "setPlanets")), (
        "the well never lifted after the car came home"
    )


def test_the_magnet_obeys_its_toggle_and_its_strength_dial(rig):
    """The magnet is a HUD option twice over: arena_magnet_enabled places or
    withholds the well, and arena_magnet_g scales its mass — membership
    rides the arena, so flipping the magnet on mid-round still catches a
    car that is already outside."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    assert module.hotPotatoSetOption("arena_magnet_enabled", False) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=8)
    assert not _commands_to(state, 3, "setPlanets"), "the magnet placed a well while switched off"
    # The car is ALREADY outside when the host flips the magnet on: it was
    # drafted while inside, so the heavier well lands on it at once.
    assert module.hotPotatoSetOption("arena_magnet_enabled", True) is True
    assert module.hotPotatoSetOption("arena_magnet_g", 2.0) is True
    state.clear()
    tick(state, module, seconds=0.2, steps=8)
    masses = _well_masses(state, 3)
    assert masses, "the mid-round toggle never placed the well"
    expected = _magnet_mass(2.0, 40.0)
    assert abs(masses[-1] - expected) / expected < 0.05, (
        f"well mass {masses[-1]:g} ignored the strength dial ({expected:g})"
    )
    # At 2.0 g the v2.9 lift cap bites: the well is LOWERED so the pull can
    # never lift more than 0.65 g, while the haul keeps the dialled gees.
    lift_g, horizontal_g = _well_components(state, 3, 40.0)
    assert lift_g <= MAGNET_LIFT_CAP_G + 0.01, f"lift {lift_g:.2f} g over the cap"
    assert horizontal_g > 1.6, f"the cap weakened the haul itself ({horizontal_g:.2f} g)"


def test_the_magnet_finishes_its_haul_then_never_outlives_it(rig):
    """A gravity well is a STANDING physics-side setting, so it must never
    leak — but v2.9 (the G2 crest-ram gate) changed WHEN it lifts: dropping
    every well the frame the round ended ABANDONED a car still outside,
    because no later round can draft a car that is not inside the ring when
    it arms. The haul now finishes across the round end, and the well lifts
    the moment the car is home, on toggle-off, and at teardown."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 8)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=6)
    assert _well_masses(state, 3), "no well to test the release against"
    state.clear()
    _detonate_carrier(state, module, spec)
    tick(state, module, seconds=0.2, steps=3)
    assert module.getSystemState(PROP_ID).behavior_phase != "live"
    assert not any("obj:setPlanets({})" in c for c in _commands_to(state, 3, "setPlanets")), (
        "the round end abandoned a car that was still outside the ring"
    )
    assert _well_masses(state, 3), "the haul stopped the moment the round ended"
    # Home: the well lifts at once, round or no round.
    state.clear()
    state.moveVehicle(3, 12.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=3)
    assert any("obj:setPlanets({})" in c for c in _commands_to(state, 3, "setPlanets")), (
        "the well outlived the car's return"
    )


def test_the_post_round_haul_is_bounded_and_releasable(rig):
    """The grace is not a licence to leak: a car that is still outside when
    it expires is released, and the toggle and teardown release instantly."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 8)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.moveVehicle(3, 400.0, 0.0, 0.0)  # far enough that it never gets home
    tick(state, module, seconds=0.2, steps=6)
    _detonate_carrier(state, module, spec)
    tick(state, module, seconds=0.2, steps=3)
    state.clear()
    run_until(
        state,
        module,
        lambda: any("obj:setPlanets({})" in c for c in _commands_to(state, 3, "setPlanets")),
        limit_seconds=30.0,
    )
    state.clear()
    tick(state, module, seconds=0.2, steps=10)
    assert not _well_masses(state, 3), "the well came back after the grace expired"


def test_the_magnet_hauls_a_far_member_at_the_dialled_gees(rig):
    """The G2 crest-ram case (a car at r 190.5 m that was never hauled
    home): there is no range cap in the well law — a drafted member gets the
    full dialled pull at any range, with the mass rebuilt from its CURRENT
    reach so the force never fades."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 91.4) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 60.0, 0.0, 0.0)  # inside: drafted
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    for distance in (110.0, 190.5, 250.0):
        state.clear()
        state.moveVehicle(3, distance, 0.0, 0.0)
        tick(state, module, seconds=0.2, steps=6)
        masses = _well_masses(state, 3)
        assert masses, f"a member at {distance} m was never tethered"
        expected = _magnet_mass(1.2, distance)
        assert abs(masses[-1] - expected) / expected < 0.05, (
            f"the well at {distance} m did not carry the dialled gees"
        )
        _lift_g, horizontal_g = _well_components(state, 3, distance)
        assert horizontal_g > 1.0, f"the haul at {distance} m is only {horizontal_g:.2f} g inward"


def test_the_magnet_ramps_its_grab_in(rig):
    """v2.9: a 1.2 g step onto a car doing 30 m/s is an impulse. The grab
    eases in over ~0.6 s instead, then holds the full dial."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    tick(state, module, seconds=0.05, steps=6)  # through the grab sweep
    first = _well_masses(state, 3)
    assert first, "no well was placed on the strayed member"
    full = _magnet_mass(1.2, 40.0)
    assert first[0] < full * 0.5, f"the grab was a step, not a ramp ({first[0]:g} vs {full:g})"
    tick(state, module, seconds=0.2, steps=10)  # past the 0.6 s ramp
    assert abs(_well_masses(state, 3)[-1] - full) / full < 0.05, (
        "the ramp never reached the dialled gees"
    )


def test_the_magnet_keeps_a_fast_car_on_its_tires(rig):
    """v2.9, the 110 km/h crest ram that ROLLED (min up-vector z 0.20, past
    78 degrees) during the haul: the fixed 31-degree hoist strips 62 % of a
    car's weight, so nothing damps a car that arrives already rotating. The
    hoist now tapers with speed — the slow tractor-beam haul is unchanged,
    a ram-speed car keeps its tires loaded."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    # Slow (the v2.7.1 braked hulk): the shipped 0.6 hoist, unchanged.
    state.clear()
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    state.setVelocity(3, 0.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    slow_lift, slow_pull = _well_components(state, 3, 40.0)
    assert abs(_well_heights(state, 3)[-1] - 24.0) < 0.2, "the slow hoist moved"
    assert 0.60 < slow_lift < 0.64, f"the braked-hulk lift changed ({slow_lift:.3f} g)"
    # 110 km/h (30.6 m/s): past the taper, the well drops and the lift with it.
    state.clear()
    state.setVelocity(3, 30.6, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=6)
    fast_lift, fast_pull = _well_components(state, 3, 40.0)
    assert fast_lift < slow_lift * 0.45, f"a ram-speed car still loses {fast_lift:.2f} g of weight"
    assert fast_lift < 0.3, f"lift {fast_lift:.2f} g still unloads the tires"
    assert fast_pull > slow_pull, "flattening the well must not weaken the haul"


def test_the_magnet_never_lifts_more_than_its_cap(rig):
    """Whatever the host dials, the well may never lift enough to take the
    wheels off the ground (arena design v3 section 4.4: lift >= 1 g is the
    ceiling). The cap lowers the well; it never weakens the haul."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    assert module.hotPotatoSetOption("arena_magnet_g", 3.0) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    lift_g, horizontal_g = _well_components(state, 3, 40.0)
    assert lift_g <= MAGNET_LIFT_CAP_G + 0.01, f"lift {lift_g:.2f} g over the cap"
    assert horizontal_g > 2.8, f"the cap stole the haul ({horizontal_g:.2f} g)"


def test_membership_is_sampled_every_frame(rig):
    """A car crossing the ring at ram speed covers ~6 m between two 0.25 s
    sweeps. Drafting on the sweep alone let a fast crossing go un-drafted -
    and an un-drafted car can never be hauled home. Membership is sampled
    every frame: one frame inside is enough."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 91.4) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 400.0, 0.0, 0.0)  # outside: not a member
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    assert not _well_masses(state, 3), "a bystander was tethered"
    # ONE frame inside the ring, mid-sweep, then straight back out at ram
    # speed - the crest-ram crossing.
    state.moveVehicle(3, 85.0, 0.0, 0.0)
    tick(state, module, seconds=0.02)
    state.moveVehicle(3, 190.5, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=6)
    assert _well_masses(state, 3), (
        "a car that crossed the ring between two sweeps was never drafted"
    )


# --------------------------------------------------------------------------
# v2.10 (2026-09-02): the arena's G3/G7.3 gates — the dodge that never
# committed, and the well that rolled a car in a sustained orbit.


def test_the_dodge_commits_instead_of_oscillating(rig):
    """G7.3 measured 25 obstacle contacts with every post registered. The
    v2.7.1 sweep recomputed the side-step from the car's CURRENT heading and
    released the moment the ray cleared, so the car oscillated around the
    pillar at 4 Hz while closing on it. The aim point is now LATCHED in
    world space and held until the car is past the post: the same target
    comes back sweep after sweep, even once the heading no longer clips."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert (
        module.hotPotatoRegisterObstacles(_lua_points(lua, [{"x": 0.0, "y": 40.0, "r": 6.5}]))
        is True
    )
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 0.0, 70.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.setVelocity(3, 0.0, -18.0, 0.0)  # southbound, dead at the post
    tick(state, module, seconds=0.2, steps=2)
    dodges = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert dodges, "no dodge was steered at the post"
    latched = _slot_target(dodges[-1])
    # The car now turns onto the escape line: its heading no longer clips
    # the post at all. The old code released here and let the role sweep
    # aim it back through the pillar; the latch must hold the SAME target.
    state.clear()
    state.setVelocity(3, -12.0, -12.0, 0.0)
    tick(state, module, seconds=0.2, steps=4)
    held = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert held, "the dodge released as soon as the heading cleared"
    assert _slot_target(held[-1]) == latched, (
        "the aim point moved mid-manoeuvre - that is the 4 Hz oscillation"
    )
    assert not any("'flee'" in c for c in _commands_to(state, 3, "ai.setMode")), (
        "the role sweep stomped the dodge mid-manoeuvre"
    )
    # Past the post: the latch lets go and the role comes back.
    state.clear()
    state.moveVehicle(3, 0.0, 10.0, 0.0)
    state.setVelocity(3, 0.0, -18.0, 0.0)
    tick(state, module, seconds=0.2, steps=8)
    assert any("'flee'" in c for c in _commands_to(state, 3, "ai.setMode")), (
        "the role never came back after the car passed the post"
    )


def test_the_dodge_aims_wide_of_the_post_at_range(rig):
    """The old side-step was the car's own heading plus a fixed offset,
    placed 8 m beyond the post: detected at 37 m that is a 12-degree
    deviation, far too shallow to leave a 6.5 m corridor. The aim point is
    now computed FROM THE POST, so the miss distance is the keep-out plus
    the clearance whatever the range."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert (
        module.hotPotatoRegisterObstacles(_lua_points(lua, [{"x": 0.0, "y": 20.0, "r": 6.5}]))
        is True
    )
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 0.0, 57.0, 0.0)  # 37 m short of the post
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.setVelocity(3, 0.0, -17.0, 0.0)
    tick(state, module, seconds=0.2, steps=2)
    dodges = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert dodges, "a post 37 m ahead was never dodged"
    tx, ty = _slot_target(dodges[-1])
    miss = abs(tx - 0.0)
    assert miss >= 10.0, f"the aim point clears the 6.5 m post by only {miss:.1f} m at range"
    assert ty < 20.0, "the aim point must sit beside the post, not beyond it"


def test_a_fast_wide_car_gets_a_wider_dodge_corridor(rig):
    """The trigger corridor grows with speed: a car at 17 m/s needs more
    room than one at 5 m/s, and the old fixed keep-out let a fast car pass
    just outside the trigger and clip the post anyway."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert (
        module.hotPotatoRegisterObstacles(_lua_points(lua, [{"x": 9.0, "y": 40.0, "r": 6.5}]))
        is True
    )  # 9 m off the ray: outside the bare 6.5 m keep-out
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 0.0, 70.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    # Slow: 9 m of miss is fine, no dodge.
    state.clear()
    state.setVelocity(3, 0.0, -5.0, 0.0)
    tick(state, module, seconds=0.2, steps=3)
    assert not _commands_to(state, 3, "ai.setSlotTrafficTarget"), (
        "a slow car dodged a post it was already missing by 9 m"
    )
    # 17 m/s: the corridor widens by 0.35 m per m/s and the post threatens.
    state.clear()
    state.setVelocity(3, 0.0, -17.0, 0.0)
    tick(state, module, seconds=0.2, steps=3)
    assert _commands_to(state, 3, "ai.setSlotTrafficTarget"), (
        "a fast car did not widen its corridor for a post 9 m off the ray"
    )


def test_the_dodge_will_not_side_step_into_the_next_post(rig):
    """A long wall registered as a STRING OF BEADS (the ramp flanks) breaks
    the naive side-step: stepping abeam one bead can aim straight at its
    neighbour. Both sides are scored by the room they actually leave, and
    the blocked one is refused. NOTE: this only makes bead-strings survivable
    - routing around a 44.5 m FACE needs a segment primitive, which is a
    design-side ask, not a runtime one (see DESIGN.md v2.10)."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    # A wall of beads running east from x = 0, and the car approaching from
    # the north: the naive "favoured side" would step it along the wall.
    wall = [{"x": float(x), "y": 40.0, "r": 6.5} for x in range(0, 30, 6)]
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, wall)) is True
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 6.0, 70.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.setVelocity(3, 0.0, -18.0, 0.0)  # dead at the bead at x = 6
    tick(state, module, seconds=0.2, steps=2)
    dodges = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert dodges, "no dodge was steered at the bead wall"
    tx, ty = _slot_target(dodges[-1])
    # Whatever side it picks, the aim point must not sit inside another bead.
    for bead in wall:
        gap = ((tx - bead["x"]) ** 2 + (ty - bead["y"]) ** 2) ** 0.5
        if bead["x"] != 6.0:
            assert gap > bead["r"], (
                f"the dodge aimed inside the bead at x={bead['x']} (gap {gap:.1f} m)"
            )
    assert tx < 0.0 or tx > 24.0, f"the escape must leave the wall's span, aimed x={tx:.1f}"


def _pin_rig(rig, post=(0.0, 40.0, 6.5)):
    """A conscripted car parked hard against a registered post, stopped."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert (
        module.hotPotatoRegisterObstacles(
            _lua_points(lua, [{"x": post[0], "y": post[1], "r": post[2]}])
        )
        is True
    )
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", post[0], post[1] + post[2] + 0.5, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.setVelocity(3, 0.0, -0.7, 0.0)  # G10's median pin speed
    return state, module


def test_a_car_pinned_against_a_post_is_backed_out(rig):
    """G10's D-8: with the dangerous strikes gone, what was left was 23
    contacts at <= 2.7 m/s (median 0.7) - cars ground against a pillar at
    fixed positions. The dodge rays the VELOCITY vector, and a pinned car
    has none, so v2.7.1's own `speed > 3.0` floor gates it out. The pin
    escape aims the car straight back AWAY from the post instead."""

    state, module = _pin_rig(rig)
    tick(state, module, seconds=0.2, steps=3)  # under the 1.5 s pin window
    assert not _commands_to(state, 3, "ai.setSlotTrafficTarget"), (
        "a momentary pause was treated as a pin"
    )
    tick(state, module, seconds=0.2, steps=8)  # past it
    escapes = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert escapes, "a car pinned against a post was left grinding"
    tx, ty = _slot_target(escapes[-1])
    # Away from the post, and well outside its keep-out.
    assert ty > 40.0, f"the escape aimed across the post, not away (y={ty})"
    gap = ((tx - 0.0) ** 2 + (ty - 40.0) ** 2) ** 0.5
    assert gap >= 6.5 + 4.0, f"the escape stops inside the keep-out ({gap:.1f} m)"


def test_the_pin_escape_commits_then_hands_back(rig):
    """The escape is latched (it must not become the 4 Hz limit cycle ask
    #5 killed) and time-boxed (a car that cannot get clear must not be
    steered at a wall for ever)."""

    state, module = _pin_rig(rig)
    tick(state, module, seconds=0.2, steps=10)
    first = _slot_target(_commands_to(state, 3, "ai.setSlotTrafficTarget")[-1])
    state.clear()
    tick(state, module, seconds=0.2, steps=6)  # still pinned, still stopped
    held = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert held, "the escape let go while the car was still pinned"
    assert _slot_target(held[-1]) == first, (
        "the escape target moved - that is the oscillation, not an escape"
    )
    assert not any("'flee'" in c for c in _commands_to(state, 3, "ai.setMode")), (
        "the role sweep stomped the escape"
    )
    # Time-boxed: a car that never gets clear is handed back to its role.
    state.clear()
    tick(state, module, seconds=0.2, steps=40)
    assert any("'flee'" in c for c in _commands_to(state, 3, "ai.setMode")), (
        "the escape held the wheel past its ceiling"
    )


def test_the_pin_escape_arms_at_the_measured_grinding_geometry(rig):
    """G11 reproduced exactly: 12 grinding events at 1.85-2.02 m of
    REF-NODE clearance from a 6.5 m post, at 0.7 m/s, with no other car
    within 6.5 m - and v2.12's flat 1.5 m envelope never armed once. A ref
    node is the car's centre, so 1.9 m of ref clearance on a car carrying
    ~2.5 m of half-extent is a BODY already inside the keep-out. Measured
    to the extent, it arms.

    This post carries no `rp`, so the envelope is judged against the
    keep-out exactly as v2.14 shipped it. Once a caller supplies measured
    physical radii (v2.15) the same question is asked of the SOLID instead
    - see the rp gates below."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert (
        module.hotPotatoRegisterObstacles(_lua_points(lua, [{"x": 0.0, "y": 40.0, "r": 6.5}]))
        is True
    )
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    # 1.9 m of ref-node clearance outside the 6.5 m keep-out: the exact
    # band G11 measured, and the band v2.12 sat just outside of.
    state.addVehicle(3, "etk800", 0.0, 40.0 + 6.5 + 1.9, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    assert not [
        v
        for v in state.vehicles.values()
        if int(v.id) not in (1, 3)
        and ((float(v.pos.x) - 0.0) ** 2 + (float(v.pos.y) - 40.0) ** 2) ** 0.5 < 6.5
    ], "the reproduction must have no other car near the post, as measured"
    state.clear()
    state.setVelocity(3, 0.0, -0.7, 0.0)  # G11's median grinding speed
    tick(state, module, seconds=0.2, steps=10)  # 2 s
    escapes = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert escapes, "the reflex still never arms at the geometry G11 measured grinding at"
    _tx, ty = _slot_target(escapes[-1])
    assert ty > 40.0, "the escape must aim away from the post"


@pytest.mark.parametrize("keepout,arms", [(8.0, True), (6.5, False)])
def test_the_pin_envelope_scales_with_the_posts_own_keepout(rig, keepout, arms):
    """The envelope is the post's OWN authored keep-out plus the car's
    cached extent plus a small margin - not a constant. So at one fixed
    distance from the post centre, an 8 m post (the handle corners and jamb
    faces) arms where a 6.5 m pillar does not."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert (
        module.hotPotatoRegisterObstacles(_lua_points(lua, [{"x": 0.0, "y": 40.0, "r": keepout}]))
        is True
    )
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 0.0, 40.0 + 10.5, 0.0)  # 10.5 m from centre
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.setVelocity(3, 0.0, -0.7, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    armed = bool(_commands_to(state, 3, "ai.setSlotTrafficTarget"))
    assert armed is arms, f"a {keepout} m post at 10.5 m {'did not arm' if arms else 'armed'}"


def _post_rig(rig, post):
    """A conscripted car plus one registered post; returns (state, module)."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, [post])) is True
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    return state, module


def test_a_post_without_rp_behaves_exactly_as_before(rig):
    """v2.15's second radius is OPTIONAL: absent, rp reports as r and every
    caller written before this round is unaffected."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, ARENA_POSTS)) is True
    report = module.hotPotatoGetObstacles()
    assert int(report.count) == 16
    for index in range(1, 17):
        entry = report.entries[index]
        assert float(entry.rp) == float(entry.r), "absent rp must default to r"


def test_the_pin_arms_on_the_solid_and_the_dodge_steers_on_the_keepout(rig):
    """G12: sizing the pin envelope on the 6.5 m KEEP-OUT inflated it to a
    9.4 m disc around all 42 posts and shoved cars off course in open
    ground (contacts 17 -> 51). The two radii answer different questions -
    the pin asks about the solid (rp), the steering dodge asks about the
    corridor (r) - and this proves each uses its own."""

    post = {"x": 0.0, "y": 40.0, "r": 6.5, "rp": 1.5}
    # 7.0 m from the post centre: inside the OLD keep-out envelope (9.49 m),
    # far outside the solid's (4.49 m). It must no longer arm.
    state, module = _post_rig(rig, post)
    state.addVehicle(3, "etk800", 0.0, 47.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.setVelocity(3, 0.0, -0.7, 0.0)
    tick(state, module, seconds=0.2, steps=12)
    assert not _commands_to(state, 3, "ai.setSlotTrafficTarget"), (
        "a car 5.5 m clear of a 1.5 m pillar was still shoved by the pin"
    )


def test_the_pin_still_arms_against_the_solid_itself(rig):
    """The other half: hard against a 1.5 m pillar, it must still arm."""

    state, module = _post_rig(rig, {"x": 0.0, "y": 40.0, "r": 6.5, "rp": 1.5})
    state.addVehicle(3, "etk800", 0.0, 44.0, 0.0)  # 4.0 m: body on the solid
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.setVelocity(3, 0.0, -0.7, 0.0)
    tick(state, module, seconds=0.2, steps=12)
    escapes = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert escapes, "a car against the solid did not arm the pin escape"
    _tx, ty = _slot_target(escapes[-1])
    # Backed out clear of the SOLID plus clearance, not of the whole
    # corridor: 1.5 + 4 + 6 = 11.5 m from the post, not 16.5 m.
    assert abs(ty - (40.0 + 11.5)) < 0.2, f"escape aimed to y={ty}, not 51.5"


def test_the_dodge_still_steers_on_the_keepout_radius(rig):
    """Same post: a MOVING car must still be given the full 6.5 m corridor
    berth, because avoidance is a question about the corridor."""

    state, module = _post_rig(rig, {"x": 0.0, "y": 40.0, "r": 6.5, "rp": 1.5})
    state.addVehicle(3, "etk800", 0.0, 70.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.setVelocity(3, 0.0, -18.0, 0.0)
    tick(state, module, seconds=0.2, steps=2)
    dodges = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert dodges, "the steering dodge stopped firing"
    tx, _ty = _slot_target(dodges[-1])
    assert abs(abs(tx) - (6.5 + 4.0)) < 0.2, (
        f"the dodge aimed {abs(tx):.1f} m abeam - it used rp, not the keep-out"
    )


def test_a_bad_rp_is_refused_whole(rig):
    """rp is the solid inside the corridor, so it can never exceed r, and
    it is validated like every other field: refused whole, one warning,
    prior set untouched."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, ARENA_POSTS)) is True
    for bad in (
        {"x": 0.0, "y": 0.0, "r": 6.5, "rp": 7.0},  # bigger than the keep-out
        {"x": 0.0, "y": 0.0, "r": 6.5, "rp": 0.0},  # under the floor
        {"x": 0.0, "y": 0.0, "r": 6.5, "rp": "1.5"},  # not a number
    ):
        assert module.hotPotatoRegisterObstacles(_lua_points(lua, [bad])) is False, bad
        assert int(module.hotPotatoGetObstacles().count) == 16
    assert not any(e.level == "E" for e in state.events.values())
    # And a legal one is accepted and reported back.
    assert (
        module.hotPotatoRegisterObstacles(
            _lua_points(lua, [{"x": 1.0, "y": 2.0, "r": 6.5, "rp": 1.5}])
        )
        is True
    )
    entry = module.hotPotatoGetObstacles().entries[1]
    assert float(entry.r) == 6.5 and float(entry.rp) == 1.5


def test_the_fuse_burn_rate_is_published(rig):
    """G12 measured 1.71x against a specified 3.0x and could not tell a
    partial application from a stalled clock. The rate is now published
    with the delta it rode on, so a gate reads it instead of inferring it:
    remaining = fuseEnds - now, and both move by the SAME b.lastDelta."""

    state, module = _oob_rig(rig)
    state.moveVehicle(2, 12.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=4)
    stats = module.getSystemState(PROP_ID).behavior_stats
    assert abs(float(stats.fuse_burn) - 1.0) < 1e-6, "in-ring burn is not 1.0"
    assert float(stats.clock_delta) > 0.0, "the mod clock is not advancing"
    assert abs(float(module.hotPotatoGetStats().fuse_burn) - 1.0) < 1e-6
    state.moveVehicle(2, 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=4)
    stats = module.getSystemState(PROP_ID).behavior_stats
    assert abs(float(stats.fuse_burn) - 3.0) < 1e-6, (
        f"out-of-ring burn published as {float(stats.fuse_burn)}, not 3.0"
    )
    assert abs(float(module.hotPotatoGetStats().fuse_burn) - 3.0) < 1e-6
    # And the published rate is the rate actually applied: the fuse falls
    # by fuse_burn x clock_delta per frame.
    before = _remaining(module)
    tick(state, module, seconds=0.2, steps=5)
    dropped = before - _remaining(module)
    assert abs(dropped - 3.0) < 0.15, f"3x published, {dropped / 1.0:.2f}s in 1s"


def test_the_pin_escape_ignores_a_car_that_is_merely_slow(rig):
    """Creeping in open ground is not a pin: no post nearby, no escape."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert (
        module.hotPotatoRegisterObstacles(_lua_points(lua, [{"x": 0.0, "y": 40.0, "r": 6.5}]))
        is True
    )
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 40.0, 40.0, 0.0)  # 40 m clear of the post
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.setVelocity(3, 0.0, -0.7, 0.0)
    tick(state, module, seconds=0.2, steps=15)
    assert not _commands_to(state, 3, "ai.setSlotTrafficTarget"), (
        "a slow car in open ground was given an escape it did not need"
    )


def test_the_flat_well_is_untouched_by_the_slope_work(rig):
    """G10's falsifier: the grade-0 reference orbit moved between serial 50
    and 51. This pins the ruling - at grade 0 every v2.11 term reduces to
    the v2.10 expression EXACTLY, so a run that changes must have sampled
    real grade somewhere along its path (the arena's own bank and glacis
    span r 76-113, and that run reached r 113-115)."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.groundGrade = 0.0
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    state.setVelocity(3, 0.0, 25.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    # The v2.10 numbers, to the digit: hoist 0.225, haul 0.620 g.
    assert abs(_well_heights(state, 3)[-1] - 9.0) < 0.05, "the flat hoist moved"
    lift, haul = _well_components(state, 3, 40.0)
    assert abs(haul - 0.620) < 0.005 and abs(lift - 0.139) < 0.005, (
        f"the flat well moved: lift {lift:.3f}, haul {haul:.3f}"
    )
    # And the same car on the glacis grade DOES see the slope terms - so a
    # path that crosses the bank cannot be called grade-0.
    state.clear()
    state.groundGrade = 0.30
    state.moveVehicle(3, 40.0, 0.0, 12.0)
    tick(state, module, seconds=0.2, steps=6)
    _slope_lift, slope_haul = _well_components(state, 3, 40.0)
    assert slope_haul < haul * 0.75, "the glacis grade did not engage - the ruling would be wrong"


# --------------------------------------------------------------------------
# v2.13 (2026-09-02): the out-of-bounds fuse burn — the player's own
# headline requirement, reinstated after G10 measured the magnet failing to
# counter the perimeter orbit on 4 of 6 bearings.


def _oob_rig(rig, *, multiplier=3.0, radius=20.0, fuse=60):
    """A live round whose carrier can be walked in and out of the ring."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    _shrink_fuse(module, fuse)
    assert module.hotPotatoSetOption("arena_radius_m", radius) is True
    if multiplier is not None:
        assert module.hotPotatoSetOption("oob_burn_multiplier", multiplier) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    return state, module


def _fuse_drop(state, module, seconds=2.0):
    """Fuse seconds consumed over `seconds` of wall clock."""

    before = _remaining(module)
    tick(state, module, seconds=0.2, steps=int(seconds / 0.2))
    return before - _remaining(module)


def test_the_option_defaults_to_off_and_clamps(rig):
    """The burn ships OFF (1.0) so no existing player's game changes; the
    arena turns it on in its boot calls, the pattern every other arena
    option already uses. It has no B entry - it was added after the last
    Blender run - so its default lives in seedOptions, and it must still
    appear in the schema and clamp like every other option."""

    _lua, _state, module, _spec = rig
    assert float(module.hotPotatoGetOptions().oob_burn_multiplier) == 1.0
    schema = module.hotPotatoGetOptionSchema().oob_burn_multiplier
    assert schema is not None and str(schema.kind) == "number"
    assert float(schema.min) == 1.0 and float(schema.max) == 5.0
    assert module.hotPotatoSetOption("oob_burn_multiplier", 3.0) is True
    assert float(module.hotPotatoGetOptions().oob_burn_multiplier) == 3.0
    # Numeric options CLAMP to their range rather than rejecting (the
    # shipped OPTION_RANGE contract), so an absurd dial lands on the max.
    assert module.hotPotatoSetOption("oob_burn_multiplier", 99.0) is True
    assert float(module.hotPotatoGetOptions().oob_burn_multiplier) == 5.0


def test_the_carrier_outside_the_ring_burns_its_fuse_faster(rig):
    """The player's brief, verbatim: "if the vehicle carrying the potato
    goes out of bounds, the potato detonate timer accelerates to 3x speed
    until they re-enter the arena"."""

    state, module = _oob_rig(rig)
    state.moveVehicle(2, 12.0, 0.0, 0.0)  # inside the 20 m ring
    inside = _fuse_drop(state, module)
    assert 1.7 < inside < 2.3, f"the in-ring fuse is not real time ({inside:.2f} s)"
    state.moveVehicle(2, 60.0, 0.0, 0.0)  # out over the crest
    outside = _fuse_drop(state, module)
    assert 5.4 < outside < 6.6, f"3x out of bounds burned {outside:.2f} s in 2 s"
    state.moveVehicle(2, 12.0, 0.0, 0.0)  # back in
    back = _fuse_drop(state, module)
    assert 1.7 < back < 2.3, f"the fuse stayed fast after re-entry ({back:.2f} s)"


def test_the_burn_is_off_by_default_and_when_the_arena_is(rig):
    """Two no-ops that must stay byte-identical: the shipped default (1.0),
    and arena_enabled false - where insideArena returns true, so there is
    no 'outside' at all."""

    state, module = _oob_rig(rig, multiplier=None)
    state.moveVehicle(2, 300.0, 0.0, 0.0)  # far outside any ring
    assert 1.7 < _fuse_drop(state, module) < 2.3, "the default burn is not off"

    state, module = _oob_rig(rig)
    assert module.hotPotatoSetOption("arena_enabled", False) is True
    state.moveVehicle(2, 300.0, 0.0, 0.0)
    assert 1.7 < _fuse_drop(state, module) < 2.3, "arena off still penalised"
    assert module.hotPotatoGetStats().oob is False


def test_the_two_burn_penalties_take_the_max_not_the_product(rig):
    """Camp burn and out-of-bounds burn are two answers to the same
    question. Multiplying them (3x camp * 3x oob = 9x) would detonate a
    slow carrier outside the ring almost instantly - a punishment no player
    could read as a rule. The rule is max()."""

    state, module = _oob_rig(rig)
    assert module.hotPotatoSetOption("camp_burn_multiplier", 3.0) is True
    assert module.hotPotatoSetOption("camp_speed_kmh", 20.0) is True
    # Outside AND stationary: both penalties apply, the burn is 3x, not 9x.
    state.moveVehicle(2, 60.0, 0.0, 0.0)
    state.setVelocity(2, 0.0, 0.0, 0.0)
    both = _fuse_drop(state, module)
    assert 5.4 < both < 6.6, f"camp and oob compounded to {both / 2.0:.1f}x"
    # A HIGHER oob multiplier wins over a lower camp one.
    assert module.hotPotatoSetOption("oob_burn_multiplier", 5.0) is True
    assert module.hotPotatoSetOption("camp_burn_multiplier", 2.0) is True
    assert 9.0 < _fuse_drop(state, module) < 11.0, "max() did not take the larger"


def test_only_the_carrier_is_penalised(rig):
    """It targets the CARRIER, which is exactly the exploit: a non-carrier
    outside the ring already cannot receive (v2.6) or score (v2.8), so only
    a carrier can win by orbiting. A bystander outside changes nothing."""

    state, module = _oob_rig(rig)
    state.moveVehicle(2, 12.0, 0.0, 0.0)  # carrier inside
    state.moveVehicle(3, 400.0, 0.0, 0.0)  # everyone else far outside
    assert 1.7 < _fuse_drop(state, module) < 2.3, (
        "a non-carrier outside the ring burned the shared fuse"
    )
    assert module.hotPotatoGetStats().oob is False


def test_the_out_of_bounds_state_is_legible(rig):
    """The v2.6 ledger declined this mechanism as "invisible punishment,
    illegible in play". That objection is answered, not ignored: a flag in
    BOTH stats channels and one message on each transition."""

    state, module = _oob_rig(rig)
    state.moveVehicle(2, 12.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=3)
    assert module.hotPotatoGetStats().oob is False
    assert module.getSystemState(PROP_ID).behavior_stats.oob is False
    state.clear()
    state.moveVehicle(2, 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=5)
    assert module.hotPotatoGetStats().oob is True, "the HUD flag never lit"
    assert module.getSystemState(PROP_ID).behavior_stats.oob is True
    warned = [m for m in state.messages.values() if "OUT OF BOUNDS" in m]
    assert len(warned) == 1, f"the exit was announced {len(warned)} times"
    # Held outside: the message does NOT repeat every frame.
    tick(state, module, seconds=0.2, steps=10)
    assert len([m for m in state.messages.values() if "OUT OF BOUNDS" in m]) == 1
    state.clear()
    state.moveVehicle(2, 12.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=5)
    assert module.hotPotatoGetStats().oob is False
    assert any("Back in the arena" in m for m in state.messages.values()), (
        "the return was never announced"
    )


def test_the_orbiting_carrier_detonates_itself(rig):
    """The endgame this exists to close: a carrier that drives out and
    circles is not farming a stalemate - its own fuse ends the round."""

    state, module = _oob_rig(rig, fuse=12)
    state.moveVehicle(2, 12.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=5)
    state.moveVehicle(2, 60.0, 0.0, 0.0)  # out over the crest, orbiting
    run_until(
        state,
        module,
        lambda: module.getSystemState(PROP_ID).behavior_phase != "live",
        limit_seconds=12.0,
    )
    assert _remaining(module) <= 0.1


def test_the_magnet_will_not_roll_a_car_in_a_sustained_orbit(rig):
    """G3's adversarial orbit rolled 4 of 6 excursions (up-vector z
    0.03-0.32) at BOTH dials. The well is a body force through the CG; when
    the tires GRIP it instead of sliding, pull x CG height against weight x
    half-track is a rollover couple. A car driving TANGENTIALLY takes the
    pull fully across its travel, so the well's share of the tipping budget
    is capped - while a car pulled along its own direction of travel (the
    braked hulk, the crest ram) is untouched."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    # Radial: the pull is straight along the car's travel - full strength.
    state.clear()
    state.moveVehicle(3, 60.0, 0.0, 0.0)
    state.setVelocity(3, 25.0, 0.0, 0.0)  # driving straight out
    tick(state, module, seconds=0.2, steps=10)
    _radial_lift, radial_haul = _well_components(state, 3, 60.0)
    # Tangential at the same speed and range: a sustained orbit.
    state.clear()
    state.setVelocity(3, 0.0, 25.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    orbit_lift, orbit_haul = _well_components(state, 3, 60.0)
    assert orbit_haul < radial_haul * 0.85, (
        f"the orbit pull was not capped ({orbit_haul:.2f} vs {radial_haul:.2f} g)"
    )
    # The well's own lateral demand must sit inside the tipping budget.
    budget = 1.2 * max(0.05, 1.0 - orbit_lift) * 0.6
    assert orbit_haul <= budget + 0.02, (
        f"lateral pull {orbit_haul:.2f} g over the tip budget {budget:.2f} g"
    )
    # Fail-open: the car is still being hauled, just not tipped.
    assert orbit_haul > 0.25, "the cap stopped the haul instead of taming it"


def _haul_on_grade(rig, grade, speed=25.0, distance=40.0, dial=1.2):
    """(lift g, haul g, well z) for a car being hauled across a fall line.

    The stub ground is a plane tilted `grade` along +x through the origin,
    so the car is parked ON it and driven ACROSS it (+y) - the traverse
    that G9 measured rolling on the glacis.
    """

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    assert module.hotPotatoSetOption("arena_magnet_g", dial) is True
    state.groundGrade = grade
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, grade * 12.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.moveVehicle(3, distance, 0.0, grade * distance)
    state.setVelocity(3, 0.0, speed, 0.0)  # across the fall line
    tick(state, module, seconds=0.2, steps=10)
    lift, haul = _well_components(state, 3, distance)
    return lift, haul, _well_heights(state, 3)[-1]


def test_the_tip_limit_tightens_as_the_cross_slope_rises(rig):
    """v2.11 (G9): the flat solve was proven correct live - an orbit at
    29.9 m/s held up-vector 0.88 and never rolled - but 9 of 10 remaining
    rolls were on the 30 % glacis cross-slope at 6.3-20.7 m/s. On a slope
    the normal load is only cos(theta) of the weight AND gravity's own
    in-plane sin(theta) is already spending the tipping budget, so a limit
    that is right on the apron is far too generous on the fall line."""

    flat_lift, flat_haul, _z = _haul_on_grade(rig, 0.0)
    # The apron number must not move by a hair (v2.10's measured 0.620 g).
    assert abs(flat_haul - 0.620) < 0.005, f"flat haul moved to {flat_haul:.3f} g"


@pytest.mark.parametrize("grade,expected_haul", [(0.0, 0.620), (0.15, 0.522), (0.30, 0.402)])
def test_the_slope_solve_matches_its_arithmetic(rig, grade, expected_haul):
    """0 %, 15 % and 30 % cross-slope: allowance = RATIO*MARGIN*cos(theta)
    - sin(theta), and the hoist fades out with the grade so the well
    presses instead of lifting."""

    lift, haul, well_z = _haul_on_grade(rig, grade)
    assert abs(haul - expected_haul) < 0.01, (
        f"grade {grade:.0%}: haul {haul:.3f} g, expected {expected_haul:.3f}"
    )
    if grade >= 0.30:
        assert lift < 0.01, f"the well still lifted {lift:.3f} g on a 30 % slope"
        assert abs(well_z) < 0.2, "the well should be level with the pad"
    else:
        assert lift >= 0.0
    # Fail-open: a slope never stops the haul, it only tames it.
    assert haul > 0.25, f"grade {grade:.0%} left only {haul:.3f} g of haul"


def test_a_slow_sideways_drag_is_capped_on_a_slope_but_not_on_the_flat(rig):
    """The speed gate: no orbit is sustainable below 8 m/s, but a TRIP
    needs only ~6 m/s of sideways drag across a fall line - which is what
    G9 measured (6.3-20.7 m/s). On a slope the cap binds from 3 m/s; on
    the flat the shipped 8 m/s gate is untouched."""

    _flat_lift, flat_haul, _z = _haul_on_grade(rig, 0.0, speed=6.3)
    assert flat_haul > 1.0, (
        f"the flat low-speed haul was capped ({flat_haul:.3f} g) - the apron moved"
    )
    _slope_lift, slope_haul, _sz = _haul_on_grade(rig, 0.30, speed=6.3)
    assert slope_haul < flat_haul * 0.5, (
        f"a 6.3 m/s traverse of a 30 % slope was not capped ({slope_haul:.3f} g)"
    )
    assert slope_haul > 0.25, "the slope cap must not abandon the car"


def test_the_ground_probe_fails_open_to_flat(rig):
    """No castRayStatic hit - a car in the air, off the mesh, or a level
    whose statics the ray cannot see - means the shipped FLAT behaviour,
    never a weaker haul on a guess."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.groundGrade = 0.30
    state.groundSolid = False  # every probe misses
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    state.setVelocity(3, 0.0, 25.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    _lift, haul = _well_components(state, 3, 40.0)
    assert abs(haul - 0.620) < 0.005, f"a missed ground probe changed the flat haul to {haul:.3f} g"


def test_the_ground_probe_is_cached_and_cheap(rig):
    """Three rays per hauled car, cached for half a second: the probe runs
    only for cars the magnet is actually hauling, so it is a handful of
    rays a second, not a per-frame cost."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.groundGrade = 0.30
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 3.6)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    # Nobody is outside the ring yet: not one ray should have been cast.
    assert int(state.groundRays) == 0, (
        f"the probe ran for a car that is not being hauled ({state.groundRays})"
    )
    state.moveVehicle(3, 40.0, 0.0, 12.0)
    state.setVelocity(3, 0.0, 25.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)  # 2 s of hauling
    rays = int(state.groundRays)
    # 2 s at a 0.5 s cache TTL is at most 5 refreshes x 3 rays for one car.
    assert 3 <= rays <= 15, f"{rays} rays for 2 s of hauling one car"


def test_the_tip_cap_leaves_the_slow_haul_alone(rig):
    """The braked hulk (v2.7.1) and every slow recovery keep the full
    dialled pull: below MAGNET_TIP_SPEED no orbit can be sustained, and a
    stationary car cannot be rolled by a force its tires will slide under."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 12.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    state.clear()
    state.moveVehicle(3, 40.0, 0.0, 0.0)
    state.setVelocity(3, 0.0, 3.0, 0.0)  # crawling sideways: below the gate
    tick(state, module, seconds=0.2, steps=10)
    expected = _magnet_mass(1.2, 40.0, speed=3.0)
    assert abs(_well_masses(state, 3)[-1] - expected) / expected < 0.05, (
        "the tip cap weakened a slow haul"
    )


def test_fireworks_draw_stars_against_the_sky(rig):
    """v2.7 ("I don't think the fireworks are working"): the v2.4 show was
    point lights ALONE, and a point light with no surface near it renders
    nothing at all against open sky. The show now draws its rising shell,
    its glyph stars and its finale rain with the debug drawer — and the
    HUD app's test button fires a full pass through the same hook this
    gate uses."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoTestFireworks("EV") is True
    tick(state, module, seconds=0.1, steps=3)
    assert module.hotPotatoGetStats().fw_stage == "launch", "the test hook never started the show"
    assert len(state.stars) > 0, "the rising shell drew nothing"
    run_until(
        state,
        module,
        lambda: module.hotPotatoGetStats().fw_stage == "burst",
        limit_seconds=3.0,
        seconds=0.1,
    )
    before = len(state.stars)
    tick(state, module, seconds=0.1)
    # E lights 18 glyph pixels; each star is a glow shell plus a white-hot
    # core, so one burst frame is at least 30 spheres.
    assert len(state.stars) - before >= 30, "the burst drew too few stars to read as a letter"


def test_fireworks_stay_dark_when_disabled(rig):
    """fireworks_enabled=false rules the drawn show and the test button."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("fireworks_enabled", False) is True
    assert module.hotPotatoTestFireworks("EV") is False
    tick(state, module, seconds=0.2, steps=10)
    assert len(state.stars) == 0, "a disabled show still drew stars"


def test_mash_steam_rides_the_landed_chunks(rig):
    """v2.7 ("very light steam to come off the chunks"): each dollop's wisp
    switches on when its chunk lands, rides the crown while it sits
    cooking, obeys the smoke toggle, and dies when the chunk melts."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 8)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    _detonate_carrier(state, module, spec)

    def _steaming():
        return [
            i
            for i in range(1, 7)
            if state.scene[f"ericrolph_hot_potato_p1_fx_mash_steam_{i}"].active
        ]

    run_until(state, module, lambda: len(_steaming()) > 0, limit_seconds=10.0)
    lit = _steaming()[0]
    poses = _poses_of(state, f"fx_mash_steam_{lit}")
    # Near grade, not the authored z -30 park: the harness ground line can
    # sit a little below zero (spawnMash takes boomFrom.z - 2.0 on the
    # fizzle path), so "above the plaza's underside" is the honest claim.
    assert poses and poses[-1][2] > -3.0, (
        "the steam wisp never rose from its under-plaza park to the chunk"
    )
    # The smoke toggle rules the wisps mid-steam…
    assert module.hotPotatoSetOption("smoke_enabled", False) is True
    tick(state, module, seconds=0.2, steps=3)
    assert not _steaming(), "smoke_enabled=false left a chunk steaming"
    # …and back on, they relight until the melt takes them all.
    assert module.hotPotatoSetOption("smoke_enabled", True) is True
    tick(state, module, seconds=0.2, steps=3)
    assert _steaming(), "the wisps never relit with the toggle"
    run_until(state, module, lambda: not _steaming(), limit_seconds=30.0)


# --------------------------------------------------------------------------
# v2.7.1 (2026-09-01): the live-play fix round — the pillar dodge, the
# dodge win, and the tractor-beam magnet (whose law is pinned above).


def test_ai_dodges_the_arch_feet(rig):
    """v2.7.1 ("AI vehicles seem to crash into the arch often"): every
    steering mode drives a straight line, and a line that passes within the
    keep-out of an arch foot gets overridden by a one-shot side-step
    slotTrafficTarget. When the heading clears, the game role is re-armed."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", -45.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)  # conscription: 3 flees 2
    assert any("'flee'" in c for c in _commands_to(state, 3, "ai.setMode")), (
        "the fleeing role never armed - the dodge under test rides on it"
    )
    # Aim car 3 dead at the west arch foot (-22.801, 0): the reflex must
    # side-step it well clear of the keep-out instead of riding through.
    state.clear()
    state.setVelocity(3, 20.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=4)
    dodges = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert dodges, "no dodge was steered for a car heading into an arch foot"
    coords = re.search(r"setSlotTrafficTarget\((-?[0-9.]+), (-?[0-9.]+),", dodges[-1])
    assert coords, f"unparseable dodge command: {dodges[-1]}"
    assert abs(float(coords.group(2))) >= 8.0, (
        "the dodge point must step ASIDE from the foot line, not along it"
    )
    # PAST the foot (v2.10: the dodge commits, so it lets go when the car
    # has passed the post — not the instant the heading stops clipping it):
    # the role sweep re-sends the game role the slot-traffic override ate.
    state.clear()
    state.moveVehicle(3, 0.0, 30.0, 0.0)
    state.setVelocity(3, 0.0, 20.0, 0.0)
    tick(state, module, seconds=0.2, steps=8)
    assert any("'flee'" in c for c in _commands_to(state, 3, "ai.setMode")), (
        "the game role never re-armed after the dodge released"
    )


def test_boom_crowns_the_last_passer_with_fireworks(rig):
    """v2.7.1 ("I didn't see the confetti or fireworks after not having the
    potato"): before this, a boom with two or more survivors celebrated
    NOBODY - celebrate() was only reachable via last-car-standing and the
    champion crowning, so ordinary classic rounds ended with a shrug. The
    last passer is the round's natural winner and takes the confetti, the
    fireworks and a mark in the champion ledger."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 8)
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 10.0) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    state.addVehicle(4, "etk800", 400.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.1, steps=30)
    # The pass: 3 slides into the bubble, takes the potato, and 2 becomes
    # the dodger-in-waiting.
    carrier = state.vehicles[_carrier_of(module)].pos
    state.moveVehicle(3, carrier.x + 8.0, carrier.y, carrier.z)
    tick(state, module, steps=2)
    assert _carrier_of(module) == 3
    state.moveVehicle(3, 150.0, 0.0, 0.0)  # separate so nothing passes back
    _detonate_carrier(state, module, spec)
    run_until(
        state,
        module,
        lambda: any("PASSED IT JUST IN TIME" in m for m in state.messages.values()),
        limit_seconds=25.0,
    )
    # The winner's honours: fireworks for the dodger, a win in the ledger.
    tick(state, module, seconds=0.1, steps=60)
    assert _poses_of(state, "fw_px_1"), "the dodge win never lit the winner's fireworks"


def test_hold_modes_do_not_crown_the_passer(rig):
    """In hoarder and protect the carrier WANTS the potato: the boom is the
    carrier's tragedy, not the passer's triumph, so the dodge win stays out
    of the hold modes."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 8)
    assert module.hotPotatoSetOption("game_mode", "hoarder") is True
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 10.0) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    state.addVehicle(4, "etk800", 400.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.1, steps=30)
    carrier = state.vehicles[_carrier_of(module)].pos
    state.moveVehicle(3, carrier.x + 8.0, carrier.y, carrier.z)
    tick(state, module, steps=2)
    assert _carrier_of(module) == 3
    state.moveVehicle(3, 150.0, 0.0, 0.0)
    _detonate_carrier(state, module, spec)
    run_until(
        state,
        module,
        lambda: any("returns to the arch" in m for m in state.messages.values()),
        limit_seconds=25.0,
    )
    assert not any("PASSED IT JUST IN TIME" in m for m in state.messages.values()), (
        "a hold-mode boom crowned the passer"
    )


# --------------------------------------------------------------------------
# v2.8 (2026-09-01): the arena hooks — the scenario's obstacle census joins
# the dodge sweep, and hold-mode scoring obeys the ring.

# The Gateway Skillet's 16 keep-out posts (arena design v3 §6.4a), re-centred
# on the harness pad at the origin: 4 mashers (r 48), 4 grinders (r 26), the
# 2 gate towers (r 58), 4 handle corners, 2 spout jamb noses.
ARENA_POSTS = [
    {"x": 33.9, "y": 33.9, "r": 6.5},
    {"x": 33.9, "y": -33.9, "r": 6.5},
    {"x": -33.9, "y": -33.9, "r": 6.5},
    {"x": -33.9, "y": 33.9, "r": 6.5},
    {"x": 18.4, "y": 18.4, "r": 6.5},
    {"x": 18.4, "y": -18.4, "r": 6.5},
    {"x": -18.4, "y": -18.4, "r": 6.5},
    {"x": -18.4, "y": 18.4, "r": 6.5},
    {"x": -6.1, "y": 57.7, "r": 6.5},
    {"x": 6.1, "y": 57.7, "r": 6.5},
    {"x": -7.0, "y": -30.0, "r": 8.0},
    {"x": 7.0, "y": -30.0, "r": 8.0},
    {"x": -7.0, "y": -88.0, "r": 8.0},
    {"x": 7.0, "y": -88.0, "r": 8.0},
    {"x": 65.8, "y": 38.0, "r": 6.5},
    {"x": -65.8, "y": -38.0, "r": 6.5},
]


def _lua_points(lua, points):
    """A Lua array of {x, y, r} tables — the hook's wire shape. Non-dict
    entries pass through as they are, so a gate can feed the hook junk."""

    return lua.table_from(
        [lua.table_from(point) if isinstance(point, dict) else point for point in points]
    )


def _slot_target(command):
    found = re.search(r"setSlotTrafficTarget\((-?[0-9.]+), (-?[0-9.]+),", command)
    assert found, f"unparseable dodge command: {command}"
    return float(found.group(1)), float(found.group(2))


def _points_of(module):
    """The leading scoreboard entry's points, 0 when nobody has scored."""

    scores = list((module.hotPotatoGetStats().scores or {}).values())
    return int(scores[0].points) if scores else 0


def test_registered_obstacles_join_the_dodge_sweep(rig):
    """v2.8 (arena design §6.4a): a scenario registers the world-space
    keep-out posts of what it built, and the dodge reflex rays against them
    exactly as it does the arch feet — side-step, then re-arm the role once
    the heading clears. The nearest threatening post along the ray owns the
    dodge, and the arch feet stay in the sweep alongside the registered set."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, ARENA_POSTS)) is True
    assert int(module.hotPotatoGetObstacles().count) == 16
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 33.9, 70.0, 0.0)  # inside the ring, north of masher_ne
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)  # conscription: 3 flees 2
    assert any("'flee'" in c for c in _commands_to(state, 3, "ai.setMode")), (
        "the fleeing role never armed - the dodge under test rides on it"
    )
    # Southbound, dead at masher_ne (33.9, 33.9), 36 m ahead: a registered
    # post must steer the same side-step an arch foot would.
    state.clear()
    state.setVelocity(3, 0.0, -20.0, 0.0)
    tick(state, module, seconds=0.2, steps=4)
    dodges = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert dodges, "no dodge was steered for a car heading into a registered post"
    tx, _ty = _slot_target(dodges[-1])
    assert abs(tx - 33.9) >= 8.0, "the dodge point must step ASIDE from the post line, not along it"
    # PAST the post (v2.10 commits to the manoeuvre, so the release is
    # positional): the dodge lets go and the role sweep re-sends the game
    # role the slot-traffic override ate.
    state.clear()
    state.moveVehicle(3, 33.9, 20.0, 0.0)
    state.setVelocity(3, 20.0, 0.0, 0.0)  # past the masher, nothing ahead
    tick(state, module, seconds=0.2, steps=8)
    assert any("'flee'" in c for c in _commands_to(state, 3, "ai.setMode")), (
        "the game role never re-armed after the dodge released"
    )
    # Nearest-along: a decoy post 20 m down the same ray must own the dodge.
    # v2.10 aims ABEAM THE POST (post y 50, 6 m short of it on this heading
    # => y 44), not off the car's own nose; the far masher would give 27.9.
    decoy = ARENA_POSTS + [{"x": 33.9, "y": 50.0, "r": 6.5}]
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, decoy)) is True
    state.clear()
    state.moveVehicle(3, 33.9, 70.0, 0.0)  # back north of both posts
    state.setVelocity(3, 0.0, -20.0, 0.0)
    tick(state, module, seconds=0.2, steps=4)
    dodges = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert dodges, "no dodge was steered against the decoy post"
    _tx, ty = _slot_target(dodges[-1])
    assert abs(ty - 44.0) <= 0.2, (
        f"the dodge must key on the NEAREST post along the ray, aimed y={ty}"
    )
    # The arch feet are still in the sweep with a registered set present.
    state.clear()
    state.moveVehicle(3, -45.0, 0.0, 0.0)
    state.setVelocity(3, 20.0, 0.0, 0.0)  # east, dead at the west foot
    tick(state, module, seconds=0.2, steps=4)
    dodges = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert dodges, "the arch feet dropped out of the sweep once posts were registered"
    _tx, ty = _slot_target(dodges[-1])
    assert abs(ty) >= 8.0, "the foot dodge lost its side-step"


def test_obstacle_registration_validates_caps_and_clears(rig):
    """v2.8: malformed input is refused whole (false, one warning, no throw)
    and leaves the registered set untouched - a bad entry, a table that is
    not a dense array (a lone post without its wrapping braces, a holed
    list, a keyed table: critic round 1 found these registering as a silent
    CLEAR with a true return), or more than 128 entries (v2.16, ask #8: the
    cap went 64 -> 128 so a level can register its 67 outside solids beside
    the arena's 46 in one replacing call); a call replaces the set; only nil
    or {} clears it; the report is a copy; the set survives a prop reset and
    dies at teardown."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, ARENA_POSTS)) is True
    assert int(module.hotPotatoGetObstacles().count) == 16

    assert module.hotPotatoRegisterObstacles("pillars") is False
    assert int(module.hotPotatoGetObstacles().count) == 16
    malformed = [
        _lua_points(lua, [{"x": 1.0, "y": 2.0}]),  # r missing
        _lua_points(lua, [{"x": 1.0, "y": 2.0, "r": 0.2}]),  # r under the 0.5 m floor
        _lua_points(lua, [{"x": 1.0, "y": 2.0, "r": 31.0}]),  # r over the 30 m ceiling
        _lua_points(lua, [{"x": "1", "y": 2.0, "r": 6.5}]),  # x not a number
        _lua_points(
            lua,
            [
                {"x": 1.0, "y": 2.0, "r": 6.5},
                {"x": 3.0, "y": float("nan"), "r": 6.5},
            ],
        ),
        _lua_points(lua, [{"x": 1.0, "y": 2.0, "r": 6.5}, 7.0]),  # a non-table entry
        # Not a dense array: ipairs walks none of these as entries.
        lua.eval("{x = 1.0, y = 2.0, r = 6.5}"),  # one post, no wrapping braces
        lua.eval("{[1] = {x = 1, y = 2, r = 6.5}, [3] = {x = 3, y = 4, r = 6.5}}"),
        lua.eval("{{x = 1, y = 2, r = 6.5}, count = 5}"),  # array plus a string key
        # Over the cap: a 129th entry refuses the call, it is not truncated.
        _lua_points(lua, [{"x": float(i), "y": 0.0, "r": 6.5} for i in range(129)]),
        # A malformed entry INSIDE the cap (127 good + 1 junk = 128 entries)
        # must not hide behind the good ones: the whole call is refused and
        # the prior set kept. (A junk 130th behind 129 good ones would be
        # moot - the cap trips at entry 129 before the junk is examined.)
        _lua_points(
            lua, [{"x": float(i), "y": 0.0, "r": 6.5} for i in range(127)] + [{"x": "junk"}]
        ),
    ]
    for index, points in enumerate(malformed):
        assert module.hotPotatoRegisterObstacles(points) is False, f"case {index}"
        assert int(module.hotPotatoGetObstacles().count) == 16, (
            f"a rejected call disturbed the registered set: case {index}"
        )
    warnings = [
        e
        for e in state.events.values()
        if e.level == "W" and "hotPotatoRegisterObstacles" in str(e.message)
    ]
    assert len(warnings) == 1 + len(malformed), "each rejection logs exactly once"
    messages = [str(e.message) for e in warnings]
    assert sum("more than 128 entries" in m for m in messages) == 1, (
        "the 129th entry must trip the cap (once), not be truncated"
    )
    assert sum("rejected entry 128 " in m for m in messages) == 1, (
        "the junk entry at 128 must be examined and refused inside the cap"
    )
    assert not any(e.level == "E" for e in state.events.values())

    # Exactly the cap (128) is fine, and the 113 the level needs sits inside it.
    at_cap = [{"x": float(i), "y": 0.0, "r": 6.5} for i in range(128)]
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, at_cap)) is True
    report = module.hotPotatoGetObstacles()
    assert int(report.count) == 128
    assert float(report.entries[128].x) == 127.0
    assert report.entries[129] is None
    # A 3-D point is a 2-D post: z is ignored, not refused.
    assert (
        module.hotPotatoRegisterObstacles(
            _lua_points(lua, [{"x": 1.0, "y": 2.0, "z": 100.0, "r": 6.5}])
        )
        is True
    )
    assert int(module.hotPotatoGetObstacles().count) == 1

    # A call replaces the whole set, and the report is a copy.
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, ARENA_POSTS[:3])) is True
    report = module.hotPotatoGetObstacles()
    assert int(report.count) == 3
    report.entries[1].x = 999.0
    assert float(module.hotPotatoGetObstacles().entries[1].x) == ARENA_POSTS[0]["x"]

    # {} and nil both clear.
    assert module.hotPotatoRegisterObstacles(lua.table_from([])) is True
    assert int(module.hotPotatoGetObstacles().count) == 0
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, ARENA_POSTS)) is True
    assert module.hotPotatoRegisterObstacles(None) is True
    assert int(module.hotPotatoGetObstacles().count) == 0

    # Survives a prop reset (the scenario is still standing), dies with the
    # prop at teardown (the map may not be).
    assert module.hotPotatoRegisterObstacles(_lua_points(lua, ARENA_POSTS)) is True
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    tick(state, module)
    module.onVehicleResetted(PROP_ID)
    tick(state, module)
    assert int(module.hotPotatoGetObstacles().count) == 16, (
        "a prop reset forgot the scenario's posts"
    )
    module.onClientEndMission("/levels/gridmap_v2/main")
    assert int(module.hotPotatoGetObstacles().count) == 0, "the obstacle census outlived the prop"


def test_the_dodge_keys_on_the_near_foot_along_the_span(rig):
    """v2.8 fixes a v2.7.1 dodge bug the shipped gate could not see: with
    BOTH arch feet on the ray - a car westbound along the span from beyond
    the east foot, exactly a containment return toward pad_center - the
    first-found order picked the WEST foot 53 m out and aimed the car at
    (-30.8, -9.5), a line straight through the east foot 7 m ahead.
    Nearest-along aims abeam the east foot instead (x 16.8 under v2.10's
    aim-from-the-post law; the far foot would be -28.8). Geometry from the
    critic's probe B."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert module.hotPotatoSetOption("ai_speed_kmh", 100) is True
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 30.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=6)
    assert any("'flee'" in c for c in _commands_to(state, 3, "ai.setMode")), (
        "the fleeing role never armed"
    )
    state.clear()
    state.moveVehicle(3, 30.0, 0.0, 0.0)
    state.setVelocity(3, -25.0, 0.0, 0.0)  # lookahead 55 m: both feet on the ray
    tick(state, module, seconds=0.2, steps=4)
    dodges = _commands_to(state, 3, "ai.setSlotTrafficTarget")
    assert dodges, "no dodge was steered along the span"
    tx, ty = _slot_target(dodges[-1])
    assert tx > 0, f"the dodge aimed past the near foot at the far one (x={tx})"
    assert abs(tx - 16.8) <= 0.2, f"expected the east foot's abeam point, got x={tx}"
    assert abs(ty) >= 8.0, "the dodge must step aside from the span line"


@pytest.mark.parametrize("mode", ["hoarder", "protect"])
def test_hold_mode_scoring_stops_at_the_ring(rig, mode):
    """v2.8 (arena design §6.4b, erratum #4): the v2.6 law - a car outside
    the circle is not part of the game - was enforced on the receiving side
    only, so an out-of-ring carrier scored a point a second uncontested. Now
    accrual and the crown share the transfer sweep's insideArena predicate:
    inside scores as before; outside freezes the hoard and cannot crown; back
    inside the race resumes."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 120)
    assert module.hotPotatoSetOption("game_mode", mode) is True
    assert module.hotPotatoSetOption("hoard_target_points", 10) is True
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 12.0, 0.0, 0.0)  # inside the 20 m ring
    tick(state, module, seconds=0.2, steps=10)  # 2 held seconds
    inside = _points_of(module)
    assert inside >= 1, f"holding inside the ring earned nothing in {mode}"

    # Out the spout: 40 m from the pad, 12 s of holding - more than the
    # 10-point target - must earn nothing and crown nobody.
    state.moveVehicle(2, 40.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=60)
    assert _points_of(module) == inside, f"an out-of-ring carrier scored in {mode}"
    assert not any("CHAMPION" in m for m in state.messages.values()), (
        f"an out-of-ring carrier was crowned in {mode}"
    )
    assert _carrier_of(module) == 2
    assert module.getSystemState(PROP_ID).behavior_phase == "live"

    # Back inside: the race resumes from where it froze and crowns.
    state.moveVehicle(2, 12.0, 0.0, 0.0)
    tick(state, module, seconds=0.2, steps=10)
    assert _points_of(module) > inside, f"scoring never resumed inside the ring in {mode}"
    run_until(
        state,
        module,
        lambda: any("CHAMPION" in m for m in state.messages.values()),
        limit_seconds=15.0,
    )


def test_arena_off_scores_the_hold_modes_anywhere(rig):
    """With arena_enabled off insideArena is always true, so the scoring
    gate is a no-op: the same faraway carrier hoards exactly as before."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("game_mode", "hoarder") is True
    assert module.hotPotatoSetOption("hoard_target_points", 10) is True
    assert module.hotPotatoSetOption("arena_enabled", False) is True
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 40.0, 0.0, 0.0)  # would be OUT of a 20 m ring
    tick(state, module, seconds=0.2, steps=10)
    assert _points_of(module) >= 1, "arena off must leave hold-mode scoring untouched"
    run_until(
        state,
        module,
        lambda: any("CHAMPION" in m for m in state.messages.values()),
        limit_seconds=15.0,
    )


def test_classic_ignores_the_scoring_gate(rig):
    """Classic has no hoard to gate: an out-of-ring carrier keeps the potato,
    the fuse keeps burning, and no scoreboard appears."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("arena_radius_m", 20) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.moveVehicle(2, 40.0, 0.0, 0.0)
    before = _remaining(module)
    tick(state, module, seconds=0.2, steps=10)
    assert _carrier_of(module) == 2
    assert _remaining(module) < before - 1.5, "the classic fuse stopped outside the ring"
    assert _points_of(module) == 0
    assert len(list(module.hotPotatoGetStats().scores or [])) == 0


# --------------------------------------------------------------------------
# v2.8 ask #3 (2026-09-01): the subject filter. The scenario's live smoke
# spawned 12 cardboard boxes and 4 barrels as breakable scenery and the
# runtime reported field = 22.


def test_prop_vehicles_are_scenery_not_subjects(rig):
    """A Prop-type vehicle (info.json Type = "Prop", the stock game's own
    classification) never receives the potato, is never conscripted, is
    never magnet-held, and does not count in the field or the last-car-
    standing verdict. The real car beside it is treated exactly as before,
    and the stats say how many props were refused."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("ai_enabled", True) is True
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 30) is True
    state.playerId = 2
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "cardboard_box", 10.0, 0.0, 0.0, 0.4, 0.4, 0.4)  # in pass range
    state.addVehicle(4, "barrels", 40.0, 0.0, 0.0, 0.5, 0.5, 0.6)  # inside the ring
    state.addVehicle(5, "etk800", 40.0, 5.0, 0.0)  # a real car beside the barrels
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=10)
    assert _carrier_of(module) == 2, "a cardboard box received the potato"
    stats = module.getSystemState(PROP_ID).behavior_stats
    assert int(stats.field) == 2, f"props counted in the field: {int(stats.field)}"
    assert int(stats.props_excluded) == 2
    assert int(module.hotPotatoGetStats().props_excluded) == 2
    assert int(module.hotPotatoGetStats().field) == 2
    # Conscription: the car got a role, the scenery did not.
    assert _commands_to(state, 5, "ai.setMode"), "the real car was never conscripted"
    assert not _commands_to(state, 4, "ai."), "the AI tried to drive a barrel"
    assert not _commands_to(state, 3, "ai."), "the AI tried to drive a box"
    # Containment and the magnet: both stray out to 200 m; only the car is
    # steered home and tethered.
    state.clear()
    state.moveVehicle(4, 200.0, 0.0, 0.0)
    state.moveVehicle(5, 200.0, 5.0, 0.0)
    tick(state, module, seconds=0.2, steps=6)
    assert _commands_to(state, 5, "setPlanets"), "the strayed car was not tethered"
    assert _commands_to(state, 5, "setSlotTrafficTarget"), "the strayed car was not herded"
    assert not _commands_to(state, 4, "setPlanets"), "the magnet grabbed a barrel"
    assert not _commands_to(state, 4, "ai."), "containment tried to steer a barrel"
    # Last car standing: the other car leaves. Two props remain, and they
    # are not cars — the carrier wins instead of waiting on the fuse.
    state.removeVehicle(5)
    run_until(
        state,
        module,
        lambda: any("LAST CAR STANDING" in m for m in state.messages.values()),
        limit_seconds=5.0,
    )


def test_unknown_model_types_stay_eligible(rig):
    """The filter fails OPEN: a model whose Type is "Unknown", and a frame
    where core_vehicles itself is missing, both leave a vehicle eligible -
    a real car must never be failed closed, and a box slipping through on a
    bad frame is the lesser evil."""

    lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 30) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "unknown_kit", 10.0, 0.0, 0.0)  # Type = "Unknown"
    tick(state, module)
    # Eligible from the first frame: the pass can land inside start_round's
    # own settle, so only the outcome is asserted.
    start_round(state, module, 2)
    run_until(state, module, lambda: _carrier_of(module) == 3, limit_seconds=5.0)
    assert int(module.hotPotatoGetStats().props_excluded) == 0
    # The GE-side lookup vanishes: a NEW box is a subject (open), a new car
    # is a legal receiver, and nothing is counted as excluded.
    lua.execute("core_vehicles = nil")
    state.addVehicle(4, "cardboard_box", 200.0, 0.0, 0.0, 0.4, 0.4, 0.4)
    state.addVehicle(5, "etk800", 10.0, 8.0, 0.0)
    run_until(state, module, lambda: _carrier_of(module) == 5, limit_seconds=8.0)
    assert int(module.hotPotatoGetStats().props_excluded) == 0
    assert int(module.getSystemState(PROP_ID).behavior_stats.field) >= 3


def test_the_shockwave_still_shoves_props(rig):
    """Props are out of the game, not out of the physics: the detonation
    shockwave asks for the whole field and shoves a box inside the blast
    radius exactly like a bystander car."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    for key, value in (
        ("fuse_min_seconds", 5.0),
        ("fuse_max_seconds", 6.0),
        ("fuse_sigma_seconds", 0.0),
    ):
        assert module.hotPotatoSetOption(key, value) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "cardboard_box", 10.0, 0.0, 0.0, 0.4, 0.4, 0.4)  # inside 22 m
    state.addVehicle(4, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    state.clear()
    run_until(
        state,
        module,
        lambda: any(int(v.id) == 3 for v in state.velocities.values()),
        limit_seconds=12.0,
    )
    assert _carrier_of(module) != 3
    assert int(module.hotPotatoGetStats().props_excluded) == 1
    shove = [v for v in state.velocities.values() if int(v.id) == 3][0]
    assert float(shove.x) > 1.0 and float(shove.z) > 0.1, "the box was not shoved outward"


def test_a_replaced_vehicle_is_reclassified_in_place(rig):
    """Critic round 3, HIGH: the engine REUSES the vehicle object on replace
    (core/vehicles.lua L1716-1765: vehsToReuse, replaceOtherVehicle on the
    same object, then onVehicleReplaced - a hook the framework never
    subscribes), so the id outlives the model. An id-only cache failed the
    replaced car closed for the whole session. The verdict is now keyed by
    (id, model) and the model re-read every pass: box -> car and car -> box
    in place, and a destroyed box whose id comes back as a car."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 30) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "cardboard_box", 10.0, 0.0, 0.0, 0.4, 0.4, 0.4)
    state.addVehicle(5, "etk800", 40.0, 0.0, 0.0)  # a car, outside pass range
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=10)
    assert _carrier_of(module) == 2
    assert int(module.hotPotatoGetStats().props_excluded) == 1

    # Tab into the box, pick a car from the selector: same id, new model,
    # and no hook the framework sees. The car must become a subject at once.
    state.vehicles[3].model = "etk800"
    run_until(state, module, lambda: _carrier_of(module) == 3, limit_seconds=6.0)
    assert int(module.hotPotatoGetStats().props_excluded) == 0

    # The other way: a car replaced by a box is scenery from the next pass,
    # even parked inside the carrier's pass range.
    state.vehicles[5].model = "cardboard_box"
    state.moveVehicle(5, 10.0, 5.0, 0.0)
    tick(state, module, seconds=0.2, steps=15)
    assert _carrier_of(module) == 3, "a car-turned-box received the potato"
    assert int(module.hotPotatoGetStats().props_excluded) == 1

    # Destroy the box through the framework hook, then reuse its id for a
    # car: reclassified, receives.
    module.onVehicleDestroyed(5)
    state.removeVehicle(5)
    state.addVehicle(5, "etk800", 10.0, 5.0, 0.0)
    run_until(state, module, lambda: _carrier_of(module) == 5, limit_seconds=8.0)
    assert int(module.hotPotatoGetStats().props_excluded) == 0


def test_the_walking_player_stays_in_the_game(rig):
    """Stock `unicycle` (walking mode) ships Type = "Prop"; the game's own
    traffic code special-cases it to 'player' (traffic/vehicle.lua L31).
    Mirrored: a pedestrian is a subject, as before v2.8."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 30) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "unicycle", 10.0, 0.0, 0.0, 0.3, 0.3, 0.9)
    tick(state, module)
    start_round(state, module, 2)  # eligible at once: the pass may land inside
    run_until(state, module, lambda: _carrier_of(module) == 3, limit_seconds=5.0)
    assert int(module.hotPotatoGetStats().props_excluded) == 0
    assert int(module.getSystemState(PROP_ID).behavior_stats.field) == 2


def test_trailers_are_scenery_too(rig):
    """Type = "Trailer" (13 stock models) joins the deny set: a hitched
    trailer sits permanently in its tow car's pass range and can neither
    drive nor be conscripted. Fail-open posture unchanged."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    assert module.hotPotatoSetOption("transfer_mode", "radius") is True
    assert module.hotPotatoSetOption("radius_m", 30) is True
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "dryvan", 10.0, 0.0, 0.0, 1.2, 6.0, 1.8)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=15)
    assert _carrier_of(module) == 2, "a trailer received the potato"
    assert int(module.hotPotatoGetStats().props_excluded) == 1
    assert int(module.getSystemState(PROP_ID).behavior_stats.field) == 1


def test_a_carrier_that_becomes_scenery_hands_the_potato_home(rig):
    """Critic round 4, MEDIUM: the carrying player opens the selector and
    picks a box. The object still resolves, roster() drops it, the field
    reads 1 against a peak of 2 - and before this fix the BOX was declared
    LAST CAR STANDING, with fireworks and a round_won in the persistent
    ledger. Now it is the carrier-lost path: the potato flies home, nobody
    wins, the ledger is untouched, the other car is left alone."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 20)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=5)  # 1 s into a two-car round
    state.clear()
    state.vehicles[2].model = "cardboard_box"
    tick(state, module, seconds=0.2, steps=15)
    assert _carrier_of(module) is None, "a box kept the potato"
    assert module.getSystemState(PROP_ID).behavior_phase in ("return", "idle")
    assert int(module.hotPotatoGetStats().props_excluded) == 1
    assert not any("LAST CAR STANDING" in m for m in state.messages.values()), (
        "a cardboard box was crowned last car standing"
    )
    assert any("returning to the arch" in m for m in state.messages.values())
    assert not any("round_won" in str(e.message) for e in state.events.values()), (
        "a round win was written to the ledger for a box"
    )
    assert len(list(module.hotPotatoGetStats().wins or [])) == 0
    assert not _poses_of(state, "fw_px_1"), "fireworks lit for a box"


def test_a_carrier_that_changes_cars_keeps_the_potato(rig):
    """The mirror: a carrier replaced in place by another CAR model keeps
    the same id and stays the carrier - what a player changing cars
    mid-round expects."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    _shrink_fuse(module, 20)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    state.addVehicle(3, "etk800", 300.0, 0.0, 0.0)
    tick(state, module)
    assert start_round(state, module, 2) == 2
    tick(state, module, seconds=0.2, steps=5)
    state.vehicles[2].model = "pickup"
    tick(state, module, seconds=0.2, steps=15)
    assert _carrier_of(module) == 2, "changing cars lost the potato"
    assert module.getSystemState(PROP_ID).behavior_phase == "live"
    assert int(module.hotPotatoGetStats().props_excluded) == 0
