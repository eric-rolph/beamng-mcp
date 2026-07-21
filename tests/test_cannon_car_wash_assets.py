from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

EXAMPLE_ROOT = Path(__file__).parents[1] / "examples" / "cannon_car_wash"
ASSET_ROOT = EXAMPLE_ROOT / "mod" / "levels" / "gridmap_v2" / "art" / "shapes" / "carwash"
DAE_PATH = ASSET_ROOT / "cannon_car_wash.dae"
GEOMETRY_PATH = ASSET_ROOT / "cannon_car_wash.geometry.json"
MATERIALS_PATH = ASSET_ROOT / "cannon_car_wash.materials.json"
MOD_INFO_ROOT = EXAMPLE_ROOT / "mod" / "mod_info" / "cannon_car_wash"
PHASE2_MANIFEST_PATH = MOD_INFO_ROOT / "phase2_manifest.json"
PHASE4_MANIFEST_PATH = MOD_INFO_ROOT / "phase4_manifest.json"
MOD_ICON_PATH = MOD_INFO_ROOT / "icon.jpg"
ROOT_INFO_PATH = EXAMPLE_ROOT / "mod" / "info.json"
BLEND_PATH = EXAMPLE_ROOT / "blender" / "cannon_car_wash.blend"
PREVIEW_PATH = EXAMPLE_ROOT / "blender" / "cannon_car_wash_preview.png"
SCENARIO_ROOT = EXAMPLE_ROOT / "mod" / "levels" / "gridmap_v2" / "scenarios" / "cannon_car_wash"
SCENARIO_PREFAB_PATH = SCENARIO_ROOT / "cannon_car_wash.prefab.json"
COLLADA_NAMESPACE = {"c": "http://www.collada.org/2005/11/COLLADASchema"}


@pytest.mark.parametrize("artifact", [BLEND_PATH, PREVIEW_PATH])
def test_authoring_artifacts_do_not_disclose_user_profile_paths(artifact: Path) -> None:
    payload = artifact.read_bytes()
    assert re.search(rb"(?i)(?:[a-z]:[\\/])?users[\\/][^\\/\x00]+", payload) is None
    assert re.search(rb"/(?:home|Users)/[^/\x00]+", payload) is None


def _geometry_position_values(root: ET.Element, node: ET.Element) -> list[float]:
    instance = node.find("c:instance_geometry", COLLADA_NAMESPACE)
    assert instance is not None
    geometry_id = instance.attrib["url"].removeprefix("#")
    geometry = root.find(
        f".//c:library_geometries/c:geometry[@id='{geometry_id}']",
        COLLADA_NAMESPACE,
    )
    assert geometry is not None
    source = next(
        candidate
        for candidate in geometry.findall("c:mesh/c:source", COLLADA_NAMESPACE)
        if candidate.attrib["id"].endswith("-positions")
    )
    raw_values = source.findtext("c:float_array", namespaces=COLLADA_NAMESPACE)
    assert raw_values is not None
    return [float(value) for value in raw_values.split()]


def _transformed_bounds(root: ET.Element, node_name: str) -> tuple[list[float], list[float]]:
    node = root.find(
        f".//c:library_visual_scenes//c:node[@name='{node_name}']",
        COLLADA_NAMESPACE,
    )
    assert node is not None
    raw_matrix = node.findtext("c:matrix", namespaces=COLLADA_NAMESPACE)
    assert raw_matrix is not None
    matrix = [float(value) for value in raw_matrix.split()]
    assert len(matrix) == 16
    positions = _geometry_position_values(root, node)
    assert len(positions) % 3 == 0

    points: list[list[float]] = []
    for index in range(0, len(positions), 3):
        homogeneous = [*positions[index : index + 3], 1.0]
        points.append(
            [
                math.fsum(matrix[row * 4 + column] * homogeneous[column] for column in range(4))
                for row in range(3)
            ]
        )
    return (
        [min(point[axis] for point in points) for axis in range(3)],
        [max(point[axis] for point in points) for axis in range(3)],
    )


