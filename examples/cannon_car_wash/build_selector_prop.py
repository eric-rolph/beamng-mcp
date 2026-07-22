"""Build the Cannon Car Wash vehicle-selector prop from Blender handoff evidence.

The Blender generator owns every coordinate. This script only translates its
checked handoff into BeamNG runtime files and refuses stale or incomplete input.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any, cast

EXAMPLE_ROOT = Path(__file__).resolve().parent
MOD_ROOT = EXAMPLE_ROOT / "mod"
MOD_ID = "ericrolph_cannon_car_wash"
AUTHORING_ROOT = EXAMPLE_ROOT / "authoring"
VEHICLE_ROOT = MOD_ROOT / "vehicles" / MOD_ID
HANDOFF_PATH = AUTHORING_ROOT / f"{MOD_ID}.selector_handoff.json"
DAE_PATH = VEHICLE_ROOT / f"{MOD_ID}.dae"
ANIMATED_DAE_PATH = VEHICLE_ROOT / f"{MOD_ID}_runtime_visual.dae"
SOURCE_ANIMATED_DAE_PATH = MOD_ROOT / "art" / "shapes" / MOD_ID / f"{MOD_ID}.dae"
SOURCE_MATERIALS_PATH = (
    MOD_ROOT / "levels" / "gridmap_v2" / "scenarios" / MOD_ID / "main.materials.json"
)
THUMBNAIL_SOURCE = MOD_ROOT / "levels" / "gridmap_v2" / "scenarios" / MOD_ID / f"{MOD_ID}.jpg"

MODEL_ID = MOD_ID
CONFIG_ID = "standard"
DISPLAY_NAME = "Cannon Car Wash"
AUTHOR = "Eric Rolph"
GROUP = f"{MOD_ID}_physics"
BASE_NODE_MASS_KG = 500.0
STRUCTURE_NODE_MASS_KG = 125.0


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_bytes(value))


def load_handoff() -> dict[str, Any]:
    handoff = json.loads(HANDOFF_PATH.read_text(encoding="utf-8"))
    if handoff.get("schema") != "ericrolph-cannon-car-wash-selector-handoff-v1":
        raise ValueError("unsupported or missing selector handoff schema")
    if handoff.get("asset", {}).get("id") != MODEL_ID:
        raise ValueError("selector handoff model id does not match output model")
    visual = handoff.get("visual", {})
    if visual.get("path") != f"vehicles/{MODEL_ID}/{MODEL_ID}.dae":
        raise ValueError("selector handoff Collada path does not match output path")
    digest = hashlib.sha256(DAE_PATH.read_bytes()).hexdigest()
    if visual.get("sha256") != digest or visual.get("size") != DAE_PATH.stat().st_size:
        raise ValueError("selector Collada changed after Blender handoff extraction")
    return cast(dict[str, Any], handoff)


def build_jbeam(handoff: dict[str, Any]) -> tuple[dict[str, Any], float]:
    nodes = handoff["nodes"]
    base_ids = set(handoff["base_nodes"])
    spawn_envelope_ids = set(handoff["spawn_envelope_nodes"])
    node_ids = {node["id"] for node in nodes}
    if len(node_ids) != len(nodes):
        raise ValueError("selector handoff contains duplicate node ids")
    if not base_ids or not base_ids <= node_ids:
        raise ValueError("selector handoff base nodes are missing from the cage")
    if len(spawn_envelope_ids) != 8 or not spawn_envelope_ids <= node_ids:
        raise ValueError("selector handoff spawn envelope must contain eight cage nodes")

    node_rows: list[list[Any]] = [["id", "posX", "posY", "posZ"]]
    for node in nodes:
        is_base = node["id"] in base_ids
        is_spawn_envelope = node["id"] in spawn_envelope_ids
        node_rows.append(
            [
                node["id"],
                *node["position"],
                {
                    # The selector model is infrastructure, not a deformable
                    # vehicle. Fix the entire measured shell so its coplanar
                    # panels cannot fold through zero-stiffness modes.
                    # BeamNG's safe-spawn/Vehicle Selector placement builds an
                    # OOBB only from collidable initial nodes.  Eight authored
                    # exterior corners provide that grounding envelope; the
                    # collision triangles remain the actual wash surface.
                    "collision": is_spawn_envelope,
                    "fixed": True,
                    "frictionCoef": 0.9,
                    "group": GROUP,
                    "nodeMaterial": "|NM_METAL",
                    "nodeWeight": BASE_NODE_MASS_KG if is_base else STRUCTURE_NODE_MASS_KG,
                    "selfCollision": False,
                    "staticCollision": is_spawn_envelope,
                },
            ]
        )

    beam_rows: list[list[Any]] = [["id1:", "id2:"]]
    for first, second in handoff["beams"]:
        if first not in node_ids or second not in node_ids:
            raise ValueError(f"beam references unknown node: {first}, {second}")
        beam_rows.append(
            [
                first,
                second,
                {
                    "beamDamp": 1500.0,
                    "beamDeform": "FLT_MAX",
                    "beamSpring": 15000000.0,
                    "beamStrength": "FLT_MAX",
                },
            ]
        )

    triangle_rows: list[list[Any]] = [["id1:", "id2:", "id3:"]]
    for triangle in handoff["triangles"]:
        triangle_nodes = triangle["nodes"]
        if len(triangle_nodes) != 3 or not set(triangle_nodes) <= node_ids:
            raise ValueError(f"triangle references invalid nodes: {triangle_nodes}")
        ground_model = "asphalt" if triangle["surface"].startswith("floor") else "metal"
        triangle_rows.append([*triangle_nodes, {"groundModel": ground_model}])

    refnodes = handoff["refnodes"]
    if not set(refnodes.values()) <= node_ids:
        raise ValueError("reference nodes are missing from the cage")
    total_mass = (
        len(base_ids) * BASE_NODE_MASS_KG + (len(nodes) - len(base_ids)) * STRUCTURE_NODE_MASS_KG
    )
    part = {
        "information": {"authors": AUTHOR, "name": DISPLAY_NAME},
        "slotType": "main",
        "cameraExternal": {
            "distance": 25.0,
            "distanceMin": 7.0,
            "fov": 65.0,
            "offset": {"x": 0.0, "y": 0.0, "z": 2.5},
        },
        "refNodes": [
            ["ref:", "back:", "left:", "up:"],
            [refnodes["ref"], refnodes["back"], refnodes["left"], refnodes["up"]],
        ],
        "flexbodies": [
            ["mesh", "[group]:"],
            [handoff["asset"]["visual_mesh"], [GROUP]],
        ],
        "nodes": node_rows,
        "beams": beam_rows,
        "triangles": triangle_rows,
    }
    return {MODEL_ID: part}, total_mass


def build_materials(handoff: dict[str, Any]) -> dict[str, Any]:
    source_materials = json.loads(SOURCE_MATERIALS_PATH.read_text(encoding="utf-8"))
    output: dict[str, Any] = {}
    for selector_name in handoff["visual"]["materials"]:
        selector_prefix = f"{MOD_ID}_selector_"
        if not selector_name.startswith(selector_prefix):
            raise ValueError(f"unexpected selector material name: {selector_name}")
        source_name = f"{MOD_ID}_{selector_name.removeprefix(selector_prefix)}"
        if source_name not in source_materials:
            raise ValueError(f"no authored material definition for {selector_name}")
        definition = copy.deepcopy(source_materials[source_name])
        definition["name"] = selector_name
        definition["mapTo"] = selector_name
        definition["persistentId"] = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"beamng-mcp:{MOD_ID}:{selector_name}",
            )
        )
        definition["materialTag0"] = f"{MOD_ID}_selector"
        output[selector_name] = definition
    return output


def build_animated_runtime_visual(handoff: dict[str, Any]) -> None:
    """Create the selector's animated TSStatic using vehicle-local material slots.

    BeamNG loads vehicle materials before vehicle Lua, while material files under
    another level are not part of the active Smallgrid load scope.  Preserve the
    authored Collada geometry and animation byte-for-byte except for the exact
    material/effect identifiers that must bind to the selector-prefixed material
    definitions already present in this vehicle directory.
    """

    payload = SOURCE_ANIMATED_DAE_PATH.read_text(encoding="utf-8")
    for selector_name in handoff["visual"]["materials"]:
        selector_prefix = f"{MOD_ID}_selector_"
        if not selector_name.startswith(selector_prefix):
            raise ValueError(f"unexpected selector material name: {selector_name}")
        source_name = f"{MOD_ID}_{selector_name.removeprefix(selector_prefix)}"
        replacements = (
            (f'"{source_name}-material"', f'"{selector_name}-material"'),
            (f'"#{source_name}-material"', f'"#{selector_name}-material"'),
            (f'"{source_name}-effect"', f'"{selector_name}-effect"'),
            (f'"#{source_name}-effect"', f'"#{selector_name}-effect"'),
            (f'name="{source_name}"', f'name="{selector_name}"'),
        )
        replacement_count = 0
        for old, new in replacements:
            count = payload.count(old)
            payload = payload.replace(old, new)
            replacement_count += count
        if replacement_count == 0:
            raise ValueError(f"animated Collada does not use material {source_name}")
    if "<library_animations>" not in payload or 'animation_clip id="ambient"' not in payload:
        raise ValueError("animated selector Collada lost its ambient brush animation")
    ANIMATED_DAE_PATH.write_text(payload, encoding="utf-8", newline="")


def main() -> None:
    handoff = load_handoff()
    jbeam, total_mass = build_jbeam(handoff)
    materials = build_materials(handoff)

    write_json(VEHICLE_ROOT / f"{MODEL_ID}.jbeam", jbeam)
    write_json(VEHICLE_ROOT / "main.materials.json", materials)
    build_animated_runtime_visual(handoff)
    write_json(
        VEHICLE_ROOT / "info.json",
        {
            "Author": AUTHOR,
            "Name": DISPLAY_NAME,
            "Type": "Prop",
            "default_pc": CONFIG_ID,
        },
    )
    write_json(
        VEHICLE_ROOT / f"{CONFIG_ID}.pc",
        {
            "format": 2,
            "mainPartName": MODEL_ID,
            "model": MODEL_ID,
            "parts": {},
        },
    )
    write_json(
        VEHICLE_ROOT / f"info_{CONFIG_ID}.json",
        {
            "Configuration": "Standard",
            "Value": 150000,
            "Weight": total_mass,
        },
    )
    shutil.copyfile(THUMBNAIL_SOURCE, VEHICLE_ROOT / "default.jpg")
    shutil.copyfile(THUMBNAIL_SOURCE, VEHICLE_ROOT / f"{CONFIG_ID}.jpg")
    print(
        json.dumps(
            {
                "model": MODEL_ID,
                "configuration": CONFIG_ID,
                "nodes": len(handoff["nodes"]),
                "beams": len(handoff["beams"]),
                "triangles": len(handoff["triangles"]),
                "mass_kg": total_mass,
                "visual_sha256": handoff["visual"]["sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
