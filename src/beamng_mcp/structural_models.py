"""Strict contracts for deterministic Blender-to-JBeam structural authoring.

The manifest deliberately carries both Blender world-space coordinates and
BeamNG vehicle-space coordinates.  A compiler must recompute the latter from
the declared rigid transform; coordinates supplied only by prose are never an
accepted input to this contract.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Vector3: TypeAlias = tuple[float, float, float]
Matrix4: TypeAlias = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]
NodeId: TypeAlias = str
MaterialPresetName: TypeAlias = Literal["steel", "concrete", "wood", "rubber"]

IDENTIFIER_PATTERN = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
MOD_NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"
ASSET_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
SHA256_PATTERN = r"^[a-f0-9]{64}$"
SLOT_ID_PATTERN = r"^[a-f0-9]{32}$"
RELATIVE_DAE_PATTERN = r"^.+\.dae$"


def _require_finite_vector(value: Vector3, *, name: str) -> Vector3:
    if not all(math.isfinite(component) for component in value):
        raise ValueError(f"{name} must contain only finite coordinates")
    return value


class StructuralModel(BaseModel):
    """Base for public structural contracts.

    ``extra='forbid'`` makes version skew fail visibly instead of silently
    dropping fields. JSON arrays are intentionally accepted for tuple-shaped
    MCP fields because MCP transports decode arrays to Python lists.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )


class Bounds3D(StructuralModel):
    """Axis-aligned bounds expressed in BeamNG vehicle space, in metres."""

    minimum: Vector3
    maximum: Vector3

    @field_validator("minimum", "maximum")
    @classmethod
    def finite_coordinates(cls, value: Vector3) -> Vector3:
        return _require_finite_vector(value, name="bounds")

    @model_validator(mode="after")
    def ordered_bounds(self) -> Bounds3D:
        if any(low > high for low, high in zip(self.minimum, self.maximum, strict=True)):
            raise ValueError("bounds minimum must not exceed maximum on any axis")
        return self


class CoordinateContract(StructuralModel):
    """Explicit Blender-world to BeamNG-vehicle coordinate conversion."""

    units: Literal["metres"] = "metres"
    source_space: Literal["blender_world"] = "blender_world"
    target_space: Literal["beamng_vehicle"] = "beamng_vehicle"
    source_up_axis: Literal["+Z"] = "+Z"
    target_axes: Literal["+X left, +Y backward, +Z up"] = "+X left, +Y backward, +Z up"
    transforms_applied: Literal[True] = True
    source_origin_world: Vector3
    source_world_to_beamng_vehicle: Matrix4
    tolerance_m: float = Field(default=1e-6, gt=0.0, le=1e-6)

    @field_validator("source_origin_world")
    @classmethod
    def finite_origin(cls, value: Vector3) -> Vector3:
        return _require_finite_vector(value, name="source_origin_world")

    @field_validator("source_world_to_beamng_vehicle")
    @classmethod
    def finite_matrix(cls, value: Matrix4) -> Matrix4:
        if not all(math.isfinite(component) for row in value for component in row):
            raise ValueError("source_world_to_beamng_vehicle must contain only finite values")
        return value


