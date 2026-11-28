"""Sample the shipped terrain under every B4 prop, then drive ``blender_props.py`` per shape.

    .\\.venv\\Scripts\\python.exe -m examples.hot_potato_arena.level.build_prop_shapes \\
        --out examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena \\
        --cache examples/hot_potato_arena/cc0_cache \\
        --manifest examples/hot_potato_arena/authoring/ericrolph_hot_potato_arena_prop_shapes.json

One Blender PROCESS per shape, for the reason ``build_forest_shapes`` records: the modifier
and operator stack leaks session state, and two full runs of an unchanged generator disagreed
on one shape out of sixty-three.  A process per shape removes it and buys a re-cuttable lock.

The ground document this writes is the ONLY terrain the Blender side sees.  Heights come from
``terrain_io.surface_z`` -- the bilinear read of the quantised grid, which report_B §3.4
measured to be the collision surface itself (``getTerrainHeight`` is the diagonal split and
differs by up to one height unit, 4.88 mm).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from examples.hot_potato_arena.level import props_spec as ps
from examples.hot_potato_arena.level import terrain_io as terrain

REPO = Path(__file__).resolve().parents[3]
BLENDER = Path(r"C:\Users\ericr\Applications\Blender\4.5.4\blender.exe")
SCRIPT = REPO / "examples/hot_potato_arena/level/blender_props.py"

#: transverse sample offsets, in half-widths, across a log's own width
OFFSETS = (-1.0, -0.5, 0.0, 0.5, 1.0)


def _log_ground(key: str, layout_name: str, extra_low: float = 0.0) -> dict[str, Any]:
    """Terrain under a tangential log, in the log's own (x along, a across) frame."""

    row = ps.log_row(layout_name)
    origin = (float(row["x"]), float(row["y"]), float(row["z_ground"]))
    heading = float(row["heading_along_decreasing_bearing"])
    ux, uy = ps.heading_vector(heading)
    vx, vy = -uy, ux
    half = float(row["length"]) / 2.0
    radius = float(row["diam"]) / 2.0
    xs: list[float] = []
    x = -half - extra_low
    step = 1.0
    while x < half:
        xs.append(round(x, 4))
        x += step
    xs.append(half)
    z = []
    for sx in xs:
        row_z = []
        for a in OFFSETS:
            wx = origin[0] + ux * sx + vx * a * radius
            wy = origin[1] + uy * sx + vy * a * radius
            row_z.append(round(float(terrain.surface_z(wx, wy)), 4))
        z.append(row_z)
    return {
        "origin": [round(c, 4) for c in origin],
        "heading": heading,
        "xs": xs,
        "offsets": list(OFFSETS),
        "z": z,
        "half_width_m": radius,
    }


def ground_document() -> dict[str, Any]:
    doc: dict[str, Any] = {}
    doc["bench_log"] = _log_ground(
        "bench_log", "bench_log", extra_low=ps.BENCH["ramp_toe_apron_m"] + 2.0
    )
    for key in ("log_north", "log_south"):
        doc[key] = _log_ground(key, key)
    return doc


def run_one(key: str, out_root: Path, cache: Path, ground: Path, blender: Path, scratch: Path):
    manifest = scratch / f"{key}.json"
    command = [
        str(blender),
        "--factory-startup",
        "--background",
        "--python",
        str(SCRIPT),
        "--",
        "--out",
        str(out_root),
        "--cache",
        str(cache),
        "--ground",
        str(ground),
        "--manifest",
        str(manifest),
        "--only",
        key,
    ]
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, paths from this module
        command, capture_output=True, text=True, cwd=str(REPO), check=False
    )
    if completed.returncode != 0 or not manifest.is_file():
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-30:])
        raise SystemExit(f"blender failed for {key} (rc {completed.returncode}):\n{tail}")
    return json.loads(manifest.read_text(encoding="utf-8"))


def build(out_root: Path, cache: Path, blender: Path, only: set[str] | None = None) -> dict:
    started = time.time()
    merged: dict[str, Any] = {"shapes": {}}
    with tempfile.TemporaryDirectory(prefix="hp_prop_shapes_") as scratch_name:
        scratch = Path(scratch_name)
        ground_path = scratch / "ground.json"
        ground = ground_document()
        ground_path.write_text(
            json.dumps(ground, indent=1, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        keys = [k for k in ps.SHAPES if not only or k in only]
        for index, key in enumerate(keys, start=1):
            part = run_one(key, out_root, cache, ground_path, blender, scratch)
            merged["shapes"].update(part["shapes"])
            for field in ("blender", "collada_decimals", "bb_property", "shape_seed"):
                merged.setdefault(field, part[field])
            print(f"[props] {index:2d}/{len(keys)} {key}", flush=True)
        merged["ground"] = ground
    merged["level_id"] = ps.LEVEL_ID
    merged["one_process_per_shape"] = True
    merged["dae_count"] = len(merged["shapes"])
    merged["seconds"] = round(time.time() - started, 1)
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--blender", type=Path, default=BLENDER)
    parser.add_argument("--only", default=None)
    arguments = parser.parse_args(argv)
    only = set(arguments.only.split(",")) if arguments.only else None
    manifest = build(arguments.out, arguments.cache, arguments.blender, only)
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"[props] {manifest['dae_count']} DAEs in {manifest['seconds']}s -> {arguments.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
