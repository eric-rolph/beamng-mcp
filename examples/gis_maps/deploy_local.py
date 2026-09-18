"""Sync the locked map ZIPs into the local BeamNG play profile, verifiably.

Ported from the Giant Props pack's ``deploy_local.py`` and keeping its rules:

    python examples/gis_maps/deploy_local.py            # report status, exit 1 if anything is stale
    python examples/gis_maps/deploy_local.py --deploy   # copy what is stale, re-hash, report
    python examples/gis_maps/deploy_local.py --maps meteor_crater --deploy   # one map, not all six
    python examples/gis_maps/deploy_local.py --remove            # list what an uninstall deletes
    python examples/gis_maps/deploy_local.py --remove --confirm  # delete it
    python examples/gis_maps/deploy_local.py --verify            # what the game's log says per map

1. A dist ZIP ships only if it byte-matches its own lock
   (``examples/gis_maps/<key>/dist/ericrolph_<key>.lock.json``). A ZIP that disagrees with
   its lock is a half-finished build (or a bad rejoin) and must be finished, not deployed.
2. Deployment is a byte copy to the profile's ``mods/`` ROOT under the stable ZIP filename,
   then a re-hash against the same lock. Nothing else is written: no backups parked under
   ``mods/`` (BeamNG mounts every zip below it recursively, so a stale copy shadows the
   release), no touching ``db.json``, ``repo/``, ``multiplayer/`` or any third-party zip.
3. The namespace shadow scan runs on CONTENT, never filename: every zip below ``mods/``
   is opened and checked for members under ``levels/<mod_id>/`` claimed by a file other
   than the map's own stable zip at the root.
4. ``--deploy`` refuses to run while a BeamNG process is alive: the engine rescans
   ``mods/`` on its own schedule and a swap under a running game is an unverifiable state.
5. ``--remove`` is the uninstall, and it is content-based for the same reason as the shadow
   scan: it deletes every zip below ``mods/`` that claims one of the pack's
   ``levels/<mod_id>/`` namespaces, which is exactly the set that makes the level appear in
   the game, wherever it was copied from. A zip that also carries a level this pack does not
   own is reported and left alone, because deleting it would take somebody else's level with
   it. Nothing else is touched: no ``db.json`` edit, no cache purge. The engine notices the
   zip is gone on its next scan.

Removal does NOT need a local build: it works from each map's ``spec.py``, so it still
cleans up a profile whose ``dist/`` ZIPs have been deleted or were never built here.

``--verify`` answers "did it actually load?" from the profile's ``beamng.log`` instead of
from somebody looking at the level selector: a deployed ZIP the engine never mounted leaves
no trace of its ``levels/<mod_id>/`` namespace in that log. The engine owns that log's
wording, not this pack, so the check reports the lines it found and flags the ones carrying
an error word rather than asserting a verdict against a format we do not control. Read the
quoted lines, not just the exit code.

The profile root is ``%LOCALAPPDATA%\\BeamNG\\BeamNG.drive\\current`` (the ``current``
version folder; on 0.3x installs check that ``mods/`` lives there and not under a
versioned folder such as ``0.39``). Override with ``BEAMNG_MAPS_PROFILE=<profile root>``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parent


def profile_mods_root() -> Path:
    override = os.environ.get("BEAMNG_MAPS_PROFILE")
    if override:
        return Path(os.path.expandvars(override)) / "mods"
    local = os.environ.get("LOCALAPPDATA") or os.path.expandvars("%LOCALAPPDATA%")
    return Path(local) / "BeamNG" / "BeamNG.drive" / "current" / "mods"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Release:
    key: str
    mod_id: str
    display_name: str
    dist_zip: Path
    lock_sha256: str


def load_spec(key: str):
    loader = importlib.util.spec_from_file_location(
        f"gis_maps_deploy_spec_{key}", PACK_ROOT / key / "spec.py"
    )
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


@dataclass
class Mod:
    """A map's identity, readable without a local build (spec.py only)."""

    key: str
    mod_id: str
    display_name: str
    zip_basename: str


def map_keys() -> list[str]:
    return sorted(
        child.name
        for child in PACK_ROOT.iterdir()
        if child.is_dir() and (child / "spec.py").is_file()
    )


def discover_mods(keys: list[str] | None = None) -> list[Mod]:
    mods = []
    for key in map_keys():
        if keys is not None and key not in keys:
            continue
        spec = load_spec(key)
        mods.append(Mod(key, spec.MOD_ID, spec.DISPLAY_NAME, spec.ZIP_BASENAME))
    return mods


