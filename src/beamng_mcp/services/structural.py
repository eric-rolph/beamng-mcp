"""Filesystem coordinator for evidence-bound Blender-to-JBeam builds."""

from __future__ import annotations

import hashlib
import json
import math
import threading
from importlib.resources import files
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..errors import ConflictError, NotFoundError, WorkspaceError
from ..structural_models import (
    AssetStage,
    AssetStageRequest,
    AssetStageValidation,
    BasePolicy,
    BlenderExportEvidence,
    BlenderStructuralManifest,
    Bounds3D,
    BracePanel,
    CoordinateContract,
    DAEArtifactEvidence,
    JBeamBuildRequest,
    MassInputs,
    ReferenceNodes,
    StructuralBuildRequest,
    StructuralBuildResult,
    StructuralEdge,
    StructuralFileResult,
    StructuralIssue,
    StructuralManifestSummary,
    StructuralMaterial,
    StructuralNode,
    StructuralTriangle,
    StructuralValidation,
    VisualDAE,
)
from .collada import ColladaInspection, inspect_collada
from .jbeam import JBeamCompiler, StructuralManifestValidator, StructuralValidationError
from .mods import ModWorkspace
from .staging import MANIFEST_NAME, AssetStagingInbox, StagedAssetData

RAW_HANDOFF_SCHEMA = "beamng-blender-handoff-v1"
RAW_HANDOFF_GENERATOR = "beamng-mcp-blender-softbody-export/1"
RAW_ROLE_NAMES = frozenset(
    {
        "beamng_base",
        "beamng_ref",
        "beamng_back",
        "beamng_left",
        "beamng_up",
        "beamng_interior",
    }
)


