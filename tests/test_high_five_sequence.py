"""Headless state-machine gate for the High Five runtime.

The pack's static gates prove the evidence chain and
``test_high_five_geometry.py`` proves the vectors. Neither can see the thing
that actually makes this prop different from the four other contraptions
that hit cars: it does not fire on a timer, it LEADS its subject. In the
``cocked`` phase it reads the subject's live position and closing speed
every frame, projects the time to the strike plane, and releases the swing
so the palm arrives when the car does.

That is a closed loop with three ways to go wrong and one of them is
silent:

* it can release too early or too late, and at one particular speed a
  fixed timer looks identical to a correct lead — which is exactly how a
  broken prediction ships,
* it can never release at all (a parked car, a reversing car, a subject
  that despawns), leaving the arm cocked forever,
* it can release twice, or wedge somewhere in the seven-phase cycle and
  never come back to idle.

So the tests below drive the REAL generated ``runtime.lua`` under lupa
against stubbed engine globals, at several speeds, following
``test_spin_launch_sequence.py`` and ``test_hot_potato_logic.py``.

It cannot prove physics: no soft body, no collision, no render. It proves
the logic those hang off. A live gate on a sentinel-isolated profile is
still required before shipping.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "high_five"
PROP_ID = 1
SUBJECT_ID = 7
OTHER_ID = 9


def load_spec():
    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader = importlib.util.spec_from_file_location("high_five_spec", spec_path)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


SPEC = load_spec()

# The engine surface runtime.lua touches. Quaternions stay IDENTITY on
# purpose: PROP_REF_OFFSET is (0, 0, 0) and the prop is spawned at the
# origin, so the authored frame and the world frame coincide and every
# measured vector is directly comparable to the numbers in spec.py.
# Rotation correctness is a render question and belongs to the live gate —
# and to test_high_five_geometry, which checks the vectors offline.
STUBS = r"""
local S = {}
S.messages = {}
S.events = {}
S.velocities = {}
S.commands = {}
S.scene = {}
S.vehicles = {}
S.collisionReloads = 0

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
  return setmetatable(
    {class = class, fields = {}, id = nextObjectId, active = false}, objmt)
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
function vehmt:getVelocity() return vec3(self.vel.x, self.vel.y, self.vel.z) end
function vehmt:getRotation() return {0, 0, 0, 1} end
function vehmt:getJBeamFilename() return self.model end
function vehmt:getRefNodeId() return 0 end
function vehmt:getSpawnWorldOOBB()
  local half = self.half
  return {getHalfExtents = function() return vec3(half.x, half.y, half.z) end}
