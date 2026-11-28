"""Blender-headless placeholder forest shapes for the level scaffold (tree + rock).

Run (Blender 4.5.4, the validated runtime)::

    $script = 'examples/hot_potato_arena/level/blender_placeholders.py'
    $out = 'examples/hot_potato_arena/mod/levels/ericrolph_hot_potato_arena/' +
        'art/shapes/hot_potato_arena_forest'
    & $blender454 --factory-startup --background --python $script -- --out $out

The module's constants are importable without ``bpy`` (``level_writer`` and the
live gate use the analytic geometry to predict ray hits); ``bpy`` is imported
only inside the build functions.

Node trees follow the stock trailing-number convention read from
``template.zip``'s ``tro_bush_small.dae`` (``base00 -> start01 -> {<name>_a250,
<name>_a550, Colmesh-1}``) and the arena laws (AGENTS.md: detail nodes under
``base00/start01``; ``Colmesh-1`` is the collision mesh):

    tree: base00 -> start01 -> {<id>_tree_a200 (16-segment), <id>_tree_a4 (6-segment), Colmesh-1}
    rock: base00 -> start01 -> {<id>_rock_a4 (icosphere subdiv 2), Colmesh-1 (subdiv 1)}

Geometry (local metres, origin at the trunk base / rock centre-bottom):
trunk cylinder r 0.25 x h 3.0; canopy cone r 2.0 from z 2.5 to 8.5; rock =
unit icosphere scaled (1.2, 0.9, 0.7) and lifted so its bottom sits at z 0.
Materials are named so ``<id>_forest.materials.json`` binds them by ``mapTo``
(the proven arena pattern: Blender writes ``<material name="<material name>">``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

LEVEL_ID = "ericrolph_hot_potato_arena"
TREE_DAE_NAME = f"{LEVEL_ID}_tree.dae"
ROCK_DAE_NAME = f"{LEVEL_ID}_rock.dae"
TREE_BARK_MATERIAL = f"{LEVEL_ID}_bark"
TREE_CANOPY_MATERIAL = f"{LEVEL_ID}_canopy"
# NOT "<id>_rock": the forest datablock is named that, and the SimObject namespace
# is global across classes - boot 1 run 1 logged "Cannot re-declare object
# [ericrolph_hot_potato_arena_rock] with a different class [material] - was
# [TSForestItemData]" and every rock instance was then dropped.
ROCK_MATERIAL = f"{LEVEL_ID}_stone"
TREE_NEAR_PX = 200
TREE_FAR_PX = 4
ROCK_DETAIL_PX = 4
TREE_NEAR_NODE = f"{LEVEL_ID}_tree_a{TREE_NEAR_PX}"
TREE_FAR_NODE = f"{LEVEL_ID}_tree_a{TREE_FAR_PX}"
ROCK_NODE = f"{LEVEL_ID}_rock_a{ROCK_DETAIL_PX}"
COLMESH_NODE = "Colmesh-1"
TREE_TRUNK_R = 0.25
TREE_TRUNK_H = 3.0
TREE_CANOPY_R = 2.0
TREE_CANOPY_BASE_Z = 2.5
TREE_CANOPY_TOP_Z = 8.5
TREE_NEAR_SEGMENTS = 16
TREE_FAR_SEGMENTS = 6
TREE_COLMESH_SEGMENTS = 16
ROCK_SCALE = (1.2, 0.9, 0.7)
ROCK_SUBDIVISIONS = 2
ROCK_COLMESH_SUBDIVISIONS = 1
COLLADA_NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}
EXPECTED_TREE_TREE = {
    "base00": None,
    "start01": "base00",
    TREE_NEAR_NODE: "start01",
    TREE_FAR_NODE: "start01",
    COLMESH_NODE: "start01",
}
EXPECTED_ROCK_TREE = {
    "base00": None,
    "start01": "base00",
    ROCK_NODE: "start01",
    COLMESH_NODE: "start01",
}


def canopy_flank_z(lateral_offset_m: float, scale: float) -> tuple[float, float]:
    """Local-z window where a vertical ray ``lateral_offset_m`` off the axis meets the canopy cone.

    Returns (low, high) in world metres above the tree base: the faceted cone's
    radius at a given height lies between the inscribed radius (cos(pi/n) * R)
    and R, so the hit height is a window rather than a point.
    """

    import math

    height = TREE_CANOPY_TOP_Z - TREE_CANOPY_BASE_Z
    inscribed = math.cos(math.pi / TREE_COLMESH_SEGMENTS)
    d = lateral_offset_m / scale
    t_high = 1.0 - d / TREE_CANOPY_R
    t_low = 1.0 - d / (TREE_CANOPY_R * inscribed)
    return (
        scale * (TREE_CANOPY_BASE_Z + t_low * height),
        scale * (TREE_CANOPY_BASE_Z + t_high * height),
    )


def rock_top_z(scale: float) -> tuple[float, float]:
    """World-metre window for a vertical ray at the rock's axis (faces sit inside the sphere)."""

    return (scale * ROCK_SCALE[2] * 2.0 * 0.92, scale * ROCK_SCALE[2] * 2.0)


