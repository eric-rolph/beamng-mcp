"""Safety primitives shared by opt-in tests that launch local BeamNG."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import socket
import stat
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from beamng_mcp.installer import BRIDGE_CONFIG, MOD_DIRECTORY, MOD_MARKER

_DEFAULT_SERVICE_PORTS = frozenset({8765, 25252})
_HELD_PROFILE_LOCKS: set[Path] = set()
_PROFILE_LOCK_GUARD = threading.Lock()
_LOG_CURSOR_ANCHOR_BYTES = 64


@dataclass(frozen=True, slots=True)
class BeamNGLogRead:
    """One incremental read from a :class:`BeamNGLogCursor`."""

    lines: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    issues: tuple[str, ...]
    restarted: bool
    start_offset: int
    end_offset: int

    @property
    def events(self) -> tuple[str, ...]:
        """Return string event names from the structured records."""

        return tuple(
            event for record in self.records if isinstance((event := record.get("event")), str)
        )


class BeamNGLogCursor:
    """Incrementally inspect one BeamNG log without repeatedly rereading it.

    BeamNG commonly replaces or truncates ``beamng.log`` during a process
    restart. The cursor detects file identity, size, and content-anchor changes
    before reading so a fast truncate-and-regrow cannot leave its byte offset in
    the middle of an unrelated run. An incomplete final line is retained until
    its newline arrives, which also makes split UTF-8 writes safe.
    """

    def __init__(
        self,
        path: Path,
        *,
        namespaces: Iterable[str] = (),
        json_tag: str | None = None,
        schema_version: int | None = None,
        start_at_end: bool = False,
    ) -> None:
        self.path = path
        self.namespaces = tuple(namespace.casefold() for namespace in namespaces if namespace)
        self.json_tag = json_tag.casefold() if json_tag else None
        self.schema_version = schema_version
        self._offset = 0
        self._pending = b""
        self._identity: tuple[int, int] | None = None
        self._anchor = b""
        self._seen_file = False
        self._missing_after_seen = False
        self._discard_until_newline = False
        if start_at_end:
            self.seek_end()

    @property
    def offset(self) -> int:
        """Current byte offset in the physical log file."""

        return self._offset

    def seek_end(self) -> None:
        """Ignore existing content and begin observing future complete lines."""

        try:
            with self.path.open("rb") as handle:
                stat_result = os.fstat(handle.fileno())
                self._identity = (stat_result.st_dev, stat_result.st_ino)
                self._offset = stat_result.st_size
                self._anchor = self._read_anchor(handle, self._offset)
                self._discard_until_newline = bool(self._offset and self._anchor[-1:] != b"\n")
        except FileNotFoundError:
            self._identity = None
            self._offset = 0
            self._anchor = b""
            self._discard_until_newline = False
        self._pending = b""
        self._seen_file = self._identity is not None
        self._missing_after_seen = False

    def read(self) -> BeamNGLogRead:
        """Return complete lines, JSON records, and relevant new warnings/errors."""

        try:
            handle = self.path.open("rb")
        except FileNotFoundError:
            if self._seen_file:
                self._missing_after_seen = True
            return BeamNGLogRead((), (), (), False, self._offset, self._offset)

        with handle:
            stat_result = os.fstat(handle.fileno())
            identity = (stat_result.st_dev, stat_result.st_ino)
            restarted = self._did_restart(handle, identity, stat_result.st_size)
            if restarted:
                self._offset = 0
                self._pending = b""
                self._anchor = b""
                self._discard_until_newline = False

            start_offset = self._offset
            handle.seek(start_offset)
            payload = handle.read()
            self._offset += len(payload)
            self._anchor = self._read_anchor(handle, self._offset)
            self._identity = identity
            self._seen_file = True
            self._missing_after_seen = False

        buffered = self._pending + payload
        if self._discard_until_newline:
            _, separator, buffered = buffered.partition(b"\n")
            if not separator:
                return BeamNGLogRead((), (), (), restarted, start_offset, self._offset)
            self._discard_until_newline = False

        complete, separator, pending = buffered.rpartition(b"\n")
        if not separator:
            self._pending += payload
            lines: tuple[str, ...] = ()
        else:
            self._pending = pending
            lines = tuple(
                line.rstrip("\r") for line in complete.decode("utf-8", errors="replace").split("\n")
            )

        records = tuple(
            record for line in lines if (record := self._structured_record(line)) is not None
        )
        issues = tuple(line for line in lines if self._is_relevant_issue(line))
        return BeamNGLogRead(
            lines=lines,
            records=records,
            issues=issues,
            restarted=restarted,
            start_offset=start_offset,
            end_offset=self._offset,
        )

    def _did_restart(
        self,
        handle: Any,
        identity: tuple[int, int],
        size: int,
    ) -> bool:
        if not self._seen_file:
            return False
        if self._missing_after_seen or self._identity != identity or size < self._offset:
            return True
        if not self._anchor:
            return False
        anchor_start = self._offset - len(self._anchor)
        handle.seek(anchor_start)
        return handle.read(len(self._anchor)) != self._anchor

    @staticmethod
    def _read_anchor(handle: Any, offset: int) -> bytes:
        anchor_start = max(0, offset - _LOG_CURSOR_ANCHOR_BYTES)
        handle.seek(anchor_start)
        return handle.read(offset - anchor_start)

    def _structured_record(self, line: str) -> dict[str, Any] | None:
        folded = line.casefold()
        if self.json_tag is not None and self.json_tag not in folded:
            return None
        json_start = line.find("{")
        if json_start < 0:
            return None
        try:
            value, _ = json.JSONDecoder().raw_decode(line[json_start:])
        except json.JSONDecodeError:
            return None
        if not isinstance(value, dict):
            return None
        if self.schema_version is not None and value.get("schema_version") != self.schema_version:
            return None
        return value

    def _is_relevant_issue(self, line: str) -> bool:
        folded = line.casefold()
        if "|e|" not in folded and "|w|" not in folded:
            return False
        return not self.namespaces or any(namespace in folded for namespace in self.namespaces)


@dataclass(slots=True)
class LoopbackPortReservation:
    """Loopback ports held exclusively until the caller is ready to launch."""

    ports: tuple[int, ...]
    _sockets: list[socket.socket]

    def release(self) -> None:
        while self._sockets:
            self._sockets.pop().close()


@contextmanager
def reserve_loopback_ports(count: int) -> Iterator[LoopbackPortReservation]:
    """Reserve non-default loopback ports and release them explicitly or on exit."""

    if count < 1:
        raise ValueError("count must be positive")
    sockets: list[socket.socket] = []
    ports: list[int] = []
    try:
        while len(sockets) < count:
            candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                candidate.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            candidate.bind(("127.0.0.1", 0))
            port = int(candidate.getsockname()[1])
            if port in _DEFAULT_SERVICE_PORTS or port in ports:
                candidate.close()
                continue
            sockets.append(candidate)
            ports.append(port)
        reservation = LoopbackPortReservation(tuple(ports), sockets)
        yield reservation
    finally:
        while sockets:
            sockets.pop().close()


def claim_owned_beamng_process(bng: Any) -> Any:
    """Reject attachment to another session before enabling quit-on-close."""

    process = bng.process
    if process is None or process.poll() is not None:
        with contextlib.suppress(Exception):
            bng.disconnect()
        raise AssertionError(
            "BeamNGpy did not launch a live owned process; refusing to use an attached session"
        )
    bng.quit_on_close = True
    return process


def cleanup_owned_beamng_session(
    bng: Any,
    *,
    owned_process: Any | None = None,
    scenario: Any | None = None,
    protocol_timeout_seconds: float = 10.0,
    process_wait_timeout_seconds: float = 15.0,
) -> bool:
    """Bound graceful protocol cleanup, then stop the exact launched process.

    Returns whether the protocol cleanup completed within the bound. The cleanup
    worker is a daemon so a frozen socket cannot strand later filesystem cleanup.
    """

    if protocol_timeout_seconds <= 0 or process_wait_timeout_seconds <= 0:
        raise ValueError("cleanup timeouts must be positive")

    process = owned_process or bng.process
    completed = threading.Event()
    abandon_protocol = threading.Event()

    def graceful_cleanup() -> None:
        try:
            if scenario is not None and process is not None:
                with contextlib.suppress(Exception):
                    bng.scenario.stop()
                if abandon_protocol.is_set():
                    return
                with contextlib.suppress(Exception):
                    scenario.delete(bng)
            if abandon_protocol.is_set():
                return
            if process is not None:
                bng.quit_on_close = True
                with contextlib.suppress(Exception):
                    bng.close()
            else:
                with contextlib.suppress(Exception):
                    bng.disconnect()
        finally:
            completed.set()

    worker = threading.Thread(
        target=graceful_cleanup,
        name="beamng-live-cleanup",
        daemon=True,
    )
    worker.start()
    graceful = completed.wait(protocol_timeout_seconds)
    if not graceful:
        abandon_protocol.set()

    if process is not None and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=process_wait_timeout_seconds)
        except Exception as initial_error:
            fallback_error: Exception = initial_error
            try:
                process.kill()
            except Exception as exc:
                fallback_error = exc
            try:
                process.wait(timeout=process_wait_timeout_seconds)
            except Exception as exc:
                fallback_error = exc
            if process.poll() is None:
                raise RuntimeError(
                    "owned BeamNG process did not exit after kill"
                ) from fallback_error
        if process.poll() is None:
            raise RuntimeError("owned BeamNG process did not exit after cleanup")

    return graceful


def cleanup_exact_live_artifacts(
    *,
    profile: Path | None = None,
    files: Iterable[Path] = (),
    empty_directories: Iterable[Path] = (),
) -> None:
    """Remove every explicitly owned artifact without recursive deletion."""

    file_targets = tuple(files)
    directory_targets = tuple(empty_directories)
    if profile is not None:
        file_targets = tuple(
            require_confined_profile_target(profile, path) for path in file_targets
        )
        directory_targets = tuple(
            require_confined_profile_target(profile, path) for path in directory_targets
        )

    errors: list[Exception] = []
    for path in file_targets:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            errors.append(exc)
    for path in directory_targets:
        try:
            path.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup("live-test artifact cleanup failed", errors)


def _require_isolated_profile(user: Path) -> Path:
    absolute = Path(os.path.abspath(user))
    _reject_link_or_reparse_components(absolute)
    resolved = absolute.resolve()
    sentinel = resolved / ".beamng-mcp-test-user"
    _reject_link_or_reparse_components(sentinel)
    if not resolved.is_dir() or not sentinel.is_file():
        raise RuntimeError("live test profile is missing its sentinel")
    return resolved


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None:
        with contextlib.suppress(OSError):
            if is_junction():
                return True
    with contextlib.suppress(OSError):
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if attributes & reparse_flag:
            return True
    return False


def _reject_link_or_reparse_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if _is_link_or_reparse(current):
            raise RuntimeError(f"mutation path contains a link or reparse point: {current}")


def require_confined_profile_target(user: Path, target: Path) -> Path:
    """Return an absolute mutation target proven to remain inside the test profile."""

    profile = _require_isolated_profile(user)
    candidate = target if target.is_absolute() else profile / target
    candidate = Path(os.path.abspath(candidate))
    try:
        candidate.relative_to(profile)
    except ValueError as exc:
        raise RuntimeError(
            f"mutation target is outside the isolated BeamNG profile: {candidate}"
        ) from exc
    _reject_link_or_reparse_components(candidate)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(profile)
    except ValueError as exc:
        raise RuntimeError(
            f"mutation target is outside the isolated BeamNG profile: {candidate}"
        ) from exc
    return candidate


@contextmanager
def isolated_profile_lock(user: Path) -> Iterator[None]:
    """Serialize processes that mutate or launch the same sentinel profile."""

    resolved = _require_isolated_profile(user)
    with _PROFILE_LOCK_GUARD:
        if resolved in _HELD_PROFILE_LOCKS:
            raise RuntimeError(f"isolated BeamNG profile is already locked: {resolved}")
        _HELD_PROFILE_LOCKS.add(resolved)

    lock_path = resolved / ".beamng-mcp-live.lock"
    handle = None
    locked = False
    try:
        handle = lock_path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError(
                    f"isolated BeamNG profile is already locked: {resolved}"
                ) from exc
        else:  # pragma: no cover - the live simulator tests are Windows-only
            import fcntl

            try:
                fcntl.flock(  # type: ignore[attr-defined]
                    handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,  # type: ignore[attr-defined]
                )
            except OSError as exc:
                raise RuntimeError(
                    f"isolated BeamNG profile is already locked: {resolved}"
                ) from exc
        locked = True
        yield
    finally:
        try:
            if handle is not None:
                try:
                    if locked:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt

                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:  # pragma: no cover - the live simulator tests are Windows-only
                            import fcntl

                            fcntl.flock(  # type: ignore[attr-defined]
                                handle.fileno(),
                                fcntl.LOCK_UN,  # type: ignore[attr-defined]
                            )
                finally:
                    handle.close()
        finally:
            with _PROFILE_LOCK_GUARD:
                _HELD_PROFILE_LOCKS.discard(resolved)


@dataclass(frozen=True, slots=True)
class TemporaryLuaEndpoint:
    port: int
    token: SecretStr


def _atomic_private_write(path: Path, data: bytes, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        temporary.write_bytes(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def temporary_lua_bridge_config(
    user: Path,
    port: int,
    *,
    heartbeat_interval_seconds: float | None = None,
    heartbeat_timeout_seconds: float | None = None,
) -> Iterator[TemporaryLuaEndpoint]:
    """Rotate the isolated bridge endpoint, then restore the exact original config."""

    if not 1024 <= port <= 65535:
        raise ValueError("port must be between 1024 and 65535")
    resolved = _require_isolated_profile(user)
    config_path = require_confined_profile_target(
        resolved,
        Path("mods") / "unpacked" / MOD_DIRECTORY / BRIDGE_CONFIG,
    )
    original = config_path.read_bytes()
    mode = stat.S_IMODE(config_path.stat().st_mode)
    raw = json.loads(original.decode("utf-8"))
    if not isinstance(raw, dict) or raw.get("marker") != MOD_MARKER:
        raise RuntimeError("isolated Lua bridge config is not a recognized installation")

    token = SecretStr(secrets.token_urlsafe(32))
    raw["port"] = port
    raw["token"] = token.get_secret_value()
    if heartbeat_interval_seconds is not None:
        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive")
        raw["heartbeat_interval_seconds"] = heartbeat_interval_seconds
    if heartbeat_timeout_seconds is not None:
        if heartbeat_timeout_seconds <= 0:
            raise ValueError("heartbeat_timeout_seconds must be positive")
        raw["heartbeat_timeout_seconds"] = heartbeat_timeout_seconds
    updated = (json.dumps(raw, indent=2) + "\n").encode("utf-8")
    _atomic_private_write(config_path, updated, mode)
    try:
        yield TemporaryLuaEndpoint(port=port, token=token)
    finally:
        _atomic_private_write(config_path, original, mode)
