-- BeamMP transport adapter for The Free-Pivot Sumo Gyro-Platform.
--
-- Match simulation remains in the generated per-prop runtime.  This root
-- extension owns only the BeamMP event registration and forwards lifecycle
-- events; keeping that boundary thin also leaves the prop fully standalone
-- when BeamMP is absent.

local M = {}

local EVENT_S2C = "ericrolph_games_s2c_v1"
local HANDLER_NAME = "ericrolph_sumo_gyro_platform_beammp"
local RUNTIME_NAME = "ericrolph__sumo__gyro__platform_runtime"

local handlerInstalled = false

local function runtime()
  return extensions and extensions[RUNTIME_NAME] or nil
end

local function forward(hookName, ...)
  local target = runtime()
  local hook = target and target[hookName]
  if type(hook) ~= "function" then return false end
  local ok, err = pcall(hook, ...)
  if not ok then
    log("E", "ERICROLPH_SUMO_BEAMMP", hookName .. " failed: " .. tostring(err))
    return false
  end
  return true
end

local function onServerMessage(payload)
  forward("onEricrolphSumoBeamMPMessage", payload)
end

local function installHandler()
  if handlerInstalled or type(AddEventHandler) ~= "function" then return end
  AddEventHandler(EVENT_S2C, onServerMessage, HANDLER_NAME)
  handlerInstalled = true
end

local function removeHandler()
  if not handlerInstalled then return end
  if type(RemoveEventHandler) == "function" then
    RemoveEventHandler(EVENT_S2C, HANDLER_NAME)
  end
  handlerInstalled = false
end

local function onInit()
  setExtensionUnloadMode(M, "manual")
  installHandler()
end

local function onExtensionUnloaded()
  removeHandler()
end

local function onBeamMPPostJoin()
  installHandler()
  forward("onEricrolphSumoBeamMPPostJoin")
end

local function onBeamMPServerLeave()
  forward("onEricrolphSumoBeamMPServerLeave")
end

M.onInit = onInit
M.onExtensionUnloaded = onExtensionUnloaded
M.onBeamMPPostJoin = onBeamMPPostJoin
M.onBeamMPServerLeave = onBeamMPServerLeave

return M
