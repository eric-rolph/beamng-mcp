-- Test-only retail BeamNG GPU capture fixture.
--
-- BeamNGpy's Camera sensor is restricted to BeamNG.tech.  This extension uses
-- the render-view API shipped in retail BeamNG.drive to save one exact-size
-- player-camera frame for integration testing.  It is copied only into the
-- sentinel-marked disposable user profile and removed by the Python test.

local M = {}

M.dependencies = {"render_renderViews"}

local requested = false

local function onInit()
  setExtensionUnloadMode(M, "manual")
  log("I", "beamng_mcp_vision_test", "retail RenderView capture fixture loaded")
end

local function requestCapture()
  local vehicle = getPlayerVehicle and getPlayerVehicle(0) or nil
  if not vehicle or not core_camera then return end

  local directory = "screenshots/beamng-mcp"
  if not FS:directoryExists(directory) then
    FS:directoryCreate(directory, true)
  end

  requested = true
  local ok, captureError = pcall(function()
    render_renderViews.takeScreenshot({
      renderViewName = "beamngMcpVisionLiveTest",
      filename = directory .. "/vision-live.png",
      resolution = vec3(640, 360, 0),
      pos = core_camera.getPosition(),
      rot = core_camera.getQuat(),
      fov = core_camera.getFovDeg(),
      nearPlane = 0.1,
      screenshotDelay = 0.1
    })
  end)
  if ok then
    log("I", "beamng_mcp_vision_test", "retail RenderView capture requested")
  else
    log("E", "beamng_mcp_vision_test", "capture failed: " .. tostring(captureError))
  end
end

local function onUpdate()
  if requested then return end
  requestCapture()
end

M.onInit = onInit
M.onUpdate = onUpdate

return M
