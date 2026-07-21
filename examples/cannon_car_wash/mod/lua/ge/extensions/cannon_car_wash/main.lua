local M = {}

local LOG_TAG = "CANNON_CAR_WASH"
local LAUNCH_TRIGGER_NAME = "LaunchTrigger_Mesh"
local WASH_TRIGGER_NAME = "WashActivationTrigger_Mesh"
local TRIGGER_CLASS = "BeamNGTrigger"
local VISUAL_NAME = "CannonCarWash_Visual"
local VISUAL_CLASS = "TSStatic"
local MISTER_CLASS = "ParticleEmitterNode"
local MISTER_NAMES = {
  "CannonWash_Mister_PreSoak_L_1",
  "CannonWash_Mister_PreSoak_L_2",
  "CannonWash_Mister_PreSoak_L_3",
  "CannonWash_Mister_PreSoak_R_1",
  "CannonWash_Mister_PreSoak_R_2",
  "CannonWash_Mister_PreSoak_R_3",
  "CannonWash_Mister_Rinse_L_1",
  "CannonWash_Mister_Rinse_L_2",
  "CannonWash_Mister_Rinse_L_3",
  "CannonWash_Mister_Rinse_R_1",
  "CannonWash_Mister_Rinse_R_2",
  "CannonWash_Mister_Rinse_R_3",
}
local TRUCK_NAME = "cannon_car_wash_truck"
local TRUCK_MODEL = "pickup"
local UI_CATEGORY = "cannon_car_wash_countdown"
local COUNTDOWN_INTERVAL_SECONDS = 1
local COUNTDOWN_MESSAGES = {"3...", "2...", "1..."}
local COUNTDOWN_EVENTS = {"countdown_3", "countdown_2", "countdown_1"}
local LAUNCH_SPEED_MPS = 100

local HOLD_VEHICLE_COMMAND = [[
if ai then ai.setMode("disabled") end
input.event("throttle", 0, 1)
input.event("brake", 1, 1)
input.event("parkingbrake", 1, 1)
controller.setFreeze(1)
]]

local RELEASE_VEHICLE_COMMAND = [[
controller.setFreeze(0)
input.event("parkingbrake", 0, 1)
input.event("brake", 0, 1)
input.event("throttle", 0, 1)
]]

local activeRun = nil
local armed = true
local countdownIndex = 1
local runCounter = 0
local sessionCounter = 0
local washSubjects = {}
local washSystemsActive = false
local washInitialized = false
local pendingLaunchEntries = {}

local function integer(value)
  return type(value) == "number" and value >= 1 and value % 1 == 0
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

local function exactTruckFromEvent(data)
  local vehicle = exactVehicleFromEvent(data)
  if not vehicle then return nil end
  if vehicle:getName() ~= TRUCK_NAME then return nil end
  if vehicle:getJBeamFilename() ~= TRUCK_MODEL then return nil end
  return vehicle
end

local function activeVehicle()
  if not activeRun then return nil end
  local vehicle = be:getObjectByID(activeRun.vehicleId)
  if not vehicle or vehicle:getId() ~= activeRun.vehicleId then return nil end
  if vehicle:getName() ~= TRUCK_NAME then return nil end
  if vehicle:getJBeamFilename() ~= TRUCK_MODEL then return nil end
  return vehicle
end

local function queueVehicleCommand(vehicle, command, failureReason)
  local ok, commandError = pcall(function() vehicle:queueLuaCommand(command) end)
  if not ok then
    emitError(failureReason, {detail = tostring(commandError)})
    return false
  end
  return true
end

local function releaseVehicle(vehicle, reason)
  if vehicle then
    queueVehicleCommand(vehicle, RELEASE_VEHICLE_COMMAND, "release_command_failed")
  end
  if activeRun then
    activeRun.holding = false
    emitEvent("I", "release", {reason = reason})
  end
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

