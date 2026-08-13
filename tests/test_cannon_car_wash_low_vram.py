"""Static gates for the Cannon Car Wash - Low VRAM edition.

The Low VRAM tree is DERIVED: every member except the six scratch-build
members (wash DAEs, selector jbeam/interaction, and the mass stamp from a
``CANNON_CAR_WASH_LOW_VRAM=1`` pipeline rebuild) must re-derive
byte-for-byte from the committed flagship tree through
``build_low_vram_variant.transform_payloads``. These gates therefore prove
the committed variant tree, the transform code, and the shipped archive
agree.
"""

from __future__ import annotations

import json
import re
import struct
from collections import Counter
from pathlib import PurePosixPath
from uuid import UUID

import pytest

import examples.cannon_car_wash.build_distribution as distribution
import examples.cannon_car_wash.build_low_vram_variant as variant

VARIANT_ROOT = variant.VARIANT_MOD_ROOT
VARIANT_ID = variant.VARIANT_MOD_ID
SCENARIO_ROOT = PurePosixPath("levels") / "gridmap_v2" / "scenarios" / VARIANT_ID


@pytest.fixture(scope="module")
def variant_files() -> dict[str, bytes]:
    sources = variant.validate_variant_tree()
    return {name: path.read_bytes() for name, path in sources.items()}


@pytest.fixture(scope="module")
def flagship_payloads() -> dict[str, bytes]:
    sources = distribution.validate_mod_tree()
    return {name: path.read_bytes() for name, path in sources.items()}


def test_variant_tree_matches_allowlist(variant_files: dict[str, bytes]) -> None:
    assert tuple(sorted(variant_files)) == variant.VARIANT_RUNTIME_FILES
    assert len(variant_files) == 82


def test_variant_rederives_from_flagship_except_scratch_members(
    variant_files: dict[str, bytes], flagship_payloads: dict[str, bytes]
) -> None:
    """The transform is the variant's generator: 76 of 82 members must re-derive
    exactly; only the six scratch-build members carry pipeline-run output."""

    rederived = variant.transform_payloads(flagship_payloads)
    exempt = {variant.rename_identifier(name) for name in variant.SCRATCH_BUILD_MEMBERS}
    assert len(exempt) == 6
    mismatched = [
        name
        for name in variant.VARIANT_RUNTIME_FILES
        if name not in exempt and rederived[name] != variant_files[name]
    ]
    assert mismatched == [], f"members no longer re-derive from the flagship: {mismatched}"
    for name in sorted(exempt):
        assert name in variant_files
        assert variant_files[name] != rederived[name], (
            f"{name} matches the flagship export; the CANNON_CAR_WASH_LOW_VRAM=1"
            " pipeline rebuild did not land"
        )


def test_wash_effects_are_opt_in_and_default_off(variant_files: dict[str, bytes]) -> None:
    # Scenario (static) version stays completely effect-free.
    prefab = variant_files[(SCENARIO_ROOT / f"{VARIANT_ID}.prefab.json").as_posix()].decode()
    assert "ParticleEmitterNode" not in prefab
    scenario_lua = variant_files[(SCENARIO_ROOT / f"{VARIANT_ID}.lua").as_posix()].decode()
    assert "local EFFECT_SPECS = {}" in scenario_lua
    assert 'emitter = "BNGP' not in scenario_lua

    # Selector prop: the 22 wash emitters remain DEFINED but only activate
    # behind the mini panel's toggle; the attract pair stays removed.
    runtime = variant_files[f"lua/ge/extensions/{VARIANT_ID}/runtime.lua"].decode()
    offsets = re.search(r"local EFFECT_OFFSETS = \{\n(.*?)\n\}\n", runtime, re.DOTALL)
    assert offsets is not None
    assert offsets.group(1).count('emitter = "') == variant.WASH_EFFECT_COUNT
    assert variant.WASH_ACTIVATION_GATED in runtime
    assert variant.DISPATCH_WITH_EFFECTS in runtime
    assert '"WASH SPRAY FX ON"' in runtime
    assert "effects_enabled = state.panel.effectsEnabled == true" in runtime
    assert "local muzzleEmitter = nil" in runtime
    assert "local sparkEmitter = nil" in runtime
    assert '"BNGP_22"' not in runtime
    assert '"BNGP_82"' not in runtime

    # The sixth hover button is wired end to end: interaction action calls
    # the variant's escaped extension identifier with the toggle suffix.
    interaction = json.loads(
        variant_files[f"vehicles/{VARIANT_ID}/{VARIANT_ID}_default.interaction.json"]
    )
    actions = interaction["actions"]
    assert len(actions) == 6
    effects_action = actions[f"{VARIANT_ID}_btn_effects"]
    assert (
        f"extensions.{variant.VARIANT_ESCAPED_ID}_runtime.pressPanelButtonByVehicle"
        in (effects_action["onDown"])
    )
    assert "'btn_effects'" in effects_action["onDown"]
    assert effects_action["title"] == "Toggle wash spray effects"