class VisualDAE(StructuralModel):
    """The exact Collada artifact to which the physics manifest is bound."""

    path: str = Field(min_length=5, max_length=512, pattern=RELATIVE_DAE_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size: int = Field(gt=0, le=67_108_864)
    mesh_name: str = Field(min_length=1, max_length=128, pattern=IDENTIFIER_PATTERN)
    material_name: str = Field(min_length=1, max_length=128, pattern=IDENTIFIER_PATTERN)
    bounds: Bounds3D

    @field_validator("path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or "//" in normalized:
            raise ValueError("DAE path must be a portable relative path")
        if any(part in {"", ".", ".."} or ":" in part for part in normalized.split("/")):
            raise ValueError("DAE path contains an unsafe component")
        return normalized


class DAEArtifactEvidence(StructuralModel):
    """Digest and size observed from a stable read of the finalized DAE."""

    path: str = Field(min_length=5, max_length=512, pattern=RELATIVE_DAE_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size: int = Field(gt=0, le=67_108_864)

    @field_validator("path")
    @classmethod
    def portable_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or "//" in normalized:
            raise ValueError("DAE evidence path must be a portable relative path")
        if any(part in {"", ".", ".."} or ":" in part for part in normalized.split("/")):
            raise ValueError("DAE evidence path contains an unsafe component")
        return normalized


class BlenderExportEvidence(StructuralModel):
    """Integrity metadata from the reviewed Blender companion's raw handoff."""

    generator: str = Field(min_length=1, max_length=128)
    blender_version: str = Field(min_length=1, max_length=64)
    raw_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    geometry_sha256: str = Field(pattern=SHA256_PATTERN)
    physics_cage: str = Field(min_length=1, max_length=128)
    visual_objects: tuple[str, ...] = Field(min_length=1, max_length=32)


class StructuralNode(StructuralModel):
    """A physics node with auditable Blender coordinate provenance."""

    id: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    source_object: str = Field(min_length=1, max_length=128)
    source_vertex_index: int | None = Field(default=None, ge=0)
    source_world_position: Vector3
    beamng_position: Vector3
    group: str = Field(min_length=1, max_length=128, pattern=IDENTIFIER_PATTERN)
    surface: bool = True
    mass_scale: float = Field(default=1.0, gt=0.0, le=100.0)

    @field_validator("source_world_position", "beamng_position")
    @classmethod
    def finite_positions(cls, value: Vector3) -> Vector3:
        return _require_finite_vector(value, name="node position")

    @model_validator(mode="after")
    def surface_nodes_have_vertices(self) -> StructuralNode:
        if self.surface and self.source_vertex_index is None:
            raise ValueError("surface nodes require source_vertex_index provenance")
        return self


class StructuralEdge(StructuralModel):
    """An explicit structural beam; the compiler never guesses proximity edges."""

    node_a: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    node_b: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    spring_scale: float = Field(default=1.0, gt=0.0, le=10.0)
    damp_scale: float = Field(default=1.0, gt=0.0, le=10.0)
    deform_scale: float = Field(default=1.0, gt=0.0, le=10.0)
    strength_scale: float = Field(default=1.0, gt=0.0, le=10.0)

    @model_validator(mode="after")
    def different_endpoints(self) -> StructuralEdge:
        if self.node_a == self.node_b:
            raise ValueError("a structural edge must connect two different nodes")
        return self


class BracePanel(StructuralModel):
    """Four explicitly ordered panel corners that generate both X diagonals."""

    id: str = Field(pattern=IDENTIFIER_PATTERN)
    nodes: tuple[NodeId, NodeId, NodeId, NodeId]

    @field_validator("nodes")
    @classmethod
    def valid_node_ids(cls, value: tuple[NodeId, NodeId, NodeId, NodeId]) -> tuple[str, ...]:
        if len(set(value)) != 4:
            raise ValueError("brace panel corners must be four distinct nodes")
        for node_id in value:
            if not node_id or len(node_id) > 64:
                raise ValueError("brace panel contains an invalid node id")
        return value


class StructuralTriangle(StructuralModel):
    """One counter-clockwise collision surface in BeamNG vehicle space."""

    nodes: tuple[NodeId, NodeId, NodeId]
    ground_model: Literal["metal", "asphalt", "rock", "wood", "rubber"] | None = None

    @field_validator("nodes")
    @classmethod
    def distinct_nodes(cls, value: tuple[NodeId, NodeId, NodeId]) -> tuple[str, ...]:
        if len(set(value)) != 3:
            raise ValueError("triangle corners must be three distinct nodes")
        for node_id in value:
            if not node_id or len(node_id) > 64:
                raise ValueError("triangle contains an invalid node id")
        return value


class ReferenceNodes(StructuralModel):
    """Nodes defining BeamNG's ref, backward, left, and up axes."""

    ref: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    back: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    left: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    up: NodeId = Field(pattern=IDENTIFIER_PATTERN)

    @model_validator(mode="after")
    def distinct_nodes(self) -> ReferenceNodes:
        if len({self.ref, self.back, self.left, self.up}) != 4:
            raise ValueError("ref, back, left, and up must be distinct nodes")
        return self


class BasePolicy(StructuralModel):
    """Explicit grounding policy for the object's lowest structural nodes."""

    mode: Literal["free", "weighted", "fixed"] = "weighted"
    node_ids: tuple[NodeId, ...] = Field(default_factory=tuple, max_length=128)
    mass_multiplier: float = Field(default=4.0, ge=1.0, le=25.0)

    @model_validator(mode="after")
    def coherent_policy(self) -> BasePolicy:
        if len(set(self.node_ids)) != len(self.node_ids):
            raise ValueError("base node_ids must be unique")
        if self.mode == "free":
            if self.node_ids or self.mass_multiplier != 1.0:
                raise ValueError("a free base requires no node_ids and mass_multiplier=1")
        else:
            if len(self.node_ids) < 3:
                raise ValueError("weighted and fixed bases require at least three nodes")
            if self.mass_multiplier < 2.0:
                raise ValueError("weighted and fixed bases require mass_multiplier >= 2")
        return self


class MassInputs(StructuralModel):
    """Either explicit total mass, or volume multiplied by material density."""

    total_mass_kg: float | None = Field(default=None, gt=0.0, le=250_000.0)
    closed_volume_m3: float | None = Field(default=None, gt=0.0, le=10_000.0)
    density_kg_m3: float | None = Field(default=None, ge=10.0, le=25_000.0)

    @model_validator(mode="after")
    def one_mass_route(self) -> MassInputs:
        if self.total_mass_kg is not None:
            if self.closed_volume_m3 is not None or self.density_kg_m3 is not None:
                raise ValueError(
                    "total_mass_kg cannot be combined with closed_volume_m3 or density_kg_m3"
                )
            return self
        if self.closed_volume_m3 is None:
            raise ValueError("supply total_mass_kg or closed_volume_m3")
        return self


class StructuralMaterial(StructuralModel):
    """Versioned physical preset plus a minimal BeamNG visual material."""

    preset: MaterialPresetName
    material_id: str = Field(pattern=IDENTIFIER_PATTERN)
    base_color: tuple[float, float, float, float] = (0.5, 0.5, 0.5, 1.0)
    roughness: float = Field(default=0.7, ge=0.0, le=1.0)
    metallic: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("base_color")
    @classmethod
    def color_channels(cls, value: tuple[float, float, float, float]) -> tuple[float, ...]:
        if not all(math.isfinite(channel) and 0.0 <= channel <= 1.0 for channel in value):
            raise ValueError("base_color channels must be finite values between 0 and 1")
        return value


class HydroSpec(StructuralModel):
    """A bounded BeamNG hydro driven by a named electrics input."""

    node_a: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    node_b: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    input_source: str = Field(min_length=1, max_length=64, pattern=IDENTIFIER_PATTERN)
    factor: float = Field(ge=-0.9, le=2.0)
    in_rate: float = Field(default=1.0, gt=0.0, le=20.0)
    out_rate: float = Field(default=1.0, gt=0.0, le=20.0)
    spring_scale: float = Field(default=1.0, gt=0.0, le=10.0)
    damp_scale: float = Field(default=1.0, gt=0.0, le=10.0)

    @model_validator(mode="after")
    def different_endpoints(self) -> HydroSpec:
        if self.node_a == self.node_b:
            raise ValueError("a hydro must connect two different nodes")
        if self.factor == 0.0:
            raise ValueError("a hydro factor must be non-zero")
        return self


class RailSpec(StructuralModel):
    """An explicitly ordered BeamNG rail."""

    name: str = Field(pattern=IDENTIFIER_PATTERN)
    node_ids: tuple[NodeId, ...] = Field(min_length=2, max_length=128)
    looped: bool = False
    capped: bool = True

    @model_validator(mode="after")
    def valid_path(self) -> RailSpec:
        if len(set(self.node_ids)) != len(self.node_ids):
            raise ValueError("rail node_ids must be unique")
        if self.looped and len(self.node_ids) < 3:
            raise ValueError("a looped rail requires at least three nodes")
        if self.looped and self.capped:
            raise ValueError("a looped rail must set capped=false")
        return self


class SlideNodeSpec(StructuralModel):
    """A node constrained to one named rail using documented JBeam fields."""

    node_id: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    rail_name: str = Field(pattern=IDENTIFIER_PATTERN)
    attached: bool = True
    fix_to_rail: bool = True
    tolerance_m: float = Field(default=0.0, ge=0.0, le=0.25)
    spring: float = Field(default=1_000_000.0, gt=0.0, le=100_000_000.0)
    strength: float = Field(default=10_000_000.0, gt=0.0, le=1_000_000_000.0)
    cap_strength: float = Field(default=10_000_000.0, gt=0.0, le=1_000_000_000.0)


class BlenderStructuralManifest(StructuralModel):
    """Complete, versioned input contract emitted from Blender's evaluated scene."""

    schema_version: Literal["beamng-structure-v1"] = Field(
        default="beamng-structure-v1", alias="schema"
    )
    mod_name: str = Field(pattern=MOD_NAME_PATTERN)
    part_name: str = Field(pattern=IDENTIFIER_PATTERN)
    display_name: str = Field(min_length=1, max_length=128)
    author: str = Field(min_length=1, max_length=128)
    source_evidence: BlenderExportEvidence | None = None
    coordinates: CoordinateContract
    bounds: Bounds3D
    visual: VisualDAE
    material: StructuralMaterial
    mass: MassInputs
    nodes: tuple[StructuralNode, ...] = Field(min_length=4, max_length=512)
    edges: tuple[StructuralEdge, ...] = Field(min_length=1, max_length=4096)
    brace_panels: tuple[BracePanel, ...] = Field(default_factory=tuple, max_length=1024)
    triangles: tuple[StructuralTriangle, ...] = Field(min_length=1, max_length=2048)
    refnodes: ReferenceNodes
    base: BasePolicy
    hydros: tuple[HydroSpec, ...] = Field(default_factory=tuple, max_length=64)
    rails: tuple[RailSpec, ...] = Field(default_factory=tuple, max_length=64)
    slidenodes: tuple[SlideNodeSpec, ...] = Field(default_factory=tuple, max_length=128)

    @model_validator(mode="after")
    def unique_declared_ids(self) -> BlenderStructuralManifest:
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("node ids must be unique")
        panel_ids = [panel.id for panel in self.brace_panels]
        if len(set(panel_ids)) != len(panel_ids):
            raise ValueError("brace panel ids must be unique")
        rail_names = [rail.name for rail in self.rails]
        if len(set(rail_names)) != len(rail_names):
            raise ValueError("rail names must be unique")
        return self


class StructuralIssue(StructuralModel):
    """Machine-readable domain validation finding."""

    severity: Literal["error", "warning"]
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    message: str
    subject: str | None = None


class NodeMass(StructuralModel):
    node_id: NodeId = Field(pattern=IDENTIFIER_PATTERN)
    mass_kg: float = Field(gt=0.0)


class StructuralValidationResult(StructuralModel):
    valid: bool
    issues: tuple[StructuralIssue, ...]
    total_mass_kg: float = Field(gt=0.0)
    node_masses: tuple[NodeMass, ...]
    generated_beam_count: int = Field(ge=0)


class GeneratedTextAsset(StructuralModel):
    """One deterministic UTF-8 file ready for an atomic workspace commit."""

    path: str
    media_type: Literal["application/json", "application/jbeam+json"]
    content: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    size: int = Field(ge=0)


class StructuralBuildSummary(StructuralModel):
    node_count: int = Field(ge=0)
    beam_count: int = Field(ge=0)
    triangle_count: int = Field(ge=0)
    hydro_count: int = Field(ge=0)
    rail_count: int = Field(ge=0)
    slidenode_count: int = Field(ge=0)
    total_mass_kg: float = Field(gt=0.0)
    bounds: Bounds3D


class JBeamCompileResult(StructuralModel):
    """All deterministic compiler products and their integrity metadata."""

    schema_version: Literal["beamng-structure-build-v1"] = "beamng-structure-build-v1"
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    dae_sha256: str = Field(pattern=SHA256_PATTERN)
    preset_catalog_version: Literal["beamng-material-baselines-v1"] = "beamng-material-baselines-v1"
    validation: StructuralValidationResult
    summary: StructuralBuildSummary
    jbeam: GeneratedTextAsset
    materials: GeneratedTextAsset
    vehicle_info: GeneratedTextAsset
    configuration_pc: GeneratedTextAsset
    configuration_info: GeneratedTextAsset
    provenance: GeneratedTextAsset

    @property
    def assets(self) -> tuple[GeneratedTextAsset, ...]:
        """Generated files in stable commit order."""

        return (
            self.jbeam,
            self.materials,
            self.vehicle_info,
            self.configuration_pc,
            self.configuration_info,
            self.provenance,
        )


class JBeamBuildRequest(StructuralModel):
    """Public request object for pure compilation after a stable DAE read."""

    manifest: BlenderStructuralManifest
    dae: DAEArtifactEvidence


class AssetStage(StructuralModel):
    """One confined, expiring handoff target for a Blender MCP export."""

    mod_name: str = Field(pattern=ASSET_NAME_PATTERN)
    asset_name: str = Field(pattern=ASSET_NAME_PATTERN)
    slot_id: str = Field(min_length=32, max_length=32, pattern=SLOT_ID_PATTERN)
    directory: str = Field(min_length=1, max_length=1024)
    manifest_path: str = Field(min_length=1, max_length=1024)
    visual_path: str = Field(min_length=1, max_length=1024)
    blender_runner_path: str = Field(min_length=1, max_length=1024)
    blender_execute_code: str = Field(min_length=1, max_length=4096)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def timezone_aware_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value


class AssetStageRequest(StructuralModel):
    """Blender object selection and explicit coordinate contract for one export slot."""

    mod_name: str = Field(pattern=ASSET_NAME_PATTERN)
    asset_name: str = Field(pattern=ASSET_NAME_PATTERN)
    visual_object: str = Field(min_length=1, max_length=64, pattern=ASSET_NAME_PATTERN)
    cage_object: str = Field(min_length=1, max_length=64, pattern=ASSET_NAME_PATTERN)
    coordinates: CoordinateContract
    visual_format: Literal["dae", "gltf"] = "dae"
    dae_operator: str | None = Field(default=None, min_length=1, max_length=128)


class StructuralManifestSummary(StructuralModel):
    """Bounded staged-manifest facts safe to return without its full topology."""

    schema_version: Literal["beamng-structure-v1"] = "beamng-structure-v1"
    mod_name: str = Field(pattern=MOD_NAME_PATTERN)
    part_name: str = Field(pattern=IDENTIFIER_PATTERN)
    mesh_name: str = Field(pattern=IDENTIFIER_PATTERN)
    material_name: str = Field(pattern=IDENTIFIER_PATTERN)
    bounds: Bounds3D
    node_count: int = Field(ge=0, le=512)
    edge_count: int = Field(ge=0, le=4096)
    brace_panel_count: int = Field(ge=0, le=1024)
    triangle_count: int = Field(ge=0, le=2048)
    closed: bool
    measured_volume_m3: float | None = Field(default=None, gt=0.0, le=10_000.0)
    node_ids: tuple[NodeId, ...] = Field(min_length=4, max_length=512)
    base_node_ids: tuple[NodeId, ...] = Field(default_factory=tuple, max_length=128)
    refnodes: ReferenceNodes


class AssetStageValidation(StructuralModel):
    """Self-contained result of stable staged-manifest and DAE inspection."""

    valid: bool
    slot_id: str = Field(min_length=32, max_length=32, pattern=SLOT_ID_PATTERN)
    manifest: StructuralManifestSummary | None = None
    manifest_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    visual_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    visual_size: int | None = Field(default=None, gt=0, le=67_108_864)
    issues: tuple[StructuralIssue, ...] = Field(default_factory=tuple)


class StructuralBuildRequest(StructuralModel):
    """Coordinator request that applies non-geometric build policy to a staged manifest."""

    slot_id: str = Field(min_length=32, max_length=32, pattern=SLOT_ID_PATTERN)
    mod_name: str = Field(pattern=ASSET_NAME_PATTERN)
    asset_name: str = Field(pattern=ASSET_NAME_PATTERN)
    title: str = Field(min_length=1, max_length=128)
    author: str = Field(min_length=1, max_length=128)
    material: StructuralMaterial
    mass: MassInputs
    grounded: bool = True
    fixed: bool = False
    hydros: tuple[HydroSpec, ...] = Field(default_factory=tuple, max_length=64)
    rails: tuple[RailSpec, ...] = Field(default_factory=tuple, max_length=64)
    slidenodes: tuple[SlideNodeSpec, ...] = Field(default_factory=tuple, max_length=128)
    overwrite: bool = False
    expected_sha256: dict[str, str] = Field(default_factory=dict, max_length=16)

    @model_validator(mode="after")
    def fixed_requires_grounded(self) -> StructuralBuildRequest:
        if self.fixed and not self.grounded:
            raise ValueError("fixed=true requires grounded=true")
        for path, digest in self.expected_sha256.items():
            normalized = path.replace("\\", "/")
            if (
                normalized != path
                or normalized.startswith("/")
                or any(part in {"", ".", ".."} or ":" in part for part in path.split("/"))
            ):
                raise ValueError("expected_sha256 keys must be portable relative paths")
            if not re.fullmatch(SHA256_PATTERN, digest):
                raise ValueError("expected_sha256 values must be lowercase SHA-256 digests")
        if self.expected_sha256 and not self.overwrite:
            raise ValueError("expected_sha256 requires overwrite=true")
        return self


class StructuralFileResult(StructuralModel):
    path: str = Field(min_length=1, max_length=512)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)


class StructuralBuildResult(StructuralModel):
    """Coordinator-facing result after generated assets are committed."""

    mod_name: str = Field(pattern=ASSET_NAME_PATTERN)
    asset_name: str = Field(pattern=ASSET_NAME_PATTERN)
    files: tuple[StructuralFileResult, ...]
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    total_mass_kg: float = Field(gt=0.0)
    warnings: tuple[str, ...] = Field(default_factory=tuple)


class StructuralValidation(StructuralModel):
    """Coordinator-facing validation result for an assembled structural mod."""

    valid: bool
    mod_name: str = Field(pattern=ASSET_NAME_PATTERN)
    asset_name: str = Field(pattern=ASSET_NAME_PATTERN)
    manifest_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    files: tuple[StructuralFileResult, ...] = Field(default_factory=tuple)
    issues: tuple[StructuralIssue, ...] = Field(default_factory=tuple)


__all__ = [
    "AssetStage",
    "AssetStageRequest",
    "AssetStageValidation",
    "BasePolicy",
    "BlenderExportEvidence",
    "BlenderStructuralManifest",
    "Bounds3D",
    "BracePanel",
    "CoordinateContract",
    "DAEArtifactEvidence",
    "GeneratedTextAsset",
    "HydroSpec",
    "JBeamBuildRequest",
    "JBeamCompileResult",
    "MassInputs",
    "Matrix4",
    "NodeMass",
    "RailSpec",
    "ReferenceNodes",
    "SlideNodeSpec",
    "StructuralBuildRequest",
    "StructuralBuildResult",
    "StructuralBuildSummary",
    "StructuralEdge",
    "StructuralFileResult",
    "StructuralIssue",
    "StructuralManifestSummary",
    "StructuralMaterial",
    "StructuralNode",
    "StructuralTriangle",
    "StructuralValidation",
    "StructuralValidationResult",
    "Vector3",
    "VisualDAE",
]
