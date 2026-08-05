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
SOURCE_MINI_CAR_PATH = MOD_ROOT / "art" / "shapes" / MOD_ID / "mini_car.dae"
MINI_CAR_DAE_PATH = VEHICLE_ROOT / "mini_car.dae"
SOURCE_CANNON_PATH = MOD_ROOT / "art" / "shapes" / MOD_ID / "cannon.dae"
CANNON_DAE_PATH = VEHICLE_ROOT / "cannon.dae"
SOURCE_RAMP_FLAP_PATH = MOD_ROOT / "art" / "shapes" / MOD_ID / "ramp_flap.dae"
SOURCE_CARRIAGE_PATH = MOD_ROOT / "art" / "shapes" / MOD_ID / "carriage.dae"
CARRIAGE_DAE_PATH = VEHICLE_ROOT / "carriage.dae"
RAMP_FLAP_DAE_PATH = VEHICLE_ROOT / "ramp_flap.dae"
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
# v1.22 mitter cloth: light free nodes on soft beams so the strips drape,
# flap, and get shouldered aside by traffic. Spring/mass sized for solver
# stability (omega = sqrt(12000/6) ~= 45 rad/s, far under the ~2 kHz step)
# with near-critical damping so strips flop once and settle instead of
# oscillating; scaled down from the proven spider-web strand recipe.
# First live tune caught cars like the spider web (48 kg strips on
# unbreakable anchored chains slung an etk800 120 m back out the door).
# Real mitter strips are feather-light, floppy, and slippery: they must
# LOSE every argument with a bumper.
CLOTH_NODE_MASS_KG = 1.0
PANEL_NODE_MASS_KG = 2.0
CLOTH_STRUCTURAL_SPRING = 2500.0
CLOTH_STRUCTURAL_DAMP = 60.0
CLOTH_SHEAR_SPRING = 800.0
CLOTH_SHEAR_DAMP = 25.0
ANCHOR_SPRING = 15000000.0
ANCHOR_DAMP = 1500.0


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

    # v1.22 mitter cloth lattice: anchors pin to world space exactly like the
    # rest of the (entirely fixed) cage; the free nodes below them are the
    # only mobile physics in the prop and carry the vehicle-facing collision.
    cloth = handoff["cloth"]
    cloth_group = cloth["group"]
    cloth_node_ids = {node["id"] for node in cloth["nodes"]}
    if cloth_node_ids & node_ids:
        raise ValueError("cloth node ids collide with cage node ids")
    if len(cloth_node_ids) != len(cloth["nodes"]):
        raise ValueError("cloth handoff contains duplicate node ids")
    cloth_free_count = 0
    for node in cloth["nodes"]:
        fixed = bool(node["fixed"])
        if not fixed:
            cloth_free_count += 1
        node_rows.append(
            [
                node["id"],
                *node["position"],
                {
                    "collision": not fixed,
                    "fixed": fixed,
                    "frictionCoef": 0.2,
                    "group": cloth_group,
                    "nodeMaterial": "|NM_RUBBER",
                    "nodeWeight": CLOTH_NODE_MASS_KG,
                    "selfCollision": False,
                    "staticCollision": False,
                },
            ]
        )
    cloth_beam_options = {
        "anchor": (ANCHOR_SPRING, ANCHOR_DAMP),
        "structural": (CLOTH_STRUCTURAL_SPRING, CLOTH_STRUCTURAL_DAMP),
        "shear": (CLOTH_SHEAR_SPRING, CLOTH_SHEAR_DAMP),
    }
    for beam in cloth["beams"]:
        first, second = beam["nodes"]
        if first not in cloth_node_ids or second not in cloth_node_ids:
            raise ValueError(f"cloth beam references unknown node: {first}, {second}")
        spring, damp = cloth_beam_options[beam["class"]]
        beam_rows.append(
            [
                first,
                second,
                {
                    "beamDamp": damp,
                    "beamDeform": "FLT_MAX",
                    "beamSpring": spring,
                    "beamStrength": "FLT_MAX",
                },
            ]
        )
    for triangle in cloth["triangles"]:
        triangle_nodes = triangle["nodes"]
        if len(triangle_nodes) != 3 or not set(triangle_nodes) <= cloth_node_ids:
            raise ValueError(f"cloth triangle references invalid nodes: {triangle_nodes}")
        triangle_rows.append([*triangle_nodes, {"groundModel": "metal"}])

    # v1.38 dashboard-style panel buttons: one dedicated FIXED anchor node
    # per button cap plus a frame node behind the wall. Each triggers2 click
    # box sits exactly ON its own node (zero translation), so the engine's
    # node-frame math cannot drift the button off the printed door art.
    panel_buttons = handoff.get("panel_buttons", [])
    if len(panel_buttons) != 5:
        raise ValueError("selector handoff must carry exactly five panel buttons")
    panel_node_ids: list[str] = []

    # v1.39 probe ground truth (getTrigger:getCenter): jbeam nodes live in
    # UNFLIPPED authored coordinates while the visual mesh carries the
    # 180-degree model alignment - the click boxes landed on the opposite
    # building corner from the rendered buttons. Apply the handoff's own
    # source->vehicle transform (negate x, y) to the anchor nodes so the
    # boxes sit on the buttons the player actually sees.
    def _vehicle_space(position):
        # v1.40 calibration: engine trigger centers sat a constant
        # (+0.035, -0.028, +0.042) m off the caps (probe-measured via
        # getTrigger:getCenter). Bake the inverse into the anchors so the
        # hover boxes land exactly on the rendered buttons.
        return [
            round(-position[0] - 0.035, 6),
            round(-position[1] + 0.028, 6),
            round(position[2] - 0.042, 6),
        ]

    for button in panel_buttons:
        node_id = f"{MOD_ID}_panel_{button['suffix']}"
        panel_node_ids.append(node_id)
        node_rows.append(
            [
                node_id,
                *_vehicle_space(button["source_position"]),
                {
                    "collision": False,
                    "fixed": True,
                    "frictionCoef": 0.9,
                    "group": GROUP,
                    "nodeMaterial": "|NM_METAL",
                    "nodeWeight": PANEL_NODE_MASS_KG,
                    "selfCollision": False,
                    "staticCollision": False,
                },
            ]
        )
    # v1.39: the engine's trigger frame needs a healthy baseline - with the
    # neighbouring cap (7 cm) as idX the box basis degenerated and the
    # hover raycast never hit (probe-proven). Two dedicated frame nodes sit
    # 1.2 m along the wall and 1.2 m up from the top cap; every button uses
    # them as idX/idY, so all five click boxes share one well-conditioned
    # basis while still sitting exactly ON their own cap node.
    top_cap = _vehicle_space(panel_buttons[0]["source_position"])
    frame_specs = (
        (f"{MOD_ID}_panel_frame_x", [top_cap[0], top_cap[1] - 1.2, top_cap[2]]),
        (f"{MOD_ID}_panel_frame_y", [top_cap[0], top_cap[1], top_cap[2] + 1.2]),
    )
    frame_node_ids: list[str] = []
    for frame_node_id, frame_position in frame_specs:
        frame_node_ids.append(frame_node_id)
        node_rows.append(
            [
                frame_node_id,
                *[round(value, 6) for value in frame_position],
                {
                    "collision": False,
                    "fixed": True,
                    "frictionCoef": 0.9,
                    "group": GROUP,
                    "nodeMaterial": "|NM_METAL",
                    "nodeWeight": PANEL_NODE_MASS_KG,
                    "selfCollision": False,
                    "staticCollision": False,
                },
            ]
        )
    zero = {"x": 0, "y": 0, "z": 0}
    trigger_rows: list[list[Any]] = [
        [
            "id",
            "idRef:",
            "idX:",
            "idY:",
            "type",
            "size",
            "baseRotation",
            "rotation",
            "translation",
            "baseTranslation",
        ]
    ]
    link_rows: list[list[Any]] = [["triggerId:triggers2", "triggerInput", "inputAction"]]
    enabled_rows: list[list[Any]] = [["id"]]
    for index, button in enumerate(panel_buttons):
        trigger_id = f"panel_{button['suffix']}"
        action_name = f"{MOD_ID}_{button['suffix']}"
        trigger_rows.append(
            [
                trigger_id,
                panel_node_ids[index],
                frame_node_ids[0],
                frame_node_ids[1],
                "box",
                {"x": 0.07, "y": 0.07, "z": 0.07},
                dict(zero),
                dict(zero),
                dict(zero),
                dict(zero),
            ]
        )
        link_rows.append([trigger_id, "action0", action_name])
        enabled_rows.append([action_name])

    total_mass = (
        len(base_ids) * BASE_NODE_MASS_KG
        + (len(nodes) - len(base_ids)) * STRUCTURE_NODE_MASS_KG
        + len(cloth["nodes"]) * CLOTH_NODE_MASS_KG
        + (len(panel_buttons) + 2) * PANEL_NODE_MASS_KG
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
            [cloth["mesh"], [cloth_group]],
        ],
        "triggers2": trigger_rows,
        "triggerEventLinks2": link_rows,
        "actionsEnabled": enabled_rows,
        "nodes": node_rows,
        "beams": beam_rows,
        "triangles": triangle_rows,
    }
    return {MODEL_ID: part}, total_mass


