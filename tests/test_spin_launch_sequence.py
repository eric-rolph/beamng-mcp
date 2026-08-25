"""Headless state-machine gate for the Spin Launch runtime.

The pack's static gates prove the evidence chain - hashes, cage consistency,
materials coverage - and they cannot see this machine's actual mechanic,
which is a nine-phase sequence ending in a single frame where a tangent has
to point somewhere specific. Both halves of that are cheap to get wrong and
expensive to find live:

- the AUTO-DETECT arms off a Contains zone plus a speed gate, so a car
  rolling across the pad must not commit the machine,
- the sequence has to walk idle -> sealing -> evacuating -> engaging ->
  spinup -> hold -> release -> recover -> idle without wedging,
- the RELEASE is a crossing test on an angle that steps up to ~33 degrees
  per tick at full power, and a naive equality test would sail past the
  window on most passes,
- and the whole point of the machine is that the launch velocity comes out
  at the speed the POWER ladder selects, aimed at the elevation the TILT
  ladder selects. That identity (theta_release = 90 + elevation) is written
  down in three places - the Blender generator that places the tube, the
  printed scale on the console, and the runtime - so it is worth one test
  that actually measures the vector.

This runs the REAL generated ``runtime.lua`` under lupa against stubbed
engine globals, following ``test_hot_potato_logic.py``. It cannot prove
physics: no soft body, no collision bake, no lights are real here. It proves
the logic those hang off. A live gate on a sentinel-isolated profile is still
required before shipping.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest

lupa = pytest.importorskip("lupa")

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_KEY = "spin_launch"
PROP_ID = 1
SUBJECT_ID = 7


def load_spec():
    spec_path = PACK_ROOT / MOD_KEY / "spec.py"
    loader_spec = importlib.util.spec_from_file_location("spin_launch_spec", spec_path)
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)
    return module


# The engine surface runtime.lua touches.
#
# THIS STUB USED TO THROW THE POSES AWAY. setPosRot, setPosition and setScale
# were `end`-immediately no-ops and quat-times-vec3 returned the vector
# unchanged, which meant the 28 kinematic parts this runtime drives could be
# placed ANYWHERE - or nowhere - and every test in this file still passed.
# Every visual defect this machine has shipped lived in exactly that deleted
# surface: needles authored at mid-scale so a machine at rest read 100 m/s,
# four bar segments translated so far back they could never light, a warning
# beacon standing inside the launch bore, a bargraph frozen at 4/8. The stub
# now RECORDS what the engine would have been told, and the pose tests below
# read it.
#
# The prop is still spawned so that its authored frame and the world frame
# coincide - but that is now EARNED rather than assumed. The runtime's
# modelRotation is MODEL_ALIGNMENT_ROTATION * vehicleRotation, and
# MODEL_ALIGNMENT_ROTATION is a half turn about Z (the authored -> mesh
# flip), so an identity spawn puts authored +Y along world -Y. register_prop
# therefore spawns the prop already half-turned, and the two half turns
# compose to identity through the real algebra below. `test_the_rig_frame_*`
# asserts the result rather than trusting it.
STUBS = r"""
local S = {}
S.messages = {}
S.events = {}
S.velocities = {}
S.scene = {}
S.vehicles = {}
S.collisionReloads = 0
-- Every queueLuaCommand the GE side sends into the vehicle VM, in order.
-- The audio bridge is the only thing that uses it, and without recording it
-- audioSend's own pcall swallows the whole cue set and every ordering
-- assertion below would pass VACUOUSLY - which is why the cue tests assert
-- this list is non-empty before they assert anything about its contents.
S.luaCommands = {}
-- The same stream, addressed: {id, command} per send.
S.vehCommands = {}

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
function vecmt:cross(o)
  return vec3(self.y * o.z - self.z * o.y,
              self.z * o.x - self.x * o.z,
              self.x * o.y - self.y * o.x)
end
-- Minimal-arc rotation carrying self onto other, CONJUGATED - see the
-- convention block below. Only the effect placer uses it, and nothing here
-- asserts which axis a SpotLight calls forward, but returning identity for
-- every pair made every effect in the mod point the same way in this rig.
function vecmt:getRotationTo(other)
  local a = vec3(self.x, self.y, self.z):normalize()
  local b = vec3(other.x, other.y, other.z):normalize()
  local dot = a:dot(b)
  if dot > 0.999999 then return quat(0, 0, 0, 1) end
  local axis
  if dot < -0.999999 then
    -- Antiparallel: the arc is a half turn about ANY perpendicular.
    local seed = math.abs(a.x) < 0.9 and vec3(1, 0, 0) or vec3(0, 1, 0)
    axis = a:cross(seed):normalize()
    return quat(-axis.x, -axis.y, -axis.z, 0)
  end
  axis = a:cross(b)
  local q = {x = axis.x, y = axis.y, z = axis.z, w = 1.0 + dot}
  local n = math.sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w)
  return quat(-q.x / n, -q.y / n, -q.z / n, q.w / n)
end
function vec3(x, y, z)
  if type(x) == "table" then x, y, z = x.x or x[1], x.y or x[2], x.z or x[3] end
  return setmetatable({x = x or 0, y = y or 0, z = z or 0}, vecmt)
end

-- ---------------------------------------------------------------------
-- QUATERNIONS, IN THE ENGINE'S CONVENTION, DERIVED RATHER THAN GUESSED.
--
-- The old stub returned the vector unchanged from quat * vec3 and identity
-- from quat * quat, so EVERY orientation this runtime computes - the tube's
-- elevation, the tether's angle, both needles, both clamps, the pump rotors,
-- the beacon - was discarded before anything could look at it.
--
-- Which convention? lua_kit's basisQuat builds the standard matrix
-- quaternion of the basis (ex, ey, ez) by the trace formula, with those
-- three as the COLUMNS of a local->world rotation R, and then returns its
-- CONJUGATE: `return quat(-x, -y, -z, w)`. Its only caller needs
-- `rotation * PROP_REF_OFFSET` to come back as the WORLD offset, i.e. to
-- apply R. Handing an operator the conjugate of R's quaternion and getting R
-- back is possible only if the operator conjugates too:
--
--     q * v  ==  conj(q) (x) v (x) q          ((x) = Hamilton product)
--
-- which is the usual Torque storage convention (an object's rotation quat is
-- the inverse of the rotation it performs). That then fixes quat * quat.
-- lua_kit's placement tombstone records that quats compose LEFT-TO-RIGHT
-- here - `MODEL_ALIGNMENT_ROTATION * vehicleRotation` applies the
-- authored->mesh flip in the model's own frame and only then the vehicle
-- attitude, measured live 2026-08-24 at 18.880 m of error on a slope the
-- other way round - and with the conjugating vector operator, left-to-right
-- IS the plain Hamilton product:
--
--     (a * b) * v = conj(a(x)b) v (a(x)b)
--                 = conj(b) (conj(a) v a) b = b * (a * v)
--
-- so `a * b` is `a (x) b`. Both halves are asserted in
-- test_the_rig_quaternion_algebra_is_the_engines, without which no pose this
-- file measures would mean anything.
-- ---------------------------------------------------------------------
local quatmt = {}
quatmt.__index = quatmt
local function hamilton(a, b)
  return quat(
    a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
    a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z)
end
function quatmt.__mul(a, b)
  if getmetatable(b) == vecmt then
    local conjugate = quat(-a.x, -a.y, -a.z, a.w)
    -- axisAngle and basisQuat both emit unit quats, so conj == inverse.
    local rotated = hamilton(hamilton(conjugate, quat(b.x, b.y, b.z, 0)), a)
    return vec3(rotated.x, rotated.y, rotated.z)
  end
  return hamilton(a, b)
end
function quatmt:toTorqueQuat() return self end
function quat(x, y, z, w)
  if type(x) == "table" then x, y, z, w = x[1] or 0, x[2] or 0, x[3] or 0, x[4] or 1 end
  return setmetatable({x = x or 0, y = y or 0, z = z or 0, w = w or 1}, quatmt)
end
function quatFromDir(dir, up)
  -- BeamNG's own quatFromDir takes an up hint; this rig only needs a real
  -- rotation that TRACKS dir, because the only assertion on it is that the
  -- beacon rays keep turning and stay unit-length.
  return vec3(0, 0, 1):getRotationTo(dir)
end

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
-- THE POSE SURFACE. posePartObjects hands every kinematic part
--   position = origin + modelRotation * (spec.pivot + offset)
--   rotation = pose.rotation * modelRotation
-- through setObjectTransform, once a frame. Recording it is the whole reason
-- this rig can say anything about where the machine's 28 moving parts are.
function objmt:setPosRot(x, y, z, qx, qy, qz, qw)
  self.pos = vec3(x, y, z)
  self.rot = quat(qx, qy, qz, qw)
  self.poseCount = (self.poseCount or 0) + 1
end
function objmt:setPosition(value)
  self.pos = vec3(value.x, value.y, value.z)
  self.poseCount = (self.poseCount or 0) + 1
end
function objmt:setScale(value) self.scale = vec3(value.x, value.y, value.z) end
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
  -- Palette materials resolve by name; runtime scene objects (<mod>_p<id>_...)
  -- must NOT, or registerInMission refuses every one of them as a name clash.
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
-- propFrame falls back to the object transform here (no node cloud is
-- stubbed), so this IS the prop's attitude. It is settable because the
-- model-alignment half turn only cancels for a prop that is itself half
-- turned - see register_prop.
function vehmt:getRotation() return self.rot or {0, 0, 0, 1} end
function vehmt:getJBeamFilename() return self.model end
function vehmt:getRefNodeId() return 0 end
function vehmt:getSpawnWorldOOBB()
  local half = self.half
  return {getHalfExtents = function() return vec3(half.x, half.y, half.z) end}
end
function vehmt:queueLuaCommand(command)
  S.luaCommands[#S.luaCommands + 1] = tostring(command)
  -- WHO was sent it, as well as what. The cue readers only ever needed the
  -- text, but a command whose whole purpose is to change one specific car's
  -- structure cannot be checked without knowing which car received it.
  S.vehCommands[#S.vehCommands + 1] = {id = self.id, command = tostring(command)}
end
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
    half = {x = hx or 0.95, y = hy or 2.3, z = hz or 0.75},
  }, vehmt)
  S.vehicles[id] = vehicle
  map.objects[id] = {vel = vec3(0, 0, 0), damage = 0}
  return vehicle
end

function S.setVehicleRotation(id, x, y, z, w)
  S.vehicles[id].rot = {x, y, z, w}
end

function S.setSpeed(id, speed)
  map.objects[id].vel = vec3(0, speed, 0)
end

-- --- pose readback -------------------------------------------------------
-- Everything registerProp creates lands in S.scene under its mission name,
-- so a part's recorded transform is one lookup away. Returned as a flat
-- table because lupa hands Lua tables back to Python as index-1 sequences.
function S.partPose(propModel, propId, name)
  local object = S.scene[
    string.format("%s_p%d_part_%s", propModel, propId, name)]
  if not object or not object.pos then return nil end
  local scale = object.scale or vec3(1, 1, 1)
  return {
    object.pos.x, object.pos.y, object.pos.z,
    object.rot and object.rot.x or 0, object.rot and object.rot.y or 0,
    object.rot and object.rot.z or 0, object.rot and object.rot.w or 1,
    scale.x, scale.y, scale.z,
    object.poseCount or 0,
  }
end

function S.lampField(propModel, propId, key, field)
  local object = S.scene[
    string.format("%s_p%d_light_%s", propModel, propId, key)]
  if not object then return nil end
  return object.fields[field]
end

-- The rotation vector operator, exposed so the pose tests can build the same
-- world frame the runtime does instead of re-deriving it in Python.
function S.rotate(qx, qy, qz, qw, x, y, z)
  local rotated = quat(qx, qy, qz, qw) * vec3(x, y, z)
  return {rotated.x, rotated.y, rotated.z}
end

function S.compose(ax, ay, az, aw, bx, by, bz, bw)
  local composed = quat(ax, ay, az, aw) * quat(bx, by, bz, bw)
  return {composed.x, composed.y, composed.z, composed.w}
end

