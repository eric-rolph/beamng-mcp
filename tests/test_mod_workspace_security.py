from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from beamng_mcp.config import Settings, WorkspaceSettings
from beamng_mcp.errors import SafetyInterlockError, WorkspaceError
from beamng_mcp.models import ModFileWrite
from beamng_mcp.services import mods as mods_module
from beamng_mcp.services.mods import ModWorkspace


def make_workspace(tmp_path: Path, **overrides: object) -> ModWorkspace:
    return ModWorkspace(WorkspaceSettings(root=tmp_path / "workspace", **overrides))


def test_mod_install_is_operator_gated_but_offline_workflow_remains_available(
    tmp_path: Path,
) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("offline_mod", title="Offline", author="Test")

    assert mods.validate("offline_mod").valid is True
    artifact = mods.pack("offline_mod")
    assert Path(artifact.path).is_file()

    with pytest.raises(SafetyInterlockError, match=r"workspace\.allow_mod_install"):
        mods.install("offline_mod", tmp_path / "user")
    assert not (tmp_path / "user" / "mods").exists()


def test_mod_install_gate_can_be_enabled_by_operator_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BEAMNG_MCP_ALLOW_MOD_INSTALL", "true")
    monkeypatch.setenv("BEAMNG_MCP_WORKSPACE", str(tmp_path / "workspace"))

    settings = Settings.load()

    assert settings.workspace.allow_mod_install is True


def test_file_count_quota_blocks_write_before_mutation(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path, max_mod_files=2)
    mods.scaffold("bounded_mod", title="Bounded", author="Test")

    with pytest.raises(WorkspaceError, match="file-count quota"):
        mods.write_file(
            ModFileWrite(
                mod_name="bounded_mod",
                path="lua/ge/extensions/third.lua",
                content="return {}\n",
            )
        )

    assert not (
        tmp_path / "workspace" / "mods" / "bounded_mod" / "lua" / "ge" / "extensions" / "third.lua"
    ).exists()


def test_total_byte_quota_blocks_write_before_mutation(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path, max_mod_bytes=1024)
    mods.scaffold("bounded_mod", title="Bounded", author="Test")

    with pytest.raises(WorkspaceError, match="total-byte quota"):
        mods.write_file(
            ModFileWrite(
                mod_name="bounded_mod",
                path="lua/ge/extensions/large.lua",
                content="x" * 1024,
            )
        )

    assert not (
        tmp_path / "workspace" / "mods" / "bounded_mod" / "lua" / "ge" / "extensions" / "large.lua"
    ).exists()


def test_validate_reports_and_pack_rejects_an_externally_over_quota_mod(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path, max_mod_files=2)
    mods.scaffold("overfull_mod", title="Overfull", author="Test")
    extra = (
        tmp_path
        / "workspace"
        / "mods"
        / "overfull_mod"
        / "lua"
        / "ge"
        / "extensions"
        / "external.lua"
    )
    extra.write_text("return {}\n", encoding="utf-8")

    validation = mods.validate("overfull_mod")

    assert validation.valid is False
    assert any("file-count quota" in issue.message for issue in validation.issues)
    with pytest.raises(WorkspaceError, match="validation errors"):
        mods.pack("overfull_mod")


