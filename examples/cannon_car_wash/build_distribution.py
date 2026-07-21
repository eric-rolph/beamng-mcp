"""Build the deterministic public Repository archive for Cannon Car Wash."""

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

EXAMPLE_ROOT = Path(__file__).resolve().parent
MOD_ROOT = EXAMPLE_ROOT / "mod"
DEFAULT_OUTPUT_DIR = EXAMPLE_ROOT / "dist"
MOD_ID = "ericrolph_cannon_car_wash"
ZIP_NAME = "cannon_car_wash_ericrolph.zip"
ALLOWED_TOP_LEVEL_ROOTS = frozenset({"levels", "vehicles"})
FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
LOGGER = logging.getLogger(__name__)

# Public Repository contents are an explicit release decision. Never replace
# this allowlist with a recursive "pack everything" implementation.
EXPECTED_RUNTIME_FILES: tuple[str, ...] = (
    f"levels/gridmap_v2/art/shapes/{MOD_ID}/{MOD_ID}.dae",
    f"levels/gridmap_v2/art/shapes/{MOD_ID}/{MOD_ID}.materials.json",
    f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.jpg",
    f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.json",
    f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.lua",
    f"levels/gridmap_v2/scenarios/{MOD_ID}/{MOD_ID}.prefab.json",
    f"vehicles/{MOD_ID}/default.jpg",
    f"vehicles/{MOD_ID}/{MOD_ID}.dae",
    f"vehicles/{MOD_ID}/{MOD_ID}.jbeam",
    f"vehicles/{MOD_ID}/info.json",
    f"vehicles/{MOD_ID}/info_standard.json",
    f"vehicles/{MOD_ID}/main.materials.json",
    f"vehicles/{MOD_ID}/standard.jpg",
    f"vehicles/{MOD_ID}/standard.pc",
)


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
    return member


def _validate_allowlist() -> None:
    if len(EXPECTED_RUNTIME_FILES) != 14:
        raise DistributionError("the public runtime allowlist must contain exactly 14 files")
    if tuple(sorted(EXPECTED_RUNTIME_FILES)) != EXPECTED_RUNTIME_FILES:
        raise DistributionError("the public runtime allowlist must be deterministically sorted")
    for name in EXPECTED_RUNTIME_FILES:
        _validate_member_name(name)
    folded = [name.casefold() for name in EXPECTED_RUNTIME_FILES]
    if len(folded) != len(set(folded)):
        raise DistributionError("the public runtime allowlist has case-insensitive duplicates")
    roots = {PurePosixPath(name).parts[0] for name in EXPECTED_RUNTIME_FILES}
    if roots != ALLOWED_TOP_LEVEL_ROOTS:
        raise DistributionError(f"public runtime roots differ from the approved roots: {roots}")


_validate_allowlist()


def _regular_file_state(path: Path) -> os.stat_result:
    try:
        state = path.lstat()
    except OSError as exc:
        raise DistributionError(f"cannot inspect release source {path}: {exc}") from exc
    if path.is_symlink() or not stat.S_ISREG(state.st_mode):
        raise DistributionError(f"release source must be a regular non-symlink file: {path}")
    return state


def validate_mod_tree(mod_root: Path = MOD_ROOT) -> dict[str, Path]:
    """Return the exact reviewed release files or reject the source tree."""

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
        _validate_member_name(relative)
        _regular_file_state(path)
        folded = relative.casefold()
        if any(existing.casefold() == folded for existing in actual):
            raise DistributionError(f"case-insensitive duplicate release path: {relative}")
        actual[relative] = path

    expected = set(EXPECTED_RUNTIME_FILES)
    present = set(actual)
    missing = sorted(expected - present)
    unexpected = sorted(present - expected)
    if missing or unexpected:
        raise DistributionError(
            "mod tree does not exactly match the public allowlist; "
            f"missing={missing}, unexpected={unexpected}"
        )
    return {name: actual[name] for name in EXPECTED_RUNTIME_FILES}


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


def _cleanup_temporary(path: Path, *, attempts: int = 2) -> OSError | None:
    """Best-effort cleanup that never replaces the operation's primary error."""

    last_error: OSError | None = None
    for _ in range(attempts):
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            last_error = exc
        else:
            return None
    return last_error


