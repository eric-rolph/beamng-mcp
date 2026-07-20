"""Pure validation and deterministic compilation for ``beamng-structure-v1``.

This module does not read or write files.  The coordinator supplies digest and
size evidence obtained from a stable read of the finalized Collada artifact,
then commits the returned text assets through the confined mod workspace.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from itertools import combinations, pairwise
from typing import Any, Literal

from ..structural_models import (
    BasePolicy,
    BlenderStructuralManifest,
    Bounds3D,
    DAEArtifactEvidence,
    GeneratedTextAsset,
    JBeamBuildRequest,
    JBeamCompileResult,
    NodeMass,
    StructuralBuildRequest,
    StructuralBuildSummary,
    StructuralIssue,
    StructuralValidationResult,
    Vector3,
)

TRANSFORM_TOLERANCE_M = 1e-6
MIN_ELEMENT_LENGTH_M = 1e-4
MATERIAL_CATALOG_VERSION = "beamng-material-baselines-v1"
MAX_TOTAL_MASS_KG = 250_000.0


@dataclass(frozen=True, slots=True)
class MaterialPreset:
    """Conservative reference values which still require in-game tuning."""

    density_kg_m3: float
    node_material: str
    friction_coef: float
    beam_spring: float
    beam_damp: float
    beam_deform: float
    beam_strength: float
    ground_model: str


# Density values are conventional material references. Beam parameters are
# deliberately bounded starting points drawn from BeamNG's documented examples,
# not a claim that geometry using a preset is physically validated.
MATERIAL_PRESETS: dict[str, MaterialPreset] = {
    "steel": MaterialPreset(
        density_kg_m3=7_850.0,
        node_material="|NM_METAL",
        friction_coef=0.7,
        beam_spring=8_000_000.0,
        beam_damp=800.0,
        beam_deform=200_000.0,
        beam_strength=1_000_000.0,
        ground_model="metal",
    ),
    "concrete": MaterialPreset(
        density_kg_m3=2_400.0,
        node_material="|NM_ASPHALT",
        friction_coef=1.3,
        beam_spring=10_000_000.0,
        beam_damp=38_000.0,
        beam_deform=20_000.0,
        beam_strength=80_000.0,
        ground_model="asphalt",
    ),
    "wood": MaterialPreset(
        density_kg_m3=700.0,
        node_material="|NM_WOOD",
        friction_coef=0.8,
        beam_spring=2_000_000.0,
        beam_damp=250.0,
        beam_deform=50_000.0,
        beam_strength=100_000.0,
        ground_model="wood",
    ),
    "rubber": MaterialPreset(
        density_kg_m3=1_100.0,
        node_material="|NM_RUBBER",
        friction_coef=1.2,
        beam_spring=250_000.0,
        beam_damp=75.0,
        beam_deform=100_000.0,
        beam_strength=200_000.0,
        ground_model="rubber",
    ),
}


@dataclass(frozen=True, slots=True)
class _CompiledBeam:
    node_a: str
    node_b: str
    spring_scale: float = 1.0
    damp_scale: float = 1.0
    deform_scale: float = 1.0
    strength_scale: float = 1.0

    @property
    def key(self) -> tuple[str, str]:
        return tuple(sorted((self.node_a, self.node_b)))  # type: ignore[return-value]


class StructuralValidationError(ValueError):
    """Raised when compilation is attempted with an invalid domain manifest."""

    def __init__(self, result: StructuralValidationResult) -> None:
        self.result = result
        messages = "; ".join(
            f"{issue.code}: {issue.message}" for issue in result.issues if issue.severity == "error"
        )
        super().__init__(messages or "structural manifest validation failed")


def _vector_sub(left: Vector3, right: Vector3) -> Vector3:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _dot(left: Vector3, right: Vector3) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _length(value: Vector3) -> float:
    return math.sqrt(_dot(value, value))


def _distance(left: Vector3, right: Vector3) -> float:
    return _length(_vector_sub(left, right))


def _transform(matrix: tuple[tuple[float, ...], ...], point: Vector3) -> tuple[Vector3, float]:
    homogeneous = (point[0], point[1], point[2], 1.0)
    output = tuple(
        math.fsum(row[index] * homogeneous[index] for index in range(4)) for row in matrix
    )
    return (output[0], output[1], output[2]), output[3]


def _bounds(points: list[Vector3]) -> Bounds3D:
    return Bounds3D(
        minimum=tuple(min(point[axis] for point in points) for axis in range(3)),  # type: ignore[arg-type]
        maximum=tuple(max(point[axis] for point in points) for axis in range(3)),  # type: ignore[arg-type]
    )


def _bounds_match(left: Bounds3D, right: Bounds3D, tolerance: float) -> bool:
    return all(
        abs(actual - declared) <= tolerance
        for actual, declared in zip(
            (*left.minimum, *left.maximum),
            (*right.minimum, *right.maximum),
            strict=True,
        )
    )


def _point_in_bounds(point: Vector3, bounds: Bounds3D, tolerance: float) -> bool:
    return all(
        low - tolerance <= coordinate <= high + tolerance
        for coordinate, low, high in zip(point, bounds.minimum, bounds.maximum, strict=True)
    )


def _point_segment_distance(point: Vector3, start: Vector3, end: Vector3) -> float:
    segment = _vector_sub(end, start)
    length_squared = _dot(segment, segment)
    if length_squared == 0.0:
        return _distance(point, start)
    offset = _vector_sub(point, start)
    fraction = max(0.0, min(1.0, _dot(offset, segment) / length_squared))
    projection = (
        start[0] + segment[0] * fraction,
        start[1] + segment[1] * fraction,
        start[2] + segment[2] * fraction,
    )
    return _distance(point, projection)


def _rail_segments(node_ids: tuple[str, ...], *, looped: bool) -> tuple[tuple[str, str], ...]:
    segments = list(pairwise(node_ids))
    if looped:
        segments.append((node_ids[-1], node_ids[0]))
    return tuple(segments)


def _canonical_json(value: Any) -> str:
    """Serialize with one stable representation and no JBeam extensions."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _asset(
    path: str,
    media_type: Literal["application/json", "application/jbeam+json"],
    content: str,
) -> GeneratedTextAsset:
    encoded = content.encode("utf-8")
    if media_type == "application/json":
        typed_media_type: Literal["application/json", "application/jbeam+json"] = "application/json"
    else:
        typed_media_type = "application/jbeam+json"
    return GeneratedTextAsset(
        path=path,
        media_type=typed_media_type,
        content=content,
        sha256=hashlib.sha256(encoded).hexdigest(),
        size=len(encoded),
    )


