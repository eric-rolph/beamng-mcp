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
def temporary_lua_bridge_config(user: Path, port: int) -> Iterator[TemporaryLuaEndpoint]:
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
    updated = (json.dumps(raw, indent=2) + "\n").encode("utf-8")
    _atomic_private_write(config_path, updated, mode)
    try:
        yield TemporaryLuaEndpoint(port=port, token=token)
    finally:
        _atomic_private_write(config_path, original, mode)