def dae_node_parents(dae_path: Path) -> dict[str, str | None]:
    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()  # noqa: S314 - a DAE this module wrote itself
    scene = root.find("c:library_visual_scenes/c:visual_scene", COLLADA_NS)
    out: dict[str, str | None] = {}

    def walk(node, parent):
        for child in node.findall("c:node", COLLADA_NS):
            name = child.get("name") or child.get("id")
            out[name] = parent
            walk(child, name)

    walk(scene, None)
    return out


def dae_material_names(dae_path: Path) -> set[str]:
    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()  # noqa: S314 - a DAE this module wrote itself
    return {m.get("name") for m in root.iter(f"{{{COLLADA_NS['c']}}}material")}


def dae_tri_count(dae_path: Path) -> int:
    import xml.etree.ElementTree as ET

    root = ET.parse(dae_path).getroot()  # noqa: S314 - a DAE this module wrote itself
    return sum(int(t.get("count")) for t in root.iter(f"{{{COLLADA_NS['c']}}}triangles"))


# --- Blender side -------------------------------------------------------------------


def _material(name: str, rgba: tuple[float, float, float, float]):
    import bpy

    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = rgba
    return material


def _empty(name: str, parent=None):
    import bpy

    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    return obj


def _set_material(obj, material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(material)


def _join(objects, name: str, parent):
    import bpy

    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    joined.data.name = name
    joined.parent = parent
    bpy.ops.object.select_all(action="DESELECT")
    return joined


def _tree_mesh(name: str, segments: int, parent, bark, canopy):
    import bpy

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=segments,
        radius=TREE_TRUNK_R,
        depth=TREE_TRUNK_H,
        location=(0.0, 0.0, TREE_TRUNK_H / 2.0),
    )
    trunk = bpy.context.active_object
    _set_material(trunk, bark)
    height = TREE_CANOPY_TOP_Z - TREE_CANOPY_BASE_Z
    bpy.ops.mesh.primitive_cone_add(
        vertices=segments,
        radius1=TREE_CANOPY_R,
        radius2=0.0,
        depth=height,
        location=(0.0, 0.0, TREE_CANOPY_BASE_Z + height / 2.0),
    )
    cone = bpy.context.active_object
    _set_material(cone, canopy)
    return _join([trunk, cone], name, parent)


def _rock_mesh(name: str, subdivisions: int, parent, material):
    import bpy

    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=subdivisions, radius=1.0, location=(0.0, 0.0, 0.0)
    )
    rock = bpy.context.active_object
    rock.scale = ROCK_SCALE
    rock.location = (0.0, 0.0, ROCK_SCALE[2])
    bpy.ops.object.select_all(action="DESELECT")
    rock.select_set(True)
    bpy.context.view_layer.objects.active = rock
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _set_material(rock, material)
    rock.name = name
    rock.data.name = name
    rock.parent = parent
    bpy.ops.object.select_all(action="DESELECT")
    return rock


