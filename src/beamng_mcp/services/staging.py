"""Single-purpose, path-confined inbox for Blender structural handoffs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any

from ..errors import ConflictError, NotFoundError, WorkspaceError
from .mods import MOD_NAME, ModWorkspace, _absolute_lexical, _is_reparse_stat

ASSET_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SLOT_ID = re.compile(r"^[a-f0-9]{32}$")
ALLOWED_EXPORT_FORMATS = frozenset({"dae", "gltf"})
STAGE_METADATA = "stage.json"
HELPER_NAME = "beamng_softbody_export.py"
RUNNER_NAME = "run_export.py"
MANIFEST_NAME = "structure.manifest.json"


@dataclass(frozen=True)
class StagePaths:
    slot_id: str
    directory: Path
    metadata: Path
    helper: Path
    runner: Path
    manifest: Path
    visual: Path
    expires_at: datetime


@dataclass(frozen=True)
class StagedAssetData:
    slot_id: str
    mod_name: str
    asset_name: str
    visual_format: str
    manifest_bytes: bytes
    manifest_sha256: str
    visual_bytes: bytes
    visual_sha256: str
    visual_size: int
    expires_at: datetime
    request_contract: dict[str, Any]


@dataclass(frozen=True)
class _StageBinding:
    """Server-session evidence which the writable handoff directory cannot redefine."""

    mod_name: str
    asset_name: str
    visual_format: str
    visual_name: str
    expires_at: datetime
    request_bytes: bytes
    request_sha256: str
    helper_sha256: str
    runner_sha256: str


class AssetStagingInbox:
    """Create one-use Blender export slots and stable-read their fixed outputs."""

    def __init__(self, mods: ModWorkspace) -> None:
        self.mods = mods
        self.settings = mods.settings
        self.root = _absolute_lexical(mods.root / "imports")
        self._bindings: dict[str, _StageBinding] = {}
        self._lock = RLock()

    def ensure(self) -> None:
        self.mods._assert_no_reparse_components(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.mods._assert_no_reparse_components(self.root)

    def create(
        self,
        *,
        mod_name: str,
        asset_name: str,
        visual_format: str,
        helper_source: bytes,
        runner_source: bytes,
        request_contract: dict[str, Any],
    ) -> StagePaths:
        with self._lock:
            return self._create_locked(
                mod_name=mod_name,
                asset_name=asset_name,
                visual_format=visual_format,
                helper_source=helper_source,
                runner_source=runner_source,
                request_contract=request_contract,
            )

    def _create_locked(
        self,
        *,
        mod_name: str,
        asset_name: str,
        visual_format: str,
        helper_source: bytes,
        runner_source: bytes,
        request_contract: dict[str, Any],
    ) -> StagePaths:
        if not MOD_NAME.fullmatch(mod_name):
            raise WorkspaceError("mod_name must start with a lowercase letter and use [a-z0-9_-]")
        if not ASSET_NAME.fullmatch(asset_name):
            raise WorkspaceError("asset_name must be lowercase snake_case")
        if visual_format not in ALLOWED_EXPORT_FORMATS:
            raise WorkspaceError("visual_format must be dae or gltf")
        for name, data in ((HELPER_NAME, helper_source), (RUNNER_NAME, runner_source)):
            if not data or len(data) > self.settings.max_file_bytes:
                raise WorkspaceError(
                    f"Staged {name} must contain 1..{self.settings.max_file_bytes} bytes"
                )

        self.ensure()
        if self._prune_stale_slots() >= self.settings.max_asset_staging_slots:
            raise WorkspaceError(
                "Active asset staging slot limit reached; consume or wait for an expiry"
            )
        slot_id = uuid.uuid4().hex
        directory = self._slot(slot_id, must_exist=False)
        try:
            directory.mkdir(parents=False, exist_ok=False)
        except FileExistsError as exc:  # pragma: no cover - UUID collision is defensive only
            raise ConflictError("Generated asset staging slot already exists") from exc
        self.mods._assert_no_reparse_components(directory)

        created_at = datetime.now(UTC)
        expires_at = created_at + timedelta(seconds=self.settings.asset_staging_ttl_seconds)
        visual_name = f"visual.{visual_format}"
        request_bytes = self._canonical_json(request_contract)
        request_sha256 = sha256_bytes(request_bytes)
        helper_sha256 = sha256_bytes(helper_source)
        runner_sha256 = sha256_bytes(runner_source)
        metadata = {
            "schema": "beamng-mcp-asset-stage-v1",
            "slot_id": slot_id,
            "mod_name": mod_name,
            "asset_name": asset_name,
            "visual_format": visual_format,
            "visual_name": visual_name,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "consumed": False,
            "request_sha256": request_sha256,
            "helper_sha256": helper_sha256,
            "runner_sha256": runner_sha256,
        }
        try:
            self._create_regular(directory / STAGE_METADATA, self._canonical_json(metadata))
            self._create_regular(directory / HELPER_NAME, helper_source)
            self._create_regular(directory / RUNNER_NAME, runner_source)
        except Exception:
            self._delete_regular_slot(directory)
            raise
        self._bindings[slot_id] = _StageBinding(
            mod_name=mod_name,
            asset_name=asset_name,
            visual_format=visual_format,
            visual_name=visual_name,
            expires_at=expires_at,
            request_bytes=request_bytes,
            request_sha256=request_sha256,
            helper_sha256=helper_sha256,
            runner_sha256=runner_sha256,
        )
        return StagePaths(
            slot_id=slot_id,
            directory=directory,
            metadata=directory / STAGE_METADATA,
            helper=directory / HELPER_NAME,
            runner=directory / RUNNER_NAME,
            manifest=directory / MANIFEST_NAME,
            visual=directory / visual_name,
            expires_at=expires_at,
        )

    def read(self, slot_id: str) -> StagedAssetData:
        with self._lock:
            return self._read_locked(slot_id)

    def _read_locked(self, slot_id: str) -> StagedAssetData:
        directory = self._slot(slot_id)
        metadata = self._read_metadata(directory)
        binding = self._binding(slot_id)
        self._verify_metadata_binding(metadata, binding)
        expires_at = self._parse_expiry(metadata)
        if datetime.now(UTC) >= expires_at:
            raise WorkspaceError("Asset staging slot has expired; create a fresh export slot")
        if metadata.get("consumed") is not False:
            raise ConflictError("Asset staging slot has already been consumed")

        visual_format = metadata.get("visual_format")
        visual_name = metadata.get("visual_name")
        if visual_format not in ALLOWED_EXPORT_FORMATS or visual_name != f"visual.{visual_format}":
            raise WorkspaceError("Asset staging metadata has an invalid visual format")

        expected_names = {
            STAGE_METADATA,
            HELPER_NAME,
            RUNNER_NAME,
            MANIFEST_NAME,
            visual_name,
        }
        self._validate_directory_entries(directory, expected_names)
        helper_sha256, _helper_size, _ = self.mods._stable_file(
            directory / HELPER_NAME,
            max_bytes=self.settings.max_file_bytes,
        )
        runner_sha256, _runner_size, _ = self.mods._stable_file(
            directory / RUNNER_NAME,
            max_bytes=self.settings.max_file_bytes,
        )
        if helper_sha256 != binding.helper_sha256 or runner_sha256 != binding.runner_sha256:
            raise ConflictError("Reviewed Blender helper or generated runner was modified")
        manifest_sha256, _manifest_size, manifest_bytes = self.mods._stable_file(
            directory / MANIFEST_NAME,
            collect=True,
            max_bytes=self.settings.max_file_bytes,
        )
        visual_sha256, visual_size, visual_bytes = self.mods._stable_file(
            directory / visual_name,
            collect=True,
            max_bytes=self.settings.max_file_bytes,
        )
        assert manifest_bytes is not None and visual_bytes is not None
        request_contract = json.loads(binding.request_bytes)
        if not isinstance(request_contract, dict):  # pragma: no cover - created internally
            raise WorkspaceError("Asset staging request contract is invalid")
        return StagedAssetData(
            slot_id=slot_id,
            mod_name=self._metadata_string(metadata, "mod_name"),
            asset_name=self._metadata_string(metadata, "asset_name"),
            visual_format=visual_format,
            manifest_bytes=manifest_bytes,
            manifest_sha256=manifest_sha256,
            visual_bytes=visual_bytes,
            visual_sha256=visual_sha256,
            visual_size=visual_size,
            expires_at=expires_at,
            request_contract=request_contract,
        )

    def consume(self, slot_id: str, *, manifest_sha256: str) -> None:
        with self._lock:
            self._consume_locked(slot_id, manifest_sha256=manifest_sha256)

    def _consume_locked(self, slot_id: str, *, manifest_sha256: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{64}", manifest_sha256):
            raise WorkspaceError("A lowercase SHA-256 digest is required")
        directory = self._slot(slot_id)
        metadata_path = directory / STAGE_METADATA
        metadata = self._read_metadata(directory)
        binding = self._binding(slot_id)
        self._verify_metadata_binding(metadata, binding)
        if metadata.get("consumed") is not False:
            raise ConflictError("Asset staging slot has already been consumed")
        metadata["consumed"] = True
        metadata["consumed_at"] = datetime.now(UTC).isoformat()
        metadata["manifest_sha256"] = manifest_sha256
        self._replace_regular(metadata_path, self._canonical_json(metadata))

    def _prune_stale_slots(self) -> int:
        """Remove expired/consumed regular slots and return the active slot count."""

        active = 0
        now = datetime.now(UTC)
        try:
            entries = list(os.scandir(self.root))
        except OSError as exc:
            raise WorkspaceError(f"Cannot inspect asset staging inbox: {exc}") from exc
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            if (
                not SLOT_ID.fullmatch(entry.name)
                or entry.is_symlink()
                or _is_reparse_stat(metadata)
                or not stat.S_ISDIR(metadata.st_mode)
            ):
                raise WorkspaceError(f"Unexpected entry in asset staging inbox: {entry.name}")
            directory = Path(entry.path)
            try:
                stage_metadata = self._read_metadata(directory)
                expires_at = self._parse_expiry(stage_metadata)
            except (NotFoundError, WorkspaceError):
                active += 1
                continue
            if stage_metadata.get("consumed") is True or now >= expires_at:
                self._delete_regular_slot(directory)
                self._bindings.pop(entry.name, None)
            else:
                active += 1
        return active

    def _delete_regular_slot(self, directory: Path) -> None:
        """Delete only verified regular files in one resolved UUID slot."""

        resolved_root = self.root.resolve(strict=False)
        resolved = directory.resolve(strict=False)
        if not resolved.is_relative_to(resolved_root) or resolved.parent != resolved_root:
            raise WorkspaceError("Refusing to delete an asset slot outside the staging inbox")
        if not SLOT_ID.fullmatch(resolved.name):
            raise WorkspaceError("Refusing to delete an invalid asset slot name")
        if not resolved.exists():
            return
        self.mods._assert_no_reparse_components(resolved)
        with os.scandir(resolved) as iterator:
            entries = list(iterator)
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            if (
                entry.is_symlink()
                or _is_reparse_stat(metadata)
                or not stat.S_ISREG(metadata.st_mode)
            ):
                raise WorkspaceError(f"Refusing to clean non-regular staging entry: {entry.name}")
        for entry in entries:
            Path(entry.path).unlink()
        resolved.rmdir()

    def _binding(self, slot_id: str) -> _StageBinding:
        binding = self._bindings.get(slot_id)
        if binding is None:
            raise ConflictError(
                "Asset staging slot is not bound to this server session; create a fresh slot"
            )
        return binding

    @staticmethod
    def _verify_metadata_binding(metadata: dict[str, Any], binding: _StageBinding) -> None:
        expected = {
            "mod_name": binding.mod_name,
            "asset_name": binding.asset_name,
            "visual_format": binding.visual_format,
            "visual_name": binding.visual_name,
            "expires_at": binding.expires_at.isoformat(),
            "request_sha256": binding.request_sha256,
            "helper_sha256": binding.helper_sha256,
            "runner_sha256": binding.runner_sha256,
        }
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ConflictError("Asset staging metadata no longer matches its server-side binding")

    def _slot(self, slot_id: str, *, must_exist: bool = True) -> Path:
        if not SLOT_ID.fullmatch(slot_id):
            raise WorkspaceError("slot_id must be a 32-character lowercase hexadecimal ID")
        self.mods._assert_no_reparse_components(self.root)
        lexical = self.root / slot_id
        self.mods._assert_no_reparse_components(lexical)
        resolved_root = self.root.resolve(strict=False)
        resolved = lexical.resolve(strict=False)
        self.mods._assert_no_reparse_components(lexical)
        if not resolved.is_relative_to(resolved_root):
            raise WorkspaceError("Resolved asset staging path escaped the inbox")
        if must_exist:
            try:
                metadata = os.lstat(resolved)
            except FileNotFoundError as exc:
                raise NotFoundError(f"Asset staging slot {slot_id!r} does not exist") from exc
            if _is_reparse_stat(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise NotFoundError(f"Asset staging slot {slot_id!r} does not exist")
        return resolved

    def _read_metadata(self, directory: Path) -> dict[str, Any]:
        _digest, _size, data = self.mods._stable_file(
            directory / STAGE_METADATA,
            collect=True,
            max_bytes=64 * 1024,
        )
        assert data is not None
        try:
            raw = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceError("Asset staging metadata is not valid JSON") from exc
        if not isinstance(raw, dict) or raw.get("schema") != "beamng-mcp-asset-stage-v1":
            raise WorkspaceError("Asset staging metadata has an unsupported schema")
        if raw.get("slot_id") != directory.name:
            raise WorkspaceError("Asset staging metadata does not match its directory")
        return raw

    def _validate_directory_entries(self, directory: Path, expected_names: set[str]) -> None:
        self.mods._assert_no_reparse_components(directory)
        try:
            with os.scandir(directory) as iterator:
                entries = list(iterator)
        except OSError as exc:
            raise WorkspaceError(f"Cannot inspect asset staging slot: {exc}") from exc
        names = {entry.name for entry in entries}
        missing = expected_names - names
        unexpected = names - expected_names
        if missing:
            missing_names = ", ".join(sorted(missing))
            raise NotFoundError(f"Asset export is incomplete; missing: {missing_names}")
        if unexpected:
            raise WorkspaceError(
                f"Asset staging slot contains unexpected files: {', '.join(sorted(unexpected))}"
            )
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            invalid_entry = (
                entry.is_symlink()
                or _is_reparse_stat(metadata)
                or not stat.S_ISREG(metadata.st_mode)
            )
            if invalid_entry:
                raise WorkspaceError(f"Asset staging entry is not a regular file: {entry.name}")

    @staticmethod
    def _parse_expiry(metadata: dict[str, Any]) -> datetime:
        raw = metadata.get("expires_at")
        if not isinstance(raw, str):
            raise WorkspaceError("Asset staging metadata is missing expires_at")
        try:
            expires_at = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise WorkspaceError("Asset staging metadata has an invalid expires_at") from exc
        if expires_at.tzinfo is None:
            raise WorkspaceError("Asset staging expiry must include a timezone")
        return expires_at.astimezone(UTC)

    @staticmethod
    def _metadata_string(metadata: dict[str, Any], key: str) -> str:
        value = metadata.get(key)
        if not isinstance(value, str):
            raise WorkspaceError(f"Asset staging metadata is missing {key}")
        return value

    def _create_regular(self, path: Path, data: bytes) -> None:
        self.mods._assert_no_reparse_components(path)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _replace_regular(self, path: Path, data: bytes) -> None:
        self.mods._assert_no_reparse_components(path)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            self.mods._assert_no_reparse_components(path)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _canonical_json(value: dict[str, Any]) -> bytes:
        return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