def _cleanup_failure_note(path: Path, error: OSError) -> str:
    return f"private temporary archive remains at {path}: {type(error).__name__}: {error}"


def _write_archive(path: Path, payloads: dict[str, bytes]) -> None:
    with zipfile.ZipFile(
        path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for name in EXPECTED_RUNTIME_FILES:
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(
                info,
                payloads[name],
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def verify_archive(path: Path) -> None:
    """Verify member identity and security properties of a completed archive."""

    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if names != list(EXPECTED_RUNTIME_FILES):
                raise DistributionError(
                    f"archive members differ from the public allowlist: {names}"
                )
            if archive.testzip() is not None:
                raise DistributionError("archive CRC verification failed")
            for member in members:
                _validate_member_name(member.filename)
                if member.is_dir() or member.filename.endswith("/"):
                    raise DistributionError(f"directory member is forbidden: {member.filename}")
                if member.flag_bits & 0x1:
                    raise DistributionError(f"encrypted member is forbidden: {member.filename}")
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


def build_distribution(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    mod_root: Path = MOD_ROOT,
    overwrite: bool = False,
) -> dict[str, str | int]:
    """Build, atomically publish, verify, and describe the release ZIP."""

    sources = validate_mod_tree(mod_root)
    payloads = {name: _stable_read(path) for name, path in sources.items()}
    # A second stable content pass detects both tree edits and changes to files
    # that completed after their first individual read.
    final_sources = validate_mod_tree(mod_root)
    for name, path in final_sources.items():
        if _stable_read(path) != payloads[name]:
            raise DistributionError(f"release source changed while snapshotting: {path}")

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

    descriptor = -1
    temporary_path: Path | None = None
    publication_committed = False
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{ZIP_NAME}.",
            suffix=".tmp",
            dir=output_dir,
        )
        os.close(descriptor)
        descriptor = -1
        temporary_path = Path(temporary_name)
        _write_archive(temporary_path, payloads)
        verify_archive(temporary_path)
        digest = _sha256(temporary_path)
        size = temporary_path.stat().st_size

        if overwrite:
            os.replace(temporary_path, destination)
            publication_committed = True
            temporary_path = None
        else:
            try:
                # The temporary and destination paths share a directory/volume.
                # Creating the destination hard link is an atomic no-clobber
                # publication: a racing writer wins without being overwritten.
                os.link(temporary_path, destination)
            except FileExistsError as exc:
                raise DistributionError(
                    f"distribution appeared during build; pass --overwrite: {destination}"
                ) from exc
            publication_committed = True
    except BaseException as exc:
        cleanup_errors: list[str] = []
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as cleanup_error:
                cleanup_errors.append(f"temporary descriptor could not be closed: {cleanup_error}")
        if temporary_path is not None:
            if cleanup_error := _cleanup_temporary(temporary_path):
                cleanup_errors.append(_cleanup_failure_note(temporary_path, cleanup_error))

        if isinstance(exc, DistributionError):
            error: BaseException = exc
        elif isinstance(exc, OSError):
            error = DistributionError(f"cannot publish distribution archive: {exc}")
        else:
            error = exc
        for note in cleanup_errors:
            error.add_note(note)
        if error is exc:
            raise
        raise error from exc

    if descriptor >= 0:  # pragma: no cover - the descriptor is normally closed above
        try:
            os.close(descriptor)
        except OSError as exc:
            LOGGER.warning(
                "distribution was published, but its temporary descriptor did not close: %s",
                exc,
            )
    if temporary_path is not None:
        cleanup_error = _cleanup_temporary(temporary_path)
        if cleanup_error is not None:
            assert publication_committed
            LOGGER.warning(
                "distribution was published successfully, but %s",
                _cleanup_failure_note(temporary_path, cleanup_error),
            )

    return {
        "archive": str(destination.resolve()),
        "sha256": digest,
        "size": size,
        "member_count": len(EXPECTED_RUNTIME_FILES),
    }


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="atomically replace an existing stable release archive",
    )
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
