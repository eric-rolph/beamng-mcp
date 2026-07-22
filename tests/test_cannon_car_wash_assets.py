from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image

EXAMPLE_ROOT = Path(__file__).parents[1] / "examples" / "cannon_car_wash"
MOD_ID = "ericrolph_cannon_car_wash"
ASSET_ROOT = EXAMPLE_ROOT / "mod" / "art" / "shapes" / MOD_ID
DAE_PATH = ASSET_ROOT / f"{MOD_ID}.dae"
GEOMETRY_PATH = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}.geometry.json"
MANIFEST_ROOT = EXAMPLE_ROOT / "validation" / "manifests"
PHASE2_MANIFEST_PATH = MANIFEST_ROOT / "phase2.json"
PHASE4_MANIFEST_PATH = MANIFEST_ROOT / "phase4.json"
REPOSITORY_ROOT = EXAMPLE_ROOT / "repository"
REPOSITORY_INFO_PATH = REPOSITORY_ROOT / "submission.json"
MOD_ICON_PATH = REPOSITORY_ROOT / "icon.jpg"
BLEND_PATH = EXAMPLE_ROOT / "blender" / "cannon_car_wash.blend"
PREVIEW_PATH = EXAMPLE_ROOT / "blender" / "cannon_car_wash_preview.png"
SCENARIO_ROOT = EXAMPLE_ROOT / "mod" / "levels" / "gridmap_v2" / "scenarios" / MOD_ID
MATERIALS_PATH = SCENARIO_ROOT / "main.materials.json"
SCENARIO_PREFAB_PATH = SCENARIO_ROOT / f"{MOD_ID}.prefab.json"
SCENARIO_PATH = SCENARIO_ROOT / f"{MOD_ID}.json"
SELECTOR_ROOT = EXAMPLE_ROOT / "mod" / "vehicles" / MOD_ID
SELECTOR_DAE_PATH = SELECTOR_ROOT / f"{MOD_ID}.dae"
SELECTOR_RUNTIME_DAE_PATH = SELECTOR_ROOT / f"{MOD_ID}_runtime_visual.dae"
SELECTOR_HANDOFF_PATH = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}.selector_handoff.json"
SELECTOR_JBEAM_PATH = SELECTOR_ROOT / f"{MOD_ID}.jbeam"
SELECTOR_MATERIALS_PATH = SELECTOR_ROOT / "main.materials.json"
SELECTOR_RESULTS_PATH = EXAMPLE_ROOT / "telemetry" / "cannon_car_wash_selector_results.json"
TEXTURE_MANIFEST_PATH = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}.textures.json"
GENERATED_TEXTURE_ROOT = EXAMPLE_ROOT / "textures" / "generated_png"
COLLADA_NAMESPACE = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
LAUNCH_TRIGGER_NAME = f"{MOD_ID}_launch_trigger"
WASH_TRIGGER_NAME = f"{MOD_ID}_wash_activation_trigger"
REPAIR_TRIGGER_NAME = f"{MOD_ID}_repair_trigger"
SCENARIO_VISUAL_NAME = f"{MOD_ID}_scenario_visual"
SCENARIO_GROUP_NAME = f"{MOD_ID}_group"
TRUCK_NAME = f"{MOD_ID}_truck"
CRASH_WALL_NAME = f"{MOD_ID}_crash_wall"
SELECTOR_VISUAL_NAME = f"{MOD_ID}_selector_visual"
SELECTOR_CAGE_NAME = f"{MOD_ID}_selector_cage"
PHYSICS_GROUP_NAME = f"{MOD_ID}_physics"
LAUNCH_TRIGGER_CENTER = [0.0, 0.0, 2.1]
LAUNCH_TRIGGER_DIMENSIONS = [5.8, 17.5, 4.6]
WASH_TRIGGER_CENTER = [0.0, 0.0, 2.2]
WASH_TRIGGER_DIMENSIONS = [5.8, 17.5, 4.4]
REPAIR_TRIGGER_CENTER = [0.0, 0.0, 2.1]
REPAIR_TRIGGER_DIMENSIONS = [5.4, 2.2, 4.2]
CITYBUS_ENVELOPE = {"width": 3.11, "length": 12.63, "height": 2.994}
COLLISION_MESH_NAMES = [f"Colmesh-{index}" for index in range(1, 5)]
EFFECT_NAMES = (
    {f"{MOD_ID}_mister_PreSoak_{side}_{height}" for side in ("L", "R") for height in range(1, 4)}
    | {f"{MOD_ID}_dryer_Mist_{side}_{height}" for side in ("L", "R") for height in range(1, 4)}
    | {f"{MOD_ID}_dryer_{layer}_{side}" for layer in ("Steam", "Dust") for side in ("L", "R")}
)
EFFECT_EMITTER_COUNTS = {
    "BNGP_sprinkler": 6,
    "BNGP_waterfallsteam": 6,
    "BNGP_34": 2,
    "BNGP_2": 2,
}
REQUESTED_TO_RUNTIME = {
    "BNG_Waterfall_Mist": "BNGP_waterfallsteam",
    "BNG_exhaust_steam": "BNGP_34",
    "BNG_Ambient_Dust": "BNGP_2",
}


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

    trigger_names = {LAUNCH_TRIGGER_NAME, WASH_TRIGGER_NAME, REPAIR_TRIGGER_NAME}
    required_nodes = (set(manifest["primary_structures"]) - trigger_names) | set(
        manifest["collision_meshes"]
    )
    runtime_node_names = {
        node.attrib["name"]
        for node in root.findall(".//c:library_visual_scenes//c:node", COLLADA_NAMESPACE)
    }
    assert trigger_names.isdisjoint(runtime_node_names)
    for node_name in required_nodes:
        node = root.find(
            f".//c:library_visual_scenes//c:node[@name='{node_name}']",
            COLLADA_NAMESPACE,
        )
        assert node is not None, node_name
        positions = _geometry_position_values(root, node)
        assert positions
        assert all(math.isfinite(value) for value in positions)
        if node_name in COLLISION_MESH_NAMES:
            instance = node.find("c:instance_geometry", COLLADA_NAMESPACE)
            assert instance is not None
            geometry_id = instance.attrib["url"].removeprefix("#")
            assert geometry_id.startswith(f"{MOD_ID}_")
            geometry = root.find(
                f".//c:library_geometries/c:geometry[@id='{geometry_id}']",
                COLLADA_NAMESPACE,
            )
            assert geometry is not None
            assert geometry.attrib["name"].startswith(f"{MOD_ID}_")

    trigger_specs = {
        LAUNCH_TRIGGER_NAME: (LAUNCH_TRIGGER_CENTER, LAUNCH_TRIGGER_DIMENSIONS),
        WASH_TRIGGER_NAME: (WASH_TRIGGER_CENTER, WASH_TRIGGER_DIMENSIONS),
        REPAIR_TRIGGER_NAME: (REPAIR_TRIGGER_CENTER, REPAIR_TRIGGER_DIMENSIONS),
    }
    for trigger_name, (center, dimensions) in trigger_specs.items():
        expected = manifest["primary_structures"][trigger_name]
        expected_minimum = [center[axis] - dimensions[axis] / 2.0 for axis in range(3)]
        expected_maximum = [center[axis] + dimensions[axis] / 2.0 for axis in range(3)]
        assert expected["min"] == pytest.approx(expected_minimum, abs=1e-5)
        assert expected["max"] == pytest.approx(expected_maximum, abs=1e-5)


