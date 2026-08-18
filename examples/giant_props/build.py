"""Build driver for the Giant Props pack.

Usage (from the repository root, venv python):

    python examples/giant_props/build.py <mod_key> prop   # handoff -> mod files
    python examples/giant_props/build.py <mod_key> dist   # mod -> dist ZIP
    python examples/giant_props/build.py <mod_key> all
    python examples/giant_props/build.py --list

Cooked-texture stages (see prop_builder.cooked_is_current):

    <mod_key> harvest        pull the game's cooked DDS cache into
                             textures_cooked/ and record the sha256 of each
                             source PNG in textures_cooked/<mod_id>.harvest.json
    <mod_key> adopt-harvest  certify an ALREADY-harvested textures_cooked/ as a
                             bake of today's PNGs, without touching the game
                             cache. Only correct when you know the sources have
                             not changed since the cook — say, a harvest taken
                             on a machine that no longer has the cache. Getting
                             this wrong is the centrifuge bug: the game renders
                             a bake of textures nobody can see any more.

The Blender stage runs separately (deterministic generator, Blender 4.5.4):

    & $blender454 --factory-startup --background \
        --python examples/giant_props/<mod_key>/blender/create_<mod_key>.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parent


def discover_mods() -> list[str]:
    keys = []
    for child in sorted(PACK_ROOT.iterdir()):
        if child.is_dir() and (child / "spec.py").is_file():
            keys.append(child.name)
    return keys


def load_spec(mod_key: str):
    example_root = PACK_ROOT / mod_key
    spec_path = example_root / "spec.py"
    if not spec_path.is_file():
        raise SystemExit(f"unknown mod key: {mod_key} (try --list)")
    loader_spec = importlib.util.spec_from_file_location(f"giant_props_spec_{mod_key}", spec_path)
    module = importlib.util.module_from_spec(loader_spec)
    loader_spec.loader.exec_module(module)
    return module


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] == "--list":
        for key in discover_mods():
            print(key)
        return
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    mod_key, stage = sys.argv[1], sys.argv[2]
    if stage not in ("textures", "prop", "dist", "all", "harvest", "adopt-harvest"):
        raise SystemExit(f"unknown stage: {stage}")
    sys.path.insert(0, str(PACK_ROOT))
    spec = load_spec(mod_key)
    example_root = PACK_ROOT / mod_key
    if stage in ("textures", "all"):
        from proplib import prop_builder

        prop_builder.ensure_textures(example_root, spec)
    if stage in ("prop", "all"):
        from proplib import prop_builder

        prop_builder.build_prop(example_root, spec)
    if stage == "harvest":
        import shutil

        from proplib import prop_builder

        # Default is the sentinel test profile, which is where the live
        # gates cook. A mod that is only ever exercised by hand cooks in
        # the player's REAL profile instead, so that root is overridable:
        #
        #   GIANT_PROPS_PROFILE=%LOCALAPPDATA%\BeamNG\BeamNG.drive\current
        #
        # Point it at the profile that actually loaded the serial you are
        # shipping — the manifest below certifies the bake against today's
        # source PNGs either way, so a stale profile fails loudly rather
        # than shipping someone else's cook.
        profile = os.environ.get("GIANT_PROPS_PROFILE")
        cache_root = (
            Path(os.path.expandvars(profile))
            if profile
            else Path.home() / "AppData/Local/beamng-mcp/test-users/BeamNG-0.38.6/current"
        )
        cache = cache_root / "temp/vehicles" / spec.MOD_ID / "textures"
        target = example_root / "textures_cooked"
        target.mkdir(exist_ok=True)
        harvested: set[str] = set()
        poisoned = 0
        if cache.is_dir():
            for dds in sorted(cache.glob("*.dds")):
                # A sha256 certifies identity, not usefulness. `steel.normal`
                # was once harvested at ZERO BYTES from a session whose log
                # ends mid-import on exactly that texture, and the manifest
                # certified it happily. Reject anything that is not a real
                # DDS: 1,398,281 bytes is the engine's 1024x1024 "IMPORTING
                # TEXTURE" placeholder (a queued-but-unfinished conversion),
                # and a valid file needs the magic, a 124-byte header and
                # surface data behind it.
                blob = dds.read_bytes()
                if (
                    len(blob) == 1398281
                    or len(blob) <= 148
                    or blob[:4] != b"DDS "
                    or int.from_bytes(blob[4:8], "little") != 124
                ):
                    poisoned += 1
                    continue
                shutil.copyfile(dds, target / dds.name)
                harvested.add(dds.name)
        print(
            f"harvested {len(harvested)} cooked DDS for {spec.MOD_ID}"
            + (f" (SKIPPED {poisoned} unfinished placeholder files)" if poisoned else "")
        )
        if harvested:
            # Stamp ONLY what this run copied. A cook is a bake of whatever
            # PNG the game last loaded, so hashing the untouched leftovers
            # of an older harvest against today's sources would certify a
            # bake nobody verified — the exact silent-shadowing failure the
            # guard exists to catch.
            recorded = prop_builder.write_harvest_manifest(
                example_root, spec.MOD_ID, stamp=harvested
            )
            print(f"recorded {len(recorded)} source hashes in {spec.MOD_ID}.harvest.json")
        else:
            print(
                "no cooked DDS found; harvest manifest left alone"
                f" (looked in {cache})"
            )
    if stage == "adopt-harvest":
        from proplib import prop_builder

        target = example_root / "textures_cooked"
        cooked = sorted(target.glob("*.dds")) if target.is_dir() else []
        if not cooked:
            raise SystemExit(f"nothing to adopt: no cooked DDS in {target}")
        prop_builder.ensure_textures(example_root, spec)
        recorded = prop_builder.write_harvest_manifest(example_root, spec.MOD_ID)
        orphans = [dds.name for dds in cooked if dds.name not in recorded]
        print(
            f"adopted {len(recorded)} cooked DDS for {spec.MOD_ID} as bakes of the"
            " current textures/ PNGs"
        )
        for name in orphans:
            print(f"  no source PNG, not adopted: {name}")
    if stage in ("dist", "all"):
        from proplib import packaging

        packaging.build_distribution(example_root, spec.MOD_ID, spec.ZIP_BASENAME)


if __name__ == "__main__":
    main()