def test_light_roster_is_five_boosted_fixtures(variant_files: dict[str, bytes]) -> None:
    lighting = variant_files[f"lua/common/{VARIANT_ID}/lighting.lua"].decode()
    names = re.findall(r'name = "([^"]+)"', lighting)
    suffixes = {name.split(f"{VARIANT_ID}_", 1)[1] for name in names}
    assert suffixes == set(variant.KEPT_LIGHT_SUFFIXES)
    assert lighting.count(f"intensity = {variant.TUNNEL_INTENSITY[1]}") == 3
    assert lighting.count(f"radius = {variant.TUNNEL_RADIUS[1]}") == 3

    prefab_lines = [
        json.loads(line)
        for line in variant_files[(SCENARIO_ROOT / f"{VARIANT_ID}.prefab.json").as_posix()]
        .decode()
        .splitlines()
        if line.strip()
    ]
    classes = Counter(record["class"] for record in prefab_lines)
    assert classes["PointLight"] == 3
    assert classes["SpotLight"] == 2
    tunnel = [r for r in prefab_lines if r["class"] == "PointLight"]
    assert all(record["intensity"] == variant.TUNNEL_INTENSITY[1] for record in tunnel)
    assert all(record["radius"] == variant.TUNNEL_RADIUS[1] for record in tunnel)


def test_no_flagship_identifier_leaks(variant_files: dict[str, bytes]) -> None:
    leak_patterns = (
        re.compile(re.escape(variant.SOURCE_MOD_ID) + r"(?!_lowvram)"),
        # The GE extension identifier escapes underscores; that form must be
        # renamed too or the variant's buttons would drive the flagship.
        re.compile(re.escape(variant.SOURCE_ESCAPED_ID) + r"(?!__lowvram)"),
    )
    for name, payload in variant_files.items():
        if PurePosixPath(name).suffix not in variant.TEXT_SUFFIXES:
            continue
        text = payload.decode("utf-8")
        for pattern in leak_patterns:
            assert pattern.search(text) is None, f"flagship identifier leaked into {name}"


