"""Build the deterministic, Z-up Cannon Car Wash scene used by the BeamNG example mod.

The script is deliberately stageable so an MCP client can validate the Blender scene between
major construction steps. Execute it with globals containing ``STAGE`` and optional output paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import bpy
from mathutils import Matrix, Vector

STAGE = str(globals().get("STAGE", os.environ.get("CANNON_CAR_WASH_STAGE", "all")))
SCRIPT_PATH = Path(str(globals().get("SCRIPT_PATH", __file__))).resolve()
EXAMPLE_ROOT = SCRIPT_PATH.parents[1]
MOD_ROOT = Path(str(globals().get("MOD_ROOT", EXAMPLE_ROOT / "mod"))).resolve()
MOD_ID = "ericrolph_cannon_car_wash"
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"
BLEND_PATH = Path(
    str(globals().get("BLEND_PATH", EXAMPLE_ROOT / "blender" / "cannon_car_wash.blend"))
).resolve()
ASSET_DIRECTORY = MOD_ROOT / "art" / "shapes" / MOD_ID
DAE_PATH = ASSET_DIRECTORY / f"{MOD_ID}.dae"
MANIFEST_PATH = AUTHORING_ROOT / f"{MOD_ID}.geometry.json"
VEHICLE_DIRECTORY = MOD_ROOT / "vehicles" / MOD_ID
VEHICLE_DAE_PATH = VEHICLE_DIRECTORY / f"{MOD_ID}.dae"
VEHICLE_HANDOFF_PATH = AUTHORING_ROOT / f"{MOD_ID}.selector_handoff.json"
VEHICLE_VISUAL_NAME = f"{MOD_ID}_selector_visual"
VEHICLE_CAGE_NAME = f"{MOD_ID}_selector_cage"
SCENARIO_VISUAL_NAME = f"{MOD_ID}_scenario_visual"


def add_ambient_animation_clip(path: Path) -> None:
    """Group every exported spinner action into BeamNG's required ambient sequence."""

    payload = path.read_bytes()
    if b'<animation_clip id="ambient" name="ambient"' in payload:
        raise RuntimeError("Collada already contains an ambient animation clip")
    animation_ids = re.findall(rb'^    <animation id="([A-Za-z0-9_.-]+)"', payload, re.MULTILINE)
    if len(animation_ids) != 5 or len(set(animation_ids)) != 5:
        raise RuntimeError(
            f"expected exactly five top-level spinner animations, found {len(animation_ids)}"
        )
    newline = b"\r\n" if b"\r\n" in payload else b"\n"
    clip_lines = [
        b"  <library_animation_clips>",
        b'    <animation_clip id="ambient" name="ambient" start="0" end="2.541667">',
    ]
    clip_lines.extend(
        b'      <instance_animation url="#' + animation_id + b'"/>'
        for animation_id in animation_ids
    )
    clip_lines.extend((b"    </animation_clip>", b"  </library_animation_clips>"))
    clip = newline.join(clip_lines) + newline
    anchor = b"  <library_visual_scenes>"
    if payload.count(anchor) != 1:
        raise RuntimeError("Collada visual-scene anchor is missing or ambiguous")
    path.write_bytes(payload.replace(anchor, clip + anchor, 1))


def collada_export_statistics(path: Path) -> dict[str, int]:
    """Measure rendered topology from the exported file, not Blender source polys."""

    namespace = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
    root = ET.parse(path).getroot()  # noqa: S314 - parses the just-exported owned DAE
    triangles = root.findall(".//c:triangles", namespace)
    poly_lists = root.findall(".//c:polylist", namespace)
    return {
        "triangle_count": sum(int(primitive.get("count", "0")) for primitive in triangles),
        "geometry_count": len(root.findall(".//c:library_geometries/c:geometry", namespace)),
        "primitive_group_count": len(triangles) + len(poly_lists),
        "material_symbol_count": len(
            {
                material.get("symbol")
                for material in root.findall(".//c:instance_material", namespace)
            }
        ),
    }


def namespaced_object_name(name: str) -> str:
    """Return a globally unique DAE/scene object name.

    BeamNG discovers collision helpers by the exact ``Colmesh-N`` convention,
    so those object names stay file-local while their mesh datablocks remain
    globally namespaced.
    """

    if name.startswith(f"{MOD_ID}_"):
        return name
    if name.startswith("Colmesh-"):
        return name
    return f"{MOD_ID}_{name}"


def scenario_material_name(name: str) -> str:
    return f"{MOD_ID}_{name}"


LAUNCH_TRIGGER_NAME = namespaced_object_name("launch_trigger")
WASH_ACTIVATION_TRIGGER_NAME = namespaced_object_name("wash_activation_trigger")
REPAIR_TRIGGER_NAME = namespaced_object_name("repair_trigger")
# BeamNG's live vehicle OOBBs can settle slightly below the road surface. Give
# Contains a measured 20 cm under-floor allowance while keeping the top inside
# the 4.48 m opening. The complete local bounds are X [-2.9, 2.9],
# Y [-8.75, 8.75], and Z [-0.2, 4.4]. Its full-bay 17.5 m span contains the
# measured stock Wentward DT40L city bus with enough hold margin to prevent
# suspension/OOBB motion from generating a false exit during countdown.
LAUNCH_TRIGGER_CENTER = (0.0, 0.0, 2.1)
LAUNCH_TRIGGER_DIMENSIONS = (5.8, 17.5, 4.6)
WASH_ACTIVATION_TRIGGER_CENTER = (0.0, 0.0, 2.2)
WASH_ACTIVATION_TRIGGER_DIMENSIONS = (5.8, 17.5, 4.4)
REPAIR_TRIGGER_CENTER = (0.0, 0.0, 2.1)
REPAIR_TRIGGER_DIMENSIONS = (5.4, 2.2, 4.2)
SUPPORTED_CITYBUS_ENVELOPE = {
    "model": "citybus",
    "configuration": "city",
    "source": "BeamNG.drive 0.38.6 vehicles/citybus/info_city.json BoundingBox",
    "width": 3.11,
    "length": 12.63,
    "height": 2.994,
}
LAUNCH_TARGET_SPEED_KPH = 360.0
TRIGGER_NAMES = {LAUNCH_TRIGGER_NAME, WASH_ACTIVATION_TRIGGER_NAME, REPAIR_TRIGGER_NAME}

PRIMARY_STRUCTURES = (
    namespaced_object_name("CarWash_Floor"),
    namespaced_object_name("CarWash_Wall_Left"),
    namespaced_object_name("CarWash_Wall_Right"),
    namespaced_object_name("CarWash_Roof"),
    LAUNCH_TRIGGER_NAME,
    WASH_ACTIVATION_TRIGGER_NAME,
    REPAIR_TRIGGER_NAME,
)
COLLISION_MESH_NAMES = tuple(namespaced_object_name(f"Colmesh-{index}") for index in range(1, 5))
PORTABLE_FILE_BROWSER_PATH = "//" + "_" * 1021
PORTABLE_ASSET_LIBRARY_PATH = "/" + "_" * 1022


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.45,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    existing = bpy.data.materials.get(name)
    if existing is not None:
        return existing
    result = bpy.data.materials.new(name)
    result.diffuse_color = color
    result.use_nodes = True
    principled = result.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Metallic"].default_value = metallic
        principled.inputs["Roughness"].default_value = roughness
        principled.inputs["Alpha"].default_value = color[3]
        if emission is not None:
            emission_input = principled.inputs.get("Emission Color")
            if emission_input is not None:
                emission_input.default_value = emission
            strength_input = principled.inputs.get("Emission Strength")
            if strength_input is not None:
                strength_input.default_value = emission_strength
    return result


def assign_material(obj: bpy.types.Object, value: bpy.types.Material | None) -> None:
    if value is not None and obj.data is not None and hasattr(obj.data, "materials"):
        obj.data.materials.append(value)


