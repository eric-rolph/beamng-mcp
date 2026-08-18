"""Assemble the beamng.com upload bundle into dist/repo_submission/.

Everything that gets uploaded, in one folder, named in the order the
resource form asks for it — so submitting is copy, paste, attach, with no
hunting through authoring/ and dist/ for which file was the current one.

The text is authored in `authoring/repo/` and copied through verbatim:

    title.txt              resource title
    tagline.txt            the one-line summary under the title
    description.bbcode     the big description field
    fields.txt             category / version / tags

BBCODE, NOT MARKDOWN. beamng.com's Resource Manager is XenForo, whose
editor takes BBCode; markdown headings paste through as literal "###".
That is why `description.bbcode` exists alongside the human-readable
`listing_copy.md` — the .md is the working doc, this is what gets pasted.

Run:  ./.venv/Scripts/python.exe \
        examples/giant_props/boot_of_doom/authoring/make_submission.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

AUTHORING = Path(__file__).resolve().parent
EXAMPLE_ROOT = AUTHORING.parent
PACK_ROOT = EXAMPLE_ROOT.parent
sys.path.insert(0, str(EXAMPLE_ROOT))

import spec  # noqa: E402

REPO_COPY = AUTHORING / "repo"
GALLERY = AUTHORING / "listing"
DIST = EXAMPLE_ROOT / "dist"
OUT = DIST / "repo_submission"

# Gallery order is the order the resource page shows them, so the lead image
# has to be the one that explains the mod in a single glance.
SCREENSHOTS = (
    ("01_rig.jpg", "the whole rig: boot, heel hinge, kick pad, control console"),
    ("03_kick_pad.jpg", "the painted X you drive over to arm it"),
    ("02_boot.jpg", "7.9 m of worn leather on a steel ground hinge"),
    ("04_console.jpg", "the KICK CONTROL console — power 1X-4X, launch angle 0-90"),
    ("05_data_plate.jpg", "CHARLIE CO. builder's plate on the back of the console"),
)


def main() -> None:
    missing = [
        path
        for path in (
            REPO_COPY / "title.txt",
            REPO_COPY / "tagline.txt",
            REPO_COPY / "description.bbcode",
            REPO_COPY / "fields.txt",
            AUTHORING / "resource_icon_96.png",
            DIST / spec.ZIP_BASENAME,
        )
        if not path.is_file()
    ]
    missing += [GALLERY / name for name, _ in SCREENSHOTS if not (GALLERY / name).is_file()]
    if missing:
        raise SystemExit(
            "cannot assemble the submission, missing:\n  "
            + "\n  ".join(str(path.relative_to(PACK_ROOT)) for path in missing)
        )

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shutil.copyfile(DIST / spec.ZIP_BASENAME, OUT / spec.ZIP_BASENAME)
    shutil.copyfile(AUTHORING / "resource_icon_96.png", OUT / "icon_96.png")
    for index, (name, _) in enumerate(SCREENSHOTS, start=1):
        shutil.copyfile(GALLERY / name, OUT / f"screenshot_{index:02d}.jpg")
    for name in ("title.txt", "tagline.txt", "description.bbcode", "fields.txt"):
        shutil.copyfile(REPO_COPY / name, OUT / name)

    title = (REPO_COPY / "title.txt").read_text(encoding="utf-8").strip()
    tagline = (REPO_COPY / "tagline.txt").read_text(encoding="utf-8").strip()
    fields = (REPO_COPY / "fields.txt").read_text(encoding="utf-8")
    zip_mb = (DIST / spec.ZIP_BASENAME).stat().st_size / 1e6
    shot_lines = "\n".join(
        f"  screenshot_{index:02d}.jpg   {caption}"
        for index, (_, caption) in enumerate(SCREENSHOTS, start=1)
    )
    field_lines = "\n".join(
        f"  {line}" for line in fields.splitlines() if line and not line.startswith("#")
    )

    (OUT / "UPLOAD.txt").write_text(
        f"""BEAMNG.COM RESOURCE SUBMISSION — {title}
{"=" * 60}

Go to beamng.com/resources -> Add resource, then:

1. TITLE
     {title}

2. TAG LINE ({len(tagline)} characters)
     {tagline}

3. DESCRIPTION
     Paste description.bbcode into the editor.
     It is BBCODE, not markdown — the editor is XenForo's. If the toolbar
     is in rich-text mode, switch it to BBCode first (the [] button at the
     right of the toolbar), or the tags paste through as literal text.

4. SHORT FIELDS
{field_lines}

5. ICON
     icon_96.png   (96 x 96)

6. RESOURCE FILE
     {spec.ZIP_BASENAME}   ({zip_mb:.1f} MB)
     Textures are pre-cooked to DDS, which is most of that size and why
     players get no first-load conversion wait.

7. SCREENSHOTS, in this order (the first is the gallery lead)
{shot_lines}

{"=" * 60}
IN-GAME NAME comes from the mod itself, not from this form: the vehicle
selector reads info.json ("{spec.DISPLAY_NAME}") and shows the card baked
into the ZIP. Nothing to upload for either.

BEFORE YOU SUBMIT: the pack rule is a live in-game play-test of the kick
at this build. The screenshots here are studio renders — honest about the
geometry, but an action shot of a car actually leaving the pad would sell
it better as the gallery lead.
""",
        encoding="utf-8",
    )

    print(f"assembled {OUT.relative_to(PACK_ROOT)}")
    for path in sorted(OUT.iterdir()):
        print(f"  {path.name:36} {path.stat().st_size / 1e3:9.1f} KB")


if __name__ == "__main__":
    main()
