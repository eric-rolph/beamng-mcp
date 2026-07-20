"""Conservative BeamNG installation discovery for Windows."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .config import Settings


@dataclass(frozen=True, slots=True)
class Installation:
    home: Path | None
    user: Path
    executable: Path | None
    version: str


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            roots.append(Path(steam_path))
    except (ImportError, OSError):
        pass

    for drive in "CDEFGHI":
        roots.extend(
            [
                Path(f"{drive}:/SteamLibrary"),
                Path(f"{drive}:/Program Files (x86)/Steam"),
                Path(f"{drive}:/Program Files/Steam"),
            ]
        )
    return list(dict.fromkeys(roots))


def find_home(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        candidates = [explicit.expanduser()]
    elif os.getenv("BNG_HOME"):
        candidates = [Path(os.environ["BNG_HOME"]).expanduser()]
    else:
        candidates = [root / "steamapps" / "common" / "BeamNG.drive" for root in _steam_roots()]

    executable_names = (
        Path("Bin64/BeamNG.drive.x64.exe"),
        Path("Bin64/BeamNG.tech.x64.exe"),
    )
    for candidate in candidates:
        if any((candidate / executable).is_file() for executable in executable_names):
            return candidate.resolve()
    return None


def find_user(version: str, explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    local_app_data = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    try:
        version_parts = tuple(int(part) for part in version.split(".")[:2])
    except ValueError:
        version_parts = (0, 0)
    if version_parts >= (0, 37):
        launcher_root = local_app_data / "BeamNG"
        launcher_ini = launcher_root / "BeamNG.drive.ini"
        configured = _launcher_user_folder(launcher_ini)
        if configured is not None:
            return configured
        # BeamNG 0.37 migrated the default Windows user root away from the
        # legacy versioned `BeamNG.drive/<version>` layout. The launcher now
        # records the active version separately and runs the game from
        # `BeamNG/BeamNG.drive/current`, including before a new install has
        # created that directory for the first time.
        target = launcher_root / "BeamNG.drive" / "current"
    else:
        target = local_app_data / "BeamNG.drive" / version
    return target.resolve()


def _launcher_user_folder(launcher_ini: Path) -> Path | None:
    """Read BeamNG's sectionless post-0.37 launcher INI without guessing an encoding."""

    try:
        content = launcher_ini.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        return None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if key.strip().casefold() != "userfolder":
            continue
        value = raw_value.strip().strip('"')
        if not value or "\x00" in value:
            return None
        configured = Path(value).expanduser()
        if not configured.is_absolute():
            configured = launcher_ini.parent / configured
        return configured.resolve()
    return None


def detect_installation(settings: Settings) -> Installation:
    user = find_user(settings.beamng.target_version, settings.beamng.user)
    executable = None
    configured_binary = settings.beamng.binary
    configured_home = (
        settings.beamng.home.expanduser().resolve() if settings.beamng.home is not None else None
    )
    home: Path | None
    candidate: Path | None
    if configured_binary is not None:
        expanded_binary = configured_binary.expanduser()
        if expanded_binary.is_absolute():
            candidate = expanded_binary.resolve()
            if configured_home is not None:
                home = configured_home
            elif candidate.parent.name.casefold() == "bin64":
                home = candidate.parent.parent
            else:
                home = candidate.parent
        else:
            home = configured_home or find_home(None)
            candidate = (home / expanded_binary).resolve() if home is not None else None
        if candidate is not None and candidate.is_file():
            executable = candidate
    else:
        home = find_home(settings.beamng.home)
    if configured_binary is None and home is not None:
        for relative in ("Bin64/BeamNG.drive.x64.exe", "Bin64/BeamNG.tech.x64.exe"):
            candidate = home / relative
            if candidate.is_file():
                executable = candidate.resolve()
                break
    return Installation(
        home=home,
        user=user,
        executable=executable,
        version=settings.beamng.target_version,
    )
