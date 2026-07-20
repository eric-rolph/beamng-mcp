from __future__ import annotations

import asyncio
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from beamng_mcp.autodetect import Installation, find_user
from beamng_mcp.config import Settings, WorkspaceSettings
from beamng_mcp.errors import ConflictError, SafetyInterlockError, WorkspaceError
from beamng_mcp.installer import discover_lua_token, install_lua_bridge
from beamng_mcp.models import ConnectionStatus, MapObjectMutation, MapObjectPatch, ModFileWrite
from beamng_mcp.runtime import Runtime
from beamng_mcp.services.jobs import JobManager
from beamng_mcp.services.mods import ModWorkspace


def workspace(tmp_path: Path) -> ModWorkspace:
    return ModWorkspace(WorkspaceSettings(root=tmp_path / "workspace"))


def test_config_redacts_secrets_and_rejects_non_loopback() -> None:
    settings = Settings(
        mcp={"http_token": SecretStr("a" * 32)},
        lua={"token": SecretStr("b" * 32)},
    )
    snapshot = settings.public_snapshot()
    assert "http_token" not in snapshot["mcp"]
    assert "token" not in snapshot["lua"]
    assert snapshot["mcp"]["http_token_configured"] is True
    assert snapshot["lua"]["token_configured"] is True

    non_loopback = ".".join(["0", "0", "0", "0"])
    with pytest.raises(ValidationError, match="loopback"):
        Settings(mcp={"host": non_loopback})
    with pytest.raises(ValidationError, match="loopback"):
        Settings(lua={"url": "ws://192.0.2.1:8765"})


def test_environment_overrides_toml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text("[beamng]\nport = 1234\n[vision]\ntarget_fps = 10\n", encoding="utf-8")
    monkeypatch.setenv("BEAMNG_MCP_BEAMNG_PORT", "25252")
    monkeypatch.setenv("BEAMNG_MCP_WORKSPACE", str(tmp_path / "overridden"))
    settings = Settings.load(config)
    assert settings.beamng.port == 25252
    assert settings.vision.target_fps == 10
    assert settings.workspace.root == tmp_path / "overridden"


def test_safety_lease_and_existing_map_edit_gates_are_strict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = Settings()
    assert defaults.lua.safety_lease_seconds == 1.0
    assert defaults.lua.safety_startup_grace_seconds == 5.0
    assert defaults.workspace.allow_existing_map_object_edits is False
    with pytest.raises(ValidationError):
        Settings(lua={"safety_lease_seconds": 0.24})
    with pytest.raises(ValidationError):
        Settings(lua={"safety_lease_seconds": 5.01})

    monkeypatch.setenv("BEAMNG_MCP_ALLOW_EXISTING_MAP_OBJECT_EDITS", "true")
    loaded = Settings.load()
    assert loaded.workspace.allow_existing_map_object_edits is True


def test_user_folder_uses_post_037_current_layout_even_before_first_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    old = tmp_path / "BeamNG.drive" / "0.36"
    old.mkdir(parents=True)
    assert find_user("0.38") == (tmp_path / "BeamNG" / "BeamNG.drive" / "current").resolve()


@pytest.mark.asyncio
async def test_runtime_uses_the_detected_direct_simulator_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "BeamNG.drive"
    executable = home / "Bin64" / "BeamNG.drive.x64.exe"
    user = tmp_path / "isolated-user"
    installation = Installation(
        home=home,
        user=user,
        executable=executable,
        version="0.38",
    )
    monkeypatch.setattr("beamng_mcp.runtime.detect_installation", lambda _settings: installation)
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    runtime = Runtime(settings)

    try:
        assert settings.beamng.home == home
        assert settings.beamng.user == user
        assert settings.beamng.binary == Path("Bin64/BeamNG.drive.x64.exe")
    finally:
        await runtime.shutdown()


