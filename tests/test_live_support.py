from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tests.live_support import (
    claim_owned_beamng_process,
    cleanup_exact_live_artifacts,
    cleanup_owned_beamng_session,
    isolated_profile_lock,
    require_confined_profile_target,
    reserve_loopback_ports,
    temporary_lua_bridge_config,
)


class _AliveProcess:
    def poll(self) -> None:
        return None


class _TerminableProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return 0 if self.terminated or self.killed else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float) -> int:
        del timeout
        return 0

    def kill(self) -> None:
        self.killed = True


class _KillNeedsWaitProcess:
    def __init__(self) -> None:
        self.wait_calls = 0
        self.killed = False
        self.reaped = False

    def poll(self) -> int | None:
        return 0 if self.reaped else None

    def terminate(self) -> None:
        pass

    def wait(self, timeout: float) -> int:
        del timeout
        self.wait_calls += 1
        if not self.killed:
            raise TimeoutError("terminate timed out")
        self.reaped = True
        return 0

    def kill(self) -> None:
        self.killed = True


def test_claim_owned_process_rejects_an_attached_session_without_enabling_quit() -> None:
    disconnected: list[bool] = []
    bng = SimpleNamespace(
        process=None,
        quit_on_close=False,
        disconnect=lambda: disconnected.append(True),
    )

    with pytest.raises(AssertionError, match="did not launch"):
        claim_owned_beamng_process(bng)

    assert disconnected == [True]
    assert bng.quit_on_close is False


def test_claim_owned_process_enables_quit_only_for_a_live_launched_process() -> None:
    process = _AliveProcess()
    bng = SimpleNamespace(process=process, quit_on_close=False)

    assert claim_owned_beamng_process(bng) is process
    assert bng.quit_on_close is True


def test_cleanup_owned_session_is_bounded_when_socket_close_never_returns() -> None:
    process = _TerminableProcess()
    close_started = threading.Event()
    release_close = threading.Event()

    def blocking_close() -> None:
        close_started.set()
        release_close.wait()

    bng = SimpleNamespace(
        process=process,
        quit_on_close=False,
        close=blocking_close,
        disconnect=lambda: None,
    )

    started = time.monotonic()
    try:
        graceful = cleanup_owned_beamng_session(
            bng,
            owned_process=process,
            protocol_timeout_seconds=0.05,
            process_wait_timeout_seconds=0.05,
        )
    finally:
        release_close.set()

    assert close_started.is_set()
    assert graceful is False
    assert process.terminated is True
    assert bng.quit_on_close is True
    assert time.monotonic() - started < 0.5


def test_timed_out_cleanup_does_not_resume_protocol_after_process_shutdown() -> None:
    process = _TerminableProcess()
    stop_started = threading.Event()
    release_stop = threading.Event()
    later_protocol_calls: list[str] = []

    def blocking_stop() -> None:
        stop_started.set()
        release_stop.wait()

    scenario = SimpleNamespace(
        delete=lambda _bng: later_protocol_calls.append("delete"),
    )
    bng = SimpleNamespace(
        process=process,
        quit_on_close=False,
        scenario=SimpleNamespace(stop=blocking_stop),
        close=lambda: later_protocol_calls.append("close"),
        disconnect=lambda: None,
    )

    graceful = cleanup_owned_beamng_session(
        bng,
        owned_process=process,
        scenario=scenario,
        protocol_timeout_seconds=0.05,
        process_wait_timeout_seconds=0.05,
    )
    assert stop_started.is_set()
    assert graceful is False
    release_stop.set()
    time.sleep(0.05)

    assert later_protocol_calls == []


def test_cleanup_waits_again_after_killing_the_owned_process() -> None:
    process = _KillNeedsWaitProcess()
    bng = SimpleNamespace(
        process=process,
        quit_on_close=False,
        close=lambda: None,
        disconnect=lambda: None,
    )

    assert cleanup_owned_beamng_session(
        bng,
        owned_process=process,
        protocol_timeout_seconds=0.05,
        process_wait_timeout_seconds=0.05,
    )
    assert process.killed is True
    assert process.wait_calls == 2
    assert process.poll() == 0


