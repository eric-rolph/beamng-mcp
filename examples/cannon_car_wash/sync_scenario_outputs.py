"""Synchronize checked BeamNG scenario records with Blender authoring evidence."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

EXAMPLE_ROOT = Path(__file__).resolve().parent
MOD_ID = "ericrolph_cannon_car_wash"
GEOMETRY_PATH = EXAMPLE_ROOT / "authoring" / f"{MOD_ID}.geometry.json"
PHASE2_PATH = EXAMPLE_ROOT / "validation" / "manifests" / "phase2.json"
SCENARIO_ROOT = EXAMPLE_ROOT / "mod" / "levels" / "gridmap_v2" / "scenarios" / MOD_ID
PREFAB_PATH = SCENARIO_ROOT / f"{MOD_ID}.prefab.json"
DAE_PATH = EXAMPLE_ROOT / "mod" / "art" / "shapes" / MOD_ID / f"{MOD_ID}.dae"
GROUP_NAME = f"{MOD_ID}_group"
WASH_TRIGGER_NAME = f"{MOD_ID}_wash_activation_trigger"
LAUNCH_TRIGGER_NAME = f"{MOD_ID}_launch_trigger"
REPAIR_TRIGGER_NAME = f"{MOD_ID}_repair_trigger"


def _persistent_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"beamng-mcp:{MOD_ID}:{name}"))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _prefab_records(path: Path) -> list[dict[str, Any]]:
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not records or not all(isinstance(record, dict) for record in records):
        raise ValueError(f"expected newline-delimited prefab objects: {path}")
    return records


def main() -> None:
    geometry = _read_json(GEOMETRY_PATH)
    phase2 = _read_json(PHASE2_PATH)
    prefab = _prefab_records(PREFAB_PATH)
    prefab_by_name = {str(record.get("name")): record for record in prefab}
    if len(prefab_by_name) != len(prefab):
        raise ValueError("prefab contains duplicate or missing object names")

    asset_position = [float(value) for value in phase2["asset"]["position"]]
    specs = geometry["wash_effects"]["effects"]
    emitter_counts = Counter(str(spec["emitter"]) for spec in specs)
    expected_counts = {
        "BNGP_sprinkler": 6,
        "BNGP_waterfallsteam": 6,
        "BNGP_34": 2,
        "BNGP_2": 2,
    }
    if (
        len(specs) != 16
        or len({spec["name"] for spec in specs}) != 16
        or dict(emitter_counts) != expected_counts
    ):
        raise ValueError(
            "Blender evidence must define the exact sixteen-node water/dryer inventory"
        )

    synchronized: list[dict[str, Any]] = []
    for spec in specs:
        name = str(spec["name"])
        local_position = [float(value) for value in spec["local_position"]]
        rotation_matrix = [float(value) for value in spec["rotation_matrix"]]
        scale = [float(value) for value in spec["scale"]]
        if len(local_position) != 3 or len(rotation_matrix) != 9 or len(scale) != 3:
            raise ValueError(f"invalid Blender effect transform: {name}")
        world_position = [
            round(asset_position[axis] + local_position[axis], 6) for axis in range(3)
        ]
        synchronized.append(
            {
                "name": name,
                "local_position": local_position,
                "world_position": world_position,
                "rotation_matrix": rotation_matrix,
                "scale": scale,
                "role": str(spec["role"]),
                "requested_particle": str(spec["requested_particle"]),
                "emitter": str(spec["emitter"]),
                "particle_data": str(spec["particle_data"]),
            }
        )

    repair = geometry["repair_trigger"]
    repair_local_center = [float(value) for value in repair["center"]]
    repair_dimensions = [float(value) for value in repair["dimensions"]]
    repair_world_center = [
        round(asset_position[axis] + repair_local_center[axis], 6) for axis in range(3)
    ]
    phase2["repair_trigger"] = {
        "name": REPAIR_TRIGGER_NAME,
        "class": "BeamNGTrigger",
        "local_center": repair_local_center,
        "world_center": repair_world_center,
        "dimensions": repair_dimensions,
        "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "lua_function": "onBeamNGTrigger",
        "mode": "Overlaps",
        "test_type": "Bounding box",
        "repair_strategy": "RESET_PHYSICS",
    }

    repair_record = {
        "name": REPAIR_TRIGGER_NAME,
        "class": "BeamNGTrigger",
        "persistentId": _persistent_id(REPAIR_TRIGGER_NAME),
        "__parent": GROUP_NAME,
        "TriggerType": "Box",
        "triggerMode": "Overlaps",
        "triggerTestType": "Bounding box",
        "luaFunction": "onBeamNGTrigger",
        "tickPeriod": "100",
        "debug": "0",
        "debugInEditor": "0",
        "ticking": "0",
        "triggerColor": "0 220 160 40",
        "defaultOnLeave": "0",
        "mode": "Ignore",
        "canSave": "1",
        "canSaveDynamicFields": "1",
        "position": repair_world_center,
        "rotationMatrix": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "scale": repair_dimensions,
    }
    effect_records = [
        {
            "name": effect["name"],
            "class": "ParticleEmitterNode",
            "persistentId": _persistent_id(effect["name"]),
            "__parent": GROUP_NAME,
            "dataBlock": geometry["wash_effects"]["node_datablock"],
            "emitter": effect["emitter"],
            "active": False,
            "position": effect["world_position"],
            "rotationMatrix": effect["rotation_matrix"],
            "scale": effect["scale"],
        }
        for effect in synchronized
    ]

    base_records = [
        record
        for record in prefab
        if record.get("class") != "ParticleEmitterNode"
        and record.get("name") != REPAIR_TRIGGER_NAME
    ]
    rewritten_prefab: list[dict[str, Any]] = []
    repair_inserted = False
    effects_inserted = False
    for record in base_records:
        rewritten_prefab.append(record)
        if record.get("name") == WASH_TRIGGER_NAME:
            rewritten_prefab.append(repair_record)
            repair_inserted = True
        if record.get("name") == LAUNCH_TRIGGER_NAME:
            rewritten_prefab.extend(effect_records)
            effects_inserted = True
    if not repair_inserted or not effects_inserted:
        raise ValueError("prefab is missing a canonical wash or launch trigger insertion point")

    phase2["asset"]["sha256"] = hashlib.sha256(DAE_PATH.read_bytes()).hexdigest()
    phase2["wash_effects"] = {
        "visual_name": geometry["wash_effects"]["roller_visual"],
        "roller_sequence": geometry["wash_effects"]["roller_sequence"],
        "roller_control_field": "playAmbient",
        "node_datablock": geometry["wash_effects"]["node_datablock"],
        "requested_to_runtime": geometry["wash_effects"]["requested_to_runtime"],
        "emitter_counts": expected_counts,
        "effects": synchronized,
    }
    PHASE2_PATH.write_text(
        json.dumps(phase2, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    PREFAB_PATH.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in rewritten_prefab),
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "asset_sha256": phase2["asset"]["sha256"],
                "effect_count": len(synchronized),
                "prefab_object_count": len(rewritten_prefab),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
