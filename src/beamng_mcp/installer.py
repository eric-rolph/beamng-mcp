"""Install the packaged GELua bridge into a dedicated unpacked mod directory."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from .config import Settings
from .errors import ConfigurationError, SafetyInterlockError

MOD_DIRECTORY = "beamng_mcp"
MOD_MARKER = "beamng-mcp-bridge"
BRIDGE_CONFIG = Path("settings/beamng_mcp.json")
PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@dataclass(frozen=True, slots=True)
class InstallResult:
    destination: Path
    port: int
    token: SecretStr = field(repr=False)
    files: int


def _copy_tree(source: Any, destination: Path) -> int:
    count = 0
    destination.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            count += _copy_tree(entry, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with entry.open("rb") as input_handle, target.open("wb") as output_handle:
                shutil.copyfileobj(input_handle, output_handle)
            count += 1
    return count


def _absolute_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & REPARSE_POINT_ATTRIBUTE)


def _reject_link_components(path: Path) -> None:
    absolute = _absolute_without_resolving(path)
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            os.lstat(current)
        except FileNotFoundError:
            break
        except OSError as exc:
            raise SafetyInterlockError(
                f"Cannot safely inspect install path {current}: {exc}"
            ) from exc
        if _is_link_or_reparse(current):
            raise SafetyInterlockError(
                f"Refusing install path containing a link or reparse point: {current}"
            )


def _restrict_config_permissions(config_path: Path) -> None:
    """Request owner-only access without making platform ACL support mandatory."""

    try:
        os.chmod(config_path, PRIVATE_FILE_MODE, follow_symlinks=False)
    except (NotImplementedError, OSError, ValueError):
        if _is_link_or_reparse(config_path):
            return
        try:
            os.chmod(config_path, PRIVATE_FILE_MODE)
        except OSError:
            pass


def _require_recognized_install(destination: Path) -> None:
    config_path = destination / BRIDGE_CONFIG
    _reject_link_components(config_path)
    try:
        existing = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing = None
    if not isinstance(existing, dict) or existing.get("marker") != MOD_MARKER:
        raise SafetyInterlockError(
            f"Refusing to force-update {destination} without a recognized bridge marker"
        )


def _cleanup_staging(staging: Path) -> None:
    """Remove only the regular staging directory created by this process."""

    if not os.path.lexists(staging):
        return
    try:
        _reject_link_components(staging)
    except SafetyInterlockError:
        return
    try:
        shutil.rmtree(staging)
    except OSError:
        pass


def _rename_directory(source: Path, destination: Path) -> None:
    """Retry narrowly scoped Windows directory moves that can race file scanners."""

    for attempt in range(5):
        try:
            source.rename(destination)
            return
        except PermissionError as exc:
            if attempt == 4:
                raise
            # Windows Defender/indexers can briefly retain a just-written file.
            # Keep the retry window bounded and re-check that no destination
            # appeared before attempting the atomic directory move again.
            if os.path.lexists(destination):
                raise SafetyInterlockError(
                    f"Refusing directory move because destination appeared: {destination}"
                ) from exc
            time.sleep(0.05 * (attempt + 1))


def install_lua_bridge(
    settings: Settings,
    *,
    user_path: Path,
    port: int = 8765,
    force: bool = False,
) -> InstallResult:
    """Install assets and generate a per-install token; never expose the token in logs."""

    if not 1024 <= port <= 65535:
        raise ConfigurationError("Lua bridge port must be between 1024 and 65535")
    user_path = _absolute_without_resolving(user_path)
    _reject_link_components(user_path)
    destination = user_path / "mods" / "unpacked" / MOD_DIRECTORY
    _reject_link_components(destination.parent)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _reject_link_components(destination.parent)
    destination_exists = os.path.lexists(destination)
    if destination_exists:
        _reject_link_components(destination)
    existing_config = destination / BRIDGE_CONFIG
    if destination_exists and not force:
        if existing_config.is_file():
            raise SafetyInterlockError(
                f"Bridge is already installed at {destination}; pass --force to update it"
            )
        raise SafetyInterlockError(
            f"Refusing to replace unrecognized directory {destination}; move it first"
        )
    if destination_exists and force:
        _require_recognized_install(destination)

    source = files("beamng_mcp.assets").joinpath("beamng_mod")
    staging_root = user_path / ".beamng_mcp_staging"
    _reject_link_components(staging_root)
    staging_root.mkdir(exist_ok=True)
    _reject_link_components(staging_root)
    staging = Path(tempfile.mkdtemp(prefix="stage-", dir=staging_root))
    cleanup_staging: Path | None = staging
    try:
        copied = _copy_tree(source, staging)
        token = secrets.token_urlsafe(32)
        config_path = staging / BRIDGE_CONFIG
        raw: dict[str, Any] = {}
        if config_path.is_file():
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        raw.update(
            {
                "marker": MOD_MARKER,
                "port": port,
                "token": token,
                "max_payload_bytes": settings.lua.max_message_bytes,
                "telemetry_interval_seconds": max(1.0 / min(settings.vision.target_fps, 20.0), 0.2),
                "heartbeat_interval_seconds": 5.0,
                "heartbeat_timeout_seconds": 20.0,
                "safety_lease_seconds": settings.lua.safety_lease_seconds,
                "safety_startup_grace_seconds": settings.lua.safety_startup_grace_seconds,
                "allow_persistent_map_edits": settings.workspace.allow_persistent_map_edits,
                "allow_existing_map_object_edits": (
                    settings.workspace.allow_existing_map_object_edits
                ),
            }
        )
        temporary = config_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        temporary.replace(config_path)
        _restrict_config_permissions(config_path)

        backup: Path | None = None
        _reject_link_components(destination.parent)
        if destination_exists:
            _reject_link_components(destination)
            _require_recognized_install(destination)
            backup_root = user_path / "mods" / f"{MOD_DIRECTORY}_backups"
            _reject_link_components(backup_root)
            backup_root.mkdir(exist_ok=True)
            _reject_link_components(backup_root)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            backup = backup_root / f"backup-{timestamp}-{secrets.token_hex(4)}"
            _rename_directory(destination, backup)
        try:
            _rename_directory(staging, destination)
        except Exception:
            if backup is not None and backup.exists() and not os.path.lexists(destination):
                _rename_directory(backup, destination)
            raise
        cleanup_staging = None
        _restrict_config_permissions(destination / BRIDGE_CONFIG)
    finally:
        if cleanup_staging is not None:
            _cleanup_staging(cleanup_staging)
    return InstallResult(
        destination=destination,
        port=port,
        token=SecretStr(token),
        files=copied,
    )


def discover_lua_token(user_path: Path) -> SecretStr | None:
    config_path = (
        _absolute_without_resolving(user_path) / "mods" / "unpacked" / MOD_DIRECTORY / BRIDGE_CONFIG
    )
    try:
        _reject_link_components(config_path)
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, SafetyInterlockError):
        return None
    if not isinstance(raw, dict):
        return None
    token = raw.get("token")
    if raw.get("marker") != MOD_MARKER or not isinstance(token, str) or len(token) < 32:
        return None
    return SecretStr(token)