def test_mod_workspace_confines_paths_and_uses_optimistic_writes(tmp_path: Path) -> None:
    mods = workspace(tmp_path)
    mods.scaffold("safe_mod", title="Safe Mod", author="Test")
    first = mods.write_file(
        ModFileWrite(
            mod_name="safe_mod", path="lua/ge/extensions/example.lua", content="return {}\n"
        )
    )
    content, read_info = mods.read_file("safe_mod", first.path)
    assert content == "return {}\n"
    assert read_info.sha256 == first.sha256

    updated = mods.write_file(
        ModFileWrite(
            mod_name="safe_mod",
            path=first.path,
            content="local M = {}\nreturn M\n",
            expected_sha256=first.sha256,
        )
    )
    assert updated.sha256 != first.sha256
    with pytest.raises(ConflictError, match="changed since"):
        mods.write_file(
            ModFileWrite(
                mod_name="safe_mod",
                path=first.path,
                content="return nil\n",
                expected_sha256=first.sha256,
            )
        )
    with pytest.raises(WorkspaceError, match="traversal"):
        mods.write_file(ModFileWrite(mod_name="safe_mod", path="../outside.txt", content="escape"))
    with pytest.raises(WorkspaceError, match="Top-level"):
        mods.write_file(ModFileWrite(mod_name="safe_mod", path="random/file.txt", content="no"))
    assert not (tmp_path / "outside.txt").exists()


def test_mod_pack_has_beamng_roots_at_zip_root(tmp_path: Path) -> None:
    mods = workspace(tmp_path)
    mods.scaffold("packed_mod", title="Packed", author="Test", kind="mixed")
    mods.write_file(
        ModFileWrite(
            mod_name="packed_mod",
            path="lua/ge/extensions/packed.lua",
            content="return {}\n",
        )
    )
    artifact = mods.pack("packed_mod")
    assert Path(artifact.path).is_file()
    with zipfile.ZipFile(artifact.path) as archive:
        names = archive.namelist()
    assert "lua/ge/extensions/packed.lua" in names
    assert not any(name.startswith("packed_mod/") for name in names)


def test_mod_install_requires_overwrite_and_makes_backup(tmp_path: Path) -> None:
    mods = ModWorkspace(WorkspaceSettings(root=tmp_path / "workspace", allow_mod_install=True))
    mods.scaffold("installed_mod", title="Installed", author="Test")
    user = tmp_path / "user"
    first = mods.install("installed_mod", user)
    assert Path(first.path).is_file()
    with pytest.raises(SafetyInterlockError, match="already exists"):
        mods.install("installed_mod", user)
    second = mods.install("installed_mod", user, overwrite=True)
    assert Path(second.path).is_file()
    assert list((user / "mods" / "repo").glob("*.backup-*"))


def test_lua_installer_generates_local_token_and_never_keeps_placeholder(tmp_path: Path) -> None:
    settings = Settings(
        beamng={"user": tmp_path / "user"},
        lua={"safety_lease_seconds": 0.75},
        workspace={
            "root": tmp_path / "workspace",
            "allow_existing_map_object_edits": True,
        },
    )
    result = install_lua_bridge(settings, user_path=tmp_path / "user")
    config_path = result.destination / "settings" / "beamng_mcp.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert raw["marker"] == "beamng-mcp-bridge"
    assert raw["token"] != "__BEAMNG_MCP_TOKEN__"
    assert len(raw["token"]) >= 32
    assert isinstance(result.token, SecretStr)
    assert raw["token"] not in repr(result)
    assert raw["max_payload_bytes"] == settings.lua.max_message_bytes
    assert raw["safety_lease_seconds"] == 0.75
    assert raw["safety_startup_grace_seconds"] == 5.0
    assert raw["allow_existing_map_object_edits"] is True
    scripts = result.destination / "scripts" / "beamng_mcp"
    assert (scripts / "modScript.lua").is_file()
    assert not (scripts / "bootstrap.lua").exists()
    discovered = discover_lua_token(tmp_path / "user")
    assert discovered is not None
    assert discovered.get_secret_value() == raw["token"]
    with pytest.raises(SafetyInterlockError, match="already installed"):
        install_lua_bridge(settings, user_path=tmp_path / "user")


