"""Rebuild the terrain intermediates for one map from a released level ZIP.

`critic_sheets.py` reads the built level plus `data/terrain/dem.npy` and
`data/terrain/layer.npy`, which the fetch and terrain stages write. Those stages need
the GIS hosts, so a session that cannot reach them could not render a sheet for a map
it had not built - which, for a session, was every map.

The published ZIP carries `theTerrain.ter`, and that file holds the same two arrays:
`heightmap.write_ter` documents the layout and `heightmap.encode` is exactly
invertible given `min_elevation_m` and `max_height_m`, both of which the handoff
records. So the sheets can be rendered from a download.

Usage (from the repository root):

    curl -sSLO https://github.com/eric-rolph/beamng-mcp/releases/download/\
        gis-maps-v1/<key>_ericrolph.zip
    python examples/gis_maps/rehydrate_release.py <key> --zip <key>_ericrolph.zip
    python examples/gis_maps/critic_sheets.py <key>

Pass the release's own `ericrolph_<key>.handoff.json` as ``--handoff`` whenever the
tree has moved on since the build that was published; the tracked handoff describes a
level the ZIP does not contain, and the numbers will not line up.
"""

from __future__ import annotations

import argparse
import json
import struct
import zipfile
from pathlib import Path

import numpy as np

PACK_ROOT = Path(__file__).resolve().parent


def read_ter(path: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """The u16 heights, the u8 layer map (both south-up) and the material names."""

    blob = path.read_bytes()
    version, size = struct.unpack_from("<BI", blob, 0)
    if version != 9:
        raise SystemExit(f"{path}: TerrainFile version {version}, expected 9")
    off = 5
    heights = np.frombuffer(blob, "<u2", size * size, off).reshape(size, size)
    off += 2 * size * size
    layer = np.frombuffer(blob, "u1", size * size, off).reshape(size, size)
    off += size * size
    (count,) = struct.unpack_from("<I", blob, off)
    off += 4
    names = []
    for _ in range(count):
        (length,) = struct.unpack_from("<B", blob, off)
        off += 1
        names.append(blob[off : off + length].decode("utf-8"))
        off += length
    return heights, layer, names


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("key")
    ap.add_argument("--zip", type=Path, help="release ZIP to unpack into <key>/mod/ first")
    ap.add_argument(
        "--handoff", type=Path, help="handoff describing the ZIP, if not the tracked one"
    )
    args = ap.parse_args(argv)

    root = PACK_ROOT / args.key
    if not root.is_dir():
        raise SystemExit(f"no such map: {args.key}")
    if args.zip:
        with zipfile.ZipFile(args.zip) as zf:
            zf.extractall(root / "mod")

    levels = root / "mod" / "levels"
    if not levels.is_dir():
        raise SystemExit(f"{levels} is missing: unpack the release ZIP there, or pass --zip")
    level_root = next(levels.iterdir())
    handoff_path = args.handoff or (root / "authoring" / f"{level_root.name}.handoff.json")
    terrain = json.loads(handoff_path.read_text(encoding="utf-8"))["terrain"]

    heights, layer, names = read_ter(level_root / "theTerrain.ter")
    if names != list(terrain["materials"]):
        raise SystemExit(
            f"the level's materials are not the handoff's - wrong handoff for this ZIP?\n"
            f"  level:   {names}\n  handoff: {terrain['materials']}"
        )
    lo = float(terrain["min_elevation_m"])
    step = float(terrain["max_height_m"]) / 65536.0
    # encode() wrote row 0 = south; every array the pipeline passes around is north-up.
    dem = (lo + heights[::-1, :].astype("float64") * step).astype("float32")
    layer = np.ascontiguousarray(layer[::-1, :])

    # The reconstruction is exact to within one step of the 16-bit ladder. Anything
    # further out means the handoff describes a different build, and a sheet rendered
    # against it would be a picture of neither.
    for what, rebuilt, recorded in (
        ("lowest", float(dem.min()), lo),
        ("highest", float(dem.max()), float(terrain["max_elevation_m"])),
    ):
        if abs(rebuilt - recorded) > step:
            raise SystemExit(
                f"{what} sample {rebuilt:.3f} m against the handoff's {recorded:.3f} m, "
                f"more than the {step * 100:.2f} cm quantisation step"
            )

    out = root / "data" / "terrain"
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "dem.npy", dem)
    np.save(out / "layer.npy", layer)
    print(
        f"{args.key}: {heights.shape[0]} samples, {len(names)} materials, "
        f"{dem.min():.1f}-{dem.max():.1f} m, step {step * 100:.2f} cm -> {out}"
    )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
