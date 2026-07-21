-- BeamNG executes this file when the Cannon Car Wash mod is activated.
-- Keep the extension path static so loading remains auditable and repository-safe.

local EXTENSION_NAME = "cannon__car__wash_main"
local EXTENSION_PATH = "cannon_car_wash/main"

if not extensions.isExtensionLoaded(EXTENSION_NAME) then
  extensions.load(EXTENSION_PATH)
end

return true
