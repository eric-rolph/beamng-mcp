"""The B3 forest as level-tree outputs: what ``level_writer`` renders and what it allowlists.

The forest splits in two by size, and the split is deliberate:

* **rendered** -- ``art/forest/managedItemData.json``, the vegetation group's JSONL and the
  five ``*.materials.json`` documents.  Small, pure functions of ``forest_spec``, so
  ``level_writer.render_level()`` emits them and ``build_level_zip.validate_level_tree``
  byte-compares them on every release like every other generated file.
* **bulk** -- the 63 DAEs (14.8 MB), the 141 cooked maps (300 MB) and the 54 ``forest4``
  instance files (31 MB).  Re-rendering those three times per ``build_distribution`` call
  (``expected_members`` + two ``validate_level_tree`` passes) would mean half a gigabyte of
  churn and a 2048-square Poisson placement per pass, so they are allowlisted from the three
  authoring manifests the build scripts write and verified against those manifests' sha256s by
  :func:`verify` and by ``tests/test_hot_potato_forest.py`` -- the same contract
  ``level_writer.dae_members()`` already used for the Blender placeholder shapes.

Re-cut order (all three write their manifest into ``authoring/``)::

    blender_forest.py   -> ericrolph_hot_potato_arena_forest_shapes.json
    forest_textures.py  -> ericrolph_hot_potato_arena_forest_textures.json
    plant_forest.py     -> ericrolph_hot_potato_arena_forest_plant.json
"""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from examples.hot_potato_arena.level import forest_spec as fs

EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
AUTHORING = EXAMPLE_ROOT / "authoring"
SHAPES_MANIFEST = AUTHORING / f"{fs.LEVEL_ID}_forest_shapes.json"
TEXTURES_MANIFEST = AUTHORING / f"{fs.LEVEL_ID}_forest_textures.json"
PLANT_MANIFEST = AUTHORING / f"{fs.LEVEL_ID}_forest_plant.json"
KEEPOUT_PROOF = AUTHORING / f"{fs.LEVEL_ID}_forest_keepout.json"
#: r4 (critic r3 D8).  The imposter atlas is the only shipped artefact that is BAKED rather
#: than built -- the engine writes it, the live gate copies it out of ``temp/``, and nothing
#: in three rounds noticed that it had not been re-baked since r1 while the tree under it was
#: rebuilt twice.  The harvest now records, per atlas, the sha256 of the DAE it was baked
#: FROM, and a static gate refuses a shipped atlas whose DAE has moved since.
IMPOSTERS_MANIFEST = AUTHORING / f"{fs.LEVEL_ID}_forest_imposters.json"


class ForestBuildError(RuntimeError):
    """A B3 manifest is missing or disagrees with the tree."""


def available() -> bool:
    return all(p.is_file() for p in (SHAPES_MANIFEST, TEXTURES_MANIFEST, PLANT_MANIFEST))


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ForestBuildError(f"missing B3 manifest {path}; re-run the forest build scripts")
    return json.loads(path.read_text(encoding="utf-8"))


def shapes_manifest() -> dict[str, Any]:
    return _load(SHAPES_MANIFEST)


def textures_manifest() -> dict[str, Any]:
    return _load(TEXTURES_MANIFEST)


def plant_manifest() -> dict[str, Any]:
    return _load(PLANT_MANIFEST)


def dae_members() -> tuple[str, ...]:
    manifest = shapes_manifest()
    rows = list(manifest["species"].values()) + list(manifest["covers"].values())
    return tuple(sorted(row["relative"] for row in rows))


def texture_members() -> tuple[str, ...]:
    return tuple(sorted(textures_manifest()["files"]))


def forest4_members() -> tuple[str, ...]:
    return tuple(sorted(name for name in plant_manifest()["files"] if name.startswith("forest/")))


def imposter_members(level_root: Path) -> tuple[str, ...]:
    """The harvested atlases beside their DAEs (written by the live imposter harvest)."""
    out = []
    for relative in dae_members():
        for suffix in (".imposter.dds", ".imposter_normals.dds"):
            if (level_root / (relative + suffix)).is_file():
                out.append(relative + suffix)
    return tuple(sorted(out))


def imposters_manifest() -> dict[str, Any]:
    return _load(IMPOSTERS_MANIFEST)


