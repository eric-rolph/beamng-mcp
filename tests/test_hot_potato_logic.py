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
S.sounds = {}
Engine.Audio = {playOnce = function(_channel, event, opts)
  S.sounds[#S.sounds + 1] = {event = event, pitch = opts and opts.pitch or 1}
end}
-- No settings file in the harness: options fall back to the shipped table.
S.settings = nil
function jsonReadFile() return S.settings end
function jsonWriteFile(_path, payload) S.settings = payload return true end

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
    raise AssertionError(
        f"condition never held within {limit_seconds}s of simulated play"
    )


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


def test_registers_with_trigger_effects_and_the_potato(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    system = module.getSystemState(PROP_ID)
    assert system.registered is True
    assert system.part_count == 1
    assert system.trigger_count == 1
    assert system.triggers.pad.mode == "Overlaps"
    # Three declared particle emitters plus the three beacon light objects the
    # behaviour makes itself and parks in state.effects for teardown.
    assert system.effect_count == 6


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
    tick(state, module, seconds=0.1,
         steps=int(spec.BEHAVIOR["join_immunity_seconds"] / 0.1) + 4)

    # Touching, but crawling: below the impact threshold nothing happens.
    close_in(state, module, 3, 2, speed_mps=1.0)
    tick(state, module, steps=4)
    assert _carrier_of(module) == 2, "a fender brush should not transfer"

    # Same geometry, a real hit.
    close_in(state, module, 3, 2,
             speed_mps=spec.BEHAVIOR["impact_kmh"] / 3.6 + 2.0)
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
    tick(state, module, seconds=0.1,
         steps=int(spec.BEHAVIOR["join_immunity_seconds"] / 0.1) + 4)

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
    tick(state, module, seconds=0.1,
         steps=int(spec.BEHAVIOR["join_immunity_seconds"] / 0.1) + 4)

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
    tick(state, module, seconds=0.1,
         steps=int(spec.BEHAVIOR["tagback_min_hold_seconds"] / 0.1) + 40)
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
        tick(state, module)
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
            # While merely carrying, the car must receive no vehicle-side
            # command at all: no crush, no breakgroups, no fire.
            assert not list(state.commands.values()), (
                "a carrying vehicle was sent a Lua command before detonation"
            )
    assert module.getSystemState(PROP_ID).behavior_phase == "boom"
    assert elapsed >= spec.BEHAVIOR["fuse_min_seconds"] - 0.5, "fuse fired early"

    commands = list(state.commands.values())
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

    run_until(state, module, lambda: _remaining(module) <= 1.0,
              limit_seconds=spec.BEHAVIOR["fuse_max_seconds"] + 10.0)
    close_in(state, module, 3, 2, speed_mps=spec.BEHAVIOR["impact_kmh"] / 3.6 + 2.0)
    tick(state, module)
    assert _carrier_of(module) == 3
    remaining = _remaining(module)
    assert remaining >= spec.BEHAVIOR["grace_seconds"] - 0.5, (
        f"receiver got only {remaining:.2f}s, below the guaranteed hot window"
    )


def test_the_tick_accelerates_and_rises_in_pitch(rig):
    """No numeric countdown: urgency rides the cue, so the cue must move."""

    _lua, state, module, spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module)
    start_round(state, module, 2)

    early, late = [], []
    budget = spec.BEHAVIOR["fuse_max_seconds"] + 10.0
    spent = 0.0
    while spent < budget:
        remaining = _remaining(module)
        if remaining <= 0.5:
            break
        state.clear()
        tick(state, module, seconds=0.2, steps=10)  # two wall seconds
        spent += 2.0
        beeps = [s for s in state.sounds.values() if "Beep" in s.event]
        sample = (len(beeps), max((b.pitch for b in beeps), default=1.0))
        if remaining > spec.BEHAVIOR["cue_window_seconds"] + 2.0:
            early.append(sample)
        elif remaining < 4.0:
            late.append(sample)

    assert early and late
    assert late[0][0] > early[0][0], "the tick did not speed up"
    assert late[0][1] > early[0][1] + 0.2, "the tick did not rise in pitch"


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
    assert module.getSystemState(PROP_ID).behavior_phase == "idle"
    assert _carrier_of(module) is None, "potato kept riding a reset carrier"


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
    run_until(state, module,
              lambda: module.getSystemState(PROP_ID).behavior_phase == "idle",
              limit_seconds=10.0)
    assert _carrier_of(module) is None
    assert any("LAST CAR STANDING" in m for m in state.messages.values()), (
        "field collapse must end as a win"
    )
    # And above all: nobody was detonated.
    assert not list(state.commands.values()), (
        "the sole survivor received a detonation command"
    )


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
    assert module.getSystemState(PROP_ID).behavior_phase == "idle"
    # The survivor is 300 m away and must NOT have inherited the potato.
    assert _carrier_of(module) is None


def test_teardown_removes_every_scene_object(rig):
    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 0.0, 0.0, 0.0)
    tick(state, module)
    assert any(name.find("ericrolph_hot_potato_p1") == 0 for name in state.scene)

    module.onClientEndMission("/levels/gridmap_v2/main")
    leftovers = [n for n in state.scene if n.find("ericrolph_hot_potato_p1") == 0]
    assert not leftovers, f"scene objects survived mission end: {leftovers}"
