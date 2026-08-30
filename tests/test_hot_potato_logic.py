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
    """

    return [
        entry
        for entry in state.commands.values()
        if any(verb in entry.command for verb in PHYSICS_VERBS)
    ]


def _tick_writes(state, vehicle_id):
    """(volume, pitch) of every tick write sent to `vehicle_id`, in order."""

    writes = []
    for entry in state.commands.values():
        if entry.id != vehicle_id:
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
    # Three declared particle emitters plus the THREE light objects the
    # behaviour makes itself and parks in state.effects for teardown: the
    # round-gated beacons. (v2.3 removed the wick and its ember lamp — the
    # smoke wisp off the crown is the idle invitation now.)
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
        entry
        for entry in state.commands.values()
        if entry.id == 2 and "stopSFX" in entry.command
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
        entry
        for entry in state.commands.values()
        if entry.id == 2 and "stopSFX" in entry.command
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
        entry
        for entry in state.commands.values()
        if entry.id == 2 and "stopSFX" in entry.command
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
        ("fuse_base_seconds", 60.0), ("fuse_sigma_seconds", 0.0),
        ("fuse_min_seconds", 60.0), ("fuse_max_seconds", 60.0),
        ("camp_burn_multiplier", 3.0), ("camp_speed_kmh", 20.0),
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
    assert 8.0 < drained_moving < 12.0, (
        f"moving carrier drained {drained_moving:.1f}s over 10s"
    )


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
        entry for entry in state.velocities.values()
        if entry.id == 3 and entry.x > 5.0 and entry.z > 0.5
    ]
    assert shoves, "the impact pass never shoved the receiver"


def test_detonation_shockwave_pushes_bystanders_not_the_distant(rig):
    _lua, state, module, spec = rig
    register_prop(state, module)
    for key, value in (
        ("fuse_min_seconds", 5.0), ("fuse_max_seconds", 6.0),
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
        obj for name, obj in state.scene.items()
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
    assert abs(final[0]) < 1.0 and abs(final[1]) < 1.0, (
        f"the potato settled off its perch: {final}"
    )
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
    assert max(still) - min(still) <= wobble_cap, (
        "bounce_enabled=false still hopped"
    )
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
        1 for entry in state.commands.values()
        if entry.id == 2 and "stopSFX" in entry.command
    )
    tick(state, module, seconds=0.05, steps=4)
    assert module.getSystemState(PROP_ID).behavior_phase == "live"
    assert len(_tick_writes(state, 2)) == before, (
        "the tick kept driving inside the silence gap"
    )
    stops_after = sum(
        1 for entry in state.commands.values()
        if entry.id == 2 and "stopSFX" in entry.command
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
    assert max(z for _x, _y, z in airborne) > 0.0, (
        "mash chunk 1 never rose above grade"
    )
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
    assert any(
        name.endswith("fw_px_1") for name in state.scene
    ), "no firework light pool was created for the champion"
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
    assert shoves and abs(shoves[0].x) >= 5.0, (
        "pinball pass came without its bumper shove"
    )


def test_steam_hiss_vents_while_idle_and_respects_its_option(rig):
    """v2.4: the idle potato periodically lets off a pitched-up air hiss —
    stock one-shot events only, positional, jittered."""

    _lua, state, module, _spec = rig
    register_prop(state, module)
    state.addVehicle(2, "etk800", 60.0, 0.0, 0.0)
    tick(state, module, seconds=0.25, steps=48)  # ~12 idle seconds

    def hisses():
        return [
            entry for entry in state.sounds.values()
            if "Pneumatics" in str(entry.event)
        ]

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
    assert late_green > early_green + 0.3, (
        f"the glow never heated: {early!r} -> {late!r}"
    )
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
        assert str(light.fields.isEnabled) == "0", (
            f"{slot} lit with the beacon disabled"
        )


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