# ------------------------------------------------------------------- reading a baked atlas
def dds_alpha(payload: bytes) -> tuple[int, int, Any]:
    """(width, height, alpha) of a DXT3/DXT5 DDS's TOP mip, as a uint8 array.

    The imposter is the one shipped artefact B3 does not author, so it has to be read back
    from its own bytes.  Only the alpha plane is needed -- it IS the billboard's silhouette --
    and both block formats put it in the first eight bytes of each 16-byte block: BC2 stores
    16 explicit 4-bit values, BC3 two endpoints and 16 three-bit indices.
    """
    import struct

    import numpy as np

    if payload[:4] != b"DDS ":
        raise ForestBuildError("not a DDS")
    _size, _flags, height, width, _pitch, _depth, _mips = struct.unpack_from("<7I", payload, 4)
    fourcc = struct.unpack_from("<4s", payload, 4 + 72 + 8)[0].decode("latin1")
    if fourcc not in ("DXT3", "DXT5"):
        raise ForestBuildError(f"unsupported imposter format {fourcc!r}")
    blocks_x, blocks_y = (width + 3) // 4, (height + 3) // 4
    data = np.frombuffer(payload, dtype=np.uint8, count=blocks_x * blocks_y * 16, offset=128)
    data = data.reshape(blocks_y, blocks_x, 16)
    if fourcc == "DXT3":
        nibbles = data[:, :, :8].reshape(blocks_y, blocks_x, 8, 1)
        values = np.concatenate([nibbles & 0x0F, nibbles >> 4], axis=3).reshape(
            blocks_y, blocks_x, 16
        )
        texels = (values * 17).astype(np.uint8)
    else:
        a0 = data[:, :, 0].astype(np.uint16)
        a1 = data[:, :, 1].astype(np.uint16)
        bits = np.zeros((blocks_y, blocks_x), dtype=np.uint64)
        for i in range(6):
            bits |= data[:, :, 2 + i].astype(np.uint64) << np.uint64(8 * i)
        index = np.stack(
            [((bits >> np.uint64(3 * k)) & np.uint64(7)).astype(np.uint8) for k in range(16)],
            axis=2,
        )
        table = np.zeros((blocks_y, blocks_x, 8), dtype=np.uint16)
        table[:, :, 0], table[:, :, 1] = a0, a1
        wide = a0 > a1
        for k in range(2, 8):
            lerp8 = ((8 - k) * a0 + (k - 1) * a1) // 7
            lerp6 = ((6 - k) * a0 + (k - 1) * a1) // 5 if k <= 5 else 0
            if k <= 5:
                table[:, :, k] = np.where(wide, lerp8, lerp6)
            else:
                table[:, :, k] = np.where(wide, lerp8, 0 if k == 6 else 255)
        texels = np.take_along_axis(table, index.astype(np.intp), axis=2).astype(np.uint8)
    texels = texels.reshape(blocks_y, blocks_x, 4, 4).transpose(0, 2, 1, 3)
    return width, height, texels.reshape(blocks_y * 4, blocks_x * 4)[:height, :width]


#: A view cell whose silhouette is shorter than this fraction of the median cell's is a
#: POLE, not a side elevation.  MEASURED (r5): r4's `f_pine_tall_a` reads 35 px against a
#: 113 px median on cells 30 and 31 (0.31) and 113 on the other thirty; italy `scots_pine`
#: reads 192-194 px on all sixteen of its 256 px cells and `cypress_tree` 237-240 on all
#: eight, so neither carries one.  Poles are a DEFAULT (`BB::INCLUDE_POLES`), not an engine
#: invariant -- stock's tree atlases are baked without them, and r5's are not either.
#:
#: The reach of this test, stated because a successor will need it: a plan view is only
#: SHORTER than a side view on a shape that is much taller than it is wide.  On r4's cut it
#: separates the two poles on 20 of 54 atlases -- every conifer and snag -- and cannot on the
#: 34 flatter deadwood and rock shapes, where the distinction does not distort the fill.
POLAR_HEIGHT_FRACTION = 0.6


