"""Typed configuration loaded from TOML plus narrowly scoped environment overrides."""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from .errors import ConfigurationError


class MCPSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["stdio", "streamable-http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = Field(default=8766, ge=1, le=65535)
    http_token: SecretStr | None = None

    @model_validator(mode="after")
    def require_loopback(self) -> MCPSettings:
        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("MCP HTTP must bind to a loopback host")
        return self


class BeamNGSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=25252, ge=1, le=65535)
    home: Path | None = None
    user: Path | None = None
    launch: bool = True
    target_version: str = "0.38"

    @field_validator("host")
    @classmethod
    def only_loopback(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("BeamNGpy connections are restricted to loopback")
        return value


class LuaSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = "ws://127.0.0.1:8765"
    token: SecretStr | None = None
    request_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    max_message_bytes: int = Field(default=1_048_576, ge=4096, le=16_777_216)
    safety_lease_seconds: float = Field(default=1.0, ge=0.25, le=5.0)
    safety_startup_grace_seconds: float = Field(default=5.0, ge=0.25, le=5.0)

    @field_validator("url")
    @classmethod
    def only_local_websocket(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("Lua bridge URL must not contain surrounding whitespace")

        try:
            parsed = urlsplit(value)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Lua bridge URL is malformed") from exc

        if parsed.scheme != "ws":
            raise ValueError("Lua bridge URL must use an unencrypted loopback WebSocket")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Lua bridge URL must not contain user information")
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Lua bridge URL must use an exact loopback host")
        if port is None:
            raise ValueError("Lua bridge URL must include an explicit port")
        if not 1 <= port <= 65535:
            raise ValueError("Lua bridge URL port must be between 1 and 65535")
        if parsed.path not in {"", "/"}:
            raise ValueError("Lua bridge URL must not contain a path")
        if parsed.query or parsed.fragment or "?" in value or "#" in value:
            raise ValueError("Lua bridge URL must not contain a query or fragment")

        canonical_host = f"[{hostname}]" if hostname == "::1" else hostname
        return f"ws://{canonical_host}:{port}"


class WorkspaceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: Path = Field(
        default_factory=lambda: user_data_path("beamng-mcp", appauthor=False) / "workspace"
    )
    artifacts: Path | None = None
    allow_persistent_map_edits: bool = False
    allow_existing_map_object_edits: bool = False
    allow_mod_install: bool = False
    max_file_bytes: int = Field(default=2_097_152, ge=1024, le=67_108_864)
    max_mod_files: int = Field(default=4096, ge=1, le=100_000)
    max_mod_bytes: int = Field(default=536_870_912, ge=1024, le=17_179_869_184)
    asset_staging_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    max_asset_staging_slots: int = Field(default=16, ge=1, le=128)
    max_structural_nodes: int = Field(default=512, ge=4, le=512)
    max_structural_beams: int = Field(default=4096, ge=6, le=4096)
    max_structural_triangles: int = Field(default=2048, ge=4, le=2048)
    max_structural_actuators: int = Field(default=128, ge=0, le=256)

    @model_validator(mode="after")
    def default_artifacts(self) -> WorkspaceSettings:
        if self.artifacts is None:
            self.artifacts = self.root / "artifacts"
        return self


class VisionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["classical", "segformer", "onnx"] = "classical"
    target_fps: float = Field(default=15.0, ge=1.0, le=60.0)
    frame_timeout_seconds: float = Field(default=0.35, ge=0.05, le=3.0)
    input_width: int = Field(default=640, ge=160, le=3840)
    input_height: int = Field(default=360, ge=90, le=2160)
    max_gpu_memory_mb: int = Field(default=4096, ge=512, le=24576)
    model: str | None = None
    onnx_path: Path | None = None
    allow_model_downloads: bool = False


class Settings(BaseModel):
    """Process configuration. Secrets are intentionally excluded from public snapshots."""

    model_config = ConfigDict(extra="forbid")

    mcp: MCPSettings = Field(default_factory=MCPSettings)
    beamng: BeamNGSettings = Field(default_factory=BeamNGSettings)
    lua: LuaSettings = Field(default_factory=LuaSettings)
    workspace: WorkspaceSettings = Field(default_factory=WorkspaceSettings)
    vision: VisionSettings = Field(default_factory=VisionSettings)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        config_path = path
        if config_path is None and os.getenv("BEAMNG_MCP_CONFIG"):
            config_path = Path(os.environ["BEAMNG_MCP_CONFIG"])

        raw: dict[str, Any] = {}
        if config_path is not None:
            try:
                with config_path.expanduser().open("rb") as handle:
                    raw = tomllib.load(handle)
            except (OSError, tomllib.TOMLDecodeError) as exc:
                raise ConfigurationError(f"Cannot load config {config_path}: {exc}") from exc

        merged = copy.deepcopy(raw)
        overrides: tuple[tuple[str, tuple[str, ...], Any], ...] = (
            ("BEAMNG_MCP_BEAMNG_HOME", ("beamng", "home"), Path),
            ("BEAMNG_MCP_BEAMNG_USER", ("beamng", "user"), Path),
            ("BEAMNG_MCP_BEAMNG_HOST", ("beamng", "host"), str),
            ("BEAMNG_MCP_BEAMNG_PORT", ("beamng", "port"), int),
            ("BEAMNG_MCP_LUA_URL", ("lua", "url"), str),
            ("BEAMNG_MCP_LUA_TOKEN", ("lua", "token"), str),
            ("BEAMNG_MCP_SAFETY_LEASE_SECONDS", ("lua", "safety_lease_seconds"), float),
            (
                "BEAMNG_MCP_SAFETY_STARTUP_GRACE_SECONDS",
                ("lua", "safety_startup_grace_seconds"),
                float,
            ),
            ("BEAMNG_MCP_WORKSPACE", ("workspace", "root"), Path),
            ("BEAMNG_MCP_HTTP_TOKEN", ("mcp", "http_token"), str),
        )
        for env_name, keys, converter in overrides:
            value = os.getenv(env_name)
            if value:
                section = merged.setdefault(keys[0], {})
                section[keys[1]] = converter(value)

        bool_value = os.getenv("BEAMNG_MCP_ALLOW_PERSISTENT_MAP_EDITS")
        if bool_value:
            merged.setdefault("workspace", {})["allow_persistent_map_edits"] = (
                bool_value.lower() in {"1", "true", "yes", "on"}
            )

        bool_value = os.getenv("BEAMNG_MCP_ALLOW_EXISTING_MAP_OBJECT_EDITS")
        if bool_value:
            merged.setdefault("workspace", {})["allow_existing_map_object_edits"] = (
                bool_value.lower() in {"1", "true", "yes", "on"}
            )

        bool_value = os.getenv("BEAMNG_MCP_ALLOW_MOD_INSTALL")
        if bool_value:
            merged.setdefault("workspace", {})["allow_mod_install"] = bool_value.lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        try:
            return cls.model_validate(merged)
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc

    def public_snapshot(self) -> dict[str, Any]:
        snapshot = self.model_dump(mode="json", exclude={"mcp": {"http_token"}, "lua": {"token"}})
        snapshot["mcp"]["http_token_configured"] = self.mcp.http_token is not None
        snapshot["lua"]["token_configured"] = self.lua.token is not None
        return snapshot
