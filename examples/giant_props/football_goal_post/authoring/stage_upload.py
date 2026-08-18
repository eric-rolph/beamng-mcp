"""Collect everything a beamng.com submission needs into one folder.

The pieces are produced by three different stages — the Blender generator
writes the selector card and the gallery, make_resource_icon.py draws the
badge, build.py writes the ZIP — and the failure mode when uploading is
not "a file is missing", it is "a file is STALE": last week's gallery next
to this week's ZIP, and nobody can tell by looking.

So this stages copies and then reports the build serial and each asset's
age against the ZIP, refusing to stage anything it cannot find. Run it
last, after the generator, the icon script and `build.py <key> all`:

    ./.venv/Scripts/python.exe \
        examples/giant_props/football_goal_post/authoring/stage_upload.py

AND THE GUARD THAT SAYING "RUN IT LAST" DOES NOT GIVE YOU (round 5). On
2026-08-15 this staged serial 27 at 18:52 and the tab-membrane fix landed
as serial 28 at 20:52. Nobody re-ran it. `dist/upload/` — the folder the
owner actually publishes from — then held, for two hours, exactly the
defective build the round existed to remove, and NOTHING SAID SO: every
check in here compares assets against whichever ZIP is sitting in
`dist/`, and a stale STAGE is invisible to all of them because it is
never a party to the comparison. A guard that only ever looks forward
cannot see the run that did not happen.

So the staged ZIP is now verified against
`dist/<mod_id>.lock.json`'s recorded sha256, after copying, by reading
the bytes back off disk. That number is written by build.py at build
time and is the only thing in the tree that knows what the current build
IS rather than how old it is. If they disagree the stage is wrong and
this exits non-zero instead of printing a reassuring summary.

AND SHOUTING IS NOT ENOUGH — STAGE, THEN PROMOTE (round 6). The first
cut of that guard copied first and compared afterwards, so on a mismatch
it exited 1 with `dist/upload/` sitting there FULLY POPULATED with the
ZIP it had just refused. B-1 was, in its own words, "the folder the
owner publishes from held the defective build"; a guard that leaves the
poison in the publish folder and prints a warning is one step short of
fixing it, because the folder outlives the terminal window. Everything
is therefore assembled in `dist/upload.pending/` and promoted to
`dist/upload/` only after the sha256 matches. THE INVARIANT IS THAT
`dist/upload/` EITHER MATCHES THE LOCK OR DOES NOT EXIST: any failure
path removes the pending directory AND any previous `dist/upload/`,
because if this run cannot prove what the current build is, neither can
a folder left over from an older one.

WHAT THE HARD GATE COVERS. The sha256 gate is only as wide as the lock,
and the lock knows about one file — the ZIP. The other assets have no
recorded hash anywhere, so their only handle is age, and the thing that
actually went stale in B-1 (the gallery) was on the soft side of that
line. Age is a real gate for the art the GENERATOR writes — the
thumbnail and the gallery shots are written seconds after the DAE by the
same run, so they cannot legitimately predate it — and those are now
hard failures. `listing_copy.md` and the icon come from other tools and
are legitimately older, so those stay warnings.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLE_ROOT = HERE.parent
MOD_ID = "ericrolph_football_goal_post"
ZIP_NAME = "football_goal_post_ericrolph.zip"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    stage = EXAMPLE_ROOT / "dist" / "upload"
    pending = EXAMPLE_ROOT / "dist" / "upload.pending"
    try:
        stage_into(pending)
    except BaseException:
        # THE FAILURE PATH OWNS THE PUBLISH FOLDER. Nothing survives a run
        # that could not prove what it staged, including whatever an
        # earlier run left behind.
        for doomed in (pending, stage):
            if doomed.exists():
                shutil.rmtree(doomed)
                print(f"removed {doomed} — nothing here is publishable")
        raise
    if stage.exists():
        shutil.rmtree(stage)
    pending.rename(stage)
    print(f"promoted {pending.name} -> {stage}")


def stage_into(stage: Path) -> None:
    zip_path = EXAMPLE_ROOT / "dist" / ZIP_NAME
    if not zip_path.is_file():
        raise SystemExit(f"no dist ZIP at {zip_path} — run build.py <key> all")
    if stage.exists():
        shutil.rmtree(stage)
    (stage / "gallery").mkdir(parents=True)

    required = [
        (zip_path, stage / ZIP_NAME, False),
        (HERE / "resource_icon_96.png", stage / "resource_icon_96.png", False),
        (HERE / "listing_copy.md", stage / "listing_copy.md", False),
        # Generator-written art: same run as the DAE, so age is a hard gate.
        (HERE / f"{MOD_ID}_thumbnail.jpg",
         stage / "selector_card_500x281.jpg", True),
    ]
    gallery = sorted((HERE / "listing").glob("*.jpg"))
    if not gallery:
        raise SystemExit("no gallery renders — run the Blender generator")
    required += [(shot, stage / "gallery" / shot.name, True)
                 for shot in gallery]

    # AGE IS MEASURED AGAINST THE GEOMETRY, NOT THE ZIP. The warning's own
    # words are "possibly built from different geometry", and the geometry
    # is the DAE — the ZIP is packed minutes later by a separate command.
    # Against the ZIP this cried wolf on 12 of 13 assets on the serial-28
    # stage: the thumbnail and all nine gallery shots are written 7-8 s
    # AFTER the DAE by the same generator run, and then land 3 minutes
    # before the ZIP, so a 60 s slack marked every one of them suspect. A
    # warning that fires on every build is how a real one gets skipped
    # past — which is the same disease as B-1, one layer down. Against the
    # DAE the only two that warn are the two that genuinely predate the
    # geometry, and that is worth reading.
    #
    # NO SILENT FALLBACK. This used to read `reference if reference.is_file()
    # else zip_path`, which meant a missing mod-tree DAE quietly re-armed the
    # cry-wolf behaviour the paragraph above exists to remove — every asset
    # suspect, on a line that reads exactly like a healthy run. If the
    # geometry is not there the baseline is not there, and that is a failure,
    # not a fallback.
    baseline = EXAMPLE_ROOT / "mod" / "vehicles" / MOD_ID / f"{MOD_ID}.dae"
    if not baseline.is_file():
        raise SystemExit(
            f"no geometry at {baseline} — asset ages have nothing to be "
            "measured against; run the Blender generator")
    baseline_mtime = baseline.stat().st_mtime
    stale = []
    outdated_art = []
    for source, target, hard in required:
        if not source.is_file():
            raise SystemExit(f"missing asset: {source}")
        shutil.copyfile(source, target)
        # A whole minute of slack: the generator, the icon and the ZIP are
        # separate runs and are never going to share a timestamp.
        if source.stat().st_mtime < baseline_mtime - 60:
            (outdated_art if hard else stale).append(source.name)
    if outdated_art:
        raise SystemExit(
            "generator-written art predates the geometry, so it shows an "
            f"older build: {', '.join(outdated_art)} (older than "
            f"{baseline.name}). Re-run the Blender generator; do not upload.")

    serial = "unknown"
    manifest = EXAMPLE_ROOT / "dist" / f"{MOD_ID}.serial.json"
    if manifest.is_file():
        serial = json.loads(manifest.read_text()).get("serial", serial)

    # THE THREE LINES THAT WOULD HAVE CAUGHT ROUND 5's B-1. Read the staged
    # bytes back and hold them against the lock, not against a timestamp.
    lock_path = EXAMPLE_ROOT / "dist" / f"{MOD_ID}.lock.json"
    if not lock_path.is_file():
        raise SystemExit(
            f"no lock file at {lock_path} — run build.py <key> all")
    lock = json.loads(lock_path.read_text())
    staged_sha = sha256_of(stage / ZIP_NAME)
    if staged_sha != lock["sha256"]:
        raise SystemExit(
            f"staged ZIP does not match the lock — staged {staged_sha}, "
            f"lock {lock['sha256']} (build serial "
            f"{lock.get('build_serial')}). This stage is not the current "
            "build and is being deleted rather than published."
        )

    publish = EXAMPLE_ROOT / "dist" / "upload"
    print(f"staged {len(required)} files for {publish}")
    print(f"  sha256 matches {lock_path.name}: {staged_sha}")
    print(f"  ZIP {zip_path.name}: build serial {serial}, "
          f"{zip_path.stat().st_size:,} bytes")
    print(f"  gallery: {len(gallery)} shots")
    if stale:
        print(f"  WARNING — older than {baseline.name}, so possibly built "
              "from different geometry:")
        for name in stale:
            print(f"    {name}")
    else:
        print(f"  every asset is at least as new as {baseline.name}")


if __name__ == "__main__":
    main()
