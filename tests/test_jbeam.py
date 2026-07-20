from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from beamng_mcp.config import WorkspaceSettings
from beamng_mcp.errors import WorkspaceError
from beamng_mcp.services.jbeam import JBeamCompiler, StructuralValidationError
from beamng_mcp.services.mods import ModWorkspace
from beamng_mcp.services.staging import StagePaths
from beamng_mcp.services.structural import StructuralModService
from beamng_mcp.structural_models import (
    BasePolicy,
    BlenderStructuralManifest,
    Bounds3D,
    CoordinateContract,
    DAEArtifactEvidence,
    HydroSpec,
    JBeamBuildRequest,
    MassInputs,
    RailSpec,
    ReferenceNodes,
    SlideNodeSpec,
    StructuralBuildRequest,
    StructuralEdge,
    StructuralMaterial,
    StructuralNode,
    StructuralTriangle,
    VisualDAE,
)


def tiny_dae() -> bytes:
    return b"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit meter="1" name="meter"/><up_axis>Z_UP</up_axis></asset>
  <library_materials><material id="demo_mat" name="demo_mat"/></library_materials>
  <library_geometries><geometry id="demo_mesh-geometry" name="demo_mesh"><mesh>
    <source id="demo_mesh-positions"><float_array id="demo_mesh-positions-array" count="12">
      0 0 0  0 1 0  1 0 0  0 0 1
    </float_array><technique_common><accessor source="#demo_mesh-positions-array"
      count="4" stride="3"><param name="X" type="float"/><param name="Y" type="float"/>
      <param name="Z" type="float"/></accessor></technique_common></source>
    <vertices id="demo_mesh-vertices"><input semantic="POSITION"
      source="#demo_mesh-positions"/></vertices>
    <triangles count="4" material="demo_mat"><input semantic="VERTEX"
      source="#demo_mesh-vertices" offset="0"/><p>0 2 1 0 1 3 0 3 2 1 2 3</p></triangles>
  </mesh></geometry></library_geometries>
  <library_visual_scenes><visual_scene id="Scene" name="Scene"><node id="demo_mesh"
    name="demo_mesh"><instance_geometry url="#demo_mesh-geometry"/></node>
  </visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
