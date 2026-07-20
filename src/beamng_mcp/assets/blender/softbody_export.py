"""Deterministic Blender-to-BeamNG soft-body structure handoff.

This module is intentionally self-contained so its reviewed source can be executed by
Blender MCP's ``execute_blender_code`` tool.  It does not patch or depend on Blender MCP.

Call :func:`export_beamng_softbody` from Blender's main thread with a mapping like::

    {
        "asset_id": "crusher_frame",
        "physics_cage": "crusher_physics",
        "visual_objects": ["crusher_visual"],
        "world_to_beamng": [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        "source_origin_world": [0.0, 0.0, 0.0],
        "visual_format": "dae",  # ``gltf`` is debug/interchange only
        "visual_path": "C:/absolute/approved/workspace/crusher_frame.dae",
        "manifest_path": "C:/absolute/approved/workspace/crusher_frame.structure.json",
        # Optional: require non-empty memberships for selected standardized roles.
        "required_roles": ["beamng_ref", "beamng_back", "beamng_left", "beamng_up"],
        # Optional when exactly one Collada operator is discovered.
        "dae_operator": "wm.collada_export",
    }

The physics-cage mesh must contain a unique, non-empty string POINT attribute named
``beamng_node_id``.  Mesh-index, nearest-point, and generated-name fallbacks are forbidden.
The Blender scene must use Metric units with ``scale_length == 1``.  Blender and BeamNG
are both Z-up; the supplied proper-rigid transform must preserve the positive Z axis.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

try:  # Keep the file importable/compilable in normal Python environments.
    import bpy  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only outside Blender
    bpy = None


SCHEMA: Final = "beamng-blender-handoff-v1"
NODE_ATTRIBUTE: Final = "beamng_node_id"
ROLE_GROUPS: Final = (
    "beamng_base",
    "beamng_ref",
    "beamng_back",
    "beamng_left",
    "beamng_up",
    "beamng_interior",
)
SINGLE_NODE_ROLES: Final = frozenset({"beamng_ref", "beamng_back", "beamng_left", "beamng_up"})
RIGID_TOLERANCE: Final = 1.0e-6
NODE_ID_PATTERN: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_FILE_ATTRIBUTE_REPARSE_POINT: Final = 0x400

JsonObject = dict[str, Any]
Vector3 = tuple[float, float, float]
Matrix4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]


class SoftbodyExportError(RuntimeError):
    """A fail-closed authoring or export validation error."""


def _require_blender() -> Any:
    if bpy is None:
        raise SoftbodyExportError("export_beamng_softbody must run inside Blender")
    return bpy


def _required_string(config: Mapping[str, object], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SoftbodyExportError(f"{key} must be a non-empty string")
    return value.strip()


def _string_list(config: Mapping[str, object], key: str, *, required: bool) -> list[str]:
    value = config.get(key)
    if value is None and not required:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise SoftbodyExportError(f"{key} must be a list of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SoftbodyExportError(f"{key} must contain only non-empty strings")
        result.append(item.strip())
    if required and not result:
        raise SoftbodyExportError(f"{key} must not be empty")
    if len(result) != len(set(result)):
        raise SoftbodyExportError(f"{key} must not contain duplicates")
    return result


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SoftbodyExportError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise SoftbodyExportError(f"{label} must be a finite number")
    return result


def _matrix4(config: Mapping[str, object]) -> Matrix4:
    value = config.get("world_to_beamng")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 4:
        raise SoftbodyExportError("world_to_beamng must be an explicit 4x4 numeric matrix")
    rows: list[tuple[float, float, float, float]] = []
    for row_index, row in enumerate(value):
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) != 4:
            raise SoftbodyExportError("world_to_beamng must be an explicit 4x4 numeric matrix")
        rows.append(
            cast(
                tuple[float, float, float, float],
                tuple(
                    _finite_number(cell, f"world_to_beamng[{row_index}][{column_index}]")
                    for column_index, cell in enumerate(row)
                ),
            )
        )
    matrix = cast(Matrix4, tuple(rows))
    _validate_rigid_z_up(matrix)
    return matrix


def _determinant3(rows: Sequence[Sequence[float]]) -> float:
    return (
        rows[0][0] * (rows[1][1] * rows[2][2] - rows[1][2] * rows[2][1])
        - rows[0][1] * (rows[1][0] * rows[2][2] - rows[1][2] * rows[2][0])
        + rows[0][2] * (rows[1][0] * rows[2][1] - rows[1][1] * rows[2][0])
    )


def _validate_rigid_z_up(matrix: Matrix4) -> None:
    expected_last = (0.0, 0.0, 0.0, 1.0)
    if any(abs(matrix[3][index] - expected_last[index]) > RIGID_TOLERANCE for index in range(4)):
        raise SoftbodyExportError("world_to_beamng must be affine with last row [0, 0, 0, 1]")

    rotation = [row[:3] for row in matrix[:3]]
    for left in range(3):
        for right in range(3):
            dot = sum(rotation[row][left] * rotation[row][right] for row in range(3))
            expected = 1.0 if left == right else 0.0
            if abs(dot - expected) > RIGID_TOLERANCE:
                raise SoftbodyExportError("world_to_beamng linear part must be orthonormal")
    if abs(_determinant3(rotation) - 1.0) > RIGID_TOLERANCE:
        raise SoftbodyExportError("world_to_beamng must be a proper rigid transform")
    transformed_up = (matrix[0][2], matrix[1][2], matrix[2][2])
    if any(
        abs(transformed_up[index] - (0.0, 0.0, 1.0)[index]) > RIGID_TOLERANCE for index in range(3)
    ):
        raise SoftbodyExportError("world_to_beamng must preserve positive Z-up")


def _transform(matrix: Matrix4, point: Vector3) -> Vector3:
    homogeneous = (point[0], point[1], point[2], 1.0)
    return cast(
        Vector3,
        tuple(
            sum(matrix[row][column] * homogeneous[column] for column in range(4))
            for row in range(3)
        ),
    )


def _vector3(value: object, label: str) -> Vector3:
    try:
        components = tuple(float(value[index]) for index in range(3))  # type: ignore[index]
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise SoftbodyExportError(f"{label} is not a three-component vector") from exc
    if not all(math.isfinite(component) for component in components):
        raise SoftbodyExportError(f"{label} contains a non-finite coordinate")
    return cast(Vector3, components)


def _source_origin(config: Mapping[str, object], transform: Matrix4) -> Vector3:
    if "source_origin_world" not in config:
        raise SoftbodyExportError("source_origin_world is required")
    source_origin = _vector3(config["source_origin_world"], "source_origin_world")
    mapped_origin = _transform(transform, source_origin)
    if any(abs(component) > RIGID_TOLERANCE for component in mapped_origin):
        raise SoftbodyExportError(
            "world_to_beamng must map source_origin_world to BeamNG [0, 0, 0]"
        )
    return source_origin


def _bounds(points: Iterable[Vector3]) -> JsonObject:
    values = list(points)
    if not values:
        raise SoftbodyExportError("physics cage has no vertices")
    minimum = [min(point[axis] for point in values) for axis in range(3)]
    maximum = [max(point[axis] for point in values) for axis in range(3)]
    return {
        "min": minimum,
        "max": maximum,
        "dimensions": [maximum[axis] - minimum[axis] for axis in range(3)],
    }


def _canonical_cycle(values: Sequence[str]) -> tuple[str, ...]:
    sequence = tuple(values)
    return min(sequence[offset:] + sequence[:offset] for offset in range(len(sequence)))


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _assert_no_reparse_components(path: Path, *, allow_missing_leaf: bool = False) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for index, part in enumerate(parts):
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if allow_missing_leaf and index == len(parts) - 1:
                return
            raise SoftbodyExportError(f"Output path component does not exist: {current}") from None
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise SoftbodyExportError(f"Output path crosses a symlink or reparse point: {current}")


def _absolute_output_path(config: Mapping[str, object], key: str, suffixes: set[str]) -> Path:
    path = Path(os.path.abspath(Path(_required_string(config, key)).expanduser()))
    if not path.is_absolute():
        raise SoftbodyExportError(f"{key} must be an absolute path")
    if path.suffix.lower() not in suffixes:
        expected = ", ".join(sorted(suffixes))
        raise SoftbodyExportError(f"{key} must end in one of: {expected}")
    _assert_no_reparse_components(path, allow_missing_leaf=True)
    parent = path.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        raise SoftbodyExportError(f"{key} parent must be an existing, non-symlink directory")
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise SoftbodyExportError(f"{key} must target a regular file")
    return path


def _atomic_write(path: Path, content: bytes) -> None:
    _assert_no_reparse_components(path, allow_missing_leaf=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _assert_no_reparse_components(path, allow_missing_leaf=True)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _hash_file(path: Path) -> tuple[str, int]:
    _assert_no_reparse_components(path)
    metadata = os.lstat(path)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
    ):
        raise SoftbodyExportError(f"Exporter did not produce a non-empty regular file: {path}")
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if (
            _is_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
        ):
            raise SoftbodyExportError("Visual export changed before it could be hashed")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        final_opened = os.fstat(handle.fileno())
    _assert_no_reparse_components(path)
    final = os.lstat(path)
    fingerprints = (
        (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns),
        (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns),
        (
            final_opened.st_dev,
            final_opened.st_ino,
            final_opened.st_size,
            final_opened.st_mtime_ns,
        ),
        (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns),
    )
    if len(set(fingerprints)) != 1:
        raise SoftbodyExportError("Visual export changed while it was being hashed")
    return digest.hexdigest(), final.st_size


def _validate_scene_units(blender: Any) -> None:
    units = blender.context.scene.unit_settings
    if str(units.system) != "METRIC" or abs(float(units.scale_length) - 1.0) > RIGID_TOLERANCE:
        raise SoftbodyExportError(
            "Scene units must be Metric with scale_length == 1.0 (one Blender unit is one metre)"
        )


def _mesh_node_ids(mesh: Any) -> list[str]:
    attribute = mesh.attributes.get(NODE_ATTRIBUTE)
    if attribute is None:
        raise SoftbodyExportError(
            "physics cage requires string POINT attribute "
            f"{NODE_ATTRIBUTE!r}; fallback is forbidden"
        )
    if str(attribute.domain) != "POINT" or str(attribute.data_type) != "STRING":
        raise SoftbodyExportError(f"{NODE_ATTRIBUTE!r} must be a string POINT attribute")
    if len(attribute.data) != len(mesh.vertices):
        raise SoftbodyExportError(f"{NODE_ATTRIBUTE!r} length does not match evaluated vertices")

    result: list[str] = []
    for index, item in enumerate(attribute.data):
        node_id = str(item.value).strip()
        if not NODE_ID_PATTERN.fullmatch(node_id):
            raise SoftbodyExportError(
                f"{NODE_ATTRIBUTE}[{index}] must match {NODE_ID_PATTERN.pattern!r}"
            )
        result.append(node_id)
    if len(result) != len(set(result)):
        duplicates = sorted(node_id for node_id, count in Counter(result).items() if count > 1)
        raise SoftbodyExportError(f"duplicate beamng_node_id values: {duplicates}")
    return result


def _roles(
    cage: Any, mesh: Any, node_ids: Sequence[str]
) -> tuple[dict[str, list[str]], list[list[str]]]:
    group_names = {int(group.index): str(group.name) for group in cage.vertex_groups}
    by_role: dict[str, list[str]] = {role: [] for role in ROLE_GROUPS}
    by_node: list[list[str]] = [[] for _ in node_ids]
    for vertex in mesh.vertices:
        for membership in vertex.groups:
            role = group_names.get(int(membership.group))
            if role in by_role and float(membership.weight) > 0.0:
                node_id = node_ids[int(vertex.index)]
                by_role[role].append(node_id)
                by_node[int(vertex.index)].append(role)
    for role in ROLE_GROUPS:
        by_role[role] = sorted(set(by_role[role]))
        if role in SINGLE_NODE_ROLES and len(by_role[role]) > 1:
            raise SoftbodyExportError(f"vertex group {role!r} may contain at most one node")
    return by_role, [sorted(set(values)) for values in by_node]


def _extract_structure(blender: Any, cage: Any, transform: Matrix4) -> JsonObject:
    depsgraph = blender.context.evaluated_depsgraph_get()
    evaluated = cage.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    if mesh is None:
        raise SoftbodyExportError("could not evaluate physics-cage mesh")
    try:
        node_ids = _mesh_node_ids(mesh)
        role_index, node_roles = _roles(cage, mesh, node_ids)
        world_matrix = evaluated.matrix_world
        world_positions: list[Vector3] = []
        beamng_positions: list[Vector3] = []
        for vertex in mesh.vertices:
            world = _vector3(world_matrix @ vertex.co, f"vertex {vertex.index}")
            world_positions.append(world)
            beamng_positions.append(_transform(transform, world))

        nodes: list[JsonObject] = [
            {
                "id": node_ids[index],
                "position": list(beamng_positions[index]),
                "source_world_position": list(world_positions[index]),
                "source_object": str(cage.name),
                "source_vertex_index": int(mesh.vertices[index].index),
                "roles": node_roles[index],
            }
            for index in range(len(node_ids))
        ]
        edge_pairs = sorted(
            {
                tuple(sorted((node_ids[int(edge.vertices[0])], node_ids[int(edge.vertices[1])])))
                for edge in mesh.edges
            }
        )
        if any(left == right for left, right in edge_pairs):
            raise SoftbodyExportError("physics cage contains a self-edge")
        edge_beams = [
            {"id": f"edge:{left}|{right}", "nodes": [left, right]} for left, right in edge_pairs
        ]

        quad_panels: list[JsonObject] = []
        brace_pairs: set[tuple[str, str]] = set()
        boundary_incidence: Counter[tuple[int, int]] = Counter()
        boundary_direction: Counter[tuple[int, int]] = Counter()
        for polygon in mesh.polygons:
            polygon_indices = [int(index) for index in polygon.vertices]
            if len(polygon_indices) < 3 or len(polygon_indices) != len(set(polygon_indices)):
                raise SoftbodyExportError(f"polygon {polygon.index} is degenerate")
            for offset, start in enumerate(polygon_indices):
                end = polygon_indices[(offset + 1) % len(polygon_indices)]
                boundary_incidence[cast(tuple[int, int], tuple(sorted((start, end))))] += 1
                boundary_direction[(start, end)] += 1
            if len(polygon_indices) == 4:
                panel_nodes = _canonical_cycle([node_ids[index] for index in polygon_indices])
                diagonals: tuple[tuple[str, str], tuple[str, str]] = (
                    cast(tuple[str, str], tuple(sorted((panel_nodes[0], panel_nodes[2])))),
                    cast(tuple[str, str], tuple(sorted((panel_nodes[1], panel_nodes[3])))),
                )
                brace_pairs.update(diagonals)
                quad_panels.append(
                    {
                        "id": "quad:" + "|".join(panel_nodes),
                        "nodes": list(panel_nodes),
                        "diagonal_beams": [list(pair) for pair in diagonals],
                    }
                )
        quad_panels.sort(key=lambda panel: panel["id"])
        brace_beams = [
            {"id": f"brace:{left}|{right}", "nodes": [left, right]}
            for left, right in sorted(brace_pairs)
        ]

        mesh.calc_loop_triangles()
        triangle_nodes: list[tuple[str, str, str]] = []
        triangle_indices: list[tuple[int, int, int]] = []
        for triangle in mesh.loop_triangles:
            indices3 = cast(tuple[int, int, int], tuple(int(index) for index in triangle.vertices))
            if len(set(indices3)) != 3:
                raise SoftbodyExportError("triangulation produced a degenerate triangle")
            triangle_indices.append(indices3)
            triangle_nodes.append(
                cast(
                    tuple[str, str, str],
                    _canonical_cycle([node_ids[index] for index in indices3]),
                )
            )
        triangle_nodes.sort()
        triangles = [
            {"id": "triangle:" + "|".join(values), "nodes": list(values)}
            for values in triangle_nodes
        ]

        closed = bool(boundary_incidence) and all(
            count == 2 for count in boundary_incidence.values()
        )
        winding_consistent = closed and all(
            boundary_direction[(left, right)] == 1 and boundary_direction[(right, left)] == 1
            for left, right in boundary_incidence
        )
        volume: float | None = None
        if closed:
            if not winding_consistent:
                raise SoftbodyExportError("closed physics cage has inconsistent face winding")
            signed_volume = 0.0
            for first, second, third in triangle_indices:
                a, b, c = (
                    beamng_positions[first],
                    beamng_positions[second],
                    beamng_positions[third],
                )
                cross = (
                    b[1] * c[2] - b[2] * c[1],
                    b[2] * c[0] - b[0] * c[2],
                    b[0] * c[1] - b[1] * c[0],
                )
                signed_volume += (a[0] * cross[0] + a[1] * cross[1] + a[2] * cross[2]) / 6.0
            volume = abs(signed_volume)

        topology_payload = {
            "node_ids": sorted(node_ids),
            "edge_beams": [beam["nodes"] for beam in edge_beams],
            "brace_beams": [beam["nodes"] for beam in brace_beams],
            "quad_brace_panels": [panel["nodes"] for panel in quad_panels],
            "triangles": [triangle["nodes"] for triangle in triangles],
            "roles": role_index,
        }
        source_bounds = _bounds(world_positions)
        beamng_bounds = _bounds(beamng_positions)
        geometry_payload = {
            "topology_sha256": _sha256_json(topology_payload),
            "nodes": nodes,
            "bounds": {"source_world": source_bounds, "beamng": beamng_bounds},
            "closed": closed,
            "winding_consistent": winding_consistent,
            "volume_m3": volume,
        }
        return {
            "nodes": nodes,
            "edge_beams": edge_beams,
            "brace_beams": brace_beams,
            "quad_brace_panels": quad_panels,
            "triangles": triangles,
            "roles": role_index,
            "bounds": {
                "source_world": source_bounds,
                "beamng": beamng_bounds,
            },
            "closed": closed,
            "winding_consistent": winding_consistent,
            "volume_m3": volume,
            "topology_sha256": geometry_payload["topology_sha256"],
            "geometry_sha256": _sha256_json(geometry_payload),
        }
    finally:
        evaluated.to_mesh_clear()


def _operator_properties(operator: Any) -> set[str]:
    try:
        return {str(prop.identifier) for prop in operator.get_rna_type().properties}
    except (AttributeError, RuntimeError):
        return set()


def _discover_dae_operators(blender: Any) -> dict[str, Any]:
    discovered: dict[str, Any] = {}
    for namespace_name in sorted(name for name in dir(blender.ops) if not name.startswith("_")):
        namespace = getattr(blender.ops, namespace_name)
        for operator_name in sorted(name for name in dir(namespace) if not name.startswith("_")):
            qualified = f"{namespace_name}.{operator_name}"
            lowered = qualified.lower()
            if "collada" not in lowered and not (
                "export" in lowered and (".dae" in lowered or "_dae" in lowered)
            ):
                continue
            operator = getattr(namespace, operator_name)
            if "filepath" in _operator_properties(operator):
                discovered[qualified] = operator
    return discovered


def _unique_object_name(blender: Any, stem: str) -> str:
    index = 0
    while True:
        candidate = f"__beamng_softbody_{stem}_{index:04d}"
        if blender.data.objects.get(candidate) is None:
            return candidate
        index += 1


def _cleanup_baked_visual_objects(
    blender: Any,
    duplicates: Sequence[Any],
    meshes: Sequence[Any],
    renamed_sources: Sequence[tuple[Any, str]],
) -> None:
    for duplicate in reversed(duplicates):
        if blender.data.objects.get(str(duplicate.name)) is duplicate:
            blender.data.objects.remove(duplicate, do_unlink=True)
    for source, original_name in renamed_sources:
        source.name = original_name
        if str(source.name) != original_name:
            raise SoftbodyExportError(
                f"could not restore source object name {original_name!r} after export"
            )
    for mesh in reversed(meshes):
        if int(mesh.users) == 0:
            blender.data.meshes.remove(mesh)


def _create_baked_visual_objects(
    blender: Any, objects: Sequence[Any], transform: Matrix4
) -> tuple[list[Any], list[Any], list[tuple[Any, str]]]:
    """Create selected-export objects whose mesh coordinates are already in BeamNG space."""

    depsgraph = blender.context.evaluated_depsgraph_get()
    duplicates: list[Any] = []
    meshes: list[Any] = []
    renamed_sources: list[tuple[Any, str]] = []
    source_names = [str(source.name) for source in objects]
    try:
        for index, source in enumerate(objects):
            evaluated = source.evaluated_get(depsgraph)
            mesh = blender.data.meshes.new_from_object(
                evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
            )
            if mesh is None:
                raise SoftbodyExportError(
                    f"could not create evaluated visual mesh for {source_names[index]!r}"
                )
            meshes.append(mesh)
            world_matrix = evaluated.matrix_world
            for vertex in mesh.vertices:
                source_world = _vector3(
                    world_matrix @ vertex.co,
                    f"visual {source_names[index]!r} vertex {vertex.index}",
                )
                vertex.co = _transform(transform, source_world)
            mesh.update()

            source_materials = [
                str(slot.material.name)
                for slot in evaluated.material_slots
                if slot.material is not None
            ]
            baked_materials = [
                str(material.name) for material in mesh.materials if material is not None
            ]
            if baked_materials != source_materials:
                raise SoftbodyExportError(
                    f"evaluated material slots changed for visual object {source_names[index]!r}"
                )

            duplicate = blender.data.objects.new(
                _unique_object_name(blender, f"baked_{index}"), mesh
            )
            blender.context.scene.collection.objects.link(duplicate)
            duplicates.append(duplicate)
            identity = evaluated.matrix_world.copy()
            identity.identity()
            duplicate.matrix_world = identity
            if any(
                abs(float(duplicate.matrix_world[row][column]) - (1.0 if row == column else 0.0))
                > RIGID_TOLERANCE
                for row in range(4)
                for column in range(4)
            ):
                raise SoftbodyExportError(
                    "temporary visual object did not retain identity transform"
                )
        # Blender object names are unique.  Free each source name only after every
        # evaluated mesh is safely baked, then give the temporary export object the
        # exact source name.  Internal object references survive the temporary rename.
        for index, source in enumerate(objects):
            original_name = source_names[index]
            source.name = _unique_object_name(blender, f"source_{index}")
            renamed_sources.append((source, original_name))
        for index, duplicate in enumerate(duplicates):
            duplicate.name = source_names[index]
            if str(duplicate.name) != source_names[index]:
                raise SoftbodyExportError(
                    f"could not preserve visual object name {source_names[index]!r}"
                )
        return duplicates, meshes, renamed_sources
    except Exception:
        _cleanup_baked_visual_objects(blender, duplicates, meshes, renamed_sources)
        raise


def _select_visual_objects(
    blender: Any, objects: Sequence[Any]
) -> tuple[list[Any], Any, dict[str, bool]]:
    previous = list(blender.context.selected_objects)
    active = blender.context.view_layer.objects.active
    hidden = {str(item.name): bool(item.hide_get()) for item in objects}
    for item in list(blender.context.selected_objects):
        item.select_set(False)
    for item in objects:
        item.hide_set(False)
        item.select_set(True)
    blender.context.view_layer.objects.active = objects[0]
    return previous, active, hidden


def _restore_selection(
    blender: Any, objects: Sequence[Any], state: tuple[list[Any], Any, dict[str, bool]]
) -> None:
    previous, active, hidden = state
    for item in list(blender.context.selected_objects):
        item.select_set(False)
    for item in objects:
        item.hide_set(hidden[str(item.name)])
    for item in previous:
        if item.name in blender.context.scene.objects:
            item.select_set(True)
    if active is not None and active.name in blender.context.scene.objects:
        blender.context.view_layer.objects.active = active


def _run_export(
    blender: Any,
    config: Mapping[str, object],
    visual_format: str,
    output: Path,
    objects: Sequence[Any],
    transform: Matrix4,
) -> JsonObject:
    source_object_names = [str(item.name) for item in objects]
    _assert_no_reparse_components(output, allow_missing_leaf=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}.", suffix=output.suffix, dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink(missing_ok=True)
    baked_objects, baked_meshes, renamed_sources = _create_baked_visual_objects(
        blender, objects, transform
    )
    selection_state: tuple[list[Any], Any, dict[str, bool]] | None = None
    operator_name: str
    export_kwargs: dict[str, object]
    try:
        selection_state = _select_visual_objects(blender, baked_objects)
        if visual_format == "gltf":
            operator_name = "export_scene.gltf"
            operator = blender.ops.export_scene.gltf
            properties = _operator_properties(operator)
            required = {"filepath", "export_format", "use_selection", "export_yup"}
            if not required.issubset(properties):
                raise SoftbodyExportError(
                    "registered glTF operator lacks required deterministic options"
                )
            export_kwargs = {
                "filepath": str(temporary),
                "export_format": "GLTF_EMBEDDED",
                "use_selection": True,
                "export_yup": False,
            }
            if "export_apply" in properties:
                export_kwargs["export_apply"] = True
        else:
            discovered = _discover_dae_operators(blender)
            requested = config.get("dae_operator")
            if requested is not None and not isinstance(requested, str):
                raise SoftbodyExportError("dae_operator must be a string when supplied")
            if requested:
                if requested not in discovered:
                    raise SoftbodyExportError(
                        f"requested Collada operator {requested!r} is unavailable; "
                        f"discovered {sorted(discovered)}"
                    )
                operator_name = requested
            elif len(discovered) == 1:
                operator_name = next(iter(discovered))
            elif not discovered:
                raise SoftbodyExportError(
                    "no Collada/DAE export operator is registered; DAE export fails closed"
                )
            else:
                raise SoftbodyExportError(
                    "multiple Collada operators discovered; set dae_operator to one of "
                    f"{sorted(discovered)}"
                )
            operator = discovered[operator_name]
            properties = _operator_properties(operator)
            selection_options = (
                "selected",
                "use_selection",
                "selected_only",
                "selection_only",
                "export_selected",
            )
            selection_property = next(
                (name for name in selection_options if name in properties), None
            )
            if selection_property is None:
                raise SoftbodyExportError(
                    f"Collada operator {operator_name!r} has no discoverable selection-only option"
                )
            export_kwargs = {"filepath": str(temporary), selection_property: True}
            for option in ("apply_modifiers", "triangulate", "sort_by_name"):
                if option in properties:
                    export_kwargs[option] = True
            if "check_existing" in properties:
                export_kwargs["check_existing"] = False

        result = operator(**export_kwargs)
        if "FINISHED" not in set(result):
            raise SoftbodyExportError(
                f"{operator_name} returned {set(result)!r} instead of FINISHED"
            )
        if not temporary.exists():
            appended = temporary.with_suffix(temporary.suffix + output.suffix)
            if appended.exists():
                temporary = appended
            else:
                raise SoftbodyExportError(f"{operator_name} did not create the requested file")
        _assert_no_reparse_components(output, allow_missing_leaf=True)
        os.replace(temporary, output)
        digest, size = _hash_file(output)
        return {
            "format": visual_format,
            "debug_only": visual_format == "gltf",
            "path": str(output),
            "operator": operator_name,
            "objects": source_object_names,
            "coordinates_baked_to_beamng": True,
            "object_transform": "identity",
            "sha256": digest,
            "size": size,
            "z_up": True,
            "units": "m",
        }
    finally:
        try:
            if selection_state is not None:
                _restore_selection(blender, baked_objects, selection_state)
        finally:
            try:
                _cleanup_baked_visual_objects(blender, baked_objects, baked_meshes, renamed_sources)
            finally:
                temporary.unlink(missing_ok=True)


def export_beamng_softbody(config: Mapping[str, object]) -> JsonObject:
    """Export a reviewed visual and raw ``beamng-blender-handoff-v1`` manifest.

    The function performs no network access, process creation, dynamic evaluation, or
    coordinate inference.  Every BeamNG position is the evaluated Blender world position
    multiplied once by the required caller-supplied rigid ``world_to_beamng`` matrix.
    """

    if not isinstance(config, Mapping):
        raise SoftbodyExportError("config must be a mapping")
    blender = _require_blender()
    _validate_scene_units(blender)
    asset_id = _required_string(config, "asset_id")
    if not NODE_ID_PATTERN.fullmatch(asset_id):
        raise SoftbodyExportError(f"asset_id must match {NODE_ID_PATTERN.pattern!r}")
    cage_name = _required_string(config, "physics_cage")
    visual_names = _string_list(config, "visual_objects", required=True)
    if cage_name in visual_names:
        raise SoftbodyExportError("physics_cage must not be included in visual_objects")
    transform = _matrix4(config)
    source_origin = _source_origin(config, transform)

    cage = blender.data.objects.get(cage_name)
    if cage is None or str(cage.type) != "MESH":
        raise SoftbodyExportError(f"physics_cage {cage_name!r} must name a mesh object")
    visual_objects: list[Any] = []
    for name in visual_names:
        item = blender.data.objects.get(name)
        if item is None or str(item.type) != "MESH":
            raise SoftbodyExportError(f"visual object {name!r} must name a mesh object")
        visual_objects.append(item)

    structure = _extract_structure(blender, cage, transform)
    required_roles = _string_list(config, "required_roles", required=False)
    unknown_roles = sorted(set(required_roles) - set(ROLE_GROUPS))
    if unknown_roles:
        raise SoftbodyExportError(f"required_roles contains unknown roles: {unknown_roles}")
    for role in required_roles:
        if not structure["roles"][role]:
            raise SoftbodyExportError(f"required vertex-group role {role!r} has no nodes")

    visual_format = _required_string(config, "visual_format").lower()
    if visual_format not in {"dae", "gltf"}:
        raise SoftbodyExportError("visual_format must be 'dae' or 'gltf'")
    visual_suffixes = {".dae"} if visual_format == "dae" else {".gltf"}
    visual_path = _absolute_output_path(config, "visual_path", visual_suffixes)
    manifest_path = _absolute_output_path(config, "manifest_path", {".json"})
    if visual_path == manifest_path:
        raise SoftbodyExportError("visual_path and manifest_path must differ")

    visual = _run_export(blender, config, visual_format, visual_path, visual_objects, transform)
    matrix_json = [list(row) for row in transform]
    manifest: JsonObject = {
        "schema": SCHEMA,
        "generator": "beamng-mcp-blender-softbody-export/1",
        "blender_version": str(blender.app.version_string),
        "asset": {
            "id": asset_id,
            "physics_cage": cage_name,
            "visual_objects": visual_names,
        },
        "coordinate_system": {
            "source": {"up_axis": "Z", "units": "m"},
            "target": {"up_axis": "Z", "units": "m"},
            "source_origin_world": list(source_origin),
            "mapped_source_origin": [0.0, 0.0, 0.0],
            "world_to_beamng": matrix_json,
        },
        "structure": structure,
        "visual": visual,
    }
    manifest_bytes = _canonical_json(manifest)
    _atomic_write(manifest_path, manifest_bytes)
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "visual_path": visual["path"],
        "visual_sha256": visual["sha256"],
        "visual_size": visual["size"],
        "node_count": len(structure["nodes"]),
        "edge_count": len(structure["edge_beams"]),
        "brace_panel_count": len(structure["quad_brace_panels"]),
        "triangle_count": len(structure["triangles"]),
        "bounds": structure["bounds"],
    }


__all__ = ["SCHEMA", "SoftbodyExportError", "export_beamng_softbody"]
