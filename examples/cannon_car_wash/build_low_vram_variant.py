"""Build the Cannon Car Wash - Low VRAM edition from the flagship mod tree.

The Low VRAM edition is a deterministically DERIVED second mod (own vehicle,
GE-extension, and scenario namespace, so it installs beside the flagship)
aimed at 2 GB graphics cards such as the GTX 1050:

- every particle emitter is removed (22 wash emitters + the 2 attract-volley
  emitters; the runtime treats wash-emitter creation failure as fatal, so the
  spec tables are emptied rather than the factory disabled),
- the 13 dynamic lights become 5 (three boosted tunnel fills + both exit
  spills; the sign keeps its calibrated emissive glow instead of its spots),
- every DDS ships with its top mip levels stripped (brush/sign atlases cap at
  1024, tileables at 512 - exact half/quarter images, no re-cook needed),
- the brush card fans may come from a CANNON_CAR_WASH_LOW_VRAM=1 Blender
  rebuild (reduced alpha-tested overdraw; collision cage, cloth, and JBeam
  are byte-identical to the flagship apart from the namespace rename).

The transform never edits the flagship tree. Inputs are the reviewed
``mod/`` release files (plus the optional card-trimmed wash DAEs) and the
output is the committed ``mod_low_vram/`` tree and its Repository archive.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import os
import re
import stat
import struct
import tempfile
import uuid
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from PIL import Image, ImageOps

if __package__:
    from . import build_distribution as flagship
else:  # direct script execution from the example directory
    import build_distribution as flagship

EXAMPLE_ROOT = Path(__file__).resolve().parent
SOURCE_MOD_ID = flagship.MOD_ID
VARIANT_MOD_ID = "ericrolph_cannon_car_wash_lowvram"
VARIANT_MOD_ROOT = EXAMPLE_ROOT / "mod_low_vram"
VARIANT_ZIP_NAME = "cannon_car_wash_lowvram_ericrolph.zip"
VARIANT_TAGID = "CANNONWSHLV"
VARIANT_REPOSITORY_ROOT = EXAMPLE_ROOT / "repository_low_vram"
SHARED_REPOSITORY_ROOT = flagship.REPOSITORY_ROOT
DEFAULT_OUTPUT_DIR = EXAMPLE_ROOT / "dist"
# Postdate-any-plausible-cache policy: next-day noon relative to the release.
ZIP_EPOCH = (2026, 8, 14, 12, 0, 0)
DAE_TIMESTAMP = "2026-08-14T12:00:00"
TEXT_SUFFIXES = {".json", ".lua", ".jbeam", ".dae", ".pc"}

# Flagship members whose payloads may be overridden by the card-trimmed
# Blender rebuild. Only these three DAEs carry brush card fans.
CARD_DAE_MEMBERS = (
    f"art/shapes/{SOURCE_MOD_ID}/{SOURCE_MOD_ID}.dae",
    f"vehicles/{SOURCE_MOD_ID}/{SOURCE_MOD_ID}.dae",
    f"vehicles/{SOURCE_MOD_ID}/{SOURCE_MOD_ID}_runtime_visual.dae",
)

WASH_EFFECT_COUNT = 22
# Light plan: names are matched by their anchor suffix after the rename.
KEPT_LIGHT_SUFFIXES = frozenset(
    {
        "light_anchor_tunnel_01",
        "light_anchor_tunnel_03",
        "light_anchor_tunnel_05",
        "light_anchor_exit_left",
        "light_anchor_exit_right",
    }
)
DROPPED_LIGHT_SUFFIXES = frozenset(
    {
        "light_anchor_tunnel_02",
        "light_anchor_tunnel_04",
        "light_anchor_wall_01",
        "light_anchor_wall_02",
        "light_anchor_wall_03",
        "light_anchor_wall_04",
        "light_anchor_sign_left",
        "light_anchor_sign_right",
    }
)
# The three kept tunnel fills cover the gaps the dropped fixtures leave.
TUNNEL_BOOST_SUFFIXES = frozenset(
    {"light_anchor_tunnel_01", "light_anchor_tunnel_03", "light_anchor_tunnel_05"}
)
TUNNEL_INTENSITY = (8000.0, 11000.0)
TUNNEL_RADIUS = (7.0, 9.0)

# Texture budget: max dimension per stem class. Never upscales.
ATLAS_DIMENSION_CAP = 1024  # brush_cards*, *_sign* (legibility-bearing atlases)
TILEABLE_DIMENSION_CAP = 512  # everything else

VARIANT_TITLE = "Cannon Car Wash - Low VRAM"
SCENARIO_DESCRIPTION_SUFFIX = (
    " Low VRAM edition: no particle effects, reduced texture and light"
    " budgets for 2 GB graphics cards."
)

PERSISTENT_ID_PATTERN = re.compile(
    r'"persistentId"(\s*:\s*)"([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})"'
)
LIGHTING_BLOCK_PATTERN = re.compile(r"  \{\n.*?\n  \},\n", re.DOTALL)

# DXGI block-compressed formats: bytes per 4x4 block.
DXGI_BLOCK_BYTES = {
    **dict.fromkeys(range(70, 73), 8),  # BC1
    **dict.fromkeys(range(73, 76), 16),  # BC2
    **dict.fromkeys(range(76, 79), 16),  # BC3
    **dict.fromkeys(range(79, 82), 8),  # BC4
    **dict.fromkeys(range(82, 85), 16),  # BC5
    **dict.fromkeys(range(94, 97), 16),  # BC6H
    **dict.fromkeys(range(97, 100), 16),  # BC7
}


class VariantError(RuntimeError):
    """The variant transform hit an input it does not fully understand."""


# BeamNG's GE extension identifiers escape literal underscores ("__"), so the
# runtime extension appears as ericrolph__cannon__car__wash_runtime in Lua and
# interaction.json. That form does NOT contain the plain mod id substring and
# needs its own rename, or the variant's panel buttons would call the
# flagship's extension.
SOURCE_ESCAPED_ID = SOURCE_MOD_ID.replace("_", "__")
VARIANT_ESCAPED_ID = VARIANT_MOD_ID.replace("_", "__")


def rename_identifier(text: str) -> str:
    return text.replace(SOURCE_MOD_ID, VARIANT_MOD_ID).replace(
        SOURCE_ESCAPED_ID, VARIANT_ESCAPED_ID
    )


def variant_member_names() -> tuple[str, ...]:
    return tuple(sorted(rename_identifier(name) for name in flagship.EXPECTED_RUNTIME_FILES))


VARIANT_RUNTIME_FILES = variant_member_names()
VARIANT_MOD_INFO_FILES: tuple[str, ...] = tuple(
    f"mod_info/{VARIANT_TAGID}/{tail}"
    for tail in (
        "icon.jpg",
        "images/1.jpg",
        "images/2.jpg",
        "info.json",
        "thumbs/1.jpg",
        "thumbs/2.jpg",
    )
)
VARIANT_ARCHIVE_MEMBERS: tuple[str, ...] = tuple(
    sorted(VARIANT_RUNTIME_FILES + VARIANT_MOD_INFO_FILES)
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VariantError(message)


def _variant_persistent_id(source_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:{VARIANT_MOD_ID}:pid:{source_id}"))


def _regenerate_persistent_ids(text: str) -> str:
    return PERSISTENT_ID_PATTERN.sub(
        lambda match: f'"persistentId"{match.group(1)}"{_variant_persistent_id(match.group(2))}"',
        text,
    )


def _pin_dae_timestamps(text: str) -> str:
    pinned, created = re.subn(
        r"<created>[^<]*</created>", f"<created>{DAE_TIMESTAMP}</created>", text
    )
    pinned, modified = re.subn(
        r"<modified>[^<]*</modified>", f"<modified>{DAE_TIMESTAMP}</modified>", pinned
    )
    _require(created >= 1 and modified >= 1, "DAE is missing its asset timestamp tags")
    return pinned


def _empty_lua_effect_specs(text: str, *, member: str, table_name: str = "EFFECT_SPECS") -> str:
    pattern = re.compile(rf"local {table_name} = \{{\n(.*?)\n\}}\n", re.DOTALL)
    match = pattern.search(text)
    _require(match is not None, f"{member}: {table_name} table not found")
    assert match is not None
    removed = match.group(1)
    entry_count = removed.count('emitter = "')
    _require(
        entry_count == WASH_EFFECT_COUNT,
        f"{member}: expected {WASH_EFFECT_COUNT} effect entries, found {entry_count}",
    )
    replacement = (
        f"-- Low VRAM edition: the wash runs without particle effects.\nlocal {table_name} = {{}}\n"
    )
    return text[: match.start()] + replacement + text[match.end() :]


ATTRACT_EMITTER_BLOCK = (
    "    local muzzleEmitter = createEffect({\n"
    '      name = prefix .. "_attract_muzzle",\n'
    '      emitter = "BNGP_22",\n'
    "    })\n"
    "    local sparkEmitter = createEffect({\n"
    '      name = prefix .. "_attract_sparks",\n'
    '      emitter = "BNGP_82",\n'
    "    })\n"
)
ATTRACT_EMITTER_REPLACEMENT = (
    "    -- Low VRAM edition: the attract volley fires without particle\n"
    "    -- effects (both handles are nil-guarded everywhere downstream).\n"
    "    local muzzleEmitter = nil\n"
    "    local sparkEmitter = nil\n"
)


def _strip_runtime_effects(text: str) -> str:
    text = _empty_lua_effect_specs(text, member="runtime.lua", table_name="EFFECT_OFFSETS")
    _require(
        text.count(ATTRACT_EMITTER_BLOCK) == 1,
        "runtime.lua: attract emitter block anchor not found exactly once",
    )
    text = text.replace(ATTRACT_EMITTER_BLOCK, ATTRACT_EMITTER_REPLACEMENT)
    _require(
        'emitter = "BNGP' not in text,
        "runtime.lua: a stock emitter reference survived the strip",
    )
    return text


def _light_suffix(name: str) -> str | None:
    marker = "_light_anchor_"
    index = name.find(marker)
    if index < 0:
        return None
    return "light_anchor_" + name[index + len(marker) :]


def _filter_lighting_lua(text: str) -> str:
    blocks = LIGHTING_BLOCK_PATTERN.findall(text)
    _require(
        len(blocks) == len(KEPT_LIGHT_SUFFIXES) + len(DROPPED_LIGHT_SUFFIXES),
        f"lighting.lua: expected 13 light blocks, found {len(blocks)}",
    )
    kept_blocks: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        name_match = re.search(r'name = "([^"]+)"', block)
        _require(name_match is not None, "lighting.lua: light block without a name")
        assert name_match is not None
        suffix = _light_suffix(name_match.group(1))
        _require(suffix is not None, f"lighting.lua: unrecognized light {name_match.group(1)}")
        assert suffix is not None
        seen.add(suffix)
        if suffix in DROPPED_LIGHT_SUFFIXES:
            continue
        _require(suffix in KEPT_LIGHT_SUFFIXES, f"lighting.lua: unplanned light {suffix}")
        if suffix in TUNNEL_BOOST_SUFFIXES:
            boosted = block.replace(
                f"intensity = {TUNNEL_INTENSITY[0]}", f"intensity = {TUNNEL_INTENSITY[1]}"
            ).replace(f"radius = {TUNNEL_RADIUS[0]}", f"radius = {TUNNEL_RADIUS[1]}")
            _require(boosted != block, f"lighting.lua: boost anchors missing on {suffix}")
            block = boosted
        kept_blocks.append(block)
    _require(
        seen == KEPT_LIGHT_SUFFIXES | DROPPED_LIGHT_SUFFIXES,
        f"lighting.lua: light roster drifted from the plan: {sorted(seen)}",
    )
    first_block_start = text.index(blocks[0])
    footer_start = text.rindex(blocks[-1]) + len(blocks[-1])
    return text[:first_block_start] + "".join(kept_blocks) + text[footer_start:]


def _transform_prefab(text: str) -> str:
    kept_lines: list[str] = []
    emitters_dropped = 0
    lights_dropped = 0
    lights_boosted = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        if '"class":"ParticleEmitterNode"' in line:
            emitters_dropped += 1
            continue
        if '"class":"PointLight"' in line or '"class":"SpotLight"' in line:
            record = json.loads(line)
            round_trip = json.dumps(record, separators=(",", ":"))
            _require(round_trip == line, "prefab light record does not round-trip verbatim")
            suffix = _light_suffix(record["name"])
            _require(suffix is not None, f"prefab: unrecognized light {record['name']}")
            assert suffix is not None
            if suffix in DROPPED_LIGHT_SUFFIXES:
                lights_dropped += 1
                continue
            _require(suffix in KEPT_LIGHT_SUFFIXES, f"prefab: unplanned light {suffix}")
            if suffix in TUNNEL_BOOST_SUFFIXES:
                _require(
                    record["intensity"] == TUNNEL_INTENSITY[0]
                    and record["radius"] == TUNNEL_RADIUS[0],
                    f"prefab: unexpected tunnel light fields on {suffix}",
                )
                record["intensity"] = TUNNEL_INTENSITY[1]
                record["radius"] = TUNNEL_RADIUS[1]
                lights_boosted += 1
            line = json.dumps(record, separators=(",", ":"))
        kept_lines.append(line)
    _require(
        emitters_dropped == WASH_EFFECT_COUNT,
        f"prefab: expected {WASH_EFFECT_COUNT} emitter records, dropped {emitters_dropped}",
    )
    _require(
        lights_dropped == len(DROPPED_LIGHT_SUFFIXES),
        f"prefab: expected {len(DROPPED_LIGHT_SUFFIXES)} dropped lights, got {lights_dropped}",
    )
    _require(lights_boosted == len(TUNNEL_BOOST_SUFFIXES), "prefab: tunnel boost incomplete")
    return "\n".join(kept_lines) + "\n"


def _patch_vehicle_info(text: str) -> str:
    record = json.loads(text)
    _require(record.get("Name") == "Cannon Car Wash", "vehicle info.json drifted")
    record["Name"] = VARIANT_TITLE
    return json.dumps(record, indent=2) + "\n"


def _patch_scenario_json(text: str) -> str:
    records = json.loads(text)
    _require(
        isinstance(records, list) and len(records) == 1 and records[0].get("name"),
        "scenario json drifted",
    )
    records[0]["name"] = VARIANT_TITLE
    records[0]["description"] = records[0]["description"] + SCENARIO_DESCRIPTION_SUFFIX
    return json.dumps(records, indent=2) + "\n"


def _dds_layout(payload: bytes, *, member: str) -> tuple[int, int, int, int, int]:
    """Return (width, height, mip_count, block_bytes, data_offset)."""

    _require(payload[:4] == b"DDS " and len(payload) > 148, f"{member}: not a DDS file")
    height, width = struct.unpack_from("<II", payload, 12)
    mip_count = struct.unpack_from("<I", payload, 28)[0]
    _require(payload[84:88] == b"DX10", f"{member}: expected a DX10-header DDS")
    dxgi_format = struct.unpack_from("<I", payload, 128)[0]
    block_bytes = DXGI_BLOCK_BYTES.get(dxgi_format)
    _require(block_bytes is not None, f"{member}: unsupported DXGI format {dxgi_format}")
    assert block_bytes is not None
    return width, height, mip_count, block_bytes, 148


def _mip_level_size(width: int, height: int, block_bytes: int) -> int:
    blocks_x = max(1, (width + 3) // 4)
    blocks_y = max(1, (height + 3) // 4)
    return blocks_x * blocks_y * block_bytes


def _texture_dimension_cap(member: str) -> int:
    stem = PurePosixPath(member).name
    if "brush_cards" in stem or "_sign" in stem:
        return ATLAS_DIMENSION_CAP
    return TILEABLE_DIMENSION_CAP


def strip_dds_mips(payload: bytes, *, member: str, dimension_cap: int) -> bytes:
    """Drop top mip levels until max(width, height) <= dimension_cap."""

    width, height, mip_count, block_bytes, data_offset = _dds_layout(payload, member=member)
    sizes: list[int] = []
    level_width, level_height = width, height
    for _ in range(mip_count):
        sizes.append(_mip_level_size(level_width, level_height, block_bytes))
        level_width = max(1, level_width // 2)
        level_height = max(1, level_height // 2)
    _require(
        data_offset + sum(sizes) == len(payload),
        f"{member}: mip chain does not account for the whole file",
    )
    dropped = 0
    new_width, new_height = width, height
    while max(new_width, new_height) > dimension_cap:
        new_width = max(1, new_width // 2)
        new_height = max(1, new_height // 2)
        dropped += 1
    if dropped == 0:
        return payload
    _require(dropped < mip_count, f"{member}: cannot drop the whole mip chain")
    header = bytearray(payload[:data_offset])
    struct.pack_into("<II", header, 12, new_height, new_width)
    struct.pack_into("<I", header, 20, _mip_level_size(new_width, new_height, block_bytes))
    struct.pack_into("<I", header, 28, mip_count - dropped)
    return bytes(header) + payload[data_offset + sum(sizes[:dropped]) :]


def load_source_payloads(card_trimmed_mod: Path | None) -> dict[str, bytes]:
    sources = flagship.validate_mod_tree(flagship.MOD_ROOT)
    payloads = {name: flagship._stable_read(path) for name, path in sources.items()}
    if card_trimmed_mod is not None:
        for member in CARD_DAE_MEMBERS:
            candidate = card_trimmed_mod / member
            _require(
                candidate.is_file(),
                f"card-trimmed tree is missing {member}",
            )
            trimmed = candidate.read_bytes()
            _require(
                trimmed != payloads[member],
                f"card-trimmed {member} is identical to the flagship export",
            )
            payloads[member] = trimmed
    return payloads


def transform_payloads(payloads: dict[str, bytes]) -> dict[str, bytes]:
    runtime_member = rename_identifier(f"lua/ge/extensions/{SOURCE_MOD_ID}/runtime.lua")
    scenario_lua_member = rename_identifier(
        f"levels/gridmap_v2/scenarios/{SOURCE_MOD_ID}/{SOURCE_MOD_ID}.lua"
    )
    lighting_member = rename_identifier(f"lua/common/{SOURCE_MOD_ID}/lighting.lua")
    prefab_member = rename_identifier(
        f"levels/gridmap_v2/scenarios/{SOURCE_MOD_ID}/{SOURCE_MOD_ID}.prefab.json"
    )
    vehicle_info_member = rename_identifier(f"vehicles/{SOURCE_MOD_ID}/info.json")
    scenario_json_member = rename_identifier(
        f"levels/gridmap_v2/scenarios/{SOURCE_MOD_ID}/{SOURCE_MOD_ID}.json"
    )

    transformed: dict[str, bytes] = {}
    for name, payload in payloads.items():
        member = rename_identifier(name)
        suffix = PurePosixPath(member).suffix
        if suffix in TEXT_SUFFIXES:
            text = rename_identifier(payload.decode("utf-8"))
            text = _regenerate_persistent_ids(text)
            if suffix == ".dae":
                text = _pin_dae_timestamps(text)
            if member == runtime_member:
                text = _strip_runtime_effects(text)
            elif member == scenario_lua_member:
                text = _empty_lua_effect_specs(text, member="scenario lua")
            elif member == lighting_member:
                text = _filter_lighting_lua(text)
            elif member == prefab_member:
                text = _transform_prefab(text)
            elif member == vehicle_info_member:
                text = _patch_vehicle_info(text)
            elif member == scenario_json_member:
                text = _patch_scenario_json(text)
            transformed[member] = text.encode("utf-8")
        elif suffix == ".dds":
            transformed[member] = strip_dds_mips(
                payload, member=member, dimension_cap=_texture_dimension_cap(member)
            )
        else:
            transformed[member] = payload
    _require(
        tuple(sorted(transformed)) == VARIANT_RUNTIME_FILES,
        "transformed member list drifted from the variant allowlist",
    )
    leak_patterns = (
        re.compile(re.escape(SOURCE_MOD_ID) + r"(?!_lowvram)"),
        re.compile(re.escape(SOURCE_ESCAPED_ID) + r"(?!__lowvram)"),
    )
    for member, payload in transformed.items():
        if PurePosixPath(member).suffix in TEXT_SUFFIXES:
            text = payload.decode("utf-8")
            _require(
                all(pattern.search(text) is None for pattern in leak_patterns),
                f"{member}: a flagship identifier survived the rename",
            )
    return transformed


def write_variant_tree(transformed: dict[str, bytes]) -> None:
    if VARIANT_MOD_ROOT.exists():
        for path in sorted(VARIANT_MOD_ROOT.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            else:
                path.rmdir()
        VARIANT_MOD_ROOT.rmdir()
    for member, payload in transformed.items():
        destination = VARIANT_MOD_ROOT / PurePosixPath(member)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)


def variant_mod_info_payloads() -> dict[str, bytes]:
    submission = json.loads(
        (VARIANT_REPOSITORY_ROOT / "submission.json").read_text(encoding="utf-8")
    )
    prefix = f"mod_info/{VARIANT_TAGID}"
    payloads: dict[str, bytes] = {
        f"{prefix}/icon.jpg": flagship._stable_read(SHARED_REPOSITORY_ROOT / "icon.jpg")
    }
    attachments = []
    gallery = ("01_exterior.png", "02_wash_active.png")
    for index, source_name in enumerate(gallery, start=1):
        with Image.open(SHARED_REPOSITORY_ROOT / "images" / source_name) as source:
            image = source.convert("RGB")
        payloads[f"{prefix}/images/{index}.jpg"] = flagship._deterministic_jpeg(image, quality=88)
        thumb = ImageOps.fit(image, (356, 200), Image.Resampling.LANCZOS)
        payloads[f"{prefix}/thumbs/{index}.jpg"] = flagship._deterministic_jpeg(thumb, quality=80)
        attachments.append(
            {
                "data_filename": f"{index}.jpg",
                "original_filename": source_name,
                "thumb_filename": f"thumbs/{index}.jpg",
            }
        )
    release_epoch = calendar.timegm((*ZIP_EPOCH, 0, 0, 0))
    info = {
        "attachments": attachments,
        "filename": VARIANT_ZIP_NAME,
        "last_update": release_epoch,
        "message": submission["description"],
        "path": f"{VARIANT_TAGID}/local/",
        "resource_date": release_epoch,
        "tag_line": submission["tag_line"],
        "tagid": VARIANT_TAGID,
        "title": submission["title"],
        "username": submission["author"],
        "version_string": submission["version"],
    }
    payloads[f"{prefix}/info.json"] = (json.dumps(info, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _require(set(payloads) == set(VARIANT_MOD_INFO_FILES), "variant mod_info members drifted")
    return payloads


def validate_variant_tree(mod_root: Path = VARIANT_MOD_ROOT) -> dict[str, Path]:
    _require(mod_root.is_dir(), f"variant mod root must be a directory: {mod_root}")
    actual: dict[str, Path] = {}
    for path in sorted(mod_root.rglob("*")):
        if path.is_dir():
            continue
        _require(path.is_file() and not path.is_symlink(), f"unsupported entry: {path}")
        relative = path.relative_to(mod_root).as_posix()
        flagship._validate_member_name(relative)
        actual[relative] = path
    _require(
        tuple(sorted(actual)) == VARIANT_RUNTIME_FILES,
        "variant tree does not exactly match the variant allowlist; "
        f"missing={sorted(set(VARIANT_RUNTIME_FILES) - set(actual))}, "
        f"unexpected={sorted(set(actual) - set(VARIANT_RUNTIME_FILES))}",
    )
    return {name: actual[name] for name in VARIANT_RUNTIME_FILES}


def _write_archive(path: Path, payloads: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in VARIANT_ARCHIVE_MEMBERS:
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, payloads[name], compress_type=zipfile.ZIP_STORED)


def verify_archive(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        _require(
            names == list(VARIANT_ARCHIVE_MEMBERS),
            f"variant archive members differ from the allowlist: {names}",
        )
        _require(archive.testzip() is None, "variant archive CRC verification failed")
        for member in members:
            flagship._validate_member_name(
                member.filename,
                allowed_roots=flagship.ALLOWED_TOP_LEVEL_ROOTS | {"mod_info"},
            )
            _require(member.date_time == ZIP_EPOCH, f"bad timestamp: {member.filename}")
            _require(
                member.compress_type == zipfile.ZIP_STORED,
                f"bad compression: {member.filename}",
            )


def pack_variant(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    mod_root: Path = VARIANT_MOD_ROOT,
    overwrite: bool = False,
) -> dict[str, str | int]:
    sources = validate_variant_tree(mod_root)
    payloads = {name: flagship._stable_read(path) for name, path in sources.items()}
    payloads.update(variant_mod_info_payloads())
    payloads = {name: payloads[name] for name in VARIANT_ARCHIVE_MEMBERS}

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / VARIANT_ZIP_NAME
    if os.path.lexists(destination) and not overwrite:
        raise VariantError(f"distribution already exists; pass --overwrite: {destination}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{VARIANT_ZIP_NAME}.", suffix=".tmp", dir=output_dir
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        _write_archive(temporary_path, payloads)
        verify_archive(temporary_path)
        digest = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
        size = temporary_path.stat().st_size
        os.replace(temporary_path, destination)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return {
        "archive": str(destination.resolve()),
        "sha256": digest,
        "size": size,
        "member_count": len(VARIANT_ARCHIVE_MEMBERS),
    }


def build_variant(
    *,
    card_trimmed_mod: Path | None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    overwrite: bool = False,
) -> dict[str, str | int]:
    payloads = load_source_payloads(card_trimmed_mod)
    transformed = transform_payloads(payloads)
    if transform_payloads(payloads) != transformed:
        raise VariantError("variant transform is not deterministic")
    write_variant_tree(transformed)
    return pack_variant(output_dir, overwrite=overwrite)


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--card-trimmed-mod",
        type=Path,
        default=None,
        help="mod tree of a CANNON_CAR_WASH_LOW_VRAM=1 pipeline build; its three"
        " card-bearing wash DAEs replace the flagship exports",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--pack-only",
        action="store_true",
        help="pack the existing committed mod_low_vram tree without re-transforming",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _argument_parser().parse_args(argv)
    try:
        if arguments.pack_only:
            result = pack_variant(arguments.output_dir, overwrite=arguments.overwrite)
        else:
            result = build_variant(
                card_trimmed_mod=arguments.card_trimmed_mod,
                output_dir=arguments.output_dir,
                overwrite=arguments.overwrite,
            )
    except (VariantError, flagship.DistributionError) as exc:
        print(f"error: {exc}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
