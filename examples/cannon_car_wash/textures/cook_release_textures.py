"""Stage Cannon PNGs for BeamNG cooking, then collect public-release DDS files.

The official workflow requires materials to reference logical PNG paths while a
published mod contains only the cooked DDS files.  ``stage`` temporarily puts
the generated PNG set into the exact runtime location.  After one isolated
BeamNG visual load, ``collect`` copies verified DDS files from that profile's
temp tree and removes only the known staged PNG names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Final

from PIL import Image

SCRIPT_ROOT: Final = Path(__file__).resolve().parent
EXAMPLE_ROOT: Final = SCRIPT_ROOT.parent
MOD_ID: Final = "ericrolph_cannon_car_wash"
GENERATED_ROOT: Final = SCRIPT_ROOT / "generated_png"
RUNTIME_TEXTURE_ROOT: Final = EXAMPLE_ROOT / "mod" / "art" / "shapes" / MOD_ID / "textures"
LOGICAL_TEXTURE_ROOT: Final = Path("art") / "shapes" / MOD_ID / "textures"


class TextureCookError(RuntimeError):
    """Raised when the isolated texture-cook handoff is incomplete or unsafe."""


def _source_files() -> list[Path]:
    files = sorted(GENERATED_ROOT.glob("*.png"))
    if not files:
        raise TextureCookError("no generated PNGs found; run textures/build_pbr_textures.py first")
    invalid = [path.name for path in files if not path.name.startswith(f"{MOD_ID}_")]
    if invalid:
        raise TextureCookError(f"unnamespaced generated textures: {invalid}")
    return files


def _dds_name(source: Path) -> str:
    if source.name.endswith((".color.png", ".normal.png", ".data.png")):
        return source.name.removesuffix(".png") + ".dds"
    raise TextureCookError(f"unsupported BeamNG texture-cooker suffix: {source.name}")


def _validate_cooked_pair(source: Path, cooked: Path) -> str | None:
    """Return a diagnostic when BeamNG produced the wrong DDS payload.

    A DDS magic/size check cannot distinguish a successfully cooked BC4 data
    map from BeamNG's RGBA fallback texture.  Pillow exposes the decoded channel
    class for BC4/BC5/BC7, so validate both dimensions and the expected logical
    channel family before a release file is copied into the mod.
    """

    try:
        with Image.open(source) as source_image, Image.open(cooked) as cooked_image:
            if cooked_image.size != source_image.size:
                return (
                    f"{cooked.name}: dimensions {cooked_image.size} do not match "
                    f"source {source_image.size}"
                )
            if source_image.mode == "L" and cooked_image.mode != "L":
                return f"{cooked.name}: expected single-channel data DDS, got {cooked_image.mode}"
            if source_image.mode != "L" and cooked_image.mode not in {"RGB", "RGBA"}:
                return f"{cooked.name}: expected color/normal DDS, got {cooked_image.mode}"
    except (OSError, ValueError) as exc:
        return f"{cooked.name}: Pillow could not decode texture pair ({exc})"
    return None


def stage() -> dict[str, object]:
    sources = _source_files()
    RUNTIME_TEXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    expected = {path.name for path in sources}
    for path in sources:
        shutil.copy2(path, RUNTIME_TEXTURE_ROOT / path.name)
    unexpected_png = sorted(
        path.name for path in RUNTIME_TEXTURE_ROOT.glob("*.png") if path.name not in expected
    )
    if unexpected_png:
        raise TextureCookError(f"unexpected runtime PNGs: {unexpected_png}")
    return {"action": "stage", "png_count": len(sources), "runtime_root": str(RUNTIME_TEXTURE_ROOT)}


def collect(profile_current: Path) -> dict[str, object]:
    sources = _source_files()
    cooked_root = profile_current.resolve() / "temp" / LOGICAL_TEXTURE_ROOT
    if not cooked_root.is_dir():
        raise TextureCookError(f"BeamNG cooked texture directory does not exist: {cooked_root}")
    pairs = [(source, cooked_root / _dds_name(source)) for source in sources]
    missing = [cooked.name for _source, cooked in pairs if not cooked.is_file()]
    if missing:
        raise TextureCookError(f"BeamNG did not cook the complete texture set: {missing}")
    invalid = []
    for source, cooked in pairs:
        if cooked.stat().st_size < 128 or cooked.read_bytes()[:4] != b"DDS ":
            invalid.append(f"{cooked.name}: invalid DDS header or payload size")
            continue
        diagnostic = _validate_cooked_pair(source, cooked)
        if diagnostic:
            invalid.append(diagnostic)
    if invalid:
        raise TextureCookError(f"invalid cooked DDS files: {invalid}")

    RUNTIME_TEXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    expected_dds = {cooked.name for _source, cooked in pairs}
    for _source, cooked in pairs:
        shutil.copy2(cooked, RUNTIME_TEXTURE_ROOT / cooked.name)
    for staged in sources:
        runtime_png = RUNTIME_TEXTURE_ROOT / staged.name
        if runtime_png.is_file():
            runtime_png.unlink()
    unexpected_dds = sorted(
        path.name for path in RUNTIME_TEXTURE_ROOT.glob("*.dds") if path.name not in expected_dds
    )
    if unexpected_dds:
        raise TextureCookError(f"unexpected runtime DDS files: {unexpected_dds}")

    files = [
        {
            "name": cooked.name,
            "size_bytes": cooked.stat().st_size,
            "sha256": hashlib.sha256(cooked.read_bytes()).hexdigest(),
        }
        for _source, cooked in pairs
    ]
    return {
        "action": "collect",
        "dds_count": len(files),
        "runtime_root": str(RUNTIME_TEXTURE_ROOT),
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("stage")
    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--profile-current", type=Path, required=True)
    args = parser.parse_args()
    result = stage() if args.action == "stage" else collect(args.profile_current)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
