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
    # Four tower spinners + overhead roller + two tire scrubbers. The
    # mitter curtain is jbeam cloth on the selector vehicle (v1.22), so it
    # deliberately has no ambient channel.
    if len(animation_ids) != 7 or len(set(animation_ids)) != 7:
        raise RuntimeError(
            f"expected exactly seven top-level spinner animations, found {len(animation_ids)}"
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
    # Torque-derived Collada loaders read sequence flags from an <extra>
    # technique on the clip; ColladaExtension_animation_clip defaults cyclic to
    # false, which froze the rollers after one 2.54 s revolution even while the
    # runtime held playAmbient enabled. The explicit flag keeps the ambient
    # sequence looping for the whole occupancy window.
    clip_lines.extend(
        (
            b"      <extra>",
            b'        <technique profile="Torque">',
            b"          <cyclic>1</cyclic>",
            b"        </technique>",
            b"      </extra>",
            b"    </animation_clip>",
            b"  </library_animation_clips>",
        )
    )
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
LAUNCH_TRIGGER_CENTER = (0.0, 5.4, 2.1)
LAUNCH_TRIGGER_DIMENSIONS = (5.8, 6.7, 4.6)
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
    bevel: float = 0.025,
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
    if bevel > 0.0:
        modifier = obj.modifiers.new("EdgeSoftening", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    return obj


def add_cone(
    name: str,
    location: tuple[float, float, float],
    radius_base: float,
    radius_tip: float,
    depth: float,
    value: bpy.types.Material | None,
    *,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    vertices: int = 14,
) -> bpy.types.Object:
    """Tapered cylinder (frustum) — the profile of a real spray-nozzle tip."""

    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius_base,
        radius2=radius_tip,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = namespaced_object_name(name)
    obj.data.name = f"{obj.name}_mesh"
    assign_material(obj, value)
    return obj


def add_ramp_wedge(
    name: str,
    sign: float,
    value: bpy.types.Material | None,
) -> bpy.types.Object:
    """Portal apron wedge: slab-top height at the floor edge tapering to grade.

    The structural slab stands 0.132 m proud of the placement datum, which
    played as a hard curb hit at both portals (player report). A 1.3 m apron
    keeps the datum and selector cage untouched while cars roll in flush.
    """

    high_y = 9.0 * sign
    toe_y = 10.3 * sign
    top_z = 0.132
    object_name = namespaced_object_name(name)
    vertices = [
        (-3.08, high_y, 0.0),
        (3.08, high_y, 0.0),
        (3.08, high_y, top_z),
        (-3.08, high_y, top_z),
        (-3.08, toe_y, 0.0),
        (3.08, toe_y, 0.0),
    ]
    faces = [(0, 1, 2, 3), (3, 2, 5, 4), (0, 4, 5, 1), (0, 3, 4), (1, 5, 2)]
    mesh = bpy.data.meshes.new(f"{object_name}_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(object_name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    if value is not None:
        assign_material(obj, value)
        add_metric_box_uvs(obj, meters_per_tile=(2.0, 2.0))
    return obj


def cut_rect_openings(
    targets: list[bpy.types.Object],
    openings: list[tuple[tuple[float, float, float], tuple[float, float, float]]],
) -> None:
    """Boolean-subtract shared rectangular openings from each target mesh.

    Any authored modifiers (the wall edge bevel) apply first in stack order,
    then every opening, so the final mesh is fully evaluated. Callers must
    re-author metric UVs afterwards because boolean cut faces carry no
    meaningful coordinates. Openings sit strictly inside each target's
    bounding box, so the evaluated bounds that feed the selector cage are
    unchanged.
    """

    cutters: list[bpy.types.Object] = []
    for index, (center, dimensions) in enumerate(openings):
        bpy.ops.mesh.primitive_cube_add(location=center)
        cutter = bpy.context.object
        cutter.name = f"{targets[0].name}_cutter_{index}"
        cutter.data.name = f"{cutter.name}_mesh"
        cutter.dimensions = dimensions
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        cutter.display_type = "WIRE"
        cutter.hide_render = True
        cutters.append(cutter)
    for target in targets:
        for index, cutter in enumerate(cutters):
            modifier = target.modifiers.new(f"Opening_{index}", "BOOLEAN")
            modifier.operation = "DIFFERENCE"
            modifier.solver = "EXACT"
            modifier.object = cutter
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        for modifier in list(target.modifiers):
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        target.select_set(False)
    for cutter in cutters:
        mesh = cutter.data
        bpy.data.objects.remove(cutter, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


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


def animate_spin(obj: bpy.types.Object, axis: int, direction: float = 1.0) -> None:
    # direction -1 counter-rotates: real wash brushes spin toward the car on
    # both sides (mirrored pairs), and the top roller scrubs against travel.
    obj.rotation_mode = "XYZ"
    obj.rotation_euler[axis] = 0.0
    obj.keyframe_insert(data_path="rotation_euler", index=axis, frame=1)
    obj.rotation_euler[axis] = math.tau * (1.0 if direction >= 0 else -1.0)
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
    sway_phase: int = 0,
    spin_direction: float = 1.0,
) -> None:
    # Off-axis spin pivot: the root sits 0.12 m off the brush's geometric
    # axis (azimuth staggered per tower via sway_phase), and the core and
    # card fan are offset back so they start at the authored position. The
    # single supported ROTATION channel then both spins the fan and
    # orbits the whole tower - the in/out scrub BeamNG's ambient loader
    # cannot express with translation channels (which it ignores) or
    # nested animated empties (which break the Collada export).
    wobble = 0.19
    wobble_angle = (sway_phase % 4) * math.tau / 4.0
    pivot = (
        location[0] + math.cos(wobble_angle) * wobble,
        location[1] + math.sin(wobble_angle) * wobble,
        location[2],
    )
    root = bpy.data.objects.new(namespaced_object_name(f"{name}_Spinner"), None)
    root.empty_display_type = "CIRCLE"
    root.location = pivot
    bpy.context.scene.collection.objects.link(root)
    # Slight static spin-axis tilt (~3.5 deg, azimuth staggered with the
    # orbit): the fan sweeps a shallow cone every revolution, reading as the
    # floppy bristle flutter a rigid rotation cannot fake. Static base
    # rotations ride in the node transform, so the ambient clip still
    # carries exactly one animated channel per spinner.
    tilt = 0.08
    root.rotation_mode = "XYZ"
    root.rotation_euler[0] = math.sin(wobble_angle) * tilt
    root.rotation_euler[1] = math.cos(wobble_angle) * tilt
    core = add_cylinder(f"{name}_Core", location, 0.16, 3.3, steel)
    parent_preserving_world(core, root)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    face_uvs: list[tuple[tuple[float, float], ...]] = []
    half_height = 1.525

    def append_ring(count, inner_radius, outer_radius, ring_half, phase, jitter):
        for index in range(count):
            angle = index * math.tau / count + phase
            cosine, sine = math.cos(angle), math.sin(angle)
            # Deterministic per-card raggedness: radius and edge heights vary
            # so the silhouette is a worn bristle pack, not a perfect pinwheel.
            reach = outer_radius + jitter * math.sin(index * 2.7 + phase * 5.0)
            drop = ring_half - 0.10 * abs(math.sin(index * 1.9 + phase))
            rise = ring_half - 0.06 * abs(math.sin(index * 3.3 + phase * 2.0))
            base = len(vertices)
            vertices.extend(
                (
                    (cosine * inner_radius, sine * inner_radius, -ring_half),
                    (cosine * reach, sine * reach, -drop),
                    (cosine * reach, sine * reach, rise),
                    (cosine * inner_radius, sine * inner_radius, ring_half),
                )
            )
            faces.append((base, base + 1, base + 2, base + 3))
            if index % 2:
                face_uvs.append(((1.0, 0.0), (0.0, 0.0), (0.0, 0.75), (1.0, 0.75)))
            else:
                face_uvs.append(((0.0, 0.0), (1.0, 0.0), (1.0, 0.75), (0.0, 0.75)))

    append_ring(16, 0.18, 0.92, half_height, 0.0, 0.07)
    # Offset inner ring fills the see-through gap between core and card tips.
    append_ring(10, 0.17, 0.55, half_height * 0.9, math.tau / 20.0, 0.04)
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
    card_cluster.location = (location[0] - pivot[0], location[1] - pivot[1], 0.0)
    animate_spin(root, 2, spin_direction)


def add_wheel_scrubber(
    name: str,
    location: tuple[float, float, float],
    side: float,
    cards: bpy.types.Material,
    steel: bpy.types.Material,
) -> None:
    """Small tilted tire brush at wheel height — spins like the towers."""

    root = bpy.data.objects.new(namespaced_object_name(f"{name}_Spinner"), None)
    root.empty_display_type = "CIRCLE"
    root.location = location
    root.rotation_mode = "XYZ"
    # Top leans toward the lane so the bristles meet the tire sidewall.
    root.rotation_euler[1] = -side * 0.24
    bpy.context.scene.collection.objects.link(root)
    # Fat bristle-body core in brush blue: the see-through middle was what
    # made the fan read as loose flat cards (player screenshot).
    core = add_cylinder(f"{name}_Core", location, 0.13, 0.82, cards, vertices=16, bevel=0.0)
    parent_preserving_world(core, root)
    axle = add_cylinder(f"{name}_Axle", location, 0.045, 0.95, steel, vertices=10, bevel=0.0)
    parent_preserving_world(axle, root)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    face_uvs: list[tuple[tuple[float, float], ...]] = []
    for index in range(14):
        angle = index * math.tau / 14.0
        cosine, sine = math.cos(angle), math.sin(angle)
        reach = 0.40 + 0.025 * math.sin(index * 2.7)
        drop = 0.40 - 0.05 * abs(math.sin(index * 1.9))
        base = len(vertices)
        vertices.extend(
            (
                (cosine * 0.13, sine * 0.13, -0.40),
                (cosine * reach, sine * reach, -drop),
                (cosine * reach, sine * reach, 0.36),
                (cosine * 0.13, sine * 0.13, 0.40),
            )
        )
        faces.append((base, base + 1, base + 2, base + 3))
        if index % 2:
            face_uvs.append(((1.0, 0.0), (0.0, 0.0), (0.0, 0.75), (1.0, 0.75)))
        else:
            face_uvs.append(((0.0, 0.0), (1.0, 0.0), (1.0, 0.75), (0.0, 0.75)))
    card_cluster = add_card_mesh(f"{name}_CardFan", location, vertices, faces, cards, face_uvs)
    card_cluster["beamng_card_count"] = len(faces)
    card_cluster.parent = root
    card_cluster.location = (0.0, 0.0, 0.0)
    animate_spin(root, 2, -side)


def add_horizontal_brush(
    location: tuple[float, float, float],
    cards: bpy.types.Material,
    steel: bpy.types.Material,
) -> None:
    # Off-axis pivot 0.05 m below the roller axis: the spin orbit presses
    # the roller down-and-up subtly each revolution (capped so its crown
    # only grazes the ceiling light plane at the top of the orbit).
    pivot = (location[0], location[1], location[2] - 0.09)
    root = bpy.data.objects.new(namespaced_object_name("Brush_Overhead_Spinner"), None)
    root.empty_display_type = "CIRCLE"
    root.location = pivot
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
    half_length = 2.225

    def append_ring(count, inner_radius, outer_radius, ring_half, phase, jitter):
        for index in range(count):
            angle = index * math.tau / count + phase
            cosine, sine = math.cos(angle), math.sin(angle)
            reach = outer_radius + jitter * math.sin(index * 2.7 + phase * 5.0)
            left = ring_half - 0.09 * abs(math.sin(index * 1.9 + phase))
            right = ring_half - 0.09 * abs(math.sin(index * 3.3 + phase * 2.0))
            base = len(vertices)
            vertices.extend(
                (
                    (-ring_half, cosine * inner_radius, sine * inner_radius),
                    (ring_half, cosine * inner_radius, sine * inner_radius),
                    (right, cosine * reach, sine * reach),
                    (-left, cosine * reach, sine * reach),
                )
            )
            faces.append((base, base + 1, base + 2, base + 3))
            # Rotate the atlas relative to the side brushes: its alpha-separated
            # cloth bands become many narrow strips along the shaft, each
            # extending outward radially, instead of long nested sheets.
            if index % 2:
                face_uvs.append(((0.0, 0.75), (0.0, 0.0), (1.0, 0.0), (1.0, 0.75)))
            else:
                face_uvs.append(((0.0, 0.0), (0.0, 0.75), (1.0, 0.75), (1.0, 0.0)))

    append_ring(18, 0.17, 0.68, half_length, 0.0, 0.05)
    append_ring(8, 0.16, 0.42, half_length * 0.94, math.tau / 36.0, 0.03)
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
    card_cluster.location = (0.0, 0.0, location[2] - pivot[2])
    # Counter-scrub: the roller's contact crown moves against vehicle travel.
    animate_spin(root, 0, -1.0)


def add_pipe_arch(
    prefix: str,
    y: float,
    steel: bpy.types.Material,
    nozzle: bpy.types.Material,
) -> None:
    for side in (-1.0, 1.0):
        x = side * 2.72
        side_name = "L" if side < 0 else "R"
        add_cylinder(f"{prefix}_Post_{side_name}", (x, y, 2.3), 0.075, 4.2, steel)
        add_cylinder(
            f"{prefix}_PostFlange_{side_name}",
            (x, y, 0.152),
            0.14,
            0.04,
            steel,
            vertices=16,
            bevel=0.0,
        )
        for z in (1.25, 2.1, 3.0):
            # Real spray-nozzle profile: supply elbow off the post, a colored
            # body, and a tapered tip, ALL collinear along one pitched spray
            # axis (v1.20 laid the centers on a horizontal line while pitching
            # each part - the assembly read visibly off-center/kinked, and the
            # right-side cones pointed upward from a sign slip).
            drop = 0.18  # tan(~10 deg) downward pitch into the lane
            axis = Vector((-side, 0.0, -drop)).normalized()
            pitch_angle = math.asin(drop / math.hypot(1.0, drop))
            # Y-rotation by theta maps the primitive +Z axis to
            # (sin theta, 0, cos theta); -side*(pi/2+pitch) lands exactly on
            # the spray axis for BOTH walls, so the cone needs no flip.
            rotation = (0.0, -side * (math.pi / 2.0 + pitch_angle), 0.0)
            start = Vector((x, y, z))

            def along(distance, start=start, axis=axis):
                point = start + axis * distance
                return (point.x, point.y, point.z)

            add_cylinder(
                f"{prefix}_Elbow_{side_name}_{z}",
                along(0.055),
                0.032,
                0.11,
                steel,
                rotation=rotation,
                vertices=10,
                bevel=0.0,
            )
            jet = add_cylinder(
                f"{prefix}_Jet_{side_name}_{z}",
                along(0.14),
                0.05,
                0.11,
                nozzle,
                rotation=rotation,
                vertices=16,
                bevel=0.0,
            )
            jet["water_jet"] = True
            add_cone(
                f"{prefix}_Tip_{side_name}_{z}",
                along(0.225),
                0.048,
                0.02,
                0.09,
                steel,
                rotation=rotation,
                vertices=14,
            )
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
    # The 2048x1024 signage atlas dedicates its top half to the entrance sign;
    # the bottom half carries the wash-menu board and the exit thank-you strip
    # so one emissive material serves all three displays.
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
        [((0.0, 0.5), (1.0, 0.5), (1.0, 1.0), (0.0, 1.0))],
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
                # v1.23.1: BeamNG 0.39 calibrated lighting - PointLight
                # intensity is physical LUMENS (a dual-tube LED batten).
                "intensity": 8000.0,
                "intensity_unit": "lm",
                "radius": 7.0,
                "cast_shadows": False,
            }
        )
    # Warm-white task fill on the piers between the windows: real express
    # tunnels pair a cool accent row with brighter neutral wall washers so the
    # brushes and vehicles read at night instead of silhouetting.
    for index, (x, y) in enumerate(((-2.7, -4.6), (2.7, -4.6), (-2.7, 4.6), (2.7, 4.6)), start=1):
        anchors.append(
            {
                "name": namespaced_object_name(f"light_anchor_wall_{index:02d}"),
                "role": "tunnel_wall_task_fill",
                "class": "PointLight",
                "local_position": [x, y, 3.9],
                "color": [0.92, 0.96, 1.0],
                "intensity": 4000.0,
                "intensity_unit": "lm",
                "radius": 5.0,
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
                # SpotLight intensity is CANDELAS: ~4000 lm flood over a
                # 48-degree cone (solid angle ~2.1 sr).
                "intensity": 2500.0,
                "intensity_unit": "cd",
                "range": 10.0,
                "inner_angle_degrees": 28.0,
                "outer_angle_degrees": 48.0,
                "cast_shadows": False,
            }
        )
    # The exit mirrors the entrance pair so departing vehicles and the
    # thank-you strip are lit instead of falling into shadow.
    for side_name, x in (("left", -1.9), ("right", 1.9)):
        anchors.append(
            {
                "name": namespaced_object_name(f"light_anchor_exit_{side_name}"),
                "role": "exit_spill",
                "class": "SpotLight",
                "local_position": [x, 8.72, 4.08],
                "local_direction": [0.0, 0.97, -0.24],
                "color": [0.1, 0.64, 1.0],
                "intensity": 2500.0,
                "intensity_unit": "cd",
                "range": 10.0,
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

    # Real punched window openings: boolean-cut through the CMU wall and the
    # brick liner so the bays read from the outside and the inside, then set
    # recessed glass and a stainless surround inside each reveal. The cutters
    # stay inside the wall bounding box, so the selector cage derived from the
    # evaluated wall bounds is untouched, and the simple collision shell stays
    # solid behind the glass.
    window_positions = (-5.8, -2.9, 0.0, 2.9, 5.8)
    window_width, window_height = 2.35, 1.45
    window_z = 2.65
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        wall = bpy.data.objects[
            namespaced_object_name(f"CarWash_Wall_{'Left' if side < 0 else 'Right'}")
        ]
        liner = bpy.data.objects[namespaced_object_name(f"InteriorBrick_{side_name}")]
        cut_rect_openings(
            [wall, liner],
            [
                ((side * 3.24, y, window_z), (0.62, window_width, window_height))
                for y in window_positions
            ],
        )
        add_metric_box_uvs(wall, meters_per_tile=(0.8, 0.4))
        add_metric_box_uvs(liner, meters_per_tile=(1.2, 0.6))
        for y in window_positions:
            add_box(
                f"WindowGlass_{side_name}_{y}",
                (side * 3.25, y, window_z),
                (0.04, window_width - 0.06, window_height - 0.06),
                glass,
                bevel=0.0,
            )
            add_box(
                f"WindowFrame_{side_name}_{y}_Top",
                (side * 3.28, y, window_z + window_height / 2.0 - 0.035),
                (0.10, window_width, 0.07),
                steel,
                bevel=0.0,
            )
            add_box(
                f"WindowFrame_{side_name}_{y}_Bottom",
                (side * 3.28, y, window_z - window_height / 2.0 + 0.035),
                (0.10, window_width, 0.07),
                steel,
                bevel=0.0,
            )
            for jamb_side in (-1.0, 1.0):
                jamb_name = "N" if jamb_side < 0 else "P"
                add_box(
                    f"WindowFrame_{side_name}_{y}_{jamb_name}",
                    (side * 3.28, y + jamb_side * (window_width / 2.0 - 0.035), window_z),
                    (0.10, 0.07, window_height - 0.14),
                    steel,
                    bevel=0.0,
                )
    for side in (-1.0, 1.0):
        x = side * 3.085
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

    # v1.25.5 foundation skirt: the exterior cladding (pilasters, wainscot,
    # portal posts) hangs outside the slab with bottoms ~5-8 cm above the
    # placement datum, showing daylight under the building (player
    # screenshot). A CMU skirt strip runs below the cladding line to 30 cm
    # below grade, with stubs under each portal post pair.
    for side in (-1.0, 1.0):
        add_box(
            f"FoundationSkirt_{'L' if side < 0 else 'R'}",
            (side * 3.485, 0.0, -0.105),
            (0.18, 18.9, 0.45),
            exterior_cmu,
            bevel=0.0,
            metric_uv_meters=(0.8, 0.4),
        )
        for end in (-1.0, 1.0):
            add_box(
                f"FoundationStub_{'L' if side < 0 else 'R'}_{'F' if end < 0 else 'R'}",
                (side * 3.35, end * 9.28, -0.105),
                (0.52, 0.24, 0.45),
                exterior_cmu,
                bevel=0.0,
                metric_uv_meters=(0.8, 0.4),
            )

    # Flush portal aprons: visual concrete wedges plus matching collision
    # wedges folded into the floor colmesh so the ramp actually carries wheels.
    add_ramp_wedge("RampApron_Entrance", -1.0, concrete)
    add_ramp_wedge("RampApron_Exit", 1.0, concrete)

    add_box("Colmesh-1", (0.0, 0.0, 0.06), (6.8, 18.0, 0.12), None, bevel=0.0)
    add_box("Colmesh-2", (-3.25, 0.0, 2.35), (0.3, 18.0, 4.6), None, bevel=0.0)
    add_box("Colmesh-3", (3.25, 0.0, 2.35), (0.3, 18.0, 4.6), None, bevel=0.0)
    add_box("Colmesh-4", (0.0, 0.0, 4.78), (6.8, 18.0, 0.36), None, bevel=0.0)
    collision_wedges = [
        add_ramp_wedge("ColmeshRamp_Entrance", -1.0, None),
        add_ramp_wedge("ColmeshRamp_Exit", 1.0, None),
    ]
    floor_colmesh = bpy.data.objects["Colmesh-1"]
    floor_colmesh_data_name = floor_colmesh.data.name
    bpy.ops.object.select_all(action="DESELECT")
    for wedge in collision_wedges:
        wedge.select_set(True)
    floor_colmesh.select_set(True)
    bpy.context.view_layer.objects.active = floor_colmesh
    bpy.ops.object.join()
    floor_colmesh.data.name = floor_colmesh_data_name
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
            (-2.10, y, 2.05),
            brush_cards,
            steel,
            sway_phase=index * 2,
            spin_direction=1.0,
        )
        add_vertical_brush(
            f"Brush_Right_{index + 1}",
            (2.10, y, 2.05),
            brush_cards,
            steel,
            sway_phase=index * 2 + 1,
            spin_direction=-1.0,
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

    # --- Interior realism pass (player request 2026-08-01) -----------------

    # Spinning tire scrubbers just inside the entrance, leaning into the
    # wheel line like real tunnel tire brushes. v1.21: each unit hangs off a
    # visible pedestal arm from the wall side (player: "make the scrubbers
    # look more realistic" - they previously floated with a loose motor cap).
    # v1.22.2 coherent drivetrain (player: "disconnected from the structure
    # mechanically"): base plate -> post -> angled arm reaching the AXLE
    # HOUSING that sits ON the spin axis just above the fan, with the motor
    # bolted to the housing. Every piece touches the next; the axle tilt
    # equals the spinner tilt so the brush visibly hangs from its drive.
    for side in (-1.0, 1.0):
        scrub_name = f"WheelScrub_{'L' if side < 0 else 'R'}"
        add_wheel_scrubber(scrub_name, (side * 2.05, -6.7, 0.68), side, brush_cards, steel)
        add_box(
            f"{scrub_name}_Base",
            (side * 2.75, -6.7, 0.157),
            (0.30, 0.34, 0.05),
            steel,
            bevel=0.0,
        )
        add_box(
            f"{scrub_name}_Post",
            (side * 2.75, -6.7, 0.79),
            (0.14, 0.18, 1.26),
            steel,
            bevel=0.0,
        )
        add_box(
            f"{scrub_name}_Arm",
            (side * 2.34, -6.7, 1.28),
            (0.88, 0.12, 0.09),
            steel,
            bevel=0.0,
            rotation=(0.0, -side * 0.174, 0.0),
        )
        add_cylinder(
            f"{scrub_name}_AxleHousing",
            (side * 1.926, -6.7, 1.185),
            0.075,
            0.20,
            steel,
            rotation=(0.0, -side * 0.24, 0.0),
            vertices=16,
            bevel=0.0,
        )
        add_box(
            f"{scrub_name}_Motor",
            (side * 1.883, -6.7, 1.36),
            (0.20, 0.20, 0.15),
            blue_brush,
            bevel=0.02,
            rotation=(0.0, -side * 0.24, 0.0),
        )
        add_box(
            f"{scrub_name}_WallBrace",
            (side * 2.87, -6.7, 1.12),
            (0.22, 0.10, 0.08),
            steel,
            bevel=0.0,
        )
        # Compliance piston on the arm: sleeve, rod, and coil rings - the
        # visible "spring mechanism" that presses the brush toward the lane.
        add_cylinder(
            f"{scrub_name}_PistonSleeve",
            (side * 2.42, -6.7, 1.265),
            0.052,
            0.26,
            steel,
            rotation=(0.0, math.pi / 2.0 - side * 0.174, 0.0),
            vertices=12,
            bevel=0.0,
        )
        add_cylinder(
            f"{scrub_name}_PistonRod",
            (side * 2.20, -6.7, 1.228),
            0.028,
            0.24,
            rubber,
            rotation=(0.0, math.pi / 2.0 - side * 0.174, 0.0),
            vertices=10,
            bevel=0.0,
        )
        for ring_index in range(3):
            offset = 0.05 + ring_index * 0.055
            add_cylinder(
                f"{scrub_name}_Coil_{ring_index}",
                (side * (2.20 - offset * 0.984), -6.7, 1.228 - offset * 0.173),
                0.048,
                0.018,
                steel,
                rotation=(0.0, math.pi / 2.0 - side * 0.174, 0.0),
                vertices=12,
                bevel=0.0,
            )

    # Tower bearing sleeves: static stubs coupling each spinning core's top
    # to its gantry motor housing, so the towers read as driven machines.
    for side in (-1.0, 1.0):
        for tower_index, tower_y in enumerate((-3.0, 1.2), start=1):
            add_cylinder(
                f"TowerBearing_{'L' if side < 0 else 'R'}_{tower_index}",
                (side * 2.28, tower_y, 3.83),
                0.075,
                0.34,
                steel,
                vertices=16,
                bevel=0.0,
            )

    # v1.22: the mitter curtain is now PHYSICS - individual strips built as
    # jbeam cloth lattices on the selector vehicle (see _selector_structure's
    # cloth section) with a flexbody card mesh that drapes over vehicles.
    # Only the support beam remains in the static scenery; the TSStatic
    # visual must not carry ghost strips over the physical ones.
    for beam_index, beam_y in enumerate((-5.30, -4.85, -4.40), start=1):
        add_box(
            f"CurtainBeam_{beam_index}", (0.0, beam_y, 4.38), (5.0, 0.14, 0.12), steel, bevel=0.0
        )
        for rod_x in (-1.8, 1.8):
            add_cylinder(
                f"CurtainRod_{beam_index}_{'L' if rod_x < 0 else 'R'}",
                (rod_x, beam_y, 4.51),
                0.03,
                0.18,
                steel,
                vertices=10,
                bevel=0.0,
            )
    add_box("CurtainRail_L", (-2.35, -4.85, 4.38), (0.12, 1.10, 0.12), steel, bevel=0.0)
    add_box("CurtainRail_R", (2.35, -4.85, 4.38), (0.12, 1.10, 0.12), steel, bevel=0.0)

    # Equipment mounting: the brushes no longer float. A ceiling gantry
    # carries the tower spinners, and columns brace the overhead roller.
    gantry_parts = [
        add_box("OverheadCross", (0.0, 4.15, 4.50), (5.44, 0.14, 0.10), steel, bevel=0.0),
    ]
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        gantry_parts.append(
            add_box(
                f"BrushGantry_{side_name}",
                (side * 2.28, -0.9, 4.44),
                (0.14, 6.2, 0.13),
                steel,
                bevel=0.0,
            )
        )
        for y in (-3.0, 1.2):
            gantry_parts.append(
                add_box(
                    f"GantryDrop_{side_name}_{y}",
                    (side * 2.28, y, 4.10),
                    (0.09, 0.09, 0.62),
                    steel,
                    bevel=0.0,
                )
            )
        gantry_parts.append(
            add_box(
                f"OverheadColumn_{side_name}",
                (side * 2.60, 4.15, 4.02),
                (0.12, 0.12, 1.00),
                steel,
                bevel=0.0,
            )
        )
    # v1.28 spring-tension bar assemblies: the visible mechanism that
    # "presses" the contact bands onto passing cars - horizontal piston
    # bars from each tower gantry drop to the band anchors, and two
    # vertical piston bars holding the overhead roller band.
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        for tension_index, tension_y in enumerate((-3.0, 1.2), start=1):
            gantry_parts.append(
                add_cylinder(
                    f"TensionSleeve_{side_name}_{tension_index}",
                    (side * 1.90, tension_y, 2.75),
                    0.05,
                    0.36,
                    steel,
                    rotation=(0.0, math.pi / 2.0, 0.0),
                    vertices=12,
                    bevel=0.0,
                )
            )
            gantry_parts.append(
                add_cylinder(
                    f"TensionRod_{side_name}_{tension_index}",
                    (side * 1.62, tension_y, 2.75),
                    0.028,
                    0.28,
                    steel,
                    rotation=(0.0, math.pi / 2.0, 0.0),
                    vertices=10,
                    bevel=0.0,
                )
            )
            for coil in range(3):
                gantry_parts.append(
                    add_cylinder(
                        f"TensionCoil_{side_name}_{tension_index}_{coil}",
                        (side * (1.74 - coil * 0.07), tension_y, 2.75),
                        0.058,
                        0.02,
                        steel,
                        rotation=(0.0, math.pi / 2.0, 0.0),
                        vertices=12,
                        bevel=0.0,
                    )
                )
            gantry_parts.append(
                add_box(
                    f"TensionMount_{side_name}_{tension_index}",
                    (side * 2.06, tension_y, 2.75),
                    (0.10, 0.16, 0.16),
                    steel,
                    bevel=0.0,
                )
            )
    for bar_x in (-1.2, 1.2):
        bar_name = "L" if bar_x < 0 else "R"
        gantry_parts.append(
            add_cylinder(
                f"RollerTensionSleeve_{bar_name}",
                (bar_x, 4.15, 3.55),
                0.06,
                0.55,
                steel,
                vertices=12,
                bevel=0.0,
            )
        )
        gantry_parts.append(
            add_cylinder(
                f"RollerTensionRod_{bar_name}",
                (bar_x, 4.15, 3.05),
                0.034,
                0.55,
                steel,
                vertices=10,
                bevel=0.0,
            )
        )
        for coil in range(3):
            gantry_parts.append(
                add_cylinder(
                    f"RollerTensionCoil_{bar_name}_{coil}",
                    (bar_x, 4.15, 3.32 - coil * 0.09),
                    0.068,
                    0.02,
                    steel,
                    vertices=12,
                    bevel=0.0,
                )
            )
    for side in (-1.0, 1.0):
        for riser_y in (-3.95, 2.15):
            gantry_parts.append(
                add_box(
                    f"GantryRiser_{'L' if side < 0 else 'R'}_{riser_y}",
                    (side * 2.28, riser_y, 4.53),
                    (0.16, 0.16, 0.06),
                    steel,
                    bevel=0.0,
                )
            )
    join_static_meshes("EquipmentGantry", gantry_parts)

    # Exit dryer battery: blower housings with tapered snouts aimed down
    # into the lane where the dryer particle effects already blow.
    add_box("DryerBeam", (0.0, 7.9, 3.85), (5.2, 0.16, 0.16), steel, bevel=0.0)
    dryer_housings = [
        add_box(
            f"DryerHousing_{'L' if side < 0 else 'R'}",
            (side * 1.1, 7.85, 3.42),
            (0.85, 0.60, 0.70),
            deep_blue,
            bevel=0.03,
            rotation=(-0.32, 0.0, 0.0),
        )
        for side in (-1.0, 1.0)
    ]
    join_static_meshes("DryerHousings", dryer_housings)
    for side in (-1.0, 1.0):
        add_box(
            f"DryerIntake_{'L' if side < 0 else 'R'}",
            (side * 1.1, 8.12, 3.52),
            (0.60, 0.04, 0.45),
            rubber,
            bevel=0.0,
            rotation=(-0.32, 0.0, 0.0),
        )
    for side in (-1.0, 1.0):
        add_cone(
            f"DryerSnout_{'L' if side < 0 else 'R'}",
            (side * 1.1, 7.45, 2.98),
            0.24,
            0.15,
            0.5,
            steel,
            rotation=(2.35, 0.0, 0.0),
            vertices=14,
        )

    # Supply plumbing (v1.21 expanded): wall mains feed each arch through a
    # valved drop with a pressure gauge, flexible feed hoses run to the
    # brush motors, and a chemical dosing station stands in the dry zone.
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        add_cylinder(
            f"SupplyMain_{side_name}",
            (side * 2.98, 0.02, 3.62),
            0.055,
            13.4,
            steel,
            rotation=(math.pi / 2.0, 0.0, 0.0),
            vertices=10,
            bevel=0.0,
        )
        for index, y in enumerate((-5.6, 5.65), start=1):
            add_cylinder(
                f"SupplyDrop_{side_name}_{index}",
                (side * 2.9, y, 3.0),
                0.05,
                1.3,
                steel,
                vertices=10,
                bevel=0.0,
            )
            add_cylinder(
                f"SupplyValve_{side_name}_{index}",
                (side * 2.83, y, 2.62),
                0.075,
                0.035,
                cyan,
                rotation=(0.0, math.pi / 2.0, 0.0),
                vertices=12,
                bevel=0.0,
            )
            add_cylinder(
                f"SupplyGauge_{side_name}_{index}",
                (side * 2.845, y + 0.16, 3.42),
                0.045,
                0.04,
                steel,
                rotation=(0.0, math.pi / 2.0, 0.0),
                vertices=10,
                bevel=0.0,
            )
        for index, y in enumerate((-3.0, 1.2), start=1):
            add_cylinder(
                f"BrushFeed_{side_name}_{index}",
                (side * 2.62, y + 0.1, 3.72),
                0.025,
                0.68,
                steel,
                rotation=(0.0, side * 1.35, 0.0),
                vertices=8,
                bevel=0.0,
            )
    for index, tank_material in enumerate((blue_brush, aqua_brush, orange)):
        add_cylinder(
            f"DosingTank_{index}",
            (-2.8, 6.2 + index * 0.34, 0.42),
            0.13,
            0.56,
            tank_material,
            vertices=12,
        )
    add_box("DosingShelf", (-2.8, 6.55, 0.10), (0.44, 1.20, 0.06), steel, bevel=0.0)
    add_cylinder(
        "DosingManifold",
        (-2.8, 6.55, 0.86),
        0.028,
        1.1,
        steel,
        rotation=(math.pi / 2.0, 0.0, 0.0),
        vertices=8,
        bevel=0.0,
    )
    add_cylinder(
        "DosingRiser",
        (-2.85, 6.9, 2.2),
        0.025,
        2.7,
        steel,
        vertices=8,
        bevel=0.0,
    )

    # Stage lighting: glowing wall bars marking each tunnel stage.
    # Stage bars mount on the window PIERS: the old y positions fell inside
    # the punched window openings, so from outside the bars floated in the
    # glass (player screenshot).
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        for index, y in enumerate((-4.35, -1.45, 1.45), start=1):
            add_box(
                f"StageLED_{side_name}_{index}",
                (side * 3.05, y, 2.55),
                (0.035, 0.09, 1.50),
                screen,
                bevel=0.0,
            )
        add_box(
            f"StageLED_{side_name}_dry",
            (side * 3.05, 7.6, 2.55),
            (0.035, 0.09, 1.50),
            light,
            bevel=0.0,
        )

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
        add_box("WheelGuide_L", (-2.48, 0.25, 0.24), (0.13, 15.5, 0.24), steel, bevel=0.0),
        add_box("WheelGuide_R", (2.48, 0.0, 0.24), (0.13, 16.0, 0.24), steel, bevel=0.0),
    ]
    # v1.24: the v1.23 flared entry tapers are gone - rotated about Z
    # they jutted into the lane as stray angled blocks (player report).
    join_static_meshes("WheelGuides", wheel_guides)

    # Recessed trench drains v3. The v1.18 "flush" grates were authored
    # against the placement datum (z 0) and ended up BURIED inside the
    # 0.12 m slab — invisible in-game (player report x3). This version cuts
    # real pockets through the slab top and wet finish, then builds the
    # grate inside the reveal: dark pit floor, bright steel bars 7 mm below
    # the surface, and a thin surface frame. Reads as a real trench drain
    # from driver height, with no collision change (Colmesh-1 stays solid).
    drain_rows = (-6.1, -3.8, -1.5, 0.8, 3.1, 5.4)
    floor = bpy.data.objects[namespaced_object_name("CarWash_Floor")]
    finish = bpy.data.objects[namespaced_object_name("WetFloorFinish")]
    cut_rect_openings(
        [floor, finish],
        [((0.0, y, 0.13), (2.4, 0.36, 0.16)) for y in drain_rows],
    )
    add_metric_box_uvs(floor, meters_per_tile=(2.0, 2.0))
    add_metric_box_uvs(finish, meters_per_tile=(2.0, 2.0))
    drain_bases: list[bpy.types.Object] = []
    drain_slots: list[bpy.types.Object] = []
    for index, y in enumerate(drain_rows):
        drain_bases.append(
            add_box(
                f"Drain_{index:02d}",
                (0.0, y, 0.05),
                (2.398, 0.358, 0.07),
                rubber,
                bevel=0.0,
            )
        )
        for liner_edge in (-1.0, 1.0):
            drain_bases.append(
                add_box(
                    f"Drain_{index:02d}_Liner_{'n' if liner_edge > 0 else 's'}",
                    (0.0, y + liner_edge * 0.174, 0.087),
                    (2.398, 0.012, 0.09),
                    rubber,
                    bevel=0.0,
                )
            )
            drain_bases.append(
                add_box(
                    f"Drain_{index:02d}_LinerCap_{'e' if liner_edge > 0 else 'w'}",
                    (liner_edge * 1.193, y, 0.087),
                    (0.012, 0.358, 0.09),
                    rubber,
                    bevel=0.0,
                )
            )
        for slot in range(-4, 5):
            drain_slots.append(
                add_box(
                    f"Drain_{index:02d}_Bar_{slot:+03d}",
                    (slot * 0.26, y, 0.121),
                    (0.07, 0.34, 0.03),
                    steel,
                    bevel=0.0,
                )
            )
        for edge in (-1.0, 1.0):
            drain_slots.append(
                add_box(
                    f"Drain_{index:02d}_Frame_{'n' if edge > 0 else 's'}",
                    (0.0, y + edge * 0.195, 0.134),
                    (2.46, 0.03, 0.02),
                    steel,
                    bevel=0.0,
                )
            )
            drain_slots.append(
                add_box(
                    f"Drain_{index:02d}_Cap_{'e' if edge > 0 else 'w'}",
                    (edge * 1.245, y, 0.134),
                    (0.03, 0.42, 0.02),
                    steel,
                    bevel=0.0,
                )
            )
    join_static_meshes("DrainBases", drain_bases)
    join_static_meshes("DrainSlots", drain_slots)

    # Exit warning band v2 (player screenshot: the old rotated pads read as
    # scattered diamonds floating off the slab). One thin black base strip
    # sits 5 mm proud of the wet finish with diagonal yellow chevron stripes
    # 8 mm over it - a painted-band look, visually flush from driver height.
    add_box("ExitHazardBase", (0.0, 6.55, 0.1365), (5.8, 0.64, 0.009), rubber, bevel=0.0)
    hazard_stripes = [
        add_box(
            f"ExitHazard_{index:02d}",
            (-2.48 + index * 0.62, 6.55, 0.1445),
            (0.28, 0.82, 0.008),
            yellow,
            bevel=0.0,
            rotation=(0.0, 0.0, -0.785),
        )
        for index in range(9)
    ]
    join_static_meshes("ExitHazardStripes", hazard_stripes)

    # Drive-up pay station v4 (player: "disjointed look, strange blocky
    # placement of items"). v3's additive detailing - three canopy segments
    # at three tilts, a punched-through crown, angled PIN wings, plates at
    # varied depths - read as a jumble. v4 is ONE mass: island -> monolith
    # body -> rounded crown -> single hood, and every control is a thin
    # COPLANAR inset on one dark face panel. Nothing tilts but the hood;
    # total relief stays under 15 mm.
    concrete = material(scenario_material_name("concrete"), (0.18, 0.2, 0.23, 1.0), roughness=0.82)
    add_box("PayKiosk_Island", (-2.65, -8.25, 0.20), (0.60, 1.05, 0.14), concrete, bevel=0.02)
    add_box("PayKiosk_Body", (-2.65, -8.25, 1.075), (0.36, 0.52, 1.55), orange, bevel=0.03)
    add_cylinder(
        "PayKiosk_Crown",
        (-2.65, -8.25, 1.85),
        0.18,
        0.52,
        orange,
        rotation=(math.pi / 2.0, 0.0, 0.0),
        vertices=20,
    )
    add_box(
        "PayKiosk_Hood",
        (-2.52, -8.25, 1.97),
        (0.30, 0.56, 0.03),
        steel,
        bevel=0.01,
        rotation=(0.0, -0.28, 0.0),
    )
    add_box("PayKiosk_FacePanel", (-2.465, -8.25, 1.26), (0.02, 0.42, 1.06), rubber, bevel=0.01)
    add_box("PayKiosk_ScreenBezel", (-2.457, -8.25, 1.60), (0.014, 0.38, 0.30), steel, bevel=0.006)
    add_box("PayKiosk_Screen", (-2.452, -8.25, 1.60), (0.015, 0.34, 0.24), screen, bevel=0.006)
    add_box("PayKiosk_KeypadPlate", (-2.457, -8.31, 1.27), (0.014, 0.26, 0.20), steel, bevel=0.0)
    for row, key_z in enumerate((1.20, 1.245, 1.29, 1.335)):
        for column, key_y in enumerate((-8.40, -8.31, -8.22)):
            add_box(
                f"PayKiosk_Key_{row}{column}",
                (-2.449, key_y, key_z),
                (0.012, 0.05, 0.03),
                rubber,
                bevel=0.0,
            )
    add_box("PayKiosk_TapPad", (-2.455, -8.06, 1.30), (0.016, 0.12, 0.12), cyan, bevel=0.006)
    add_box("PayKiosk_CardSlot", (-2.453, -8.06, 1.16), (0.014, 0.14, 0.03), steel, bevel=0.0)
    add_cylinder(
        "PayKiosk_CoinReturn",
        (-2.454, -8.06, 1.06),
        0.035,
        0.02,
        steel,
        rotation=(0.0, math.pi / 2.0, 0.0),
        vertices=14,
        bevel=0.0,
    )
    add_box("PayKiosk_ReceiptSlot", (-2.454, -8.25, 0.90), (0.014, 0.20, 0.028), steel, bevel=0.0)
    add_cylinder(
        "PayKiosk_Speaker",
        (-2.454, -8.25, 1.44),
        0.05,
        0.018,
        steel,
        rotation=(0.0, math.pi / 2.0, 0.0),
        vertices=16,
        bevel=0.0,
    )
    add_cylinder(
        "PayKiosk_SpeakerInner",
        (-2.448, -8.25, 1.44),
        0.036,
        0.014,
        rubber,
        rotation=(0.0, math.pi / 2.0, 0.0),
        vertices=14,
        bevel=0.0,
    )
    add_box(
        "PayKiosk_IslandStripe",
        (-2.36, -8.25, 0.278),
        (0.04, 1.05, 0.018),
        yellow,
        bevel=0.0,
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
    # Emissive wall-pack fixtures on the window piers give the four warm-white
    # task-fill anchors a visible source.
    for index, (side, y) in enumerate(((-1.0, -4.6), (1.0, -4.6), (-1.0, 4.6), (1.0, 4.6)), 1):
        add_box(
            f"WallPack_{index:02d}",
            (side * 3.03, y, 3.95),
            (0.10, 0.30, 0.12),
            light,
            bevel=0.0,
        )

    exterior_cmu = material(
        scenario_material_name("exterior_cmu"), (0.32, 0.34, 0.36, 1.0), roughness=0.88
    )
    corrugated_blue = material(
        scenario_material_name("corrugated_blue"),
        (0.018, 0.13, 0.34, 1.0),
        metallic=0.0,
        roughness=0.31,
    )

    # Entrance tower: a raised deep-blue fascia carries the cabinet sign above
    # the roofline, replacing the old flat slab-on-header mount. The tower's
    # z-minimum matches the existing header bottom (3.99) so the drivable
    # opening is unchanged, and every part stays outside the building at
    # y <= -9.25.
    add_box("EntranceTowerFascia", (0.0, -9.32, 5.05), (7.30, 0.14, 2.10), deep_blue, bevel=0.02)
    add_box("TowerCopingCap", (0.0, -9.32, 6.13), (7.46, 0.30, 0.06), steel, bevel=0.0)
    add_box("Sign_Cabinet_Body", (0.0, -9.51, 4.90), (5.00, 0.25, 1.36), deep_blue, bevel=0.02)
    add_box("Sign_Retainer_Top", (0.0, -9.652, 5.545), (4.98, 0.085, 0.09), steel, bevel=0.0)
    add_box("Sign_Retainer_Bottom", (0.0, -9.652, 4.255), (4.98, 0.085, 0.09), steel, bevel=0.0)
    add_box("Sign_Retainer_L", (-2.445, -9.652, 4.90), (0.09, 0.085, 1.20), steel, bevel=0.0)
    add_box("Sign_Retainer_R", (2.445, -9.652, 4.90), (0.09, 0.085, 1.20), steel, bevel=0.0)
    # The cannon finial is the brand landmark: a stainless barrel breaking the
    # coping line with a hazard-yellow muzzle ring, aimed along the launch arc.
    add_box("Sign_Cannon_Base", (1.62, -9.51, 5.65), (0.30, 0.26, 0.18), deep_blue, bevel=0.015)
    add_cylinder(
        "Sign_Cannon_Barrel",
        (1.62, -9.74, 6.03),
        0.085,
        0.80,
        steel,
        rotation=(math.radians(35.0), 0.0, 0.0),
        vertices=16,
    )
    add_cylinder(
        "Sign_Cannon_Muzzle",
        (1.62, -9.94, 6.32),
        0.105,
        0.09,
        yellow,
        rotation=(math.radians(35.0), 0.0, 0.0),
        vertices=16,
    )
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        add_cylinder(
            f"SignDownlightCan_{side_name}",
            (side * 1.30, -9.79, 5.78),
            0.07,
            0.20,
            steel,
            rotation=(math.radians(35.0), 0.0, 0.0),
            vertices=8,
        )
        add_box(
            f"DownlightArm_{side_name}",
            (side * 1.30, -9.585, 5.88),
            (0.05, 0.41, 0.05),
            steel,
            bevel=0.0,
        )
    sign = add_sign_face((0.0, -9.639, 4.90), (4.8, 1.2), sign_face)
    sign["uv0_usage"] = "0..1 sign albedo/emissive atlas"
    sign["uv2_usage"] = "0..1 future sign AO"
    # The dual-layer sign atlas owns its letters and emissive halo. Separate
    # converted font meshes duplicated the label and contributed >19k export
    # triangles, so they are deliberately not part of the runtime asset.

    # Parapet band and stainless coping wrap the flat roof edge; LED accent
    # strips tuck under the fascia. Side runs embed into the tower and the
    # exit band so no corner gap opens.
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        add_box(
            f"ParapetFascia_{side_name}",
            (side * 3.46, -0.02, 4.86),
            (0.06, 18.47, 0.62),
            deep_blue,
            bevel=0.0,
        )
        add_box(
            f"CopingCap_{side_name}",
            (side * 3.44, -0.025, 5.195),
            (0.18, 18.51, 0.05),
            steel,
            bevel=0.0,
        )
        add_box(
            f"LEDAccent_{side_name}",
            (side * 3.465, 0.0, 4.515),
            (0.05, 17.80, 0.07),
            light,
            bevel=0.0,
        )
    add_box("ParapetFascia_Exit", (0.0, 9.21, 4.86), (7.04, 0.06, 0.62), deep_blue, bevel=0.0)
    add_box("CopingCap_Exit", (0.0, 9.20, 5.195), (7.10, 0.18, 0.05), steel, bevel=0.0)

    # Facade rhythm: CMU pilasters between the windows, a deep-blue wainscot
    # with a stainless drip cap, and square downspouts near the corners.
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        for index, y in enumerate((-7.6, -4.35, -1.45, 1.45, 4.35, 7.6), start=1):
            add_box(
                f"Pilaster_{side_name}_{index}",
                (side * 3.475, y, 2.305),
                (0.16, 0.50, 4.49),
                exterior_cmu,
                bevel=0.0,
                metric_uv_meters=(0.8, 0.4),
            )
        add_box(
            f"Wainscot_{side_name}",
            (side * 3.42, 0.0, 0.585),
            (0.05, 17.20, 1.05),
            deep_blue,
            bevel=0.0,
        )
        add_box(
            f"WainscotCap_{side_name}",
            (side * 3.43, 0.0, 1.13),
            (0.09, 17.20, 0.04),
            steel,
            bevel=0.0,
        )
        for end_name, y in (("F", -8.4), ("R", 8.4)):
            add_box(
                f"Downspout_{end_name}{side_name}",
                (side * 3.465, y, 2.27),
                (0.09, 0.09, 4.42),
                steel,
                bevel=0.0,
            )

    # Site furniture: clearance bar, menu monument, and bollards signal a
    # commercial express wash while keeping the approach lane |x| <= 3.1 clear.
    # The portal header soffit is the true low point at z 3.99, so the honest
    # clearance bar hangs just below it rather than at the interior 4.48 m
    # clear height.
    add_box("ClearanceBar", (0.0, -11.40, 3.90), (6.90, 0.10, 0.28), yellow, bevel=0.0)
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        add_box(
            f"ClearancePost_{side_name}",
            (side * 3.32, -11.40, 2.38),
            (0.12, 0.12, 4.76),
            steel,
            bevel=0.0,
        )
        add_box(
            f"ClearanceBase_{side_name}",
            (side * 3.32, -11.40, 0.02),
            (0.30, 0.30, 0.04),
            steel,
            bevel=0.0,
        )
    add_box("MenuCabinet", (-4.30, -11.20, 1.45), (1.40, 0.16, 1.90), deep_blue, bevel=0.0)
    add_box("MenuPedestal", (-4.30, -11.20, 0.25), (1.50, 0.45, 0.50), rubber, bevel=0.0)
    # The FIRING TABLE wash menu lives in the signage atlas's bottom-left
    # 416x512 region, sharing the emissive sign_face material so no material
    # slot is added for a second backlit display.
    menu_screen = add_card_mesh(
        "MenuScreen",
        (-4.30, -11.285, 1.45),
        [
            (-0.60, 0.0, -0.75),
            (0.60, 0.0, -0.75),
            (0.60, 0.0, 0.75),
            (-0.60, 0.0, 0.75),
        ],
        [(0, 1, 2, 3)],
        sign_face,
        [((0.0, 0.0), (0.203125, 0.0), (0.203125, 0.5), (0.0, 0.5))],
        alpha_test=False,
    )
    menu_screen["uv0_usage"] = "signage-atlas menu region"
    add_box("MenuTopCap", (-4.30, -11.20, 2.425), (1.50, 0.20, 0.05), steel, bevel=0.0)
    # The entrance-portal pair moved inside to guard the pay kiosk (third
    # coordinate = local floor height: slab-top for interior bollards).
    bollard_positions = (
        (-2.55, -8.95, 0.132),
        (-2.55, -7.55, 0.132),
        (-3.38, 9.80, 0.0),
        (3.38, 9.80, 0.0),
        (-3.65, -10.90, 0.0),
        (-4.95, -10.90, 0.0),
    )
    for index, (x, y, base_z) in enumerate(bollard_positions, start=1):
        add_cylinder(f"Bollard_{index:02d}", (x, y, base_z + 0.50), 0.10, 1.00, orange, vertices=24)
        add_cylinder(
            f"BollardBand_{index:02d}",
            (x, y, base_z + 0.80),
            0.104,
            0.10,
            yellow,
            vertices=24,
            bevel=0.0,
        )
        add_cylinder(
            f"BollardBaseRing_{index:02d}",
            (x, y, base_z + 0.015),
            0.135,
            0.03,
            steel,
            vertices=20,
            bevel=0.0,
        )
    # Threshold stripes sit at the ramp apron toes now that the portals have
    # flush entry wedges (previously they floated where the ramps now stand).
    for end_name, y in (("Entrance", -10.55), ("Exit", 10.55)):
        add_box(
            f"ThresholdStripe_{end_name}",
            (0.0, y, 0.008),
            (6.16, 0.50, 0.016),
            yellow,
            bevel=0.0,
        )

    # Exit accents and interior guard rails. The thank-you strip faces +Y so
    # departing (or airborne) drivers read it; sign_face is single-sided, so
    # the winding is reversed relative to the entrance sign and the U axis is
    # mirrored to keep the text unreflected for a viewer beyond the exit.
    thank_you = add_card_mesh(
        "ThankYouPanel",
        (0.0, 9.26, 4.30),
        [
            (1.60, 0.0, -0.25),
            (-1.60, 0.0, -0.25),
            (-1.60, 0.0, 0.25),
            (1.60, 0.0, 0.25),
        ],
        [(0, 1, 2, 3)],
        sign_face,
        [
            (
                (0.21875, 0.255859375),
                (1.0, 0.255859375),
                (1.0, 0.5),
                (0.21875, 0.5),
            )
        ],
        alpha_test=False,
    )
    thank_you["uv0_usage"] = "signage-atlas thank-you region"
    for side in (-1.0, 1.0):
        side_name = "L" if side < 0 else "R"
        add_box(
            f"ExitBlade_{side_name}",
            (side * 3.625, 9.05, 2.00),
            (0.06, 0.16, 3.50),
            cyan,
            bevel=0.0,
        )
        add_box(
            f"TunnelGuardRail_{side_name}",
            (side * 3.048, 0.0, 0.98),
            (0.05, 16.80, 0.22),
            orange,
            bevel=0.0,
        )

    # Rooftop equipment visible along the launch arc.
    add_box(
        "RoofEquipScreen",
        (1.50, 4.20, 5.36),
        (2.60, 3.40, 0.80),
        corrugated_blue,
        bevel=0.0,
        metric_uv_meters=(1.2, 1.2),
    )
    add_cylinder("RoofVent", (-1.80, 6.50, 5.41), 0.14, 0.90, steel, vertices=14)
    add_box("RoofDuct", (-0.50, 5.60, 5.11), (0.30, 1.20, 0.30), steel, bevel=0.0)

    # Small equipment-wall props: instantly readable realism anchors.
    add_cylinder(
        "FireExtinguisher",
        (3.0, -7.6, 1.05),
        0.085,
        0.52,
        orange,
        vertices=14,
    )
    add_box("FireExtinguisherBracket", (3.045, -7.6, 1.05), (0.05, 0.10, 0.30), steel, bevel=0.0)
    add_cylinder(
        "FireExtinguisherBand",
        (3.0, -7.6, 1.22),
        0.087,
        0.06,
        steel,
        vertices=14,
        bevel=0.0,
    )
    add_cylinder(
        "HoseReel_Drum",
        (3.02, 6.4, 1.45),
        0.24,
        0.16,
        cyan,
        rotation=(0.0, math.pi / 2.0, 0.0),
        vertices=18,
    )
    add_cylinder(
        "HoseReel_Hose",
        (3.02, 6.4, 1.45),
        0.19,
        0.10,
        rubber,
        rotation=(0.0, math.pi / 2.0, 0.0),
        vertices=18,
        bevel=0.0,
    )
    add_box("HoseReel_Mount", (3.06, 6.4, 1.45), (0.06, 0.16, 0.34), steel, bevel=0.0)
    add_box("HoseReel_Guide", (2.94, 6.4, 1.12), (0.05, 0.12, 0.05), steel, bevel=0.0)

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

    # v1.20.1: the ramp aprons must exist in the CAGE, not just the scenario
    # colmesh - a placed selector prop collides through these jbeam triangles,
    # so the v1.20 visual ramps left a 13 cm invisible cliff at both portals
    # (player report: "running into it I seem to warp into it slightly" - the
    # wheel nodes caught the unsupported floor-band edge). Apron stations sit
    # at -1 and 7 so every triangle still spans exactly two adjacent stations
    # and the drive-through portals stay open.
    apron_tracks = ("apron_left", "apron_center", "apron_right")
    apron_x = (left_wall["max"][0], 0.0, right_wall["min"][0])
    ramp_length = 1.3
    apron_specs = (
        ("f", -1, 0, y_min - ramp_length),
        ("r", len(stations), len(stations) - 1, y_max + ramp_length),
    )
    floor_edge_tracks = ("floor_inner_left", "floor_center", "floor_inner_right")
    for end_name, apron_station, portal_station, apron_y in apron_specs:
        for track_index, (track_name, track_x) in enumerate(
            zip(apron_tracks, apron_x, strict=True)
        ):
            identifier = f"{MOD_ID}_apron_{end_name}_t{track_index:02d}"
            source = Vector((track_x, apron_y, floor["min"][2]))
            mapped = rotation @ source
            node_id[(apron_station, track_name)] = identifier
            nodes.append(
                {
                    "id": identifier,
                    "source_object": VEHICLE_CAGE_NAME,
                    "source_vertex_index": len(nodes),
                    "source_world_position": [round(value, 6) for value in source],
                    "position": [round(value, 6) for value in mapped],
                    "station": apron_station,
                    "track": track_name,
                }
            )
        for first_index in range(len(apron_tracks) - 1):
            add_beam(
                node_id[(apron_station, apron_tracks[first_index])],
                node_id[(apron_station, apron_tracks[first_index + 1])],
            )
        for apron_track, floor_track in zip(apron_tracks, floor_edge_tracks, strict=True):
            add_beam(
                node_id[(apron_station, apron_track)],
                node_id[(portal_station, floor_track)],
            )
        for band_index in range(len(apron_tracks) - 1):
            first_apron = node_id[(apron_station, apron_tracks[band_index])]
            second_apron = node_id[(apron_station, apron_tracks[band_index + 1])]
            first_floor = node_id[(portal_station, floor_edge_tracks[band_index])]
            second_floor = node_id[(portal_station, floor_edge_tracks[band_index + 1])]
            add_beam(first_apron, second_floor)
            add_beam(second_apron, first_floor)
            surface = f"ramp_apron_{end_name}"
            triangles.extend(
                (
                    {"nodes": [first_apron, second_apron, first_floor], "surface": surface},
                    {"nodes": [second_apron, second_floor, first_floor], "surface": surface},
                )
            )

    # v1.25.4: chamfered corner guards. The cage walls end at the slab edge
    # (y +/-9) but the visual facade - portal posts, entrance tower, corner
    # brick - extends ~0.4 m further out and forward, so cars buried into
    # the corner visuals before any collision engaged (player report:
    # "vehicle collision is wonky"). Each corner gets a slanted guard plane
    # from the wall end's outer edge to the facade's outer corner - it
    # deflects like a real corner guard. Guard nodes ride the apron
    # stations so every triangle still spans two adjacent stations and the
    # drive-through portals stay open.
    guard_specs = (
        ("f", -1, 0, y_min - 0.42),
        ("r", len(stations), len(stations) - 1, y_max + 0.42),
    )
    for end_name, guard_station, portal_station, guard_y in guard_specs:
        for side_name, floor_track, roof_track, guard_x in (
            ("left", "floor_outer_left", "roof_top_left", floor["min"][0] - 0.22),
            ("right", "floor_outer_right", "roof_top_right", floor["max"][0] + 0.22),
        ):
            bottom_track = f"guard_{side_name}_bottom"
            top_track = f"guard_{side_name}_top"
            for track_label, guard_z in (
                (bottom_track, floor["min"][2]),
                (top_track, roof["max"][2]),
            ):
                identifier = f"{MOD_ID}_guard_{end_name}_{track_label}"
                source = Vector((guard_x, guard_y, guard_z))
                mapped = rotation @ source
                node_id[(guard_station, track_label)] = identifier
                nodes.append(
                    {
                        "id": identifier,
                        "source_object": VEHICLE_CAGE_NAME,
                        "source_vertex_index": len(nodes),
                        "source_world_position": [round(value, 6) for value in source],
                        "position": [round(value, 6) for value in mapped],
                        "station": guard_station,
                        "track": track_label,
                    }
                )
            bottom_id = node_id[(guard_station, bottom_track)]
            top_id = node_id[(guard_station, top_track)]
            wall_bottom = node_id[(portal_station, floor_track)]
            wall_top = node_id[(portal_station, roof_track)]
            # The wall END FACE (its 30 cm cross-section at the portal
            # line) was never capped either - nose-first approaches pushed
            # straight into it. The guard is therefore a full WEDGE: one
            # slanted face from the INNER portal jamb out to the facade
            # corner (a beveled entrance funnel that guides cars in), and
            # one closing the outer corner. Every triangle spans the
            # portal and guard stations.
            inner_track = "floor_inner_left" if side_name == "left" else "floor_inner_right"
            inner_top_track = (
                "wall_top_inner_left" if side_name == "left" else "wall_top_inner_right"
            )
            jamb_bottom = node_id[(portal_station, inner_track)]
            jamb_top = node_id[(portal_station, inner_top_track)]
            add_beam(bottom_id, top_id)
            add_beam(bottom_id, wall_bottom)
            add_beam(top_id, wall_top)
            add_beam(bottom_id, wall_top)
            add_beam(bottom_id, jamb_bottom)
            add_beam(top_id, jamb_top)
            add_beam(bottom_id, jamb_top)
            surface = f"corner_guard_{end_name}_{side_name}"
            triangles.extend(
                (
                    {"nodes": [jamb_bottom, bottom_id, jamb_top], "surface": surface},
                    {"nodes": [bottom_id, top_id, jamb_top], "surface": surface},
                    {"nodes": [wall_bottom, bottom_id, wall_top], "surface": surface},
                    {"nodes": [bottom_id, top_id, wall_top], "surface": surface},
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
    # v1.22 physics mitter curtain: twelve cloth strips as light node/beam
    # lattices. Anchor nodes are FIXED at the support beam; the free nodes
    # below carry collision triangles so the strips drape over and get
    # shoved aside by vehicles - real engine physics instead of an ambient
    # pose. A separate flexbody card mesh (built in the selector export
    # from these exact vehicle-space positions) deforms with the nodes.
    cloth_nodes: list[dict[str, Any]] = []
    cloth_beams: list[dict[str, Any]] = []
    cloth_triangles: list[dict[str, Any]] = []
    cloth_quads: list[dict[str, Any]] = []
    cloth_position: dict[str, list[float]] = {}
    # Hem at 1.0 m: the strips must actually reach vehicles (first cloth
    # probe: a 2.05 m hem cleared an etk800 roof by 60 cm and the curtain
    # never moved). Real mitters drag across the hood and roof.
    # v1.26 contact-brush rows (player request: brushes should softly meet
    # the vehicle): the same lose-every-argument cloth recipe hangs at the
    # second tower pair and at the overhead roller, so cars feel soft
    # bristle contact on the upper body and roof exactly where the
    # spinning visuals are scrubbing. Anchor springs are the "soft spring
    # mechanism"; the spinning-physics ban stands (v1.22 catapult lesson).
    # v1.27 (player): one dense TRIPLE CURTAIN in a ~0.9 m band right
    # after the pre-soak arch instead of rows scattered down the tunnel
    # (mid-tunnel strips read as hanging from air). Staggered hems and
    # strip offsets give layered depth like a real mitter bank.
    # v1.28 brush contact bands (player: "roller brushes should come out
    # to meet the width and height of the car through a gentle tension
    # spring mechanism"): motorized seeking is impossible (ambient clips
    # cannot react to vehicles), but passive SPRING COMPLIANCE is the real
    # mechanism many washes use - the bands rest inside the car envelope
    # and the anchor springs press them against whatever body passes.
    # Side bands hang angled at each tower's inner face; the top band
    # rests at hood height and rides up over the roof.
    brush_band_rows = (
        ("bandl1", -3.0, -1.0),
        ("bandr1", -3.0, 1.0),
        ("bandl2", 1.2, -1.0),
        ("bandr2", 1.2, 1.0),
    )
    cloth_rows = (
        ("mitter", -5.30, 12, 0.42, 0.19, (4.30, 3.25, 2.18, 1.10)),
        ("scrub", -4.85, 10, 0.50, 0.22, (4.30, 3.28, 2.24, 1.20)),
        ("top", -4.40, 12, 0.42, 0.19, (4.30, 3.25, 2.18, 1.10)),
        # Overhead roller contact band: rests at hood height under the
        # spinning top roller and rides up over whatever passes.
        ("roller", 4.15, 10, 0.50, 0.22, (3.70, 2.85, 2.00, 1.15)),
    )
    for row_index, (row_name, row_y, strip_count, spacing, half_width, strip_levels) in enumerate(
        cloth_rows
    ):
        mitter_y = row_y
        row_start_x = -((strip_count - 1) / 2.0) * spacing
        for strip in range(strip_count):
            strip_x = row_start_x + strip * spacing
            strip_ids: dict[tuple[int, int], str] = {}
            for column, x in enumerate((strip_x - half_width, strip_x + half_width)):
                for level, z in enumerate(strip_levels):
                    identifier = f"{MOD_ID}_{row_name}_s{strip:02d}_c{column}_l{level}"
                    source = Vector((x, mitter_y, z))
                    mapped = rotation @ source
                    strip_ids[(column, level)] = identifier
                    cloth_position[identifier] = [round(value, 6) for value in mapped]
                    cloth_nodes.append(
                        {
                            "id": identifier,
                            "position": cloth_position[identifier],
                            "source_world_position": [round(value, 6) for value in source],
                            "fixed": level == 0,
                        }
                    )
            for column in range(2):
                for level in range(3):
                    cloth_beams.append(
                        {
                            "nodes": [strip_ids[(column, level)], strip_ids[(column, level + 1)]],
                            "class": "structural",
                        }
                    )
            for level in range(4):
                cloth_beams.append(
                    {
                        "nodes": [strip_ids[(0, level)], strip_ids[(1, level)]],
                        "class": "anchor" if level == 0 else "structural",
                    }
                )
            for level in range(3):
                cloth_beams.append(
                    {
                        "nodes": [strip_ids[(0, level)], strip_ids[(1, level + 1)]],
                        "class": "shear",
                    }
                )
                cloth_beams.append(
                    {
                        "nodes": [strip_ids[(1, level)], strip_ids[(0, level + 1)]],
                        "class": "shear",
                    }
                )
                first = strip_ids[(0, level)]
                second = strip_ids[(1, level)]
                third = strip_ids[(1, level + 1)]
                fourth = strip_ids[(0, level + 1)]
                cloth_triangles.append({"nodes": [first, second, third], "surface": "mitter"})
                cloth_triangles.append({"nodes": [first, third, fourth], "surface": "mitter"})
                # The strips map into the atlas's dedicated MITTER RIBBON BAND
                # (v 0.765..0.995): continuous lanes tileable along U, so the
                # strip length runs along U with a per-strip offset for
                # variety. The card fringe region tore into floating bands
                # (player screenshot); the ribbon band is solid cloth.
                along_top = (level / 3.0) * 1.5 + strip * 0.13 + row_index * 0.41
                along_bottom = ((level + 1) / 3.0) * 1.5 + strip * 0.13 + row_index * 0.41
                # Window inset from the band edges: mips average across the
                # card/band boundary, so sampling too close ghosts the wavy
                # card fringe into the lanes (player: jagged mid-strip band).
                quad_uvs = [
                    [along_top, 0.79],
                    [along_top, 0.985],
                    [along_bottom, 0.985],
                    [along_bottom, 0.79],
                ]
                cloth_quads.append(
                    {
                        "positions": [
                            cloth_position[first],
                            cloth_position[second],
                            cloth_position[third],
                            cloth_position[fourth],
                        ],
                        "uvs": quad_uvs,
                    }
                )

    band_levels_z = (2.75, 2.00, 1.30, 0.55)
    band_levels_x = (1.55, 1.33, 1.13, 0.95)
    for band_name, band_y, band_side in brush_band_rows:
        for strip in range(3):
            strip_y = band_y + (strip - 1) * 0.25
            strip_ids = {}
            for column, column_y in enumerate((strip_y - 0.12, strip_y + 0.12)):
                for level in range(4):
                    identifier = f"{MOD_ID}_{band_name}_s{strip:02d}_c{column}_l{level}"
                    source = Vector(
                        (band_side * band_levels_x[level], column_y, band_levels_z[level])
                    )
                    mapped = rotation @ source
                    strip_ids[(column, level)] = identifier
                    cloth_position[identifier] = [round(value, 6) for value in mapped]
                    cloth_nodes.append(
                        {
                            "id": identifier,
                            "position": cloth_position[identifier],
                            "source_world_position": [round(value, 6) for value in source],
                            "fixed": level == 0,
                        }
                    )
            for level in range(4):
                cloth_beams.append(
                    {
                        "nodes": [strip_ids[(0, level)], strip_ids[(1, level)]],
                        "class": "structural",
                    }
                )
            for level in range(3):
                for column in range(2):
                    cloth_beams.append(
                        {
                            "nodes": [strip_ids[(column, level)], strip_ids[(column, level + 1)]],
                            "class": "structural",
                        }
                    )
                cloth_beams.append(
                    {
                        "nodes": [strip_ids[(0, level)], strip_ids[(1, level + 1)]],
                        "class": "shear",
                    }
                )
                cloth_beams.append(
                    {
                        "nodes": [strip_ids[(1, level)], strip_ids[(0, level + 1)]],
                        "class": "shear",
                    }
                )
                first = strip_ids[(0, level)]
                second = strip_ids[(1, level)]
                third = strip_ids[(1, level + 1)]
                fourth = strip_ids[(0, level + 1)]
                cloth_triangles.append({"nodes": [first, second, third], "surface": "mitter"})
                cloth_triangles.append({"nodes": [first, third, fourth], "surface": "mitter"})
                along_top = (level / 3.0) * 0.8 + strip * 0.31 + (0.5 if band_side > 0 else 0.1)
                along_bottom = (
                    ((level + 1) / 3.0) * 0.8 + strip * 0.31 + (0.5 if band_side > 0 else 0.1)
                )
                quad_uvs = [
                    [along_top, 0.79],
                    [along_top, 0.985],
                    [along_bottom, 0.985],
                    [along_bottom, 0.79],
                ]
                cloth_quads.append(
                    {
                        "positions": [
                            cloth_position[first],
                            cloth_position[second],
                            cloth_position[third],
                            cloth_position[fourth],
                        ],
                        "uvs": quad_uvs,
                    }
                )

    return {
        "schema": "ericrolph-cannon-car-wash-selector-handoff-v1",
        "asset": {
            "id": MOD_ID,
            "physics_cage": VEHICLE_CAGE_NAME,
            "visual_mesh": VEHICLE_VISUAL_NAME,
            "cloth_mesh": f"{MOD_ID}_MitterStrips",
        },
        "cloth": {
            "group": f"{MOD_ID}_mitter",
            "mesh": f"{MOD_ID}_MitterStrips",
            "material": f"{MOD_ID}_selector_brush_cards",
            "nodes": cloth_nodes,
            "beams": cloth_beams,
            "triangles": cloth_triangles,
            "visual_quads": cloth_quads,
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

    # v1.22: the mitter curtain ships as its OWN mesh in the vehicle DAE so
    # jbeam can bind it as a per-group flexbody that deforms with the cloth
    # nodes. Quad positions come straight from the handoff (already in
    # BeamNG vehicle space), so the strips and the physics lattice are the
    # same geometry by construction.
    cloth = structure["cloth"]
    strips_vertices: list[tuple[float, float, float]] = []
    strips_faces: list[tuple[int, int, int, int]] = []
    strips_uvs: list[tuple[tuple[float, float], ...]] = []
    for quad in cloth["visual_quads"]:
        base = len(strips_vertices)
        strips_vertices.extend(tuple(position) for position in quad["positions"])
        strips_faces.append((base, base + 1, base + 2, base + 3))
        strips_uvs.append(tuple(tuple(uv) for uv in quad["uvs"]))
    strips_mesh = bpy.data.meshes.new(f"{cloth['mesh']}_mesh")
    strips_mesh.from_pydata(strips_vertices, [], strips_faces)
    strips_mesh.update()
    strips = bpy.data.objects.new(cloth["mesh"], strips_mesh)
    temporary_collection.objects.link(strips)
    cards_material = selector_materials.get(f"{MOD_ID}_brush_cards")
    if cards_material is None:
        raise RuntimeError("selector brush_cards material missing for the mitter strips")
    strips_mesh.materials.append(cards_material)
    uv0 = strips_mesh.uv_layers.new(name="UVMap")
    uv2 = strips_mesh.uv_layers.new(name="UVMap_2")
    for polygon, coordinates in zip(strips_mesh.polygons, strips_uvs, strict=True):
        for loop_index, coordinate in zip(polygon.loop_indices, coordinates, strict=True):
            uv0.data[loop_index].uv = coordinate
            uv2.data[loop_index].uv = coordinate
    strips["beamng_alpha_test"] = True

    bpy.ops.object.select_all(action="DESELECT")
    visual.select_set(True)
    strips.select_set(True)
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
    bpy.data.objects.remove(strips, do_unlink=True)
    if strips_mesh.users == 0:
        bpy.data.meshes.remove(strips_mesh)
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
                "vertical_cards_per_brush": 26,
                "overhead_cards": 26,
                "card_layout": "jittered outer ring + offset inner ring",
                "motion": "off-axis orbit + 3.4 deg axis tilt, mirrored pairs counter-rotate",
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