def _compiled_beams(manifest: BlenderStructuralManifest) -> tuple[_CompiledBeam, ...]:
    by_key: dict[tuple[str, str], _CompiledBeam] = {}
    for edge in manifest.edges:
        beam = _CompiledBeam(
            edge.node_a,
            edge.node_b,
            spring_scale=edge.spring_scale,
            damp_scale=edge.damp_scale,
            deform_scale=edge.deform_scale,
            strength_scale=edge.strength_scale,
        )
        by_key.setdefault(beam.key, beam)
    for panel in manifest.brace_panels:
        for node_a, node_b in ((panel.nodes[0], panel.nodes[2]), (panel.nodes[1], panel.nodes[3])):
            beam = _CompiledBeam(node_a, node_b)
            by_key.setdefault(beam.key, beam)
    return tuple(by_key[key] for key in sorted(by_key))


def _total_mass(manifest: BlenderStructuralManifest) -> float:
    if manifest.mass.total_mass_kg is not None:
        return manifest.mass.total_mass_kg
    assert manifest.mass.closed_volume_m3 is not None
    preset = MATERIAL_PRESETS[manifest.material.preset]
    density = manifest.mass.density_kg_m3 or preset.density_kg_m3
    return manifest.mass.closed_volume_m3 * density


def _node_masses(manifest: BlenderStructuralManifest) -> tuple[NodeMass, ...]:
    total = _total_mass(manifest)
    base_ids = set(manifest.base.node_ids)
    ordered_nodes = sorted(manifest.nodes, key=lambda node: node.id)
    factors = [
        node.mass_scale * (manifest.base.mass_multiplier if node.id in base_ids else 1.0)
        for node in ordered_nodes
    ]
    factor_sum = math.fsum(factors)
    values = [total * factor / factor_sum for factor in factors]
    # Assign the binary floating-point residual deterministically so fsum of
    # emitted node weights equals the requested total mass.
    values[-1] += total - math.fsum(values)
    return tuple(
        NodeMass(node_id=node.id, mass_kg=mass)
        for node, mass in zip(ordered_nodes, values, strict=True)
    )


