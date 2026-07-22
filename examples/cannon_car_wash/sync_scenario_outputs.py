"""Synchronize checked BeamNG scenario records with Blender authoring evidence."""

from __future__ import annotations

import hashlib
import json
import math
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
LIGHTING_LUA_PATH = EXAMPLE_ROOT / "mod" / "lua" / "common" / MOD_ID / "lighting.lua"
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


def _normalized(values: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in values))
    if not math.isfinite(length) or length < 1e-9:
        raise ValueError("cannot normalize an invalid light direction")
    return [value / length for value in values]


def _direction_rotation_matrix(direction: list[float]) -> list[float]:
    """Return BeamNG's column-major +Y-forward basis for a SpotLight."""

    forward = _normalized(direction)
    up_reference = [0.0, 0.0, 1.0]
    right = _normalized(
        [
            forward[1] * up_reference[2] - forward[2] * up_reference[1],
            forward[2] * up_reference[0] - forward[0] * up_reference[2],
            forward[0] * up_reference[1] - forward[1] * up_reference[0],
        ]
    )
    up = _normalized(
        [
            right[1] * forward[2] - right[2] * forward[1],
            right[2] * forward[0] - right[0] * forward[2],
            right[0] * forward[1] - right[1] * forward[0],
        ]
    )
    return [round(value, 9) for axis in (right, forward, up) for value in axis]


def _lua_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError("non-finite value in generated lighting Lua")
        return repr(value)
    if isinstance(value, list):
        return "{" + ", ".join(_lua_value(item) for item in value) + "}"
    raise TypeError(f"unsupported generated Lua value: {type(value)!r}")


