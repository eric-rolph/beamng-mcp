from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID
from xml.etree import ElementTree as ET

import pytest

import examples.cannon_car_wash.build_distribution as distribution
from examples.cannon_car_wash.build_distribution import (
    ALLOWED_TOP_LEVEL_ROOTS,
    EXAMPLE_ROOT,
    EXPECTED_RUNTIME_FILES,
    FILENAME_PATTERN,
    MOD_ID,
    MOD_ROOT,
    ZIP_EPOCH,
    ZIP_NAME,
    DistributionError,
    build_distribution,
    validate_mod_tree,
)

VEHICLE_ROOT = PurePosixPath("vehicles") / MOD_ID
LEVEL_ASSET_ROOT = PurePosixPath("levels") / "gridmap_v2" / "art" / "shapes" / MOD_ID
SCENARIO_ROOT = PurePosixPath("levels") / "gridmap_v2" / "scenarios" / MOD_ID
REPOSITORY_ROOT = EXAMPLE_ROOT / "repository"

COLLADA_NAMESPACE = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
COLLISION_NODE_NAMES = {f"Colmesh-{index}" for index in range(1, 5)}
STOCK_CRASH_WALL = "/levels/gridmap_v2/art/shapes/grid/s_gm_block_16mX2mX8m.dae"
ALLOWED_STOCK_DEPENDENCY_REFERENCES = {
    "pickup",
    "default_vehicle",
    "BNGP_sprinkler",
    "lightExampleEmitterNodeData1",
    "onBeamNGTrigger",
    STOCK_CRASH_WALL,
}
PERSISTENT_ID_BASELINE = 42
TEXT_RUNTIME_SUFFIXES = {".dae", ".jbeam", ".json", ".lua", ".pc"}
LEGACY_AUTHORED_PATTERNS = {
    "legacy scenario material": re.compile(r"(?<![A-Za-z0-9_])CW_[A-Za-z0-9_]+"),
    "legacy selector material": re.compile(r"(?<![A-Za-z0-9_])CWV_[A-Za-z0-9_]+"),
    "legacy model": re.compile(r"(?<![A-Za-z0-9_])cannon_car_wash(?![A-Za-z0-9_])"),
    "legacy group": re.compile(r"(?<![A-Za-z0-9_])cannon_car_wash_group(?![A-Za-z0-9_])"),
    "legacy selector visual": re.compile(
        r"(?<![A-Za-z0-9_])cannon_car_wash_visual(?![A-Za-z0-9_])"
    ),
    "legacy selector truck": re.compile(r"(?<![A-Za-z0-9_])cannon_car_wash_truck(?![A-Za-z0-9_])"),
    "legacy scenario visual": re.compile(r"(?<![A-Za-z0-9_])CannonCarWash_Visual(?![A-Za-z0-9_])"),
    "legacy launch trigger": re.compile(r"(?<![A-Za-z0-9_])LaunchTrigger_Mesh(?![A-Za-z0-9_])"),
    "legacy wash trigger": re.compile(
        r"(?<![A-Za-z0-9_])WashActivationTrigger_Mesh(?![A-Za-z0-9_])"
    ),
}
LEGACY_DAE_ID_PATTERN = re.compile(r"\b(?:id|name)=([\"'])(?:Cube|Cylinder)(?:[_.-]|(?=\1))")


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json_loads(source: str) -> Any:
    return json.loads(
        source,
        parse_constant=_reject_non_finite,
        object_pairs_hook=_unique_object,
    )


def _strict_json_file(path: Path) -> Any:
    return _strict_json_loads(path.read_text(encoding="utf-8"))


