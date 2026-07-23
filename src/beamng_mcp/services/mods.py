"""Path-confined, quota-bounded mod authoring and packaging."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import BinaryIO

from ..config import WorkspaceSettings
from ..errors import ConflictError, NotFoundError, SafetyInterlockError, WorkspaceError
from ..models import ModArtifact, ModFileInfo, ModFileWrite, ModValidation, ValidationIssue

MOD_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
DYNAMIC_LUA_EVAL = re.compile(r"(?<!\bextensions\.)\bload\s*\(|\b(?:loadstring|dostring)\s*\(")
ALLOWED_TOP_LEVEL = frozenset(
    {
        "art",
        "assets",
        "gameplay",
        "levels",
        "lua",
        "mod_info",
        "scripts",
        "settings",
        "trackEditor",
        "ui",
        "vehicleGroups",
        "vehicles",
        "info.json",
        "README.md",
        "LICENSE",
    }
)


def _is_reparse_stat(value: os.stat_result) -> bool:
    """Recognize POSIX symlinks and Windows junction/reparse-point metadata."""

    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = int(getattr(value, "st_file_attributes", 0))
    return stat.S_ISLNK(value.st_mode) or bool(attributes & reparse_flag)


def _absolute_lexical(path: Path) -> Path:
    """Make a path absolute without dereferencing a link component."""

    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _fingerprint(value: os.stat_result) -> tuple[int, int, int, int]:
    modified_ns = int(getattr(value, "st_mtime_ns", value.st_mtime * 1_000_000_000))
    return (value.st_dev, value.st_ino, value.st_size, modified_ns)


def _same_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    """Compare snapshots while tolerating zeroed Windows DirEntry identity fields."""

    left_modified = int(getattr(left, "st_mtime_ns", left.st_mtime * 1_000_000_000))
    right_modified = int(getattr(right, "st_mtime_ns", right.st_mtime * 1_000_000_000))
    if (
        stat.S_IFMT(left.st_mode) != stat.S_IFMT(right.st_mode)
        or left.st_size != right.st_size
        or left_modified != right_modified
    ):
        return False
    left_identity = (left.st_dev, left.st_ino)
    right_identity = (right.st_dev, right.st_ino)
    return not all(left_identity) or not all(right_identity) or left_identity == right_identity


def _has_strict_regular_identity(value: os.stat_result) -> bool:
    return (
        stat.S_ISREG(value.st_mode)
        and not _is_reparse_stat(value)
        and bool(value.st_dev)
        and bool(value.st_ino)
    )


def _same_strict_file_state(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        _has_strict_regular_identity(left)
        and _has_strict_regular_identity(right)
        and (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)
        and _same_file_state(left, right)
    )


class _QuotaExceeded(WorkspaceError):
    def __init__(self, message: str, *, files_checked: int) -> None:
        super().__init__(message)
        self.files_checked = files_checked


class _PrefabJsonError(ValueError):
    """A malformed record in BeamNG's newline-delimited prefab format."""


def _validate_json_text(path: str, text: str) -> None:
    """Validate ordinary JSON or BeamNG's one-object-per-line prefab JSON."""

    if not path.casefold().endswith(".prefab.json"):
        json.loads(text)
        return

    records = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        records += 1
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _PrefabJsonError(
                f"invalid prefab object on line {line_number}: {exc.msg} at column {exc.colno}"
            ) from exc
        if not isinstance(value, dict):
            raise _PrefabJsonError(f"prefab record on line {line_number} must be a JSON object")
    if records == 0:
        raise _PrefabJsonError("prefab JSON must contain at least one object")