def discover_releases(keys: list[str] | None = None) -> list[Release]:
    releases = []
    for child in sorted(PACK_ROOT.iterdir()):
        if not child.is_dir() or not (child / "spec.py").is_file():
            continue
        if keys is not None and child.name not in keys:
            continue
        spec = load_spec(child.name)
        dist_zip = child / "dist" / spec.ZIP_BASENAME
        lock_path = child / "dist" / f"{spec.MOD_ID}.lock.json"
        if not dist_zip.is_file() or not lock_path.is_file():
            print(
                f"{child.name}: no dist zip + lock "
                "(build it, or rejoin delivered parts with join_parts.py)"
            )
            continue
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        releases.append(
            Release(child.name, spec.MOD_ID, spec.DISPLAY_NAME, dist_zip, lock["sha256"])
        )
    return releases


def shadow_scan(mods_root: Path, releases: list[Release]) -> list[str]:
    """Content-based namespace ownership check across every zip below mods/."""

    owners = {release.mod_id: release.dist_zip.name for release in releases}
    findings = []
    for path in sorted(mods_root.rglob("*.zip")):
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
        except (zipfile.BadZipFile, OSError):
            continue
        for mod_id, stable in owners.items():
            if any(name.startswith(f"levels/{mod_id}/") for name in names):
                if path.parent != mods_root or path.name != stable:
                    findings.append(
                        f"{path.relative_to(mods_root)} also carries levels/{mod_id}/ "
                        f"(owner: {stable} at the mods root)"
                    )
    return findings


def level_namespaces(path: Path) -> set[str]:
    """The ``levels/<name>/`` namespaces a zip claims, by content."""

    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except (zipfile.BadZipFile, OSError):
        return set()
    found = set()
    for name in names:
        parts = name.split("/")
        if len(parts) > 2 and parts[0] == "levels" and parts[1]:
            found.add(parts[1])
    return found


def removal_plan(
    mods_root: Path, selected: list[Mod]
) -> tuple[list[tuple[Path, set[str]]], list[str]]:
    """Zips below mods/ that carry a selected map, and the ones too mixed to delete.

    A zip is removable only when EVERY level it carries was selected. A zip that also
    carries a level the caller did not name - somebody else's, or one of ours held back
    by ``--maps`` - would be collateral damage, so it is reported instead of deleted.
    The pack ships one level per zip, so this only ever fires on a hand-made bundle.
    """

    wanted = {mod.mod_id for mod in selected}
    removable: list[tuple[Path, set[str]]] = []
    refused: list[str] = []
    for path in sorted(mods_root.rglob("*.zip")):
        carried = level_namespaces(path)
        hit = carried & wanted
        if not hit:
            continue
        extra = carried - wanted
        if extra:
            refused.append(
                f"{path.relative_to(mods_root)} carries {', '.join(sorted(hit))} "
                f"but also {', '.join(sorted(extra))}, which you did not ask to remove; "
                "delete it by hand or widen --maps"
            )
            continue
        removable.append((path, carried))
    return removable, refused


def remove(mods_root: Path, selected: list[Mod], *, confirm: bool) -> int:
    removable, refused = removal_plan(mods_root, selected)
    for finding in refused:
        print(f"SKIP: {finding}")
    if not removable:
        print("nothing installed to remove" if not refused else "nothing removable")
        return 1 if refused else 0
    verb = "removing" if confirm else "would remove"
    for path, carried in removable:
        print(f"{verb} {path.relative_to(mods_root)} ({', '.join(sorted(carried))})")
    if not confirm:
        print("re-run with --confirm to delete these files")
        return 1
    if beamng_running():
        print("refusing to remove while BeamNG is running; close the game and re-run")
        return 1
    for path, _ in removable:
        path.unlink()
    print(
        "removed; the levels are gone from Freeroam > Select Level on the next launch. "
        "Nothing else in the profile was touched."
    )
    return 1 if refused else 0


ERROR_WORDS = ("error", "failed", "failure", "missing", "not found", "invalid", "corrupt")


def profile_log(mods_root: Path) -> Path:
    return mods_root.parent / "beamng.log"