def add_metric_box_uvs(
    obj: bpy.types.Object,
    *,
    meters_per_tile: tuple[float, float],
) -> None:
    """Author deterministic UV0 tiling plus a normalized UV2 grime/AO channel.

    Blender's primitive cube UVs map every face to the full image, which would
    stretch a single CMU block across an 18 m wall.  Dominant-axis box mapping
    keeps texel density stable in meters while the second channel remains a
    normalized 0..1 projection suitable for a future baked grime/AO atlas.
    """

    if obj.type != "MESH":
        raise TypeError(f"metric box UVs require a mesh object: {obj.name}")
    if min(meters_per_tile) <= 0.0:
        raise ValueError("meters_per_tile values must be positive")
    mesh = obj.data
    uv0 = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    uv2 = mesh.uv_layers.get("UVMap_2") or mesh.uv_layers.new(name="UVMap_2")
    coordinates = [vertex.co for vertex in mesh.vertices]
    minimum = [min(co[axis] for co in coordinates) for axis in range(3)]
    maximum = [max(co[axis] for co in coordinates) for axis in range(3)]
    for polygon in mesh.polygons:
        normal_axis = max(range(3), key=lambda axis: abs(polygon.normal[axis]))
        if normal_axis == 0:
            u_axis, v_axis = 1, 2
        elif normal_axis == 1:
            u_axis, v_axis = 0, 2
        else:
            u_axis, v_axis = 0, 1
        u_direction = -1.0 if polygon.normal[normal_axis] < 0.0 else 1.0
        u_extent = max(maximum[u_axis] - minimum[u_axis], 1e-9)
        v_extent = max(maximum[v_axis] - minimum[v_axis], 1e-9)
        for loop_index in polygon.loop_indices:
            coordinate = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv0.data[loop_index].uv = (
                u_direction * coordinate[u_axis] / meters_per_tile[0],
                coordinate[v_axis] / meters_per_tile[1],
            )
            uv2.data[loop_index].uv = (
                (coordinate[u_axis] - minimum[u_axis]) / u_extent,
                (coordinate[v_axis] - minimum[v_axis]) / v_extent,
            )
    obj["uv0_projection"] = "metric dominant-axis box mapping"
    obj["uv0_meters_per_tile"] = list(meters_per_tile)
    obj["uv2_usage"] = "normalized future AO/grime"