def test_validate_warns_on_plain_lua_load_call(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("dynamic_lua", title="Dynamic Lua", author="Test")
    mods.write_file(
        ModFileWrite(
            mod_name="dynamic_lua",
            path="lua/ge/extensions/dynamic.lua",
            content="local callback = load(source)\nreturn callback\n",
        )
    )

    validation = mods.validate("dynamic_lua")

    assert any(
        issue.path == "lua/ge/extensions/dynamic.lua"
        and issue.message == "Dynamic Lua evaluation found; review before installing"
        for issue in validation.issues
    )


def test_validate_allows_fixed_extension_bootstrap_load(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("static_lua", title="Static Lua", author="Test")
    mods.write_file(
        ModFileWrite(
            mod_name="static_lua",
            path="scripts/static_lua/modScript.lua",
            content=('local EXTENSION_PATH = "static_lua/main"\nextensions.load(EXTENSION_PATH)\n'),
        )
    )

    validation = mods.validate("static_lua")

    assert not any(
        issue.message == "Dynamic Lua evaluation found; review before installing"
        for issue in validation.issues
    )


@pytest.mark.parametrize(
    "content",
    [
        "local callback = loadstring (source)\nreturn callback\n",
        "dostring \t(source)\n",
        "local callback = _G.load(source)\nreturn callback\n",
        "local callback = sandbox.load (source)\nreturn callback\n",
        "local callback = sandbox:load(source)\nreturn callback\n",
    ],
    ids=[
        "loadstring-whitespace",
        "dostring-whitespace",
        "global-table-load",
        "member-load",
        "method-load",
    ],
)
def test_validate_warns_on_qualified_or_whitespace_dynamic_lua_calls(
    content: str, tmp_path: Path
) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("dynamic_lua", title="Dynamic Lua", author="Test")
    mods.write_file(
        ModFileWrite(
            mod_name="dynamic_lua",
            path="lua/ge/extensions/dynamic.lua",
            content=content,
        )
    )

    validation = mods.validate("dynamic_lua")

    assert any(
        issue.path == "lua/ge/extensions/dynamic.lua"
        and issue.message == "Dynamic Lua evaluation found; review before installing"
        for issue in validation.issues
    )


def test_validate_does_not_warn_for_identifiers_containing_load(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("static_lua", title="Static Lua", author="Test")
    mods.write_file(
        ModFileWrite(
            mod_name="static_lua",
            path="lua/ge/extensions/static.lua",
            content="local function preload(source)\n  return source\nend\nreturn preload\n",
        )
    )

    validation = mods.validate("static_lua")

    assert not any(
        issue.message == "Dynamic Lua evaluation found; review before installing"
        for issue in validation.issues
    )


def test_validate_accepts_beamng_newline_delimited_prefab_json(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("prefab_mod", title="Prefab", author="Test")
    mods.write_file(
        ModFileWrite(
            mod_name="prefab_mod",
            path="levels/gridmap_v2/scenarios/demo/demo.prefab.json",
            content=(
                '{"name":"truck","class":"BeamNGVehicle"}\n'
                '{"name":"demo_group","class":"SimGroup"}\n'
            ),
        )
    )

    validation = mods.validate("prefab_mod")

    assert validation.valid is True
    assert validation.issues == []


def test_validate_reports_the_malformed_prefab_json_record_line(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("prefab_mod", title="Prefab", author="Test")
    mods.write_file(
        ModFileWrite(
            mod_name="prefab_mod",
            path="levels/gridmap_v2/scenarios/demo/demo.prefab.json",
            content=('{"name":"truck","class":"BeamNGVehicle"}\n{"name":"broken",}\n'),
        )
    )

    validation = mods.validate("prefab_mod")

    assert validation.valid is False
    assert any(
        issue.path == "levels/gridmap_v2/scenarios/demo/demo.prefab.json"
        and "invalid prefab object on line 2" in issue.message
        for issue in validation.issues
    )


def test_validate_keeps_ordinary_json_as_one_document(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("json_mod", title="JSON", author="Test")
    mods.write_file(
        ModFileWrite(
            mod_name="json_mod",
            path="levels/gridmap_v2/scenarios/demo/data.json",
            content='{"first":1}\n{"second":2}\n',
        )
    )

    validation = mods.validate("json_mod")

    assert validation.valid is False
    assert any(
        issue.path == "levels/gridmap_v2/scenarios/demo/data.json"
        and "Invalid JSON: Extra data" in issue.message
        for issue in validation.issues
    )


def test_validate_accepts_standard_root_mod_metadata(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("metadata_mod", title="Metadata", author="Test")
    mods.write_file(
        ModFileWrite(
            mod_name="metadata_mod",
            path="info.json",
            content=(
                '{"title":"Metadata","name":"metadata_mod","version":"1.0.0","type":"Other"}\n'
            ),
        )
    )

    validation = mods.validate("metadata_mod")

    assert validation.valid is True
    assert validation.issues == []


def test_internal_symlink_is_rejected_for_listing_and_writes(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("linked_mod", title="Linked", author="Test")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "workspace" / "mods" / "linked_mod" / "lua" / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(WorkspaceError, match=r"[Rr]eparse|[Ss]ymlink"):
        mods.list_files("linked_mod")
    with pytest.raises(WorkspaceError, match=r"[Rr]eparse|[Ss]ymlink"):
        mods.write_file(
            ModFileWrite(
                mod_name="linked_mod",
                path="lua/linked/escape.lua",
                content="return {}\n",
            )
        )
    assert not (outside / "escape.lua").exists()


def test_windows_reparse_attribute_is_recognized_without_symlink_mode() -> None:
    fake_stat = SimpleNamespace(
        st_mode=stat.S_IFDIR,
        st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
    )

    assert mods_module._is_reparse_stat(fake_stat) is True


def test_pack_revalidates_files_after_its_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("racing_mod", title="Racing", author="Test")
    target = tmp_path / "workspace" / "mods" / "racing_mod" / "README.md"
    original_list = mods.list_files
    calls = 0

    def list_then_mutate(mod_name: str):
        nonlocal calls
        result = original_list(mod_name)
        calls += 1
        if calls == 2:
            target.write_text("changed after snapshot\n", encoding="utf-8")
        return result

    monkeypatch.setattr(mods, "list_files", list_then_mutate)

    with pytest.raises(WorkspaceError, match="changed while it was being processed"):
        mods.pack("racing_mod")
    assert not (tmp_path / "workspace" / "artifacts" / "racing_mod.zip").exists()


def test_configured_workspace_with_symlink_component_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(real, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")
    mods = ModWorkspace(WorkspaceSettings(root=linked / "workspace"))

    with pytest.raises(WorkspaceError, match=r"[Rr]eparse|[Ss]ymlink"):
        mods.ensure()


@pytest.mark.parametrize("linked_component", ["user", "mods", "repo"])
def test_install_rejects_linked_beamng_path_components(
    linked_component: str, tmp_path: Path
) -> None:
    mods = make_workspace(tmp_path, allow_mod_install=True)
    mods.scaffold("linked_install", title="Linked", author="Test")
    outside = tmp_path / "outside"
    outside.mkdir()
    user = tmp_path / "user"

    if linked_component == "user":
        link = user
    else:
        user.mkdir()
        if linked_component == "mods":
            link = user / "mods"
        else:
            (user / "mods").mkdir()
            link = user / "mods" / "repo"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(WorkspaceError, match=r"[Rr]eparse|[Ss]ymlink"):
        mods.install("linked_install", user)
    assert not (outside / "linked_install.zip").exists()


def test_install_rejects_non_regular_destination(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path, allow_mod_install=True)
    mods.scaffold("special_destination", title="Special", author="Test")
    destination = tmp_path / "user" / "mods" / "repo" / "special_destination.zip"
    destination.mkdir(parents=True)

    with pytest.raises(SafetyInterlockError, match="non-regular"):
        mods.install("special_destination", tmp_path / "user", overwrite=True)


def test_install_rejects_a_linked_destination_without_touching_its_target(
    tmp_path: Path,
) -> None:
    mods = make_workspace(tmp_path, allow_mod_install=True)
    mods.scaffold("linked_destination", title="Linked destination", author="Test")
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"must remain unchanged")
    destination = tmp_path / "user" / "mods" / "repo" / "linked_destination.zip"
    destination.parent.mkdir(parents=True)
    try:
        destination.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable: {exc}")

    with pytest.raises(WorkspaceError, match=r"[Rr]eparse|[Ss]ymlink"):
        mods.install("linked_destination", tmp_path / "user", overwrite=True)
    assert outside.read_bytes() == b"must remain unchanged"


def test_install_stages_atomic_swap_and_preserves_recovery_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mods = make_workspace(tmp_path, allow_mod_install=True)
    mods.scaffold("recoverable", title="Recoverable", author="Test")
    user = tmp_path / "user"
    original = mods.install("recoverable", user)
    destination = Path(original.path)
    original_bytes = b"previous installed artifact"
    destination.write_bytes(original_bytes)
    original_replace = Path.replace

    def fail_install_swap(path: Path, target: Path) -> Path:
        if path.parent == destination.parent and path.name.endswith(".install.tmp"):
            raise OSError("simulated atomic swap failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_install_swap)

    with pytest.raises(WorkspaceError, match="simulated atomic swap failure"):
        mods.install("recoverable", user, overwrite=True)

    assert destination.read_bytes() == original_bytes
    backups = list(destination.parent.glob("recoverable.zip.backup-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original_bytes
    assert not list(destination.parent.glob("*.install.tmp"))
    assert not list(destination.parent.glob("*.backup.tmp"))


def test_install_restores_previous_file_if_post_swap_verification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mods = make_workspace(tmp_path, allow_mod_install=True)
    mods.scaffold("rollback", title="Rollback", author="Test")
    user = tmp_path / "user"
    destination = Path(mods.install("rollback", user).path)
    previous = b"previous installed artifact"
    destination.write_bytes(previous)
    stable_file = mods._stable_file

    def fail_new_destination(path: Path, **kwargs: object):
        if path == destination and path.read_bytes() != previous:
            raise WorkspaceError("simulated post-swap verification failure")
        return stable_file(path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(mods, "_stable_file", fail_new_destination)

    with pytest.raises(WorkspaceError, match="previous file was restored"):
        mods.install("rollback", user, overwrite=True)

    assert destination.read_bytes() == previous
    assert not list(destination.parent.glob("*.install.tmp"))
    assert not list(destination.parent.glob("*.backup.tmp"))
    assert not list(destination.parent.glob("rollback.zip.backup-*"))
    assert not list(destination.parent.glob("*.rollback.tmp"))


def test_install_preserves_concurrent_replacement_and_backup_during_rollback_race(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mods = make_workspace(tmp_path, allow_mod_install=True)
    mods.scaffold("raced_rollback", title="Raced rollback", author="Test")
    user = tmp_path / "user"
    destination = Path(mods.install("raced_rollback", user).path)
    previous = b"previous installed artifact"
    destination.write_bytes(previous)
    replacement_bytes = b"installed independently by another process"
    stable_file = mods._stable_file
    original_replace = Path.replace

    def fail_new_destination(path: Path, **kwargs: object):
        if path == destination and path.read_bytes() != previous:
            raise WorkspaceError("simulated post-swap verification failure")
        return stable_file(path, **kwargs)  # type: ignore[arg-type]

    def replace_destination_before_quarantine(path: Path, target: Path) -> Path:
        if path == destination and target.name.endswith(".rollback.tmp"):
            replacement = destination.with_name("other-process.zip.tmp")
            replacement.write_bytes(replacement_bytes)
            original_replace(replacement, destination)
        return original_replace(path, target)

    monkeypatch.setattr(mods, "_stable_file", fail_new_destination)
    monkeypatch.setattr(Path, "replace", replace_destination_before_quarantine)

    with pytest.raises(SafetyInterlockError, match="identity changed during quarantine"):
        mods.install("raced_rollback", user, overwrite=True)

    assert destination.read_bytes() == replacement_bytes
    backups = list(destination.parent.glob("raced_rollback.zip.backup-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == previous
    assert not list(destination.parent.glob("*.install.tmp"))
    assert not list(destination.parent.glob("*.backup.tmp"))
    assert not list(destination.parent.glob("*.rollback.tmp"))


def test_install_removes_new_file_if_post_swap_verification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mods = make_workspace(tmp_path, allow_mod_install=True)
    mods.scaffold("new_rollback", title="New rollback", author="Test")
    user = tmp_path / "user"
    destination = user / "mods" / "repo" / "new_rollback.zip"
    stable_file = mods._stable_file

    def fail_new_destination(path: Path, **kwargs: object):
        if path == destination:
            raise WorkspaceError("simulated post-swap verification failure")
        return stable_file(path, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(mods, "_stable_file", fail_new_destination)

    with pytest.raises(WorkspaceError, match="could not be verified"):
        mods.install("new_rollback", user)

    assert not destination.exists()
    assert not list(destination.parent.glob("*.install.tmp"))
    assert not list(destination.parent.glob("*.backup.tmp"))
    assert not list(destination.parent.glob("new_rollback.zip.backup-*"))
    assert not list(destination.parent.glob("*.rollback.tmp"))


def test_install_preserves_concurrent_replacement_if_new_file_verification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mods = make_workspace(tmp_path, allow_mod_install=True)
    mods.scaffold("raced_cleanup", title="Raced cleanup", author="Test")
    user = tmp_path / "user"
    destination = user / "mods" / "repo" / "raced_cleanup.zip"
    replacement_bytes = b"installed independently by another process"
    stable_file = mods._stable_file
    original_replace = Path.replace

    def fail_destination_verification(path: Path, **kwargs: object):
        if path == destination and "initial" in kwargs:
            raise WorkspaceError("simulated post-swap replacement race")
        return stable_file(path, **kwargs)  # type: ignore[arg-type]

    def replace_destination_before_quarantine(path: Path, target: Path) -> Path:
        if path == destination and target.name.endswith(".rollback.tmp"):
            replacement = destination.with_name("other-process.zip.tmp")
            replacement.write_bytes(replacement_bytes)
            original_replace(replacement, destination)
        return original_replace(path, target)

    monkeypatch.setattr(mods, "_stable_file", fail_destination_verification)
    monkeypatch.setattr(Path, "replace", replace_destination_before_quarantine)

    with pytest.raises(SafetyInterlockError, match=r"identity changed|refusing to remove"):
        mods.install("raced_cleanup", user)

    assert destination.read_bytes() == replacement_bytes
    assert not list(destination.parent.glob("*.install.tmp"))
    assert not list(destination.parent.glob("*.backup.tmp"))
    assert not list(destination.parent.glob("*.rollback.tmp"))