-- The rig's vehicles are fixed points: applyClusterVelocityScaleAdd records
-- what the field asked for and nothing moves. That is enough for every
-- assertion about WHO the field touches, and useless for the PICKUP, whose
-- whole question is what the command does once the payload has started
-- answering it. follow_field below closes that loop.
function S.movePayload(id, x, y, z)
  local vehicle = S.vehicles[id]
  vehicle.pos.x, vehicle.pos.y, vehicle.pos.z = x, y, z
end

function S.setHalfExtent(id, value)
  S.vehicles[id].half = {x = value, y = value, z = value}
end

function S.removeVehicle(id) S.vehicles[id] = nil; map.objects[id] = nil end
function S.clearVelocities() S.velocities = {} end
function S.lastVelocity()
  return S.velocities[#S.velocities]
end
function S.velocityCount() return #S.velocities end

be = {}
function be:getObjectByID(id) return S.vehicles[id] end
function be:reloadCollision() S.collisionReloads = S.collisionReloads + 1 end

guihooks = {message = function(payload)
  S.messages[#S.messages + 1] = tostring(payload.txt or "")
end}
-- THE LOG CHANNEL IS AN OBSERVABLE, NOT A SINK. emitError routes every
-- runtime failure through here at level "E" - a missing material, a part
-- that would not create, a velocity that came out NaN, a trigger that never
-- registered - and this list was captured and then never read by anything,
-- so a runtime emitting errors on every single frame passed the whole file.
function log(level, tag, message)
  S.events[#S.events + 1] = {level = level, tag = tag, message = message}
end
-- A readable stand-in, because emitEvent routes every telemetry record and
-- every runtime ERROR through it. tostring(table) gave `table: 0x...`, which
-- made the log channel unreadable even once something started reading it.
function jsonEncode(value)
  if type(value) ~= "table" then return tostring(value) end
  local parts = {}
  for _, key in ipairs(sortedKeysForJson(value)) do
    parts[#parts + 1] = tostring(key) .. "=" .. jsonEncode(value[key])
  end
  return "{" .. table.concat(parts, ",") .. "}"
end
function sortedKeysForJson(map)
  local keys = {}
  for key in pairs(map) do keys[#keys + 1] = key end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  return keys
end
core_vehicle_manager = {getVehicleData = function() return nil end}
function loadJsonMaterialsFile() return true end

return S
"""


def _vdata_stub(spec) -> str:
    """A vdata node table with the emitter node DELIBERATELY NOT AT CID 0.

    ``core_vehicle_manager.getVehicleData`` is what ``resolveNodeCid`` asks,
    and the whole reason the audio emitter is resolved by name is that
    BeamNG's cids are NOT jbeam row indices: fixed nodes are renumbered ahead
    of free ones, and the live measurement was that cid 0 is a plinth corner
    76 m from the machine while the jbeam's first ROW is the bore mouth.

    A stub that handed back the rows in file order would let a runtime that
    had gone back to authoring the literal 0 pass this gate, so this one
    rotates the table: the shipped jbeam's rows are dealt out starting one
    third of the way in, which puts a node that is NOT the emitter at cid 0
    and the emitter somewhere the runtime has to look for it.
    """

    jbeam = json.loads(
        (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / spec.MOD_ID
         / f"{spec.MOD_ID}.jbeam").read_text(encoding="utf-8"))
    rows = [row for row in jbeam[spec.MOD_ID]["nodes"]
            if isinstance(row, list) and row[0] != "id"]
    offset = len(rows) // 3
    rotated = rows[offset:] + rows[:offset]
    entries = ",".join(
        f'{{cid={index},name="{row[0]}"}}'
        for index, row in enumerate(rotated))
    return (
        "local NODES = {" + entries + "}\n"
        "core_vehicle_manager = {getVehicleData = function()\n"
        "  return {vdata = {nodes = NODES}}\n"
        "end}\n")


def expected_emitter_cid(spec) -> int:
    """Where _vdata_stub put the emitter, computed the same way."""

    jbeam = json.loads(
        (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / spec.MOD_ID
         / f"{spec.MOD_ID}.jbeam").read_text(encoding="utf-8"))
    rows = [row for row in jbeam[spec.MOD_ID]["nodes"]
            if isinstance(row, list) and row[0] != "id"]
    offset = len(rows) // 3
    rotated = rows[offset:] + rows[:offset]
    return next(index for index, row in enumerate(rotated)
                if row[0] == spec.AUDIO_EMITTER_NODE_NAME)


@pytest.fixture()
def rig():
    spec = load_spec()
    runtime_path = (
        PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions" / spec.MOD_ID
        / "runtime.lua"
    )
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    state = lua.execute(STUBS)
    # The node table resolveNodeCid asks for, with the emitter deliberately
    # NOT at cid 0 - see _vdata_stub.
    lua.execute(_vdata_stub(spec))
    module = lua.execute(runtime_path.read_text(encoding="utf-8"))
    return lua, state, module, spec


def runtime_source(spec) -> str:
    return (PACK_ROOT / MOD_KEY / "mod" / "lua" / "ge" / "extensions"
            / spec.MOD_ID / "runtime.lua").read_text(encoding="utf-8")


def shipped_ref_offset(spec) -> tuple[float, float, float]:
    """PROP_REF_OFFSET as the SHIPPED runtime carries it.

    Read rather than assumed, because it is the one number that pins the
    authored -> vehicle flip: the ref node is the ramp foot at authored
    (0, RAMP_Y0, 0) with RAMP_Y0 negative, and the shipped constant is
    (~0, -RAMP_Y0, 0). Anything else and the rig's frame is a fiction.
    """

    match = re.search(
        r"local PROP_REF_OFFSET = vec3\(([^)]*)\)", runtime_source(spec))
    assert match, "the shipped runtime has no PROP_REF_OFFSET"
    return tuple(float(part) for part in match.group(1).split(","))


# The authored -> mesh half turn about Z that lua_kit applies to every
# placement (MODEL_ALIGNMENT_ROTATION). Spawning the prop already turned by
# it makes modelRotation come out as identity THROUGH THE REAL ALGEBRA, so
# authored == world for every vector this file measures - and the two
# rotations are actually multiplied rather than assumed away.
MODEL_ALIGNMENT_QUAT = (0.0, 0.0, 1.0, 0.0)


def register_prop(state, module, spec):
    """Spawn the prop so its authored frame and the world frame coincide.

    runtime origin = position - vehicleRotation * PROP_REF_OFFSET, and
    modelRotation = MODEL_ALIGNMENT_ROTATION * vehicleRotation. Set the
    vehicle's own attitude to the alignment half turn and the two cancel,
    which leaves world = authored and origin = position + FLIP(refOffset).
    """

    offset = shipped_ref_offset(spec)
    # FLIP is a half turn about Z: it negates x and y and is its own inverse.
    spawn = (-offset[0], -offset[1], -offset[2])
    state.addVehicle(PROP_ID, spec.MOD_ID, spawn[0], spawn[1], spawn[2],
                     26.0, 46.0, 30.0)
    state.setVehicleRotation(PROP_ID, *MODEL_ALIGNMENT_QUAT)
    module.registerProp(PROP_ID)


def enter_zone(lua, state, module, zone, vehicle_id):
    name = f"{load_spec().MOD_ID}_p{PROP_ID}_{zone}"
    trigger = state.scene[name]
    module.onBeamNGTrigger(lua.table_from({
        "event": "enter",
        "triggerID": trigger.id,
        "triggerName": name,
        "subjectID": vehicle_id,
    }))


def status(module):
    return module.getSystemState(PROP_ID).behavior_status


def messages(state):
    """Every guihooks line the runtime has emitted, oldest first."""
    return [state.messages[index + 1] for index in range(len(state.messages))]


def errors(state):
    """Every E-level log record the runtime has emitted.

    emitError is the runtime's single failure channel, and until this helper
    existed nothing read it: a runtime that could not create a part, could
    not find a material or was handing the solver a NaN velocity every frame
    logged it faithfully and passed all 33 tests.
    """

    out = []
    for index in range(len(state.events)):
        record = state.events[index + 1]
        if record.level == "E":
            out.append(str(record.message))
    return out


def pose(state, spec, name):
    """A part's last recorded world transform, or None if never placed."""

    raw = state.partPose(spec.MOD_ID, PROP_ID, name)
    assert raw is not None, f"part {name!r} was never placed"
    values = [raw[index + 1] for index in range(10)]
    return {
        "position": tuple(values[0:3]),
        "rotation": tuple(values[3:7]),
        "scale": tuple(values[7:10]),
        "poses": raw[11],
    }


def part_angle(state, spec, name, axis):
    """The angle the runtime asked this part to turn through, about `axis`.

    The inverse of lua_kit's own axisAngle: a rotation of theta about a unit
    n is (n * sin(theta/2), cos(theta/2)), so theta = 2 * atan2(q.xyz . n,
    q.w). Reading it back this way needs no opinion about which direction the
    engine's quaternion operator rotates in - it measures the angle the
    runtime CONSTRUCTED, which is the angle the render shows.

    The pose recorded on the object is `pose.rotation * modelRotation`, and
    register_prop makes modelRotation the identity half-turn pair, so what
    comes back is pose.rotation itself up to an overall sign (q and -q are
    the same rotation); atan2 of the signed pair handles that.
    """

    q = pose(state, spec, name)["rotation"]
    # q and -q are the same rotation, and the recorded pose is
    # `pose.rotation * modelRotation` with modelRotation the NEGATED identity,
    # so half of these arrive sign-flipped. Put w on the positive side first
    # or the identity reads as a full turn.
    if q[3] < 0.0:
        q = tuple(-component for component in q)
    dot = q[0] * axis[0] + q[1] * axis[1] + q[2] * axis[2]
    # Off-axis content means this is not a single rotation about `axis` and
    # the answer would be meaningless, so say so rather than return a number.
    residual = math.sqrt(max(0.0, (q[0] ** 2 + q[1] ** 2 + q[2] ** 2) - dot ** 2))
    assert residual <= 1e-9, (
        f"{name} is not a pure rotation about {axis}: residual {residual:.3e}")
    return math.degrees(2.0 * math.atan2(dot, q[3]))


def angle_delta(measured, expected):
    """Signed degrees from expected to measured, wrapped to (-180, 180].

    part_angle returns a PRINCIPAL angle, so a needle asked for 250 degrees
    comes back as -110. Comparing through this keeps the tests honest about
    the fact that a rotation is an angle modulo a full turn.
    """

    return (measured - expected + 180.0) % 360.0 - 180.0


def tick(module, seconds=0.05, steps=1):
    for _ in range(steps):
        module.onPreRender(seconds, seconds, seconds)


def run_until(module, predicate, limit=4000, seconds=0.05):
    """Tick until ``predicate(status)`` holds; returns the elapsed sim time."""

    for step in range(limit):
        if predicate(status(module)):
            return step * seconds
        tick(module, seconds)
    raise AssertionError(
        f"never satisfied after {limit} ticks; phase={status(module).phase}")


def board_payload(lua, state, module, spec, position=None):
    """Put a stationary car on the cradle and announce it to both zones."""

    x, y, z = position or (0.0, 0.0, spec.HUB_Z - spec.PAYLOAD_R)
    state.addVehicle(SUBJECT_ID, "pickup", x, y, z)
    enter_zone(lua, state, module, "chamber_zone", SUBJECT_ID)
    enter_zone(lua, state, module, "cradle_zone", SUBJECT_ID)


def armour_traffic(state, vehicle_id=None):
    """Every armour chunk the GE side sent, as ("on"|"off", vehicle_id).

    The two chunks are told apart by what they DO, not by a marker comment:
    the pin writes math.huge, the restore writes a saved value back. A chunk
    that stopped doing either would fall out of this list rather than being
    silently reclassified.
    """

    out = []
    for index in range(len(state.vehCommands)):
        record = state.vehCommands[index + 1]
        text = str(record.command)
        if "spinLaunchArmour" not in text:
            continue
        kind = "on" if "math.huge" in text else "off"
        if vehicle_id is None or int(record.id) == vehicle_id:
            out.append((kind, int(record.id)))
    return out


def armour_chunk(state, kind):
    """The exact shipped text of one armour chunk."""

    for index in range(len(state.vehCommands)):
        record = state.vehCommands[index + 1]
        text = str(record.command)
        if "spinLaunchArmour" not in text:
            continue
        if (kind == "on") == ("math.huge" in text):
            return text
    raise AssertionError(f"no {kind!r} armour chunk was ever sent")


def test_registers_and_starts_idle(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    result = module.getSystemState(PROP_ID)
    assert result.registered is True
    assert result.trigger_count == 3
    # 28 kinematic parts, all created up front.
    assert result.part_count == 28
    assert status(module).phase == "idle"
    # Both collision parts start at an endpoint pose, so registration bakes.
    assert state.collisionReloads >= 1


# ---------------------------------------------------------------------------
# THE PLACEMENT SURFACE (item 1). Everything below reads the transforms the
# stub now records, and nothing below existed while setPosRot was a no-op.
#
# Two small quaternion helpers, written out in Python from first principles
# rather than imported from anywhere, so these gates re-derive the runtime's
# answer instead of restating it.
# ---------------------------------------------------------------------------
def q_axis_angle(axis, degrees):
    """(n sin(theta/2), cos(theta/2)) - the same thing lua_kit's axisAngle is."""

    half = math.radians(degrees) * 0.5
    length = math.sqrt(sum(component ** 2 for component in axis))
    sine = math.sin(half) / length
    return (axis[0] * sine, axis[1] * sine, axis[2] * sine, math.cos(half))


def q_hamilton(a, b):
    """a (x) b. The runtime's `a * b` means "apply a, then b" and IS this."""

    return (
        a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
        a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
        a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
        a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2],
    )


def rotate_x(degrees, point):
    """Rotate an authored-frame point about the chamber's own spin axis."""

    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return (point[0], point[1] * c - point[2] * s, point[1] * s + point[2] * c)


def carried_about_hub(spec, pivot, phi_deg):
    """Where a part bolted to the rotating assembly ends up.

    carryAboutHub moves the part's own authored pivot around the hub; this is
    the same statement written straight from the geometry.
    """

    relative = tuple(pivot[k] - spec.HUB[k] for k in range(3))
    moved = rotate_x(phi_deg, relative)
    return tuple(spec.HUB[k] + moved[k] for k in range(3))


def shipped_part_pivots(spec):
    """PART_SPECS as the SHIPPED runtime carries it: {name: (x, y, z)}."""

    found = {}
    for match in re.finditer(
        r"^\s+(\w+) = \{(?:collision = true, )?pivot = vec3\(([^)]*)\)",
        runtime_source(spec), re.MULTILINE,
    ):
        found[match.group(1)] = tuple(
            float(part) for part in match.group(2).split(","))
    return found


def lua_seq(table, count):
    """Values out of a Lua sequence. `list()` on one yields its KEYS."""

    return [table[index + 1] for index in range(count)]


def lua_rotate(state, quaternion, vector):
    return lua_seq(state.rotate(*quaternion, *vector), 3)


def lua_compose(state, first, second):
    return lua_seq(state.compose(*first, *second), 4)


def quats_equal(measured, expected, tolerance=1e-9):
    """q and -q are one rotation, so compare up to an overall sign."""

    same = all(abs(measured[k] - expected[k]) <= tolerance for k in range(4))
    flipped = all(abs(measured[k] + expected[k]) <= tolerance for k in range(4))
    return same or flipped


def test_the_rig_quaternion_algebra_is_the_engines(rig):
    """WITHOUT THIS, NO POSE BELOW MEANS ANYTHING.

    Two claims, both taken from lua_kit rather than invented here:

    - `basisQuat` builds the standard matrix quaternion of a local->world
      basis and returns its CONJUGATE, because its caller needs
      `rotation * offset` to come back as the world offset. So the vector
      operator must conjugate: q * v = conj(q) (x) v (x) q.
    - the placement tombstone says quats compose LEFT-TO-RIGHT
      (`MODEL_ALIGNMENT_ROTATION * vehicleRotation`, 18.880 m of measured
      error on a slope the other way round), which with the conjugating
      vector operator is exactly the plain Hamilton product.
    """

    lua, state, module, spec = rig

    # 1. The basisQuat round trip, worked by hand. A quarter turn about +Z
    #    carries +X onto +Y, so its local->world basis is
    #    ex = (0, 1, 0), ey = (-1, 0, 0), ez = (0, 0, 1), whose standard
    #    quaternion is (0, 0, sin45, cos45). basisQuat ships the conjugate.
    root_half = math.sqrt(0.5)
    stored = (0.0, 0.0, -root_half, root_half)
    turned = lua_rotate(state, stored, (1.0, 0.0, 0.0))
    assert turned == pytest.approx([0.0, 1.0, 0.0], abs=1e-12), turned

    # 2. Left-to-right composition, on two rotations that do NOT commute.
    first = q_axis_angle((1.0, 0.0, 0.0), 37.0)
    second = q_axis_angle((0.0, 1.0, 0.0), 61.0)
    probe = (0.3, -0.7, 0.45)
    composed = lua_rotate(state, lua_compose(state, first, second), probe)
    step_by_step = lua_rotate(state, second, lua_rotate(state, first, probe))
    assert composed == pytest.approx(step_by_step, abs=1e-12)
    # ...and the other order is genuinely different, or the claim is empty.
    other_way = lua_rotate(state, lua_compose(state, second, first), probe)
    assert max(abs(a - b) for a, b in zip(other_way, composed, strict=True)) > 0.05

    # 3. Python's re-derivation agrees with the Lua's, so the expected values
    #    the pose tests build below are the same algebra.
    assert lua_compose(state, first, second) == pytest.approx(
        list(q_hamilton(first, second)), abs=1e-12)


def test_the_rig_frame_is_the_shipped_ref_offset_and_authored_equals_world(rig):
    """The premise the whole file rests on, asserted instead of assumed.

    The ref node is the ramp foot at authored (0, RAMP_Y0, 0) and the shipped
    PROP_REF_OFFSET is its VEHICLE-frame position - the authored frame with x
    and y negated. Read one, derive the other. Then every part must land on
    its own authored pivot, which is only true if the model-alignment half
    turn really did cancel.
    """

    lua, state, module, spec = rig
    offset = shipped_ref_offset(spec)
    assert offset[1] == pytest.approx(-spec.RAMP_Y0, abs=1e-4), offset
    assert offset[2] == pytest.approx(0.0, abs=1e-4), offset

    register_prop(state, module, spec)
    pivots = shipped_part_pivots(spec)
    # 28 kinematic parts plus the one trigger spec the same table syntax
    # matches; the parts themselves are what getSystemState counts.
    parts = {name: pivot for name, pivot in pivots.items()
             if not name.endswith("_zone")}
    assert len(parts) == 28, sorted(parts)

    # Every part is placed, and placed where it was authored - except the
    # beacon, which rests SUNK in its housing (poseMachine's -0.40).
    for name, pivot in parts.items():
        placed = pose(state, spec, name)
        assert placed["poses"] >= 1, name
        expected = list(pivot)
        if name == "beacon":
            expected[2] -= 0.40
        for axis in range(3):
            assert placed["position"][axis] == pytest.approx(
                expected[axis], abs=1e-4), (name, placed["position"], expected)
        # ...and at rest nothing is turned: the machine is a still photograph.
        assert quats_equal(placed["rotation"], (0.0, 0.0, 0.0, 1.0), 1e-9), (
            name, placed["rotation"])


def test_the_launch_tube_and_its_muzzle_track_the_elevation_ladder(rig):
    """THE 33 m BARREL, MEASURED AT EVERY RUNG.

    tubePhi is the DIFFERENCE from the authored elevation, and the muzzle is
    carried around the hub by the same phi. Both are re-derived here from the
    printed ladder and the authored pivot, not from the runtime's expression.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    for index, elevation in enumerate(spec.TILT_STEPS_DEG, start=1):
        while status(module).tilt_index < index:
            module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_up")
        while status(module).tilt_index > index:
            module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_down")
        # Long enough for a rate-limited traverse to settle at any rung.
        tick(module, 0.05, 400)
        assert status(module).tilt_index == index

        phi = elevation - spec.TILT_REF_DEG
        measured = part_angle(state, spec, "tube", (1.0, 0.0, 0.0))
        assert angle_delta(measured, phi) == pytest.approx(0.0, abs=1e-6), (
            elevation, measured, phi)
        # The tube pivots about the chamber axis, so its own origin does not
        # move; the muzzle, bolted 35 m out, does.
        assert pose(state, spec, "tube")["position"] == pytest.approx(
            tuple(spec.HUB), abs=1e-4)
        expected = carried_about_hub(spec, spec.MUZZLE_PIVOT, phi)
        assert pose(state, spec, "muzzle")["position"] == pytest.approx(
            expected, abs=1e-4), (elevation, expected)


def test_the_tether_and_both_clamps_turn_as_one_assembly(rig):
    """The clamps are bolted to the cradle, so they orbit with it.

    Read at a real ride angle rather than at rest: the composition
    `localRot * spin` is a hinge about +Y carried by a spin about +X, and at
    theta = LOAD_THETA both of those are separately zero, which is the one
    place a broken composition looks fine.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup", limit=20000)
    tick(module, 0.05, 30)

    reading = status(module)
    theta = reading.theta_deg
    phi = theta - spec.LOAD_THETA_DEG
    assert abs(angle_delta(phi, 0.0)) > 5.0, "the tether never left the cradle"

    assert angle_delta(
        part_angle(state, spec, "tether", (1.0, 0.0, 0.0)), phi
    ) == pytest.approx(0.0, abs=1e-6)

    clamp_deg = reading.clamp * spec.BEHAVIOR["clamp_closed_deg"]
    spin = q_axis_angle((1.0, 0.0, 0.0), phi)
    for name, pivot, sense in (("clamp_l", spec.CLAMP_PIVOT_L, 1.0),
                               ("clamp_r", spec.CLAMP_PIVOT_R, -1.0)):
        placed = pose(state, spec, name)
        assert placed["position"] == pytest.approx(
            carried_about_hub(spec, pivot, phi), abs=1e-4), name
        hinge = q_axis_angle((0.0, 1.0, 0.0), sense * clamp_deg)
        assert quats_equal(placed["rotation"], q_hamilton(hinge, spin), 1e-9), (
            name, placed["rotation"], q_hamilton(hinge, spin))


def test_both_needles_rest_at_the_bottom_of_their_own_printed_scales(rig):
    """THE MID-SCALE AUTHORING BUG, now visible from here.

    Each pointer is AUTHORED at its rest reading, so poseMachine has to send
    the DIFFERENCE. Send the absolute angle instead and a machine that has
    never been touched reads 100 m/s and 50 kPa - which is what shipped. At
    rest the answer is therefore exactly zero, and at full scale it is
    exactly the printed sweep.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    tick(module, 0.05, 4)

    axis = (0.0, 1.0, 0.0)
    assert angle_delta(
        part_angle(state, spec, "needle_vel", axis), 0.0
    ) == pytest.approx(0.0, abs=1e-9)
    # vac rests at ATMOSPHERE, which is the zero end of its own travel.
    assert angle_delta(
        part_angle(state, spec, "needle_vac", axis), 0.0
    ) == pytest.approx(0.0, abs=1e-9)

    board_payload(lua, state, module, spec)
    for _ in range(len(spec.POWER_STEPS_MPS) - spec.POWER_NOM_INDEX):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_pwr_up")
    # Hard vacuum: the vac needle has to have swung the full sweep by then.
    run_until(module, lambda s: s.phase == "engaging", limit=20000)
    assert status(module).vac == pytest.approx(0.0, abs=1e-6)
    assert angle_delta(
        part_angle(state, spec, "needle_vac", axis), -spec.GAUGE_SWEEP_DEG
    ) == pytest.approx(0.0, abs=1e-6)

    # ...and the velocity needle reads the ride, on the scale it is printed
    # with: the top rung is 182 m/s against a 200 m/s dial, i.e. 91 percent of
    # a 250 degree sweep. Derived from the ladder and the dial, not from the
    # runtime's expression - a needle running backwards, or one on the wrong
    # sweep, lands somewhere else.
    run_until(module, lambda s: s.phase == "hold", limit=20000)
    speed = status(module).speed_mps
    assert speed == pytest.approx(spec.POWER_STEPS_MPS[-1], rel=1e-6)
    assert speed < spec.GAUGE_MAX_MPS, "the dial no longer covers the top rung"
    expected = spec.GAUGE_SWEEP_DEG * speed / spec.GAUGE_MAX_MPS
    assert angle_delta(
        part_angle(state, spec, "needle_vel", axis), expected
    ) == pytest.approx(0.0, abs=1e-4)


def _segment_authored_y(spec, name):
    """Mid-height y of a bar segment's own MESH, from the shipped DAE.

    The lit/unlit distinction is carved into the geometry - build_bar_segment
    authors every above-nominal block already translated back by
    bar_hidden_dy - so the pose alone cannot say whether a segment reads. Only
    mesh + pose can, and the mesh has to come from the artefact.
    """

    path = (PACK_ROOT / MOD_KEY / "mod" / "vehicles" / spec.MOD_ID
            / f"{spec.MOD_ID}_{name}.dae")
    for element in ElementTree.parse(path).iter():
        if element.tag.split("}")[-1] != "float_array":
            continue
        if not (element.get("id") or "").endswith("positions-array"):
            continue
        values = [float(token) for token in element.text.split()]
        ys = values[1::3]
        return 0.5 * (min(ys) + max(ys))
    raise AssertionError(f"no vertex positions in {path.name}")


@pytest.mark.parametrize("row, button, ladder", [
    ("pwr_seg", "btn_pwr", "POWER_STEPS_MPS"),
    ("tilt_seg", "btn_tilt", "TILT_STEPS_DEG"),
])
def test_the_bar_graphs_light_the_rung_the_console_prints(rig, row, button, ladder):
    """FOUR SEGMENTS THAT COULD NEVER LIGHT, caught from the outside.

    A lit block stands proud of the plate; an unlit one is translated
    bar_hidden_dy back through an opaque console body. Measured on the shipped
    DAEs 2026-08-25, pwr_seg5..8 carry y +0.095..+0.155 against pwr_seg1..4's
    -0.065..-0.005, and the runtime used to send the ABSOLUTE offset on top of
    that - 0.16 + 0.16 - so the top four rungs stayed in the cabinet at every
    setting and the row was frozen at nominal.

    This adds the mesh to the pose, which is what the eye does, and asserts
    the two planes: everything at or below the setting on one, everything
    above it exactly bar_hidden_dy behind.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    hidden = spec.BEHAVIOR["bar_hidden_dy"]
    pivots = shipped_part_pivots(spec)
    meshes = {index: _segment_authored_y(spec, f"{row}{index}")
              for index in range(1, 9)}
    # The authored hiding is real and is 0.16: without it there are no two
    # planes to be on and the rest of this test is vacuous.
    nominal = spec.BEHAVIOR[
        "power_nom_index" if row == "pwr_seg" else "tilt_nom_index"]
    assert meshes[8] - meshes[1] == pytest.approx(hidden, abs=1e-6), meshes
    assert meshes[nominal] == pytest.approx(meshes[1], abs=1e-6), meshes

    for setting in range(1, len(getattr(spec, ladder)) + 1):
        while status(module).power_index if row == "pwr_seg" else True:
            break
        current = (status(module).power_index if row == "pwr_seg"
                   else status(module).tilt_index)
        for _ in range(abs(setting - current)):
            module.pressPanelButtonByVehicle(
                PROP_ID, f"{button}_up" if setting > current else f"{button}_down")
        tick(module, 0.05, 2)

        faces = {}
        for index in range(1, 9):
            name = f"{row}{index}"
            placed = pose(state, spec, name)
            travel = placed["position"][1] - pivots[name][1]
            faces[index] = meshes[index] + travel
        lit = [faces[index] for index in range(1, setting + 1)]
        dark = [faces[index] for index in range(setting + 1, 9)]
        assert max(lit) - min(lit) < 1e-6, (setting, faces)
        for value in dark:
            assert value - lit[0] == pytest.approx(hidden, abs=1e-6), (
                setting, faces)


def test_the_deck_and_the_blast_door_travel_their_authored_strokes(rig):
    """Both are pure translation, and both are COLLISION parts.

    A deck that never actually moves leaves a floor under a car the tether is
    trying to swing, and a door that never actually moves is a vacuum chamber
    with the airlock open. Nothing in this file could see either.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    pivots = shipped_part_pivots(spec)
    assert pose(state, spec, "deck")["position"][2] == pytest.approx(
        pivots["deck"][2], abs=1e-6)

    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "evacuating", limit=20000)
    assert status(module).door_close == pytest.approx(1.0)
    assert pose(state, spec, "door")["position"][2] == pytest.approx(
        pivots["door"][2] - spec.BEHAVIOR["door_travel"], abs=1e-6)

    run_until(module, lambda s: s.phase == "spinup", limit=20000)
    assert pose(state, spec, "deck")["position"][2] == pytest.approx(
        pivots["deck"][2] - spec.BEHAVIOR["deck_drop"], abs=1e-6)


def test_the_warning_beacon_stands_up_when_the_machine_is_live(rig):
    """Sunk in its housing at rest, up and turning whenever it can hurt you."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    pivots = shipped_part_pivots(spec)
    parked = pose(state, spec, "beacon")["position"][2]
    assert parked == pytest.approx(pivots["beacon"][2] - 0.40, abs=1e-6)

    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup", limit=20000)
    tick(module, 0.05, 60)
    assert pose(state, spec, "beacon")["position"][2] == pytest.approx(
        pivots["beacon"][2], abs=1e-6)
    # ...and it is TURNING, which the lamps read off the same angle.
    first = part_angle(state, spec, "beacon", (0.0, 0.0, 1.0))
    tick(module, 0.05, 3)
    assert abs(angle_delta(
        part_angle(state, spec, "beacon", (0.0, 0.0, 1.0)), first)) > 1.0
    assert state.lampField(spec.MOD_ID, PROP_ID, "beacon_glow", "isEnabled") == "1"


def test_a_nominal_sequence_never_logs_an_error(rig):
    """NEARLY FREE, AND IT WOULD HAVE CAUGHT REAL FAULTS.

    emitError is the runtime's single failure channel - a material that would
    not resolve, a part that would not create, a trigger that never
    registered, a velocity that came out NaN - and this rig captured every one
    of them into a list nothing read. A runtime emitting E-level records on
    every frame passed all 33 tests in this file.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    assert errors(state) == [], errors(state)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "arming", limit=500)
    run_until(module, lambda s: s.phase == "recover", limit=20000)
    state.removeVehicle(SUBJECT_ID)
    run_until(module, lambda s: s.phase == "idle", limit=20000)
    tick(module, 0.05, 200)
    assert errors(state) == [], errors(state)


def test_an_abort_never_logs_an_error_either(rig):
    """The other path, which is the one that runs when something is wrong."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup", limit=20000)
    tick(module, 0.05, 20)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_abort")
    run_until(module, lambda s: s.phase == "idle", limit=20000)
    tick(module, 0.05, 100)
    assert errors(state) == [], errors(state)


# ---------------------------------------------------------------------------
# WHO GETS THROWN, AND WHEN (items 3 and 5).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("on_the_bed", [SUBJECT_ID, 42])
def test_the_payload_is_the_car_nearest_the_cradle_not_whichever_pairs_yields(
    rig, on_the_bed
):
    """THE SELECTION WAS MADE BY pairs(), WHOSE ORDER LUA DOES NOT DEFINE.

    Two cars in a 14 m cradle box: one on the bed, one 5 m up the tunnel. The
    old firstOccupant walked the zone table with pairs() and returned
    whichever the hash order offered, so the machine could seal, evacuate and
    throw the wrong one at 182 m/s - and could pick differently on a
    different run, or on a different machine.

    Run BOTH WAYS ROUND on purpose. The lower id is announced first every
    time, so the case that puts the HIGHER id on the bed is the one a
    sorted-by-id selection would fail, and the case that puts the lower id on
    the bed is the one a last-announced selection would fail. Only "nearest
    the cradle" passes both.

    Read off getStatus rather than by arming, because with two cars in the
    disc the machine correctly REFUSES to arm at all now (see the chamber
    interlock below). The selection still has to be right: it is what ABORT's
    refusal latch keys on, and it is what the machine takes the moment the
    second car leaves.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    seat = (0.0, 0.0, spec.HUB_Z - spec.PAYLOAD_R)
    up_the_tunnel = (0.0, 5.0, seat[2])

    for vehicle_id in (SUBJECT_ID, 42):
        where = seat if vehicle_id == on_the_bed else up_the_tunnel
        state.addVehicle(vehicle_id, "pickup", *where)
        enter_zone(lua, state, module, "chamber_zone", vehicle_id)
        enter_zone(lua, state, module, "cradle_zone", vehicle_id)

    tick(module, 0.05, 4)
    assert status(module).aboard == 2
    assert status(module).cradle_candidate_id == on_the_bed, (
        status(module).cradle_candidate_id)
    # ...and once the other car is gone, that IS the car it takes.
    other = 42 if on_the_bed == SUBJECT_ID else SUBJECT_ID
    state.removeVehicle(other)
    tick(module, 0.05, 4)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_launch")
    assert status(module).payload_id == on_the_bed, status(module).payload_id


def test_the_arm_countdown_starts_again_when_the_candidate_changes(rig):
    """CAR B MUST NOT INHERIT CAR A'S THREE SECONDS.

    b.armTimer accumulated on `counting` and never on candidate IDENTITY. Car
    A stands on the cradle for 2.9 s; car B arrives nearer the bed; the
    selection returns B, `counting` is still true, and the timer crosses
    arm_delay_s on the next frame - so B is committed after 0.05 s, having
    been announced about A.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    seat = (0.0, 0.0, spec.HUB_Z - spec.PAYLOAD_R)

    state.addVehicle(SUBJECT_ID, "pickup", seat[0], seat[1] + 5.0, seat[2])
    enter_zone(lua, state, module, "chamber_zone", SUBJECT_ID)
    enter_zone(lua, state, module, "cradle_zone", SUBJECT_ID)
    # 2.9 s of A's countdown: one frame short of committing.
    steps = int((spec.BEHAVIOR["arm_delay_s"] - 0.1) / 0.05)
    tick(module, 0.05, steps)
    assert status(module).phase == "arming", status(module).phase

    # B arrives, nearer the bed. It must serve its own three seconds - and
    # the machine must not commit on the very next frame.
    state.addVehicle(42, "pickup", *seat)
    enter_zone(lua, state, module, "cradle_zone", 42)
    tick(module, 0.05, 2)
    assert status(module).phase == "arming", status(module).phase
    assert status(module).payload_id is None
    # Two thirds of the delay later it is still counting, not committed.
    tick(module, 0.05, int(spec.BEHAVIOR["arm_delay_s"] * 0.6 / 0.05))
    assert status(module).payload_id is None, "B inherited A's countdown"
    # ...and it does eventually commit, on B.
    run_until(module, lambda s: s.phase == "sealing", limit=400)
    assert status(module).payload_id == 42


def test_the_machine_will_not_arm_into_a_chamber_holding_a_wreck(rig):
    """AN ABORT AT 182 m/s LEAVES A CAR LOOSE IN THE CHAMBER BY DESIGN.

    The arm condition tested the cradle box, the speed, the door pin and the
    refusal latch, and never asked whether the chamber was clear. Drive the
    next car in and the tether swings a payload round a 15.9 m circle through
    wherever the wreck came to rest - and the tether has no collision, so the
    arm ghosts through the wreck while the payload does not.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    seat = (0.0, 0.0, spec.HUB_Z - spec.PAYLOAD_R)

    # The wreck: inside the disc, nowhere near the cradle bed.
    state.addVehicle(99, "pickup", 0.0, -12.0, spec.HUB_Z - 14.0)
    enter_zone(lua, state, module, "chamber_zone", 99)
    # ...and a fresh car on the bed.
    board_payload(lua, state, module, spec, position=seat)
    assert status(module).aboard == 2
    assert status(module).chamber_clear is False

    # Auto-detect must refuse, for as long as anyone cares to wait.
    tick(module, 0.05, int(spec.BEHAVIOR["arm_delay_s"] * 4 / 0.05))
    assert status(module).phase == "idle", status(module).phase
    assert any("chamber is not clear" in line for line in messages(state))
    # ...and so must the button.
    module.pressPanelButtonByVehicle(PROP_ID, "btn_launch")
    assert status(module).phase == "idle", status(module).phase

    # Clear the wreck and the same car arms normally.
    state.removeVehicle(99)
    tick(module, 0.05, 2)
    assert status(module).chamber_clear is True
    run_until(module, lambda s: s.phase == "sealing", limit=400)
    assert status(module).payload_id == SUBJECT_ID


# ---------------------------------------------------------------------------
# THE TRAVERSE (item 4).
# ---------------------------------------------------------------------------
def test_the_launch_tube_traverses_instead_of_teleporting(rig):
    """A 33.5 m BARREL MOVED 3.69 m BETWEEN TWO FRAMES.

    tubePhi was computed straight from the selected elevation with no rate
    limit, while every other moving part on the machine is rate-limited and
    the console printed "Tube traversing." Measured at the bore mouth, which
    is hypot(PAYLOAD_R + TUBE_BORE_R, TUBE_S1) = 35.22 m from the pivot.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    lever = math.hypot(spec.PAYLOAD_R + spec.TUBE_BORE_R, spec.TUBE_S1)
    rate = spec.BEHAVIOR["tube_traverse_deg_s"]
    dt = 0.05

    start = part_angle(state, spec, "tube", (1.0, 0.0, 0.0))
    # The whole ladder in one press-storm: bottom rung to top rung.
    for _ in range(len(spec.TILT_STEPS_DEG)):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_up")
    assert status(module).tilt_index == len(spec.TILT_STEPS_DEG)

    previous, worst, elapsed = start, 0.0, 0.0
    for _ in range(1000):
        tick(module, dt)
        elapsed += dt
        current = part_angle(state, spec, "tube", (1.0, 0.0, 0.0))
        worst = max(worst, abs(angle_delta(current, previous)))
        previous = current
        if status(module).tube_aligned:
            break
    target = spec.TILT_STEPS_DEG[-1] - spec.TILT_REF_DEG
    assert angle_delta(previous, target) == pytest.approx(0.0, abs=1e-4)

    # No frame may move it faster than the rate says, and the bore mouth's
    # speed follows from that: 2.5 deg/s is 1.54 m/s at 35.22 m.
    assert worst <= rate * dt + 1e-9, worst
    assert lever * math.radians(worst / dt) <= 1.60, worst
    # ...and it really did take the time a traverse takes: 22 degrees of
    # ladder at 2.5 deg/s is 8.8 s, not one frame.
    span = spec.TILT_STEPS_DEG[-1] - spec.TILT_STEPS_DEG[spec.TILT_NOM_INDEX - 1]
    assert elapsed >= 0.9 * span / rate, elapsed
    assert elapsed <= 1.2 * span / rate + 0.2, elapsed


def test_the_release_will_not_fire_down_a_barrel_that_is_still_moving(rig):
    """The hazard the rate limit would otherwise have introduced.

    releaseTheta is derived from the SETTING, so a machine that fired while
    the tube was still traversing would aim the tangent at an elevation the
    bore has not reached. The interlock freezes the setting at `spinup`, and
    this asserts the other half: the crossing test does not run until the
    barrel has arrived.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    # The worst case the interlock still permits, arranged deliberately: the
    # SLOWEST power rung, so spin-up is 4.40 s rather than 12.9, and the full
    # 38-degree ladder committed on the first frame of `engaging`, which is
    # the last phase in which ELEVATION is still settable. Measured on this
    # rig: `release` opens 12.6 s later, and 38 deg at 2.5 deg/s is 15.2 s,
    # so the barrel still has about 2.6 s to run when the muzzle finishes
    # opening.
    for _ in range(spec.POWER_NOM_INDEX - 1):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_pwr_down")
    # Park the barrel at the BOTTOM rung first and let it get there, so the
    # slam below is the whole 38-degree ladder and not the 22 degrees from
    # nominal. Sealing plus evacuation is 9.6 s; 16 degrees at 2.5 deg/s is
    # 6.4 s, so it arrives with room to spare.
    for _ in range(len(spec.TILT_STEPS_DEG)):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_down")
    run_until(module, lambda s: s.phase == "engaging", limit=20000)
    assert status(module).tube_deg == pytest.approx(
        spec.TILT_STEPS_DEG[0], abs=1e-3), status(module).tube_deg
    for _ in range(len(spec.TILT_STEPS_DEG)):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_up")
    assert status(module).tilt_index == len(spec.TILT_STEPS_DEG)

    # Watch every frame of `release`. The ride field and the launch both go
    # through applyClusterVelocityScaleAdd with scale 0, so "did it fire" is
    # not readable off the velocity stream - the phase edge is. The claim is
    # therefore a timing one: the release cannot COMPLETE before the barrel
    # arrives.
    run_until(module, lambda s: s.phase == "release", limit=20000)
    assert status(module).tube_aligned is False, (
        "the barrel had already arrived; this test would prove nothing")
    aligned_at, left_at = None, None
    for step in range(2000):
        tick(module, 0.05)
        reading = status(module)
        if aligned_at is None and reading.tube_aligned:
            aligned_at = step
        if reading.phase != "release":
            left_at = step
            break
    assert aligned_at is not None, "the barrel never arrived"
    assert left_at is not None, "the release never ended"
    assert left_at >= aligned_at, (
        f"fired on frame {left_at}, barrel arrived on frame {aligned_at}")
    assert status(module).phase == "recover", status(module).phase

    # ...and the shot it eventually took is aimed where the ladder says.
    assert status(module).tube_aligned is True
    assert status(module).tube_deg == pytest.approx(
        spec.TILT_STEPS_DEG[-1], abs=1e-3)
    launch = state.lastVelocity()
    assert launch is not None
    elevation = math.degrees(math.atan2(
        launch.z, math.hypot(launch.x, launch.y)))
    assert elevation == pytest.approx(spec.TILT_STEPS_DEG[-1], abs=1e-4)


def test_elevation_is_locked_wherever_power_is(rig):
    """The two interlocks were asymmetric: POWER from `spinup`, ELEVATION
    only in `release`. A 33.5 m barrel could be slewed across the launch slot
    with the tether at 182 m/s and the payload committed."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    for phase in ("spinup", "hold", "release"):
        if status(module).phase != phase:
            run_until(module, lambda s, p=phase: s.phase == p, limit=20000)
        before = status(module).tilt_index
        module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_up")
        module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_down")
        assert status(module).tilt_index == before, phase
        assert any("ELEVATION LOCKED" in line for line in messages(state)), phase


def test_the_beacon_mast_rises_instead_of_popping(rig):
    """The tube's defect one order of magnitude smaller: a hard 0.40 m jump
    between the two poses on the frame the phase changed."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    pivots = shipped_part_pivots(spec)
    rise = spec.BEHAVIOR["beacon_rise_m"]
    speed = spec.BEHAVIOR["beacon_rise_mps"]
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "arming", limit=400)

    previous = pose(state, spec, "beacon")["position"][2]
    worst, elapsed = 0.0, 0.0
    for _ in range(200):
        tick(module, 0.05)
        elapsed += 0.05
        current = pose(state, spec, "beacon")["position"][2]
        worst = max(worst, abs(current - previous) / 0.05)
        previous = current
        if current >= pivots["beacon"][2] - 1e-9:
            break
    assert previous == pytest.approx(pivots["beacon"][2], abs=1e-9)
    assert worst <= speed + 1e-9, worst
    # 0.40 m at 0.50 m/s is 0.80 s, and it has to be inside the countdown it
    # is a warning for.
    assert elapsed == pytest.approx(rise / speed, abs=0.06), elapsed
    assert elapsed < spec.BEHAVIOR["arm_delay_s"]


def test_auto_detect_needs_a_car_that_has_actually_stopped(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    # Rolling across the pad at 6 m/s must NOT commit the machine, however
    # long it stays inside the box.
    state.setSpeed(SUBJECT_ID, 6.0)
    tick(module, 0.05, int(spec.BEHAVIOR["arm_delay_s"] / 0.05) + 40)
    assert status(module).phase == "idle"

    state.setSpeed(SUBJECT_ID, 0.0)
    # ARMING IS A REAL PHASE NOW. It is entered on the first tick the car
    # reads stopped, and arm_delay_s is the LENGTH of that phase - not a
    # silent gap before "sealing". Before the fix "arming" was read twice
    # and assigned nowhere, so the countdown emitted no message, the beacon
    # stayed sunk in its housing and the status lamp stayed green for three
    # seconds. `phase != "idle"` is therefore no longer the right question.
    armed = run_until(module, lambda s: s.phase == "arming")
    assert armed <= 0.10, armed
    elapsed = armed + run_until(module, lambda s: s.phase == "sealing")
    assert (0.9 * spec.BEHAVIOR["arm_delay_s"]
            <= elapsed <= 1.6 * spec.BEHAVIOR["arm_delay_s"]), elapsed
    assert status(module).phase == "sealing"
    assert any("PAYLOAD ON THE CRADLE" in line for line in messages(state))


def test_sequence_walks_every_phase_in_order(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)

    seen = []
    for _ in range(6000):
        phase = status(module).phase
        if not seen or seen[-1] != phase:
            seen.append(phase)
        if len(seen) > 1 and phase == "idle":
            break
        tick(module)
    assert seen == [
        "idle", "arming", "sealing", "evacuating", "engaging", "spinup",
        "hold", "release", "recover", "idle",
    ], seen


def test_the_chamber_actually_seals_and_evacuates(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)

    run_until(module, lambda s: s.phase == "evacuating")
    assert status(module).door_close == pytest.approx(1.0)
    run_until(module, lambda s: s.phase == "engaging")
    # Hard vacuum before the deck moves, deck fully down before the spin.
    assert status(module).vac == pytest.approx(0.0)
    run_until(module, lambda s: s.phase == "spinup")
    assert status(module).deck_drop == pytest.approx(spec.BEHAVIOR["deck_drop"])
    assert status(module).clamp == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# THE PICKUP. Three assertions on the one part of this machine where the
# field's command is not simply "go round".
#
# Live 2026-08-25 at the 82 m/s rung, the payload's orbit radius peaked at
# 19.12 m against a seated 16.28 m - 2.84 m of sag during `engaging`, then a
# catch on the first frame of `spinup`. The RIDE was clean on the same run
# (15.83-15.91 m against PAYLOAD_R 15.90 for every revolution) and the 182 m/s
# shot, which only samples from `spinup`, peaked at 15.92 m. So the defect is
# the pickup, and it is a defect of the control LAW - which is exactly what
# this module can prove.
#
# What it CANNOT prove, stated once so nobody reads more into these numbers
# than is there: the magnitude of the live sag. That came from a car resting
# on a collision surface that was sinking under it while only its ref-node
# cluster was velocity-driven, and none of soft body, collision or gravity
# exists here. These three gates pin the law - the rate limit is on the AIM,
# the spring's authority is NOT clipped, and the deck waits for the load -
# and the live gate's `orbit_max <= CHAMBER_R` still owns the outcome.
# ---------------------------------------------------------------------------
PICKUP_DRAW_MPS = 3.5           # LUA_BODY's own constant, read from the source
PICKUP_TAKEUP_MAX_S = 3.0       # ditto: the take-up watchdog


def field_command(state, vehicle_id):
    """The last velocity the field set on one vehicle this tick, or None."""

    for index in reversed(range(state.velocityCount())):
        record = state.velocities[index + 1]
        if record.id == vehicle_id:
            return (record.x, record.y, record.z)
    return None


def follow_field(state, module, position, seconds=0.05):
    """One tick with the payload OBEYING the field, and the command it got.

    The runtime's actuator is ``applyClusterVelocityScaleAdd(ref, 0, v)`` - a
    hard velocity SET, once per frame. Integrating the stub payload at exactly
    that velocity is therefore the ideal actuator, which is the one the
    runtime believes it has. It is not BeamNG: the real cluster is a handful
    of nodes out of a hundred and fifty, and the rest of the car drags it.
    That difference is the live gate's business. This closes the loop the
    CONTROL LAW runs in, so a proportional term can be told apart from a
    clipped one.
    """

    state.clearVelocities()
    module.onPreRender(seconds, seconds, seconds)
    command = field_command(state, SUBJECT_ID)
    if command is not None:
        position = tuple(p + v * seconds for p, v
                         in zip(position, command, strict=True))
        state.movePayload(SUBJECT_ID, *position)
    return position, command


def drive_to_engaging(lua, state, module, spec, offset=(0.0, 0.0, 0.0)):
    """Seat a payload (optionally parked off the cradle) and reach `engaging`.

    The seat is the tether point itself rather than the 0.40 m lower spot a
    real car's ref node settles at, because nothing here has suspension; the
    OFFSET is what each test is actually about.
    """

    seat = (offset[0], offset[1], spec.HUB_Z - spec.PAYLOAD_R + offset[2])
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec, position=seat)
    run_until(module, lambda s: s.phase == "engaging", limit=20000)
    return seat


def test_the_pickup_draws_a_car_parked_off_the_cradle_in_at_a_walking_pace(rig):
    """THE SNAP THE RATE LIMIT EXISTS TO PREVENT, still prevented.

    The tracking term is a spring in velocity space, so an unlimited one hands
    a car parked 2 m off the cradle ``2.0 * track_gain`` = 32 m/s on the first
    frame of engage, with the car still sitting on the deck. That is a
    teleport. The limit now lives on the AIM instead of on the output, and a
    ramp cannot step - so the command tops out at the ramp's own rate plus the
    spring's steady-state lag, and the payload still arrives.
    """

    lua, state, module, spec = rig
    seat = drive_to_engaging(lua, state, module, spec, offset=(0.0, 2.0, 0.0))
    target = (0.0, 0.0, spec.HUB_Z - spec.PAYLOAD_R)
    assert math.dist(seat, target) == pytest.approx(2.0)

    # `engaging` ONLY. The moment the tether starts turning the field is
    # commanding an orbit at up to 182 m/s and the draw limit is deliberately
    # inert; measuring past that boundary measures the ride, not the pickup.
    position, worst = seat, 0.0
    for _ in range(400):
        if status(module).phase != "engaging":
            break
        position, command = follow_field(state, module, position)
        if command is not None:
            worst = max(worst, math.dist((0.0, 0.0, 0.0), command))
    assert status(module).phase == "spinup", status(module).phase
    # 5 percent over the ramp rate: the spring is tracking a ramp, so its
    # command settles AT the ramp rate, not above it.
    assert worst <= PICKUP_DRAW_MPS * 1.05, worst
    # ...and it is a pickup, not a refusal to move.
    assert math.dist(position, target) <= 0.05, (position, target)


def test_the_pickup_is_not_clipped_when_the_payload_falls_away_from_it(rig):
    """THE SAG. This is the assertion the live 19.12 m reading bought.

    Once the aim has arrived on the tether point the spring is the ONLY thing
    holding the payload, and the old code clipped it to PICKUP_DRAW_MPS for as
    long as the tether was still at the load pose - i.e. for the whole of
    `engaging`, which is precisely the window in which the floor leaves. A
    2 m miss got 3.5 m/s of answer whether it was a car parked 2 m away or a
    car 2 m into a fall. Authority has to be proportional to the miss.
    """

    lua, state, module, spec = rig
    drive_to_engaging(lua, state, module, spec)
    target = (0.0, 0.0, spec.HUB_Z - spec.PAYLOAD_R)

    # Let the aim arrive - the deck starting to move is the machine's own
    # statement that it has.
    position = target
    for _ in range(int(PICKUP_TAKEUP_MAX_S / 0.05) + 20):
        position, _command = follow_field(state, module, position)
        if status(module).deck_drop > 0.0:
            break
    assert status(module).deck_drop > 0.0, status(module).deck_drop

    # Now drop the payload 2 m, which is what a retracting deck does to a car
    # the field is not really holding, and read what the field asks for.
    sagged = (position[0], position[1], position[2] - 2.0)
    state.movePayload(SUBJECT_ID, *sagged)
    state.clearVelocities()
    tick(module)
    command = field_command(state, SUBJECT_ID)
    assert command is not None
    answer = math.dist((0.0, 0.0, 0.0), command)
    gain = min(spec.BEHAVIOR["track_gain"], 0.8 / 0.05)
    # 90 percent of the proportional answer, which is 2.0 * 16.0 = 32.0 m/s.
    # The clipped version returned PICKUP_DRAW_MPS = 3.5 here, every frame,
    # however far the payload had fallen.
    assert answer >= 0.9 * 2.0 * gain, (answer, gain)
    # Up, not sideways: the miss is purely radial at bottom-dead-centre.
    assert command[2] > 0.0, command


def test_the_aim_cannot_walk_away_from_a_payload_that_is_not_following(rig):
    """The hole the setpoint ramp opens, closed.

    Moving the limit off the output and onto the aim bounds the command for
    as long as the payload keeps up. This rig's vehicles never move at all,
    which makes it the perfect stand-in for one that CANNOT - wedged on the
    retracting deck, jammed against a clamp - and without the lead guard the
    aim walks off at PICKUP_DRAW_MPS while the uncapped spring turns the
    growing gap into track_gain times it. Nothing is integrated here on
    purpose.
    """

    lua, state, module, spec = rig
    drive_to_engaging(lua, state, module, spec, offset=(0.0, 3.0, 0.0))

    worst = 0.0
    for _ in range(int(PICKUP_TAKEUP_MAX_S / 0.05) + 60):
        state.clearVelocities()
        tick(module)
        command = field_command(state, SUBJECT_ID)
        if command is None:
            break
        worst = max(worst, math.dist((0.0, 0.0, 0.0), command))
    gain = min(spec.BEHAVIOR["track_gain"], 0.8 / 0.05)
    # PICKUP_LEAD_M * track_gain = 8.0 m/s, plus one frame of ramp travel
    # (3.5 * 0.05 = 0.175 m, another 2.8 m/s) because the guard is applied
    # after the step rather than before it.
    assert worst <= (0.50 + PICKUP_DRAW_MPS * 0.05) * gain, worst
    # Un-guarded this reaches the full 3.0 m offset: 48 m/s.
    assert worst < 0.5 * 3.0 * gain, worst


def test_the_load_deck_waits_until_the_field_has_taken_the_payload(rig):
    """TAKE THE LOAD, THEN TAKE THE FLOOR AWAY.

    The deck used to start retracting on the same frame the field first ran,
    on the argument that this meant the car was never unsupported. It does
    not: the field is a velocity constraint on the ref-node cluster and the
    deck is a collision surface sinking at deck_drop / deck_seconds = 1.5 m/s
    under a car that is sitting on it. The gate is the field's own aim, so it
    cannot drift away from what the field is actually doing, and it converges
    in gap / PICKUP_DRAW_MPS seconds for any gap - hence no wedge, and hence
    a watchdog rather than a timeout as the fallback.
    """

    lua, state, module, spec = rig
    seat = drive_to_engaging(lua, state, module, spec, offset=(0.0, 1.0, 0.0))

    # First frame of engage: the field is already working and the floor has
    # not moved.
    state.clearVelocities()
    tick(module)
    assert field_command(state, SUBJECT_ID) is not None
    assert status(module).deck_drop == 0.0, status(module).deck_drop

    position, opened = seat, None
    for step in range(int(PICKUP_TAKEUP_MAX_S / 0.05) + 40):
        position, _command = follow_field(state, module, position)
        if opened is None and status(module).deck_drop > 0.0:
            opened = (step + 2) * 0.05
    assert opened is not None, "the deck never retracted"
    # A 1.0 m gap is 1.0 / 3.5 = 0.286 s of ramp plus 3 / track_gain = 0.188 s
    # of settle. The watchdog must not be what opened it.
    assert 0.30 <= opened <= 0.75, opened
    assert opened < PICKUP_TAKEUP_MAX_S, opened


@pytest.mark.parametrize("tilt_index", [1, 4, 8])
def test_launch_speed_and_elevation_match_the_console(rig, tilt_index):
    """THE aiming identity: theta_release = 90 + elevation.

    Measured, not asserted from the same expression the runtime uses: the
    expected direction here is built straight from the elevation in degrees
    that the console prints.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)

    # Lowest power rung keeps the spin-up short; the aiming claim is
    # independent of speed and the speed claim is checked on the same shot.
    for _ in range(spec.POWER_NOM_INDEX - 1):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_pwr_down")
    for _ in range(abs(tilt_index - spec.TILT_NOM_INDEX)):
        module.pressPanelButtonByVehicle(
            PROP_ID,
            "btn_tilt_up" if tilt_index > spec.TILT_NOM_INDEX else "btn_tilt_down")
    assert status(module).power_index == 1
    assert status(module).tilt_index == tilt_index

    run_until(module, lambda s: s.phase == "release")
    state.clearVelocities()
    run_until(module, lambda s: s.phase == "recover")

    launch = state.lastVelocity()
    assert launch is not None
    # Scale 0 is a REPLACE, which is what a launch must be.
    assert launch.scale == 0
    speed = math.sqrt(launch.x ** 2 + launch.y ** 2 + launch.z ** 2)
    expected_speed = spec.POWER_STEPS_MPS[0]
    assert speed == pytest.approx(expected_speed, rel=1e-6)

    elevation = math.radians(spec.TILT_STEPS_DEG[tilt_index - 1])
    assert launch.x == pytest.approx(0.0, abs=1e-9)
    assert launch.y == pytest.approx(expected_speed * math.cos(elevation), rel=1e-6)
    assert launch.z == pytest.approx(expected_speed * math.sin(elevation), rel=1e-6)


def test_release_window_is_not_missed_at_full_power(rig):
    """At the top rung the tether steps ~33 degrees per tick.

    An equality test on the release angle - or a window narrower than one
    step - sails straight past it on most passes, and the machine would spin
    forever holding a payload it can never let go of. The crossing test has
    to be a WRAPPED comparison, so this asserts the throw lands within a
    single revolution of the muzzle opening.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    for _ in range(len(spec.POWER_STEPS_MPS) - spec.POWER_NOM_INDEX):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_pwr_up")
    assert status(module).power_index == len(spec.POWER_STEPS_MPS)

    run_until(module, lambda s: s.phase == "release", limit=8000)
    omega = status(module).omega
    revolution = 2.0 * math.pi / omega
    state.clearVelocities()
    elapsed = run_until(module, lambda s: s.phase == "recover", limit=8000)
    # muzzle travel plus at most one full pass.
    assert elapsed <= spec.BEHAVIOR["muzzle_seconds"] + revolution + 0.2
    assert elapsed < spec.BEHAVIOR["release_timeout_s"]

    launch = state.lastVelocity()
    speed = math.sqrt(launch.x ** 2 + launch.y ** 2 + launch.z ** 2)
    assert speed == pytest.approx(spec.POWER_STEPS_MPS[-1], rel=1e-6)


def test_power_and_elevation_are_locked_once_the_tether_is_at_speed(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup")

    before = status(module).power_index
    module.pressPanelButtonByVehicle(PROP_ID, "btn_pwr_up")
    assert status(module).power_index == before

    run_until(module, lambda s: s.phase == "release", limit=8000)
    tilt_before = status(module).tilt_index
    module.pressPanelButtonByVehicle(PROP_ID, "btn_tilt_up")
    assert status(module).tilt_index == tilt_before


def test_abort_cuts_the_field_and_returns_the_machine_to_idle(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup")
    tick(module, 0.05, 40)

    module.pressPanelButtonByVehicle(PROP_ID, "btn_abort")
    assert status(module).phase == "abort"
    state.clearVelocities()
    tick(module, 0.05, 4)
    # An abort is an E-STOP: the field lets go THIS frame, so nothing more is
    # written to the payload's velocity.
    assert state.velocityCount() == 0

    run_until(module, lambda s: s.phase == "idle", limit=8000)
    result = status(module)
    assert result.door_close == pytest.approx(0.0)
    assert result.deck_drop == pytest.approx(0.0)
    assert result.vac == pytest.approx(1.0)
    # The tether indexes back to the load position before the deck returns.
    assert result.theta_deg == pytest.approx(spec.LOAD_THETA_DEG, abs=1e-6)


def test_purge_throws_whatever_is_aboard(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    state.clearVelocities()
    module.pressPanelButtonByVehicle(PROP_ID, "btn_purge")
    launch = state.lastVelocity()
    assert launch is not None and launch.scale == 0
    assert launch.z == pytest.approx(spec.BEHAVIOR["purge_up_mps"], rel=1e-6)
    horizontal = math.sqrt(launch.x ** 2 + launch.y ** 2)
    assert horizontal == pytest.approx(spec.BEHAVIOR["purge_out_mps"], rel=1e-6)


def test_a_node_excursion_quarantines_the_payload(rig):
    """The field must stop feeding a solver that is already losing the car."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup")

    state.setHalfExtent(SUBJECT_ID, spec.BEHAVIOR["safety_node_dist"] * 3.0)
    tick(module, 0.05, int(spec.BEHAVIOR["safety_check_interval"] / 0.05) + 4)
    state.clearVelocities()
    tick(module, 0.05, 10)
    assert state.velocityCount() == 0


def test_a_payload_outside_the_chamber_is_never_field_held(rig):
    """chamber_zone occupancy alone lies; the radial gate is the authority."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup")

    # Same zone membership, but parked well outside the disc.
    state.addVehicle(99, "pickup", 0.0, -60.0, 0.0)
    enter_zone(lua, state, module, "chamber_zone", 99)
    state.clearVelocities()
    tick(module, 0.05, 6)
    touched = {state.velocities[index + 1].id
               for index in range(state.velocityCount())}
    assert touched == {SUBJECT_ID}


def test_only_the_payload_is_ever_held_or_fired(rig):
    """A second car inside the disc must not be dragged into the payload.

    Measured on the shipped runtime 2026-08-24: a car parked 3.0 m off the
    cradle during spinup was handed (0, -169.5, +169.9) - 240.0 m/s, which
    is field_speed_cap_mps exactly - on the first frame the field saw it,
    and was then fired down the tube alongside the payload.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup")
    tick(module, 0.05, 60)
    # Second car, on the deck, well inside the 20.4 m bore.
    state.addVehicle(42, "pickup", 0.0, 3.0, spec.HUB_Z - spec.PAYLOAD_R + 0.2)
    enter_zone(lua, state, module, "chamber_zone", 42)
    assert status(module).aboard == 2
    assert status(module).payload_id == SUBJECT_ID

    state.clearVelocities()
    tick(module, 0.05, 4)
    held = {state.velocities[index + 1].id
            for index in range(state.velocityCount())}
    assert held == {SUBJECT_ID}, held

    state.clearVelocities()
    run_until(module, lambda s: s.phase == "recover", limit=8000)
    fired = {state.velocities[index + 1].id
             for index in range(state.velocityCount())}
    assert fired == {SUBJECT_ID}, fired


def test_purge_is_interlocked_against_the_running_sequence(rig):
    """PURGE at 182 m/s threw the payload at a shut airlock.

    Measured on the shipped runtime: the press replaced the ride velocity
    with (0, -26.00, +34.00) while door_close read 1.00, latched
    b.launched so the field let go, left the phase alone, and the machine
    fired an empty tether 1.4 s later.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    for _ in range(len(spec.POWER_STEPS_MPS) - spec.POWER_NOM_INDEX):
        module.pressPanelButtonByVehicle(PROP_ID, "btn_pwr_up")
    run_until(module, lambda s: s.phase == "release", limit=8000)
    assert status(module).door_close == pytest.approx(1.0)

    state.clearVelocities()
    module.pressPanelButtonByVehicle(PROP_ID, "btn_purge")
    assert state.velocityCount() == 0
    assert status(module).phase == "release"

    run_until(module, lambda s: s.phase == "recover", limit=8000)
    launch = state.lastVelocity()
    speed = math.sqrt(launch.x ** 2 + launch.y ** 2 + launch.z ** 2)
    assert speed == pytest.approx(spec.POWER_STEPS_MPS[-1], rel=1e-6)


def test_resetting_the_prop_clears_the_pinned_airlock(rig):
    """behavior.reset IS behavior.init, so init must clear doorManual.

    Measured on the shipped runtime: after DOOR + reset the door snapped to
    0 for one frame and drove straight back to 1.00, and the machine never
    saw the stopped car on the cradle.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_door")
    tick(module, 0.05, 80)
    assert status(module).door_close == pytest.approx(1.0)
    assert status(module).door_manual is True

    module.onVehicleResetted(PROP_ID)
    assert status(module).door_manual is False
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "sealing", limit=400)


def test_manual_start_will_not_commit_an_empty_machine(rig):
    """b.payloadId is nil in idle; the old code armed with it anyway."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_launch")
    assert status(module).phase == "idle"

    board_payload(lua, state, module, spec)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_launch")
    assert status(module).phase == "sealing"
    assert status(module).payload_id == SUBJECT_ID


def test_abort_cannot_pin_the_machine_out_of_service(rig):
    """Each abort reset b.timer, and idle needs b.timer >= recover_hold_s.

    Measured on the shipped runtime: ABORT every 0.5 s for 60 simulated
    seconds never reached idle and logged 121 aborts for one sequence.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup")
    module.pressPanelButtonByVehicle(PROP_ID, "btn_abort")
    reached = None
    for step in range(1200):                      # 60 s of sim
        tick(module, 0.05)
        if step % 10 == 0:                        # 0.5 s < recover_hold_s
            module.pressPanelButtonByVehicle(PROP_ID, "btn_abort")
        if status(module).phase == "idle":
            reached = step * 0.05
            break
    assert reached is not None
    assert module.getSystemState(PROP_ID).behavior_stats.aborts == 1


def test_losing_the_payload_mid_ride_recovers_the_machine(rig):
    """Two routes out: the event, and the watchdog for when there is none."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup")
    tick(module, 0.05, 40)
    module.onVehicleResetted(SUBJECT_ID)          # lua_kit -> onSubjectGone
    assert status(module).phase == "recover"
    run_until(module, lambda s: s.phase == "idle", limit=8000)


def test_a_payload_that_simply_vanishes_trips_the_watchdog(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup")
    tick(module, 0.05, 40)
    state.removeVehicle(SUBJECT_ID)               # no event at all
    # Grace is one safety_check_interval - reused, not a new tunable.
    tick(module, 0.05, int(spec.BEHAVIOR["safety_check_interval"] / 0.05) + 4)
    assert status(module).phase == "recover"


def test_a_quarantined_payload_no_longer_fires_an_empty_tether(rig):
    """Extends test_a_node_excursion_quarantines_the_payload by one claim."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup")
    state.setHalfExtent(SUBJECT_ID, spec.BEHAVIOR["safety_node_dist"] * 3.0)
    run_until(module, lambda s: s.phase == "recover", limit=400)


