from __future__ import annotations

import json
from pathlib import Path

import pytest

from beamng_mcp.config import WorkspaceSettings
from beamng_mcp.errors import ConflictError, WorkspaceError
from beamng_mcp.services.mods import ModWorkspace
from beamng_mcp.services.staging import AssetStagingInbox


def request_contract() -> dict[str, object]:
    return {"schema": "test-stage-request-v1"}


def make_workspace(tmp_path: Path) -> ModWorkspace:
    return ModWorkspace(
        WorkspaceSettings(
            root=tmp_path / "workspace",
            max_file_bytes=1024 * 1024,
        )
    )


def test_asset_stage_is_fixed_path_hash_bound_and_single_use(tmp_path: Path) -> None:
    mods = make_workspace(tmp_path)
    inbox = AssetStagingInbox(mods)
    stage = inbox.create(
        mod_name="crusher_mod",
        asset_name="crusher_body",
        visual_format="dae",
        helper_source=b"# helper\n",
        runner_source=b"# runner\n",
        request_contract=request_contract(),
    )

    manifest = b'{"schema_version":"beamng-structure-v1"}\n'
    visual = b"<COLLADA/>\n"
    stage.manifest.write_bytes(manifest)
    stage.visual.write_bytes(visual)

    data = inbox.read(stage.slot_id)
    assert data.mod_name == "crusher_mod"
    assert data.asset_name == "crusher_body"
    assert data.visual_bytes == visual
    assert data.visual_size == len(visual)
    assert len(data.visual_sha256) == 64

    inbox.consume(stage.slot_id, manifest_sha256=data.manifest_sha256)
    with pytest.raises(ConflictError, match="already been consumed"):
        inbox.read(stage.slot_id)


def test_asset_stage_rejects_unexpected_or_linked_outputs(tmp_path: Path) -> None:
    inbox = AssetStagingInbox(make_workspace(tmp_path))
    stage = inbox.create(
        mod_name="ramp_mod",
        asset_name="ramp",
        visual_format="dae",
        helper_source=b"# helper\n",
        runner_source=b"# runner\n",
        request_contract=request_contract(),
    )
    stage.manifest.write_text("{}\n", encoding="utf-8")
    stage.visual.write_text("<COLLADA/>\n", encoding="utf-8")
    unexpected = stage.directory / "surprise.bin"
    unexpected.write_bytes(b"no")

    with pytest.raises(WorkspaceError, match="unexpected files"):
        inbox.read(stage.slot_id)

    unexpected.unlink()
    stage.visual.unlink()
    target = tmp_path / "outside.dae"
    target.write_text("outside\n", encoding="utf-8")
    try:
        stage.visual.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable: {exc}")
    with pytest.raises(WorkspaceError, match=r"reparse|regular file"):
        inbox.read(stage.slot_id)


def test_asset_stage_rejects_expired_metadata(tmp_path: Path) -> None:
    inbox = AssetStagingInbox(make_workspace(tmp_path))
    stage = inbox.create(
        mod_name="pendulum_mod",
        asset_name="pendulum",
        visual_format="dae",
        helper_source=b"# helper\n",
        runner_source=b"# runner\n",
        request_contract=request_contract(),
    )
    metadata = json.loads(stage.metadata.read_text(encoding="utf-8"))
    metadata["expires_at"] = "2000-01-01T00:00:00+00:00"
    stage.metadata.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ConflictError, match="server-side binding"):
        inbox.read(stage.slot_id)


@pytest.mark.parametrize("reviewed_file", ("helper", "runner"))
def test_asset_stage_rejects_modified_reviewed_blender_code(
    reviewed_file: str,
    tmp_path: Path,
) -> None:
    inbox = AssetStagingInbox(make_workspace(tmp_path))
    stage = inbox.create(
        mod_name="bound_mod",
        asset_name="bound_asset",
        visual_format="dae",
        helper_source=b"# reviewed helper\n",
        runner_source=b"# generated runner\n",
        request_contract={"asset_id": "bound_asset", "transform": "identity"},
    )
    stage.manifest.write_text("{}\n", encoding="utf-8")
    stage.visual.write_text("<COLLADA/>\n", encoding="utf-8")
    getattr(stage, reviewed_file).write_text("# modified\n", encoding="utf-8")

    with pytest.raises(ConflictError, match="helper or generated runner was modified"):
        inbox.read(stage.slot_id)