def add_box(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    value: bpy.types.Material | None,
    *,
    bevel: float = 0.04,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    metric_uv_meters: tuple[float, float] | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = namespaced_object_name(name)
    mesh_name = f"{MOD_ID}_{name}" if name.startswith("Colmesh-") else obj.name
    obj.data.name = f"{mesh_name}_mesh"
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if metric_uv_meters is not None:
        add_metric_box_uvs(obj, meters_per_tile=metric_uv_meters)
    assign_material(obj, value)
    if bevel > 0.0:
        modifier = obj.modifiers.new("EdgeSoftening", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    return obj


def add_cylinder(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    value: bpy.types.Material | None,
    *,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    vertices: int = 20,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = namespaced_object_name(name)
    obj.data.name = f"{obj.name}_mesh"
    assign_material(obj, value)
    bevel = obj.modifiers.new("EdgeSoftening", "BEVEL")
    bevel.width = 0.025
    bevel.segments = 2
    return obj


def join_static_meshes(name: str, objects: list[bpy.types.Object]) -> bpy.types.Object:
    """Join one-material static details into a single exported submesh."""

    if not objects:
        raise ValueError(f"cannot join an empty static-mesh group: {name}")
    material_layout = tuple(material.name for material in objects[0].data.materials)
    for obj in objects:
        if obj.type != "MESH":
            raise ValueError(f"static join requires meshes: {obj.name}")
        if tuple(material.name for material in obj.data.materials) != material_layout:
            raise ValueError(f"static join material mismatch: {obj.name}")
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        for modifier in list(obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    result = objects[0]
    bpy.context.view_layer.objects.active = result
    bpy.ops.object.join()
    result.name = namespaced_object_name(name)
    result.data.name = f"{result.name}_mesh"
    return result


def consolidate_static_visuals() -> None:
    """Batch unanimated one-material visuals without touching contract objects."""

    protected = set(PRIMARY_STRUCTURES) | set(COLLISION_MESH_NAMES)
    groups: dict[str, list[bpy.types.Object]] = {}
    for obj in list(bpy.context.scene.objects):
        if (
            obj.type != "MESH"
            or obj.name in protected
            or obj.parent is not None
            or obj.animation_data is not None
            or len(obj.data.materials) != 1
            or obj.data.materials[0] is None
        ):
            continue
        material_name = obj.data.materials[0].name
        groups.setdefault(material_name, []).append(obj)
    for material_name, objects in sorted(groups.items()):
        if len(objects) > 1:
            suffix = material_name.removeprefix(f"{MOD_ID}_")
            join_static_meshes(f"StaticBatch_{suffix}", objects)


def parent_preserving_world(child: bpy.types.Object, parent: bpy.types.Object) -> None:
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def animate_spin(obj: bpy.types.Object, axis: int) -> None:
    obj.rotation_mode = "XYZ"
    obj.rotation_euler[axis] = 0.0
    obj.keyframe_insert(data_path="rotation_euler", index=axis, frame=1)
    obj.rotation_euler[axis] = math.tau
    obj.keyframe_insert(data_path="rotation_euler", index=axis, frame=61)
    if obj.animation_data is None or obj.animation_data.action is None:
        return
    for curve in obj.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
        curve.modifiers.new("CYCLES")


def add_card_mesh(
    name: str,
    location: tuple[float, float, float],
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int, int]],
    value: bpy.types.Material,
    face_uvs: list[tuple[tuple[float, float], ...]],
    *,
    alpha_test: bool = True,
) -> bpy.types.Object:
    """Create an explicitly UV-authored alpha-test card cluster."""

    object_name = namespaced_object_name(name)
    mesh = bpy.data.meshes.new(f"{object_name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(object_name, mesh)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    assign_material(obj, value)
    uv0 = mesh.uv_layers.new(name="UVMap")
    uv2 = mesh.uv_layers.new(name="UVMap_2")
    if len(face_uvs) != len(mesh.polygons):
        raise RuntimeError(f"UV face count does not match {object_name}")
    for polygon, coordinates in zip(mesh.polygons, face_uvs, strict=True):
        if len(coordinates) != len(polygon.loop_indices):
            raise RuntimeError(f"UV loop count does not match {object_name}")
        for loop_index, coordinate in zip(polygon.loop_indices, coordinates, strict=True):
            uv0.data[loop_index].uv = coordinate
            uv2.data[loop_index].uv = coordinate
    obj["beamng_alpha_test"] = alpha_test
    if alpha_test:
        obj["beamng_card_strategy"] = "radial star fan"
        obj["uv0_usage"] = "brush card atlas"
        obj["uv2_usage"] = "future per-card AO"
    return obj


def add_vertical_brush(
    name: str,
    location: tuple[float, float, float],
    cards: bpy.types.Material,
    steel: bpy.types.Material,
) -> None:
    root = bpy.data.objects.new(namespaced_object_name(f"{name}_Spinner"), None)
    root.empty_display_type = "CIRCLE"
    root.location = location
    bpy.context.scene.collection.objects.link(root)
    core = add_cylinder(f"{name}_Core", location, 0.16, 3.3, steel)
    parent_preserving_world(core, root)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    face_uvs: list[tuple[tuple[float, float], ...]] = []
    inner_radius = 0.18
    outer_radius = 0.92
    half_height = 1.525
    for index in range(16):
        angle = index * math.tau / 16.0
        cosine, sine = math.cos(angle), math.sin(angle)
        base = len(vertices)
        vertices.extend(
            (
                (cosine * inner_radius, sine * inner_radius, -half_height),
                (cosine * outer_radius, sine * outer_radius, -half_height),
                (cosine * outer_radius, sine * outer_radius, half_height),
                (cosine * inner_radius, sine * inner_radius, half_height),
            )
        )
        faces.append((base, base + 1, base + 2, base + 3))
        # Alternate the atlas direction to break up obvious repeated highlights.
        if index % 2:
            face_uvs.append(((1.0, 0.0), (0.0, 0.0), (0.0, 1.0), (1.0, 1.0)))
        else:
            face_uvs.append(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)))
    card_cluster = add_card_mesh(
        f"{name}_CardFan",
        location,
        vertices,
        faces,
        cards,
        face_uvs,
    )
    card_cluster["beamng_card_count"] = len(faces)
    card_cluster.parent = root
    card_cluster.location = (0.0, 0.0, 0.0)
    animate_spin(root, 2)


def add_horizontal_brush(
    location: tuple[float, float, float],
    cards: bpy.types.Material,
    steel: bpy.types.Material,
) -> None:
    root = bpy.data.objects.new(namespaced_object_name("Brush_Overhead_Spinner"), None)
    root.empty_display_type = "CIRCLE"
    root.location = location
    bpy.context.scene.collection.objects.link(root)
    core = add_cylinder(
        "Brush_Overhead_Core",
        location,
        0.15,
        4.7,
        steel,
        rotation=(0.0, math.pi / 2.0, 0.0),
    )
    parent_preserving_world(core, root)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    face_uvs: list[tuple[tuple[float, float], ...]] = []
    inner_radius = 0.17
    outer_radius = 0.68
    half_length = 2.225
    for index in range(14):
        angle = index * math.tau / 14.0
        cosine, sine = math.cos(angle), math.sin(angle)
        base = len(vertices)
        vertices.extend(
            (
                (-half_length, cosine * inner_radius, sine * inner_radius),
                (half_length, cosine * inner_radius, sine * inner_radius),
                (half_length, cosine * outer_radius, sine * outer_radius),
                (-half_length, cosine * outer_radius, sine * outer_radius),
            )
        )
        faces.append((base, base + 1, base + 2, base + 3))
        # Rotate the atlas relative to the side brushes: its alpha-separated
        # cloth bands become many narrow strips along the shaft, each extending
        # outward radially, instead of long nested sheets spanning the cylinder.
        if index % 2:
            face_uvs.append(((0.0, 1.0), (0.0, 0.0), (1.0, 0.0), (1.0, 1.0)))
        else:
            face_uvs.append(((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)))
    card_cluster = add_card_mesh(
        "Brush_Overhead_CardFan",
        location,
        vertices,
        faces,
        cards,
        face_uvs,
    )
    card_cluster["beamng_card_count"] = len(faces)
    card_cluster.parent = root
    card_cluster.location = (0.0, 0.0, 0.0)
    animate_spin(root, 0)


def add_pipe_arch(
    prefix: str,
    y: float,
    steel: bpy.types.Material,
    nozzle: bpy.types.Material,
) -> None:
    for side in (-1.0, 1.0):
        x = side * 2.72
        add_cylinder(f"{prefix}_Post_{'L' if side < 0 else 'R'}", (x, y, 2.3), 0.075, 4.2, steel)
        for z in (1.25, 2.1, 3.0):
            jet = add_cylinder(
                f"{prefix}_Jet_{'L' if side < 0 else 'R'}_{z}",
                (x - side * 0.1, y, z),
                0.055,
                0.22,
                nozzle,
                rotation=(0.0, math.pi / 2.0, 0.0),
                vertices=12,
            )
            jet["water_jet"] = True
    add_cylinder(
        f"{prefix}_Header",
        (0.0, y, 4.36),
        0.075,
        5.45,
        steel,
        rotation=(0.0, math.pi / 2.0, 0.0),
    )


def wash_effect_specs() -> list[dict[str, Any]]:
    """Return the exact BeamNG particle-node contract for both arches.

    ``ParticleEmitterNode.emitter`` consumes ``ParticleEmitterData`` objects
    (the ``BNGP_*`` names below), not the underlying ``ParticleData`` object.
    BeamNG 0.38.6 does not contain the three user-facing semantic labels, so
    the manifest records both the requested role and its verified stock
    runtime mapping.
    """

    specs: list[dict[str, Any]] = []

    def append_effect(
        *,
        suffix: str,
        side_name: str,
        side: float,
        y: float,
        z: float,
        role: str,
        requested_particle: str,
        emitter: str,
        particle_data: str,
    ) -> None:
        # ParticleEmitterNode emits along local +Z. Rotate that axis inward so
        # every layer follows its matching Blender nozzle. BeamNG serializes
        # rotationMatrix column-by-column; the final triplet is emitted +Z.
        rotation = (
            (0.0, 0.0, -1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0)
            if side < 0
            else (0.0, 0.0, 1.0, 0.0, 1.0, 0.0, -1.0, 0.0, 0.0)
        )
        specs.append(
            {
                "name": namespaced_object_name(suffix),
                "role": role,
                "requested_particle": requested_particle,
                "emitter": emitter,
                "particle_data": particle_data,
                "local_position": [round(-side * 0.1 + side * 2.72, 6), y, z],
                "rotation_matrix": list(rotation),
                "scale": [1.0, 1.0, 1.0],
            }
        )

    for side_name, side in (("L", -1.0), ("R", 1.0)):
        for index, z in enumerate((1.25, 2.1, 3.0), start=1):
            append_effect(
                suffix=f"mister_PreSoak_{side_name}_{index}",
                side_name=side_name,
                side=side,
                y=-5.6,
                z=z,
                role="wash_water",
                requested_particle="BNG_sprinkler",
                emitter="BNGP_sprinkler",
                particle_data="BNG_sprinkler",
            )
            append_effect(
                suffix=f"dryer_Mist_{side_name}_{index}",
                side_name=side_name,
                side=side,
                y=5.65,
                z=z,
                role="dryer_primary",
                requested_particle="BNG_Waterfall_Mist",
                emitter="BNGP_waterfallsteam",
                particle_data="BNG_waterfallsteam",
            )
        append_effect(
            suffix=f"dryer_Steam_{side_name}",
            side_name=side_name,
            side=side,
            y=5.65,
            z=2.1,
            role="dryer_secondary",
            requested_particle="BNG_exhaust_steam",
            emitter="BNGP_34",
            particle_data="BNG_steam_light_exhaust",
        )
        append_effect(
            suffix=f"dryer_Dust_{side_name}",
            side_name=side_name,
            side=side,
            y=5.65,
            z=1.25,
            role="dryer_ambient",
            requested_particle="BNG_Ambient_Dust",
            emitter="BNGP_2",
            particle_data="BNG_dust_light",
        )
    return specs


def add_text_mesh(
    name: str,
    body: str,
    location: tuple[float, float, float],
    value: bpy.types.Material,
    *,
    size: float,
) -> None:
    object_name = namespaced_object_name(name)
    curve = bpy.data.curves.new(f"{object_name}_curve", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.035
    curve.bevel_depth = 0.012
    obj = bpy.data.objects.new(object_name, curve)
    obj.location = location
    obj.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    bpy.context.scene.collection.objects.link(obj)
    assign_material(obj, value)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    obj.select_set(False)


def add_sign_face(
    location: tuple[float, float, float],
    dimensions: tuple[float, float],
    value: bpy.types.Material,
) -> bpy.types.Object:
    """Create the UV-authored emissive sign face behind the channel letters."""

    half_width, half_height = dimensions[0] / 2.0, dimensions[1] / 2.0
    # Winding points toward the entrance (-Y). The BeamNG material is
    # double-sided, but deterministic front-face orientation aids previews.
    return add_card_mesh(
        "EntranceSign_Face",
        location,
        [
            (-half_width, 0.0, -half_height),
            (half_width, 0.0, -half_height),
            (half_width, 0.0, half_height),
            (-half_width, 0.0, half_height),
        ],
        [(0, 1, 2, 3)],
        value,
        [((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))],
        alpha_test=False,
    )


def lighting_specs() -> list[dict[str, Any]]:
    """Return namespaced authoring anchors consumed by BeamNG scene/runtime setup."""

    anchors: list[dict[str, Any]] = []
    for index, y in enumerate((-6.8, -3.4, 0.0, 3.4, 6.8), start=1):
        anchors.append(
            {
                "name": namespaced_object_name(f"light_anchor_tunnel_{index:02d}"),
                "role": "tunnel_fluorescent_fill",
                "class": "PointLight",
                "local_position": [0.0, y, 4.34],
                "color": [0.56, 0.82, 1.0],
                "brightness": 1.25,
                "radius": 4.4,
                "cast_shadows": False,
            }
        )
    for side_name, x in (("left", -1.9), ("right", 1.9)):
        anchors.append(
            {
                "name": namespaced_object_name(f"light_anchor_sign_{side_name}"),
                "role": "entrance_sign_spill",
                "class": "SpotLight",
                "local_position": [x, -8.72, 4.08],
                "local_direction": [0.0, -0.97, -0.24],
                "color": [0.1, 0.64, 1.0],
                "brightness": 1.8,
                "range": 7.5,
                "inner_angle_degrees": 28.0,
                "outer_angle_degrees": 48.0,
                "cast_shadows": False,
            }
        )
    return anchors


def add_light_anchors() -> None:
    for spec in lighting_specs():
        anchor = bpy.data.objects.new(spec["name"], None)
        anchor.empty_display_type = "SPHERE" if spec["class"] == "PointLight" else "CONE"
        anchor.empty_display_size = 0.18
        anchor.location = spec["local_position"]
        for key, value in spec.items():
            if key not in {"name", "local_position"}:
                anchor[f"beamng_{key}"] = value
        bpy.context.scene.collection.objects.link(anchor)


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.actions):
        for datablock in list(datablocks):
            datablocks.remove(datablock)
    scene = bpy.context.scene
    scene.name = namespaced_object_name("scene")
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    # Keep the authoring file portable. Blender persists this setting inside the
    # .blend, so an absolute preview path would disclose the builder's checkout.
    scene.render.filepath = "//cannon_car_wash_preview.png"
    scene.render.use_stamp = False
    scene.frame_start = 1
    # The spinner actions key a full revolution at frame 61. Collada samples
    # through frame_end and writes its last sample into visual_scene, so ending
    # on the equivalent rest pose keeps animated and flattened exports aligned.
    scene.frame_end = 61
    scene["beamng_axis"] = "Z-up, +Y drive direction"
    scene["beamng_asset"] = MOD_ID
    print("CANNON_CAR_WASH_STAGE reset complete")


def build_shell() -> None:
    concrete = material(scenario_material_name("concrete"), (0.18, 0.2, 0.23, 1.0), roughness=0.82)
    exterior_cmu = material(
        scenario_material_name("exterior_cmu"), (0.32, 0.34, 0.36, 1.0), roughness=0.88
    )
    interior_brick = material(
        scenario_material_name("interior_brick"), (0.19, 0.075, 0.045, 1.0), roughness=0.82
    )
    wet_concrete = material(
        scenario_material_name("wet_concrete"), (0.16, 0.18, 0.19, 1.0), roughness=0.24
    )
    corrugated_blue = material(
        scenario_material_name("corrugated_blue"),
        (0.018, 0.13, 0.34, 1.0),
        # Factory paint is dielectric. Exposed-steel chips would require a
        # dedicated metallic mask rather than a uniform metallic factor.
        metallic=0.0,
        roughness=0.31,
    )
    cyan = material(scenario_material_name("cyan_trim"), (0.0, 0.52, 0.83, 1.0), metallic=0.25)
    steel = material(
        scenario_material_name("stainless"), (0.42, 0.46, 0.5, 1.0), metallic=0.9, roughness=0.2
    )
    glass = material(
        scenario_material_name("glass"), (0.03, 0.32, 0.48, 0.38), metallic=0.1, roughness=0.08
    )

    # Keep the source shell and collision bounds unchanged. A thin wet finish
    # sits exactly on the structural slab instead of changing the placement datum.
    add_box(
        "CarWash_Floor",
        (0.0, 0.0, 0.06),
        (6.8, 18.0, 0.12),
        concrete,
        bevel=0.025,
        metric_uv_meters=(2.0, 2.0),
    )
    add_box(
        "WetFloorFinish",
        (0.0, 0.0, 0.126),
        (6.16, 17.7, 0.012),
        wet_concrete,
        bevel=0.0,
        metric_uv_meters=(2.0, 2.0),
    )
    add_box(
        "CarWash_Wall_Left",
        (-3.25, 0.0, 2.35),
        (0.3, 18.0, 4.6),
        exterior_cmu,
        metric_uv_meters=(0.8, 0.4),
    )
    add_box(
        "CarWash_Wall_Right",
        (3.25, 0.0, 2.35),
        (0.3, 18.0, 4.6),
        exterior_cmu,
        metric_uv_meters=(0.8, 0.4),
    )
    add_box(
        "CarWash_Roof",
        (0.0, 0.0, 4.78),
        (6.8, 18.0, 0.36),
        corrugated_blue,
        metric_uv_meters=(1.2, 1.2),
    )

    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        add_box(
            f"InteriorBrick_{side_name}",
            (side * 3.087, 0.0, 2.37),
            (0.025, 17.5, 4.34),
            interior_brick,
            bevel=0.0,
            metric_uv_meters=(1.2, 0.6),
        )
    add_box(
        "CorrugatedCeilingLiner",
        (0.0, 0.0, 4.585),
        (6.15, 17.5, 0.03),
        corrugated_blue,
        bevel=0.0,
        metric_uv_meters=(1.2, 1.2),
    )

    for side in (-1.0, 1.0):
        x = side * 3.085
        for y in (-5.8, -2.9, 0.0, 2.9, 5.8):
            add_box(
                f"Window_{'L' if side < 0 else 'R'}_{y}",
                (x, y, 2.65),
                (0.035, 2.35, 1.45),
                glass,
                bevel=0.015,
            )
        add_box(
            f"LowerTrim_{'L' if side < 0 else 'R'}",
            (x - side * 0.03, 0.0, 0.62),
            (0.08, 17.3, 0.16),
            cyan,
            bevel=0.025,
        )

    for y, label in ((-9.05, "Entrance"), (9.05, "Exit")):
        add_box(
            f"Portal_{label}_Header",
            (0.0, y, 4.3),
            (7.05, 0.35, 0.62),
            corrugated_blue,
            metric_uv_meters=(1.2, 1.2),
        )
        for side in (-1.0, 1.0):
            add_box(
                f"Portal_{label}_{'L' if side < 0 else 'R'}",
                (side * 3.42, y, 2.25),
                (0.34, 0.42, 4.35),
                steel,
            )

    add_box("Colmesh-1", (0.0, 0.0, 0.06), (6.8, 18.0, 0.12), None, bevel=0.0)
    add_box("Colmesh-2", (-3.25, 0.0, 2.35), (0.3, 18.0, 4.6), None, bevel=0.0)
    add_box("Colmesh-3", (3.25, 0.0, 2.35), (0.3, 18.0, 4.6), None, bevel=0.0)
    add_box("Colmesh-4", (0.0, 0.0, 4.78), (6.8, 18.0, 0.36), None, bevel=0.0)
    for name in COLLISION_MESH_NAMES:
        collision = bpy.data.objects[name]
        collision.display_type = "WIRE"
        collision.hide_render = True
        collision["beamng_collision_mesh"] = True
    print("CANNON_CAR_WASH_STAGE shell complete")


def build_details() -> None:
    cyan = material(scenario_material_name("cyan_trim"), (0.0, 0.52, 0.83, 1.0), metallic=0.25)
    deep_blue = material(
        scenario_material_name("deep_blue"), (0.015, 0.09, 0.22, 1.0), metallic=0.15
    )
    blue_brush = material(
        scenario_material_name("brush_blue"), (0.005, 0.2, 0.74, 1.0), roughness=0.72
    )
    aqua_brush = material(
        scenario_material_name("brush_aqua"), (0.0, 0.82, 0.83, 1.0), roughness=0.72
    )
    brush_cards = material(
        scenario_material_name("brush_cards"), (0.005, 0.26, 0.72, 1.0), roughness=0.72
    )
    orange = material(
        scenario_material_name("safety_orange"), (1.0, 0.16, 0.015, 1.0), roughness=0.38
    )
    yellow = material(
        scenario_material_name("hazard_yellow"), (1.0, 0.68, 0.015, 1.0), roughness=0.45
    )
    rubber = material(scenario_material_name("rubber"), (0.012, 0.014, 0.018, 1.0), roughness=0.9)
    steel = material(
        scenario_material_name("stainless"), (0.42, 0.46, 0.5, 1.0), metallic=0.9, roughness=0.2
    )
    screen = material(
        scenario_material_name("screen"),
        (0.005, 0.12, 0.2, 1.0),
        emission=(0.0, 0.55, 1.0, 1.0),
        emission_strength=4.0,
    )
    light = material(
        scenario_material_name("led"),
        (0.75, 0.93, 1.0, 1.0),
        emission=(0.5, 0.9, 1.0, 1.0),
        emission_strength=7.0,
    )
    sign_face = material(
        scenario_material_name("sign_face"),
        (0.008, 0.025, 0.055, 1.0),
        roughness=0.28,
        emission=(0.015, 0.36, 1.0, 1.0),
        emission_strength=4.5,
    )

    for index, y in enumerate((-3.0, 1.2)):
        add_vertical_brush(
            f"Brush_Left_{index + 1}",
            (-2.28, y, 2.05),
            brush_cards,
            steel,
        )
        add_vertical_brush(
            f"Brush_Right_{index + 1}",
            (2.28, y, 2.05),
            brush_cards,
            steel,
        )
        # Compact motor housings keep the original colour accents without
        # assigning extra materials to the alpha-card bristle cluster.
        add_box(
            f"BrushMotor_Left_{index + 1}",
            (-2.28, y, 3.78),
            (0.43, 0.43, 0.26),
            blue_brush if index % 2 == 0 else aqua_brush,
            bevel=0.035,
        )
        add_box(
            f"BrushMotor_Right_{index + 1}",
            (2.28, y, 3.78),
            (0.43, 0.43, 0.26),
            aqua_brush if index % 2 == 0 else blue_brush,
            bevel=0.035,
        )
    add_horizontal_brush((0.0, 4.15, 3.82), brush_cards, steel)

    add_pipe_arch("PreSoakArch", -5.6, steel, orange)
    add_pipe_arch("RinseArch", 5.65, steel, cyan)

    # Wall-hugging electrical details add believable industrial scale while
    # remaining above the brush/vehicle envelope. Eight-sided conduit keeps
    # the silhouette round at a fraction of a production-cylinder budget.
    junction_boxes: list[bpy.types.Object] = []
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        add_cylinder(
            f"ElectricalConduit_{side_name}",
            (side * 3.01, 0.0, 4.18),
            0.035,
            15.8,
            steel,
            rotation=(math.pi / 2.0, 0.0, 0.0),
            vertices=8,
        )
        for index, y in enumerate((-4.6, 0.0, 4.6), start=1):
            junction_boxes.append(
                add_box(
                    f"JunctionBox_{side_name}_{index:02d}",
                    (side * 3.02, y, 3.97),
                    (0.1, 0.34, 0.34),
                    deep_blue,
                    bevel=0.0,
                )
            )
            add_cylinder(
                f"JunctionDrop_{side_name}_{index:02d}",
                (side * 3.015, y, 4.08),
                0.024,
                0.28,
                steel,
                vertices=8,
            )

    join_static_meshes("JunctionBoxes", junction_boxes)

    wheel_guides = [
        add_box(
            f"WheelGuide_{'L' if side < 0 else 'R'}",
            (side * 2.48, 0.0, 0.24),
            (0.13, 16.0, 0.24),
            steel,
            bevel=0.0,
        )
        for side in (-1.0, 1.0)
    ]
    join_static_meshes("WheelGuides", wheel_guides)

    drain_bases: list[bpy.types.Object] = []
    drain_slots: list[bpy.types.Object] = []
    for index, y in enumerate((-6.1, -3.8, -1.5, 0.8, 3.1, 5.4)):
        drain_bases.append(
            add_box(
                f"Drain_{index:02d}",
                (0.0, y, 0.135),
                (2.4, 0.33, 0.04),
                rubber,
                bevel=0.0,
            )
        )
        for slot in range(-5, 6):
            drain_slots.append(
                add_box(
                    f"Drain_{index:02d}_Slot_{slot:+03d}",
                    (slot * 0.2, y, 0.158),
                    (0.09, 0.29, 0.018),
                    steel,
                    bevel=0.0,
                )
            )
    join_static_meshes("DrainBases", drain_bases)
    join_static_meshes("DrainSlots", drain_slots)

    hazard_groups: dict[str, list[bpy.types.Object]] = {"yellow": [], "rubber": []}
    for index, x in enumerate((-2.35, -1.55, -0.75, 0.05, 0.85, 1.65, 2.45)):
        group = "yellow" if index % 2 == 0 else "rubber"
        hazard_groups[group].append(
            add_box(
                f"ExitHazard_{index:02d}",
                (x, 6.55, 0.145),
                (0.56, 0.6, 0.035),
                yellow if group == "yellow" else rubber,
                bevel=0.0,
                rotation=(0.0, 0.0, -0.32),
            )
        )
    join_static_meshes("ExitHazardYellow", hazard_groups["yellow"])
    join_static_meshes("ExitHazardRubber", hazard_groups["rubber"])

    add_box("PayKiosk_Body", (-2.65, -7.0, 1.05), (0.55, 0.75, 1.9), orange)
    add_box("PayKiosk_Screen", (-2.64, -7.39, 1.38), (0.38, 0.035, 0.52), screen, bevel=0.008)
    add_cylinder(
        "PayKiosk_Button",
        (-2.64, -7.42, 0.82),
        0.09,
        0.07,
        cyan,
        rotation=(math.pi / 2.0, 0.0, 0.0),
        vertices=16,
    )

    ceiling_lights = [
        add_box(
            f"CeilingLight_{y}",
            (0.0, y, 4.54),
            (3.1, 0.22, 0.055),
            light,
            bevel=0.0,
        )
        for y in (-6.8, -3.4, 0.0, 3.4, 6.8)
    ]
    join_static_meshes("CeilingLights", ceiling_lights)

    add_box("EntranceSign_Back", (0.0, -9.245, 4.28), (5.15, 0.08, 1.35), rubber, bevel=0.025)
    sign = add_sign_face((0.0, -9.288, 4.28), (4.8, 1.2), sign_face)
    sign["uv0_usage"] = "0..1 sign albedo/emissive atlas"
    sign["uv2_usage"] = "0..1 future sign AO"
    # The dual-layer sign atlas owns its letters and emissive halo. Separate
    # converted font meshes duplicated the label and contributed >19k export
    # triangles, so they are deliberately not part of the runtime asset.
    add_light_anchors()

    trigger_material = material(
        scenario_material_name("trigger_invisible"),
        (1.0, 0.0, 0.0, 0.0),
        roughness=1.0,
    )
    trigger_specs = (
        (
            LAUNCH_TRIGGER_NAME,
            LAUNCH_TRIGGER_CENTER,
            LAUNCH_TRIGGER_DIMENSIONS,
            f"{MOD_ID}_launch",
            "Contains",
        ),
        (
            WASH_ACTIVATION_TRIGGER_NAME,
            WASH_ACTIVATION_TRIGGER_CENTER,
            WASH_ACTIVATION_TRIGGER_DIMENSIONS,
            f"{MOD_ID}_cycle",
            "Overlaps",
        ),
        (
            REPAIR_TRIGGER_NAME,
            REPAIR_TRIGGER_CENTER,
            REPAIR_TRIGGER_DIMENSIONS,
            f"{MOD_ID}_repair",
            "Overlaps",
        ),
    )
    for name, center, dimensions, event, mode in trigger_specs:
        trigger = add_box(name, center, dimensions, trigger_material, bevel=0.0)
        trigger.display_type = "WIRE"
        trigger.show_in_front = True
        trigger.hide_render = True
        trigger["beamng_type"] = "BeamNGTrigger"
        trigger["beamng_collision"] = "None"
        trigger["trigger_event"] = event
        trigger["trigger_mode"] = mode
        trigger["trigger_axis"] = "+Y"
        if name == LAUNCH_TRIGGER_NAME:
            trigger["trigger_target_speed_kph"] = LAUNCH_TARGET_SPEED_KPH
        elif name == REPAIR_TRIGGER_NAME:
            trigger["repair_strategy"] = "RESET_PHYSICS"
    print("CANNON_CAR_WASH_STAGE details complete")


def object_bounds(obj: bpy.types.Object) -> dict[str, Any]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    minimum = [min(point[axis] for point in corners) for axis in range(3)]
    maximum = [max(point[axis] for point in corners) for axis in range(3)]
    return {
        "min": [round(value, 6) for value in minimum],
        "max": [round(value, 6) for value in maximum],
        "corners": [[round(value, 6) for value in point] for point in corners],
    }


def evaluated_object_bounds(obj: bpy.types.Object) -> dict[str, Any]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    corners = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
    minimum = [min(point[axis] for point in corners) for axis in range(3)]
    maximum = [max(point[axis] for point in corners) for axis in range(3)]
    return {
        "min": [round(value, 6) for value in minimum],
        "max": [round(value, 6) for value in maximum],
        "corners": [[round(value, 6) for value in point] for point in corners],
    }


def mesh_statistics(meshes: list[bpy.types.Object] | None = None) -> dict[str, int]:
    if meshes is None:
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    return {
        "objects": len(meshes),
        "vertices": sum(len(obj.data.vertices) for obj in meshes),
        "polygons": sum(len(obj.data.polygons) for obj in meshes),
    }


def save_portable_blend() -> None:
    """Save without persisting author-machine paths in the portable source file."""
    BLEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_preferences = bpy.context.preferences.filepaths
    save_version = file_preferences.save_version
    asset_libraries = list(file_preferences.asset_libraries)
    asset_library_paths = [library.path for library in asset_libraries]
    file_browser_params = [
        area.spaces.active.params
        for screen in bpy.data.screens
        for area in screen.areas
        if area.type == "FILE_BROWSER" and area.spaces.active.params is not None
    ]
    file_browser_directories = [params.directory for params in file_browser_params]
    try:
        file_preferences.save_version = 0
        for library in asset_libraries:
            library.path = PORTABLE_ASSET_LIBRARY_PATH
        for params in file_browser_params:
            params.directory = PORTABLE_FILE_BROWSER_PATH.encode()
        bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH), check_existing=False)
    finally:
        file_preferences.save_version = save_version
        for library, path in zip(asset_libraries, asset_library_paths, strict=True):
            library.path = path
        for params, directory in zip(file_browser_params, file_browser_directories, strict=True):
            params.directory = directory


