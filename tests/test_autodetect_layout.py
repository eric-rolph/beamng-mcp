from __future__ import annotations

from pathlib import Path

import pytest

from beamng_mcp.autodetect import detect_installation, find_home, find_user
from beamng_mcp.config import Settings


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


def test_configured_binary_is_authoritative_when_drive_and_tech_both_exist(
    tmp_path: Path,
) -> None:
    home = tmp_path / "BeamNG.drive"
    drive = home / "Bin64" / "BeamNG.drive.x64.exe"
    tech = home / "Bin64" / "BeamNG.tech.x64.exe"
    drive.parent.mkdir(parents=True)
    drive.touch()
    tech.touch()
    settings = Settings(
        beamng={
            "home": home,
            "binary": Path("Bin64/BeamNG.tech.x64.exe"),
            "user": tmp_path / "user",
        }
    )

    installation = detect_installation(settings)

    assert installation.home == home.resolve()
    assert installation.executable == tech.resolve()


def test_absolute_configured_binary_can_define_a_nonstandard_installation(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "CustomBeamNG" / "custom-drive.exe"
    binary.parent.mkdir()
    binary.touch()
    settings = Settings(
        beamng={
            "binary": binary,
            "user": tmp_path / "user",
        }
    )

    installation = detect_installation(settings)

    assert installation.executable == binary.resolve()


def test_invalid_explicit_home_never_falls_back_to_another_installation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    requested = tmp_path / "requested-but-invalid"
    other_root = tmp_path / "SteamLibrary"
    other_binary = other_root / "steamapps" / "common" / "BeamNG.drive" / "Bin64"
    other_binary.mkdir(parents=True)
    (other_binary / "BeamNG.drive.x64.exe").touch()
    monkeypatch.setattr("beamng_mcp.autodetect._steam_roots", lambda: [other_root])

    assert find_home(requested) is None

    settings = Settings(beamng={"home": requested, "user": tmp_path / "user"})
    installation = detect_installation(settings)
    assert installation.home is None
    assert installation.executable is None