def _prefab_records(path: Path) -> list[dict[str, Any]]:
    records = [
        _strict_json_loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records
    assert all(isinstance(record, dict) for record in records)
    return records


def _persistent_ids(value: Any) -> list[str]:
    if isinstance(value, dict):
        result = [value["persistentId"]] if "persistentId" in value else []
        for nested in value.values():
            result.extend(_persistent_ids(nested))
        return result
    if isinstance(value, list):
        return [identifier for nested in value for identifier in _persistent_ids(nested)]
    return []


def _is_namespaced(value: str) -> bool:
    return value == MOD_ID or value.startswith((f"{MOD_ID}_", f"{MOD_ID}-"))


def test_distribution_tree_contains_only_approved_runtime_files() -> None:
    files = validate_mod_tree()
    assert len(EXPECTED_RUNTIME_FILES) == 14
    assert set(files) == set(EXPECTED_RUNTIME_FILES)

    forbidden_suffixes = (".blend", ".py", ".geometry.json", ".selector_handoff.json")
    for relative, path in files.items():
        parts = PurePosixPath(relative).parts
        assert len(parts) >= 2, f"loose file at ZIP root: {relative}"
        assert parts[0] in ALLOWED_TOP_LEVEL_ROOTS, f"invalid ZIP root: {relative}"
        assert all(FILENAME_PATTERN.fullmatch(part) for part in parts)
        assert "mod_info" not in {part.casefold() for part in parts}
        assert path.name.casefold() != "readme.md"
        assert not path.name.casefold().endswith(forbidden_suffixes)
        assert re.fullmatch(r"phase\d+_manifest\.json", path.name, re.IGNORECASE) is None


def test_every_beamng_json_artifact_uses_the_strict_json_subset() -> None:
    files = validate_mod_tree()
    json_artifacts = {
        relative: path
        for relative, path in files.items()
        if path.suffix in {".jbeam", ".json", ".pc"}
    }
    assert json_artifacts
    for relative, path in json_artifacts.items():
        if relative.endswith(".prefab.json"):
            _prefab_records(path)
        else:
            assert _strict_json_file(path) is not None


def test_runtime_persistent_ids_are_canonical_and_globally_unique() -> None:
    identifiers: list[str] = []
    for relative, path in validate_mod_tree().items():
        if path.suffix not in {".jbeam", ".json", ".pc"}:
            continue
        documents = (
            _prefab_records(path)
            if relative.endswith(".prefab.json")
            else [_strict_json_file(path)]
        )
        for document in documents:
            for identifier in _persistent_ids(document):
                assert isinstance(identifier, str), f"non-string persistentId in {relative}"
                try:
                    parsed = UUID(identifier)
                except (AttributeError, ValueError) as error:
                    pytest.fail(f"invalid persistentId in {relative}: {identifier!r}: {error}")
                assert str(parsed) == identifier, (
                    f"non-canonical persistentId in {relative}: {identifier!r}"
                )
                identifiers.append(identifier)

    assert len(identifiers) >= PERSISTENT_ID_BASELINE
    assert len(identifiers) == len(set(identifiers)), "persistentId values must be globally unique"

    scenario_materials = _strict_json_file(
        MOD_ROOT / Path((LEVEL_ASSET_ROOT / f"{MOD_ID}.materials.json").as_posix())
    )
    selector_materials = _strict_json_file(
        MOD_ROOT / Path((VEHICLE_ROOT / "main.materials.json").as_posix())
    )
    scenario_ids = {material["persistentId"] for material in scenario_materials.values()}
    selector_ids = {material["persistentId"] for material in selector_materials.values()}
    assert len(scenario_ids) == len(scenario_materials)
    assert len(selector_ids) == len(selector_materials)
    assert scenario_ids.isdisjoint(selector_ids)


def test_runtime_text_declarations_have_no_legacy_authored_identifiers() -> None:
    runtime_text = {
        relative: path.read_text(encoding="utf-8")
        for relative, path in validate_mod_tree().items()
        if path.suffix in TEXT_RUNTIME_SUFFIXES
    }
    assert runtime_text

    # These unnamespaced values belong to stock BeamNG contracts, not this mod.
    corpus = "\n".join(runtime_text.values())
    for reference in ALLOWED_STOCK_DEPENDENCY_REFERENCES:
        assert reference in corpus, f"expected stock dependency reference is missing: {reference}"

    violations: list[str] = []
    for relative, source in runtime_text.items():
        for label, pattern in LEGACY_AUTHORED_PATTERNS.items():
            if match := pattern.search(source):
                violations.append(f"{relative}: {label}: {match.group(0)!r}")
        if relative.endswith(".dae") and (match := LEGACY_DAE_ID_PATTERN.search(source)):
            violations.append(f"{relative}: legacy DAE ID: {match.group(0)!r}")

    assert violations == []


def test_vehicle_jbeam_model_groups_and_flexbody_are_namespaced() -> None:
    vehicle_root = MOD_ROOT / Path(VEHICLE_ROOT.as_posix())
    jbeam = _strict_json_file(vehicle_root / f"{MOD_ID}.jbeam")
    assert isinstance(jbeam, dict)
    assert set(jbeam) == {MOD_ID}
    part = jbeam[MOD_ID]
    assert part["slotType"] == "main"

    configuration = _strict_json_file(vehicle_root / "standard.pc")
    assert configuration["model"] == MOD_ID
    assert configuration["mainPartName"] == MOD_ID
    assert all(_is_namespaced(name) for name in configuration.get("parts", {}))
    assert all(
        not isinstance(value, str) or _is_namespaced(value)
        for value in configuration.get("parts", {}).values()
    )

    node_rows = part["nodes"][1:]
    assert node_rows
    node_ids = [row[0] for row in node_rows]
    assert len(node_ids) == len(set(node_ids))
    node_groups = {
        row[-1]["group"]
        for row in node_rows
        if isinstance(row[-1], dict) and isinstance(row[-1].get("group"), str)
    }
    assert node_groups
    assert all(_is_namespaced(group) for group in node_groups)

    flexbody_rows = part["flexbodies"][1:]
    assert flexbody_rows
    flexbody_meshes = [row[0] for row in flexbody_rows]
    assert len(flexbody_meshes) == len(set(flexbody_meshes))
    assert all(_is_namespaced(mesh) for mesh in flexbody_meshes)
    flexbody_groups = [group for row in flexbody_rows for group in row[1]]
    assert flexbody_groups
    assert all(_is_namespaced(group) for group in flexbody_groups)


def test_material_roots_names_and_mapto_values_are_globally_namespaced() -> None:
    material_paths = [
        MOD_ROOT / Path((LEVEL_ASSET_ROOT / f"{MOD_ID}.materials.json").as_posix()),
        MOD_ROOT / Path((VEHICLE_ROOT / "main.materials.json").as_posix()),
    ]
    seen_roots: set[str] = set()
    seen_names: set[str] = set()
    seen_map_to: set[str] = set()
    for path in material_paths:
        materials = _strict_json_file(path)
        assert isinstance(materials, dict) and materials
        for root_name, definition in materials.items():
            name = definition["name"]
            map_to = definition["mapTo"]
            assert _is_namespaced(root_name)
            assert _is_namespaced(name)
            assert _is_namespaced(map_to)
            assert root_name not in seen_roots
            assert name not in seen_names
            assert map_to not in seen_map_to
            seen_roots.add(root_name)
            seen_names.add(name)
            seen_map_to.add(map_to)


def test_collada_geometry_controller_material_and_node_ids_are_namespaced() -> None:
    dae_and_materials = [
        (
            MOD_ROOT / Path((LEVEL_ASSET_ROOT / f"{MOD_ID}.dae").as_posix()),
            MOD_ROOT / Path((LEVEL_ASSET_ROOT / f"{MOD_ID}.materials.json").as_posix()),
            True,
        ),
        (
            MOD_ROOT / Path((VEHICLE_ROOT / f"{MOD_ID}.dae").as_posix()),
            MOD_ROOT / Path((VEHICLE_ROOT / "main.materials.json").as_posix()),
            False,
        ),
    ]
    for dae_path, materials_path, collision_expected in dae_and_materials:
        root = ET.parse(dae_path).getroot()  # noqa: S314 - repository-owned fixture
        elements = [
            *root.findall(".//c:library_geometries/c:geometry", COLLADA_NAMESPACE),
            *root.findall(".//c:library_controllers/c:controller", COLLADA_NAMESPACE),
            *root.findall(".//c:library_materials/c:material", COLLADA_NAMESPACE),
            *root.findall(".//c:library_visual_scenes//c:node", COLLADA_NAMESPACE),
        ]
        assert elements

        identifiers: list[str] = []
        collision_node_names: set[str] = set()
        for element in elements:
            values = [element.attrib[key] for key in ("id", "name") if key in element.attrib]
            assert values
            for value in values:
                if element.tag.endswith("}node") and value.startswith("Colmesh-"):
                    assert value in COLLISION_NODE_NAMES
                    collision_node_names.add(value)
                else:
                    assert _is_namespaced(value), value
            if "id" in element.attrib:
                identifiers.append(element.attrib["id"])

        assert len(identifiers) == len(set(identifiers))
        assert collision_node_names == (COLLISION_NODE_NAMES if collision_expected else set())
        dae_material_names = {
            material.attrib["name"]
            for material in root.findall(".//c:library_materials/c:material", COLLADA_NAMESPACE)
        }
        assert dae_material_names == set(_strict_json_file(materials_path))


def test_prefab_scene_names_are_namespaced_and_stock_assets_remain_references() -> None:
    prefab_path = MOD_ROOT / Path((SCENARIO_ROOT / f"{MOD_ID}.prefab.json").as_posix())
    records = _prefab_records(prefab_path)
    assert all(_is_namespaced(record["name"]) for record in records)
    assert all("__parent" not in record or _is_namespaced(record["__parent"]) for record in records)

    vehicles = [record for record in records if record.get("class") == "BeamNGVehicle"]
    assert len(vehicles) == 1
    assert vehicles[0]["jBeam"] == "pickup"

    misters = [record for record in records if record.get("class") == "ParticleEmitterNode"]
    assert len(misters) == 12
    assert {record["emitter"] for record in misters} == {"BNGP_sprinkler"}
    assert {record["dataBlock"] for record in misters} == {"lightExampleEmitterNodeData1"}

    shape_references = {
        record["shapeName"] for record in records if isinstance(record.get("shapeName"), str)
    }
    assert STOCK_CRASH_WALL in shape_references
    assert any(MOD_ID in shape_name for shape_name in shape_references)
    assert all(
        shape_name == STOCK_CRASH_WALL or MOD_ID in shape_name for shape_name in shape_references
    )
    assert not (MOD_ROOT / STOCK_CRASH_WALL.removeprefix("/")).exists()


def test_lua_extension_is_scenario_owned_and_namespaced() -> None:
    lua_path = MOD_ROOT / Path((SCENARIO_ROOT / f"{MOD_ID}.lua").as_posix())
    scenario_path = MOD_ROOT / Path((SCENARIO_ROOT / f"{MOD_ID}.json").as_posix())
    assert lua_path.is_file()
    scenario = _strict_json_file(scenario_path)
    assert scenario[0]["extensions"] == [{"name": MOD_ID}]
    assert not any((MOD_ROOT / "scripts").rglob("modScript.lua"))
    assert not (MOD_ROOT / "lua" / "ge" / "extensions" / MOD_ID / "main.lua").is_file()


def test_repository_submission_assets_and_authoring_evidence_stay_outside_mod() -> None:
    submission_path = REPOSITORY_ROOT / "submission.json"
    icon_path = REPOSITORY_ROOT / "icon.jpg"
    submission = _strict_json_file(submission_path)
    serialized_submission = json.dumps(submission, sort_keys=True)
    assert MOD_ID in serialized_submission
    assert ZIP_NAME in serialized_submission
    assert icon_path.is_file() and icon_path.stat().st_size > 0

    submission_images = [
        path
        for path in REPOSITORY_ROOT.rglob("*")
        if path.is_file()
        and path != icon_path
        and path.suffix.casefold() in {".jpg", ".jpeg", ".png"}
    ]
    assert len(submission_images) >= 2
    assert all(path.stat().st_size > 0 for path in submission_images)

    source_files = [
        path
        for path in EXAMPLE_ROOT.rglob("*")
        if path.is_file() and not path.is_relative_to(MOD_ROOT)
    ]
    source_names = {path.name for path in source_files}
    assert any(path.suffix.casefold() == ".blend" for path in source_files)
    assert "create_cannon_car_wash.py" in source_names
    assert any(path.name.endswith(".geometry.json") for path in source_files)
    assert any(path.name.endswith(".selector_handoff.json") for path in source_files)
    for phase in (2, 3, 4):
        assert {f"phase{phase}.json", f"phase{phase}_manifest.json"} & source_names


def test_deterministic_repository_archive_has_only_approved_root_members(tmp_path: Path) -> None:
    first_result = build_distribution(tmp_path / "first")
    second_result = build_distribution(tmp_path / "second")
    first_archive = Path(str(first_result["archive"]))
    second_archive = Path(str(second_result["archive"]))
    assert first_archive.name == ZIP_NAME
    assert second_archive.name == ZIP_NAME
    assert first_archive.read_bytes() == second_archive.read_bytes()
    assert first_result["sha256"] == second_result["sha256"]
    assert first_result["size"] == first_archive.stat().st_size
    assert first_result["member_count"] == len(EXPECTED_RUNTIME_FILES)
    submission = _strict_json_file(REPOSITORY_ROOT / "submission.json")
    assert submission["release_artifact"] == {
        "filename": ZIP_NAME,
        "sha256": first_result["sha256"],
        "size_bytes": first_result["size"],
        "member_count": first_result["member_count"],
    }

    with pytest.raises(DistributionError, match="--overwrite"):
        build_distribution(tmp_path / "first")
    overwritten = build_distribution(tmp_path / "first", overwrite=True)
    assert overwritten["sha256"] == first_result["sha256"]

    with zipfile.ZipFile(first_archive) as archive:
        names = archive.namelist()
        assert names == list(EXPECTED_RUNTIME_FILES)
        assert archive.testzip() is None
        assert all(not member.is_dir() for member in archive.infolist())
        assert all(not member.flag_bits & 0x1 for member in archive.infolist())
        assert all(member.date_time == ZIP_EPOCH for member in archive.infolist())
        assert all((member.external_attr >> 16) & 0o777 == 0o644 for member in archive.infolist())
        roots = {PurePosixPath(name).parts[0] for name in names}
        assert roots == {"levels", "vehicles"}
        assert roots == ALLOWED_TOP_LEVEL_ROOTS


def test_distribution_builder_refuses_an_unexpected_mod_file(tmp_path: Path) -> None:
    staged_mod = tmp_path / "mod"
    for relative in EXPECTED_RUNTIME_FILES:
        source = MOD_ROOT / Path(relative)
        destination = staged_mod / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    unexpected = staged_mod / "vehicles" / MOD_ID / "unexpected.txt"
    unexpected.write_text("must not enter the public archive\n", encoding="utf-8")

    output_dir = tmp_path / "output"
    with pytest.raises(DistributionError, match=r"unexpected=.*unexpected\.txt"):
        build_distribution(output_dir, mod_root=staged_mod)
    assert not (output_dir / ZIP_NAME).exists()
    if output_dir.exists():
        assert not list(output_dir.glob(f".{ZIP_NAME}.*.tmp"))


def test_distribution_builder_rejects_a_source_changed_after_its_first_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged_mod = tmp_path / "mod"
    for relative in EXPECTED_RUNTIME_FILES:
        source = MOD_ROOT / Path(relative)
        destination = staged_mod / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    victim = staged_mod / Path(EXPECTED_RUNTIME_FILES[0])
    real_stable_read = distribution._stable_read
    source_changed = False

    def change_source_after_first_read(path: Path) -> bytes:
        nonlocal source_changed
        payload = real_stable_read(path)
        if path == victim and not source_changed:
            victim.write_bytes(payload + b"\n")
            source_changed = True
        return payload

    monkeypatch.setattr(distribution, "_stable_read", change_source_after_first_read)
    output_dir = tmp_path / "output"
    with pytest.raises(DistributionError, match="changed while snapshotting"):
        build_distribution(output_dir, mod_root=staged_mod)

    assert source_changed is True
    assert not output_dir.exists()


def test_post_commit_temporary_cleanup_is_retried_without_false_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "cleanup-retry"
    real_unlink = Path.unlink
    cleanup_attempts = 0

    def fail_first_temporary_cleanup(path: Path, *, missing_ok: bool = False) -> None:
        nonlocal cleanup_attempts
        if path.parent == output_dir and path.name.startswith(f".{ZIP_NAME}."):
            cleanup_attempts += 1
            if cleanup_attempts == 1:
                raise PermissionError("simulated transient cleanup denial")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_first_temporary_cleanup)
    result = build_distribution(output_dir)
    destination = output_dir / ZIP_NAME

    assert cleanup_attempts == 2
    assert Path(str(result["archive"])) == destination
    assert destination.is_file()
    assert not list(output_dir.glob(f".{ZIP_NAME}.*.tmp"))


