"""Build the deterministic distribution archive for the standalone level scaffold.

Separate from the shipped arena dist (``examples/hot_potato_arena/dist/``), which
this round leaves untouched: the level ships as its own zip under
``examples/hot_potato_arena/dist_level/`` with its own lock.

Same house style as ``build_distribution.py``: a COMPUTED member allowlist
(every file ``level_writer.render_level`` emits plus the two Blender DAEs),
ZIP_STORED members, a fixed per-release epoch, a two-pass stable read, the
LF law on text members, atomic no-clobber publication, and a verification
pass over the finished archive. The lock records sha256, size, member list
and epoch so the live gate hash-verifies what it installs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import stat
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from examples.hot_potato_arena.level import cook_terrain_textures as cook
from examples.hot_potato_arena.level.level_writer import (
    EXAMPLE_ROOT,
    LEVEL_ID,
    LEVEL_RELATIVE,
    MOD_ROOT,
    expected_level_members,
    render_level,
)

DEFAULT_OUTPUT_DIR = EXAMPLE_ROOT / "dist_level"
ZIP_NAME = "hot_potato_arena_level_ericrolph.zip"
LOCK_NAME = f"{LEVEL_ID}_level.lock.json"
ALLOWED_TOP_LEVEL_ROOTS = frozenset({"levels"})
FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
# Fixed per-release timestamp: BeamNG compares Collada mtimes to its compiled
# .cdae cache, so bump this when a shipped DAE changes and keep it fixed otherwise.
ZIP_EPOCH = (2026, 9, 17, 12, 0, 0)  # bumped: seven DAEs moved (A7 cliffs, shrub stems)
TEXT_SUFFIXES = {".json", ".dae", ".lua"}
LOGGER = logging.getLogger(__name__)


class DistributionError(RuntimeError):
    """The source tree or requested release operation is unsafe."""


def _validate_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name:
        raise DistributionError(f"unsafe archive member name: {name!r}")
    member = PurePosixPath(name)
    if member.is_absolute() or member.as_posix() != name:
        raise DistributionError(f"archive member is not a canonical relative POSIX path: {name}")
    if len(member.parts) < 3 or any(part in {"", ".", ".."} for part in member.parts):
        raise DistributionError(f"archive member contains an unsafe path component: {name}")
    if member.parts[0] not in ALLOWED_TOP_LEVEL_ROOTS or member.parts[1] != LEVEL_ID:
        raise DistributionError(f"archive member is outside levels/{LEVEL_ID}/: {name}")
    if not all(FILENAME_PATTERN.fullmatch(part) for part in member.parts):
        raise DistributionError(f"archive member contains unsupported filename characters: {name}")
    return member


def expected_members() -> tuple[str, ...]:
    members = expected_level_members()
    folded = [name.casefold() for name in members]
    if len(folded) != len(set(folded)):
        raise DistributionError("the level allowlist has case-insensitive duplicates")
    for name in members:
        _validate_member_name(name)
    return members


def _regular_file_state(path: Path) -> os.stat_result:
    try:
        state = path.lstat()
    except OSError as exc:
        raise DistributionError(f"cannot inspect release source {path}: {exc}") from exc
    if path.is_symlink() or not stat.S_ISREG(state.st_mode):
        raise DistributionError(f"release source must be a regular non-symlink file: {path}")
    return state


def validate_level_tree(
    mod_root: Path = MOD_ROOT,
    members: Sequence[str] | None = None,
    ignore_stale: Sequence[str] = (),
) -> dict[str, Path]:
    """The level subtree must hold exactly the allowlist and match the generator's render.

    ``ignore_stale`` names members whose bytes are NOT compared against the current
    generator output. The level tree is built by several rounds at once; a round
    cutting its own subset stages the file IT authored for a group another round is
    still editing, and says so in its report. Everything else stays an exact match.
    """

    expected_list = tuple(members) if members is not None else expected_members()
    level_root = mod_root / LEVEL_RELATIVE
    if level_root.is_symlink() or not level_root.is_dir():
        raise DistributionError(f"level root must be a real directory: {level_root}")
    actual: dict[str, Path] = {}
    for path in level_root.rglob("*"):
        if path.is_symlink():
            raise DistributionError(f"symlinks are forbidden in the release source tree: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise DistributionError(f"unsupported filesystem entry in level tree: {path}")
        relative = path.relative_to(mod_root).as_posix()
        _validate_member_name(relative)
        _regular_file_state(path)
        actual[relative] = path
    missing = sorted(set(expected_list) - set(actual))
    unexpected = sorted(set(actual) - set(expected_list))
    if missing or unexpected:
        raise DistributionError(
            f"level tree does not exactly match the allowlist; missing={missing}, "
            f"unexpected={unexpected}"
        )
    # Only members that are ALSO generator outputs are staleness-checked: a round
    # cutting its own subset (see ``stage_level_tree``) ships a member list that does
    # not carry the other rounds' generated files.
    wanted = {name.removeprefix(f"{LEVEL_RELATIVE}/") for name in expected_list}
    skip = set(ignore_stale)
    rendered = {k: v for k, v in render_level().items() if k in wanted and k not in skip}
    stale = [rel for rel, payload in rendered.items() if (level_root / rel).read_bytes() != payload]
    if stale:
        raise DistributionError(
            f"level tree is stale against the generator; re-run level_writer: {stale}"
        )
    # The cooked CC0 art is not re-derived here (55 s); the cook manifest's per-file
    # sha256 is the contract, and every cooked member must match it byte for byte.
    stale_art = [name for name in cook.verify_tree(level_root) if name in wanted]
    if stale_art:
        raise DistributionError(
            "cooked terrain textures are stale against "
            f"{cook.MANIFEST_PATH.name}; re-run cook_terrain_textures: {stale_art}"
        )
    return {name: actual[name] for name in expected_list}


def _stable_read(path: Path) -> bytes:
    before = _regular_file_state(path)
    payload = path.read_bytes()
    after = _regular_file_state(path)
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(
        payload
    ) != after.st_size:
        raise DistributionError(f"release source changed while it was read: {path}")
    return payload


def _check_text_payload(name: str, payload: bytes) -> None:
    if PurePosixPath(name).suffix in TEXT_SUFFIXES and b"\r" in payload:
        raise DistributionError(f"release text member carries CR bytes (LF law): {name}")


def _write_archive(path: Path, members: Sequence[str], payloads: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in members:
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payloads[name], compress_type=zipfile.ZIP_STORED)


def verify_archive(path: Path, members: Sequence[str] | None = None) -> None:
    expected_list = list(members) if members is not None else list(expected_members())
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            names = [member.filename for member in entries]
            if names != expected_list:
                raise DistributionError(f"archive members differ from the allowlist: {names}")
            if archive.testzip() is not None:
                raise DistributionError("archive CRC verification failed")
            for member in entries:
                _validate_member_name(member.filename)
                if member.is_dir() or member.filename.endswith("/"):
                    raise DistributionError(f"directory member is forbidden: {member.filename}")
                if member.flag_bits & 0x1:
                    raise DistributionError(f"encrypted member is forbidden: {member.filename}")
                if member.compress_type != zipfile.ZIP_STORED:
                    raise DistributionError(f"non-portable compression for {member.filename}")
                if member.date_time != ZIP_EPOCH:
                    raise DistributionError(f"non-deterministic timestamp: {member.filename}")
                if member.create_system != 3:
                    raise DistributionError(f"unexpected ZIP creator system: {member.filename}")
                mode = (member.external_attr >> 16) & 0o177777
                if mode != stat.S_IFREG | 0o644:
                    raise DistributionError(f"unexpected file mode for {member.filename}: {mode:o}")
    except (OSError, zipfile.BadZipFile) as exc:
        raise DistributionError(f"cannot verify distribution archive {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


#: PNG members the game reads as IMAGES, not as material textures: the level previews and
#: the minimap (UI), and the terrain depth map (read by the terrain, never cooked). These
#: ship as PNG whatever the cooked-texture harvest holds.
COOKED_KEEP_PNG_SUFFIXES = ("_preview.png", "_preview_hearth.png", "_minimap.png", ".ter.depth.png")


def cooked_substitutions(
    members: Sequence[str], payloads: dict[str, bytes], cooked_dir: Path
) -> dict[str, dict[str, object]]:
    """Which PNG members ship as the engine's own cooked DDS, and the proof for each.

    B6 (2026-09-15). BeamNG cooks a level's PNG textures to DDS lazily, on the first frame
    that needs each map, so every first load of a new build shows the "NO TEXTURE"
    placeholder on foliage and rock for minutes. The giant-props releases already ship the
    engine's cooked DDS IN PLACE of each PNG while the materials keep naming the .png (the
    game resolves the cooked sibling; proven Cannon Car Wash layout, `proplib/prop_builder`).
    This does the same for the level from a harvest taken on the sentinel
    (`level_round/b6/cook_harvest_r1.py`): a PNG member is replaced only when the harvest
    manifest pins the sha256 of the PNG bytes being shipped, so a re-cooked source can
    never ship a stale bake. UI images and the depth map stay PNG.
    """

    manifest_path = cooked_dir / "harvest.json"
    if not manifest_path.is_file():
        raise DistributionError(f"cooked-texture harvest manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files", {})
    substitutions: dict[str, dict[str, object]] = {}
    for name in members:
        if not name.lower().endswith(".png") or name.endswith(COOKED_KEEP_PNG_SUFFIXES):
            continue
        relative = name.removeprefix(f"{LEVEL_RELATIVE}/")
        cooked_relative = relative[: -len(".png")] + ".dds"
        row = files.get(cooked_relative)
        if not row:
            continue
        source_sha = hashlib.sha256(payloads[name]).hexdigest()
        if row.get("source_png_sha256") != source_sha:
            continue  # the PNG moved since the cook: ship it raw, never a stale bake
        cooked_path = cooked_dir / cooked_relative
        if not cooked_path.is_file():
            continue
        blob = cooked_path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != row.get("sha256"):
            raise DistributionError(
                f"cooked DDS does not match its harvest manifest: {cooked_relative}"
            )
        substitutions[name] = {
            "shipped": f"{LEVEL_RELATIVE}/{cooked_relative}",
            "payload": blob,
            "source_sha256": source_sha,
            "cooked_sha256": row["sha256"],
            "texture_quality": manifest.get("texture_quality"),
        }
    return substitutions


def build_distribution(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    mod_root: Path = MOD_ROOT,
    overwrite: bool = False,
    write_lock: bool = True,
    members: Sequence[str] | None = None,
    ignore_stale: Sequence[str] = (),
    cooked_dir: Path | None = None,
) -> dict[str, object]:
    members = tuple(members) if members is not None else expected_members()
    for name in members:
        _validate_member_name(name)
    sources = validate_level_tree(mod_root, members, ignore_stale)
    payloads = {name: _stable_read(path) for name, path in sources.items()}
    for name, path in validate_level_tree(mod_root, members, ignore_stale).items():
        if _stable_read(path) != payloads[name]:
            raise DistributionError(f"release source changed while snapshotting: {path}")
    for name, payload in payloads.items():
        _check_text_payload(name, payload)

    # B6: swap PNG members for the engine's cooked DDS where the harvest proves the bake.
    cooked: dict[str, dict[str, object]] = {}
    if cooked_dir is not None:
        cooked = cooked_substitutions(members, payloads, cooked_dir)
        shipped_members = tuple(
            str(cooked[name]["shipped"]) if name in cooked else name for name in members
        )
        shipped_payloads = {
            (str(cooked[name]["shipped"]) if name in cooked else name): (
                cooked[name]["payload"] if name in cooked else payloads[name]  # type: ignore[misc]
            )
            for name in members
        }
        folded = [name.casefold() for name in shipped_members]
        if len(folded) != len(set(folded)):
            raise DistributionError("cooked substitution produced a case-insensitive duplicate")
        members = tuple(sorted(shipped_members))
        payloads = shipped_payloads  # type: ignore[assignment]

    if output_dir.resolve() == mod_root.resolve() or output_dir.resolve().is_relative_to(
        mod_root.resolve()
    ):
        raise DistributionError("distribution output must stay outside the mod source tree")
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / ZIP_NAME
    if os.path.lexists(destination) and not overwrite:
        raise DistributionError(f"distribution already exists; pass --overwrite: {destination}")

    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{ZIP_NAME}.", suffix=".tmp", dir=output_dir
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        _write_archive(temporary_path, members, payloads)
        verify_archive(temporary_path, members)
        digest = _sha256(temporary_path)
        size = temporary_path.stat().st_size
        if overwrite:
            os.replace(temporary_path, destination)
            temporary_path = None
        else:
            try:
                os.link(temporary_path, destination)
            except FileExistsError as exc:
                raise DistributionError(
                    f"distribution appeared during build; pass --overwrite: {destination}"
                ) from exc
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    if temporary_path is not None:
        temporary_path.unlink(missing_ok=True)

    result: dict[str, object] = {
        "archive": str(destination.resolve()),
        "sha256": digest,
        "size": size,
        "member_count": len(members),
    }
    if write_lock:
        lock = {
            "mod_id": f"{LEVEL_ID}_level",
            "level_id": LEVEL_ID,
            "zip": ZIP_NAME,
            "sha256": digest,
            "size": size,
            "members": list(members),
            "member_sha256": {name: hashlib.sha256(payloads[name]).hexdigest() for name in members},
            "zip_epoch": list(ZIP_EPOCH),
        }
        if cooked:
            # shipped DDS name -> the PNG it stands in for, with both hashes, so a reader
            # can map the archive back onto the tree and a stale bake is provable.
            lock["cooked"] = {
                str(row["shipped"]): {
                    "source": source,
                    "source_sha256": row["source_sha256"],
                    "cooked_sha256": row["cooked_sha256"],
                }
                for source, row in sorted(cooked.items())
            }
            lock["cooked_texture_quality"] = next(iter(cooked.values()))["texture_quality"]
            lock["cooked_dir"] = str(cooked_dir)
        lock_path = output_dir / LOCK_NAME
        lock_path.write_text(
            json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        result["lock"] = str(lock_path.resolve())
    return result


def stage_level_tree(
    destination: Path, mod_root: Path = MOD_ROOT, members: Sequence[str] | None = None
) -> Path:
    """Copy EXACTLY the allowlist into a clean tree and return it as a mod root.

    The level tree is built by several rounds in parallel (B1 terrain, B3
    vegetation, ...). ``validate_level_tree`` is deliberately an EXACT match, so
    a round that wants to cut its own dist while another round is still writing
    into ``mod/`` stages its members first. The archive is byte-identical to one
    cut straight from ``mod/`` once the other round's files are removed, because
    every member is copied byte for byte and the member list is the same.
    """

    members = tuple(members) if members is not None else expected_members()
    if destination.exists():
        raise DistributionError(f"staging directory already exists: {destination}")
    for name in members:
        source = mod_root / name
        _regular_file_state(source)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_stable_read(source))
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--mod-root",
        type=Path,
        default=MOD_ROOT,
        help="build from this mod root instead of examples/hot_potato_arena/mod",
    )
    parser.add_argument(
        "--members-file",
        type=Path,
        help="JSON list of archive members to ship instead of the whole level allowlist",
    )
    parser.add_argument(
        "--stage-into",
        type=Path,
        help="first copy exactly the allowlist into this empty directory and build from it",
    )
    parser.add_argument(
        "--cooked-dir",
        type=Path,
        default=None,
        help="ship the engine's cooked DDS from this harvest in place of each PNG it proves",
    )
    arguments = parser.parse_args(argv)
    mod_root = arguments.mod_root
    members: Sequence[str] | None = None
    if arguments.members_file is not None:
        members = json.loads(arguments.members_file.read_text(encoding="utf-8"))
    try:
        if arguments.stage_into is not None:
            mod_root = stage_level_tree(arguments.stage_into, arguments.mod_root, members)
        result = build_distribution(
            arguments.output_dir,
            mod_root=mod_root,
            overwrite=arguments.overwrite,
            members=members,
            cooked_dir=arguments.cooked_dir,
        )
    except DistributionError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