class StructuralModService:
    """Join a confined Blender inbox, pure compiler, and transactional mod workspace."""

    def __init__(self, mods: ModWorkspace) -> None:
        self.mods = mods
        self.settings = mods.settings
        self.inbox = AssetStagingInbox(mods)
        self.validator = StructuralManifestValidator()
        self.compiler = JBeamCompiler(self.validator)
        self._build_lock = threading.Lock()

    def create_handoff(self, request: AssetStageRequest) -> AssetStage:
        if request.asset_name != request.mod_name:
            raise WorkspaceError("v1 structural builds require asset_name to equal mod_name")
        for label, name in (
            ("visual_object", request.visual_object),
            ("cage_object", request.cage_object),
        ):
            if name != request.asset_name and not name.startswith(f"{request.asset_name}_"):
                raise WorkspaceError(f"{label} must equal asset_name or start with '<asset_name>_'")
        helper = (
            files("beamng_mcp").joinpath("assets", "blender", "softbody_export.py").read_bytes()
        )
        visual_name = f"visual.{request.visual_format}"
        config = {
            "asset_id": request.asset_name,
            "physics_cage": request.cage_object,
            "visual_objects": [request.visual_object],
            "world_to_beamng": request.coordinates.source_world_to_beamng_vehicle,
            "source_origin_world": request.coordinates.source_origin_world,
            "tolerance_m": request.coordinates.tolerance_m,
            "required_roles": [
                "beamng_ref",
                "beamng_back",
                "beamng_left",
                "beamng_up",
            ],
            "visual_format": request.visual_format,
            "_stage_manifest_name": MANIFEST_NAME,
            "_stage_visual_name": visual_name,
        }
        if request.dae_operator is not None:
            config["dae_operator"] = request.dae_operator
        runner = self._runner_source(config)
        stage = self.inbox.create(
            mod_name=request.mod_name,
            asset_name=request.asset_name,
            visual_format=request.visual_format,
            helper_source=helper,
            runner_source=runner,
            request_contract=config,
        )
        execute_code = (
            f"import runpy\nrunpy.run_path({json.dumps(str(stage.runner))}, run_name='__main__')"
        )
        return AssetStage(
            mod_name=request.mod_name,
            asset_name=request.asset_name,
            slot_id=stage.slot_id,
            directory=str(stage.directory),
            manifest_path=str(stage.manifest),
            visual_path=str(stage.visual),
            blender_runner_path=str(stage.runner),
            blender_execute_code=execute_code,
            expires_at=stage.expires_at,
        )

    def validate_handoff(self, slot_id: str) -> AssetStageValidation:
        try:
            staged = self.inbox.read(slot_id)
        except (ConflictError, NotFoundError, WorkspaceError) as exc:
            return AssetStageValidation(
                valid=False,
                slot_id=slot_id,
                issues=(self._issue("stage_unavailable", str(exc)),),
            )
        if staged.visual_format != "dae":
            return AssetStageValidation(
                valid=False,
                slot_id=slot_id,
                manifest_sha256=staged.manifest_sha256,
                visual_sha256=staged.visual_sha256,
                visual_size=staged.visual_size,
                issues=(
                    self._issue(
                        "gltf_runtime_unsupported",
                        "glTF is diagnostic interchange only; "
                        "BeamNG 0.38 flexbody builds require DAE",
                    ),
                ),
            )

        try:
            manifest, inspection, domain_issues = self._validate_staged_dae(staged)
        except (ConflictError, ValidationError, ValueError, WorkspaceError) as exc:
            return AssetStageValidation(
                valid=False,
                slot_id=slot_id,
                manifest_sha256=staged.manifest_sha256,
                visual_sha256=staged.visual_sha256,
                visual_size=staged.visual_size,
                issues=(self._issue("invalid_handoff", self._safe_message(exc)),),
            )

        issues = list(domain_issues)
        issues.extend(self._capacity_issues(manifest))
        issues.extend(self._collada_alignment_issues(manifest, inspection))
        return AssetStageValidation(
            valid=not any(issue.severity == "error" for issue in issues),
            slot_id=slot_id,
            manifest=self._summary(manifest),
            manifest_sha256=staged.manifest_sha256,
            visual_sha256=staged.visual_sha256,
            visual_size=staged.visual_size,
            issues=tuple(issues),
        )

    def build(self, request: StructuralBuildRequest) -> StructuralBuildResult:
        with self._build_lock:
            return self._build_locked(request)

    def _build_locked(self, request: StructuralBuildRequest) -> StructuralBuildResult:
        staged = self.inbox.read(request.slot_id)
        if staged.visual_format != "dae":
            raise WorkspaceError("A runtime soft-body build requires a Collada .dae handoff")
        if (staged.mod_name, staged.asset_name) != (request.mod_name, request.asset_name):
            raise ConflictError("Build request does not match the names bound to the handoff slot")
        actuator_count = len(request.hydros) + len(request.rails) + len(request.slidenodes)
        if actuator_count > self.settings.max_structural_actuators:
            raise WorkspaceError(
                "Structural build request actuator count "
                f"{actuator_count} exceeds configured maximum "
                f"{self.settings.max_structural_actuators}"
            )

        manifest, inspection, domain_issues = self._validate_staged_dae(staged)
        blocking = [issue for issue in domain_issues if issue.severity == "error"]
        blocking.extend(self._capacity_issues(manifest))
        blocking.extend(self._collada_alignment_issues(manifest, inspection))
        blocking = [issue for issue in blocking if issue.severity == "error"]
        if blocking:
            codes = ", ".join(sorted({issue.code for issue in blocking}))
            raise WorkspaceError(f"Structural handoff failed validation: {codes}")

        evidence = DAEArtifactEvidence(
            path=manifest.visual.path,
            sha256=staged.visual_sha256,
            size=staged.visual_size,
        )
        try:
            compiled = self.compiler.compile_manifest(manifest, evidence, request)
        except StructuralValidationError as exc:
            codes = ", ".join(
                sorted({issue.code for issue in exc.result.issues if issue.severity == "error"})
            )
            raise WorkspaceError(f"Structural build policy failed validation: {codes}") from exc

        if not self.mods.exists(request.mod_name):
            self.mods.scaffold(
                request.mod_name,
                title=request.title,
                author=request.author,
                kind="vehicle",
            )
        bundle: dict[str, bytes] = {manifest.visual.path: staged.visual_bytes}
        bundle.update({asset.path: asset.content.encode() for asset in compiled.assets})
        # Reserve the one-use evidence before any mod mutation. A failed commit consumes the
        # slot deliberately; retrying requires a fresh Blender export rather than risking two
        # different policy bundles from one handoff.
        self.inbox.consume(request.slot_id, manifest_sha256=compiled.manifest_sha256)
        committed = self.mods.write_bundle(
            request.mod_name,
            bundle,
            overwrite=request.overwrite,
            expected_sha256=request.expected_sha256,
        )

        warnings = tuple(
            issue.message for issue in compiled.validation.issues if issue.severity == "warning"
        )
        return StructuralBuildResult(
            mod_name=request.mod_name,
            asset_name=request.asset_name,
            files=tuple(
                StructuralFileResult(path=item.path, size=item.size, sha256=item.sha256)
                for item in committed
            ),
            manifest_sha256=compiled.manifest_sha256,
            total_mass_kg=compiled.summary.total_mass_kg,
            warnings=warnings,
        )

    def validate_mod(self, mod_name: str, asset_name: str) -> StructuralValidation:
        issues: list[StructuralIssue] = []
        file_results: list[StructuralFileResult] = []
        manifest_sha256: str | None = None
        if not (asset_name == mod_name or asset_name.startswith(f"{mod_name}_")):
            return StructuralValidation(
                valid=False,
                mod_name=mod_name,
                asset_name=asset_name,
                issues=(
                    self._issue(
                        "asset_not_namespaced",
                        "asset_name must equal mod_name or start with '<mod_name>_'",
                    ),
                ),
            )

        provenance_path = f"vehicles/{mod_name}/{asset_name}.structure.json"
        try:
            provenance_bytes, provenance_file = self._read_mod_bytes(mod_name, provenance_path)
            file_results.append(provenance_file)
            provenance = json.loads(provenance_bytes)
            if not isinstance(provenance, dict):
                raise ValueError("provenance root must be an object")
            embedded_manifest = json.dumps(
                provenance.get("manifest"),
                sort_keys=True,
                separators=(",", ":"),
            )
            manifest = BlenderStructuralManifest.model_validate_json(embedded_manifest)
            if manifest.mod_name != mod_name or manifest.part_name != asset_name:
                raise ValueError(
                    "provenance manifest identity does not match the requested mod and asset"
                )
            raw_manifest_sha = provenance.get("manifestSha256")
            if not isinstance(raw_manifest_sha, str):
                raise ValueError("provenance is missing manifestSha256")
            manifest_sha256 = raw_manifest_sha
            dae_bytes, dae_file = self._read_mod_bytes(mod_name, manifest.visual.path)
            file_results.append(dae_file)
            evidence = DAEArtifactEvidence(
                path=manifest.visual.path,
                sha256=dae_file.sha256,
                size=dae_file.size,
            )
            inspection = inspect_collada(
                dae_bytes,
                expected_mesh_name=manifest.visual.mesh_name,
                expected_material_name=manifest.visual.material_name,
            )
            issues.extend(self._collada_alignment_issues(manifest, inspection))
            compiled = self.compiler.compile(JBeamBuildRequest(manifest=manifest, dae=evidence))
            if compiled.provenance.path != provenance_path:
                raise ValueError("compiled provenance path does not match the requested asset")
            if compiled.manifest_sha256 != manifest_sha256:
                issues.append(
                    self._issue(
                        "manifest_hash_mismatch",
                        "provenance manifest hash does not match the embedded canonical manifest",
                    )
                )
            for asset in compiled.assets:
                actual_bytes, actual_file = self._read_mod_bytes(mod_name, asset.path)
                if actual_file.path != provenance_path:
                    file_results.append(actual_file)
                if actual_bytes != asset.content.encode():
                    issues.append(
                        self._issue(
                            "generated_file_mismatch",
                            "assembled file does not match deterministic compiler output",
                            asset.path,
                        )
                    )
        except (ValidationError, ValueError, WorkspaceError, NotFoundError) as exc:
            issues.append(self._issue("assembled_mod_invalid", self._safe_message(exc)))

        try:
            generic = self.mods.validate(mod_name)
            for generic_issue in generic.issues:
                issues.append(
                    StructuralIssue(
                        severity=generic_issue.severity,
                        code="mod_workspace_validation",
                        message=generic_issue.message,
                        subject=generic_issue.path,
                    )
                )
        except (NotFoundError, WorkspaceError) as exc:
            issues.append(self._issue("mod_workspace_unavailable", self._safe_message(exc)))
        ordered = tuple(
            sorted(issues, key=lambda item: (item.severity, item.code, item.subject or ""))
        )
        return StructuralValidation(
            valid=not any(issue.severity == "error" for issue in ordered),
            mod_name=mod_name,
            asset_name=asset_name,
            manifest_sha256=manifest_sha256,
            files=tuple(sorted(file_results, key=lambda item: item.path)),
            issues=ordered,
        )

    def _validate_staged_dae(
        self, staged: StagedAssetData
    ) -> tuple[BlenderStructuralManifest, ColladaInspection, tuple[StructuralIssue, ...]]:
        raw = self._raw_manifest(staged.manifest_bytes)
        asset = self._object(raw.get("asset"), "asset")
        visual_objects = self._string_list(asset.get("visual_objects"), "visual_objects")
        if len(visual_objects) != 1:
            raise WorkspaceError("beamng-structure-v1 supports exactly one visual object")
        inspection = inspect_collada(
            staged.visual_bytes,
            expected_mesh_name=visual_objects[0],
            expected_material_name=None,
        )
        if len(inspection.material_names) != 1:
            raise WorkspaceError(
                "v1 soft-body builds require exactly one uniquely named DAE material"
            )
        material_name = inspection.material_names[0]
        if material_name != staged.asset_name and not material_name.startswith(
            f"{staged.asset_name}_"
        ):
            raise WorkspaceError(
                "DAE material name must equal asset_name or start with '<asset_name>_'"
            )
        manifest = self._convert_raw_manifest(staged, raw, inspection)
        evidence = DAEArtifactEvidence(
            path=manifest.visual.path,
            sha256=staged.visual_sha256,
            size=staged.visual_size,
        )
        validation = self.validator.validate(manifest, evidence)
        return manifest, inspection, validation.issues

    def _convert_raw_manifest(
        self,
        staged: StagedAssetData,
        raw: dict[str, Any],
        inspection: ColladaInspection,
    ) -> BlenderStructuralManifest:
        if raw.get("schema") != RAW_HANDOFF_SCHEMA:
            raise WorkspaceError("Blender manifest has an unsupported schema")
        if raw.get("generator") != RAW_HANDOFF_GENERATOR:
            raise ConflictError("Blender manifest generator does not match the reviewed helper")
        contract = self._object(staged.request_contract, "staged request contract")
        asset = self._object(raw.get("asset"), "asset")
        if self._string(asset.get("id"), "asset.id") != staged.asset_name:
            raise ConflictError("Blender asset ID does not match the bound handoff asset")
        cage_name = self._string(asset.get("physics_cage"), "asset.physics_cage")
        visual_objects = tuple(
            self._string_list(asset.get("visual_objects"), "asset.visual_objects")
        )
        expected_cage = self._string(contract.get("physics_cage"), "request.physics_cage")
        expected_visual_objects = tuple(
            self._string_list(contract.get("visual_objects"), "request.visual_objects")
        )
        if cage_name != expected_cage or visual_objects != expected_visual_objects:
            raise ConflictError("Blender object identities do not match the bound handoff request")

        visual = self._object(raw.get("visual"), "visual")
        if visual.get("format") != "dae" or visual.get("debug_only") is not False:
            raise WorkspaceError("Blender manifest does not describe a runtime DAE export")
        if (
            visual.get("coordinates_baked_to_beamng") is not True
            or visual.get("object_transform") != "identity"
        ):
            raise WorkspaceError("Blender visual export must bake an identity BeamNG transform")
        if tuple(self._string_list(visual.get("objects"), "visual.objects")) != visual_objects:
            raise ConflictError("Blender visual evidence does not match the bound visual objects")
        visual_operator = self._string(visual.get("operator"), "visual.operator")
        requested_operator = contract.get("dae_operator")
        if requested_operator is not None and visual_operator != requested_operator:
            raise ConflictError("Blender DAE operator does not match the bound handoff request")
        if visual.get("sha256") != staged.visual_sha256 or visual.get("size") != staged.visual_size:
            raise ConflictError("Blender manifest visual digest/size does not match staged bytes")
        if Path(self._string(visual.get("path"), "visual.path")).name != "visual.dae":
            raise WorkspaceError(
                "Blender manifest visual path does not match the fixed slot output"
            )
        if visual.get("units") != "m" or visual.get("z_up") is not True:
            raise WorkspaceError("Blender visual export must declare metres and Z-up")

        coordinate_system = self._object(raw.get("coordinate_system"), "coordinate_system")
        source = self._object(coordinate_system.get("source"), "coordinate_system.source")
        target = self._object(coordinate_system.get("target"), "coordinate_system.target")
        if source != {"units": "m", "up_axis": "Z"} or target != {
            "units": "m",
            "up_axis": "Z",
        }:
            raise WorkspaceError("Blender manifest coordinate systems must be Z-up metres")
        coordinates = CoordinateContract(
            source_origin_world=self._vector3(
                coordinate_system.get("source_origin_world"),
                "coordinate_system.source_origin_world",
            ),
            source_world_to_beamng_vehicle=self._matrix4(coordinate_system.get("world_to_beamng")),
            tolerance_m=self._number(contract.get("tolerance_m"), "request.tolerance_m"),
        )
        expected_origin = self._vector3(contract.get("source_origin_world"), "request origin")
        expected_matrix = self._matrix4(contract.get("world_to_beamng"))
        if (
            coordinates.source_origin_world != expected_origin
            or coordinates.source_world_to_beamng_vehicle != expected_matrix
        ):
            raise ConflictError(
                "Blender coordinate contract does not match the bound handoff request"
            )
        mapped_origin = self._vector3(
            coordinate_system.get("mapped_source_origin"),
            "coordinate_system.mapped_source_origin",
        )
        if any(abs(component) > coordinates.tolerance_m for component in mapped_origin):
            raise ConflictError("Blender source origin was not mapped to vehicle-local zero")

        structure = self._object(raw.get("structure"), "structure")
        topology_sha256 = self._verify_raw_integrity(structure)
        raw_nodes = self._list(structure.get("nodes"), "structure.nodes")
        raw_node_objects = [self._object(value, "structure.nodes[]") for value in raw_nodes]
        raw_node_ids = [self._string(node.get("id"), "node.id") for node in raw_node_objects]
        if len(raw_node_ids) != len(set(raw_node_ids)):
            raise WorkspaceError("Blender node IDs must be unique")
        role_index = self._object(structure.get("roles"), "structure.roles")
        if set(role_index) != RAW_ROLE_NAMES:
            raise WorkspaceError("Blender role index has missing or unsupported role names")
        role_members = {
            role: tuple(self._string_list(role_index.get(role), f"roles.{role}"))
            for role in sorted(RAW_ROLE_NAMES)
        }
        unknown_role_nodes = set().union(*(set(values) for values in role_members.values())) - set(
            raw_node_ids
        )
        if unknown_role_nodes:
            raise WorkspaceError("Blender role index references unknown node IDs")
        nodes: list[StructuralNode] = []
        source_indices: list[int] = []
        for expected_source_index, raw_node in enumerate(raw_node_objects):
            node_id = self._string(raw_node.get("id"), "node.id")
            node_roles = self._string_list(raw_node.get("roles"), "node.roles")
            expected_roles = sorted(
                role for role, members in role_members.items() if node_id in members
            )
            if sorted(node_roles) != expected_roles:
                raise ConflictError("Per-node roles do not match the digest-bound role index")
            source_index = raw_node.get("source_vertex_index")
            if isinstance(source_index, bool) or not isinstance(source_index, int):
                raise WorkspaceError("Every Blender node needs an exact source_vertex_index")
            if source_index != expected_source_index:
                raise ConflictError(
                    "Blender node rows must be ordered by exact source_vertex_index"
                )
            source_indices.append(source_index)
            source_object = self._string(raw_node.get("source_object"), "node.source_object")
            if source_object != expected_cage:
                raise ConflictError("Node source object does not match the bound physics cage")
            nodes.append(
                StructuralNode(
                    id=node_id,
                    source_object=source_object,
                    source_vertex_index=source_index,
                    source_world_position=self._vector3(
                        raw_node.get("source_world_position"), "node.source_world_position"
                    ),
                    beamng_position=self._vector3(raw_node.get("position"), "node.position"),
                    group=staged.asset_name,
                    surface=node_id not in role_members["beamng_interior"],
                )
            )
        if source_indices != list(range(len(nodes))):
            raise ConflictError("Cage source_vertex_index values must be exactly 0..node_count-1")

        edges = tuple(
            StructuralEdge(node_a=pair[0], node_b=pair[1])
            for pair in (
                self._node_pair(item, "edge_beams")
                for item in self._list(structure.get("edge_beams"), "structure.edge_beams")
            )
        )
        brace_panels = tuple(
            BracePanel(
                id=f"brace_panel_{index:04d}",
                nodes=self._node_quad(item, "quad_brace_panels"),
            )
            for index, item in enumerate(
                self._list(structure.get("quad_brace_panels"), "structure.quad_brace_panels")
            )
        )
        triangles = tuple(
            StructuralTriangle(nodes=self._node_triangle(item, "triangles"))
            for item in self._list(structure.get("triangles"), "structure.triangles")
        )

        refnodes = ReferenceNodes(
            ref=self._single_role(role_index, "beamng_ref"),
            back=self._single_role(role_index, "beamng_back"),
            left=self._single_role(role_index, "beamng_left"),
            up=self._single_role(role_index, "beamng_up"),
        )
        base_ids = tuple(self._string_list(role_index.get("beamng_base"), "roles.beamng_base"))
        base = (
            BasePolicy(mode="weighted", node_ids=base_ids, mass_multiplier=4.0)
            if len(base_ids) >= 3
            else BasePolicy(mode="free", node_ids=(), mass_multiplier=1.0)
        )
        raw_bounds = self._object(structure.get("bounds"), "structure.bounds")
        source_world_bounds = self._object(
            raw_bounds.get("source_world"), "structure.bounds.source_world"
        )
        declared_source_bounds = Bounds3D(
            minimum=self._vector3(source_world_bounds.get("min"), "source bounds.min"),
            maximum=self._vector3(source_world_bounds.get("max"), "source bounds.max"),
        )
        self._verify_bound_dimensions(
            source_world_bounds,
            declared_source_bounds,
            "source bounds.dimensions",
        )
        actual_source_bounds = self._bounds([node.source_world_position for node in nodes])
        if declared_source_bounds != actual_source_bounds:
            raise ConflictError(
                "Blender source-world bounds do not match source vertex coordinates"
            )
        beamng_bounds = self._object(raw_bounds.get("beamng"), "structure.bounds.beamng")
        bounds = Bounds3D(
            minimum=self._vector3(beamng_bounds.get("min"), "bounds.min"),
            maximum=self._vector3(beamng_bounds.get("max"), "bounds.max"),
        )
        self._verify_bound_dimensions(beamng_bounds, bounds, "bounds.dimensions")
        closed_value = structure.get("closed")
        winding_value = structure.get("winding_consistent")
        if not isinstance(closed_value, bool) or not isinstance(winding_value, bool):
            raise WorkspaceError("Blender closed/winding evidence must be boolean")
        if closed_value != winding_value:
            raise WorkspaceError("Blender closed cages require consistent winding")
        closed = closed_value
        volume = structure.get("volume_m3")
        if closed:
            if (
                isinstance(volume, bool)
                or not isinstance(volume, (int, float))
                or not math.isfinite(float(volume))
                or float(volume) <= 0.0
            ):
                raise WorkspaceError("A closed Blender cage must have positive finite volume")
        elif volume is not None:
            raise WorkspaceError("An open Blender cage must report volume_m3=null")
        mass = (
            MassInputs(closed_volume_m3=float(volume))
            if closed
            and isinstance(volume, (int, float))
            and not isinstance(volume, bool)
            and volume > 0
            else MassInputs(total_mass_kg=1.0)
        )
        manifest_visual = VisualDAE(
            path=f"vehicles/{staged.mod_name}/{staged.asset_name}.dae",
            sha256=staged.visual_sha256,
            size=staged.visual_size,
            mesh_name=visual_objects[0],
            material_name=inspection.material_names[0],
            bounds=Bounds3D(
                minimum=inspection.bounds_min,
                maximum=inspection.bounds_max,
            ),
        )
        return BlenderStructuralManifest(
            mod_name=staged.mod_name,
            part_name=staged.asset_name,
            display_name=staged.asset_name.replace("_", " ").title(),
            author="BeamNG MCP Blender handoff",
            source_evidence=BlenderExportEvidence(
                generator=self._string(raw.get("generator"), "generator"),
                blender_version=self._string(raw.get("blender_version"), "blender_version"),
                raw_manifest_sha256=staged.manifest_sha256,
                topology_sha256=topology_sha256,
                geometry_sha256=self._string(
                    structure.get("geometry_sha256"), "structure.geometry_sha256"
                ),
                physics_cage=cage_name,
                visual_objects=visual_objects,
            ),
            coordinates=coordinates,
            bounds=bounds,
            visual=manifest_visual,
            material=StructuralMaterial(preset="steel", material_id=staged.asset_name),
            mass=mass,
            nodes=tuple(nodes),
            edges=edges,
            brace_panels=brace_panels,
            triangles=triangles,
            refnodes=refnodes,
            base=base,
        )

    def _capacity_issues(self, manifest: BlenderStructuralManifest) -> list[StructuralIssue]:
        counts = {
            "nodes": (len(manifest.nodes), self.settings.max_structural_nodes),
            "beams": (
                len(manifest.edges) + 2 * len(manifest.brace_panels),
                self.settings.max_structural_beams,
            ),
            "triangles": (len(manifest.triangles), self.settings.max_structural_triangles),
            "actuators": (
                len(manifest.hydros) + len(manifest.rails) + len(manifest.slidenodes),
                self.settings.max_structural_actuators,
            ),
        }
        return [
            self._issue(
                "structural_capacity_exceeded",
                f"{name} count {count} exceeds configured maximum {maximum}",
                name,
            )
            for name, (count, maximum) in counts.items()
            if count > maximum
        ]

    @staticmethod
    def _collada_alignment_issues(
        manifest: BlenderStructuralManifest, inspection: ColladaInspection
    ) -> list[StructuralIssue]:
        tolerance = manifest.coordinates.tolerance_m
        actual = Bounds3D(minimum=inspection.bounds_min, maximum=inspection.bounds_max)
        visual_differences = [
            abs(left - right)
            for pair in (
                zip(actual.minimum, manifest.visual.bounds.minimum, strict=True),
                zip(actual.maximum, manifest.visual.bounds.maximum, strict=True),
            )
            for left, right in pair
        ]
        structural_differences = [
            abs(left - right)
            for pair in (
                zip(actual.minimum, manifest.bounds.minimum, strict=True),
                zip(actual.maximum, manifest.bounds.maximum, strict=True),
            )
            for left, right in pair
        ]
        issues: list[StructuralIssue] = []
        if max(visual_differences, default=0.0) > tolerance:
            issues.append(
                StructuralModService._issue(
                    "dae_bounds_mismatch",
                    "Collada POSITION bounds do not match the recorded visual bounds",
                )
            )
        if max(structural_differences, default=0.0) > tolerance:
            issues.append(
                StructuralModService._issue(
                    "cage_visual_bounds_mismatch",
                    "Physics-cage bounds must exactly match the visual shell bounds",
                )
            )
        tolerance_squared = tolerance * tolerance
        position_bins: dict[tuple[int, int, int], list[tuple[float, float, float]]] = {}
        for position in inspection.positions:
            key = (
                math.floor(position[0] / tolerance),
                math.floor(position[1] / tolerance),
                math.floor(position[2] / tolerance),
            )
            position_bins.setdefault(key, []).append(position)
        for node in manifest.nodes:
            if not node.surface:
                continue
            node_key = tuple(
                math.floor(component / tolerance) for component in node.beamng_position
            )
            matched = any(
                sum((node.beamng_position[index] - position[index]) ** 2 for index in range(3))
                <= tolerance_squared
                for offset_x in (-1, 0, 1)
                for offset_y in (-1, 0, 1)
                for offset_z in (-1, 0, 1)
                for position in position_bins.get(
                    (
                        node_key[0] + offset_x,
                        node_key[1] + offset_y,
                        node_key[2] + offset_z,
                    ),
                    (),
                )
            )
            if not matched:
                issues.append(
                    StructuralModService._issue(
                        "surface_node_not_visual_vertex",
                        "Every surface physics node must match an emitted DAE vertex",
                        node.id,
                    )
                )
        return issues

    @staticmethod
    def _raw_manifest(data: bytes) -> dict[str, Any]:
        try:
            value = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceError("Blender structure manifest is not valid JSON") from exc
        return StructuralModService._object(value, "manifest")

    @staticmethod
    def _verify_raw_integrity(structure: dict[str, Any]) -> str:
        nodes = StructuralModService._list(structure.get("nodes"), "structure.nodes")
        edge_beams = StructuralModService._list(structure.get("edge_beams"), "structure.edge_beams")
        brace_beams = StructuralModService._list(
            structure.get("brace_beams"), "structure.brace_beams"
        )
        panels = StructuralModService._list(
            structure.get("quad_brace_panels"), "structure.quad_brace_panels"
        )
        triangles = StructuralModService._list(structure.get("triangles"), "structure.triangles")
        declared_braces = [
            tuple(sorted(StructuralModService._node_pair(item, "brace_beams")))
            for item in brace_beams
        ]
        if len(declared_braces) != len(set(declared_braces)):
            raise ConflictError("Blender brace-beam evidence contains duplicates")
        expected_braces = {
            pair
            for item in panels
            for panel in (StructuralModService._node_quad(item, "quad_brace_panels"),)
            for pair in (
                tuple(sorted((panel[0], panel[2]))),
                tuple(sorted((panel[1], panel[3]))),
            )
        }
        if set(declared_braces) != expected_braces:
            raise ConflictError("Blender brace-beam evidence does not match quad-panel diagonals")
        topology_payload = {
            "node_ids": sorted(
                StructuralModService._string(
                    StructuralModService._object(node, "node").get("id"), "node.id"
                )
                for node in nodes
            ),
            "edge_beams": [
                StructuralModService._object(beam, "edge_beam").get("nodes") for beam in edge_beams
            ],
            "brace_beams": [
                StructuralModService._object(beam, "brace_beam").get("nodes")
                for beam in brace_beams
            ],
            "quad_brace_panels": [
                StructuralModService._object(panel, "brace_panel").get("nodes") for panel in panels
            ],
            "triangles": [
                StructuralModService._object(triangle, "triangle").get("nodes")
                for triangle in triangles
            ],
            "roles": structure.get("roles"),
        }
        topology_sha256 = hashlib.sha256(
            StructuralModService._canonical_json_bytes(topology_payload)
        ).hexdigest()
        if structure.get("topology_sha256") != topology_sha256:
            raise ConflictError("Blender topology digest does not match its manifest payload")
        geometry_payload = {
            "topology_sha256": topology_sha256,
            "nodes": nodes,
            "bounds": structure.get("bounds"),
            "closed": structure.get("closed"),
            "winding_consistent": structure.get("winding_consistent"),
            "volume_m3": structure.get("volume_m3"),
        }
        geometry_sha256 = hashlib.sha256(
            StructuralModService._canonical_json_bytes(geometry_payload)
        ).hexdigest()
        if structure.get("geometry_sha256") != geometry_sha256:
            raise ConflictError("Blender geometry digest does not match its manifest payload")
        return topology_sha256

    @staticmethod
    def _node_pair(value: Any, label: str) -> tuple[str, str]:
        item = StructuralModService._object(value, label)
        nodes = StructuralModService._string_list(item.get("nodes"), f"{label}.nodes")
        if len(nodes) != 2:
            raise WorkspaceError(f"{label}.nodes must contain exactly two node IDs")
        return nodes[0], nodes[1]

    @staticmethod
    def _node_quad(value: Any, label: str) -> tuple[str, str, str, str]:
        item = StructuralModService._object(value, label)
        nodes = StructuralModService._string_list(item.get("nodes"), f"{label}.nodes")
        if len(nodes) != 4:
            raise WorkspaceError(f"{label}.nodes must contain exactly four node IDs")
        return nodes[0], nodes[1], nodes[2], nodes[3]

    @staticmethod
    def _node_triangle(value: Any, label: str) -> tuple[str, str, str]:
        item = StructuralModService._object(value, label)
        nodes = StructuralModService._string_list(item.get("nodes"), f"{label}.nodes")
        if len(nodes) != 3:
            raise WorkspaceError(f"{label}.nodes must contain exactly three node IDs")
        return nodes[0], nodes[1], nodes[2]

    @staticmethod
    def _single_role(roles: dict[str, Any], name: str) -> str:
        values = StructuralModService._string_list(roles.get(name), f"roles.{name}")
        if len(values) != 1:
            raise WorkspaceError(f"roles.{name} must contain exactly one node")
        return values[0]

    @staticmethod
    def _object(value: Any, label: str) -> dict[str, Any]:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise WorkspaceError(f"{label} must be a JSON object with string keys")
        return value

    @staticmethod
    def _list(value: Any, label: str) -> list[Any]:
        if not isinstance(value, list):
            raise WorkspaceError(f"{label} must be a JSON array")
        return value

    @staticmethod
    def _string(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value:
            raise WorkspaceError(f"{label} must be a non-empty string")
        return value

    @staticmethod
    def _string_list(value: Any, label: str) -> list[str]:
        raw = StructuralModService._list(value, label)
        result = [StructuralModService._string(item, f"{label}[]") for item in raw]
        if len(result) != len(set(result)):
            raise WorkspaceError(f"{label} must not contain duplicate strings")
        return result

    @staticmethod
    def _vector3(value: Any, label: str) -> tuple[float, float, float]:
        raw = StructuralModService._list(value, label)
        if len(raw) != 3:
            raise WorkspaceError(f"{label} must contain exactly three numbers")
        values: list[float] = []
        for item in raw:
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise WorkspaceError(f"{label} must contain only finite numbers")
            number = float(item)
            if not math.isfinite(number):
                raise WorkspaceError(f"{label} must contain only finite numbers")
            values.append(number)
        return values[0], values[1], values[2]

    @staticmethod
    def _number(value: Any, label: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise WorkspaceError(f"{label} must be a finite number")
        result = float(value)
        if not math.isfinite(result):
            raise WorkspaceError(f"{label} must be a finite number")
        return result

    @staticmethod
    def _bounds(points: list[tuple[float, float, float]]) -> Bounds3D:
        if not points:
            raise WorkspaceError("Cannot calculate bounds without points")
        return Bounds3D(
            minimum=(
                min(point[0] for point in points),
                min(point[1] for point in points),
                min(point[2] for point in points),
            ),
            maximum=(
                max(point[0] for point in points),
                max(point[1] for point in points),
                max(point[2] for point in points),
            ),
        )

    @staticmethod
    def _verify_bound_dimensions(
        raw: dict[str, Any],
        bounds: Bounds3D,
        label: str,
    ) -> None:
        dimensions = StructuralModService._vector3(raw.get("dimensions"), label)
        expected = tuple(bounds.maximum[index] - bounds.minimum[index] for index in range(3))
        if any(left != right for left, right in zip(dimensions, expected, strict=True)):
            raise ConflictError(f"{label} does not match min/max")

    @staticmethod
    def _matrix4(
        value: Any,
    ) -> tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
    ]:
        raw = StructuralModService._list(value, "world_to_beamng")
        if len(raw) != 4:
            raise WorkspaceError("world_to_beamng must contain exactly four rows")
        rows: list[tuple[float, float, float, float]] = []
        for index, row in enumerate(raw):
            values = StructuralModService._list(row, f"world_to_beamng[{index}]")
            if len(values) != 4:
                raise WorkspaceError("world_to_beamng rows must contain exactly four numbers")
            numbers: list[float] = []
            for item in values:
                if isinstance(item, bool) or not isinstance(item, (int, float)):
                    raise WorkspaceError("world_to_beamng must contain finite numbers")
                number = float(item)
                if not math.isfinite(number):
                    raise WorkspaceError("world_to_beamng must contain finite numbers")
                numbers.append(number)
            rows.append((numbers[0], numbers[1], numbers[2], numbers[3]))
        return rows[0], rows[1], rows[2], rows[3]

    @staticmethod
    def _canonical_json_bytes(value: Any) -> bytes:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode()

    def _read_mod_bytes(self, mod_name: str, path: str) -> tuple[bytes, StructuralFileResult]:
        target = self.mods._file(mod_name, path, must_exist=True)
        digest, size, data = self.mods._stable_file(
            target,
            collect=True,
            max_bytes=self.settings.max_file_bytes,
        )
        assert data is not None
        return data, StructuralFileResult(path=path, size=size, sha256=digest)

    @staticmethod
    def _summary(manifest: BlenderStructuralManifest) -> StructuralManifestSummary:
        return StructuralManifestSummary(
            mod_name=manifest.mod_name,
            part_name=manifest.part_name,
            mesh_name=manifest.visual.mesh_name,
            material_name=manifest.visual.material_name,
            bounds=manifest.visual.bounds,
            node_count=len(manifest.nodes),
            edge_count=len(manifest.edges),
            brace_panel_count=len(manifest.brace_panels),
            triangle_count=len(manifest.triangles),
            closed=manifest.mass.closed_volume_m3 is not None,
            measured_volume_m3=manifest.mass.closed_volume_m3,
            node_ids=tuple(sorted(node.id for node in manifest.nodes)),
            base_node_ids=tuple(sorted(manifest.base.node_ids)),
            refnodes=manifest.refnodes,
        )

    @staticmethod
    def _runner_source(config: dict[str, Any]) -> bytes:
        encoded = json.dumps(config, sort_keys=True, separators=(",", ":"))
        source = (
            "# Generated by BeamNG MCP; execute this exact file through Blender MCP.\n"
            "import json\n"
            "import runpy\n"
            "from pathlib import Path\n\n"
            "job_dir = Path(__file__).resolve().parent\n"
            f"config = json.loads({encoded!r})\n"
            "config['visual_path'] = str(job_dir / config.pop('_stage_visual_name'))\n"
            "config['manifest_path'] = str(job_dir / config.pop('_stage_manifest_name'))\n"
            "module = runpy.run_path(str(job_dir / 'beamng_softbody_export.py'))\n"
            "result = module['export_beamng_softbody'](config)\n"
            "print(json.dumps(result, sort_keys=True))\n"
        )
        return source.encode()

    @staticmethod
    def _issue(code: str, message: str, subject: str | None = None) -> StructuralIssue:
        return StructuralIssue(
            severity="error",
            code=code,
            message=message[:1000],
            subject=subject,
        )

    @staticmethod
    def _safe_message(exc: Exception) -> str:
        message = str(exc).replace("\x00", "")
        return message[:1000] or type(exc).__name__
