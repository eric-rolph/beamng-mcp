local M = {}

local LOG_TAG = "CANNON_CAR_WASH"
local TRIGGER_NAME = "LaunchTrigger_Mesh"
local TRIGGER_CLASS = "BeamNGTrigger"
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

local function exactTriggerFromEvent(data)
  if type(data) ~= "table"
    or data.triggerName ~= TRIGGER_NAME
    or not integer(data.triggerID) then
    return nil
  end

  local triggerByName = scenetree.findObject(TRIGGER_NAME)
  local triggerById = scenetree.findObjectById(data.triggerID)
  if not triggerByName or not triggerById then return nil end
  if triggerByName:getId() ~= data.triggerID then return nil end
  if triggerById:getId() ~= data.triggerID then return nil end
  if triggerByName:getClassName() ~= TRIGGER_CLASS then return nil end
  if triggerById:getClassName() ~= TRIGGER_CLASS then return nil end
  return triggerById
end

local function exactTruckFromEvent(data)
  if type(data) ~= "table" or not integer(data.subjectID) then return nil end
  local vehicle = be:getObjectByID(data.subjectID)
  if not vehicle then return nil end
  if vehicle:getId() ~= data.subjectID then return nil end
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

local function resetState()
  activeRun = nil
  armed = true
  countdownIndex = 1
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

local function onBeamNGTrigger(data)
  if type(data) ~= "table"
    or data.triggerName ~= TRIGGER_NAME
    or not integer(data.triggerID)
    or not integer(data.subjectID) then
    return
  end
  if not exactTriggerFromEvent(data) then return end
  local vehicle = exactTruckFromEvent(data)
  if not vehicle then return end

  if data.event == "exit" then
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

local function onPreRender(dtReal,dtSim,dtRaw)
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
  emitEvent("I", "session_start", {level_path = tostring(levelPath or "")})
end

local function onClientEndMission(levelPath)
  abortActiveRun("mission_ended")
  resetState()
  emitEvent("I", "session_end", {level_path = tostring(levelPath or "")})
end

local function onVehicleResetted(vehicleId)
  if activeRun and activeRun.vehicleId == vehicleId then
    abortActiveRun("vehicle_reset")
    resetState()
  end
end

local function onVehicleDestroyed(vehicleId)
  if activeRun and activeRun.vehicleId == vehicleId then
    emitEvent("W", "abort", {reason = "vehicle_destroyed"})
    resetState()
  end
end

local function onExtensionLoaded()
  abortActiveRun("extension_loaded")
  resetState()
  if setExtensionUnloadMode then setExtensionUnloadMode(M, "manual") end
  emitEvent("I", "extension_loaded")
end

local function onExtensionUnloaded()
  abortActiveRun("extension_unloaded")
  resetState()
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

return M
