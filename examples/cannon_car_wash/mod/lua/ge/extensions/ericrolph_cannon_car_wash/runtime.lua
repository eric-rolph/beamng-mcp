local M = {}

local LOG_TAG = "ERICROLPH_CANNON_CAR_WASH_RUNTIME"
local RUNTIME_EXTENSION_NAME = "ericrolph__cannon__car__wash_runtime"
local PROP_MODEL = "ericrolph_cannon_car_wash"
local PROP_VISUAL_MESH = "ericrolph_cannon_car_wash_selector_visual"
local VISUAL_SHAPE = (
  "/vehicles/ericrolph_cannon_car_wash/ericrolph_cannon_car_wash_runtime_visual.dae"
)
local VISUAL_MATERIALS_PATH = "vehicles/ericrolph_cannon_car_wash/main.materials.json"
local REQUIRED_VISUAL_MATERIALS = {
  "ericrolph_cannon_car_wash_selector_brush_aqua",
  "ericrolph_cannon_car_wash_selector_brush_blue",
  "ericrolph_cannon_car_wash_selector_brush_cards",
  "ericrolph_cannon_car_wash_selector_concrete",
  "ericrolph_cannon_car_wash_selector_corrugated_blue",
  "ericrolph_cannon_car_wash_selector_cyan_trim",
  "ericrolph_cannon_car_wash_selector_deep_blue",
  "ericrolph_cannon_car_wash_selector_exterior_cmu",
  "ericrolph_cannon_car_wash_selector_glass",
  "ericrolph_cannon_car_wash_selector_hazard_yellow",
  "ericrolph_cannon_car_wash_selector_interior_brick",
  "ericrolph_cannon_car_wash_selector_led",
  "ericrolph_cannon_car_wash_selector_rubber",
  "ericrolph_cannon_car_wash_selector_safety_orange",
  "ericrolph_cannon_car_wash_selector_screen",
  "ericrolph_cannon_car_wash_selector_sign_face",
  "ericrolph_cannon_car_wash_selector_stainless",
  "ericrolph_cannon_car_wash_selector_wet_concrete",
}
local UI_CATEGORY = "ericrolph_cannon_car_wash_runtime_countdown"
local TRIGGER_CLASS = "BeamNGTrigger"
local VISUAL_CLASS = "TSStatic"
local EFFECT_CLASS = "ParticleEmitterNode"
local LIGHT_SPECS = require("common/ericrolph_cannon_car_wash/lighting")
local COUNTDOWN_INTERVAL_SECONDS = 1
local COUNTDOWN_MESSAGES = {"3...", "2...", "1..."}
local COUNTDOWN_EVENTS = {"countdown_3", "countdown_2", "countdown_1"}
local LAUNCH_SPEED_MPS = 100
local TRANSFORM_REFRESH_SECONDS = 0.1
local VEHICLE_ACK_TIMEOUT_SECONDS = 1
local REPAIR_ACK_TIMEOUT_SECONDS = 2
local REPAIR_SETTLE_SIM_FRAMES = 2
local REPAIR_MAX_CENTERLINE_ERROR_METERS = 0.15
local REPAIR_MIN_CORRIDOR_DOT = 0.999
local REPAIR_MIN_UPRIGHT_DOT = 0.999
local REPAIR_MAX_POSE_CORRECTION_ATTEMPTS = 2
local RELEASE_GRACE_SIM_FRAMES = 2

-- The selector handoff uses a ground-plane reference node. The authored
-- scenario DAE remains in Blender/world orientation, so its transform is a
-- proper 180-degree Z rotation from BeamNG vehicle space.
local PROP_REF_OFFSET = vec3(0, 0, 0)
local MODEL_ALIGNMENT_ROTATION = quat(0, 0, 1, 0)
local WASH_TRIGGER_LOCAL_POSITION = vec3(0, 0, 2.2)
local WASH_TRIGGER_SCALE = vec3(5.8, 17.5, 4.4)
local REPAIR_TRIGGER_LOCAL_POSITION = vec3(0, 0, 2.1)
local REPAIR_TRIGGER_SCALE = vec3(5.4, 2.2, 4.2)
local LAUNCH_TRIGGER_LOCAL_POSITION = vec3(0, 0, 2.1)
local LAUNCH_TRIGGER_SCALE = vec3(5.8, 17.5, 4.6)
local EFFECT_OFFSETS = {
  {suffix = "mister_PreSoak_L_1", emitter = "BNGP_sprinkler", position = vec3(-2.62, -5.6, 1.25), inward = vec3(1, 0, 0)},
  {suffix = "mister_PreSoak_L_2", emitter = "BNGP_sprinkler", position = vec3(-2.62, -5.6, 2.1), inward = vec3(1, 0, 0)},
  {suffix = "mister_PreSoak_L_3", emitter = "BNGP_sprinkler", position = vec3(-2.62, -5.6, 3.0), inward = vec3(1, 0, 0)},
  {suffix = "mister_PreSoak_R_1", emitter = "BNGP_sprinkler", position = vec3(2.62, -5.6, 1.25), inward = vec3(-1, 0, 0)},
  {suffix = "mister_PreSoak_R_2", emitter = "BNGP_sprinkler", position = vec3(2.62, -5.6, 2.1), inward = vec3(-1, 0, 0)},
  {suffix = "mister_PreSoak_R_3", emitter = "BNGP_sprinkler", position = vec3(2.62, -5.6, 3.0), inward = vec3(-1, 0, 0)},
  {suffix = "dryer_Mist_L_1", emitter = "BNGP_waterfallsteam", position = vec3(-2.62, 5.65, 1.25), inward = vec3(1, 0, 0)},
  {suffix = "dryer_Mist_L_2", emitter = "BNGP_waterfallsteam", position = vec3(-2.62, 5.65, 2.1), inward = vec3(1, 0, 0)},
  {suffix = "dryer_Mist_L_3", emitter = "BNGP_waterfallsteam", position = vec3(-2.62, 5.65, 3.0), inward = vec3(1, 0, 0)},
  {suffix = "dryer_Mist_R_1", emitter = "BNGP_waterfallsteam", position = vec3(2.62, 5.65, 1.25), inward = vec3(-1, 0, 0)},
  {suffix = "dryer_Mist_R_2", emitter = "BNGP_waterfallsteam", position = vec3(2.62, 5.65, 2.1), inward = vec3(-1, 0, 0)},
  {suffix = "dryer_Mist_R_3", emitter = "BNGP_waterfallsteam", position = vec3(2.62, 5.65, 3.0), inward = vec3(-1, 0, 0)},
  {suffix = "dryer_Steam_L", emitter = "BNGP_34", position = vec3(-2.62, 5.65, 2.1), inward = vec3(1, 0, 0)},
  {suffix = "dryer_Steam_R", emitter = "BNGP_34", position = vec3(2.62, 5.65, 2.1), inward = vec3(-1, 0, 0)},
  {suffix = "dryer_Dust_L", emitter = "BNGP_2", position = vec3(-2.62, 5.65, 1.25), inward = vec3(1, 0, 0)},
  {suffix = "dryer_Dust_R", emitter = "BNGP_2", position = vec3(2.62, 5.65, 1.25), inward = vec3(-1, 0, 0)},
}

local function holdVehicleCommand(propId, runNumber)
  return string.format([[
local existing = ericrolphCannonCarWashHoldState
local currentFrozen = controller and controller.isFrozen == true or false
local previousFrozen = currentFrozen
if existing then previousFrozen = existing.frozen == true end
local accepted = controller ~= nil
  and type(controller.setFreeze) == "function"
  and (not existing or (existing.propId == %d and existing.runNumber == %d))
if accepted then
  ericrolphCannonCarWashHoldState = existing or {
    propId = %d,
    runNumber = %d,
    frozen = previousFrozen
  }
  controller.setFreeze(1)
end
local actualFrozen = controller and controller.isFrozen == true or false
obj:queueGameEngineLua(string.format(
  "extensions.hook('onEricrolphCannonCarWashHoldAcknowledged', %%d, %%d, %%d, %%s, %%s, %%s)",
  obj:getId(), %d, %d, tostring(accepted), tostring(previousFrozen), tostring(actualFrozen)
))
]], propId, runNumber, propId, runNumber, propId, runNumber)
end

local function releaseVehicleCommand(propId, runNumber)
  return string.format([[
local existing = ericrolphCannonCarWashHoldState
local matched = existing ~= nil
  and existing.propId == %d
  and existing.runNumber == %d
local previousFrozen = controller and controller.isFrozen == true or false
if matched then previousFrozen = existing.frozen == true end
local restored = matched
  and controller ~= nil
  and type(controller.setFreeze) == "function"
if restored then
  controller.setFreeze(previousFrozen and 1 or 0)
  ericrolphCannonCarWashHoldState = nil
end
local actualFrozen = controller and controller.isFrozen == true or false
obj:queueGameEngineLua(string.format(
  "extensions.hook('onEricrolphCannonCarWashReleaseAcknowledged', %%d, %%d, %%d, %%s, %%s, %%s)",
  obj:getId(), %d, %d, tostring(restored), tostring(previousFrozen), tostring(actualFrozen)
))
]], propId, runNumber, propId, runNumber)
end

local function repairIntegrityCommand(propId, token, stage)
  return string.format([[
local expectedPropId = %d
local expectedToken = %d
local stage = '%s'
local existing = ericrolphCannonCarWashRepairHoldState
local matched = existing ~= nil
  and existing.propId == expectedPropId
  and existing.token == expectedToken
local currentFrozen = controller and controller.isFrozen == true or false
local previousFrozen = currentFrozen
if matched then previousFrozen = existing.frozen == true end
local holdAccepted = controller ~= nil
  and type(controller.setFreeze) == "function"
  and ((stage == "before" and (existing == nil or matched))
    or (stage == "after" and matched))
if holdAccepted then
  if stage == "before" and not matched then
    existing = {
      propId = expectedPropId,
      token = expectedToken,
      frozen = previousFrozen
    }
    ericrolphCannonCarWashRepairHoldState = existing
  end
  controller.setFreeze(1)
end
local actualFrozen = controller and controller.isFrozen == true or false
local damage = beamstate and tonumber(beamstate.damage) or 0
local partDamage = beamstate and type(beamstate.getPartDamageData) == "function"
  and beamstate.getPartDamageData() or {}
local partDamageCount = 0
for _ in pairs(partDamage) do partDamageCount = partDamageCount + 1 end
local brokenBeamCount = 0
if v and v.data and v.data.beams then
  for _, beam in pairs(v.data.beams) do
    if type(beam) == "table" and beam.cid ~= nil and obj:beamIsBroken(beam.cid) then
      brokenBeamCount = brokenBeamCount + 1
    end
  end
end
local deflatedTireCount = 0
if wheels and wheels.wheels then
  for _, wheel in pairs(wheels.wheels) do
    if type(wheel) == "table" and wheel.isTireDeflated == true then
      deflatedTireCount = deflatedTireCount + 1
    end
  end
end
obj:queueGameEngineLua(string.format(
  "extensions.hook('onEricrolphCannonCarWashRepairIntegrityAcknowledged', %%d, %%d, %%d, '%s', %%s, %%s, %%s, %%.12f, %%d, %%d, %%d)",
  obj:getId(), %d, %d, tostring(holdAccepted), tostring(previousFrozen),
  tostring(actualFrozen), damage, partDamageCount, brokenBeamCount, deflatedTireCount
))
]], propId, token, stage, stage, propId, token)
end