def test_abort_during_arming_cancels_instead_of_recovering(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "arming")
    module.pressPanelButtonByVehicle(PROP_ID, "btn_abort")
    assert status(module).phase == "idle"
    # And it stays cancelled: the same car parked in the same place must not
    # simply re-arm three seconds later, or the button reads as broken.
    tick(module, 0.05, int(spec.BEHAVIOR["arm_delay_s"] / 0.05) + 60)
    assert status(module).phase == "idle"


def test_registration_bakes_collision_exactly_once(rig):
    """init already bakes this pose; a nil latch baked it a second time.

    be:reloadCollision is a whole-level rebuild. Measured on the shipped
    runtime: 1 reload after registerProp, 2 after a single tick.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    tick(module, 0.05, 20)
    assert state.collisionReloads == 1


def test_the_release_timeout_is_a_stop_not_a_second_trigger(rig):
    """Analytic bound on release latency, and what the timeout does now.

    muzzle_seconds + one revolution at the slowest rung is the worst a
    healthy machine can do; if the crossing test has not fired by
    release_timeout_s the tether is not where the tube is, and firing would
    aim the tangent into the shell.
    """

    lua, state, module, spec = rig
    bound = (spec.BEHAVIOR["muzzle_seconds"]
             + 2.0 * math.pi * spec.PAYLOAD_R / spec.POWER_STEPS_MPS[0])
    assert bound == pytest.approx(4.968, abs=0.01)
    assert bound < 0.4 * spec.BEHAVIOR["release_timeout_s"]

    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    for _ in range(spec.POWER_NOM_INDEX - 1):     # slowest rung = worst case
        module.pressPanelButtonByVehicle(PROP_ID, "btn_pwr_down")
    run_until(module, lambda s: s.phase == "release", limit=20000)
    elapsed = run_until(module, lambda s: s.phase == "recover", limit=20000)
    assert elapsed <= bound
    assert module.getSystemState(PROP_ID).behavior_stats.aborts == 0


# ---------------------------------------------------------------------------
# THE CUE SET (CP-5). Static gates live in tests/test_spin_launch_audio.py;
# what only this rig can prove is the ORDER cues are dispatched in and - the
# one a live run genuinely cannot check, because you cannot hear a leaked
# source over a running one - that no loop is left playing when the machine
# comes back to rest.
# ---------------------------------------------------------------------------

CUE_CALL = re.compile(
    r"extensions\.\w+_vehicle\.(slAudio\w+)\(\s*(?:\"([\w]+)\")?")


def cues(state):
    """Every audio dispatch the GE side has sent, as (verb, cue name).

    Reads the same queueLuaCommand stream the vehicle VM would: this is the
    only observable the bridge has, which is exactly why the stub records it.
    """

    out = []
    for index in range(len(state.luaCommands)):
        match = CUE_CALL.search(state.luaCommands[index + 1])
        if match:
            out.append((match.group(1), match.group(2)))
    return out


def cue_names(state, verb=None):
    return [name for method, name in cues(state)
            if name is not None and (verb is None or method == verb)]


def loops_left_on(module):
    """Cue names whose GE-side latch is still true, straight off getStatus.

    A latch that is true with the machine idle is a source nothing will ever
    stop - and the same field is readable live, so this assertion transfers
    to the game unchanged.
    """

    latched = status(module).audio_loops or ""
    return sorted(name for name in latched.split(",") if name)


def test_every_phase_edge_dispatches_its_cue_in_order(rig):
    """The eight beats, in the order the machine plays them.

    This is the assertion that makes the module docstring's claim - that
    every step has its own sound-of-machinery beat - a MEASUREMENT. Note the
    stub must actually be recording: without a queueLuaCommand that captures,
    audioSend's own pcall swallows the whole set and this passes vacuously,
    so the first assertion is that anything arrived at all.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "arming", limit=200)
    run_until(module, lambda s: s.phase == "idle", limit=20000)

    played = cue_names(state, "slAudioPlay") + [
        name for method, name in cues(state) if method == "slAudioSet"
        and name == "stage_tick"]
    assert state.luaCommands, "the rig never recorded a queueLuaCommand"
    assert played, "no cue was ever dispatched"

    # Order of FIRST appearance, one entry per cue, ignoring the automation
    # pushes that ride between them.
    ordered, seen = [], set()
    for method, name in cues(state):
        if name is None or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    assert ordered == [
        "arm_charge",     # the 3 s hold
        "detect_klaxon",  # committed
        "door_travel",    # the blast door
        "door_slam",      # shut in
        "pump_down",      # 7 s of evacuation
        "hard_vacuum",    # it arrives
        "deck_retract",   # the floor leaves
        "clamp_close",    # the cradle takes your weight
        "spin_loop",      # the ride
        "stage_tick",     # eight rungs
        "muzzle_open",    # the hatch
        "release_alarm",  # the interlock
        "release_bang",   # separation
        "shutdown",       # power down
        "repress",        # air comes back
    ], ordered
    # abort_klaxon is the sixteenth and correctly absent: nothing aborted.
    assert "abort_klaxon" not in ordered
    # One tick per rung of STAGE_FRACS, no more and no fewer.
    ticks = [name for method, name in cues(state)
             if method == "slAudioSet" and name == "stage_tick"]
    assert len(ticks) == 8, ticks


