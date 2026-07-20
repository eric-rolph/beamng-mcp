from .beamng import BeamNGController
from .config import Settings
from .lua_bridge import LuaBridge
from .safety import ControlSafetyGate
from .vision import VisionEngine


class Application:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.beamng = BeamNGController(self.settings)
        self.lua = LuaBridge(
            self.settings.lua_ws_host,
            self.settings.lua_ws_port,
            self.settings.lua_shared_secret,
        )
        self.vision = VisionEngine(self.settings.vision_model, self.settings.vision_device)
        self.safety = ControlSafetyGate(self.settings.control_ttl_seconds, self.beamng.stop)