class ModWorkspace:
    def __init__(self, settings: WorkspaceSettings) -> None:
        self.settings = settings
        self.root = _absolute_lexical(settings.root)
        assert settings.artifacts is not None
        self.artifacts = _absolute_lexical(settings.artifacts)
        self._lock = RLock()

    def _assert_no_reparse_components(self, path: Path) -> None:
        absolute = _absolute_lexical(path)
        current = Path(absolute.anchor)
        parts = absolute.parts[1:] if absolute.anchor else absolute.parts
        for part in parts:
            current /= part
            try:
                metadata = os.lstat(current)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise WorkspaceError(
                    f"Cannot inspect workspace path component {current}: {exc}"
                ) from exc
            if _is_reparse_stat(metadata):
                raise WorkspaceError(
                    f"Symlink, junction, or reparse component is not allowed: {current}"
                )

    def ensure(self) -> None:
        with self._lock:
            self._assert_no_reparse_components(self.root)
            self._assert_no_reparse_components(self.artifacts)
            self.root.mkdir(parents=True, exist_ok=True)
            self.artifacts.mkdir(parents=True, exist_ok=True)
            self._assert_no_reparse_components(self.root)
            self._assert_no_reparse_components(self.artifacts)

    def _mod_root(self, mod_name: str, *, must_exist: bool = True) -> Path:
        if not MOD_NAME.fullmatch(mod_name):
            raise WorkspaceError("mod_name must start with a lowercase letter and use [a-z0-9_-]")
        expected_parent = self.root / "mods"
        lexical_root = expected_parent / mod_name
        self._assert_no_reparse_components(lexical_root)
        resolved_parent = expected_parent.resolve(strict=False)
        root = lexical_root.resolve(strict=False)
        self._assert_no_reparse_components(lexical_root)
        if not root.is_relative_to(resolved_parent):
            raise WorkspaceError("Resolved mod path escaped the workspace")
        if must_exist:
            try:
                metadata = os.lstat(root)
            except FileNotFoundError as exc:
                raise NotFoundError(f"Mod {mod_name!r} does not exist") from exc
            if _is_reparse_stat(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise NotFoundError(f"Mod {mod_name!r} does not exist")
        return root

    def _file(self, mod_name: str, relative: str, *, must_exist: bool = False) -> Path:
        if not relative or "\x00" in relative:
            raise WorkspaceError("A non-empty relative file path is required")
        relative_path = Path(relative.replace("\\", "/"))
        if (
            relative_path.is_absolute()
            or not relative_path.parts
            or ".." in relative_path.parts
            or any(":" in part for part in relative_path.parts)
        ):
            raise WorkspaceError(
                "Absolute paths, alternate streams, and '..' traversal are not allowed"
            )
        root = self._mod_root(mod_name)
        lexical_target = root / relative_path
        self._assert_no_reparse_components(lexical_target)
        target = lexical_target.resolve(strict=False)
        self._assert_no_reparse_components(lexical_target)
        if not target.is_relative_to(root):
            raise WorkspaceError("Resolved file path escaped the mod root")
        if relative_path.parts[0] not in ALLOWED_TOP_LEVEL:
            raise WorkspaceError(
                f"Top-level path {relative_path.parts[0]!r} is not a BeamNG mod root"
            )
        if must_exist:
            try:
                metadata = os.lstat(target)
            except FileNotFoundError as exc:
                raise NotFoundError(
                    f"File {relative!r} does not exist in mod {mod_name!r}"
                ) from exc
            if _is_reparse_stat(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise NotFoundError(f"File {relative!r} does not exist in mod {mod_name!r}")
        return target

    def _stable_file(
        self,
        path: Path,
        *,
        initial: os.stat_result | None = None,
        collect: bool = False,
        max_bytes: int,
    ) -> tuple[str, int, bytes | None]:
        """Read one regular file while detecting link swaps and in-place changes."""

        self._assert_no_reparse_components(path)
        try:
            before = os.lstat(path)
            if _is_reparse_stat(before) or not stat.S_ISREG(before.st_mode):
                raise WorkspaceError(f"Only regular files are allowed in mod workspaces: {path}")
            if initial is not None and not _same_file_state(initial, before):
                raise WorkspaceError(f"File changed while it was being processed: {path}")

            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            try:
                opened = os.fstat(descriptor)
                if _is_reparse_stat(opened) or not stat.S_ISREG(opened.st_mode):
                    raise WorkspaceError(
                        f"Only regular files are allowed in mod workspaces: {path}"
                    )
                if not _same_file_state(before, opened):
                    raise WorkspaceError(f"File changed while it was being processed: {path}")

                digest = hashlib.sha256()
                chunks: list[bytes] | None = [] if collect else None
                size = 0
                while True:
                    chunk = os.read(descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise WorkspaceError(
                            f"File exceeds the configured {max_bytes} byte processing limit: {path}"
                        )
                    digest.update(chunk)
                    if chunks is not None:
                        chunks.append(chunk)
                after_open = os.fstat(descriptor)
            finally:
                os.close(descriptor)

            self._assert_no_reparse_components(path)
            after = os.lstat(path)
        except WorkspaceError:
            raise
        except OSError as exc:
            raise WorkspaceError(f"Cannot safely read mod file {path}: {exc}") from exc

        fingerprints = {
            _fingerprint(before),
            _fingerprint(opened),
            _fingerprint(after_open),
            _fingerprint(after),
        }
        if len(fingerprints) != 1 or _is_reparse_stat(after):
            raise WorkspaceError(f"File changed while it was being processed: {path}")
        data = b"".join(chunks) if chunks is not None else None
        return digest.hexdigest(), size, data

    def _scan_files(self, mod_name: str) -> list[ModFileInfo]:
        root = self._mod_root(mod_name)
        pending = [root]
        result: list[ModFileInfo] = []
        total_bytes = 0

        while pending:
            directory = pending.pop()
            self._assert_no_reparse_components(directory)
            try:
                before = os.lstat(directory)
                if _is_reparse_stat(before) or not stat.S_ISDIR(before.st_mode):
                    raise WorkspaceError(f"Only regular directories are allowed: {directory}")
                with os.scandir(directory) as iterator:
                    entries = sorted(iterator, key=lambda entry: entry.name)
            except WorkspaceError:
                raise
            except OSError as exc:
                raise WorkspaceError(f"Cannot scan mod directory {directory}: {exc}") from exc

            child_directories: list[Path] = []
            for entry in entries:
                path = directory / entry.name
                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise WorkspaceError(f"Cannot inspect mod path {path}: {exc}") from exc
                if entry.is_symlink() or _is_reparse_stat(metadata):
                    raise WorkspaceError(
                        "Symlink, junction, or reparse entry is not allowed: "
                        f"{path.relative_to(root)}"
                    )
                if stat.S_ISDIR(metadata.st_mode):
                    child_directories.append(path)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise WorkspaceError(
                        f"Only regular files and directories are allowed: {path.relative_to(root)}"
                    )

                files_seen = len(result) + 1
                if files_seen > self.settings.max_mod_files:
                    raise _QuotaExceeded(
                        "Mod file-count quota exceeded "
                        f"({files_seen} > {self.settings.max_mod_files})",
                        files_checked=files_seen,
                    )
                if total_bytes + metadata.st_size > self.settings.max_mod_bytes:
                    raise _QuotaExceeded(
                        "Mod total-byte quota exceeded "
                        f"({total_bytes + metadata.st_size} > {self.settings.max_mod_bytes})",
                        files_checked=files_seen,
                    )
                digest, size, _ = self._stable_file(
                    path,
                    initial=metadata,
                    max_bytes=self.settings.max_mod_bytes,
                )
                if total_bytes + size > self.settings.max_mod_bytes:
                    raise _QuotaExceeded(
                        "Mod total-byte quota exceeded "
                        f"({total_bytes + size} > {self.settings.max_mod_bytes})",
                        files_checked=files_seen,
                    )
                total_bytes += size
                result.append(
                    ModFileInfo(path=path.relative_to(root).as_posix(), size=size, sha256=digest)
                )

            try:
                after = os.lstat(directory)
            except OSError as exc:
                raise WorkspaceError(
                    f"Mod directory changed while being scanned: {directory}"
                ) from exc
            if _fingerprint(before) != _fingerprint(after) or _is_reparse_stat(after):
                raise WorkspaceError(f"Mod directory changed while being scanned: {directory}")
            pending.extend(reversed(child_directories))

        result.sort(key=lambda info: info.path)
        return result

    def _read_stable_bytes(self, root: Path, info: ModFileInfo) -> bytes:
        target = self._file(root.name, info.path, must_exist=True)
        digest, size, data = self._stable_file(
            target,
            collect=True,
            max_bytes=self.settings.max_file_bytes,
        )
        if digest != info.sha256 or size != info.size:
            raise WorkspaceError(f"File changed while it was being processed: {info.path}")
        assert data is not None
        return data

    def _check_projected_quota(self, *, files: int, total_bytes: int) -> None:
        if files > self.settings.max_mod_files:
            raise WorkspaceError(
                f"Mod file-count quota exceeded ({files} > {self.settings.max_mod_files})"
            )
        if total_bytes > self.settings.max_mod_bytes:
            raise WorkspaceError(
                f"Mod total-byte quota exceeded ({total_bytes} > {self.settings.max_mod_bytes})"
            )

    def scaffold(
        self,
        mod_name: str,
        *,
        title: str,
        author: str,
        kind: str = "lua",
    ) -> list[ModFileInfo]:
        with self._lock:
            directories = {
                "lua": ["lua/ge/extensions"],
                "vehicle": ["vehicles"],
                "level": ["levels"],
                "mixed": ["lua/ge/extensions", "vehicles", "levels"],
            }
            if kind not in directories:
                raise WorkspaceError("kind must be one of: lua, vehicle, level, mixed")

            info = {
                "name": title,
                "author": author,
                "version": "0.1.0",
                "description": f"Created with BeamNG MCP ({kind} mod)",
            }
            info_bytes = (json.dumps(info, indent=2) + "\n").encode()
            readme_bytes = (f"# {title}\n\nBeamNG {kind} mod scaffolded by BeamNG MCP.\n").encode()
            for content in (info_bytes, readme_bytes):
                if len(content) > self.settings.max_file_bytes:
                    raise WorkspaceError(
                        f"Scaffold file is {len(content)} bytes; "
                        f"limit is {self.settings.max_file_bytes}"
                    )
            self._check_projected_quota(files=2, total_bytes=len(info_bytes) + len(readme_bytes))

            self.ensure()
            root = self._mod_root(mod_name, must_exist=False)
            self._assert_no_reparse_components(root)
            if root.exists():
                if not root.is_dir() or any(root.iterdir()):
                    raise ConflictError(f"Mod {mod_name!r} already exists and is not empty")
            root.mkdir(parents=True, exist_ok=True)
            self._assert_no_reparse_components(root)
            for directory in directories[kind]:
                target_directory = root / directory
                self._assert_no_reparse_components(target_directory)
                target_directory.mkdir(parents=True, exist_ok=True)
            info_dir = root / "mod_info" / mod_name
            self._assert_no_reparse_components(info_dir)
            info_dir.mkdir(parents=True, exist_ok=True)
            (info_dir / "info.json").write_bytes(info_bytes)
            (root / "README.md").write_bytes(readme_bytes)
            return self.list_files(mod_name)

    def exists(self, mod_name: str) -> bool:
        """Return whether a regular, confined mod workspace already exists."""

        with self._lock:
            try:
                self._mod_root(mod_name)
            except NotFoundError:
                return False
            return True

    def write_bundle(
        self,
        mod_name: str,
        contents: dict[str, bytes],
        *,
        overwrite: bool = False,
        expected_sha256: dict[str, str] | None = None,
    ) -> list[ModFileInfo]:
        """Atomically stage and transactionally replace a bounded binary/text file bundle.

        The filesystem cannot make several paths globally atomic. This method stages every
        byte first, verifies all optimistic preconditions, then uses same-directory replaces
        with recovery copies so a failed commit restores the previous bundle.
        """

        with self._lock:
            if not contents:
                raise WorkspaceError("A mod bundle must contain at least one file")

            root = self._mod_root(mod_name)
            files = self.list_files(mod_name)
            by_path = {info.path: info for info in files}
            normalized: dict[str, tuple[Path, bytes]] = {}
            for supplied_path, data in contents.items():
                if not isinstance(data, bytes):
                    raise WorkspaceError("Bundle contents must be bytes")
                if len(data) > self.settings.max_file_bytes:
                    raise WorkspaceError(
                        f"File {supplied_path!r} is {len(data)} bytes; "
                        f"limit is {self.settings.max_file_bytes}"
                    )
                target = self._file(mod_name, supplied_path)
                relative = target.relative_to(root).as_posix()
                if relative in normalized:
                    raise WorkspaceError(f"Duplicate normalized bundle path: {relative}")
                normalized[relative] = (target, data)

            existing = {path: by_path[path] for path in normalized if path in by_path}
            expected_normalized: dict[str, str] = {}
            for supplied_path, digest in (expected_sha256 or {}).items():
                if not re.fullmatch(r"[a-f0-9]{64}", digest):
                    raise WorkspaceError("Bundle expected hashes must be lowercase SHA-256")
                expected_target = self._file(mod_name, supplied_path)
                expected_relative = expected_target.relative_to(root).as_posix()
                if expected_relative in expected_normalized:
                    raise WorkspaceError(
                        f"Duplicate normalized expected-hash path: {expected_relative}"
                    )
                if expected_relative not in normalized:
                    raise WorkspaceError(
                        f"Expected-hash path is not part of this bundle: {expected_relative}"
                    )
                expected_normalized[expected_relative] = digest
            if existing and not overwrite:
                conflicts = ", ".join(sorted(existing))
                raise ConflictError(
                    f"Generated bundle would replace existing files: {conflicts}; "
                    "set overwrite=true after reviewing their hashes"
                )
            if expected_normalized and not overwrite:
                raise WorkspaceError("Bundle expected hashes require overwrite=true")
            if overwrite and set(expected_normalized) != set(existing):
                missing = sorted(set(existing) - set(expected_normalized))
                unexpected = sorted(set(expected_normalized) - set(existing))
                details: list[str] = []
                if missing:
                    details.append(f"missing expected hashes for: {', '.join(missing)}")
                if unexpected:
                    details.append(f"expected paths do not exist: {', '.join(unexpected)}")
                raise ConflictError(
                    "Bundle overwrite authorization mismatch (" + "; ".join(details) + ")"
                )
            for relative, previous in existing.items():
                if expected_normalized.get(relative) != previous.sha256:
                    raise ConflictError(f"Bundle expected hash mismatch for {relative}")

            projected_files = len(files) + sum(path not in by_path for path in normalized)
            projected_bytes = sum(info.size for info in files)
            projected_bytes -= sum(info.size for info in existing.values())
            projected_bytes += sum(len(data) for _target, data in normalized.values())
            self._check_projected_quota(files=projected_files, total_bytes=projected_bytes)

            staged: dict[str, Path] = {}
            backups: dict[str, Path] = {}
            committed: set[str] = set()
            commit_succeeded = False
            try:
                for relative, (target, data) in sorted(normalized.items()):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    self._assert_no_reparse_components(target)
                    descriptor, temporary_name = tempfile.mkstemp(
                        prefix=f".{target.name}.", suffix=".bundle.tmp", dir=target.parent
                    )
                    temporary = Path(temporary_name)
                    staged[relative] = temporary
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(data)
                        handle.flush()
                        os.fsync(handle.fileno())

                for relative, (target, _data) in sorted(normalized.items()):
                    prior_file = existing.get(relative)
                    if prior_file is not None:
                        current_digest, current_size, _ = self._stable_file(
                            target,
                            max_bytes=self.settings.max_file_bytes,
                        )
                        if (current_digest, current_size) != (
                            prior_file.sha256,
                            prior_file.size,
                        ):
                            raise ConflictError(
                                f"File changed while the bundle was staged: {relative}"
                            )
                        backup = target.with_name(
                            f".{target.name}.{secrets.token_hex(8)}.bundle.backup"
                        )
                        self._assert_no_reparse_components(backup)
                        if os.path.lexists(backup):
                            raise ConflictError(f"Recovery path unexpectedly exists for {relative}")
                        target.replace(backup)
                        backups[relative] = backup
                    elif os.path.lexists(target):
                        raise ConflictError(
                            f"Bundle target appeared while the bundle was staged: {relative}"
                        )

                    self._assert_no_reparse_components(staged[relative])
                    self._assert_no_reparse_components(target)
                    staged[relative].replace(target)
                    committed.add(relative)

                final_files = self.list_files(mod_name)
                final_by_path = {info.path: info for info in final_files}
                for relative, (_target, data) in normalized.items():
                    result = final_by_path.get(relative)
                    expected = hashlib.sha256(data).hexdigest()
                    if result is None or result.size != len(data) or result.sha256 != expected:
                        raise WorkspaceError(
                            f"Committed bundle file did not match staged bytes: {relative}"
                        )
                commit_succeeded = True
            except Exception as commit_error:
                rollback_errors: list[str] = []
                for relative, (target, _data) in reversed(list(sorted(normalized.items()))):
                    recovery = backups.get(relative)
                    try:
                        if relative in committed and os.path.lexists(target):
                            self._assert_no_reparse_components(target)
                            target.unlink()
                        if recovery is not None and os.path.lexists(recovery):
                            self._assert_no_reparse_components(recovery)
                            self._assert_no_reparse_components(target)
                            recovery.replace(target)
                    except OSError as rollback_error:
                        rollback_errors.append(f"{relative}: {rollback_error}")
                if rollback_errors:
                    rollback_details = "; ".join(rollback_errors)
                    raise WorkspaceError(
                        f"Bundle commit failed and rollback was incomplete ({rollback_details})"
                    ) from commit_error
                raise
            finally:
                for temporary in staged.values():
                    temporary.unlink(missing_ok=True)
                if commit_succeeded:
                    for backup in backups.values():
                        backup.unlink(missing_ok=True)

            final_by_path = {info.path: info for info in self.list_files(mod_name)}
            return [final_by_path[path] for path in sorted(normalized)]

    def write_file(self, request: ModFileWrite) -> ModFileInfo:
        with self._lock:
            encoded = request.content.encode("utf-8")
            if len(encoded) > self.settings.max_file_bytes:
                raise WorkspaceError(
                    f"File is {len(encoded)} bytes; limit is {self.settings.max_file_bytes}"
                )
            target = self._file(request.mod_name, request.path)
            root = self._mod_root(request.mod_name)
            relative = target.relative_to(root).as_posix()
            files = self.list_files(request.mod_name)
            by_path = {info.path: info for info in files}
            existing = by_path.get(relative)

            try:
                target_metadata = os.lstat(target)
            except FileNotFoundError:
                target_metadata = None
            if target_metadata is not None and (
                _is_reparse_stat(target_metadata) or not stat.S_ISREG(target_metadata.st_mode)
            ):
                raise WorkspaceError(f"Target exists but is not a regular file: {relative}")
            if existing is not None and request.expected_sha256 is not None:
                if existing.sha256 != request.expected_sha256:
                    raise ConflictError(
                        "File changed since it was read "
                        f"(expected {request.expected_sha256}, got {existing.sha256})"
                    )
            elif existing is None and request.expected_sha256 is not None:
                raise ConflictError(
                    "expected_sha256 was supplied but the target file does not exist"
                )

            projected_files = len(files) + (0 if existing is not None else 1)
            projected_bytes = (
                sum(info.size for info in files)
                - (existing.size if existing is not None else 0)
                + len(encoded)
            )
            self._check_projected_quota(files=projected_files, total_bytes=projected_bytes)

            target.parent.mkdir(parents=True, exist_ok=True)
            self._assert_no_reparse_components(target)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.", dir=target.parent
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                if existing is not None and request.expected_sha256 is not None:
                    current_digest, _, _ = self._stable_file(
                        target,
                        max_bytes=self.settings.max_file_bytes,
                    )
                    if current_digest != request.expected_sha256:
                        raise ConflictError("File changed since it was read")
                self._assert_no_reparse_components(target)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)

            final_files = self.list_files(request.mod_name)
            final_info = next((info for info in final_files if info.path == relative), None)
            if final_info is None:
                raise WorkspaceError(f"Atomic write did not produce expected file: {relative}")
            return final_info

    def read_file(self, mod_name: str, path: str) -> tuple[str, ModFileInfo]:
        with self._lock:
            target = self._file(mod_name, path, must_exist=True)
            digest, size, data = self._stable_file(
                target,
                collect=True,
                max_bytes=self.settings.max_file_bytes,
            )
            assert data is not None
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise WorkspaceError("Only UTF-8 text files can be read through MCP") from exc
            info = ModFileInfo(
                path=target.relative_to(self._mod_root(mod_name)).as_posix(),
                size=size,
                sha256=digest,
            )
            return content, info

    def list_files(self, mod_name: str) -> list[ModFileInfo]:
        with self._lock:
            return self._scan_files(mod_name)

    def validate(self, mod_name: str) -> ModValidation:
        with self._lock:
            root = self._mod_root(mod_name)
            issues: list[ValidationIssue] = []
            try:
                files = self.list_files(mod_name)
            except _QuotaExceeded as exc:
                return ModValidation(
                    valid=False,
                    mod_name=mod_name,
                    files_checked=exc.files_checked,
                    issues=[ValidationIssue(severity="error", message=str(exc))],
                )

            # Repository upload archives intentionally omit mod_info. BeamNG's
            # Repository service injects that account/resource metadata after
            # upload, so its absence is not a validation issue for a runtime mod.
            for file in files:
                top = Path(file.path).parts[0]
                if top not in ALLOWED_TOP_LEVEL:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            path=file.path,
                            message=f"Invalid top-level directory {top!r}",
                        )
                    )
                if file.size > self.settings.max_file_bytes:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            path=file.path,
                            message=f"File exceeds {self.settings.max_file_bytes} byte limit",
                        )
                    )
                    continue

                suffix = Path(file.path).suffix.lower()
                if suffix == ".json" and not file.path.lower().endswith(".jbeam"):
                    try:
                        text = self._read_stable_bytes(root, file).decode("utf-8")
                        _validate_json_text(file.path, text)
                    except (UnicodeDecodeError, json.JSONDecodeError, _PrefabJsonError) as exc:
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                path=file.path,
                                message=f"Invalid JSON: {exc}",
                            )
                        )
                if suffix == ".lua":
                    text = self._read_stable_bytes(root, file).decode("utf-8", errors="replace")
                    if DYNAMIC_LUA_EVAL.search(text):
                        issues.append(
                            ValidationIssue(
                                severity="warning",
                                path=file.path,
                                message="Dynamic Lua evaluation found; review before installing",
                            )
                        )
            return ModValidation(
                valid=not any(issue.severity == "error" for issue in issues),
                mod_name=mod_name,
                files_checked=len(files),
                issues=issues,
            )

    def pack(self, mod_name: str) -> ModArtifact:
        with self._lock:
            validation = self.validate(mod_name)
            if not validation.valid:
                raise WorkspaceError("Cannot pack a mod with validation errors")
            root = self._mod_root(mod_name)
            files = self.list_files(mod_name)
            self.ensure()
            destination = self.artifacts / f"{mod_name}.zip"
            self._assert_no_reparse_components(destination)

            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{mod_name}.", suffix=".zip.tmp", dir=self.artifacts
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w+b") as handle:
                    with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                        for info in files:
                            archive.writestr(info.path, self._read_stable_bytes(root, info))
                    handle.flush()
                    os.fsync(handle.fileno())

                final_files = self.list_files(mod_name)
                initial_signature = [(item.path, item.size, item.sha256) for item in files]
                final_signature = [(item.path, item.size, item.sha256) for item in final_files]
                if final_signature != initial_signature:
                    raise WorkspaceError(
                        "Mod changed while it was being packed; retry the operation"
                    )
                self._assert_no_reparse_components(temporary)
                self._assert_no_reparse_components(destination)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)

            digest, size, _ = self._stable_file(
                destination,
                max_bytes=self.settings.max_mod_bytes + self.settings.max_mod_files * 1024,
            )
            return ModArtifact(
                mod_name=mod_name,
                path=str(destination),
                sha256=digest,
                size=size,
            )

    def _restore_quarantined_regular_file(
        self,
        quarantine: Path,
        destination: Path,
        expected: os.stat_result,
    ) -> bool:
        """Best-effort no-clobber restoration of a raced-in regular file."""

        if not _has_strict_regular_identity(expected):
            return False
        try:
            self._assert_no_reparse_components(quarantine.parent)
            current = os.lstat(quarantine)
            if not _same_strict_file_state(expected, current):
                return False
            self._assert_no_reparse_components(destination)
            os.link(quarantine, destination, follow_symlinks=False)
            self._assert_no_reparse_components(destination)
            restored = os.lstat(destination)
            current = os.lstat(quarantine)
            if not _same_strict_file_state(expected, restored) or not _same_strict_file_state(
                expected, current
            ):
                return False
            quarantine.unlink()
        except (OSError, WorkspaceError):
            return False
        return True

    def _quarantine_owned_destination(
        self,
        destination: Path,
        expected: os.stat_result,
        *,
        operation: str,
    ) -> Path:
        """Move an owned destination aside without losing a raced-in replacement."""

        quarantine = destination.with_name(
            f".{destination.name}.{secrets.token_hex(16)}.rollback.tmp"
        )
        if not quarantine.is_relative_to(destination.parent):
            raise SafetyInterlockError(f"{operation}; rollback quarantine escaped the repository")
        self._assert_no_reparse_components(quarantine)
        if os.path.lexists(quarantine):
            raise SafetyInterlockError(f"{operation}; rollback quarantine already exists")

        try:
            self._assert_no_reparse_components(destination)
            current = os.lstat(destination)
        except (OSError, WorkspaceError) as exc:
            raise SafetyInterlockError(
                f"{operation}; destination identity could not be confirmed, refusing to remove "
                f"or replace {destination}: {exc}"
            ) from exc
        if not _same_strict_file_state(expected, current):
            raise SafetyInterlockError(
                f"{operation}; destination identity changed, refusing to remove or replace "
                f"{destination}"
            )

        try:
            destination.replace(quarantine)
            self._assert_no_reparse_components(quarantine.parent)
            quarantined_state = os.lstat(quarantine)
        except OSError as exc:
            raise SafetyInterlockError(
                f"{operation}; could not quarantine the installed file safely: {exc}"
            ) from exc

        if _same_strict_file_state(expected, quarantined_state):
            return quarantine

        restored = self._restore_quarantined_regular_file(
            quarantine,
            destination,
            quarantined_state,
        )
        preserved_at = destination if restored else quarantine
        raise SafetyInterlockError(
            f"{operation}; destination identity changed during quarantine, so the concurrent "
            f"replacement was preserved at {preserved_at}"
        )

    def _remove_owned_private_file(
        self,
        path: Path,
        expected: os.stat_result,
        *,
        operation: str,
        label: str,
    ) -> None:
        try:
            self._assert_no_reparse_components(path)
            current = os.lstat(path)
        except (OSError, WorkspaceError) as exc:
            raise SafetyInterlockError(
                f"{operation}; {label} could not be confirmed at {path}: {exc}"
            ) from exc
        if not _same_strict_file_state(expected, current):
            raise SafetyInterlockError(
                f"{operation}; {label} identity changed and was preserved at {path}"
            )
        try:
            path.unlink()
        except OSError as exc:
            raise SafetyInterlockError(f"{operation}; {label} remains at {path}: {exc}") from exc

    def _restore_backup_without_clobber(
        self,
        destination: Path,
        backup: Path,
        installed_state: os.stat_result,
    ) -> None:
        operation = "Installed mod verification failed"
        try:
            self._assert_no_reparse_components(backup)
            backup_state = os.lstat(backup)
        except (OSError, WorkspaceError) as exc:
            raise SafetyInterlockError(
                f"{operation}; recovery backup could not be confirmed at {backup}: {exc}"
            ) from exc
        if not _has_strict_regular_identity(backup_state):
            raise SafetyInterlockError(
                f"{operation}; recovery backup has no stable regular-file identity at {backup}"
            )

        quarantine = self._quarantine_owned_destination(
            destination,
            installed_state,
            operation=operation,
        )
        try:
            self._assert_no_reparse_components(destination)
            os.link(backup, destination, follow_symlinks=False)
            self._assert_no_reparse_components(destination)
            restored_state = os.lstat(destination)
        except (OSError, WorkspaceError) as exc:
            raise SafetyInterlockError(
                f"{operation}; automatic no-clobber restore failed. Recovery backup remains at "
                f"{backup} and the unverified install remains at {quarantine}: {exc}"
            ) from exc
        if not _same_strict_file_state(backup_state, restored_state):
            raise SafetyInterlockError(
                f"{operation}; restored destination identity changed. Recovery backup remains "
                f"at {backup} and the unverified install remains at {quarantine}"
            )

        self._remove_owned_private_file(
            quarantine,
            installed_state,
            operation=operation,
            label="rollback quarantine",
        )
        try:
            self._assert_no_reparse_components(destination)
            restored_state = os.lstat(destination)
        except (OSError, WorkspaceError) as exc:
            raise SafetyInterlockError(
                f"{operation}; restored destination could not be reconfirmed. Recovery backup "
                f"remains at {backup}: {exc}"
            ) from exc
        if not _same_strict_file_state(backup_state, restored_state):
            raise SafetyInterlockError(
                f"{operation}; restored destination identity changed. Recovery backup remains "
                f"at {backup}"
            )
        self._remove_owned_private_file(
            backup,
            backup_state,
            operation=operation,
            label="recovery backup",
        )

    def install(self, mod_name: str, user_path: Path, *, overwrite: bool = False) -> ModArtifact:
        with self._lock:
            if not self.settings.allow_mod_install:
                raise SafetyInterlockError(
                    "Mod installation is disabled; an operator must enable "
                    "workspace.allow_mod_install"
                )
            artifact = self.pack(mod_name)
            source = _absolute_lexical(Path(artifact.path))
            user_path = _absolute_lexical(user_path)
            mods_dir = user_path / "mods"
            destination_dir = mods_dir / "repo"
            destination = destination_dir / source.name

            for child, parent, label in (
                (mods_dir, user_path, "BeamNG mods directory"),
                (destination_dir, mods_dir, "BeamNG mod repository"),
                (destination, destination_dir, "mod destination"),
            ):
                if not child.is_relative_to(parent):
                    raise SafetyInterlockError(f"{label} escaped its lexical parent")

            self._ensure_install_directory(user_path, parents=True)
            self._ensure_install_directory(mods_dir)
            self._ensure_install_directory(destination_dir)
            self._assert_no_reparse_components(source)
            self._assert_no_reparse_components(destination)

            try:
                destination_state = os.lstat(destination)
            except FileNotFoundError:
                destination_state = None
            except OSError as exc:
                raise SafetyInterlockError(
                    f"Cannot safely inspect mod destination {destination}: {exc}"
                ) from exc
            if destination_state is not None and (
                _is_reparse_stat(destination_state) or not stat.S_ISREG(destination_state.st_mode)
            ):
                raise SafetyInterlockError(
                    f"Refusing to replace non-regular mod destination {destination}"
                )
            if destination_state is not None and not overwrite:
                raise SafetyInterlockError(
                    f"{destination} already exists; set overwrite=true to replace it with a backup"
                )

            conflicts = self._conflicting_mod_archives(mods_dir, destination, source)
            if conflicts:
                raise SafetyInterlockError(
                    "BeamNG registers every .zip under mods/ recursively, and these other "
                    "archives ship the same mod namespace, so they would shadow the "
                    "installed runtime files nondeterministically: "
                    + ", ".join(sorted(conflicts))
                    + ". Move backups and stale copies outside the mods directory, then retry."
                )

            maximum_artifact_bytes = (
                self.settings.max_mod_bytes + self.settings.max_mod_files * 1024
            )
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{source.name}.", suffix=".install.tmp", dir=destination_dir
            )
            staged = Path(temporary_name)
            backup: Path | None = None
            backup_temporary: Path | None = None
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    staged_sha256, staged_size = self._copy_stable_file(
                        source,
                        handle,
                        max_bytes=maximum_artifact_bytes,
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
                if staged_sha256 != artifact.sha256 or staged_size != artifact.size:
                    raise WorkspaceError("Packed mod changed before it could be installed")
                self._assert_no_reparse_components(staged)
                verified_sha256, verified_size, _ = self._stable_file(
                    staged,
                    max_bytes=maximum_artifact_bytes,
                )
                if (verified_sha256, verified_size) != (staged_sha256, staged_size):
                    raise WorkspaceError("Staged mod changed before installation")
                staged_state = os.lstat(staged)
                if not _has_strict_regular_identity(staged_state):
                    raise SafetyInterlockError(
                        "Staged mod has no stable regular-file identity; refusing installation"
                    )

                if destination_state is not None:
                    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                    backup = destination.with_suffix(f".zip.backup-{stamp}-{secrets.token_hex(4)}")
                    if not backup.is_relative_to(destination_dir):
                        raise SafetyInterlockError("Mod backup escaped the repository")
                    self._assert_no_reparse_components(backup)
                    backup_descriptor, backup_name = tempfile.mkstemp(
                        prefix=f".{source.name}.", suffix=".backup.tmp", dir=destination_dir
                    )
                    backup_temporary = Path(backup_name)
                    with os.fdopen(backup_descriptor, "wb") as handle:
                        backup_sha256, backup_size = self._copy_stable_file(
                            destination,
                            handle,
                            initial=destination_state,
                            max_bytes=maximum_artifact_bytes,
                        )
                        handle.flush()
                        os.fsync(handle.fileno())
                    self._assert_no_reparse_components(backup_temporary)
                    backup_temporary.replace(backup)
                    backup_temporary = None

                    current_sha256, current_size, _ = self._stable_file(
                        destination,
                        initial=destination_state,
                        max_bytes=maximum_artifact_bytes,
                    )
                    if (current_sha256, current_size) != (backup_sha256, backup_size):
                        raise WorkspaceError(
                            "Installed mod changed while its recovery backup was created"
                        )
                elif os.path.lexists(destination):
                    raise SafetyInterlockError(
                        "Mod destination appeared during installation; retry after inspecting it"
                    )

                self._assert_no_reparse_components(destination_dir)
                self._assert_no_reparse_components(destination)
                staged.replace(destination)

                installed_state: os.stat_result | None = None
                try:
                    self._assert_no_reparse_components(destination)
                    candidate_state = os.lstat(destination)
                    if not _same_strict_file_state(staged_state, candidate_state):
                        raise SafetyInterlockError(
                            "Installed mod destination identity changed before verification"
                        )
                    installed_state = candidate_state
                    installed_sha256, installed_size, _ = self._stable_file(
                        destination,
                        initial=installed_state,
                        max_bytes=maximum_artifact_bytes,
                    )
                    if (installed_sha256, installed_size) != (staged_sha256, staged_size):
                        raise WorkspaceError("Installed mod did not match the staged artifact")
                except Exception as install_error:
                    if backup is not None:
                        if installed_state is None:
                            raise SafetyInterlockError(
                                "Installed mod verification failed before destination ownership "
                                f"could be established; recovery backup remains at {backup}"
                            ) from install_error
                        self._restore_backup_without_clobber(
                            destination,
                            backup,
                            installed_state,
                        )
                        backup = None
                        raise WorkspaceError(
                            "Installed mod verification failed; the previous file was restored "
                            "and its recovery backup was consumed"
                        ) from install_error
                    if installed_state is None:
                        raise SafetyInterlockError(
                            "New mod installation could not be verified because destination "
                            "ownership could not be established; refusing to remove it"
                        ) from install_error
                    operation = "New mod installation verification failed"
                    quarantine = self._quarantine_owned_destination(
                        destination,
                        installed_state,
                        operation=operation,
                    )
                    self._remove_owned_private_file(
                        quarantine,
                        installed_state,
                        operation=operation,
                        label="rollback quarantine",
                    )
                    raise WorkspaceError(
                        "New mod installation could not be verified after its atomic replacement; "
                        "the unverified file was removed"
                    ) from install_error
            except (SafetyInterlockError, WorkspaceError):
                raise
            except OSError as exc:
                raise WorkspaceError(f"Cannot safely install mod at {destination}: {exc}") from exc
            finally:
                staged.unlink(missing_ok=True)
                if backup_temporary is not None:
                    backup_temporary.unlink(missing_ok=True)

            return ModArtifact(
                mod_name=mod_name,
                path=str(destination),
                sha256=installed_sha256,
                size=installed_size,
            )

    @staticmethod
    def _mod_identity_prefixes(archive: Path) -> set[str]:
        """Return the vehicle and GE-extension namespaces an archive ships."""

        prefixes: set[str] = set()
        try:
            with zipfile.ZipFile(archive) as bundle:
                for name in bundle.namelist():
                    parts = PurePosixPath(name.replace("\\", "/")).parts
                    if len(parts) >= 2 and parts[0] == "vehicles":
                        prefixes.add(f"vehicles/{parts[1]}")
                    elif len(parts) >= 4 and parts[:3] == ("lua", "ge", "extensions"):
                        prefixes.add(f"lua/ge/extensions/{parts[3]}")
        except (OSError, zipfile.BadZipFile):
            return set()
        return prefixes

    def _conflicting_mod_archives(
        self,
        mods_dir: Path,
        destination: Path,
        source: Path,
    ) -> list[str]:
        """Find other mounted archives shipping this mod's namespaces.

        BeamNG registers every ``*.zip`` under ``mods/`` recursively, so a
        stray backup or stale copy of the same mod shadows freshly installed
        runtime files nondeterministically. A real-profile backup zip parked
        under ``mods/`` silently reverted Cannon Car Wash runtime behaviour;
        installs now fail closed until such duplicates are moved out.
        """

        identity = self._mod_identity_prefixes(source)
        if not identity:
            return []
        conflicts: list[str] = []
        try:
            candidates = [candidate for candidate in mods_dir.rglob("*.zip") if candidate.is_file()]
        except OSError:
            return []
        for candidate in candidates:
            resolved = _absolute_lexical(candidate)
            if resolved == destination:
                continue
            if identity & self._mod_identity_prefixes(resolved):
                conflicts.append(str(resolved))
        return conflicts

    def _ensure_install_directory(self, path: Path, *, parents: bool = False) -> None:
        """Create one lexical install directory and reject links or special files."""

        self._assert_no_reparse_components(path)
        try:
            path.mkdir(parents=parents, exist_ok=True)
            self._assert_no_reparse_components(path)
            metadata = os.lstat(path)
        except WorkspaceError:
            raise
        except OSError as exc:
            raise SafetyInterlockError(
                f"Cannot safely create or inspect install directory {path}: {exc}"
            ) from exc
        if _is_reparse_stat(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise SafetyInterlockError(f"Install path is not a regular directory: {path}")

    def _copy_stable_file(
        self,
        source: Path,
        destination: BinaryIO,
        *,
        max_bytes: int,
        initial: os.stat_result | None = None,
    ) -> tuple[str, int]:
        """Stream a stable regular source into an already-open staging file."""

        self._assert_no_reparse_components(source)
        try:
            before = os.lstat(source)
            if _is_reparse_stat(before) or not stat.S_ISREG(before.st_mode):
                raise WorkspaceError(f"Only regular mod artifacts may be installed: {source}")
            if initial is not None and not _same_file_state(initial, before):
                raise WorkspaceError(f"Mod artifact changed while being copied: {source}")
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(source, flags)
            try:
                opened = os.fstat(descriptor)
                if _is_reparse_stat(opened) or not stat.S_ISREG(opened.st_mode):
                    raise WorkspaceError(f"Only regular mod artifacts may be installed: {source}")
                if not _same_file_state(before, opened):
                    raise WorkspaceError(f"Mod artifact changed while being copied: {source}")
                digest = hashlib.sha256()
                size = 0
                while True:
                    chunk = os.read(descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise WorkspaceError(
                            f"Mod artifact exceeds the configured {max_bytes} byte limit"
                        )
                    digest.update(chunk)
                    destination.write(chunk)
                after_open = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            self._assert_no_reparse_components(source)
            after = os.lstat(source)
        except WorkspaceError:
            raise
        except OSError as exc:
            raise WorkspaceError(f"Cannot safely copy mod artifact {source}: {exc}") from exc

        if len(
            {
                _fingerprint(before),
                _fingerprint(opened),
                _fingerprint(after_open),
                _fingerprint(after),
            }
        ) != 1 or _is_reparse_stat(after):
            raise WorkspaceError(f"Mod artifact changed while being copied: {source}")
        return digest.hexdigest(), size