def test_no_loop_is_left_playing_when_the_machine_returns_to_idle(rig):
    """The failure a live run cannot hear.

    Every loop here is started by a latch and stopped by one, and the ride is
    a bed that can run for 28 seconds. A latch left true after the sequence
    ends is a source with no handle in the next sequence's state - the
    machine hums from across the map and nothing in the log says so.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "arming", limit=500)
    run_until(module, lambda s: s.phase == "recover", limit=20000)
    # The payload has left down the tube. Take it out of the roster before
    # running on, or the machine correctly notices the car still sitting on
    # the cradle and starts arming again - and this assertion would be
    # measuring a live countdown rather than a leak. (Asserting at rest with
    # a car still aboard is how this test passed VACUOUSLY when it was
    # written: run_until("idle") returns on step 0, because idle is where the
    # machine starts.)
    state.removeVehicle(SUBJECT_ID)
    run_until(module, lambda s: s.phase == "idle", limit=20000)
    tick(module, 0.05, 200)
    assert status(module).phase == "idle"
    assert loops_left_on(module) == []
    # ...and every loop that was started was also stopped, exactly once each.
    started = cue_names(state, "slAudioPlay")
    stopped = cue_names(state, "slAudioStop")
    loops = {name for name, stop, _volume in spec.AUDIO_CUE_TABLE if stop is None}
    assert any(started.count(name) for name in loops), "no loop ever started"
    for name in loops:
        assert started.count(name) == stopped.count(name), name


def test_an_abort_mid_spin_silences_the_ride(rig):
    """The other half of the same property, on the path most likely to break
    it: ABORT during spin-up leaves the bed running on purpose (it spins
    DOWN under the klaxon), and enterRecover is the single funnel that has to
    silence both."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup", limit=20000)
    tick(module, 0.05, 20)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_abort")
    run_until(module, lambda s: s.phase == "abort", limit=200)
    tick(module, 0.05)          # run_until stops ON the edge, before the body
    assert "abort_klaxon" in cue_names(state, "slAudioPlay")
    run_until(module, lambda s: s.phase == "recover", limit=20000)
    state.removeVehicle(SUBJECT_ID)
    run_until(module, lambda s: s.phase == "idle", limit=20000)
    tick(module, 0.05, 200)
    assert loops_left_on(module) == []
    assert "shutdown" in cue_names(state, "slAudioPlay")
    # The ride was never fired: an abort must not sound like a launch.
    assert "release_bang" not in cue_names(state, "slAudioPlay")