def test_lua_installer_force_rejects_an_unrecognized_destination(tmp_path: Path) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    destination = tmp_path / "user" / "mods" / "unpacked" / "beamng_mcp"
    config = destination / "settings" / "beamng_mcp.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"marker": "some-other-project", "sentinel": true}\n', encoding="utf-8")

    with pytest.raises(SafetyInterlockError, match=r"recognized.*marker"):
        install_lua_bridge(settings, user_path=tmp_path / "user", force=True)

    assert json.loads(config.read_text(encoding="utf-8"))["sentinel"] is True


def test_lua_installer_force_swaps_a_fresh_tree_and_keeps_backup(tmp_path: Path) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    first = install_lua_bridge(settings, user_path=tmp_path / "user")
    stale = first.destination / "stale.lua"
    stale.write_text("old and unsafe\n", encoding="utf-8")
    old_token = first.token.get_secret_value()

    updated = install_lua_bridge(
        settings,
        user_path=tmp_path / "user",
        force=True,
    )

    assert not (updated.destination / "stale.lua").exists()
    assert updated.token.get_secret_value() != old_token
    backups = list((tmp_path / "user" / "mods" / "beamng_mcp_backups").glob("backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "stale.lua").read_text(encoding="utf-8") == "old and unsafe\n"
    assert list((tmp_path / "user" / ".beamng_mcp_staging").iterdir()) == []


def test_lua_installer_retries_transient_windows_directory_move(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real_rename = Path.rename
    denied_once = False

    def flaky_rename(source: Path, target: Path) -> Path:
        nonlocal denied_once
        if not denied_once and ".beamng_mcp_staging" in source.parts:
            denied_once = True
            raise PermissionError(5, "transient scanner handle")
        return real_rename(source, target)

    monkeypatch.setattr(Path, "rename", flaky_rename)
    result = install_lua_bridge(
        Settings(workspace={"root": tmp_path / "workspace"}),
        user_path=tmp_path / "user",
    )

    assert denied_once is True
    assert result.destination.is_dir()


def test_lua_installer_restricts_generated_config_permissions_best_effort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    chmod_calls: list[tuple[Path, int]] = []
    real_chmod = os.chmod

    def recording_chmod(path, mode, *args, **kwargs):
        chmod_calls.append((Path(path), mode))
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr("beamng_mcp.installer.os.chmod", recording_chmod)
    result = install_lua_bridge(
        Settings(workspace={"root": tmp_path / "workspace"}),
        user_path=tmp_path / "user",
    )

    config = result.destination / "settings" / "beamng_mcp.json"
    assert (config, stat.S_IRUSR | stat.S_IWUSR) in chmod_calls


def test_lua_installer_tolerates_unavailable_permission_hardening(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def unavailable_chmod(*_args, **_kwargs):
        raise OSError("ACL operation unavailable")

    monkeypatch.setattr("beamng_mcp.installer.os.chmod", unavailable_chmod)
    result = install_lua_bridge(
        Settings(workspace={"root": tmp_path / "workspace"}),
        user_path=tmp_path / "user",
    )

    assert (result.destination / "settings" / "beamng_mcp.json").is_file()


def test_lua_installer_restores_original_when_staged_swap_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(workspace={"root": tmp_path / "workspace"})
    original = install_lua_bridge(settings, user_path=tmp_path / "user")
    original_token = original.token.get_secret_value()
    sentinel = original.destination / "keep-me.txt"
    sentinel.write_text("original\n", encoding="utf-8")
    real_rename = Path.rename

    def fail_staging_swap(path: Path, target: Path) -> Path:
        if path.parent.name == ".beamng_mcp_staging" and Path(target) == original.destination:
            raise OSError("injected swap failure")
        return real_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_staging_swap)

    with pytest.raises(OSError, match="injected swap failure"):
        install_lua_bridge(settings, user_path=tmp_path / "user", force=True)

    restored = json.loads(
        (original.destination / "settings" / "beamng_mcp.json").read_text(encoding="utf-8")
    )
    assert restored["token"] == original_token
    assert sentinel.read_text(encoding="utf-8") == "original\n"


def test_lua_installer_rejects_a_planted_destination_link(tmp_path: Path) -> None:
    target = tmp_path / "attacker-controlled"
    config = target / "settings" / "beamng_mcp.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        '{"marker": "beamng-mcp-bridge", "token": "dddddddddddddddddddddddddddddddd", '
        '"sentinel": true}\n',
        encoding="utf-8",
    )
    destination = tmp_path / "user" / "mods" / "unpacked" / "beamng_mcp"
    destination.parent.mkdir(parents=True)
    try:
        destination.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(SafetyInterlockError, match=r"link|reparse"):
        install_lua_bridge(
            Settings(workspace={"root": tmp_path / "workspace"}),
            user_path=tmp_path / "user",
            force=True,
        )

    assert json.loads(config.read_text(encoding="utf-8"))["sentinel"] is True
    assert discover_lua_token(tmp_path / "user") is None


def test_lua_installer_rejects_links_in_parent_components(tmp_path: Path) -> None:
    target = tmp_path / "attacker-controlled-user"
    target.mkdir()
    linked_user = tmp_path / "linked-user"
    try:
        linked_user.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(SafetyInterlockError, match=r"link|reparse"):
        install_lua_bridge(
            Settings(workspace={"root": tmp_path / "workspace"}),
            user_path=linked_user,
        )

    assert not (target / "mods").exists()


@pytest.mark.asyncio
async def test_job_manager_tracks_progress_results_and_cancel() -> None:
    manager = JobManager()

    async def success(context):
        await context.progress(0.5)
        return {"answer": 42}

    job = await manager.start("test", success)
    await manager._tasks[job.job_id]
    finished = manager.get(job.job_id)
    assert finished.status == "succeeded"
    assert finished.progress == 1.0
    assert finished.result == {"answer": 42}

    blocker = asyncio.Event()

    async def wait_forever(_context):
        await blocker.wait()
        return {}

    pending = await manager.start("blocked", wait_forever)
    cancelled = await manager.cancel(pending.job_id)
    assert cancelled.status == "cancelled"
    await manager.shutdown()


class FakeLua:
    connected = True

    def __init__(self, *, managed: bool = True, level: str = "west_coast_usa") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.managed = managed
        self.level = level

    async def call(self, method: str, params: dict) -> dict:
        self.calls.append((method, params))
        if method == "world.get_object":
            return {"managed": self.managed}
        if method == "telemetry.snapshot":
            return {"level": self.level}
        return {"ok": True}


@pytest.mark.asyncio
async def test_runtime_maps_models_to_allowlisted_lua_contract() -> None:
    runtime = object.__new__(Runtime)
    runtime.lua = FakeLua()
    runtime.settings = Settings()

    mutation = MapObjectMutation(name="test_box", class_name="TSStatic", position=(1, 2, 3))
    await runtime.map_create_object(mutation)
    assert runtime.lua.calls[-1][0] == "world.create_object"
    assert runtime.lua.calls[-1][1]["class"] == "TSStatic"
    assert "class_name" not in runtime.lua.calls[-1][1]

    patch = MapObjectPatch(object_id=17, position=(3, 2, 1))
    await runtime.map_update_object(patch)
    assert runtime.lua.calls[-1][1]["id"] == 17
    await runtime.map_delete_object("test_box", confirm=True)
    assert runtime.lua.calls[-1][1] == {"confirm": True, "name": "test_box"}

    with pytest.raises(SafetyInterlockError, match="disabled"):
        await runtime.map_save(level=None, confirm=True)


@pytest.mark.asyncio
async def test_runtime_blocks_existing_map_object_mutation_without_operator_gate() -> None:
    runtime = object.__new__(Runtime)
    runtime.lua = FakeLua(managed=False)
    runtime.settings = Settings()

    patch = MapObjectPatch(object_id=17, position=(3, 2, 1))
    with pytest.raises(SafetyInterlockError, match="existing map object"):
        await runtime.map_update_object(patch)
    with pytest.raises(SafetyInterlockError, match="existing map object"):
        await runtime.map_delete_object(17, confirm=True)

    assert not any(
        method in {"world.update_object", "world.delete_object"}
        for method, _params in runtime.lua.calls
    )


@pytest.mark.asyncio
async def test_map_save_requires_exact_loaded_level_identifier() -> None:
    runtime = object.__new__(Runtime)
    runtime.lua = FakeLua(level="west_coast_usa")
    runtime.settings = Settings(workspace={"allow_persistent_map_edits": True})

    with pytest.raises(SafetyInterlockError, match="exact loaded level"):
        await runtime.map_save(level=None, confirm=True)
    with pytest.raises(SafetyInterlockError, match="does not match"):
        await runtime.map_save(level="gridmap_v2", confirm=True)

    result = await runtime.map_save(level="west_coast_usa", confirm=True)
    assert result == {"ok": True}
    assert runtime.lua.calls[-2:] == [
        ("telemetry.snapshot", {}),
        ("world.save_level", {"level": "west_coast_usa", "confirm": True}),
    ]


class IdleAutonomy:
    running = False


class HangingStatusSimulator:
    async def status(self) -> ConnectionStatus:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def emergency_stop(self, _vehicle_id: str | None = None) -> None:
        raise AssertionError("stop must not run before a connected status")


class ReconnectingLua:
    connected = False

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call(self, method: str, params: dict) -> dict:
        self.calls.append((method, params))
        return {"stopped": True}


@pytest.mark.asyncio
async def test_emergency_stop_does_not_let_wedged_beamngpy_block_lua() -> None:
    runtime = object.__new__(Runtime)
    runtime.settings = Settings(lua={"token": SecretStr("c" * 32), "request_timeout_seconds": 0.02})
    runtime.autonomy = IdleAutonomy()
    runtime.simulator = HangingStatusSimulator()
    runtime.lua = ReconnectingLua()

    result = await asyncio.wait_for(runtime.emergency_stop("ego"), timeout=0.5)

    assert runtime.lua.calls == [("emergency_stop", {"vehicle_name": "ego"})]
    assert result.ok is False
    assert result.data["paths"] == ["lua"]
    assert result.data["outcomes"]["beamngpy"]["status"] == "timeout"
    assert result.data["outcomes"]["lua"]["status"] == "applied"


class FailingAutonomy:
    running = True

    async def emergency_stop(self, _reason: str) -> None:
        raise RuntimeError("autonomy shutdown failed")


class ConnectedStopSimulator:
    def __init__(self) -> None:
        self.stopped: list[str | None] = []

    async def status(self) -> ConnectionStatus:
        return ConnectionStatus(connected=True, host="127.0.0.1", port=25252)

    async def emergency_stop(self, vehicle_id: str | None = None) -> None:
        self.stopped.append(vehicle_id)


@pytest.mark.asyncio
async def test_emergency_stop_reports_partial_failure_without_claiming_success() -> None:
    runtime = object.__new__(Runtime)
    runtime.settings = Settings(lua={"token": SecretStr("e" * 32)})
    runtime.autonomy = FailingAutonomy()
    runtime.simulator = ConnectedStopSimulator()
    runtime.lua = ReconnectingLua()

    result = await runtime.emergency_stop("17")

    assert runtime.simulator.stopped == ["17"]
    assert runtime.lua.calls == [("emergency_stop", {"vehicle_name": "17"})]
    assert result.ok is False
    assert result.data["paths"] == ["beamngpy", "lua"]
    assert result.data["outcomes"]["autonomy"]["status"] == "failed"
    assert "autonomy shutdown failed" in result.data["outcomes"]["autonomy"]["error"]