local function repairReleaseCommand(propId, token, expectedPreviousFrozen)
  return string.format([[
local existing = ericrolphCannonCarWashRepairHoldState
local matched = existing ~= nil
  and existing.propId == %d
  and existing.token == %d
local previousFrozen = %s
if matched then previousFrozen = existing.frozen == true end
local attempted = (existing == nil or matched)
  and controller ~= nil
  and type(controller.setFreeze) == "function"
if attempted then controller.setFreeze(previousFrozen and 1 or 0) end
local actualFrozen = controller and controller.isFrozen == true or false
local restored = attempted and actualFrozen == previousFrozen
if restored and matched then ericrolphCannonCarWashRepairHoldState = nil end
obj:queueGameEngineLua(string.format(
  "extensions.hook('onEricrolphCannonCarWashRepairReleaseAcknowledged', %%d, %%d, %%d, %%s, %%s, %%s)",
  obj:getId(), %d, %d, tostring(restored), tostring(previousFrozen), tostring(actualFrozen)
))
]], propId, token, tostring(expectedPreviousFrozen == true), propId, token)
end

local installations = {}
local triggerOwners = {}
local runCounter = 0
local repairCounter = 0
local sessionCounter = 0
local unloadRequested = false
local extensionUnloading = false

local function integer(value)
  return type(value) == "number" and value == math.floor(value)
end

local function nonnegativeInteger(value)
  return integer(value) and value >= 0
end

local function finiteNumber(value)
  return type(value) == "number"
    and value == value
    and value ~= math.huge
    and value ~= -math.huge
end

