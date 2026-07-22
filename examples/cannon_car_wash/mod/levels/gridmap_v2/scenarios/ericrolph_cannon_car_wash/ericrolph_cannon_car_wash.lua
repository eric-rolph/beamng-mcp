local M = {}

local LOG_TAG = "ERICROLPH_CANNON_CAR_WASH"
local LAUNCH_TRIGGER_NAME = "ericrolph_cannon_car_wash_launch_trigger"
local WASH_TRIGGER_NAME = "ericrolph_cannon_car_wash_wash_activation_trigger"
local REPAIR_TRIGGER_NAME = "ericrolph_cannon_car_wash_repair_trigger"
local TRIGGER_CLASS = "BeamNGTrigger"
local VISUAL_NAME = "ericrolph_cannon_car_wash_scenario_visual"
local VISUAL_CLASS = "TSStatic"
local EFFECT_CLASS = "ParticleEmitterNode"
local EFFECT_SPECS = {
  {name = "ericrolph_cannon_car_wash_mister_PreSoak_L_1", emitter = "BNGP_sprinkler"},
  {name = "ericrolph_cannon_car_wash_mister_PreSoak_L_2", emitter = "BNGP_sprinkler"},
  {name = "ericrolph_cannon_car_wash_mister_PreSoak_L_3", emitter = "BNGP_sprinkler"},
  {name = "ericrolph_cannon_car_wash_mister_PreSoak_R_1", emitter = "BNGP_sprinkler"},
  {name = "ericrolph_cannon_car_wash_mister_PreSoak_R_2", emitter = "BNGP_sprinkler"},
  {name = "ericrolph_cannon_car_wash_mister_PreSoak_R_3", emitter = "BNGP_sprinkler"},
  {name = "ericrolph_cannon_car_wash_dryer_Mist_L_1", emitter = "BNGP_waterfallsteam"},
  {name = "ericrolph_cannon_car_wash_dryer_Mist_L_2", emitter = "BNGP_waterfallsteam"},
  {name = "ericrolph_cannon_car_wash_dryer_Mist_L_3", emitter = "BNGP_waterfallsteam"},
  {name = "ericrolph_cannon_car_wash_dryer_Mist_R_1", emitter = "BNGP_waterfallsteam"},
  {name = "ericrolph_cannon_car_wash_dryer_Mist_R_2", emitter = "BNGP_waterfallsteam"},
  {name = "ericrolph_cannon_car_wash_dryer_Mist_R_3", emitter = "BNGP_waterfallsteam"},
  {name = "ericrolph_cannon_car_wash_dryer_Steam_L", emitter = "BNGP_34"},
  {name = "ericrolph_cannon_car_wash_dryer_Steam_R", emitter = "BNGP_34"},
  {name = "ericrolph_cannon_car_wash_dryer_Dust_L", emitter = "BNGP_2"},
  {name = "ericrolph_cannon_car_wash_dryer_Dust_R", emitter = "BNGP_2"},
}
local UI_CATEGORY = "ericrolph_cannon_car_wash_countdown"
local COUNTDOWN_INTERVAL_SECONDS = 1
local COUNTDOWN_MESSAGES = {"3...", "2...", "1..."}
local COUNTDOWN_EVENTS = {"countdown_3", "countdown_2", "countdown_1"}
local LAUNCH_SPEED_MPS = 100
local VEHICLE_ACK_TIMEOUT_SECONDS = 1
local REPAIR_ACK_TIMEOUT_SECONDS = 2
local REPAIR_SETTLE_SIM_FRAMES = 2
local REPAIR_MAX_CENTERLINE_ERROR_METERS = 0.15
local REPAIR_MIN_CORRIDOR_DOT = 0.999
local REPAIR_MIN_UPRIGHT_DOT = 0.999
local REPAIR_MAX_POSE_CORRECTION_ATTEMPTS = 2
local RELEASE_GRACE_SIM_FRAMES = 2

local function holdVehicleCommand(runNumber)
  return string.format([[
local existing = ericrolphCannonCarWashScenarioHoldState
local currentFrozen = controller and controller.isFrozen == true or false
local previousFrozen = currentFrozen
if existing then previousFrozen = existing.frozen == true end
local accepted = controller ~= nil
  and type(controller.setFreeze) == "function"
  and (not existing or existing.runNumber == %d)
if accepted then
  ericrolphCannonCarWashScenarioHoldState = existing or {
    runNumber = %d,
    frozen = previousFrozen
  }
  controller.setFreeze(1)
end
local actualFrozen = controller and controller.isFrozen == true or false
obj:queueGameEngineLua(string.format(
  "extensions.hook('onEricrolphCannonCarWashScenarioHoldAcknowledged', %%d, %%d, %%s, %%s, %%s)",
  obj:getId(), %d, tostring(accepted), tostring(previousFrozen), tostring(actualFrozen)
))
]], runNumber, runNumber, runNumber)
end

local function releaseVehicleCommand(runNumber)
  return string.format([[
local existing = ericrolphCannonCarWashScenarioHoldState
local matched = existing ~= nil and existing.runNumber == %d
local previousFrozen = controller and controller.isFrozen == true or false
if matched then previousFrozen = existing.frozen == true end
local restored = matched
  and controller ~= nil
  and type(controller.setFreeze) == "function"
if restored then
  controller.setFreeze(previousFrozen and 1 or 0)
  ericrolphCannonCarWashScenarioHoldState = nil
end
local actualFrozen = controller and controller.isFrozen == true or false
obj:queueGameEngineLua(string.format(
  "extensions.hook('onEricrolphCannonCarWashScenarioReleaseAcknowledged', %%d, %%d, %%s, %%s, %%s)",
  obj:getId(), %d, tostring(restored), tostring(previousFrozen), tostring(actualFrozen)
))
]], runNumber, runNumber)
end

