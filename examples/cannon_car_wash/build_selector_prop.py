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
from typing import Any

EXAMPLE_ROOT = Path(__file__).resolve().parent
MOD_ROOT = EXAMPLE_ROOT / "mod"
VEHICLE_ROOT = MOD_ROOT / "vehicles" / "cannon_car_wash"
HANDOFF_PATH = VEHICLE_ROOT / "cannon_car_wash.selector_handoff.json"
DAE_PATH = VEHICLE_ROOT / "cannon_car_wash.dae"
SOURCE_MATERIALS_PATH = (
    MOD_ROOT
    / "levels"
    / "gridmap_v2"
    / "art"
    / "shapes"
    / "carwash"
    / "cannon_car_wash.materials.json"
)
THUMBNAIL_SOURCE = MOD_ROOT / "mod_info" / "cannon_car_wash" / "icon.jpg"

MODEL_ID = "cannon_car_wash"
CONFIG_ID = "standard"
DISPLAY_NAME = "Cannon Car Wash"
AUTHOR = "beamng-mcp contributors"
GROUP = "cannon_car_wash"
BASE_NODE_MASS_KG = 500.0
STRUCTURE_NODE_MASS_KG = 125.0


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_bytes(value))


def load_handoff() -> dict[str, Any]:
    handoff = json.loads(HANDOFF_PATH.read_text(encoding="utf-8"))
    if handoff.get("schema") != "cannon-car-wash-selector-handoff-v1":
        raise ValueError("unsupported or missing selector handoff schema")
    if handoff.get("asset", {}).get("id") != MODEL_ID:
        raise ValueError("selector handoff model id does not match output model")
    visual = handoff.get("visual", {})
    if visual.get("path") != f"vehicles/{MODEL_ID}/{MODEL_ID}.dae":
        raise ValueError("selector handoff Collada path does not match output path")
    digest = hashlib.sha256(DAE_PATH.read_bytes()).hexdigest()
    if visual.get("sha256") != digest or visual.get("size") != DAE_PATH.stat().st_size:
        raise ValueError("selector Collada changed after Blender handoff extraction")
    return handoff


def build_jbeam(handoff: dict[str, Any]) -> tuple[dict[str, Any], float]:
    nodes = handoff["nodes"]
    base_ids = set(handoff["base_nodes"])
    node_ids = {node["id"] for node in nodes}
    if len(node_ids) != len(nodes):
        raise ValueError("selector handoff contains duplicate node ids")
    if not base_ids or not base_ids <= node_ids:
        raise ValueError("selector handoff base nodes are missing from the cage")

    node_rows: list[list[Any]] = [["id", "posX", "posY", "posZ"]]
    for node in nodes:
        fixed = node["id"] in base_ids
        node_rows.append(
            [
                node["id"],
                *node["position"],
                {
                    "collision": not fixed,
                    "fixed": fixed,
                    "frictionCoef": 0.9,
                    "group": GROUP,
                    "nodeMaterial": "|NM_METAL",
                    "nodeWeight": BASE_NODE_MASS_KG if fixed else STRUCTURE_NODE_MASS_KG,
                    "selfCollision": False,
                    "staticCollision": not fixed,
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
        if not selector_name.startswith("CWV_"):
            raise ValueError(f"unexpected selector material name: {selector_name}")
        source_name = f"CW_{selector_name.removeprefix('CWV_')}"
        if source_name not in source_materials:
            raise ValueError(f"no authored material definition for {selector_name}")
        definition = copy.deepcopy(source_materials[source_name])
        definition["name"] = selector_name
        definition["mapTo"] = selector_name
        definition["persistentId"] = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:cannon-car-wash:{selector_name}")
        )
        definition["materialTag0"] = "cannon_car_wash_selector"
        output[selector_name] = definition
    return output


def main() -> None:
    handoff = load_handoff()
    jbeam, total_mass = build_jbeam(handoff)
    materials = build_materials(handoff)

    write_json(VEHICLE_ROOT / f"{MODEL_ID}.jbeam", jbeam)
    write_json(VEHICLE_ROOT / "main.materials.json", materials)
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
