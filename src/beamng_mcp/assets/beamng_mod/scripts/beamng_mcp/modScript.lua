-- BeamNG executes this file when the unpacked mod is activated.
-- It loads the bridge exactly once and keeps the extension path in one place.

local EXTENSION_NAME = "beamng__mcp_bridge"
local EXTENSION_PATH = "beamng_mcp/bridge"

if not extensions.isExtensionLoaded(EXTENSION_NAME) then
  extensions.load(EXTENSION_PATH)
end

return true