def test_texture_budget_caps(variant_files: dict[str, bytes]) -> None:
    dds_members = [name for name in variant_files if name.endswith(".dds")]
    assert len(dds_members) == 54
    for name in dds_members:
        payload = variant_files[name]
        width, height, mip_count, block_bytes, data_offset = variant._dds_layout(
            payload, member=name
        )
        cap = variant._texture_dimension_cap(name)
        assert max(width, height) <= cap, f"{name} is {width}x{height}, cap {cap}"
        sizes = 0
        level_width, level_height = width, height
        for _ in range(mip_count):
            sizes += variant._mip_level_size(level_width, level_height, block_bytes)
            level_width = max(1, level_width // 2)
            level_height = max(1, level_height // 2)
        assert data_offset + sizes == len(payload), f"{name} mip chain is inconsistent"
        declared_mip0 = struct.unpack_from("<I", payload, 20)[0]
        assert declared_mip0 == variant._mip_level_size(width, height, block_bytes)


def test_persistent_ids_are_canonical_unique_and_disjoint(
    variant_files: dict[str, bytes], flagship_payloads: dict[str, bytes]
) -> None:
    def collect(payloads: dict[str, bytes]) -> list[str]:
        found: list[str] = []
        for name, payload in payloads.items():
            if not name.endswith(".json"):
                continue
            found.extend(
                match.group(2)
                for match in variant.PERSISTENT_ID_PATTERN.finditer(payload.decode("utf-8"))
            )
        return found

    variant_ids = collect(variant_files)
    assert variant_ids, "the variant tree lost its persistentId records"
    for identifier in variant_ids:
        assert str(UUID(identifier)) == identifier
    assert len(variant_ids) == len(set(variant_ids))
    flagship_ids = set(collect(flagship_payloads))
    assert not set(variant_ids) & flagship_ids, (
        "variant persistentIds collide with the flagship mod"
    )


def test_jbeam_is_flagship_physics_plus_only_the_effects_button(
    variant_files: dict[str, bytes], flagship_payloads: dict[str, bytes]
) -> None:
    """Physics must be untouched: after removing the mini panel's button rows
    (one node, one trigger box, one event link, one enabled action), the
    variant JBeam must equal the flagship's modulo the namespace rename."""

    flagship_jbeam = json.loads(
        variant.rename_identifier(
            flagship_payloads[
                f"vehicles/{variant.SOURCE_MOD_ID}/{variant.SOURCE_MOD_ID}.jbeam"
            ].decode("utf-8")
        )
    )
    variant_jbeam = json.loads(variant_files[f"vehicles/{VARIANT_ID}/{VARIANT_ID}.jbeam"])
    flagship_part = flagship_jbeam[VARIANT_ID]
    variant_part = variant_jbeam[VARIANT_ID]
    scrubbed = 0
    for section, rows in variant_part.items():
        if isinstance(rows, list):
            kept = [row for row in rows if "btn_effects" not in json.dumps(row)]
            scrubbed += len(rows) - len(kept)
            variant_part[section] = kept
    assert scrubbed == 4, f"expected exactly 4 btn_effects rows, scrubbed {scrubbed}"
    assert variant_part == flagship_part

    # The +2 kg button node lands in the mass stamp.
    flagship_info = json.loads(
        flagship_payloads[f"vehicles/{variant.SOURCE_MOD_ID}/info_standard.json"]
    )
    variant_info = json.loads(variant_files[f"vehicles/{VARIANT_ID}/info_standard.json"])
    assert variant_info["Weight"] == flagship_info["Weight"] + 2.0


def test_archive_packs_deterministically(tmp_path) -> None:
    first = variant.pack_variant(tmp_path / "first")
    second = variant.pack_variant(tmp_path / "second")
    assert first["sha256"] == second["sha256"]
    first_bytes = (tmp_path / "first" / variant.VARIANT_ZIP_NAME).read_bytes()
    second_bytes = (tmp_path / "second" / variant.VARIANT_ZIP_NAME).read_bytes()
    assert first_bytes == second_bytes
    assert first["member_count"] == 88
    # When the release archive has been built locally it must match too.
    committed = variant.DEFAULT_OUTPUT_DIR / variant.VARIANT_ZIP_NAME
    if committed.is_file():
        assert committed.read_bytes() == first_bytes


def test_variant_titles_are_distinct(variant_files: dict[str, bytes]) -> None:
    info = json.loads(variant_files[f"vehicles/{VARIANT_ID}/info.json"])
    assert info["Name"] == variant.VARIANT_TITLE
    scenario = json.loads(variant_files[(SCENARIO_ROOT / f"{VARIANT_ID}.json").as_posix()])
    assert scenario[0]["name"] == variant.VARIANT_TITLE
    assert "Low VRAM edition" in scenario[0]["description"]
    submission = json.loads(
        (variant.VARIANT_REPOSITORY_ROOT / "submission.json").read_text(encoding="utf-8")
    )
    assert submission["internal_name"] == VARIANT_ID
    assert submission["stable_zip_filename"] == variant.VARIANT_ZIP_NAME