def test_asset_stage_uses_the_server_bound_request_not_writable_metadata(tmp_path: Path) -> None:
    inbox = AssetStagingInbox(make_workspace(tmp_path))
    expected_contract = {
        "asset_id": "bound_asset",
        "physics_cage": "bound_asset_cage",
        "world_to_beamng": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
    }
    stage = inbox.create(
        mod_name="bound_mod",
        asset_name="bound_asset",
        visual_format="dae",
        helper_source=b"# reviewed helper\n",
        runner_source=b"# generated runner\n",
        request_contract=expected_contract,
    )
    stage.manifest.write_text("{}\n", encoding="utf-8")
    stage.visual.write_text("<COLLADA/>\n", encoding="utf-8")

    staged = inbox.read(stage.slot_id)

    assert staged.request_contract == expected_contract
    assert "request_contract" not in json.loads(stage.metadata.read_text(encoding="utf-8"))


def test_asset_stage_caps_active_slots_and_prunes_consumed_slots(tmp_path: Path) -> None:
    mods = ModWorkspace(
        WorkspaceSettings(
            root=tmp_path / "workspace",
            max_file_bytes=1024 * 1024,
            max_asset_staging_slots=1,
        )
    )
    inbox = AssetStagingInbox(mods)
    first = inbox.create(
        mod_name="stage_mod",
        asset_name="stage_asset",
        visual_format="dae",
        helper_source=b"# helper\n",
        runner_source=b"# runner\n",
        request_contract=request_contract(),
    )
    with pytest.raises(WorkspaceError, match="slot limit"):
        inbox.create(
            mod_name="other_mod",
            asset_name="other_asset",
            visual_format="dae",
            helper_source=b"# helper\n",
            runner_source=b"# runner\n",
            request_contract=request_contract(),
        )

    inbox.consume(first.slot_id, manifest_sha256="0" * 64)
    second = inbox.create(
        mod_name="other_mod",
        asset_name="other_asset",
        visual_format="dae",
        helper_source=b"# helper\n",
        runner_source=b"# runner\n",
        request_contract=request_contract(),
    )
    assert second.directory.is_dir()
    assert not first.directory.exists()


def test_mod_bundle_supports_binary_assets_and_requires_explicit_overwrite(
    tmp_path: Path,
) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("softbody_mod", title="Soft Body", author="Test", kind="vehicle")
    first = mods.write_bundle(
        "softbody_mod",
        {
            "vehicles/softbody_mod/softbody_mod.dae": b"\x00dae-v1\n",
            "vehicles/softbody_mod/softbody_mod.jbeam": b"{}\n",
        },
    )
    assert [item.path for item in first] == [
        "vehicles/softbody_mod/softbody_mod.dae",
        "vehicles/softbody_mod/softbody_mod.jbeam",
    ]

    with pytest.raises(ConflictError, match="overwrite=true"):
        mods.write_bundle(
            "softbody_mod",
            {"vehicles/softbody_mod/softbody_mod.dae": b"\x00dae-v2\n"},
        )

    updated = mods.write_bundle(
        "softbody_mod",
        {"vehicles/softbody_mod/softbody_mod.dae": b"\x00dae-v2\n"},
        overwrite=True,
        expected_sha256={first[0].path: first[0].sha256},
    )
    assert updated[0].sha256 != first[0].sha256


def test_mod_bundle_overwrite_is_compare_and_swap_for_every_expected_file(
    tmp_path: Path,
) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("cas_mod", title="CAS", author="Test", kind="vehicle")
    path = "vehicles/cas_mod/cas_mod.jbeam"
    original = b'{"version":1}\n'
    mods.write_bundle("cas_mod", {path: original})

    with pytest.raises(ConflictError, match="hash mismatch"):
        mods.write_bundle(
            "cas_mod",
            {path: b'{"version":2}\n'},
            overwrite=True,
            expected_sha256={path: "0" * 64},
        )

    content, _info = mods.read_file("cas_mod", path)
    assert content.encode() == original


def test_mod_bundle_restores_every_previous_file_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mods = make_workspace(tmp_path)
    mods.scaffold("rollback_mod", title="Rollback", author="Test", kind="vehicle")
    paths = {
        "vehicles/rollback_mod/one.jbeam": b'{"version":1}\n',
        "vehicles/rollback_mod/two.jbeam": b'{"version":1}\n',
    }
    mods.write_bundle("rollback_mod", paths)
    existing = {
        item.path: item.sha256 for item in mods.list_files("rollback_mod") if item.path in paths
    }
    original_replace = Path.replace
    injected = False

    def fail_second_staged_replace(source: Path, target: Path) -> Path:
        nonlocal injected
        if (
            not injected
            and source.name.endswith(".bundle.tmp")
            and Path(target).name == "two.jbeam"
        ):
            injected = True
            raise OSError("injected bundle commit failure")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_second_staged_replace)
    with pytest.raises(OSError, match="injected bundle commit failure"):
        mods.write_bundle(
            "rollback_mod",
            {path: b'{"version":2}\n' for path in paths},
            overwrite=True,
            expected_sha256=existing,
        )

    assert injected is True
    for path, expected in paths.items():
        content, _info = mods.read_file("rollback_mod", path)
        assert content.encode() == expected