def test_cannon_car_wash_collada_matches_exported_geometry_manifest() -> None:
    manifest = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
    root = ET.parse(DAE_PATH).getroot()  # noqa: S314 - parses a repository-owned fixture

    unit = root.find("c:asset/c:unit", COLLADA_NAMESPACE)
    assert unit is not None
    assert float(unit.attrib["meter"]) == pytest.approx(1.0)
    assert root.findtext("c:asset/c:up_axis", namespaces=COLLADA_NAMESPACE) == "Z_UP"

    required_nodes = set(manifest["primary_structures"]) | set(manifest["collision_meshes"])
    for node_name in required_nodes:
        node = root.find(
            f".//c:library_visual_scenes//c:node[@name='{node_name}']",
            COLLADA_NAMESPACE,
        )
        assert node is not None, node_name
        positions = _geometry_position_values(root, node)
        assert positions
        assert all(math.isfinite(value) for value in positions)

    actual_minimum, actual_maximum = _transformed_bounds(root, "LaunchTrigger_Mesh")
    expected = manifest["primary_structures"]["LaunchTrigger_Mesh"]
    assert actual_minimum == pytest.approx(expected["min"], abs=1e-5)
    assert actual_maximum == pytest.approx(expected["max"], abs=1e-5)


def test_cannon_car_wash_clearance_trigger_and_animation_contract() -> None:
    manifest = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
    root = ET.parse(DAE_PATH).getroot()  # noqa: S314 - parses a repository-owned fixture

    assert manifest["coordinate_system"] == "right-handed, meters, Z-up"
    assert manifest["drive_axis"] == [0.0, 1.0, 0.0]
    assert manifest["entrance_center"][1] < manifest["trigger"]["center"][1]
    assert manifest["trigger"]["center"][1] < manifest["exit_center"][1]
    assert manifest["trigger"]["target_speed_kph"] >= 300.0

    opening = manifest["clear_opening"]
    truck = manifest["truck_envelope"]
    assert opening["width"] - truck["width"] >= 1.0
    assert opening["height"] - truck["height"] >= 1.0
    assert manifest["mesh_statistics"]["polygons"] <= 20_000
    assert manifest["collision_meshes"] == [
        "Colmesh-1",
        "Colmesh-2",
        "Colmesh-3",
        "Colmesh-4",
    ]

    channels = root.findall(".//c:library_animations//c:channel", COLLADA_NAMESPACE)
    spinner_targets = {
        channel.attrib["target"]
        for channel in channels
        if "Spinner" in channel.attrib.get("target", "")
    }
    assert spinner_targets == {
        "Brush_Left_1_Spinner/transform",
        "Brush_Left_2_Spinner/transform",
        "Brush_Right_1_Spinner/transform",
        "Brush_Right_2_Spinner/transform",
        "Brush_Overhead_Spinner/transform",
    }


def test_cannon_car_wash_phase2_materials_cover_every_collada_slot() -> None:
    root = ET.parse(DAE_PATH).getroot()  # noqa: S314 - parses a repository-owned fixture
    material_names = {
        material.attrib["name"]
        for material in root.findall(".//c:library_materials/c:material", COLLADA_NAMESPACE)
    }
    materials = json.loads(MATERIALS_PATH.read_text(encoding="utf-8"))

    assert set(materials) == material_names
    assert {definition["mapTo"] for definition in materials.values()} == material_names
    assert all(definition["class"] == "Material" for definition in materials.values())
    assert all(definition["version"] == 1.5 for definition in materials.values())
    invisible = materials["CW_TriggerInvisible"]
    assert invisible["translucent"] is True
    assert invisible["castShadows"] is False
    assert invisible["Stages"][0]["opacityFactor"] == 0.0