local function repairIntegrityCommand(token, stage)
  return string.format([[
local repairStage = '%s'
local repairToken = %d
local existing = ericrolphCannonCarWashScenarioRepairHoldState
local currentFrozen = controller and controller.isFrozen == true or false
local previousFrozen = currentFrozen
if existing and existing.token == repairToken then
  previousFrozen = existing.frozen == true
end
local holdAccepted = controller ~= nil
  and type(controller.setFreeze) == "function"
  and ((repairStage == "before" and existing == nil)
    or (existing ~= nil and existing.token == repairToken))
if holdAccepted then
  if repairStage == "before" and existing == nil then
    existing = {token = repairToken, frozen = previousFrozen}
    ericrolphCannonCarWashScenarioRepairHoldState = existing
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
  "extensions.hook('onEricrolphCannonCarWashScenarioRepairIntegrityAcknowledged', %%d, %%d, '%s', %%.12f, %%d, %%d, %%d, %%s, %%s, %%s)",
  obj:getId(), %d, damage, partDamageCount, brokenBeamCount, deflatedTireCount,
  tostring(holdAccepted), tostring(previousFrozen), tostring(actualFrozen)
))
]], stage, token, stage, token)
end

local function repairReleaseCommand(token, expectedPreviousFrozen)
  return string.format([[
local repairToken = %d
local existing = ericrolphCannonCarWashScenarioRepairHoldState
local matched = existing ~= nil and existing.token == repairToken
local previousFrozen = %s
if matched then previousFrozen = existing.frozen == true end
local restored = controller ~= nil
  and type(controller.setFreeze) == "function"
  and (existing == nil or matched)
if restored then
  controller.setFreeze(previousFrozen and 1 or 0)
  ericrolphCannonCarWashScenarioRepairHoldState = nil
end
local actualFrozen = controller and controller.isFrozen == true or false
obj:queueGameEngineLua(string.format(
  "extensions.hook('onEricrolphCannonCarWashScenarioRepairReleaseAcknowledged', %%d, %%d, %%s, %%s, %%s)",
  obj:getId(), repairToken, tostring(restored), tostring(previousFrozen), tostring(actualFrozen)
))
]], token, tostring(expectedPreviousFrozen == true))
end

local activeRun = nil
local armed = true
local countdownIndex = 1
local runCounter = 0
local sessionCounter = 0
local washSubjects = {}
local washSystemsActive = false
local washInitialized = false
local pendingLaunchEntries = {}
local repairCounter = 0
local repairOccupants = {}

local function integer(value)
  return type(value) == "number" and value >= 1 and value % 1 == 0
end

local function nonnegativeInteger(value)
  return type(value) == "number" and value >= 0 and value % 1 == 0
end

local function finiteNumber(value)
  return type(value) == "number"
    and value == value
    and value > -math.huge
    and value < math.huge
end

local function emitEvent(level, event, fields)
  local record = {
    schema_version = 1,
    phase = 3,
    event = event,
    session = sessionCounter,
    run = activeRun and activeRun.number or runCounter,
    vehicle_id = activeRun and activeRun.vehicleId or 0,
    elapsed_time_seconds = activeRun and activeRun.elapsedTime or 0,
  }
  if type(fields) == "table" then
    for key, value in pairs(fields) do record[key] = value end
  end
  local encoded = jsonEncode(record)
  log(level, LOG_TAG, encoded)
end

local function emitError(reason, fields)
  local details = fields or {}
  details.reason = reason
  emitEvent("E", "error", details)
end

local function showMessage(message, ttl)
  local ok, messageError = pcall(function()
    guihooks.message({txt = message}, ttl, UI_CATEGORY)
  end)
  if not ok then emitError("gui_message_failed", {detail = tostring(messageError)}) end
end

local function exactTriggerFromEvent(data, expectedName, expectedMode)
  if type(data) ~= "table"
    or data.triggerName ~= expectedName
    or not integer(data.triggerID) then
    return nil
  end

  local triggerByName = scenetree.findObject(expectedName)
  local triggerById = scenetree.findObjectById(data.triggerID)
  if not triggerByName or not triggerById then return nil end
  if triggerByName:getId() ~= data.triggerID then return nil end
  if triggerById:getId() ~= data.triggerID then return nil end
  if triggerByName:getClassName() ~= TRIGGER_CLASS then return nil end
  if triggerById:getClassName() ~= TRIGGER_CLASS then return nil end
  if triggerByName:getField("triggerMode", 0) ~= expectedMode then return nil end
  if triggerById:getField("triggerMode", 0) ~= expectedMode then return nil end
  if triggerByName:getField("triggerTestType", 0) ~= "Bounding box" then return nil end
  if triggerById:getField("triggerTestType", 0) ~= "Bounding box" then return nil end
  return triggerById
end

local function exactVehicleFromEvent(data)
  if type(data) ~= "table" or not integer(data.subjectID) then return nil end
  local vehicle = be:getObjectByID(data.subjectID)
  if not vehicle then return nil end
  if vehicle:getId() ~= data.subjectID then return nil end
  return vehicle
end

local function activeVehicle()
  if not activeRun then return nil end
  local vehicle = be:getObjectByID(activeRun.vehicleId)
  if not vehicle or vehicle:getId() ~= activeRun.vehicleId then return nil end
  return vehicle
end

local function queueVehicleCommand(vehicle, command, failureReason, reportFailure)
  local ok, commandError = pcall(function() vehicle:queueLuaCommand(command) end)
  if not ok then
    local detail = tostring(commandError)
    if reportFailure ~= false then emitError(failureReason, {detail = detail}) end
    return false, detail
  end
  return true
end

