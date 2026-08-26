"""Blender-side helpers for the Giant Props pack generators.

This module is imported *inside* Blender (``bpy`` available). It factors the
Cannon Car Wash authoring idioms into reusable pieces:

- deterministic primitive construction with namespaced object names,
- solid-colour preview materials (the BeamNG PBR authority is the generated
  ``main.materials.json``; Blender materials only carry the same base colour),
- a :class:`CageBuilder` that authors the physics cage from evaluated Blender
  coordinates and never invents a vertex the scene cannot measure,
- Collada exports for the vehicle-frame flexbody visual and for kinematic
  runtime part shapes (authored relative to their pivot),
- the exact-coordinate handoff JSON that the Python-side prop builder
  consumes verbatim.

The canonical frames match the Cannon Car Wash: the scene is authored
right-handed, meters, Z-up with +Y as the drive direction; BeamNG vehicle
space is -Y forward, so the flexbody visual and every cage node are mapped
through the same proper 180-degree Z rotation. Kinematic part shapes stay in
the authored frame because the runtime poses them with the prop's model
rotation (which already contains that flip).
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

HANDOFF_SCHEMA = "ericrolph-giant-props-handoff-v1"
VEHICLE_ROTATION = Matrix.Rotation(math.pi, 4, "Z")


def vehicle_frame(point: Vector | tuple[float, float, float]) -> list[float]:
    """Map an authored world point into BeamNG vehicle space (-Y forward)."""

    mapped = VEHICLE_ROTATION @ Vector(point)
    return [round(value, 6) for value in mapped]


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for collection in (
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.objects,
        bpy.data.curves,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.actions,
    ):
        for block in list(collection):
            collection.remove(block)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.frame_set(1)


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.45,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
    glow_map: bool = False,
    texture: Path | str | None = None,
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
        # Preview-only: wire the generated maps so the Blender thumbnails
        # show the textured look. The BeamNG material JSON remains the
        # in-game authority.
        # 2026-08-13: this used to wire ONLY the colour map, which made the
        # verify renders actively misleading for any material whose look
        # lives in its NORMAL or OPACITY map - the washer's water (scrolled
        # ripple normals) and its suds (a foam-raft alpha mask) both
        # rendered as flat blank sheets here while being fine in game, so
        # round after round of water work could not be judged from a
        # render. Normal and opacity maps are now wired too.
        if texture is not None and Path(texture).is_file():
            tree = result.node_tree
            image_node = tree.nodes.new("ShaderNodeTexImage")
            image_node.image = bpy.data.images.load(str(texture))
            image_node.location = (-350, 200)
            tree.links.new(image_node.outputs["Color"], principled.inputs["Base Color"])
            if str(texture).endswith(".color.png"):
                base = str(texture)[: -len(".color.png")]
                opacity_path = Path(f"{base}_opacity.data.png")
                if opacity_path.is_file():
                    opacity_node = tree.nodes.new("ShaderNodeTexImage")
                    opacity_image = bpy.data.images.load(str(opacity_path))
                    opacity_image.colorspace_settings.name = "Non-Color"
                    opacity_node.image = opacity_image
                    opacity_node.location = (-350, -420)
                    tree.links.new(opacity_node.outputs["Color"], principled.inputs["Alpha"])
                else:
                    tree.links.new(image_node.outputs["Alpha"], principled.inputs["Alpha"])
                normal_path = Path(f"{base}.normal.png")
                if normal_path.is_file():
                    normal_node = tree.nodes.new("ShaderNodeTexImage")
                    normal_image = bpy.data.images.load(str(normal_path))
                    normal_image.colorspace_settings.name = "Non-Color"
                    normal_node.image = normal_image
                    normal_node.location = (-650, -180)
                    normal_map = tree.nodes.new("ShaderNodeNormalMap")
                    normal_map.location = (-350, -180)
                    tree.links.new(normal_node.outputs["Color"], normal_map.inputs["Color"])
                    tree.links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])
                rough_path = Path(f"{base}_roughness.data.png")
                if rough_path.is_file():
                    rough_node = tree.nodes.new("ShaderNodeTexImage")
                    rough_image = bpy.data.images.load(str(rough_path))
                    rough_image.colorspace_settings.name = "Non-Color"
                    rough_node.image = rough_image
                    rough_node.location = (-650, 40)
                    tree.links.new(rough_node.outputs["Color"], principled.inputs["Roughness"])
                # OPT-IN, like every other probe here should have been. A
                # family that emits a _glow map had no branch at all, so an
                # emissive surface rendered as a featureless self-lit slab and
                # the map was entirely unverifiable from a render.
                glow_path = Path(f"{base}_glow.color.png")
                if glow_map and glow_path.is_file():
                    glow_input = principled.inputs.get("Emission Color")
                    if glow_input is not None:
                        glow_node = tree.nodes.new("ShaderNodeTexImage")
                        glow_node.image = bpy.data.images.load(str(glow_path))
                        glow_node.location = (-350, -640)
                        tree.links.new(glow_node.outputs["Color"], glow_input)
    return result


def materials_from_palette(
    spec: Any,
    texture_dir: Path,
    *,
    preview_emission: bool = False,
) -> dict[str, bpy.types.Material]:
    """Build every palette material, textured for preview when maps exist.

    ``preview_emission`` wires an emissive palette entry into the Blender
    preview shader. It is OPT-IN and defaults OFF, and that default is the
    important part: Blender's Collada exporter writes the Principled BSDF's
    emission into ``<emission>``, so turning this on unconditionally changes
    the exported DAE bytes - and therefore the handoff sha256, the build
    serial and the ZIP lock - of the SEVEN other specs in this pack that carry
    an ``emissive`` key, for a preview-only reason the engine never reads.
    Every texture_kit family added in 2026-08 took an opt-in parameter for
    exactly this reason; this is the same discipline applied here.
    """

    materials: dict[str, bpy.types.Material] = {}
    for name, entry in spec.PALETTE.items():
        texture_path = texture_dir / f"{name}.color.png"
        emissive = entry.get("emissive") if preview_emission else None
        materials[name] = material(
            name,
            tuple(entry["color"]),
            metallic=entry.get("metallic", 0.0),
            roughness=entry.get("roughness", 0.45),
            texture=texture_path if "texture" in entry else None,
            glow_map=preview_emission,
            emission=(tuple(emissive) + (1.0,)) if emissive else None,
            emission_strength=(
                float((entry.get("stage") or {}).get("emissiveIntensityNits", 0.0))
                / 400.0
                if emissive
                else 0.0
            ),
        )
    return materials


def add_metric_box_uvs(
    obj: bpy.types.Object,
    *,
    meters_per_tile: tuple[float, float],
) -> None:
    """Deterministic dominant-axis box UVs with stable texel density in meters.

    Blender's primitive cube maps every face to the full image, which would
    stretch one texture tile across a 20 m wall (the Cannon Car Wash "tiny
    blocks" lesson). Metric mapping keeps procedural textures true to their
    authored tile size.
    """

    if obj.type != "MESH":
        raise TypeError(f"metric box UVs require a mesh object: {obj.name}")
    if min(meters_per_tile) <= 0.0:
        raise ValueError("meters_per_tile values must be positive")
    mesh = obj.data
    uv0 = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        normal_axis = max(range(3), key=lambda axis: abs(polygon.normal[axis]))
        if normal_axis == 0:
            u_axis, v_axis = 1, 2
        elif normal_axis == 1:
            u_axis, v_axis = 0, 2
        else:
            u_axis, v_axis = 0, 1
        u_direction = -1.0 if polygon.normal[normal_axis] < 0.0 else 1.0
        for loop_index in polygon.loop_indices:
            coordinate = mesh.vertices[mesh.loops[loop_index].vertex_index].co
            uv0.data[loop_index].uv = (
                u_direction * coordinate[u_axis] / meters_per_tile[0],
                coordinate[v_axis] / meters_per_tile[1],
            )


def scale_uvs(obj: bpy.types.Object, u_scale: float, v_scale: float) -> None:
    """Multiply the default primitive UVs (cylinders/spheres) for tiling."""

    mesh = obj.data
    layer = mesh.uv_layers.active
    if layer is None:
        return
    for loop in layer.data:
        loop.uv = (loop.uv[0] * u_scale, loop.uv[1] * v_scale)


def assign_material(obj: bpy.types.Object, value: bpy.types.Material | None) -> None:
    if value is not None and obj.data is not None and hasattr(obj.data, "materials"):
        obj.data.materials.append(value)


def _finish_primitive(
    obj: bpy.types.Object,
    name: str,
    value: bpy.types.Material | None,
    bevel: float,
) -> bpy.types.Object:
    obj.name = name
    if obj.data is not None:
        obj.data.name = f"{name}_mesh"
    if bevel > 0.0:
        modifier = obj.modifiers.new("Bevel", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        modifier.limit_method = "ANGLE"
    assign_material(obj, value)
    # Smooth-by-angle everywhere: faceted spheres/cylinders read as
    # programmer art. 38 degrees keeps box faces flat while smoothing
    # curved surfaces and bevel transitions.
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(38.0))
    except Exception:
        bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return obj


def add_box(
    name: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    value: bpy.types.Material | None,
    *,
    bevel: float = 0.04,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    metric_uv: tuple[float, float] | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.scale = (dimensions[0] / 2.0, dimensions[1] / 2.0, dimensions[2] / 2.0)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    if metric_uv is not None:
        add_metric_box_uvs(obj, meters_per_tile=metric_uv)
    return _finish_primitive(obj, name, value, bevel)


def add_cylinder(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    depth: float,
    value: bpy.types.Material | None,
    *,
    vertices: int = 24,
    axis: str = "Z",
    bevel: float = 0.0,
    radius_x: float | None = None,
    radius_y: float | None = None,
    metric_uv: tuple[float, float] | None = None,
    open_ended: bool = False,
) -> bpy.types.Object:
    rotation = {
        "Z": (0.0, 0.0, 0.0),
        "X": (0.0, math.pi / 2.0, 0.0),
        "Y": (math.pi / 2.0, 0.0, 0.0),
    }[axis]
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=location,
        rotation=rotation,
        end_fill_type="NOTHING" if open_ended else "NGON",
    )
    obj = bpy.context.object
    if radius_x is not None or radius_y is not None:
        scale_x = (radius_x or radius) / radius
        scale_y = (radius_y or radius) / radius
        if axis == "Z":
            obj.scale = (scale_x, scale_y, 1.0)
        elif axis == "X":
            obj.scale = (1.0, scale_x, scale_y)
        else:
            obj.scale = (scale_x, 1.0, scale_y)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    if metric_uv is not None:
        scale_uvs(
            obj,
            (2.0 * math.pi * radius) / metric_uv[0],
            depth / metric_uv[1],
        )
    return _finish_primitive(obj, name, value, bevel)


def add_cone(
    name: str,
    location: tuple[float, float, float],
    radius_bottom: float,
    radius_top: float,
    depth: float,
    value: bpy.types.Material | None,
    *,
    vertices: int = 24,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bevel: float = 0.0,
    metric_uv: tuple[float, float] | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius_bottom,
        radius2=radius_top,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    if metric_uv is not None:
        # A truncated cone carries the primitive's 0..1 side UV, so ONE tile
        # spans the whole circumference AND the whole slant. Left alone, a
        # 5 m-radius housing lands near 30 px/m beside boxes at ~430 - the
        # Cannon Car Wash "tiny blocks" density cliff, in reverse. U follows
        # the MEAN circumference and V the slant length, so the tile stays
        # roughly square along the taper.
        mean_radius = 0.5 * (radius_bottom + radius_top)
        slant = math.hypot(depth, radius_bottom - radius_top)
        scale_uvs(
            obj,
            (2.0 * math.pi * mean_radius) / metric_uv[0],
            slant / metric_uv[1],
        )
    return _finish_primitive(obj, name, value, bevel)


def add_sphere(
    name: str,
    location: tuple[float, float, float],
    radius: float,
    value: bpy.types.Material | None,
    *,
    segments: int = 24,
    rings: int = 16,
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    bevel: float = 0.0,
    metric_uv: tuple[float, float] | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        radius=radius,
        location=location,
    )
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if metric_uv is not None:
        # U spans the equator, V runs pole to pole (half the circumference).
        # Measured on the AUTHORED radius times the dominant scale, because
        # the transform_apply above has already baked `scale` into the mesh.
        equator = 2.0 * math.pi * radius * max(scale[0], scale[1])
        meridian = math.pi * radius * max(scale[0], scale[1], scale[2])
        scale_uvs(obj, equator / metric_uv[0], meridian / metric_uv[1])
    return _finish_primitive(obj, name, value, bevel)


def add_torus(
    name: str,
    location: tuple[float, float, float],
    major_radius: float,
    minor_radius: float,
    value: bpy.types.Material | None,
    *,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    major_segments: int = 24,
    minor_segments: int = 12,
    bevel: float = 0.0,
    metric_uv: tuple[float, float] | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        location=location,
        rotation=rotation,
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=major_segments,
        minor_segments=minor_segments,
    )
    obj = bpy.context.object
    if metric_uv is not None:
        # U runs the major circumference, V the minor (tube) circumference.
        scale_uvs(
            obj,
            (2.0 * math.pi * major_radius) / metric_uv[0],
            (2.0 * math.pi * minor_radius) / metric_uv[1],
        )
    return _finish_primitive(obj, name, value, bevel)


def cut_openings(target: bpy.types.Object, cutters: list[bpy.types.Object]) -> None:
    """Boolean-difference cutter volumes out of the target, then delete them.

    KNOWN BUG, BEHAVIOUR DELIBERATELY UNCHANGED (round 3, football goal
    post). This applies the BOOLEAN modifiers only. If the target still
    carries the BEVEL modifier `_finish_primitive` leaves pending — i.e.
    any target built by `add_box(bevel=...)` — Blender applies the boolean
    OUT OF ORDER, to the base mesh, and the bevel stays pending. The
    exporters evaluate the depsgraph, so that bevel is then applied to the
    boolean's output, where the EXACT solver's sub-nanometre artifact edges
    clamp its width to zero. The result is full bevel TOPOLOGY at zero
    AREA: no visible chamfer plus a pile of degenerate triangles.

    Measured on the football goal post's flag tab: 514 zero-area triangles
    per side, 0.0% oblique surface area, against a 36.9%-oblique control
    with the same bevel and no boolean.

    THIS IS NOT FIXED HERE BECAUSE THE FIX IS NOT COSMETIC. Applying the
    whole stack in order would re-cut the geometry of every shipped mod
    that booleans a bevelled primitive — `catapult_seesaw` (4 deck boards,
    bevel 0.03), `giant_toaster` (shell, bevel 0.85) and
    `spin_cycle_washer` (body, bevel 0.4) all do — and each of those is
    packaged, hashed and in `spin_cycle_washer`'s case installed. Changing
    them belongs in a round that rebuilds and re-gates them.

    CALLERS: pass targets with `bevel=0.0` and cut the chamfer into the
    mesh AFTER the boolean. `football_goal_post`'s `break_arris()` is the
    worked example.
    """

    for cutter in cutters:
        modifier = target.modifiers.new("Opening", "BOOLEAN")
        modifier.operation = "DIFFERENCE"
        modifier.solver = "EXACT"
        modifier.object = cutter
    bpy.context.view_layer.objects.active = target
    for modifier in [m for m in target.modifiers if m.type == "BOOLEAN"]:
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    for cutter in cutters:
        mesh = cutter.data
        bpy.data.objects.remove(cutter, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def object_bounds(obj: bpy.types.Object) -> dict[str, Any]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return {
        "min": [round(min(point[axis] for point in corners), 6) for axis in range(3)],
        "max": [round(max(point[axis] for point in corners), 6) for axis in range(3)],
    }


def evaluated_object_bounds(obj: bpy.types.Object) -> dict[str, Any]:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        coordinates = [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()
    if not coordinates:
        raise ValueError(f"object has no evaluated vertices: {obj.name}")
    return {
        "min": [round(min(point[axis] for point in coordinates), 6) for axis in range(3)],
        "max": [round(max(point[axis] for point in coordinates), 6) for axis in range(3)],
    }


class CageBuilder:
    """Author the physics cage from measured coordinates.

    Node identifiers are namespaced and stable. Every coordinate passed in is
    an authored/evaluated Blender-world value; the builder maps it into
    vehicle space through the shared proper rotation and never rounds beyond
    six decimals. Beam behaviour is selected by named specs so soft regions
    (bouncy floors, cables) coexist with rigid fixed structure in one
    connected cage.
    """

    RIGID = "rigid"

    def __init__(self, mod_id: str) -> None:
        self.mod_id = mod_id
        self.nodes: list[dict[str, Any]] = []
        self.node_index: dict[str, int] = {}
        self.beams: dict[tuple[str, str], str] = {}
        self.triangles: list[dict[str, Any]] = []
        self.rails: dict[str, dict[str, Any]] = {}
        self.slidenodes: list[dict[str, Any]] = []
        self.beam_specs: dict[str, dict[str, Any]] = {
            self.RIGID: {
                "beamSpring": 15000000.0,
                "beamDamp": 1500.0,
                "beamDeform": "FLT_MAX",
                "beamStrength": "FLT_MAX",
            }
        }
        self.base_nodes: list[str] = []
        self.spawn_envelope_nodes: list[str] = []
        self.refnodes: dict[str, str] = {}

    def define_beam_spec(self, name: str, **values: Any) -> None:
        for key in ("beamSpring", "beamDamp", "beamDeform", "beamStrength"):
            if key not in values:
                raise ValueError(f"beam spec {name} is missing {key}")
        self.beam_specs[name] = dict(values)

    def add_rail(
        self,
        name: str,
        node_ids: list[str] | tuple[str, ...],
        *,
        looped: bool = False,
        capped: bool = True,
    ) -> None:
        """Add an ordered BeamNG rail backed by existing cage nodes."""

        if name in self.rails:
            raise ValueError(f"duplicate rail name: {name}")
        if len(node_ids) < 2 or len(set(node_ids)) != len(node_ids):
            raise ValueError(f"rail {name} needs at least two unique nodes")
        missing = [identifier for identifier in node_ids if identifier not in self.node_index]
        if missing:
            raise ValueError(f"rail {name} references unknown nodes: {missing}")
        if looped and capped:
            raise ValueError(f"looped rail {name} cannot be capped")
        self.rails[name] = {
            "links": list(node_ids),
            "looped": bool(looped),
            "capped": bool(capped),
        }

    def add_slidenode(
        self,
        node_id: str,
        rail_name: str,
        *,
        attached: bool = True,
        fix_to_rail: bool = True,
        tolerance: float = 0.0,
        spring: float = 10_001_000.0,
        strength: float | str = "FLT_MAX",
        cap_strength: float | str = "FLT_MAX",
    ) -> None:
        """Constrain one existing cage node to an authored rail."""

        if node_id not in self.node_index:
            raise ValueError(f"slidenode references unknown node: {node_id}")
        if rail_name not in self.rails:
            raise ValueError(f"slidenode references unknown rail: {rail_name}")
        if tolerance < 0:
            raise ValueError("slidenode tolerance must be non-negative")
        self.slidenodes.append(
            {
                "node": node_id,
                "rail": rail_name,
                "attached": bool(attached),
                "fix_to_rail": bool(fix_to_rail),
                "tolerance": float(tolerance),
                "spring": float(spring),
                "strength": strength,
                "cap_strength": cap_strength,
            }
        )

    def add_node(
        self,
        suffix: str,
        position: Vector | tuple[float, float, float],
        *,
        fixed: bool = True,
        collision: bool = False,
        weight: float = 125.0,
        friction: float = 0.9,
        node_material: str = "|NM_METAL",
        group: str | None = None,
        self_collision: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> str:
        identifier = f"{self.mod_id}_{suffix}"
        if identifier in self.node_index:
            raise ValueError(f"duplicate cage node id: {identifier}")
        source = Vector(position)
        self.node_index[identifier] = len(self.nodes)
        node = {
            "id": identifier,
            "source_world_position": [round(value, 6) for value in source],
            "position": vehicle_frame(source),
            "fixed": fixed,
            "collision": collision,
            "self_collision": self_collision,
            "weight": weight,
            "friction": friction,
            "node_material": node_material,
        }
        if group is not None:
            # Group SUFFIX: nodes in a non-default group are excluded from
            # the flexbody skinning (which binds only <mod>_physics). Fast
            # free nodes bound into the visual smear it into morphing
            # blades (proven in play-testing 2026-07-22).
            node["group"] = group
        if extra:
            node["extra"] = dict(extra)
        self.nodes.append(node)
        return identifier

    def add_beam(
        self,
        first: str,
        second: str,
        spec: str = RIGID,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """``extra`` merges per-beam jbeam options over the named spec —
        e.g. ``{"breakGroup": ..., "beamStrength": 40000}`` for breakable
        glass supports."""

        if first == second:
            return
        if first not in self.node_index or second not in self.node_index:
            raise ValueError(f"beam references unknown node: {first}, {second}")
        if spec not in self.beam_specs:
            raise ValueError(f"unknown beam spec: {spec}")
        key = (min(first, second), max(first, second))
        entry = (spec, dict(extra) if extra else None)
        existing = self.beams.get(key)
        if existing is not None and existing != entry:
            raise ValueError(f"conflicting beam specs for {key}: {existing} vs {entry}")
        self.beams[key] = entry

    def add_triangle(
        self,
        first: str,
        second: str,
        third: str,
        *,
        ground_model: str = "metal",
        extra: dict[str, Any] | None = None,
    ) -> None:
        for identifier in (first, second, third):
            if identifier not in self.node_index:
                raise ValueError(f"triangle references unknown node: {identifier}")
        if len({first, second, third}) != 3:
            raise ValueError("degenerate collision triangle")
        entry: dict[str, Any] = {
            "nodes": [first, second, third],
            "ground_model": ground_model,
        }
        if extra:
            entry["extra"] = dict(extra)
        self.triangles.append(entry)

    def add_quad(
        self,
        corners: list[str],
        *,
        ground_model: str = "metal",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Two triangles over a quad given in winding order."""

        a, b, c, d = corners
        self.add_triangle(a, b, c, ground_model=ground_model, extra=extra)
        self.add_triangle(a, c, d, ground_model=ground_model, extra=extra)

    def add_quad_both(
        self,
        corners: list[str],
        *,
        ground_model: str = "metal",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Double-sided quad without the twin-tiling trap (CHIEF b83-b94).

        ``add_quad(q)`` + ``add_quad(reversed(q))`` re-triangulates the
        reversed copy on the OPPOSITE diagonal. On twisted quads the two
        tilings are different surfaces up to tens of cm apart, and the
        down-facing one hovers as an invisible one-way ceiling that wedges
        wheels. Exactly-coincident mirrored twins (same diagonal, both
        windings) are no fix either: jbeam triangles carry contact state,
        and a zero-thickness twin spikes the solver — popped tires on flat
        planar ground. NEVER emit the same node triple twice.

        This emits the HIGHER tiling wound up (the ride surface is the true
        upper envelope) and the LOWER tiling wound down as the one-way
        underside: four distinct triples, a ceiling can never sit above a
        floor. Sliver and near-vertical wall quads have no meaningful
        projected-z winding; they fall back to the crossed-diagonal pair,
        which is exact for the planar quads walls are built from and still
        has four distinct triples.
        """

        a, b, c, d = corners
        pos = {
            identifier: self.nodes[self.node_index[identifier]]["position"]
            for identifier in (a, b, c, d)
        }

        def wind_up(t1: str, t2: str, t3: str) -> tuple[str, str, str]:
            p1, p2, p3 = pos[t1], pos[t2], pos[t3]
            nz = (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p2[1] - p1[1]) * (p3[0] - p1[0])
            return (t1, t2, t3) if nz >= 0 else (t3, t2, t1)

        def wind_down(t1: str, t2: str, t3: str) -> tuple[str, str, str]:
            up = wind_up(t1, t2, t3)
            return (up[2], up[1], up[0])

        pa, pb, pc, pd = pos[a], pos[b], pos[c], pos[d]
        d1 = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
        d2 = (pd[0] - pb[0], pd[1] - pb[1], pd[2] - pb[2])
        qn = (
            d1[1] * d2[2] - d1[2] * d2[1],
            d1[2] * d2[0] - d1[0] * d2[2],
            d1[0] * d2[1] - d1[1] * d2[0],
        )
        qlen = math.sqrt(qn[0] ** 2 + qn[1] ** 2 + qn[2] ** 2) or 1.0
        if qlen < 0.02 or abs(qn[2]) / qlen < 0.35:
            self.add_quad([a, b, c, d], ground_model=ground_model, extra=extra)
            self.add_quad([d, c, b, a], ground_model=ground_model, extra=extra)
            return
        if (pa[2] + pc[2]) >= (pb[2] + pd[2]):
            up_tris = ((a, b, c), (a, c, d))
            down_tris = ((b, c, d), (b, d, a))
        else:
            up_tris = ((b, c, d), (b, d, a))
            down_tris = ((a, b, c), (a, c, d))
        for tri in up_tris:
            self.add_triangle(*wind_up(*tri), ground_model=ground_model, extra=extra)
        for tri in down_tris:
            self.add_triangle(*wind_down(*tri), ground_model=ground_model, extra=extra)

    def add_box_lattice(
        self,
        prefix: str,
        minimum: tuple[float, float, float],
        maximum: tuple[float, float, float],
        *,
        subdivisions: tuple[int, int, int] = (1, 1, 1),
        fixed: bool = True,
        collision: bool = False,
        weight: float = 125.0,
        friction: float = 0.9,
        spec: str = RIGID,
        collision_faces: tuple[str, ...] = (),
        face_ground_models: dict[str, str] | None = None,
    ) -> dict[tuple[int, int, int], str]:
        """A rectangular grid of nodes with full edge + diagonal bracing.

        ``collision_faces`` selects outer faces ("top", "bottom", "north"
        (+Y), "south" (-Y), "east" (+X), "west" (-X)) that receive collision
        triangles; nodes on those faces become collidable.
        """

        nx, ny, nz = (max(1, int(value)) for value in subdivisions)
        face_ground_models = face_ground_models or {}
        grid: dict[tuple[int, int, int], str] = {}
        for ix in range(nx + 1):
            for iy in range(ny + 1):
                for iz in range(nz + 1):
                    x = minimum[0] + (maximum[0] - minimum[0]) * ix / nx
                    y = minimum[1] + (maximum[1] - minimum[1]) * iy / ny
                    z = minimum[2] + (maximum[2] - minimum[2]) * iz / nz
                    on_face = {
                        "west": ix == 0,
                        "east": ix == nx,
                        "south": iy == 0,
                        "north": iy == ny,
                        "bottom": iz == 0,
                        "top": iz == nz,
                    }
                    node_collides = collision or any(on_face[face] for face in collision_faces)
                    grid[(ix, iy, iz)] = self.add_node(
                        f"{prefix}_{ix:02d}_{iy:02d}_{iz:02d}",
                        (x, y, z),
                        fixed=fixed,
                        collision=node_collides,
                        weight=weight,
                        friction=friction,
                    )
        # Axis edges plus all four space diagonals of every cell keep the
        # lattice from folding through zero-stiffness shear modes.
        for (ix, iy, iz), identifier in grid.items():
            for dx, dy, dz in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
                neighbour = grid.get((ix + dx, iy + dy, iz + dz))
                if neighbour:
                    self.add_beam(identifier, neighbour, spec)
            for dx, dy in ((1, 1), (1, -1)):
                neighbour = grid.get((ix + dx, iy + dy, iz))
                if neighbour:
                    self.add_beam(identifier, neighbour, spec)
            for dx, dz in ((1, 1), (1, -1)):
                neighbour = grid.get((ix + dx, iy, iz + dz))
                if neighbour:
                    self.add_beam(identifier, neighbour, spec)
            for dy, dz in ((1, 1), (1, -1)):
                neighbour = grid.get((ix, iy + dy, iz + dz))
                if neighbour:
                    self.add_beam(identifier, neighbour, spec)
            cell_diagonal = grid.get((ix + 1, iy + 1, iz + 1))
            if cell_diagonal:
                self.add_beam(identifier, cell_diagonal, spec)

        def face_quads(face: str) -> list[list[str]]:
            quads: list[list[str]] = []
            if face in ("top", "bottom"):
                iz = nz if face == "top" else 0
                for ix in range(nx):
                    for iy in range(ny):
                        quad = [
                            grid[(ix, iy, iz)],
                            grid[(ix + 1, iy, iz)],
                            grid[(ix + 1, iy + 1, iz)],
                            grid[(ix, iy + 1, iz)],
                        ]
                        if face == "bottom":
                            quad.reverse()
                        quads.append(quad)
            elif face in ("north", "south"):
                iy = ny if face == "north" else 0
                for ix in range(nx):
                    for iz in range(nz):
                        quad = [
                            grid[(ix, iy, iz)],
                            grid[(ix + 1, iy, iz)],
                            grid[(ix + 1, iy, iz + 1)],
                            grid[(ix, iy, iz + 1)],
                        ]
                        if face == "north":
                            quad.reverse()
                        quads.append(quad)
            else:
                ix = nx if face == "east" else 0
                for iy in range(ny):
                    for iz in range(nz):
                        quad = [
                            grid[(ix, iy, iz)],
                            grid[(ix, iy + 1, iz)],
                            grid[(ix, iy + 1, iz + 1)],
                            grid[(ix, iy, iz + 1)],
                        ]
                        # Unreversed winding faces +X, which is outward for
                        # the east face; the west face flips.
                        if face == "west":
                            quad.reverse()
                        quads.append(quad)
            return quads

        for face in collision_faces:
            ground_model = face_ground_models.get(face, "metal")
            for quad in face_quads(face):
                self.add_quad(quad, ground_model=ground_model)
        return grid

    def stitch(self, first: str, second: str, spec: str = RIGID) -> None:
        self.add_beam(first, second, spec)

    def set_ground_reference(
        self,
        ref_position: Vector | tuple[float, float, float],
        back_position: Vector | tuple[float, float, float],
        *,
        left: str,
        up: str,
        support_nodes: list[str],
    ) -> None:
        """Author the two ground-datum nodes plus the refNodes table.

        The datum sits on the measured underside of the structure so callers
        place the prop with the actual map surface Z (Cannon Car Wash rule).
        ``back_position`` must map to +Y in vehicle space (i.e. sit at lower
        authored Y than ``ref_position``... in authored frame the drive
        direction is +Y, so "back" is authored *behind* the reference at a
        smaller Y; the shared rotation flips it to BeamNG's +Y/backward).
        """

        ref_id = self.add_node("ground_reference", ref_position, fixed=True, weight=500.0)
        back_id = self.add_node("ground_back", back_position, fixed=True, weight=500.0)
        if not support_nodes:
            raise ValueError("ground reference requires support nodes")
        for support in support_nodes:
            self.add_beam(ref_id, support)
            self.add_beam(back_id, support)
        self.add_beam(ref_id, back_id)
        self.refnodes = {"ref": ref_id, "back": back_id, "left": left, "up": up}

    def set_refnodes_existing(self, *, ref: str, back: str, left: str, up: str) -> None:
        """Designate existing measured cage nodes as the reference frame.

        The ref node is the spawn datum: keep it a minimum-Z node on the
        measured underside so base-origin placement uses the actual map
        surface Z. ``back`` must map to +Y in vehicle space, i.e. sit at a
        smaller authored Y than ``ref``.
        """

        for name, identifier in (("ref", ref), ("back", back), ("left", left), ("up", up)):
            if identifier not in self.node_index:
                raise ValueError(f"unknown {name} refnode: {identifier}")
        ref_node = self.nodes[self.node_index[ref]]
        back_node = self.nodes[self.node_index[back]]
        if back_node["position"][1] <= ref_node["position"][1]:
            raise ValueError("back refnode must sit behind ref in vehicle space (+Y)")
        self.refnodes = {"ref": ref, "back": back, "left": left, "up": up}

    def set_spawn_envelope(self, node_ids: list[str]) -> None:
        if len(node_ids) != 8:
            raise ValueError("spawn envelope needs exactly eight cage corners")
        for identifier in node_ids:
            if identifier not in self.node_index:
                raise ValueError(f"unknown spawn envelope node: {identifier}")
            self.nodes[self.node_index[identifier]]["collision"] = True
            self.nodes[self.node_index[identifier]]["spawn_envelope"] = True
        self.spawn_envelope_nodes = list(node_ids)

    def auto_base_nodes(self) -> None:
        """Mark every fixed minimum-Z node as ground-datum ballast."""

        fixed_nodes = [node for node in self.nodes if node["fixed"]]
        if not fixed_nodes:
            raise ValueError("cage has no fixed nodes to ground")
        min_z = min(node["position"][2] for node in fixed_nodes)
        self.base_nodes = [
            node["id"] for node in fixed_nodes if abs(node["position"][2] - min_z) < 0.05
        ]
        if len(self.base_nodes) < 3:
            raise ValueError("fewer than three minimum-Z base nodes")

    def validate(self) -> None:
        if not self.refnodes:
            raise ValueError("cage is missing refnodes")
        if not self.base_nodes:
            raise ValueError("cage is missing base nodes")
        if not self.spawn_envelope_nodes:
            raise ValueError("cage is missing its spawn envelope")
        if not self.triangles:
            raise ValueError("cage has no collision triangles")
        slide_pairs: set[tuple[str, str]] = set()
        for slide in self.slidenodes:
            pair = (slide["node"], slide["rail"])
            if pair in slide_pairs:
                raise ValueError(f"duplicate slidenode attachment: {pair}")
            slide_pairs.add(pair)
        adjacency: dict[str, set[str]] = {node["id"]: set() for node in self.nodes}
        for first, second in self.beams:
            adjacency[first].add(second)
            adjacency[second].add(first)
        # A locked, matching coupler is a real spawn-time structural edge.
        # Multi-body mechanisms such as a suspended counterweight may be
        # intentionally disconnected after that coupler releases, so forcing
        # them to add a redundant NORMAL beam defeats the mechanism and can
        # introduce a spring mode.  Count only explicitly locked couplers and
        # matching tagged latch nodes; unlocked proximity couplers do not make
        # an authored cage connected.
        latch_nodes: dict[str, list[str]] = {}
        for node in self.nodes:
            tag = node.get("extra", {}).get("tag")
            if isinstance(tag, str) and tag:
                latch_nodes.setdefault(tag, []).append(node["id"])
        for node in self.nodes:
            extra = node.get("extra", {})
            tag = extra.get("couplerTag")
            if not extra.get("couplerLock") or not isinstance(tag, str):
                continue
            for latch_id in latch_nodes.get(tag, []):
                adjacency[node["id"]].add(latch_id)
                adjacency[latch_id].add(node["id"])
        seen: set[str] = set()
        frontier = [self.nodes[0]["id"]]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            frontier.extend(adjacency[current] - seen)
        if len(seen) != len(self.nodes):
            missing = sorted(set(adjacency) - seen)
            raise ValueError(f"cage graph is disconnected; unreachable: {missing[:8]}")
        for node in self.nodes:
            if not node["fixed"]:
                anchored = any(
                    self.nodes[self.node_index[other]]["fixed"] for other in adjacency[node["id"]]
                )
                # Free nodes may chain (cables); require the chain to reach a
                # fixed anchor within the connected graph, which the global
                # connectivity check above already guarantees.
                del anchored

    def structure(self) -> dict[str, Any]:
        self.validate()
        beam_rows = []
        for (first, second), entry in sorted(self.beams.items()):
            spec, extra = entry
            row: dict[str, Any] = {"nodes": [first, second], "spec": spec}
            if extra:
                row["extra"] = extra
            beam_rows.append(row)
        return {
            "nodes": self.nodes,
            "beams": beam_rows,
            "beam_specs": self.beam_specs,
            "triangles": self.triangles,
            "rails": self.rails,
            "slidenodes": self.slidenodes,
            "base_nodes": self.base_nodes,
            "spawn_envelope_nodes": self.spawn_envelope_nodes,
            "refnodes": self.refnodes,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _export_selected_collada(path: Path, include_animations: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = bpy.ops.wm.collada_export(
        filepath=str(path),
        check_existing=False,
        selected=True,
        include_children=False,
        include_animations=include_animations,
        include_all_actions=include_animations,
        apply_modifiers=True,
        triangulate=True,
        use_texture_copies=False,
        apply_global_orientation=True,
        export_global_forward_selection="Y",
        export_global_up_selection="Z",
        sort_by_name=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"Collada export failed for {path}: {result}")
    _strip_absolute_image_paths(path)


def _strip_absolute_image_paths(path: Path) -> None:
    """Rewrite the DAE's ``<init_from>`` image refs to bare filenames.

    THE PATH-LEAK FIX (found while checking a mod for public upload,
    2026-08-15). Blender writes every texture reference as an absolute URI
    of the machine that exported it — 15 of them in the goal post's DAE,
    each reading ``/C:/Users/<name>/beamng-mcp/examples/...``. That ships
    the author's username and directory layout to everyone who downloads
    the mod.

    It is harmless to the game, which resolves textures through
    main.materials.json and never reads these, and that is exactly why it
    survived this long: nothing breaks, so nothing complains. A bare
    filename is what a portable DAE should carry anyway, and it still
    resolves for anyone who opens the file next to its textures.
    """

    import re

    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"(<init_from>)([^<]*)(</init_from>)")

    def _basename(match: re.Match[str]) -> str:
        value = match.group(2)
        if "/" not in value and "\\" not in value:
            return match.group(0)
        leaf = value.replace("\\", "/").rsplit("/", 1)[-1]
        return f"{match.group(1)}{leaf}{match.group(3)}"

    rewritten, count = pattern.subn(_basename, text)
    if count:
        path.write_text(rewritten, encoding="utf-8")


def export_flexbody_visual(
    mod_id: str,
    dae_path: Path,
    source_objects: list[bpy.types.Object],
    visual_name: str,
) -> dict[str, Any]:
    """Join evaluated copies of the sources, flip into vehicle frame, export."""

    if not source_objects:
        raise ValueError("flexbody visual export received no source objects")
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    temporary = bpy.data.collections.new(f"{mod_id}_visual_export")
    scene.collection.children.link(temporary)
    duplicates: list[bpy.types.Object] = []
    for source in sorted(source_objects, key=lambda obj: obj.name):
        evaluated = source.evaluated_get(depsgraph)
        mesh_copy = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
        )
        duplicate = bpy.data.objects.new(f"{source.name}_export", mesh_copy)
        duplicate.data.name = f"{duplicate.name}_mesh"
        temporary.objects.link(duplicate)
        duplicate.matrix_world = VEHICLE_ROTATION @ source.matrix_world
        duplicates.append(duplicate)
    bpy.ops.object.select_all(action="DESELECT")
    for duplicate in duplicates:
        duplicate.select_set(True)
    bpy.context.view_layer.objects.active = duplicates[0]
    if len(duplicates) > 1:
        bpy.ops.object.join()
    visual = bpy.context.object
    visual.name = visual_name
    visual.data.name = visual_name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bounds = object_bounds(visual)
    materials = sorted(mat.name for mat in visual.data.materials if mat is not None)
    bpy.ops.object.select_all(action="DESELECT")
    visual.select_set(True)
    bpy.context.view_layer.objects.active = visual
    _export_selected_collada(dae_path)
    visual_mesh = visual.data
    bpy.data.objects.remove(visual, do_unlink=True)
    if visual_mesh.users == 0:
        bpy.data.meshes.remove(visual_mesh)
    bpy.data.collections.remove(temporary)
    return {
        "bounds": bounds,
        "materials": materials,
        "sha256": _sha256(dae_path),
        "size": dae_path.stat().st_size,
    }


def export_multi_flexbody(
    mod_id: str,
    dae_path: Path,
    mesh_groups: dict[str, list[bpy.types.Object]],
    weld: float | None = None,
) -> dict[str, Any]:
    """Export several named flexbody meshes into ONE Collada file.

    Each entry becomes a separate named mesh in the DAE (vehicle frame), so
    the jbeam ``flexbodies`` table can bind each one to its own node group —
    the mechanism that lets a broken glass floor's mesh fall with its own
    nodes instead of smearing across the whole tower.

    ``weld`` merges coincident vertices AFTER the join, which is the only
    place it can be done: the generators build one object per surface and the
    join leaves every shared ring as two coincident-but-separate vertex sets,
    so the shaded normals are averaged per SURFACE and a false crease appears
    along every seam. Measured on colossus_tire, 554 vertex pairs down each
    edge of its drive lane had a median normal split of 30.75 degrees where
    the welded geometry bends 2.5. OPT-IN, and defaulting to off, because
    turning it on moves the exported bytes and therefore the lock of every mod
    that calls this.
    """

    if not mesh_groups:
        raise ValueError("multi-flexbody export received no mesh groups")
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    temporary = bpy.data.collections.new(f"{mod_id}_multi_export")
    scene.collection.children.link(temporary)
    joined: list[bpy.types.Object] = []
    per_mesh: dict[str, Any] = {}
    for mesh_name in sorted(mesh_groups):
        source_objects = mesh_groups[mesh_name]
        if not source_objects:
            raise ValueError(f"flexbody mesh has no source objects: {mesh_name}")
        duplicates: list[bpy.types.Object] = []
        for source in sorted(source_objects, key=lambda obj: obj.name):
            evaluated = source.evaluated_get(depsgraph)
            mesh_copy = bpy.data.meshes.new_from_object(
                evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
            )
            duplicate = bpy.data.objects.new(f"{source.name}_mexport", mesh_copy)
            duplicate.data.name = f"{duplicate.name}_mesh"
            temporary.objects.link(duplicate)
            duplicate.matrix_world = VEHICLE_ROTATION @ source.matrix_world
            duplicates.append(duplicate)
        bpy.ops.object.select_all(action="DESELECT")
        for duplicate in duplicates:
            duplicate.select_set(True)
        bpy.context.view_layer.objects.active = duplicates[0]
        if len(duplicates) > 1:
            bpy.ops.object.join()
        merged = bpy.context.object
        merged.name = mesh_name
        merged.data.name = mesh_name
        if weld is not None:
            welder = bmesh.new()
            welder.from_mesh(merged.data)
            bmesh.ops.remove_doubles(welder, verts=welder.verts, dist=weld)
            welder.to_mesh(merged.data)
            welder.free()
            merged.data.update()
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        per_mesh[mesh_name] = {
            "bounds": object_bounds(merged),
            "materials": sorted(mat.name for mat in merged.data.materials if mat is not None),
        }
        joined.append(merged)
    bpy.ops.object.select_all(action="DESELECT")
    for merged in joined:
        merged.select_set(True)
    bpy.context.view_layer.objects.active = joined[0]
    _export_selected_collada(dae_path)
    materials: set[str] = set()
    for info in per_mesh.values():
        materials.update(info["materials"])
    for merged in joined:
        merged_mesh = merged.data
        bpy.data.objects.remove(merged, do_unlink=True)
        if merged_mesh.users == 0:
            bpy.data.meshes.remove(merged_mesh)
    bpy.data.collections.remove(temporary)
    return {
        "meshes": per_mesh,
        "materials": sorted(materials),
        "sha256": _sha256(dae_path),
        "size": dae_path.stat().st_size,
    }


def export_part_shape(
    mod_id: str,
    part_name: str,
    dae_path: Path,
    source_objects: list[bpy.types.Object],
    pivot_world: Vector | tuple[float, float, float],
) -> dict[str, Any]:
    """Export a kinematic runtime part relative to its pivot, authored frame.

    The runtime poses the TSStatic with the prop's model rotation, which
    already contains the vehicle-frame flip; the shape itself therefore stays
    in the authored frame, translated so the pivot is at the DAE origin.
    """

    if not source_objects:
        raise ValueError(f"part export received no source objects: {part_name}")
    pivot = Vector(pivot_world)
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    temporary = bpy.data.collections.new(f"{mod_id}_{part_name}_export")
    scene.collection.children.link(temporary)
    offset = Matrix.Translation(-pivot)
    duplicates: list[bpy.types.Object] = []
    for source in sorted(source_objects, key=lambda obj: obj.name):
        evaluated = source.evaluated_get(depsgraph)
        mesh_copy = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
        )
        duplicate = bpy.data.objects.new(f"{source.name}_part_export", mesh_copy)
        duplicate.data.name = f"{duplicate.name}_mesh"
        temporary.objects.link(duplicate)
        duplicate.matrix_world = offset @ source.matrix_world
        duplicates.append(duplicate)
    bpy.ops.object.select_all(action="DESELECT")
    for duplicate in duplicates:
        duplicate.select_set(True)
    bpy.context.view_layer.objects.active = duplicates[0]
    if len(duplicates) > 1:
        bpy.ops.object.join()
    part = bpy.context.object
    export_name = f"{mod_id}_{part_name}"
    part.name = export_name
    part.data.name = export_name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    materials = sorted(mat.name for mat in part.data.materials if mat is not None)
    bpy.ops.object.select_all(action="DESELECT")
    part.select_set(True)
    bpy.context.view_layer.objects.active = part
    _export_selected_collada(dae_path)
    part_mesh = part.data
    bpy.data.objects.remove(part, do_unlink=True)
    if part_mesh.users == 0:
        bpy.data.meshes.remove(part_mesh)
    bpy.data.collections.remove(temporary)
    return {
        "name": part_name,
        "pivot_world": [round(value, 6) for value in pivot],
        "materials": materials,
        "sha256": _sha256(dae_path),
        "size": dae_path.stat().st_size,
    }


def render_thumbnail(
    path: Path,
    *,
    camera_location: tuple[float, float, float],
    look_at: tuple[float, float, float],
    resolution: tuple[int, int] = (500, 281),
    sun_direction: tuple[float, float, float] = (-0.4, 0.35, -1.0),
    sun_energy: float = 3.0,
    world_color: tuple[float, float, float] = (0.72, 0.82, 0.92),
    world_strength: float = 1.0,
    strip_stamp: bool = False,
) -> None:
    """Render one review/thumbnail frame.

    ``world_strength`` defaults to 1.0 against a bright sky, which is what
    every mod in the pack has always used — so the default is left alone.
    It is a PARAMETER because that ambient is not free: fitting
    ``render = k*albedo + A*neutral`` against a known swatch on the High
    Five renders put A at 69 counts, which halved every chroma and more
    than doubled the floor of every shadow (the darkest 15% of the hand
    bottomed out at luma 135 against the reference photograph's 63). Two
    separate material changes measured as a ONE-COUNT difference because of
    it, and a reviewer spent two rounds attributing the loss to the texture
    before the pedestal was found. A prop whose look is being judged from
    these frames needs a rig whose shadows reach.
    """
    scene = bpy.context.scene
    camera_data = bpy.data.cameras.new("thumbnail_camera")
    camera = bpy.data.objects.new("thumbnail_camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = camera_location
    direction = Vector(look_at) - Vector(camera_location)
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera_data.lens = 32.0
    sun_data = bpy.data.lights.new("thumbnail_sun", "SUN")
    sun_data.energy = sun_energy
    sun = bpy.data.objects.new("thumbnail_sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = Vector(sun_direction).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("thumbnail_world")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs[0].default_value = (*world_color, 1.0)
        background.inputs[1].default_value = world_strength
    scene.world = world
    previous_camera = scene.camera
    scene.camera = camera
    scene.render.engine = (
        "BLENDER_EEVEE_NEXT" if hasattr(bpy.types, "SceneEEVEE") else "BLENDER_EEVEE"
    )
    scene.render.resolution_x = resolution[0]
    scene.render.resolution_y = resolution[1]
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 88
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    if strip_stamp:
        strip_render_stamp(path)
    scene.camera = previous_camera
    bpy.data.objects.remove(camera, do_unlink=True)
    bpy.data.cameras.remove(camera_data)
    bpy.data.objects.remove(sun, do_unlink=True)
    bpy.data.lights.remove(sun_data)


def strip_render_stamp(path: Path) -> bool:
    """Drop Blender's wall-clock COM segments out of a rendered JPEG.

    Blender writes ``Blender:Date:YYYY/MM/DD HH:MM:SS`` and
    ``Blender:RenderTime`` into every JPEG it renders. prop_builder copies the
    thumbnail into the shipped tree TWICE, so a pixel-identical re-render
    still changes the mod's content sha, bumps its build serial and
    invalidates the ZIP lock the live gate verifies against - the same defect
    the Collada normaliser was written for, from the same Blender run, missed
    because only the mesh was being looked at.

    OPT-IN at the call site, following normalise_collada's precedent: turning
    it on unconditionally would move the locks of every other mod in the pack.
    """

    blob = path.read_bytes()
    if not blob.startswith(b"\xff\xd8"):
        return False
    out = bytearray(blob[:2])
    index = 2
    changed = False
    while index + 4 <= len(blob):
        if blob[index] != 0xFF:
            break
        marker = blob[index + 1]
        if marker == 0xDA:                       # start of scan: the rest is data
            out += blob[index:]
            index = len(blob)
            break
        length = int.from_bytes(blob[index + 2:index + 4], "big")
        segment = blob[index:index + 2 + length]
        if marker == 0xFE and b"Blender:" in segment:
            changed = True
        else:
            out += segment
        index += 2 + length
    if index < len(blob):
        out += blob[index:]
    if changed:
        path.write_bytes(bytes(out))
    return changed


def write_handoff(
    handoff_path: Path,
    *,
    mod_id: str,
    display_name: str,
    cage: CageBuilder,
    visual: dict[str, Any],
    visual_dae_relative: str,
    visual_mesh_name: str,
    parts: list[dict[str, Any]],
    palette: dict[str, Any],
    behavior: dict[str, Any],
    flexbodies_extra: list[dict[str, Any]] | None = None,
    panel: dict[str, Any] | None = None,
    visual_groups: list[str] | None = None,
) -> dict[str, Any]:
    structure = cage.structure()
    handoff = {
        "schema": HANDOFF_SCHEMA,
        "asset": {
            "id": mod_id,
            "display_name": display_name,
            "physics_cage": f"{mod_id}_cage",
            "visual_mesh": visual_mesh_name,
            # Optional: bind the main visual flexbody to these node groups
            # (mod-prefixed by prop_builder) instead of the default
            # <mod>_physics group. colossus_tire needed it when its chock
            # visual, left on the default, skinned to a group that held the
            # 16 FIXED buried anchors - each 0.6 m under a wedge corner,
            # closer than the wedge's own nodes - so the winch dragged the
            # wedges 5 m while their visuals stayed nailed to the ground.
            "visual_groups": visual_groups or [],
            "flexbodies_extra": flexbodies_extra or [],
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
        "visual": {"path": visual_dae_relative, **visual},
        "parts": parts,
        "palette": palette,
        "behavior": behavior,
        **structure,
    }
    if panel is not None:
        handoff["panel"] = panel
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return handoff
