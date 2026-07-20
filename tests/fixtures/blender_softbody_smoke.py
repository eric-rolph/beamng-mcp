"""Create and export a minimal real Blender soft-body handoff fixture."""

from __future__ import annotations

import json
import math
import runpy
import sys
from pathlib import Path

import bpy


def _arguments() -> tuple[Path, Path, str]:
    try:
        separator = sys.argv.index("--")
        helper, output, case = sys.argv[separator + 1 : separator + 4]
    except (ValueError, IndexError) as exc:
        raise RuntimeError("expected -- <helper.py> <output-directory> <case>") from exc
    return Path(helper).resolve(), Path(output).resolve(), case


def _mesh(name: str) -> bpy.types.Mesh:
    vertices = [
        (-1.0, -1.0, -1.0),
        (1.0, -1.0, -1.0),
        (1.0, 1.0, -1.0),
        (-1.0, 1.0, -1.0),
        (-1.0, -1.0, 1.0),
        (1.0, -1.0, 1.0),
        (1.0, 1.0, 1.0),
        (-1.0, 1.0, 1.0),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def _add_group(obj: bpy.types.Object, name: str, indices: list[int]) -> None:
    group = obj.vertex_groups.new(name=name)
    group.add(indices, 1.0, "REPLACE")


def main() -> None:
    helper_path, output_dir, case = _arguments()
    if case not in {"identity", "transformed"}:
        raise RuntimeError(f"unsupported smoke case: {case}")
    output_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    cage_mesh = _mesh("smoke_asset_physics_mesh")
    node_ids = cage_mesh.attributes.new("beamng_node_id", "STRING", "POINT")
    for index, item in enumerate(node_ids.data):
        item.value = f"node_{index}".encode()
    cage = bpy.data.objects.new("smoke_asset_physics", cage_mesh)
    scene.collection.objects.link(cage)
    _add_group(cage, "beamng_base", [0, 1, 2, 3])
    _add_group(cage, "beamng_ref", [0])
    _add_group(cage, "beamng_back", [1])
    _add_group(cage, "beamng_left", [3])
    _add_group(cage, "beamng_up", [4])

    visual_mesh = _mesh("smoke_asset_visual_mesh")
    material = bpy.data.materials.new("smoke_asset_material")
    material.diffuse_color = (0.35, 0.35, 0.35, 1.0)
    visual_mesh.materials.append(material)
    visual = bpy.data.objects.new("smoke_asset_visual", visual_mesh)
    scene.collection.objects.link(visual)

    source_origin = [0.0, 0.0, 0.0]
    world_to_beamng = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    if case == "transformed":
        for obj in (cage, visual):
            obj.location = (3.0, -4.0, 2.0)
            obj.rotation_euler = (0.0, 0.0, math.pi / 2.0)
            obj.scale = (2.0, 1.0, 0.5)
        source_origin = [3.0, -4.0, 2.0]
        world_to_beamng = [
            [1.0, 0.0, 0.0, -3.0],
            [0.0, 1.0, 0.0, 4.0],
            [0.0, 0.0, 1.0, -2.0],
            [0.0, 0.0, 0.0, 1.0],
        ]

    bpy.context.view_layer.update()
    source_state = {
        obj.name: tuple(tuple(value for value in row) for row in obj.matrix_world)
        for obj in (cage, visual)
    }

    module = runpy.run_path(str(helper_path))
    result = module["export_beamng_softbody"](
        {
            "asset_id": "smoke_asset",
            "physics_cage": cage.name,
            "visual_objects": [visual.name],
            "world_to_beamng": world_to_beamng,
            "source_origin_world": source_origin,
            "visual_format": "dae",
            "visual_path": str(output_dir / "smoke_asset.dae"),
            "manifest_path": str(output_dir / "smoke_asset.structure.json"),
            "required_roles": ["beamng_ref", "beamng_back", "beamng_left", "beamng_up"],
        }
    )
    for name, matrix in source_state.items():
        restored = bpy.data.objects.get(name)
        if restored is None:
            raise RuntimeError(f"source object was removed during export: {name}")
        current = tuple(tuple(value for value in row) for row in restored.matrix_world)
        if any(
            abs(current[row][column] - matrix[row][column]) > 1e-9
            for row in range(4)
            for column in range(4)
        ):
            raise RuntimeError(f"source transform changed during export: {name}")
    result["case"] = case
    result["source_state_restored"] = True
    (output_dir / "result.json").write_text(
        json.dumps(result, sort_keys=True, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