local function releaseVehicle(vehicle, reason)
  if not activeRun then return end
  if not activeRun.holding
    and not activeRun.holdCommandPending
    and not activeRun.releasePending then
    return
  end
  if vehicle then
    queueVehicleCommand(
      vehicle,
      releaseVehicleCommand(activeRun.number),
      "release_command_failed"
    )
  end
  activeRun.holding = false
  activeRun.holdCommandPending = false
  activeRun.releasePending = false
  emitEvent("I", "release", {reason = reason})
end

local function washSubjectCount()
  local count = 0
  for _ in pairs(washSubjects) do count = count + 1 end
  return count
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

local function resolveWashObjects()
  local visual = exactSceneObject(VISUAL_NAME, VISUAL_CLASS)
  local effects = {}
  local missing = {}
  if not visual then missing[#missing + 1] = VISUAL_NAME end
  for _, spec in ipairs(EFFECT_SPECS) do
    local effect = exactSceneObject(spec.name, EFFECT_CLASS)
    if effect and effect:getField("emitter", 0) == spec.emitter then
      effects[#effects + 1] = effect
    else
      missing[#missing + 1] = spec.name
    end
  end
  return visual, effects, missing
end

local function setVisualAmbient(visual, enabled)
  if not visual then return end
  if type(visual.preApply) == "function" then visual:preApply() end
  visual:setField("playAmbient", 0, enabled and "1" or "0")
  if type(visual.postApply) == "function" then visual:postApply() end
end

local function forceWashSystemsOff(visual, effects)
  if visual then pcall(function() setVisualAmbient(visual, false) end) end
  for _, effect in ipairs(effects or {}) do
    pcall(function() effect:setActive(false) end)
  end
  washSystemsActive = false
  washInitialized = false
end

local function setWashSystemsEnabled(enabled, reason, strict)
  local visual, effects, missing = resolveWashObjects()
  if not visual or #missing > 0 then
    forceWashSystemsOff(visual, effects)
    if strict then
      emitError("wash_objects_missing", {missing_objects = table.concat(missing, ",")})
    end
    return false
  end

  local updated, updateError = pcall(function()
    setVisualAmbient(visual, enabled)
    for _, effect in ipairs(effects) do
      effect:setActive(enabled)
    end
  end)
  if not updated then
    forceWashSystemsOff(visual, effects)
    if strict then
      emitError("wash_system_update_failed", {detail = tostring(updateError)})
    end
    return false
  end

  washSystemsActive = enabled
  washInitialized = true
  emitEvent("I", enabled and "wash_systems_start" or "wash_systems_stop", {
    reason = reason,
    roller_sequence = "ambient",
    effect_count = #EFFECT_SPECS,
    emitter_counts = {
      BNGP_sprinkler = 6,
      BNGP_waterfallsteam = 6,
      BNGP_34 = 2,
      BNGP_2 = 2,
    },
  })
  return true
end

local function releaseRepairHold(vehicleId, repair, reason)
  if not repair or not repair.holding then return true end
  local vehicle = be:getObjectByID(vehicleId)
  repair.holding = false
  if not vehicle or vehicle:getId() ~= vehicleId then return false end
  local queued = queueVehicleCommand(
    vehicle,
    repairReleaseCommand(repair.token, repair.previousFrozen),
    "repair_release_command_failed"
  )
  emitEvent("I", "repair_release_requested", {
    subject_id = vehicleId,
    repair_token = repair.token,
    reason = reason,
  })
  return queued
end

local function resetWashState(reason, strict)
  for vehicleId, repair in pairs(repairOccupants) do
    releaseRepairHold(vehicleId, repair, reason)
  end
  washSubjects = {}
  repairOccupants = {}
  washInitialized = false
  return setWashSystemsEnabled(false, reason, strict)
end

local function removeWashSubject(vehicleId, reason)
  pendingLaunchEntries[vehicleId] = nil
  releaseRepairHold(vehicleId, repairOccupants[vehicleId], reason)
  repairOccupants[vehicleId] = nil
  if not washSubjects[vehicleId] then return end
  washSubjects[vehicleId] = nil
  emitEvent("I", "wash_subject_removed", {
    subject_id = vehicleId,
    reason = reason,
  })
  if washSubjectCount() == 0 and washSystemsActive then
    setWashSystemsEnabled(false, reason, true)
  end
end

local function washSystemState()
  local visual = exactSceneObject(VISUAL_NAME, VISUAL_CLASS)
  local repairTrigger = exactSceneObject(REPAIR_TRIGGER_NAME, TRIGGER_CLASS)
  local activeEffects = 0
  local presentEffects = 0
  local pendingRepairs = 0
  local completedRepairs = 0
  local emitterPresentCounts = {}
  local emitterActiveCounts = {}
  for _, spec in ipairs(EFFECT_SPECS) do
    local effect = exactSceneObject(spec.name, EFFECT_CLASS)
    if effect and effect:getField("emitter", 0) == spec.emitter then
      presentEffects = presentEffects + 1
      emitterPresentCounts[spec.emitter] = (emitterPresentCounts[spec.emitter] or 0) + 1
      local activeField = string.lower(tostring(effect:getField("active", 0) or ""))
      if activeField == "1" or activeField == "true" then
        activeEffects = activeEffects + 1
        emitterActiveCounts[spec.emitter] = (emitterActiveCounts[spec.emitter] or 0) + 1
      end
    end
  end
  for _, repair in pairs(repairOccupants) do
    if repair.phase == "complete" then
      completedRepairs = completedRepairs + 1
    elseif repair.phase ~= "failed" then
      pendingRepairs = pendingRepairs + 1
    end
  end
  return {
    active = washSystemsActive,
    subject_count = washSubjectCount(),
    roller_play_ambient = visual and visual:getField("playAmbient", 0) or nil,
    effect_active_count = activeEffects,
    effect_present_count = presentEffects,
    effect_expected_count = #EFFECT_SPECS,
    emitter_present_counts = emitterPresentCounts,
    emitter_active_counts = emitterActiveCounts,
    repair_trigger = {
      name = REPAIR_TRIGGER_NAME,
      id = repairTrigger and repairTrigger:getId() or nil,
      mode = repairTrigger and repairTrigger:getField("triggerMode", 0) or nil,
      test_type = repairTrigger and repairTrigger:getField("triggerTestType", 0) or nil,
    },
    repair_pending_count = pendingRepairs,
    repaired_subject_count = completedRepairs,
  }
end

local function resetState()
  activeRun = nil
  armed = true
  countdownIndex = 1
  pendingLaunchEntries = {}
end

local function abortActiveRun(reason, vehicle)
  if activeRun then
    if activeRun.phase == "launched" and not activeRun.holding then
      emitEvent("I", "launch_complete", {exit_reason = reason})
      resetState()
      return
    end
    local active = vehicle or activeVehicle()
    releaseVehicle(active, reason)
    emitEvent("I", "abort", {reason = reason})
  end
  resetState()
end

local function launchVehicle(vehicle)
  if not activeRun or activeRun.phase ~= "release_grace" or activeRun.holding then return end
  local direction = vehicle:getDirectionVector()
  if not direction
    or not finiteNumber(direction.x)
    or not finiteNumber(direction.y)
    or not finiteNumber(direction.z)
    or direction:length() < 0.000001 then
    emitError("invalid_forward_axis")
    abortActiveRun("invalid_forward_axis", vehicle)
    return
  end

  direction:normalize()
  local velocity = direction * LAUNCH_SPEED_MPS

  showMessage("GO!", 1.5)
  emitEvent("I", "go", {
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
    emitError("velocity_injection_failed", {detail = tostring(launchError)})
    abortActiveRun("velocity_injection_failed", vehicle)
    return
  end

  activeRun.phase = "launched"
  emitEvent("I", "launch", {
    target_speed_mps = LAUNCH_SPEED_MPS,
    velocity_x = velocity.x,
    velocity_y = velocity.y,
    velocity_z = velocity.z,
  })
end

local function requestReleaseForLaunch(vehicle)
  if not activeRun or activeRun.phase ~= "countdown" or not activeRun.holding then return false end
  activeRun.phase = "release_pending"
  activeRun.releasePending = true
  activeRun.ackElapsed = 0
  local queued = queueVehicleCommand(
    vehicle,
    releaseVehicleCommand(activeRun.number),
    "release_command_failed"
  )
  if not queued then
    abortActiveRun("release_command_failed", vehicle)
    return false
  end
  emitEvent("I", "release_requested", {reason = "launch"})
  return true
end

local countdownJob

countdownJob = function(job, runNumber)
  local timer = hptimer()
  for nextIndex = 2, #COUNTDOWN_MESSAGES do
    job.sleep(COUNTDOWN_INTERVAL_SECONDS)
    if not activeRun
      or not activeRun.holding
      or activeRun.phase ~= "countdown"
      or activeRun.number ~= runNumber then
      return
    end
    local vehicle = activeVehicle()
    if not vehicle then
      emitError("active_vehicle_missing")
      abortActiveRun("active_vehicle_missing")
      return
    end

    activeRun.elapsedTime = timer:stop() / 1000
    countdownIndex = nextIndex
    showMessage(COUNTDOWN_MESSAGES[countdownIndex], 1.1)
    local countdownValue = #COUNTDOWN_MESSAGES - countdownIndex + 1
    emitEvent("I", COUNTDOWN_EVENTS[countdownIndex], {
      countdown_value = countdownValue,
    })
  end

  job.sleep(COUNTDOWN_INTERVAL_SECONDS)
  if not activeRun
    or not activeRun.holding
    or activeRun.phase ~= "countdown"
    or activeRun.number ~= runNumber then
    return
  end
  local vehicle = activeVehicle()
  if not vehicle then
    emitError("active_vehicle_missing")
    abortActiveRun("active_vehicle_missing")
    return
  end
  activeRun.elapsedTime = timer:stop() / 1000
  requestReleaseForLaunch(vehicle)
end

local function onEricrolphCannonCarWashScenarioHoldAcknowledged(
  vehicleId,
  runNumber,
  accepted,
  previousFrozen,
  actualFrozen
)
  if not integer(vehicleId)
    or not integer(runNumber)
    or type(accepted) ~= "boolean"
    or type(previousFrozen) ~= "boolean"
    or type(actualFrozen) ~= "boolean" then
    return
  end
  if not activeRun
    or activeRun.vehicleId ~= vehicleId
    or activeRun.number ~= runNumber
    or activeRun.phase ~= "hold_pending" then
    return
  end
  activeRun.holdCommandPending = false
  activeRun.previousFrozen = previousFrozen
  -- An accepted hold owns a Vehicle Lua state record even when the reported
  -- freeze state is invalid. Mark that ownership before validation so every
  -- failure path queues a matching release and clears the record.
  activeRun.holding = accepted
  if not accepted or not actualFrozen then
    emitError("hold_acknowledgement_failed", {
      accepted = accepted,
      actual_frozen = actualFrozen,
    })
    abortActiveRun("hold_acknowledgement_failed", activeVehicle())
    return
  end
  if previousFrozen then
    emitError("vehicle_already_frozen")
    abortActiveRun("vehicle_already_frozen", activeVehicle())
    return
  end

  local vehicle = activeVehicle()
  if not vehicle then
    emitError("active_vehicle_missing")
    abortActiveRun("active_vehicle_missing")
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
    emitError("hold_velocity_stop_failed", {detail = tostring(stopError)})
    abortActiveRun("hold_velocity_stop_failed", vehicle)
    return
  end

  activeRun.phase = "countdown"
  activeRun.ackElapsed = 0
  countdownIndex = 1
  emitEvent("I", "hold_ack", {
    previous_frozen = previousFrozen,
    actual_frozen = actualFrozen,
  })
  emitEvent("I", "hold_start")
  showMessage(COUNTDOWN_MESSAGES[countdownIndex], 1.1)
  emitEvent("I", COUNTDOWN_EVENTS[countdownIndex], {countdown_value = 3})
  local timerCreated, timerOrError = pcall(function()
    return extensions.core_jobsystem.create(countdownJob, nil, activeRun.number)
  end)
  if not timerCreated or not timerOrError then
    emitError("countdown_job_start_failed", {detail = tostring(timerOrError)})
    abortActiveRun("countdown_job_start_failed", activeVehicle())
    return
  end
  activeRun.countdownJob = timerOrError
  emitEvent("I", "countdown_timer_start", {clock = "jobsystem_hptimer"})
end

local function onEricrolphCannonCarWashScenarioReleaseAcknowledged(
  vehicleId,
  runNumber,
  restored,
  previousFrozen,
  actualFrozen
)
  if not integer(vehicleId)
    or not integer(runNumber)
    or type(restored) ~= "boolean"
    or type(previousFrozen) ~= "boolean"
    or type(actualFrozen) ~= "boolean" then
    return
  end
  if not activeRun
    or activeRun.vehicleId ~= vehicleId
    or activeRun.number ~= runNumber
    or activeRun.phase ~= "release_pending" then
    return
  end
  if not restored
    or previousFrozen ~= activeRun.previousFrozen
    or actualFrozen ~= previousFrozen then
    emitError("release_acknowledgement_failed", {
      restored = restored,
      previous_frozen = previousFrozen,
      actual_frozen = actualFrozen,
    })
    abortActiveRun("release_acknowledgement_failed", activeVehicle())
    return
  end

  activeRun.holding = false
  activeRun.releasePending = false
  activeRun.phase = "release_grace"
  activeRun.releaseGraceFrames = RELEASE_GRACE_SIM_FRAMES
  activeRun.ackElapsed = 0
  emitEvent("I", "release_ack", {
    reason = "launch",
    previous_frozen = previousFrozen,
    actual_frozen = actualFrozen,
  })
  emitEvent("I", "release", {reason = "launch"})
end

local handleLaunchTrigger

local function processPendingLaunch(subjectId)
  local pending = pendingLaunchEntries[subjectId]
  if not pending or not washSubjects[subjectId] or not washSystemsActive then return end
  local repair = repairOccupants[subjectId]
  if not repair or repair.phase ~= "complete"
    or repair.resetEdgeGuard
    or repair.washExitDeferred then return end
  pendingLaunchEntries[subjectId] = nil
  handleLaunchTrigger(pending)
end

local function failRepair(vehicleId, reason, fields)
  local repair = repairOccupants[vehicleId]
  local deferredWashExit = repair and repair.washExitDeferred == true
  if repair then
    releaseRepairHold(vehicleId, repair, reason)
    repair.phase = "failed"
    repair.elapsed = 0
    repair.resetEdgeGuard = false
  end
  local payload = fields or {}
  payload.subject_id = vehicleId
  emitError(reason, payload)
  if deferredWashExit then
    removeWashSubject(vehicleId, "deferred_exit_after_repair_failure")
  end
end

local function onEricrolphCannonCarWashScenarioRepairIntegrityAcknowledged(
  vehicleId,
  token,
  stage,
  damage,
  partDamageCount,
  brokenBeamCount,
  deflatedTireCount,
  holdAccepted,
  previousFrozen,
  actualFrozen
)
  if not integer(vehicleId)
    or not integer(token)
    or (stage ~= "before" and stage ~= "after")
    or not finiteNumber(damage)
    or not nonnegativeInteger(partDamageCount)
    or not nonnegativeInteger(brokenBeamCount)
    or not nonnegativeInteger(deflatedTireCount)
    or type(holdAccepted) ~= "boolean"
    or type(previousFrozen) ~= "boolean"
    or type(actualFrozen) ~= "boolean" then
    return
  end
  local repair = repairOccupants[vehicleId]
  if not repair or repair.token ~= token then
    if stage == "before" and holdAccepted and actualFrozen then
      local staleVehicle = be:getObjectByID(vehicleId)
      if staleVehicle and staleVehicle:getId() == vehicleId then
        queueVehicleCommand(
          staleVehicle,
          repairReleaseCommand(token, previousFrozen),
          "orphaned_repair_release_command_failed"
        )
      end
    end
    return
  end

  if stage == "before" then
    if repair.phase ~= "precheck_pending" then return end
    repair.previousFrozen = previousFrozen
    repair.holding = actualFrozen == true
    if not holdAccepted or not actualFrozen then
      failRepair(vehicleId, "repair_hold_failed", {
        hold_accepted = holdAccepted,
        actual_frozen = actualFrozen,
      })
      return
    end
    repair.before = {
      damage = damage,
      partDamageCount = partDamageCount,
      brokenBeamCount = brokenBeamCount,
      deflatedTireCount = deflatedTireCount,
    }
    emitEvent("I", "repair_snapshot", {
      subject_id = vehicleId,
      repair_token = token,
      damage_before = damage,
      part_damage_before = partDamageCount,
      broken_beams_before = brokenBeamCount,
      deflated_tires_before = deflatedTireCount,
    })
    local vehicle = be:getObjectByID(vehicleId)
    if not vehicle or vehicle:getId() ~= vehicleId then
      failRepair(vehicleId, "repair_vehicle_missing")
      return
    end
    local repairTrigger = exactSceneObject(REPAIR_TRIGGER_NAME, TRIGGER_CLASS)
    local target, targetError = repairTargetPose(vehicle, repairTrigger)
    if not target then
      failRepair(vehicleId, "repair_target_pose_failed", {detail = targetError})
      return
    end
    for key, value in pairs(target) do repair[key] = value end
    repair.phase = "reset_pending"
    repair.elapsed = 0
    repair.resetEdgeGuard = true
    repair.washExitDeferred = false
    emitEvent("I", "repair_requested", {
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
      failRepair(vehicleId, "repair_reset_failed", {detail = tostring(resetError)})
      return
    end
    return
  end

  if repair.phase ~= "verify_pending" then return end
  repair.holding = actualFrozen == true
  if not holdAccepted
    or not actualFrozen
    or previousFrozen ~= repair.previousFrozen then
    failRepair(vehicleId, "repair_hold_lost", {
      hold_accepted = holdAccepted,
      previous_frozen = previousFrozen,
      actual_frozen = actualFrozen,
    })
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
    failRepair(vehicleId, "repair_verification_failed", {
      damage_after = damage,
      part_damage_after = partDamageCount,
      broken_beams_after = brokenBeamCount,
      deflated_tires_after = deflatedTireCount,
    })
    return
  end

  local vehicle = be:getObjectByID(vehicleId)
  local poseMetrics = repairedPoseMetrics(vehicle, repair)
  if not poseMetrics then
    failRepair(vehicleId, "repair_pose_verification_unavailable")
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
      local correctionTarget, correctionTargetError = repairTargetPose(vehicle, repairTrigger)
      if not correctionTarget then
        failRepair(vehicleId, "repair_pose_correction_target_failed", {
          detail = correctionTargetError,
        })
        return
      end
      if correctionTarget.targetDirection:dot(repair.targetDirection) <= 0 then
        failRepair(vehicleId, "repair_pose_correction_travel_sign_changed")
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
        failRepair(vehicleId, "repair_pose_correction_failed", {
          detail = tostring(correctionError),
          correction_attempt = repair.poseCorrectionAttempts,
        })
        return
      end
      emitEvent("I", "repair_pose_correction_requested", {
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
    failRepair(vehicleId, "repair_pose_verification_failed", {
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
  local queued, queueError = queueVehicleCommand(
    vehicle,
    repairReleaseCommand(token, repair.previousFrozen),
    "repair_release_command_failed",
    false
  )
  if not queued then
    failRepair(vehicleId, "repair_release_command_failed", {detail = queueError})
    return
  end
  emitEvent("I", "repair_release_requested", {
    subject_id = vehicleId,
    repair_token = token,
    reason = "repair_complete",
  })
end

local function onEricrolphCannonCarWashScenarioRepairReleaseAcknowledged(
  vehicleId,
  token,
  restored,
  previousFrozen,
  actualFrozen
)
  if not integer(vehicleId)
    or not integer(token)
    or type(restored) ~= "boolean"
    or type(previousFrozen) ~= "boolean"
    or type(actualFrozen) ~= "boolean" then
    return
  end
  local repair = repairOccupants[vehicleId]
  if not repair or repair.token ~= token or repair.phase ~= "release_pending" then return end
  if not restored
    or previousFrozen ~= repair.previousFrozen
    or actualFrozen ~= repair.previousFrozen then
    failRepair(vehicleId, "repair_release_failed", {
      restored = restored,
      previous_frozen = previousFrozen,
      actual_frozen = actualFrozen,
    })
    return
  end

  repair.holding = false
  repair.phase = "complete"
  repair.elapsed = 0
  repair.edgeGuardFrames = REPAIR_SETTLE_SIM_FRAMES
  showMessage("Vehicle restored!", 1.5)
  emitEvent("I", "repair_release_ack", {
    subject_id = vehicleId,
    repair_token = token,
    previous_frozen = previousFrozen,
    actual_frozen = actualFrozen,
  })
  emitEvent("I", "repair_complete", {
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
  processPendingLaunch(vehicleId)
end

local function handleRepairTrigger(data)
  if type(data) ~= "table"
    or data.triggerName ~= REPAIR_TRIGGER_NAME
    or not integer(data.triggerID)
    or not integer(data.subjectID) then
    return
  end
  if not exactTriggerFromEvent(data, REPAIR_TRIGGER_NAME, "Overlaps") then return end
  local vehicle = exactVehicleFromEvent(data)
  if not vehicle then return end

  if data.event == "exit" then
    local repair = repairOccupants[data.subjectID]
    if repair then repair.exitObserved = true end
    emitEvent("I", "repair_trigger_exit", {subject_id = data.subjectID})
    return
  end
  if data.event ~= "enter" or repairOccupants[data.subjectID] then return end

  repairCounter = repairCounter + 1
  repairOccupants[data.subjectID] = {
    token = repairCounter,
    phase = "precheck_pending",
    elapsed = 0,
    exitObserved = false,
    holding = false,
  }
  emitEvent("I", "repair_trigger_enter", {
    subject_id = data.subjectID,
    repair_token = repairCounter,
  })
  if not queueVehicleCommand(
    vehicle,
    repairIntegrityCommand(repairCounter, "before"),
    "repair_precheck_command_failed"
  ) then
    repairOccupants[data.subjectID].phase = "failed"
  end
end

local function handleWashTrigger(data)
  if type(data) ~= "table"
    or data.triggerName ~= WASH_TRIGGER_NAME
    or not integer(data.triggerID)
    or not integer(data.subjectID) then
    return
  end
  if not exactTriggerFromEvent(data, WASH_TRIGGER_NAME, "Overlaps") then return end
  local vehicle = exactVehicleFromEvent(data)
  if not vehicle then return end

  if data.event == "enter" then
    local wasPresent = washSubjects[data.subjectID] == true
    washSubjects[data.subjectID] = true
    local repair = repairOccupants[data.subjectID]
    if repair and repair.resetEdgeGuard then repair.washExitDeferred = false end
    emitEvent("I", "wash_trigger_enter", {subject_id = data.subjectID})
    if not wasPresent and not washSystemsActive then
      setWashSystemsEnabled(true, "vehicle_enter", true)
    end
    processPendingLaunch(data.subjectID)
    return
  end
  if data.event ~= "exit" then return end

  local repair = repairOccupants[data.subjectID]
  if repair and repair.resetEdgeGuard then
    repair.washExitDeferred = true
    emitEvent("I", "wash_trigger_exit_suppressed", {
      subject_id = data.subjectID,
      reason = "intentional_repair_reset",
      repair_token = repair.token,
    })
    return
  end

  emitEvent("I", "wash_trigger_exit", {subject_id = data.subjectID})
  removeWashSubject(data.subjectID, "last_vehicle_exit")
end

handleLaunchTrigger = function(data)
  if type(data) ~= "table"
    or data.triggerName ~= LAUNCH_TRIGGER_NAME
    or not integer(data.triggerID)
    or not integer(data.subjectID) then
    return
  end
  local trigger = exactTriggerFromEvent(data, LAUNCH_TRIGGER_NAME, "Contains")
  if not trigger then return end
  local vehicle = exactVehicleFromEvent(data)
  if not vehicle then return end

  if data.event == "exit" then
    pendingLaunchEntries[data.subjectID] = nil
    if activeRun
      and activeRun.vehicleId == data.subjectID
      and activeRun.phase ~= "launched"
      and washSubjects[data.subjectID]
      and washSystemsActive then
      emitEvent("I", "containment_exit_suppressed", {
        reason = "verified_subject_still_in_wash",
        active_phase = activeRun.phase,
      })
      return
    end
    if activeRun and activeRun.vehicleId == data.subjectID then
      if activeRun.phase == "launched" then
        emitEvent("I", "trigger_exit")
        emitEvent("I", "launch_complete", {exit_reason = "launch_trigger_exit"})
        resetState()
      else
        abortActiveRun("trigger_exit_before_launch", vehicle)
      end
    else
      armed = true
    end
    return
  end
  if data.event ~= "enter" then return end
  if not armed or activeRun then return end
  if not washSubjects[data.subjectID] or not washSystemsActive then
    pendingLaunchEntries[data.subjectID] = {
      triggerName = data.triggerName,
      triggerID = data.triggerID,
      subjectID = data.subjectID,
      event = "enter",
    }
    emitEvent("I", "launch_deferred", {reason = "wash_not_active"})
    return
  end
  local repair = repairOccupants[data.subjectID]
  if not repair or repair.phase ~= "complete"
    or repair.resetEdgeGuard
    or repair.washExitDeferred then
    pendingLaunchEntries[data.subjectID] = {
      triggerName = data.triggerName,
      triggerID = data.triggerID,
      subjectID = data.subjectID,
      event = "enter",
    }
    emitEvent("I", "launch_deferred", {
      reason = repair and "repair_pending" or "repair_not_started",
    })
    return
  end

  pendingLaunchEntries[data.subjectID] = nil
  armed = false
  runCounter = runCounter + 1
  countdownIndex = 1
  activeRun = {
    number = runCounter,
    vehicleId = data.subjectID,
    triggerId = data.triggerID,
    phase = "hold_pending",
    holding = false,
    holdCommandPending = true,
    releasePending = false,
    elapsedTime = 0,
    ackElapsed = 0,
  }

  emitEvent("I", "containment_verified", {
    trigger_mode = trigger:getField("triggerMode", 0),
    trigger_test_type = trigger:getField("triggerTestType", 0),
  })
  emitEvent("I", "trigger_enter")
  local held = queueVehicleCommand(
    vehicle,
    holdVehicleCommand(activeRun.number),
    "hold_command_failed"
  )
  if not held then
    abortActiveRun("hold_command_failed", vehicle)
    return
  end
  emitEvent("I", "hold_requested", {run_number = activeRun.number})
end

local function onBeamNGTrigger(data)
  if type(data) ~= "table" then return end
  if data.triggerName == WASH_TRIGGER_NAME then
    handleWashTrigger(data)
  elseif data.triggerName == REPAIR_TRIGGER_NAME then
    handleRepairTrigger(data)
  elseif data.triggerName == LAUNCH_TRIGGER_NAME then
    handleLaunchTrigger(data)
  end
end

local function onPreRender(dtReal,dtSim,dtRaw)
  -- The extension can load before its prefab.  Retry silently until the
  -- animated visual and every particle node exist, preserving the desired
  -- state if a vehicle reached the bay during prefab initialization.
  if not washInitialized then
    setWashSystemsEnabled(washSubjectCount() > 0, "scene_initialized", false)
    if washSystemsActive then
      local pendingSubjects = {}
      for subjectId in pairs(pendingLaunchEntries) do
        pendingSubjects[#pendingSubjects + 1] = subjectId
      end
      for _, subjectId in ipairs(pendingSubjects) do processPendingLaunch(subjectId) end
    end
  end

  local repairElapsed = finiteNumber(dtReal) and dtReal or 0
  for vehicleId, repair in pairs(repairOccupants) do
    if repair.phase == "precheck_pending"
      or repair.phase == "reset_pending"
      or repair.phase == "pose_restore_pending"
      or repair.phase == "verify_pending"
      or repair.phase == "release_pending" then
      repair.elapsed = (repair.elapsed or 0) + repairElapsed
      if repair.elapsed > REPAIR_ACK_TIMEOUT_SECONDS then
        failRepair(vehicleId, "repair_acknowledgement_timeout", {
          repair_phase = repair.phase,
          repair_token = repair.token,
        })
      end
    elseif repair.phase == "settling" and finiteNumber(dtSim) and dtSim > 0 then
      repair.settleFrames = (repair.settleFrames or 1) - 1
      if repair.settleFrames <= 0 then
        local vehicle = be:getObjectByID(vehicleId)
        if not vehicle or vehicle:getId() ~= vehicleId then
          failRepair(vehicleId, "repair_vehicle_missing")
        else
          repair.phase = "verify_pending"
          repair.elapsed = 0
          local queued, queueError = queueVehicleCommand(
            vehicle,
            repairIntegrityCommand(repair.token, "after"),
            "repair_verification_command_failed",
            false
          )
          if not queued then
            failRepair(vehicleId, "repair_verification_command_failed", {
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
          removeWashSubject(vehicleId, "deferred_exit_after_repair")
        else
          processPendingLaunch(vehicleId)
        end
      end
    end
  end

  if not activeRun then return end

  local vehicle = activeVehicle()
  if not vehicle then
    emitError("active_vehicle_missing")
    abortActiveRun("active_vehicle_missing")
    return
  end

  if activeRun.phase == "hold_pending" or activeRun.phase == "release_pending" then
    local elapsed = finiteNumber(dtReal) and dtReal or 0
    activeRun.ackElapsed = (activeRun.ackElapsed or 0) + elapsed
    if activeRun.ackElapsed > VEHICLE_ACK_TIMEOUT_SECONDS then
      local timeoutReason = activeRun.phase == "hold_pending"
        and "hold_acknowledgement_timeout"
        or "release_acknowledgement_timeout"
      emitError(timeoutReason)
      abortActiveRun(timeoutReason, vehicle)
    end
  elseif activeRun.phase == "release_grace" and finiteNumber(dtSim) and dtSim > 0 then
    activeRun.releaseGraceFrames = (activeRun.releaseGraceFrames or 1) - 1
    if activeRun.releaseGraceFrames <= 0 then launchVehicle(vehicle) end
  end
end

local function onClientStartMission(levelPath)
  abortActiveRun("mission_started")
  resetState()
  sessionCounter = sessionCounter + 1
  resetWashState("mission_started", false)
  emitEvent("I", "session_start", {level_path = tostring(levelPath or "")})
end

local function onClientEndMission(levelPath)
  abortActiveRun("mission_ended")
  resetState()
  resetWashState("mission_ended", false)
  washInitialized = false
  emitEvent("I", "session_end", {level_path = tostring(levelPath or "")})
end

local function onVehicleResetted(vehicleId)
  local repair = repairOccupants[vehicleId]
  if repair and repair.phase == "pose_restore_pending" then
    repair.phase = "settling"
    repair.elapsed = 0
    repair.settleFrames = REPAIR_SETTLE_SIM_FRAMES
    emitEvent("I", "repair_pose_restore_ack", {
      subject_id = vehicleId,
      repair_token = repair.token,
    })
    return
  end
  if repair and repair.phase == "reset_pending" then
    local vehicle = be:getObjectByID(vehicleId)
    if not vehicle
      or vehicle:getId() ~= vehicleId
      or not repair.targetPosition
      or not repair.targetRotation then
      failRepair(vehicleId, "repair_pose_restore_unavailable")
      return
    end
    local position = repair.targetPosition
    local rotation = repair.targetRotation
    repair.phase = "pose_restore_pending"
    repair.elapsed = 0
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
      failRepair(vehicleId, "repair_pose_restore_failed", {detail = tostring(restoreError)})
      return
    end
    emitEvent("I", "repair_reset_ack", {
      subject_id = vehicleId,
      repair_token = repair.token,
      pose_restore_requested = true,
      pose_policy = "center_oobb_on_trigger_axis_align_upright_preserve_travel_sign",
    })
    return
  end
  removeWashSubject(vehicleId, "vehicle_reset")
  if activeRun and activeRun.vehicleId == vehicleId then
    abortActiveRun("vehicle_reset")
    resetState()
  end
end

local function onVehicleDestroyed(vehicleId)
  repairOccupants[vehicleId] = nil
  removeWashSubject(vehicleId, "vehicle_destroyed")
  if activeRun and activeRun.vehicleId == vehicleId then
    emitEvent("I", "abort", {reason = "vehicle_destroyed"})
    resetState()
  end
end

local function onExtensionLoaded()
  abortActiveRun("extension_loaded")
  resetState()
  resetWashState("extension_loaded", false)
  emitEvent("I", "extension_loaded")
end

local function onExtensionUnloaded()
  abortActiveRun("extension_unloaded")
  resetState()
  resetWashState("extension_unloaded", false)
  washInitialized = false
  emitEvent("I", "extension_unloaded")
end

M.onBeamNGTrigger = onBeamNGTrigger
M.onEricrolphCannonCarWashScenarioHoldAcknowledged = (
  onEricrolphCannonCarWashScenarioHoldAcknowledged
)
M.onEricrolphCannonCarWashScenarioReleaseAcknowledged = (
  onEricrolphCannonCarWashScenarioReleaseAcknowledged
)
M.onEricrolphCannonCarWashScenarioRepairIntegrityAcknowledged = (
  onEricrolphCannonCarWashScenarioRepairIntegrityAcknowledged
)
M.onEricrolphCannonCarWashScenarioRepairReleaseAcknowledged = (
  onEricrolphCannonCarWashScenarioRepairReleaseAcknowledged
)
M.onPreRender = onPreRender
M.onClientStartMission = onClientStartMission
M.onClientEndMission = onClientEndMission
M.onVehicleResetted = onVehicleResetted
M.onVehicleDestroyed = onVehicleDestroyed
M.onExtensionLoaded = onExtensionLoaded
M.onExtensionUnloaded = onExtensionUnloaded
M.getSystemState = washSystemState

return M
