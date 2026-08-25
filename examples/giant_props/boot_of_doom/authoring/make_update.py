"""Assemble the beamng.com resource UPDATE bundle into dist/repo_update/.

The sibling of make_submission.py. That one drives "Add resource" for a mod
nobody has yet; this one drives "Post resource update" for one that is already
published, so it carries an update title and a what-changed message instead of
a title, tagline, category and version.

The text is authored in `authoring/repo_update/` and copied through verbatim:

    update_title.txt           the update's own title
    update_description.bbcode  the what-changed post

BBCODE, NOT MARKDOWN, for the message — beamng.com's Resource Manager is
XenForo. Markdown headings paste through as literal "###".

UPLOAD.txt is RENDERED here rather than authored, and its certified-build
block is read out of the lockfile at staging time. Catapult's equivalent is
hand-written, and its block silently went stale the moment its archive was
re-cut: it certified a build serial and SHA-256 that no longer existed. A
certification that is copied by hand is a certification that will be wrong.

Boot of Doom's build serial is past the packaging timestamp clamp, so every
rebuild produces a NEW SHA-256 from identical content. Stage LAST, after the
final `build.py boot_of_doom dist`, or the hash in UPLOAD.txt will not be the
hash of the file you attach. The staged archive is byte-compared against
dist/ on every run, and tests/test_boot_of_doom_release.py pins it too.

Run:  ./.venv/Scripts/python.exe \
        examples/giant_props/boot_of_doom/authoring/make_update.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

AUTHORING = Path(__file__).resolve().parent
EXAMPLE_ROOT = AUTHORING.parent
sys.path.insert(0, str(EXAMPLE_ROOT))

import spec  # noqa: E402

UPDATE_COPY = AUTHORING / "repo_update"
DIST = EXAMPLE_ROOT / "dist"
OUT = DIST / "repo_update"

# The published resource went out as 1.0.0 (authoring/repo/fields.txt). This
# release changes no content and adds no features, so it is a patch bump.
PUBLISHED_VERSION = "1.0.0"
RECOMMENDED_VERSION = "1.0.1"


def main() -> None:
    lock_path = DIST / f"{spec.MOD_ID}.lock.json"
    archive = DIST / spec.ZIP_BASENAME
    missing = [
        path
        for path in (
            UPDATE_COPY / "update_title.txt",
            UPDATE_COPY / "update_description.bbcode",
            archive,
            lock_path,
        )
        if not path.is_file()
    ]
    if missing:
        raise SystemExit("missing inputs:\n  " + "\n  ".join(str(path) for path in missing))

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    payload = archive.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != lock["sha256"] or len(payload) != lock["size"]:
        raise SystemExit(
            "dist archive does not match its lockfile - re-run "
            f"`build.py {EXAMPLE_ROOT.name} dist` before staging"
        )

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copyfile(archive, OUT / spec.ZIP_BASENAME)
    for name in ("update_title.txt", "update_description.bbcode"):
        shutil.copyfile(UPDATE_COPY / name, OUT / name)

    update_title = (UPDATE_COPY / "update_title.txt").read_text(encoding="utf-8").strip()
    upload = f"""POSTING THIS UPDATE ON BEAMNG.COM
=================================

This is an UPDATE to the existing {spec.DISPLAY_NAME} resource. Do not
create a new resource.

    Resource options  ->  Post resource update


1. TITLE
   Paste update_title.txt:

       {update_title}


2. MESSAGE
   Paste update_description.bbcode as BBCode, not Markdown.


3. VERSION
   This is a bug fix with no content or feature changes, so it is a patch
   bump. The published resource went out as {PUBLISHED_VERSION}.
   Recommended version:

       {RECOMMENDED_VERSION}

   If the live resource already uses {RECOMMENDED_VERSION} or newer, choose the next
   unused patch version instead; beamng.com requires a version that is not
   already used.


4. FILE
   Attach this file from the same repo_update folder:

       {spec.ZIP_BASENAME}

   Certified final build:

       build serial: {lock["build_serial"]}
       size:         {lock["size"]:,} bytes
       ZIP members:  {lock["members"]}
       SHA-256:      {lock["sha256"]}

   This build serial is past the packaging timestamp clamp, so rebuilding
   produces a different SHA-256 from identical content. If you rebuild,
   re-run this script before uploading and use the new hash.

   Tick the option to replace the existing file so subscribers receive it.