def build_interaction(handoff: dict[str, Any]) -> dict[str, Any]:
    """Dashboard-style click actions for the panel's triggers2 buttons.

    onDown runs in the wash prop's Vehicle Lua on click - exactly the
    mechanism behind in-car dashboard controls - and forwards to the GE
    runtime with the prop's own object id.
    """

    actions: dict[str, Any] = {}
    for order, button in enumerate(handoff.get("panel_buttons", []), start=1):
        suffix = button["suffix"]
        actions[f"{MOD_ID}_{suffix}"] = {
            "order": float(order),
            "onDown": (
                "obj:queueGameEngineLua(string.format("
                f"\"extensions.ericrolph__cannon__car__wash_runtime.pressPanelButtonByVehicle(%d, '{suffix}')\""
                ", objectId))"
            ),
            "title": button["title"],
        }
    return {"fileversion": 2, "actions": actions}


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


def copy_mini_car() -> None:
    if not SOURCE_MINI_CAR_PATH.is_file():
        raise FileNotFoundError(f"mini car shape missing: {SOURCE_MINI_CAR_PATH}")
    shutil.copyfile(SOURCE_MINI_CAR_PATH, MINI_CAR_DAE_PATH)
    if not SOURCE_CANNON_PATH.is_file():
        raise FileNotFoundError(f"cannon shape missing: {SOURCE_CANNON_PATH}")
    shutil.copyfile(SOURCE_CANNON_PATH, CANNON_DAE_PATH)
    if not SOURCE_RAMP_FLAP_PATH.is_file():
        raise FileNotFoundError(f"ramp flap shape missing: {SOURCE_RAMP_FLAP_PATH}")
    shutil.copyfile(SOURCE_RAMP_FLAP_PATH, RAMP_FLAP_DAE_PATH)
    if not SOURCE_CARRIAGE_PATH.is_file():
        raise FileNotFoundError(f"carriage shape missing: {SOURCE_CARRIAGE_PATH}")
    shutil.copyfile(SOURCE_CARRIAGE_PATH, CARRIAGE_DAE_PATH)


def main() -> None:
    handoff = load_handoff()
    jbeam, total_mass = build_jbeam(handoff)
    materials = build_materials(handoff)

    copy_mini_car()
    write_json(VEHICLE_ROOT / f"{MODEL_ID}.jbeam", jbeam)
    write_json(
        VEHICLE_ROOT / f"{MODEL_ID}_default.interaction.json",
        build_interaction(handoff),
    )
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
                "cloth_nodes": len(handoff["cloth"]["nodes"]),
                "cloth_beams": len(handoff["cloth"]["beams"]),
                "cloth_triangles": len(handoff["cloth"]["triangles"]),
                "mass_kg": total_mass,
                "visual_sha256": handoff["visual"]["sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