def test_cleanup_fails_explicitly_when_owned_process_survives_kill() -> None:
    process = SimpleNamespace(
        poll=lambda: None,
        terminate=lambda: None,
        wait=lambda timeout: (_ for _ in ()).throw(TimeoutError(timeout)),
        kill=lambda: None,
    )
    bng = SimpleNamespace(
        process=process,
        quit_on_close=False,
        close=lambda: None,
        disconnect=lambda: None,
    )

    with pytest.raises(RuntimeError, match="did not exit after kill"):
        cleanup_owned_beamng_session(
            bng,
            owned_process=process,
            protocol_timeout_seconds=0.05,
            process_wait_timeout_seconds=0.05,
        )


def test_cleanup_kills_and_waits_when_terminate_itself_fails() -> None:
    state = {"killed": False, "reaped": False, "waits": 0}

    def fail_terminate() -> None:
        raise OSError("terminate failed")

    def kill() -> None:
        state["killed"] = True

    def wait(timeout: float) -> int:
        del timeout
        state["waits"] += 1
        assert state["killed"] is True
        state["reaped"] = True
        return 0

    process = SimpleNamespace(
        poll=lambda: 0 if state["reaped"] else None,
        terminate=fail_terminate,
        wait=wait,
        kill=kill,
    )
    bng = SimpleNamespace(
        process=process,
        quit_on_close=False,
        close=lambda: None,
        disconnect=lambda: None,
    )

    assert cleanup_owned_beamng_session(
        bng,
        owned_process=process,
        protocol_timeout_seconds=0.05,
        process_wait_timeout_seconds=0.05,
    )
    assert state == {"killed": True, "reaped": True, "waits": 1}


def test_reserved_loopback_ports_are_unique_nondefault_and_releasable() -> None:
    with reserve_loopback_ports(2) as reservation:
        assert len(set(reservation.ports)) == 2
        assert not set(reservation.ports).intersection({8765, 25252})
        reservation.release()
        reservation.release()


def test_exact_artifact_cleanup_attempts_every_path_after_one_failure(tmp_path: Path) -> None:
    package = tmp_path / "disposable.zip"
    package.write_bytes(b"test")
    scenario_directory = tmp_path / "scenario"
    scenario_directory.mkdir()
    (scenario_directory / "unexpected.txt").write_text("not owned", encoding="utf-8")

    with pytest.raises(ExceptionGroup, match="live-test artifact cleanup failed"):
        cleanup_exact_live_artifacts(
            files=(package,),
            empty_directories=(scenario_directory,),
        )

    assert not package.exists()
    assert scenario_directory.is_dir()


