local EXTENSION_NAME = "ericrolphSumoBeamMP"

if not extensions.isExtensionLoaded(EXTENSION_NAME) then
  extensions.load(EXTENSION_NAME)
end

return true