local function emitEvent(state, level, event, fields)
  local record = {
    schema_version = 2,
    event = event,
    mode = "selector_prop",
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
  guihooks.message({txt = message}, ttl or 1.1, UI_CATEGORY)
end

local function exactVehicle(vehicleId)
  if not integer(vehicleId) then return nil end
  local vehicle = be:getObjectByID(vehicleId)
  if not vehicle or vehicle:getId() ~= vehicleId then return nil end
  return vehicle
end

local function isWashProp(vehicle)
  if not vehicle then return false end
  local ok, model = pcall(function() return vehicle:getJBeamFilename() end)
  return ok and model == PROP_MODEL
end

local function eligibleSubject(vehicleId)
  if installations[vehicleId] then return nil end
  local vehicle = exactVehicle(vehicleId)
  if not vehicle or isWashProp(vehicle) then return nil end
  return vehicle
end

local function exactSceneObject(name, expectedClass)
  local object = scenetree.findObject(name)
  if not object or object:getName() ~= name then return nil end
  if object:getClassName() ~= expectedClass then return nil end
  return object
end

local function finiteVector3(value)
  return value
    and finiteNumber(value.x)
    and finiteNumber(value.y)
    and finiteNumber(value.z)
end

local function finiteQuaternion(value)
  return value
    and finiteNumber(value.x)
    and finiteNumber(value.y)
    and finiteNumber(value.z)
    and finiteNumber(value.w)
end

-- Construct the repaired pose from the live trigger frame instead of assuming
-- any vehicle model's internal forward axis. The source/target frame delta
-- preserves BeamNG's own vehicle quaternion convention while aligning the
-- visible vehicle with the wash corridor.
local function repairTargetPose(vehicle, trigger)
  if not vehicle or not trigger then return nil, "repair target objects are unavailable" end
  local position = vehicle:getPosition()
  local rotation = quat(vehicle:getRotation())
  local direction = vec3(vehicle:getDirectionVector())
  local vehicleUp = vec3(vehicle:getDirectionVectorUp())
  local triggerPosition = trigger:getPosition()
  local triggerRotation = quat(trigger:getRotation())
  local boundingBox = vehicle:getSpawnWorldOOBB()
  local boundingCenter = boundingBox and boundingBox:getCenter() or nil
  if not finiteVector3(position)
    or not finiteQuaternion(rotation)
    or not finiteVector3(direction)
    or not finiteVector3(vehicleUp)
    or not finiteVector3(triggerPosition)
    or not finiteQuaternion(triggerRotation)
    or not finiteVector3(boundingCenter)
    or direction:length() < 0.000001
    or vehicleUp:length() < 0.000001 then
    return nil, "repair pose snapshot is invalid"
  end
  direction:normalize()
  vehicleUp:normalize()

  local corridorUp = triggerRotation * vec3(0, 0, 1)
  local corridorForward = triggerRotation * vec3(0, 1, 0)
  if not finiteVector3(corridorUp)
    or not finiteVector3(corridorForward)
    or corridorUp:length() < 0.000001 then
    return nil, "repair trigger frame is invalid"
  end
  corridorUp:normalize()
  corridorForward = corridorForward - corridorUp * corridorForward:dot(corridorUp)
  if corridorForward:length() < 0.000001 then
    return nil, "repair trigger corridor axis is invalid"
  end
  corridorForward:normalize()

  local travelSign = 1
  if direction:dot(corridorForward) < 0 then
    corridorForward = -corridorForward
    travelSign = -1
  end
  local travelDirectionDotBefore = direction:dot(corridorForward)
  if travelDirectionDotBefore <= 0.000001 then
    return nil, "vehicle travel direction is perpendicular to the wash corridor"
  end

  local corridorRight = corridorForward:cross(corridorUp)
  if not finiteVector3(corridorRight) or corridorRight:length() < 0.000001 then
    return nil, "repair trigger lateral axis is invalid"
  end
  corridorRight:normalize()
  local sourceUp = vehicleUp - direction * vehicleUp:dot(direction)
  if sourceUp:length() < 0.000001 then
    return nil, "vehicle forward/up basis is degenerate"
  end
  sourceUp:normalize()
  local forwardAlignment = direction:getRotationTo(corridorForward)
  local alignedUp = forwardAlignment * sourceUp
  alignedUp = alignedUp - corridorForward * alignedUp:dot(corridorForward)
  if alignedUp:length() < 0.000001 then
    return nil, "aligned vehicle up axis is degenerate"
  end
  alignedUp:normalize()
  -- Both vectors are perpendicular to corridorForward, so this second,
  -- shortest-arc rotation is around the corridor axis and cannot undo the
  -- forward alignment. This avoids quatFromDir basis ambiguity on vehicles
  -- such as the city bus while removing roll/pitch explicitly.
  local upAlignment = alignedUp:getRotationTo(corridorUp)
  local alignmentRotation = (upAlignment * forwardAlignment):normalized()
  local targetRotation = (alignmentRotation * rotation):normalized()
  local alignedBoundingOffset = alignmentRotation * (boundingCenter - position)
  local alignedBoundingCenter = position + alignedBoundingOffset
  local centerlineOffset = (alignedBoundingCenter - triggerPosition):dot(corridorRight)
  local targetPosition = position - corridorRight * centerlineOffset
  if not finiteVector3(targetPosition) or not finiteQuaternion(targetRotation) then
    return nil, "repair target transform is invalid"
  end

  return {
    positionBefore = vec3(position.x, position.y, position.z),
    rotationBefore = quat(rotation.x, rotation.y, rotation.z, rotation.w),
    directionBefore = vec3(direction.x, direction.y, direction.z),
    upBefore = vec3(vehicleUp.x, vehicleUp.y, vehicleUp.z),
    targetPosition = targetPosition,
    targetRotation = targetRotation,
    targetDirection = corridorForward,
    targetUp = corridorUp,
    corridorRight = corridorRight,
    corridorCenter = vec3(triggerPosition.x, triggerPosition.y, triggerPosition.z),
    centerlineErrorBefore = math.abs(
      (boundingCenter - triggerPosition):dot(corridorRight)
    ),
    alignmentTranslation = (targetPosition - position):length(),
    travelDirectionDotBefore = travelDirectionDotBefore,
    travelSign = travelSign,
  }
end

local function repairedPoseMetrics(vehicle, repair)
  if not vehicle or not repair then return nil end
  local position = vehicle:getPosition()
  local direction = vec3(vehicle:getDirectionVector())
  local vehicleUp = vec3(vehicle:getDirectionVectorUp())
  local boundingBox = vehicle:getSpawnWorldOOBB()
  local boundingCenter = boundingBox and boundingBox:getCenter() or nil
  if not finiteVector3(position)
    or not finiteVector3(direction)
    or not finiteVector3(vehicleUp)
    or not finiteVector3(boundingCenter)
    or direction:length() < 0.000001
    or vehicleUp:length() < 0.000001 then
    return nil
  end
  direction:normalize()
  vehicleUp:normalize()
  local centerlineError = math.abs(
    (boundingCenter - repair.corridorCenter):dot(repair.corridorRight)
  )
  local corridorDirectionDot = direction:dot(repair.targetDirection)
  local uprightDot = vehicleUp:dot(repair.targetUp)
  local travelDirectionDot = direction:dot(repair.directionBefore)
  return {
    targetPositionDrift = (position - repair.targetPosition):length(),
    centerlineError = centerlineError,
    corridorDirectionDot = corridorDirectionDot,
    uprightDot = uprightDot,
    travelDirectionDot = travelDirectionDot,
    travelSignPreserved = travelDirectionDot > 0,
  }
end

local function queueVehicleCommand(vehicle, command, state, failureReason, reportFailure)
  local ok, commandError = pcall(function() vehicle:queueLuaCommand(command) end)
  if not ok then
    local detail = tostring(commandError)
    if reportFailure ~= false then emitError(state, failureReason, {detail = detail}) end
    return false, detail
  end
  return true
end

local function acknowledgeRegistration(vehicle)
  pcall(function()
    vehicle:queueLuaCommand(
      "extensions.hook('onEricrolphCannonCarWashRegistered')"
    )
  end)
end

local function propFrame(vehicle)
  local position = vehicle:getPosition()
  local vehicleRotation = quat(vehicle:getRotation())
  if not position
    or not finiteNumber(position.x)
    or not finiteNumber(position.y)
    or not finiteNumber(position.z)
    or not finiteNumber(vehicleRotation.x)
    or not finiteNumber(vehicleRotation.y)
    or not finiteNumber(vehicleRotation.z)
    or not finiteNumber(vehicleRotation.w) then
    return nil
  end
  local origin = position - vehicleRotation * PROP_REF_OFFSET
  return {
    origin = origin,
    vehicleRotation = vehicleRotation,
    modelRotation = vehicleRotation * MODEL_ALIGNMENT_ROTATION,
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
    local material = scenetree.findObject(name)
    local className = material and string.lower(tostring(material:getClassName())) or ""
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
  missing = {}
  for _, name in ipairs(REQUIRED_VISUAL_MATERIALS) do
    local material = scenetree.findObject(name)
    local className = material and string.lower(tostring(material:getClassName())) or ""
    if className ~= "material" then
      missing[#missing + 1] = name
    end
  end
  if #missing > 0 then
    return false, "material mappings remain unavailable: " .. table.concat(missing, ",")
  end
  return true
end

local function createVisual(name)
  local object = createObject(VISUAL_CLASS)
  if not object then return nil, "BeamNG did not create the runtime visual" end
  local ok, createError = pcall(function()
    object.loadMode = 1
    if type(object.preApply) == "function" then object:preApply() end
    setCanSaveFalse(object)
    object:setField("shapeName", 0, VISUAL_SHAPE)
    object:setField("dynamic", 0, "1")
    object:setField("playAmbient", 0, "0")
    object:setField("collisionType", 0, "None")
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

local function createEffect(spec)
  local emitterData = scenetree.findObject(spec.emitter)
  if not emitterData then return nil, "stock emitter is unavailable: " .. spec.emitter end
  local object = createObject(EFFECT_CLASS)
  if not object then return nil, "BeamNG did not create effect " .. spec.name end
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
  local registered, registerError = registerInMission(object, spec.name)
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

local function lightSpecs(prefix)
  local specs = {}
  local sourcePrefix = PROP_MODEL .. "_"
  for _, source in ipairs(LIGHT_SPECS) do
    if type(source.name) ~= "string"
      or source.name:sub(1, #sourcePrefix) ~= sourcePrefix
      or (source.class ~= "PointLight" and source.class ~= "SpotLight") then
      error("invalid authored light specification")
    end
    local spec = {
      name = prefix .. "_" .. source.name:sub(#sourcePrefix + 1),
      role = source.role,
      class = source.class,
      position = vec3(
        source.local_position[1],
        source.local_position[2],
        source.local_position[3]
      ),
      color = source.color,
      brightness = source.brightness,
      castShadows = source.cast_shadows,
      radius = source.radius,
      range = source.range,
      innerAngle = source.inner_angle_degrees,
      outerAngle = source.outer_angle_degrees,
    }
    if source.local_direction then
      spec.direction = vec3(
        source.local_direction[1],
        source.local_direction[2],
        source.local_direction[3]
      )
    end
    specs[#specs + 1] = spec
  end
  return specs
end

local function createLight(spec)
  local object = createObject(spec.class)
  if not object then return nil, "BeamNG did not create light " .. spec.name end
  local ok, createError = pcall(function()
    object.loadMode = 1
    if type(object.preApply) == "function" then object:preApply() end
    setCanSaveFalse(object)
    object:setField("isEnabled", 0, "1")
    object:setField(
      "color",
      0,
      string.format("%.6f %.6f %.6f 1", spec.color[1], spec.color[2], spec.color[3])
    )
    object:setField("brightness", 0, tostring(spec.brightness))
    object:setField("castShadows", 0, spec.castShadows and "1" or "0")
    object:setField("priority", 0, "1")
    object:setField("attenuationRatio", 0, "0 1 1")
    object:setField("texSize", 0, "256")
    if spec.class == "PointLight" then
      object:setField("radius", 0, tostring(spec.radius))
      object:setField("shadowType", 0, "DualParaboloidSinglePass")
    else
      object:setField("range", 0, tostring(spec.range))
      object:setField("innerAngle", 0, tostring(spec.innerAngle))
      object:setField("outerAngle", 0, tostring(spec.outerAngle))
      object:setField("shadowSoftness", 0, "2")
      object:setField("shadowType", 0, "Spot")
    end
    if type(object.postApply) == "function" then object:postApply() end
  end)
  if not ok then
    pcall(function() object:delete() end)
    return nil, tostring(createError)
  end
  local registered, registerError = registerInMission(object, spec.name)
  if not registered then
    pcall(function() object:delete() end)
    return nil, registerError
  end
  return object
end

local function effectSpecs(prefix)
  local specs = {}
  for _, offset in ipairs(EFFECT_OFFSETS) do
    specs[#specs + 1] = {
      name = string.format("%s_%s", prefix, offset.suffix),
      emitter = offset.emitter,
      position = offset.position,
      inward = offset.inward,
    }
  end
  return specs
end

local function setObjectTransform(object, position, rotation, scale)
  object:setPosRot(
    position.x,
    position.y,
    position.z,
    rotation.x,
    rotation.y,
    rotation.z,
    rotation.w
  )
  if scale then object:setScale(scale) end
end

local function synchronizeTransforms(state)
  local vehicle = exactVehicle(state.propId)
  if not vehicle or not isWashProp(vehicle) then return false, "registered prop is unavailable" end
  local frame = propFrame(vehicle)
  if not frame then return false, "registered prop transform is invalid" end

  local ok, transformError = pcall(function()
    setObjectTransform(state.visual, frame.origin, frame.modelRotation, vec3(1, 1, 1))
    setObjectTransform(
      state.washTrigger,
      frame.origin + frame.modelRotation * WASH_TRIGGER_LOCAL_POSITION,
      frame.modelRotation,
      WASH_TRIGGER_SCALE
    )
    setObjectTransform(
      state.repairTrigger,
      frame.origin + frame.modelRotation * REPAIR_TRIGGER_LOCAL_POSITION,
      frame.modelRotation,
      REPAIR_TRIGGER_SCALE
    )
    setObjectTransform(
      state.launchTrigger,
      frame.origin + frame.modelRotation * LAUNCH_TRIGGER_LOCAL_POSITION,
      frame.modelRotation,
      LAUNCH_TRIGGER_SCALE
    )
    for index, effect in ipairs(state.effects) do
      local spec = state.effectSpecs[index]
      local worldDirection = frame.modelRotation * spec.inward
      worldDirection:normalize()
      setObjectTransform(
        effect,
        frame.origin + frame.modelRotation * spec.position,
        vec3(0, 0, 1):getRotationTo(worldDirection),
        vec3(1, 1, 1)
      )
    end
    local worldUp = frame.modelRotation * vec3(0, 0, 1)
    worldUp:normalize()
    for index, light in ipairs(state.lights) do
      local spec = state.lightSpecs[index]
      local rotation = frame.modelRotation
      if spec.direction then
        local worldDirection = frame.modelRotation * spec.direction
        worldDirection:normalize()
        rotation = quatFromDir(worldDirection, worldUp)
      end
      -- The engine links a light's illuminated extent to its object scale, so
      -- scaling a light to 1,1,1 silently collapses its radius/range to one
      -- meter. Move lights without touching scale, then re-assert the
      -- authored extent because pose updates can still rewrite it.
      setObjectTransform(
        light,
        frame.origin + frame.modelRotation * spec.position,
        rotation,
        nil
      )
      if type(light.preApply) == "function" then light:preApply() end
      if spec.class == "PointLight" then
        light:setField("radius", 0, tostring(spec.radius))
      else
        light:setField("range", 0, tostring(spec.range))
      end
      if type(light.postApply) == "function" then light:postApply() end
    end
    vehicle:setMeshAlpha(0, PROP_VISUAL_MESH, false)
  end)
  if not ok then return false, tostring(transformError) end
  state.origin = frame.origin
  state.vehicleRotation = frame.vehicleRotation
  state.modelRotation = frame.modelRotation
  return true
end

local function washSubjectCount(state)
  local count = 0
  for _ in pairs(state.washSubjects) do count = count + 1 end
  return count
end

local function setVisualAmbient(visual, enabled)
  if not visual then return end
  if type(visual.preApply) == "function" then visual:preApply() end
  visual:setField("playAmbient", 0, enabled and "1" or "0")
  if type(visual.postApply) == "function" then visual:postApply() end
end

local function forceWashSystemsOff(state)
  if state.visual then
    pcall(function() setVisualAmbient(state.visual, false) end)
  end
  for _, effect in ipairs(state.effects or {}) do
    pcall(function() effect:setActive(false) end)
  end
  state.washSystemsActive = false
end

local function setWashSystemsEnabled(state, enabled, reason)
  local visual = exactSceneObject(state.visualName, VISUAL_CLASS)
  if visual ~= state.visual then
    forceWashSystemsOff(state)
    emitError(state, "runtime_visual_missing")
    return false
  end
  for index, effect in ipairs(state.effects) do
    local spec = state.effectSpecs[index]
    if exactSceneObject(spec.name, EFFECT_CLASS) ~= effect
      or effect:getField("emitter", 0) ~= spec.emitter then
      forceWashSystemsOff(state)
      emitError(state, "runtime_effect_missing", {effect_index = index})
      return false
    end
  end

  local updated, updateError = pcall(function()
    setVisualAmbient(visual, enabled)
    for _, effect in ipairs(state.effects) do effect:setActive(enabled) end
  end)
  if not updated then
    forceWashSystemsOff(state)
    emitError(state, "wash_system_update_failed", {detail = tostring(updateError)})
    return false
  end
  state.washSystemsActive = enabled
  emitEvent(state, "I", enabled and "wash_systems_start" or "wash_systems_stop", {
    reason = reason,
    roller_sequence = "ambient",
    effect_count = #state.effects,
    emitter_counts = {
      BNGP_sprinkler = 6,
      BNGP_waterfallsteam = 6,
      BNGP_34 = 2,
      BNGP_2 = 2,
    },
  })
  return true
end

local function activeVehicle(state)
  if not state.activeRun then return nil end
  return eligibleSubject(state.activeRun.vehicleId)
end

local function bestEffortReleaseRepair(state, vehicleId, repair, reason)
  if not repair or not repair.holdMayExist or repair.bestEffortReleaseQueued then
    return false
  end
  local vehicle = eligibleSubject(vehicleId)
  if not vehicle then return false end
  local queued = queueVehicleCommand(
    vehicle,
    repairReleaseCommand(state.propId, repair.token, repair.previousFrozen),
    state,
    "repair_best_effort_release_failed",
    false
  )
  if queued then
    repair.bestEffortReleaseQueued = true
    emitEvent(state, "I", "repair_release_best_effort", {
      subject_id = vehicleId,
      repair_token = repair.token,
      reason = reason,
    })
  end
  return queued
end

local countdownJob

local function releaseVehicle(state, vehicle, reason)
  local run = state.activeRun
  if not run then return end
  if not run.holding and not run.holdCommandPending and not run.releasePending then return end
  if vehicle then
    queueVehicleCommand(
      vehicle,
      releaseVehicleCommand(state.propId, run.number),
      state,
      "release_command_failed"
    )
  end
  run.holding = false
  run.holdCommandPending = false
  run.releasePending = false
  emitEvent(state, "I", "release", {
    reason = reason,
    vehicle_id = run.vehicleId,
  })
end

local function abortActiveRun(state, reason, vehicle)
  if state.activeRun then
    releaseVehicle(state, vehicle or activeVehicle(state), reason)
    emitEvent(state, "I", "abort", {
      reason = reason,
      vehicle_id = state.activeRun.vehicleId,
    })
  end
  state.activeRun = nil
end

local function finishActiveRunOnExit(state, vehicleId, reason, vehicle)
  local run = state.activeRun
  if not run or run.vehicleId ~= vehicleId then return false end
  if run.phase == "launched" then
    emitEvent(state, "I", "launch_complete", {
      vehicle_id = vehicleId,
      exit_reason = reason,
    })
    state.activeRun = nil
  else
    abortActiveRun(state, reason, vehicle)
  end
  return true
end

local function removeWashSubject(state, vehicleId, reason)
  state.pendingLaunchEntries[vehicleId] = nil
  local repair = state.repairOccupants[vehicleId]
  bestEffortReleaseRepair(state, vehicleId, repair, reason)
  state.repairOccupants[vehicleId] = nil
  if not state.washSubjects[vehicleId] then return end
  state.washSubjects[vehicleId] = nil
  if finishActiveRunOnExit(state, vehicleId, reason) then
    state.armed = true
  end
  emitEvent(state, "I", "wash_subject_removed", {
    subject_id = vehicleId,
    reason = reason,
  })
  if washSubjectCount(state) == 0 and state.washSystemsActive then
    setWashSystemsEnabled(state, false, reason)
  end
end

local function launchVehicle(state, vehicle)
  local run = state.activeRun
  if not run or run.phase ~= "release_grace" or run.holding then return end
  local direction = vehicle:getDirectionVector()
  if not direction
    or not finiteNumber(direction.x)
    or not finiteNumber(direction.y)
    or not finiteNumber(direction.z)
    or direction:length() < 0.000001 then
    emitError(state, "invalid_forward_axis")
    abortActiveRun(state, "invalid_forward_axis", vehicle)
    return
  end
  direction:normalize()
  local velocity = direction * LAUNCH_SPEED_MPS
  showMessage("GO!", 1.5)
  emitEvent(state, "I", "go", {
    vehicle_id = vehicle:getId(),
    direction_x = direction.x,
    direction_y = direction.y,
    direction_z = direction.z,
  })
  local launched, launchError = pcall(function()
    vehicle:applyClusterVelocityScaleAdd(
      vehicle:getRefNodeId(),
      0,
      velocity.x,
      velocity.y,
      velocity.z
    )
  end)
  if not launched then
    emitError(state, "velocity_injection_failed", {detail = tostring(launchError)})
    abortActiveRun(state, "velocity_injection_failed", vehicle)
    return
  end
  run.phase = "launched"
  emitEvent(state, "I", "launch", {
    vehicle_id = vehicle:getId(),
    target_speed_mps = LAUNCH_SPEED_MPS,
    velocity_x = velocity.x,
    velocity_y = velocity.y,
    velocity_z = velocity.z,
  })
end

local function requestReleaseForLaunch(state, vehicle)
  local run = state.activeRun
  if not run or run.phase ~= "countdown" or not run.holding then return false end
  run.phase = "release_pending"
  run.releasePending = true
  run.ackElapsed = 0
  local queued = queueVehicleCommand(
    vehicle,
    releaseVehicleCommand(state.propId, run.number),
    state,
    "release_command_failed"
  )
  if not queued then
    abortActiveRun(state, "release_command_failed", vehicle)
    state.armed = true
    return false
  end
  emitEvent(state, "I", "release_requested", {
    reason = "launch",
    vehicle_id = run.vehicleId,
  })
  return true
end

countdownJob = function(job, propId, runNumber)
  local timer = hptimer()
  for nextIndex = 2, #COUNTDOWN_MESSAGES do
    job.sleep(COUNTDOWN_INTERVAL_SECONDS)
    local state = installations[propId]
    if not state
      or not state.activeRun
      or not state.activeRun.holding
      or state.activeRun.phase ~= "countdown"
      or state.activeRun.number ~= runNumber then
      return
    end
    local vehicle = activeVehicle(state)
    if not vehicle then
      emitError(state, "active_vehicle_missing")
      abortActiveRun(state, "active_vehicle_missing")
      return
    end
    state.activeRun.elapsedTime = timer:stop() / 1000
    showMessage(COUNTDOWN_MESSAGES[nextIndex], 1.1)
    emitEvent(state, "I", COUNTDOWN_EVENTS[nextIndex], {
      vehicle_id = vehicle:getId(),
      countdown_value = #COUNTDOWN_MESSAGES - nextIndex + 1,
      elapsed_time_seconds = state.activeRun.elapsedTime,
    })
  end

  job.sleep(COUNTDOWN_INTERVAL_SECONDS)
  local state = installations[propId]
  if not state
    or not state.activeRun
    or not state.activeRun.holding
    or state.activeRun.phase ~= "countdown"
    or state.activeRun.number ~= runNumber then
    return
  end
  local vehicle = activeVehicle(state)
  if not vehicle then
    emitError(state, "active_vehicle_missing")
    abortActiveRun(state, "active_vehicle_missing")
    return
  end
  state.activeRun.elapsedTime = timer:stop() / 1000
  requestReleaseForLaunch(state, vehicle)
end

local function onEricrolphCannonCarWashHoldAcknowledged(
  vehicleId,
  propId,
  runNumber,
  accepted,
  previousFrozen,
  actualFrozen
)
  if not integer(vehicleId)
    or not integer(propId)
    or not integer(runNumber)
    or type(accepted) ~= "boolean"
    or type(previousFrozen) ~= "boolean"
    or type(actualFrozen) ~= "boolean" then
    return
  end
  local state = installations[propId]
  local run = state and state.activeRun or nil
  if not run
    or run.vehicleId ~= vehicleId
    or run.number ~= runNumber
    or run.phase ~= "hold_pending" then
    return
  end
  run.holdCommandPending = false
  run.previousFrozen = previousFrozen
  -- An accepted hold owns a Vehicle Lua state record even when the reported
  -- freeze state is invalid. Mark that ownership before validation so every
  -- failure path queues a matching release and clears the record.
  run.holding = accepted
  if not accepted or not actualFrozen then
    emitError(state, "hold_acknowledgement_failed", {
      vehicle_id = vehicleId,
      accepted = accepted,
      actual_frozen = actualFrozen,
    })
    abortActiveRun(state, "hold_acknowledgement_failed", activeVehicle(state))
    state.armed = true
    return
  end
  if previousFrozen then
    emitError(state, "vehicle_already_frozen", {vehicle_id = vehicleId})
    abortActiveRun(state, "vehicle_already_frozen", activeVehicle(state))
    state.armed = true
    return
  end

  local vehicle = activeVehicle(state)
  if not vehicle then
    emitError(state, "active_vehicle_missing", {vehicle_id = vehicleId})
    abortActiveRun(state, "active_vehicle_missing")
    state.armed = true
    return
  end
  -- Stop the complete main cluster once, after Vehicle Lua confirms the
  -- controller freeze. A uniform one-shot stop preserves relative node
  -- velocities; unlike the old per-frame override it does not fight
  -- suspension and contact impulses throughout the countdown.
  local stopped, stopError = pcall(function()
    vehicle:applyClusterVelocityScaleAdd(vehicle:getRefNodeId(), 0, 0, 0, 0)
  end)
  if not stopped then
    emitError(state, "hold_velocity_stop_failed", {detail = tostring(stopError)})
    abortActiveRun(state, "hold_velocity_stop_failed", vehicle)
    state.armed = true
    return
  end

  run.phase = "countdown"
  run.ackElapsed = 0
  showMessage(COUNTDOWN_MESSAGES[1], 1.1)
  emitEvent(state, "I", "hold_ack", {
    vehicle_id = vehicleId,
    previous_frozen = previousFrozen,
    actual_frozen = actualFrozen,
  })
  emitEvent(state, "I", "hold_start", {vehicle_id = vehicleId})
  emitEvent(state, "I", "countdown_timer_start", {vehicle_id = vehicleId})
  emitEvent(state, "I", COUNTDOWN_EVENTS[1], {
    vehicle_id = vehicleId,
    countdown_value = #COUNTDOWN_MESSAGES,
    elapsed_time_seconds = 0,
  })
  local scheduled, scheduleError = pcall(function()
    extensions.core_jobsystem.create(countdownJob, nil, propId, runNumber)
  end)
  if not scheduled then
    emitError(state, "countdown_schedule_failed", {detail = tostring(scheduleError)})
    abortActiveRun(state, "countdown_schedule_failed", activeVehicle(state))
    state.armed = true
  end
end

local function onEricrolphCannonCarWashReleaseAcknowledged(
  vehicleId,
  propId,
  runNumber,
  restored,
  previousFrozen,
  actualFrozen
)
  if not integer(vehicleId)
    or not integer(propId)
    or not integer(runNumber)
    or type(restored) ~= "boolean"
    or type(previousFrozen) ~= "boolean"
    or type(actualFrozen) ~= "boolean" then
    return
  end
  local state = installations[propId]
  local run = state and state.activeRun or nil
  if not run
    or run.vehicleId ~= vehicleId
    or run.number ~= runNumber
    or run.phase ~= "release_pending" then
    return
  end
  if not restored or previousFrozen ~= run.previousFrozen or actualFrozen ~= previousFrozen then
    emitError(state, "release_acknowledgement_failed", {
      vehicle_id = vehicleId,
      restored = restored,
      previous_frozen = previousFrozen,
      actual_frozen = actualFrozen,
    })
    abortActiveRun(state, "release_acknowledgement_failed", activeVehicle(state))
    state.armed = true
    return
  end

  run.holding = false
  run.releasePending = false
  run.phase = "release_grace"
  run.releaseGraceFrames = RELEASE_GRACE_SIM_FRAMES
  run.ackElapsed = 0
  emitEvent(state, "I", "release_ack", {
    reason = "launch",
    vehicle_id = vehicleId,
    previous_frozen = previousFrozen,
    actual_frozen = actualFrozen,
  })
  emitEvent(state, "I", "release", {
    reason = "launch",
    vehicle_id = vehicleId,
  })
end

local handleLaunchTrigger

local function processPendingLaunch(state, subjectId)
  local pending = state.pendingLaunchEntries[subjectId]
  if not pending or not state.washSubjects[subjectId] or not state.washSystemsActive then return end
  local repair = state.repairOccupants[subjectId]
  if not repair or repair.phase ~= "complete"
    or repair.resetEdgeGuard
    or repair.washExitDeferred then return end
  state.pendingLaunchEntries[subjectId] = nil
  handleLaunchTrigger(state, pending)
end

local function validateTriggerEvent(state, data, kind)
  if type(data) ~= "table"
    or (data.event ~= "enter" and data.event ~= "exit")
    or not integer(data.triggerID)
    or not integer(data.subjectID) then
    return nil
  end
  local expectedByKind = {
    wash = state.washTrigger,
    repair = state.repairTrigger,
    launch = state.launchTrigger,
  }
  local nameByKind = {
    wash = state.washTriggerName,
    repair = state.repairTriggerName,
    launch = state.launchTriggerName,
  }
  local modeByKind = {wash = "Overlaps", repair = "Overlaps", launch = "Contains"}
  local expected = expectedByKind[kind]
  local expectedName = nameByKind[kind]
  local expectedMode = modeByKind[kind]
  if not expected or not expectedName or not expectedMode then return nil end
  if data.triggerName ~= expectedName then return nil end
  local byId = scenetree.findObjectById(data.triggerID)
  local byName = scenetree.findObject(expectedName)
  if byId ~= expected or byName ~= expected then return nil end
  if expected:getClassName() ~= TRIGGER_CLASS then return nil end
  if expected:getField("triggerMode", 0) ~= expectedMode then return nil end
  if expected:getField("triggerTestType", 0) ~= "Bounding box" then return nil end
  return eligibleSubject(data.subjectID)
end

local function failRepair(state, vehicleId, reason, fields)
  local repair = state.repairOccupants[vehicleId]
  local deferredWashExit = repair and repair.washExitDeferred == true
  if repair then
    repair.phase = "failed"
    repair.elapsed = 0
    repair.resetEdgeGuard = false
    bestEffortReleaseRepair(state, vehicleId, repair, reason)
  end
  local payload = fields or {}
  payload.subject_id = vehicleId
  emitError(state, reason, payload)
  if deferredWashExit then
    removeWashSubject(state, vehicleId, "deferred_exit_after_repair_failure")
  end
end

local function onEricrolphCannonCarWashRepairIntegrityAcknowledged(
  vehicleId,
  propId,
  token,
  stage,
  holdAccepted,
  previousFrozen,
  actualFrozen,
  damage,
  partDamageCount,
  brokenBeamCount,
  deflatedTireCount
)
  if not integer(vehicleId)
    or not integer(propId)
    or not integer(token)
    or (stage ~= "before" and stage ~= "after")
    or type(holdAccepted) ~= "boolean"
    or type(previousFrozen) ~= "boolean"
    or type(actualFrozen) ~= "boolean"
    or not finiteNumber(damage)
    or not nonnegativeInteger(partDamageCount)
    or not nonnegativeInteger(brokenBeamCount)
    or not nonnegativeInteger(deflatedTireCount) then
    return
  end
  local state = installations[propId]
  local repair = state and state.repairOccupants[vehicleId] or nil
  if not repair or repair.token ~= token then
    if stage == "before" and holdAccepted and actualFrozen then
      local orphanedVehicle = exactVehicle(vehicleId)
      if orphanedVehicle and not isWashProp(orphanedVehicle) then
        queueVehicleCommand(
          orphanedVehicle,
          repairReleaseCommand(propId, token, previousFrozen),
          state,
          "orphaned_repair_release_command_failed",
          false
        )
      end
    end
    return
  end
  local expectedPhase = stage == "before" and "precheck_pending"
    or "verify_pending"
  if repair.phase ~= expectedPhase then return end
  if not holdAccepted
    or not actualFrozen
    or (stage ~= "before" and previousFrozen ~= repair.previousFrozen) then
    failRepair(state, vehicleId, "repair_hold_acknowledgement_failed", {
      repair_stage = stage,
      repair_token = token,
      hold_accepted = holdAccepted,
      previous_frozen = previousFrozen,
      actual_frozen = actualFrozen,
    })
    return
  end

  if stage == "before" then
    repair.previousFrozen = previousFrozen
    repair.before = {
      damage = damage,
      partDamageCount = partDamageCount,
      brokenBeamCount = brokenBeamCount,
      deflatedTireCount = deflatedTireCount,
    }
    emitEvent(state, "I", "repair_hold_ack", {
      subject_id = vehicleId,
      repair_token = token,
      previous_frozen = previousFrozen,
      actual_frozen = actualFrozen,
    })
    emitEvent(state, "I", "repair_snapshot", {
      subject_id = vehicleId,
      repair_token = token,
      damage_before = damage,
      part_damage_before = partDamageCount,
      broken_beams_before = brokenBeamCount,
      deflated_tires_before = deflatedTireCount,
    })
    local vehicle = eligibleSubject(vehicleId)
    if not vehicle then
      failRepair(state, vehicleId, "repair_vehicle_missing")
      return
    end
    local target, targetError = repairTargetPose(vehicle, state.repairTrigger)
    if not target then
      failRepair(state, vehicleId, "repair_target_pose_failed", {detail = targetError})
      return
    end
    for key, value in pairs(target) do repair[key] = value end
    repair.phase = "reset_pending"
    repair.elapsed = 0
    repair.resetEdgeGuard = true
    repair.washExitDeferred = false
    emitEvent(state, "I", "repair_requested", {
      subject_id = vehicleId,
      repair_token = token,
      strategy = "RESET_PHYSICS",
      pose_policy = "center_oobb_on_trigger_axis_align_upright_preserve_travel_sign",
      centerline_error_before_m = repair.centerlineErrorBefore,
      alignment_translation_m = repair.alignmentTranslation,
      travel_direction_dot_before = repair.travelDirectionDotBefore,
      travel_sign = repair.travelSign,
    })
    local reset, resetError = pcall(function()
      vehicle:requestReset(RESET_PHYSICS)
      vehicle:resetBrokenFlexMesh()
    end)
    if not reset then
      failRepair(state, vehicleId, "repair_reset_failed", {detail = tostring(resetError)})
      return
    end
    return
  end

  repair.after = {
    damage = damage,
    partDamageCount = partDamageCount,
    brokenBeamCount = brokenBeamCount,
    deflatedTireCount = deflatedTireCount,
  }
  if damage > 0.01
    or partDamageCount ~= 0
    or brokenBeamCount ~= 0
    or deflatedTireCount ~= 0 then
    failRepair(state, vehicleId, "repair_verification_failed", {
      damage_after = damage,
      part_damage_after = partDamageCount,
      broken_beams_after = brokenBeamCount,
      deflated_tires_after = deflatedTireCount,
    })
    return
  end

  local vehicle = eligibleSubject(vehicleId)
  local poseMetrics = repairedPoseMetrics(vehicle, repair)
  if not poseMetrics then
    failRepair(state, vehicleId, "repair_pose_verification_unavailable")
    return
  end
  repair.positionDrift = poseMetrics.targetPositionDrift
  repair.directionDot = poseMetrics.corridorDirectionDot
  repair.centerlineError = poseMetrics.centerlineError
  repair.corridorDirectionDot = poseMetrics.corridorDirectionDot
  repair.uprightDot = poseMetrics.uprightDot
  repair.travelDirectionDot = poseMetrics.travelDirectionDot
  repair.travelSignPreserved = poseMetrics.travelSignPreserved
  if repair.centerlineError > REPAIR_MAX_CENTERLINE_ERROR_METERS
    or repair.corridorDirectionDot < REPAIR_MIN_CORRIDOR_DOT
    or repair.uprightDot < REPAIR_MIN_UPRIGHT_DOT
    or not repair.travelSignPreserved then
    local correctionAttempts = repair.poseCorrectionAttempts or 0
    if correctionAttempts < REPAIR_MAX_POSE_CORRECTION_ATTEMPTS then
      -- RESET_PHYSICS can change the renewed vehicle's OOBB-to-origin offset.
      -- Recompute from the live repaired geometry; reusing the pre-reset target
      -- cannot remove that residual and is especially visible on buses.
      local correctionTarget, correctionTargetError = repairTargetPose(
        vehicle,
        state.repairTrigger
      )
      if not correctionTarget then
        failRepair(state, vehicleId, "repair_pose_correction_target_failed", {
          detail = correctionTargetError,
        })
        return
      end
      if correctionTarget.targetDirection:dot(repair.targetDirection) <= 0 then
        failRepair(state, vehicleId, "repair_pose_correction_travel_sign_changed")
        return
      end
      repair.poseCorrectionAttempts = correctionAttempts + 1
      repair.phase = "pose_restore_pending"
      repair.elapsed = 0
      repair.targetPosition = correctionTarget.targetPosition
      repair.targetRotation = correctionTarget.targetRotation
      local position = correctionTarget.targetPosition
      local rotation = correctionTarget.targetRotation
      local corrected, correctionError = pcall(function()
        vehicle:setPositionRotation(
          position.x,
          position.y,
          position.z,
          rotation.x,
          rotation.y,
          rotation.z,
          rotation.w
        )
      end)
      if not corrected then
        failRepair(state, vehicleId, "repair_pose_correction_failed", {
          detail = tostring(correctionError),
          correction_attempt = repair.poseCorrectionAttempts,
        })
        return
      end
      emitEvent(state, "I", "repair_pose_correction_requested", {
        subject_id = vehicleId,
        repair_token = token,
        correction_attempt = repair.poseCorrectionAttempts,
        centerline_error_m = repair.centerlineError,
        corridor_direction_dot = repair.corridorDirectionDot,
        upright_dot = repair.uprightDot,
        travel_direction_dot = repair.travelDirectionDot,
        correction_translation_m = correctionTarget.alignmentTranslation,
      })
      return
    end
    failRepair(state, vehicleId, "repair_pose_verification_failed", {
      centerline_error_m = repair.centerlineError,
      corridor_direction_dot = repair.corridorDirectionDot,
      upright_dot = repair.uprightDot,
      travel_direction_dot = repair.travelDirectionDot,
      travel_sign_preserved = repair.travelSignPreserved,
      correction_attempts = correctionAttempts,
    })
    return
  end
  repair.phase = "release_pending"
  repair.elapsed = 0
  repair.bestEffortReleaseQueued = false
  local queued, queueError = queueVehicleCommand(
    vehicle,
    repairReleaseCommand(state.propId, repair.token, repair.previousFrozen),
    state,
    "repair_release_command_failed",
    false
  )
  if not queued then
    failRepair(state, vehicleId, "repair_release_command_failed", {detail = queueError})
    return
  end
  emitEvent(state, "I", "repair_release_requested", {
    subject_id = vehicleId,
    repair_token = token,
    previous_frozen = repair.previousFrozen,
  })
end

local function onEricrolphCannonCarWashRepairReleaseAcknowledged(
  vehicleId,
  propId,
  token,
  restored,
  previousFrozen,
  actualFrozen
)
  if not integer(vehicleId)
    or not integer(propId)
    or not integer(token)
    or type(restored) ~= "boolean"
    or type(previousFrozen) ~= "boolean"
    or type(actualFrozen) ~= "boolean" then
    return
  end
  local state = installations[propId]
  local repair = state and state.repairOccupants[vehicleId] or nil
  if not repair or repair.token ~= token or repair.phase ~= "release_pending" then return end
  if not restored
    or previousFrozen ~= repair.previousFrozen
    or actualFrozen ~= previousFrozen then
    failRepair(state, vehicleId, "repair_release_acknowledgement_failed", {
      repair_token = token,
      restored = restored,
      previous_frozen = previousFrozen,
      actual_frozen = actualFrozen,
    })
    return
  end

  repair.holdMayExist = false
  repair.phase = "complete"
  repair.elapsed = 0
  repair.edgeGuardFrames = REPAIR_SETTLE_SIM_FRAMES
  showMessage("Vehicle restored!", 1.5)
  emitEvent(state, "I", "repair_release_ack", {
    subject_id = vehicleId,
    repair_token = token,
    previous_frozen = previousFrozen,
    actual_frozen = actualFrozen,
  })
  emitEvent(state, "I", "repair_complete", {
    subject_id = vehicleId,
    repair_token = token,
    damage_after = repair.after.damage,
    part_damage_after = repair.after.partDamageCount,
    broken_beams_after = repair.after.brokenBeamCount,
    deflated_tires_after = repair.after.deflatedTireCount,
    position_drift_m = repair.positionDrift,
    direction_dot = repair.directionDot,
    centerline_error_before_m = repair.centerlineErrorBefore,
    centerline_error_m = repair.centerlineError,
    alignment_translation_m = repair.alignmentTranslation,
    corridor_direction_dot = repair.corridorDirectionDot,
    upright_dot = repair.uprightDot,
    travel_direction_dot = repair.travelDirectionDot,
    travel_sign_preserved = repair.travelSignPreserved,
    travel_sign = repair.travelSign,
    pose_correction_attempts = repair.poseCorrectionAttempts or 0,
  })
  processPendingLaunch(state, vehicleId)
end

local function handleRepairTrigger(state, data)
  local vehicle = validateTriggerEvent(state, data, "repair")
  if not vehicle then return end
  if data.event == "exit" then
    local repair = state.repairOccupants[data.subjectID]
    if repair then repair.exitObserved = true end
    emitEvent(state, "I", "repair_trigger_exit", {subject_id = data.subjectID})
    return
  end
  if state.repairOccupants[data.subjectID] then return end

  repairCounter = repairCounter + 1
  state.repairOccupants[data.subjectID] = {
    token = repairCounter,
    phase = "precheck_pending",
    elapsed = 0,
    exitObserved = false,
    holdMayExist = false,
    bestEffortReleaseQueued = false,
  }
  emitEvent(state, "I", "repair_trigger_enter", {
    subject_id = data.subjectID,
    repair_token = repairCounter,
  })
  local queued, queueError = queueVehicleCommand(
    vehicle,
    repairIntegrityCommand(state.propId, repairCounter, "before"),
    state,
    "repair_precheck_command_failed",
    false
  )
  if queued then
    state.repairOccupants[data.subjectID].holdMayExist = true
  else
    failRepair(state, data.subjectID, "repair_precheck_command_failed", {
      detail = queueError,
    })
  end
end

local function handleWashTrigger(state, data)
  local vehicle = validateTriggerEvent(state, data, "wash")
  if not vehicle then return end
  if data.event == "enter" then
    local repair = state.repairOccupants[data.subjectID]
    if repair and repair.resetEdgeGuard then repair.washExitDeferred = false end
    if state.washSubjects[data.subjectID] then return end
    state.washSubjects[data.subjectID] = true
    emitEvent(state, "I", "wash_trigger_enter", {subject_id = data.subjectID})
    if not state.washSystemsActive and not setWashSystemsEnabled(state, true, "vehicle_enter") then
      state.washSubjects[data.subjectID] = nil
      return
    end
    processPendingLaunch(state, data.subjectID)
    return
  end
  if not state.washSubjects[data.subjectID] then return end
  local repair = state.repairOccupants[data.subjectID]
  if repair and repair.resetEdgeGuard then
    repair.washExitDeferred = true
    emitEvent(state, "I", "wash_trigger_exit_suppressed", {
      subject_id = data.subjectID,
      reason = "intentional_repair_reset",
      repair_token = repair.token,
    })
    return
  end
  emitEvent(state, "I", "wash_trigger_exit", {subject_id = data.subjectID})
  removeWashSubject(state, data.subjectID, "last_vehicle_exit")
end

handleLaunchTrigger = function(state, data)
  local vehicle = validateTriggerEvent(state, data, "launch")
  if not vehicle then return end
  if data.event == "exit" then
    state.pendingLaunchEntries[data.subjectID] = nil
    if state.activeRun
      and state.activeRun.vehicleId == data.subjectID
      and state.activeRun.phase ~= "launched"
      and state.washSubjects[data.subjectID]
      and state.washSystemsActive then
      emitEvent(state, "I", "containment_exit_suppressed", {
        vehicle_id = data.subjectID,
        reason = "verified_subject_still_in_wash",
        active_phase = state.activeRun.phase,
      })
      return
    end
    finishActiveRunOnExit(state, data.subjectID, "launch_trigger_exit", vehicle)
    state.armed = state.activeRun == nil
    emitEvent(state, "I", "trigger_exit", {vehicle_id = data.subjectID})
    return
  end
  if not state.washSubjects[data.subjectID] or not state.washSystemsActive then
    state.pendingLaunchEntries[data.subjectID] = {
      event = data.event,
      triggerID = data.triggerID,
      triggerName = data.triggerName,
      subjectID = data.subjectID,
    }
    emitEvent(state, "I", "launch_deferred", {
      vehicle_id = data.subjectID,
      reason = "wash_not_active",
    })
    return
  end
  local repair = state.repairOccupants[data.subjectID]
  if not repair or repair.phase ~= "complete"
    or repair.resetEdgeGuard
    or repair.washExitDeferred then
    state.pendingLaunchEntries[data.subjectID] = {
      event = data.event,
      triggerID = data.triggerID,
      triggerName = data.triggerName,
      subjectID = data.subjectID,
    }
    emitEvent(state, "I", "launch_deferred", {
      vehicle_id = data.subjectID,
      reason = repair and "repair_pending" or "repair_not_started",
    })
    return
  end
  if not state.armed or state.activeRun then return end

  state.armed = false
  runCounter = runCounter + 1
  state.activeRun = {
    number = runCounter,
    vehicleId = data.subjectID,
    triggerId = data.triggerID,
    holding = false,
    holdCommandPending = true,
    releasePending = false,
    phase = "hold_pending",
    elapsedTime = 0,
    ackElapsed = 0,
  }
  emitEvent(state, "I", "containment_verified", {
    vehicle_id = data.subjectID,
    trigger_mode = state.launchTrigger:getField("triggerMode", 0),
    trigger_test_type = state.launchTrigger:getField("triggerTestType", 0),
  })
  if not queueVehicleCommand(
    vehicle,
    holdVehicleCommand(state.propId, state.activeRun.number),
    state,
    "hold_command_failed"
  ) then
    abortActiveRun(state, "hold_command_failed", vehicle)
    state.armed = true
    return
  end
  emitEvent(state, "I", "hold_requested", {
    vehicle_id = data.subjectID,
    run_number = state.activeRun.number,
  })
end

local function onBeamNGTrigger(data)
  if type(data) ~= "table" or not integer(data.triggerID) then return end
  if installations[data.subjectID] then return end
  local owner = triggerOwners[data.triggerID]
  if not owner then return end
  local state = installations[owner.propId]
  if not state then return end
  if owner.kind == "wash" then
    handleWashTrigger(state, data)
  elseif owner.kind == "repair" then
    handleRepairTrigger(state, data)
  elseif owner.kind == "launch" then
    handleLaunchTrigger(state, data)
  end
end

local function deleteSceneObject(object)
  if not object then return end
  pcall(function()
    if object:getClassName() == EFFECT_CLASS then object:setActive(false) end
  end)
  pcall(function() object:delete() end)
end

local function forgetTriggerOwner(trigger)
  if not trigger then return end
  local resolved, triggerId = pcall(function() return trigger:getId() end)
  if resolved and integer(triggerId) then triggerOwners[triggerId] = nil end
end

local function rebuildTriggersAfterReset(state)
  forgetTriggerOwner(state.washTrigger)
  forgetTriggerOwner(state.repairTrigger)
  forgetTriggerOwner(state.launchTrigger)
  deleteSceneObject(state.washTrigger)
  deleteSceneObject(state.repairTrigger)
  deleteSceneObject(state.launchTrigger)
  state.washTrigger = nil
  state.repairTrigger = nil
  state.launchTrigger = nil

  state.resetCount = (state.resetCount or 0) + 1
  state.washTriggerName = string.format(
    "%s_reset_%d_wash_trigger",
    state.prefix,
    state.resetCount
  )
  state.launchTriggerName = string.format(
    "%s_reset_%d_launch_trigger",
    state.prefix,
    state.resetCount
  )
  state.repairTriggerName = string.format(
    "%s_reset_%d_repair_trigger",
    state.prefix,
    state.resetCount
  )

  local washTrigger, washError = createTrigger(state.washTriggerName, "Overlaps")
  if not washTrigger then return false, washError end
  state.washTrigger = washTrigger

  local repairTrigger, repairError = createTrigger(state.repairTriggerName, "Overlaps")
  if not repairTrigger then
    deleteSceneObject(washTrigger)
    state.washTrigger = nil
    return false, repairError
  end
  state.repairTrigger = repairTrigger

  local launchTrigger, launchError = createTrigger(state.launchTriggerName, "Contains")
  if not launchTrigger then
    deleteSceneObject(washTrigger)
    deleteSceneObject(repairTrigger)
    state.washTrigger = nil
    state.repairTrigger = nil
    return false, launchError
  end
  state.launchTrigger = launchTrigger

  local synced, syncError = synchronizeTransforms(state)
  if not synced then
    deleteSceneObject(washTrigger)
    deleteSceneObject(repairTrigger)
    deleteSceneObject(launchTrigger)
    state.washTrigger = nil
    state.repairTrigger = nil
    state.launchTrigger = nil
    return false, syncError
  end
  triggerOwners[washTrigger:getId()] = {propId = state.propId, kind = "wash"}
  triggerOwners[repairTrigger:getId()] = {propId = state.propId, kind = "repair"}
  triggerOwners[launchTrigger:getId()] = {propId = state.propId, kind = "launch"}
  return true
end

local function unloadIfIdleJob(job)
  unloadRequested = false
  if not extensionUnloading and next(installations) == nil then
    emitEvent(nil, "I", "extension_unload_attempt", {
      extension_name = RUNTIME_EXTENSION_NAME,
    })
    local unloaded, unloadError = pcall(function()
      extensions.unload(RUNTIME_EXTENSION_NAME)
    end)
    if not unloaded then
      emitError(nil, "extension_unload_failed", {detail = tostring(unloadError)})
    end
  end
end

local function requestUnloadIfIdle()
  if extensionUnloading or unloadRequested or next(installations) ~= nil then return end
  unloadRequested = true
  local scheduled = pcall(function()
    extensions.core_jobsystem.create(unloadIfIdleJob)
  end)
  if not scheduled then unloadRequested = false end
end

local function cleanupInstallation(state, reason)
  if not state then return end
  for vehicleId, repair in pairs(state.repairOccupants or {}) do
    bestEffortReleaseRepair(state, vehicleId, repair, reason or "installation_cleanup")
  end
  abortActiveRun(state, reason)
  forceWashSystemsOff(state)
  forgetTriggerOwner(state.washTrigger)
  forgetTriggerOwner(state.repairTrigger)
  forgetTriggerOwner(state.launchTrigger)
  deleteSceneObject(state.washTrigger)
  deleteSceneObject(state.repairTrigger)
  deleteSceneObject(state.launchTrigger)
  for _, effect in ipairs(state.effects or {}) do deleteSceneObject(effect) end
  for _, light in ipairs(state.lights or {}) do deleteSceneObject(light) end
  deleteSceneObject(state.visual)
  local vehicle = exactVehicle(state.propId)
  if vehicle and isWashProp(vehicle) then
    pcall(function() vehicle:setMeshAlpha(1, PROP_VISUAL_MESH, false) end)
  end
  installations[state.propId] = nil
  emitEvent(state, "I", "prop_unregistered", {reason = reason})
  requestUnloadIfIdle()
end

local function cleanupAll(reason)
  local states = {}
  for _, state in pairs(installations) do states[#states + 1] = state end
  for _, state in ipairs(states) do cleanupInstallation(state, reason) end
  triggerOwners = {}
end

local function registerProp(propId)
  if not integer(propId) then return false end
  local vehicle = exactVehicle(propId)
  if not vehicle or not isWashProp(vehicle) then return false end
  local existing = installations[propId]
  if existing then
    local synced, syncError = synchronizeTransforms(existing)
    if synced then
      acknowledgeRegistration(vehicle)
      return true
    end
    emitError(existing, "transform_sync_failed", {detail = syncError})
    cleanupInstallation(existing, "registration_recovery")
  end

  local prefix = string.format("ericrolph_cannon_car_wash_runtime_%d", propId)
  local state = {
    propId = propId,
    prefix = prefix,
    visualName = prefix .. "_visual",
    washTriggerName = prefix .. "_wash_trigger",
    repairTriggerName = prefix .. "_repair_trigger",
    launchTriggerName = prefix .. "_launch_trigger",
    effects = {},
    effectSpecs = effectSpecs(prefix),
    lights = {},
    lightSpecs = lightSpecs(prefix),
    washSubjects = {},
    repairOccupants = {},
    pendingLaunchEntries = {},
    washSystemsActive = false,
    activeRun = nil,
    armed = true,
    resetCount = 0,
    transformElapsed = 0,
  }
  installations[propId] = state

  local materialsReady, materialError = ensureVisualMaterials()
  if not materialsReady then
    emitError(state, "visual_materials_unavailable", {detail = materialError})
    cleanupInstallation(state, "registration_failed")
    return false
  end

  local visual, visualError = createVisual(state.visualName)
  if not visual then
    emitError(state, "visual_creation_failed", {detail = visualError})
    cleanupInstallation(state, "registration_failed")
    return false
  end
  state.visual = visual
  local washTrigger, washError = createTrigger(state.washTriggerName, "Overlaps")
  if not washTrigger then
    emitError(state, "wash_trigger_creation_failed", {detail = washError})
    cleanupInstallation(state, "registration_failed")
    return false
  end
  state.washTrigger = washTrigger
  local repairTrigger, repairError = createTrigger(state.repairTriggerName, "Overlaps")
  if not repairTrigger then
    emitError(state, "repair_trigger_creation_failed", {detail = repairError})
    cleanupInstallation(state, "registration_failed")
    return false
  end
  state.repairTrigger = repairTrigger
  local launchTrigger, launchError = createTrigger(state.launchTriggerName, "Contains")
  if not launchTrigger then
    emitError(state, "launch_trigger_creation_failed", {detail = launchError})
    cleanupInstallation(state, "registration_failed")
    return false
  end
  state.launchTrigger = launchTrigger

  for _, spec in ipairs(state.effectSpecs) do
    local effect, effectError = createEffect(spec)
    if not effect then
      emitError(state, "effect_creation_failed", {detail = effectError, name = spec.name})
      cleanupInstallation(state, "registration_failed")
      return false
    end
    state.effects[#state.effects + 1] = effect
  end

  for _, spec in ipairs(state.lightSpecs) do
    local light, lightError = createLight(spec)
    if not light then
      emitError(state, "light_creation_failed", {detail = lightError, name = spec.name})
      cleanupInstallation(state, "registration_failed")
      return false
    end
    state.lights[#state.lights + 1] = light
  end

  local synced, syncError = synchronizeTransforms(state)
  if not synced then
    emitError(state, "transform_sync_failed", {detail = syncError})
    cleanupInstallation(state, "registration_failed")
    return false
  end
  triggerOwners[state.washTrigger:getId()] = {propId = propId, kind = "wash"}
  triggerOwners[state.repairTrigger:getId()] = {propId = propId, kind = "repair"}
  triggerOwners[state.launchTrigger:getId()] = {propId = propId, kind = "launch"}
  forceWashSystemsOff(state)
  acknowledgeRegistration(vehicle)
  emitEvent(state, "I", "prop_registered", {
    visual_name = state.visualName,
    wash_trigger_name = state.washTriggerName,
    repair_trigger_name = state.repairTriggerName,
    launch_trigger_name = state.launchTriggerName,
    effect_count = #state.effects,
    light_count = #state.lights,
    ground_origin_z = state.origin.z,
  })
  return true
end

local function unregisterProp(propId, reason)
  local state = installations[propId]
  if not state then return false end
  cleanupInstallation(state, reason or "explicit_unregister")
  return true
end

local function onPreRender(dtReal, dtSim, dtRaw)
  local elapsed = finiteNumber(dtReal) and dtReal or 0
  local stale = {}
  for propId, state in pairs(installations) do
    state.transformElapsed = state.transformElapsed + elapsed
    if state.transformElapsed >= TRANSFORM_REFRESH_SECONDS then
      state.transformElapsed = 0
      local synced, syncError = synchronizeTransforms(state)
      if not synced then
        emitError(state, "transform_sync_failed", {detail = syncError})
        stale[#stale + 1] = propId
      end
    end
    for vehicleId, repair in pairs(state.repairOccupants) do
      if repair.phase == "precheck_pending"
        or repair.phase == "reset_pending"
        or repair.phase == "pose_restore_pending"
        or repair.phase == "verify_pending"
        or repair.phase == "release_pending" then
        repair.elapsed = (repair.elapsed or 0) + elapsed
        if repair.elapsed > REPAIR_ACK_TIMEOUT_SECONDS then
          failRepair(state, vehicleId, "repair_acknowledgement_timeout", {
            repair_phase = repair.phase,
            repair_token = repair.token,
          })
        end
      elseif repair.phase == "settling" and finiteNumber(dtSim) and dtSim > 0 then
        repair.settleFrames = (repair.settleFrames or 1) - 1
        if repair.settleFrames <= 0 then
          local vehicle = eligibleSubject(vehicleId)
          if not vehicle then
            failRepair(state, vehicleId, "repair_vehicle_missing")
          else
            repair.phase = "verify_pending"
            repair.elapsed = 0
            local queued, queueError = queueVehicleCommand(
              vehicle,
              repairIntegrityCommand(state.propId, repair.token, "after"),
              state,
              "repair_verification_command_failed",
              false
            )
            if not queued then
              failRepair(state, vehicleId, "repair_verification_command_failed", {
                detail = queueError,
              })
            end
          end
        end
      elseif repair.phase == "complete"
        and repair.resetEdgeGuard
        and finiteNumber(dtSim)
        and dtSim > 0 then
        repair.edgeGuardFrames = (repair.edgeGuardFrames or 1) - 1
        if repair.edgeGuardFrames <= 0 then
          local deferredWashExit = repair.washExitDeferred == true
          repair.resetEdgeGuard = false
          repair.washExitDeferred = false
          if deferredWashExit then
            removeWashSubject(state, vehicleId, "deferred_exit_after_repair")
          else
            processPendingLaunch(state, vehicleId)
          end
        end
      end
    end
    local run = state.activeRun
    if run then
      local vehicle = activeVehicle(state)
      if not vehicle then
        abortActiveRun(state, "active_vehicle_missing")
        state.armed = true
      elseif run.phase == "hold_pending" or run.phase == "release_pending" then
        run.ackElapsed = (run.ackElapsed or 0) + elapsed
        if run.ackElapsed > VEHICLE_ACK_TIMEOUT_SECONDS then
          local timeoutReason = run.phase == "hold_pending"
            and "hold_acknowledgement_timeout"
            or "release_acknowledgement_timeout"
          emitError(state, timeoutReason, {vehicle_id = run.vehicleId})
          abortActiveRun(state, timeoutReason, vehicle)
          state.armed = true
        end
      elseif run.phase == "release_grace" and finiteNumber(dtSim) and dtSim > 0 then
        run.releaseGraceFrames = (run.releaseGraceFrames or 1) - 1
        if run.releaseGraceFrames <= 0 then launchVehicle(state, vehicle) end
      end
    end
  end
  for _, propId in ipairs(stale) do
    local state = installations[propId]
    if state then cleanupInstallation(state, "prop_missing") end
  end
end

local function onVehicleResetted(vehicleId)
  for _, installation in pairs(installations) do
    local repair = installation.repairOccupants[vehicleId]
    if repair and repair.phase == "reset_pending" then
      local vehicle = eligibleSubject(vehicleId)
      if not vehicle or not repair.targetPosition or not repair.targetRotation then
        failRepair(installation, vehicleId, "repair_pose_restore_unavailable")
        return
      end
      repair.phase = "pose_restore_pending"
      repair.elapsed = 0
      local position = repair.targetPosition
      local rotation = repair.targetRotation
      local restored, restoreError = pcall(function()
        vehicle:setPositionRotation(
          position.x,
          position.y,
          position.z,
          rotation.x,
          rotation.y,
          rotation.z,
          rotation.w
        )
      end)
      if not restored then
        failRepair(installation, vehicleId, "repair_pose_restore_failed", {
          detail = tostring(restoreError),
        })
        return
      end
      emitEvent(installation, "I", "repair_reset_ack", {
        subject_id = vehicleId,
        repair_token = repair.token,
        pose_restore_requested = true,
        pose_policy = "center_oobb_on_trigger_axis_align_upright_preserve_travel_sign",
      })
      return
    end
    if repair and repair.phase == "pose_restore_pending" then
      repair.phase = "settling"
      repair.elapsed = 0
      repair.settleFrames = REPAIR_SETTLE_SIM_FRAMES
      emitEvent(installation, "I", "repair_pose_restore_ack", {
        subject_id = vehicleId,
        repair_token = repair.token,
      })
      return
    end
  end
  local state = installations[vehicleId]
  if state then
    local activeVehicleId = state.activeRun and state.activeRun.vehicleId or nil
    if activeVehicleId then
      finishActiveRunOnExit(state, activeVehicleId, "prop_reset", activeVehicle(state))
    end
    for subjectId, repair in pairs(state.repairOccupants) do
      bestEffortReleaseRepair(state, subjectId, repair, "prop_reset")
    end
    state.washSubjects = {}
    state.repairOccupants = {}
    state.pendingLaunchEntries = {}
    state.armed = true
    forceWashSystemsOff(state)
    local rebuilt, rebuildError = rebuildTriggersAfterReset(state)
    if not rebuilt then
      emitError(state, "reset_trigger_rebuild_failed", {detail = rebuildError})
      cleanupInstallation(state, "reset_trigger_rebuild_failed")
      if not registerProp(vehicleId) then
        emitError(nil, "reset_registration_recovery_failed", {prop_id = vehicleId})
      end
      return
    end
    -- Replacing all three trigger objects clears BeamNG's internal overlap cache.
    -- Vehicles already inside after a reset therefore receive fresh enter
    -- events instead of remaining in a silent, stale occupancy state.
    emitEvent(state, "I", "prop_reset", {
      reset_count = state.resetCount,
      wash_trigger_name = state.washTriggerName,
      repair_trigger_name = state.repairTriggerName,
      launch_trigger_name = state.launchTriggerName,
      wash_systems_active = state.washSystemsActive,
      armed = state.armed,
    })
    return
  end
  local affected = {}
  for _, installation in pairs(installations) do
    local activeVehicleId = installation.activeRun and installation.activeRun.vehicleId or nil
    if installation.washSubjects[vehicleId]
      or installation.repairOccupants[vehicleId]
      or installation.pendingLaunchEntries[vehicleId]
      or activeVehicleId == vehicleId then
      affected[#affected + 1] = installation
    end
  end
  for _, installation in ipairs(affected) do
    local repair = installation.repairOccupants[vehicleId]
    if repair and repair.phase ~= "complete" then
      repair.phase = "failed"
      bestEffortReleaseRepair(installation, vehicleId, repair, "unexpected_subject_reset")
    end
    removeWashSubject(installation, vehicleId, "unexpected_subject_reset")
    installation.armed = installation.activeRun == nil
    local rebuilt, rebuildError = rebuildTriggersAfterReset(installation)
    if not rebuilt then
      emitError(installation, "reset_trigger_rebuild_failed", {detail = rebuildError})
      local propId = installation.propId
      cleanupInstallation(installation, "reset_trigger_rebuild_failed")
      if not registerProp(propId) then
        emitError(nil, "reset_registration_recovery_failed", {prop_id = propId})
      end
    else
      emitEvent(installation, "I", "subject_reset", {
        subject_id = vehicleId,
        reset_count = installation.resetCount,
        wash_trigger_name = installation.washTriggerName,
        repair_trigger_name = installation.repairTriggerName,
        launch_trigger_name = installation.launchTriggerName,
        remaining_subject_count = washSubjectCount(installation),
        wash_systems_active = installation.washSystemsActive,
        armed = installation.armed,
      })
    end
  end
end

local function onVehicleDestroyed(vehicleId)
  local state = installations[vehicleId]
  if state then
    cleanupInstallation(state, "prop_destroyed")
    return
  end
  for _, installation in pairs(installations) do
    removeWashSubject(installation, vehicleId, "vehicle_destroyed")
  end
end

local function installationState(state)
  local activeEffects = 0
  local presentEffects = 0
  local emitterPresentCounts = {}
  local emitterActiveCounts = {}
  local pendingRepairs = 0
  local completedRepairs = 0
  local presentLights = 0
  for index, effect in ipairs(state.effects) do
    local spec = state.effectSpecs[index]
    if exactSceneObject(spec.name, EFFECT_CLASS) == effect
      and effect:getField("emitter", 0) == spec.emitter then
      presentEffects = presentEffects + 1
      emitterPresentCounts[spec.emitter] = (emitterPresentCounts[spec.emitter] or 0) + 1
      local active = string.lower(tostring(effect:getField("active", 0) or ""))
      if active == "1" or active == "true" then
        activeEffects = activeEffects + 1
        emitterActiveCounts[spec.emitter] = (emitterActiveCounts[spec.emitter] or 0) + 1
      end
    end
  end
  for index, light in ipairs(state.lights) do
    local spec = state.lightSpecs[index]
    if exactSceneObject(spec.name, spec.class) == light then presentLights = presentLights + 1 end
  end
  for _, repair in pairs(state.repairOccupants) do
    if repair.phase == "complete" then
      completedRepairs = completedRepairs + 1
    elseif repair.phase ~= "failed" then
      pendingRepairs = pendingRepairs + 1
    end
  end
  return {
    registered = true,
    prop_id = state.propId,
    arbitrary_vehicle_support = true,
    ground_origin = state.origin and {state.origin.x, state.origin.y, state.origin.z} or nil,
    visual_name = state.visualName,
    roller_play_ambient = state.visual and state.visual:getField("playAmbient", 0) or nil,
    wash_trigger = {
      name = state.washTriggerName,
      id = state.washTrigger and state.washTrigger:getId() or nil,
      mode = state.washTrigger and state.washTrigger:getField("triggerMode", 0) or nil,
      test_type = state.washTrigger and state.washTrigger:getField("triggerTestType", 0) or nil,
    },
    repair_trigger = {
      name = state.repairTriggerName,
      id = state.repairTrigger and state.repairTrigger:getId() or nil,
      mode = state.repairTrigger and state.repairTrigger:getField("triggerMode", 0) or nil,
      test_type = state.repairTrigger and state.repairTrigger:getField("triggerTestType", 0) or nil,
    },
    launch_trigger = {
      name = state.launchTriggerName,
      id = state.launchTrigger and state.launchTrigger:getId() or nil,
      mode = state.launchTrigger and state.launchTrigger:getField("triggerMode", 0) or nil,
      test_type = state.launchTrigger and state.launchTrigger:getField("triggerTestType", 0) or nil,
    },
    wash_active = state.washSystemsActive,
    wash_subject_count = washSubjectCount(state),
    effect_present_count = presentEffects,
    effect_active_count = activeEffects,
    effect_expected_count = #state.effects,
    light_present_count = presentLights,
    light_expected_count = #state.lights,
    emitter_present_counts = emitterPresentCounts,
    emitter_active_counts = emitterActiveCounts,
    repair_pending_count = pendingRepairs,
    repaired_subject_count = completedRepairs,
    armed = state.armed,
    active_vehicle_id = state.activeRun and state.activeRun.vehicleId or nil,
    active_phase = state.activeRun and state.activeRun.phase or nil,
    active_holding = state.activeRun and state.activeRun.holding or false,
    release_grace_frames = state.activeRun and state.activeRun.releaseGraceFrames or nil,
  }
end

local function getSystemState(propId)
  if integer(propId) then
    local state = installations[propId]
    return state and installationState(state) or {registered = false, prop_id = propId}
  end
  local states = {}
  for _, state in pairs(installations) do states[#states + 1] = installationState(state) end
  table.sort(states, function(first, second) return first.prop_id < second.prop_id end)
  return {installation_count = #states, installations = states}
end

local function onClientPreStartMission(levelPath)
  cleanupAll("mission_started")
  sessionCounter = sessionCounter + 1
  emitEvent(nil, "I", "mission_pre_start", {level_path = levelPath})
end

local function onClientStartMission(levelPath)
  emitEvent(nil, "I", "mission_started", {level_path = levelPath})
end

local function onClientEndMission(levelPath)
  cleanupAll("mission_ended")
  emitEvent(nil, "I", "mission_ended", {level_path = levelPath})
end

local function onExtensionLoaded()
  extensionUnloading = false
  unloadRequested = false
  sessionCounter = sessionCounter + 1
  emitEvent(nil, "I", "extension_loaded")
end

local function onExtensionUnloaded()
  extensionUnloading = true
  unloadRequested = false
  cleanupAll("extension_unloaded")
  emitEvent(nil, "I", "extension_unloaded")
end

M.registerProp = registerProp
M.unregisterProp = unregisterProp
M.getSystemState = getSystemState
M.onBeamNGTrigger = onBeamNGTrigger
M.onEricrolphCannonCarWashHoldAcknowledged = onEricrolphCannonCarWashHoldAcknowledged
M.onEricrolphCannonCarWashReleaseAcknowledged = onEricrolphCannonCarWashReleaseAcknowledged
M.onEricrolphCannonCarWashRepairIntegrityAcknowledged = (
  onEricrolphCannonCarWashRepairIntegrityAcknowledged
)
M.onEricrolphCannonCarWashRepairReleaseAcknowledged = (
  onEricrolphCannonCarWashRepairReleaseAcknowledged
)
M.onPreRender = onPreRender
M.onVehicleResetted = onVehicleResetted
M.onVehicleDestroyed = onVehicleDestroyed
M.onClientPreStartMission = onClientPreStartMission
M.onClientStartMission = onClientStartMission
M.onClientEndMission = onClientEndMission
M.onExtensionLoaded = onExtensionLoaded
M.onExtensionUnloaded = onExtensionUnloaded

return M