def _export(
    nodes, dae_path: Path, expected_tree: dict[str, str | None], expected_materials: set[str]
) -> dict:
    import bpy

    dae_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in nodes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = nodes[0]
    result = bpy.ops.wm.collada_export(
        filepath=str(dae_path),
        check_existing=False,
        selected=True,
        include_children=True,
        include_animations=False,
        include_all_actions=False,
        apply_modifiers=True,
        triangulate=True,
        use_texture_copies=False,
        apply_global_orientation=True,
        export_global_forward_selection="Y",
        export_global_up_selection="Z",
        sort_by_name=True,
    )
    if "FINISHED" not in result:
        raise SystemExit(f"Collada export failed for {dae_path.name}: {result}")
    bpy.ops.object.select_all(action="DESELECT")
    # LF law: the exporter writes CRLF on Windows; the zip builder refuses CR bytes in .dae.
    raw = dae_path.read_bytes().replace(b"\r\n", b"\n")
    dae_path.write_bytes(raw)
    actual = dae_node_parents(dae_path)
    for name, parent in expected_tree.items():
        if name not in actual:
            raise SystemExit(f"{dae_path.name}: node {name} missing from the export")
        if actual[name] != parent:
            raise SystemExit(
                f"{dae_path.name}: node {name} is under {actual[name]!r}, authored under {parent!r}"
            )
    extra = set(actual) - set(expected_tree)
    if extra:
        raise SystemExit(f"{dae_path.name}: unexpected nodes {sorted(extra)}")
    materials = dae_material_names(dae_path)
    if materials != expected_materials:
        raise SystemExit(
            f"{dae_path.name}: materials {sorted(materials)} != {sorted(expected_materials)}"
        )
    return {
        "file": dae_path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": len(raw),
        "triangles": dae_tri_count(dae_path),
        "node_parents": actual,
        "materials": sorted(materials),
    }


def _clear_scene() -> None:
    import bpy

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def build(out_dir: Path) -> dict:
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    manifest: dict = {"level_id": LEVEL_ID, "blender": bpy.app.version_string, "shapes": {}}

    bark = _material(TREE_BARK_MATERIAL, (0.42, 0.30, 0.20, 1.0))
    canopy = _material(TREE_CANOPY_MATERIAL, (0.18, 0.40, 0.14, 1.0))
    base = _empty("base00")
    start = _empty("start01", base)
    near = _tree_mesh(TREE_NEAR_NODE, TREE_NEAR_SEGMENTS, start, bark, canopy)
    far = _tree_mesh(TREE_FAR_NODE, TREE_FAR_SEGMENTS, start, bark, canopy)
    col = _tree_mesh(COLMESH_NODE, TREE_COLMESH_SEGMENTS, start, bark, canopy)
    manifest["shapes"]["tree"] = _export(
        [base, start, near, far, col],
        out_dir / TREE_DAE_NAME,
        EXPECTED_TREE_TREE,
        {TREE_BARK_MATERIAL, TREE_CANOPY_MATERIAL},
    )
    _clear_scene()

    rock_material = _material(ROCK_MATERIAL, (0.48, 0.47, 0.45, 1.0))
    base = _empty("base00")
    start = _empty("start01", base)
    rock = _rock_mesh(ROCK_NODE, ROCK_SUBDIVISIONS, start, rock_material)
    col = _rock_mesh(COLMESH_NODE, ROCK_COLMESH_SUBDIVISIONS, start, rock_material)
    manifest["shapes"]["rock"] = _export(
        [base, start, rock, col], out_dir / ROCK_DAE_NAME, EXPECTED_ROCK_TREE, {ROCK_MATERIAL}
    )
    _clear_scene()
    manifest["geometry"] = {
        "trunk_r": TREE_TRUNK_R,
        "trunk_h": TREE_TRUNK_H,
        "canopy_r": TREE_CANOPY_R,
        "canopy_base_z": TREE_CANOPY_BASE_Z,
        "canopy_top_z": TREE_CANOPY_TOP_Z,
        "rock_scale": list(ROCK_SCALE),
    }
    return manifest


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    arguments = parser.parse_args(argv)
    manifest = build(arguments.out)
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if arguments.manifest is not None:
        arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
        arguments.manifest.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
