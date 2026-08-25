"""Generate a Giant Props GELua runtime extension from the handoff + spec.

Every mod's ``runtime.lua`` is produced from one shared template so the ten
contraptions stay behaviourally consistent: the same trigger lifecycle,
transform synchronization, reset handling, and mission cleanup that the
Cannon Car Wash proved live. Subject-mutation helpers are capability-gated;
physics-only props omit them entirely. Only the ``behavior`` chunk — each
mod's anticipation state machine — differs, and its geometry constants come
from the same Blender handoff the JBeam was built from.

Design rules carried over from AGENTS.md:

- Scenario behaviour lives in a per-mod GELua extension loaded on demand by
  the prop's vehicle bootstrap; there is no global ``modScript.lua``.
- Triggers are transient, namespaced, non-saveable ``BeamNGTrigger`` objects
  using ``onBeamNGTrigger`` with exact object and vehicle identity checks.
- Trigger containment mode is selected per interaction; vehicle-size-agnostic
  parking zones may deliberately use ``Overlaps`` plus an exact position test.
- All runtime objects are removed on unregister/destruction/mission teardown.
  Props that opt into subject mutation must keep every injected velocity
  finite and derive it from live measured state.
"""

from __future__ import annotations

from typing import Any


def lua_number(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    number = float(value)
    if number == int(number) and abs(number) < 1e15:
        return f"{number:.1f}"
    return repr(number)


def lua_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return lua_number(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        if len(value) == 3 and all(isinstance(item, (int, float)) for item in value):
            return f"vec3({lua_number(value[0])}, {lua_number(value[1])}, {lua_number(value[2])})"
        items = ", ".join(lua_value(item) for item in value)
        return "{" + items + "}"
    if isinstance(value, dict):
        items = ", ".join(f"{key} = {lua_value(item)}" for key, item in sorted(value.items()))
        return "{" + items + "}"
    raise TypeError(f"cannot serialize to Lua: {value!r}")


def lua_table(entries: dict[str, Any], indent: str = "  ") -> str:
    lines = []
    for key, value in sorted(entries.items()):
        lines.append(f"{indent}{key} = {lua_value(value)},")
    return "\n".join(lines)


def generate_runtime(mod_id: str, display_name: str, handoff: dict[str, Any], spec: Any) -> str:
    behavior = handoff["behavior"]
    tunables = behavior.get("tunables", {})
    triggers = behavior.get("triggers", {})
    effects = behavior.get("effects", {})

    part_entries: dict[str, Any] = {}
    for part in handoff.get("parts", []):
        entry: dict[str, Any] = {
            "shape": f"/vehicles/{mod_id}/{mod_id}_{part['name']}.dae",
            "pivot": part["pivot_world"],
        }
        if part.get("collision"):
            entry["collision"] = True
        part_entries[part["name"]] = entry

    trigger_entries: dict[str, Any] = {}
    for suffix, trigger in triggers.items():
        mode = trigger["mode"]
        if mode not in ("Contains", "Overlaps"):
            raise ValueError(f"unsupported trigger mode for {suffix}: {mode}")
        trigger_entries[suffix] = {
            "position": trigger["center"],
            "scale": trigger["dimensions"],
            "mode": mode,
        }

    effect_entries: dict[str, Any] = {}
    for suffix, effect in effects.items():
        effect_entries[suffix] = {
            "emitter": effect["emitter"],
            "position": effect["position"],
            "direction": effect["direction"],
        }

    referenced_materials: set[str] = set(handoff["visual"]["materials"])
    for part in handoff.get("parts", []):
        referenced_materials.update(part.get("materials", []))

    extension_name = f"{mod_id}/runtime".replace("_", "__").replace("/", "_")
    camel = "".join(part.capitalize() for part in mod_id.split("_"))
    behavior_chunk = spec.LUA_BEHAVIOR.strip("\n")

    material_lines = "\n".join(f'  "{name}",' for name in sorted(referenced_materials))
    subject_mutation_helpers = r"""local function launchSubject(state, vehicle, velocity)
  if not finiteVector3(velocity) then
    emitError(state, "launch_velocity_not_finite")
    return false
  end
  local launched, launchError = pcall(function()
    vehicle:applyClusterVelocityScaleAdd(
      vehicle:getRefNodeId(), 0, velocity.x, velocity.y, velocity.z
    )
  end)
  if not launched then
    emitError(state, "velocity_injection_failed", {detail = tostring(launchError)})
    return false
  end
  emitEvent(state, "I", "subject_launched", {
    subject_id = vehicle:getId(),
    velocity_x = velocity.x,
    velocity_y = velocity.y,
    velocity_z = velocity.z,
  })
  return true
end

local function addSubjectVelocity(state, vehicle, delta)
  if not finiteVector3(delta) then return false end
  local ok = pcall(function()
    vehicle:applyClusterVelocityScaleAdd(
      vehicle:getRefNodeId(), 1, delta.x, delta.y, delta.z
    )
  end)
  return ok
end

local function teleportSubject(state, vehicle, position, rotation)
  if not finiteVector3(position) then
    emitError(state, "teleport_position_not_finite")
    return false
  end
  local moved, moveError = pcall(function()
    vehicle:setPositionRotation(
      position.x, position.y, position.z,
      rotation.x, rotation.y, rotation.z, rotation.w
    )
  end)
  if not moved then
    emitError(state, "teleport_failed", {detail = tostring(moveError)})
    return false
  end
  emitEvent(state, "I", "subject_teleported", {subject_id = vehicle:getId()})
  return true
end"""
    if not getattr(spec, "ALLOW_SUBJECT_MUTATION", True):
        subject_mutation_helpers = (
            "-- Subject velocity and teleport primitives intentionally omitted "
            "for this physics-only prop."
        )

    template = r"""local M = {}

-- Generated by examples/giant_props/proplib/lua_kit.py. Do not hand-edit;
-- change the mod's spec.py / Blender generator and rebuild.

local LOG_TAG = "@LOG_TAG@"
local PROP_MODEL = "@MOD_ID@"
local DISPLAY_NAME = "@DISPLAY_NAME@"
local UI_CATEGORY = "@MOD_ID@_messages"
local TRIGGER_CLASS = "BeamNGTrigger"
local PART_CLASS = "TSStatic"
local EFFECT_CLASS = "ParticleEmitterNode"
local VISUAL_MATERIALS_PATH = "vehicles/@MOD_ID@/main.materials.json"
local REQUIRED_VISUAL_MATERIALS = {
@REQUIRED_MATERIALS@
}

-- The prop's spawn position is its REF NODE's world position. When the ref
-- node is not at the authored origin (e.g. the vacuum's deck centre), every
-- authored-frame placement must subtract the ref node's vehicle-frame
-- position or all triggers/effects land offset from the geometry (proven
-- live 2026-07-22: the vacuum's zones sat 6 m off).
local PROP_REF_OFFSET = @REF_OFFSET@
local MODEL_ALIGNMENT_ROTATION = quat(0, 0, 1, 0)

-- The jbeam refNodes, with the authored vehicle-frame position of each. These
-- are the live datum for every placement (see propFrame).
local FRAME_NODES = @FRAME_NODES@

local PART_SPECS = {
@PART_SPECS@
}

local TRIGGER_SPECS = {
@TRIGGER_SPECS@
}

local EFFECT_SPECS = {
@EFFECT_SPECS@
}

-- Authored behaviour constants from the Blender handoff (single source of
-- truth shared with the generated JBeam).
local B = {
@TUNABLES@
}

local installations = {}
local triggerOwners = {}
local sessionCounter = 0
local extensionUnloading = false

local function integer(value)
  return type(value) == "number" and value == math.floor(value)
end

local function finiteNumber(value)
  return type(value) == "number" and value == value
    and value ~= math.huge and value ~= -math.huge
end

local function finiteVector3(value)
  return value
    and finiteNumber(value.x)
    and finiteNumber(value.y)
    and finiteNumber(value.z)
end

-- Lua's pairs() has UNSPECIFIED order, so the sequence in which parts and
-- effects were built varied between machines and between runs. That is fine
-- while everything works and miserable the moment one of them misbehaves:
-- "Charlie's Catapult Seesaw" shipped 2026-08-14 with future-dated ZIP
-- members, BeamNG treated every shipped Collada as permanently newer than
-- its .cdae cache and re-imported forever, and TSStatic::_createShape
-- substituted /core/art/shapes/no_mesh.dae for whichever shape happened to
-- still be in flight. On the machine that filmed it that was the winch, so
-- the placeholder text inherited the winch's spool rotation and span with
-- it. The date bug is fixed in packaging.py; this makes WHICH part loses
-- such a race deterministic, so the next one reproduces instead of
-- depending on whose hash order it is.
local function sortedKeys(map)
  local keys = {}
  for key in pairs(map) do keys[#keys + 1] = key end
  table.sort(keys)
  return keys
end

local function emitEvent(state, level, event, fields)
  local record = {
    schema_version = 1,
    event = event,
    mode = "giant_prop",
    prop_model = PROP_MODEL,
    prop_id = state and state.propId or nil,
    session = sessionCounter,
  }
  for key, value in pairs(fields or {}) do record[key] = value end
  local encodedOk, encoded = pcall(jsonEncode, record)
  if encodedOk then
    log(level, LOG_TAG, encoded)
  else
    log("E", LOG_TAG, "runtime telemetry encoding failed")
  end
end

local function emitError(state, reason, fields)
  local payload = fields or {}
  payload.reason = reason
  emitEvent(state, "E", "error", payload)
end

local function showMessage(message, ttl)
  guihooks.message({txt = message}, ttl or 1.5, UI_CATEGORY)
end

local function exactVehicle(vehicleId)
  if not integer(vehicleId) then return nil end
  local vehicle = be:getObjectByID(vehicleId)
  if not vehicle or vehicle:getId() ~= vehicleId then return nil end
  return vehicle
end

local function isSelfProp(vehicle)
  if not vehicle then return false end
  local ok, model = pcall(function() return vehicle:getJBeamFilename() end)
  return ok and model == PROP_MODEL
end

local function eligibleSubject(vehicleId)
  if installations[vehicleId] then return nil end
  local vehicle = exactVehicle(vehicleId)
  if not vehicle or isSelfProp(vehicle) then return nil end
  return vehicle
end

local function axisAngle(axis, angle)
  local direction = vec3(axis.x, axis.y, axis.z)
  if direction:length() < 0.000001 then return quat(0, 0, 0, 1) end
  direction:normalize()
  local half = angle * 0.5
  local sine = math.sin(half)
  return quat(direction.x * sine, direction.y * sine, direction.z * sine, math.cos(half))
end

-- The game does NOT assign node cids in jbeam row order (fixed nodes are
-- renumbered ahead of free ones — probed live 2026-07-23), so any authored
-- row index is wrong at runtime: resolve cids by node NAME from vdata and
-- cache per name. Returns nil (and retries next call) until vdata is ready.
local function resolveNodeCid(state, nodeName)
  state.nodeCids = state.nodeCids or {}
  local cached = state.nodeCids[nodeName]
  if cached then return cached end
  local ok, data = pcall(function()
    return core_vehicle_manager.getVehicleData(state.propId)
  end)
  local nodes = ok and data and data.vdata and data.vdata.nodes or nil
  if not nodes then return nil end
  for _, node in pairs(nodes) do
    if node.name == nodeName then
      state.nodeCids[nodeName] = node.cid
      return node.cid
    end
  end
  return nil
end

-- World position of one named cage node, or nil until vdata is ready.
-- getNodePosition is relative to the vehicle datum, so the sum tracks the
-- LIVE node even while the object transform itself is stale.
local function nodeWorldPosition(state, vehicle, position, nodeName)
  local cid = resolveNodeCid(state, nodeName)
  if not cid then return nil end
  local ok, relative = pcall(function() return vehicle:getNodePosition(cid) end)
  if not ok or not relative or not finiteVector3(relative) then return nil end
  return vec3(position.x + relative.x, position.y + relative.y, position.z + relative.z)
end

-- Orthonormal basis from two independent baselines, built the same way on both
-- sides so the result is always a PROPER rotation (no handedness check needed).
local function baselineBasis(primary, secondary)
  local e1 = vec3(primary.x, primary.y, primary.z)
  if e1:length() < 0.05 then return nil end
  e1:normalize()
  local e2 = vec3(secondary.x, secondary.y, secondary.z)
  local along = e1 * e2:dot(e1)
  e2 = e2 - along
  -- Near-collinear baselines cannot pin a rotation about their shared axis.
  if e2:length() < 0.05 then return nil end
  e2:normalize()
  return e1, e2, e1:cross(e2)
end

-- Quaternion that maps the authored axes onto the basis VECTORS given (the
-- columns of the rotation matrix). Shepperd's method: branch on the largest
-- diagonal term so the divisor never approaches zero.
--
-- The result is CONJUGATED before it is returned. Shepperd yields the textbook
-- quaternion, whose rotation is q*v*inverse(q) — but the engine's `q * vec3`
-- applies the OPPOSITE handedness, the same reversal behind the documented
-- "quats compose LEFT-TO-RIGHT" rule. Feeding the textbook quat to the engine
-- transposes the rotation, which is an identity no-op on a level spawn and
-- silently wrong the moment the prop tilts: measured live 2026-08-24, the
-- transposed frame still left Boot of Doom's instruments 2.2 m off a
-- 7 m-per-12 m slope, having removed only the pitch error and not the roll.
local function basisQuat(ex, ey, ez)
  local x, y, z, w
  local trace = ex.x + ey.y + ez.z
  if trace > 0 then
    local s = math.sqrt(trace + 1.0) * 2
    x, y, z, w = (ey.z - ez.y) / s, (ez.x - ex.z) / s, (ex.y - ey.x) / s, 0.25 * s
  elseif ex.x > ey.y and ex.x > ez.z then
    local s = math.sqrt(1.0 + ex.x - ey.y - ez.z) * 2
    x, y, z, w = 0.25 * s, (ey.x + ex.y) / s, (ez.x + ex.z) / s, (ey.z - ez.y) / s
  elseif ey.y > ez.z then
    local s = math.sqrt(1.0 + ey.y - ex.x - ez.z) * 2
    x, y, z, w = (ey.x + ex.y) / s, 0.25 * s, (ez.y + ey.z) / s, (ez.x - ex.z) / s
  else
    local s = math.sqrt(1.0 + ez.z - ex.x - ey.y) * 2
    x, y, z, w = (ez.x + ex.z) / s, (ez.y + ey.z) / s, 0.25 * s, (ex.y - ey.x) / s
  end
  return quat(-x, -y, -z, w)
end

-- PLACEMENT FRAME — derived from the LIVE node cloud, never from the object
-- transform.
--
-- `vehicle:getRotation()` only refreshes on spawn/teleport/reset, so a prop
-- that settles onto sloped ground keeps reporting its SPAWN attitude while the
-- flexbody renders at the real nodes. Every runtime part, trigger and effect is
-- dead-reckoned from this frame, and props carry geometry many metres out from
-- the ref node, so a stale rotation is multiplied by that lever arm. Measured
-- live on utah 2026-08-24 against a Boot of Doom console node 13 m out:
--
--     terrain drop over 12 m     object transform      node cloud
--     0.03 m (flat)                    0.209 m            0.000 m
--     0.48 m (gentle)                  1.025 m            0.000 m
--     7.09 m (steep)                  11.611 m            0.000 m
--
-- The 1 m gentle-slope case is the shipped-mod bug report: Boot of Doom's
-- indicator lights floating a metre under their own control panel. Every gate
-- before this ran on flat smallgrid, the one condition where the object
-- transform and the node cloud agree and the error is invisible.
--
-- The refNodes give both the origin and the basis. Which PAIR of baselines
-- pins the basis is chosen per frame by conditioning, not hardcoded: what
-- matters is the Gram-Schmidt residual (how much of the second baseline is
-- genuinely perpendicular to the first), NOT how far apart the nodes are.
-- pendulum_gauntlet's ref/back/left sit only 10.2 degrees apart, so its
-- nominally 10.16 m left baseline pins the second axis with just 1.80 m of
-- residual; its up node is a far better partner. Boot of Doom is the opposite
-- case — its up baseline is 14 cm — so it keeps back/left. Picking the best
-- available pair covers both without either cage having to be re-authored.
local function propFrame(state, vehicle)
  local located, position = pcall(function() return vehicle:getPosition() end)
  if not located or not finiteVector3(position) then return nil end

  local refWorld = nodeWorldPosition(state, vehicle, position, FRAME_NODES.ref.name)

  local vehicleRotation
  local origin
  local frameSource = "object_transform"
  if refWorld then
    -- One lookup per node, not one per pair.
    local world = {}
    for _, role in ipairs({"back", "left", "up"}) do
      world[role] = nodeWorldPosition(state, vehicle, position, FRAME_NODES[role].name)
    end
    -- Map the authored baselines onto the live ones: R = V * transpose(U).
    local best, bestResidual = nil, 0
    for _, roles in ipairs({{"back", "left"}, {"back", "up"}, {"left", "up"}}) do
      local first, second = FRAME_NODES[roles[1]], FRAME_NODES[roles[2]]
      local firstWorld, secondWorld = world[roles[1]], world[roles[2]]
      if firstWorld and secondWorld then
        local u1, u2, u3 = baselineBasis(
          first.mesh - FRAME_NODES.ref.mesh, second.mesh - FRAME_NODES.ref.mesh)
        if u1 then
          -- Score on the AUTHORED geometry so the choice is stable frame to
          -- frame; a live score would let noise flip the pair mid-flight.
          --
          -- BOTH axes have to be well pinned, so score the WEAKER of the two.
          -- The residual alone only says how well the SECOND axis is fixed;
          -- the first axis inherits angular noise as sigma / |first|, which a
          -- residual-only score never sees. Scoring the residual alone would
          -- hand bouncy_castle a 2.50 m primary with an 11.51 m residual over
          -- a 10.00 m primary with a 3.94 m residual — the worse frame by the
          -- axis that actually limits it. (Dot product with the unit residual
          -- direction is a length, so it is already non-negative.)
          local firstLength = (first.mesh - FRAME_NODES.ref.mesh):length()
          local residual = (second.mesh - FRAME_NODES.ref.mesh):dot(u2)
          if firstLength < residual then residual = firstLength end
          if residual > bestResidual then
            local v1, v2, v3 = baselineBasis(firstWorld - refWorld, secondWorld - refWorld)
            if v1 then
              bestResidual = residual
              best = {u1 = u1, u2 = u2, u3 = u3, v1 = v1, v2 = v2, v3 = v3}
            end
          end
        end
      end
    end
    if best then
      local ex = best.v1 * best.u1.x + best.v2 * best.u2.x + best.v3 * best.u3.x
      local ey = best.v1 * best.u1.y + best.v2 * best.u2.y + best.v3 * best.u3.y
      local ez = best.v1 * best.u1.z + best.v2 * best.u2.z + best.v3 * best.u3.z
      local rotation = basisQuat(ex, ey, ez)
      if finiteNumber(rotation.x) and finiteNumber(rotation.y)
        and finiteNumber(rotation.z) and finiteNumber(rotation.w) then
        vehicleRotation = rotation
        origin = refWorld - rotation * PROP_REF_OFFSET
        frameSource = "node_cloud"
      end
    end
  end

  if not vehicleRotation then
    -- vdata is not ready yet (the first frames after spawn) or the cage is
    -- degenerate. Fall back to the object transform: wrong on a slope, but it
    -- keeps the prop placed until the node cloud answers, and the per-frame
    -- resync in synchronizeInstallation corrects it as soon as it does.
    local turned, objectRotation = pcall(function() return quat(vehicle:getRotation()) end)
    if not turned or not objectRotation
      or not finiteNumber(objectRotation.x)
      or not finiteNumber(objectRotation.y)
      or not finiteNumber(objectRotation.z)
      or not finiteNumber(objectRotation.w) then
      return nil
    end
    vehicleRotation = objectRotation
    origin = position - vehicleRotation * PROP_REF_OFFSET
  end

  if not finiteVector3(origin) then return nil end
  -- WITHOUT THIS THE FALLBACK IS INVISIBLE. On flat ground both paths agree to
  -- 0.000 m, so a prop stuck on the object transform forever looks identical to
  -- a healthy one in every smallgrid gate — and then flies apart on a slope.
  -- Report the transition, once, rather than every frame.
  if state.frameSource ~= frameSource then
    local previous = state.frameSource
    state.frameSource = frameSource
    if previous ~= nil or frameSource ~= "node_cloud" then
      emitEvent(
        state,
        -- Losing a frame source that was working is a regression; acquiring it
        -- during the first frames after spawn is just startup.
        (previous == "node_cloud") and "W" or "I",
        "prop_frame_source",
        {frame_source = frameSource, previous = previous}
      )
    end
  end
  return {
    origin = origin,
    vehicleRotation = vehicleRotation,
    -- ORDER MATTERS, and an identity spawn cannot prove it. Quats compose
    -- left-to-right here, so `FLIP * vehicleRotation` applies the authored ->
    -- mesh flip in the MODEL's own frame and only then the vehicle attitude;
    -- `vehicleRotation * FLIP` would flip about the WORLD axis instead. Both
    -- read identically while the prop sits LEVEL, which is every spawn the
    -- gates ever made, so the wrong order survived until the frame started
    -- carrying a real rotation. The error scales with TILT, not with yaw.
    -- Measured live 2026-08-24 against a panel node 13 m out:
    --                              flat   flat+yaw40   slope
    --     FLIP * vehicleRotation   0.000      0.002     0.000 m
    --     vehicleRotation * FLIP   0.380      0.425    18.880 m
    -- (A fourth spawn, slope+yaw40, is deliberately not quoted: it read like a
    -- level spawn, i.e. that prop had not taken the terrain's attitude when it
    -- was sampled. Which is precisely why the gate now ASSERTS measured tilt
    -- instead of assuming a sloped spot produces a tilted prop.)
    modelRotation = MODEL_ALIGNMENT_ROTATION * vehicleRotation,
  }
end

local function setCanSaveFalse(object)
  if type(object.setCanSave) == "function" then object:setCanSave(false) end
  object.canSave = false
  object:setField("canSave", 0, "0")
end

local function registerInMission(object, name)
  local registered, registerError = pcall(function()
    if not scenetree.MissionGroup then error("MissionGroup is unavailable") end
    if scenetree.findObject(name) then error("scene name is already in use: " .. name) end
    object:registerObject(name)
    scenetree.MissionGroup:addObject(object)
    if scenetree.findObject(name) ~= object then
      error("registered scene object cannot be resolved: " .. name)
    end
  end)
  if not registered then return false, tostring(registerError) end
  return true
end

local function ensureVisualMaterials()
  local missing = {}
  for _, name in ipairs(REQUIRED_VISUAL_MATERIALS) do
    local materialObject = scenetree.findObject(name)
    local className = materialObject
      and string.lower(tostring(materialObject:getClassName())) or ""
    if className ~= "material" then
      missing[#missing + 1] = name
    end
  end
  if #missing == 0 then return true end
  if type(loadJsonMaterialsFile) ~= "function" then
    return false, "loadJsonMaterialsFile is unavailable"
  end
  local loaded, loadError = pcall(loadJsonMaterialsFile, VISUAL_MATERIALS_PATH)
  if not loaded then return false, tostring(loadError) end
  return true
end

local function createPart(name, spec)
  local object = createObject(PART_CLASS)
  if not object then return nil, "BeamNG did not create part " .. name end
  local ok, createError = pcall(function()
    object.loadMode = 1
    if type(object.preApply) == "function" then object:preApply() end
    setCanSaveFalse(object)
    object:setField("shapeName", 0, spec.shape)
    object:setField("dynamic", 0, "1")
    -- Collision parts (e.g. the centrifuge door plug) get static collision
    -- that follows their pose after a be:reloadCollision at travel
    -- endpoints (runtime TSStatics have NO collision until the reload).
    object:setField(
      "collisionType", 0, spec.collision and "Visible Mesh Final" or "None")
    object:setField("decalType", 0, "None")
    object:setField("useInstanceRenderData", 0, "1")
    if type(object.postApply) == "function" then object:postApply() end
  end)
  if not ok then
    pcall(function() object:delete() end)
    return nil, tostring(createError)
  end
  local registered, registerError = registerInMission(object, name)
  if not registered then
    pcall(function() object:delete() end)
    return nil, registerError
  end
  return object
end

local function createTrigger(name, mode)
  local object = createObject(TRIGGER_CLASS)
  if not object then return nil, "BeamNG did not create trigger " .. name end
  local ok, createError = pcall(function()
    object.loadMode = 1
    if type(object.preApply) == "function" then object:preApply() end
    setCanSaveFalse(object)
    object:setField("luaFunction", 0, "onBeamNGTrigger")
    object:setField("triggerType", 0, "Box")
    object:setField("triggerMode", 0, mode)
    object:setField("triggerTestType", 0, "Bounding box")
    object:setField("tickPeriod", 0, "100")
    object:setField("ticking", 0, "0")
    object:setField("debug", 0, "0")
    object:setField("debugInEditor", 0, "0")
    if type(object.postApply) == "function" then object:postApply() end
  end)
  if not ok then
    pcall(function() object:delete() end)
    return nil, tostring(createError)
  end
  local registered, registerError = registerInMission(object, name)
  if not registered then
    pcall(function() object:delete() end)
    return nil, registerError
  end
  return object
end

local function createEffect(name, spec)
  local emitterData = scenetree.findObject(spec.emitter)
  if not emitterData then return nil, "stock emitter is unavailable: " .. spec.emitter end
  local object = createObject(EFFECT_CLASS)
  if not object then return nil, "BeamNG did not create effect " .. name end
  local ok, createError = pcall(function()
    object.loadMode = 1
    if type(object.preApply) == "function" then object:preApply() end
    setCanSaveFalse(object)
    object:setField("dataBlock", 0, "lightExampleEmitterNodeData1")
    object:setField("emitter", 0, spec.emitter)
    object:setField("active", 0, "0")
    if type(object.postApply) == "function" then object:postApply() end
  end)
  if not ok then
    pcall(function() object:delete() end)
    return nil, tostring(createError)
  end
  local registered, registerError = registerInMission(object, name)
  if not registered then
    pcall(function() object:delete() end)
    return nil, registerError
  end
  local configured, configureError = pcall(function()
    object:setEmitterDataBlock(emitterData)
    object:setActive(false)
  end)
  if not configured then
    pcall(function() object:delete() end)
    return nil, tostring(configureError)
  end
  return object
end

local function setObjectTransform(object, position, rotation, scale)
  object:setPosRot(
    position.x, position.y, position.z,
    rotation.x, rotation.y, rotation.z, rotation.w
  )
  if scale then object:setScale(scale) end
end

local function toWorldPoint(state, localPoint)
  return state.origin + state.modelRotation * localPoint
end

local function toWorldDir(state, localDir)
  local direction = state.modelRotation * localDir
  direction:normalize()
  return direction
end

local function setPartPose(state, name, offset, rotation, scale)
  local pose = state.partPoses[name]
  if not pose then
    pose = {offset = vec3(0, 0, 0), rotation = quat(0, 0, 0, 1), scale = nil}
    state.partPoses[name] = pose
  end
  if offset then pose.offset = offset end
  if rotation then pose.rotation = rotation end
  if scale then pose.scale = scale end
end

local function requestCollisionReload(state)
  state.collisionReloadPending = true
end

local function setEffectActive(state, name, active)
  local effect = state.effects[name]
  if not effect then return end
  pcall(function() effect:setActive(active and true or false) end)
end

local function zoneOccupants(state, zone)
  return state.zones[zone] or {}
end

local function zoneCount(state, zone)
  local count = 0
  for _ in pairs(zoneOccupants(state, zone)) do count = count + 1 end
  return count
end

local function firstOccupant(state, zone)
  for vehicleId in pairs(zoneOccupants(state, zone)) do
    local vehicle = exactVehicle(vehicleId)
    if vehicle then return vehicle end
  end
  return nil
end

@SUBJECT_MUTATION_HELPERS@

local behavior = {}

-- ========================================================================
-- @DISPLAY_NAME@ behaviour
-- ========================================================================
@BEHAVIOR_CHUNK@
-- ========================================================================

local function synchronizeInstallation(state, force)
  local vehicle = exactVehicle(state.propId)
  if not vehicle or not isSelfProp(vehicle) then
    return false, "registered prop is unavailable"
  end
  local frame = propFrame(state, vehicle)
  if not frame then return false, "registered prop transform is invalid" end
  local moved = force
    or not state.origin
    or (frame.origin - state.origin):length() > 0.005
    or math.abs(frame.modelRotation.x - state.modelRotation.x) > 0.0005
    or math.abs(frame.modelRotation.y - state.modelRotation.y) > 0.0005
    or math.abs(frame.modelRotation.z - state.modelRotation.z) > 0.0005
    or math.abs(frame.modelRotation.w - state.modelRotation.w) > 0.0005
  state.origin = frame.origin
  state.vehicleRotation = frame.vehicleRotation
  state.modelRotation = frame.modelRotation
  if not moved then return true end
  local ok, transformError = pcall(function()
    for suffix, trigger in pairs(state.triggers) do
      local spec = TRIGGER_SPECS[suffix]
      setObjectTransform(
        trigger,
        frame.origin + frame.modelRotation * spec.position,
        frame.modelRotation,
        spec.scale
      )
    end
    for suffix, effect in pairs(state.effects) do
      -- state.effects is the teardown register for EVERY scene object a
      -- behaviour makes, not just the declared EFFECT_SPECS emitters: the
      -- pack's PA horn clusters park their SFXEmitters here so
      -- cleanupInstallation deletes them on every path. Those keys have no
      -- spec, and an unguarded spec.direction threw INSIDE this pcall - which
      -- costs the whole frame, because onPreRender skips behavior.update and
      -- posePartObjects when synchronizeInstallation returns false. Behaviours
      -- that park objects here own their own re-posing (see Horn.place).
      local spec = EFFECT_SPECS[suffix]
      if spec then
        local direction = frame.modelRotation * spec.direction
        direction:normalize()
        setObjectTransform(
          effect,
          frame.origin + frame.modelRotation * spec.position,
          vec3(0, 0, 1):getRotationTo(direction),
          vec3(1, 1, 1)
        )
      end
    end
  end)
  if not ok then return false, tostring(transformError) end
  return true
end

local function posePartObjects(state)
  if not state.origin then return end
  for name, part in pairs(state.parts) do
    local spec = PART_SPECS[name]
    local pose = state.partPoses[name]
    local offset = pose and pose.offset or vec3(0, 0, 0)
    local rotation = pose and pose.rotation or quat(0, 0, 0, 1)
    local scale = pose and pose.scale or vec3(1, 1, 1)
    local ok = pcall(function()
      -- BeamNG's quat product composes left-to-right, so the authored
      -- local rotation must be the LEFT operand to apply in the authored
      -- frame before the vehicle/model flip (the seesaw plank rested
      -- inverted until this was play-tested 2026-07-22).
      setObjectTransform(
        part,
        state.origin + state.modelRotation * (spec.pivot + offset),
        rotation * state.modelRotation,
        scale
      )
    end)
    if not ok then return end
  end
end

local function deleteSceneObject(object)
  if not object then return end
  pcall(function() object:delete() end)
end

local function forgetTriggerOwner(trigger)
  for name, owner in pairs(triggerOwners) do
    if owner.trigger == trigger then triggerOwners[name] = nil end
  end
end

local function removeSubjectEverywhere(state, vehicleId, reason)
  local wasTracked = false
  for zone, occupants in pairs(state.zones) do
    if occupants[vehicleId] then
      occupants[vehicleId] = nil
      wasTracked = true
      if behavior.onExit then
        pcall(behavior.onExit, state, zone, vehicleId)
      end
    end
  end
  if wasTracked and behavior.onSubjectGone then
    pcall(behavior.onSubjectGone, state, vehicleId, reason)
  end
  return wasTracked
end

local function rebuildTriggers(state)
  for suffix, trigger in pairs(state.triggers) do
    forgetTriggerOwner(trigger)
    deleteSceneObject(trigger)
    state.triggers[suffix] = nil
  end
  for suffix, spec in pairs(TRIGGER_SPECS) do
    local name = string.format("%s_p%d_%s", PROP_MODEL, state.propId, suffix)
    local trigger, triggerError = createTrigger(name, spec.mode)
    if not trigger then
      emitError(state, "trigger_rebuild_failed", {trigger = suffix, detail = triggerError})
      return false
    end
    state.triggers[suffix] = trigger
    triggerOwners[name] = {propId = state.propId, zone = suffix, trigger = trigger}
  end
  state.zones = {}
  return synchronizeInstallation(state, true)
end

local function cleanupInstallation(state, reason)
  for _, trigger in pairs(state.triggers) do
    forgetTriggerOwner(trigger)
    deleteSceneObject(trigger)
  end
  local hadCollisionPart = false
  for name, _part in pairs(state.parts) do
    local spec = PART_SPECS[name]
    if spec and spec.collision then hadCollisionPart = true end
  end
  for _, part in pairs(state.parts) do deleteSceneObject(part) end
  for _, effect in pairs(state.effects) do deleteSceneObject(effect) end
  state.triggers = {}
  state.parts = {}
  state.effects = {}
  installations[state.propId] = nil
  -- Static collision is a snapshot refreshed only by reload: deleting a
  -- collision part without one leaves its last bake floating invisibly
  -- in open space (red-team finding, 2026-08-09).
  if hadCollisionPart then
    pcall(function() be:reloadCollision() end)
  end
  emitEvent(state, "I", "prop_unregistered", {reason = reason})
end

local function cleanupAll(reason)
  for _, state in pairs(installations) do
    cleanupInstallation(state, reason)
  end
end

local function acknowledgeRegistration(vehicle)
  pcall(function()
    vehicle:queueLuaCommand("extensions.hook('on@CAMEL@Registered')")
  end)
end

local function registerProp(propId)
  if extensionUnloading then return end
  if not integer(propId) then return end
  local vehicle = exactVehicle(propId)
  if not vehicle or not isSelfProp(vehicle) then return end
  local existing = installations[propId]
  if existing then
    acknowledgeRegistration(vehicle)
    synchronizeInstallation(existing, true)
    return
  end
  sessionCounter = sessionCounter + 1
  local state = {
    propId = propId,
    triggers = {},
    parts = {},
    effects = {},
    partPoses = {},
    zones = {},
    behavior = {},
    origin = nil,
    modelRotation = quat(0, 0, 0, 1),
  }
  local materialsOk, materialsError = ensureVisualMaterials()
  if not materialsOk then
    emitError(state, "visual_materials_unavailable", {detail = materialsError})
  end
  for _, name in ipairs(sortedKeys(PART_SPECS)) do
    local spec = PART_SPECS[name]
    local sceneName = string.format("%s_p%d_part_%s", PROP_MODEL, propId, name)
    local part, partError = createPart(sceneName, spec)
    if not part then
      emitError(state, "part_create_failed", {part = name, detail = partError})
      for _, created in pairs(state.parts) do deleteSceneObject(created) end
      return
    end
    state.parts[name] = part
  end
  for _, name in ipairs(sortedKeys(EFFECT_SPECS)) do
    local spec = EFFECT_SPECS[name]
    local sceneName = string.format("%s_p%d_fx_%s", PROP_MODEL, propId, name)
    local effect, effectError = createEffect(sceneName, spec)
    if not effect then
      -- Missing stock particle data degrades the show but never blocks the
      -- contraption.
      emitError(state, "effect_create_failed", {effect = name, detail = effectError})
    else
      state.effects[name] = effect
    end
  end
  installations[propId] = state
  if not rebuildTriggers(state) then
    cleanupInstallation(state, "trigger_creation_failed")
    return
  end
  if behavior.init then pcall(behavior.init, state) end
  posePartObjects(state)
  if state.collisionReloadPending then
    state.collisionReloadPending = nil
    pcall(function() be:reloadCollision() end)
  end
  acknowledgeRegistration(vehicle)
  emitEvent(state, "I", "prop_registered", {})
end

local function unregisterProp(propId, reason)
  local state = installations[propId]
  if not state then return end
  cleanupInstallation(state, reason or "unregistered")
end

local function validateTriggerEvent(data)
  if type(data) ~= "table"
    or (data.event ~= "enter" and data.event ~= "exit")
    or not integer(data.triggerID)
    or not integer(data.subjectID) then
    return nil
  end
  local owner = triggerOwners[tostring(data.triggerName or "")]
  if not owner then return nil end
  local state = installations[owner.propId]
  if not state then return nil end
  if state.triggers[owner.zone] ~= owner.trigger then return nil end
  -- Revalidate the live trigger identity, mode, and test type before acting.
  local byId = scenetree.findObjectById(data.triggerID)
  local byName = scenetree.findObject(tostring(data.triggerName))
  if byId ~= owner.trigger or byName ~= owner.trigger then return nil end
  if owner.trigger:getClassName() ~= TRIGGER_CLASS then return nil end
  local expectedMode = TRIGGER_SPECS[owner.zone].mode
  if owner.trigger:getField("triggerMode", 0) ~= expectedMode then return nil end
  if owner.trigger:getField("triggerTestType", 0) ~= "Bounding box" then return nil end
  return state, owner.zone
end

local function onBeamNGTrigger(data)
  local state, zone = validateTriggerEvent(data)
  if not state then return end
  local vehicleId = data.subjectID
  if data.event == "enter" then
    local vehicle = eligibleSubject(vehicleId)
    if not vehicle then return end
    local occupants = state.zones[zone]
    if not occupants then
      occupants = {}
      state.zones[zone] = occupants
    end
    if occupants[vehicleId] then return end
    occupants[vehicleId] = true
    emitEvent(state, "I", "zone_enter", {zone = zone, subject_id = vehicleId})
    if behavior.onEnter then
      local vehicleObject = exactVehicle(vehicleId)
      if vehicleObject then
        pcall(behavior.onEnter, state, zone, vehicleObject)
      end
    end
  else
    local occupants = state.zones[zone]
    if not occupants or not occupants[vehicleId] then return end
    occupants[vehicleId] = nil
    emitEvent(state, "I", "zone_exit", {zone = zone, subject_id = vehicleId})
    if behavior.onExit then
      pcall(behavior.onExit, state, zone, vehicleId)
    end
  end
end

local function sweepZones(state)
  for zone, occupants in pairs(state.zones) do
    for vehicleId in pairs(occupants) do
      if not exactVehicle(vehicleId) then
        occupants[vehicleId] = nil
        if behavior.onExit then pcall(behavior.onExit, state, zone, vehicleId) end
        if behavior.onSubjectGone then
          pcall(behavior.onSubjectGone, state, vehicleId, "vehicle_missing")
        end
      end
    end
  end
end

local sweepElapsed = 0

local function onPreRender(dtReal, dtSim, dtRaw)
  sweepElapsed = sweepElapsed + (dtReal or 0)
  local sweep = false
  if sweepElapsed >= 0.5 then
    sweepElapsed = 0
    sweep = true
  end
  for _, state in pairs(installations) do
    local ok = synchronizeInstallation(state, false)
    if ok then
      if sweep then sweepZones(state) end
      if behavior.update then
        -- TWO CLOCKS, AND A BEHAVIOUR MAY PICK (2026-08-15, pachinko round 9).
        --
        -- `dtSim` is scaled by simTimeAuthority: slow motion, bullet time and
        -- pause are all bound to player keys, and in normal play the ratio is
        -- 1.00 (measured both ways, pachinko_tower AUDIO_SIM_PER_WALL - the
        -- "dtSim runs 3x wall" reading was a deterministic HARNESS stepping
        -- the world as fast as the machine could, never a property of
        -- behavior.update). So dtSim is the right clock for anything coupled
        -- to the simulation, and it stays the SECOND argument, unchanged, for
        -- every behaviour in the pack.
        --
        -- What dtSim cannot carry is a MUSICAL timeline. Audio plays on FMOD's
        -- real-time clock whatever the player does to sim time, and
        -- `Engine.Audio` exposes no playback position anywhere in the GE tree,
        -- so a show synchronised to a cue can only run open-loop from the
        -- trigger instant. Run that on dtSim and one tap of slow motion
        -- desynchronises it without bound.
        --
        -- `onPreRender` already receives dtReal; it was simply never passed
        -- on. This is additive: every existing behaviour declares
        -- `function(state, dtSim)` and ignores a third argument, so no mod in
        -- the pack changes behaviour by one frame.
        local updated, updateError = pcall(
          behavior.update, state, dtSim or 0, dtReal or 0)
        if not updated then
          emitError(state, "behavior_update_failed", {detail = tostring(updateError)})
        end
      end
      posePartObjects(state)
  if state.collisionReloadPending then
    state.collisionReloadPending = nil
    pcall(function() be:reloadCollision() end)
  end
    end
  end
end

local function onVehicleResetted(vehicleId)
  local propState = installations[vehicleId]
  if propState then
    synchronizeInstallation(propState, true)
    if behavior.reset then pcall(behavior.reset, propState) end
    rebuildTriggers(propState)
    posePartObjects(propState)
    return
  end
  for _, state in pairs(installations) do
    if removeSubjectEverywhere(state, vehicleId, "subject_reset") then
      -- A reset can leave the thin trigger without a fresh enter event;
      -- rebuilding restores overlap delivery for vehicles still inside.
      rebuildTriggers(state)
    end
  end
end

local function onVehicleDestroyed(vehicleId)
  local propState = installations[vehicleId]
  if propState then
    cleanupInstallation(propState, "prop_destroyed")
    return
  end
  for _, state in pairs(installations) do
    removeSubjectEverywhere(state, vehicleId, "subject_destroyed")
  end
end

local function onClientEndMission(levelPath)
  cleanupAll("mission_end")
end

local function onExtensionLoaded()
  extensionUnloading = false
end

local function onExtensionUnloaded()
  extensionUnloading = true
  cleanupAll("extension_unloaded")
end

local function getSystemState(propId)
  local state = installations[propId]
  if not state then return {registered = false} end
  local result = {
    registered = true,
    prop_model = PROP_MODEL,
    part_count = 0,
    effect_count = 0,
    trigger_count = 0,
    triggers = {},
    zone_counts = {},
    behavior_phase = state.behavior and state.behavior.phase or nil,
    -- "node_cloud" once the live frame is up; "object_transform" while the
    -- fallback is carrying it. Exposed so a placement test can prove WHICH
    -- path produced the pose it just measured — on flat ground the two are
    -- indistinguishable by position alone.
    frame_source = state.frameSource,
  }
  for _ in pairs(state.parts) do result.part_count = result.part_count + 1 end
  for _ in pairs(state.effects) do result.effect_count = result.effect_count + 1 end
  for suffix, trigger in pairs(state.triggers) do
    result.trigger_count = result.trigger_count + 1
    result.triggers[suffix] = {
      name = trigger:getName(),
      id = trigger:getID(),
      mode = trigger:getField("triggerMode", 0),
      test_type = trigger:getField("triggerTestType", 0),
    }
  end
  for zone in pairs(TRIGGER_SPECS) do
    result.zone_counts[zone] = zoneCount(state, zone)
  end
  if state.origin then
    result.origin = {state.origin.x, state.origin.y, state.origin.z}
  end
  if state.behavior and state.behavior.stats then
    result.behavior_stats = state.behavior.stats
  end
  if state.behavior then
    -- Live phase telemetry (round 15): max_rpm is a lifetime maximum, so
    -- probes asserting on button presses need the actual phase and
    -- instantaneous rpm.
    result.behavior_phase = state.behavior.phase
    result.behavior_rpm = state.behavior.rpm
    result.behavior_manual = state.behavior.manual and true or false
    result.behavior_door = state.behavior.doorSlide
    result.behavior_shelf = state.behavior.shelfDrop
    -- Mouth-eject probes (centrifuge 2026-08-09): bake state + launch
    -- count. Nil-safe on every other prop.
    result.behavior_shelf_baked = state.behavior.shelfReloaded and true or false
    local ejectedCount = 0
    for _ in pairs(state.behavior.ejected or {}) do
      ejectedCount = ejectedCount + 1
    end
    result.behavior_ejected = ejectedCount
    if behavior.getStatus then
      local statusOk, status = pcall(behavior.getStatus, state)
      if statusOk then result.behavior_status = status end
    end
  end
  return result
end

-- Interactive panel buttons (vehicle triggers2 rows forward presses here
-- via the interaction json's onDown; see the cannon-wash recipe in
-- AGENTS.md "Interactive dashboard-style buttons on a prop").
local function pressPanelButtonByVehicle(vehicleId, buttonId)
  local state = installations[vehicleId]
  if not state or type(buttonId) ~= "string" then return false end
  if behavior.onPanelButton then
    local ok, pressError = pcall(behavior.onPanelButton, state, buttonId)
    if not ok then
      emitEvent(state, "E", "panel_button_error", {
        button = buttonId, detail = tostring(pressError),
      })
      return false
    end
    emitEvent(state, "I", "panel_button", {button = buttonId})
    return true
  end
  return false
end

M.registerProp = registerProp
M.getSystemState = getSystemState
M.unregisterProp = unregisterProp
M.pressPanelButtonByVehicle = pressPanelButtonByVehicle
M.onBeamNGTrigger = onBeamNGTrigger
M.onPreRender = onPreRender
M.onVehicleResetted = onVehicleResetted
M.onVehicleDestroyed = onVehicleDestroyed
M.onClientEndMission = onClientEndMission
M.onExtensionLoaded = onExtensionLoaded
M.onExtensionUnloaded = onExtensionUnloaded

-- Behaviour chunks may export extra GE hooks (e.g. acknowledgement
-- callbacks queued back from prop vehicle Lua via extensions.hook).
if behavior.hooks then
  for hookName, hookFn in pairs(behavior.hooks) do
    M[hookName] = hookFn
  end
end

return M
"""

    node_positions = {node["id"]: node["position"] for node in handoff["nodes"]}
    ref_id = handoff["refnodes"]["ref"]
    ref_position = node_positions[ref_id]
    ref_offset = (
        f"vec3({lua_number(ref_position[0])}, "
        f"{lua_number(ref_position[1])}, {lua_number(ref_position[2])})"
    )

    # propFrame rebuilds the placement basis from these nodes' LIVE positions
    # every frame, because vehicle:getRotation() goes stale the moment a prop
    # settles onto anything that is not flat.
    frame_lines = []
    for role in ("ref", "back", "left", "up"):
        node_id = handoff["refnodes"][role]
        position = node_positions[node_id]
        frame_lines.append(
            f"  {role} = {{name = {lua_value(node_id)}, mesh = vec3("
            f"{lua_number(position[0])}, {lua_number(position[1])}, "
            f"{lua_number(position[2])})}},"
        )
    frame_nodes = "{\n" + "\n".join(frame_lines) + "\n}"

    replacements = {
        "@REF_OFFSET@": ref_offset,
        "@FRAME_NODES@": frame_nodes,
        "@MOD_ID@": mod_id,
        "@DISPLAY_NAME@": display_name,
        "@LOG_TAG@": mod_id.upper() + "_RUNTIME",
        "@CAMEL@": camel,
        "@REQUIRED_MATERIALS@": material_lines,
        "@PART_SPECS@": lua_table(part_entries),
        "@TRIGGER_SPECS@": lua_table(trigger_entries),
        "@EFFECT_SPECS@": lua_table(effect_entries),
        "@TUNABLES@": lua_table(tunables),
        "@SUBJECT_MUTATION_HELPERS@": subject_mutation_helpers,
        "@BEHAVIOR_CHUNK@": behavior_chunk,
    }
    source = template
    for token, value in replacements.items():
        source = source.replace(token, value)
    if "@" in source.replace(extension_name, ""):
        # Every token must have been replaced; a stray @ means a typo in the
        # template or behaviour chunk placeholders.
        stray = [line for line in source.splitlines() if "@" in line][:3]
        raise ValueError(f"unreplaced template token near: {stray}")
    return source