def _selector_structure() -> dict[str, Any]:
    """Derive the selector JBeam cage from evaluated primary-structure bounds.

    BeamNG vehicle space points forward along -Y. The authored scene drives along
    +Y, so both the cage and selector visual use the same proper 180-degree Z
    rotation. No node coordinate is entered independently of the Blender shell.
    """
    primary = {name: evaluated_object_bounds(bpy.data.objects[name]) for name in PRIMARY_STRUCTURES}
    floor = primary[namespaced_object_name("CarWash_Floor")]
    left_wall = primary[namespaced_object_name("CarWash_Wall_Left")]
    right_wall = primary[namespaced_object_name("CarWash_Wall_Right")]
    roof = primary[namespaced_object_name("CarWash_Roof")]
    y_min, y_max = floor["min"][1], floor["max"][1]
    stations = [y_min + (y_max - y_min) * index / 6.0 for index in range(7)]

    tracks = (
        ("floor_outer_left", floor["min"][0], floor["min"][2]),
        ("floor_inner_left", left_wall["max"][0], floor["max"][2]),
        ("floor_center", 0.0, floor["max"][2]),
        ("floor_inner_right", right_wall["min"][0], floor["max"][2]),
        ("floor_outer_right", floor["max"][0], floor["min"][2]),
        ("wall_top_inner_right", right_wall["min"][0], roof["min"][2]),
        ("roof_top_right", roof["max"][0], roof["max"][2]),
        ("roof_top_center", 0.0, roof["max"][2]),
        ("roof_top_left", roof["min"][0], roof["max"][2]),
        ("wall_top_inner_left", left_wall["max"][0], roof["min"][2]),
        ("roof_bottom_center", 0.0, roof["min"][2]),
    )
    rotation = Matrix.Rotation(math.pi, 4, "Z")
    nodes: list[dict[str, Any]] = []
    node_id: dict[tuple[int, str], str] = {}
    for station_index, source_y in enumerate(stations):
        for track_index, (track_name, source_x, source_z) in enumerate(tracks):
            identifier = f"{MOD_ID}_s{station_index:02d}_t{track_index:02d}"
            source = Vector((source_x, source_y, source_z))
            mapped = rotation @ source
            node_id[(station_index, track_name)] = identifier
            nodes.append(
                {
                    "id": identifier,
                    "source_object": VEHICLE_CAGE_NAME,
                    "source_vertex_index": len(nodes),
                    "source_world_position": [round(value, 6) for value in source],
                    "position": [round(value, 6) for value in mapped],
                    "station": station_index,
                    "track": track_name,
                }
            )

    # A vehicle's spawn position is its reference-node position. Keep the
    # selector datum on the measured underside of the floor so callers can use
    # the actual map-surface Z without a hidden 12 cm compensation. These two
    # points are derived from the evaluated floor minimum and authored station
    # coordinates; they are part of the Blender handoff, never patched into the
    # generated JBeam independently.
    middle_station = len(stations) // 2
    ground_reference_tracks = (
        (middle_station, "ground_reference"),
        (middle_station - 1, "ground_back"),
    )
    for station_index, track_name in ground_reference_tracks:
        source = Vector((0.0, stations[station_index], floor["min"][2]))
        mapped = rotation @ source
        identifier = f"{MOD_ID}_{track_name}"
        node_id[(station_index, track_name)] = identifier
        nodes.append(
            {
                "id": identifier,
                "source_object": VEHICLE_CAGE_NAME,
                "source_vertex_index": len(nodes),
                "source_world_position": [round(value, 6) for value in source],
                "position": [round(value, 6) for value in mapped],
                "station": station_index,
                "track": track_name,
            }
        )

    cross_section_edges = (
        ("floor_outer_left", "floor_inner_left"),
        ("floor_inner_left", "floor_center"),
        ("floor_center", "floor_inner_right"),
        ("floor_inner_right", "floor_outer_right"),
        ("floor_outer_right", "wall_top_inner_right"),
        ("wall_top_inner_right", "roof_top_right"),
        ("roof_top_right", "roof_top_center"),
        ("roof_top_center", "roof_top_left"),
        ("roof_top_left", "wall_top_inner_left"),
        ("wall_top_inner_left", "floor_outer_left"),
        ("floor_outer_right", "roof_top_right"),
        ("roof_top_left", "floor_outer_left"),
        ("floor_inner_right", "wall_top_inner_right"),
        ("wall_top_inner_right", "roof_bottom_center"),
        ("roof_bottom_center", "wall_top_inner_left"),
        ("wall_top_inner_left", "floor_inner_left"),
    )
    surface_bands = (
        ("floor_outer_left", "floor_inner_left", "floor_edge_left"),
        ("floor_inner_left", "floor_center", "floor_left"),
        ("floor_center", "floor_inner_right", "floor_right"),
        ("floor_inner_right", "floor_outer_right", "floor_edge_right"),
        ("floor_outer_right", "roof_top_right", "wall_outer_right"),
        ("floor_inner_right", "wall_top_inner_right", "wall_inner_right"),
        ("roof_top_right", "roof_top_center", "roof_top_right"),
        ("roof_top_center", "roof_top_left", "roof_top_left"),
        ("wall_top_inner_right", "roof_bottom_center", "roof_bottom_right"),
        ("roof_bottom_center", "wall_top_inner_left", "roof_bottom_left"),
        ("wall_top_inner_left", "floor_inner_left", "wall_inner_left"),
        ("roof_top_left", "floor_outer_left", "wall_outer_left"),
    )

    beams: set[tuple[str, str]] = set()

    def add_beam(first: str, second: str) -> None:
        if first != second:
            beams.add(tuple(sorted((first, second))))

    for station_index in range(len(stations)):
        for first_track, second_track in cross_section_edges:
            add_beam(
                node_id[(station_index, first_track)],
                node_id[(station_index, second_track)],
            )
    for station_index in range(len(stations) - 1):
        for track_name, _x, _z in tracks:
            add_beam(
                node_id[(station_index, track_name)],
                node_id[(station_index + 1, track_name)],
            )
        for first_track, second_track, _surface in surface_bands:
            add_beam(
                node_id[(station_index, first_track)],
                node_id[(station_index + 1, second_track)],
            )
            add_beam(
                node_id[(station_index, second_track)],
                node_id[(station_index + 1, first_track)],
            )

    for station_index, track_name in ground_reference_tracks:
        reference_id = node_id[(station_index, track_name)]
        for support_track in ("floor_outer_left", "floor_center", "floor_outer_right"):
            add_beam(reference_id, node_id[(station_index, support_track)])
    add_beam(
        node_id[(middle_station, "ground_reference")],
        node_id[(middle_station - 1, "ground_back")],
    )

    triangles: list[dict[str, Any]] = []
    for station_index in range(len(stations) - 1):
        for first_track, second_track, surface in surface_bands:
            first_now = node_id[(station_index, first_track)]
            second_now = node_id[(station_index, second_track)]
            first_next = node_id[(station_index + 1, first_track)]
            second_next = node_id[(station_index + 1, second_track)]
            triangles.extend(
                (
                    {"nodes": [first_now, second_now, first_next], "surface": surface},
                    {"nodes": [second_now, second_next, first_next], "surface": surface},
                )
            )

    base_nodes = [
        node_id[(station_index, track_name)]
        for station_index in range(len(stations))
        for track_name in ("floor_outer_left", "floor_outer_right")
    ]
    # BeamNG's Vehicle Selector grounds a newly spawned/replaced vehicle from
    # its *collidable* initial-node OOBB.  Keep that placement envelope sparse
    # and outside the drive lane: the eight measured shell corners give the
    # selector a non-degenerate XYZ box without adding collision points around
    # the brushes or the vehicle path.  The JBeam builder consumes this exact
    # Blender-derived list; it never invents an independent placement cage.
    spawn_envelope_nodes = [
        node_id[(station_index, track_name)]
        for station_index in (0, len(stations) - 1)
        for track_name in (
            "floor_outer_left",
            "floor_outer_right",
            "roof_top_left",
            "roof_top_right",
        )
    ]
    refnodes = {
        "ref": node_id[(middle_station, "ground_reference")],
        # Source station 2 maps from Y=-3 to BeamNG's +Y/back direction.
        "back": node_id[(middle_station - 1, "ground_back")],
        # Source -X maps to BeamNG +X/left after the proper Z rotation.
        "left": node_id[(middle_station, "floor_outer_left")],
        "up": node_id[(middle_station, "roof_bottom_center")],
    }
    return {
        "schema": "ericrolph-cannon-car-wash-selector-handoff-v1",
        "asset": {
            "id": MOD_ID,
            "physics_cage": VEHICLE_CAGE_NAME,
            "visual_mesh": VEHICLE_VISUAL_NAME,
        },
        "coordinate_system": {
            "source": "right-handed, meters, Z-up, +Y drive direction",
            "target": "BeamNG vehicle space, meters, Z-up, -Y forward",
            "source_world_to_beamng_vehicle": [
                [-1.0, 0.0, 0.0, 0.0],
                [0.0, -1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
        },
        "source_primary_bounds": primary,
        "stations_source_y": [round(value, 6) for value in stations],
        "nodes": nodes,
        "beams": [list(pair) for pair in sorted(beams)],
        "triangles": triangles,
        "base_nodes": base_nodes,
        "spawn_envelope_nodes": spawn_envelope_nodes,
        "refnodes": refnodes,
    }


def export_vehicle_selector_asset() -> None:
    """Export one multi-material flexbody mesh plus its exact Blender cage evidence."""
    VEHICLE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    previous_frame = scene.frame_current
    scene.frame_set(1)
    bpy.context.view_layer.update()

    old_cage = bpy.data.objects.get(VEHICLE_CAGE_NAME)
    if old_cage is not None:
        old_mesh = old_cage.data
        bpy.data.objects.remove(old_cage, do_unlink=True)
        if old_mesh is not None and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    structure = _selector_structure()
    cage_mesh = bpy.data.meshes.new(f"{VEHICLE_CAGE_NAME}_Mesh")
    cage_mesh.from_pydata(
        [node["position"] for node in structure["nodes"]],
        [
            (
                next(
                    node["source_vertex_index"]
                    for node in structure["nodes"]
                    if node["id"] == first
                ),
                next(
                    node["source_vertex_index"]
                    for node in structure["nodes"]
                    if node["id"] == second
                ),
            )
            for first, second in structure["beams"]
        ],
        [
            tuple(
                next(
                    node["source_vertex_index"]
                    for node in structure["nodes"]
                    if node["id"] == identifier
                )
                for identifier in triangle["nodes"]
            )
            for triangle in structure["triangles"]
        ],
    )
    cage_mesh.update()
    cage = bpy.data.objects.new(VEHICLE_CAGE_NAME, cage_mesh)
    scene.collection.objects.link(cage)
    cage.display_type = "WIRE"
    cage.hide_render = True
    cage.show_in_front = True
    cage["beamng_physics_cage"] = True
    cage["beamng_vehicle_forward"] = "-Y"
    save_portable_blend()

    sources = sorted(
        (
            obj
            for obj in scene.objects
            if obj.type == "MESH"
            and not obj.name.startswith("Colmesh-")
            and obj.name not in TRIGGER_NAMES | {VEHICLE_CAGE_NAME}
        ),
        key=lambda obj: obj.name,
    )
    if not sources:
        raise RuntimeError("No visible meshes are available for the selector prop export")

    temporary_collection = bpy.data.collections.new(f"{MOD_ID}_selector_export")
    scene.collection.children.link(temporary_collection)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    vehicle_rotation = Matrix.Rotation(math.pi, 4, "Z")
    duplicates: list[bpy.types.Object] = []
    selector_materials: dict[str, bpy.types.Material] = {}
    for source in sources:
        evaluated = source.evaluated_get(depsgraph)
        mesh_copy = bpy.data.meshes.new_from_object(
            evaluated,
            preserve_all_data_layers=True,
            depsgraph=depsgraph,
        )
        for material_index, source_material in enumerate(mesh_copy.materials):
            if source_material is None:
                continue
            selector_material = selector_materials.get(source_material.name)
            if selector_material is None:
                selector_material = source_material.copy()
                if not source_material.name.startswith(f"{MOD_ID}_"):
                    raise RuntimeError(
                        f"Scenario material is not namespaced: {source_material.name}"
                    )
                suffix = source_material.name.removeprefix(f"{MOD_ID}_")
                selector_material.name = f"{MOD_ID}_selector_{suffix}"
                selector_materials[source_material.name] = selector_material
            mesh_copy.materials[material_index] = selector_material
        source_suffix = source.name.removeprefix(f"{MOD_ID}_")
        duplicate = bpy.data.objects.new(
            f"{MOD_ID}_selector_export_{source_suffix}",
            mesh_copy,
        )
        duplicate.data.name = f"{duplicate.name}_mesh"
        temporary_collection.objects.link(duplicate)
        duplicate.matrix_world = vehicle_rotation @ source.matrix_world
        duplicates.append(duplicate)

    bpy.ops.object.select_all(action="DESELECT")
    for duplicate in duplicates:
        duplicate.select_set(True)
    bpy.context.view_layer.objects.active = duplicates[0]
    bpy.ops.object.join()
    visual = bpy.context.object
    visual.name = VEHICLE_VISUAL_NAME
    visual.data.name = VEHICLE_VISUAL_NAME
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    visual_bounds = object_bounds(visual)

    bpy.ops.object.select_all(action="DESELECT")
    visual.select_set(True)
    bpy.context.view_layer.objects.active = visual
    result = bpy.ops.wm.collada_export(
        filepath=str(VEHICLE_DAE_PATH),
        check_existing=False,
        selected=True,
        include_children=False,
        include_animations=False,
        include_all_actions=False,
        apply_modifiers=True,
        triangulate=True,
        use_texture_copies=True,
        apply_global_orientation=True,
        export_global_forward_selection="Y",
        export_global_up_selection="Z",
        sort_by_name=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"Vehicle-selector Collada export failed: {result}")

    structure["visual"] = {
        "path": f"vehicles/{MOD_ID}/{MOD_ID}.dae",
        "bounds": visual_bounds,
        "materials": sorted(material.name for material in visual.data.materials if material),
        "sha256": hashlib.sha256(VEHICLE_DAE_PATH.read_bytes()).hexdigest(),
        "size": VEHICLE_DAE_PATH.stat().st_size,
    }
    VEHICLE_HANDOFF_PATH.write_text(
        json.dumps(structure, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    visual_mesh = visual.data
    bpy.data.objects.remove(visual, do_unlink=True)
    if visual_mesh.users == 0:
        bpy.data.meshes.remove(visual_mesh)
    for selector_material in selector_materials.values():
        if selector_material.users == 0:
            bpy.data.materials.remove(selector_material)
    bpy.data.collections.remove(temporary_collection)
    scene.frame_set(previous_frame)
    print(
        "CANNON_CAR_WASH_STAGE vehicle_prop complete",
        json.dumps(
            {
                "dae": str(VEHICLE_DAE_PATH),
                "handoff": str(VEHICLE_HANDOFF_PATH),
                "nodes": len(structure["nodes"]),
                "beams": len(structure["beams"]),
                "triangles": len(structure["triangles"]),
            },
            sort_keys=True,
        ),
    )


def finalize() -> None:
    ASSET_DIRECTORY.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    BLEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Collada writes the current evaluated pose into visual-scene transforms in
    # addition to its animation channels. Keep the scenario and flattened
    # selector exports on the same authored rest frame.
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    consolidate_static_visuals()
    bpy.context.view_layer.update()
    primary = {name: object_bounds(bpy.data.objects[name]) for name in PRIMARY_STRUCTURES}
    manifest_meshes = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "MESH"
        and obj.name not in {VEHICLE_CAGE_NAME, VEHICLE_VISUAL_NAME}
        and not obj.name.startswith(f"{MOD_ID}_selector_export_")
    ]
    visible_meshes = [obj for obj in manifest_meshes if not obj.name.startswith("Colmesh-")]
    all_corners = [
        obj.matrix_world @ Vector(corner) for obj in visible_meshes for corner in obj.bound_box
    ]
    manifest = {
        "asset": MOD_ID,
        "coordinate_system": "right-handed, meters, Z-up",
        "drive_axis": [0.0, 1.0, 0.0],
        "entrance_center": [0.0, -9.0, 0.12],
        "exit_center": [0.0, 9.0, 0.12],
        "truck_envelope": {"width": 2.4, "height": 2.6, "length": 6.2},
        "supported_large_vehicle_envelope": SUPPORTED_CITYBUS_ENVELOPE,
        # Usable height is measured from the 0.12 m floor surface to the 4.60 m
        # roof underside, rather than from the world-space zero datum.
        "clear_opening": {"width": 6.2, "height": 4.48, "length": 18.0},
        "scene_bounds": {
            "min": [round(min(point[axis] for point in all_corners), 6) for axis in range(3)],
            "max": [round(max(point[axis] for point in all_corners), 6) for axis in range(3)],
        },
        "primary_structures": primary,
        "trigger": {
            "name": LAUNCH_TRIGGER_NAME,
            "center": list(LAUNCH_TRIGGER_CENTER),
            "dimensions": list(LAUNCH_TRIGGER_DIMENSIONS),
            "mode": "Contains",
            "events": ["enter", "exit"],
            "target_speed_kph": LAUNCH_TARGET_SPEED_KPH,
        },
        "wash_activation_trigger": {
            "name": WASH_ACTIVATION_TRIGGER_NAME,
            "center": list(WASH_ACTIVATION_TRIGGER_CENTER),
            "dimensions": list(WASH_ACTIVATION_TRIGGER_DIMENSIONS),
            "mode": "Overlaps",
            "events": ["enter", "exit"],
        },
        "repair_trigger": {
            "name": REPAIR_TRIGGER_NAME,
            "center": list(REPAIR_TRIGGER_CENTER),
            "dimensions": list(REPAIR_TRIGGER_DIMENSIONS),
            "mode": "Overlaps",
            "events": ["enter", "exit"],
            "repair_strategy": "RESET_PHYSICS",
        },
        "wash_effects": {
            "roller_visual": SCENARIO_VISUAL_NAME,
            "roller_sequence": "ambient",
            "node_datablock": "lightExampleEmitterNodeData1",
            "requested_to_runtime": {
                "BNG_Waterfall_Mist": "BNGP_waterfallsteam",
                "BNG_exhaust_steam": "BNGP_34",
                "BNG_Ambient_Dust": "BNGP_2",
            },
            "effects": wash_effect_specs(),
        },
        "visual_authoring": {
            "uv0": "metric tile mapping on architectural materials; explicit 0..1 on cards/sign",
            "uv2": "UVMap_2 normalized AO/grime channel",
            "brush_strategy": {
                "material": scenario_material_name("brush_cards"),
                "alpha_mode": "alpha test/clip",
                "vertical_cards_per_brush": 16,
                "overhead_cards": 14,
                "sorting_policy": "no alpha blending",
            },
            "tileable_materials": {
                scenario_material_name("exterior_cmu"): [0.8, 0.4],
                scenario_material_name("interior_brick"): [1.2, 0.6],
                scenario_material_name("wet_concrete"): [2.0, 2.0],
                scenario_material_name("corrugated_blue"): [1.2, 1.2],
            },
        },
        "lighting": {
            "coordinate_space": "Blender local, meters, Z-up",
            "anchors": lighting_specs(),
        },
        "mesh_statistics": mesh_statistics(manifest_meshes),
        "collision_meshes": list(COLLISION_MESH_NAMES),
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    # Blender serializes user asset-library and file-browser paths into a .blend
    # even with --factory-startup. Save through the sanitizing helper so no
    # author-machine paths survive in the checked-in source file.
    save_portable_blend()

    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if (
            obj.type in {"MESH", "EMPTY"}
            and obj.name not in {VEHICLE_CAGE_NAME, VEHICLE_VISUAL_NAME}
            and obj.name not in TRIGGER_NAMES
            and not obj.name.startswith(f"{MOD_ID}_selector_export_")
        ):
            obj.select_set(True)
    result = bpy.ops.wm.collada_export(
        filepath=str(DAE_PATH),
        check_existing=False,
        selected=True,
        include_children=True,
        include_animations=True,
        include_all_actions=True,
        apply_modifiers=True,
        triangulate=True,
        use_texture_copies=True,
        apply_global_orientation=True,
        export_global_forward_selection="Y",
        export_global_up_selection="Z",
        sort_by_name=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"Collada export failed: {result}")
    add_ambient_animation_clip(DAE_PATH)
    manifest["export_statistics"] = collada_export_statistics(DAE_PATH)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "CANNON_CAR_WASH_STAGE finalize complete",
        json.dumps(
            {
                "blend": str(BLEND_PATH),
                "dae": str(DAE_PATH),
                "manifest": str(MANIFEST_PATH),
                "stats": manifest["mesh_statistics"],
                "trigger": manifest["trigger"],
            },
            sort_keys=True,
        ),
    )


if STAGE in {"reset", "all"}:
    reset_scene()
if STAGE in {"shell", "all"}:
    build_shell()
if STAGE in {"details", "all"}:
    build_details()
if STAGE in {"finalize", "all"}:
    finalize()
if STAGE in {"vehicle_prop", "all"}:
    export_vehicle_selector_asset()
