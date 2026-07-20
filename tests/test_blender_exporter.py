from __future__ import annotations

import ast
import importlib
from importlib.resources import files
from types import SimpleNamespace

import pytest


def exporter_module():
    return importlib.import_module("beamng_mcp.assets.blender.softbody_export")


def test_blender_exporter_is_packaged_and_contains_no_process_or_dynamic_eval_calls() -> None:
    source = (
        files("beamng_mcp")
        .joinpath("assets", "blender", "softbody_export.py")
        .read_text(encoding="utf-8")
    )
    tree = ast.parse(source)
    forbidden = {"eval", "exec", "compile", "system", "popen", "run", "Popen"}
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls.isdisjoint(forbidden)


def test_blender_exporter_requires_a_rigid_z_up_origin_mapping() -> None:
    module = exporter_module()
    identity = (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    assert module._source_origin({"source_origin_world": [0.0, 0.0, 0.0]}, identity) == (
        0.0,
        0.0,
        0.0,
    )
    with pytest.raises(module.SoftbodyExportError, match="must map source_origin_world"):
        module._source_origin({"source_origin_world": [1.0, 0.0, 0.0]}, identity)

    reflection = (
        (-1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    with pytest.raises(module.SoftbodyExportError, match="proper rigid"):
        module._validate_rigid_z_up(reflection)


def test_blender_exporter_fails_closed_outside_blender() -> None:
    module = exporter_module()
    with pytest.raises(module.SoftbodyExportError, match="inside Blender"):
        module.export_beamng_softbody({})


@pytest.mark.parametrize(
    ("key", "value", "suffixes"),
    [
        ("visual_path", "relative-output.dae", {".dae", ".gltf"}),
        ("manifest_path", "relative-manifest.json", {".json"}),
    ],
)
def test_blender_exporter_rejects_relative_output_paths(
    key: str, value: str, suffixes: set[str]
) -> None:
    module = exporter_module()

    with pytest.raises(module.SoftbodyExportError, match=rf"{key} must be an absolute path"):
        module._absolute_output_path({key: value}, key, suffixes)


def test_blender_exporter_accepts_real_blender_string_attribute_bytes() -> None:
    module = exporter_module()
    attribute = SimpleNamespace(
        domain="POINT",
        data_type="STRING",
        data=[SimpleNamespace(value=b"node_a"), SimpleNamespace(value=b"node_b")],
    )
    mesh = SimpleNamespace(
        attributes={module.NODE_ATTRIBUTE: attribute},
        vertices=[object(), object()],
    )

    assert module._mesh_node_ids(mesh) == ["node_a", "node_b"]


def test_blender_exporter_discovers_export_but_not_import_operators() -> None:
    module = exporter_module()

    def operator(*property_names: str) -> SimpleNamespace:
        rna = SimpleNamespace(
            properties=[SimpleNamespace(identifier=name) for name in property_names]
        )
        return SimpleNamespace(get_rna_type=lambda: rna)

    collada_export = operator("filepath", "selected")
    collada_import = operator("filepath")
    blender = SimpleNamespace(
        ops=SimpleNamespace(
            wm=SimpleNamespace(
                collada_export=collada_export,
                collada_import=collada_import,
            )
        )
    )

    assert module._discover_dae_operators(blender) == {"wm.collada_export": collada_export}
