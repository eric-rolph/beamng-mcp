local EXTENSION_NAME = "beamng__mcp_vision__test__capture"
local EXTENSION_PATH = "beamng_mcp/vision_test_capture"

if not extensions.isExtensionLoaded(EXTENSION_NAME) then
  extensions.load(EXTENSION_PATH)
end

return true