local function resolveWashObjects()
  local visual = exactSceneObject(VISUAL_NAME, VISUAL_CLASS)
  local misters = {}
  local missing = {}
  if not visual then missing[#missing + 1] = VISUAL_NAME end
  for _, name in ipairs(MISTER_NAMES) do
    local mister = exactSceneObject(name, MISTER_CLASS)
    if mister then
      misters[#misters + 1] = mister
    else
      missing[#missing + 1] = name
    end
  end
  return visual, misters, missing
end

local function forceWashSystemsOff(visual, misters)
  if visual then pcall(function() visual:setField("playAmbient", 0, "0") end) end
  for _, mister in ipairs(misters or {}) do
    pcall(function() mister:setActive(false) end)
  end
  washSystemsActive = false
  washInitialized = false
end

local function setWashSystemsEnabled(enabled, reason, strict)
  local expectedField = enabled and "1" or "0"
  local visual, misters, missing = resolveWashObjects()
  if not visual or #missing > 0 then
    forceWashSystemsOff(visual, misters)
    if strict then
      emitError("wash_objects_missing", {missing_objects = table.concat(missing, ",")})
    end
    return false
  end

  local updated, updateError = pcall(function()
    visual:setField("playAmbient", 0, expectedField)
    for _, mister in ipairs(misters) do
      mister:setActive(enabled)
    end
  end)
  if not updated then
    forceWashSystemsOff(visual, misters)
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
    mister_emitter = "BNGP_sprinkler",
    mister_count = #MISTER_NAMES,
  })
  return true
end

local function resetWashState(reason, strict)
  washSubjects = {}
  washInitialized = false
  return setWashSystemsEnabled(false, reason, strict)
end

local function removeWashSubject(vehicleId, reason)
  pendingLaunchEntries[vehicleId] = nil
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
  local activeMisters = 0
  local presentMisters = 0
  for _, name in ipairs(MISTER_NAMES) do
    local mister = exactSceneObject(name, MISTER_CLASS)
    if mister then
      presentMisters = presentMisters + 1
      local activeField = string.lower(tostring(mister:getField("active", 0) or ""))
      if activeField == "1" or activeField == "true" then
        activeMisters = activeMisters + 1
      end
    end
  end
  return {
    active = washSystemsActive,
    subject_count = washSubjectCount(),
    roller_play_ambient = visual and visual:getField("playAmbient", 0) or nil,
    mister_active_count = activeMisters,
    mister_present_count = presentMisters,
    mister_expected_count = #MISTER_NAMES,
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
    local active = vehicle or activeVehicle()
    releaseVehicle(active, reason)
    emitEvent("W", "abort", {reason = reason})
  end
  resetState()
end

local function launchVehicle(vehicle)
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
  releaseVehicle(vehicle, "launch")

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

local function countdownJob(job, runNumber)
  local timer = hptimer()
  for nextIndex = 2, #COUNTDOWN_MESSAGES do
    job.sleep(COUNTDOWN_INTERVAL_SECONDS)
    if not activeRun
      or not activeRun.holding
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
  launchVehicle(vehicle)
end

local handleLaunchTrigger

local function processPendingLaunch(subjectId)
  local pending = pendingLaunchEntries[subjectId]
  if not pending or not washSubjects[subjectId] or not washSystemsActive then return end
  pendingLaunchEntries[subjectId] = nil
  handleLaunchTrigger(pending)
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
    emitEvent("I", "wash_trigger_enter", {subject_id = data.subjectID})
    if not wasPresent and not washSystemsActive then
      setWashSystemsEnabled(true, "vehicle_enter", true)
    end
    processPendingLaunch(data.subjectID)
    return
  end
  if data.event ~= "exit" then return end

  pendingLaunchEntries[data.subjectID] = nil
  washSubjects[data.subjectID] = nil
  emitEvent("I", "wash_trigger_exit", {subject_id = data.subjectID})
  if washSubjectCount() == 0 and washSystemsActive then
    setWashSystemsEnabled(false, "last_vehicle_exit", true)
  end
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
  local vehicle = exactTruckFromEvent(data)
  if not vehicle then return end

  if data.event == "exit" then
    pendingLaunchEntries[data.subjectID] = nil
    if activeRun and activeRun.vehicleId == data.subjectID then
      if activeRun.holding then
        abortActiveRun("trigger_exit_during_countdown", vehicle)
      else
        emitEvent("I", "trigger_exit")
        resetState()
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

  pendingLaunchEntries[data.subjectID] = nil
  armed = false
  runCounter = runCounter + 1
  countdownIndex = 1
  activeRun = {
    number = runCounter,
    vehicleId = data.subjectID,
    triggerId = data.triggerID,
    phase = "countdown",
    holding = true,
    elapsedTime = 0,
  }

  emitEvent("I", "containment_verified", {
    trigger_mode = trigger:getField("triggerMode", 0),
    trigger_test_type = trigger:getField("triggerTestType", 0),
  })
  emitEvent("I", "trigger_enter")
  local held = queueVehicleCommand(vehicle, HOLD_VEHICLE_COMMAND, "hold_command_failed")
  if not held then
    abortActiveRun("hold_command_failed", vehicle)
    return
  end
  vehicle:applyClusterVelocityScaleAdd(vehicle:getRefNodeId(), 0, 0, 0, 0)
  emitEvent("I", "hold_start")
  showMessage(COUNTDOWN_MESSAGES[countdownIndex], 1.1)
  emitEvent("I", COUNTDOWN_EVENTS[countdownIndex], {countdown_value = 3})
  local timerCreated, timerOrError = pcall(function()
    return extensions.core_jobsystem.create(countdownJob, nil, activeRun.number)
  end)
  if not timerCreated or not timerOrError then
    emitError("countdown_job_start_failed", {detail = tostring(timerOrError)})
    abortActiveRun("countdown_job_start_failed", vehicle)
    return
  end
  activeRun.countdownJob = timerOrError
  emitEvent("I", "countdown_timer_start", {clock = "jobsystem_hptimer"})
end

local function onBeamNGTrigger(data)
  if type(data) ~= "table" then return end
  if data.triggerName == WASH_TRIGGER_NAME then
    handleWashTrigger(data)
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

  if not activeRun or not activeRun.holding then return end

  local vehicle = activeVehicle()
  if not vehicle then
    emitError("active_vehicle_missing")
    abortActiveRun("active_vehicle_missing")
    return
  end

  if activeRun.holding then
    local stopped, stopError = pcall(function()
      vehicle:applyClusterVelocityScaleAdd(vehicle:getRefNodeId(), 0, 0, 0, 0)
    end)
    if not stopped then
      emitError("hold_velocity_zero_failed", {detail = tostring(stopError)})
      abortActiveRun("hold_velocity_zero_failed", vehicle)
      return
    end
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
  removeWashSubject(vehicleId, "vehicle_reset")
  if activeRun and activeRun.vehicleId == vehicleId then
    abortActiveRun("vehicle_reset")
    resetState()
  end
end

local function onVehicleDestroyed(vehicleId)
  removeWashSubject(vehicleId, "vehicle_destroyed")
  if activeRun and activeRun.vehicleId == vehicleId then
    emitEvent("W", "abort", {reason = "vehicle_destroyed"})
    resetState()
  end
end

local function onExtensionLoaded()
  abortActiveRun("extension_loaded")
  resetState()
  resetWashState("extension_loaded", false)
  if setExtensionUnloadMode then setExtensionUnloadMode(M, "manual") end
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
M.onPreRender = onPreRender
M.onClientStartMission = onClientStartMission
M.onClientEndMission = onClientEndMission
M.onVehicleResetted = onVehicleResetted
M.onVehicleDestroyed = onVehicleDestroyed
M.onExtensionLoaded = onExtensionLoaded
M.onExtensionUnloaded = onExtensionUnloaded
M.getSystemState = washSystemState

return M
