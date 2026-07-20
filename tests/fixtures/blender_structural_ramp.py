"""Build a deterministic concrete-ramp scene and execute a staged handoff runner."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import bpy


def _arguments() -> tuple[Path, str]:
    try:
        separator = sys.argv.index("--")
        value = sys.argv[separator + 1]
    except (ValueError, IndexError) as exc:
        raise RuntimeError("expected -- <staged-runner.py>") from exc
    asset_name = sys.argv[separator + 2] if len(sys.argv) > separator + 2 else "live_ramp"
    return Path(value).resolve(), asset_name


def _add_group(obj: bpy.types.Object, name: str, indices: list[int]) -> None:
    group = obj.vertex_groups.new(name=name)
    group.add(indices, 1.0, "REPLACE")


def _ramp_mesh(name: str) -> bpy.types.Mesh:
    vertices = [
        (-1.0, -2.0, 0.0),
        (1.0, -2.0, 0.0),
        (1.0, 2.0, 0.0),
        (-1.0, 2.0, 0.0),
        (-1.0, -2.0, 1.5),
        (1.0, -2.0, 1.5),
    ]
    faces = [
        (0, 3, 2, 1),
        (3, 4, 5, 2),
        (0, 1, 5, 4),
        (0, 4, 3),
        (1, 2, 5),
    ]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def main() -> None:
    runner, asset_name = _arguments()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

    cage_mesh = _ramp_mesh(f"{asset_name}_physics_mesh")
    node_ids = cage_mesh.attributes.new("beamng_node_id", "STRING", "POINT")
    for index, item in enumerate(node_ids.data):
        item.value = f"ramp_{index}".encode()
    cage = bpy.data.objects.new(f"{asset_name}_physics", cage_mesh)
    scene.collection.objects.link(cage)
    _add_group(cage, "beamng_base", [0, 1, 2, 3])
    _add_group(cage, "beamng_ref", [0])
    _add_group(cage, "beamng_back", [3])
    _add_group(cage, "beamng_left", [1])
    _add_group(cage, "beamng_up", [4])

    visual_mesh = _ramp_mesh(f"{asset_name}_visual_mesh")
    material = bpy.data.materials.new(f"{asset_name}_material")
    material.diffuse_color = (0.45, 0.47, 0.5, 1.0)
    visual_mesh.materials.append(material)
    visual = bpy.data.objects.new(f"{asset_name}_visual", visual_mesh)
    scene.collection.objects.link(visual)

    runpy.run_path(str(runner), run_name="__main__")


if __name__ == "__main__":
    main()