def verify(mods_root: Path, selected: list[Mod]) -> int:
    """Report, per map, what the game's own log says about the level's namespace."""

    log_path = profile_log(mods_root)
    if not log_path.is_file():
        print(f"no log at {log_path}: launch BeamNG.drive once, then re-run --verify")
        return 1
    text = log_path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines()]
    problems = 0
    for mod in selected:
        hits = [line for line in lines if mod.mod_id in line or mod.zip_basename in line]
        if not hits:
            installed = (mods_root / mod.zip_basename).is_file()
            print(
                f"{mod.key}: the log never mentions {mod.mod_id}"
                + (
                    " although its ZIP is in mods/ (the engine has not rescanned: relaunch it)"
                    if installed
                    else " and its ZIP is not in mods/ (install it first)"
                )
            )
            problems += 1
            continue
        bad = [line for line in hits if any(word in line.lower() for word in ERROR_WORDS)]
        print(f"{mod.key}: {len(hits)} log line(s) mention {mod.mod_id} ({mod.display_name})")
        for line in (bad or hits)[-3:]:
            print(f"    {line[:200]}")
        if bad:
            print(f"  {len(bad)} of them carry an error word; read them above")
            problems += 1
    return 1 if problems else 0


def beamng_running() -> bool:
    if os.environ.get("BEAMNG_MAPS_ALLOW_RUNNING"):
        return False
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq BeamNG.drive.x64.exe"],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
            ).stdout
            return "BeamNG.drive.x64.exe" in out
        out = subprocess.run(
            ["pgrep", "-fl", "BeamNG.drive"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return bool(out.strip())
    except OSError:
        return False


def parse_maps(argv: list[str]) -> list[str] | None:
    """``--maps a b c`` -> the keys; absent -> None, meaning every map in the pack."""

    if "--maps" not in argv:
        return None
    keys = []
    for arg in argv[argv.index("--maps") + 1 :]:
        if arg.startswith("-"):
            break
        keys.append(arg)
    known = map_keys()
    unknown = [key for key in keys if key not in known]
    if unknown or not keys:
        complaint = f"unknown map key(s): {', '.join(unknown)}" if unknown else "no keys given"
        raise SystemExit(f"--maps: {complaint}; known keys: {', '.join(known)}")
    return keys


def main(argv: list[str]) -> int:
    deploy = "--deploy" in argv
    keys = parse_maps(argv)
    mods_root = profile_mods_root()
    print(f"profile mods root: {mods_root}")
    if not mods_root.is_dir():
        print(
            "  not found: is BeamNG installed and has it been launched once? "
            "(or set BEAMNG_MAPS_PROFILE)"
        )
        return 1
    if "--remove" in argv:
        return remove(mods_root, discover_mods(keys), confirm="--confirm" in argv)
    if "--verify" in argv:
        return verify(mods_root, discover_mods(keys))
    releases = discover_releases(keys)
    if not releases:
        print("nothing to deploy")
        return 1
    problems = 0
    stale: list[Release] = []
    for release in releases:
        local_sha = sha256_file(release.dist_zip)
        if local_sha != release.lock_sha256:
            print(
                f"{release.key}: dist zip does not match its lock "
                f"({local_sha[:12]} != {release.lock_sha256[:12]}); not deployable"
            )
            problems += 1
            continue
        target = mods_root / release.dist_zip.name
        if target.is_file() and sha256_file(target) == release.lock_sha256:
            print(f"{release.key}: current ({release.display_name})")
        else:
            state = "stale" if target.is_file() else "missing"
            print(f"{release.key}: {state} -> {target.name}")
            stale.append(release)
    for finding in shadow_scan(mods_root, releases):
        print(f"CONFLICT: {finding}")
        problems += 1
    if not deploy:
        return 1 if (stale or problems) else 0
    if problems:
        print("refusing to deploy while conflicts or lock mismatches stand")
        return 1
    if beamng_running():
        print("refusing to deploy while BeamNG is running; close the game and re-run")
        return 1
    for release in stale:
        target = mods_root / release.dist_zip.name
        shutil.copyfile(release.dist_zip, target)
        if sha256_file(target) != release.lock_sha256:
            print(f"{release.key}: copy verification FAILED, removing {target.name}")
            target.unlink(missing_ok=True)
            return 1
        print(
            f"{release.key}: deployed {target.name} "
            f"({target.stat().st_size / 1e6:.1f} MB, sha256 verified)"
        )
    print(
        "done: launch BeamNG.drive -> Freeroam -> Select Level; "
        "the maps appear under their display names"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