def test_cannon_car_wash_repository_metadata_and_icon() -> None:
    root_info = json.loads(ROOT_INFO_PATH.read_text(encoding="utf-8"))
    repository_info = json.loads((MOD_INFO_ROOT / "info.json").read_text(encoding="utf-8"))

    assert root_info["name"] == "cannon_car_wash"
    assert root_info["title"] == "Cannon Car Wash"
    assert root_info["version"] == "1.0.0"
    assert repository_info["name"] == root_info["name"]
    assert repository_info["version"] == root_info["version"]
    assert repository_info["version_string"] == root_info["version"]

    with Image.open(MOD_ICON_PATH) as icon:
        assert icon.format == "JPEG"
        assert icon.size == (640, 360)


def test_cannon_car_wash_phase2_package_preserves_the_blender_coordinate_contract() -> None:
    geometry = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
    phase2 = json.loads(PHASE2_MANIFEST_PATH.read_text(encoding="utf-8"))
    dae_sha256 = hashlib.sha256(DAE_PATH.read_bytes()).hexdigest()

    assert phase2["schema_version"] == 1
    assert phase2["phase"] == 2
    assert phase2["asset"]["sha256"] == dae_sha256
    assert phase2["trigger"]["local_center"] == geometry["trigger"]["center"]
    assert phase2["trigger"]["dimensions"] == geometry["trigger"]["dimensions"]
    assert phase2["phase3_launch_behavior_present"] is False

    asset_position = phase2["asset"]["position"]
    local_center = phase2["trigger"]["local_center"]
    assert phase2["asset"]["rotation_xyzw"] == [0.0, 0.0, 0.0, 1.0]
    expected_world_center = [asset_position[axis] + local_center[axis] for axis in range(3)]
    assert phase2["trigger"]["world_center"] == pytest.approx(expected_world_center)

    prefab_source = SCENARIO_PREFAB_PATH.read_text(encoding="utf-8")
    prefab_records = [json.loads(line) for line in prefab_source.splitlines() if line.strip()]
    prefab = {record["name"]: record for record in prefab_records}
    assert len(prefab_records) == 5
    assert prefab["cannon_car_wash_group"]["class"] == "SimGroup"

    visual = prefab["CannonCarWash_Visual"]
    assert visual["class"] == "TSStatic"
    assert visual["position"] == phase2["asset"]["position"]
    assert visual["scale"] == phase2["asset"]["scale"]
    assert visual["collisionType"] == "Collision Mesh"

    trigger = prefab["LaunchTrigger_Mesh"]
    assert trigger["class"] == "BeamNGTrigger"
    assert trigger["position"] == phase2["trigger"]["world_center"]
    assert trigger["scale"] == geometry["trigger"]["dimensions"]
    assert trigger["luaFunction"] == "onBeamNGTrigger"

    vehicle = prefab["cannon_car_wash_truck"]
    assert vehicle["class"] == "BeamNGVehicle"
    assert vehicle["jBeam"] == "pickup"
    assert vehicle["position"] == phase2["vehicle"]["position"]
    assert "applyClusterVelocityScaleAdd" not in prefab_source

    phase4 = json.loads(PHASE4_MANIFEST_PATH.read_text(encoding="utf-8"))
    wall = prefab["CannonCrashWall"]
    assert wall["class"] == "TSStatic"
    assert wall["shapeName"] == phase4["crash_target"]["asset"]
    assert wall["position"] == phase4["crash_target"]["position"]
    assert wall["collisionType"] == "Collision Mesh"
    assert phase4["crash_target"]["world_bounds"]["minimum"] == wall["position"]
    assert phase4["crash_target"]["world_bounds"]["maximum"] == pytest.approx(
        [
            wall["position"][axis] + phase4["crash_target"]["local_bounds"]["maximum"][axis]
            for axis in range(3)
        ]
    )

    # BeamNG's scenario loader accepts one scenario object wrapped in a JSON array.
    scenario_data = json.loads((SCENARIO_ROOT / "cannon_car_wash.json").read_text(encoding="utf-8"))
    assert isinstance(scenario_data, list) and len(scenario_data) == 1
    # BeamNG 0.38 auto-discovers a same-named sibling prefab. Listing that path
    # explicitly makes the legacy scenario loader append it twice.
    assert scenario_data[0]["prefabs"] == []
