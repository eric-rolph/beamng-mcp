-- BeamMP Client resources need a modScript to load custom-event adapters.
-- Gameplay is still owned by the spawned Hot Potato prop/runtime; this
-- extension only carries versioned envelopes to and from the server relay.

local EXTENSION_NAME = "ericrolphHotPotatoBeamMP"

if not extensions.isExtensionLoaded(EXTENSION_NAME) then
  extensions.load(EXTENSION_NAME)
end

return true
