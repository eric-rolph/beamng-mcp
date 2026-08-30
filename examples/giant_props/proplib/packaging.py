"""Deterministic distribution ZIP builder for the Giant Props pack.

Follows the Cannon Car Wash release policies:

- ``ZIP_STORED`` members only (level-9 DEFLATE is not byte-stable across
  zlib versions, which broke a cross-runtime SHA-256 lock once already),
- a fixed per-release cache epoch timestamp (BeamNG compares Collada source
  timestamps to compiled ``.cdae`` cache entries; bump the epoch whenever a
  shipped DAE changes),
- only approved BeamNG top-level folders inside the archive, no wrapper
  folder, no source/evidence files, no README,
- one stable ZIP filename per mod; version lives in metadata, not the name.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

APPROVED_ROOTS = {
    "vehicles",
    "levels",
    "art",
    "assets",
    "lua",
    "scripts",
    "ui",
    "gameplay",
    "settings",
    "trackEditor",
    "vehicleGroups",
}

# BeamNG recompiles a cached .cdae/cooked texture only when the shipped
# member timestamp is NEWER than the cache. A fixed epoch served stale
# first-build visuals forever, and content-hash timestamps (random within a
# day) still looked "older" half the time (both proven in play-testing
# 2026-07-22). Timestamps must therefore be MONOTONIC: a per-mod build
# serial, persisted in dist/ and bumped whenever member content changes,
# mapped to an always-advancing date.
#
# THE FUTURE-DATE TRAP (2026-08-14, pachinko_tower build 34). "Always
# advancing" was implemented as SERIAL_BASE + serial DAYS, which overtook the
# calendar the moment a mod passed ~a serial a day: pachinko at serial 34 was
# stamped 2026-09-04 and the published centrifuge at serial 147 was stamped
# 2026-12-26. A member dated in the FUTURE is newer than a cache entry the
# engine writes NOW, and it stays newer forever, so the staleness test never
# clears:
#
#   material asks for x.color.png -> cache /temp/.../x.color.dds is "stale"
#   -> TextureCooker queues an import -> while it is in flight the engine
#   binds core/art/importingMat.dds (the green "IMPORTING TEXTURE"
#   checkerboard) -> the cook lands, the next request finds it stale AGAIN.
#
# On a 100-texture prop the queue never drains and the player drives a tower
# rendered almost entirely in placeholder. Measured live, cold isolated
# profile, dx11 windowed, one variable changed (A/B in this order):
#
#   members dated 2026-09-04  ->  267 cook starts rising to 652 over 85
#                                 textures, steel.color re-imported 37x,
#                                 whole prop on IMPORTING TEXTURE
#   members dated 2026-08-01  ->  84 cook starts, exactly one per texture,
#                                 every surface correct
#
# (Which few materials looked "fine" in the broken build is a race between a
# cook landing and the next invalidation, not a property of those materials -
# hazard and copper were among the MOST re-cooked and still rendered.)
#
# So the rule is monotonic AND NEVER IN THE FUTURE. ``_serial_timestamp``
# clamps to the build's own wall clock, and ``future_dated_members`` is a hard
# gate so this can never ship again.
#
# THE STALE-CACHE TRAP is the same comparison from the other side (2026-08-29,
# hot_potato v2). The engine keeps whichever of source/cache is NEWER, so a
# member stamped in the past loses to any cache the machine cooked later:
# hot_potato's serial-13 members read 2026-08-14, the player's real profile
# cooked v1's .cdae on 2026-08-25, and the v2 Gateway Arch never imported —
# the game rendered the v1 gantry against materials v2 no longer ships
# (orange NO MATERIAL) for four days of otherwise-current deploys. A
# synthetic serial-days date is monotonic against other BUILDS but not
# against a CACHE, whose mtime is the wall clock.
#
# So every CONTENT CUT is stamped with the wall-clock moment the serial
# bumped, recorded in serial.json as ``stamped_at``. That stamp postdates
# every cache cooked from any earlier cut, stays fixed for no-op rebuilds
# (which restores byte-reproducibility for mods past the old clamp), and is
# still clamped under the build clock so the future-date trap stays closed.
# serial.json files from before this scheme have no ``stamped_at``; they keep
# the legacy serial-days stamp so their shipped locks remain verifiable, and
# they migrate the next time their content actually changes.
SERIAL_BASE = datetime.date(2026, 8, 1)

# How far behind "now" a stamp sits when it is derived from the build clock.
# It only has to be in the past; one minute stays safely on the correct side
# of clock skew between the build and the engine.
CLAMP_MARGIN = datetime.timedelta(minutes=1)

EXCLUDED_ROOTS = {"mod_info"}

# Shipping raw authoring PNGs under a vehicle's ``textures/`` directory is an
# ADVISORY, not an error.
#
# It was a hard gate for a few hours on 2026-08-14, on the theory that a
# runtime PNG->DDS conversion is what put pachinko_tower on the "IMPORTING
# TEXTURE" checkerboard. That theory is FALSIFIED. The A/B in THE FUTURE-DATE
# TRAP above holds the texture bytes fixed and moves only the ZIP member date:
# raw PNGs cook exactly once and render correctly when the date is sane, and
# pre-cooked DDS was only ever a workaround that happened to sidestep the
# staleness test because a DDS is never cooked at all.
#
# What the harvest still buys is a player who pays zero cook on first load,
# and what it costs is size: pachinko_tower is 9.7 MB shipping its 100 source
# PNGs and 30.3 MB shipping the 85 harvested DDS. That is a per-mod judgement
# call, so the build prints it and moves on.
UNCOOKED_OVERRIDE_ENV = "GIANT_PROPS_ALLOW_UNCOOKED_TEXTURES"


def uncooked_texture_members(members: list[str]) -> list[str]:
    """Archive-relative paths of raw PNGs under any ``vehicles/*/textures/``."""

    found = []
    for relative in members:
        parts = relative.split("/")
        if len(parts) < 4 or parts[0] != "vehicles" or parts[2] != "textures":
            continue
        if parts[-1].lower().endswith(".png"):
            found.append(relative)
    return sorted(found)


def _serial_timestamp(
    serial: int,
    now: datetime.datetime | None = None,
    stamped_at: str | None = None,
) -> tuple[int, int, int, int, int, int]:
    """Monotonic member timestamp that is never in the future.

    With ``stamped_at`` (recorded in serial.json when the serial bumped) the
    stamp IS that cut's wall-clock moment: newer than any cache cooked from an
    earlier cut (THE STALE-CACHE TRAP above) and byte-stable across no-op
    rebuilds. Without it — a serial.json from before the scheme — the legacy
    serial-days stamp is reproduced so existing locks stay verifiable. Both
    paths clamp under the build clock so a skewed or hand-edited stamp can
    never trip THE FUTURE-DATE TRAP.
    """

    now = now or datetime.datetime.now()
    ceiling = now - CLAMP_MARGIN
    if stamped_at:
        candidate = datetime.datetime.fromisoformat(stamped_at)
    else:
        candidate = datetime.datetime.combine(
            SERIAL_BASE + datetime.timedelta(days=serial), datetime.time()
        )
    stamp = min(candidate, ceiling)
    return (stamp.year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)


def future_dated_members(
    archive: zipfile.ZipFile, now: datetime.datetime | None = None
) -> list[str]:
    """Members stamped later than ``now`` — see THE FUTURE-DATE TRAP above."""

    now = now or datetime.datetime.now()
    late = []
    for info in archive.infolist():
        if datetime.datetime(*info.date_time) > now:
            late.append(f"{info.filename} @ {datetime.datetime(*info.date_time).isoformat()}")
    return sorted(late)


def build_distribution(example_root: Path, mod_id: str, zip_basename: str) -> dict[str, Any]:
    mod_root = example_root / "mod"
    if not mod_root.is_dir():
        raise FileNotFoundError(f"mod tree is missing: {mod_root}")
    members: list[Path] = []
    for path in sorted(mod_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(mod_root)
        root = relative.parts[0]
        if root in EXCLUDED_ROOTS:
            continue
        if root not in APPROVED_ROOTS:
            raise ValueError(f"unapproved top-level folder in mod tree: {relative}")
        members.append(path)
    if not members:
        raise ValueError("mod tree contains no distributable files")

    relatives = [path.relative_to(mod_root).as_posix() for path in members]
    uncooked = uncooked_texture_members(relatives)
    if uncooked:
        print(
            f"{mod_id}: shipping {len(uncooked)} source PNG(s) under "
            f"vehicles/{mod_id}/textures/; BeamNG cooks each of them once on "
            "first load. `build.py <mod_key> harvest` trades a larger download "
            "for a zero-cook first load.",
            file=sys.stderr,
        )

    dist_root = example_root / "dist"
    dist_root.mkdir(parents=True, exist_ok=True)
    zip_path = dist_root / zip_basename

    content_digest = hashlib.sha256()
    for path in members:
        content_digest.update(path.relative_to(mod_root).as_posix().encode())
        content_digest.update(path.read_bytes())
    content_sha = content_digest.hexdigest()
    serial_path = dist_root / f"{mod_id}.serial.json"
    serial_state = {"serial": 0, "content_sha": None}
    if serial_path.is_file():
        serial_state = json.loads(serial_path.read_text(encoding="utf-8"))
    if serial_state.get("content_sha") != content_sha:
        serial_state = {
            "serial": int(serial_state.get("serial", 0)) + 1,
            "content_sha": content_sha,
            # The cut's wall-clock moment, the member stamp from now on: see
            # THE STALE-CACHE TRAP above. Recorded once, at the bump, so
            # re-zipping unchanged content reproduces the exact bytes.
            "stamped_at": (datetime.datetime.now() - CLAMP_MARGIN).isoformat(
                timespec="seconds"
            ),
        }
        serial_path.write_text(
            json.dumps(serial_state, indent=2, sort_keys=True) + chr(10),
            encoding="utf-8",
            newline=chr(10),
        )
    timestamp = _serial_timestamp(
        int(serial_state["serial"]), stamped_at=serial_state.get("stamped_at")
    )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in members:
            relative = path.relative_to(mod_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=timestamp)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())

    # HARD GATE. A future-dated member is the permanent-recook bug; nothing
    # downstream can see it and no amount of looking at the mod tree reveals
    # it, so it is checked here, on the artefact, every single build.
    with zipfile.ZipFile(zip_path) as archive:
        late = future_dated_members(archive)
    if late:
        zip_path.unlink(missing_ok=True)
        listed = "\n".join(f"    {name}" for name in late[:6])
        raise ValueError(
            f"{mod_id}: {len(late)} ZIP member(s) are stamped in the FUTURE. "
            "BeamNG treats a future-dated source as permanently newer than its "
            "cooked cache and re-cooks it forever, so the prop renders on the "
            "IMPORTING TEXTURE placeholder (pachinko_tower build 34).\n"
            f"{listed}"
        )

    payload = zip_path.read_bytes()
    lock = {
        "mod_id": mod_id,
        "zip": zip_basename,
        "members": len(members),
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "build_serial": int(serial_state["serial"]),
        "timestamp_scheme": (
            "cut-wallclock@serial-bump"
            if serial_state.get("stamped_at")
            else "monotonic-serial-days@2026-08-01-clamped-to-build-clock"
        ),
        "member_timestamp": datetime.datetime(*timestamp).isoformat(),
    }
    lock_path = dist_root / f"{mod_id}.lock.json"
    lock_path.write_text(
        json.dumps(lock, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(lock, sort_keys=True))
    return lock
