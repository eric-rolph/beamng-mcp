"""The B4 props as level-tree outputs: what ``level_writer`` renders and what it allowlists.

Same split B3's ``forest_build`` uses, for the same reason:

* **rendered** -- the props group's JSONL, the four ``.prefab`` cluster files and the props
  material document.  Small pure functions, so ``render_level()`` emits them and
  ``build_level_zip.validate_level_tree`` byte-compares them on every release.
* **bulk** -- the 12 DAEs and the 55 cooked maps.  Allowlisted from the two authoring
  manifests and verified against their sha256s by :func:`verify`.

Re-cut order (each writes its manifest into ``authoring/``)::

    prop_textures.py       -> ericrolph_hot_potato_arena_prop_textures.json
    build_prop_shapes.py   -> ericrolph_hot_potato_arena_prop_shapes.json
    place_props.py         -> ericrolph_hot_potato_arena_props_place.json
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from examples.hot_potato_arena.level import props_spec as ps

EXAMPLE_ROOT = ps.EXAMPLE_ROOT
AUTHORING = EXAMPLE_ROOT / "authoring"
SHAPES_MANIFEST = AUTHORING / f"{ps.LEVEL_ID}_prop_shapes.json"
TEXTURES_MANIFEST = AUTHORING / f"{ps.LEVEL_ID}_prop_textures.json"
PLACE_MANIFEST = AUTHORING / f"{ps.LEVEL_ID}_props_place.json"
IMPOSTERS_MANIFEST = AUTHORING / f"{ps.LEVEL_ID}_prop_imposters.json"
#: r3: the engine's own ``.cdae`` bakes, harvested out of the sentinel's ``temp/`` before the
#: purge and staged beside the DAE they were baked from.
#:
#: r2 measured QB-8 at 0.096 and handed it to B6.  Critic pass 2 then showed that B4's OWN
#: certified boot had cooked exactly the 75 missing siblings into ``temp/`` and swept all 75
#: unread -- 12 of them B4's own props -- while the same boot was already harvesting 14
#: imposter atlases out of the same directory.  The round held the fix and deleted it.
#:
#: This manifest is EXPLICIT rather than globbed: it lists the exact relative paths staged,
#: wherever in the tree they live, so composing it into ``bulk_members`` cannot silently
#: enumerate another round's directory (the shared-composition family the orchestrator has
#: patched three times).  Every row pins its SOURCE DAE's sha256, so a bake that goes stale
#: because B1 or B3 re-cooked its shape fails :func:`verify` loudly instead of shipping a
#: mesh the engine will prefer over the DAE beside it.
HARVEST_MANIFEST = AUTHORING / f"{ps.LEVEL_ID}_prop_harvest.json"


class PropBuildError(RuntimeError):
    """A B4 manifest is missing or disagrees with the tree."""


def available() -> bool:
    return all(p.is_file() for p in (SHAPES_MANIFEST, TEXTURES_MANIFEST, PLACE_MANIFEST))


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PropBuildError(f"missing B4 manifest {path}; re-run the prop build scripts")
    return json.loads(path.read_text(encoding="utf-8"))


def shapes_manifest() -> dict[str, Any]:
    return _load(SHAPES_MANIFEST)


def textures_manifest() -> dict[str, Any]:
    return _load(TEXTURES_MANIFEST)


def place_manifest() -> dict[str, Any]:
    return _load(PLACE_MANIFEST)


def dae_members() -> tuple[str, ...]:
    return tuple(sorted(row["relative"] for row in shapes_manifest()["shapes"].values()))


def texture_members() -> tuple[str, ...]:
    return tuple(sorted(textures_manifest()["files"]))


def imposter_members(level_root: Path) -> tuple[str, ...]:
    """Harvested atlases beside the DAEs (the engine bakes them at level load, B3 r5)."""

    if not IMPOSTERS_MANIFEST.is_file():
        return ()
    manifest = json.loads(IMPOSTERS_MANIFEST.read_text(encoding="utf-8"))
    files = manifest.get("files", {})
    return tuple(sorted(name for name in files if (level_root / name).is_file()))


def harvest_manifest() -> dict[str, Any]:
    if not HARVEST_MANIFEST.is_file():
        return {"files": {}}
    return json.loads(HARVEST_MANIFEST.read_text(encoding="utf-8"))


def harvest_members(level_root: Path) -> tuple[str, ...]:
    """The engine bakes actually staged in the tree right now (QB-8).

    Shaped like :func:`imposter_members`: a member only ships when the file is there, so a
    tree without a harvest still builds -- it just fails QB-8, loudly and by name.
    """

    files = harvest_manifest().get("files", {})
    return tuple(sorted(name for name in files if (level_root / name).is_file()))


def bulk_members(level_root: Path | None = None) -> tuple[str, ...]:
    members = [*dae_members(), *texture_members()]
    if level_root is not None:
        members.extend(imposter_members(level_root))
        members.extend(harvest_members(level_root))
    return tuple(sorted(set(members)))


def rendered_outputs() -> dict[str, bytes]:
    from examples.hot_potato_arena.level import place_props as placer

    return placer.rendered_outputs()


def verify(level_root: Path) -> dict[str, list[str]]:
    problems: dict[str, list[str]] = {"missing": [], "changed": [], "stale_harvest": []}
    expected: dict[str, str] = {}
    for row in shapes_manifest()["shapes"].values():
        expected[row["relative"]] = row["sha256"]
    for name, row in textures_manifest()["files"].items():
        expected[name] = row["sha256"]
    for relative, digest in sorted(expected.items()):
        path = level_root / relative
        if not path.is_file():
            problems["missing"].append(relative)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems["changed"].append(relative)
    # a harvested bake is only valid for the shape it was baked FROM.  The engine prefers a
    # .cdae over the .dae beside it, so a stale one silently ships the old mesh -- exactly
    # the failure mode B3 r5 recorded for a stale imposter atlas, one layer down.
    for name, row in sorted(harvest_manifest().get("files", {}).items()):
        path = level_root / name
        if not path.is_file():
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            problems["changed"].append(name)
        source = level_root / str(row["source"])
        if not source.is_file():
            problems["stale_harvest"].append(f"{name}: source {row['source']} is gone")
        elif hashlib.sha256(source.read_bytes()).hexdigest() != row["source_sha256"]:
            problems["stale_harvest"].append(f"{name}: {row['source']} was re-cooked since")
    return problems