class StructuralManifestValidator:
    """Cross-field validator for geometry, mechanics, mass, and DAE identity."""

    def validate(
        self,
        manifest: BlenderStructuralManifest,
        dae: DAEArtifactEvidence,
    ) -> StructuralValidationResult:
        issues: list[StructuralIssue] = []

        def issue(
            severity: Literal["error", "warning"],
            code: str,
            message: str,
            subject: str | None = None,
        ) -> None:
            issues.append(
                StructuralIssue(
                    severity=severity,
                    code=code,
                    message=message,
                    subject=subject,
                )
            )

        tolerance = min(manifest.coordinates.tolerance_m, TRANSFORM_TOLERANCE_M)
        matrix = manifest.coordinates.source_world_to_beamng_vehicle
        rotation: tuple[Vector3, Vector3, Vector3] = (
            (matrix[0][0], matrix[0][1], matrix[0][2]),
            (matrix[1][0], matrix[1][1], matrix[1][2]),
            (matrix[2][0], matrix[2][1], matrix[2][2]),
        )
        if any(
            abs(matrix[3][index] - expected) > tolerance
            for index, expected in enumerate((0, 0, 0, 1))
        ):
            issue("error", "transform_affine_row", "transform last row must be [0, 0, 0, 1]")
        for row_index, row in enumerate(rotation):
            if abs(_dot(row, row) - 1.0) > tolerance:
                issue(
                    "error",
                    "transform_not_rigid",
                    "transform rotation rows must have unit length",
                    f"row:{row_index}",
                )
        for first, second in ((0, 1), (0, 2), (1, 2)):
            if abs(_dot(rotation[first], rotation[second])) > tolerance:
                issue(
                    "error",
                    "transform_not_orthogonal",
                    "transform rotation rows must be mutually orthogonal",
                    f"rows:{first},{second}",
                )
        determinant = _dot(rotation[0], _cross(rotation[1], rotation[2]))
        if abs(determinant - 1.0) > tolerance:
            issue(
                "error",
                "transform_handedness",
                "transform must be a proper rigid rotation with determinant +1",
            )
        transformed_up = (matrix[0][2], matrix[1][2], matrix[2][2])
        if _distance(transformed_up, (0.0, 0.0, 1.0)) > tolerance:
            issue(
                "error",
                "transform_not_z_up",
                "Blender +Z must remain BeamNG +Z",
            )

        transformed_origin, origin_w = _transform(matrix, manifest.coordinates.source_origin_world)
        if abs(origin_w - 1.0) > tolerance or _length(transformed_origin) > tolerance:
            issue(
                "error",
                "origin_not_local",
                "Blender source origin must transform to BeamNG vehicle origin",
            )

        by_id = {node.id: node for node in manifest.nodes}
        source_vertices: dict[tuple[str, int], str] = {}
        for node in manifest.nodes:
            transformed, weight = _transform(matrix, node.source_world_position)
            if (
                abs(weight - 1.0) > tolerance
                or _distance(transformed, node.beamng_position) > tolerance
            ):
                issue(
                    "error",
                    "coordinate_mismatch",
                    "beamng_position does not match the declared source transform within 1e-6 m",
                    node.id,
                )
            if not _point_in_bounds(node.beamng_position, manifest.visual.bounds, tolerance):
                issue(
                    "error",
                    "node_outside_visual_bounds",
                    "physics node lies outside the DAE bounds",
                    node.id,
                )
            if node.source_vertex_index is not None:
                source_key = (node.source_object, node.source_vertex_index)
                previous_node = source_vertices.get(source_key)
                if previous_node is not None:
                    issue(
                        "error",
                        "duplicate_source_vertex",
                        "two physics nodes cite the same Blender source vertex",
                        f"{previous_node},{node.id}",
                    )
                source_vertices[source_key] = node.id

        for first_node, second_node in combinations(manifest.nodes, 2):
            if (
                _distance(first_node.beamng_position, second_node.beamng_position)
                < MIN_ELEMENT_LENGTH_M
            ):
                issue(
                    "error",
                    "duplicate_node_position",
                    "distinct physics nodes must not occupy the same position",
                    f"{first_node.id},{second_node.id}",
                )
        actual_bounds = _bounds([node.beamng_position for node in manifest.nodes])
        if not _bounds_match(actual_bounds, manifest.bounds, tolerance):
            issue(
                "error",
                "structural_bounds_mismatch",
                "declared structural bounds do not match transformed node coordinates",
            )

        if dae.path != manifest.visual.path:
            issue("error", "dae_path_mismatch", "DAE evidence path does not match the manifest")
        if dae.sha256 != manifest.visual.sha256:
            issue("error", "dae_hash_mismatch", "DAE evidence SHA-256 does not match the manifest")
        if dae.size != manifest.visual.size:
            issue("error", "dae_size_mismatch", "DAE evidence size does not match the manifest")
        expected_prefix = f"vehicles/{manifest.mod_name}/"
        if not manifest.visual.path.startswith(expected_prefix):
            issue(
                "error",
                "dae_wrong_vehicle_root",
                f"DAE path must be below {expected_prefix}",
                manifest.visual.path,
            )
        if not (
            manifest.part_name == manifest.mod_name
            or manifest.part_name.startswith(f"{manifest.mod_name}_")
        ):
            issue(
                "error",
                "part_not_namespaced",
                "part_name must equal mod_name or start with '<mod_name>_'",
            )
        if not (
            manifest.material.material_id == manifest.mod_name
            or manifest.material.material_id.startswith(f"{manifest.mod_name}_")
        ):
            issue(
                "error",
                "material_not_namespaced",
                "material_id must equal mod_name or start with '<mod_name>_'",
            )
        for subject, value in (
            ("visual.mesh_name", manifest.visual.mesh_name),
            ("visual.material_name", manifest.visual.material_name),
        ):
            if value != manifest.mod_name and not value.startswith(f"{manifest.mod_name}_"):
                issue(
                    "error",
                    "visual_name_not_namespaced",
                    "runtime mesh and material names must be mod-namespaced",
                    subject,
                )

        explicit_edges: set[tuple[str, str]] = set()
        for edge in manifest.edges:
            edge_key = (min(edge.node_a, edge.node_b), max(edge.node_a, edge.node_b))
            if edge.node_a not in by_id or edge.node_b not in by_id:
                issue(
                    "error",
                    "unknown_edge_node",
                    "edge references an unknown node",
                    str(edge_key),
                )
                continue
            if edge_key in explicit_edges:
                issue(
                    "error",
                    "duplicate_edge",
                    "duplicate undirected structural edge",
                    str(edge_key),
                )
            explicit_edges.add(edge_key)
            if (
                _distance(by_id[edge.node_a].beamng_position, by_id[edge.node_b].beamng_position)
                < MIN_ELEMENT_LENGTH_M
            ):
                issue("error", "short_edge", "edge is shorter than 0.1 mm", str(edge_key))

        for panel in manifest.brace_panels:
            missing = sorted(set(panel.nodes) - by_id.keys())
            if missing:
                issue(
                    "error",
                    "unknown_brace_node",
                    f"brace panel references unknown nodes: {', '.join(missing)}",
                    panel.id,
                )

        beams = _compiled_beams(manifest)
        beam_keys = {beam.key for beam in beams}
        triangle_keys: set[tuple[str, str, str]] = set()
        for triangle in manifest.triangles:
            if any(node_id not in by_id for node_id in triangle.nodes):
                issue(
                    "error",
                    "unknown_triangle_node",
                    "triangle references an unknown node",
                    str(triangle.nodes),
                )
                continue
            interior_nodes = [node_id for node_id in triangle.nodes if not by_id[node_id].surface]
            if interior_nodes:
                issue(
                    "error",
                    "triangle_interior_node",
                    "collision triangles may reference only surface nodes",
                    ",".join(interior_nodes),
                )
            sorted_triangle_nodes = sorted(triangle.nodes)
            triangle_key = (
                sorted_triangle_nodes[0],
                sorted_triangle_nodes[1],
                sorted_triangle_nodes[2],
            )
            if triangle_key in triangle_keys:
                issue(
                    "error",
                    "duplicate_triangle",
                    "duplicate collision triangle regardless of winding",
                    str(triangle.nodes),
                )
            triangle_keys.add(triangle_key)
            triangle_first, triangle_second, triangle_third = (
                by_id[node_id].beamng_position for node_id in triangle.nodes
            )
            doubled_area = _length(
                _cross(
                    _vector_sub(triangle_second, triangle_first),
                    _vector_sub(triangle_third, triangle_first),
                )
            )
            if doubled_area <= tolerance * tolerance:
                issue(
                    "error",
                    "degenerate_triangle",
                    "collision triangle has zero or near-zero area",
                    str(triangle.nodes),
                )
            sides = (
                tuple(sorted((triangle.nodes[0], triangle.nodes[1]))),
                tuple(sorted((triangle.nodes[1], triangle.nodes[2]))),
                tuple(sorted((triangle.nodes[2], triangle.nodes[0]))),
            )
            missing_sides = [side for side in sides if side not in beam_keys]
            if missing_sides:
                issue(
                    "error",
                    "triangle_side_unbeamed",
                    "every collision-triangle side must be an explicit or brace-generated beam",
                    str(missing_sides),
                )

        adjacency = {node_id: set[str]() for node_id in by_id}
        for beam in beams:
            if beam.node_a in adjacency and beam.node_b in adjacency:
                adjacency[beam.node_a].add(beam.node_b)
                adjacency[beam.node_b].add(beam.node_a)
        visited: set[str] = set()
        pending = [next(iter(sorted(by_id)))]
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(sorted(adjacency[current] - visited, reverse=True))
        disconnected = sorted(by_id.keys() - visited)
        if disconnected:
            issue(
                "error",
                "disconnected_structure",
                f"nodes are disconnected from the beam graph: {', '.join(disconnected)}",
            )

        reference = manifest.refnodes
        missing_references = sorted(
            {reference.ref, reference.back, reference.left, reference.up} - by_id.keys()
        )
        if missing_references:
            issue(
                "error",
                "unknown_refnode",
                f"reference frame uses unknown nodes: {', '.join(missing_references)}",
            )
        else:
            origin = by_id[reference.ref].beamng_position
            back = _vector_sub(by_id[reference.back].beamng_position, origin)
            left = _vector_sub(by_id[reference.left].beamng_position, origin)
            up = _vector_sub(by_id[reference.up].beamng_position, origin)
            axis_checks = (
                (back, 1, "back", "+Y"),
                (left, 0, "left", "+X"),
                (up, 2, "up", "+Z"),
            )
            for vector, axis, name, expected in axis_checks:
                off_axis = [abs(value) for index, value in enumerate(vector) if index != axis]
                if vector[axis] <= tolerance or any(value > tolerance for value in off_axis):
                    issue(
                        "error",
                        "refnode_axis_mismatch",
                        f"{name} refnode must lie exactly along BeamNG {expected}",
                        name,
                    )

        base = manifest.base
        if base.mode != "free":
            missing_base = sorted(set(base.node_ids) - by_id.keys())
            if missing_base:
                issue(
                    "error",
                    "unknown_base_node",
                    f"base references unknown nodes: {', '.join(missing_base)}",
                )
            else:
                minimum_z = actual_bounds.minimum[2]
                for node_id in base.node_ids:
                    if abs(by_id[node_id].beamng_position[2] - minimum_z) > tolerance:
                        issue(
                            "error",
                            "base_not_ground_plane",
                            "base node must lie on the structure's minimum-Z plane",
                            node_id,
                        )
                points = [by_id[node_id].beamng_position for node_id in base.node_ids]
                origin = points[0]
                has_area = any(
                    abs(
                        (first[0] - origin[0]) * (second[1] - origin[1])
                        - (first[1] - origin[1]) * (second[0] - origin[0])
                    )
                    > tolerance * tolerance
                    for index, first in enumerate(points[1:], start=1)
                    for second in points[index + 1 :]
                )
                if not has_area:
                    issue(
                        "error",
                        "base_collinear",
                        "base needs at least three non-collinear nodes in the ground plane",
                    )
            if base.mode == "fixed":
                issue(
                    "warning",
                    "fixed_nodes_disable_dynamic_collision",
                    "BeamNG fixed nodes do not participate in dynamic collision; "
                    "ensure other nodes cover the exterior",
                )

        hydro_keys: set[tuple[str, str, str]] = set()
        for hydro in manifest.hydros:
            if hydro.node_a not in by_id or hydro.node_b not in by_id:
                issue("error", "unknown_hydro_node", "hydro references an unknown node")
            hydro_key = (
                min(hydro.node_a, hydro.node_b),
                max(hydro.node_a, hydro.node_b),
                hydro.input_source,
            )
            if hydro_key in hydro_keys:
                issue("error", "duplicate_hydro", "duplicate hydro definition", str(hydro_key))
            hydro_keys.add(hydro_key)

        rails = {rail.name: rail for rail in manifest.rails}
        for rail in manifest.rails:
            missing = sorted(set(rail.node_ids) - by_id.keys())
            if missing:
                issue(
                    "error",
                    "unknown_rail_node",
                    f"rail references unknown nodes: {', '.join(missing)}",
                    rail.name,
                )
            for rail_first, rail_second in _rail_segments(rail.node_ids, looped=rail.looped):
                if (
                    rail_first in by_id
                    and rail_second in by_id
                    and _distance(
                        by_id[rail_first].beamng_position,
                        by_id[rail_second].beamng_position,
                    )
                    < MIN_ELEMENT_LENGTH_M
                ):
                    issue(
                        "error",
                        "short_rail_segment",
                        "rail segment is shorter than 0.1 mm",
                        rail.name,
                    )

        slide_keys: set[tuple[str, str]] = set()
        for slide in manifest.slidenodes:
            key = (slide.node_id, slide.rail_name)
            if key in slide_keys:
                issue("error", "duplicate_slidenode", "duplicate slidenode definition", str(key))
            slide_keys.add(key)
            if slide.node_id not in by_id:
                issue(
                    "error", "unknown_slidenode", "slidenode references an unknown node", str(key)
                )
                continue
            selected_rail = rails.get(slide.rail_name)
            if selected_rail is None:
                issue(
                    "error", "unknown_slide_rail", "slidenode references an unknown rail", str(key)
                )
                continue
            if slide.node_id in selected_rail.node_ids:
                issue(
                    "error",
                    "slidenode_is_rail_node",
                    "a slidenode cannot also be one of its rail's link nodes",
                    str(key),
                )
            if all(node_id in by_id for node_id in selected_rail.node_ids):
                point = by_id[slide.node_id].beamng_position
                rail_distance = min(
                    _point_segment_distance(
                        point,
                        by_id[segment_first].beamng_position,
                        by_id[segment_second].beamng_position,
                    )
                    for segment_first, segment_second in _rail_segments(
                        selected_rail.node_ids,
                        looped=selected_rail.looped,
                    )
                )
                permitted_distance = max(tolerance, slide.tolerance_m)
                if rail_distance > permitted_distance:
                    issue(
                        "error",
                        "slidenode_off_rail",
                        "slidenode is not aligned to its rail within declared tolerance",
                        str(key),
                    )

        masses = _node_masses(manifest)
        total_mass = _total_mass(manifest)
        if total_mass > MAX_TOTAL_MASS_KG:
            issue(
                "error",
                "total_mass_exceeded",
                f"computed total mass exceeds the {MAX_TOTAL_MASS_KG:g} kg safety limit",
            )
        for node_mass in masses:
            if node_mass.mass_kg < 0.01:
                issue(
                    "warning",
                    "very_light_node",
                    "node mass below 0.01 kg can destabilize a stiff structure",
                    node_mass.node_id,
                )
            if node_mass.mass_kg > 25_000.0:
                issue(
                    "warning",
                    "very_heavy_node",
                    "node mass above 25,000 kg needs explicit in-game stability testing",
                    node_mass.node_id,
                )

        severity_order = {"error": 0, "warning": 1}
        ordered_issues = tuple(
            sorted(
                issues,
                key=lambda item: (
                    severity_order[item.severity],
                    item.code,
                    item.subject or "",
                    item.message,
                ),
            )
        )
        return StructuralValidationResult(
            valid=not any(item.severity == "error" for item in ordered_issues),
            issues=ordered_issues,
            total_mass_kg=total_mass,
            node_masses=masses,
            generated_beam_count=len(beams),
        )