def test_cannon_car_wash_clearance_trigger_and_animation_contract() -> None:
    manifest = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
    root = ET.parse(DAE_PATH).getroot()  # noqa: S314 - parses a repository-owned fixture

    assert manifest["asset"] == MOD_ID
    assert manifest["coordinate_system"] == "right-handed, meters, Z-up"
    assert manifest["drive_axis"] == [0.0, 1.0, 0.0]
    assert manifest["entrance_center"][1] < manifest["trigger"]["center"][1]
    assert manifest["trigger"]["center"][1] < manifest["exit_center"][1]
    assert manifest["trigger"] == {
        "name": LAUNCH_TRIGGER_NAME,
        "center": LAUNCH_TRIGGER_CENTER,
        "dimensions": LAUNCH_TRIGGER_DIMENSIONS,
        "mode": "Contains",
        "events": ["enter", "exit"],
        "target_speed_kph": 360.0,
    }
    assert manifest["wash_activation_trigger"] == {
        "name": WASH_TRIGGER_NAME,
        "center": WASH_TRIGGER_CENTER,
        "dimensions": WASH_TRIGGER_DIMENSIONS,
        "mode": "Overlaps",
        "events": ["enter", "exit"],
    }
    assert manifest["repair_trigger"] == {
        "name": REPAIR_TRIGGER_NAME,
        "center": REPAIR_TRIGGER_CENTER,
        "dimensions": REPAIR_TRIGGER_DIMENSIONS,
        "mode": "Overlaps",
        "events": ["enter", "exit"],
        "repair_strategy": "RESET_PHYSICS",
    }
    assert manifest["trigger"]["target_speed_kph"] >= 300.0

    opening = manifest["clear_opening"]
    truck = manifest["truck_envelope"]
    citybus = manifest["supported_large_vehicle_envelope"]
    assert opening["width"] - truck["width"] >= 1.0
    assert opening["height"] - truck["height"] >= 1.0
    assert manifest["trigger"]["dimensions"][1] > truck["length"]
    assert manifest["trigger"]["dimensions"][2] > truck["height"]
    assert citybus == {
        "model": "citybus",
        "configuration": "city",
        "source": "BeamNG.drive 0.38.6 vehicles/citybus/info_city.json BoundingBox",
        **CITYBUS_ENVELOPE,
    }
    assert manifest["trigger"]["dimensions"][0] > citybus["width"]
    assert manifest["trigger"]["dimensions"][1] > citybus["length"]
    assert manifest["trigger"]["dimensions"][2] > citybus["height"]
    assert manifest["wash_activation_trigger"]["dimensions"][1] <= opening["length"]
    entrance_y = float(manifest["entrance_center"][1])
    exit_y = float(manifest["exit_center"][1])
    assert manifest["repair_trigger"]["center"][1] == pytest.approx((entrance_y + exit_y) / 2.0)
    wash_min_y = WASH_TRIGGER_CENTER[1] - WASH_TRIGGER_DIMENSIONS[1] / 2.0
    wash_max_y = WASH_TRIGGER_CENTER[1] + WASH_TRIGGER_DIMENSIONS[1] / 2.0
    launch_min_y = LAUNCH_TRIGGER_CENTER[1] - LAUNCH_TRIGGER_DIMENSIONS[1] / 2.0
    launch_max_y = LAUNCH_TRIGGER_CENTER[1] + LAUNCH_TRIGGER_DIMENSIONS[1] / 2.0
    repair_min_y = REPAIR_TRIGGER_CENTER[1] - REPAIR_TRIGGER_DIMENSIONS[1] / 2.0
    repair_max_y = REPAIR_TRIGGER_CENTER[1] + REPAIR_TRIGGER_DIMENSIONS[1] / 2.0
    assert wash_min_y <= launch_min_y < launch_max_y <= wash_max_y
    assert wash_min_y <= repair_min_y < repair_max_y <= wash_max_y
    assert manifest["mesh_statistics"]["polygons"] <= 20_000
    exported = manifest["export_statistics"]
    actual_triangle_count = sum(
        int(primitive.attrib["count"])
        for primitive in root.findall(".//c:triangles", COLLADA_NAMESPACE)
    )
    actual_geometry_count = len(
        root.findall(".//c:library_geometries/c:geometry", COLLADA_NAMESPACE)
    )
    actual_primitive_group_count = len(root.findall(".//c:triangles", COLLADA_NAMESPACE))
    actual_material_symbol_count = len(
        {
            material.attrib["symbol"]
            for material in root.findall(".//c:instance_material", COLLADA_NAMESPACE)
        }
    )
    assert exported == {
        "triangle_count": actual_triangle_count,
        "geometry_count": actual_geometry_count,
        "primitive_group_count": actual_primitive_group_count,
        "material_symbol_count": actual_material_symbol_count,
    }
    assert actual_triangle_count <= 15_000
    assert actual_primitive_group_count <= 36
    assert actual_material_symbol_count == 18
    dae_text = DAE_PATH.read_text(encoding="utf-8")
    assert "EntranceSign_Text" not in dae_text
    assert "ExitSign_Text" not in dae_text
    assert manifest["collision_meshes"] == COLLISION_MESH_NAMES

    channels = root.findall(".//c:library_animations//c:channel", COLLADA_NAMESPACE)
    spinner_targets = {
        channel.attrib["target"]
        for channel in channels
        if "Spinner" in channel.attrib.get("target", "")
    }
    assert spinner_targets == {
        f"{MOD_ID}_Brush_Left_1_Spinner/transform",
        f"{MOD_ID}_Brush_Left_2_Spinner/transform",
        f"{MOD_ID}_Brush_Right_1_Spinner/transform",
        f"{MOD_ID}_Brush_Right_2_Spinner/transform",
        f"{MOD_ID}_Brush_Overhead_Spinner/transform",
    }
    ambient = root.find(
        "c:library_animation_clips/c:animation_clip[@name='ambient']",
        COLLADA_NAMESPACE,
    )
    assert ambient is not None
    assert float(ambient.attrib["start"]) == pytest.approx(0.0)
    assert float(ambient.attrib["end"]) == pytest.approx(2.541667)
    animation_ids = {
        animation.attrib["id"]
        for animation in root.findall("c:library_animations/c:animation", COLLADA_NAMESPACE)
    }
    clip_targets = {
        instance.attrib["url"].removeprefix("#")
        for instance in ambient.findall("c:instance_animation", COLLADA_NAMESPACE)
    }
    assert len(animation_ids) == 5
    assert clip_targets == animation_ids
    cyclic = ambient.find(
        "c:extra/c:technique[@profile='Torque']/c:cyclic",
        COLLADA_NAMESPACE,
    )
    assert cyclic is not None and cyclic.text == "1"


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
    assert all(name.startswith(f"{MOD_ID}_") for name in materials)
    assert f"{MOD_ID}_trigger_invisible" not in materials


