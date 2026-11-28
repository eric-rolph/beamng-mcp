"""Build the deterministic distribution archive for the Gateway Skillet arena.

Mirrors examples/cannon_car_wash/build_distribution.py: an explicit member
allowlist (never a recursive pack-everything), ZIP_STORED members, a fixed
per-release epoch, a two-pass stable read, atomic no-clobber publication, and
a verification pass over the finished archive. The allowlist is COMPUTED from
reviewed sources rather than typed in - the handoff's shape table, the
materials json's own texture references, and the four scenario files - so a
geometry re-cut that adds a shape changes the manifest through the handoff and
nowhere else. The approved top-level root is exactly ``levels``.

Alongside the zip the builder writes ``<mod_id>.lock.json`` (sha256, size,
member list, epoch, and the sha256 of the Hot Potato dist zip this arena was
cut against, when that lock is present) so live gates can hash-verify what
they install.
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

from examples.hot_potato_arena.sync_scenario_outputs import (
    EXAMPLE_ROOT,
    LEVEL_ID,
    MOD_ID,
    MOD_ROOT,
    SCENARIO_RELATIVE,
    SHAPES_RELATIVE,
    read_handoff,
    shipped_art_members,
)

DEFAULT_OUTPUT_DIR = EXAMPLE_ROOT / "dist"
ZIP_NAME = "hot_potato_arena_ericrolph.zip"
LOCK_NAME = f"{MOD_ID}.lock.json"
ALLOWED_TOP_LEVEL_ROOTS = frozenset({"levels"})
FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
# Deterministic per-release timestamp (see the CCW builder: BeamNG compares
# Collada mtimes to its compiled .cdae cache, so bump this whenever a shipped
# DAE changes and keep it fixed otherwise).
ZIP_EPOCH = (2026, 9, 1, 12, 0, 0)
HOT_POTATO_LOCK = (
    EXAMPLE_ROOT.parent / "giant_props" / "hot_potato" / "dist" / "ericrolph_hot_potato.lock.json"
)
LOGGER = logging.getLogger(__name__)

SCENARIO_FILES: tuple[str, ...] = tuple(
    f"{SCENARIO_RELATIVE}/{MOD_ID}{suffix}" for suffix in (".jpg", ".json", ".lua", ".prefab.json")
)

# `mod/` holds TWO products, and this module ships only the first of them:
#
#   mod/levels/ericrolph_hot_potato_arena/art/shapes/hot_potato_arena/  <- ours
#   mod/levels/ericrolph_hot_potato_arena/scenarios/<MOD_ID>/           <- ours
#   everything else under mod/levels/ericrolph_hot_potato_arena/        <- NOT ours
#
# B5 (2026-09-10) moved the scenario off stock `gridmap_v2` onto the round's own
# level, so the two products now share one level DIRECTORY and are separated by
# subtree rather than by level id. They stay TWO archives on purpose: this one is
# ~8 MB and is re-cut whenever the Hot Potato runtime serial moves, while the
# level is ~905 MB and is re-cut by four other rounds that have nothing to do
# with that serial. BeamNG's VFS merges zips, so both mount into the same
# `/levels/<id>/` tree - which is exactly what this archive already did on
# `gridmap_v2`, where the level came from the game's own content zip.
#
# The standalone level is cut by `level/build_level_zip.py` against its own
# member list (`level/members_full_level.json`), locked separately in
# `dist_level/`, and gated by `tests/test_hot_potato_level_scaffold.py`. It has
# never been part of this archive: `expected_members()` is derived from the
# handoff plus SCENARIO_FILES and names none of it.
#
# `validate_mod_tree()` nevertheless walks all of `mod/`, so once the level
# round landed 800+ files here, four of this suite's gates failed on the level's
# own filenames (`info.json` and friends are namespaced by DIRECTORY, which is
# correct for a BeamNG level and wrong under this archive's per-file rule).
# Skipping the subtree is the fix; do NOT relax `_validate_member_name`, which
# is protecting this archive's members and should stay strict. The skip is
# scoped to the level MINUS our own two subtrees, so a stray file dropped beside
# the scenario or the shapes is still refused by the exact-match check.
LEVEL_SUBTREE = PurePosixPath("levels") / LEVEL_ID
ARENA_SUBTREES: tuple[PurePosixPath, ...] = (
    PurePosixPath(SHAPES_RELATIVE),
    PurePosixPath(SCENARIO_RELATIVE),
)


def _is_foreign_level_file(relative: PurePosixPath) -> bool:
    """True for a level member that belongs to the level round, not to us."""

    if not relative.is_relative_to(LEVEL_SUBTREE):
        return False
    return not any(relative.is_relative_to(subtree) for subtree in ARENA_SUBTREES)


class DistributionError(RuntimeError):
    """The source tree or requested release operation is unsafe."""


def _validate_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name:
        raise DistributionError(f"unsafe archive member name: {name!r}")
    member = PurePosixPath(name)
    if member.is_absolute() or member.as_posix() != name:
        raise DistributionError(f"archive member is not a canonical relative POSIX path: {name}")
    if len(member.parts) < 2 or any(part in {"", ".", ".."} for part in member.parts):
        raise DistributionError(f"archive member contains an unsafe path component: {name}")
    if member.parts[0] not in ALLOWED_TOP_LEVEL_ROOTS:
        raise DistributionError(f"archive member has an unapproved top-level root: {name}")
    if not all(FILENAME_PATTERN.fullmatch(part) for part in member.parts):
        raise DistributionError(f"archive member contains unsupported filename characters: {name}")
    if MOD_ID not in member.name and "hot_potato_arena" not in member.parts:
        raise DistributionError(f"archive member is not namespaced: {name}")
    return member


def expected_members() -> tuple[str, ...]:
    """The exact archive member list, derived from the reviewed sources."""

    handoff = read_handoff()
    members = tuple(sorted({*shipped_art_members(handoff), *SCENARIO_FILES}))
    folded = [name.casefold() for name in members]
    if len(folded) != len(set(folded)):
        raise DistributionError("the runtime allowlist has case-insensitive duplicates")
    for name in members:
        _validate_member_name(name)
    roots = {PurePosixPath(name).parts[0] for name in members}
    if roots != ALLOWED_TOP_LEVEL_ROOTS:
        raise DistributionError(f"runtime roots differ from the approved roots: {roots}")
    return members


def _regular_file_state(path: Path) -> os.stat_result:
    try:
        state = path.lstat()
    except OSError as exc:
        raise DistributionError(f"cannot inspect release source {path}: {exc}") from exc
    if path.is_symlink() or not stat.S_ISREG(state.st_mode):
        raise DistributionError(f"release source must be a regular non-symlink file: {path}")
    return state


def validate_mod_tree(
    mod_root: Path = MOD_ROOT, members: Sequence[str] | None = None
) -> dict[str, Path]:
    """Return the exact reviewed release files or reject the source tree."""

    expected_list = tuple(members) if members is not None else expected_members()
    if mod_root.is_symlink() or not mod_root.is_dir():
        raise DistributionError(f"mod root must be a real directory: {mod_root}")
    actual: dict[str, Path] = {}
    for path in mod_root.rglob("*"):
        if path.is_symlink():
            raise DistributionError(f"symlinks are forbidden in the release source tree: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise DistributionError(f"unsupported filesystem entry in mod tree: {path}")
        relative = path.relative_to(mod_root).as_posix()
        if _is_foreign_level_file(PurePosixPath(relative)):
            continue  # the standalone level; see LEVEL_SUBTREE
        _validate_member_name(relative)
        _regular_file_state(path)
        folded = relative.casefold()
        if any(existing.casefold() == folded for existing in actual):
            raise DistributionError(f"case-insensitive duplicate release path: {relative}")
        actual[relative] = path
    expected = set(expected_list)
    present = set(actual)
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)
    if missing or unexpected:
        raise DistributionError(
            "mod tree does not exactly match the runtime allowlist; "
            f"missing={missing}, unexpected={unexpected}"
        )
    return {name: actual[name] for name in expected_list}


def _stable_read(path: Path) -> bytes:
    before = _regular_file_state(path)
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise DistributionError(f"cannot read release source {path}: {exc}") from exc
    after = _regular_file_state(path)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or len(payload) != after.st_size:
        raise DistributionError(f"release source changed while it was read: {path}")
    return payload


def _check_text_payload(name: str, payload: bytes) -> None:
    if PurePosixPath(name).suffix in {".json", ".lua", ".dae"} and b"\r" in payload:
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
    """Verify member identity and security properties of a completed archive."""

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
                    raise DistributionError(
                        f"non-portable compression method for {member.filename}: "
                        f"{member.compress_type}"
                    )
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
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise DistributionError(f"cannot hash distribution archive {path}: {exc}") from exc
    return digest.hexdigest()


def _hot_potato_dependency() -> dict[str, str | int] | None:
    if not HOT_POTATO_LOCK.is_file():
        return None
    lock = json.loads(HOT_POTATO_LOCK.read_text(encoding="utf-8"))
    return {
        "zip": str(lock.get("zip", "")),
        "sha256": str(lock.get("sha256", "")),
        "build_serial": int(lock.get("build_serial", 0)),
    }


def build_distribution(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    mod_root: Path = MOD_ROOT,
    overwrite: bool = False,
    write_lock: bool = True,
) -> dict[str, object]:
    """Build, atomically publish, verify, and describe the release ZIP."""

    members = expected_members()
    sources = validate_mod_tree(mod_root, members)
    payloads = {name: _stable_read(path) for name, path in sources.items()}
    final_sources = validate_mod_tree(mod_root, members)
    for name, path in final_sources.items():
        if _stable_read(path) != payloads[name]:
            raise DistributionError(f"release source changed while snapshotting: {path}")
    for name, payload in payloads.items():
        _check_text_payload(name, payload)

    resolved_mod_root = mod_root.resolve()
    resolved_output_dir = output_dir.resolve()
    if resolved_output_dir == resolved_mod_root or resolved_output_dir.is_relative_to(
        resolved_mod_root
    ):
        raise DistributionError("distribution output must stay outside the mod source tree")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DistributionError(f"cannot create distribution output directory: {exc}") from exc
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise DistributionError(f"distribution output must be a real directory: {output_dir}")

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
    except BaseException as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                exc.add_note(
                    f"private temporary archive remains at {temporary_path}: {cleanup_error}"
                )
        if isinstance(exc, OSError) and not isinstance(exc, DistributionError):
            raise DistributionError(f"cannot publish distribution archive: {exc}") from exc
        raise
    if temporary_path is not None:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            LOGGER.warning("distribution was published, but %s", cleanup_error)

    result: dict[str, object] = {
        "archive": str(destination.resolve()),
        "sha256": digest,
        "size": size,
        "member_count": len(members),
    }
    if write_lock:
        lock = {
            "mod_id": MOD_ID,
            "zip": ZIP_NAME,
            "sha256": digest,
            "size": size,
            "members": list(members),
            "zip_epoch": list(ZIP_EPOCH),
            "depends_on": _hot_potato_dependency(),
        }
        lock_path = output_dir / LOCK_NAME
        lock_path.write_text(
            json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        result["lock"] = str(lock_path.resolve())
    return result


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _argument_parser()
    arguments = parser.parse_args(argv)
    try:
        result = build_distribution(arguments.output_dir, overwrite=arguments.overwrite)
    except DistributionError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
