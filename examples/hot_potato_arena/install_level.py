"""Install Giant's Hearth for play: the REAL profile and the BeamMP client folder.

The level is NOT in ``examples/giant_props/deploy_local.py``'s release table (see the
README), so this is its installer. Two release archives ship together and both must be
present wherever the level is played:

* the level zip   ``dist_level/hot_potato_arena_level_ericrolph.zip``  (lock beside it)
* the arena zip   ``dist/hot_potato_arena_ericrolph.zip``               (lock beside it)

The Hot Potato prop mod (``hot_potato_ericrolph.zip``) is owned by ``deploy_local.py``; it is
REPORTED here against its release lock and never copied.

Default (no flags) is a report: for every target and release, the installed sha256 against
the lock - ``current`` / ``stale`` / ``missing``. ``--deploy`` copies what is stale or
missing (temp file, fsync, atomic replace, re-hash of the bytes on disk) and refuses while
the game or the BeamMP client is running, because the engine holds the zips open.

BeamMP's ``Resources/Client/mods.json`` is regenerated after any BeamMP change. Its
``lastwrite`` is a **Windows FILETIME** (100 ns ticks since 1601-01-01), not .NET ticks -
the value in the file the server wrote on 2026-09-08 equals ``mtime_ns // 100 +
116444736000000000`` exactly. The previous file is kept as ``mods.json.bak-<YYYYMMDD>``.

Generated text (``mods.json``) is written with ``newline="\\n"``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXAMPLE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_ROOT.parent.parent
LEVEL_ID = "ericrolph_hot_potato_arena"

#: (label, zip name, lock path, deployed by this tool?)
RELEASES: tuple[tuple[str, str, Path, bool], ...] = (
    (
        "level",
        "hot_potato_arena_level_ericrolph.zip",
        EXAMPLE_ROOT / "dist_level" / f"{LEVEL_ID}_level.lock.json",
        True,
    ),
    (
        "arena",
        "hot_potato_arena_ericrolph.zip",
        EXAMPLE_ROOT / "dist" / f"{LEVEL_ID}.lock.json",
        True,
    ),
    (
        "hot_potato",
        "hot_potato_ericrolph.zip",
        REPO_ROOT
        / "examples"
        / "giant_props"
        / "hot_potato"
        / "dist"
        / "ericrolph_hot_potato.lock.json",
        False,
    ),
)

FILETIME_EPOCH_OFFSET_100NS = 116444736000000000  # 1601-01-01 -> 1970-01-01
GAME_PROCESSES = ("BeamNG.drive.x64.exe", "BeamNG.drive.exe", "BeamMP-Launcher.exe")


class InstallError(RuntimeError):
    """The install cannot proceed safely."""


def real_profile_mods() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise InstallError("LOCALAPPDATA is not set; this installer is Windows-only")
    return Path(local) / "BeamNG" / "BeamNG.drive" / "current" / "mods"


def beammp_client_dir() -> Path:
    return Path(
        os.environ.get("HOT_POTATO_BEAMMP_CLIENT_DIR", r"C:\Users\ericr\Downloads\Resources\Client")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filetime_from_mtime_ns(mtime_ns: int) -> int:
    """Windows FILETIME (100 ns ticks since 1601-01-01 UTC) from a POSIX mtime in ns."""

    return mtime_ns // 100 + FILETIME_EPOCH_OFFSET_100NS


def read_lock(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise InstallError(f"release lock missing; cut the release first: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def release_rows() -> list[dict[str, Any]]:
    rows = []
    for label, zip_name, lock_path, deployable in RELEASES:
        lock = read_lock(lock_path)
        source = lock_path.parent / zip_name
        if not source.is_file():
            raise InstallError(f"release archive missing beside its lock: {source}")
        actual = sha256_file(source)
        if actual != lock["sha256"]:
            raise InstallError(
                f"{label}: dist archive does not match its lock ({actual[:16]} != "
                f"{lock['sha256'][:16]}); re-cut before installing"
            )
        rows.append(
            {
                "label": label,
                "zip": zip_name,
                "source": source,
                "sha256": lock["sha256"],
                "size": int(lock["size"]),
                "deployable": deployable,
            }
        )
    return rows


def classify(target_dir: Path, row: dict[str, Any]) -> dict[str, Any]:
    installed = target_dir / row["zip"]
    if not installed.is_file():
        return {"state": "missing", "installed_sha256": None}
    digest = sha256_file(installed)
    return {
        "state": "current" if digest == row["sha256"] else "stale",
        "installed_sha256": digest,
        "installed_size": installed.stat().st_size,
    }


def report(targets: dict[str, Path]) -> dict[str, Any]:
    rows = release_rows()
    out: dict[str, Any] = {"targets": {}, "releases": {r["label"]: r["sha256"] for r in rows}}
    for name, directory in targets.items():
        out["targets"][name] = {
            "dir": str(directory),
            "exists": directory.is_dir(),
            "releases": {
                r["label"]: {
                    "zip": r["zip"],
                    "deployable": r["deployable"],
                    **classify(directory, r),
                }
                for r in rows
            }
            if directory.is_dir()
            else {},
        }
    return out


def game_running() -> list[str]:
    if sys.platform != "win32":
        return []
    tasklist = shutil.which("tasklist") or str(
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tasklist.exe"
    )
    try:
        listing = subprocess.run(  # noqa: S603 - fixed system executable, static arguments
            [tasklist, "/FO", "CSV", "/NH"], capture_output=True, text=True, check=False
        ).stdout
    except OSError:
        return []
    names = {line.split('","')[0].strip('"') for line in listing.splitlines() if line}
    return sorted(n for n in GAME_PROCESSES if n in names)


def _copy_atomic(source: Path, destination: Path, expected_sha256: str) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle, source.open("rb") as inbound:
            for chunk in iter(lambda: inbound.read(1 << 20), b""):
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if sha256_file(temporary) != expected_sha256:
            raise InstallError(f"copy of {source.name} does not hash to its lock; not installed")
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return sha256_file(destination)


def regenerate_mods_json(client_dir: Path, *, backup: bool = True) -> dict[str, Any]:
    """Rewrite BeamMP's ``mods.json`` from every zip in the client folder."""

    path = client_dir / "mods.json"
    previous: dict[str, Any] = {}
    if path.is_file():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}
        if backup:
            stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
            backup_path = client_dir / f"mods.json.bak-{stamp}"
            if not backup_path.exists():
                backup_path.write_bytes(path.read_bytes())
    entries: dict[str, Any] = {}
    for zip_path in sorted(client_dir.glob("*.zip")):
        state = zip_path.stat()
        old = previous.get(zip_path.name, {}) if isinstance(previous, dict) else {}
        entries[zip_path.name] = {
            "filesize": state.st_size,
            "hash": sha256_file(zip_path),
            "lastwrite": filetime_from_mtime_ns(state.st_mtime_ns),
            "protected": bool(old.get("protected", False)),
        }
    path.write_text(json.dumps(entries, indent=4) + "\n", encoding="utf-8", newline="\n")
    return entries