def test_persistent_post_commit_cleanup_logs_without_reporting_publication_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    output_dir = tmp_path / "cleanup-warning"
    real_unlink = Path.unlink

    def fail_temporary_cleanup(path: Path, *, missing_ok: bool = False) -> None:
        if path.parent == output_dir and path.name.startswith(f".{ZIP_NAME}."):
            raise PermissionError("simulated persistent cleanup denial")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_temporary_cleanup)
    with caplog.at_level("WARNING", logger=distribution.__name__):
        result = build_distribution(output_dir)

    destination = output_dir / ZIP_NAME
    assert "published successfully" in caplog.text
    assert Path(str(result["archive"])) == destination
    assert destination.is_file()
    temporary_paths = list(output_dir.glob(f".{ZIP_NAME}.*.tmp"))
    assert len(temporary_paths) == 1

    monkeypatch.setattr(Path, "unlink", real_unlink)
    temporary_paths[0].unlink()


def test_cleanup_error_does_not_mask_a_primary_publication_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "masked-error"
    real_unlink = Path.unlink

    def fail_publication(_source: Path, _target: Path) -> None:
        raise PermissionError("simulated publication denial")

    def fail_temporary_cleanup(path: Path, *, missing_ok: bool = False) -> None:
        if path.parent == output_dir and path.name.startswith(f".{ZIP_NAME}."):
            raise PermissionError("simulated cleanup denial")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(distribution.os, "link", fail_publication)
    monkeypatch.setattr(Path, "unlink", fail_temporary_cleanup)

    with pytest.raises(DistributionError, match="simulated publication denial") as captured:
        build_distribution(output_dir)

    assert any("simulated cleanup denial" in note for note in captured.value.__notes__)
    assert not (output_dir / ZIP_NAME).exists()

    monkeypatch.setattr(Path, "unlink", real_unlink)
    for temporary in output_dir.glob(f".{ZIP_NAME}.*.tmp"):
        temporary.unlink()


def test_no_overwrite_publication_preserves_a_racing_competitor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "race"
    output_dir.mkdir()
    destination = output_dir / ZIP_NAME
    competitor = b"archive published by a competing process\n"
    real_link = os.link

    def publish_competitor_then_link(source: Path, target: Path) -> None:
        Path(target).write_bytes(competitor)
        real_link(source, target)

    monkeypatch.setattr(
        "examples.cannon_car_wash.build_distribution.os.link",
        publish_competitor_then_link,
    )

    with pytest.raises(DistributionError, match="appeared during build"):
        build_distribution(output_dir)
    assert destination.read_bytes() == competitor
    assert not list(output_dir.glob(f".{ZIP_NAME}.*.tmp"))
