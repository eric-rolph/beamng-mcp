from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BEAMNG_MCP_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 64256
    home: Path | None = None
    user_path: Path | None = None
    launch: bool = False
    lua_ws_host: str = "127.0.0.1"
    lua_ws_port: int = 8765
    lua_shared_secret: str = Field(default="change-me", min_length=8)
    artifact_dir: Path = Path("artifacts")
    max_speed_kph: float = Field(default=130.0, gt=0, le=400)
    control_ttl_seconds: float = Field(default=0.5, gt=0.05, le=5)
    vision_device: str = "cuda:0"
    vision_model: str = "yolo11n.pt"
    vision_hz: float = Field(default=10, gt=0, le=60)

