local M = {}

local GE_EXTENSION_PATH = "ericrolph_cannon_car_wash/runtime"
-- BeamNG doubles literal underscores before replacing the path separator.
-- ericrolph_cannon_car_wash/runtime ->
-- ericrolph__cannon__car__wash_runtime
local GE_EXTENSION_NAME = "ericrolph__cannon__car__wash_runtime"
local RETRY_INTERVAL_SECONDS = 0.5
local MAX_REGISTRATION_ATTEMPTS = 12

local registrationConfirmed = false
local registrationAttempts = 0
local retryElapsed = 0

local function queueRegistration()
  if registrationConfirmed or registrationAttempts >= MAX_REGISTRATION_ATTEMPTS then return end
  registrationAttempts = registrationAttempts + 1
  local vehicleId = obj:getID()
  obj:queueGameEngineLua(string.format([[
    if not extensions.isExtensionLoaded(%q) then
      extensions.load(%q)
    end
    local extension = extensions[%q]
    if extension and extension.registerProp then
      extension.registerProp(%d)
    end
  ]], GE_EXTENSION_NAME, GE_EXTENSION_PATH, GE_EXTENSION_NAME, vehicleId))
end

local function resetRegistration()
  registrationConfirmed = false
  registrationAttempts = 0
  retryElapsed = RETRY_INTERVAL_SECONDS
end

local function onVehicleLoaded()
  resetRegistration()
  queueRegistration()
end

local function onReset()
  resetRegistration()
  queueRegistration()
end

local function updateGFX(dt)
  if registrationConfirmed or registrationAttempts >= MAX_REGISTRATION_ATTEMPTS then return end
  retryElapsed = retryElapsed + dt
  if retryElapsed < RETRY_INTERVAL_SECONDS then return end
  retryElapsed = 0
  queueRegistration()
end

local function onEricrolphCannonCarWashRegistered()
  registrationConfirmed = true
end

local function onExtensionUnloaded()
  local vehicleId = obj and obj:getID() or nil
  if not vehicleId then return end
  obj:queueGameEngineLua(string.format([[
    local extension = extensions[%q]
    if extension and extension.unregisterProp then
      extension.unregisterProp(%d, "vehicle_lua_unloaded")
    end
  ]], GE_EXTENSION_NAME, vehicleId))
end

M.onVehicleLoaded = onVehicleLoaded
M.onReset = onReset
M.updateGFX = updateGFX
M.onEricrolphCannonCarWashRegistered = onEricrolphCannonCarWashRegistered
M.onExtensionUnloaded = onExtensionUnloaded

return M
