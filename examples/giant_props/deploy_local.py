"""Sync the locked dist ZIPs into the local play profile, verifiably.

Usage (repo venv, from the repository root):

    python examples/giant_props/deploy_local.py            # report status, exit 1 if stale
    python examples/giant_props/deploy_local.py --deploy   # copy what is stale, verify, report

Scope: the REAL play profile's ``mods/`` root — the one place mods must live to
be playable (``%LOCALAPPDATA%\\BeamNG\\BeamNG.drive\\current\\mods``, overridable
by pointing ``GIANT_PROPS_PROFILE`` at a profile root, same semantics as
``build.py harvest``). This tool deliberately does NOT serve the sentinel test
profile; live gates install through the service (``mod_install``), which owns
backups and atomicity there.

What it enforces, in order:

1. A dist ZIP ships only if it byte-matches its own release lock
   (``dist/ericrolph_<key>.lock.json`` for giant props,
   ``repository/submission.json`` -> ``release_artifact.sha256`` for the cannon
   car wash). A dist that disagrees with its lock is a half-finished re-cut and
   must be finished, not deployed.
2. Deployment is a byte copy to the profile ``mods/`` ROOT under the stable ZIP
   filename, followed by a re-hash against the same lock. Nothing else is ever
   written: no backups parked under ``mods/`` (BeamNG mounts every zip below it
   recursively, so a stale copy shadows the release nondeterministically), no
   touching ``db.json``, ``repo/``, ``multiplayer/``, or any third-party zip.
3. The namespace shadow scan runs on CONTENT, never filename: every zip below
   ``mods/`` is opened and checked for members under ``vehicles/<mod_id>/`` or
   ``lua/ge/extensions/<mod_id>/`` claimed by a file other than the mod's own
   stable zip at the root.
4. The unpacked MCP bridge (``mods/unpacked/beamng_mcp/``) is compared against
   ``src/beamng_mcp/assets/beamng_mod/`` and its CODE files synced on
   ``--deploy``. ``settings/beamng_mcp.json`` is machine-local (auth token,
   port) and is never compared, reported, or written.
5. ``--deploy`` refuses to run while a BeamNG process is alive: the engine
   rescans ``mods/`` on its own schedule and a swap under a running game is an
   unverifiable state.

``cannon_car_wash_lowvram_ericrolph.zip`` is an alternate build of the same
namespace: it is never deployed by this tool, and its presence at the profile
root alongside the main zip is reported as a conflict (same-namespace zips
shadow each other).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACK_ROOT.parent.parent
CANNON_ROOT = REPO_ROOT / "examples" / "cannon_car_wash"
BRIDGE_SOURCE = REPO_ROOT / "src" / "beamng_mcp" / "assets" / "beamng_mod"
BRIDGE_LOCAL_ONLY = ("settings/beamng_mcp.json",)
LOWVRAM_ZIP = "cannon_car_wash_lowvram_ericrolph.zip"


def profile_mods_root() -> Path:
    override = os.environ.get("GIANT_PROPS_PROFILE")
    if override:
        return Path(os.path.expandvars(override)) / "mods"
    return (
        Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "BeamNG" / "BeamNG.drive" / "current" / "mods"
    )


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
    dist_zip: Path
    lock_sha256: str


def discover_releases() -> list[Release]:
    releases = []
    for child in sorted(PACK_ROOT.iterdir()):
        if not child.is_dir() or not (child / "spec.py").is_file():
            continue
        mod_id = f"ericrolph_{child.name}"
        dist_zip = child / "dist" / f"{child.name}_ericrolph.zip"
        lock_path = child / "dist" / f"{mod_id}.lock.json"
        if not dist_zip.is_file() or not lock_path.is_file():
            raise SystemExit(f"{child.name}: missing dist zip or lock — finish the re-cut first")
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        releases.append(Release(child.name, mod_id, dist_zip, lock["sha256"]))
    submission = json.loads(
        (CANNON_ROOT / "repository" / "submission.json").read_text(encoding="utf-8")
    )
    releases.append(
        Release(
            "cannon_car_wash",
            "ericrolph_cannon_car_wash",
            CANNON_ROOT / "dist" / submission["stable_zip_filename"],
            submission["release_artifact"]["sha256"],
        )
    )
    return releases


def shadow_scan(mods_root: Path, releases: list[Release]) -> list[str]:
    """Content-based namespace ownership check across every zip below mods/."""
    import zipfile

    owners = {release.mod_id: f"{release.key}_ericrolph.zip" for release in releases}
    prefixes = {
        mod_id: (f"vehicles/{mod_id}/", f"lua/ge/extensions/{mod_id}/") for mod_id in owners
    }
    findings = []
    for zip_path in sorted(mods_root.rglob("*.zip")):
        rel = zip_path.relative_to(mods_root).as_posix()
        try:
            names = zipfile.ZipFile(zip_path).namelist()
        except Exception as error:
            findings.append(f"unreadable zip in mods tree: {rel} ({error})")
            continue
        for mod_id, mod_prefixes in prefixes.items():
            if any(name.startswith(mod_prefixes) for name in names) and rel != owners[mod_id]:
                findings.append(f"{rel} ships {mod_id} but the owner is {owners[mod_id]}")
    return findings


def bridge_stale_files(mods_root: Path) -> list[str]:
    unpacked = mods_root / "unpacked" / "beamng_mcp"
    if not unpacked.is_dir():
        return [f"(bridge not installed at {unpacked})"]
    stale = []
    for source in sorted(BRIDGE_SOURCE.rglob("*")):
        if not source.is_file():
            continue
        rel = source.relative_to(BRIDGE_SOURCE).as_posix()
        if rel in BRIDGE_LOCAL_ONLY:
            continue
        target = unpacked / rel
        if not target.is_file() or sha256_file(target) != sha256_file(source):
            stale.append(rel)
    return stale


def beamng_is_running() -> bool:
    tasklist = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tasklist.exe"
    probe = subprocess.run(  # noqa: S603 - fixed system executable, static arguments
        [str(tasklist), "/FI", "IMAGENAME eq BeamNG.drive.x64.exe", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "BeamNG.drive.x64.exe" in probe.stdout


def main() -> None:
    deploy = "--deploy" in sys.argv[1:]
    mods_root = profile_mods_root()
    if not mods_root.is_dir():
        raise SystemExit(f"profile mods root does not exist: {mods_root}")
    releases = discover_releases()

    stale: list[Release] = []
    for release in releases:
        dist_sha = sha256_file(release.dist_zip)
        if dist_sha != release.lock_sha256:
            raise SystemExit(
                f"{release.key}: dist zip does not match its lock "
                f"({dist_sha[:12]} != {release.lock_sha256[:12]}) — "
                "finish the re-cut, do not deploy"
            )
        deployed = mods_root / release.dist_zip.name
        if not deployed.is_file() or sha256_file(deployed) != release.lock_sha256:
            stale.append(release)
            print(f"STALE   {release.key}: profile copy missing or differs from locked dist")
        else:
            print(f"current {release.key}")

    conflicts = shadow_scan(mods_root, releases)
    if (mods_root / LOWVRAM_ZIP).is_file() and (mods_root / releases[-1].dist_zip.name).is_file():
        conflicts.append(f"{LOWVRAM_ZIP} co-installed with the main cannon car wash zip")
    for finding in conflicts:
        print(f"CONFLICT {finding}")

    bridge_stale = bridge_stale_files(mods_root)
    for rel in bridge_stale:
        print(f"STALE   bridge: {rel}")

    if not deploy:
        if stale or conflicts or bridge_stale:
            raise SystemExit(1)
        print("profile is current")
        return

    if conflicts:
        raise SystemExit("resolve the conflicts above by hand before deploying")
    if beamng_is_running():
        raise SystemExit("BeamNG is running — close it before swapping zips")
    for release in stale:
        target = mods_root / release.dist_zip.name
        shutil.copyfile(release.dist_zip, target)
        if sha256_file(target) != release.lock_sha256:
            raise SystemExit(f"{release.key}: post-copy hash mismatch at {target}")
        print(f"deployed {release.key} ({release.lock_sha256[:12]}…, verified)")
        # The engine keeps whichever of source/cache is NEWER, and this
        # machine may have cooked the OLD zip after the new one was built —
        # hot_potato served a four-day-stale v1 .cdae over a current deploy
        # exactly that way (2026-08-29). The cache is derived state; deleting
        # it costs one re-cook on next load and closes the race completely.
        cache = mods_root.parent / "temp" / "vehicles" / release.mod_id
        if cache.is_dir():
            shutil.rmtree(cache)
            print(f"purged shape/texture cache for {release.key} ({cache})")
    unpacked = mods_root / "unpacked" / "beamng_mcp"
    for rel in bridge_stale:
        if rel.startswith("("):
            print(f"skipped bridge sync: {rel}")
            continue
        source = BRIDGE_SOURCE / rel
        target = unpacked / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha256_file(target) != sha256_file(source):
            raise SystemExit(f"bridge: post-copy hash mismatch at {target}")
        print(f"deployed bridge {rel} (verified; settings untouched)")
    print("profile is current")


if __name__ == "__main__":
    main()
