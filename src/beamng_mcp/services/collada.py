"""Fail-closed inspection for the narrow Collada subset used by soft-body flexbodies."""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ..errors import WorkspaceError

_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_SURFACE_PRIMITIVES = frozenset({"triangles", "polylist", "polygons", "trifans", "tristrips"})
_UNSUPPORTED_PRIMITIVES = frozenset({"lines", "linestrips"})
MAX_REFERENCED_VERTICES = 250_000


@dataclass(frozen=True)
class ColladaInspection:
    geometry_names: tuple[str, ...]
    scene_node_names: tuple[str, ...]
    material_names: tuple[str, ...]
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    vertex_count: int
    positions: tuple[tuple[float, float, float], ...]


def inspect_collada(
    data: bytes,
    *,
    expected_mesh_name: str,
    expected_material_name: str | None,
) -> ColladaInspection:
    """Parse a DAE without entity expansion and enforce a self-contained identity scene."""

    upper_data = data.upper()
    if b"\x00" in data or b"<!DOCTYPE" in upper_data or b"<!ENTITY" in upper_data:
        raise WorkspaceError("Collada must not contain NUL bytes, a DOCTYPE, or entities")
    try:
        # Input is size-bounded by the staging inbox and entity declarations were
        # rejected above before stdlib parsing.
        root = ET.fromstring(data)  # noqa: S314
    except ET.ParseError as exc:
        raise WorkspaceError(f"Collada is not well-formed XML: {exc}") from exc
    if _local_name(root.tag) != "COLLADA":
        raise WorkspaceError("Visual asset root element must be COLLADA")

    asset = _first_child(root, "asset")
    unit = _first_descendant(asset, "unit")
    try:
        meter = float(unit.attrib["meter"])
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkspaceError("Collada must declare its asset unit in meters") from exc
    if not math.isclose(meter, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise WorkspaceError(f"Collada unit meter must be 1.0, got {meter}")
    up_axis = _first_descendant(asset, "up_axis")
    if (up_axis.text or "").strip() != "Z_UP":
        raise WorkspaceError("Collada must declare Z_UP")

    _reject_external_references(root)
    for image in _descendants(root, "image"):
        init_from = _first_descendant(image, "init_from")
        if (init_from.text or "").strip():
            raise WorkspaceError(
                "v1 soft-body DAE files must not reference external image textures"
            )
    geometry_names: set[str] = set()
    geometries_by_id: dict[str, ET.Element] = {}
    for geometry in _descendants(root, "geometry"):
        geometry_name = geometry.attrib.get("name") or geometry.attrib.get("id")
        if geometry_name:
            geometry_names.add(geometry_name)
        geometry_id = geometry.attrib.get("id")
        if not geometry_id:
            raise WorkspaceError("Every Collada geometry must have an id")
        if geometry_id in geometries_by_id:
            raise WorkspaceError(f"Collada geometry id is duplicated: {geometry_id}")
        geometries_by_id[geometry_id] = geometry

    scene = _first_child(root, "scene")
    scene_instance = _first_child(scene, "instance_visual_scene")
    scene_reference = scene_instance.attrib.get("url", "")
    if not scene_reference.startswith("#") or len(scene_reference) == 1:
        raise WorkspaceError("Collada scene must use one local instance_visual_scene")
    visual_scene_id = scene_reference[1:]
    visual_scenes = [
        item
        for item in _descendants(root, "visual_scene")
        if item.attrib.get("id") == visual_scene_id
    ]
    if len(visual_scenes) != 1:
        raise WorkspaceError("Collada active visual scene does not resolve uniquely")
    active_scene = visual_scenes[0]

    scene_nodes = _descendants(active_scene, "node")
    scene_node_names: set[str] = set()
    for node in scene_nodes:
        node_name = node.attrib.get("name") or node.attrib.get("id")
        if node_name:
            scene_node_names.add(node_name)
        if any(
            _local_name(child.tag) in {"lookat", "rotate", "scale", "skew", "translate"}
            for child in node
        ):
            raise WorkspaceError("Flexbody Collada scene nodes must use a baked identity transform")
        matrices = [child for child in node if _local_name(child.tag) == "matrix"]
        if any(not _is_identity_matrix(matrix.text or "") for matrix in matrices):
            raise WorkspaceError("Flexbody Collada scene nodes must use a baked identity matrix")
        if any(_local_name(child.tag) == "instance_controller" for child in node):
            raise WorkspaceError("Flexbody Collada controller instances are unsupported in v1")

    matching_nodes = [
        node
        for node in scene_nodes
        if expected_mesh_name in {node.attrib.get("id"), node.attrib.get("name")}
    ]
    if len(matching_nodes) != 1:
        available = ", ".join(sorted(scene_node_names)) or "none"
        raise WorkspaceError(
            f"Collada active scene must contain exactly one node named "
            f"{expected_mesh_name!r}; available names: {available}"
        )
    selected_node = matching_nodes[0]
    geometry_instances = [
        child for child in selected_node if _local_name(child.tag) == "instance_geometry"
    ]
    if len(geometry_instances) != 1:
        raise WorkspaceError("Expected flexbody scene node must instance exactly one geometry")
    geometry_instance = geometry_instances[0]
    geometry_reference = geometry_instance.attrib.get("url", "")
    if not geometry_reference.startswith("#") or len(geometry_reference) == 1:
        raise WorkspaceError("Expected flexbody geometry instance must use a local URL")
    selected_geometry = geometries_by_id.get(geometry_reference[1:])
    if selected_geometry is None:
        raise WorkspaceError("Expected flexbody geometry instance does not resolve")
    mesh = _optional_child(selected_geometry, "mesh")
    if mesh is None:
        raise WorkspaceError("Expected flexbody geometry contains no mesh")
    positions, material_symbols = _mesh_evidence(mesh)
    if not positions:
        raise WorkspaceError("Expected Collada mesh has no referenced surface POSITION data")

    material_names = _bound_material_names(root, geometry_instance, material_symbols)
    if expected_material_name is not None and expected_material_name not in material_names:
        available_materials = ", ".join(sorted(material_names)) or "none"
        raise WorkspaceError(
            f"Collada does not contain expected material {expected_material_name!r}; "
            f"available materials: {available_materials}"
        )

    bounds_min = (
        min(point[0] for point in positions),
        min(point[1] for point in positions),
        min(point[2] for point in positions),
    )
    bounds_max = (
        max(point[0] for point in positions),
        max(point[1] for point in positions),
        max(point[2] for point in positions),
    )
    return ColladaInspection(
        geometry_names=tuple(sorted(geometry_names)),
        scene_node_names=tuple(sorted(scene_node_names)),
        material_names=tuple(sorted(material_names)),
        bounds_min=bounds_min,
        bounds_max=bounds_max,
        vertex_count=len(positions),
        positions=tuple(positions),
    )


def _mesh_evidence(
    mesh: ET.Element,
) -> tuple[list[tuple[float, float, float]], set[str]]:
    sources = {
        source.attrib["id"]: source
        for source in mesh
        if _local_name(source.tag) == "source" and "id" in source.attrib
    }
    vertices_positions: dict[str, str] = {}
    for vertices in (child for child in mesh if _local_name(child.tag) == "vertices"):
        vertices_id = vertices.attrib.get("id")
        if not vertices_id:
            raise WorkspaceError("Collada vertices element is missing an id")
        position_sources: list[str] = []
        for input_element in vertices:
            if (
                _local_name(input_element.tag) == "input"
                and input_element.attrib.get("semantic") == "POSITION"
            ):
                reference = input_element.attrib.get("source", "")
                if reference.startswith("#"):
                    position_sources.append(reference[1:])
        if len(position_sources) != 1:
            raise WorkspaceError("Collada vertices must bind exactly one POSITION source")
        vertices_positions[vertices_id] = position_sources[0]

    referenced: dict[str, set[int]] = {}
    material_symbols: set[str] = set()
    primitive_count = 0
    for primitive in mesh:
        primitive_name = _local_name(primitive.tag)
        if primitive_name in _UNSUPPORTED_PRIMITIVES:
            raise WorkspaceError(f"Unsupported Collada mesh primitive: {primitive_name}")
        if primitive_name not in _SURFACE_PRIMITIVES:
            continue
        primitive_count += 1
        material_symbol = primitive.attrib.get("material")
        if not material_symbol:
            raise WorkspaceError("Every Collada surface primitive must bind a material")
        material_symbols.add(material_symbol)
        inputs = [child for child in primitive if _local_name(child.tag) == "input"]
        if not inputs:
            raise WorkspaceError("Collada surface primitive has no inputs")
        try:
            tuple_width = max(int(item.attrib.get("offset", "0")) for item in inputs) + 1
        except ValueError as exc:
            raise WorkspaceError("Collada primitive input offset is invalid") from exc
        position_inputs: list[tuple[str, int]] = []
        for item in inputs:
            semantic = item.attrib.get("semantic")
            reference = item.attrib.get("source", "")
            if not reference.startswith("#"):
                continue
            source_id = reference[1:]
            if semantic == "VERTEX":
                source_id = vertices_positions.get(source_id, "")
            elif semantic != "POSITION":
                continue
            if not source_id:
                raise WorkspaceError("Collada primitive POSITION binding does not resolve")
            try:
                input_offset = int(item.attrib.get("offset", "0"))
            except ValueError as exc:
                raise WorkspaceError("Collada primitive POSITION offset is invalid") from exc
            position_inputs.append((source_id, input_offset))
        if len(position_inputs) != 1:
            raise WorkspaceError("Surface primitive must have exactly one POSITION/VERTEX input")
        source_id, position_offset = position_inputs[0]
        payloads = [child for child in primitive if _local_name(child.tag) == "p"]
        if not payloads:
            raise WorkspaceError("Collada surface primitive has no index payload")
        for payload in payloads:
            try:
                indices = [int(value) for value in (payload.text or "").split()]
            except ValueError as exc:
                raise WorkspaceError("Collada surface indices must be integers") from exc
            if not indices or len(indices) % tuple_width != 0:
                raise WorkspaceError("Collada surface index payload has an invalid stride")
            selected = referenced.setdefault(source_id, set())
            selected.update(indices[position_offset::tuple_width])
    if primitive_count == 0:
        raise WorkspaceError("Expected Collada mesh contains no supported surface primitives")

    result: set[tuple[float, float, float]] = set()
    for source_id, referenced_indices in referenced.items():
        source = sources.get(source_id)
        if source is None:
            raise WorkspaceError(f"Collada POSITION source is missing: {source_id}")
        source_positions = _source_positions(source)
        for index in referenced_indices:
            if index < 0 or index >= len(source_positions):
                raise WorkspaceError("Collada surface index exceeds its POSITION source")
            result.add(source_positions[index])
            if len(result) > MAX_REFERENCED_VERTICES:
                raise WorkspaceError(
                    f"Collada exceeds the {MAX_REFERENCED_VERTICES} referenced-vertex limit"
                )
    return sorted(result), material_symbols


def _source_positions(source: ET.Element) -> tuple[tuple[float, float, float], ...]:
    float_arrays = [child for child in source if _local_name(child.tag) == "float_array"]
    if len(float_arrays) != 1:
        raise WorkspaceError("Collada POSITION source must contain one float_array")
    float_array = float_arrays[0]
    try:
        values = [float(value) for value in (float_array.text or "").split()]
    except ValueError as exc:
        raise WorkspaceError("Collada POSITION data contains a non-numeric value") from exc
    if not values or any(not math.isfinite(value) for value in values):
        raise WorkspaceError("Collada POSITION data must contain finite values")
    accessor = _first_descendant(source, "accessor")
    accessor_source = accessor.attrib.get("source", "")
    if float_array.attrib.get("id") and accessor_source != f"#{float_array.attrib['id']}":
        raise WorkspaceError("Collada POSITION accessor does not reference its float_array")
    try:
        stride = int(accessor.attrib.get("stride", "1"))
        count = int(accessor.attrib["count"])
        offset = int(accessor.attrib.get("offset", "0"))
    except (KeyError, ValueError) as exc:
        raise WorkspaceError("Collada POSITION accessor is invalid") from exc
    if stride < 3 or count < 1 or offset < 0 or offset + count * stride > len(values):
        raise WorkspaceError("Collada POSITION accessor exceeds its float array")
    return tuple(
        (values[start], values[start + 1], values[start + 2])
        for index in range(count)
        for start in (offset + index * stride,)
    )


def _bound_material_names(
    root: ET.Element,
    geometry_instance: ET.Element,
    symbols: set[str],
) -> set[str]:
    materials = _descendants(root, "material")
    by_id = {item.attrib.get("id", ""): item for item in materials if item.attrib.get("id")}
    bindings: dict[str, str] = {}
    for item in _descendants(geometry_instance, "instance_material"):
        symbol = item.attrib.get("symbol", "")
        target = item.attrib.get("target", "")
        if not symbol or not target.startswith("#") or len(target) == 1:
            raise WorkspaceError("Collada instance_material binding is invalid")
        if symbol in bindings and bindings[symbol] != target[1:]:
            raise WorkspaceError("Collada material symbol has conflicting bindings")
        bindings[symbol] = target[1:]

    result: set[str] = set()
    for symbol in symbols:
        material_id = bindings.get(symbol, symbol)
        material = by_id.get(material_id)
        if material is None:
            candidates = [item for item in materials if item.attrib.get("name") == material_id]
            if len(candidates) != 1:
                raise WorkspaceError(f"Collada material symbol is not bound: {symbol}")
            material = candidates[0]
        name = material.attrib.get("name") or material.attrib.get("id")
        if not name:
            raise WorkspaceError("Bound Collada material has no stable name")
        result.add(name)
    return result


def _reject_external_references(root: ET.Element) -> None:
    for element in root.iter():
        for key, value in element.attrib.items():
            if _local_name(key) == "url" and value and not value.startswith("#"):
                raise WorkspaceError(f"Collada contains an external URL reference: {value!r}")
        if _local_name(element.tag) != "init_from":
            continue
        value = (element.text or "").strip()
        if (
            "://" in value
            or value.startswith(("/", "\\"))
            or _DRIVE_PATH.match(value)
            or ".." in value.replace("\\", "/").split("/")
        ):
            raise WorkspaceError(f"Collada contains an external asset reference: {value!r}")


def _is_identity_matrix(text: str) -> bool:
    try:
        values = [float(value) for value in text.split()]
    except ValueError:
        return False
    if len(values) != 16 or any(not math.isfinite(value) for value in values):
        return False
    expected = [
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
    ]
    pairs = zip(values, expected, strict=True)
    return all(math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9) for left, right in pairs)


def _local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _descendants(parent: ET.Element, name: str) -> list[ET.Element]:
    return [element for element in parent.iter() if _local_name(element.tag) == name]


def _optional_child(parent: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in parent if _local_name(child.tag) == name), None)


def _first_child(parent: ET.Element, name: str) -> ET.Element:
    child = _optional_child(parent, name)
    if child is None:
        raise WorkspaceError(f"Collada is missing required {name} element")
    return child


def _first_descendant(parent: ET.Element, name: str) -> ET.Element:
    element = next((item for item in parent.iter() if _local_name(item.tag) == name), None)
    if element is None:
        raise WorkspaceError(f"Collada is missing required {name} element")
    return element