5. DO NOT EDIT THE RESOURCE DESCRIPTION
   Unlike the catapult update, nothing in the published listing became
   untrue. The title, tag line, category, tags, icon and gallery all still
   describe this build, and every performance figure in the description
   still matches the handoff: 27-42 m/s launch, 62 degree punt angle,
   power 1X-4X, launch angle 0-90, 3.5 s recovery.

   Leave the description, tagline and gallery alone.


WHAT ACTUALLY CHANGED
---------------------
   Exactly one file in the archive differs from the published release:

       lua/ge/extensions/{spec.MOD_ID}/runtime.lua

   All 46 other members - every mesh, texture, material, jbeam, config and
   thumbnail - are byte-identical to the published build. Verified member by
   member against the published archive (SHA-256 b59e0b40..., 55,389,675
   bytes, build serial 20).

   The prop places its boot, its console instruments, its two trigger zones
   and its launch dust at runtime, every frame, relative to the machine. The
   published build derived that placement from the orientation the engine
   reports for the vehicle object, which only refreshes on spawn, teleport
   and reset. A prop that settles onto a slope keeps reporting its spawn
   attitude, so everything was placed as though the machine were still level,
   displaced in proportion to its distance from the pad datum.

   Measured on a 53 degree settle, against the machine's own structure:

     * power ladder segments and angle needle: 11.61 m and 11.57 m off;
     * the boot itself: 8.54 m off;
     * strike_zone trigger: 2.60 m off a 5.4 x 9.4 m box;
     * kick_pad trigger: 1.61 m off, against a 2.3 m half-extent; and
     * punt_dust effect: 0.54 m off.

   A gentle 0.48 m-per-12 m grade put the console instruments 1.03 m out,
   which is the case the player video showed.

   The frame is now derived from the vehicle's live node cloud every frame.
   Two convention bugs in the replacement had to be fixed with it: a
   hand-built quaternion needs conjugating for the engine's q * vec3
   handedness, and the model flip must compose as FLIP * rotation rather
   than the reverse. All three faults are exactly identity on a level,
   unyawed spawn, which is why none of them showed on flat ground.


VALIDATION BEHIND THIS BUILD
----------------------------
   Proven live on utah with tests/test_giant_props_slope_live.py, spawning
   at four attitudes spanning 0.93 to 53.19 degrees of measured tilt:

     * every part-to-cage-node distance held to 24 um across attitudes,
       against a 5 cm tolerance;
     * unposed parts sat within 12 um of their authored geometry; and
     * the runtime reported the node-cloud frame, not the fallback, on
       every attitude.

   The gate was mutation-tested: reverting the composition-order fix alone
   reproduces 18.487 m of drift and the gate rejects the build.

   Offline, tests/test_giant_props_frame_math.py re-implements the frame
   math and checks it against all 21 mods in the pack.

   Still owed by the pack's own rule: a live in-game play-test of the kick
   itself at this build, on sloped ground as well as flat.


NOTE ABOUT FIRST LOAD
---------------------
   This archive ships BeamNG-cooked DDS textures, all 24 of them certified
   against their PNG sources by the harvest manifest, so there is no
   IMPORTING TEXTURE stall on first spawn.


LOCAL SIDELOAD TESTING
----------------------
   Do not drop this ZIP into a running game while the subscribed release is
   still mounted. Fully exit BeamNG, move the subscribed copy out of mods/
   (a profile-root sibling folder, never anywhere under mods/ - BeamNG
   mounts every ZIP below mods/ recursively and a stale copy shadows the new
   one nondeterministically), then place this ZIP in mods and restart.
"""
    (OUT / "UPLOAD.txt").write_text(upload, encoding="utf-8", newline="\n")

    print(f"staged {OUT}")
    for path in sorted(OUT.iterdir()):
        print(f"  {path.name:38s} {path.stat().st_size / 1024:10.1f} KB")
    print(f"\ncertified serial {lock['build_serial']}  sha256 {lock['sha256']}")


if __name__ == "__main__":
    main()