class JBeamCompiler:
    """Compile a validated manifest into deterministic UTF-8 vehicle artifacts."""

    def __init__(self, validator: StructuralManifestValidator | None = None) -> None:
        self.validator = validator or StructuralManifestValidator()

    def compile(self, request: JBeamBuildRequest) -> JBeamCompileResult:
        manifest = request.manifest
        validation = self.validator.validate(manifest, request.dae)
        if not validation.valid:
            raise StructuralValidationError(validation)

        preset = MATERIAL_PRESETS[manifest.material.preset]
        masses = {item.node_id: item.mass_kg for item in validation.node_masses}
        base_ids = set(manifest.base.node_ids)
        beams = _compiled_beams(manifest)
        vehicle_root = f"vehicles/{manifest.mod_name}"

        node_rows: list[list[Any]] = [["id", "posX", "posY", "posZ"]]
        for node in sorted(manifest.nodes, key=lambda item: item.id):
            options: dict[str, Any] = {
                "collision": node.surface,
                "frictionCoef": preset.friction_coef,
                "group": node.group,
                "nodeMaterial": preset.node_material,
                "nodeWeight": masses[node.id],
                "selfCollision": False,
                "staticCollision": node.surface,
            }
            if manifest.base.mode == "fixed" and node.id in base_ids:
                options.update({"collision": False, "fixed": True, "selfCollision": False})
            node_rows.append([node.id, *node.beamng_position, options])

        beam_rows: list[list[Any]] = [["id1:", "id2:"]]
        for beam in beams:
            beam_rows.append(
                [
                    beam.node_a,
                    beam.node_b,
                    {
                        "beamDamp": preset.beam_damp * beam.damp_scale,
                        "beamDeform": preset.beam_deform * beam.deform_scale,
                        "beamSpring": preset.beam_spring * beam.spring_scale,
                        "beamStrength": preset.beam_strength * beam.strength_scale,
                    },
                ]
            )

        triangle_rows: list[list[Any]] = [["id1:", "id2:", "id3:"]]
        for triangle in sorted(manifest.triangles, key=lambda item: item.nodes):
            triangle_rows.append(
                [
                    *triangle.nodes,
                    {"groundModel": triangle.ground_model or preset.ground_model},
                ]
            )

        groups = sorted({node.group for node in manifest.nodes})
        part: dict[str, Any] = {
            "beams": beam_rows,
            "flexbodies": [
                ["mesh", "[group]:"],
                [manifest.visual.mesh_name, groups],
            ],
            "information": {
                "authors": manifest.author,
                "name": manifest.display_name,
            },
            "nodes": node_rows,
            "refNodes": [
                ["ref:", "back:", "left:", "up:"],
                [
                    manifest.refnodes.ref,
                    manifest.refnodes.back,
                    manifest.refnodes.left,
                    manifest.refnodes.up,
                ],
            ],
            "slotType": "main",
            "triangles": triangle_rows,
        }
        if manifest.hydros:
            hydro_rows: list[list[Any]] = [["id1:", "id2:"]]
            for hydro in sorted(
                manifest.hydros,
                key=lambda item: (item.node_a, item.node_b, item.input_source),
            ):
                hydro_rows.append(
                    [
                        hydro.node_a,
                        hydro.node_b,
                        {
                            "beamDamp": preset.beam_damp * hydro.damp_scale,
                            "beamSpring": preset.beam_spring * hydro.spring_scale,
                            "factor": hydro.factor,
                            "inRate": hydro.in_rate,
                            "inputSource": hydro.input_source,
                            "outRate": hydro.out_rate,
                        },
                    ]
                )
            part["hydros"] = hydro_rows
        if manifest.rails:
            part["rails"] = {
                rail.name: {
                    "broken:": [],
                    "capped": rail.capped,
                    "links:": list(rail.node_ids),
                    "looped": rail.looped,
                }
                for rail in sorted(manifest.rails, key=lambda item: item.name)
            }
        if manifest.slidenodes:
            slide_rows: list[list[Any]] = [
                [
                    "id:",
                    "railName",
                    "attached",
                    "fixToRail",
                    "tolerance",
                    "spring",
                    "strength",
                    "capStrength",
                ]
            ]
            for slide in sorted(
                manifest.slidenodes,
                key=lambda item: (item.node_id, item.rail_name),
            ):
                slide_rows.append(
                    [
                        slide.node_id,
                        slide.rail_name,
                        slide.attached,
                        slide.fix_to_rail,
                        slide.tolerance_m,
                        slide.spring,
                        slide.strength,
                        slide.cap_strength,
                    ]
                )
            part["slidenodes"] = slide_rows

        jbeam_text = _canonical_json({manifest.part_name: part})
        jbeam = _asset(
            f"{vehicle_root}/{manifest.part_name}.jbeam",
            "application/jbeam+json",
            jbeam_text,
        )

        materials_text = _canonical_json(
            {
                manifest.material.material_id: {
                    "Stages": [
                        {
                            "baseColorFactor": list(manifest.material.base_color),
                            "metallicFactor": manifest.material.metallic,
                            "roughnessFactor": manifest.material.roughness,
                        }
                    ],
                    "class": "Material",
                    "mapTo": manifest.visual.material_name,
                    "name": manifest.material.material_id,
                    "version": 1.5,
                }
            }
        )
        materials = _asset(
            f"{vehicle_root}/main.materials.json",
            "application/json",
            materials_text,
        )

        info_text = _canonical_json(
            {
                "Author": manifest.author,
                "Name": manifest.display_name,
                "Type": "Prop",
                "default_pc": manifest.part_name,
            }
        )
        vehicle_info = _asset(f"{vehicle_root}/info.json", "application/json", info_text)

        configuration_pc = _asset(
            f"{vehicle_root}/{manifest.part_name}.pc",
            "application/json",
            _canonical_json(
                {
                    "format": 2,
                    "mainPartName": manifest.part_name,
                    "model": manifest.mod_name,
                    "parts": {},
                }
            ),
        )
        configuration_info = _asset(
            f"{vehicle_root}/info_{manifest.part_name}.json",
            "application/json",
            _canonical_json(
                {
                    "Configuration": manifest.display_name,
                    "Weight": validation.total_mass_kg,
                }
            ),
        )

        manifest_text = _canonical_json(
            manifest.model_dump(mode="json", by_alias=True, exclude_none=False)
        )
        manifest_sha256 = _sha256_text(manifest_text)
        summary = StructuralBuildSummary(
            node_count=len(manifest.nodes),
            beam_count=len(beams),
            triangle_count=len(manifest.triangles),
            hydro_count=len(manifest.hydros),
            rail_count=len(manifest.rails),
            slidenode_count=len(manifest.slidenodes),
            total_mass_kg=validation.total_mass_kg,
            bounds=manifest.bounds,
        )
        provenance_text = _canonical_json(
            {
                "compiler": {
                    "materialCatalog": MATERIAL_CATALOG_VERSION,
                    "name": "beamng-mcp",
                },
                "coordinateContract": manifest.coordinates.model_dump(mode="json"),
                "dae": request.dae.model_dump(mode="json"),
                "manifest": manifest.model_dump(mode="json", by_alias=True, exclude_none=False),
                "manifestSchema": "beamng-structure-v1",
                "manifestSha256": manifest_sha256,
                "outputs": {
                    asset.path: {"sha256": asset.sha256, "size": asset.size}
                    for asset in (
                        jbeam,
                        materials,
                        vehicle_info,
                        configuration_pc,
                        configuration_info,
                    )
                },
                "schema": "beamng-structure-provenance-v1",
                "summary": summary.model_dump(mode="json"),
            }
        )
        provenance = _asset(
            f"{vehicle_root}/{manifest.part_name}.structure.json",
            "application/json",
            provenance_text,
        )

        return JBeamCompileResult(
            manifest_sha256=manifest_sha256,
            dae_sha256=request.dae.sha256,
            validation=validation,
            summary=summary,
            jbeam=jbeam,
            materials=materials,
            vehicle_info=vehicle_info,
            configuration_pc=configuration_pc,
            configuration_info=configuration_info,
            provenance=provenance,
        )

    def compile_manifest(
        self,
        manifest: BlenderStructuralManifest,
        dae: DAEArtifactEvidence,
        build: StructuralBuildRequest,
    ) -> JBeamCompileResult:
        """Apply coordinator policy without changing any geometric evidence.

        Coordinates, topology, bounds, visual identity, and reference nodes are
        copied unchanged from the staged Blender manifest.  Human-facing
        metadata, material/mass policy, grounding mode, and explicitly typed
        mechanisms come from the confirmed build request.
        """

        if build.mod_name != manifest.mod_name:
            raise ValueError("build mod_name does not match the staged manifest")
        visual_stem = manifest.visual.path.rsplit("/", 1)[-1].removesuffix(".dae")
        if build.asset_name != visual_stem:
            raise ValueError("build asset_name does not match the staged DAE filename")

        if build.mass.total_mass_kg is None:
            measured_volume = manifest.mass.closed_volume_m3
            requested_volume = build.mass.closed_volume_m3
            if measured_volume is None or requested_volume is None:
                raise ValueError("volume-based mass requires a closed measured Blender cage")
            if abs(measured_volume - requested_volume) > manifest.coordinates.tolerance_m:
                raise ValueError(
                    "volume-based mass must use the measured Blender cage volume exactly"
                )

        if not build.grounded:
            base = BasePolicy(mode="free", node_ids=(), mass_multiplier=1.0)
        else:
            if manifest.base.mode == "free" or len(manifest.base.node_ids) < 3:
                raise ValueError("a grounded build requires explicit base nodes in Blender")
            base = BasePolicy(
                mode="fixed" if build.fixed else "weighted",
                node_ids=manifest.base.node_ids,
                mass_multiplier=manifest.base.mass_multiplier,
            )

        effective_manifest = BlenderStructuralManifest.model_validate(
            {
                **manifest.model_dump(mode="python", by_alias=True),
                "display_name": build.title,
                "author": build.author,
                "material": build.material.model_dump(mode="python"),
                "mass": build.mass.model_dump(mode="python"),
                "base": base.model_dump(mode="python"),
                "hydros": tuple(item.model_dump(mode="python") for item in build.hydros),
                "rails": tuple(item.model_dump(mode="python") for item in build.rails),
                "slidenodes": tuple(item.model_dump(mode="python") for item in build.slidenodes),
            }
        )
        return self.compile(JBeamBuildRequest(manifest=effective_manifest, dae=dae))


def validate_structure(request: JBeamBuildRequest) -> StructuralValidationResult:
    """Validate a request without compiling files."""

    return StructuralManifestValidator().validate(request.manifest, request.dae)


def compile_structure(request: JBeamBuildRequest) -> JBeamCompileResult:
    """Compile one manifest using the default deterministic compiler."""

    return JBeamCompiler().compile(request)


__all__ = [
    "MATERIAL_CATALOG_VERSION",
    "MATERIAL_PRESETS",
    "JBeamCompiler",
    "MaterialPreset",
    "StructuralManifestValidator",
    "StructuralValidationError",
    "compile_structure",
    "validate_structure",
]