def test_exact_artifact_cleanup_refuses_a_linked_profile_target(tmp_path: Path) -> None:
    user = tmp_path / "current"
    user.mkdir()
    (user / ".beamng-mcp-test-user").touch()
    real_repo = user / "real-repo"
    real_repo.mkdir()
    package = real_repo / "keep.zip"
    package.write_bytes(b"keep")
    linked_repo = user / "repo"
    try:
        linked_repo.symlink_to(real_repo, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory links are unavailable on this host: {exc}")

    with pytest.raises(RuntimeError, match="link or reparse"):
        cleanup_exact_live_artifacts(profile=user, files=(linked_repo / package.name,))

    assert package.read_bytes() == b"keep"


def test_profile_target_guard_rejects_a_target_outside_the_sentinel_profile(
    tmp_path: Path,
) -> None:
    user = tmp_path / "current"
    user.mkdir()
    (user / ".beamng-mcp-test-user").touch()
    outside = tmp_path / "outside.zip"

    with pytest.raises(RuntimeError, match="outside the isolated BeamNG profile"):
        require_confined_profile_target(user, outside)


def test_profile_target_guard_rejects_a_link_component_even_when_it_points_inward(
    tmp_path: Path,
) -> None:
    user = tmp_path / "current"
    user.mkdir()
    (user / ".beamng-mcp-test-user").touch()
    real_mods = user / "real-mods"
    real_mods.mkdir()
    linked_mods = user / "mods"
    try:
        linked_mods.symlink_to(real_mods, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory links are unavailable on this host: {exc}")

    with pytest.raises(RuntimeError, match="link or reparse"):
        require_confined_profile_target(user, linked_mods / "repo" / "test.zip")


def test_isolated_profile_rejects_a_link_to_a_sentinel_directory(tmp_path: Path) -> None:
    real_user = tmp_path / "real-current"
    real_user.mkdir()
    (real_user / ".beamng-mcp-test-user").touch()
    linked_user = tmp_path / "current"
    try:
        linked_user.symlink_to(real_user, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory links are unavailable on this host: {exc}")

    with pytest.raises(RuntimeError, match="link or reparse"):
        with isolated_profile_lock(linked_user):
            pass


def test_temporary_lua_bridge_config_rotates_endpoint_and_restores_exact_bytes(
    tmp_path: Path,
) -> None:
    user = tmp_path / "current"
    (user / ".beamng-mcp-test-user").parent.mkdir(parents=True)
    (user / ".beamng-mcp-test-user").touch()
    config = user / "mods" / "unpacked" / "beamng_mcp" / "settings" / "beamng_mcp.json"
    config.parent.mkdir(parents=True)
    original = b'{"marker":"beamng-mcp-bridge","port":8765,"token":"original-secret"}\n'
    config.write_bytes(original)

    with temporary_lua_bridge_config(user, 49123) as endpoint:
        current = json.loads(config.read_text(encoding="utf-8"))
        assert endpoint.port == 49123
        assert current["port"] == 49123
        assert current["token"] == endpoint.token.get_secret_value()
        assert current["token"] != "original-secret"

    assert config.read_bytes() == original


def test_temporary_lua_bridge_config_refuses_a_linked_mod_directory(
    tmp_path: Path,
) -> None:
    user = tmp_path / "current"
    user.mkdir()
    (user / ".beamng-mcp-test-user").touch()
    real_mods = user / "real-mods"
    config = real_mods / "unpacked" / "beamng_mcp" / "settings" / "beamng_mcp.json"
    config.parent.mkdir(parents=True)
    original = b'{"marker":"beamng-mcp-bridge","port":8765,"token":"keep"}\n'
    config.write_bytes(original)
    try:
        (user / "mods").symlink_to(real_mods, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory links are unavailable on this host: {exc}")

    with pytest.raises(RuntimeError, match="link or reparse"):
        with temporary_lua_bridge_config(user, 49123):
            pass

    assert config.read_bytes() == original


def test_isolated_profile_lock_serializes_the_exact_sentinel_profile(tmp_path: Path) -> None:
    user = tmp_path / "current"
    user.mkdir()
    (user / ".beamng-mcp-test-user").touch()

    with isolated_profile_lock(user):
        with pytest.raises(RuntimeError, match="already locked"):
            with isolated_profile_lock(user):
                pass


def test_isolated_profile_lock_can_retry_after_lock_file_open_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "current"
    user.mkdir()
    (user / ".beamng-mcp-test-user").touch()
    lock_path = user / ".beamng-mcp-live.lock"
    original_open = Path.open
    attempts = 0

    def fail_first_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        nonlocal attempts
        if path == lock_path and attempts == 0:
            attempts += 1
            raise OSError("simulated lock-file open failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_first_open)

    with pytest.raises(OSError, match="simulated lock-file open failure"):
        with isolated_profile_lock(user):
            pass

    with isolated_profile_lock(user):
        pass