def imposter_reading(
    payload: bytes, cell: int = fs.BB_DIM, floor: int = 96, detail: bool = False
) -> dict[str, Any]:
    """What the baked billboard LOOKS like: view cells used, and how full each one is.

    critic r3's D8 measurement, made B3's own so it can be gated.  The engine packs the views
    into a grid of ``BB::DIM``-pixel cells; a cell that carries a view has opaque texels in
    it, and the silhouette's BBOX FILL -- opaque texels over the area of their own bounding
    box -- says whether the billboard is a tree or a stipple.  r1's bake, still shipping in
    r3, read 0.054-0.138 against five stock maps' 0.40-0.66 and against 0.23-0.35 for the
    mesh it stands in for.

    r5 (critic r4 B1/B2) also separates the POLAR cells from the equator ring, because a
    ground camera never samples a pole and quoting a whole-atlas ``bbox_fill_min`` from one
    understates the billboard: ``f_pine_tall_a``'s minimum is 0.066 on a 35 px polar disc
    while its thirty equator views run 0.255-0.305.  A pole is found by MEASUREMENT, not by
    index -- a cell whose silhouette is under ``POLAR_HEIGHT_FRACTION`` of the median cell's
    height -- so the same function reports two poles on B3's atlases and NONE on stock's,
    which is the evidence behind the corrected engine law.
    """
    import numpy as np

    width, height, alpha = dds_alpha(payload)
    columns, rows = max(1, width // cell), max(1, height // cell)
    used, touched = 0, 0
    per_cell: list[dict[str, Any]] = []
    for row in range(rows):
        for column in range(columns):
            tile = alpha[row * cell : (row + 1) * cell, column * cell : (column + 1) * cell]
            opaque = tile >= floor
            count = int(opaque.sum())
            if count:
                touched += 1
            # `cells_used` keeps critic r3's convention -- a cell counts when it carries more
            # than 0.2 % of its own texels -- so the r1/r3/r4 and stock columns compare.
            # `cells_touched` is the weaker question the GATE asks: did this view render at
            # all?  A 8 m log seen from the pole is a legitimate sliver under the first.
            if count < 0.002 * tile.size:
                continue
            used += 1
            ys, xs = np.nonzero(opaque)
            tall = int(ys.max() - ys.min() + 1)
            wide = int(xs.max() - xs.min() + 1)
            per_cell.append(
                {
                    "cell": row * columns + column,
                    "fill": round(count / float(tall * wide), 4),
                    "height_px": tall,
                    "width_px": wide,
                    "aspect": round(wide / float(tall), 3),
                }
            )
    # r9 (B1 r9's CORRECTION_forest_medians.md): these three were UPPER medians
    # (`sorted(xs)[n // 2]`), +1.29 % on the published aggregate and +3.56 % on the worst
    # atlas.  `statistics.median` is the true median; the polar rule is unchanged.
    fills = sorted(c["fill"] for c in per_cell)
    heights = [c["height_px"] for c in per_cell]
    median_height = statistics.median(heights) if heights else 0
    polar = [c for c in per_cell if c["height_px"] < POLAR_HEIGHT_FRACTION * median_height]
    equator = sorted(c["fill"] for c in per_cell if c not in polar)
    return {
        "width": width,
        "height": height,
        "cell": cell,
        "cells": columns * rows,
        "cells_used": used,
        "cells_touched": touched,
        "bbox_fill_min": round(fills[0], 4) if fills else 0.0,
        "bbox_fill_median": round(statistics.median(fills), 4) if fills else 0.0,
        "bbox_fill_max": round(fills[-1], 4) if fills else 0.0,
        "subject_height_px_max": max(heights) if heights else 0,
        "polar_cells": [c["cell"] for c in polar],
        "equator_cells": len(equator),
        "bbox_fill_equator_min": round(equator[0], 4) if equator else 0.0,
        "bbox_fill_equator_median": round(statistics.median(equator), 4) if equator else 0.0,
        "bbox_fill_equator_max": round(equator[-1], 4) if equator else 0.0,
        **({"per_cell": per_cell} if detail else {}),
    }


def bulk_members(level_root: Path | None = None) -> tuple[str, ...]:
    """Allowlisted-but-not-rendered members: shapes, maps, instances and harvested atlases."""
    members = [*dae_members(), *texture_members(), *forest4_members()]
    if level_root is not None:
        members.extend(imposter_members(level_root))
    return tuple(sorted(set(members)))


def rendered_outputs() -> dict[str, bytes]:
    """The small text files ``level_writer.render_level`` owns."""
    from examples.hot_potato_arena.level import plant_forest as planter

    outputs = {
        "art/forest/managedItemData.json": planter._json_bytes(planter.forest_item_data()),
        "main/MissionGroup/level_objects/vegetation/items.level.json": planter._jsonl_bytes(
            planter.vegetation_records()
        ),
    }
    for family, document in planter.material_documents().items():
        outputs[f"{planter.FAMILY_DIRS[family]}/{fs.LEVEL_ID}_{family}.materials.json"] = (
            planter._json_bytes(document)
        )
    return outputs


def verify(level_root: Path) -> dict[str, list[str]]:
    """Every bulk member present and byte-identical to the manifest that produced it."""
    problems: dict[str, list[str]] = {"missing": [], "changed": []}
    expected: dict[str, str] = {}
    shapes = shapes_manifest()
    for row in list(shapes["species"].values()) + list(shapes["covers"].values()):
        expected[row["relative"]] = row["sha256"]
    for name, row in textures_manifest()["files"].items():
        expected[name] = row["sha256"]
    for name, row in plant_manifest()["files"].items():
        if name.startswith("forest/"):
            expected[name] = row["sha256"]
    for relative, digest in sorted(expected.items()):
        path = level_root / relative
        if not path.is_file():
            problems["missing"].append(relative)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems["changed"].append(relative)
    return problems