end
function vehmt:queueLuaCommand(cmd)
  S.commands[#S.commands + 1] = {id = self.id, cmd = cmd}
end
function vehmt:getPosition()
  return vec3(self.pos.x, self.pos.y, self.pos.z)
end
function vehmt:getVelocity()
  return vec3(self.vel.x, self.vel.y, self.vel.z)
end
function vehmt:getDirectionVectorUp() return vec3(0, 0, 1) end
function vehmt:applyClusterVelocityScaleAdd(_node, scale, x, y, z)
  S.velocities[#S.velocities + 1] = {id = self.id, scale = scale,
                                     x = x, y = y, z = z}
end
function vehmt:setPositionRotation() end

map = {objects = {}}

function S.addVehicle(id, model, x, y, z, hx, hy, hz)
  local vehicle = setmetatable({
    id = id, model = model,
    pos = {x = x, y = y, z = z},
    vel = {x = 0, y = 0, z = 0},
    half = {x = hx or 0.95, y = hy or 2.3, z = hz or 0.75},
  }, vehmt)
  S.vehicles[id] = vehicle
  map.objects[id] = {vel = vec3(0, 0, 0), damage = 0}
  return vehicle
end

-- Drive a subject up-road at a constant closing speed. The runtime reads
-- BOTH position and velocity every frame, so the test has to actually move
-- the car rather than just claim a speed.
function S.setMotion(id, speed)
  S.vehicles[id].vel = {x = 0, y = speed, z = 0}
end
function S.advance(id, dt)
  local v = S.vehicles[id]
  v.pos.x = v.pos.x + v.vel.x * dt
  v.pos.y = v.pos.y + v.vel.y * dt
  v.pos.z = v.pos.z + v.vel.z * dt
end
function S.positionOf(id) return S.vehicles[id].pos.y end
function S.lateralOf(id) return S.vehicles[id].pos.x end
function S.removeVehicle(id) S.vehicles[id] = nil; map.objects[id] = nil end
function S.clearVelocities() S.velocities = {} end
function S.lastCommand() return S.commands[#S.commands] end
function S.lastVelocity() return S.velocities[#S.velocities] end
function S.velocityCount() return #S.velocities end
function S.lastMessage() return S.messages[#S.messages] end

be = {}
function be:getObjectByID(id) return S.vehicles[id] end
function be:reloadCollision() S.collisionReloads = S.collisionReloads + 1 end

guihooks = {message = function(payload)
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
    runtime_path = (
        PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / SPEC.MOD_ID / "runtime.lua"
    )
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    state = lua.execute(STUBS)
    module = lua.execute(runtime_path.read_text(encoding="utf-8"))
    state.addVehicle(PROP_ID, SPEC.MOD_ID, 0.0, 0.0, 0.0, 20.0, 30.0, 12.0)
    module.registerProp(PROP_ID)
    _ZONES[id(module)] = Zones(lua, state, module)
    return lua, state, module


def status(module):
    return module.getSystemState(PROP_ID).behavior_status


def tick(module, seconds=1.0 / 60.0, steps=1):
    for _ in range(steps):
        module.onPreRender(seconds, seconds, seconds)


def enter_zone(lua, state, module, zone, vehicle_id):
    name = f"{SPEC.MOD_ID}_p{PROP_ID}_{zone}"
    trigger = state.scene[name]
    module.onBeamNGTrigger(
        lua.table_from(
            {
                "event": "enter",
                "triggerID": trigger.id,
                "triggerName": name,
                "subjectID": vehicle_id,
            }
        )
    )


def exit_zone(lua, state, module, zone, vehicle_id):
    name = f"{SPEC.MOD_ID}_p{PROP_ID}_{zone}"
    trigger = state.scene[name]
    module.onBeamNGTrigger(
        lua.table_from(
            {
                "event": "exit",
                "triggerID": trigger.id,
                "triggerName": name,
                "subjectID": vehicle_id,
            }
        )
    )


# Half the length of the car this harness drives. The trigger mode is
# Overlaps, so a box is entered when the bounding box first touches it.
CAR_HALF = 2.25
CAR_HALF_WIDTH = 0.95


#: one Zones per live runtime, so drive() is geometry-driven everywhere
#: without every call site having to thread it through.
_ZONES: dict = {}


class Zones:
    """Zone membership DERIVED FROM THE SHIPPED TRIGGER GEOMETRY.

    This replaces hand-fired enter/exit events, and it is the single most
    important thing in this file.

    Injecting the events by hand meant the corridor's dimensions and the
    timing constants were never coupled, so the harness happily proved a
    lead that the real geometry could never deliver — and it hid the SAME
    class of defect twice. Round 1: a 62 m corridor whose far edge a fast
    car crossed before the arm was cocked. Round 2, after the corridor
    moved to clear the console apron: a 12.2 m strip in front of the strike
    plane where the machine tracked nobody, which killed every speed from
    20 to 110 km/h. Both were invisible here and obvious on the road.

    Every zone event this harness fires is now a CONSEQUENCE of where the
    car is, exactly as it is in game.
    """

    def __init__(self, lua, state, module):
        self.lua, self.state, self.module = lua, state, module
        self.inside = {}

    @staticmethod
    def _overlaps(zone, x, y):
        centre = SPEC.TRIGGERS[zone]["center"]
        half_x = SPEC.TRIGGERS[zone]["dimensions"][0] / 2.0
        half_y = SPEC.TRIGGERS[zone]["dimensions"][1] / 2.0
        return (
            abs(x - centre[0]) <= half_x + CAR_HALF_WIDTH
            and abs(y - centre[1]) <= half_y + CAR_HALF
        )

    def update(self, vehicle_id, x, y):
        for zone in SPEC.TRIGGERS:
            key = (zone, vehicle_id)
            now = self._overlaps(zone, x, y)
            was = self.inside.get(key, False)
            if now and not was:
                enter_zone(self.lua, self.state, self.module, zone, vehicle_id)
            elif was and not now:
                exit_zone(self.lua, self.state, self.module, zone, vehicle_id)
            self.inside[key] = now


def approach(lua, state, module, *, speed, start_y=None, vehicle_id=SUBJECT_ID, x=0.0):
    """Put a car on the road well up-corridor and start it closing.

    The default start is just OUTSIDE the corridor's far edge, so the entry
    is a real crossing.
    """

    corridor = SPEC.TRIGGERS["approach"]
    far_edge = corridor["center"][1] - corridor["dimensions"][1] / 2.0
    if start_y is None:
        start_y = far_edge - 12.0
    state.addVehicle(vehicle_id, "pickup", x, start_y, 0.5)
    state.setMotion(vehicle_id, speed)
    return vehicle_id


def drive(state, module, vehicle_id, seconds, *, dt=1.0 / 60.0, until=None):
    """Advance the subject and the sim together, firing zone crossings.

    Returns the elapsed time when ``until`` first holds, or None.
    """

    # KeyError, not .get(): a rig that forgot to register would otherwise
    # fire NO zone events at all, and a negative test like the dodge one
    # would pass for entirely the wrong reason.
    zones = _ZONES[id(module)]
    steps = int(seconds / dt)
    for step in range(steps):
        if zones is not None:
            zones.update(vehicle_id, state.lateralOf(vehicle_id), state.positionOf(vehicle_id))
        if until is not None and until(status(module)):
            return step * dt
        state.advance(vehicle_id, dt)
        tick(module, dt)
    if until is not None and until(status(module)):
        return steps * dt
    return None if until is not None else steps * dt


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_registers_idle_with_every_part_and_trigger(rig):
    _lua, _state, module = rig
    result = module.getSystemState(PROP_ID)
    assert result.registered is True
    assert result.trigger_count == 2
    # arm + cuff + palm + 5 digits + 10 power segments + 7 tilt segments
    # + lamp. The cuff is its own part because the runtime drops the hand as
    # the wrist rolls, and a collar bolted to the arm would have the foam
    # stump pull out through its own bore.
    assert result.part_count == 26
    assert status(module).phase == "idle"
    assert status(module).faulted is False


def test_console_defaults_are_the_shipped_ones(rig):
    _lua, _state, module = rig
    reading = status(module)
    behavior = SPEC.BEHAVIOR
    assert reading.power_level == behavior["default_power_level"]
    assert reading.tilt_index == behavior["default_tilt_index"]
    assert reading.tilt_deg == pytest.approx(
        behavior["default_tilt_index"] * behavior["tilt_step_deg"]
    )


# ---------------------------------------------------------------------------
# The anticipation
# ---------------------------------------------------------------------------


def test_entering_the_approach_corridor_wakes_the_hand_but_not_the_arm(rig):
    """The fingers move first and the arm does not. That pause IS the gag,
    and the pack's design rule is to exaggerate it."""

    lua, state, module = rig
    approach(lua, state, module, speed=25.0)
    # The car starts outside the corridor and drives in, so the wake-up is a
    # real crossing of the shipped trigger box.
    entered = drive(state, module, SUBJECT_ID, 4.0, until=lambda s: s.phase != "idle")
    assert entered is not None, "never entered the corridor"
    assert status(module).phase == "alert"
    assert status(module).azimuth_deg == pytest.approx(SPEC.REST_DEG)
    drive(state, module, SUBJECT_ID, SPEC.BEHAVIOR["alert_seconds"] * 0.8)
    assert status(module).phase == "alert", "left alert before alert_seconds"
    assert status(module).azimuth_deg == pytest.approx(SPEC.REST_DEG), (
        "the arm moved during the alert; the whole joke is that it does not"
    )


def test_the_arm_draws_back_past_rest_before_it_swings(rig):
    lua, state, module = rig
    approach(lua, state, module, speed=22.0)
    drive(state, module, SUBJECT_ID, 4.0, until=lambda s: s.phase == "cocked")
    assert status(module).phase == "cocked"
    assert status(module).azimuth_deg == pytest.approx(SPEC.WINDUP_DEG)
    assert SPEC.WINDUP_DEG < SPEC.REST_DEG < SPEC.CONTACT_DEG, (
        "the windup must go the OTHER way from the swing"
    )


# ---------------------------------------------------------------------------
# The lead — the thing that makes this prop work at any speed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("speed", [12.0, 25.0, 40.0])
def test_the_palm_arrives_when_the_car_does(rig, speed):
    """Release, then swing, then contact — and the car should be at the
    strike plane at contact, whatever speed it came in at.

    This is the assertion a fixed timer cannot pass at more than one speed,
    which is the entire reason ``swing_lead_seconds`` exists.
    """

    lua, state, module = rig
    # Far enough back that the alert and windup always finish first.
    approach(lua, state, module, speed=speed)
    drive(state, module, SUBJECT_ID, 30.0, until=lambda s: s.slapped)
    assert status(module).slapped is True, f"never slapped at {speed} m/s"
    at_contact = state.positionOf(SUBJECT_ID)
    # Half the slap zone's own length is the honest tolerance: the zone is
    # swept at contact time, so anything inside it is hit.
    tolerance = SPEC.TRIGGERS["slap_zone"]["dimensions"][1] / 2.0
    assert abs(at_contact) < tolerance, (
        f"at {speed} m/s the palm arrived with the car {at_contact:+.1f} m from "
        f"the strike plane (tolerance +/-{tolerance:.1f} m)"
    )


def test_a_faster_car_releases_the_swing_further_out():
    """Sanity on the direction of the prediction: lead distance must grow
    with speed, or the loop is reading something that is not velocity."""

    def release_distance(speed):
        lua, state, module = fresh_rig()
        approach(lua, state, module, speed=speed)
        drive(state, module, SUBJECT_ID, 30.0, until=lambda s: s.phase == "slapping")
        assert status(module).phase == "slapping", speed
        return abs(state.positionOf(SUBJECT_ID))

    slow = release_distance(12.0)
    fast = release_distance(40.0)
    assert fast > slow * 2.0, (
        f"release distance barely changed with speed ({slow:.1f} m -> {fast:.1f} m); "
        "the lead is not tracking the subject"
    )


def test_a_parked_car_is_slapped_anyway_by_the_hold_timer(rig):
    """Stopping to look at it must not leave the arm cocked forever — and
    getting slapped for stopping is the funnier outcome."""

    lua, state, module = rig
    approach(lua, state, module, speed=25.0)
    drive(state, module, SUBJECT_ID, 3.0, until=lambda s: s.phase == "cocked")
    assert status(module).phase == "cocked"
    state.setMotion(SUBJECT_ID, 0.0)
    held = drive(
        state,
        module,
        SUBJECT_ID,
        SPEC.BEHAVIOR["max_hold_seconds"] + 1.0,
        until=lambda s: s.phase != "cocked",
    )
    assert held is not None, "the arm stayed cocked past max_hold_seconds"
    assert held == pytest.approx(SPEC.BEHAVIOR["max_hold_seconds"], abs=0.15)


def test_leaving_the_corridor_does_not_disarm_the_trap(rig):
    """Pulling onto the shoulder must not switch the machine off, or the
    trap is trivially defeated.

    This gate used to assert ``subject_id == -1`` after the exit — it
    pinned, as correct, the exact behaviour that killed every speed from 20
    to 110 km/h. The corridor is an ARMING trigger; while the machine is
    tracking, an exit means nothing.
    """

    lua, state, module = rig
    approach(lua, state, module, speed=25.0)
    drive(state, module, SUBJECT_ID, 6.0, until=lambda s: s.phase == "cocked")
    exit_zone(lua, state, module, "approach", SUBJECT_ID)
    assert status(module).phase == "cocked"
    assert status(module).subject_id == SUBJECT_ID, (
        "the machine forgot who it was aiming at the moment they crossed a "
        "line 16 m short of the strike plane"
    )
    drive(
        state,
        module,
        SUBJECT_ID,
        SPEC.BEHAVIOR["max_hold_seconds"] + 1.0,
        until=lambda s: s.phase != "cocked",
    )
    assert status(module).phase != "cocked"


def test_a_subject_that_vanishes_mid_hold_does_not_wedge_the_arm(rig):
    lua, state, module = rig
    approach(lua, state, module, speed=25.0)
    drive(state, module, SUBJECT_ID, 3.0, until=lambda s: s.phase == "cocked")
    state.removeVehicle(SUBJECT_ID)
    for _ in range(int((SPEC.BEHAVIOR["max_hold_seconds"] + 1.0) * 60)):
        tick(module)
    assert status(module).phase != "cocked"


# ---------------------------------------------------------------------------
# The slap
# ---------------------------------------------------------------------------


def fresh_rig():
    """A brand-new runtime, registered and idle.

    Measurements that need several full passes build one of these each
    time rather than resetting a shared prop: a reset rebuilds the trigger
    objects and clears zone occupancy, so re-using one rig makes the test
    depend on the order the reset and the trigger events happen to arrive
    in, which is not what any of these tests are about.
    """

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    state = lua.execute(STUBS)
    runtime = (
        PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / SPEC.MOD_ID / "runtime.lua"
    ).read_text(encoding="utf-8")
    module = lua.execute(runtime)
    state.addVehicle(PROP_ID, SPEC.MOD_ID, 0.0, 0.0, 0.0, 20.0, 30.0, 12.0)
    module.registerProp(PROP_ID)
    _ZONES[id(module)] = Zones(lua, state, module)
    return lua, state, module


def slap_once(lua, state, module, *, power=None, tilt=None, speed=25.0):
    """Run one full approach and return the launch record."""

    if power is not None:
        for _ in range(20):
            module.pressPanelButtonByVehicle(PROP_ID, "btn_power_down")
        for _ in range(power - 1):
            module.pressPanelButtonByVehicle(PROP_ID, "btn_power_up")
    if tilt is not None:
        for _ in range(20):
            module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_down")
        for _ in range(tilt):
            module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_up")
    approach(lua, state, module, speed=speed)
    state.clearVelocities()
    drive(state, module, SUBJECT_ID, 30.0, until=lambda s: s.slapped)
    assert status(module).slapped is True
    launched = state.lastVelocity()
    assert launched is not None, "the slap landed but nothing was launched"
    return launched


def test_the_launch_leaves_along_the_palm_normal():
    """A slap can only throw a thing along the palm it was struck with, so
    the launch elevation must BE the TILT setting — that identity is what
    the console is selling."""

    behavior = SPEC.BEHAVIOR
    for tilt_index in range(behavior["tilt_levels"]):
        lua, state, module = fresh_rig()
        launched = slap_once(lua, state, module, power=1, tilt=tilt_index)
        speed = math.sqrt(launched.x**2 + launched.y**2 + launched.z**2)
        elevation = math.degrees(math.asin(max(-1.0, min(1.0, launched.z / speed))))
        expected = tilt_index * behavior["tilt_step_deg"]
        assert elevation == pytest.approx(expected, abs=0.5), (
            f"TILT {expected} deg launched at {elevation:.1f} deg"
        )
        assert abs(launched.x) < 1e-6, "the slap threw sideways off the palm normal"


def test_power_scales_the_launch_across_its_whole_ladder():
    behavior = SPEC.BEHAVIOR
    speeds = []
    for level in (1, behavior["power_levels"]):
        lua, state, module = fresh_rig()
        launched = slap_once(lua, state, module, power=level, tilt=0)
        speeds.append(math.sqrt(launched.x**2 + launched.y**2 + launched.z**2))
    ratio = speeds[1] / speeds[0]
    # Both draws are random inside slap_speed_min..max, so the ratio is a
    # band, not a number: worst case is min at full power over max at 1x.
    lowest = (behavior["slap_speed_min_mps"] * behavior["power_multiplier_max"]) / behavior[
        "slap_speed_max_mps"
    ]
    assert ratio > lowest * 0.95, f"POWER ladder ratio {ratio:.2f} is too flat"


def test_the_velocity_is_replaced_not_added(rig):
    """``launchSubject`` must zero the incoming velocity, or a fast car
    keeps its own momentum and the slap reads as a nudge."""

    lua, state, module = rig
    launched = slap_once(lua, state, module, power=3, tilt=2, speed=40.0)
    assert launched.scale == 0, (
        "applyClusterVelocityScaleAdd was called with a non-zero scale; the "
        "subject keeps its old velocity"
    )


# ---------------------------------------------------------------------------
# The cycle
# ---------------------------------------------------------------------------


def test_the_full_cycle_returns_to_idle(rig):
    lua, state, module = rig
    seen = []
    approach(lua, state, module, speed=25.0)
    zones = _ZONES[id(module)]
    for _ in range(int(40.0 * 60)):
        phase = status(module).phase
        if phase != "idle" and (not seen or seen[-1] != phase):
            seen.append(phase)
        zones.update(SUBJECT_ID, state.lateralOf(SUBJECT_ID), state.positionOf(SUBJECT_ID))
        state.advance(SUBJECT_ID, 1.0 / 60.0)
        tick(module)
        if len(seen) >= 8:
            break
    # The machine re-arms in the SAME update it reaches idle when the
    # corridor is still occupied, so "idle" is never observed from outside
    # — assert the seven phases it does walk, in order, and separately that
    # it got as far as cooldown.
    assert seen[:8] == [
        "alert",
        "windup",
        "cocked",
        "slapping",
        "follow",
        "holding",
        "returning",
        "cooldown",
    ], seen


def test_it_re_arms_for_a_car_already_waiting(rig):
    lua, state, module = rig
    approach(lua, state, module, speed=25.0)
    # A second car enters the corridor while the first is being dealt with,
    # and the first LEAVES it (it has just been launched down the road), so
    # the only occupant left to pick up is the second.
    state.addVehicle(OTHER_ID, "pickup", 0.0, -70.0, 0.5)
    state.setMotion(OTHER_ID, 20.0)
    enter_zone(lua, state, module, "approach", OTHER_ID)
    departed = False
    for _ in range(int(40.0 * 60)):
        if not departed and status(module).phase == "follow":
            exit_zone(lua, state, module, "approach", SUBJECT_ID)
            departed = True
        state.advance(SUBJECT_ID, 1.0 / 60.0)
        state.advance(OTHER_ID, 1.0 / 60.0)
        tick(module)
        if status(module).phase == "alert" and status(module).subject_id == OTHER_ID:
            break
    assert status(module).subject_id == OTHER_ID, (
        "the machine did not pick up the car still waiting in the corridor"
    )


def test_a_reset_returns_the_arm_to_rest(rig):
    lua, state, module = rig
    approach(lua, state, module, speed=25.0)
    drive(state, module, SUBJECT_ID, 3.0, until=lambda s: s.phase == "cocked")
    module.onVehicleResetted(PROP_ID)
    reading = status(module)
    assert reading.phase == "idle"
    assert reading.azimuth_deg == pytest.approx(SPEC.REST_DEG)
    assert reading.subject_id == -1


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------


def test_console_clamps_at_both_ends(rig):
    _lua, _state, module = rig
    behavior = SPEC.BEHAVIOR
    for _ in range(behavior["power_levels"] + 5):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_power_up")
    assert status(module).power_level == behavior["power_levels"]
    for _ in range(behavior["power_levels"] + 5):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_power_down")
    assert status(module).power_level == 1
    for _ in range(behavior["tilt_levels"] + 5):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_up")
    assert status(module).tilt_index == behavior["tilt_levels"] - 1
    for _ in range(behavior["tilt_levels"] + 5):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_down")
    assert status(module).tilt_index == 0


def test_an_unknown_button_id_changes_nothing(rig):
    _lua, _state, module = rig
    before = status(module)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_not_a_button")
    after = status(module)
    assert after.power_level == before.power_level
    assert after.tilt_index == before.tilt_index


def test_no_lua_errors_were_logged(rig):
    """Every behaviour hook runs under pcall, so a crash inside one is
    SILENT — the phase just stops advancing. The error log is the only
    place it surfaces."""

    lua, state, module = rig
    approach(lua, state, module, speed=25.0)
    drive(state, module, SUBJECT_ID, 20.0)
    errors = [event.message for event in state.events.values() if event.level == "E"]
    assert not errors, errors


def test_the_corridor_can_actually_deliver_the_lead_it_promises():
    """CLOSED FORM, no simulation: the corridor and the timing must be
    compatible at the slowest speed the mod claims to support.

    The release fires when the subject is ``swing_lead_seconds * v`` metres
    from the strike plane. If the machine stops tracking at the corridor's
    near edge, then below ``near_edge / swing_lead`` the subject is lost
    BEFORE the lead can ever fire. With a near edge 16 m out and a 0.45 s
    lead that is 30.6 m/s — every speed from 20 to 110 km/h dead, which is
    exactly what shipped.

    The runtime now holds the subject through the exit while it is
    tracking, so the corridor's near edge no longer bounds anything. This
    asserts the invariant that makes that safe, and it is deliberately
    written as arithmetic rather than as a replay so it cannot be satisfied
    by a harness that fires its own events.
    """

    corridor = SPEC.TRIGGERS["approach"]
    near_edge = abs(corridor["center"][1] + corridor["dimensions"][1] / 2.0)
    lead = SPEC.BEHAVIOR["swing_lead_seconds"]
    slowest = SPEC.BEHAVIOR["min_closing_mps"]
    runtime = (
        PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / SPEC.MOD_ID / "runtime.lua"
    ).read_text(encoding="utf-8")
    holds = "if TRACKING_PHASES[b.phase] then return end" in runtime
    assert holds or lead * slowest >= near_edge, (
        f"the corridor's near edge is {near_edge:.1f} m out and the lead only "
        f"reaches {lead * slowest:.1f} m at {slowest:.1f} m/s, and the runtime "
        "drops the subject at the exit — every speed below "
        f"{near_edge / lead:.1f} m/s can never be hit"
    )


@pytest.mark.parametrize("speed", [6.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 55.0])
def test_it_connects_across_the_whole_drivable_range(speed):
    """The end-to-end version of the above, driven through the REAL trigger
    boxes at eight speeds spanning 22 to 198 km/h.

    Two separate reviewers measured dead bands here that every green gate
    in this file missed, both times because the harness injected its own
    zone events. It does not any more.
    """

    lua, state, module = fresh_rig()
    approach(lua, state, module, speed=speed)
    drive(state, module, SUBJECT_ID, 60.0, until=lambda s: s.slapped)
    assert status(module).slapped is True, f"never slapped at {speed} m/s"
    # `slapped` is set when the STROKE completes, before slapStrikeZone runs
    # — it means "the swing happened", not "a car was hit". Without this the
    # whole sweep would stay green if the strike zone stopped connecting.
    assert state.velocityCount() > 0, f"the swing completed at {speed} m/s but nothing was launched"
    at_contact = state.positionOf(SUBJECT_ID)
    tolerance = SPEC.TRIGGERS["slap_zone"]["dimensions"][1] / 2.0 + CAR_HALF
    assert abs(at_contact) < tolerance, (
        f"at {speed} m/s the palm arrived with the car {at_contact:+.1f} m from "
        f"the strike plane (tolerance +/-{tolerance:.1f} m)"
    )


def test_holding_the_mast_side_line_is_a_real_escape():
    """The mod's only skill line. The strike zone is offset +2 m in x to
    match where the hand actually is, which leaves a lane on the mast side
    that arms the machine and then misses.

    If this ever stops being true the encounter has no way to lose again.
    """

    lua, state, module = fresh_rig()
    zone = SPEC.TRIGGERS["slap_zone"]
    dodge_x = zone["center"][0] - zone["dimensions"][0] / 2.0 - CAR_HALF_WIDTH - 0.3
    corridor = SPEC.TRIGGERS["approach"]
    armed_x = corridor["center"][0] - corridor["dimensions"][0] / 2.0 - CAR_HALF_WIDTH
    assert dodge_x > armed_x, "there is no lane that both wakes the machine and escapes it"
    approach(lua, state, module, speed=30.0, x=dodge_x)
    drive(state, module, SUBJECT_ID, 40.0, until=lambda s: s.phase == "follow")
    assert status(module).phase == "follow", "the machine never swung"
    assert state.velocityCount() == 0, (
        f"a car at x={dodge_x:.2f} was launched; the hand does not reach it"
    )


def test_a_dodger_cannot_steal_the_aim_from_a_car_in_the_kill_lane():
    """``timeToStrike`` is purely longitudinal and the re-scoring loop has no
    lateral filter, so a fast car holding the mast-side ESCAPE lane can
    outbid a slower car the machine could actually reach — and then the
    swing is timed for someone it cannot hit and misses the one it could.

    Both cars in the existing multi-car gate sit at x = 0, so nothing saw
    this.
    """

    lua, state, module = fresh_rig()
    zone = SPEC.TRIGGERS["slap_zone"]
    dodge_x = zone["center"][0] - zone["dimensions"][0] / 2.0 - CAR_HALF_WIDTH - 0.3
    approach(lua, state, module, speed=15.0, vehicle_id=SUBJECT_ID, x=0.0)
    # The dodger enters later but closes faster.
    corridor = SPEC.TRIGGERS["approach"]
    far = corridor["center"][1] - corridor["dimensions"][1] / 2.0
    state.addVehicle(OTHER_ID, "pickup", dodge_x, far - 40.0, 0.5)
    state.setMotion(OTHER_ID, 40.0)
    zones = _ZONES[id(module)]
    launched = None
    for _ in range(int(45.0 * 60)):
        for identifier in (SUBJECT_ID, OTHER_ID):
            zones.update(identifier, state.lateralOf(identifier), state.positionOf(identifier))
            state.advance(identifier, 1.0 / 60.0)
        tick(module)
        if state.velocityCount() > 0:
            launched = state.lastVelocity().id
            break
    assert launched == SUBJECT_ID, (
        f"the machine launched {launched}; a car in the escape lane took the "
        "aim from one it could actually reach"
    )


def test_a_car_that_only_touches_the_pad_is_slapped(rig):
    """THE PAINTED PAD HAS TO WORK, and this was found in play.

    The approach corridor runs y = -124 .. -16. The painted pad is
    y = -4.3 .. +4.3. So the one object in the scene that says "drive
    here" -- a hand stencilled on the road -- sat 11.7 m outside the only
    trigger that armed anything, and `onEnter` opened with
    `if zone ~= "approach" then return end`. Drive onto the pad from the
    side, or from anywhere nearer than 16 m, and the hand just watched.

    Every other test in this file approaches down the corridor, which is
    exactly why none of them saw it: they all exercise the MECHANISM and
    none of them exercise the AFFORDANCE. The live gate missed it for the
    same reason -- it placed the car 85 m up the corridor and drove it
    straight down the centreline.
    """

    _lua, state, module = rig
    corridor = SPEC.TRIGGERS["approach"]
    near_edge = corridor["center"][1] + corridor["dimensions"][1] / 2.0
    assert near_edge < -CAR_HALF, (
        "the corridor now reaches the pad, so parking on the pad would arm "
        "through the corridor and this test would prove nothing"
    )

    # Straight onto the pad, stationary, having never been up the road.
    state.addVehicle(SUBJECT_ID, "pickup", 0.0, 0.0, 0.5)
    state.setMotion(SUBJECT_ID, 0.0)

    # The RESPONSE is immediate; the punchline waits 0.5 s for its setup.
    # "You are standing ON it." used to fire on the same tick as the swing,
    # so setup and punchline landed inside one 0.28 s beat and were read
    # airborne. The beat is the fix; the immediacy is the requirement.
    noticed = drive(
        state, module, SUBJECT_ID, 3.0, until=lambda s: s.phase == "pad_alert"
    )
    assert noticed is not None, (
        "a car sitting on the painted pad never got noticed; the affordance "
        "and the trigger are still different things"
    )
    assert noticed < 0.25, (
        f"the pad response took {noticed:.2f} s to start; the machine must "
        "react the moment a wheel is on the paint"
    )
    swung = drive(
        state, module, SUBJECT_ID, 2.0, until=lambda s: s.phase == "slapping"
    )
    assert swung is not None, "the pad alert never released into the swing"
    assert swung < SPEC.BEHAVIOR["pad_alert_seconds"] + 0.15, (
        f"the pad beat held {swung:.2f} s past the alert; setup then "
        "punchline, not a stall"
    )

    drive(state, module, SUBJECT_ID, 2.0, until=lambda s: state.lastVelocity() is not None)
    launched = state.lastVelocity()
    assert launched is not None, "the pad swing connected with nothing"
    assert launched.scale == 0, "the pad launch did not replace the velocity"


def test_the_corridor_still_leads_after_the_pad_shortcut(rig):
    """The pad path must not have turned the machine into a doorbell.

    Arming from the strike zone is a swing from rest with no anticipation,
    which is right for a car that is already there and would be wrong for
    one arriving at speed. This pins that a corridor approach still runs
    alert -> windup before it swings.
    """

    lua, state, module = rig
    approach(lua, state, module, speed=25.0)
    seen = []
    drive(
        state,
        module,
        SUBJECT_ID,
        6.0,
        until=lambda s: (seen.append(s.phase) or False) if s.phase not in seen else False,
    )
    assert "alert" in seen, seen
    assert "windup" in seen, seen
    assert seen.index("alert") < seen.index("windup"), seen


def _spin_command(state):
    """The newest thrusters.applyAccel command any slap queued, parsed.

    NOT state.lastCommand(): queueLuaCommand is also how the PROP announces
    its own registration hook, so the newest command in the log is not
    necessarily the spin -- the first version of this helper grabbed
    "extensions.hook(...)" off the prop and reported that no spin was ever
    queued. Scan backwards for the command this gate is actually about.
    """

    import re

    record = None
    index = 1
    newest = None
    while True:
        entry = state.commands[index]
        if entry is None:
            break
        if "thrusters.applyAccel" in str(entry["cmd"]):
            newest = entry
        index += 1
    record = newest
    if record is None:
        return None
    command = record["cmd"]
    match = re.search(
        r"thrusters\.applyAccel\(vec3\(0,0,0\), ([0-9.]+), nil, "
        r"vec3\((-?[0-9.]+), (-?[0-9.]+), (-?[0-9.]+)\)\)",
        command,
    )
    if not match:
        return None
    dt = float(match.group(1))
    accel = tuple(float(match.group(i)) for i in (2, 3, 4))
    # angularAccel * dt = the angular velocity the contact dwell imparts.
    return {
        "id": record["id"],
        "dt": dt,
        "omega": tuple(a * dt for a in accel),
    }


def test_the_slap_spins_the_car(rig):
    """A slap is an OFF-CENTRE impulse, and the spin is the Jackass in it.

    launchSubject replaces linear velocity along the palm normal; alone
    that reads as a nudge from a giant air-hockey paddle -- the car sails
    flat, wheels down, and lands like a delivery. The palm lands on the
    flank ABOVE the car's centre of mass, so the real impulse both throws
    and tumbles. The runtime queues the tumble into the car's own physics
    (thrusters.applyAccel -> obj:applyClusterLinearAngularAccel), so what
    happens after the palm leaves is the engine's integration, not an
    animation.

    The stub prop sits at identity, so the queued world vector is directly
    comparable to the authored-frame model: spin axis = r x d with
    r = (-0.8, 0, 1.30) and d = (0, cos tilt, sin tilt). At the default
    tilt the axis is dominated by -x (end-over-end roll, top of the car
    carried down-road) with a -z drag-yaw component, and NO +y component
    of any size -- a slap does not spin a car about its own flight path
    like a rifle bullet.
    """

    lua, state, module = rig
    slap_once(lua, state, module, power=3, tilt=2)
    spin = _spin_command(state)
    assert spin is not None, (
        "the slap queued no thrusters.applyAccel -- the car leaves with "
        "zero angular velocity and sails flat like a parcel"
    )
    assert spin["id"] == SUBJECT_ID
    assert spin["dt"] == pytest.approx(
        SPEC.BEHAVIOR["slap_contact_seconds"], abs=1e-3
    )

    omega = spin["omega"]
    magnitude = math.sqrt(sum(component ** 2 for component in omega))
    # Expected: transfer * armRate * mult, capped. Corridor slap swings
    # from WINDUP (-104 deg); power 3 on the shipped ladder is 1.356x.
    arm_rate = (
        SPEC.BEHAVIOR["slap_ease"]
        * math.radians(104.0)
        / SPEC.BEHAVIOR["slap_seconds"]
    )
    mult = 1.0 + (3 - 1) * (SPEC.BEHAVIOR["power_multiplier_max"] - 1.0) / (
        SPEC.BEHAVIOR["power_levels"] - 1
    )
    expected = min(
        SPEC.BEHAVIOR["slap_spin_cap_rps"],
        SPEC.BEHAVIOR["slap_spin_transfer"] * arm_rate * mult,
    )
    assert magnitude == pytest.approx(expected, rel=0.05), (
        f"spin magnitude {magnitude:.2f} rad/s against the model's "
        f"{expected:.2f}"
    )
    # The axis: roll-dominant, negative x; drag yaw negative z; nothing
    # along the flight path.
    assert omega[0] < 0, "the tumble must carry the car top-over, not back"
    assert abs(omega[0]) > abs(omega[2]), "roll must dominate yaw"
    assert omega[2] < 0, "the drag yaw must follow the palm sweep"
    assert abs(omega[1]) < 0.25 * magnitude, (
        "a slap does not rifle-spin a car about its own flight path"
    )
    # And it must be a real spin, not a garnish: at least one full
    # revolution over a typical 3 s flight is 2.1 rad/s.
    assert magnitude > 2.1, f"{magnitude:.2f} rad/s is a garnish, not a tumble"


def test_the_spin_scales_with_the_power_dial(rig):
    """POWER is sold as one dial for the whole slap. If the launch speed
    scales 2.6x while the tumble stays fixed, max power reads as the same
    slap with a longer throw -- the dial must make the whole event wilder,
    up to the cap that keeps it this side of absurd."""

    del rig  # two independent rigs, same pattern as the launch ladder test
    lua, state, module = fresh_rig()
    slap_once(lua, state, module, power=1, tilt=2)
    low = _spin_command(state)
    lua, state, module = fresh_rig()
    slap_once(lua, state, module, power=10, tilt=2)
    high = _spin_command(state)

    assert low is not None and high is not None
    low_mag = math.sqrt(sum(c ** 2 for c in low["omega"]))
    high_mag = math.sqrt(sum(c ** 2 for c in high["omega"]))
    cap = SPEC.BEHAVIOR["slap_spin_cap_rps"]
    if high_mag < cap - 1e-6:
        assert high_mag > low_mag * 1.5, (
            f"power 10 spins at {high_mag:.2f} against power 1's "
            f"{low_mag:.2f}; the dial is not reaching the tumble"
        )
    else:
        assert high_mag == pytest.approx(cap, rel=0.02), (
            "past the cap the spin must sit AT the cap, not above it"
        )
    assert low_mag > 1.0, "even power 1 must visibly tumble"


def test_a_pad_slap_spins_less_than_a_full_windup(rig):
    """The spin comes from the arm's actual rate at contact, which comes
    from the ACTUAL swingFrom -- a pad swing starts at REST (-72 deg), a
    corridor swing at WINDUP (-104), so the pad slap is gentler for free.
    If these come out equal, somebody has hard-coded the windup angle into
    the tumble and the model has become a dial."""

    lua, state, module = rig
    state.addVehicle(SUBJECT_ID, "pickup", 0.0, 0.0, 0.5)
    state.setMotion(SUBJECT_ID, 0.0)
    drive(state, module, SUBJECT_ID, 3.0,
          until=lambda s: _spin_command(state) is not None)
    pad = _spin_command(state)
    assert pad is not None, "the pad slap queued no spin"
    pad_mag = math.sqrt(sum(c ** 2 for c in pad["omega"]))

    expected_ratio = 72.0 / 104.0
    arm_rate = (
        SPEC.BEHAVIOR["slap_ease"]
        * math.radians(72.0)
        / SPEC.BEHAVIOR["slap_seconds"]
    )
    mult = 1.0 + (SPEC.BEHAVIOR["default_power_level"] - 1) * (
        SPEC.BEHAVIOR["power_multiplier_max"] - 1.0
    ) / (SPEC.BEHAVIOR["power_levels"] - 1)
    expected = min(
        SPEC.BEHAVIOR["slap_spin_cap_rps"],
        SPEC.BEHAVIOR["slap_spin_transfer"] * arm_rate * mult,
    )
    assert pad_mag == pytest.approx(expected, rel=0.05), (
        f"pad spin {pad_mag:.2f} rad/s against the from-rest model's "
        f"{expected:.2f} -- the tumble is not reading the real swingFrom"
    )


def test_the_machine_reports_the_score(rig):
    """The aftermath must be MEASURED and SAID, or it never happened.

    A reviewer walked all three live films and found the machine's best
    material — a 200 m tumbling flight with a bounce onto the roof —
    happening off-frame, unmeasured, unannounced. The runtime computed
    slap speed, spin and power for every slap and showed them to nobody.
    The scoreboard is the fix: the machine watches what it launched until
    it stops moving, then says the number while the palm is still out.

    The stub car never moves after launch (setMotion 0), so the flight
    settles immediately and the toast reads zero distance and no rotation
    — which is exactly right for a car that went nowhere, and proves the
    reporting path rather than the physics (frames3 proved the physics).
    """

    import re

    lua, state, module = rig
    state.addVehicle(SUBJECT_ID, "pickup", 0.0, 0.0, 0.5)
    state.setMotion(SUBJECT_ID, 0.0)
    drive(state, module, SUBJECT_ID, 3.0,
          until=lambda s: state.lastVelocity() is not None)
    assert state.lastVelocity() is not None

    settle = SPEC.BEHAVIOR["score_settle_seconds"] + 0.6
    drive(state, module, SUBJECT_ID, settle, until=None)

    messages = []
    index = 1
    while True:
        entry = state.messages[index]
        if entry is None:
            break
        messages.append(str(entry))
        index += 1
    scored = [m for m in messages if re.match(r"^\d+ m\. ", m)]
    assert scored, (
        f"no scoreboard toast after a settled flight; messages: {messages}"
    )
    assert "rotation" in scored[-1], scored[-1]
    assert re.search(r"(wheels|side|ROOF)", scored[-1]), scored[-1]
