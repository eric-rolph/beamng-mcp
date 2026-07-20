from __future__ import annotations

from pathlib import Path

import pytest

from beamng_mcp.autodetect import find_user


def test_post_037_user_folder_uses_current_layout_before_first_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert find_user("0.38") == (tmp_path / "BeamNG" / "BeamNG.drive" / "current").resolve()


def test_legacy_user_folder_remains_versioned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert find_user("0.36") == (tmp_path / "BeamNG.drive" / "0.36").resolve()


def test_explicit_user_folder_wins_over_layout_detection(tmp_path: Path) -> None:
    explicit = tmp_path / "dedicated-beamng-user"

    assert find_user("0.38", explicit) == explicit.resolve()


@pytest.mark.parametrize("configured", ["D:/BeamNG User", "custom/user"])
def test_post_037_user_folder_honors_launcher_ini(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, configured: str
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    launcher = tmp_path / "BeamNG" / "BeamNG.drive.ini"
    launcher.parent.mkdir(parents=True)
    launcher.write_text(
        f"version = 0.38.6.0\nuserFolder = {configured}\n",
        encoding="utf-8",
    )
    expected = Path(configured)
    if not expected.is_absolute():
        expected = launcher.parent / expected

    assert find_user("0.38") == expected.resolve()


def test_empty_launcher_override_uses_default_current_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    launcher = tmp_path / "BeamNG" / "BeamNG.drive.ini"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("userFolder =\n", encoding="utf-8")

    assert find_user("0.38") == (tmp_path / "BeamNG" / "BeamNG.drive" / "current").resolve()