def _write_lighting_lua(anchors: list[dict[str, Any]]) -> None:
    fields = (
        "name",
        "role",
        "class",
        "local_position",
        "local_direction",
        "color",
        "brightness",
        "radius",
        "range",
        "inner_angle_degrees",
        "outer_angle_degrees",
        "cast_shadows",
    )
    ordered_lines = [
        "-- Generated from the Blender geometry handoff by sync_scenario_outputs.py.",
        "-- Do not edit runtime light transforms independently.",
        "return {",
    ]
    for anchor in anchors:
        ordered_lines.append("  {")
        for field in fields:
            if field in anchor:
                ordered_lines.append(f"    {field} = {_lua_value(anchor[field])},")
        ordered_lines.append("  },")
    ordered_lines.append("}")
    LIGHTING_LUA_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIGHTING_LUA_PATH.write_text("\n".join(ordered_lines) + "\n", encoding="utf-8", newline="\n")


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

    trigger_definitions = (
        ("wash_activation_trigger", WASH_TRIGGER_NAME, "Overlaps", "0 160 255 35"),
        ("repair_trigger", REPAIR_TRIGGER_NAME, "Overlaps", "0 220 160 40"),
        ("trigger", LAUNCH_TRIGGER_NAME, "Contains", "255 96 0 45"),
    )
    trigger_records: dict[str, dict[str, Any]] = {}
    for geometry_key, name, mode, color in trigger_definitions:
        authored = geometry[geometry_key]
        if authored["name"] != name or authored["mode"] != mode:
            raise ValueError(f"unexpected Blender trigger contract: {geometry_key}")
        local_center = [float(value) for value in authored["center"]]
        dimensions = [float(value) for value in authored["dimensions"]]
        if (
            len(local_center) != 3
            or len(dimensions) != 3
            or any(value <= 0 for value in dimensions)
        ):
            raise ValueError(f"invalid Blender trigger transform: {name}")
        world_center = [round(asset_position[axis] + local_center[axis], 6) for axis in range(3)]
        phase2_trigger = {
            "name": name,
            "class": "BeamNGTrigger",
            "local_center": local_center,
            "world_center": world_center,
            "dimensions": dimensions,
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "lua_function": "onBeamNGTrigger",
            "mode": mode,
            "test_type": "Bounding box",
        }
        if geometry_key == "repair_trigger":
            phase2_trigger["repair_strategy"] = str(authored["repair_strategy"])
        phase2[geometry_key] = phase2_trigger
        trigger_records[name] = {
            "name": name,
            "class": "BeamNGTrigger",
            "persistentId": _persistent_id(name),
            "__parent": GROUP_NAME,
            "TriggerType": "Box",
            "triggerMode": mode,
            "triggerTestType": "Bounding box",
            "luaFunction": "onBeamNGTrigger",
            "tickPeriod": "100",
            "debug": "0",
            "debugInEditor": "0",
            "ticking": "0",
            "triggerColor": color,
            "defaultOnLeave": "0",
            "mode": "Ignore",
            "canSave": "1",
            "canSaveDynamicFields": "1",
            "position": world_center,
            "rotationMatrix": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            "scale": dimensions,
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

    light_anchors = geometry["lighting"]["anchors"]
    if (
        len(light_anchors) != 7
        or len({anchor["name"] for anchor in light_anchors}) != 7
        or Counter(anchor["class"] for anchor in light_anchors) != {"PointLight": 5, "SpotLight": 2}
    ):
        raise ValueError("Blender evidence must define five point and two spot light anchors")
    light_records: list[dict[str, Any]] = []
    synchronized_lights: list[dict[str, Any]] = []
    for anchor in light_anchors:
        local_position = [float(value) for value in anchor["local_position"]]
        color = [float(value) for value in anchor["color"]]
        if len(local_position) != 3 or len(color) != 3:
            raise ValueError(f"invalid Blender light anchor: {anchor['name']}")
        world_position = [
            round(asset_position[axis] + local_position[axis], 6) for axis in range(3)
        ]
        record: dict[str, Any] = {
            "name": str(anchor["name"]),
            "class": str(anchor["class"]),
            "persistentId": _persistent_id(str(anchor["name"])),
            "__parent": GROUP_NAME,
            "isEnabled": True,
            "color": [*color, 1.0],
            "brightness": float(anchor["brightness"]),
            "castShadows": bool(anchor["cast_shadows"]),
            "priority": 1,
            "attenuationRatio": [0.0, 1.0, 1.0],
            "texSize": 256,
            "canSave": "1",
            "canSaveDynamicFields": "1",
            "position": world_position,
            "scale": [1.0, 1.0, 1.0],
        }
        evidence = dict(anchor)
        evidence["world_position"] = world_position
        if anchor["class"] == "PointLight":
            record.update(
                {
                    "radius": float(anchor["radius"]),
                    "shadowType": "DualParaboloidSinglePass",
                    "rotationMatrix": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
                }
            )
        else:
            local_direction = [float(value) for value in anchor["local_direction"]]
            if len(local_direction) != 3:
                raise ValueError(f"invalid Blender spotlight direction: {anchor['name']}")
            rotation_matrix = _direction_rotation_matrix(local_direction)
            record.update(
                {
                    "range": float(anchor["range"]),
                    "innerAngle": float(anchor["inner_angle_degrees"]),
                    "outerAngle": float(anchor["outer_angle_degrees"]),
                    "shadowSoftness": 2.0,
                    "shadowType": "Spot",
                    "rotationMatrix": rotation_matrix,
                }
            )
            evidence["rotation_matrix"] = rotation_matrix
        light_records.append(record)
        synchronized_lights.append(evidence)
    _write_lighting_lua(light_anchors)

    rewritten_prefab: list[dict[str, Any]] = []
    synchronized_triggers: set[str] = set()
    effects_inserted = False
    for record in prefab:
        if record.get("class") in {"ParticleEmitterNode", "PointLight", "SpotLight"}:
            continue
        name = str(record.get("name"))
        if name in trigger_records:
            rewritten_prefab.append(trigger_records[name])
            synchronized_triggers.add(name)
        else:
            rewritten_prefab.append(record)
        if name == LAUNCH_TRIGGER_NAME:
            rewritten_prefab.extend(effect_records)
            rewritten_prefab.extend(light_records)
            effects_inserted = True
    if synchronized_triggers != set(trigger_records) or not effects_inserted:
        raise ValueError("prefab is missing a canonical trigger synchronization point")

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
    phase2["lighting"] = {
        "coordinate_space": geometry["lighting"]["coordinate_space"],
        "light_count": len(synchronized_lights),
        "class_counts": {"PointLight": 5, "SpotLight": 2},
        "lights": synchronized_lights,
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
                "light_count": len(synchronized_lights),
                "prefab_object_count": len(rewritten_prefab),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