"""


def tetra_manifest(dae: bytes | None = None) -> BlenderStructuralManifest:
    dae = dae or tiny_dae()
    positions = {
        "n_ref": (0.0, 0.0, 0.0),
        "n_back": (0.0, 1.0, 0.0),
        "n_left": (1.0, 0.0, 0.0),
        "n_up": (0.0, 0.0, 1.0),
    }
    nodes = tuple(
        StructuralNode(
            id=node_id,
            source_object="demo_cage",
            source_vertex_index=index,
            source_world_position=position,
            beamng_position=position,
            group="demo_group",
        )
        for index, (node_id, position) in enumerate(positions.items())
    )
    pairs = (
        ("n_ref", "n_back"),
        ("n_ref", "n_left"),
        ("n_ref", "n_up"),
        ("n_back", "n_left"),
        ("n_back", "n_up"),
        ("n_left", "n_up"),
    )
    return BlenderStructuralManifest(
        mod_name="demo",
        part_name="demo",
        display_name="Demo Soft Body",
        author="Test Author",
        coordinates=CoordinateContract(
            source_origin_world=(0.0, 0.0, 0.0),
            source_world_to_beamng_vehicle=(
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
        ),
        bounds=Bounds3D(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)),
        visual=VisualDAE(
            path="vehicles/demo/demo.dae",
            sha256=hashlib.sha256(dae).hexdigest(),
            size=len(dae),
            mesh_name="demo_mesh",
            material_name="demo_mat",
            bounds=Bounds3D(minimum=(0.0, 0.0, 0.0), maximum=(1.0, 1.0, 1.0)),
        ),
        material=StructuralMaterial(preset="steel", material_id="demo_material"),
        mass=MassInputs(total_mass_kg=100.0),
        nodes=nodes,
        edges=tuple(StructuralEdge(node_a=left, node_b=right) for left, right in pairs),
        triangles=(
            StructuralTriangle(nodes=("n_ref", "n_left", "n_back")),
            StructuralTriangle(nodes=("n_ref", "n_back", "n_up")),
            StructuralTriangle(nodes=("n_ref", "n_up", "n_left")),
            StructuralTriangle(nodes=("n_back", "n_left", "n_up")),
        ),
        refnodes=ReferenceNodes(ref="n_ref", back="n_back", left="n_left", up="n_up"),
        base=BasePolicy(
            mode="weighted",
            node_ids=("n_ref", "n_back", "n_left"),
            mass_multiplier=4.0,
        ),
    )


def evidence(manifest: BlenderStructuralManifest) -> DAEArtifactEvidence:
    return DAEArtifactEvidence(
        path=manifest.visual.path,
        sha256=manifest.visual.sha256,
        size=manifest.visual.size,
    )


def raw_export_manifest(dae: bytes) -> dict[str, object]:
    nodes = [
        {
            "id": "n_back",
            "position": [0.0, 1.0, 0.0],
            "source_object": "demo_cage",
            "source_vertex_index": 1,
            "source_world_position": [0.0, 1.0, 0.0],
            "roles": ["beamng_back", "beamng_base"],
        },
        {
            "id": "n_left",
            "position": [1.0, 0.0, 0.0],
            "source_object": "demo_cage",
            "source_vertex_index": 2,
            "source_world_position": [1.0, 0.0, 0.0],
            "roles": ["beamng_base", "beamng_left"],
        },
        {
            "id": "n_ref",
            "position": [0.0, 0.0, 0.0],
            "source_object": "demo_cage",
            "source_vertex_index": 0,
            "source_world_position": [0.0, 0.0, 0.0],
            "roles": ["beamng_base", "beamng_ref"],
        },
        {
            "id": "n_up",
            "position": [0.0, 0.0, 1.0],
            "source_object": "demo_cage",
            "source_vertex_index": 3,
            "source_world_position": [0.0, 0.0, 1.0],
            "roles": ["beamng_up"],
        },
    ]
    nodes.sort(key=lambda item: int(item["source_vertex_index"]))
    pairs = [
        ["n_back", "n_left"],
        ["n_back", "n_ref"],
        ["n_back", "n_up"],
        ["n_left", "n_ref"],
        ["n_left", "n_up"],
        ["n_ref", "n_up"],
    ]
    edge_beams = [{"id": f"edge:{pair[0]}|{pair[1]}", "nodes": pair} for pair in pairs]
    triangles = [
        {"id": "triangle:n_ref|n_left|n_back", "nodes": ["n_ref", "n_left", "n_back"]},
        {"id": "triangle:n_ref|n_back|n_up", "nodes": ["n_ref", "n_back", "n_up"]},
        {"id": "triangle:n_ref|n_up|n_left", "nodes": ["n_ref", "n_up", "n_left"]},
        {"id": "triangle:n_back|n_left|n_up", "nodes": ["n_back", "n_left", "n_up"]},
    ]
    roles = {
        "beamng_back": ["n_back"],
        "beamng_base": ["n_back", "n_left", "n_ref"],
        "beamng_interior": [],
        "beamng_left": ["n_left"],
        "beamng_ref": ["n_ref"],
        "beamng_up": ["n_up"],
    }
    topology = {
        "node_ids": ["n_back", "n_left", "n_ref", "n_up"],
        "edge_beams": pairs,
        "brace_beams": [],
        "quad_brace_panels": [],
        "triangles": [item["nodes"] for item in triangles],
        "roles": roles,
    }

    def canonical(value: object) -> bytes:
        return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

    topology_sha256 = hashlib.sha256(canonical(topology)).hexdigest()
    geometry = {
        "topology_sha256": topology_sha256,
        "nodes": nodes,
        "bounds": {
            "source_world": {
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 1.0],
                "dimensions": [1.0, 1.0, 1.0],
            },
            "beamng": {
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 1.0],
                "dimensions": [1.0, 1.0, 1.0],
            },
        },
        "closed": True,
        "winding_consistent": True,
        "volume_m3": 1.0 / 6.0,
    }
    geometry_sha256 = hashlib.sha256(canonical(geometry)).hexdigest()
    return {
        "schema": "beamng-blender-handoff-v1",
        "generator": "beamng-mcp-blender-softbody-export/1",
        "blender_version": "5.2.0",
        "asset": {
            "id": "demo",
            "physics_cage": "demo_cage",
            "visual_objects": ["demo_mesh"],
        },
        "coordinate_system": {
            "source": {"up_axis": "Z", "units": "m"},
            "target": {"up_axis": "Z", "units": "m"},
            "source_origin_world": [0.0, 0.0, 0.0],
            "mapped_source_origin": [0.0, 0.0, 0.0],
            "world_to_beamng": [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
        },
        "structure": {
            "nodes": nodes,
            "edge_beams": edge_beams,
            "brace_beams": [],
            "quad_brace_panels": [],
            "triangles": triangles,
            "roles": roles,
            "bounds": {
                "source_world": {
                    "min": [0.0, 0.0, 0.0],
                    "max": [1.0, 1.0, 1.0],
                    "dimensions": [1.0, 1.0, 1.0],
                },
                "beamng": {
                    "min": [0.0, 0.0, 0.0],
                    "max": [1.0, 1.0, 1.0],
                    "dimensions": [1.0, 1.0, 1.0],
                },
            },
            "closed": True,
            "winding_consistent": True,
            "volume_m3": 1.0 / 6.0,
            "topology_sha256": topology_sha256,
            "geometry_sha256": geometry_sha256,
        },
        "visual": {
            "format": "dae",
            "debug_only": False,
            "objects": ["demo_mesh"],
            "coordinates_baked_to_beamng": True,
            "object_transform": "identity",
            "path": "C:/approved/visual.dae",
            "operator": "wm.collada_export",
            "sha256": hashlib.sha256(dae).hexdigest(),
            "size": len(dae),
            "z_up": True,
            "units": "m",
        },
    }


def staged_raw_handoff(
    service: StructuralModService,
    dae: bytes,
    raw_manifest: dict[str, object],
) -> StagePaths:
    stage = service.inbox.create(
        mod_name="demo",
        asset_name="demo",
        visual_format="dae",
        helper_source=b"# reviewed helper\n",
        runner_source=b"# reviewed runner\n",
        request_contract={
            "asset_id": "demo",
            "physics_cage": "demo_cage",
            "visual_objects": ["demo_mesh"],
            "world_to_beamng": [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            "source_origin_world": [0.0, 0.0, 0.0],
            "tolerance_m": 1e-6,
        },
    )
    stage.visual.write_bytes(dae)
    stage.manifest.write_text(
        json.dumps(raw_manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return stage


def refresh_raw_geometry_digest(raw_manifest: dict[str, object]) -> None:
    structure = raw_manifest["structure"]
    assert isinstance(structure, dict)
    nodes = structure["nodes"]
    assert isinstance(nodes, list)
    geometry = {
        "topology_sha256": structure["topology_sha256"],
        "nodes": nodes,
        "bounds": structure["bounds"],
        "closed": structure["closed"],
        "winding_consistent": structure["winding_consistent"],
        "volume_m3": structure["volume_m3"],
    }
    canonical = (json.dumps(geometry, sort_keys=True, separators=(",", ":")) + "\n").encode()
    structure["geometry_sha256"] = hashlib.sha256(canonical).hexdigest()


def test_compiler_is_deterministic_and_preserves_exact_coordinates_and_mass() -> None:
    manifest = tetra_manifest()
    compiler = JBeamCompiler()
    first = compiler.compile(JBeamBuildRequest(manifest=manifest, dae=evidence(manifest)))
    second = compiler.compile(JBeamBuildRequest(manifest=manifest, dae=evidence(manifest)))

    assert [asset.content for asset in first.assets] == [asset.content for asset in second.assets]
    assert first.summary.node_count == 4
    assert first.summary.beam_count == 6
    assert sum(item.mass_kg for item in first.validation.node_masses) == pytest.approx(100.0)
    jbeam = json.loads(first.jbeam.content)
    rows = jbeam["demo"]["nodes"][1:]
    emitted = {row[0]: tuple(row[1:4]) for row in rows}
    assert emitted == {node.id: node.beamng_position for node in manifest.nodes}
    material = json.loads(first.materials.content)["demo_material"]
    assert material["mapTo"] == "demo_mat"
    assert material["Stages"][0]["baseColorFactor"] == [0.5, 0.5, 0.5, 1.0]
    assert "baseColor" not in material["Stages"][0]
    assert json.loads(first.vehicle_info.content) == {
        "Author": "Test Author",
        "Name": "Demo Soft Body",
        "Type": "Prop",
        "default_pc": "demo",
    }
    assert json.loads(first.configuration_pc.content) == {
        "format": 2,
        "mainPartName": "demo",
        "model": "demo",
        "parts": {},
    }
    assert json.loads(first.configuration_info.content) == {
        "Configuration": "Demo Soft Body",
        "Weight": 100.0,
    }
    provenance = json.loads(first.provenance.content)
    assert len(provenance["manifest"]["nodes"]) == 4


def test_compiler_rejects_coordinate_and_dae_tampering() -> None:
    manifest = tetra_manifest()
    changed_node = manifest.nodes[0].model_copy(update={"beamng_position": (0.01, 0.0, 0.0)})
    tampered = manifest.model_copy(update={"nodes": (changed_node, *manifest.nodes[1:])})
    with pytest.raises(StructuralValidationError) as coordinate_error:
        JBeamCompiler().compile(JBeamBuildRequest(manifest=tampered, dae=evidence(tampered)))
    assert any(
        issue.code == "coordinate_mismatch" for issue in coordinate_error.value.result.issues
    )

    wrong_dae = evidence(manifest).model_copy(update={"sha256": "0" * 64})
    with pytest.raises(StructuralValidationError) as digest_error:
        JBeamCompiler().compile(JBeamBuildRequest(manifest=manifest, dae=wrong_dae))
    assert any(issue.code == "dae_hash_mismatch" for issue in digest_error.value.result.issues)

    duplicate_source = manifest.nodes[1].model_copy(update={"source_vertex_index": 0})
    duplicate_manifest = manifest.model_copy(
        update={"nodes": (manifest.nodes[0], duplicate_source, *manifest.nodes[2:])}
    )
    with pytest.raises(StructuralValidationError) as provenance_error:
        JBeamCompiler().compile(
            JBeamBuildRequest(manifest=duplicate_manifest, dae=evidence(duplicate_manifest))
        )
    assert any(
        issue.code == "duplicate_source_vertex" for issue in provenance_error.value.result.issues
    )


def test_validator_rejects_a_slidenode_that_is_not_on_its_explicit_rail() -> None:
    manifest = tetra_manifest().model_copy(
        update={
            "rails": (RailSpec(name="demo_rail", node_ids=("n_ref", "n_back")),),
            "slidenodes": (
                SlideNodeSpec(node_id="n_left", rail_name="demo_rail", tolerance_m=0.0),
            ),
        }
    )
    with pytest.raises(StructuralValidationError) as error:
        JBeamCompiler().compile(JBeamBuildRequest(manifest=manifest, dae=evidence(manifest)))
    assert any(issue.code == "slidenode_off_rail" for issue in error.value.result.issues)


def test_compiler_marks_interior_nodes_non_collidable_and_rejects_interior_triangles() -> None:
    original = tetra_manifest()
    interior = StructuralNode(
        id="n_core",
        source_object="demo_cage",
        source_vertex_index=None,
        source_world_position=(0.25, 0.25, 0.25),
        beamng_position=(0.25, 0.25, 0.25),
        group="demo_group",
        surface=False,
    )
    interior_edges = tuple(
        StructuralEdge(node_a="n_core", node_b=node.id) for node in original.nodes
    )
    manifest = original.model_copy(
        update={
            "nodes": (*original.nodes, interior),
            "edges": (*original.edges, *interior_edges),
        }
    )

    compiled = JBeamCompiler().compile(JBeamBuildRequest(manifest=manifest, dae=evidence(manifest)))
    rows = json.loads(compiled.jbeam.content)["demo"]["nodes"][1:]
    options = next(row[4] for row in rows if row[0] == "n_core")
    assert options["collision"] is False
    assert options["staticCollision"] is False

    invalid_triangle = StructuralTriangle(nodes=("n_core", "n_left", "n_back"))
    invalid = manifest.model_copy(update={"triangles": (invalid_triangle, *manifest.triangles[1:])})
    with pytest.raises(StructuralValidationError) as error:
        JBeamCompiler().compile(JBeamBuildRequest(manifest=invalid, dae=evidence(invalid)))
    assert any(issue.code == "triangle_interior_node" for issue in error.value.result.issues)


def test_validator_accepts_a_world_translation_that_preserves_positive_z_up() -> None:
    original = tetra_manifest()
    origin = (10.0, 20.0, 30.0)
    translated_nodes = tuple(
        node.model_copy(
            update={
                "source_world_position": tuple(
                    node.beamng_position[index] + origin[index] for index in range(3)
                )
            }
        )
        for node in original.nodes
    )
    coordinates = CoordinateContract(
        source_origin_world=origin,
        source_world_to_beamng_vehicle=(
            (1.0, 0.0, 0.0, -10.0),
            (0.0, 1.0, 0.0, -20.0),
            (0.0, 0.0, 1.0, -30.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )
    manifest = original.model_copy(update={"coordinates": coordinates, "nodes": translated_nodes})

    compiled = JBeamCompiler().compile(JBeamBuildRequest(manifest=manifest, dae=evidence(manifest)))

    assert compiled.validation.valid is True
    assert not any(issue.code == "transform_not_z_up" for issue in compiled.validation.issues)

    rotated_coordinates = CoordinateContract(
        source_origin_world=(0.0, 0.0, 0.0),
        source_world_to_beamng_vehicle=(
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, -1.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ),
    )
    rotated = original.model_copy(update={"coordinates": rotated_coordinates})
    with pytest.raises(StructuralValidationError) as rotated_error:
        JBeamCompiler().compile(JBeamBuildRequest(manifest=rotated, dae=evidence(rotated)))
    assert any(issue.code == "transform_not_z_up" for issue in rotated_error.value.result.issues)


def test_validator_caps_density_computed_mass() -> None:
    manifest = tetra_manifest().model_copy(
        update={"mass": MassInputs(closed_volume_m3=100.0, density_kg_m3=7_850.0)}
    )

    with pytest.raises(StructuralValidationError) as error:
        JBeamCompiler().compile(JBeamBuildRequest(manifest=manifest, dae=evidence(manifest)))

    assert any(issue.code == "total_mass_exceeded" for issue in error.value.result.issues)


def test_validator_checks_the_closing_segment_of_a_looped_rail() -> None:
    original = tetra_manifest()
    near_ref = StructuralNode(
        id="n_near_ref",
        source_object="demo_cage",
        source_vertex_index=None,
        source_world_position=(0.0, 0.0, 0.00005),
        beamng_position=(0.0, 0.0, 0.00005),
        group="demo_group",
        surface=False,
    )
    manifest = original.model_copy(
        update={
            "nodes": (*original.nodes, near_ref),
            "edges": (
                *original.edges,
                StructuralEdge(node_a="n_near_ref", node_b="n_ref"),
                StructuralEdge(node_a="n_near_ref", node_b="n_back"),
            ),
            "rails": (
                RailSpec(
                    name="closing_rail",
                    node_ids=("n_ref", "n_back", "n_near_ref"),
                    looped=True,
                    capped=False,
                ),
            ),
        }
    )

    with pytest.raises(StructuralValidationError) as error:
        JBeamCompiler().compile(JBeamBuildRequest(manifest=manifest, dae=evidence(manifest)))

    assert any(
        issue.code == "short_rail_segment" and issue.subject == "closing_rail"
        for issue in error.value.result.issues
    )


def test_volume_based_build_must_reuse_the_measured_blender_volume() -> None:
    measured = 1.0 / 6.0
    manifest = tetra_manifest().model_copy(update={"mass": MassInputs(closed_volume_m3=measured)})
    common = {
        "slot_id": "0" * 32,
        "mod_name": "demo",
        "asset_name": "demo",
        "title": "Demo",
        "author": "Test",
        "material": manifest.material,
    }
    mismatched = StructuralBuildRequest(
        **common,
        mass=MassInputs(closed_volume_m3=measured + 0.01),
    )

    with pytest.raises(ValueError, match="measured Blender cage volume exactly"):
        JBeamCompiler().compile_manifest(manifest, evidence(manifest), mismatched)

    matching = StructuralBuildRequest(**common, mass=MassInputs(closed_volume_m3=measured))
    compiled = JBeamCompiler().compile_manifest(manifest, evidence(manifest), matching)
    assert compiled.summary.total_mass_kg == pytest.approx(measured * 7_850.0)


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("physics_cage", "object identities"),
        ("visual_object", "visual evidence"),
        ("visual_transform", "identity BeamNG transform"),
        ("coordinate_contract", "coordinate contract"),
        ("node_roles", "Per-node roles"),
        ("node_source_object", "source object"),
        ("node_source_index", "source_vertex_index"),
    ),
)
def test_raw_handoff_semantics_remain_bound_after_digest_recomputation(
    case: str,
    message: str,
    tmp_path: Path,
) -> None:
    dae = tiny_dae()
    raw = raw_export_manifest(dae)
    asset = raw["asset"]
    visual = raw["visual"]
    coordinates = raw["coordinate_system"]
    structure = raw["structure"]
    assert isinstance(asset, dict)
    assert isinstance(visual, dict)
    assert isinstance(coordinates, dict)
    assert isinstance(structure, dict)
    nodes = structure["nodes"]
    assert isinstance(nodes, list)
    first_node = nodes[0]
    assert isinstance(first_node, dict)

    if case == "physics_cage":
        asset["physics_cage"] = "other_cage"
    elif case == "visual_object":
        visual["objects"] = ["other_mesh"]
    elif case == "visual_transform":
        visual["object_transform"] = "translated"
    elif case == "coordinate_contract":
        coordinates["source_origin_world"] = [1.0, 0.0, 0.0]
    elif case == "node_roles":
        first_node["roles"] = ["beamng_back"]
    elif case == "node_source_object":
        first_node["source_object"] = "other_cage"
    elif case == "node_source_index":
        first_node["source_vertex_index"] = 2
    else:  # pragma: no cover - the parametrization is exhaustive
        raise AssertionError(case)
    refresh_raw_geometry_digest(raw)

    mods = ModWorkspace(WorkspaceSettings(root=tmp_path / "workspace"))
    service = StructuralModService(mods)
    stage = staged_raw_handoff(service, dae, raw)
    validation = service.validate_handoff(stage.slot_id)

    assert validation.valid is False
    assert any(message in issue.message for issue in validation.issues)


def test_raw_handoff_rejects_a_source_vertex_index_permutation(tmp_path: Path) -> None:
    dae = tiny_dae()
    raw = raw_export_manifest(dae)
    structure = raw["structure"]
    assert isinstance(structure, dict)
    nodes = structure["nodes"]
    assert isinstance(nodes, list)
    first = nodes[0]
    second = nodes[1]
    assert isinstance(first, dict) and isinstance(second, dict)
    first["source_vertex_index"], second["source_vertex_index"] = (
        second["source_vertex_index"],
        first["source_vertex_index"],
    )
    refresh_raw_geometry_digest(raw)
    service = StructuralModService(ModWorkspace(WorkspaceSettings(root=tmp_path / "workspace")))
    stage = staged_raw_handoff(service, dae, raw)

    validation = service.validate_handoff(stage.slot_id)

    assert validation.valid is False
    assert any("source_vertex_index" in issue.message for issue in validation.issues)


def test_structural_build_enforces_the_configured_actuator_cap(tmp_path: Path) -> None:
    dae = tiny_dae()
    mods = ModWorkspace(WorkspaceSettings(root=tmp_path / "workspace", max_structural_actuators=0))
    service = StructuralModService(mods)
    stage = staged_raw_handoff(service, dae, raw_export_manifest(dae))
    request = StructuralBuildRequest(
        slot_id=stage.slot_id,
        mod_name="demo",
        asset_name="demo",
        title="Demo",
        author="Test",
        material=StructuralMaterial(preset="steel", material_id="demo_material"),
        mass=MassInputs(total_mass_kg=100.0),
        hydros=(
            HydroSpec(
                node_a="n_ref",
                node_b="n_up",
                input_source="crusher_input",
                factor=0.5,
            ),
        ),
    )

    with pytest.raises(WorkspaceError, match="actuator count 1 exceeds configured maximum 0"):
        service.build(request)


def test_structural_service_validates_builds_and_revalidates_the_assembled_mod(
    tmp_path: Path,
) -> None:
    dae = tiny_dae()
    mods = ModWorkspace(WorkspaceSettings(root=tmp_path / "workspace", max_file_bytes=1024 * 1024))
    service = StructuralModService(mods)
    stage = service.inbox.create(
        mod_name="demo",
        asset_name="demo",
        visual_format="dae",
        helper_source=b"# reviewed helper\n",
        runner_source=b"# reviewed runner\n",
        request_contract={
            "asset_id": "demo",
            "physics_cage": "demo_cage",
            "visual_objects": ["demo_mesh"],
            "world_to_beamng": [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ],
            "source_origin_world": [0.0, 0.0, 0.0],
            "tolerance_m": 1e-6,
        },
    )
    stage.visual.write_bytes(dae)
    raw_manifest = raw_export_manifest(dae)
    stage.manifest.write_text(
        json.dumps(raw_manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    validation = service.validate_handoff(stage.slot_id)
    assert validation.valid is True
    build = service.build(
        StructuralBuildRequest(
            slot_id=stage.slot_id,
            mod_name="demo",
            asset_name="demo",
            title="Demo Soft Body",
            author="Test Author",
            material=StructuralMaterial(preset="steel", material_id="demo_material"),
            mass=MassInputs(total_mass_kg=125.0),
        )
    )
    assert build.total_mass_kg == pytest.approx(125.0)
    assert {file.path for file in build.files} == {
        "vehicles/demo/demo.dae",
        "vehicles/demo/demo.jbeam",
        "vehicles/demo/demo.structure.json",
        "vehicles/demo/demo.pc",
        "vehicles/demo/info.json",
        "vehicles/demo/info_demo.json",
        "vehicles/demo/main.materials.json",
    }
    assembled = service.validate_mod("demo", "demo")
    assert assembled.valid is True
    assert assembled.manifest_sha256 == build.manifest_sha256

    provenance_path = (
        tmp_path / "workspace" / "mods" / "demo" / "vehicles" / "demo" / "demo.structure.json"
    )
    original_provenance = provenance_path.read_text(encoding="utf-8")
    provenance = json.loads(original_provenance)
    provenance["manifestSha256"] = "0" * 64
    provenance_path.write_text(
        json.dumps(provenance, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    tampered = service.validate_mod("demo", "demo")
    assert tampered.valid is False
    assert any(issue.code == "manifest_hash_mismatch" for issue in tampered.issues)

    identity_substitution = json.loads(original_provenance)
    identity_substitution["manifest"]["mod_name"] = "substitute"
    provenance_path.write_text(
        json.dumps(identity_substitution, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    substituted = service.validate_mod("demo", "demo")
    assert substituted.valid is False
    assert any(
        issue.code == "assembled_mod_invalid" and "identity" in issue.message
        for issue in substituted.issues
    )