def test_resetting_the_prop_silences_everything_it_can_still_reach(rig):
    """A reset mid-spin is the single most likely thing a player does on this
    machine. behavior.reset calls behavior.init, which clears the three latch
    tables AND tells the vehicle VM to stop every source it still holds - the
    GE side cannot know which ids exist, so it has to ask."""

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "spinup", limit=20000)
    tick(module, 0.05, 20)      # run_until stops ON the edge, before the body
    assert "spin_loop" in cue_names(state, "slAudioPlay")
    module.onVehicleResetted(PROP_ID)
    assert status(module).phase == "idle"
    assert loops_left_on(module) == []
    assert any(method == "slAudioStopAll" for method, _name in cues(state))


def test_the_audio_emitter_node_is_resolved_by_name_and_pushed(rig):
    """THE EMITTER, END TO END, ON THE SHIPPED RUNTIME.

    The static gate in test_spin_launch_audio.py proves the NAME is in both
    halves of the Lua and that the node it names is in the chamber. This one
    proves the mechanism: that the GE side actually asks resolveNodeCid for
    it, gets the cid the engine would give, and pushes THAT to the vehicle VM
    - against a stub whose cid order is deliberately not the jbeam's, which
    is the fact the shipped `AUDIO_NODE = 0` was wrong about.

    A runtime that went back to authoring a literal index would still pass
    every other test in this file, because nothing else here looks at where
    the sound comes from.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    tick(module, steps=4)

    wanted = expected_emitter_cid(spec)
    assert wanted != 0, "the stub must not put the emitter at cid 0"
    pushed = [command for index in range(len(state.luaCommands))
              for command in (state.luaCommands[index + 1],)
              if "slAudioNode" in command]
    assert pushed, "the GE side never resolved the audio emitter node"
    assert f"slAudioNode({wanted})" in pushed[0], pushed[0]
    # ...once, not once a frame: this is a latch, and every push is a
    # queueLuaCommand that drops and rebuilds every source on the far side.
    assert len(pushed) == 1, pushed


# ---------------------------------------------------------------------
# Payload armour.
# ---------------------------------------------------------------------
#
# The field drives the ref-node CLUSTER only, so the rest of the car is
# hauled round a 15.9 m circle by its own beams and carries the whole of
# v^2/r - 43 g on the nominal rung, 212 g on POWER 8. Before B.payload_armour
# the machine delivered a wreck to the muzzle and then threw it.


def test_the_armour_chunk_pins_every_beam_and_remembers_what_it_pinned(rig):
    """Execute the SHIPPED chunk against a stub vehicle VM.

    Asserting that a string was sent proves nothing about what the string
    does. This runs the real text through lupa with a stub obj/v and checks
    the two things that matter: every beam ends unbreakable, and the value
    it had first is kept somewhere the restore can find it.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_launch")
    run_until(module, lambda s: s.phase == "sealing", limit=400)
    # The sync is a frame-loop diff, so the send lands on the tick AFTER the
    # phase flips, not on the flip itself.
    tick(module, steps=4)

    vm = lupa.LuaRuntime(unpack_returned_tuples=True)
    vm.execute("""
      applied = {}
      v = {data = {beams = {
        {cid = 0, beamDeform = 12000, beamStrength = 34000},
        {cid = 1, beamDeform = 500,   beamStrength = 900},
        {cid = 2},
      }}}
      obj = {
        setBeamDeform = function(_, cid, value)
          applied[#applied + 1] = {"deform", cid, value}
        end,
        setBeamStrength = function(_, cid, value)
          applied[#applied + 1] = {"strength", cid, value}
        end,
      }
    """)
    vm.execute(armour_chunk(state, "on"))

    applied = vm.eval("applied")
    writes = {(str(applied[i + 1][1]), int(applied[i + 1][2])): applied[i + 1][3]
              for i in range(len(applied))}
    # The two fully specified beams are pinned on both properties.
    for cid in (0, 1):
        assert writes[("deform", cid)] == float("inf"), cid
        assert writes[("strength", cid)] == float("inf"), cid
    # A beam whose jbeam carried neither property is left completely alone -
    # inventing a limit for it would be a change, not a freeze.
    assert ("deform", 2) not in writes
    assert ("strength", 2) not in writes
    # And the originals are held for the restore.
    saved = vm.eval("spinLaunchArmour")
    assert saved[0][1] == 12000 and saved[0][2] == 34000
    assert saved[1][1] == 500 and saved[1][2] == 900