def deploy(targets: dict[str, Path], *, beammp_name: str = "beammp") -> dict[str, Any]:
    running = game_running()
    if running:
        raise InstallError(f"refusing to deploy while the game holds the zips open: {running}")
    before = report(targets)
    actions: list[dict[str, Any]] = []
    rows = {r["label"]: r for r in release_rows()}
    touched_beammp = False
    for name, directory in targets.items():
        if not directory.is_dir():
            raise InstallError(f"target does not exist: {directory}")
        for label, state in before["targets"][name]["releases"].items():
            row = rows[label]
            if not row["deployable"] or state["state"] == "current":
                continue
            digest = _copy_atomic(row["source"], directory / row["zip"], row["sha256"])
            actions.append(
                {"target": name, "zip": row["zip"], "was": state["state"], "sha256": digest}
            )
            touched_beammp |= name == beammp_name
    mods_json = None
    if touched_beammp and beammp_name in targets:
        mods_json = regenerate_mods_json(targets[beammp_name])
    after = report(targets)
    return {"actions": actions, "mods_json": mods_json, "after": after}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--deploy", action="store_true", help="copy stale/missing releases (default: report only)"
    )
    parser.add_argument(
        "--profile-mods", type=Path, default=None, help="override the real profile mods root"
    )
    parser.add_argument(
        "--beammp-client", type=Path, default=None, help="override the BeamMP client folder"
    )
    parser.add_argument(
        "--regen-mods-json", action="store_true", help="rewrite BeamMP mods.json even with no copy"
    )
    arguments = parser.parse_args(argv)
    targets = {
        "profile": arguments.profile_mods or real_profile_mods(),
        "beammp": arguments.beammp_client or beammp_client_dir(),
    }
    try:
        if arguments.deploy:
            result = deploy(targets)
            if arguments.regen_mods_json and result["mods_json"] is None:
                result["mods_json"] = regenerate_mods_json(targets["beammp"])
        else:
            result = report(targets)
            if arguments.regen_mods_json:
                result["mods_json"] = regenerate_mods_json(targets["beammp"])
    except InstallError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
