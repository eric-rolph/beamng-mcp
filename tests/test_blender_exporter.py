from __future__ import annotations

import ast
import importlib
from importlib.resources import files

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
