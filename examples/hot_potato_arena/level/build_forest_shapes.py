"""Drive ``blender_forest.py`` ONE SHAPE PER BLENDER PROCESS, then merge the manifests.

    .\\.venv\\Scripts\\python.exe -m examples.hot_potato_arena.level.build_forest_shapes \\
        --out examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena \\
        --cache examples/hot_potato_arena/cc0_cache \\
        --manifest authoring/ericrolph_hot_potato_arena_forest_shapes.json

Why a process per shape.  AGENTS.md L710 records that Blender's Collada exporter is not
deterministic and that the fix is quantisation; ``blender_forest`` applies that fix, and the
18 generated conifers and every card shape then reproduce byte-for-byte.  The 36 CC0 MODEL
shapes go through ``bpy.ops.mesh.remove_doubles``, the Decimate modifier and
``bpy.ops.mesh.convex_hull``, and those three are sensitive to what ran BEFORE them in the
same Blender session: two full 63-shape runs of an unchanged generator agreed on 62 shapes
and disagreed on ``windthrow_roots``.  Three runs of the SAME shape in three fresh processes
agreed exactly -- so the state that leaks is the session's, and one process per shape removes
it.  The cost is about four minutes of process starts for a build that runs once a round, and
what it buys is a lock a critic can re-cut and verify.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from examples.hot_potato_arena.level import forest_spec as fs

REPO = Path(__file__).resolve().parents[3]
BLENDER = Path(r"C:\Users\ericr\Applications\Blender\4.5.4\blender.exe")
SCRIPT = REPO / "examples/hot_potato_arena/level/blender_forest.py"


def keys() -> list[str]:
    return [s["key"] for s in fs.SPECIES] + [c["key"] for c in fs.COVER_SHAPES]


def run_one(key: str, out_root: Path, cache: Path, blender: Path, scratch: Path) -> dict:
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
        "--manifest",
        str(manifest),
        "--only",
        key,
    ]
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, paths from this module
        command, capture_output=True, text=True, cwd=str(REPO), check=False
    )
    if completed.returncode != 0 or not manifest.is_file():
        tail = "\n".join((completed.stdout + completed.stderr).splitlines()[-25:])
        raise SystemExit(f"blender failed for {key} (rc {completed.returncode}):\n{tail}")
    return json.loads(manifest.read_text(encoding="utf-8"))


def build(
    out_root: Path,
    cache: Path,
    blender: Path,
    only: set[str] | None = None,
    existing: Path | None = None,
) -> dict:
    """Build the shapes and return the manifest.

    r10: a ``--only`` run MERGES into the manifest already on disk instead of replacing it.
    Rewriting it truncated the shipped
    ``authoring/ericrolph_hot_potato_arena_forest_shapes.json`` to just the shapes that run --
    a nine-shape re-cut left a nine-row manifest, and a one-shape re-cut left ONE row, with
    every static gate that reads the manifest then measuring almost nothing and passing.  This
    is the same shared-file overwrite family `level_facts` records for ``stage_harvest.py``
    (2026-09-09) and for ``mission_group_records`` / ``main.decals.json``: **merge, never
    rewrite.**  A full run still replaces every row it rebuilds, so nothing goes stale.
    """

    started = time.time()
    merged: dict = {"species": {}, "covers": {}}
    if only and existing and existing.is_file():
        prior = json.loads(existing.read_text(encoding="utf-8"))
        for section in ("species", "covers"):
            merged[section].update(prior.get(section, {}))
        for field in ("blender", "collada_decimals", "bb_dim", "shape_seed"):
            if field in prior:
                merged.setdefault(field, prior[field])
        merged["merged_into_an_existing_manifest"] = sorted(only)
    with tempfile.TemporaryDirectory(prefix="hp_forest_shapes_") as scratch_name:
        scratch = Path(scratch_name)
        for index, key in enumerate(keys(), start=1):
            if only and key not in only:
                continue
            part = run_one(key, out_root, cache, blender, scratch)
            for section in ("species", "covers"):
                merged[section].update(part[section])
            merged.setdefault("blender", part["blender"])
            merged.setdefault("collada_decimals", part["collada_decimals"])
            merged.setdefault("bb_dim", part["bb_dim"])
            merged.setdefault("shape_seed", part["shape_seed"])
            print(f"[shapes] {index:2d}/{len(keys())} {key}", flush=True)
    merged["level_id"] = fs.LEVEL_ID
    merged["one_process_per_shape"] = True
    merged["seconds"] = round(time.time() - started, 1)
    merged["dae_count"] = len(merged["species"]) + len(merged["covers"])
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
    manifest = build(
        arguments.out, arguments.cache, arguments.blender, only, existing=arguments.manifest
    )
    arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
    arguments.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"[shapes] {manifest['dae_count']} DAEs in {manifest['seconds']}s -> {arguments.manifest}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