def test_selector_runtime_visual_preserves_animations_and_uses_vehicle_materials() -> None:
    root = ET.parse(SELECTOR_RUNTIME_DAE_PATH).getroot()  # noqa: S314 - owned fixture
    channels = root.findall(".//c:library_animations//c:channel", COLLADA_NAMESPACE)
    assert len(channels) == 5
    runtime_ambient = root.find(
        "c:library_animation_clips/c:animation_clip[@name='ambient']",
        COLLADA_NAMESPACE,
    )
    assert runtime_ambient is not None
    runtime_cyclic = runtime_ambient.find(
        "c:extra/c:technique[@profile='Torque']/c:cyclic",
        COLLADA_NAMESPACE,
    )
    assert runtime_cyclic is not None and runtime_cyclic.text == "1"

    runtime_materials = {
        material.attrib["name"]
        for material in root.findall(".//c:library_materials/c:material", COLLADA_NAMESPACE)
    }
    selector_materials = json.loads(SELECTOR_MATERIALS_PATH.read_text(encoding="utf-8"))
    assert runtime_materials == set(selector_materials)
    assert len(runtime_materials) == 18
    assert all(name.startswith(f"{MOD_ID}_selector_") for name in runtime_materials)


def test_cannon_car_wash_pbr_authoring_maps_are_power_of_two_seamless_and_typed() -> None:
    manifest = json.loads(TEXTURE_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["texture_root"] == "textures/generated_png"
    assert manifest["normal_convention"] == "OpenGL_Y_positive"
    assert len(manifest["files"]) == 22
    assert {entry["name"] for entry in manifest["files"]} == {
        path.name for path in GENERATED_TEXTURE_ROOT.glob("*.png")
    }

    for entry in manifest["files"]:
        path = GENERATED_TEXTURE_ROOT / entry["name"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        with Image.open(path) as image:
            assert image.width >= 16 and image.width & (image.width - 1) == 0
            assert image.height >= 16 and image.height & (image.height - 1) == 0
            expected_mode = "L" if path.name.endswith(".data.png") else "RGB"
            if path.name.endswith("sign_emissive.data.png"):
                expected_mode = "RGB"
            assert image.mode == expected_mode
            if any(
                material in path.name
                for material in ("_cmu.", "_interior_brick.", "_wet_concrete.", "_corrugated_blue.")
            ):
                assert list(image.crop((0, 0, 1, image.height)).getdata()) == list(
                    image.crop((image.width - 1, 0, image.width, image.height)).getdata()
                )
                assert list(image.crop((0, 0, image.width, 1)).getdata()) == list(
                    image.crop((0, image.height - 1, image.width, image.height)).getdata()
                )


def test_cannon_car_wash_materials_use_specialized_pbr_channels() -> None:
    materials = json.loads(MATERIALS_PATH.read_text(encoding="utf-8"))
    required = {
        f"{MOD_ID}_exterior_cmu",
        f"{MOD_ID}_interior_brick",
        f"{MOD_ID}_wet_concrete",
        f"{MOD_ID}_corrugated_blue",
        f"{MOD_ID}_brush_cards",
        f"{MOD_ID}_sign_face",
    }
    assert required <= set(materials)
    for name in required - {f"{MOD_ID}_brush_cards", f"{MOD_ID}_sign_face"}:
        stage = materials[name]["Stages"][0]
        assert {"baseColorMap", "normalMap", "roughnessMap", "ambientOcclusionMap"} <= set(stage)
    brush = materials[f"{MOD_ID}_brush_cards"]
    assert brush["alphaTest"] is True
    assert brush["doubleSided"] is True
    assert brush["translucentBlendOp"] == "None"
    assert brush["Stages"][0]["opacityMap"].endswith("_opacity.data.png")
    sign_stage = materials[f"{MOD_ID}_sign_face"]["Stages"][0]
    assert sign_stage["emissiveMap"].endswith("_sign_emissive.data.png")
    assert min(sign_stage["emissiveFactor"]) > 1.0


def test_cannon_car_wash_vehicle_selector_metadata_and_thumbnails() -> None:
    model_info = json.loads((SELECTOR_ROOT / "info.json").read_text(encoding="utf-8"))
    config_info = json.loads((SELECTOR_ROOT / "info_standard.json").read_text(encoding="utf-8"))
    config = json.loads((SELECTOR_ROOT / "standard.pc").read_text(encoding="utf-8"))

    assert model_info == {
        "Author": "Eric Rolph",
        "Name": "Cannon Car Wash",
        "Type": "Prop",
        "default_pc": "standard",
    }
    assert config == {
        "format": 2,
        "mainPartName": MOD_ID,
        "model": MOD_ID,
        "parts": {},
    }
    assert config_info["Configuration"] == "Standard"
    assert config_info["Weight"] > 10_000
    assert config_info["Value"] > 0
    for thumbnail_name in ("default.jpg", "standard.jpg"):
        with Image.open(SELECTOR_ROOT / thumbnail_name) as thumbnail:
            assert thumbnail.format == "JPEG"
            assert thumbnail.size == (640, 360)


def test_cannon_car_wash_selector_collada_is_a_clean_single_flexbody() -> None:
    handoff = json.loads(SELECTOR_HANDOFF_PATH.read_text(encoding="utf-8"))
    root = ET.parse(SELECTOR_DAE_PATH).getroot()  # noqa: S314 - repository-owned fixture
    dae_bytes = SELECTOR_DAE_PATH.read_bytes()

    assert handoff["schema"] == "ericrolph-cannon-car-wash-selector-handoff-v1"
    assert handoff["asset"]["id"] == MOD_ID
    assert handoff["asset"]["physics_cage"] == SELECTOR_CAGE_NAME
    assert handoff["asset"]["visual_mesh"] == SELECTOR_VISUAL_NAME
    assert handoff["coordinate_system"]["source_world_to_beamng_vehicle"] == [
        [-1.0, 0.0, 0.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    assert handoff["visual"]["sha256"] == hashlib.sha256(dae_bytes).hexdigest()
    assert handoff["visual"]["size"] == len(dae_bytes)
    assert root.findtext("c:asset/c:up_axis", namespaces=COLLADA_NAMESPACE) == "Z_UP"

    scene_nodes = root.findall(".//c:library_visual_scenes//c:node", COLLADA_NAMESPACE)
    assert [node.attrib["name"] for node in scene_nodes] == [SELECTOR_VISUAL_NAME]
    assert LAUNCH_TRIGGER_NAME.encode() not in dae_bytes
    assert WASH_TRIGGER_NAME.encode() not in dae_bytes
    assert b"Colmesh-" not in dae_bytes
    assert SELECTOR_CAGE_NAME.encode() not in dae_bytes

    actual_minimum, actual_maximum = _transformed_bounds(root, SELECTOR_VISUAL_NAME)
    assert actual_minimum == pytest.approx(handoff["visual"]["bounds"]["min"], abs=1e-5)
    assert actual_maximum == pytest.approx(handoff["visual"]["bounds"]["max"], abs=1e-5)

    dae_materials = {
        material.attrib["name"]
        for material in root.findall(".//c:library_materials/c:material", COLLADA_NAMESPACE)
    }
    selector_materials = json.loads(SELECTOR_MATERIALS_PATH.read_text(encoding="utf-8"))
    scenario_materials = json.loads(MATERIALS_PATH.read_text(encoding="utf-8"))
    assert dae_materials == set(handoff["visual"]["materials"])
    assert set(selector_materials) == dae_materials
    assert {definition["mapTo"] for definition in selector_materials.values()} == dae_materials
    assert dae_materials.isdisjoint(scenario_materials)
    assert all(name.startswith(f"{MOD_ID}_selector_") for name in dae_materials)


def test_cannon_car_wash_selector_jbeam_exactly_matches_blender_cage() -> None:
    handoff = json.loads(SELECTOR_HANDOFF_PATH.read_text(encoding="utf-8"))
    jbeam = json.loads(SELECTOR_JBEAM_PATH.read_text(encoding="utf-8"))
    assert list(jbeam) == [MOD_ID]
    part = jbeam[MOD_ID]

    assert part["slotType"] == "main"
    assert part["flexbodies"] == [
        ["mesh", "[group]:"],
        [SELECTOR_VISUAL_NAME, [PHYSICS_GROUP_NAME]],
    ]
    assert part["cameraExternal"]["distance"] >= 20.0
    assert part["refNodes"] == [
        ["ref:", "back:", "left:", "up:"],
        [
            handoff["refnodes"]["ref"],
            handoff["refnodes"]["back"],
            handoff["refnodes"]["left"],
            handoff["refnodes"]["up"],
        ],
    ]

    expected_positions = {node["id"]: node["position"] for node in handoff["nodes"]}
    actual_nodes = {row[0]: row for row in part["nodes"][1:]}
    assert set(actual_nodes) == set(expected_positions)
    for node_id, expected_position in expected_positions.items():
        assert actual_nodes[node_id][1:4] == expected_position
        assert actual_nodes[node_id][4]["group"] == PHYSICS_GROUP_NAME

    assert len(actual_nodes) == 79
    fixed_nodes = {node_id for node_id, row in actual_nodes.items() if row[4]["fixed"]}
    assert fixed_nodes == set(actual_nodes)
    assert set(handoff["refnodes"].values()) <= fixed_nodes
    assert expected_positions[handoff["refnodes"]["ref"]] == [0.0, 0.0, 0.0]
    assert expected_positions[handoff["refnodes"]["back"]] == [0.0, 3.0, 0.0]
    spawn_envelope_nodes = set(handoff["spawn_envelope_nodes"])
    assert len(spawn_envelope_nodes) == 8
    assert set(handoff["refnodes"].values()).isdisjoint(spawn_envelope_nodes)
    assert {
        node_id for node_id, row in actual_nodes.items() if row[4]["collision"] is True
    } == spawn_envelope_nodes
    assert all(row[4]["selfCollision"] is False for row in actual_nodes.values())
    assert {
        node_id for node_id, row in actual_nodes.items() if row[4]["staticCollision"] is True
    } == spawn_envelope_nodes

    envelope_positions = [expected_positions[node_id] for node_id in spawn_envelope_nodes]
    envelope_minimum = [min(position[axis] for position in envelope_positions) for axis in range(3)]
    envelope_maximum = [max(position[axis] for position in envelope_positions) for axis in range(3)]
    assert envelope_minimum == pytest.approx([-3.4, -9.0, 0.0], abs=1e-5)
    assert envelope_maximum == pytest.approx([3.4, 9.0, 4.96], abs=1e-5)
    assert all(envelope_maximum[axis] > envelope_minimum[axis] for axis in range(3))

    base_nodes = set(handoff["base_nodes"])
    minimum_z = min(position[2] for position in expected_positions.values())
    assert all(expected_positions[node_id][2] == minimum_z for node_id in base_nodes)
    assert len(base_nodes) >= 4
    assert all(actual_nodes[node_id][4]["nodeWeight"] == 500.0 for node_id in base_nodes)
    assert all(
        row[4]["nodeWeight"] == 125.0
        for node_id, row in actual_nodes.items()
        if node_id not in base_nodes
    )

    actual_beams = {tuple(sorted(row[:2])) for row in part["beams"][1:]}
    expected_beams = {tuple(sorted(pair)) for pair in handoff["beams"]}
    assert actual_beams == expected_beams
    assert all(row[2]["beamStrength"] == "FLT_MAX" for row in part["beams"][1:])

    expected_triangles = [triangle["nodes"] for triangle in handoff["triangles"]]
    actual_triangles = [row[:3] for row in part["triangles"][1:]]
    assert actual_triangles == expected_triangles
    assert {node_id for triangle in actual_triangles for node_id in triangle} <= fixed_nodes
    station_by_node = {node["id"]: node["station"] for node in handoff["nodes"]}
    # Every collision triangle spans adjacent length stations. No end-cap triangle
    # closes either portal, so the standard D-Series can drive through the prop.
    for triangle in actual_triangles:
        stations = {station_by_node[node_id] for node_id in triangle}
        assert len(stations) == 2
        assert max(stations) - min(stations) == 1
        for index, first in enumerate(triangle):
            second = triangle[(index + 1) % len(triangle)]
            assert tuple(sorted((first, second))) in expected_beams

    total_mass = math.fsum(row[4]["nodeWeight"] for row in actual_nodes.values())
    config_info = json.loads((SELECTOR_ROOT / "info_standard.json").read_text(encoding="utf-8"))
    assert total_mass == config_info["Weight"]

    live_result = json.loads(SELECTOR_RESULTS_PATH.read_text(encoding="utf-8"))
    assert live_result["result"] == "passed"
    assert live_result["catalog"] == {
        "default_configuration": "standard",
        "model": MOD_ID,
        "name": "Cannon Car Wash",
        "type": "Prop",
    }
    assert live_result["topology"] == {
        "beam_count": len(handoff["beams"]),
        "engine_collision_mode_3_count": len(spawn_envelope_nodes),
        "fixed_node_count": len(handoff["nodes"]),
        "flexbody_count": 1,
        "node_count": len(handoff["nodes"]),
        "total_mass_kg": total_mass,
        "triangle_count": len(handoff["triangles"]),
        "vehicle_directory": f"/vehicles/{MOD_ID}/",
    }
    collision = live_result["collision_contact"]
    assert collision["vehicle"] == TRUCK_NAME
    assert collision["injected_velocity_x_mps"] == 30.0
    assert collision["peak_positive_velocity_x_mps"] >= 20.0
    assert collision["minimum_post_impact_velocity_x_mps"] <= 5.0
    assert collision["maximum_world_x"] < collision["wall_world_x"]
    assert collision["final_truck_position"][0] < collision["wall_world_x"]
    assert (
        math.dist(
            collision["prop_position_after_contact"], live_result["stability"]["settled_position"]
        )
        <= 0.05
    )
    assert math.sqrt(sum(value * value for value in collision["final_truck_velocity_mps"])) <= 0.05
    assert live_result["stability"]["rigidity"] == {
        "maximum_shell_node_displacement_m": 0.0,
        "maximum_shell_node_speed_mps": 0.0,
    }
    assert collision["rigidity"]["maximum_ref_displacement_m"] <= 0.005
    assert collision["rigidity"]["maximum_ref_speed_mps"] <= 0.01
    assert collision["rigidity"]["maximum_shell_node_displacement_m"] <= 0.005
    assert collision["rigidity"]["maximum_shell_node_speed_mps"] <= 0.01
    assert collision["rigidity"]["sample_count"] >= 30
    assert collision["sample_count"] == 70
    assert live_result["selector_asset_errors"] == []


def test_cannon_car_wash_repository_metadata_and_icon() -> None:
    repository_info = json.loads(REPOSITORY_INFO_PATH.read_text(encoding="utf-8"))

    assert repository_info["internal_name"] == MOD_ID
    assert repository_info["title"] == "Cannon Car Wash"
    assert repository_info["version"] == "1.11.1"
    assert repository_info["author"] == "Eric Rolph"

    with Image.open(MOD_ICON_PATH) as icon:
        assert icon.format == "JPEG"
        assert icon.size == (96, 96)
    assert repository_info["resource_icon"] == {
        "path": "icon.jpg",
        "width": 96,
        "height": 96,
    }


def test_cannon_car_wash_phase2_package_preserves_the_blender_coordinate_contract() -> None:
    geometry = json.loads(GEOMETRY_PATH.read_text(encoding="utf-8"))
    phase2 = json.loads(PHASE2_MANIFEST_PATH.read_text(encoding="utf-8"))
    dae_sha256 = hashlib.sha256(DAE_PATH.read_bytes()).hexdigest()

    assert phase2["schema_version"] == 1
    assert phase2["phase"] == 2
    assert phase2["asset"]["path"] == (f"/art/shapes/{MOD_ID}/{MOD_ID}.dae")
    assert phase2["asset"]["sha256"] == dae_sha256
    assert phase2["trigger"]["name"] == LAUNCH_TRIGGER_NAME
    assert phase2["trigger"]["local_center"] == geometry["trigger"]["center"]
    assert phase2["trigger"]["dimensions"] == geometry["trigger"]["dimensions"]
    assert phase2["trigger"]["mode"] == "Contains"
    assert phase2["trigger"]["test_type"] == "Bounding box"
    assert (
        phase2["wash_activation_trigger"]["local_center"]
        == geometry["wash_activation_trigger"]["center"]
    )
    assert phase2["wash_activation_trigger"]["name"] == WASH_TRIGGER_NAME
    assert (
        phase2["wash_activation_trigger"]["dimensions"]
        == geometry["wash_activation_trigger"]["dimensions"]
    )
    assert phase2["wash_activation_trigger"]["mode"] == "Overlaps"
    assert phase2["wash_activation_trigger"]["test_type"] == "Bounding box"
    assert phase2["repair_trigger"]["name"] == REPAIR_TRIGGER_NAME
    assert phase2["repair_trigger"]["local_center"] == geometry["repair_trigger"]["center"]
    assert phase2["repair_trigger"]["dimensions"] == geometry["repair_trigger"]["dimensions"]
    assert phase2["repair_trigger"]["mode"] == "Overlaps"
    assert phase2["repair_trigger"]["test_type"] == "Bounding box"
    assert phase2["repair_trigger"]["repair_strategy"] == "RESET_PHYSICS"
    assert phase2["wash_effects"]["visual_name"] == SCENARIO_VISUAL_NAME
    assert phase2["wash_effects"]["roller_sequence"] == "ambient"
    assert phase2["wash_effects"]["roller_control_field"] == "playAmbient"
    assert phase2["wash_effects"]["node_datablock"] == "lightExampleEmitterNodeData1"
    assert phase2["wash_effects"]["requested_to_runtime"] == REQUESTED_TO_RUNTIME
    assert phase2["phase3_launch_behavior_present"] is False

    asset_position = phase2["asset"]["position"]
    local_center = phase2["trigger"]["local_center"]
    assert phase2["asset"]["rotation_xyzw"] == [0.0, 0.0, 0.0, 1.0]
    expected_world_center = [asset_position[axis] + local_center[axis] for axis in range(3)]
    assert phase2["trigger"]["world_center"] == pytest.approx(expected_world_center)
    wash_local_center = phase2["wash_activation_trigger"]["local_center"]
    expected_wash_world_center = [
        asset_position[axis] + wash_local_center[axis] for axis in range(3)
    ]
    assert phase2["wash_activation_trigger"]["world_center"] == pytest.approx(
        expected_wash_world_center
    )
    repair_local_center = phase2["repair_trigger"]["local_center"]
    expected_repair_world_center = [
        asset_position[axis] + repair_local_center[axis] for axis in range(3)
    ]
    assert phase2["repair_trigger"]["world_center"] == pytest.approx(expected_repair_world_center)

    prefab_source = SCENARIO_PREFAB_PATH.read_text(encoding="utf-8")
    prefab_records = [json.loads(line) for line in prefab_source.splitlines() if line.strip()]
    prefab = {record["name"]: record for record in prefab_records}
    assert len(prefab_records) == 36
    assert prefab[SCENARIO_GROUP_NAME]["class"] == "SimGroup"

    visual = prefab[SCENARIO_VISUAL_NAME]
    assert visual["class"] == "TSStatic"
    assert visual["shapeName"] == f"/art/shapes/{MOD_ID}/{MOD_ID}.dae"
    assert visual["position"] == phase2["asset"]["position"]
    assert visual["rotationMatrix"] == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    assert visual["scale"] == phase2["asset"]["scale"]
    assert visual["dynamic"] == "1"
    assert visual["playAmbient"] == "1"
    assert visual["collisionType"] == "Collision Mesh"

    trigger = prefab[LAUNCH_TRIGGER_NAME]
    assert trigger["class"] == "BeamNGTrigger"
    assert trigger["position"] == phase2["trigger"]["world_center"]
    assert trigger["scale"] == geometry["trigger"]["dimensions"]
    assert trigger["luaFunction"] == "onBeamNGTrigger"
    assert trigger["triggerMode"] == "Contains"
    assert trigger["triggerTestType"] == "Bounding box"

    wash_trigger = prefab[WASH_TRIGGER_NAME]
    assert wash_trigger["class"] == "BeamNGTrigger"
    assert wash_trigger["position"] == phase2["wash_activation_trigger"]["world_center"]
    assert wash_trigger["scale"] == geometry["wash_activation_trigger"]["dimensions"]
    assert wash_trigger["luaFunction"] == "onBeamNGTrigger"
    assert wash_trigger["triggerMode"] == "Overlaps"
    assert wash_trigger["triggerTestType"] == "Bounding box"

    repair_trigger = prefab[REPAIR_TRIGGER_NAME]
    assert repair_trigger["class"] == "BeamNGTrigger"
    assert repair_trigger["position"] == phase2["repair_trigger"]["world_center"]
    assert repair_trigger["scale"] == geometry["repair_trigger"]["dimensions"]
    assert repair_trigger["luaFunction"] == "onBeamNGTrigger"
    assert repair_trigger["triggerMode"] == "Overlaps"
    assert repair_trigger["triggerTestType"] == "Bounding box"

    effect_specs = {effect["name"]: effect for effect in geometry["wash_effects"]["effects"]}
    assert set(effect_specs) == EFFECT_NAMES
    phase2_effects = {effect["name"]: effect for effect in phase2["wash_effects"]["effects"]}
    assert set(phase2_effects) == EFFECT_NAMES
    effects = {
        name: record for name, record in prefab.items() if record["class"] == "ParticleEmitterNode"
    }
    assert set(effects) == EFFECT_NAMES
    assert geometry["wash_effects"]["node_datablock"] == "lightExampleEmitterNodeData1"
    assert geometry["wash_effects"]["requested_to_runtime"] == REQUESTED_TO_RUNTIME
    assert Counter(effect["emitter"] for effect in effect_specs.values()) == EFFECT_EMITTER_COUNTS
    assert Counter(effect["role"] for effect in effect_specs.values()) == {
        "wash_water": 6,
        "dryer_primary": 6,
        "dryer_secondary": 2,
        "dryer_ambient": 2,
    }
    for name, effect in effects.items():
        spec = effect_specs[name]
        expected_position = [
            asset_position[axis] + spec["local_position"][axis] for axis in range(3)
        ]
        synchronized = phase2_effects[name]
        for field in ("role", "requested_particle", "emitter", "particle_data"):
            assert synchronized[field] == spec[field]
        assert synchronized["local_position"] == spec["local_position"]
        assert synchronized["world_position"] == pytest.approx(expected_position)
        assert synchronized["rotation_matrix"] == spec["rotation_matrix"]
        assert effect["position"] == pytest.approx(expected_position)
        assert effect["rotationMatrix"] == spec["rotation_matrix"]
        assert effect["dataBlock"] == "lightExampleEmitterNodeData1"
        assert effect["emitter"] == spec["emitter"]
        assert effect["active"] is False
        assert effect["__parent"] == SCENARIO_GROUP_NAME

    light_specs = {light["name"]: light for light in geometry["lighting"]["anchors"]}
    phase2_lights = {light["name"]: light for light in phase2["lighting"]["lights"]}
    lights = {
        name: record
        for name, record in prefab.items()
        if record["class"] in {"PointLight", "SpotLight"}
    }
    assert len(light_specs) == len(phase2_lights) == len(lights) == 13
    assert set(light_specs) == set(phase2_lights) == set(lights)
    assert Counter(spec["class"] for spec in light_specs.values()) == {
        "PointLight": 9,
        "SpotLight": 4,
    }
    assert phase2["lighting"]["class_counts"] == {"PointLight": 9, "SpotLight": 4}
    for name, light in lights.items():
        spec = light_specs[name]
        expected_position = [
            asset_position[axis] + spec["local_position"][axis] for axis in range(3)
        ]
        assert light["position"] == pytest.approx(expected_position)
        assert light["brightness"] == spec["brightness"]
        assert light["castShadows"] is spec["cast_shadows"]
        assert len(light["rotationMatrix"]) == 9
        if spec["class"] == "PointLight":
            assert light["radius"] == spec["radius"]
        else:
            assert light["range"] == spec["range"]
            assert light["innerAngle"] == spec["inner_angle_degrees"]
            assert light["outerAngle"] == spec["outer_angle_degrees"]

    vehicle = prefab[TRUCK_NAME]
    assert vehicle["class"] == "BeamNGVehicle"
    assert vehicle["jBeam"] == "pickup"
    assert phase2["vehicle"]["name"] == TRUCK_NAME
    assert vehicle["position"] == phase2["vehicle"]["position"]
    assert "applyClusterVelocityScaleAdd" not in prefab_source

    phase4 = json.loads(PHASE4_MANIFEST_PATH.read_text(encoding="utf-8"))
    wall = prefab[CRASH_WALL_NAME]
    assert phase4["crash_target"]["name"] == CRASH_WALL_NAME
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
    scenario_data = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    assert isinstance(scenario_data, list) and len(scenario_data) == 1
    # BeamNG 0.38 auto-discovers a same-named sibling prefab. Listing that path
    # explicitly makes the legacy scenario loader append it twice.
    assert scenario_data[0]["prefabs"] == []