def test_the_restore_hands_back_the_car_s_own_numbers_and_never_a_default(rig):
    """FREEZE, NEVER REPAIR.

    The point of the machine is the landing. A restore that wrote defaults -
    or that skipped a beam - would hand back a car that crashes like some
    other car, and a car driven in already dented has to launch dented.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_launch")
    run_until(module, lambda s: s.phase == "sealing", limit=400)
    # The sync is a frame-loop diff, so the send lands on the tick AFTER the
    # phase flips, not on the flip itself. Abort to make the machine emit the
    # restore chunk as well, so both halves under test are the shipped text.
    tick(module, steps=4)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_abort")
    tick(module, steps=4)

    vm = lupa.LuaRuntime(unpack_returned_tuples=True)
    vm.execute("""
      applied = {}
      v = {data = {beams = {
        {cid = 7, beamDeform = 1234, beamStrength = 5678},
        {cid = 9, beamDeform = 4321},
      }}}
      obj = {
        setBeamDeform = function(_, cid, value)
          applied[#applied + 1] = {"deform", cid, value}
        end,
        setBeamStrength = function(_, cid, value)
          applied[#applied + 1] = {"strength", cid, value}
        end,
      }
    """)
    vm.execute(armour_chunk(state, "on"))
    vm.execute("applied = {}")
    vm.execute(armour_chunk(state, "off"))

    applied = vm.eval("applied")
    writes = {(str(applied[i + 1][1]), int(applied[i + 1][2])): applied[i + 1][3]
              for i in range(len(applied))}
    assert writes[("deform", 7)] == 1234
    assert writes[("strength", 7)] == 5678
    assert writes[("deform", 9)] == 4321
    # Beam 9 never had a strength, so it must not acquire one on the way out.
    assert ("strength", 9) not in writes
    # And the VM is left clean, so a second ride re-reads the real values
    # rather than restoring math.huge over them for ever.
    assert vm.eval("spinLaunchArmour") is None


def test_a_car_merely_parked_on_the_cradle_is_never_pinned(rig):
    """arming is not a commitment.

    The driver can still pull off the cradle during the countdown. Pinning
    there would let anyone collect an indestructible car by driving in,
    waiting two seconds and leaving.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    run_until(module, lambda s: s.phase == "arming", limit=400)
    tick(module, steps=20)

    assert status(module).phase == "arming"
    assert armour_traffic(state) == []


def test_the_payload_is_pinned_for_the_ride_and_freed_for_the_landing(rig):
    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_launch")

    run_until(module, lambda s: s.phase == "sealing", limit=400)
    tick(module, steps=4)
    assert armour_traffic(state, SUBJECT_ID) == [("on", SUBJECT_ID)], (
        "the payload was not pinned when it committed")

    # Through the whole loaded ride it stays pinned exactly once - the sync
    # is a diff, not a resend, so a per-frame call must not spam the VM.
    run_until(module, lambda s: s.phase == "spinup", limit=20000)
    assert armour_traffic(state, SUBJECT_ID) == [("on", SUBJECT_ID)]

    # WHEN the restore lands, not merely that it eventually does: a car freed
    # late is a car that lands rigid, and at 180 m/s a short flight is the
    # whole flight.
    #
    # It lands one tick into "recover", and that is as early as the machine
    # can manage: launching the car, clearing b.payloadId and leaving the
    # "release" phase all happen in the same frame, so the earliest sync that
    # can see any of it is the next one. That coincidence also makes the
    # b.launched guard in armourSubject defensive rather than load-bearing -
    # deleting it changes no outcome here, because payloadId and the phase
    # have already both said no. It is kept because it is the guard that
    # states the actual rule.
    launched_at, seen_release = None, False
    for index in range(40000):
        tick(module)
        phase = str(status(module).phase)
        if phase == "release":
            seen_release = True
        elif seen_release and launched_at is None:
            launched_at = index
        if armour_traffic(state, SUBJECT_ID)[-1][0] == "off":
            break
    else:
        raise AssertionError("the car was never handed its structure back")
    assert launched_at is not None
    assert index - launched_at <= 1, (
        f"the car flew rigid for {index - launched_at} frames after launch")

    run_until(module, lambda s: s.phase == "idle", limit=40000)
    assert armour_traffic(state, SUBJECT_ID) == [
        ("on", SUBJECT_ID), ("off", SUBJECT_ID)], (
        "the launched car was not handed its structure back")


@pytest.mark.parametrize("ending", ["abort", "prop_reset", "subject_gone"])
def test_no_ending_leaves_a_car_permanently_indestructible(rig, ending):
    """The failure that matters is not a dent, it is a car that drives away
    invincible for the rest of the session.

    Three ways a ride can end other than a launch. Each has to give the
    structure back, and the machine has to stop believing it holds one.
    """

    lua, state, module, spec = rig
    register_prop(state, module, spec)
    board_payload(lua, state, module, spec)
    module.pressPanelButtonByVehicle(PROP_ID, "btn_launch")
    run_until(module, lambda s: s.phase == "spinup", limit=20000)
    assert armour_traffic(state, SUBJECT_ID) == [("on", SUBJECT_ID)]

    if ending == "abort":
        module.pressPanelButtonByVehicle(PROP_ID, "btn_abort")
    elif ending == "prop_reset":
        module.onVehicleResetted(PROP_ID)
    else:
        module.onVehicleResetted(SUBJECT_ID)
    tick(module, steps=4)

    assert armour_traffic(state, SUBJECT_ID)[-1] == ("off", SUBJECT_ID), (
        f"{ending} left the car pinned")
    assert not errors(state)
