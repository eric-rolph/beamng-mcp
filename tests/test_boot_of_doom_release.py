"""Release integrity for the Boot of Doom beamng.com update bundle.

`dist/repo_update/` is what actually gets uploaded, so it has to agree with the
archive the lockfile certifies. Two ways it can silently stop agreeing:

- the staged ZIP goes stale after a re-cut. That is what happened to
  catapult_seesaw, and `test_repo_update_stages_the_exact_certified_release_archive`
  exists because of it.
- the CERTIFICATION BLOCK inside UPLOAD.txt goes stale. Catapult has no test for
  that, and it silently certified build serial 78 with a SHA-256 that no longer
  existed after its archive was re-cut. An operator following those instructions
  would have attached one file while vouching for the hash of another.

Boot of Doom's build serial is past the packaging timestamp clamp, so every
rebuild yields a new SHA-256 from byte-identical content. That makes staleness
the normal outcome of any rebuild rather than an unlucky one, so it is checked
rather than trusted.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

PACK_ROOT = Path(__file__).resolve().parents[1] / "examples" / "giant_props"
MOD_ROOT = PACK_ROOT / "boot_of_doom"
MOD_ID = "ericrolph_boot_of_doom"
ZIP_BASENAME = "boot_of_doom_ericrolph.zip"

DIST = MOD_ROOT / "dist"
STAGED = DIST / "repo_update"
AUTHORED = MOD_ROOT / "authoring" / "repo_update"
LOCK_PATH = DIST / f"{MOD_ID}.lock.json"

# dist/ is gitignored, so a clean checkout has no archive to check until the
# pack is built. Skip rather than fail there; the bundle is only meaningful
# once a release has actually been cut.
pytestmark = pytest.mark.skipif(
    not (DIST / ZIP_BASENAME).is_file() or not LOCK_PATH.is_file(),
    reason="no built Boot of Doom release in dist/ to check the upload bundle against",
)


def _lock() -> dict:
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def test_dist_archive_matches_its_lockfile() -> None:
    lock = _lock()
    payload = (DIST / ZIP_BASENAME).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == lock["sha256"]
    assert len(payload) == lock["size"]


def test_repo_update_stages_the_exact_certified_release_archive() -> None:
    """The attached file must be the file the lock vouches for."""

    staged = STAGED / ZIP_BASENAME
    assert staged.is_file(), (
        "no staged update bundle - run authoring/make_update.py after cutting the release"
    )
    assert staged.read_bytes() == (DIST / ZIP_BASENAME).read_bytes(), (
        "dist/repo_update is stale; re-run authoring/make_update.py so the staged "
        "archive is the one the lockfile and the live gate validated"
    )


def test_upload_sheet_certifies_the_archive_it_ships() -> None:
    """The four certified values must describe the staged archive.

    Catapult's hand-written sheet drifted from its archive precisely here.
    """

    upload = (STAGED / "UPLOAD.txt").read_text(encoding="utf-8")
    lock = _lock()
    certified = re.search(
        r"build serial: (\d+)\s*\n\s*size:\s+([\d,]+) bytes\s*\n"
        r"\s*ZIP members:\s+(\d+)\s*\n\s*SHA-256:\s+([0-9a-f]{64})",
        upload,
    )
    assert certified, "UPLOAD.txt has no certified-build block"
    serial, size, members, digest = certified.groups()
    assert int(serial) == lock["build_serial"]
    assert int(size.replace(",", "")) == lock["size"]
    assert int(members) == lock["members"]
    assert digest == lock["sha256"]


def test_staged_text_is_the_authored_text() -> None:
    """Nothing gets hand-edited in dist/; the source of truth is authoring/."""

    for name in ("update_title.txt", "update_description.bbcode"):
        assert (STAGED / name).read_bytes() == (AUTHORED / name).read_bytes(), name


def test_update_message_is_bbcode_not_markdown() -> None:
    """XenForo takes BBCode; markdown headings paste through as literal '###'."""

    body = (AUTHORED / "update_description.bbcode").read_text(encoding="utf-8")
    offenders = [line for line in body.splitlines() if line.lstrip().startswith("#")]
    assert not offenders, offenders
    assert "[B]" in body and "[LIST]" in body


def test_the_bundle_carries_no_first_submission_fields() -> None:
    """An update posts a title and a message - not a category, version or tags.

    Staging fields.txt here would invite someone to re-submit the resource
    instead of updating it.
    """

    unexpected = sorted(
        path.name
        for path in STAGED.iterdir()
        if path.name
        not in {ZIP_BASENAME, "UPLOAD.txt", "update_title.txt", "update_description.bbcode"}
    )
    assert not unexpected, unexpected
